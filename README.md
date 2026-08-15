# 🤖 AI Agent — Свой чат + руки + Automator

Собственная AI-система с веб-чатом, где:
- **Мозг** — DeepSeek (V3/V4 Flash Free) или Qwen (через API)
- **Руки** — собственный исполнитель команд (shell, файлы)
- **Automator** — Project Automator для генерации проектов
- **Чат** — свой веб-интерфейс (как opencode)

## Архитектура

```
Пользователь → Веб-чат (Flask) → AI (DeepSeek/Qwen) → Руки (executor)
                                                           ↓
                                              shell | файлы | Automator
                                                           ↓
                                              Результат → AI → Ответ пользователю
```

## Быстрый запуск

### 1. Установка зависимостей

```bash
cd C:\Users\lesya\my_agent
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Для **Google Gemini** (рекомендую) — **бесплатно, нужен ключ**:
```bash
set AI_MODE=gemini
set GEMINI_API_KEY=...ваш_ключ_с_aistudio.google.com...
```
👉 Получить ключ: https://aistudio.google.com/apikey (без карты, 1500 запр./день)

Для **OpenCode Zen** (DeepSeek V4 Flash Free) — нужен ключ с opencode.ai:
```bash
set AI_MODE=zen
set ZEN_API_KEY=...ваш_ключ...
```

Для **DeepSeek** (бесплатно, нужен ключ с platform.deepseek.com):
```bash
set AI_MODE=deepseek
set DEEPSEEK_API_KEY=sk-...ваш_ключ...
```

Для **Qwen** (нужен ключ с dashscope.aliyuncs.com):
```bash
set AI_MODE=qwen
set QWEN_API_KEY=sk-...ваш_ключ...
```

Можно также указать ключ прямо в интерфейсе чата — в поле "API Ключ".

### 3. Запуск сервера

```bash
python server.py
```

### 4. Открыть чат

➡️ **http://127.0.0.1:5000**

## Настройка Project Automator

Automator уже должен быть установлен. Если нет:
```bash
cd C:\Users\lesya\OneDrive\Рабочий стол\automator_project
pip install -e .
```

Путь к Automator можно указать через переменную:
```bash
set AUTOMATOR_PATH=C:\Users\lesya\OneDrive\Рабочий стол\automator_project
```

## Как это работает

1. Ты пишешь задачу в чат (например: "создай проект калькулятора на Python")
2. Система добавляет системный промт (описание возможностей)
3. Запрос уходит в AI (DeepSeek или Qwen)
4. AI анализирует задачу и выдаёт команды в формате:
   ```
   [TOOL]
   {"action": "shell", "command": "mkdir project"}
   [/TOOL]
   ```
5. «Руки» выполняют команду, результат отправляется AI
6. AI может выполнить несколько итераций (создать файлы, запустить Automator и т.д.)
7. Итоговый ответ показывается тебе

## Формат команд AI

### Shell — выполнить команду
```json
[TOOL]
{"action": "shell", "command": "python --version"}
[/TOOL]
```

### File Write — создать файл
```json
[TOOL]
{"action": "file_write", "path": "C:/test/hello.py", "content": "print('Hello')"}
[/TOOL]
```

### File Read — прочитать файл
```json
[TOOL]
{"action": "file_read", "path": "C:/test/hello.py"}
[/TOOL]
```

### Automator — запустить Project Automator
```json
[TOOL]
{"action": "automator", "instruction_path": "C:/test/instruction.txt"}
[/TOOL]
```

## Возможности

- ✅ Веб-чат с историей сообщений
- ✅ Потоковый вывод (SSE) — ответ приходит по частям
- ✅ Кнопка «Стоп» для прерывания
- ✅ Редактирование своих сообщений
- ✅ Переключение между DeepSeek и Qwen
- ✅ Выполнение shell-команд (PowerShell, cmd)
- ✅ Чтение/запись файлов
- ✅ Интеграция с Project Automator
- ✅ Логирование всех действий (agent.log)
- ✅ Системный промт на русском

## Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|-------------|
| `AI_MODE` | gemini / zen / deepseek / qwen | gemini |
| `GEMINI_API_KEY` | API-ключ Google Gemini (https://aistudio.google.com/apikey) | — |
| `GEMINI_BASE_URL` | URL Gemini API | https://generativelanguage.googleapis.com/v1beta/openai/v1 |
| `GEMINI_MODEL` | Модель Gemini | gemini-2.0-flash |
| `ZEN_API_KEY` | API-ключ OpenCode Zen | — |
| `ZEN_BASE_URL` | URL OpenCode Zen API | https://opencode.ai/zen/v1 |
| `ZEN_MODEL` | Модель Zen | deepseek-v4-flash-free |
| `DEEPSEEK_API_KEY` | Ключ DeepSeek | — |
| `DEEPSEEK_BASE_URL` | URL DeepSeek API | https://api.deepseek.com |
| `DEEPSEEK_MODEL` | Модель DeepSeek | deepseek-chat |
| `QWEN_API_KEY` | Ключ Qwen | — |
| `QWEN_BASE_URL` | URL Qwen API | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| `QWEN_MODEL` | Модель Qwen | qwen-plus |
| `AUTOMATOR_PATH` | Путь к Automator | (путь на десктопе) |
| `HOST` | Хост сервера | 127.0.0.1 |
| `PORT` | Порт сервера | 5000 |
| `DEBUG` | Режим отладки | true |

## Структура проекта

```
my_agent/
├── server.py           # Flask-сервер с логикой агента
├── ai_client.py        # Клиент для DeepSeek/Qwen API
├── hands.py            # «Руки» — исполнитель команд
├── system_prompt.py    # Системный промт для AI
├── config.py           # Конфигурация
├── requirements.txt    # Зависимости
├── README.md           # Этот файл
├── templates/
│   └── index.html      # Веб-чат
└── static/
    ├── style.css       # Стили
    └── script.js       # JavaScript (SSE, UI)
```

## Лицензия

MIT
