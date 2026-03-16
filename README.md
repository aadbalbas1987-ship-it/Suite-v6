# 🚀 Retail Engine: RPA Suite v6.0

![Version](https://img.shields.io/badge/Versi%C3%B3n-6.0-blue)
![Python](https://img.shields.io/badge/Python-3.10%2B-green)
![Status](https://img.shields.io/badge/Estado-Producci%C3%B3n-success)
![AI](https://img.shields.io/badge/IA-Groq%20%7C%20Llama%203.3-purple)

**Retail Engine (RPA Suite v6)** es una infraestructura integral de automatización empresarial (RPA) e Inteligencia de Negocios (BI) diseñada específicamente para la industria del retail y consumo masivo. 

El sistema conecta un ERP Legacy (basado en consola/terminal) con tecnologías modernas de Análisis de Datos, Machine Learning e Inteligencia Artificial Generativa, eliminando la carga manual y potenciando la toma de decisiones estratégicas.

---

## 🧠 Arquitectura Core (Optimizaciones Enterprise)

La versión 6.0 abandona las simulaciones de teclado tradicionales en favor de una arquitectura de backend robusta y silenciosa:

*   **Sincronización Estricta (Anti-Amontonamiento):** Los robots utilizan `Paramiko` para inyectar comandos directamente a través de SSH. Se implementó una limpieza predictiva del buffer TCP para evitar que el ERP legacy colapse ante cargas masivas.
*   **Caché en Memoria RAM (O(1)):** Las búsquedas de descripciones de artículos no consultan el disco. Al arrancar, el sistema carga más de 10,000 SKUs en un Hash Map (Diccionario), permitiendo búsquedas en nanosegundos y evitando cuellos de botella en los dashboards.
*   **Gobernanza de Base de Datos (Anti-Lock):** Base de datos SQLite configurada en **modo WAL (Write-Ahead Logging)** con *Exponential Backoff*. Esto permite que los robots escriban el historial de precios al mismo tiempo que los analistas leen los dashboards, sin bloqueos (`database is locked`).
*   **Control de Procesos Huérfanos:** Un recolector de basura (Garbage Collector) en segundo plano limpia puertos trabados (8501, 8502, etc.) usando comandos nativos de red de Windows al iniciar la app.
*   **Modo Backdoor (Segundo Plano):** El 100% de los robots operan en segundo plano. El usuario puede seguir utilizando su computadora mientras el sistema gestiona precios, inventarios y cheques de forma invisible.

---

## 🤖 Módulos de Automatización (Robots Paramiko)

Todos los robots incluyen un sistema de **Self-Healing (Autoreparación) con IA**. Si el ERP legacy arroja un error inesperado, el robot captura la pantalla de la terminal, se la envía a la IA de Groq (Llama-3.3-70b) y toma la decisión correcta (`ESC`, `ENTER`, `END`) para destrabarse y continuar trabajando.

1.  **⚡ Gestión de Precios (`Precios_Paramiko.py`):** Carga masiva de listas de precios, costos, precios mayoristas y márgenes. Detecta márgenes negativos preventivamente.
2.  **⚡ Inventarios y Stock (`Stock_Paramiko.py`):** Actualización de stock físico en el ERP mediante Excel. Soporta manejo de decimales y gramajes.
3.  **⚡ Ajustes Analíticos (`Ajuste_Paramiko.py`):** Generación de Notas de Crédito / Ajustes de inventario por mermas o diferencias de auditoría.
4.  **⚡ Cartera de Cheques (`Cheques_Paramiko.py`):** Carga de cheques de terceros, cálculo automático de retenciones y balance de comprobantes en el sistema financiero.

---

## 📊 Decision Intelligence (Portal de Dashboards)

El sistema incluye un portal unificado en **Streamlit** para la analítica avanzada del negocio, transformando datos crudos en acciones concretas.

### 1. Business Intelligence (BI) y What-If
*   **Análisis ABC:** Clasificación automática del catálogo (Principio de Pareto).
*   **Efectividad de Promociones:** Evaluación del costo de los descuentos vs. el incremento del volumen de unidades.
*   **Simulador de Escenarios (What-If):** Cálculo predictivo del impacto en la caja ante subidas de precios, aplicando la elasticidad de la demanda.

### 2. Prevención de Quiebres y Sobrestock
*   **Estacionalidad Proactiva:** Ajuste algorítmico de la demanda por meses pico (diciembre) y meses valle (enero).
*   **Heatmap de Capital Inmovilizado:** Treemap interactivo que muestra dónde está el dinero "dormido" por sobrestock.
*   **Alertas por Webhook:** Botón de pánico que dispara alertas directo a **WhatsApp** (vía CallMeBot) advirtiendo sobre pérdidas de caja inminentes por quiebres en artículos de Clase A.

### 3. CRM y Segmentación de Clientes (Matriz RFM)
*   Clasificación algorítmica de clientes basada en **Recencia, Frecuencia y Valor Monetario**.
*   Etiquetado dinámico: *🏆 Campeones*, *⚠️ En Riesgo*, *🌱 Promesas*.
*   Dashboard exportable a Excel para accionar campañas de marketing y retención.

### 4. Machine Learning & Auditoría
*   **Detección de Anomalías (Isolation Forest):** Modelo de Scikit-Learn que evalúa comportamientos atípicos entre el volumen de ventas y el stock físico almacenado.
*   **Centro de Auditoría:** Trazabilidad en tiempo real. Cruza los precios actuales del sistema contra el historial de intentos del robot, calculando deltas y marcando discrepancias.

---

## 🛠️ Herramientas Adicionales

*   **OCR de Remitos en Lote (Gemini Vision):** Lectura masiva de facturas/remitos en JPG/PNG, extrayendo tablas estructuradas a Excel.
*   **Validación de CUITs:** Integración directa con el padrón AFIP.
*   **Descargas SSH (SFTP):** Extracción automatizada de reportes (ventas, clientes, stock) desde el servidor cloud local.
*   **Programador de Tareas (Scheduler):** Ejecución desatendida de robots a horas predefinidas.

---

## ⚙️ Instalación y Despliegue

### 1. Requisitos Previos
*   Windows 10 / 11 o Windows Server.
*   Python 3.10 o superior (con la opción "Add to PATH" marcada).
*   Git para Windows.

### 2. Instalación Automática
Ejecutar el archivo batch proporcionado en la raíz del proyecto. Este script instalará y validará todas las dependencias necesarias.
```cmd
instalar_suite.bat
```
*Dependencias principales: `pandas`, `customtkinter`, `streamlit`, `plotly`, `paramiko`, `scikit-learn`, `requests`, `google-generativeai`.*

### 3. Configuración del Entorno (.env)
Crear un archivo `.env` en la raíz (basado en el panel "Configuración" de la GUI) con:
```ini
# Credenciales SSH
SSH_HOST=192.168.x.x
SSH_PORT=22
SSH_USER=tu_usuario
SSH_PASSWORD=tu_clave

# Inteligencia Artificial
GROQ_API_KEY=gsk_tu_clave_de_groq
GEMINI_API_KEY=AIzaSy_tu_clave_de_gemini

# Alertas Webhook (Opcional)
WHATSAPP_PHONE=+549XXXXXXXXXX
WHATSAPP_APIKEY=123456
```

### 4. Ejecución
Lanzar la interfaz gráfica principal:
```cmd
python main_gui.py
```

---

## 📁 Estructura de Directorios

```text
RPA_Suite_v6/
│
├── main_gui.py                # Interfaz gráfica principal (CustomTkinter)
├── config.py                  # Gestor de variables de entorno y constantes
├── instalar_suite.bat         # Script de despliegue
├── Descripcionesmaestras.xlsx # BD Maestra para Caché en RAM O(1)
│
├── core/                      # 🧠 Lógica empresarial profunda
│   ├── database.py            # Motor SQLite con WAL y Anti-Lock
│   ├── utils.py               # Caché RAM, LLM Groq, Formateos
│   ├── pre_validador.py       # Validaciones pre-ejecución (Márgenes, Deltas)
│   └── seguridad.py           # Encriptación AES-256 de credenciales
│
├── robots/                    # 🤖 Trabajadores SSH Paramiko
│   ├── Precios_Paramiko.py
│   ├── Stock_Paramiko.py
│   ├── Ajuste_Paramiko.py
│   └── Cheques_Paramiko.py
│
├── dashboards/                # 📊 Analítica y Streamlit (Portal Unificado)
│   ├── main_app.py
│   ├── app_dashboard.py       # BI, ABC, Simulador
│   ├── quiebres_dashboard.py  # Detección Anomalías ML, Webhooks
│   ├── crm_dashboard.py       # RFM Clientes
│   └── auditoria_dashboard.py # Auditoría de Robots
│
├── input/                     # Cola de entrada de archivos a procesar
├── procesados/                # Archivos terminados y resultados OCR/Auditoría
└── logs/                      # Caja Negra SSH, logs rotativos
```

---

## 🛡️ Seguridad

El sistema cuenta con un panel de seguridad dedicado (`abrir_panel_seguridad`) que garantiza que los datos sensibles nunca queden expuestos:
1.  **Cifrado AES-256-GCM:** Posibilidad de cifrar el `.env` con una master password.
2.  **Verificación de Integridad (SHA-256):** Detecta si alguien modificó las configuraciones sin autorización.
3.  **Git Safe Push:** Herramienta integrada que actualiza GitHub automáticamente asegurando que ningún archivo de configuración o logs locales suba al repositorio público (inyección forzada de `.gitignore`).

---
*Desarrollado con arquitectura Data-Driven para minimizar la brecha entre operaciones logísticas (Backoffice) e inteligencia comercial.*