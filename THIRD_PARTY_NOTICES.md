# Third-party software notices

The application includes Qt/PySide6 under its available open-source license terms.
Qt is dynamically linked. Keep the bundled Qt DLLs and license files together.
Source and license information: https://www.qt.io/qt-for-python and https://code.qt.io/pyside/pyside-setup.git

This file inventories installed dependencies; some may not be included by PyInstaller.

Optional local inference uses a separately installed Ollama runtime (https://github.com/ollama/ollama).
The presentation preset uses Qwen2.5-Coder models from https://huggingface.co/Qwen; model licenses are provided by their publisher.
Ollama and model weights are not redistributed in the application bundle. Model downloads are explicit setup actions.

Bundled offline formatting uses Black 26.5.1 (Python package license below), Prettier 3.9.10 (MIT) and Node.js 24.12.0 (MIT and included third-party terms).
Prettier license: resources/formatting/prettier/LICENSE. Node and embedded third-party licenses: resources/formatting/NODE_LICENSE.
Pinned sources and integrity hashes: resources/formatting/manifest.json and scripts/prepare_formatter.py.

- PySide6 6.12.0: 
- PySide6_Addons 6.12.0: 
- PySide6_Essentials 6.12.0: 
- PySide6_Pdf 6.12.0.140: 
- PySide6_WebEngine 6.12.0.140: 
- Pygments 2.21.0: 
- altgraph 0.17.5: https://altgraph.readthedocs.io
- black 26.5.1: 
- click 8.5.0: 
- cloudpickle 3.1.2: https://github.com/cloudpipe/cloudpickle
- colorama 0.4.6: 
- exceptiongroup 1.3.1: 
- iniconfig 2.3.1: 
- jedi 0.20.1: https://github.com/davidhalter/jedi
- joblib 1.6.0: 
- mypy_extensions 1.1.0: 
- numpy 2.2.6: 
- packaging 26.3: 
- parso 0.8.7: https://github.com/davidhalter/parso
- pathspec 1.1.1: 
- pefile 2024.8.26: https://github.com/erocarrera/pefile
- pip 26.2.2: 
- platformdirs 4.12.4: 
- pluggy 1.7.0: 
- pyinstaller 6.22.3: 
- pyinstaller-hooks-contrib 2026.9: https://github.com/pyinstaller/pyinstaller-hooks-contrib
- pytest 9.1.1: 
- pytokens 0.4.1: 
- pytoolconfig 1.3.1: 
- pywin32-ctypes 0.2.3: https://github.com/enthought/pywin32-ctypes
- rope 1.15.0: 
- scikit-learn 1.7.2: 
- scipy 1.15.3: 
- setuptools 57.4.0: https://github.com/pypa/setuptools
- shiboken6 6.12.0: 
- threadpoolctl 3.7.0: 
- tomli 2.5.0: 
- tree-sitter 0.25.2: 
- tree-sitter-c-sharp 0.23.5: 
- tree-sitter-dart 0.1.0: 
- tree-sitter-go 0.25.0: 
- tree-sitter-java 0.23.5: 
- tree-sitter-javascript 0.25.0: 
- tree-sitter-rust 0.24.2: 
- tree-sitter-typescript 0.23.2: 
- typing_extensions 4.16.0: 