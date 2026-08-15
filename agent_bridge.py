"""
agent_bridge.py — Мост для запуска ML-кода на облачном GPU через Modal.com.

Класс ModalAgentBridge:
  1. Принимает Python-код и Modal credentials
  2. Устанавливает переменные окружения MODAL_TOKEN_ID / MODAL_TOKEN_SECRET
  3. Сохраняет код во временный .py файл
  4. Запускает через `modal run <file>`
  5. Перехватывает stdout/stderr
  6. Обрабатывает таймауты (до 30 мин)
  7. Возвращает структурированный результат
"""

import os
import sys
import json
import tempfile
import subprocess
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("agent.agent_bridge")

MODAL_RUN_TIMEOUT = 1800  # 30 минут
MAX_RETRIES = 5


class ModalAgentBridge:
    def __init__(self, token_id: str = "", token_secret: str = ""):
        self.token_id = token_id or os.environ.get("MODAL_TOKEN_ID", "")
        self.token_secret = token_secret or os.environ.get("MODAL_TOKEN_SECRET", "")
        self.temp_dir = Path(tempfile.gettempdir()) / "modal_agent_runs"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_code(self, code: str) -> str:
        """Проверяет, что код содержит @app.function или @app.local_entrypoint.
        Если нет — оборачивает в простую функцию."""
        stripped = code.strip()
        if "@app." in stripped:
            return code
        wrapped = (
            'import modal\n'
            f'app = modal.App("agent_ml_task")\n'
            '\n'
            '\n'
            f'{code}\n'
            '\n'
            '@app.local_entrypoint()\n'
            'def main():\n'
        )
        for line in code.split("\n"):
            wrapped += f"    {line}\n"
        return wrapped

    def _validate_credentials(self) -> bool:
        """Проверяет, что credentials заполнены."""
        return bool(self.token_id and self.token_secret)

    def _get_env(self) -> Dict[str, str]:
        """Формирует окружение с Modal токенами (без логирования secret)."""
        env = dict(os.environ)
        env["MODAL_TOKEN_ID"] = self.token_id
        env["MODAL_TOKEN_SECRET"] = self.token_secret
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["MPLBACKEND"] = "Agg"
        return env

    def _write_temp_script(self, code: str) -> Path:
        """Сохраняет код во временный файл."""
        import uuid
        filename = f"modal_agent_{uuid.uuid4().hex[:12]}.py"
        filepath = self.temp_dir / filename
        filepath.write_text(code, encoding="utf-8")
        logger.debug(f"[MODAL_BRIDGE] Script saved: {filepath}")
        return filepath

    def _cleanup(self, filepath: Path):
        """Удаляет временный файл."""
        try:
            if filepath.exists():
                filepath.unlink()
        except Exception as e:
            logger.warning(f"[MODAL_BRIDGE] Cleanup error: {e}")

    def _detect_image_deps(self, stderr: str) -> list:
        """Анализирует stderr на ModuleNotFoundError и возвращает список пакетов."""
        deps = []
        for m in re.finditer(
            r"ModuleNotFoundError.*?No module named ['\"]([^'\"]+)['\"]",
            stderr, re.IGNORECASE
        ):
            pkg = m.group(1).split(".")[0].lower()
            if pkg not in deps:
                deps.append(pkg)
        for m in re.finditer(
            r"No module named ['\"]([^'\"]+)['\"]",
            stderr, re.IGNORECASE
        ):
            pkg = m.group(1).split(".")[0].lower()
            if pkg not in deps:
                deps.append(pkg)
        return deps

    def _detect_oom(self, stderr: str) -> bool:
        """Проверяет, есть ли CUDA Out of Memory."""
        patterns = [
            "CUDA out of memory",
            "out of memory",
            "CUDA_OOM",
            "memory exceeded",
            "allocate",
        ]
        return any(p.lower() in stderr.lower() for p in patterns)

    def run(
        self,
        code: str,
        timeout: int = MODAL_RUN_TIMEOUT,
    ) -> Dict[str, Any]:
        """
        Запускает Python-код на Modal.

        Параметры:
            code    : str — Python-код для выполнения
            timeout : int — таймаут в секундах (по умолч. 1800)

        Возвращает:
            {"success": bool, "stdout": str, "stderr": str,
             "return_code": int, "diagnosis": dict}
        """
        if not self._validate_credentials():
            return {
                "success": False,
                "stdout": "",
                "stderr": (
                    "Modal credentials not configured.\n"
                    "Please fill in Modal Token ID and Modal Token Secret "
                    "in the sidebar and click Save."
                ),
                "return_code": -1,
                "diagnosis": {"action": "request_credentials"},
            }

        script_path = None
        diagnosis = {}
        max_retries = 3
        retry_delay = 5

        try:
            final_code = self._sanitize_code(code)
            script_path = self._write_temp_script(final_code)

            env = self._get_env()

            last_stdout = ""
            last_stderr = ""
            last_rc = -1

            for attempt in range(1, max_retries + 1):
                logger.info(f"[MODAL_BRIDGE] Running: modal run {script_path.name} (attempt {attempt}/{max_retries})")
                proc = subprocess.run(
                    [sys.executable, "-m", "modal", "run", str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    cwd=str(self.temp_dir),
                )
                last_stdout = proc.stdout or ""
                last_stderr = proc.stderr or ""
                last_rc = proc.returncode

                if last_rc == 0:
                    break

                is_connection_error = any(
                    p in (last_stderr + last_stdout).lower()
                    for p in ["heartbeat failed", "cancellederror", "grpclib",
                              "connection refused", "connection reset",
                              "deadline exceeded", "connection closed",
                              "remote end closed connection"]
                )
                if is_connection_error and attempt < max_retries:
                    logger.warning(f"[MODAL_BRIDGE] Connection error on attempt {attempt}, retrying in {retry_delay}s...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                break

            stdout = last_stdout
            stderr = last_stderr
            rc = last_rc

            diagnosis = {
                "return_code": rc,
                "stderr_len": len(stderr),
            }

            missing_deps = self._detect_image_deps(stderr + stdout)
            if missing_deps:
                diagnosis["missing_deps"] = missing_deps
                diagnosis["action"] = "install_deps_and_retry"

            is_oom = self._detect_oom(stderr + stdout)
            if is_oom:
                diagnosis["oom_detected"] = True
                diagnosis["action"] = "reduce_batch_size"

            success = rc == 0

            logger.info(
                f"[MODAL_BRIDGE] Done: success={success}, rc={rc}, "
                f"stdout={len(stdout)}b, stderr={len(stderr)}b"
            )

            return {
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
                "return_code": rc,
                "diagnosis": diagnosis,
            }

        except subprocess.TimeoutExpired:
            logger.warning(f"[MODAL_BRIDGE] Timeout after {timeout}s")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Timeout after {timeout}s. "
                         f"Consider optimizing the code or increasing timeout.",
                "return_code": -1,
                "diagnosis": {"action": "timeout", "timeout_s": timeout},
            }
        except FileNotFoundError:
            logger.error("[MODAL_BRIDGE] modal CLI not found")
            return {
                "success": False,
                "stdout": "",
                "stderr": (
                    "Modal CLI not found. Install it:\n"
                    "pip install modal\n"
                    "modal setup"
                ),
                "return_code": -1,
                "diagnosis": {"action": "install_modal"},
            }
        except Exception as e:
            logger.error(f"[MODAL_BRIDGE] Error: {e}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Modal run error: {e}",
                "return_code": -1,
                "diagnosis": {"action": "unknown_error", "error": str(e)},
            }
        finally:
            if script_path:
                self._cleanup(script_path)

    @staticmethod
    def build_self_heal_prompt(diagnosis: dict, attempt: int, max_attempts: int) -> str:
        """Генерирует nudge для AI на основе диагноза."""
        action = diagnosis.get("action", "")

        if action == "request_credentials":
            return (
                "You need Modal.com credentials to run cloud GPU tasks.\n"
                "Politely ask the user to fill in Modal Token ID and Modal Token Secret "
                "in the sidebar and click Save."
            )

        if action == "install_modal":
            return (
                "Modal CLI is not installed. Ask the user to run:\n"
                "  pip install modal\n"
                "  modal setup\n"
                "Then retry."
            )

        if action == "timeout":
            return (
                f"The Modal run timed out after {diagnosis.get('timeout_s', '?')}s. "
                "Optimize the code: reduce data size, use a smaller model, "
                "or increase parallelism. Then retry."
            )

        missing_deps = diagnosis.get("missing_deps", [])
        if missing_deps:
            deps_str = ", ".join(missing_deps)
            return (
                f"Self-heal attempt {attempt}/{max_attempts}: "
                f"missing Python packages detected: {deps_str}. "
                f"Regenerate the code with these imports added to the Modal image:\n"
                f'  image = modal.Image.debian_slim().pip_install("{'", "'.join(missing_deps)}")\n'
                f"Then retry the run."
            )

        if diagnosis.get("oom_detected"):
            return (
                f"Self-heal attempt {attempt}/{max_attempts}: "
                "CUDA out of memory. Regenerate the code with:\n"
                "- Smaller batch size (batch_size //= 2)\n"
                "- Smaller model or fewer parameters\n"
                "- DataLoader with num_workers=0\n"
                "Then retry."
            )

        return (
            f"Self-heal attempt {attempt}/{max_attempts}: "
            f"The Modal run failed with return code {diagnosis.get('return_code', '?')}. "
            f"Analyze the error above, fix the code, and retry."
        )
