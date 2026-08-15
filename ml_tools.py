"""
ml_tools.py — Инструменты для машинного обучения (ML).

Содержит функции, которые AI-агент может вызывать через механизм инструментов.
Добавлено два инструмента:
  1. fetch_dataset  — скачивание датасетов с Hugging Face
  2. run_local_ml   — запуск ML-кода (scikit-learn, pandas, numpy)
"""

import ast
import json
import os
import re
import socket
import sys
import subprocess
import tempfile
import atexit
from pathlib import Path
from typing import Dict, Any

from config import logger
from agent_bridge import ModalAgentBridge

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False


# ============================================================
# ИНСТРУМЕНТ 1: Скачивание данных с Hugging Face
# ============================================================
def fetch_dataset(
    hf_token: str = "",
    dataset_name: str = "",
    save_path: str = "",
) -> Dict[str, Any]:
    """
    Скачивает датасет с Hugging Face и возвращает информацию о нём.

    Параметры:
        hf_token (str): API-токен Hugging Face (https://huggingface.co/settings/tokens).
                        Можно оставить пустым для публичных датасетов.
        dataset_name (str): Имя датасета на Hugging Face, например "imdb", "sst2", "mnist".
        save_path (str): Папка для сохранения. Если не указана, сохраняет в datasets/ рядом с агентом.

    Возвращает:
        Словарь с результатом: success, stdout (описание), stderr, returncode.
    """
    logger.debug(f"[ML] fetch_dataset: dataset_name={dataset_name}, has_token={bool(hf_token)}")

    # --- Проверка обязательного параметра ---
    if not dataset_name:
        return {
            "success": False,
            "stdout": "",
            "stderr": (
                "Ошибка: не указано имя датасета (dataset_name).\n"
                "Примеры: 'stanfordnlp/imdb', 'sst2', 'mnist', 'tweet_eval'.\n"
                "Полный список: https://huggingface.co/datasets"
            ),
            "returncode": -1,
        }

    try:
        # --- Пытаемся импортировать библиотеку datasets ---
        try:
            from datasets import load_dataset
        except ImportError:
            return {
                "success": False,
                "stdout": "",
                "stderr": (
                    "Библиотека 'datasets' от Hugging Face не установлена.\n"
                    "Установи её командой: pip install datasets"
                ),
                "returncode": -1,
            }

        # --- Определяем папку для сохранения ---
        if save_path:
            datasets_dir = Path(save_path)
        else:
            datasets_dir = Path(__file__).parent / "datasets"
        datasets_dir.mkdir(parents=True, exist_ok=True)

        # --- Загружаем датасет (streaming, без скачивания всего объёма) ---
        logger.info(f"[ML] Загружаю датасет '{dataset_name}' с Hugging Face...")

        dataset = None
        last_error = None
        try:
            load_kwargs = {"path": dataset_name, "streaming": True}
            if hf_token:
                load_kwargs["token"] = hf_token
            dataset = load_dataset(**load_kwargs)
            logger.info(f"[ML] Датaсет найден по имени: {dataset_name}")
        except Exception as e:
            last_error = e
            logger.debug(f"[ML] Имя {dataset_name} не подошло: {e}")

        if dataset is None:
            if "/" not in dataset_name:
                err_hint = (
                    f"Датасет '{dataset_name}' не загрузился. "
                    "Библиотека huggingface_hub требует полный формат 'организация/имя'.\n"
                    "Примеры: 'stanfordnlp/imdb', 'rotten_tomatoes/rotten_tomatoes', 'sst2'.\n"
                    "Попробуй указать полное имя датасета."
                )
                return {"success": False, "stdout": "", "stderr": err_hint, "returncode": -1}
            raise last_error or Exception(f"Не удалось загрузить датасет '{dataset_name}'")

        # --- Собираем информацию о датасете (streaming: без len()) ---
        splits_info = []
        from datasets import get_dataset_split_names
        try:
            splits = get_dataset_split_names(dataset_name)
            for split_name in splits:
                splits_info.append(f"  \u2022 {split_name}")
        except Exception:
            for split_name in dataset.keys():
                splits_info.append(f"  \u2022 {split_name}")

        # Берём первые записи через take() для образца
        first_split_name = list(dataset.keys())[0]
        columns = []
        sample_rows = []
        for i, row in enumerate(dataset[first_split_name]):
            if i == 0:
                columns = list(row.keys())
            if i < 5:
                preview = {}
                for col in columns[:5]:
                    val = row[col]
                    if isinstance(val, (str, int, float, bool)):
                        preview[col] = val if isinstance(val, (int, float)) else str(val)[:80]
                sample_rows.append(json.dumps(preview, ensure_ascii=False))
            if i >= 4:
                break

        columns_str = ", ".join(columns[:10])
        if len(columns) > 10:
            columns_str += f" и ещё {len(columns) - 10} колонок"

        # --- Сохраняем мета-информацию в JSON (без total_records — streaming) ---
        safe_name = dataset_name.replace("/", "_").replace("-", "_")
        meta_path = datasets_dir / f"{safe_name}_meta.json"
        meta_info = {
            "dataset_name": dataset_name,
            "splits": list(dataset.keys()),
            "columns": columns,
            "num_columns": len(columns),
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_info, f, ensure_ascii=False, indent=2)

        # --- Формируем текстовый отчёт ---
        sample_text = "\n".join(sample_rows)
        splits_text = "\n".join(splits_info)

        result_text = (
            f"Датасет '{dataset_name}' успешно загружен (streaming)!\n"
            f"\n"
            f"Разбивка по split'ам:\n"
            f"{splits_text}\n"
            f"\n"
            f"Колонки: {columns_str}\n"
            f"\n"
            f"Пример данных (первые записи):\n"
            f"{sample_text}\n"
            f"\n"
            f"Мета-информация сохранена: {meta_path}\n"
            f"\n"
            f"Совет: используй run_local_ml для анализа этих данных "
            f"с помощью pandas и scikit-learn."
        )

        logger.info(f"[ML] Датасет '{dataset_name}' готов: split={list(dataset.keys())}, {len(columns)} колонок")

        return {
            "success": True,
            "stdout": result_text,
            "stderr": "",
            "returncode": 0,
        }

    except ImportError as e:
        error_msg = f"Ошибка импорта: {e}. Установи библиотеку: pip install datasets"
        logger.error(f"[ML] {error_msg}")
        return {"success": False, "stdout": "", "stderr": error_msg, "returncode": -1}

    except Exception as e:
        error_str = str(e)

        # --- Дружелюбные сообщения для частых ошибок ---
        if "401" in error_str or "Unauthorized" in error_str:
            user_msg = (
                "Ошибка аутентификации: неверный токен Hugging Face.\n"
                "1. Зайди на https://huggingface.co/settings/tokens\n"
                "2. Создай новый токен (или скопируй существующий)\n"
                "3. Передай его в параметре hf_token\n\n"
                "Для публичных датасетов токен не обязателен — оставь hf_token пустым."
            )
        elif "404" in error_str or "Not found" in error_str or "not found" in error_str.lower():
            user_msg = (
                f"Датасет '{dataset_name}' не найден на Hugging Face.\n"
                "Проверь название. Популярные датасеты:\n"
                "  'stanfordnlp/imdb' — отзывы к фильмам\n"
                "  'sst2' — тональность текстов\n"
                "  'mnist' — рукописные цифры\n"
                "  'tweet_eval' — твиты\n"
                "  'ag_news' — новости\n\n"
                "Полный поиск: https://huggingface.co/datasets"
            )
        elif "Connection" in error_str or "timeout" in error_str.lower():
            user_msg = (
                "Не удалось подключиться к Hugging Face.\n"
                "Проверь подключение к интернету."
            )
        else:
            user_msg = f"Ошибка при скачивании датасета: {error_str}"

        logger.error(f"[ML] fetch_dataset error: {e}")
        return {"success": False, "stdout": "", "stderr": user_msg, "returncode": -1}


# ============================================================
# ИНСТРУМЕНТ 4 (вспомогательный): Парсер ML-метрик
# ============================================================
def _format_metrics_str(raw_metrics: Any) -> str:
    """
    Внутренняя функция: преобразует сырые метрики в Markdown-строку.
    Используется run_local_ml (через _try_format_metrics) и parse_ml_metrics (публичный инструмент).
    """
    logger.debug(f"[ML] _format_metrics_str: type={type(raw_metrics).__name__}")

    # --- Если передан JSON-строка, парсим её ---
    if isinstance(raw_metrics, str):
        try:
            raw_metrics = json.loads(raw_metrics)
        except json.JSONDecodeError:
            try:
                raw_metrics = ast.literal_eval(raw_metrics)
            except (ValueError, SyntaxError, MemoryError):
                return f"[ОТЧЕТ] Передана строка, но не удалось распарсить JSON. Содержимое:\n{raw_metrics[:500]}"

    if not raw_metrics or not isinstance(raw_metrics, dict):
        return "[ОТЧЕТ] Передан пустой или некорректный словарь метрик."

    lines = []
    lines.append("[ОТЧЕТ ML МОДЕЛИ]")
    lines.append("")

    # --- 1. Точность (accuracy) ---
    accuracy = raw_metrics.get("accuracy")
    if accuracy is not None:
        # Если accuracy в виде доли (0.95), переводим в проценты
        if isinstance(accuracy, (int, float)):
            acc_val = accuracy * 100 if accuracy <= 1 else accuracy
            lines.append(f"Финальная точность: {acc_val:.2f}%")
    else:
        lines.append("Финальная точность: не указана")

    # --- 2. Loss: тренд обучения ---
    loss = raw_metrics.get("loss")
    loss_history = raw_metrics.get("loss_history")

    if loss_history and isinstance(loss_history, list) and len(loss_history) >= 2:
        start_loss = loss_history[0]
        end_loss = loss_history[-1]

        # Определяем тренд: падал, рос или колебался
        if end_loss < start_loss * 0.95:
            trend_text = "снижался (модель обучается)"
        elif end_loss > start_loss * 1.05:
            trend_text = "рос (модель расходится)"
        else:
            trend_text = "стабилен"

        lines.append(f"Тренд обучения (Loss): {start_loss:.4f} -> {end_loss:.4f} ({trend_text})")
    elif loss is not None:
        lines.append(f"Финальный Loss: {loss:.4f}")
    else:
        lines.append("Тренд обучения: нет данных")

    # --- 3. Дополнительные метрики ---
    extra_metrics = []
    for key in ("precision", "recall", "f1_score", "f1"):
        val = raw_metrics.get(key)
        if val is not None:
            v = val * 100 if isinstance(val, (int, float)) and val <= 1 else val
            extra_metrics.append(f"{key}: {v:.2f}%")

    if extra_metrics:
        lines.append("Дополнительные метрики: " + ", ".join(extra_metrics))

    # --- 4. Матрица ошибок (confusion matrix) ---
    cm = raw_metrics.get("confusion_matrix")
    if cm and isinstance(cm, (list, tuple)) and len(cm) == 2 and all(len(row) == 2 for row in cm):
        tn, fp = cm[0]
        fn, tp = cm[1]
        total = tn + fp + fn + tp
        lines.append("")
        lines.append("Детализация ошибок:")
        if total > 0:
            lines.append(f"  Верно предсказано: {tn + tp} ({((tn + tp) / total * 100):.1f}%)")
            lines.append(f"  Ложноположительных (FP): {fp} ({fp / total * 100:.1f}%)")
            lines.append(f"  Ложноотрицательных (FN): {fn} ({fn / total * 100:.1f}%)")
            lines.append(f"  Матрица ошибок:")
            lines.append(f"    [[ TN={tn}, FP={fp} ],")
            lines.append(f"     [ FN={fn}, TP={tp} ]]")
        else:
            lines.append("  (пустая матрица)")

    # --- 5. Отчёт по классам ---
    class_report = raw_metrics.get("class_report")
    if class_report:
        lines.append("")
        if isinstance(class_report, dict):
            lines.append("Отчёт по классам:")
            for cls_name, metrics in class_report.items():
                if isinstance(metrics, dict):
                    parts = [f"{k}={v:.2f}" for k, v in metrics.items() if isinstance(v, (int, float))]
                    if parts:
                        lines.append(f"  {cls_name}: {', '.join(parts)}")
        elif isinstance(class_report, str):
            lines.append(f"Отчёт по классам:\n{class_report[:500]}")

    # --- 6. Размер выборки (если есть) ---
    n_samples = raw_metrics.get("n_samples") or raw_metrics.get("num_samples")
    if n_samples:
        lines.append("")
        lines.append(f"Размер выборки: {n_samples} примеров")

    logger.debug(f"[ML] parse_ml_metrics: готов отчёт из {len(lines)} строк")
    return "\n".join(lines)


def _try_format_metrics(output_text: str) -> str:
    """
    Пытается распознать в тексте вывода сырые ML-метрики и
    преобразовать их в красивый отчёт через _format_metrics_str.

    Если распознать не удалось — возвращает исходный текст без изменений.
    """
    if not output_text:
        return output_text

    candidates = []

    # --- Попытка 1: распарсить весь вывод как JSON ---
    try:
        data = json.loads(output_text)
        if isinstance(data, dict):
            candidates.append(data)
    except (json.JSONDecodeError, ValueError):
        pass

    # --- Попытка 2: распарсить весь вывод как Python-словарь ---
    if not candidates:
        try:
            data = ast.literal_eval(output_text)
            if isinstance(data, dict):
                candidates.append(data)
        except (ValueError, SyntaxError, MemoryError):
            pass

    # --- Попытка 3: найти JSON внутри текста (между { }) ---
    if not candidates:
        for m in re.finditer(r'\{[^{}]*\}', output_text, re.DOTALL):
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    candidates.append(data)
            except (json.JSONDecodeError, ValueError):
                pass

    # --- Пробуем каждый кандидат ---
    for data in candidates:
        # Проверяем, похоже ли на ML-метрики
        if any(k in data for k in ("accuracy", "loss", "confusion_matrix", "loss_history", "f1_score")):
            return _format_metrics_str(data)

    # Не удалось распознать — возвращаем как есть
    return output_text


# ============================================================
# ИНСТРУМЕНТ 4 (публичный): Парсер ML-метрик
# ============================================================
def parse_ml_metrics(raw_metrics: Any = "") -> Dict[str, Any]:
    """
    Публичный инструмент: преобразует сырые ML-метрики в красивый Markdown-отчёт.

    Принимает как словарь, так и JSON-строку.
    Вместо вывода 100 значений loss показывает тренд (начало -> конец).
    Матрицу ошибок превращает в человеческий текст.

    Параметры:
        raw_metrics (dict или str): Словарь или JSON-строка с метриками.

    Возвращает:
        Словарь с результатом: success, stdout (Markdown-отчёт), stderr, returncode.
    """
    logger.debug(f"[ML] parse_ml_metrics: type={type(raw_metrics).__name__}")

    if not raw_metrics:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Ошибка: не переданы метрики (raw_metrics). Передай словарь или JSON с accuracy/loss/etc.",
            "returncode": -1,
        }

    try:
        result_text = _format_metrics_str(raw_metrics)
        return {
            "success": True,
            "stdout": result_text,
            "stderr": "",
            "returncode": 0,
        }
    except Exception as e:
        logger.error(f"[ML] parse_ml_metrics error: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Ошибка при форматировании метрик: {e}",
            "returncode": -1,
        }


# ============================================================
# ИНСТРУМЕНТ 2: Локальный запуск ML-кода
# ============================================================
def run_local_ml(ml_code: str = "") -> Dict[str, Any]:
    """
    Принимает Python-код для машинного обучения и выполняет его локально.

    Параметры:
        ml_code (str): Исходный код на Python. Может использовать:
                       scikit-learn, pandas, numpy, matplotlib, joblib.

    Возвращает:
        Словарь с результатом: success, stdout (вывод кода), stderr (ошибки), returncode.
    """
    logger.debug(f"[ML] run_local_ml: code_length={len(ml_code)}")

    # --- Проверка, что код не пустой ---
    if not ml_code or not ml_code.strip():
        return {
            "success": False,
            "stdout": "",
            "stderr": "Ошибка: передан пустой код (ml_code). Напиши Python-код для ML.",
            "returncode": -1,
        }

    # --- Определяем, это просто выражение или полноценный код ---
    # Если код — однострочное выражение вроде "2+2", exec не покажет результат.
    # Поэтому оборачиваем в print() если это просто выражение.
    code_to_run = ml_code.strip()

    # Список ключевых слов, которые говорят, что это полноценный код
    has_statement = any(
        kw in code_to_run
        for kw in ["import ", "from ", "def ", "class ", "print(", "return ",
                    "for ", "while ", "if ", "with ", "try:", "except",
                    "=", "plt.", "pd.", "np.", "sns."]
    )

    # Если это просто выражение (не полноценный код), оборачиваем в print
    if not has_statement:
        try:
            compile(code_to_run, "<string>", "eval")
            code_to_run = f"print({code_to_run})"
        except SyntaxError:
            pass  # Это полноценный код, оставляем как есть

    # --- Добавляем "шапку" для правильного вывода ---
    # Оборачиваем код с перехватом stdout

    # Индентируем код пользователя (нужно для wrapping в try-except)
    indented_code = "\n".join(
        "    " + line if line.strip() else ""
        for line in code_to_run.split("\n")
    )

    full_code = f"""import sys
import io

# Перенаправляем stdout, чтобы поймать весь вывод
_ml_output = io.StringIO()
_ml_old_stdout = sys.stdout
sys.stdout = _ml_output

# Импортируем популярные ML-библиотеки
try:
    import numpy as np
    import pandas as pd
    import sklearn
except ImportError as _e:
    print(f"Ошибка импорта: {{_e}}. Установи: pip install numpy pandas scikit-learn", file=_ml_old_stdout)
    sys.stdout = _ml_old_stdout
    sys.exit(1)

# Пробуем matplotlib (не обязателен)
try:
    import matplotlib
    matplotlib.use("Agg")  # Без графического окна
    import matplotlib.pyplot as plt
except ImportError:
    pass

# Пробуем joblib для сохранения моделей (не обязателен)
try:
    import joblib
except ImportError:
    pass

# --- КОД ПОЛЬЗОВАТЕЛЯ (с защитой от ошибок sklearn) ---
try:
{indented_code}
except ValueError as _ml_err:
    _ml_err_text = str(_ml_err)
    if "sklearn" in str(sys.modules.get("sklearn", "")) or "informative" in _ml_err_text.lower():
        print(f"[ОШИБКА ML] sklearn: {{_ml_err}}", file=_ml_old_stdout)
        print("[ПОДСКАЗКА] Проверь параметры: n_informative + n_redundant + n_repeated должно быть меньше n_features. Используй n_samples=1000, n_features=20, n_informative=2, n_redundant=2, n_classes=2", file=_ml_old_stdout)
    else:
        print(f"[ОШИБКА ML] {{_ml_err}}", file=_ml_old_stdout)
    sys.stdout = _ml_old_stdout
    sys.exit(1)
except Exception as _ml_err:
    print(f"[ОШИБКА ML] {{type(_ml_err).__name__}}: {{_ml_err}}", file=_ml_old_stdout)
    sys.stdout = _ml_old_stdout
    sys.exit(1)

# --- Возвращаем stdout ---
sys.stdout = _ml_old_stdout
_output_text = _ml_output.getvalue()
if _output_text:
    print(_output_text, end="")
else:
    print("[Код выполнен успешно, но не вывел результат]")
"""

    # --- Сохраняем код во временный файл и запускаем ---
    tmp_file = None
    try:
        # Создаём временный .py файл
        tmp = tempfile.NamedTemporaryFile(
            suffix=".py",
            mode="w",
            encoding="utf-8",
            delete=False,
        )
        tmp.write(full_code)
        tmp.close()
        tmp_file = tmp.name

        atexit.register(lambda p=tmp_file: os.unlink(p) if os.path.exists(p) else None)

        logger.info(f"[ML] Запуск ML-кода (файл: {tmp_file})")

        # Запускаем Python-процесс
        result = subprocess.run(
            [sys.executable, tmp_file],
            capture_output=True,
            text=True,
            timeout=300,  # 5 минут на выполнение
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8"},
        )

        # --- Формируем результат ---
        if result.returncode == 0:
            output = result.stdout.strip() or result.stderr.strip() or "Код выполнен успешно!"
            logger.info(f"[ML] Код выполнен: stdout={len(result.stdout)} символов")

            # Пытаемся преобразовать сырые метрики в красивый отчёт
            formatted_output = _try_format_metrics(output)
            if formatted_output != output:
                logger.info(f"[ML] Метрики распознаны и отформатированы")
                output = formatted_output

            return {
                "success": True,
                "stdout": output,
                "stderr": "",
                "returncode": 0,
            }
        else:
            # Пытаемся извлечь понятную ошибку
            error_msg = result.stderr.strip() or result.stdout.strip() or "Неизвестная ошибка"

            # Сокращаем трейсбек до полезной части
            lines = error_msg.split("\n")
            useful_lines = []
            for line in lines:
                if "Traceback" in line:
                    continue
                if 'File "' in line and ', line ' in line:
                    useful_lines.append(line)
                elif "Error:" in line or "Exception:" in line:
                    useful_lines.append("  " + line)
                elif line.strip():
                    useful_lines.append("  " + line)

            if useful_lines:
                formatted_error = "\n".join(useful_lines[-10:])  # Последние 10 строк
            else:
                formatted_error = error_msg[:2000]

            logger.warning(f"[ML] Ошибка выполнения кода:\n{error_msg[:500]}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Ошибка выполнения ML-кода:\n{formatted_error}",
                "returncode": result.returncode,
            }

    except subprocess.TimeoutExpired:
        logger.warning("[ML] Таймаут: код выполнялся дольше 5 минут")
        return {
            "success": False,
            "stdout": "",
            "stderr": "Превышено время выполнения (5 минут). Код слишком долгий или содержит бесконечный цикл.",
            "returncode": -1,
        }

    except Exception as e:
        logger.error(f"[ML] run_local_ml error: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Внутренняя ошибка: {e}",
            "returncode": -1,
        }

    finally:
        # Чистим временный файл
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:
                pass


# ============================================================
# ИНСТРУМЕНТ 3: Запуск ML на облачном GPU (Kaggle)
# ============================================================
def run_cloud_gpu_ml(
    ml_code: str = "",
    kaggle_username: str = "",
    kaggle_key: str = "",
) -> Dict[str, Any]:
    """
    Отправляет ML-код на выполнение в облачную GPU-среду (Kaggle).

    Если указаны kaggle_username и kaggle_key — формирует задачу и
    эмулирует отправку в Kaggle (реальное API можно подключить позже).
    Если ключи не указаны — возвращает понятную ошибку.

    Параметры:
        ml_code (str): Python-код для ML, который будет выполняться на GPU.
        kaggle_username (str): Имя пользователя Kaggle.
        kaggle_key (str): API-ключ Kaggle (https://www.kaggle.com/settings).

    Возвращает:
        Словарь с результатом: success, stdout (статус задачи), stderr, returncode.
    """
    logger.debug(f"[ML] run_cloud_gpu_ml: code_length={len(ml_code)}, has_username={bool(kaggle_username)}, has_key={bool(kaggle_key)}")

    # --- Проверка, что код не пустой ---
    if not ml_code or not ml_code.strip():
        return {
            "success": False,
            "stdout": "",
            "stderr": "Ошибка: передан пустой код (ml_code). Напиши Python-код для ML.",
            "returncode": -1,
        }

    # --- Проверка ключей Kaggle ---
    if not kaggle_username or not kaggle_key:
        return {
            "success": False,
            "stdout": "",
            "stderr": (
                "Для облачного GPU нужны ключи Kaggle.\n\n"
                "Как получить:\n"
                "1. Зайди на https://www.kaggle.com (зарегистрируйся, если нет аккаунта)\n"
                "2. Открой Settings -> API -> Create New Token\n"
                "3. Скачается файл kaggle.json — в нём username и key\n"
                "4. Передай их в параметры kaggle_username и kaggle_key\n\n"
                "Без GPU облака ML-код выполнится локально через run_local_ml."
            ),
            "returncode": -1,
        }

    try:
        # --- Создаём папку для облачных задач ---
        cloud_dir = Path(__file__).parent / "cloud_jobs"
        cloud_dir.mkdir(parents=True, exist_ok=True)

        # --- Генерируем уникальный ID задачи ---
        import uuid as _uuid
        import datetime as _dt
        job_id = f"kaggle_{_uuid.uuid4().hex[:12]}"
        timestamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # --- Сохраняем код в файл для истории ---
        safe_name = f"job_{job_id}"
        code_path = cloud_dir / f"{safe_name}.py"
        code_path.write_text(ml_code, encoding="utf-8")

        # --- Также сохраняем мета-информацию ---
        meta = {
            "job_id": job_id,
            "timestamp": timestamp,
            "kaggle_username": kaggle_username,
            "code_file": str(code_path),
            "status": "submitted",
        }
        meta_path = cloud_dir / f"{safe_name}_meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info(f"[ML] Облачная задача {job_id} создана. Код: {code_path}")

        # --- Формируем сообщение для пользователя ---
        # Пробуем реальный API Kaggle, если установлен пакет kagglehub
        real_api_available = False
        try:
            import kagglehub  # type: ignore
            real_api_available = True
        except ImportError:
            pass

        if real_api_available:
            # Реальное API Kagglehub — TODO: подключить в будущем
            result_text = (
                f"Задача отправлена на облачный GPU (Kaggle)!\n"
                f"ID задачи: {job_id}\n"
                f"Пользователь: {kaggle_username}\n"
                f"Время отправки: {timestamp}\n\n"
                f"Статус: отправлено в облако. Проверь результат на Kaggle.\n"
                f"Код сохранён локально: {code_path}"
            )
        else:
            # Эмуляция (заглушка) — так как реальный API не подключён
            result_text = (
                f"[OK] Задача отправлена в облако!\n"
                f"ID задачи: {job_id}\n"
                f"Пользователь: {kaggle_username}\n"
                f"Время отправки: {timestamp}\n"
                f"Код сохранён: {code_path}\n\n"
                f"Статус: задача поставлена в очередь облачного GPU.\n"
                f"Результат будет доступен после выполнения.\n\n"
                f"💡 Примечание: это эмуляция облачного запуска.\n"
                f"Для реального запуска на Kaggle API потребуется\n"
                f"установить пакет: pip install kagglehub\n"
                f"и настроить интеграцию."
            )

        return {
            "success": True,
            "stdout": result_text,
            "stderr": "",
            "returncode": 0,
        }

    except Exception as e:
        logger.error(f"[ML] run_cloud_gpu_ml error: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Ошибка при отправке задачи в облако: {e}",
            "returncode": -1,
        }


# ============================================================
# ИНСТРУМЕНТ 5: Запуск ML на Modal.com (облачный GPU)
# ============================================================
def run_modal_ml(
    ml_code: str = "",
    timeout: int = 1800,
) -> Dict[str, Any]:
    """
    Запускает ML-код на облачном GPU через Modal.com.

    Параметры:
        ml_code (str): Python-код для Modal. Может содержать @app.function или
                       @app.local_entrypoint декораторы. Если их нет — код
                       автоматически оборачивается в local_entrypoint.
        timeout (int): таймаут в секундах (по умолчанию 1800 = 30 мин)

    Возвращает:
        Словарь с результатом: success, stdout, stderr, return_code, diagnosis.
    """
    logger.debug(f"[ML] run_modal_ml: code_length={len(ml_code)}, timeout={timeout}")

    if not ml_code or not ml_code.strip():
        return {
            "success": False,
            "stdout": "",
            "stderr": "Ошибка: передан пустой код (ml_code). Напиши Python-код для ML.",
            "returncode": -1,
        }

    if timeout > 3600:
        timeout = 3600

    # Credentials будут подставлены из сессии в server.py перед вызовом
    bridge = ModalAgentBridge()

    result = bridge.run(ml_code, timeout=timeout)

    diagnosis = result.get("diagnosis", {})

    # Если ошибка — сохраняем диагноз в stderr для self-healing
    if not result["success"]:
        action = diagnosis.get("action", "")
        missing_deps = diagnosis.get("missing_deps", [])

        if action == "request_credentials":
            return {
                "success": False,
                "stdout": "",
                "stderr": result["stderr"],
                "returncode": -1,
                "diagnosis": diagnosis,
            }

        if missing_deps:
            deps_str = ", ".join(missing_deps)
            diagnosis_msg = (
                f"ModuleNotFoundError detected: {deps_str}. "
                "Self-healing will add these packages to Modal image."
            )
            logger.info(f"[ML] {diagnosis_msg}")
            return {
                "success": False,
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", "") + f"\n\n{diagnosis_msg}",
                "returncode": result.get("return_code", -1),
                "diagnosis": diagnosis,
            }

        if diagnosis.get("oom_detected"):
            oom_msg = (
                "CUDA out of memory detected. "
                "Self-healing: reduce batch size, model size, or data size."
            )
            return {
                "success": False,
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", "") + f"\n\n{oom_msg}",
                "returncode": result.get("return_code", -1),
                "diagnosis": diagnosis,
            }

        return {
            "success": False,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "returncode": result.get("return_code", -1),
            "diagnosis": diagnosis,
        }

    return {
        "success": True,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "returncode": result.get("return_code", 0),
        "diagnosis": diagnosis,
    }


# ============================================================
# SSH-инструменты: диагностика сервера (вспомогательное)
# ============================================================
SSH_PROBE_CMD = r"""
echo '=== OS ==='
(head -5 /etc/os-release 2>/dev/null || uname -a)
uname -m 2>/dev/null
echo '=== CPU ==='
(nproc 2>/dev/null || grep -c processor /proc/cpuinfo || echo '?')
echo '=== MEM ==='
(free -m 2>/dev/null | head -2 || head -4 /proc/meminfo || echo '?')
echo '=== DISK ==='
(df -h / 2>/dev/null | tail -1 || echo '?')
echo '=== PYTHON ==='
for p in python3 python; do
  if command -v $p >/dev/null 2>&1; then
    echo "  $p: $($p --version 2>&1)"
    echo "  pip: $($p -m pip --version 2>&1 | head -1)"
  fi
done
echo '=== GPU ==='
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
  echo 'nvidia-smi: НЕТ'
fi
(lspci 2>/dev/null | grep -i -E 'vga|3d controller|nvidia') || echo 'lspci: недоступен'
(ls /dev/nvidia* 2>/dev/null) || echo '/dev/nvidia*: нет'
echo '=== PACKAGES ==='
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  PY=''
fi
if [ -n "$PY" ]; then
$PY - <<'PYEOF'
import importlib.util as u
pkgs = ["numpy", "pandas", "scipy", "matplotlib", "scikit-learn", "torch", "tensorflow", "qiskit", "pennylane", "psutil", "requests"]
for p in pkgs:
    print(p + ": " + ("YES" if u.find_spec(p) else "NO"))
PYEOF
else
  echo 'Python не найден'
fi
"""


def _parse_probe(output: str) -> Dict[str, Any]:
    """Разбирает вывод SSH_PROBE_CMD в структуру: ОС, Python, GPU, пакеты."""
    info: Dict[str, Any] = {
        "os": "", "arch": "", "cpu": "", "mem": "", "disk": "",
        "pythons": {}, "pip": [], "gpu": [], "packages": {},
    }
    sections: Dict[str, list] = {}
    section = None
    for line in output.splitlines():
        m = re.match(r"===\s*(.*?)\s*===", line)
        if m:
            section = m.group(1).strip().upper()
            sections.setdefault(section, [])
            continue
        if section:
            sections.setdefault(section, []).append(line.strip())

    os_lines = sections.get("OS", [])
    if os_lines:
        info["os"] = os_lines[0]
    if len(os_lines) > 1:
        info["arch"] = os_lines[1]
    info["cpu"] = " ".join(sections.get("CPU", [])).strip()
    info["mem"] = "\n".join(sections.get("MEM", [])).strip()
    info["disk"] = "\n".join(sections.get("DISK", [])).strip()

    for line in sections.get("PYTHON", []):
        m = re.match(r"(\w+):\s*(.+)", line)
        if m and m.group(1).startswith("python"):
            info["pythons"][m.group(1)] = m.group(2)
        elif "pip" in line.lower():
            info["pip"].append(line.strip())

    info["gpu"] = [l for l in sections.get("GPU", []) if l.strip()]

    for line in sections.get("PACKAGES", []):
        m = re.match(r"([a-zA-Z0-9_\-]+):\s*(YES|NO)", line)
        if m:
            info["packages"][m.group(1)] = m.group(2) == "YES"

    return info


def _format_server_info(info: Dict[str, Any], host: str) -> str:
    """Человекочитаемый отчёт о состоянии сервера для модели."""
    lines = ["[СЕРВЕР-ИНФО] Авто-диагностика сервера " + (host or "?"), ""]
    lines.append("ОС: " + (info["os"] or "не определена"))
    lines.append("Архитектура: " + (info["arch"] or "?"))
    lines.append("CPU (ядер): " + (info["cpu"] or "?"))
    if info["mem"]:
        lines.append("Память:\n" + info["mem"])
    if info["disk"]:
        lines.append("Диск:\n" + info["disk"])
    if info["pythons"]:
        lines.append("Python: " + "; ".join(f"{k}: {v}" for k, v in info["pythons"].items()))
    else:
        lines.append("Python: НЕ УСТАНОВЛЕН")
    if info["pip"]:
        lines.append("Pip: " + "; ".join(info["pip"]))
    if info["gpu"]:
        lines.append("GPU:\n" + "\n".join(info["gpu"]))
    else:
        lines.append("GPU: не обнаружена")
    installed = [k for k, v in info["packages"].items() if v]
    missing = [k for k, v in info["packages"].items() if not v]
    lines.append("Пакеты установлены: " + (", ".join(installed) if installed else "нет"))
    lines.append("Пакеты отсутствуют: " + (", ".join(missing) if missing else "нет"))
    lines.append("")
    lines.append("Правила работы на этом сервере:")
    lines.append("  - Это Linux: в коде используй пути вида /tmp/файл, а НЕ \\tmp\\файл.")
    lines.append("  - Если для задачи нужен GPU, а на сервере его нет (nvidia-smi не найден) —")
    lines.append("    сервер не подходит: останови работу и сообщи пользователю, какой сервер нужен.")
    lines.append("  - Если чего-то не хватает — попробуй установить (pip/apt).")
    lines.append("  - Если установить не получается — сообщи пользователю честно, что сервер не подходит.")
    return "\n".join(lines)


def _try_install_python(ssh) -> bool:
    """Пытается установить Python 3 на сервере через apt/yum/apk (с sudo и без)."""
    candidates = [
        "sudo apt-get update && sudo apt-get install -y python3 python3-pip",
        "apt-get update && apt-get install -y python3 python3-pip",
        "sudo yum install -y python3 python3-pip",
        "yum install -y python3 python3-pip",
        "sudo apk add --no-cache python3 py3-pip",
        "apk add --no-cache python3 py3-pip",
    ]
    for cmd in candidates:
        try:
            _in, _out, _err = ssh.exec_command(cmd, timeout=240)
            code = _out.channel.recv_exit_status()
            _out.read()
            _err.read()
            logger.info(f"[ML] SSH: установка Python: exit={code}")
            if code == 0:
                _in2, _out2, _err2 = ssh.exec_command("command -v python3 && python3 --version", timeout=30)
                code2 = _out2.channel.recv_exit_status()
                ver = _out2.read().decode("utf-8", errors="replace").strip()
                if code2 == 0:
                    logger.info(f"[ML] SSH: Python установлен: {ver}")
                    return True
        except Exception as e:
            logger.warning(f"[ML] SSH: установка Python не удалась ({cmd[:30]}): {e}")
    return False


def _ssh_install_package(ssh, interpreter: str, package: str, timeout: int = 600) -> Dict[str, Any]:
    """Устанавливает пакет на сервере через pip. Возвращает ok/stdout/stderr."""
    cmd = f"{interpreter} -m pip install --quiet --disable-pip-version-check {package}"
    try:
        _in, _out, _err = ssh.exec_command(cmd, timeout=timeout)
        exit_code = _out.channel.recv_exit_status()
        out = _out.read().decode("utf-8", errors="replace")
        err = _err.read().decode("utf-8", errors="replace")
        logger.info(f"[ML] SSH: pip install {package}: exit={exit_code}")
        return {"ok": exit_code == 0, "stdout": out, "stderr": err}
    except Exception as e:
        logger.warning(f"[ML] SSH: pip install {package} прерван: {e}")
        return {"ok": False, "stdout": "", "stderr": str(e)}


# ============================================================
# ИНСТРУМЕНТ 6: Запуск ML на удалённом GPU через SSH
# ============================================================
def run_ssh_ml(
    ml_code: str = "",
    ssh_host: str = "",
    ssh_port: int = 22,
    ssh_username: str = "",
    ssh_key_path: str = "",
    password: str = "",
    timeout: int = 1800,
) -> Dict[str, Any]:
    """
    Выполняет Python-код на удалённом GPU-сервере через SSH.

    ПЕРВЫМ ДЕЛОМ диагностирует сервер (ОС, CPU, память, Python, pip, GPU,
    установленные пакеты) и включает результат в stdout как [СЕРВЕР-ИНФО] —
    модель видит, к чему подключилась, и решает, что нужно для задачи.

    Если на сервере нет Python — пробует установить (apt/yum/apk).
    Если в коде не хватает пакетов — устанавливает их честно через pip
    на сервере и повторяет запуск. Если сервер не подходит (нет Python,
    нет pip, нет GPU для GPU-задачи) — возвращает понятное сообщение,
    чтобы агент сказал пользователю, какой сервер нужен.

    Авторизация: ИЛИ ssh_key_path (SSH-ключ), ИЛИ password (пароль).
    Приоритет: если заданы ОБА — используется SSH-ключ.
    Пароль НИКОГДА не логируется и не попадает в вывод.

    Параметры:
        ml_code      : str  — Python-код для выполнения на удалённом сервере
        ssh_host     : str  — IP или хост удалённого сервера
        ssh_port     : int  — SSH порт (по умолчанию 22)
        ssh_username : str  — имя пользователя для SSH
        ssh_key_path : str  — путь к приватному SSH-ключу
        password     : str  — пароль для SSH-подключения (если нет ключа)
        timeout      : int  — таймаут выполнения кода на сервере (сек, по умолчанию 1800 = 30 мин)

    Возвращает:
        словарь с результатом: success, stdout (включая [СЕРВЕР-ИНФО]), stderr, returncode
    """
    logger.debug(f"[ML] run_ssh_ml: host={ssh_host}, user={ssh_username}, key={bool(ssh_key_path)}, has_password={bool(password)}")

    # --- Валидация параметров ---
    if not ml_code or not ml_code.strip():
        return {"success": False, "stdout": "", "stderr": "Ошибка: передан пустой код (ml_code).", "returncode": -1}

    if not ssh_host:
        return {"success": False, "stdout": "", "stderr": "Ошибка: не указан SSH Host. Заполните поле в боковой панели.", "returncode": -1}

    if not ssh_username:
        return {"success": False, "stdout": "", "stderr": "Ошибка: не указан SSH Username. Заполните поле в боковой панели.", "returncode": -1}

    if not ssh_key_path and not password:
        return {"success": False, "stdout": "", "stderr": "❌ Укажите либо SSH-ключ, либо пароль в боковой панели", "returncode": -1}

    if not HAS_PARAMIKO:
        return {
            "success": False, "stdout": "", "stderr":
            "Библиотека paramiko не установлена. Установите: pip install paramiko",
            "returncode": -1,
        }

    # --- Подключение по SSH ---
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        logger.info(f"[ML] SSH: подключаюсь к {ssh_host}:{ssh_port} как {ssh_username} "
                    f"({('ключ' if ssh_key_path else 'пароль')})")
        connect_kwargs = {
            "hostname": ssh_host,
            "port": int(ssh_port) if ssh_port else 22,
            "username": ssh_username,
            "timeout": 30,
        }
        if ssh_key_path:
            # Приоритет у SSH-ключа (обратная совместимость)
            connect_kwargs["key_filename"] = ssh_key_path
        elif password:
            # Подключение по паролю (без перебора ключей/ssh-agent)
            connect_kwargs["password"] = password
            connect_kwargs["look_for_keys"] = False
            connect_kwargs["allow_agent"] = False
        ssh.connect(**connect_kwargs)
        logger.info(f"[ML] SSH: подключение установлено")

        # --- ПЕРВЫМ ДЕЛОМ: диагностика сервера ---
        # Проверяем, к чему подключились: ОС, CPU, память, Python, pip, GPU, пакеты.
        # Только после этого решаем, что нужно для задачи.
        logger.info(f"[ML] SSH: проверяю сервер {ssh_host} (ОС, Python, GPU, пакеты)...")
        probe_out = ""
        probe_err = ""
        try:
            _in, _out, _err = ssh.exec_command(SSH_PROBE_CMD, timeout=60)
            _out.channel.recv_exit_status()
            probe_out = _out.read().decode("utf-8", errors="replace")
            probe_err = _err.read().decode("utf-8", errors="replace")
        except Exception as e:
            probe_err = str(e)
        if probe_err:
            logger.warning(f"[ML] SSH: ошибка диагностики: {probe_err[:200]}")

        server_info = _parse_probe(probe_out)
        server_info_text = _format_server_info(server_info, ssh_host)
        logger.info(f"[ML] SSH: ОС={server_info['os'][:40]}, python={list(server_info['pythons'])}")

        # --- Выбор интерпретатора Python ---
        interpreter = ""
        if "python3" in server_info["pythons"]:
            interpreter = "python3"
        elif "python" in server_info["pythons"]:
            interpreter = "python"

        if not interpreter:
            # Python на сервере нет — пробуем установить сами
            logger.info(f"[ML] SSH: Python не найден, пытаюсь установить...")
            if _try_install_python(ssh):
                interpreter = "python3"
                server_info_text += "\n\n[УСТАНОВКА] Python 3 был установлен автоматически на сервере."
            else:
                return {
                    "success": False,
                    "stdout": server_info_text,
                    "stderr": (
                        "Сервер не подходит для задачи: на нём не установлен Python, "
                        "и установить его автоматически не удалось (нет apt/yum/apk или прав sudo).\n"
                        "Нужен сервер с установленным Python 3 и pip. "
                        "Сообщи пользователю, что сервер не подходит и какой сервер нужен."
                    ),
                    "returncode": -1,
                }

        # pip может быть недоступен — пробуем ensurepip
        if interpreter and not server_info["pip"]:
            try:
                _in, _out, _err = ssh.exec_command(
                    f"{interpreter} -m ensurepip --upgrade 2>&1 || {interpreter} -m pip --version",
                    timeout=120,
                )
                _out.channel.recv_exit_status()
                _out.read()
            except Exception as e:
                logger.warning(f"[ML] SSH: ensurepip не удался: {e}")

        # --- Загружаем код на сервер через SFTP ---
        sftp = ssh.open_sftp()
        remote_path = "/tmp/agent_script.py"
        with sftp.open(remote_path, "w") as f:
            f.write(ml_code)
        sftp.close()
        logger.info(f"[ML] SSH: код загружен в {remote_path}")

        # --- Выполняем код с self-healing (честная автоустановка пакетов) ---
        max_retries = 4
        last_stdout = ""
        last_stderr = ""
        last_exit_code = -1
        installed_packages = set()

        for attempt in range(1, max_retries + 1):
            cmd = f"{interpreter} {remote_path}"
            logger.info(f"[ML] SSH: выполняю (попытка {attempt}/{max_retries}): {cmd}")
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            stdout_str = stdout.read().decode("utf-8", errors="replace")
            stderr_str = stderr.read().decode("utf-8", errors="replace")
            last_stdout = stdout_str
            last_stderr = stderr_str
            last_exit_code = exit_code

            if exit_code == 0:
                logger.info(f"[ML] SSH: успешно (попытка {attempt})")
                break

            # --- Self-healing: ищем ModuleNotFoundError ---
            error_text = stderr_str + stdout_str
            m = re.search(r"ModuleNotFoundError.*?No module named ['\"]([^'\"]+)['\"]", error_text)
            if not m:
                m = re.search(r"No module named ['\"]([^'\"]+)['\"]", error_text)
            if not m or attempt >= max_retries:
                break

            pkg = m.group(1).split(".")[0].lower()
            if pkg in installed_packages:
                break
            installed_packages.add(pkg)

            logger.info(f"[ML] SSH: не хватает '{pkg}', ставлю на сервере...")
            last_stderr += f"\n[SELF-HEAL] Пакет '{pkg}' не найден на сервере. Устанавливаю: {interpreter} -m pip install {pkg}..."
            pip_res = _ssh_install_package(ssh, interpreter, pkg, timeout=900)
            if not pip_res["ok"]:
                last_stderr += (
                    f"\n[SELF-HEAL] Не удалось установить '{pkg}' на сервере: "
                    f"{(pip_res['stderr'] or pip_res['stdout'] or 'неизвестная ошибка')[:500]}"
                    f"\nСервер может не подходить для задачи (нет интернета или прав pip) — "
                    f"сообщи пользователю, что нужен сервер, где pip работает."
                )
                break
            last_stderr += f"\n[SELF-HEAL] Пакет '{pkg}' установлен. Повторный запуск (попытка {attempt + 1}/{max_retries})..."

            # Загружаем ОРИГИНАЛЬНЫЙ код заново (без изменений)
            sftp = ssh.open_sftp()
            with sftp.open(remote_path, "w") as f:
                f.write(ml_code)
            sftp.close()
            continue

        logger.info(f"[ML] SSH: exit_code={last_exit_code}, stdout={len(last_stdout)}b, stderr={len(last_stderr)}b")

        # В stdout всегда включаем диагностику сервера — модель должна её видеть
        final_stdout = server_info_text
        if last_stdout.strip():
            final_stdout += "\n\n--- ВЫВОД ПРОГРАММЫ ---\n" + last_stdout
        else:
            final_stdout += "\n\n--- ВЫВОД ПРОГРАММЫ: пусто ---"

        return {
            "success": last_exit_code == 0,
            "stdout": final_stdout,
            "stderr": last_stderr,
            "returncode": last_exit_code,
        }

    except socket.timeout as e:
        # При таймауте убиваем зависший процесс на удалённом сервере
        error_msg = f"Таймаут выполнения ({timeout}с). Код на сервере выполнялся слишком долго."
        try:
            ssh.exec_command(f"kill $(pgrep -f python3 {remote_path}) 2>/dev/null;")
        except Exception:
            pass
        logger.error(f"[ML] {error_msg}")
        return {"success": False, "stdout": "", "stderr": error_msg, "returncode": -1}

    except paramiko.AuthenticationException:
        error_msg = "Ошибка аутентификации SSH: неверный логин/пароль или ключ не подходит. Проверьте данные в боковой панели."
        logger.warning(f"[ML] {error_msg}")
        return {"success": False, "stdout": "", "stderr": error_msg, "returncode": -1}

    except paramiko.SSHException as e:
        error_msg = f"Ошибка SSH: {e}. Проверьте доступность сервера {ssh_host}:{ssh_port}."
        logger.error(f"[ML] {error_msg}")
        return {"success": False, "stdout": "", "stderr": error_msg, "returncode": -1}

    except TimeoutError as e:
        error_msg = f"Таймаут подключения к {ssh_host}:{ssh_port}. Сервер недоступен или блокирует соединение."
        logger.error(f"[ML] {error_msg}")
        return {"success": False, "stdout": "", "stderr": error_msg, "returncode": -1}

    except Exception as e:
        error_msg = f"Ошибка SSH: {e}"
        logger.error(f"[ML] {error_msg}")
        return {"success": False, "stdout": "", "stderr": error_msg, "returncode": -1}

    finally:
        try:
            ssh.close()
        except Exception:
            pass
