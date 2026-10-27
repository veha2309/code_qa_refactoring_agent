"""Collect distribution licenses for the actual packaged environment."""
from importlib import metadata
from pathlib import Path
import shutil

if __name__ == "__main__":
    output = Path("THIRD_PARTY_LICENSES")
    output.mkdir(exist_ok=True)
    lines = ["# Third-party software notices", "", "The application includes Qt/PySide6 under its available open-source license terms.",
             "Qt is dynamically linked. Keep the bundled Qt DLLs and license files together.",
             "Source and license information: https://www.qt.io/qt-for-python and https://code.qt.io/pyside/pyside-setup.git", "",
             "This file inventories installed dependencies; some may not be included by PyInstaller.", "",
             "Optional local inference uses a separately installed Ollama runtime (https://github.com/ollama/ollama).",
             "The presentation preset uses Qwen2.5-Coder models from https://huggingface.co/Qwen; model licenses are provided by their publisher.",
             "Ollama and model weights are not redistributed in the application bundle. Model downloads are explicit setup actions.", ""]
    lines += ['Bundled offline formatting uses Black 26.5.1 (Python package license below), Prettier 3.9.10 (MIT) and Node.js 24.12.0 (MIT and included third-party terms).',
              'Prettier license: resources/formatting/prettier/LICENSE. Node and embedded third-party licenses: resources/formatting/NODE_LICENSE.',
              'Pinned sources and integrity hashes: resources/formatting/manifest.json and scripts/prepare_formatter.py.', '']
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata.get("Name", "")):
        name = dist.metadata.get("Name", "unknown")
        lines.append(f"- {name} {dist.version}: {dist.metadata.get('Home-page', '')}")
        for item in dist.files or []:
            if any(term in item.name.lower() for term in ("license", "copying", "notice")):
                source = Path(dist.locate_file(item))
                if source.is_file():
                    target = output / name / str(item).replace("../", "").replace("..\\", "")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    for name in ("requests", "flask", "click"):
        root = Path("evaluation/repos") / name
        for source in root.glob("LICENSE*"):
            target = output / ("evaluation-" + name) / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    Path("THIRD_PARTY_NOTICES.md").write_text("\n".join(lines), encoding="utf-8")

