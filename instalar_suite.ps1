# ============================================================
# instalar_suite.ps1 - RPA Suite v5
# ============================================================
# Descomprime RPA_Suite_v5_actualizado.zip y reemplaza todos
# los archivos .py en sus carpetas correctas.
#
# INSTRUCCIONES:
#   1. Copia este .ps1 y el .zip a C:\Users\HP\Desktop\
#   2. Abre PowerShell
#   3. Ejecuta: .\instalar_suite.ps1
# ============================================================

$DESTINO = "C:\Users\HP\Desktop\RPA_Suite_v5"
$ZIP     = "$PSScriptRoot\RPA_Suite_v5_actualizado.zip"
$TEMP    = "$env:TEMP\rpa_suite_extract"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  RPA Suite v5 - Instalador de archivos"    -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# -- Verificar que el ZIP existe --------------------------------
if (-not (Test-Path $ZIP)) {
    Write-Host "  ERROR: No se encontro: $ZIP" -ForegroundColor Red
    Write-Host "  Asegurate de que el .zip este junto a este script." -ForegroundColor Yellow
    exit 1
}

# -- Verificar que la carpeta destino existe --------------------
if (-not (Test-Path $DESTINO)) {
    Write-Host "  ERROR: No se encontro la carpeta: $DESTINO" -ForegroundColor Red
    exit 1
}

# -- Crear subcarpetas si no existen ----------------------------
foreach ($carpeta in @("robots", "dashboards", "core", "tools")) {
    $ruta = Join-Path $DESTINO $carpeta
    if (-not (Test-Path $ruta)) {
        New-Item -ItemType Directory -Path $ruta | Out-Null
        Write-Host "  [+] Carpeta creada: $carpeta\" -ForegroundColor Green
    }
}

# -- __init__.py en robots/ y core/ ----------------------------
foreach ($carpeta in @("robots", "core")) {
    $init = Join-Path $DESTINO "$carpeta\__init__.py"
    if (-not (Test-Path $init)) {
        "" | Out-File -FilePath $init -Encoding utf8
        Write-Host "  [+] Creado: $carpeta\__init__.py" -ForegroundColor Green
    }
}

# -- Extraer ZIP a carpeta temporal ----------------------------
Write-Host ""
Write-Host "  Extrayendo ZIP..." -ForegroundColor Cyan

if (Test-Path $TEMP) { Remove-Item $TEMP -Recurse -Force }
Expand-Archive -Path $ZIP -DestinationPath $TEMP -Force
Write-Host "  OK: ZIP extraido" -ForegroundColor Green

# -- Copiar cada archivo a su destino correcto -----------------
Write-Host ""
Write-Host "  Copiando archivos..." -ForegroundColor Cyan

$archivos = Get-ChildItem -Path $TEMP -Recurse -Filter "*.py"
$copiados = 0
$errores  = 0

foreach ($archivo in $archivos) {
    $relativa        = $archivo.FullName.Substring($TEMP.Length).TrimStart("\")
    $destino_archivo = Join-Path $DESTINO $relativa
    $dir_destino     = Split-Path $destino_archivo -Parent

    if (-not (Test-Path $dir_destino)) {
        New-Item -ItemType Directory -Path $dir_destino | Out-Null
    }

    try {
        Copy-Item -Path $archivo.FullName -Destination $destino_archivo -Force
        Write-Host ("  OK: " + $relativa) -ForegroundColor Green
        $copiados++
    } catch {
        Write-Host ("  FAIL: " + $relativa + " - " + $_.Exception.Message) -ForegroundColor Red
        $errores++
    }
}

# -- Limpieza --------------------------------------------------
Remove-Item $TEMP -Recurse -Force

# -- Resultado final -------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
if ($errores -eq 0) {
    Write-Host "  Instalacion completada: $copiados archivos OK" -ForegroundColor Green
} else {
    Write-Host "  Completado con errores: $copiados OK, $errores fallidos" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  Estructura final:" -ForegroundColor Cyan
Get-ChildItem $DESTINO -Recurse -Filter "*.py" |
    Where-Object { $_.FullName -notlike "*\__pycache__*" } |
    ForEach-Object { "    " + $_.FullName.Replace($DESTINO + "\", "") } |
    Sort-Object |
    Write-Host -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
