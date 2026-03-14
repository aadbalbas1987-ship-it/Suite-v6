@echo off
title Reinicio de Git - RPA Suite
color 0B
echo ========================================================
echo     RESETEO COMPLETO DE GIT Y GITHUB
echo ========================================================
echo.
echo Esto borrara la configuracion local trabada de Git.
echo Tus archivos de codigo y la Suite NO se borraran.
echo.
pause

cd /d "%~dp0"

:: 1. Borrar la carpeta oculta .git para empezar de cero
if exist .git (
    rmdir /s /q .git
    echo [OK] Historial y configuracion anterior borrados.
)

:: 2. Inicializar de nuevo
git init
git branch -m main

:: 3. Pedir datos
echo.
set /p GIT_NAME="1. Tu nombre (ej. Andres): "
set /p GIT_EMAIL="2. Tu email de GitHub: "
set /p GIT_TOKEN="3. Pega tu Token (empieza con ghp_...): "

:: 4. Configurar con el token inyectado
git config user.name "%GIT_NAME%"
git config user.email "%GIT_EMAIL%"
git remote add origin https://%GIT_TOKEN%@github.com/aadbalbas1987-ship-it/Suite-v6.git

:: 5. Asegurar el .gitignore para no subir claves
echo .env > .gitignore
echo .env.enc >> .gitignore
echo .env.hash >> .gitignore
echo logs/ >> .gitignore
echo __pycache__/ >> .gitignore

:: 6. Subir todo
echo.
echo Agregando archivos...
git add .
git commit -m "Reinicio limpio de configuracion"

echo.
echo Empujando a GitHub...
git push -u origin main --force

echo.
echo ========================================================
echo   EXITO: GIT RECONFIGURADO Y CONECTADO.
echo ========================================================
pause
