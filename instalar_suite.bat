@echo off
title RPA Suite v5 - Instalador

echo.
echo  ================================================
echo   RPA Suite v5 - Instalador de Dependencias
echo   Andres Diaz - 2026
echo  ================================================
echo.
echo  Instalara todas las librerias necesarias.
echo  Tiempo estimado: 3-8 minutos.
echo.
echo  REQUIERE: Python 3.10+ instalado con pip.
echo            Conexion a internet.
echo.
pause

:: ============================================================
:: VERIFICAR PYTHON
:: ============================================================
echo.
echo [1/7] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python no encontrado en PATH.
    echo  Descargalo de: https://www.python.org/downloads/
    echo  Marca "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)
python --version
echo  OK: Python encontrado.

:: ============================================================
:: ACTUALIZAR PIP
:: ============================================================
echo.
echo [2/7] Actualizando pip...
python -m pip install --upgrade pip --quiet
echo  OK: pip actualizado.

:: ============================================================
:: DEPENDENCIAS CORE
:: ============================================================
echo.
echo [3/7] Instalando dependencias CORE...
echo  pandas, numpy, openpyxl, python-dotenv, paramiko,
echo  streamlit, plotly, reportlab, customtkinter, requests, scikit-learn
echo.

pip install pandas --quiet
if errorlevel 1 (echo  ERROR: pandas) else (echo  OK: pandas)

pip install numpy --quiet
if errorlevel 1 (echo  ERROR: numpy) else (echo  OK: numpy)

pip install openpyxl --quiet
if errorlevel 1 (echo  ERROR: openpyxl) else (echo  OK: openpyxl)

pip install python-dotenv --quiet
if errorlevel 1 (echo  ERROR: python-dotenv) else (echo  OK: python-dotenv)

pip install paramiko --quiet
if errorlevel 1 (echo  ERROR: paramiko) else (echo  OK: paramiko)

pip install streamlit --quiet
if errorlevel 1 (echo  ERROR: streamlit) else (echo  OK: streamlit)

pip install plotly --quiet
if errorlevel 1 (echo  ERROR: plotly) else (echo  OK: plotly)

pip install reportlab --quiet
if errorlevel 1 (echo  ERROR: reportlab) else (echo  OK: reportlab)

pip install customtkinter --quiet
if errorlevel 1 (echo  ERROR: customtkinter) else (echo  OK: customtkinter)

pip install requests --quiet
if errorlevel 1 (echo  ERROR: requests) else (echo  OK: requests)

pip install scikit-learn --quiet
if errorlevel 1 (echo  ERROR: scikit-learn) else (echo  OK: scikit-learn)

:: ============================================================
:: DEPENDENCIAS WINDOWS (robots + watchdog)
:: ============================================================
echo.
echo [4/7] Instalando dependencias Windows (robots + watchdog)...
echo  pyautogui, pygetwindow, Pillow, pywin32
echo.

pip install pyautogui --quiet
if errorlevel 1 (echo  ERROR: pyautogui) else (echo  OK: pyautogui)

pip install pygetwindow --quiet
if errorlevel 1 (echo  ERROR: pygetwindow) else (echo  OK: pygetwindow)

pip install Pillow --quiet
if errorlevel 1 (echo  ERROR: Pillow) else (echo  OK: Pillow)

pip install pywin32 --quiet
if errorlevel 1 (
    echo  ADVERTENCIA: pywin32 fallo con pip. Intentando alternativa...
    python -m pip install pywin32 --upgrade
    if errorlevel 1 (
        echo  ERROR: pywin32 no se instalo automaticamente.
        echo  Descargalo manualmente desde:
        echo  https://github.com/mhammond/pywin32/releases
        echo  Busca el .exe para tu Python (cp312, cp311, cp310)
    ) else (
        echo  OK: pywin32 (metodo alternativo)
    )
) else (
    echo  OK: pywin32
)

echo.
echo  Ejecutando post-install de pywin32...
python -m pywin32_postinstall -install >nul 2>&1
echo  OK: pywin32 post-install listo.

:: ============================================================
:: GEMINI IA
:: ============================================================
echo.
echo [5/7] Instalando Gemini IA...
echo  google-generativeai
echo.

pip install google-generativeai --quiet
if errorlevel 1 (echo  ERROR: google-generativeai) else (echo  OK: google-generativeai)

:: ============================================================
:: OPCIONALES
:: ============================================================
echo.
echo [6/7] Instalando opcionales...
echo  pdfplumber, pywebview, qrcode
echo.

pip install pdfplumber --quiet
if errorlevel 1 (echo  AVISO: pdfplumber no instalado (no critico)) else (echo  OK: pdfplumber)

pip install pywebview --quiet
if errorlevel 1 (echo  AVISO: pywebview no instalado (no critico)) else (echo  OK: pywebview)

pip install qrcode --quiet
if errorlevel 1 (echo  AVISO: qrcode no instalado (no critico)) else (echo  OK: qrcode)

:: ============================================================
:: VERIFICACION FINAL
:: ============================================================
echo.
echo [7/7] Verificando instalacion...
echo.

python -c "
paquetes = [
    ('pandas',              'CORE'),
    ('numpy',               'CORE'),
    ('openpyxl',            'CORE'),
    ('dotenv',              'CORE'),
    ('paramiko',            'CORE'),
    ('streamlit',           'CORE'),
    ('plotly',              'CORE'),
    ('reportlab',           'CORE'),
    ('customtkinter',       'CORE'),
    ('pyautogui',           'WIN'),
    ('pygetwindow',         'WIN'),
    ('PIL',                 'WIN'),
    ('win32gui',            'WIN'),
    ('google.generativeai', 'AI'),
    ('pdfplumber',          'OPT'),
]
errores = 0
for imp, cat in paquetes:
    try:
        __import__(imp.split('.')[0])
        print('  OK  [' + cat + '] ' + imp)
    except ImportError:
        if cat == 'OPT':
            print('  --  [' + cat + '] ' + imp + ' (opcional)')
        else:
            print('  ERR [' + cat + '] ' + imp + '  <-- FALTA')
            errores += 1
print()
if errores:
    print('  RESULTADO: ' + str(errores) + ' paquetes faltantes. Ver ERR arriba.')
else:
    print('  RESULTADO: Todo instalado correctamente.')
"

echo.
echo  ================================================
echo   INSTALACION FINALIZADA
echo  ================================================
echo.
echo  PASO SIGUIENTE OBLIGATORIO:
echo  Renombra el archivo _env a  .env  (con el punto)
echo  y completalo con tus credenciales reales.
echo.
echo  Para lanzar la suite:
echo    python main_gui.py
echo.
echo  Para el dashboard solo:
echo    streamlit run app_dashboard.py
echo.
echo  NOTA - easyocr (Conciliador OCR) NO instalado.
echo  Requiere PyTorch (~2GB). Solo si lo necesitas:
echo    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
echo    pip install easyocr
echo.
pause
