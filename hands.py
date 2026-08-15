"""
«Руки» агента — исполнитель команд.
Умеет:
- shell: запуск PowerShell/cmd команд
- file_read: чтение файлов
- file_write: запись файлов
- automator: запуск Project Automator
- quantum: квантовые симуляции (Bell, noise, IBM real)
- quantum_simulator: запуск пользовательского квантового кода
- draw_circuit: ASCII-диаграмма квантовой схемы
- parse_result: парсинг квантовых результатов в Markdown
- get_backends: получение списка реальных бэкендов IBM Quantum
- transpile_circuit: транспиляция схемы под реальное железо
- run_on_real: запуск на реальном квантовом компьютере IBM
"""
import subprocess
import sys
import json
import importlib.util
import os
from pathlib import Path
from typing import Any, Dict

from config import logger, AUTOMATOR_PATH, INSTRUCTIONS_DIR

# Импортируем ML-инструменты
from ml_tools import (
    fetch_dataset,
    run_local_ml,
    run_cloud_gpu_ml,
    parse_ml_metrics,
    run_modal_ml,
    run_ssh_ml,
)

# Импортируем биоинструменты (биопрограммирование, Cortical Labs)
from bio_tools import (
    run_bio_check,
    run_bio_ml,
)

# Импортируем нейроинструменты (нейроморфные вычисления, SNN)
from neuro_tools import (
    run_neuro_check,
    run_neuro_ml,
)

# Импортируем дополнительные квантовые инструменты
from quantum_extras import (
    run_quantum_simulator,
    draw_circuit as draw_circuit_fn,
    parse_quantum_result,
    get_available_backends,
    transpile_circuit,
    run_on_real_hardware,
    run_on_quantum_inspire,
    apply_error_mitigation,
    compare_backends,
)


class HandsError(Exception):
    """Ошибка выполнения команды."""
    pass


def shell(command: str, timeout: int = 600, shell_type: str = "auto") -> Dict[str, Any]:
    import sys as _sys
    _sys.stderr.write(f"[HANDS_DEBUG] shell called: command={command[:100]}\n")
    _sys.stderr.write(f"[HANDS_DEBUG] os.getcwd()={os.getcwd()}\n")
    _sys.stderr.write(f"[HANDS_DEBUG] AGENT_DIR={os.environ.get('AGENT_DIR', 'NOT SET')}\n")
    _sys.stderr.flush()
    logger.debug(f"[HANDS] shell: {command[:200]}")

    # Block browser-opening, second agent, and explorer commands
    blocked_patterns = [
        "start http", "start https", "start chrome", "start firefox", "start msedge",
        "start opera", "start brave", "start edge", "start www",
        "start file://", "start file:",
        "start .html", "start .htm",
        "explorer ", "explorer.exe",
        "start ./", "start .\\", "start dist", "start \"\"", "start ''",
        "start /d",
    ]
    for bp in blocked_patterns:
        if bp.lower() in command.lower():
            logger.warning(f"[HANDS] Blocked command (would open browser/app): {command[:100]}")
            return {
                "success": False,
                "stdout": "",
                "stderr": "Blocked: browser/explorer/app-launch commands are not allowed. Use only the provided tools.",
                "returncode": 1,
            }
    import re as _re
    if _re.search(r'\b(start|open|invoke-item)\s+', command, _re.I):
        rest = _re.sub(r'^(start|open|invoke-item)\s+', '', command, flags=_re.I).strip()
        rest = _re.sub(r'^/(?:[bwd]|min|max|wait|separate|shared|low|normal|realtime|high|abovenormal|belownormal|node|scope|window)\s+', '', rest, flags=_re.I).strip()
        if rest:
            safe_starts = ['python', 'cmd', 'powershell', 'ping', 'ipconfig', 'dir', 'cd ', 'echo', 'type ', 'find', 'sort', 'more', 'tree', 'set ', 'chcp', 'color', 'help', 'ver', 'time', 'date', 'mkdir', 'copy', 'move', 'del ', 'ren ', 'rd ', 'xcopy', 'robocopy']
            is_safe = any(rest.lower().startswith(s) for s in safe_starts)
            if not is_safe:
                logger.warning(f"[HANDS] Blocked start/launch command: {command[:100]}")
                return {"success": False, "stdout": "", "stderr": "Blocked: app-launch commands are not allowed. Only python/cmd/powershell/utility commands are permitted.", "returncode": 1}
    
    _env_raw = {**os.environ, "MPLBACKEND": "Agg"}
    _env = {}
    try:
        for _k, _v in _env_raw.items():
            if isinstance(_k, str) and isinstance(_v, str):
                _env[_k] = _v.replace('\x00', '')
    except Exception:
        _env = _env_raw
    _env.setdefault("MPLBACKEND", "Agg")

    try:
        use_powershell = False
        actual_command = command
        
        stripped_for_check = command.strip().strip("'").strip('"').strip()

        def _run_python_file(file_path: str) -> Dict[str, Any]:
            # Пробуем разные варианты вызова python
            approaches = [
                {"args": [sys.executable, file_path], "use_cwd": False, "use_env": True, "shell": False},
                {"args": [sys.executable, file_path], "use_cwd": False, "use_env": False, "shell": False},
                {"args": f'"{sys.executable}" "{file_path}"', "use_cwd": False, "use_env": False, "shell": True},
            ]
            for attempt_idx, approach in enumerate(approaches):
                try:
                    kwargs = {
                        "capture_output": True,
                        "text": True,
                        "timeout": timeout,
                        "encoding": "utf-8",
                        "errors": "replace",
                    }
                    if approach.get("use_env"):
                        kwargs["env"] = _env
                    if approach.get("use_cwd"):
                        _py_cwd = os.environ.get("AGENT_DIR", "") or os.getcwd()
                        kwargs["cwd"] = _py_cwd if os.path.isdir(_py_cwd) else os.getcwd()
                    if approach.get("shell"):
                        kwargs["shell"] = True
                    r = subprocess.run(approach["args"], **kwargs)
                    return {
                        "success": r.returncode == 0,
                        "stdout": r.stdout,
                        "stderr": r.stderr,
                        "returncode": r.returncode,
                    }
                except subprocess.TimeoutExpired:
                    return {"success": False, "stdout": "", "stderr": f"Timeout after {timeout}s", "returncode": -1}
                except Exception as e:
                    if attempt_idx < len(approaches) - 1:
                        logger.debug(f"[HANDS] _run_python_file attempt {attempt_idx+1} failed: {e}, trying next...")
                        continue
                    return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}
            return {"success": False, "stdout": "", "stderr": "all attempts exhausted", "returncode": -1}

        def _extract_pycode_from_c(cmd: str) -> str:
            m = _re.search(r'(?:python(?:3|\.exe)?)\s+-c\s+([\'\"])(.*?)\1', cmd, _re.DOTALL)
            if m:
                code = m.group(2).replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
                return code
            return ""

        def _write_temp_py(code: str) -> str:
            import tempfile as _tf
            import atexit as _ae
            tmp = _tf.NamedTemporaryFile(suffix='.py', mode='w', encoding='utf-8', delete=False)
            tmp.write(code)
            tmp.close()
            _ae.register(lambda p=tmp.name: os.unlink(p) if os.path.exists(p) else None)
            return tmp.name

        # 1. Пытаемся найти python -c "..." и выполнить через temp-файл
        py_code = _extract_pycode_from_c(command)
        if py_code:
            logger.debug(f"[HANDS] Extracted python -c code ({len(py_code)} chars), writing to temp file")
            tmp_path = _write_temp_py(py_code)
            result = _run_python_file(tmp_path)
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return result

        # 2. Detect bare Python code and run via temp file
        python_keywords = ["import ", "from ", "print(", "def ", "class ", "# encoding", "import\n"]
        is_python = False
        for pk in python_keywords:
            if stripped_for_check.startswith(pk):
                is_python = True
                break
        if not is_python:
            if stripped_for_check.startswith("import") or stripped_for_check.startswith("from "):
                is_python = True
        if is_python:
            clean_code = stripped_for_check.replace("\\n", "\n")
            tmp_path = _write_temp_py(clean_code)
            result = _run_python_file(tmp_path)
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return result

        # 3. Обнаруживаем cd ... && python -c без явного -c в начале
        if " && python" in command or "| python" in command:
            py_code2 = _extract_pycode_from_c(command)
            if py_code2:
                logger.debug(f"[HANDS] Extracted python -c after cd/pipe, writing to temp file")
                tmp_path = _write_temp_py(py_code2)
                result = _run_python_file(tmp_path)
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                return result

        if command.startswith("powershell:"):
            use_powershell = True
            actual_command = command[len("powershell:"):].strip()
        elif command.startswith("cmd:"):
            use_powershell = False
            actual_command = command[len("cmd:"):].strip()
        elif shell_type == "powershell":
            use_powershell = True
        elif shell_type == "cmd":
            use_powershell = False
        else:
            ps_keywords = ["Get-", "Set-", "New-", "Remove-", "Write-",
                           "Select-Object", "Where-Object", "ForEach-Object",
                           "Select-String"]
            for kw in ps_keywords:
                if kw.lower() in command.lower():
                    use_powershell = True
                    break
            if not use_powershell and "|" in command:
                pipe_parts = command.split("|")
                for part in pipe_parts[1:]:
                    p = part.strip().split()[0].lower() if part.strip() else ""
                    if p and (p.startswith("select") or p.startswith("where") or p.startswith("foreach")
                              or p.startswith("get-") or p.startswith("sort") or p.startswith("group")):
                        use_powershell = True
                        break

        has_non_ascii = any(ord(c) > 127 for c in actual_command)
        if has_non_ascii and not use_powershell:
            use_powershell = True
            logger.debug(f"[HANDS] Non-ASCII detected, forcing PowerShell: {actual_command[:100]}")

        ps_path = None
        if use_powershell:
            for candidate in [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                              r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"]:
                if os.path.exists(candidate):
                    ps_path = candidate
                    break
            if ps_path is None:
                ps_path = "powershell"

        # Вспомогательная функция для выполнения subprocess с несколькими fallback'ами
        def _sanitize_env(raw_env) -> dict:
            if raw_env is None:
                return None
            safe = {}
            try:
                for k, v in raw_env.items():
                    if isinstance(k, str) and isinstance(v, str):
                        safe[k] = v.replace('\x00', '')
            except Exception:
                pass
            safe.setdefault("MPLBACKEND", "Agg")
            return safe

        def _validate_cwd(path) -> str:
            if path and isinstance(path, str) and path.strip():
                try:
                    if os.path.isdir(path):
                        return path
                except Exception:
                    pass
            return None

        def _run_subprocess_safe(cmd_list, cwd, env, timeout_s=timeout):
            last_error = None

            # ---- Санируем входные параметры ----
            safe_cwd = _validate_cwd(cwd)
            safe_env = _sanitize_env(env)

            # ---- Пытаемся извлечь "чистую" команду из cmd /c обёртки ----
            # и выполнить напрямую через shell=True (без cmd /c)
            raw_cmd_str = None
            if isinstance(cmd_list, list) and len(cmd_list) >= 2:
                first = cmd_list[0].lower() if cmd_list else ''
                if 'cmd' in first or 'powershell' in first:
                    last_part = cmd_list[-1] if len(cmd_list) > 1 else None
                    if last_part and '&&' in last_part:
                        after_and = last_part.split('&&', 1)[1].strip()
                        if after_and:
                            raw_cmd_str = after_and
                    if not raw_cmd_str and last_part:
                        raw_cmd_str = last_part
                elif len(cmd_list) == 1:
                    raw_cmd_str = cmd_list[0]

            if raw_cmd_str:
                try:
                    r = subprocess.run(
                        raw_cmd_str,
                        capture_output=True, text=True, timeout=timeout_s,
                        shell=True,
                        env=safe_env,
                    )
                    return r
                except Exception as e:
                    last_error = e
                    logger.warning(f"[HANDS] direct shell fallback failed ({e}), trying subprocess...")

            # Попытка 1: subprocess.run с валидными cwd/env
            try:
                kwargs = {
                    "capture_output": True,
                    "text": True,
                    "timeout": timeout_s,
                    "encoding": "utf-8",
                    "errors": "replace",
                }
                if safe_cwd is not None:
                    kwargs["cwd"] = safe_cwd
                if safe_env is not None:
                    kwargs["env"] = safe_env
                r = subprocess.run(cmd_list, **kwargs)
                return r
            except Exception as e:
                last_error = e
                logger.warning(f"[HANDS] subprocess error ({e}), trying shell=True fallback...")

            # Попытка 2: shell=True, без cwd
            try:
                raw_cmd = " ".join(cmd_list) if isinstance(cmd_list, list) else cmd_list
                kwargs = {
                    "capture_output": True,
                    "text": True,
                    "timeout": timeout_s,
                    "encoding": "utf-8",
                    "errors": "replace",
                    "shell": True,
                }
                if safe_env is not None:
                    kwargs["env"] = safe_env
                r = subprocess.run(raw_cmd, **kwargs)
                return r
            except Exception as e:
                last_error = e
                logger.warning(f"[HANDS] shell=True fallback failed ({e}), trying without env...")

            # Попытка 3: shell=True, без cwd, без env
            try:
                raw_cmd = " ".join(cmd_list) if isinstance(cmd_list, list) else cmd_list
                r = subprocess.run(
                    raw_cmd,
                    capture_output=True, text=True, timeout=timeout_s,
                    shell=True,
                )
                return r
            except Exception as e:
                last_error = e
                logger.warning(f"[HANDS] attempt 3 failed ({e}), trying Popen...")

            # Попытка 4: subprocess.Popen (без text/encoding)
            try:
                raw_cmd = " ".join(cmd_list) if isinstance(cmd_list, list) else cmd_list
                proc = subprocess.Popen(
                    raw_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                )
                stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_s)
                stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
                proc_class = type('', (), {})()
                proc_class.returncode = proc.returncode
                proc_class.stdout = stdout
                proc_class.stderr = stderr
                return proc_class
            except Exception as e:
                last_error = e
                logger.warning(f"[HANDS] attempt 4 failed ({e}), trying os.popen...")

            # Попытка 5: os.popen
            try:
                raw_cmd = " ".join(cmd_list) if isinstance(cmd_list, list) else cmd_list
                proc_obj = os.popen(f'{raw_cmd} 2>&1')
                output = proc_obj.read()
                exit_code = proc_obj.close()
                proc_class = type('', (), {})()
                proc_class.returncode = exit_code if exit_code is not None else -1
                proc_class.stdout = output or ""
                proc_class.stderr = ""
                return proc_class
            except Exception as e:
                last_error = e
                logger.warning(f"[HANDS] attempt 5 (os.popen) failed ({e}), trying os.system...")

            # Попытка 6: os.system (самый низкоуровневый)
            try:
                raw_cmd = " ".join(cmd_list) if isinstance(cmd_list, list) else cmd_list
                import tempfile as _tf_sys
                _out_file = _tf_sys.NamedTemporaryFile(suffix='.txt', mode='w+', delete=False, encoding='utf-8')
                _out_path = _out_file.name
                _out_file.close()
                exit_code = os.system(f'({raw_cmd}) > "{_out_path}" 2>&1')
                stdout_text = ""
                try:
                    with open(_out_path, 'r', encoding='utf-8', errors='replace') as _f:
                        stdout_text = _f.read()
                except Exception:
                    pass
                try:
                    os.unlink(_out_path)
                except Exception:
                    pass
                proc_class = type('', (), {})()
                proc_class.returncode = exit_code
                proc_class.stdout = stdout_text
                proc_class.stderr = ""
                return proc_class
            except Exception as e:
                last_error = e
                logger.warning(f"[HANDS] ALL subprocess attempts failed. Last error: {last_error}")

            # Все fallback'и исчерпаны — отдаём последнюю ошибку
            raise last_error

        if use_powershell:
            _ps_cwd_raw = os.environ.get("AGENT_DIR", os.getcwd())
            ps_cwd = _ps_cwd_raw if _ps_cwd_raw and os.path.isdir(_ps_cwd_raw) else os.getcwd()
            ps_cmd = actual_command.replace("2>nul", "2>$null").replace("> nul", ">$null").replace(">nul", ">$null")
            shell_cmd = [
                ps_path, "-NoProfile",
                "-OutputFormat", "Text",
                "-Command",
                f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; [Console]::InputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; {ps_cmd}"
            ]
            logger.debug(f"[HANDS] Running PS in {ps_cwd}: {actual_command[:200]}")
            result = _run_subprocess_safe(shell_cmd, ps_cwd, _env)
        else:
            py_cwd = os.getcwd()
            env_cwd = os.environ.get("AGENT_DIR", "NOT_SET")
            cmd_cwd = env_cwd if env_cwd != "NOT_SET" else py_cwd
            logger.info(f"[HANDS] CMD cwd={cmd_cwd} py_cwd={py_cwd} AGENT_DIR={env_cwd}")
            shell_cmd = ["cmd", "/c", f"chcp 65001 > nul && {actual_command}"]
            logger.debug(f"[HANDS] Running CMD in {cmd_cwd}: {actual_command[:200]}")
            result = _run_subprocess_safe(shell_cmd, cmd_cwd, _env)
        
        actual_child_cwd = ps_cwd if use_powershell else cmd_cwd
        output = {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "cwd": actual_child_cwd,
        }
        
        logger.debug(f"[HANDS] Result: success={output['success']}, "
                     f"stdout_len={len(result.stdout)}, stderr_len={len(result.stderr)}, cwd={os.getcwd()}")

        # Fallback A: если cmd упал и есть не-ASCII → retry with PowerShell
        if not output["success"] and not use_powershell and has_non_ascii:
            logger.warning(f"[HANDS] CMD failed with non-ASCII command, retrying with PowerShell: {actual_command[:100]}")
            ps_retry_cwd = os.environ.get("AGENT_DIR", os.getcwd())
            for candidate in [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                              r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"]:
                if os.path.exists(candidate):
                    ps_path = candidate
                    break
            if ps_path is None:
                ps_path = "powershell"
            ps_cmd = actual_command.replace("2>nul", "2>$null").replace("> nul", ">$null").replace(">nul", ">$null")
            shell_cmd = [ps_path, "-NoProfile", "-OutputFormat", "Text", "-Command",
                         f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; [Console]::InputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; {ps_cmd}"]
            try:
                retry_result = _run_subprocess_safe(shell_cmd, ps_retry_cwd, _env)
                if retry_result.returncode == 0:
                    logger.info(f"[HANDS] PowerShell retry succeeded")
                    return {"success": True, "stdout": retry_result.stdout, "stderr": retry_result.stderr, "returncode": 0, "cwd": ps_retry_cwd}
            except Exception as retry_e:
                logger.warning(f"[HANDS] PowerShell retry also failed: {retry_e}")

        # Fallback B: SyntaxError → retry via tempfile
        if not output["success"] and ("SyntaxError" in output["stderr"] or "SyntaxError" in output["stdout"]):
            fb_code = command.strip()
            fb_m = _re.search(r'(?:python(?:3|\.exe)?)\s+-c\s+([\'\"])(.*?)\1', fb_code, _re.DOTALL)
            if fb_m:
                fb_code = fb_m.group(2).replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
            else:
                fb_code = fb_code.strip().strip("'").strip('"').strip()
            if fb_code and not fb_code.lower().startswith("cmd") and not fb_code.lower().startswith("powershell:"):
                tmp_path = _write_temp_py(fb_code.replace("\\n", "\n"))
                fb_result = _run_python_file(tmp_path)
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                return fb_result

        return output

    except subprocess.TimeoutExpired:
        logger.warning(f"[HANDS] Timeout after {timeout}s: {command[:100]}")
        return {"success": False, "stdout": "", "stderr": f"Timeout after {timeout}s", "returncode": -1}
    except Exception as e:
        logger.error(f"[HANDS] Error: {e}")
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def file_write(path: str, content: str = "") -> Dict[str, Any]:
    """Записать содержимое в файл.
    
    Поддерживает как абсолютные пути, так и относительные.
    Автоматически создаёт родительские папки.
    Относительные пути и пути в Temp перенаправляются в AGENT_DIR.
    """
    logger.debug(f"[HANDS] file_write: {path}")
    
    try:
        raw_path = Path(path).expanduser()
        
        # Redirect temp folder paths to AGENT_DIR
        agent_dir = os.environ.get("AGENT_DIR", str(Path.cwd()))
        temp_dir = Path(os.environ.get("TEMP", "C:\\Windows\\Temp")).resolve()
        user_temp = Path(os.environ.get("TMP", "")).resolve() if os.environ.get("TMP") else None
        
        file_path = raw_path.resolve()
        try:
            if temp_dir in file_path.parents or (user_temp and user_temp in file_path.parents):
                name = file_path.name  # just the filename
                file_path = Path(agent_dir) / name
                logger.info(f"[HANDS] Redirected from temp to: {file_path}")
        except (ValueError, OSError):
            pass  # path not relative to temp, keep as-is
        
        # If still relative, make absolute using agent_dir
        if not file_path.is_absolute():
            file_path = Path(agent_dir) / file_path
            logger.info(f"[HANDS] Resolved relative path -> {file_path}")
        
        file_path = file_path.resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Если контент пустой, создаём пустой файл
        file_path.write_text(content, encoding="utf-8")
        
        result = {
            "success": True,
            "stdout": f"File written: {file_path} ({len(content)} chars)",
            "stderr": "",
            "returncode": 0,
        }
        logger.debug(f"[HANDS] file_write OK: {file_path}")
        return result
        
    except Exception as e:
        logger.error(f"[HANDS] file_write error: {e}")
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def file_read(path: str) -> Dict[str, Any]:
    """Прочитать содержимое файла или список файлов в директории.
    
    Возвращает содержимое как текст.
    """
    logger.debug(f"[HANDS] file_read: {path}")
    
    try:
        file_path = Path(path).expanduser().resolve()
        
        if not file_path.exists():
            msg = f"File not found: {file_path}"
            logger.warning(f"[HANDS] {msg}")
            return {"success": False, "stdout": "", "stderr": msg, "returncode": -1}
        
        # If it's a directory, list contents
        if file_path.is_dir():
            items = []
            for entry in sorted(file_path.iterdir()):
                suffix = "/" if entry.is_dir() else ""
                items.append(f"{entry.name}{suffix}")
            content = "\n".join(items)
            result = {
                "success": True,
                "stdout": f"[DIR] {file_path}\n{content}",
                "stderr": "",
                "returncode": 0,
            }
            logger.debug(f"[HANDS] file_read (dir): {file_path} ({len(items)} entries)")
            return result
        
        content = file_path.read_text(encoding="utf-8", errors="replace")
        
        result = {
            "success": True,
            "stdout": content,
            "stderr": "",
            "returncode": 0,
        }
        logger.debug(f"[HANDS] file_read OK: {file_path} ({len(content)} chars)")
        return result
        
    except Exception as e:
        logger.error(f"[HANDS] file_read error: {e}")
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def install_python_package(package_name: str, timeout: int = 600, force: bool = False) -> Dict[str, Any]:
    """
    Устанавливает Python-пакет через pip в текущую среду.

    Параметры:
        package_name : str  — имя пакета (например, 'quantuminspire', 'qiskit')
        timeout      : int  — таймаут установки в секундах
        force        : bool — принудительная переустановка (--force-reinstall --no-deps)

    Возвращает:
        словарь с результатом установки
    """
    logger.debug(f"[HANDS] install_python_package: {package_name} (force={force})")

    if not package_name or not package_name.strip():
        return {"success": False, "stdout": "", "stderr": "Имя пакета не указано.", "returncode": -1}

    # Очищаем имя пакета от лишних символов
    package_name = package_name.strip().strip("'\"")

    try:
        import subprocess as _sp
        import re as _re_clean
        import shutil as _shutil

        def _pip_install():
            args = [sys.executable, "-m", "pip", "install", package_name]
            if force:
                args += ["--force-reinstall", "--no-deps"]
            return _sp.run(
                args,
                capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )

        result = _pip_install()

        if result.returncode != 0 and "invalid distribution" in (result.stderr or "").lower():
            # Остатки прерванной установки: каталог "~имя_пакета" в site-packages.
            # pip игнорирует его, но из-за него не может корректно установить пакет.
            # Удаляем остаток и повторяем установку.
            m = _re_clean.search(r"invalid distribution ~([\w\-_.]+) \(([^)]+)\)", result.stderr, _re_clean.IGNORECASE)
            if m:
                bad_dir = Path(m.group(2)) / ("~" + m.group(1))
                if bad_dir.exists():
                    logger.warning(f"[HANDS] Removing broken leftover directory: {bad_dir}")
                    _shutil.rmtree(bad_dir, ignore_errors=True)
                    result = _pip_install()

        if result.returncode == 0:
            logger.info(f"[HANDS] Пакет {package_name} успешно установлен")
            return {
                "success": True,
                "stdout": f"Пакет {package_name} успешно установлен. Попробуйте выполнить задачу снова.",
                "stderr": "",
                "returncode": 0,
            }
        else:
            stderr = (result.stderr or "")[:2000]
            stdout = (result.stdout or "")[:2000]
            error_text = stderr or stdout
            logger.warning(f"[HANDS] Ошибка установки {package_name}: {error_text[:200]}")

            # Проверяем специфичные ошибки
            if "No matching distribution" in error_text or "could not find" in error_text.lower():
                hint = f"Пакет {package_name} не найден в PyPI. Проверьте правильность написания."
            elif "connection error" in error_text.lower() or "timeout" in error_text.lower():
                hint = f"Ошибка сети при установке {package_name}. Проверьте интернет-соединение."
            elif "permission denied" in error_text.lower():
                hint = f"Недостаточно прав для установки {package_name}. Попробуйте запустить от имени администратора."
            else:
                hint = f"Не удалось установить {package_name}. Ошибка: {error_text[:300]}"

            return {
                "success": False,
                "stdout": "",
                "stderr": hint,
                "returncode": result.returncode,
            }

    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Таймаут установки {package_name} ({timeout}с).", "returncode": -1}
    except Exception as e:
        logger.error(f"[HANDS] Ошибка install_python_package: {e}")
        return {"success": False, "stdout": "", "stderr": f"Ошибка установки: {e}", "returncode": -1}


def automator(instruction_path: str, timeout: int = 600) -> Dict[str, Any]:
    """Запустить Project Automator с указанной инструкцией.
    
    Проверяет, что Automator установлен, и запускает его.
    Возвращает stdout/stderr Automator-а.
    """
    logger.debug(f"[HANDS] automator: {instruction_path}")
    
    try:
        instr_path = Path(instruction_path).expanduser().resolve()
        
        if not instr_path.exists():
            msg = f"Instruction file not found: {instr_path}"
            logger.warning(f"[HANDS] {msg}")
            return {"success": False, "stdout": "", "stderr": msg, "returncode": -1}
        
        # Проверяем, установлен ли automator как пакет
        # Если нет — добавляем его путь в PYTHONPATH
        env = dict(AUTOMATOR_PATH=str(AUTOMATOR_PATH))
        
        import subprocess as _sp
        check = _sp.run(
            [sys.executable, "-c", "import automator"],
            capture_output=True, text=True,
            cwd=str(AUTOMATOR_PATH),
        )
        if check.returncode != 0:
            # Пакет не установлен — добавляем в PYTHONPATH
            env["PYTHONPATH"] = str(AUTOMATOR_PATH)
            logger.warning(f"[HANDS] automator not installed as package, adding PYTHONPATH={AUTOMATOR_PATH}")
        
        # Запускаем как модуль из корня AUTOMATOR_PATH
        shell_cmd = [
            sys.executable, "-m", "automator.cli",
            str(instr_path),
            "--verbose",
        ]
        
        logger.debug(f"[HANDS] Running automator: {' '.join(shell_cmd)}")
        
        import os as _os
        full_env = dict(_os.environ)
        full_env["MPLBACKEND"] = "Agg"
        full_env.update(env)
        
        result = subprocess.run(
            shell_cmd,
            capture_output=True,
            text=True,
            timeout=300,  # Automator может работать долго
            encoding="utf-8",
            errors="replace",
            cwd=str(AUTOMATOR_PATH),
            env=full_env,
        )
        
        output = {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
        
        logger.debug(f"[HANDS] Automator result: success={output['success']}, "
                     f"stdout_len={len(result.stdout)}")
        
        return output
        
    except subprocess.TimeoutExpired:
        logger.warning(f"[HANDS] Automator timeout")
        return {"success": False, "stdout": "", "stderr": "Automator timeout (300s)", "returncode": -1}
    except Exception as e:
        logger.error(f"[HANDS] Automator error: {e}")
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def quantum(mode: str = "bell", ibm_token: str = "", shots: int = 1024, noise_path: str = "", **kwargs) -> Dict[str, Any]:
    """Quantum module. mode: bell | noise | real"""
    try:
        import importlib
        qt_spec = importlib.util.find_spec("quantum_kit.quantum_tools")
        if qt_spec is None:
            return {"success": False, "error": "quantum_kit.quantum_tools module not found"}
        from quantum_kit.quantum_tools import simulate, load_noise_model, run_on_real, generate_default_noise
        from qiskit import QuantumCircuit

        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])

        if mode == "bell":
            result = simulate(qc, shots=shots)
            if result["success"]:
                result["noise_params"] = None
            return result

        elif mode == "noise":
            noise_model = None
            noise_desc = "default_depolarizing_p=0.05"
            if noise_path:
                noise_model = load_noise_model(noise_path)
                noise_desc = f"from_file:{noise_path}"
            else:
                from quantum_kit.noise_model import NoiseModel
                nm = NoiseModel()
                nm.generate_depolarizing(0.05)
                noise_model = nm
            result = simulate(qc, shots=shots, noise_model=noise_model)
            if result["success"]:
                result["noise_params"] = {"model": noise_desc}
            return result

        elif mode == "real":
            if not ibm_token:
                return {"success": False, "error": "SIMULATOR_FIRST: Run mode='bell' first to prove simulation works. Then ask the user for their IBM Quantum API token (ibm_token)."}
            return run_on_real(qc, api_key=ibm_token, shots=shots)

        else:
            return {"success": False, "error": f"Unknown quantum mode: {mode}"}
    except ImportError as e:
        return {"success": False, "error": f"Qiskit import error: {e}"}
    except Exception as e:
        err_str = str(e)
        if "DLL" in err_str or "dll" in err_str.lower():
            return {"success": False, "error": f"Qiskit-Aer DLL error: {e}. This is a system dependency issue on Windows."}
        return {"success": False, "error": f"Quantum error: {e}"}


def glob(pattern: str, path: str = "") -> Dict[str, Any]:
    """Find files matching a glob pattern. Like opencode's Glob tool.
    
    Examples:
      pattern="**/*.py"  — all Python files recursively
      pattern="*.json"   — JSON files in root
      pattern="src/**/*.ts" — TypeScript files in src/
    """
    logger.debug(f"[HANDS] glob: {pattern} in {path or 'cwd'}")
    try:
        import glob as glob_module
        search_path = Path(path).expanduser().resolve() if path else Path.cwd()
        logger.info(f"[HANDS] glob search_path={search_path}")
        full_pattern = str(search_path / pattern)
        matches = glob_module.glob(full_pattern, recursive=True)
        result = "\n".join(sorted(matches)) if matches else "(no matches)"
        return {
            "success": True,
            "stdout": result,
            "stderr": "",
            "returncode": 0,
            "cwd": str(Path.cwd()),
            "search_path": str(search_path),
        }
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def grep(pattern: str, include: str = "", path: str = "") -> Dict[str, Any]:
    """Search file contents by regex pattern. Like opencode's Grep tool.
    
    Examples:
      pattern="class.*Handler" — find class definitions
      pattern="def quantum" include="*.py" — find quantum functions in Python files
      pattern="TODO|FIXME"    — find todos
    """
    logger.debug(f"[HANDS] grep: '{pattern}' in {path or 'cwd'} incl={include or '*'}")
    try:
        search_path = Path(path).expanduser().resolve() if path else Path.cwd()
        matches = []
        file_filter = include or "*"
        import glob as glob_module
        for f in sorted(glob_module.glob(str(search_path / file_filter), recursive=True)):
            fpath = Path(f)
            if not fpath.is_file():
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                import re
                if re.search(pattern, line):
                    matches.append(f"{fpath}:{i}: {line.rstrip()}")
        result = "\n".join(matches) if matches else "(no matches)"
        return {
            "success": True,
            "stdout": result,
            "stderr": "",
            "returncode": 0,
        }
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


# Словарь действий: имя → функция
ACTIONS = {
    "shell": shell,
    "file_write": file_write,
    "file_read": file_read,
    "automator": automator,
    "quantum": quantum,
    "glob": glob,
    "grep": grep,
    # ML-инструменты
    "fetch_dataset": fetch_dataset,
    "run_local_ml": run_local_ml,
    "run_cloud_gpu_ml": run_cloud_gpu_ml,
    "parse_ml_metrics": parse_ml_metrics,
    # ML-инструмент для Modal.com
    "run_modal_ml": run_modal_ml,
    # ML-инструмент для удалённого GPU через SSH
    "run_ssh_ml": run_ssh_ml,
    # Биоинструменты (биопрограммирование, Cortical Labs)
    "run_bio_check": run_bio_check,
    "run_bio_ml": run_bio_ml,
    # Нейроинструменты (нейроморфные вычисления, SNN)
    "run_neuro_check": run_neuro_check,
    "run_neuro_ml": run_neuro_ml,
    # Псевдонимы для run_ssh_ml (AI может назвать инструмент иначе)
    "run_code": run_ssh_ml,
    "execute_python": run_ssh_ml,
    "train_model": run_ssh_ml,
    # Системный инструмент: установка Python-пакетов
    "install_python_package": install_python_package,
    # Новые квантовые инструменты
    "quantum_simulator": run_quantum_simulator,
    "draw_circuit": draw_circuit_fn,
    "parse_result": parse_quantum_result,
    # Инструменты для работы с реальным IBM Quantum
    "get_backends": get_available_backends,
    "transpile_circuit": transpile_circuit,
    "run_on_real": run_on_real_hardware,
    # Инструмент для работы с Quantum Inspire
    "run_on_quantum_inspire": run_on_quantum_inspire,
    # Продвинутые квантовые инструменты
    "apply_error_mitigation": apply_error_mitigation,
    "compare_backends": compare_backends,
}

# Список доступных действий (для UI)
AVAILABLE_ACTIONS = list(ACTIONS.keys())


def execute_tool(tool_block: Dict[str, Any]) -> Dict[str, Any]:
    action = tool_block.get("action", "").lower()
    logger.debug(f"[HANDS] execute_tool: {action}")
    
    if action not in ACTIONS:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}",
            "returncode": -1,
        }
    
    params = {k: v for k, v in tool_block.items() if k != "action"}
    
    # Parameter name aliases (model sometimes guesses wrong names)
    PARAM_ALIASES = {
        "file_read": {"start": "path", "file": "path", "filepath": "path", "file_path": "path", "line": "path", "offset": "path", "lines": "path", "name": "path", "filename": "path"},
        "file_write": {"file": "path", "filepath": "path", "file_path": "path", "text": "content", "data": "content", "body": "content"},
        "shell": {"cmd": "command", "exec": "command", "script": "command", "code": "command"},
        "quantum_simulator": {"code": "quantum_code", "script": "quantum_code", "source": "quantum_code", "circuit": "quantum_code"},
        "draw_circuit": {"code": "quantum_code", "script": "quantum_code", "source": "quantum_code", "circuit": "quantum_code"},
        "parse_result": {"result": "raw_result", "data": "raw_result", "json": "raw_result"},
        "get_backends": {"token": "ibm_api_key", "api_key": "ibm_api_key", "key": "ibm_api_key"},
        "transpile_circuit": {"token": "ibm_api_key", "api_key": "ibm_api_key", "key": "ibm_api_key", "backend": "backend_name", "code": "quantum_code"},
        "run_on_real": {"token": "ibm_api_key", "api_key": "ibm_api_key", "key": "ibm_api_key", "backend": "backend_name", "code": "quantum_code"},
        "run_on_quantum_inspire": {"qasm": "qasm_code", "code": "qasm_code", "token": "qi_api_token", "api_token": "qi_api_token"},
        "apply_error_mitigation": {"qasm": "qasm_code", "code": "qasm_code", "technique": "mitigation_technique", "method": "mitigation_technique"},
        "compare_backends": {"list": "backend_list", "backends": "backend_list", "names": "backend_list"},
        "install_python_package": {"package": "package_name", "name": "package_name", "pkg": "package_name", "packages": "package_name"},
        "fetch_dataset": {"name": "dataset_name", "dataset": "dataset_name", "data_name": "dataset_name", "token": "hf_token"},
        "run_local_ml": {"code": "ml_code", "script": "ml_code", "python_code": "ml_code", "source": "ml_code"},
        "run_cloud_gpu_ml": {"code": "ml_code", "script": "ml_code", "username": "kaggle_username", "key": "kaggle_key", "api_key": "kaggle_key"},
        "parse_ml_metrics": {"metrics": "raw_metrics", "data": "raw_metrics", "results": "raw_metrics", "report": "raw_metrics"},
        "run_modal_ml": {"code": "ml_code", "script": "ml_code", "python_code": "ml_code", "source": "ml_code"},
        "run_ssh_ml": {"code": "ml_code", "script": "ml_code", "python_code": "ml_code", "source": "ml_code", "host": "ssh_host", "port": "ssh_port", "user": "ssh_username", "username": "ssh_username", "key": "ssh_key_path", "key_path": "ssh_key_path", "private_key": "ssh_key_path", "pass": "password", "pwd": "password", "ssh_password": "password"},
        "run_bio_check": {"project": "bio_project_path", "project_path": "bio_project_path", "path": "bio_project_path"},
        "run_bio_ml": {"code": "bio_code", "script": "bio_code", "python_code": "bio_code", "source": "bio_code", "project": "bio_project_path", "project_path": "bio_project_path"},
        "run_neuro_check": {"project": "neuro_python_path", "project_path": "neuro_python_path", "path": "neuro_python_path", "python": "neuro_python_path", "python_path": "neuro_python_path"},
        "run_neuro_ml": {"code": "neuro_code", "script": "neuro_code", "python_code": "neuro_code", "source": "neuro_code", "project": "neuro_python_path", "project_path": "neuro_python_path", "path": "neuro_python_path", "python": "neuro_python_path", "python_path": "neuro_python_path"},
    }
    
    if action in PARAM_ALIASES:
        aliases = PARAM_ALIASES[action]
        for wrong_name, correct_name in aliases.items():
            if wrong_name in params and correct_name not in params:
                params[correct_name] = params.pop(wrong_name)
    
    try:
        func = ACTIONS[action]
        import inspect
        sig = inspect.signature(func)
        expected = list(sig.parameters.keys())
        filtered = {}
        for k, v in params.items():
            if k in expected:
                # Coerce types when possible
                param_type = sig.parameters[k].annotation
                if param_type is str and not isinstance(v, str):
                    v = str(v)
                filtered[k] = v
            else:
                logger.warning(f"[HANDS] Ignoring unexpected param '{k}={v}' for {action}. Expected: {expected}")
        result = func(**filtered)
        return result
    except TypeError as e:
        logger.error(f"[HANDS] Wrong params for {action}: {e}")
        func = ACTIONS[action]
        import inspect
        sig = inspect.signature(func)
        expected = list(sig.parameters.keys())
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Wrong parameters for {action}: {e}. Expected: {expected}. Got: {list(params.keys())}",
            "returncode": -1,
        }
    except Exception as e:
        logger.error(f"[HANDS] Error executing {action}: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Error: {e}",
            "returncode": -1,
        }
