"""
bio_tools.py — Инструменты для биопрограммирования (Cortical Labs SDK "cl").

Содержит функции, которые AI-агент может вызывать через механизм инструментов:
  1. run_bio_check — проверка био-окружения и подключение к биокомпьютеру
  2. run_bio_ml    — запуск Python-кода в био-окружении (cl-sdk, numpy, pandas,
                     matplotlib) с авто-установкой недостающих пакетов
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

# Путь к био-проекту по умолчанию (папка, внутри которой лежит .venv)
BIO_DEFAULT_PROJECT = r"C:\Users\lesya\OneDrive\Рабочий стол\cl_project"

# Пакеты для диагностики: имя модуля → что показать пользователю
BIO_PACKAGES = {
    "cl": "cl-sdk (Cortical Labs)",
    "numpy": "numpy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "scipy": "scipy",
    "networkx": "networkx",
    "community": "python-louvain",
    "tables": "tables (PyTables)",
    "websockets": "websockets",
    "msgpack": "msgpack",
    "msgpack_numpy": "msgpack-numpy",
    "jupyterlab": "jupyterlab",
    "akida": "Akida (BrainChip)",
    "lava": "Lava (Intel)",
    "brian2": "Brian2",
    "snntorch": "snnTorch",
    "nengo": "Nengo",
    "rockpool": "Rockpool",
    "bindsnet": "BindsNET",
    "sinabs": "Sinabs",
    "jax": "JAX",
    "torch": "PyTorch",
    "pyNN": "pyNN",
}

# Известные соответствия "имя модуля → имя pip-пакета"
_PIP_NAMES = {
    "cl": "cl-sdk",
    "lava": "lava-nc",
    "pyNN": "pyNN",
    "snntorch": "snntorch",
    "brian2": "brian2",
    "akida": "akida",
    "nengo": "nengo",
    "rockpool": "rockpool",
    "bindsnet": "bindsnet",
    "sinabs": "sinabs",
    "jax": "jax",
    "community": "python-louvain",
    "msgpack_numpy": "msgpack-numpy",
}

_MAX_OUTPUT_LEN = 8000
_MAX_INSTALL_RETRIES = 3


# ============================================================
# Внутренние помощники
# ============================================================
def _find_bio_python(bio_project_path: str = "") -> Optional[str]:
    """Находит python.exe био-окружения.

    Принимает: путь к папке биопроекта (с .venv внутри) или
    непосредственно путь к python.exe. Если ничего не указано —
    использует известный проект по умолчанию.
    """
    candidates: list = []
    if bio_project_path and bio_project_path.strip():
        p = Path(bio_project_path.strip()).expanduser()
        if p.name.lower() in ("python.exe", "python"):
            if p.is_file():
                return str(p)
            return None
        candidates.append(p / ".venv" / "Scripts" / "python.exe")
        candidates.append(p / "venv" / "Scripts" / "python.exe")
    candidates.append(Path(BIO_DEFAULT_PROJECT) / ".venv" / "Scripts" / "python.exe")
    for c in candidates:
        try:
            if c.is_file():
                return str(c)
        except OSError:
            continue
    return None


def _bio_project_dir(python_path: str) -> str:
    """Возвращает папку биопроекта (родитель .venv) по пути python.exe."""
    p = Path(python_path)
    # ...\Биопроект\.venv\Scripts\python.exe → папка биопроекта
    if p.parents[1].name in (".venv", "venv"):
        return str(p.parents[2])
    return str(p.parents[1])


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
    # Берём верхний уровень: "cl.sim" → "cl"
    return mod.split(".")[0] if mod else None


def _pip_install(python_path: str, module_name: str) -> bool:
    """Устанавливает pip-пакет в био-окружение. Возвращает успех."""
    pkg = _PIP_NAMES.get(module_name, module_name)
    logger.info(f"[BIO] Авто-установка пакета {pkg} в био-окружение")
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
            logger.warning(f"[BIO] pip install {pkg} failed: {res.stderr[-500:]}")
        return ok
    except Exception as e:
        logger.error(f"[BIO] pip install {pkg} error: {e}")
        return False


def _cap_output(text: str) -> str:
    if text and len(text) > _MAX_OUTPUT_LEN:
        return text[:_MAX_OUTPUT_LEN] + "\n...[вывод обрезан, показано начало]"
    return text


def _fmt_error(stderr: str) -> str:
    """Сокращает трейсбек до полезной части (как в run_local_ml)."""
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
# ИНСТРУМЕНТ 1: Проверка био-окружения и биокомпьютера
# ============================================================
def run_bio_check(bio_project_path: str = "") -> Dict[str, Any]:
    """
    Проверяет био-окружение (папку биопроекта с .venv и пакетами)
    и подключается к биокомпьютеру (симулятору Cortical Labs).
    Возвращает блок [БИО-ИНФО] с версией Python, списком установленных
    пакетов и [БИОКОМП] с характеристиками подключения
    (каналы/нейроны, кадры в секунду, симулятор или реальный чип).

    Параметры:
        bio_project_path (str): Путь к папке биопроекта (где .venv)
                                или к python.exe био-окружения.
                                Если пусто — используется проект по умолчанию.

    Возвращает:
        Словарь с результатом: success, stdout, stderr, returncode.
    """
    logger.debug(f"[BIO] run_bio_check: project={bio_project_path or BIO_DEFAULT_PROJECT}")

    python_path = _find_bio_python(bio_project_path)
    if not python_path:
        return {
            "success": False,
            "stdout": "",
            "stderr": (
                "[БИО-ИНФО] Био-окружение НЕ НАЙДЕНО.\n"
                "Не найдена папка .venv в биопроекте. Проверь поле «Био-проект» "
                "в боковой панели — там должен быть путь к папке биопроекта "
                "(например: C:\\Users\\lesya\\OneDrive\\Рабочий стол\\cl_project)."
            ),
            "returncode": -1,
        }

    project_dir = _bio_project_dir(python_path)

    # Скрипт диагностики: окружение + подключение к биокомпьютеру
    check_script = r'''import sys
import importlib.util

print("[БИО-ИНФО]")
print("python:", sys.version.split()[0])
print("executable:", sys.executable)

mods = {
    "cl": "cl-sdk (Cortical Labs)",
    "numpy": "numpy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "scipy": "scipy",
    "networkx": "networkx",
    "community": "python-louvain",
    "tables": "tables (PyTables)",
    "websockets": "websockets",
    "msgpack": "msgpack",
    "msgpack_numpy": "msgpack-numpy",
    "jupyterlab": "jupyterlab",
    "akida": "Akida (BrainChip)",
    "lava": "Lava (Intel)",
    "brian2": "Brian2",
    "snntorch": "snnTorch",
    "nengo": "Nengo",
    "rockpool": "Rockpool",
    "bindsnet": "BindsNET",
    "sinabs": "Sinabs",
    "jax": "JAX",
    "torch": "PyTorch",
    "pyNN": "pyNN",
}
for mod, label in mods.items():
    try:
        spec = importlib.util.find_spec(mod)
        present = spec is not None
    except (ImportError, ValueError, AttributeError):
        present = False
    print(f"{label}: {'ПРИСУТСТВУЕТ' if present else 'НЕТ'}")

print("[БИОКОМП]")
try:
    import cl
    with cl.open(take_control=False, wait_until_recordable=False) as neurons:
        print("статус: ПОДКЛЮЧЕН")
        print("устройство:", "СИМУЛЯТОР" if cl.is_simulator() else "РЕАЛЬНЫЙ ЧИП")
        print("каналов (нейронов):", neurons.get_channel_count())
        print("кадров в секунду:", neurons.get_frames_per_second())
        print("длительность кадра (мкс):", neurons.get_frame_duration_us())
        print("читаемо:", neurons.is_readable())
        try:
            frame = neurons.read(1)
            print("тест чтения 1 кадра:", frame.shape)
        except Exception as e:
            print("тест чтения не удался:", type(e).__name__, str(e)[:200])
except Exception as e:
    print("ОШИБКА ПОДКЛЮЧЕНИЯ:", type(e).__name__, str(e)[:300])
    print("ПОДСКАЗКА: запусти симулятор Cortical Labs (dishsim) перед проверкой.")
'''

    tmp_file = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False)
        tmp.write(check_script)
        tmp.close()
        tmp_file = tmp.name
        atexit.register(lambda p=tmp_file: os.unlink(p) if os.path.exists(p) else None)

        result = _run_process(python_path, tmp_file, timeout=45, cwd=project_dir)

        if result.returncode == 0 and result.stdout.strip():
            logger.info(f"[BIO] Проверка окружения OK ({len(result.stdout)} симв.)")
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
            "stderr": f"Ошибка проверки био-окружения:\n{_fmt_error(error_msg)}",
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Проверка био-окружения заняла больше 45 секунд и была прервана.",
            "returncode": -1,
        }
    except Exception as e:
        logger.error(f"[BIO] run_bio_check error: {e}")
        return {"success": False, "stdout": "", "stderr": f"Внутренняя ошибка: {e}", "returncode": -1}
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:
                pass


# ============================================================
# ИНСТРУМЕНТ 2: Запуск кода в био-окружении
# ============================================================
def run_bio_ml(bio_code: str = "", bio_project_path: str = "", timeout: int = 300) -> Dict[str, Any]:
    """
    Выполняет Python-код в био-окружении (Cortical Labs SDK "cl").

    Параметры:
        bio_code (str): Исходный код на Python. Может использовать:
                        numpy (np), pandas (pd), matplotlib (plt) — пред-импортированы,
                        а также cl (import cl) для работы с биокомпьютером.
        bio_project_path (str): Путь к папке биопроекта (где .venv) или к python.exe.
                                Если пусто — используется проект по умолчанию.
        timeout (int): Таймаут выполнения в секундах (по умолчанию 300, максимум 3600).

    Возвращает:
        Словарь с результатом: success, stdout, stderr, returncode.
    """
    logger.debug(f"[BIO] run_bio_ml: code_length={len(bio_code)}, timeout={timeout}")

    if not bio_code or not bio_code.strip():
        return {
            "success": False,
            "stdout": "",
            "stderr": "Ошибка: передан пустой код (bio_code). Напиши Python-код для биопрограммирования.",
            "returncode": -1,
        }

    try:
        timeout = int(timeout)
    except (ValueError, TypeError):
        timeout = 300
    timeout = max(1, min(timeout, 3600))

    python_path = _find_bio_python(bio_project_path)
    if not python_path:
        return {
            "success": False,
            "stdout": "",
            "stderr": (
                "[БИО-ИНФО] Био-окружение НЕ НАЙДЕНО.\n"
                "Не найдена папка .venv в биопроекте. Проверь поле «Био-проект» "
                "в боковой панели или укажи bio_project_path."
            ),
            "returncode": -1,
        }
    project_dir = _bio_project_dir(python_path)

    # Если код — простое выражение ("2+2"), оборачиваем в print
    code_to_run = bio_code.strip()
    has_statement = any(
        kw in code_to_run
        for kw in ["import ", "from ", "def ", "class ", "print(", "return ",
                    "for ", "while ", "if ", "with ", "try:", "except",
                    "=", "plt.", "pd.", "np.", "cl."]
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

_bio_out = io.StringIO()
_bio_old_stdout = sys.stdout
sys.stdout = _bio_out

try:
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception as _e:
    print(f"[ОШИБКА ИМПОРТА] {{_e}}", file=_bio_old_stdout)
    sys.stdout = _bio_old_stdout
    sys.exit(1)

try:
{indented_code}
except Exception as _err:
    print(f"[ОШИБКА] {{type(_err).__name__}}: {{_err}}", file=_bio_old_stdout)
    sys.stdout = _bio_old_stdout
    sys.exit(1)

sys.stdout = _bio_old_stdout
_output_text = _bio_out.getvalue()
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
                result = _run_process(python_path, tmp_file, timeout=timeout, cwd=project_dir)
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
                logger.info(f"[BIO] Код выполнен: stdout={len(result.stdout)} символов")
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
                logger.info(f"[BIO] Попытка {attempt + 1}: авто-установка '{missing}'")
                if _pip_install(python_path, missing):
                    continue
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": (
                        f"[БИО] Не удалось установить пакет '{missing}' в био-окружение.\n"
                        f"Ошибка кода:\n{last_error}\n"
                        f"Установи пакет вручную: {python_path} -m pip install {_PIP_NAMES.get(missing, missing)}"
                    ),
                    "returncode": -1,
                }

            return {
                "success": False,
                "stdout": "",
                "stderr": f"Ошибка выполнения био-кода:\n{last_error}",
                "returncode": result.returncode,
            }

    except Exception as e:
        logger.error(f"[BIO] run_bio_ml error: {e}")
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
