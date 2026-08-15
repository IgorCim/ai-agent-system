"""
Десктоп-приложение AI Agent.
Запускает Flask-сервер в фоне и открывает чат в нативном окне (WebView2).
"""
import os
import sys
import time
import threading
import webbrowser
import urllib.request
import urllib.error


def _get_asset_path(relative_path: str) -> str:
    """Вернуть путь к файлу: для PyInstaller ищет в _MEIPASS, для dev — рядом с .py."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


def start_flask():
    """Запустить Flask-сервер в фоновом потоке."""
    # Чтобы Flask нашёл templates/static при любом запуске
    os.chdir(_get_asset_path("."))
    from config import HOST, PORT, DEBUG
    from server import app
    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True, use_reloader=False)


def wait_for_server(url: str, timeout: int = 15) -> bool:
    """Ждать, пока сервер не ответит."""
    for _ in range(timeout * 2):
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.5)
    return False


def start_desktop_app():
    """Запустить Flask + WebView (или браузер как fallback)."""
    from config import HOST, PORT
    url = f"http://{HOST}:{PORT}"

    # 1. Запускаем сервер
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    if not wait_for_server(url):
        print("Ошибка: сервер не запустился.")
        return

    # 2. Пробуем PyWebView (нативное окно Chromium)
    try:
        import webview
        window = webview.create_window(
            "AI Agent",
            url,
            width=1200,
            height=800,
            resizable=True,
            min_size=(800, 500),
            text_select=True,
        )
        webview.start()
    except Exception as e:
        print(f"PyWebView: {e}. Открываю в браузере...")
        webbrowser.open(url)
        print(f"Чат: {url}. Нажми Ctrl+C для выхода.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nВыход...")


def main():
    print("Запуск AI Agent...")
    mode = os.environ.get("AI_MODE", "zen")
    print(f"Режим: {mode}")
    start_desktop_app()


if __name__ == "__main__":
    main()
