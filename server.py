import json
import os
import re
import sys
import uuid
import threading
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from flask import Flask, request, jsonify, render_template, Response, stream_with_context

from config import logger, HOST, PORT, DEBUG, SECRET_KEY, AI_MODE, AUTOMATOR_PATH
from ai_client import AIClient
from hands import execute_tool
from system_prompt import get_system_prompt

# Fix CWD: always use agent's own directory, not PyInstaller temp folder
if getattr(sys, 'frozen', False):
    _agent_dir = Path(sys.executable).parent  # EXE location
else:
    _agent_dir = Path(__file__).resolve().parent  # server.py location
os.chdir(str(_agent_dir))
os.environ["AGENT_DIR"] = str(_agent_dir)
logger.info(f"[CWD] Changed to: {os.getcwd()} (frozen={getattr(sys, 'frozen', False)})")

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.jinja_env.auto_reload = True

class Session:
    def __init__(self, session_id: str):
        self.id = session_id
        self.messages: List[Dict[str, str]] = []
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.is_running = False
        self.stop_requested = False
        self.ibm_token: str = ""
        self.qi_api_token: str = ""
        self.qi_email: str = ""
        self.qi_password: str = ""
        self.hf_token: str = ""
        self.kaggle_key: str = ""
        self.modal_token_id: str = ""
        self.modal_token_secret: str = ""
        self.ssh_host: str = ""
        self.ssh_port: int = 22
        self.ssh_username: str = ""
        self.ssh_key_path: str = ""
        self.ssh_password: str = ""
        self.bio_project_path: str = ""
        self.neuro_python_path: str = ""

    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content, "timestamp": datetime.now().isoformat()})
        self.updated_at = datetime.now()
        _save_session(self)

    def add_assistant_message(self, content: str):
        self.messages.append({"role": "assistant", "content": content, "timestamp": datetime.now().isoformat()})
        self.updated_at = datetime.now()
        _save_session(self)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "messages": self.messages,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_running": self.is_running,
        }


SESSIONS_DIR = Path(__file__).parent / "sessions_data"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:64]
    return SESSIONS_DIR / f"{safe}.json"


def _save_session(session: Session):
    try:
        with open(_session_path(session.id), "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"[SESSION] Save failed: {e}")


def _load_session(session_id: str) -> Optional[Session]:
    p = _session_path(session_id)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        s = Session(session_id)
        s.messages = data.get("messages", [])
        s.created_at = datetime.fromisoformat(data.get("created_at", datetime.now().isoformat()))
        s.updated_at = datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat()))
        s.is_running = False
        s.stop_requested = False
        return s
    except Exception as e:
        logger.warning(f"[SESSION] Load failed: {e}")
        return None


def _delete_session_file(session_id: str):
    try:
        p = _session_path(session_id)
        if p.exists():
            p.unlink()
    except Exception as e:
        logger.warning(f"[SESSION] Delete failed: {e}")


sessions: Dict[str, Session] = {}
sessions_lock = threading.Lock()
ai_client = AIClient()


def get_or_create_session(session_id: Optional[str] = None) -> Session:
    with sessions_lock:
        if session_id and session_id in sessions:
            return sessions[session_id]
        new_id = session_id or str(uuid.uuid4())[:8]
        session = Session(new_id)
        restored = _load_session(new_id) if session_id else None
        if restored is not None:
            sessions[new_id] = restored
            return restored
        sessions[new_id] = session
        if len(sessions) > 100:
            oldest = sorted(sessions.keys(), key=lambda k: sessions[k].updated_at)[:50]
            for k in oldest:
                del sessions[k]
        return session


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/test", methods=["GET"])
def test_route():
    return jsonify({"ok": True, "path": "/api/test"})

@app.route("/api/debug", methods=["GET"])
def debug_info():
    import os as _os
    cwd = _os.getcwd()
    logger.info(f"[DEBUG] CWD at request time: {cwd}")
    logger.info(f"[DEBUG] AGENT_DIR: {_os.environ.get('AGENT_DIR', 'NOT SET')}")
    logger.info(f"[DEBUG] Frozen: {getattr(sys, 'frozen', False)}")
    return jsonify({
        "cwd": cwd,
        "agent_dir": _os.environ.get("AGENT_DIR", "NOT SET"),
        "frozen": getattr(sys, 'frozen', False),
        "executable": str(Path(sys.executable).resolve()),
    })

@app.route("/api/session", methods=["POST"])
def create_session():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    session = get_or_create_session(session_id)
    return jsonify({"session_id": session.id})


@app.route("/api/messages", methods=["GET"])
def get_messages():
    session_id = request.args.get("session_id", "")
    session = get_or_create_session(session_id)
    return jsonify({"messages": session.to_dict()["messages"]})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    message = data.get("message", "").strip()
    mode = data.get("mode", AI_MODE)
    api_key = data.get("api_key", "") or request.headers.get("X-API-Key", "")
    ibm_token = data.get("ibm_token", "") or data.get("ibm_api_key", "")
    qi_api_token = data.get("qi_api_token", "")
    qi_email = data.get("qi_email", "")
    qi_password = data.get("qi_password", "")
    hf_token = data.get("hf_token", "")
    kaggle_key = data.get("kaggle_key", "")
    modal_token_id = data.get("modal_token_id", "")
    modal_token_secret = data.get("modal_token_secret", "")
    ssh_host = data.get("ssh_host", "")
    ssh_port = data.get("ssh_port", 22)
    ssh_username = data.get("ssh_username", "")
    ssh_key_path = data.get("ssh_key_path", "")
    ssh_password = data.get("ssh_password", "")
    bio_project_path = data.get("bio_project_path", "")
    neuro_python_path = data.get("neuro_python_path", "")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    session = get_or_create_session(session_id)

    if session.is_running:
        return jsonify({"error": "Session is busy"}), 429

    # Zen mode never needs an API key вЂ” using "Bearer public"
    if mode == 'zen':
        effective_key = None
    else:
        effective_key = api_key if api_key else None
    if mode:
        ai_client.switch_mode(mode, api_key=effective_key)

    session.empty_retries = 0
    session.ibm_token = ibm_token
    session.qi_api_token = qi_api_token
    session.qi_email = qi_email
    session.qi_password = qi_password
    session.hf_token = hf_token
    session.kaggle_key = kaggle_key
    session.modal_token_id = modal_token_id
    session.modal_token_secret = modal_token_secret
    session.ssh_host = ssh_host
    try:
        session.ssh_port = int(ssh_port) if ssh_port else 22
    except (ValueError, TypeError):
        session.ssh_port = 22
    session.ssh_username = ssh_username
    session.ssh_key_path = ssh_key_path
    session.ssh_password = ssh_password
    session.bio_project_path = bio_project_path
    session.neuro_python_path = neuro_python_path
    session.add_user_message(message)
    session.is_running = True
    session.stop_requested = False

    def generate():
        try:
            yield from _process_agent_loop(session, api_key=api_key, ibm_token=ibm_token, qi_api_token=qi_api_token, qi_email=qi_email, qi_password=qi_password, hf_token=hf_token, kaggle_key=kaggle_key, modal_token_id=modal_token_id, modal_token_secret=modal_token_secret, ssh_host=ssh_host, ssh_port=session.ssh_port, ssh_username=ssh_username, ssh_key_path=ssh_key_path, ssh_password=ssh_password, bio_project_path=bio_project_path, neuro_python_path=neuro_python_path)
        except Exception as e:
            import traceback as _tb
            logger.error(f"[CHAT] Agent loop crashed: {_tb.format_exc()}")
            try:
                yield _sse("error", {"content": f"Внутренняя ошибка агента: {type(e).__name__}: {e}"})
            except Exception:
                pass
        finally:
            with sessions_lock:
                session.is_running = False
                session.stop_requested = False

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@app.route("/api/ping_chat", methods=["POST"])
def ping_chat():
    """Non-streaming test endpoint"""
    data = request.get_json(silent=True) or {}
    msg = data.get("message", "").strip()
    if not msg:
        return jsonify({"error": "Message is required"}), 400
    # just call the LLM directly and return the response
    import json
    events = []
    try:
        session = get_or_create_session(data.get("session_id", ""))
        session.add_user_message(msg)
        session.is_running = True
        for ev in _process_agent_loop(session):
            events.append(ev)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        session.is_running = False
    return jsonify({"events": len(events), "first": events[0] if events else None})


@app.route("/api/stop", methods=["POST"])
def stop_chat():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    with sessions_lock:
        if session_id in sessions:
            sessions[session_id].stop_requested = True
            return jsonify({"status": "stopped"})
    return jsonify({"error": "Session not found"}), 404


@app.route("/api/clear", methods=["POST"])
def clear_session():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    with sessions_lock:
        if session_id in sessions:
            session = sessions[session_id]
            session.messages = []
            session.is_running = False
            session.stop_requested = False
            _delete_session_file(session_id)
            return jsonify({"status": "cleared"})
    return jsonify({"error": "Session not found"}), 404


def _sanitize_messages(messages):
    """Приводит последовательность сообщений к валидному виду для API.
    Осиротевшие tool-сообщения (без предшествующего assistant tool_calls)
    и хвостовые assistant tool_calls без ответа tool отбрасываются —
    иначе провайдер возвращает 400 'tool must be a response to a preceding message'."""
    clean = []
    pending_tool_ids = set()
    for m in messages:
        role = m.get("role")
        if role == "tool":
            if m.get("tool_call_id", "") in pending_tool_ids:
                clean.append(m)
        elif role == "assistant":
            clean.append(m)
            pending_tool_ids = {tc.get("id", "") for tc in (m.get("tool_calls") or []) if isinstance(tc, dict)}
        else:
            clean.append(m)
    while clean and clean[-1].get("role") == "assistant":
        if clean[-1].get("tool_calls"):
            clean.pop()
        else:
            break
    return clean


def _build_state_summary(messages, max_steps=15, max_len=3500) -> str:
    """Краткая сводка задачи и уже сделанных шагов.

    Нужна, когда история сжимается (пустой ответ, ошибка API):
    в тексте сохраняются исходная задача пользователя и список
    вызванных инструментов с результатами, чтобы модель не теряла
    контекст и продолжала работу, а не отвечала приветствием."""
    parts = []

    first_user = None
    for m in messages[1:]:
        if m.get("role") == "user" and first_user is None:
            first_user = str(m.get("content", ""))[:500]
            break
    if first_user:
        parts.append(f"Исходная задача пользователя: {first_user}")

    steps = []
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            for tc in m.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                fn = (tc.get("function") or {}).get("name", "?")
                args = (tc.get("function") or {}).get("arguments", {})
                try:
                    args_txt = json.dumps(args, ensure_ascii=False)
                except Exception:
                    args_txt = str(args)
                steps.append(f"  - вызван инструмент {fn}({args_txt[:150]})")
        elif role == "tool":
            content = str(m.get("content", "")).replace("\n", " ").strip()
            if content:
                steps.append(f"  - результат: {content[:250]}")

    if steps:
        parts.append("Что уже сделано:")
        parts.extend(steps[-max_steps:])
    else:
        parts.append("Пока ничего не сделано.")

    summary = "\n".join(parts)
    if len(summary) > max_len:
        summary = summary[:max_len] + "..."
    return summary


def _process_agent_loop(session: Session, api_key: str = "", ibm_token: str = "", qi_api_token: str = "", qi_email: str = "", qi_password: str = "", hf_token: str = "", kaggle_key: str = "", modal_token_id: str = "", modal_token_secret: str = "", ssh_host: str = "", ssh_port: int = 22, ssh_username: str = "", ssh_key_path: str = "", ssh_password: str = "", bio_project_path: str = "", neuro_python_path: str = ""):
    import time as _time
    from tools import TOOLS

    max_iterations = 40


    iteration = 0
    max_tool_errors = 6
    tool_errors_in_row = 0
    total_tool_errors = 0
    error_nudge_sent = False
    loop_forced_stop = False
    MAX_TOTAL_TIME = 1800
    PER_ITER_TIMEOUT = 600
    _start_time = _time.time()
    tool_call_history = []
    last_tool_sig = None
    max_repeated_tool_calls = 10
    no_tools_mode = False
    connection_retries = 0
    MAX_CONNECTION_RETRIES = 3
    modal_retry_count = 0

    created_py_files = set()
    tested_py_files = set()
    test_nudge_sent = False

    system_prompt = get_system_prompt()
    current_messages = [{"role": "system", "content": system_prompt}]
    current_messages.extend([{"role": m["role"], "content": m["content"]} for m in session.messages])

    # Сообщаем AI о наличии credentials, чтобы модель не просила заполнить боковую панель
    if ibm_token or qi_api_token or qi_email or qi_password or hf_token or kaggle_key or modal_token_id or bio_project_path or neuro_python_path:
        creds_parts = []
        if ibm_token:
            creds_parts.append("IBM API Key: \u043f\u0435\u0440\u0435\u0434\u0430\u043d")
        if qi_api_token:
            creds_parts.append("Quantum Inspire Token: \u043f\u0435\u0440\u0435\u0434\u0430\u043d")
        if qi_email:
            creds_parts.append("Quantum Inspire Email: \u043f\u0435\u0440\u0435\u0434\u0430\u043d")
        if qi_password:
            creds_parts.append("Quantum Inspire Password: \u043f\u0435\u0440\u0435\u0434\u0430\u043d")
        if hf_token:
            creds_parts.append("Hugging Face Token: \u043f\u0435\u0440\u0435\u0434\u0430\u043d")
        if kaggle_key:
            creds_parts.append("Kaggle API Key: \u043f\u0435\u0440\u0435\u0434\u0430\u043d")
        if modal_token_id and modal_token_secret:
            os.environ["MODAL_TOKEN_ID"] = modal_token_id
            os.environ["MODAL_TOKEN_SECRET"] = modal_token_secret
            creds_parts.append("Modal Token: передан (облачный GPU)")
        if hf_token:
            os.environ["HF_TOKEN"] = hf_token
        if bio_project_path:
            creds_parts.append("Био-проект: передан")
        if neuro_python_path:
            creds_parts.append("Нейро-окружение: передан")
        current_messages.append({
            "role": "system",
            "content": "[SYSTEM] \u0414\u0430\u043d\u043d\u044b\u0435 \u0438\u0437 \u0431\u043e\u043a\u043e\u0432\u043e\u0439 \u043f\u0430\u043d\u0435\u043b\u0438 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u044b. " + ", ".join(creds_parts) + ". \u041d\u0430\u0447\u0438\u043d\u0430\u044e \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435..."
        })

    while iteration < max_iterations:
        iteration += 1

        if session.stop_requested:
            break

        # Enforce total time limit
        elapsed = _time.time() - _start_time
        if elapsed > MAX_TOTAL_TIME:
            yield _sse("error", {"content": f"Total time limit reached ({MAX_TOTAL_TIME}s). The task took too long."})
            return

        ai_response_text = ""
        tool_calls_data = None
        had_error = False

        current_tools = None if no_tools_mode else TOOLS
        no_tools_mode = False

        for event in ai_client.chat(
            current_messages,
            api_key=api_key if api_key else None,
            tools=current_tools,
        ):
            if session.stop_requested:
                break
            if event["type"] == "chunk":
                ai_response_text += event["content"]
            elif event["type"] == "thinking":
                yield _sse("thinking", {"content": event["content"]})
            elif event["type"] == "tool_calls":
                tool_calls_data = event["calls"]
            elif event["type"] == "error":
                had_error = True
                error_msg = event["content"]
                # Модель слишком долго "размышляла" без ответа (обрыв на нашей стороне) —
                # обрабатываем как пустой ответ: nudge ниже скажет отвечать сразу.
                if "reasoning_only" in error_msg:
                    logger.warning(f"[AI] {error_msg}")
                    ai_response_text = ""
                    tool_calls_data = None
                    had_error = False
                    break
                # Connection errors — retry
                if ("Cannot connect" in error_msg or "Connection was interrupted" in error_msg or "Stream was cut" in error_msg or "Request timeout" in error_msg) and connection_retries < MAX_CONNECTION_RETRIES:
                    connection_retries += 1
                    wait = 2.0 * connection_retries
                    logger.warning(f"[AI] Connection error, retry {connection_retries}/{MAX_CONNECTION_RETRIES} in {wait}s...")
                    yield _sse("thinking", {"content": f"Ошибка соединения, повтор {connection_retries}/{MAX_CONNECTION_RETRIES} через {int(wait)}с..."})
                    _time.sleep(wait)
                    iteration -= 1
                    break
                # API error (400, 500, Upstream failed) — retry with reduced context
                if ("400" in error_msg or "500" in error_msg or "Upstream" in error_msg) and connection_retries < MAX_CONNECTION_RETRIES + 2:
                    connection_retries += 1
                    wait = 3.0 * connection_retries
                    logger.warning(f"[AI] API error, retry {connection_retries}/{MAX_CONNECTION_RETRIES+2} in {wait}s with reduced context...")
                    yield _sse("thinking", {"content": f"API временно недоступен, повтор {connection_retries} через {int(wait)}с..."})
                    _time.sleep(wait)
                    # Сжимаем контекст, но сохраняем сводку задачи, чтобы модель не потеряла её
                    _state = _build_state_summary(current_messages, max_len=2500)
                    current_messages = _sanitize_messages(current_messages[:1] + current_messages[-6:])
                    current_messages.append({
                        "role": "user",
                        "content": f"Контекст был сжат из-за ошибки API. Состояние задачи:\n{_state}\nПродолжай выполнение."
                    })
                    iteration -= 1
                    break
                yield _sse("error", {"content": error_msg})
                return

        if session.stop_requested:
            break

        if had_error and connection_retries <= MAX_CONNECTION_RETRIES:
            continue
        if had_error:
            yield _sse("error", {"content": "API провайдера временно недоступен (ошибка 400/500). Попробуйте позже или перезапустите сервер."})
            return

        connection_retries = 0  # reset on success

        if session.stop_requested:
            break

        # Small delay between iterations to avoid rate limiting
        _time.sleep(0.5)

        if tool_calls_data:
            tool_errors_in_row = 0

            current_tool_names = tuple(tc["function"]["name"] for tc in tool_calls_data)
            tool_call_history.append(current_tool_names)

            if len(tool_call_history) >= max_repeated_tool_calls:
                recent = tool_call_history[-max_repeated_tool_calls:]
                unique_tools = set()
                for tup in recent:
                    unique_tools.update(tup)
                if len(unique_tools) <= 2:
                    logger.warning(f"[AI] Tool call loop detected: {recent}")
                    nudge = (
                        f"You have been calling the same tool(s) repeatedly "
                        f"({', '.join(unique_tools)}) for {max_repeated_tool_calls}+ iterations without completing. "
                        "STOP calling tools. Analyze the results you already have and respond with a final answer."
                    )
                    current_messages.append({"role": "user", "content": nudge})
                    tool_call_history = []
                    continue

            sig = tuple(
                (tc["function"]["name"], json.dumps(tc["function"]["arguments"], sort_keys=True))
                for tc in tool_calls_data
            )
            if sig == last_tool_sig:
                logger.warning(f"[AI] Repeated exact tool call, sending nudge")
                current_messages.append({
                    "role": "user",
                    "content": "You just called the identical tool with identical arguments. Analyze the previous result and either call a DIFFERENT tool or respond with a final answer."
                })
                last_tool_sig = None
                continue
            last_tool_sig = sig

            openai_calls = []
            for tc in tool_calls_data:
                openai_calls.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": json.dumps(tc["function"]["arguments"], ensure_ascii=False),
                    }
                })
            assistant_msg = {"role": "assistant", "content": ai_response_text or None, "tool_calls": openai_calls}
            current_messages.append(assistant_msg)

            for tc in tool_calls_data:
                if session.stop_requested:
                    break

                tool_name = tc["function"]["name"]
                tool_args = tc["function"]["arguments"]
                tool_call_id = tc["id"]

                if not tool_call_id:
                    tool_call_id = f"call_{uuid.uuid4().hex[:12]}"

                # Validate that tool call has arguments
                if not tool_args or tool_args == {}:
                    error_msg = f"Tool call '{tool_name}' has empty arguments. AI must retry with proper parameters."
                    logger.warning(f"[AI] {error_msg}")
                    yield _sse("tool_result", {
                        "tool": {"action": tool_name},
                        "result": {"success": False, "stdout": "", "stderr": error_msg, "returncode": -1},
                        "formatted": f"Error: {error_msg}"
                    })
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": f"Error: {error_msg}",
                    })
                    tool_errors_in_row += 1
                    continue

                tool_block = {"action": tool_name, **tool_args}

                # РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРё РІСЃС‚Р°РІР»СЏРµРј ibm_token РІ РєРІР°РЅС‚РѕРІС‹Рµ РёРЅСЃС‚СЂСѓРјРµРЅС‚С‹, РµСЃР»Рё РѕРЅ РµСЃС‚СЊ
                if ibm_token and tool_name in ("quantum", "quantum_simulator", "get_backends", "transpile_circuit", "run_on_real"):
                    if "ibm_token" not in tool_block or not tool_block.get("ibm_token"):
                        tool_block["ibm_token"] = ibm_token
                        if "ibm_api_key" not in tool_block or not tool_block.get("ibm_api_key"):
                            tool_block["ibm_api_key"] = ibm_token

                # Всегда подставляем реальные credentials Quantum Inspire, если они есть
                # (AI может передать заглушки типа "__QI_EMAIL__", перезаписываем)
                if tool_name in ("run_on_quantum_inspire", "get_backends", "transpile_circuit", "apply_error_mitigation", "compare_backends"):
                    if qi_api_token:
                        tool_block["qi_api_token"] = qi_api_token
                    if qi_email:
                        tool_block["qi_email"] = qi_email
                    if qi_password:
                        tool_block["qi_password"] = qi_password

                # РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРё РІСЃС‚Р°РІР»СЏРµРј ML credentials РІ ML-РёРЅСЃС‚СЂСѓРјРµРЅС‚С‹
                if tool_name in ("fetch_dataset",):
                    if hf_token:
                        tool_block["hf_token"] = hf_token
                if tool_name in ("run_cloud_gpu_ml",):
                    if kaggle_key and ":" in kaggle_key:
                        parts = kaggle_key.split(":", 1)
                        tool_block["kaggle_username"] = parts[0]
                        tool_block["kaggle_key"] = parts[1]

                # РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРё РІСЃС‚Р°РІР»СЏРµРј SSH credentials РІ run_ssh_ml
                if tool_name in ("run_ssh_ml",):
                    if ssh_host and not tool_block.get("ssh_host"):
                        tool_block["ssh_host"] = ssh_host
                    if ssh_port and not tool_block.get("ssh_port"):
                        tool_block["ssh_port"] = ssh_port
                    if ssh_username and not tool_block.get("ssh_username"):
                        tool_block["ssh_username"] = ssh_username
                    if ssh_key_path and not tool_block.get("ssh_key_path"):
                        tool_block["ssh_key_path"] = ssh_key_path
                    if ssh_password and not tool_block.get("password"):
                        tool_block["password"] = ssh_password

                # Автоматически вставляем путь био-проекта в биоинструменты
                if tool_name in ("run_bio_check", "run_bio_ml"):
                    if bio_project_path and not tool_block.get("bio_project_path"):
                        tool_block["bio_project_path"] = bio_project_path

                # Автоматически вставляем путь нейро-окружения в нейроинструменты
                if tool_name in ("run_neuro_check", "run_neuro_ml"):
                    if neuro_python_path and not tool_block.get("neuro_python_path"):
                        tool_block["neuro_python_path"] = neuro_python_path


                yield _sse("tool_start", {"tool": _sanitize_tool_for_sse(tool_block)})

                # Долгие инструменты (обучение, установка пакетов) выполняются
                # минутами. Чтобы SSE-соединение не оборвалось из-за долгого
                # молчания ("Ошибка соединения: network error"), пока инструмент
                # работает, каждые 20 секунд отправляем heartbeat-событие.
                import concurrent.futures as _cf
                _tool_action = tool_block.get("action", "?")
                _executor = _cf.ThreadPoolExecutor(max_workers=1)
                _future = _executor.submit(execute_tool, tool_block)
                _t_start = _time.time()
                result = None
                while result is None:
                    try:
                        result = _future.result(timeout=20)
                    except _cf.TimeoutError:
                        if session.stop_requested:
                            result = {"success": False, "stdout": "", "stderr": "Операция остановлена пользователем.", "returncode": -1}
                            break
                        yield _sse("thinking", {"content": f"⏳ Инструмент {_tool_action} выполняется... уже {int(_time.time() - _t_start)}с"})
                _executor.shutdown(wait=False)
                result_text = _simple_tool_result(tool_block, result)
                yield _sse("tool_result", {"tool": _sanitize_tool_for_sse(tool_block), "result": result, "formatted": result_text})

                if not result.get("success", False):
                    tool_errors_in_row += 1
                    total_tool_errors += 1
                    # Self-healing: detect ModuleNotFoundError and auto-install
                    error_text = (result.get("stderr", "") or result.get("stdout", "") or "")
                    _healed = _try_self_heal(error_text, tool_block, tool_call_id, current_messages, ibm_token, qi_api_token, qi_email, qi_password)
                    if _healed:
                        tool_errors_in_row = max(0, tool_errors_in_row - 1)
                        # Auto-retry the same tool call without asking AI
                        retry_result = execute_tool(tool_block)
                        retry_text = _simple_tool_result(tool_block, retry_result)
                        if retry_result.get("success"):
                            yield _sse("tool_result", {"tool": _sanitize_tool_for_sse(tool_block), "result": retry_result, "formatted": retry_text, "retry": True})
                        current_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": retry_text,
                        })
                        if not retry_result.get("success"):
                            tool_errors_in_row += 1
                            total_tool_errors += 1
                        continue

                    # Self-healing: Modal-specific diagnosis (missing deps, OOM, timeout)
                    if tool_name == "run_modal_ml":
                        diagnosis = result.get("diagnosis", {})
                        if diagnosis:
                            from agent_bridge import ModalAgentBridge
                            modal_retry_count += 1
                            if modal_retry_count <= 5:
                                heal_prompt = ModalAgentBridge.build_self_heal_prompt(diagnosis, modal_retry_count, 5)
                                # Не увеличиваем счётчик ошибок для self-heal попыток Modal
                                tool_errors_in_row = max(0, tool_errors_in_row - 1)
                                total_tool_errors = max(0, total_tool_errors - 1)
                                current_messages.append({
                                    "role": "user",
                                    "content": heal_prompt,
                                })
                                result_text = f"[MODAL SELF-HEAL] Попытка {modal_retry_count}/5. {heal_prompt[:200]}"
                                yield _sse("tool_result", {"tool": tool_block, "result": result, "formatted": result_text, "self_heal": True})
                                continue

                # Сбрасываем счётчик Modal retry при успехе
                if tool_name == "run_modal_ml" and result.get("success", False):
                    modal_retry_count = 0

                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_text,
                })

                if tool_name == "file_write":
                    written_path = tool_args.get("path", "")
                    if written_path.endswith(".py"):
                        created_py_files.add(written_path)
                        logger.info(f"[TEST] Created .py file: {written_path}")

                if tool_name == "shell":
                    cmd = tool_args.get("command", "")
                    for pyf in list(created_py_files):
                        py_basename = os.path.basename(pyf)
                        if py_basename in cmd or pyf in cmd:
                            tested_py_files.add(pyf)
                            logger.info(f"[TEST] .py file tested via shell: {pyf}")

            if tool_errors_in_row >= max_tool_errors or total_tool_errors >= 12:
                if not error_nudge_sent:
                    error_nudge_sent = True
                    tool_errors_in_row = 0
                    nudge = (
                        f"CRITICAL: {tool_errors_in_row} consecutive / {total_tool_errors} total tool errors. "
                        "HALT all tool calls. Step back and analyze the root cause. "
                        "Respond with a clear message to the user explaining what went wrong "
                        "and what they need to do to fix it (install packages, check credentials, etc). "
                        "DO NOT call any more tools."
                    )
                    current_messages.append({"role": "user", "content": nudge})
                    no_tools_mode = True
                    continue
                # Second nudge already sent, force stop
                logger.warning(f"[AI] Forced stop after {total_tool_errors} total tool errors")
                yield _sse("error", {"content": f"Слишком много ошибок ({total_tool_errors}). Анализ прерван. Попробуйте переформулировать запрос или проверьте данные в боковой панели."})
                return

            untested = created_py_files - tested_py_files
            if untested and not test_nudge_sent:
                test_nudge_sent = True
                fnames = ", ".join(os.path.basename(f) for f in untested)
                dirs = set(os.path.dirname(f) for f in untested)
                test_cmd = f"cd {next(iter(dirs))} && python {os.path.basename(next(iter(untested)))}" if len(dirs) == 1 else f"python {os.path.basename(next(iter(untested)))}"
                nudge = (
                    f"You created .py file(s): {fnames}. "
                    f"You MUST test them before finishing! "
                    f"Run: shell(command='{test_cmd}'). "
                    "If it fails, read the error, fix the code, and test again."
                )
                current_messages.append({"role": "user", "content": nudge})
                continue

            continue

        if ai_response_text:
            untested = created_py_files - tested_py_files
            if untested and not test_nudge_sent:
                test_nudge_sent = True
                fnames = ", ".join(os.path.basename(f) for f in untested)
                dirs = set(os.path.dirname(f) for f in untested)
                test_cmd = f"cd {next(iter(dirs))} && python {os.path.basename(next(iter(untested)))}" if len(dirs) == 1 else f"python {os.path.basename(next(iter(untested)))}"
                nudge = (
                    f"You created .py file(s): {fnames} but haven't tested them yet. "
                    f"Run: shell(command='{test_cmd}') to verify they work. "
                    "Only provide the final answer after tests pass."
                )
                current_messages.append({"role": "user", "content": nudge})
                continue

            yield _sse("user_text", {"content": ai_response_text})
            session.add_assistant_message(ai_response_text)
            yield _sse("done")
            return

        # Build a context-aware nudge based on what happened last
        last_action = "unknown"
        for m in reversed(current_messages):
            if m["role"] == "tool" and m.get("content"):
                txt = m["content"][:120]
                if "File written:" in txt:
                    last_action = f"writing file ({txt})"
                elif "[Exit:" in txt:
                    last_action = f"running command ({txt})"
                elif "Error:" in txt:
                    last_action = f"error: {txt}"
                else:
                    last_action = txt
                break
            if m["role"] == "assistant" and m.get("tool_calls"):
                tcs = m["tool_calls"]
                if tcs:
                    last_action = f"calling tool '{tcs[0]['function']['name']}'"
                break

        session.empty_retries = getattr(session, 'empty_retries', 0) + 1
        attempt = session.empty_retries
        context_size = ai_client.total_chars(current_messages)
        MAX_EMPTY_ATTEMPTS = 5

        logger.warning(f"[AI] Empty response attempt {attempt}/{MAX_EMPTY_ATTEMPTS}, last: {last_action}, ctx: {context_size} chars")

        if attempt > 1:
            # Даём провайдеру передышку между попытками
            _time.sleep(min(3 * attempt, 20))

        if attempt <= MAX_EMPTY_ATTEMPTS:
            # Сводка строится ДО сжатия истории — в ней остаётся вся работа
            # (задача + вызванные инструменты + результаты), даже после урезания.
            state_summary = _build_state_summary(current_messages)
            if attempt == 1:
                kept = _sanitize_messages(current_messages[:1] + current_messages[-6:])
                # Задача пользователя (первое user-сообщение) всегда нужна модели —
                # иначе она теряет контекст и отвечает приветствием.
                first_user = None
                for m in current_messages[1:]:
                    if m["role"] == "user":
                        first_user = m
                        break
                if first_user is not None and not any(m is first_user for m in kept):
                    kept = _sanitize_messages([kept[0], first_user] + kept[1:])
                current_messages[:] = kept
                current_messages.append({
                    "role": "user",
                    "content": f"Продолжай выполнение задачи. Состояние задачи:\n{state_summary}\nПоследний шаг: {last_action}\nОтвечай или вызови следующий инструмент СРАЗУ — без длинных рассуждений."
                })
            elif attempt == 2:
                tool_indices = [i for i, m in enumerate(current_messages) if m["role"] == "tool"]
                if len(tool_indices) > 4:
                    for i in reversed(tool_indices[:-4]):
                        current_messages.pop(i)
                current_messages.append({
                    "role": "user",
                    "content": f"КРИТИЧНО: продолжай выполнение задачи, не молчи. Состояние задачи:\n{state_summary}\nТы должен либо (a) вызвать инструмент для продолжения, либо (b) дать текстовый ответ. Последний шаг: {last_action}"
                })
            else:
                # Жёсткое сжатие: системный промпт + ОРИГИНАЛЬНАЯ задача пользователя
                # (первое user-сообщение) + сводка состояния. Nudge-сообщения отбрасываем —
                # если оставить их, модель теряет задачу и отвечает приветствием вместо работы.
                first_user = None
                for m in current_messages[1:]:
                    if m["role"] == "user":
                        first_user = m
                        break
                kept = current_messages[:1]
                if first_user is not None:
                    kept.append(first_user)
                current_messages[:] = _sanitize_messages(kept)
                current_messages.append({
                    "role": "user",
                    "content": f"ОТВЕТЬ СЕЙЧАС коротким текстом или ОДНИМ вызовом инструмента. Не думай долго. Состояние задачи:\n{state_summary}\nПоследнее, что ты сделал: {last_action}"
                })
            continue

        yield _sse("error", {"content": f"AI returned empty response {attempt} times. Last step: {last_action}. The free Zen model is overloaded or degraded. Switch mode in the dropdown to 'Google Gemini' or 'DeepSeek API' (with your key) and retry."})
        break

    if iteration >= max_iterations:
        err = f"Maximum iterations reached ({max_iterations}). The model kept calling tools without completing the task."
        yield _sse("error", {"content": err})
    yield _sse("done")


def _sanitize_tool_for_sse(tool: Dict) -> Dict:
    """Убирает пароль из tool-блока перед отправкой в браузер (SSE).
    Пароль не должен светиться в истории чата и в UI."""
    if isinstance(tool, dict) and tool.get("password"):
        safe = dict(tool)
        safe["password"] = "***"
        return safe
    return tool


def _simple_tool_result(tool: Dict, result: Dict) -> str:
    action = tool.get("action", "?")

    if result.get("success"):
        if action == "quantum":
            counts = result.get("counts", {})
            meta = result.get("metadata", {})
            noise = result.get("noise_params", {})
            parts = ["[Quantum Result]"]
            if counts:
                parts.append(f"Counts: {json.dumps(counts, ensure_ascii=False)}")
            if noise:
                parts.append(f"Noise: {json.dumps(noise, ensure_ascii=False, default=str)}")
            if meta:
                parts.append(f"Metadata: {json.dumps(meta, ensure_ascii=False, default=str)}")
            return "\n".join(parts)

        if action == "shell":
            stdout = (result.get("stdout", "") or "").strip()
            returncode = result.get("returncode", 0)
            cwd = result.get("cwd", "")
            parts = [f"[CWD: {cwd or os.getcwd()}]", f"[Exit: {returncode}]"]
            if stdout:
                parts.append(stdout[:20000])
            stderr = result.get("stderr", "")
            if stderr:
                parts.append(f"[stderr]: {stderr[:5000]}")
            return "\n".join(parts)

        stdout = (result.get("stdout", "") or "").strip()
        return stdout[:20000] if stdout else "OK"
    else:
        # Сначала пытаемся извлечь error из JSON в stdout (ошибки quantum_extras)
        error = result.get("error", "") or result.get("stderr", "") or ""
        if not error:
            stdout_raw = result.get("stdout", "")
            if stdout_raw:
                try:
                    parsed = json.loads(stdout_raw)
                    if isinstance(parsed, dict) and parsed.get("error"):
                        error = parsed["error"]
                except (json.JSONDecodeError, TypeError):
                    pass
        if not error:
            error = "unknown error"
        return f"Error: {error[:2000]}"


def _try_self_heal(error_text: str, tool_block: Dict, tool_call_id: str, current_messages: List, ibm_token: str = "", qi_api_token: str = "", qi_email: str = "", qi_password: str = "") -> bool:
    """
    Self-healing: detects ModuleNotFoundError, auto-installs the missing package,
    and injects a retry instruction for the agent.

    Returns True if healing was triggered, False otherwise.
    """
    import re as _re

    # Пытаемся извлечь JSON из stdout, если ошибка пришла в JSON-формате
    json_error = None
    if error_text:
        try:
            parsed = json.loads(error_text)
            if isinstance(parsed, dict) and parsed.get("error"):
                json_error = parsed["error"]
        except (json.JSONDecodeError, TypeError):
            pass

    # Используем JSON-ошибку если есть, иначе исходный текст
    search_text = json_error or error_text

    # Парсим имя пакета из ошибки ModuleNotFoundError
    m = _re.search(r"ModuleNotFoundError.*?No module named ['\"]([^'\"]+)['\"]", search_text, _re.IGNORECASE)
    if not m:
        m = _re.search(r"No module named ['\"]([^'\"]+)['\"]", search_text, _re.IGNORECASE)
    if not m:
        m = _re.search(r"ModuleNotFoundError.*?(['\"][^'\"]+['\"])", search_text, _re.IGNORECASE)

    # НОВОЕ: ищем фразу "не установлен" и извлекаем имя пакета
    if not m:
        m = _re.search(r"(\w[\w\-_.]+?)\s+не установлен", search_text, _re.IGNORECASE)
    if not m:
        # Пробуем другой паттерн: "пакет X не найден" или "X не установлен"
        m = _re.search(r"пакет[а]?\s+(\w[\w\-_.]+?)\s+не", search_text, _re.IGNORECASE)

    if not m:
        return False

    package_name = m.group(1).strip()
    if not package_name:
        return False

    # БЕРЁМ ТОЛЬКО ВЕРХНИЙ ПАКЕТ: quantuminspire.api → quantuminspire
    package_name = package_name.split(".")[0]
    # PyPI имена всегда в нижнем регистре: Qiskit → qiskit
    import_name = package_name
    package_name = package_name.lower()

    logger.info(f"[SELF-HEAL] Detected missing package: {package_name}")

    # Устанавливаем пакет (torch и tensorflow — гигантские, даём больше времени)
    HEAVY_PACKAGES = {"torch", "tensorflow", "jax", "pytorch", "transformers", "datasets"}
    install_timeout = 600 if package_name.lower() in HEAVY_PACKAGES else 120
    from hands import install_python_package
    install_result = install_python_package(package_name=package_name, timeout=install_timeout)

    if install_result.get("success"):
        logger.info(f"[SELF-HEAL] Package {package_name} installed successfully")
        # Верифицируем: проверяем что пакет действительно импортируется (в нижнем регистре)
        import subprocess as _sp_verify
        verify_name = import_name if import_name.islower() else package_name
        # Тяжёлые пакеты (tensorflow/torch) импортируются 15-60 сек — таймаут 10с
        # приводил к TimeoutExpired и обрыву SSE-соединения ("network error")
        verify_timeout = 600 if package_name.lower() in HEAVY_PACKAGES else 60
        verified = False
        try:
            verify = _sp_verify.run(
                [sys.executable, "-c", f"import {verify_name}; print('OK')"],
                capture_output=True, text=True, timeout=verify_timeout,
                encoding="utf-8", errors="replace",
            )
            verified = verify.returncode == 0
        except _sp_verify.TimeoutExpired:
            # Таймаут верификации не значит, что пакет сломан: импорт тяжёлого
            # пакета может занимать больше времени, чем отведено. Продолжаем —
            # повторный вызов инструмента покажет реальное состояние пакета.
            logger.warning(f"[SELF-HEAL] Package {package_name} import check timed out after {verify_timeout}s; proceeding with retry")
            verified = True
        if not verified:
            # Пакет числится установленным, но не импортируется (повреждённая
            # установка, остатки прерванного pip). Переустанавливаем принудительно.
            logger.warning(f"[SELF-HEAL] Package {package_name} present but import failed; forcing reinstall")
            from hands import install_python_package as _install_force
            force_result = _install_force(package_name=package_name, timeout=install_timeout, force=True)
            if force_result.get("success"):
                try:
                    verify = _sp_verify.run(
                        [sys.executable, "-c", f"import {verify_name}; print('OK')"],
                        capture_output=True, text=True, timeout=verify_timeout,
                        encoding="utf-8", errors="replace",
                    )
                    verified = verify.returncode == 0
                except _sp_verify.TimeoutExpired:
                    verified = True
            else:
                logger.warning(f"[SELF-HEAL] Force reinstall of {package_name} failed: {force_result.get('stderr', '')[:200]}")
                return False
        if verified:
            logger.info(f"[SELF-HEAL] Package {package_name} verified: import OK")
        else:
            logger.warning(f"[SELF-HEAL] Package {package_name} installed but import failed")
        # ВАЖНО: НЕ добавляем в контекст сообщения с вымышленными tool_call_id
        # (..._heal / ..._heal_fail) — API требует, чтобы каждый tool_call ассистента
        # имел ответное tool-сообщение с тем же id, иначе приходит ошибка 400:
        # "An assistant message with 'tool_calls' must be followed by tool messages..."
        # Автоматический повторный вызов инструмента делает retry в _process_agent_loop.
        return True
    else:
        err_msg = install_result.get("stderr", "неизвестная ошибка")
        logger.warning(f"[SELF-HEAL] Failed to install {package_name}: {err_msg}")
        # Не добавляем сообщение с вымышленным tool_call_id (..._heal_fail) —
        # это вызывает ошибку 400 у провайдера (нет ответа на tool_call).
        # Обработку ошибки выполняет обычный поток в _process_agent_loop.
        return False


def _sse(event_type: str, data: Optional[Dict] = None) -> str:
    payload = {"type": event_type}
    if data:
        payload.update(data)
    try:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    except Exception as e:
        logger.error(f"[SSE] Failed to serialize: {e}")
        return f"data: {json.dumps({'type': 'error', 'content': 'Serialization error'}, ensure_ascii=False)}\n\n"


if __name__ == "__main__":
    import sys as _sys
    import os as _os
    import __main__ as _mm
    _start_debug = _os.path.expanduser("~/Desktop/agent_startup_log.txt")
    try:
        with open(_start_debug, "w", encoding="utf-8") as _f:
            _f.write("STARTING\n")
            _mm_file = getattr(_mm, '__file__', 'N/A')
            _f.write(f"__main__.__file__ = {_mm_file}\n")
            _f.write(f"server.__file__ = {__file__}\n")
            _routes = sorted([r.rule for r in app.url_map.iter_rules()])
            _f.write(f"routes = {_routes}\n")
            _f.write(f"has /api/debug = {'/api/debug' in _routes}\n")
        _sys.stdout.reconfigure(encoding='utf-8')
    except Exception as _e:
        with open(_start_debug, "a", encoding="utf-8") as _f:
            _f.write(f"reconfigure error: {_e}\n")
    try:
        from config import get_provider_label
        provider_label = get_provider_label()
        _banner = f"""
+{'='*56}+
|  AI Agent - Server started{' ' * 35}|
|  Chat: http://{HOST}:{PORT}{' ' * (36 - len(str(PORT)))}|
|  Provider: {provider_label}{' ' * (39 - len(provider_label))}|
|  Model: {ai_client.model}{' ' * (43 - len(ai_client.model))}|
+{'='*56}+
"""
        _sys.stdout.write(_banner)
        _sys.stdout.flush()
        with open(_start_debug, "a", encoding="utf-8") as _f:
            _f.write("BANNER PRINTED\n")
    except Exception as _e:
        with open(_start_debug, "a", encoding="utf-8") as _f:
            _f.write(f"banner error: {_e}\n")
        import traceback as _tb
        with open(_start_debug, "a", encoding="utf-8") as _f:
            _tb.print_exc(file=_f)
    try:
        is_bundled = getattr(_sys, 'frozen', False)
        with open(_start_debug, "a", encoding="utf-8") as _f:
            _f.write(f"frozen={is_bundled}\n")
        _sys.stderr.write(f"[BOOT] Starting {HOST}:{PORT} via app.run()...\n")
        app.run(host=HOST, port=PORT, debug=False, threaded=True, use_reloader=False)
    except Exception as _e:
        with open(_start_debug, "a", encoding="utf-8") as _f:
            _f.write(f"run error: {_e}\n")
        import traceback as _tb
        with open(_start_debug, "a", encoding="utf-8") as _f:
            _tb.print_exc(file=_f)

