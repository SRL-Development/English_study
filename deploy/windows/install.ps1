$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Root

$Launcher = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { throw '未找到 Python，请先安装 Python 3.11 或 3.12。' }
$LauncherArgs = if ($Launcher -eq 'py') { @('-3.12') } else { @() }

if (-not (Test-Path 'venv\Scripts\python.exe')) {
    & $Launcher @LauncherArgs -m venv venv
}

& '.\venv\Scripts\python.exe' -m pip install --upgrade pip
& '.\venv\Scripts\python.exe' -m pip install -r requirements.txt

New-Item -ItemType Directory -Force -Path data | Out-Null

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Warning '已创建 .env。请先填写 ADMIN_PASSWORD、MAIL_SECRET 和 SITE_BASE_URL。'
}

Write-Host '安装完成。编辑 .env 后运行：powershell -ExecutionPolicy Bypass -File deploy\windows\start.ps1'
