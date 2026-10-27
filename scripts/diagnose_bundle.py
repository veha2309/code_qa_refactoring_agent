"""Inspect direct Windows import/export compatibility without loading DLLs."""
from pathlib import Path
import pefile


def main():
    root = Path("dist/ChangeLens/_internal")
    roots = [root, root / "PySide6", root / "shiboken6", Path("C:/Windows/System32")]
    cache = {}

    def binary(path):
        key = str(path).lower()
        if key not in cache:
            value = pefile.PE(str(path), fast_load=True, max_symbol_exports=100000)
            value.parse_data_directories(directories=[1, 0])
            cache[key] = value
        return cache[key]

    queue = [root / "PySide6/QtCore.pyd", root / "PySide6/Qt6Core.dll",
             root / "PySide6/pyside6.abi3.dll", root / "shiboken6/shiboken6.abi3.dll"]
    seen = set()
    missing = []
    while queue:
        path = queue.pop(0)
        if path in seen or not path.exists():
            continue
        seen.add(path)
        for entry in getattr(binary(path), "DIRECTORY_ENTRY_IMPORT", []):
            name = entry.dll.decode()
            found = next((folder / name for folder in roots if (folder / name).exists()), None)
            if not found:
                if not name.lower().startswith(("api-ms-", "ext-ms-")):
                    missing.append((path.name, name, "file not found"))
                continue
            exported = {item.name for item in getattr(getattr(binary(found), "DIRECTORY_ENTRY_EXPORT", None), "symbols", [])}
            for item in entry.imports:
                if item.name and item.name not in exported:
                    missing.append((path.name, str(found), item.name.decode(errors="replace")))
            if found.is_relative_to(root):
                queue.append(found)
    for item in missing:
        print(item)
    print(f"Inspected {len(seen)} files; {len(missing)} missing direct imports")


if __name__ == "__main__":
    main()
