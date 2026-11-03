$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$TaskName = 'EnglishLearningServer'
Set-Location $Root

$trackedChanges = git status --porcelain --untracked-files=no
if ($trackedChanges) { throw "检测到本地代码修改，请先处理：`n$trackedChanges" }

$BackupDir = Join-Path $Root 'backups'
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$Db = (& '.\venv\Scripts\python.exe' -c 'import server; print(server.DB)').Trim()

if (Test-Path $Db) {
    $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $Backup = Join-Path $BackupDir "app-$Stamp.db"
    & '.\venv\Scripts\python.exe' -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" $Db $Backup
}

$TaskExists = [bool](Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)
if ($TaskExists) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

$Old = (git rev-parse HEAD).Trim()
try {
    git fetch origin main
    if ($LASTEXITCODE -ne 0) { throw 'git fetch 失败' }
    git merge --ff-only origin/main
    if ($LASTEXITCODE -ne 0) { throw 'git merge 失败' }
    & '.\venv\Scripts\python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
}
catch {
    git reset --hard $Old
    & '.\venv\Scripts\python.exe' -m pip install -r requirements.txt
    throw
}
finally {
    if ($TaskExists) {
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 4
    }
}

if ($TaskExists) {
    Invoke-RestMethod 'http://127.0.0.1:5000/api/health'
} else {
    Write-Warning '代码与依赖已更新；当前未注册开机任务，请手动运行 start.ps1。'
}
