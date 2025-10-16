import os
from pathlib import Path
from datetime import datetime

# === Настройки ===
IGNORE_DIRS = {'.git', '__pycache__', '.venv', 'venv', '.idea', '.vscode', 'node_modules'}
IGNORE_FILES_BASE = {'.DS_Store', 'Thumbs.db', '.gitignore'}


def _build_subtree(directory: Path, prefix: str = "") -> str:
    try:
        entries = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    except (PermissionError, OSError):
        return ""

    dirs = [e for e in entries if e.is_dir() and e.name not in IGNORE_DIRS]
    files = [e for e in entries if e.is_file() and e.name not in IGNORE_FILES]
    all_entries = dirs + files

    result = ""
    for i, entry in enumerate(all_entries):
        is_last = i == len(all_entries) - 1
        connector = "└── " if is_last else "├── "
        result += prefix + connector + (entry.name + "/" if entry.is_dir() else entry.name) + "\n"
        if entry.is_dir():
            ext_prefix = prefix + ("    " if is_last else "│   ")
            result += _build_subtree(entry, ext_prefix)
    return result


def get_all_files(root: Path) -> list[Path]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for f in filenames:
            if f not in IGNORE_FILES:
                files.append(Path(dirpath) / f)
    return sorted(files)


def main():
    root = Path(__file__).parent.resolve()

    # Генерируем имя файла с датой и временем
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file = root / f"project_dump_{timestamp}.txt"

    # Динамически обновляем игнор-лист, чтобы исключить сам выходной файл (на всякий случай)
    global IGNORE_FILES
    IGNORE_FILES = IGNORE_FILES_BASE | {output_file.name}

    print(f"Сканирование проекта: {root.name}/")
    print(f"Выходной файл: {output_file.name}")

    # 1. Строим дерево
    tree = f"{root.name}/\n"
    try:
        entries = sorted(root.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        dirs = [e for e in entries if e.is_dir() and e.name not in IGNORE_DIRS]
        files = [e for e in entries if e.is_file() and e.name not in IGNORE_FILES]
        all_entries = dirs + files

        for i, entry in enumerate(all_entries):
            is_last = i == len(all_entries) - 1
            connector = "└── " if is_last else "├── "
            tree += connector + (entry.name + "/" if entry.is_dir() else entry.name) + "\n"
            if entry.is_dir():
                prefix = "    " if is_last else "│   "
                tree += _build_subtree(entry, prefix)
    except Exception as e:
        print(f"⚠️ Ошибка при построении дерева: {e}")
        tree = f"{root.name}/\n(ошибка генерации структуры)\n"

    # 2. Собираем все файлы
    all_files = get_all_files(root)

    # 3. Пишем в файл
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(tree)
        f.write("\n" + "=" * 60 + "\n\n")

        for file_path in all_files:
            rel_path = file_path.relative_to(root)
            header = f"{root.name}/{rel_path}"
            f.write(f"{header}:\n")
            f.write("-" * len(header) + "\n")
            try:
                with open(file_path, "r", encoding="utf-8") as src:
                    content = src.read()
            except Exception as e:
                content = f"<<< ОШИБКА ЧТЕНИЯ: {e} >>>"
            f.write(content)
            f.write("\n\n" + "=" * 60 + "\n\n")

    print(f"✅ Готово! Результат сохранён в: {output_file.name}")


if __name__ == "__main__":
    main()