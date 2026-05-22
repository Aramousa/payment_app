param(
    [string]$Python = ".\venv\Scripts\python.exe",
    [string]$TesseractDir = "C:\Program Files\Tesseract-OCR"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $Root
$WheelDir = Join-Path $Root "python-wheels"
$Requirements = Join-Path $ProjectRoot "requirements.txt"
$TessDir = Join-Path $Root "tesseract"
$Installer = Join-Path $TessDir "tesseract-ocr-w64-setup-5.5.0.20241111.exe"
$TessData = Join-Path $TessDir "tessdata"

if (!(Test-Path $Python)) {
    throw "Python executable not found: $Python"
}
if (!(Test-Path $WheelDir)) {
    throw "Wheelhouse not found: $WheelDir"
}

& $Python -m pip install --no-index --find-links $WheelDir -r $Requirements

if (Test-Path $Installer) {
    Write-Host "Tesseract installer is available at: $Installer"
    Write-Host "Run it on the server if Tesseract OCR is not installed yet."
}

if (Test-Path $TessData) {
    $TargetTessData = Join-Path $TesseractDir "tessdata"
    Write-Host "Copy OCR language files from:"
    Write-Host "  $TessData"
    Write-Host "to:"
    Write-Host "  $TargetTessData"
    Write-Host "At minimum copy fas.traineddata and eng.traineddata."
}

Write-Host "Offline Python packages installed."
