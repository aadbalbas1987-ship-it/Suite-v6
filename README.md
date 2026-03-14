# 🤖 RPA Suite v5.4 — Andrés Díaz

## 🆕 Novedades v5.4

### Status Bar fija abajo de la ventana
Muestra en tiempo real (polling cada 3 segundos):
- 🟢/🔴 PuTTY detectado o no
- 🟢/⚫ Dashboard Streamlit activo o no  
- 🟡 Robot corriendo / inactivo
- 📂 Cantidad de archivos listos en input/

### Popup de preview + confirmación antes de ejecutar
Antes de tocar PuTTY, se abre un popup con:
- Resumen completo del archivo (suma de control, total filas)
- Mini tabla con las primeras 5 filas del Excel
- Alertas de validación por color (✅ / ⚠ / ❌)
- Botón **Confirmar y Ejecutar** / Cancelar
- Si hay errores críticos (ej: cheques vencidos, margen negativo) el botón Confirmar queda deshabilitado

### Validaciones pre-ejecución automáticas
| Robot | Qué valida |
|---|---|
| **Stock** | Suma de control de cantidades, SKUs duplicados, filas inválidas |
| **Ajuste** | Delta neto (positivo+negativo), tipo de ingreso válido, duplicados |
| **Precios** | Margen negativo (bloquea), margen bajo mínimo (advierte), cambios >20% vs anterior |
| **Cheques** | Fechas vencidas (bloquea), montos atípicos, resumen por banco |

### Notificaciones de escritorio Windows
Cuando la ventana está minimizada, al terminar un lote aparece notificación nativa de Windows con el resumen. También al haber errores críticos.

### Panel de Configuración desde la GUI
Botón "Configuración" en el sidebar abre un editor del archivo `.env` directamente en la app. Guardá las credenciales sin abrir el Bloc de Notas.

---

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
