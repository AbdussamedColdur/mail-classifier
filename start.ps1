# MailKarar: kurulum yoksa yapar, ön yüzü derler ve http://127.0.0.1:8000 adresinde başlatır.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$py = Join-Path $root 'backend\.venv\Scripts\python.exe'

if (-not (Test-Path $py)) {
    Write-Host 'Python ortamı kuruluyor...'
    python -m venv (Join-Path $root 'backend\.venv')
    & $py -m pip install -q --disable-pip-version-check -r (Join-Path $root 'backend\requirements.txt')
}

$front = Join-Path $root 'frontend'
if (-not (Test-Path (Join-Path $front 'node_modules'))) {
    Write-Host 'Ön yüz paketleri kuruluyor...'
    npm --prefix $front install --no-audit --no-fund
}
Write-Host 'Ön yüz derleniyor...'
npm --prefix $front run build

Write-Host 'MailKarar http://127.0.0.1:8000 adresinde başlıyor (durdurmak için Ctrl+C).'
Start-Process 'http://127.0.0.1:8000'
Set-Location (Join-Path $root 'backend')
& $py -W ignore::FutureWarning -m uvicorn app.main:app --host 127.0.0.1 --port 8000
