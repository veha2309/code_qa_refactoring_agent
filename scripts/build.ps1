param([string]$OutputDirectory = 'dist')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$taskWorkspace = (Get-Location).Path
$taskOutput = [System.IO.Path]::GetFullPath((Join-Path $taskWorkspace $OutputDirectory))
if (-not $taskOutput.StartsWith($taskWorkspace + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Choose an output directory inside the workspace.' }
$taskBundle = Join-Path $taskOutput 'ChangeLens'
$taskPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath 'resources\refactoring\node_modules\typescript\lib\typescript.js')) {
    throw 'Run scripts/setup.ps1 to prepare the TypeScript refactoring assets before building.'
}
& $taskPython -m scripts.notices
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
& $taskPython -m scripts.build_runner --noconfirm --clean --distpath $taskOutput ChangeLens.spec
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed' }
Get-ChildItem '.venv\Lib\site-packages\PySide6' -File | Where-Object { $_.Name -match '^(VCRUNTIME140|MSVCP140).*\.dll$' } | Copy-Item -Destination (Join-Path $taskBundle '_internal') -Force
Copy-Item -LiteralPath 'README.md','USER_GUIDE.md','THIRD_PARTY_NOTICES.md','LICENSE' -Destination $taskBundle -Force
New-Item -ItemType Directory -Path (Join-Path $taskBundle 'evaluation') -Force | Out-Null
Copy-Item -LiteralPath 'evaluation\RESULTS.md','evaluation\CORE_REFINEMENTS.md','evaluation\AUTOMATION_AND_LOCAL_AI.md','evaluation\LENS_DESIGN.md','evaluation\MULTILANGUAGE.md','evaluation\FORMATTING_AND_GLASS.md','evaluation\WORKFLOW_REFINEMENTS.md','evaluation\UI_USABILITY.md','evaluation\ARCHITECTURE_LLD.md','evaluation\DESIGN_EDITOR.md','evaluation\FOCUS_AND_CHANGE_CONTROL.md','evaluation\NAVIGATION_REPAIR.md' -Destination (Join-Path $taskBundle 'evaluation') -Force
Copy-Item -LiteralPath 'evaluation\FEATURE_FLOWS.md','evaluation\PROPOSAL_CONTRACT.md','evaluation\DESIGN_INTERACTIONS.md','evaluation\REVIEW_QUALITY.md' -Destination (Join-Path $taskBundle 'evaluation') -Force
Write-Host "Ready: $taskBundle\ChangeLens.exe. Distribute the whole ChangeLens directory."

