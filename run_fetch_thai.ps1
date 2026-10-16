# Called by the "Market Dashboard - Thai data" scheduled task. Output goes to logs\fetch_thai.log
$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot
New-Item -ItemType Directory -Force logs | Out-Null
$env:PYTHONIOENCODING = 'utf-8'
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" fetch_thai.py 2>&1 | Out-File -Append -Encoding utf8 logs\fetch_thai.log
