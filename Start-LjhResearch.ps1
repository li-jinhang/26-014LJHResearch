param([string]$Project = (Join-Path $PSScriptRoot '.local/demo-project'))
$ErrorActionPreference = 'Stop'
$toolPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $toolPython)) { throw 'Run ljh-research-setup to prepare the application environment first.' }
if (-not (Test-Path -LiteralPath (Join-Path $Project 'ljh research docs/.workspace.json'))) { throw 'Initialize the selected project with ljh-research-setup first.' }
& $toolPython -m ljh_research_panel --project-root $Project --open
