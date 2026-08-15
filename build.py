"""
Сборка AI Agent в единый .exe для Windows.
Запуск: python build.py

Результат: dist/AI Agent.exe
"""
import os
import sys
import shutil
import subprocess


def build():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    dist_name = "AI Agent"
    icon_path = os.path.join(project_dir, "static", "icon.ico")
    if not os.path.exists(icon_path):
        icon_path = None

    # Удаляем старую сборку
    for d in ["build", "dist"]:
        p = os.path.join(project_dir, d)
        if os.path.exists(p):
            shutil.rmtree(p, ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", dist_name,
        "--onefile",
        "--noconsole",
        "--add-data", f"templates{os.pathsep}templates",
        "--add-data", f"static{os.pathsep}static",
        "--add-data", f"logs{os.pathsep}logs",
        "--add-data", f"quantum_kit{os.pathsep}quantum_kit",
        "--hidden-import", "flask",
        "--hidden-import", "requests",
        "--hidden-import", "webview",
        "--hidden-import", "tools",
        "--hidden-import", "ai_client",
        "--hidden-import", "hands",
        "--hidden-import", "system_prompt",
        "--hidden-import", "config",
        "--hidden-import", "quantum_kit.noise_model",
        "--hidden-import", "quantum_kit.quantum_tools",
    ]
    if icon_path:
        cmd.extend(["--icon", icon_path])
    
    # Исключаем лишнее
    cmd.append("--exclude-module")
    cmd.append("tkinter")
    cmd.append("--exclude-module")
    cmd.append("unittest")
    
    entry_point = os.path.join(project_dir, "desktop_app.py")
    cmd.append(entry_point)

    print("=" * 60)
    print("Сборка AI Agent...")
    print("=" * 60)
    print(f"Входная точка: {entry_point}")
    print(f"Выходной файл: dist/{dist_name}.exe")
    print(f"Icon: {icon_path or 'нет'}")
    print()

    result = subprocess.run(cmd, cwd=project_dir)
    if result.returncode == 0:
        print("\nГотово! Файл: dist/AI Agent.exe")
        print("Просто скопируй .exe куда хочешь и запусти.")
    else:
        print(f"\nОшибка сборки (код {result.returncode})")

    return result.returncode


if __name__ == "__main__":
    sys.exit(build())
