# 🤖 RPA Suite v6 — Andrés Díaz

Una suite integral de Automatización Robótica de Procesos (RPA), Inteligencia Artificial (IA) y Business Intelligence (BI) orientada a sistemas ERP retail/mayoristas.

## 🆕 Novedades v6

### 🔒 Capa de Seguridad Militar (Nuevo)
- **Cifrado `.env`**: Las credenciales se cifran con AES-256-GCM y PBKDF2 (100.000 iteraciones).
- **Git Seguro**: Auto-configuración de Git que bloquea subidas accidentales de claves al repo.
- **Auditoría**: Panel en la GUI para verificar integridad de variables y portapapeles con auto-limpieza.

### 🧠 Integración de IA y Machine Learning (Fase 1 & 2)
- **Normalizador de Artículos (Gemini 1.5)**: Convierte descripciones "sucias" del ERP a formatos estándar con asignación automática de categorías.
- **Detección de Anomalías (Isolation Forest)**: ML aplicado en stock/ventas para alertar riesgos de quiebre o sobre-stock.
- **Resúmenes Ejecutivos IA (Groq)**: Lectura de dashboards de quiebre que emiten recomendaciones redactadas en lenguaje natural.

### 🛠️ Nuevos Robots y Backdoors Paramiko
- **Backdoors Paramiko**: Módulos para ejecutar cambios en Precios, Stock y Ajustes de manera ultra rápida, por túneles SSH nativos, ignorando la GUI de PuTTY.
- **Robot UXB**: Corrector inteligente de Unidades por Bulto.
- **Alta Masiva de Artículos**: Robot que crea nuevos SKUs e interactúa con el menú del sistema legado.

### 📊 Dashboards Streamlit Unificados & Compartidos
- Portal consolidado con Quiebres de Stock, Pricing Intelligence, Conciliación Bancaria y Business Intelligence.
- **Compartir vía Ngrok**: Botón de un solo clic para exponer un dashboard en Internet de forma segura y compartirlo por WhatsApp (incluye código QR).

### ⚙️ Mejoras Core
- **Watchdog con Visión Artificial**: Monitorea el progreso del robot. Si salta una ventana inesperada de Windows o PuTTY se congela, bloquea la ejecución para evitar desastres.
- **Base de Datos SQLite (`rpa_suite.db`)**: Tracking del historial completo de lo inyectado en el sistema.
- **Modo Programado (Scheduler)**: Para dejar tareas en background (Ej: que "Stock" corra a las 8:00 AM).
- **Sistema de Checkpoint**: Guarda el estado ante una falla; permite hacer *dry-runs* sin impactar la DB.

## 📂 Estructura

```
RPA_Suite_v5/
├── main_gui.py              ← GUI principal (v5.4)
├── config.py
├── .env                     ← Credenciales (editar desde GUI)
├── .env.template
│
├── input/                   ← Dropear archivos aquí
│   └── LEER_ESTO.txt
│
├── core/
│   ├── input_manager.py     ← Carga batch por keyword
│   ├── pre_validador.py     ← NEW: Validaciones pre-ejecución
│   ├── notificaciones.py    ← NEW: Notificaciones Windows
│   ├── checkpoint.py
│   ├── file_manager.py
│   ├── etl_precios.py
│   └── normalizador_articulos.py
│
├── robots/
│   ├── Robot_Putty.py       ← keyword: carga
│   ├── ajuste.py            ← keyword: nc
│   ├── Precios_V2.py        ← keyword: precios
│   ├── Cheques.py           ← keyword: cheque
│   ├── robot_ssh_report.py
│   └── robot_descarga_datos.py
│
├── dashboards/
│   ├── app_dashboard.py     (puerto 8501)
│   ├── quiebres_dashboard.py (puerto 8502)
│   └── pricing_dashboard.py  (puerto 8504)
│
└── tools/
    ├── watchdog.py
    ├── diagnostico_ssh.py
    └── pricing_research.py
```

## 🚀 Instalación

```powershell
pip install -r requirements.txt
python main_gui.py
```

## 🔑 Keywords de archivos (input/)

| Robot | Keyword | Ejemplo |
|---|---|---|
| Stock | `carga` | `carga_lunes.xlsx` |
| Ajuste | `nc` | `NC semana.xlsx` |
| Precios | `precios` | `precios trio.xlsx` |
| Cheques | `cheque` | `cheques semana.xlsx` |

*RPA Suite v5.4 — Marzo 2026*
