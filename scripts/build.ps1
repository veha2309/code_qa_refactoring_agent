param([string]$OutputDirectory = 'dist')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$taskWorkspace = (Get-Location).Path
$taskOutput = [System.IO.Path]::GetFullPath((Join-Path $taskWorkspace $OutputDirectory))
if (-not $taskOutput.StartsWith($taskWorkspace + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Choose an output directory inside the workspace.' }
$taskBundle = Join-Path $taskOutput 'ChangeLens'
$taskPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
& $taskPython -m scripts.notices
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
& $taskPython -m scripts.build_runner --noconfirm --clean --onedir --windowed --name ChangeLens --distpath $taskOutput --add-data 'resources;resources' --add-data 'THIRD_PARTY_LICENSES;THIRD_PARTY_LICENSES' --add-data 'THIRD_PARTY_NOTICES.md;.' --hidden-import pytest --hidden-import importlib.resources --copy-metadata rope --copy-metadata jedi --copy-metadata black --collect-all pytokens --collect-submodules _pytest --collect-submodules pygments.lexers --collect-all tree_sitter --collect-all tree_sitter_javascript --collect-all tree_sitter_typescript --collect-all tree_sitter_java --collect-all tree_sitter_c_sharp --collect-all tree_sitter_go --collect-all tree_sitter_rust --collect-all tree_sitter_dart --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtWebEngineQuick launcher.py
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed' }
Get-ChildItem '.venv\Lib\site-packages\PySide6' -File | Where-Object { $_.Name -match '^(VCRUNTIME140|MSVCP140).*\.dll$' } | Copy-Item -Destination (Join-Path $taskBundle '_internal') -Force
Copy-Item -LiteralPath 'README.md','USER_GUIDE.md','THIRD_PARTY_NOTICES.md','LICENSE' -Destination $taskBundle -Force
New-Item -ItemType Directory -Path (Join-Path $taskBundle 'evaluation') -Force | Out-Null
Copy-Item -LiteralPath 'evaluation\RESULTS.md','evaluation\CORE_REFINEMENTS.md','evaluation\AUTOMATION_AND_LOCAL_AI.md','evaluation\LENS_DESIGN.md','evaluation\MULTILANGUAGE.md','evaluation\FORMATTING_AND_GLASS.md','evaluation\WORKFLOW_REFINEMENTS.md' -Destination (Join-Path $taskBundle 'evaluation') -Force
Write-Host "Ready: $taskBundle\ChangeLens.exe. Distribute the whole ChangeLens directory."

