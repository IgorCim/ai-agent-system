"""
neuro_tools.py — Инструменты для нейроморфного программирования (SNN).

Содержит функции, которые AI-агент может вызывать через механизм инструментов:
  1. run_neuro_check — проверка нейро-окружения (какие SNN-библиотеки стоят)
  2. run_neuro_ml    — запуск Python-кода в нейро-окружении (Lava, Akida, PyNN,
                       Brian2, snnTorch, Nengo, Rockpool, BindsNET, Sinabs, JAX)
                       с авто-установкой недостающих пакетов

Нейроморфные библиотеки установлены в системный Python (тот же, которым
запущен агент), поэтому по умолчанию используется sys.executable.
"""

import io
import os
import re
import subprocess
import sys
import tempfile
import atexit
from pathlib import Path
from typing import Dict, Any, Optional

from config import logger

# Нейро-окружение по умолчанию: системный Python агента
# (в нём установлены Lava, Akida, PyNN, Brian2, snnTorch, Nengo, Rockpool и т.д.)
NEURO_DEFAULT_PYTHON = sys.executable

# Пакеты для диагностики: имя модуля → что показать пользователю
NEURO_PACKAGES = {
    "lava": "Lava (Intel Loihi)",
    "akida": "Akida (BrainChip)",
    "cnn2snn": "cnn2snn (Akida конвертер)",
    "quantizeml": "quantizeml (Akida)",
    "pyNN": "PyNN",
    "brian2": "Brian2",
    "snntorch": "snnTorch",
    "nengo": "Nengo",
    "rockpool": "Rockpool",
    "bindsnet": "BindsNET",
    "sinabs": "Sinabs (DVS/события)",
    "jax": "JAX (GPU/TPU)",
    "torch": "PyTorch",
    "keras": "Keras",
    "tensorflow": "TensorFlow",
    "numpy": "numpy",
    "matplotlib": "matplotlib",
}

# Известные соответствия "имя модуля → имя pip-пакета"
_PIP_NAMES = {
    "lava": "lava-nc",
    "pyNN": "pyNN",
    "brian2": "brian2",
    "snntorch": "snntorch",
    "akida": "akida",
    "cnn2snn": "cnn2snn",
    "quantizeml": "quantizeml",
    "nengo": "nengo",
    "rockpool": "rockpool",
    "bindsnet": "bindsnet",
    "sinabs": "sinabs",
    "jax": "jax",
    "jaxlib": "jaxlib",
}

_MAX_OUTPUT_LEN = 8000
_MAX_INSTALL_RETRIES = 3


# ============================================================
# Внутренние помощники
# ============================================================
def _find_neuro_python(neuro_python_path: str = "") -> Optional[str]:
    """Находит python.exe нейро-окружения.

    Принимает: путь к python.exe или к папке с .venv внутри.
    Если ничего не указано — использует системный Python агента
    (в нём установлены все SNN-библиотеки).
    """
    if neuro_python_path and neuro_python_path.strip():
        p = Path(neuro_python_path.strip()).expanduser()
        if p.name.lower() in ("python.exe", "python"):
            if p.is_file():
                return str(p)
            return None
        candidates = [p / ".venv" / "Scripts" / "python.exe", p / "venv" / "Scripts" / "python.exe"]
        for c in candidates:
            try:
                if c.is_file():
                    return str(c)
            except OSError:
                continue
        return None
    return NEURO_DEFAULT_PYTHON


def _run_process(
    python_path: str,
    script_path: str,
    timeout: int,
    cwd: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Запускает скрипт указанным python и возвращает результат."""
    env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [python_path, script_path],
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=cwd,
    )


def _extract_missing_module(text: str) -> Optional[str]:
    """Извлекает имя отсутствующего модуля из текста ошибки."""
    m = re.search(r"No module named ['\"]([^'\"]+)['\"]", text)
    if not m:
        return None
    mod = m.group(1)
    # Берём верхний уровень: "lava.magma" → "lava"
    return mod.split(".")[0] if mod else None


def _pip_install(python_path: str, module_name: str) -> bool:
    """Устанавливает pip-пакет в нейро-окружение. Возвращает успех."""
    pkg = _PIP_NAMES.get(module_name, module_name)
    logger.info(f"[NEURO] Авто-установка пакета {pkg} в нейро-окружение")
    try:
        res = subprocess.run(
            [python_path, "-m", "pip", "install", "--disable-pip-version-check", pkg],
            capture_output=True,
            text=True,
            timeout=600,
            encoding="utf-8",
            errors="replace",
        )
        ok = res.returncode == 0
        if not ok:
            logger.warning(f"[NEURO] pip install {pkg} failed: {res.stderr[-500:]}")
        return ok
    except Exception as e:
        logger.error(f"[NEURO] pip install {pkg} error: {e}")
        return False


def _cap_output(text: str) -> str:
    if text and len(text) > _MAX_OUTPUT_LEN:
        return text[:_MAX_OUTPUT_LEN] + "\n...[вывод обрезан, показано начало]"
    return text


def _fmt_error(stderr: str) -> str:
    """Сокращает трейсбек до полезной части."""
    lines = stderr.split("\n")
    useful = []
    for line in lines:
        if "Traceback" in line:
            continue
        if 'File "' in line and ", line " in line:
            useful.append(line)
        elif "Error:" in line or "Exception:" in line:
            useful.append("  " + line)
        elif line.strip():
            useful.append("  " + line)
    if useful:
        return "\n".join(useful[-10:])
    return stderr[:2000]


# ============================================================
# ИНСТРУМЕНТ 1: Проверка нейро-окружения
# ============================================================
def run_neuro_check(neuro_python_path: str = "") -> Dict[str, Any]:
    """
    Проверяет нейро-окружение: версию Python и список установленных
    нейроморфных библиотек (Lava, Akida, PyNN, Brian2, snnTorch, Nengo,
    Rockpool, BindsNET, Sinabs, JAX, PyTorch и др.).
    Возвращает блок [НЕЙРО-ИНФО] с результатами.

    Параметры:
        neuro_python_path (str): Путь к python.exe нейро-окружения
                                 или к папке с .venv внутри.
                                 Если пусто — используется системный Python
                                 агента (где стоят SNN-библиотеки).

    Возвращает:
        Словарь с результатом: success, stdout, stderr, returncode.
    """
    logger.debug(f"[NEURO] run_neuro_check: python={neuro_python_path or NEURO_DEFAULT_PYTHON}")

    python_path = _find_neuro_python(neuro_python_path)
    if not python_path:
        return {
            "success": False,
            "stdout": "",
            "stderr": (
                "[НЕЙРО-ИНФО] Нейро-окружение НЕ НАЙДЕНО.\n"
                "Не найден python.exe по указанному пути. Проверь поле "
                "«Нейро-окружение» в боковой панели — туда можно вписать "
                "путь к python.exe (например: C:\\Python312\\python.exe) "
                "или к папке с .venv."
            ),
            "returncode": -1,
        }

    # Скрипт диагностики: окружение + список SNN-библиотек
    check_script = r'''import sys
import importlib.util

print("[НЕЙРО-ИНФО]")
print("python:", sys.version.split()[0])
print("executable:", sys.executable)

mods = {
    "lava": "Lava (Intel Loihi)",
    "akida": "Akida (BrainChip)",
    "cnn2snn": "cnn2snn (Akida конвертер)",
    "quantizeml": "quantizeml (Akida)",
    "pyNN": "PyNN",
    "brian2": "Brian2",
    "snntorch": "snnTorch",
    "nengo": "Nengo",
    "rockpool": "Rockpool",
    "bindsnet": "BindsNET",
    "sinabs": "Sinabs (DVS/события)",
    "jax": "JAX (GPU/TPU)",
    "torch": "PyTorch",
    "keras": "Keras",
    "tensorflow": "TensorFlow",
    "numpy": "numpy",
    "matplotlib": "matplotlib",
}
for mod, label in mods.items():
    try:
        spec = importlib.util.find_spec(mod)
        present = spec is not None
    except (ImportError, ValueError, AttributeError):
        present = False
    print(f"{label}: {'ПРИСУТСТВУЕТ' if present else 'НЕТ'}")
'''

    tmp_file = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False)
        tmp.write(check_script)
        tmp.close()
        tmp_file = tmp.name
        atexit.register(lambda p=tmp_file: os.unlink(p) if os.path.exists(p) else None)

        result = _run_process(python_path, tmp_file, timeout=60)

        if result.returncode == 0 and result.stdout.strip():
            logger.info(f"[NEURO] Проверка окружения OK ({len(result.stdout)} симв.)")
            return {
                "success": True,
                "stdout": _cap_output(result.stdout.strip()),
                "stderr": "",
                "returncode": 0,
            }
        error_msg = result.stderr.strip() or result.stdout.strip() or "Неизвестная ошибка"
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Ошибка проверки нейро-окружения:\n{_fmt_error(error_msg)}",
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Проверка нейро-окружения заняла больше 60 секунд и была прервана.",
            "returncode": -1,
        }
    except Exception as e:
        logger.error(f"[NEURO] run_neuro_check error: {e}")
        return {"success": False, "stdout": "", "stderr": f"Внутренняя ошибка: {e}", "returncode": -1}
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:
                pass


# ============================================================
# ИНСТРУМЕНТ 2: Запуск кода в нейро-окружении
# ============================================================
def run_neuro_ml(neuro_code: str = "", neuro_python_path: str = "", timeout: int = 300) -> Dict[str, Any]:
    """
    Выполняет Python-код в нейро-окружении (SNN-библиотеки).

    Параметры:
        neuro_code (str): Исходный код на Python. Может использовать:
                          numpy (np), pandas (pd), matplotlib (plt) — пред-импортированы,
                          а также любые SNN-библиотеки: import lava, akida, pyNN,
                          brian2, snntorch, nengo, rockpool, bindsnet, sinabs, jax.
        neuro_python_path (str): Путь к python.exe нейро-окружения или к папке
                                 с .venv внутри. Если пусто — системный Python.
        timeout (int): Таймаут выполнения в секундах (по умолчанию 300, максимум 3600).

    Возвращает:
        Словарь с результатом: success, stdout, stderr, returncode.
    """
    logger.debug(f"[NEURO] run_neuro_ml: code_length={len(neuro_code)}, timeout={timeout}")

    if not neuro_code or not neuro_code.strip():
        return {
            "success": False,
            "stdout": "",
            "stderr": "Ошибка: передан пустой код (neuro_code). Напиши Python-код для нейроморфных вычислений.",
            "returncode": -1,
        }

    try:
        timeout = int(timeout)
    except (ValueError, TypeError):
        timeout = 300
    timeout = max(1, min(timeout, 3600))

    python_path = _find_neuro_python(neuro_python_path)
    if not python_path:
        return {
            "success": False,
            "stdout": "",
            "stderr": (
                "[НЕЙРО-ИНФО] Нейро-окружение НЕ НАЙДЕНО.\n"
                "Не найден python.exe по указанному пути. Проверь поле "
                "«Нейро-окружение» в боковой панели или укажи neuro_python_path."
            ),
            "returncode": -1,
        }

    # Если код — простое выражение ("2+2"), оборачиваем в print
    code_to_run = neuro_code.strip()
    has_statement = any(
        kw in code_to_run
        for kw in ["import ", "from ", "def ", "class ", "print(", "return ",
                    "for ", "while ", "if ", "with ", "try:", "except",
                    "=", "plt.", "pd.", "np."]
    )
    if not has_statement:
        try:
            compile(code_to_run, "<string>", "eval")
            code_to_run = f"print({code_to_run})"
        except SyntaxError:
            pass

    indented_code = "\n".join(
        "    " + line if line.strip() else ""
        for line in code_to_run.split("\n")
    )

    full_code = f"""import sys
import io

_neuro_out = io.StringIO()
_neuro_old_stdout = sys.stdout
sys.stdout = _neuro_out

try:
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception as _e:
    print(f"[ОШИБКА ИМПОРТА] {{_e}}", file=_neuro_old_stdout)
    sys.stdout = _neuro_old_stdout
    sys.exit(1)

try:
{indented_code}
except Exception as _err:
    print(f"[ОШИБКА] {{type(_err).__name__}}: {{_err}}", file=_neuro_old_stdout)
    sys.stdout = _neuro_old_stdout
    sys.exit(1)

sys.stdout = _neuro_old_stdout
_output_text = _neuro_out.getvalue()
if _output_text:
    print(_output_text, end="")
else:
    print("[Код выполнен успешно, но не вывел результат]")
"""

    tmp_file = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False)
        tmp.write(full_code)
        tmp.close()
        tmp_file = tmp.name
        atexit.register(lambda p=tmp_file: os.unlink(p) if os.path.exists(p) else None)

        last_error = ""
        installed = set()
        for attempt in range(_MAX_INSTALL_RETRIES + 1):
            try:
                result = _run_process(python_path, tmp_file, timeout=timeout)
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Превышено время выполнения ({timeout} сек). "
                              f"Код слишком долгий или содержит бесконечный цикл. "
                              f"При необходимости передай больший timeout.",
                    "returncode": -1,
                }

            if result.returncode == 0:
                output = result.stdout.strip() or result.stderr.strip() or "Код выполнен успешно!"
                logger.info(f"[NEURO] Код выполнен: stdout={len(result.stdout)} символов")
                return {
                    "success": True,
                    "stdout": _cap_output(output),
                    "stderr": "",
                    "returncode": 0,
                }

            combined = (result.stderr or "") + "\n" + (result.stdout or "")
            last_error = _fmt_error(result.stderr.strip() or result.stdout.strip() or "Неизвестная ошибка")

            # Пытаемся авто-установить недостающий пакет и повторить
            missing = _extract_missing_module(combined)
            if missing and missing not in installed:
                installed.add(missing)
                logger.info(f"[NEURO] Попытка {attempt + 1}: авто-установка '{missing}'")
                if _pip_install(python_path, missing):
                    continue
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": (
                        f"[НЕЙРО] Не удалось установить пакет '{missing}' в нейро-окружение.\n"
                        f"Ошибка кода:\n{last_error}\n"
                        f"Установи пакет вручную: {python_path} -m pip install {_PIP_NAMES.get(missing, missing)}"
                    ),
                    "returncode": -1,
                }

            return {
                "success": False,
                "stdout": "",
                "stderr": f"Ошибка выполнения нейро-кода:\n{last_error}",
                "returncode": result.returncode,
            }

    except Exception as e:
        logger.error(f"[NEURO] run_neuro_ml error: {e}")
        return {"success": False, "stdout": "", "stderr": f"Внутренняя ошибка: {e}", "returncode": -1}
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:
                pass

    return {
        "success": False,
        "stdout": "",
        "stderr": f"Не удалось выполнить код после {_MAX_INSTALL_RETRIES} попыток: {last_error}",
        "returncode": -1,
    }
