# MailKarar: kurulum yoksa yapar, ön yüzü derler ve http://127.0.0.1:8000 adresinde başlatır.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venv = Join-Path $root 'backend\.venv'
$py = Join-Path $venv 'Scripts\python.exe'

# Ortam başka bir bilgisayardan kopyalanmış ya da Python kaldırılmış olabilir; dosyanın varlığı
# yetmez, yorumlayıcı çalışmalı ve paketler yüklenebilmeli.
function Test-Venv {
    if (-not (Test-Path $py)) { return $false }
    try { & $py -c 'import fastapi, uvicorn, googleapiclient, keyring' } catch { return $false }
    return $LASTEXITCODE -eq 0
}

if (-not (Test-Venv)) {
    Write-Host 'Python ortamı kuruluyor...'
    # Windows'taki "python" çoğu zaman Microsoft Store yönlendiricisidir; py başlatıcısı varsa onu kullan.
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv --clear $venv }
    else { & python -m venv --clear $venv }
    if ($LASTEXITCODE -ne 0) { throw 'Python ortamı oluşturulamadı. Python 3.10+ kurulu mu?' }
    & $py -m pip install -q --disable-pip-version-check -r (Join-Path $root 'backend\requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Python paketleri kurulamadı.' }
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
