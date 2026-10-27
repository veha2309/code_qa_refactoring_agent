$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
if (-not (Test-Path -LiteralPath 'resources\formatting\manifest.json') -or -not (Test-Path -LiteralPath 'resources\formatting\node.exe')) {
    & .\.venv\Scripts\python.exe -m scripts.prepare_formatter
    if ($LASTEXITCODE -ne 0) { throw 'Formatter asset preparation failed' }
}
& .\.venv\Scripts\python.exe -m scripts.prepare
if ($LASTEXITCODE -ne 0) { throw 'Demo manifest creation failed' }
& .\.venv\Scripts\python.exe -m scripts.train
if ($LASTEXITCODE -ne 0) { throw 'Model training failed' }
Write-Host 'Ready. Double-click Start Change Lens.cmd.'
