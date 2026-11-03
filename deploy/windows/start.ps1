$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Root

if (-not (Test-Path '.env')) { throw '缺少 .env，请先运行 install.ps1 并填写配置。' }
if (-not (Test-Path 'venv\Scripts\waitress-serve.exe')) { throw '缺少 Waitress，请先运行 install.ps1。' }

New-Item -ItemType Directory -Force -Path 'data\logs' | Out-Null
$Log = Join-Path $Root 'data\logs\server.log'

& '.\venv\Scripts\waitress-serve.exe' --host=127.0.0.1 --port=5000 --threads=8 server:app *>> $Log
