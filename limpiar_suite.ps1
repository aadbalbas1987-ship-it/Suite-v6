# ============================================================
# limpiar_suite.ps1 - RPA Suite v5
# ============================================================
# Elimina archivos duplicados mal ubicados y crea los
# __init__.py faltantes.
# Ejecutar desde cualquier lugar, apunta directo a la suite.
# ============================================================

$BASE = "C:\Users\HP\Desktop\RPA_Suite_v5"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  RPA Suite v5 - Limpieza de duplicados"    -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# -- Archivos duplicados a eliminar ---------------------------
# analizador_conteo.py pertenece a core\ no a robots# conciliador_flexible.py pertenece a tools\ no a robots
$duplicados = @(
    "robots\analizador_conteo.py",
    "robots\conciliador_flexible.py"
)

foreach ($rel in $duplicados) {
    $ruta = Join-Path $BASE $rel
    if (Test-Path $ruta) {
        Remove-Item $ruta -Force
        Write-Host "  BORRADO: $rel" -ForegroundColor Yellow
    } else {
        Write-Host "  YA NO EXISTE: $rel" -ForegroundColor Gray
    }
}

# -- __init__.py faltantes ------------------------------------
# core\ necesita __init__.py para que Python lo trate como paquete

$inits = @("core", "tools")

foreach ($carpeta in $inits) {
    $ruta = Join-Path $BASE "$carpeta\__init__.py"
    if (-not (Test-Path $ruta)) {
        "" | Out-File -FilePath $ruta -Encoding utf8
        Write-Host "  CREADO: $carpeta\__init__.py" -ForegroundColor Green
    } else {
        Write-Host "  YA EXISTE: $carpeta\__init__.py" -ForegroundColor Gray
    }
}

# -- Verificacion final ---------------------------------------
Write-Host ""
Write-Host "  Estructura .py (sin .venv):" -ForegroundColor Cyan
Get-ChildItem $BASE -Recurse -Filter "*.py" |
    Where-Object { $_.FullName -notlike "*\.venv\*" -and $_.FullName -notlike "*\__pycache__\*" } |
    ForEach-Object { "    " + $_.FullName.Replace($BASE + "\", "") } |
    Sort-Object |
    Write-Host -ForegroundColor White

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Listo. Estructura limpia." -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
