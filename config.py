"""
Конфигурация агента.
Настройки подключения к DeepSeek / Qwen, пути к Automator и т.д.
"""
import os
import logging
from pathlib import Path

# ------ Настройки AI (мозг) ------

# Режим по умолчанию: "deepseek_api", "deepseek_free", "qwen"
AI_MODE = os.getenv("AI_MODE", "zen")  # По умолчанию — DeepSeek V4 Flash Free (Zen, без ключа)

# --- DeepSeek (официальный API — нужен ключ, но даёт 5$ бесплатно) ---
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# --- OpenRouter (бесплатный доступ к DeepSeek и другим моделям) ---
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")

# --- Qwen (требуется API-ключ от Alibaba Cloud) ---
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")

# --- OpenCode Zen (требуется API-ключ с opencode.ai/zen) ---
ZEN_BASE_URL = os.getenv("ZEN_BASE_URL", "https://opencode.ai/zen/v1")
ZEN_API_KEY = os.getenv("ZEN_API_KEY", "")  # Нужен ключ с opencode.ai
ZEN_MODEL = os.getenv("ZEN_MODEL", "deepseek-v4-flash-free")

# --- Google Gemini (бесплатно, ключ с https://aistudio.google.com/apikey) ---
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/v1")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# ------ Настройки проекта ------

# Путь к Project Automator
AUTOMATOR_PATH = Path(os.getenv(
    "AUTOMATOR_PATH",
    r"C:\Users\lesya\OneDrive\Рабочий стол\automator_project"
))

# Папка для временных инструкций Automator
INSTRUCTIONS_DIR = Path(os.getenv(
    "INSTRUCTIONS_DIR",
    str(AUTOMATOR_PATH / "test_instr")
))

# ------ Настройки сервера ------

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "my-agent-secret-key-change-me")

# ------ Логирование ------

LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
LOG_FILE = os.getenv("LOG_FILE", str(Path(__file__).parent / "logs" / "agent.log"))

# ------ Маппинг моделей ------

AI_CONFIG = {
    "gemini": {
        "base_url": GEMINI_BASE_URL,
        "api_key": GEMINI_API_KEY,
        "model": GEMINI_MODEL,
        "label": "Google Gemini (бесплатно)",
        "provider": "gemini",
    },
    "zen": {
        "base_url": ZEN_BASE_URL,
        "api_key": ZEN_API_KEY,
        "model": ZEN_MODEL,
        "label": "DeepSeek V4 Flash Free (Zen)",
        "provider": "zen",
    },
    "deepseek_api": {
        "base_url": DEEPSEEK_BASE_URL,
        "api_key": DEEPSEEK_API_KEY,
        "model": DEEPSEEK_MODEL,
        "label": "DeepSeek API (ключ)",
        "provider": "deepseek",
    },
    "deepseek_free": {
        "base_url": OPENROUTER_BASE_URL,
        "api_key": OPENROUTER_API_KEY,
        "model": "deepseek/deepseek-chat",
        "label": "DeepSeek Free (OpenRouter)",
        "provider": "openrouter",
    },
    "qwen": {
        "base_url": QWEN_BASE_URL,
        "api_key": QWEN_API_KEY,
        "model": QWEN_MODEL,
        "label": "Qwen (ключ)",
        "provider": "qwen",
    },
}

def get_active_config():
    """Вернуть активную конфигурацию AI."""
    if AI_MODE not in AI_CONFIG:
        logger.warning(f"[CONFIG] Unknown AI_MODE={AI_MODE!r}, falling back to zen")
    return AI_CONFIG.get(AI_MODE, AI_CONFIG["zen"])

def get_provider_label(mode: str = None) -> str:
    """Вернуть название провайдера для отображения."""
    mode = mode or AI_MODE
    cfg = AI_CONFIG.get(mode, {})
    return cfg.get("label", mode)


# Создаём нужные папки
INSTRUCTIONS_DIR.mkdir(parents=True, exist_ok=True)
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

# Настройка логгера
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.DEBUG),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("agent")
