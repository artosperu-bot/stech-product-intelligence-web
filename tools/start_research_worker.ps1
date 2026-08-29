param(
    [string]$Server = "https://stech-product-intelligence-web.onrender.com",
    [string]$Token = $env:STECH_RESEARCH_WORKER_TOKEN
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ([string]::IsNullOrWhiteSpace($Token)) {
    Write-Host "Falta el token del worker." -ForegroundColor Yellow
    Write-Host 'Copia solo el valor de STECH_RESEARCH_WORKER_TOKEN desde Render.'
    exit 2
}

$Token = $Token.Trim()
$TokenIsPrintableAscii = $Token -cmatch '^[\x21-\x7E]+$'
if (-not $TokenIsPrintableAscii) {
    Write-Host "Token del worker inválido: contiene espacios o caracteres no ASCII." -ForegroundColor Red
    Write-Host "Longitud recibida: $($Token.Length)"
    Write-Host "Copia únicamente el valor exacto de STECH_RESEARCH_WORKER_TOKEN desde Render; no copies etiquetas ni texto de la página."
    exit 3
}

Write-Host "============================================================"
Write-Host " STECH V7 RESEARCH WORKER"
Write-Host "============================================================"
Write-Host "Render : $Server"
Write-Host "Repo   : $RepoRoot"
Write-Host "Token  : válido (longitud $($Token.Length), valor oculto)"

py -c "import playwright, httpx" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Instalando dependencias mínimas (playwright + httpx)..."
    py -m pip install "playwright==1.55.0" "httpx==0.28.1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$env:STECH_RESEARCH_WORKER_TOKEN = $Token
$env:STECH_RENDER_URL = $Server

py .\tools\research_worker_windows.py
exit $LASTEXITCODE
