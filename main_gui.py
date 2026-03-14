"""
main_gui.py — RPA Suite v5.9
============================
Interfaz principal. Mejoras v5.9:
  - Status bar fija abajo: PuTTY / Streamlit / Robot / Archivos en input
  - Popup de preview+confirmación antes de ejecutar cualquier robot
  - Validaciones pre-ejecución: suma control, márgenes, fechas, duplicados
  - Notificaciones de escritorio Windows (cuando ventana minimizada)
  - Configuración .env desde GUI (panel Settings)
  - Carga batch por keyword (input/)
  - Logging profesional rotativo
  - PyWebView ventana nativa
"""
import customtkinter as ctk
import pandas as pd
import time, os, sys, threading, subprocess, traceback
from pathlib import Path
from tkinter import filedialog, messagebox

# ── Logging profesional ──────────────────────────────────────
import logging
import logging.handlers

def _setup_logger() -> logging.Logger:
    if sys.platform == "win32":
        _appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        _appdata = Path.home()
    _log_dir = _appdata / "RPASuite" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = _log_dir / "rpa_suite.log"

    logger = logging.getLogger("rpa_suite")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    fh = logging.handlers.RotatingFileHandler(
        _log_file, maxBytes=5*1024*1024, backupCount=10, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(fh)
    return logger

_logger = _setup_logger()

# ── PyWebView — disponible si instalado ─────────────────────
try:
    import webview as _webview  # type: ignore[import-untyped]
    WEBVIEW_OK = True
except ImportError:
    _webview = None  # type: ignore[assignment]
    WEBVIEW_OK = False

from config import validar_entorno
from core.etl_precios import procesar_lista_precios_mbf
from core.normalizador_articulos import ejecutar_normalizador
from core.utils import (
    forzar_caps_off,
    enfocar_putty,
    etl_lpcio_a_excel,
    etl_ventas_a_excel,
    motor_bi_avanzado,
    procesar_analitica_conteo,
    disparar_descarga_ssh,
)
from core.file_manager import listar_procesados, obtener_historial
from robots.robot_descarga_datos import ejecutar_descarga_dashboard, calcular_semanas, MESES

from robots.Robot_Putty import ejecutar_stock
from robots.ajuste import ejecutar_ajuste, ejecutar_ajuste_analitico
from robots.Cheques import ejecutar_cheques
from robots.Precios_V2 import ejecutar_precios_v2
from core.input_manager import InputManager, ROBOT_KEYWORDS
from core.pre_validador import validar_por_modo, PreValidacion, guardar_snapshot_precios
from core.notificaciones import notificar_exito, notificar_error
from core.modo_programado import Scheduler

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent


class SuiteRPA(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("RPA Suite v5.9 — Andrés Díaz")
        self.geometry("1400x880")
        self.minsize(1200, 740)
        self.state("zoomed")
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.archivo_ruta = None
        self.modo = None
        self.velocidad_var = ctk.DoubleVar(value=1.0)
        self._streamlit_proc = None
        self._streamlit_proc_quiebres = None
        self._streamlit_proc_pricing = None
        self._streamlit_proc_pricing_intel = None
        self._streamlit_proc_conciliacion = None
        self._streamlit_proc_normalizador = None
        self._streamlit_proc_cxc = None
        self._norm_stop_event = None
        self._robot_corriendo = False  # para status bar
        self._scheduler = Scheduler()

        # Validar .env al arrancar
        self._validar_entorno_inicio()
        self.setup_ui()
        # Mostrar resumen de archivos disponibles en input/
        self.after(500, self._mostrar_resumen_input)
        # Arrancar polling del status bar
        self.after(1000, self._actualizar_status_bar)

    def _mostrar_resumen_input(self):
        resumen = InputManager.resumen_input(base_dir=BASE_DIR)
        self.log("─" * 50)
        self.log(resumen)
        self.log("─" * 50)

    def _validar_entorno_inicio(self):
        """Avisa si faltan variables de entorno críticas."""
        warnings = validar_entorno(requerir_ssh=True, requerir_gemini=True)
        if warnings:
            msg = "\n".join(warnings)
            messagebox.showwarning(
                "Configuración incompleta",
                f"Se detectaron variables faltantes en .env:\n\n{msg}\n\n"
                "Algunos módulos pueden no funcionar.\n"
                "Completá el archivo .env para activar todas las funciones."
            )

    # =========================================================
    # UI SETUP
    # =========================================================
    def setup_ui(self):
        # ── Grid raíz: sidebar | content / status bar abajo ──
        self.grid_columnconfigure(0, weight=0)   # sidebar fijo
        self.grid_columnconfigure(1, weight=1)   # content expandible
        self.grid_rowconfigure(0, weight=1)       # fila principal
        self.grid_rowconfigure(1, weight=0)       # status bar fija abajo

        # ══════════════════════════════════════════════════
        # COLORES SAP FIORI
        # ══════════════════════════════════════════════════
        SB_BG     = "#1D2D3E"
        SB_HOVER  = "#243547"
        SB_ACTIVE = "#0057A8"
        SB_TEXT   = "#C8D6E5"
        SB_MUTED  = "#4A6580"
        SB_DIV    = "#253444"

        # ══════════════════════════════════════════════════
        # SIDEBAR
        # ══════════════════════════════════════════════════
        # Contenedor externo fijo
        self._sidebar_outer = ctk.CTkFrame(self, width=256, corner_radius=0, fg_color=SB_BG)
        self._sidebar_outer.grid(row=0, column=0, sticky="nsew")
        self._sidebar_outer.grid_propagate(False)
        self._sidebar_outer.pack_propagate(False)

        # Logo fijo (no scrollea)
        logo_frame = ctk.CTkFrame(self._sidebar_outer, fg_color="#162333", corner_radius=0)
        logo_frame.pack(fill="x", side="top")
        ctk.CTkLabel(
            logo_frame, text="RPA Suite",
            font=ctk.CTkFont(size=15, weight="bold"), text_color="white"
        ).pack(side="left", padx=18, pady=14)
        ctk.CTkLabel(
            logo_frame, text="v5.9",
            font=ctk.CTkFont(size=10), text_color=SB_ACTIVE
        ).pack(side="left", pady=14)

        # Area scrolleable para los botones
        self.sidebar = ctk.CTkScrollableFrame(
            self._sidebar_outer,
            fg_color=SB_BG,
            corner_radius=0,
            scrollbar_button_color=SB_HOVER,
            scrollbar_button_hover_color=SB_ACTIVE,
        )
        self.sidebar.pack(fill="both", expand=True, side="top")

        def _sep(label=None):
            ctk.CTkFrame(self.sidebar, height=1, fg_color=SB_DIV).pack(fill="x", padx=0, pady=(6, 2))
            if label:
                ctk.CTkLabel(
                    self.sidebar, text=label,
                    font=ctk.CTkFont(size=9, weight="bold"),
                    text_color=SB_MUTED
                ).pack(anchor="w", padx=16, pady=(4, 2))

        def _nav_btn(text, command, icon=""):
            full = f"  {icon}  {text}" if icon else f"  {text}"
            b = ctk.CTkButton(
                self.sidebar, text=full, anchor="w",
                fg_color="transparent", hover_color=SB_HOVER,
                text_color=SB_TEXT, height=32,
                font=ctk.CTkFont(size=11),
                corner_radius=0, border_width=0,
                command=command,
            )
            b.pack(fill="x", padx=0, pady=0)
            return b

        def _mode_btn(text, modo, icon=""):
            full = f"  {icon}  {text}" if icon else f"  {text}"
            b = ctk.CTkButton(
                self.sidebar, text=full, anchor="w",
                fg_color="transparent", hover_color=SB_HOVER,
                text_color=SB_TEXT, height=34,
                font=ctk.CTkFont(size=12),
                corner_radius=0, border_width=0,
                command=lambda m=modo: self.set_modo(m),
            )
            b.pack(fill="x", padx=0, pady=0)
            return b

        # ── Robots ──
        _sep("ROBOTS")
        _nav_btn("Robot UXB",              self.abrir_robot_uxb,       "◈")
        _nav_btn("Alta Masiva Artículos",  self.abrir_robot_articulos, "+")
        _mode_btn("Inventarios / Stock",   "STOCK",            "▸")
        _mode_btn("Stock (Backdoor)",      "STOCK_PARAMIKO",   "⚡")
        _mode_btn("Facturación",           "FACTURA",          "▸")
        _mode_btn("Gestión de Precios",    "PRECIOS",          "▸")
        _mode_btn("Precios (Backdoor)",    "PRECIOS_PARAMIKO", "⚡")
        _mode_btn("Ajustes Basicos",     "AJUSTE",           "▸")
        _mode_btn("Ajustes (Backdoor)",  "AJUSTE_PARAMIKO",  "⚡")
        _mode_btn("Ajuste Analítico",      "AJUSTE_ANALITICO", "▸")
        _mode_btn("Cartera de Cheques",    "CHEQUES",          "▸")

        # ── Herramientas ──
        _sep("HERRAMIENTAS")
        _nav_btn("Descargar Lista Gral",  self.lanzar_descarga_ssh,  "↓")
        _nav_btn("ETL Lista de Precios",  self.lanzar_etl_precios,   "≡")

        # Normalizar con botón stop integrado
        norm_row = ctk.CTkFrame(self.sidebar, fg_color="transparent", corner_radius=0)
        norm_row.pack(fill="x")
        norm_row.grid_columnconfigure(0, weight=1)
        self._btn_norm = ctk.CTkButton(
            norm_row, text="  ✦  Normalizar Artículos", anchor="w",
            fg_color="transparent", hover_color=SB_HOVER,
            text_color=SB_TEXT, height=34,
            font=ctk.CTkFont(size=12),
            corner_radius=0, border_width=0,
            command=self.lanzar_normalizador,
        )
        self._btn_norm.grid(row=0, column=0, sticky="ew")
        self._btn_norm_stop = ctk.CTkButton(
            norm_row, text="■", width=30, height=34,
            fg_color="transparent", hover_color="#7f1d1d",
            text_color=SB_MUTED, corner_radius=0,
            command=self.detener_normalizador, state="disabled",
        )
        self._btn_norm_stop.grid(row=0, column=1)

        _nav_btn("Generar Auditoría",     self.lanzar_analitica,     "◈")
        _nav_btn("Validar CUITs (AFIP)",  self.abrir_validar_cuits,  "◈")

        # ── Dashboards ──
        _sep("DASHBOARDS")
        _nav_btn("Portal de Dashboards",  self.lanzar_portal_dashboards, "📊")
        _nav_btn("Compartir Dashboard",   self.abrir_compartir_dashboard, "📡")
        _nav_btn("Detener Dashboards",    self.detener_dashboards, "⏹")

        # ── Datos ──
        _sep("DATOS")
        _nav_btn("Descargar Datos",       self.abrir_descarga_datos, "↓")
        _nav_btn("Descargar del Servidor",self.abrir_descarga_ssh, "↓")

        # ── Sistema ──
        _sep()
        _nav_btn("Guardar en GitHub",     self.git_commit_push,   "↑")
        _nav_btn("🔐 Seguridad",          self.abrir_panel_seguridad, "🔐")
        _nav_btn("Modo Programado",       self.abrir_modo_programado, "⏰")
        _nav_btn("Actualizar desde Git",  self.git_pull_update,   "↓")
        _nav_btn("Configuracion",         self.abrir_settings,    "⚙")

        # ══════════════════════════════════════════════════
        # ÁREA PRINCIPAL (col 1, row 0)
        # ══════════════════════════════════════════════════
        self.content = ctk.CTkFrame(self, fg_color="#F5F7FA", corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=0)  # toolbar
        self.content.grid_rowconfigure(1, weight=1)  # log (expande)
        self.content.grid_rowconfigure(2, weight=0)  # footer

        # ── Toolbar superior ──────────────────────────────
        toolbar = ctk.CTkFrame(self.content, fg_color="white", corner_radius=0)
        toolbar.grid(row=0, column=0, sticky="ew")
        ctk.CTkFrame(toolbar, height=1, fg_color="#E2E8F0").pack(side="bottom", fill="x")

        tb_inner = ctk.CTkFrame(toolbar, fg_color="transparent")
        tb_inner.pack(fill="x", padx=20, pady=10)
        tb_inner.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            tb_inner, text="Seleccionar Archivo",
            fg_color="#0057A8", hover_color="#004A8F",
            text_color="white", height=34,
            font=ctk.CTkFont(size=12), corner_radius=6,
            command=self.seleccionar_archivo
        ).grid(row=0, column=0, padx=(0, 12))

        self.lbl_archivo = ctk.CTkLabel(
            tb_inner, text="Ningún archivo seleccionado",
            text_color="#94A3B8", font=ctk.CTkFont(size=12)
        )
        self.lbl_archivo.grid(row=0, column=1, sticky="w")

        vel_frame = ctk.CTkFrame(tb_inner, fg_color="transparent")
        vel_frame.grid(row=0, column=2, sticky="e")

        self._vel_valor_label = ctk.CTkLabel(
            vel_frame, text="x1.0",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#0057A8", width=36
        )
        self._vel_valor_label.pack(side="right", padx=(6, 0))

        self._slider_vel = ctk.CTkSlider(
            vel_frame, from_=0.3, to=2.0, number_of_steps=17,
            variable=self.velocidad_var, width=160,
            progress_color="#0057A8", button_color="#0057A8",
            button_hover_color="#004A8F",
            command=self._actualizar_label_velocidad,
        )
        self._slider_vel.pack(side="right")

        ctk.CTkLabel(
            vel_frame, text="Velocidad",
            font=ctk.CTkFont(size=11), text_color="#64748B"
        ).pack(side="right", padx=(0, 8))

        # ── Panel log ─────────────────────────────────────
        log_card = ctk.CTkFrame(
            self.content, fg_color="white", corner_radius=8,
            border_width=1, border_color="#E2E8F0"
        )
        log_card.grid(row=1, column=0, sticky="nsew", padx=20, pady=16)
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        log_hdr = ctk.CTkFrame(log_card, fg_color="transparent")
        log_hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        ctk.CTkLabel(
            log_hdr, text="Registro de Actividad",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#1E293B"
        ).pack(side="left")
        ctk.CTkButton(
            log_hdr, text="Exportar Log", width=90, height=26,
            fg_color="transparent", hover_color="#F1F5F9",
            text_color="#64748B", border_width=1, border_color="#CBD5E1",
            font=ctk.CTkFont(size=10), corner_radius=4,
            command=self.exportar_debug_log
        ).pack(side="right")
        ctk.CTkFrame(log_card, height=1, fg_color="#F1F5F9").grid(
            row=0, column=0, sticky="ew", padx=0, pady=(44, 0)
        )

        self.log_txt = ctk.CTkTextbox(
            log_card, fg_color="white", text_color="#334155",
            border_width=0, font=("Consolas", 11), corner_radius=0, wrap="none",
        )
        self.log_txt.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        # ── Footer con botón Ejecutar ─────────────────────
        footer = ctk.CTkFrame(self.content, fg_color="white", corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        ctk.CTkFrame(footer, height=1, fg_color="#E2E8F0").pack(side="top", fill="x")
        self.btn_run = ctk.CTkButton(
            footer, text="▶   EJECUTAR PROCESO",
            height=40, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0057A8", hover_color="#004A8F",
            text_color="white", corner_radius=6,
            command=self.preparar_ejecucion, state="disabled"
        )
        self.btn_run.pack(side="right", padx=20, pady=10)

        # ══════════════════════════════════════════════════
        # STATUS BAR — fija en row=1 de la ventana raíz
        # ══════════════════════════════════════════════════
        self._status_bar = ctk.CTkFrame(
            self, height=26, corner_radius=0, fg_color="#1D2D3E"
        )
        self._status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")

        self._lbl_status_putty  = self._mk_status_lbl("⬤ PuTTY", "#64748B")
        self._lbl_status_stream = self._mk_status_lbl("⬤ Dashboard", "#64748B")
        self._lbl_status_robot  = self._mk_status_lbl("⬤ Robot inactivo", "#64748B")
        self._lbl_status_input  = self._mk_status_lbl("📂 input: —", "#64748B")
        self._lbl_status_ver    = self._mk_status_lbl("RPA Suite v5.9", "#4A6580", side="right")


    def _mk_status_lbl(self, text, color, side="left"):
        lbl = ctk.CTkLabel(
            self._status_bar, text=text,
            font=ctk.CTkFont(size=10),
            text_color=color, height=26
        )
        lbl.pack(side=side, padx=12)
        return lbl

    def _actualizar_status_bar(self):
        """Polling cada 3s para actualizar el status bar."""
        try:
            from core.utils import enfocar_putty
            import socket

            # PuTTY
            try:
                putty_ok = enfocar_putty(solo_verificar=True) if hasattr(enfocar_putty, '__call__') else False
            except Exception:
                putty_ok = False

            # Streamlit (algún puerto activo)
            stream_ok = False
            for puerto in [8501, 8502, 8504]:
                try:
                    with socket.create_connection(("localhost", puerto), timeout=0.3):
                        stream_ok = True
                        break
                except Exception:
                    pass

            # Archivos en input
            todos = InputManager.listar_todos(base_dir=BASE_DIR)
            total_archivos = sum(len(v) for v in todos.values())

            # Actualizar labels
            self._lbl_status_putty.configure(
                text="⬤ PuTTY OK" if putty_ok else "⬤ PuTTY",
                text_color="#22c55e" if putty_ok else "#ef4444"
            )
            self._lbl_status_stream.configure(
                text="⬤ Dashboard ON" if stream_ok else "⬤ Dashboard OFF",
                text_color="#22c55e" if stream_ok else "#64748B"
            )
            self._lbl_status_robot.configure(
                text="⬤ Robot CORRIENDO" if self._robot_corriendo else "⬤ Robot inactivo",
                text_color="#f59e0b" if self._robot_corriendo else "#64748B"
            )
            self._lbl_status_input.configure(
                text=f"📂 input: {total_archivos} archivo(s)" if total_archivos else "📂 input: vacía",
                text_color="#60a5fa" if total_archivos else "#64748B"
            )
        except Exception:
            pass
        finally:
            self.after(3000, self._actualizar_status_bar)

    def run_in_background(self, target, *args, **kwargs):
        """Lanza una tarea en un hilo seguro, capturando y logueando excepciones."""
        def _wrapper():
            try:
                target(*args, **kwargs)
            except Exception as e:
                import traceback
                _logger.exception(f"Excepción no controlada en hilo {target.__name__}")
                self.log(f"🔥 Error en subproceso: {e}")
        t = threading.Thread(target=_wrapper, daemon=True)
        t.start()
        return t

    # =========================================================
    # HELPERS
    # =========================================================
    def crear_boton_menu(self, texto, modo):
        """Legacy — no usado en v5 redesign."""
        pass

    def set_modo(self, modo):
        self.modo = modo
        kw = ROBOT_KEYWORDS.get(modo, ["?"])[0]
        self.log(f"📍 Módulo seleccionado: {modo}  (keyword de archivos: '{kw}')")

        # Buscar archivos disponibles en input/
        archivos = InputManager.buscar_archivos(modo, base_dir=BASE_DIR)
        if archivos:
            self.log(f"   ✅ {len(archivos)} archivo(s) con '{kw}' en input/:")
            for a in archivos:
                self.log(f"      • {a.name}")
            self.lbl_archivo.configure(
                text=f"📦  {len(archivos)} archivo(s) en input/  (keyword: {kw})",
                text_color="#16a34a"
            )
            self.btn_run.configure(state="normal")
        else:
            self.log(f"   ⚠ No hay archivos con '{kw}' en input/")
            self.log(f"      → Podés usar 'Seleccionar Archivo' para elegir uno manualmente")
            self.lbl_archivo.configure(
                text=f"⚠  Sin archivos '{kw}' en input/  — o seleccioná uno",
                text_color="#f59e0b"
            )
            # Habilitar igual para selección manual
            self.btn_run.configure(state="normal")

    def log(self, msj: str):
        ts = time.strftime('%H:%M:%S')
        self.log_txt.insert("end", f"[{ts}] {msj}\n")
        self.log_txt.see("end")
        # Mirror al archivo de log rotativo
        if "ERROR" in msj or "❌" in msj or "🔥" in msj:
            _logger.error(msj)
        elif "⚠" in msj or "WARNING" in msj:
            _logger.warning(msj)
        else:
            _logger.info(msj)

    def seleccionar_archivo(self):
        ruta = filedialog.askopenfilename(
            filetypes=[("Archivos de datos", "*.xlsx *.xls *.csv *.txt")]
        )
        if ruta:
            self.archivo_ruta = ruta
            nombre = Path(ruta).name
            # Validar keyword si hay modo seleccionado
            aviso = ""
            if self.modo:
                kw = ROBOT_KEYWORDS.get(self.modo, ["?"])[0]
                if not InputManager.validar_nombre(nombre, self.modo):
                    aviso = f"  ⚠ El nombre no contiene '{kw}'"
            self.lbl_archivo.configure(
                text=f"📄  {nombre}{aviso}",
                text_color="#f59e0b" if aviso else "#1d4ed8"
            )
            self.log(f"📂 Archivo manual: {nombre}{aviso}")
            if self.modo:
                self.btn_run.configure(state="normal")

    def exportar_debug_log(self):
        contenido = self.log_txt.get("1.0", "end")
        ruta = str(BASE_DIR / f"debug_report_{time.strftime('%Y%m%d_%H%M%S')}.txt")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(f"REPORTE RPA Suite v5 — {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n{contenido}")
        os.startfile(ruta)
        self.log(f"📋 Log exportado: {ruta}")


    def abrir_settings(self):
        """Panel de configuración — edita el .env desde la GUI sin salir de la app."""
        env_path = BASE_DIR / ".env"
        env_content = ""
        if env_path.exists():
            try:
                env_content = env_path.read_text(encoding="utf-8")
            except Exception:
                pass

        popup = ctk.CTkToplevel(self)
        popup.title("Configuracion — .env")
        popup.geometry("560x480")
        popup.resizable(True, True)
        popup.grab_set(); popup.lift(); popup.focus_force()

        ctk.CTkLabel(popup, text="Configuracion del sistema",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#1E293B").pack(pady=(16,2), padx=20, anchor="w")
        ctk.CTkLabel(popup, text=f"Archivo: {env_path}",
                     font=ctk.CTkFont(size=10), text_color="#94A3B8").pack(padx=20, anchor="w")
        ctk.CTkLabel(popup, text="No compartás este archivo — contiene credenciales.",
                     font=ctk.CTkFont(size=10), text_color="#f59e0b").pack(padx=20, pady=(2,8), anchor="w")

        editor = ctk.CTkTextbox(popup, font=("Consolas", 11), fg_color="#F8FAFC",
                                text_color="#1E293B", border_width=1, border_color="#CBD5E1", wrap="none")
        editor.pack(fill="both", expand=True, padx=16, pady=(0,8))
        editor.insert("1.0", env_content)

        ctk.CTkFrame(popup, height=1, fg_color="#E2E8F0").pack(fill="x")
        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(pady=8)

        def _guardar():
            nuevo = editor.get("1.0", "end").rstrip("\n")
            try:
                env_path.write_text(nuevo + "\n", encoding="utf-8")
                self.log("Settings: .env guardado. Reinicia la app para aplicar cambios.")
                popup.destroy()
            except Exception as e:
                self.log(f"Error guardando .env: {e}")

        ctk.CTkButton(btn_row, text="Guardar", width=130, height=34,
                      fg_color="#0057A8", hover_color="#004A8F", text_color="white",
                      corner_radius=6, command=_guardar).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cancelar", width=90, height=34,
                      fg_color="#6B7280", hover_color="#4B5563", text_color="white",
                      corner_radius=6, command=popup.destroy).pack(side="left", padx=6)
        popup.bind("<Escape>", lambda e: popup.destroy())

    def abrir_carpeta_procesados(self):
        """Abre el explorador en la carpeta /procesados/ y muestra resumen en el log."""
        procesados_path = BASE_DIR / "procesados"
        procesados_path.mkdir(exist_ok=True)
        os.startfile(str(procesados_path))

        # Mostrar resumen en log
        historial = obtener_historial(ultimos_n=10)
        if historial:
            self.log("─" * 50)
            self.log("📁 Últimos 10 archivos procesados:")
            for h in reversed(historial):
                estado = "✅"
                self.log(
                    f"  {estado} [{h['robot']}] {h['archivo_origen']} "
                    f"({h['filas_procesadas']} filas) — {h['timestamp'][:16]}"
                )
            self.log("─" * 50)
        else:
            self.log("📁 No hay archivos procesados aún.")

    # =========================================================
    # EJECUCIÓN
    # =========================================================
    def preparar_ejecucion(self):
        """Carga archivos, valida, muestra popup de confirmación y ejecuta."""
        if not self.modo:
            self.log("⚠ Seleccioná un módulo primero.")
            return

        # Determinar fuente de archivos
        archivos_input = InputManager.buscar_archivos(self.modo, base_dir=BASE_DIR)
        if archivos_input:
            pares_raw = list(InputManager.cargar_todos(self.modo, base_dir=BASE_DIR, log_func=self.log))
        elif self.archivo_ruta:
            df = InputManager.cargar_df(Path(self.archivo_ruta), self.log)
            pares_raw = [(Path(self.archivo_ruta), df)] if df is not None else []
        else:
            self.log("❌ Sin archivos para procesar.")
            return

        if not pares_raw:
            self.log("❌ No se pudo cargar ningún archivo.")
            return

        # ── Auto-split para archivos grandes de STOCK ──────────
        if self.modo == "STOCK":
            from core.input_manager import split_en_lotes
            LIMITE_FILAS = 200
            pares_expandidos = []
            for ruta, df in pares_raw:
                if len(df) > LIMITE_FILAS:
                    self.log(f"  ✂ {ruta.name} tiene {len(df)} filas — dividiendo en lotes de {LIMITE_FILAS}...")
                    lotes = split_en_lotes(df, LIMITE_FILAS, self.log)
                    for j, lote in enumerate(lotes, 1):
                        # Crear ruta virtual para identificar cada lote
                        from pathlib import Path as _P
                        ruta_lote = _P(str(ruta).replace(ruta.suffix, f"_lote{j}{ruta.suffix}"))
                        pares_expandidos.append((ruta_lote, lote))
                    self.log(f"  ✅ {len(lotes)} lotes listos para procesar secuencialmente")
                else:
                    pares_expandidos.append((ruta, df))
            pares_raw = pares_expandidos

        # Correr validaciones pre-ejecución
        from core.pre_validador import cargar_snapshot_precios
        snap_anterior = cargar_snapshot_precios() if self.modo == "PRECIOS" else None

        validaciones = []
        for ruta, df in pares_raw:
            kwargs = {}
            if self.modo == "PRECIOS" and snap_anterior:
                import pandas as _pd
                snap_df = _pd.DataFrame([
                    {"sku": k, "p_salon": v["p_salon"], "costo": v["costo"]}
                    for k, v in snap_anterior.items()
                ])
                kwargs["snapshot_anterior"] = snap_df if not snap_df.empty else None
            v = validar_por_modo(self.modo, df, str(ruta), **kwargs)
            validaciones.append((ruta, df, v))

        # Mostrar popup de confirmación
        self._mostrar_popup_confirmacion(validaciones)

    def _mostrar_popup_confirmacion(self, validaciones: list):
        """Popup con preview de datos y validaciones. Confirmar → ejecutar."""
        SB_BG    = "#1D2D3E"
        SB_TEXT  = "#C8D6E5"
        ACENT    = "#0057A8"
        ERROR_C  = "#ef4444"
        WARN_C   = "#f59e0b"
        OK_C     = "#22c55e"

        popup = ctk.CTkToplevel(self)
        popup.title(f"Confirmar ejecución — {self.modo}")
        popup.geometry("780x560")
        popup.resizable(True, True)
        popup.grab_set()
        popup.lift()
        popup.focus_force()

        hay_errores_criticos = any(v.errores and not v.ok for _, _, v in validaciones)

        # Título
        ctk.CTkLabel(
            popup,
            text=f"📋  Revisión pre-ejecución — {self.modo}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#1E293B"
        ).pack(pady=(16, 4), padx=20, anchor="w")

        ctk.CTkLabel(
            popup,
            text=f"{len(validaciones)} archivo(s) en cola",
            font=ctk.CTkFont(size=11),
            text_color="#64748B"
        ).pack(padx=20, anchor="w")

        ctk.CTkFrame(popup, height=1, fg_color="#E2E8F0").pack(fill="x", padx=0, pady=8)

        # Scrollable para las validaciones
        scroll = ctk.CTkScrollableFrame(popup, fg_color="#F8FAFC", corner_radius=6)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        for ruta, df, v in validaciones:
            # Card por archivo
            card = ctk.CTkFrame(scroll, fg_color="white", corner_radius=6,
                                border_width=1,
                                border_color=ERROR_C if v.errores else "#E2E8F0")
            card.pack(fill="x", padx=4, pady=4)

            # Header del card
            hdr = ctk.CTkFrame(card, fg_color="#F1F5F9", corner_radius=0)
            hdr.pack(fill="x")
            icono = "❌" if v.errores else ("⚠️" if v.advertencias else "✅")
            ctk.CTkLabel(
                hdr,
                text=f"{icono}  {ruta.name}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#1E293B"
            ).pack(side="left", padx=10, pady=6)

            # Resumen
            ctk.CTkLabel(
                card,
                text=v.resumen,
                font=ctk.CTkFont(size=11),
                text_color="#334155"
            ).pack(anchor="w", padx=12, pady=(4, 0))

            # Detalles
            for d in v.detalles:
                ctk.CTkLabel(card, text=f"  ✅ {d}",
                             font=ctk.CTkFont(size=10), text_color=OK_C
                             ).pack(anchor="w", padx=12)
            for w in v.advertencias:
                ctk.CTkLabel(card, text=f"  ⚠  {w}",
                             font=ctk.CTkFont(size=10), text_color=WARN_C
                             ).pack(anchor="w", padx=12)
            for e in v.errores:
                ctk.CTkLabel(card, text=f"  ❌ {e}",
                             font=ctk.CTkFont(size=10), text_color=ERROR_C
                             ).pack(anchor="w", padx=12)

            # Mini tabla preview
            if v.preview_filas:
                tabla_frame = ctk.CTkFrame(card, fg_color="#F8FAFC", corner_radius=4)
                tabla_frame.pack(fill="x", padx=12, pady=(4, 8))
                cols = list(v.preview_filas[0].keys())
                # Headers
                hrow = ctk.CTkFrame(tabla_frame, fg_color="#E2E8F0", corner_radius=0)
                hrow.pack(fill="x")
                for col in cols:
                    ctk.CTkLabel(hrow, text=col,
                                 font=ctk.CTkFont(size=9, weight="bold"),
                                 text_color="#475569", width=100
                                 ).pack(side="left", padx=6, pady=2)
                # Filas
                for fila in v.preview_filas:
                    frow = ctk.CTkFrame(tabla_frame, fg_color="transparent", corner_radius=0)
                    frow.pack(fill="x")
                    for col in cols:
                        ctk.CTkLabel(frow, text=str(fila.get(col, ""))[:18],
                                     font=ctk.CTkFont(size=9),
                                     text_color="#334155", width=100
                                     ).pack(side="left", padx=6, pady=1)
                ctk.CTkLabel(tabla_frame,
                             text=f"  ... primeras {len(v.preview_filas)} filas",
                             font=ctk.CTkFont(size=9), text_color="#94A3B8"
                             ).pack(anchor="w", padx=6, pady=2)

        # Footer con botones
        ctk.CTkFrame(popup, height=1, fg_color="#E2E8F0").pack(fill="x")
        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(pady=10)

        confirmar_estado = "disabled" if hay_errores_criticos else "normal"

        def _confirmar():
            popup.destroy()
            self.btn_run.configure(state="disabled", text="⏳ EJECUTANDO...")
            pares = [(r, d) for r, d, _ in validaciones]
            self.run_in_background(self.run_robot, pares)

        def _cancelar():
            popup.destroy()
            self.log("🚫 Ejecución cancelada por el usuario.")

        if hay_errores_criticos:
            ctk.CTkLabel(
                btn_row,
                text="⚠ Hay errores críticos — corregí el archivo antes de ejecutar",
                font=ctk.CTkFont(size=10), text_color=ERROR_C
            ).pack(pady=(0, 6))

        ctk.CTkButton(
            btn_row, text="▶  CONFIRMAR Y EJECUTAR",
            width=200, height=36,
            fg_color=ACENT, hover_color="#004A8F",
            text_color="white", corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
            state=confirmar_estado,
            command=_confirmar
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="Cancelar",
            width=100, height=36,
            fg_color="#6B7280", hover_color="#4B5563",
            text_color="white", corner_radius=6,
            command=_cancelar
        ).pack(side="left", padx=8)

        popup.bind("<Escape>", lambda e: _cancelar())

    def run_robot(self, pares: list = None):
        """Ejecuta los robots para la lista de (ruta, df) pares."""
        if self.modo not in ("PRECIOS_PARAMIKO", "STOCK_PARAMIKO", "AJUSTE_PARAMIKO"):
            if not enfocar_putty():
                self.log("❌ ERROR: PuTTY no detectado. Abrí PuTTY antes de ejecutar.")
                self.btn_run.configure(state="normal", text="▶  EJECUTAR PROCESO")
                return

        self._robot_corriendo = True
        total_filas_procesadas = 0

        try:
            forzar_caps_off()
            velocidad = round(0.05 / max(0.1, self.velocidad_var.get()), 3)

            if not pares:
                self.log("❌ Sin pares de archivos para ejecutar.")
                return

            total_pares = len(pares)
            self.log(f"{'─'*50}")

            for idx, (ruta, df) in enumerate(pares, 1):
                self.log(f"\n📋 [{idx}/{total_pares}] Procesando: {ruta.name}")
                self.log(f"{'─'*50}")

                kwargs_comunes = dict(
                    df=df,
                    total_filas=len(df),
                    log_func=self.log,
                    progress_func=lambda x: None,
                    velocidad=velocidad,
                    archivo_origen=str(ruta),
                )

                if self.modo in ("STOCK", "STOCK_PARAMIKO"):
                    if self.modo == "STOCK":
                        ejecutar_stock(**kwargs_comunes)
                        origen_db = "Robot_Putty"
                    else:
                        from robots.Stock_Paramiko import ejecutar_stock_paramiko
                        ejecutar_stock_paramiko(df=df, log_func=self.log,
                                                progress_func=lambda x: None, archivo_origen=str(ruta))
                        origen_db = "Stock_Paramiko"
                    
                    # Guardar los registros procesados en SQLite
                    try:
                        from core.database import execute_query
                        from core.pre_validador import _limpiar_sku, _to_float
                        
                        insertados = 0
                        for _, fila_df in df.iterrows():
                            sku = _limpiar_sku(fila_df.iloc[0])
                            if not sku or sku.lower() in ("none", "nan", ""):
                                continue
                            cant = _to_float(fila_df.iloc[1]) if len(fila_df) > 1 else None
                            if cant is not None:
                                execute_query(
                                    "INSERT INTO cargas_stock (sku, cantidad_cargada, robot_origen) VALUES (?, ?, ?)",
                                    params=(sku, cant, f"{origen_db} ({ruta.name})"),
                                    is_commit=True
                                )
                                insertados += 1
                        self.log(f"   💾 SQLite: {insertados} registros guardados en 'cargas_stock'")
                    except Exception as e_db:
                        self.log(f"   ⚠️ SQLite: Error guardando historial: {e_db}")
                        
                elif self.modo == "FACTURA":
                    from robots.robot_facturacion import ejecutar_facturacion
                    ejecutar_facturacion(**kwargs_comunes)
                elif self.modo == "PRECIOS":
                    ejecutar_precios_v2(df, len(df), self.log, lambda x: None,
                                        velocidad, archivo_origen=str(ruta))
                    # Guardar snapshot para comparación en la próxima carga
                    guardar_snapshot_precios(df, str(ruta))
                    self.log("   💾 Snapshot de precios guardado para comparación futura")
                elif self.modo == "PRECIOS_PARAMIKO":
                    from robots.Precios_Paramiko import ejecutar_precios_paramiko
                    ejecutar_precios_paramiko(df=df, log_func=self.log,
                                              progress_func=lambda x: None,
                                              archivo_origen=str(ruta))
                    # Guardar snapshot para comparación en la próxima carga
                    guardar_snapshot_precios(df, str(ruta))
                    self.log("   💾 Snapshot de precios guardado para comparación futura")
                    
                    # Guardar los registros procesados en SQLite
                    try:
                        from core.database import execute_query
                        from core.pre_validador import _limpiar_sku, _to_float
                        
                        # Saltar cabecera para no insertarla en la base de datos
                        tiene_cabecera = False
                        if len(df) > 0 and not str(df.iloc[0, 0]).strip().isdigit():
                            tiene_cabecera = True
                        df_db = df.iloc[3:] if tiene_cabecera else df
                        
                        insertados = 0
                        for _, fila_df in df_db.iterrows():
                            sku = _limpiar_sku(fila_df.iloc[0])
                            if not sku or sku.lower() in ("none", "nan", ""):
                                continue
                            
                            costo = _to_float(fila_df.iloc[1]) if len(fila_df) > 1 else None
                            p_salon = _to_float(fila_df.iloc[2]) if len(fila_df) > 2 else None
                            p_may = _to_float(fila_df.iloc[3]) if len(fila_df) > 3 else None
                            p_galpon = _to_float(fila_df.iloc[4]) if len(fila_df) > 4 else None
                            
                            execute_query(
                                "INSERT INTO historial_precios_propios (sku, costo, precio_salon, precio_mayorista, precio_galpon, robot_origen) VALUES (?, ?, ?, ?, ?, ?)",
                                params=(sku, costo, p_salon, p_may, p_galpon, f"Precios_Paramiko ({ruta.name})"),
                                is_commit=True
                            )
                            insertados += 1
                        self.log(f"   💾 SQLite: {insertados} registros guardados en 'historial_precios_propios'")
                    except Exception as e_db:
                        self.log(f"   ⚠️ SQLite: Error guardando historial de precios: {e_db}")
                elif self.modo == "AJUSTE":
                    ejecutar_ajuste(**kwargs_comunes)
                elif self.modo == "AJUSTE_PARAMIKO":
                    from robots.Ajuste_Paramiko import ejecutar_ajuste_paramiko
                    ejecutar_ajuste_paramiko(df=df, log_func=self.log,
                                             progress_func=lambda x: None, archivo_origen=str(ruta))
                elif self.modo == "AJUSTE_ANALITICO":
                    ejecutar_ajuste_analitico(**kwargs_comunes)
                elif self.modo == "CHEQUES":
                    ejecutar_cheques(df=df, log_func=self.log,
                                     progress_func=lambda x: None,
                                     archivo_origen=str(ruta))

                total_filas_procesadas += len(df)
                self.log(f"✅ [{idx}/{total_pares}] {ruta.name} — OK")

            self.log(f"{'─'*50}")
            self.log(f"🏁 {self.modo} completado — {total_pares} archivo(s), {total_filas_procesadas} filas")

            # Notificación de escritorio si está minimizada
            notificar_exito(self.modo, total_pares, total_filas_procesadas, tk_root=self)

        except Exception:
            self.log(f"🔥 ERROR CRÍTICO:\n{traceback.format_exc()}")
            notificar_error(self.modo, "Error crítico — revisá el log.", tk_root=self)

        finally:
            self._robot_corriendo = False
            self.btn_run.configure(state="normal", text="▶  EJECUTAR PROCESO")

    # =========================================================
    # HERRAMIENTAS
    # =========================================================
    def lanzar_descarga_ssh(self):
        """Abre popup para ingresar el mail destino y lanza el robot SSH."""
        from robots.robot_ssh_report import ejecutar_descarga_reporte
        try:
            from config import get_ssh_config
            default_mail = get_ssh_config().default_email
        except Exception:
            default_mail = ""
        popup = ctk.CTkToplevel(self)
        popup.title("📥 Descargar Lista de Precios")
        popup.geometry("420x200")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()
        ctk.CTkLabel(popup, text="📥  Descargar Lista de Precios",
                     font=ctk.CTkFont(size=14, weight="bold"), text_color="#1A1D23").pack(pady=(18,4))
        ctk.CTkLabel(popup, text="Ingresá el email al que se enviará el listado:",
                     font=ctk.CTkFont(size=11), text_color="#556B82").pack()
        entry = ctk.CTkEntry(popup, width=300, placeholder_text="correo@ejemplo.com",
                             fg_color="#F5F6F7", border_color="#D1D5DB", font=ctk.CTkFont(size=12))
        entry.pack(pady=(10,0))
        if default_mail: entry.insert(0, default_mail)
        entry.focus()
        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(pady=14)
        def _confirmar():
            mail = entry.get().strip()
            if not mail or "@" not in mail:
                ctk.CTkLabel(popup, text="⚠ Ingresá un email válido.",
                             text_color="#BB0000", font=ctk.CTkFont(size=11)).pack(); return
            popup.destroy()
            self.log(f"📥 Iniciando descarga → {mail}")
            def tarea():
                ejecutar_descarga_reporte(email_destino=mail, log_func=self.log)
            self.run_in_background(tarea)
        ctk.CTkButton(btn_row, text="▶  Iniciar robot", width=140, height=34,
                      fg_color="#0057A8", hover_color="#003D7A",
                      command=_confirmar).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cancelar", width=90, height=34,
                      fg_color="#6B7280", hover_color="#4B5563",
                      command=popup.destroy).pack(side="left", padx=6)
        popup.bind("<Return>", lambda e: _confirmar())
        popup.bind("<Escape>", lambda e: popup.destroy())

    def lanzar_analitica(self):
        csv_sis = filedialog.askopenfilename(
            title="1. CSV del SISTEMA", filetypes=[("CSV", "*.csv")]
        )
        if not csv_sis:
            return
        excel_cnt = filedialog.askopenfilename(
            title="2. Excel de CONTEO", filetypes=[("Excel", "*.xlsx")]
        )
        if not excel_cnt:
            return

        def tarea():
            archivo = procesar_analitica_conteo(csv_sis, excel_cnt, self.log)
            if archivo:
                os.startfile(archivo)
                messagebox.showinfo("Auditoría", "Informe generado con éxito.")

        self.run_in_background(tarea)

    def lanzar_etl_precios(self):
        """
        Abre un diálogo para seleccionar el CSV/TSV de PuTTY,
        ejecuta el ETL de precios y abre el Excel resultante.
        """
        ruta = filedialog.askopenfilename(
            title="Seleccioná el archivo de Lista de Precios (CSV o TSV)",
            filetypes=[
                ("Archivos de texto", "*.csv *.tsv *.txt"),
                ("Todos los archivos", "*.*"),
            ]
        )
        if not ruta:
            return

        self.log(f"🧾 ETL de Precios iniciado: {Path(ruta).name}")

        def tarea():
            try:
                ruta_excel = procesar_lista_precios_mbf(ruta, self.log)
                if ruta_excel:
                    self.log(f"📂 Abriendo Excel generado...")
                    os.startfile(ruta_excel)
                    messagebox.showinfo(
                        "ETL Completado",
                        f"Lista de precios procesada con éxito.\n\nArchivo generado:\n{Path(ruta_excel).name}"
                    )
                else:
                    messagebox.showerror(
                        "ETL Fallido",
                        "No se pudo procesar el archivo.\nRevisá el log para más detalles."
                    )
            except Exception as e:
                self.log(f"❌ Error en ETL de Precios: {e}")

        self.run_in_background(tarea)

    def lanzar_normalizador(self):
        """
        Normaliza descripciones de artículos con Gemini IA.
        Formato resultante: Marca + Producto + Variante + Contenido
        """
        ruta = filedialog.askopenfilename(
            title="Seleccioná el CSV de artículos (lpcio_mbf_*.csv)",
            filetypes=[
                ("Archivos de texto", "*.csv *.tsv *.txt"),
                ("Todos los archivos", "*.*"),
            ]
        )
        if not ruta:
            return

        # Preguntar si forzar reproceso
        forzar = messagebox.askyesno(
            "Cache de normalización",
            "¿Forzar reproceso completo ignorando el cache?\n\n"
            "Elegí NO para procesar solo artículos nuevos (más rápido y económico).\n"
            "Elegí SÍ para renormalizar todo desde cero."
        )

        self.log(f"✨ Normalizador de Artículos iniciado")
        self.log(f"   Archivo: {Path(ruta).name}")
        if forzar:
            self.log("   ⚠ Modo: reproceso total (cache ignorado)")
        else:
            self.log("   ⚡ Modo: solo artículos nuevos (cache activo)")

        import threading as _th
        self._norm_stop_event = _th.Event()
        self._btn_norm_stop.configure(state="normal")
        self._btn_norm.configure(state="disabled")

        def tarea():
            try:
                ruta_excel = ejecutar_normalizador(
                    ruta_csv=ruta,
                    log_func=self.log,
                    forzar_reproceso=forzar,
                    stop_event=self._norm_stop_event,
                )
                if ruta_excel:
                    self.log(f"📂 Abriendo Excel de revisión...")
                    os.startfile(ruta_excel)
                    messagebox.showinfo(
                        "Normalización Completada",
                        f"Artículos normalizados con éxito.\n\n"
                        f"El Excel tiene 3 hojas:\n"
                        f"  • Normalizados — todos los artículos\n"
                        f"  • ⚠ Revisar — confianza baja (<70%)\n"
                        f"  • Estadísticas — resumen del proceso\n\n"
                        f"Archivo: {Path(ruta_excel).name}"
                    )
                else:
                    if not self._norm_stop_event.is_set():
                        messagebox.showerror(
                            "Error en Normalización",
                            "No se pudo completar la normalización.\n"
                            "Revisá el log para más detalles."
                        )
            except Exception as e:
                self.log(f"❌ Error en normalizador: {e}")
            finally:
                self._btn_norm_stop.configure(state="disabled")
                self._btn_norm.configure(state="normal")
                self._norm_stop_event = None

        self.run_in_background(tarea)

    def _lanzar_streamlit(self, path: str, puerto: int, titulo: str, proc_attr: str):
        """Helper genérico: levanta Streamlit y abre en WebView o navegador."""
        import shutil, socket, webbrowser

        def _esperar(host="localhost", timeout=30) -> bool:
            inicio = time.time()
            while time.time() - inicio < timeout:
                try:
                    with socket.create_connection((host, puerto), timeout=1):
                        return True
                except (ConnectionRefusedError, OSError):
                    time.sleep(0.5)
            return False

        def _lanzar():
            # Verificar que el archivo existe
            if not Path(path).exists():
                self.log(f"  ❌ Archivo no encontrado: {Path(path).name}")
                return

            # Si ya hay un proceso Streamlit previo para este dashboard, cerrarlo para liberar RAM
            proc_prev = getattr(self, proc_attr, None)
            if proc_prev and proc_prev.poll() is None:
                try:
                    self.log("  ⏹ Cerrando instancia previa de Streamlit...")
                    proc_prev.terminate()
                    proc_prev.wait(timeout=3)
                except Exception:
                    try:
                        proc_prev.kill()
                    except Exception:
                        pass

            exe = shutil.which("streamlit")
            if not exe:
                for n in ["streamlit.exe", "streamlit"]:
                    c = Path(sys.executable).parent / n
                    if c.exists():
                        exe = str(c); break
            cmd = (
                [exe, "run", path, "--server.headless", "true",
                 "--server.port", str(puerto), "--server.address", "0.0.0.0"]
                if exe else
                [sys.executable, "-m", "streamlit", "run", path,
                 "--server.headless", "true",
                 "--server.port", str(puerto), "--server.address", "0.0.0.0"]
            )
            try:
                cr = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                proc = subprocess.Popen(
                    cmd, creationflags=cr,
                    stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                )
                setattr(self, proc_attr, proc)
                self.log(f"  Ejecutable: {exe or 'python -m streamlit'}")
                self.log(f"  Puerto {puerto} — esperando servidor...")
                listo = _esperar(timeout=30)
                url = f"http://localhost:{puerto}"

                if not listo:
                    # Proceso terminó antes de tiempo — leer el error
                    if proc.poll() is not None:
                        try:
                            stderr_txt = proc.stderr.read(3000).decode(errors="replace")
                            errores = [l.strip() for l in stderr_txt.splitlines()
                                       if any(k in l for k in
                                              ["Error", "error", "No module", "ImportError",
                                               "ModuleNotFound", "Cannot", "cannot"])]
                            self.log(f"  ❌ {titulo} falló al arrancar:")
                            for e in errores[:6]:
                                self.log(f"     {e}")
                            if not errores and stderr_txt.strip():
                                self.log(f"     {stderr_txt.strip()[:200]}")
                        except Exception:
                            self.log(f"  ❌ {titulo} terminó inesperadamente")
                        return
                    else:
                        self.log(f"  ⚠ Timeout 30s — abriendo igual: {url}")

                if WEBVIEW_OK:
                    self.log(f"  Abriendo ventana nativa: {titulo}")
                    self.after(0, lambda u=url, t=titulo: self._abrir_webview(t, u))
                else:
                    webbrowser.open(url)
                    self.log(f"  ✅ Abierto en navegador: http://localhost:{puerto}")
            except Exception as e:
                self.log(f"  ❌ Error lanzando {titulo}: {e}")
                _logger.exception(f"Error lanzando {titulo}")

        self.run_in_background(_lanzar)

    def _abrir_webview(self, titulo: str, url: str):
        """
        Abre pywebview en el main thread.
        tkinter y pywebview no pueden compartir el main thread simultaneamente,
        por eso lanzamos webview en un thread separado con su propio loop.
        En Windows, pywebview usa EdgeChromium/MSHTML que no requiere main thread.
        """
        import webbrowser

        def _wv():
            try:
                _webview.create_window(
                    titulo, url,
                    width=1280, height=820,
                    resizable=True, on_top=False,
                )
                _webview.start(debug=False)
            except Exception as e:
                self.log(f"WebView error: {e} — abriendo en navegador...")
                webbrowser.open(url)

        # Thread NO daemon para que webview no muera con la GUI
        t = threading.Thread(target=_wv, daemon=False)
        t.start()

    def lanzar_portal_dashboards(self):
        """Lanza el portal unificado de Dashboards (Multipage App)."""
        self.log("🌐 Iniciando Portal Unificado de Dashboards...")
        self._lanzar_streamlit(
            path=str(BASE_DIR / "dashboards" / "main_app.py"),
            puerto=8501, titulo="RPA Suite — Portal Dashboards",
            proc_attr="_streamlit_proc",
        )


    def detener_normalizador(self):
        """Señala al normalizador que debe detenerse al terminar el lote actual."""
        if self._norm_stop_event:
            self._norm_stop_event.set()
            self._btn_norm_stop.configure(state="disabled")
            self.log("⏹ Señal de stop enviada — el proceso terminará al finalizar el lote actual.")

    def _actualizar_label_velocidad(self, val=None):
        """Actualiza el label del slider y escribe la velocidad en config global."""
        import config as _cfg
        v = round(self.velocidad_var.get(), 1)
        _cfg.ROBOT_SPEED = v

        if v <= 0.5:
            desc = "Muy seguro"
        elif v <= 0.8:
            desc = "Seguro"
        elif v <= 1.2:
            desc = "Normal"
        elif v <= 1.6:
            desc = "Rápido"
        else:
            desc = "Máximo"

        self._vel_valor_label.configure(text=f"Velocidad: x{v:.1f} — {desc}")


    def abrir_descarga_datos(self):
        from datetime import date
        try:
            from config import get_ssh_config
            default_mail = get_ssh_config().default_email
        except Exception:
            default_mail = ""
        hoy = date.today()
        popup = ctk.CTkToplevel(self)
        popup.title("⬇️ Descargar Datos para Dashboard")
        popup.geometry("500x520")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()

        ctk.CTkLabel(popup, text="⬇️  Descarga Automática de Datos",
                     font=ctk.CTkFont(size=14, weight="bold"), text_color="#1A1D23").pack(pady=(16,2))
        ctk.CTkLabel(popup, text="PuTTY debe estar abierto en el menú principal.",
                     font=ctk.CTkFont(size=10), text_color="#9AA0AD").pack(pady=(0,10))

        form = ctk.CTkFrame(popup, fg_color="#F5F6F7", corner_radius=10)
        form.pack(fill="x", padx=20, pady=(0,8))

        def _row(parent, label):
            r = ctk.CTkFrame(parent, fg_color="transparent"); r.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(r, text=label, width=130, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#374151").pack(side="left")
            return r

        meses_lista = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                       "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
        mes_var  = ctk.StringVar(value=meses_lista[hoy.month - 1])
        anio_var = ctk.StringVar(value=str(hoy.year))
        suc_var  = ctk.StringVar(value="01")
        mail_var = ctk.StringVar(value=default_mail)
        cli_var  = ctk.BooleanVar(value=False)

        r_mes = _row(form, "📅 Mes:")
        ctk.CTkOptionMenu(r_mes, values=meses_lista, variable=mes_var, width=180,
                          fg_color="#FFFFFF", button_color="#354A5E",
                          button_hover_color="#2C3F52").pack(side="left")
        r_anio = _row(form, "📆 Año:")
        ctk.CTkEntry(r_anio, textvariable=anio_var, width=90,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")
        r_suc = _row(form, "🏪 Sucursal:")
        ctk.CTkSegmentedButton(r_suc, values=["01","09","Ambas"],
                                variable=suc_var, width=220).pack(side="left")
        r_mail = _row(form, "📧 Mail stock:")
        ctk.CTkEntry(r_mail, textvariable=mail_var, width=240,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")
        r_cli = _row(form, "👥 Clientes:")
        ctk.CTkSwitch(r_cli, text="Incluir archivo de clientes",
                      variable=cli_var, onvalue=True, offvalue=False).pack(side="left")

        incr_var = ctk.BooleanVar(value=True)
        r_incr = _row(form, "⏭ Incremental:")
        ctk.CTkSwitch(r_incr, text="Saltar semanas ya descargadas",
                      variable=incr_var, onvalue=True, offvalue=False).pack(side="left")

        # Preview semanas
        pf = ctk.CTkFrame(popup, fg_color="#EFF6FF", corner_radius=8,
                           border_width=1, border_color="#BFDBFE")
        pf.pack(fill="x", padx=20, pady=(0,8))
        plbl = ctk.CTkLabel(pf, text="", font=ctk.CTkFont(family="Courier New", size=10),
                             text_color="#1E40AF", justify="left")
        plbl.pack(padx=12, pady=8, anchor="w")

        def _preview(*_):
            try:
                mn = meses_lista.index(mes_var.get()) + 1
                an = int(anio_var.get())
                semanas = calcular_semanas(mn, an)
                lines = [f"Semanas — {mes_var.get()} {an}:"]
                for i, (ini, fin) in enumerate(semanas, 1):
                    lines.append(f"  S{i}: {ini.strftime('%d/%m')} → {fin.strftime('%d/%m')}")
                suc = suc_var.get()
                n = 4 * (2 if suc == "Ambas" else 1)
                if cli_var.get(): n += (2 if suc == "Ambas" else 1)
                n += 1
                plbl.configure(text="\n".join(lines))
            except Exception:
                plbl.configure(text="Completá mes y año.")

        mes_var.trace_add("write", _preview); anio_var.trace_add("write", _preview)
        suc_var.trace_add("write", _preview); cli_var.trace_add("write", _preview)
        _preview()

        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(pady=10)

        def _iniciar():
            try:
                mn = meses_lista.index(mes_var.get()) + 1
                an = int(anio_var.get())
                mail = mail_var.get().strip()
                if not mail or "@" not in mail:
                    ctk.CTkLabel(popup, text="⚠ Mail inválido.",
                                 text_color="#BB0000", font=ctk.CTkFont(size=11)).pack(); return
                sucursales = ["01","09"] if suc_var.get() == "Ambas" else [suc_var.get()]
                popup.destroy()
                self.log(f"⬇️ Descarga {mes_var.get()} {an} — suc: {sucursales}")
                def _tarea():
                    ejecutar_descarga_dashboard(
                        mes=mn, anio=an, sucursales=sucursales,
                        email_stock=mail, incluir_clientes=cli_var.get(),
                        solo_semanas_nuevas=incr_var.get(),
                        log_func=self.log
                    )
                threading.Thread(target=_tarea, daemon=True).start()
            except Exception as ex:
                self.log(f"❌ Config error: {ex}")

        ctk.CTkButton(btn_row, text="▶  Iniciar robot", width=150, height=34,
                      fg_color="#1D3557", hover_color="#152742",
                      command=_iniciar).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cancelar", width=90, height=34,
                      fg_color="#6B7280", hover_color="#4B5563",
                      command=popup.destroy).pack(side="left", padx=6)
        popup.bind("<Return>", lambda e: _iniciar())
        popup.bind("<Escape>", lambda e: popup.destroy())



    def lanzar_pricing(self):
        """Lanza el dashboard de Pricing & Market Research en puerto 8504."""
        self.log("💰 Iniciando Pricing & Market Research...")
        self._lanzar_streamlit(
            path=str(BASE_DIR / "dashboards" / "pricing_dashboard.py"),
            puerto=8504, titulo="RPA Suite — Pricing Research",
            proc_attr="_streamlit_proc_pricing",
        )

    # ══════════════════════════════════════════════════════════
    # GIT — Commit y Push con 1 click
    # ══════════════════════════════════════════════════════════

    # ── Descarga SSH → local ──────────────────────────────────
    def abrir_descarga_ssh(self):
        """
        Popup MCANET — descarga *.csv del servidor via SFTP.
        Equivale al .bat:
          pscp -P 9229 mbf.andres@35.198.62.182:/home/asp/mbf/Intercambio/Public/*.csv
               C:\\Clientes\\mbf\\Intercambio\\Estadistica
        """
        from robots.robot_descarga_ssh import (
            RUTA_REMOTA_DEFAULT, EXTENSION_DEFAULT, DESTINO_WIN
        )

        popup = ctk.CTkToplevel(self)
        popup.title("↓ MCANET — Descargar desde Servidor")
        popup.geometry("540x520")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()

        # ── Título ───────────────────────────────────────────
        ctk.CTkLabel(popup, text="↓  MCANET — Descarga de Servidor",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#1A1D23").pack(pady=(16, 2))
        ctk.CTkLabel(popup,
                     text="Reemplaza el .bat de pscp — sin necesidad de PuTTY.",
                     font=ctk.CTkFont(size=10), text_color="#9AA0AD").pack(pady=(0, 8))

        # ── Formulario ───────────────────────────────────────
        form = ctk.CTkFrame(popup, fg_color="#F5F6F7", corner_radius=10)
        form.pack(fill="x", padx=20, pady=(0, 8))

        def _row(label):
            r = ctk.CTkFrame(form, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=5)
            ctk.CTkLabel(r, text=label, width=130, anchor="w",
                         font=ctk.CTkFont(size=11),
                         text_color="#374151").pack(side="left")
            return r

        # Leer SSH_HOST/PORT/USER del .env para mostrarlos como info
        try:
            from config import get_ssh_config
            _cfg  = get_ssh_config()
            _host = _cfg.host
            _port = _cfg.port
            _user = _cfg.user
            _pass_env = _cfg.password   # contraseña guardada en .env (si existe)
        except Exception:
            _host = "35.198.62.182"
            _port = 9229
            _user = "mbf.andres"
            _pass_env = ""

        # Info servidor (no editable)
        r_srv = _row("🖥  Servidor:")
        ctk.CTkLabel(r_srv,
                     text=f"{_user}@{_host}:{_port}",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#1D3557").pack(side="left")

        # Contraseña — campo editable, pre-cargado del .env
        r_pw = _row("🔑 Contraseña:")
        pw_var = ctk.StringVar(value=_pass_env)
        entry_pw = ctk.CTkEntry(r_pw, textvariable=pw_var, show="●",
                                width=200, fg_color="#FFFFFF",
                                border_color="#D1D5DB",
                                font=ctk.CTkFont(size=12))
        entry_pw.pack(side="left", padx=(0, 6))
        # Botón ver/ocultar contraseña
        ojo_var = ctk.BooleanVar(value=False)
        def _toggle_ojo():
            entry_pw.configure(show="" if ojo_var.get() else "●")
        ctk.CTkCheckBox(r_pw, text="Mostrar", variable=ojo_var,
                        command=_toggle_ojo,
                        font=ctk.CTkFont(size=10),
                        checkbox_width=16, checkbox_height=16).pack(side="left")

        # Ruta remota
        ruta_var = ctk.StringVar(value=RUTA_REMOTA_DEFAULT)
        r1 = _row("📁 Ruta remota:")
        ctk.CTkEntry(r1, textvariable=ruta_var, width=280,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")

        # Extensión
        ext_var = ctk.StringVar(value=EXTENSION_DEFAULT)
        r2 = _row("📄 Extensión:")
        ctk.CTkEntry(r2, textvariable=ext_var, width=80,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")

        # Destino local
        dest_var = ctk.StringVar(value=DESTINO_WIN)
        r3 = _row("💾 Destino local:")
        ctk.CTkEntry(r3, textvariable=dest_var, width=280,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")

        # Solo nuevos
        nuevo_var = ctk.BooleanVar(value=True)
        r4 = _row("⏭  Solo nuevos:")
        ctk.CTkSwitch(r4, text="Saltar archivos ya descargados",
                      variable=nuevo_var,
                      onvalue=True, offvalue=False).pack(side="left")

        # ── Log ──────────────────────────────────────────────
        log_frame = ctk.CTkTextbox(popup, height=140, fg_color="#1A1D23",
                                    text_color="#A3E635", font=("Consolas", 10))
        log_frame.pack(fill="x", padx=20, pady=(0, 8))

        def _log_popup(m):
            log_frame.configure(state="normal")
            log_frame.insert("end", m + "\n")
            log_frame.see("end")
            popup.update_idletasks()

        # ── Botones ──────────────────────────────────────────
        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(pady=6)

        def _iniciar():
            password = pw_var.get().strip()
            if not password:
                _log_popup("⚠  Ingresá la contraseña antes de descargar.")
                return
            btn_ok.configure(state="disabled", text="Descargando...")
            log_frame.delete("1.0", "end")

            def _tarea():
                try:
                    from robots.robot_descarga_ssh import sincronizar_procesados
                    archivos = sincronizar_procesados(
                        ruta_remota  = ruta_var.get().strip(),
                        extension    = ext_var.get().strip(),
                        destino_local= dest_var.get().strip(),
                        solo_nuevos  = nuevo_var.get(),
                        host         = _host,
                        port         = _port,
                        user         = _user,
                        password     = password,
                        log_func     = _log_popup,
                    )
                    self.log(f"↓ MCANET: {len(archivos)} archivo(s) descargado(s)")
                except Exception as e:
                    _log_popup(f"❌ {e}")
                    self.log(f"❌ Error descarga SSH: {e}")
                finally:
                    popup.after(0, lambda: btn_ok.configure(
                        state="normal", text="↓ Descargar"))

            threading.Thread(target=_tarea, daemon=True).start()

        btn_ok = ctk.CTkButton(btn_row, text="↓ Descargar", width=150, height=34,
                                fg_color="#1D3557", hover_color="#152742",
                                font=ctk.CTkFont(size=12, weight="bold"),
                                command=_iniciar)
        btn_ok.pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cerrar", width=90, height=34,
                      fg_color="#6B7280", hover_color="#4B5563",
                      command=popup.destroy).pack(side="left", padx=6)
        popup.bind("<Return>", lambda e: _iniciar())
        popup.bind("<Escape>",  lambda e: popup.destroy())

    # ── Validar CUITs AFIP ────────────────────────────────────
    def abrir_validar_cuits(self):
        """Abre el portal de AFIP para consultar CUITs."""
        import webbrowser
        url = "https://seti.afip.gob.ar/padron-puc-constancia-internet/ConsultaConstanciaAction.do"
        self.log(f"🌍 Abriendo portal de AFIP: {url}")
        webbrowser.open(url)

        # ── Modo programado ──────────────────────────────────────
    def _run_robot_auto(self, robot: str):
        """Callback que dispara el scheduler: selecciona modo y ejecuta."""
        self.log(f"⏰ Modo programado — iniciando {robot} automáticamente")
        self.modo = robot
        self.preparar_ejecucion()

    def abrir_modo_programado(self):
        """Popup de configuración del modo programado."""
        popup = ctk.CTkToplevel(self)
        popup.title("⏰ Modo Programado")
        popup.geometry("540x600")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()

        ctk.CTkLabel(popup, text="⏰  Modo Programado",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#1A1D23").pack(pady=(16,2))
        ctk.CTkLabel(popup, text="Ejecutar robots automáticamente a una hora fija.",
                     font=ctk.CTkFont(size=10), text_color="#9AA0AD").pack(pady=(0,10))

        ROBOTS    = ["STOCK", "STOCK_PARAMIKO", "PRECIOS", "PRECIOS_PARAMIKO", "AJUSTE", "AJUSTE_PARAMIKO", "CHEQUES"]
        DIAS_OPTS = ["lun","mar","mie","jue","vie","sab","dom"]

        form = ctk.CTkFrame(popup, fg_color="#F5F6F7", corner_radius=10)
        form.pack(fill="x", padx=20, pady=(0,8))

        def _row(lbl):
            r = ctk.CTkFrame(form, fg_color="transparent"); r.pack(fill="x", padx=14, pady=5)
            ctk.CTkLabel(r, text=lbl, width=130, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#374151").pack(side="left")
            return r

        robot_var = ctk.StringVar(value="STOCK")
        hora_var  = ctk.StringVar(value="08:00")
        dias_vars = {d: ctk.BooleanVar(value=(d in ["lun","mar","mie","jue","vie"])) for d in DIAS_OPTS}

        r1 = _row("🤖 Robot:")
        ctk.CTkOptionMenu(r1, values=ROBOTS, variable=robot_var, width=160,
                          fg_color="#FFFFFF", button_color="#354A5E").pack(side="left")
        r2 = _row("🕐 Hora (HH:MM):")
        ctk.CTkEntry(r2, textvariable=hora_var, width=90,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")
        r3 = _row("📅 Días:")
        for dia, var in dias_vars.items():
            ctk.CTkCheckBox(r3, text=dia, variable=var, width=55,
                            font=ctk.CTkFont(size=10)).pack(side="left")

        # Lista de tareas actuales
        ctk.CTkLabel(popup, text="Tareas programadas:",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#374151").pack(anchor="w", padx=20, pady=(8,2))
        lista_frame = ctk.CTkScrollableFrame(popup, height=100, fg_color="#F8FAFC")
        lista_frame.pack(fill="x", padx=20, pady=(0,6))

        def _refresh_lista():
            for w in lista_frame.winfo_children(): w.destroy()
            tareas = self._scheduler.listar_tareas()
            if not tareas:
                ctk.CTkLabel(lista_frame, text="Sin tareas programadas.",
                             font=ctk.CTkFont(size=10), text_color="#9AA0AD").pack(anchor="w")
                return
            for t in tareas:
                row = ctk.CTkFrame(lista_frame, fg_color="transparent")
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(row, text=f"⏰ {t.robot} — {t.hora} ({', '.join(t.dias)})",
                             font=ctk.CTkFont(size=10), text_color="#1A1D23").pack(side="left")
                ctk.CTkButton(row, text="✕", width=28, height=22,
                              fg_color="#EF4444", hover_color="#DC2626",
                              font=ctk.CTkFont(size=10),
                              command=lambda r=t.robot: (_eliminar(r))).pack(side="right", padx=4)

        def _eliminar(robot):
            self._scheduler.eliminar_tarea(robot)
            _refresh_lista()

        _refresh_lista()

        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(pady=8)

        def _agregar():
            hora = hora_var.get().strip()
            import re
            if not re.match(r'^\d{2}:\d{2}$', hora):
                self.log("⚠ Hora inválida — usá formato HH:MM"); return
            dias = [d for d, v in dias_vars.items() if v.get()]
            if not dias:
                self.log("⚠ Seleccioná al menos un día"); return
            self._scheduler.agregar_tarea(robot_var.get(), hora, dias)
            if not self._scheduler._running:
                self._scheduler.iniciar()
            self.log(f"✅ Tarea programada: {robot_var.get()} a las {hora}")
            _refresh_lista()

        ctk.CTkButton(btn_row, text="➕ Agregar tarea", width=150, height=34,
                      fg_color="#1D3557", hover_color="#152742",
                      command=_agregar).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cerrar", width=90, height=34,
                      fg_color="#6B7280", hover_color="#4B5563",
                      command=popup.destroy).pack(side="left", padx=6)
        popup.bind("<Escape>", lambda e: popup.destroy())

    # ── Auto-update desde GitHub ──────────────────────────────
    def git_pull_update(self):
        """git pull origin main + notifica si hubo cambios."""
        import subprocess as _sp

        popup = ctk.CTkToplevel(self)
        popup.title("↓ Actualizar desde GitHub")
        popup.geometry("460x220")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()

        ctk.CTkLabel(popup, text="↓  Actualizar desde GitHub",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#1A1D23").pack(pady=(16,8))

        log_pull = ctk.CTkTextbox(popup, height=100, fg_color="#1A1D23",
                                   text_color="#A3E635", font=("Consolas", 10))
        log_pull.pack(fill="x", padx=16, pady=(0,8))

        def _log(msg):
            log_pull.insert("end", msg + "\n")
            log_pull.see("end")
            popup.update()

        def _pull():
            btn_pull.configure(state="disabled", text="Actualizando...")
            def _tarea():
                try:
                    repo = str(BASE_DIR)
                    _log("git fetch origin...")
                    r = _sp.run(["git", "fetch", "origin"],
                                cwd=repo, capture_output=True, text=True, timeout=30)
                    if r.returncode != 0:
                        _log(f"❌ {r.stderr.strip()}"); return

                    _log("git pull origin main...")
                    r = _sp.run(["git", "pull", "origin", "main"],
                                cwd=repo, capture_output=True, text=True, timeout=30)
                    salida = r.stdout.strip()
                    _log(salida or "Sin cambios nuevos.")
                    if "Already up to date" in salida or salida == "":
                        self.log("↓ GitHub: sin cambios nuevos.")
                    else:
                        self.log(f"↓ GitHub actualizado:\n{salida}")
                        self.log("⚠ Reiniciá la app para aplicar los cambios.")
                except Exception as e:
                    _log(f"❌ Error: {e}")
                finally:
                    btn_pull.configure(state="normal", text="↓ Actualizar")
            threading.Thread(target=_tarea, daemon=True).start()

        btn_pull = ctk.CTkButton(popup, text="↓ Actualizar", width=160, height=34,
                                  fg_color="#1D3557", hover_color="#152742",
                                  command=_pull)
        btn_pull.pack(pady=4)
        popup.bind("<Return>", lambda e: _pull())
        popup.bind("<Escape>", lambda e: popup.destroy())
        _pull()   # ejecutar automáticamente al abrir

    def git_commit_push(self):
        """
        Guardar en GitHub — versión segura v5.9.
        Detecta si el repo está configurado y ofrece configurarlo si no.
        Nunca sube .env ni .env.enc al repo.
        """
        import subprocess as _sp
        from core.seguridad import git_commit_push_seguro, asegurar_gitignore

        # Verificar si es un repo Git ANTES de abrir el popup
        r = _sp.run(["git", "rev-parse", "--is-inside-work-tree"],
                    cwd=str(BASE_DIR), capture_output=True, text=True)
        es_repo = r.returncode == 0

        r2 = _sp.run(["git", "remote", "get-url", "origin"],
                     cwd=str(BASE_DIR), capture_output=True, text=True)
        tiene_remote = r2.returncode == 0

        if not es_repo or not tiene_remote:
            # Redirigir al popup de configuración
            self._popup_configurar_git()
            return

        popup = ctk.CTkToplevel(self)
        popup.title("Guardar en GitHub")
        popup.geometry("500x320")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()

        ctk.CTkLabel(popup, text="⬆  Guardar en GitHub",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#1A1D23").pack(pady=(16, 4))

        remote_url = r2.stdout.strip()
        ctk.CTkLabel(popup, text=f"Remote: {remote_url[:60]}",
                     font=ctk.CTkFont(size=10), text_color="#6B7280").pack()

        ctk.CTkLabel(popup, text="Mensaje del commit:",
                     font=ctk.CTkFont(size=11), text_color="#556B82").pack(pady=(10,2))

        ts    = time.strftime("%Y-%m-%d %H:%M")
        entry = ctk.CTkEntry(popup, width=420, fg_color="#F5F6F7",
                             border_color="#D1D5DB", font=ctk.CTkFont(size=12))
        entry.pack(pady=(0, 6))
        entry.insert(0, f"actualizacion {ts}")
        entry.focus()

        log_git = ctk.CTkTextbox(popup, height=100, fg_color="#1A1D23",
                                  text_color="#A3E635", font=("Consolas", 10))
        log_git.pack(fill="x", padx=16, pady=(4, 8))

        def _log(msg):
            log_git.insert("end", msg + "\n")
            log_git.see("end"); popup.update()

        def _ejecutar():
            btn_ok.configure(state="disabled", text="Guardando...")
            msg = entry.get().strip() or f"actualizacion {ts}"
            def _tarea():
                try:
                    asegurar_gitignore(_log)
                    ok = git_commit_push_seguro(msg, log_func=_log)
                    if ok:
                        self.log(f"✅ GitHub actualizado: {msg}")
                        popup.after(2500, popup.destroy)
                except FileNotFoundError:
                    _log("❌ Git no encontrado — instalá Git para Windows")
                    _log("   https://git-scm.com/download/win")
                except Exception as ex:
                    _log(f"❌ Error: {ex}")
                finally:
                    popup.after(0, lambda: btn_ok.configure(state="normal", text="Guardar"))
            threading.Thread(target=_tarea, daemon=True).start()

        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack()
        btn_ok = ctk.CTkButton(btn_row, text="Guardar", width=140, height=34,
                               fg_color="#24292e", hover_color="#1a1f24",
                               command=_ejecutar)
        btn_ok.pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cancelar", width=90, height=34,
                      fg_color="#6B7280", hover_color="#4B5563",
                      command=popup.destroy).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="⚙ Config Git", width=110, height=34,
                      fg_color="#2563EB", hover_color="#1D4ED8",
                      command=lambda: [popup.destroy(), self._popup_configurar_git()]
                      ).pack(side="left", padx=6)
        popup.bind("<Return>", lambda e: _ejecutar())
        popup.bind("<Escape>",  lambda e: popup.destroy())

    def _popup_configurar_git(self):
        """Popup para configurar Git desde cero si no está inicializado."""
        from core.seguridad import configurar_git_repositorio, asegurar_gitignore

        popup = ctk.CTkToplevel(self)
        popup.title("Configurar Git")
        popup.geometry("540x600")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()

        ctk.CTkLabel(popup, text="⚙  Configurar repositorio Git",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#1A1D23").pack(pady=(16, 4))
        ctk.CTkLabel(popup,
                     text="Necesitás configurar Git una sola vez para poder guardar en GitHub.",
                     font=ctk.CTkFont(size=11), text_color="#6B7280",
                     wraplength=460).pack(pady=(0,12))

        def _campo(label, placeholder, default=""):
            ctk.CTkLabel(popup, text=label, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#374151").pack(anchor="w", padx=24)
            e = ctk.CTkEntry(popup, width=460, fg_color="#F5F6F7",
                             border_color="#D1D5DB", placeholder_text=placeholder)
            e.pack(pady=(2,8), padx=24)
            if default:
                e.insert(0, default)
            return e

        e_remote = _campo("URL del repositorio GitHub:",
                          "https://github.com/aadbalbas1987-ship-it/Suite-v6.git",
                          "https://github.com/aadbalbas1987-ship-it/Suite-v6.git")
        e_name   = _campo("Tu nombre (para los commits):", "Andres Bianfra", "Andres")
        e_email  = _campo("Tu email GitHub:", "tu@email.com",
                          "aadbalbas1987@gmail.com")

        # Token GitHub (opcional) — si no usás Git Credential Manager.
        ctk.CTkLabel(popup, text="Token GitHub (PAT) — opcional:",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#374151").pack(anchor="w", padx=24)
        token_row = ctk.CTkFrame(popup, fg_color="transparent")
        token_row.pack(fill="x", padx=24, pady=(2, 8))
        token_var = ctk.StringVar(value="")
        e_token = ctk.CTkEntry(token_row, width=360, fg_color="#F5F6F7",
                               border_color="#D1D5DB", placeholder_text="ghp_... (no se guarda)",
                               textvariable=token_var, show="●")
        e_token.pack(side="left")
        mostrar_var = ctk.BooleanVar(value=False)
        def _toggle_token():
            e_token.configure(show="" if mostrar_var.get() else "●")
        ctk.CTkCheckBox(token_row, text="Mostrar", variable=mostrar_var,
                        command=_toggle_token,
                        font=ctk.CTkFont(size=10),
                        checkbox_width=16, checkbox_height=16).pack(side="left", padx=10)

        log_cfg = ctk.CTkTextbox(popup, height=110, fg_color="#1A1D23",
                                  text_color="#A3E635", font=("Consolas", 10))
        log_cfg.pack(fill="x", padx=16, pady=(4, 8))

        def _log(m):
            log_cfg.insert("end", m + "\n"); log_cfg.see("end"); popup.update()

        def _configurar():
            btn.configure(state="disabled", text="Configurando...")
            remote = e_remote.get().strip()
            token  = e_token.get().strip()
            name   = e_name.get().strip()
            email  = e_email.get().strip()
            if not remote or not name or not email:
                _log("❌ Completá todos los campos"); btn.configure(state="normal", text="Configurar"); return
            # Incrustar token en la URL si fue provisto
            # https://TOKEN@github.com/usuario/repo.git
            remote_con_token = remote
            if token and "github.com" in remote and "@" not in remote:
                remote_con_token = remote.replace(
                    "https://", f"https://{token}@"
                )
            def _tarea():
                try:
                    ok = configurar_git_repositorio(
                        remote_url=remote_con_token, user_name=name,
                        user_email=email, log_func=_log,
                    )
                    if ok:
                        _log("\n✅ Git configurado. Ya podés usar 'Guardar en GitHub'.")
                        self.log("✅ Git configurado correctamente")
                        popup.after(3000, popup.destroy)
                except FileNotFoundError:
                    _log("❌ Git no instalado — descargá en https://git-scm.com/download/win")
                except Exception as ex:
                    _log(f"❌ Error: {ex}")
                finally:
                    popup.after(0, lambda: btn.configure(state="normal", text="Configurar"))
            threading.Thread(target=_tarea, daemon=True).start()

        btn_row = ctk.CTkFrame(popup, fg_color="transparent"); btn_row.pack()
        btn = ctk.CTkButton(btn_row, text="Configurar", width=150, height=34,
                            fg_color="#16A34A", hover_color="#15803D",
                            command=_configurar)
        btn.pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cancelar", width=90, height=34,
                      fg_color="#6B7280", hover_color="#4B5563",
                      command=popup.destroy).pack(side="left", padx=6)

    def abrir_robot_uxb(self):
        """
        Abre el Robot UXB:
          - Parte 1: uxb_robot.html en el navegador (IA busca UXB correcto, revisás y exportás)
          - Parte 2: popup para correr uxb_putty_robot.py con el archivo exportado
        """
        import subprocess
        import webbrowser

        popup = ctk.CTkToplevel(self)
        popup.title("Robot UXB")
        popup.geometry("520x560")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()

        ctk.CTkLabel(popup, text="◈ Robot UXB — Corrector Inteligente",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#1A1D23").pack(pady=(16, 2))
        ctk.CTkLabel(popup,
                     text="Dos pasos: la IA corrige los UXB, luego el robot los carga en PuTTY.",
                     font=ctk.CTkFont(size=10), text_color="#9AA0AD").pack(pady=(0, 10))

        # ── PASO 1 ──
        f1 = ctk.CTkFrame(popup, fg_color="#EFF6FF", corner_radius=10,
                           border_width=1, border_color="#BFDBFE")
        f1.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(f1, text="PASO 1 — App Web (IA busca UXB)",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#1E40AF").pack(anchor="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(f1,
                     text="1. Cargá tu archivo uxb_arreglo.txt\n"
                          "2. La IA busca el UXB correcto para cada producto\n"
                          "3. Revisás, editás y aprobás\n"
                          "4. Exportás el archivo uxb_aprobados_XXXX.txt",
                     font=ctk.CTkFont(size=10), text_color="#374151",
                     justify="left").pack(anchor="w", padx=14, pady=(0, 6))

        def _abrir_html():
            ruta = Path(BASE_DIR) / "tools" / "uxb_robot.html"
            if ruta.exists():
                webbrowser.open(f"file:///{ruta.as_posix()}")
                self.log("Robot UXB: app web abierta en navegador")
            else:
                import tkinter.messagebox as mb
                mb.showerror("No encontrado",
                             f"No se encontró uxb_robot.html en:\n{ruta}")

        ctk.CTkButton(f1, text="🌐 Abrir App Web (Parte 1)", width=220, height=32,
                      fg_color="#1D4ED8", hover_color="#1E40AF",
                      command=_abrir_html).pack(pady=(0, 10))

        # ── PASO 2 ──
        f2 = ctk.CTkFrame(popup, fg_color="#F0FDF4", corner_radius=10,
                           border_width=1, border_color="#BBF7D0")
        f2.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(f2, text="PASO 2 — Cargar en PuTTY",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#15803D").pack(anchor="w", padx=14, pady=(10, 2))

        r_file = ctk.CTkFrame(f2, fg_color="transparent")
        r_file.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(r_file, text="Archivo exportado:", width=130, anchor="w",
                     font=ctk.CTkFont(size=10), text_color="#374151").pack(side="left")
        file_var = ctk.StringVar(value="")
        file_entry = ctk.CTkEntry(r_file, textvariable=file_var, width=210,
                                   fg_color="#FFFFFF", border_color="#D1D5DB")
        file_entry.pack(side="left", padx=(0, 6))

        def _browse():
            from tkinter import filedialog
            p = filedialog.askopenfilename(
                title="Seleccionar archivo exportado",
                filetypes=[("TXT exportado", "*.txt"), ("Todos", "*.*")]
            )
            if p: file_var.set(p)
        ctk.CTkButton(r_file, text="...", width=36, height=28,
                      fg_color="#E2E8F0", hover_color="#CBD5E1",
                      text_color="#374151", command=_browse).pack(side="left")

        r_delay = ctk.CTkFrame(f2, fg_color="transparent")
        r_delay.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(r_delay, text="Delay (segundos):", width=130, anchor="w",
                     font=ctk.CTkFont(size=10), text_color="#374151").pack(side="left")
        delay_var = ctk.StringVar(value="0.5")
        ctk.CTkEntry(r_delay, textvariable=delay_var, width=60,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")
        ctk.CTkLabel(r_delay, text="  (0.3 rápido / 0.8 seguro)",
                     font=ctk.CTkFont(size=9), text_color="#9CA3AF").pack(side="left")

        r_desde = ctk.CTkFrame(f2, fg_color="transparent")
        r_desde.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(r_desde, text="Empezar desde:", width=130, anchor="w",
                     font=ctk.CTkFont(size=10), text_color="#374151").pack(side="left")
        desde_var = ctk.StringVar(value="1")
        ctk.CTkEntry(r_desde, textvariable=desde_var, width=60,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")
        ctk.CTkLabel(r_desde, text="  (útil si se interrumpió)",
                     font=ctk.CTkFont(size=9), text_color="#9CA3AF").pack(side="left")

        dry_var = ctk.BooleanVar(value=False)
        r_dry = ctk.CTkFrame(f2, fg_color="transparent")
        r_dry.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(r_dry, text="Dry-run:", width=130, anchor="w",
                     font=ctk.CTkFont(size=10), text_color="#374151").pack(side="left")
        ctk.CTkSwitch(r_dry, text="Simular sin tocar PuTTY",
                      variable=dry_var, onvalue=True, offvalue=False).pack(side="left")

        # Log
        log_box = ctk.CTkTextbox(popup, height=120, fg_color="#1A1D23",
                                  text_color="#A3E635", font=("Consolas", 10))
        log_box.pack(fill="x", padx=20, pady=(0, 8))

        def _log(m):
            log_box.configure(state="normal")
            log_box.insert("end", m + "\n")
            log_box.see("end")
            popup.update_idletasks()

        aviso = ctk.CTkLabel(popup,
                              text="ANTES DE CARGAR: PuTTY abierto en menú 3-3-2",
                              font=ctk.CTkFont(size=10, weight="bold"),
                              text_color="#B45309")
        aviso.pack(pady=(0, 4))

        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(pady=4)

        def _correr_putty():
            ruta = file_var.get().strip()
            if not ruta or not Path(ruta).exists():
                _log("Seleccioná el archivo exportado primero.")
                return
            if not dry_var.get():
                import tkinter.messagebox as mb
                if not mb.askyesno(
                    "Confirmar",
                    "PuTTY debe estar en menú 3-3-2.\n"
                    "El robot arranca en 5 segundos.\n¿Confirmar?"
                ):
                    return

            btn_putty.configure(state="disabled", text="Cargando...")
            log_box.delete("1.0", "end")

            def _tarea():
                try:
                    robot_path = Path(BASE_DIR) / "robots" / "robot_uxb.py"
                    cmd = [
                        sys.executable, str(robot_path),
                        "--file", ruta,
                        "--delay", delay_var.get() or "0.5",
                        "--start", desde_var.get() or "1",
                    ]
                    if dry_var.get():
                        cmd.append("--dry-run")
                    _log(f"Ejecutando: {' '.join(cmd)}")
                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace"
                    )
                    for line in proc.stdout:
                        _log(line.rstrip())
                    proc.wait()
                    _log(f"\nProceso finalizado (código {proc.returncode})")
                    self.log(f"Robot UXB: proceso finalizado")
                except Exception as e:
                    _log(f"Error: {e}")
                finally:
                    popup.after(0, lambda: btn_putty.configure(
                        state="normal", text="▶ Cargar en PuTTY"))

            self.run_in_background(_tarea)

        ctk.CTkButton(btn_row, text="🌐 Abrir App Web", width=140, height=34,
                      fg_color="#1D4ED8", hover_color="#1E40AF",
                      command=_abrir_html).pack(side="left", padx=6)

        btn_putty = ctk.CTkButton(btn_row, text="▶ Cargar en PuTTY", width=150, height=34,
                                   fg_color="#16A34A", hover_color="#15803D",
                                   command=_correr_putty)
        btn_putty.pack(side="left", padx=6)

        ctk.CTkButton(btn_row, text="Cerrar", width=80, height=34,
                      fg_color="#6B7280", hover_color="#4B5563",
                      command=popup.destroy).pack(side="left", padx=6)

        popup.bind("<Escape>", lambda e: popup.destroy())

    def abrir_robot_articulos(self):
        """
        Popup robot de carga masiva de articulos via PuTTY.
        Lee Excel, asigna categori con IA, carga en menu 3-3-2.
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Alta Masiva de Artículos")
        popup.geometry("580x680")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()

        ctk.CTkLabel(popup, text="+ Alta Masiva de Artículos",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#1A1D23").pack(pady=(16, 2))
        ctk.CTkLabel(popup,
                     text="Lee el Excel, asigna categorias con IA y carga en PuTTY (menú 3-3-2).",
                     font=ctk.CTkFont(size=10), text_color="#9AA0AD").pack(pady=(0, 8))

        form = ctk.CTkFrame(popup, fg_color="#F5F6F7", corner_radius=10)
        form.pack(fill="x", padx=20, pady=(0, 8))

        def _row(label, pady=5):
            r = ctk.CTkFrame(form, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=pady)
            ctk.CTkLabel(r, text=label, width=150, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#374151").pack(side="left")
            return r

        # Excel path
        excel_var = ctk.StringVar(value="")
        r_excel = _row("Excel de articulos:")
        excel_entry = ctk.CTkEntry(r_excel, textvariable=excel_var, width=240,
                                    fg_color="#FFFFFF", border_color="#D1D5DB")
        excel_entry.pack(side="left", padx=(0, 6))

        def _browse_excel():
            from tkinter import filedialog
            p = filedialog.askopenfilename(
                title="Seleccionar Excel de articulos",
                filetypes=[("Excel", "*.xlsx *.xls"), ("Todos", "*.*")]
            )
            if p:
                excel_var.set(p)
        ctk.CTkButton(r_excel, text="...", width=36, height=28,
                      fg_color="#E2E8F0", hover_color="#CBD5E1",
                      text_color="#374151",
                      command=_browse_excel).pack(side="left")

        # Encabezados
        enc_var = ctk.BooleanVar(value=True)
        r_enc = _row("Tiene encabezados:")
        ctk.CTkSwitch(r_enc, text="Sí (saltar primera fila)",
                      variable=enc_var, onvalue=True, offvalue=False).pack(side="left")

        # Categori.txt
        cat_var = ctk.StringVar(value=str(Path(BASE_DIR) / "Categori.txt"))
        r_cat = _row("Categori.txt:")
        cat_entry = ctk.CTkEntry(r_cat, textvariable=cat_var, width=240,
                                  fg_color="#FFFFFF", border_color="#D1D5DB")
        cat_entry.pack(side="left", padx=(0, 6))
        def _browse_cat():
            from tkinter import filedialog
            p = filedialog.askopenfilename(
                title="Seleccionar Categori.txt",
                filetypes=[("Texto", "*.txt"), ("Todos", "*.*")]
            )
            if p: cat_var.set(p)
        ctk.CTkButton(r_cat, text="...", width=36, height=28,
                      fg_color="#E2E8F0", hover_color="#CBD5E1",
                      text_color="#374151",
                      command=_browse_cat).pack(side="left")

        # Delay
        delay_var = ctk.StringVar(value="0.4")
        r_delay = _row("Delay (segundos):")
        ctk.CTkEntry(r_delay, textvariable=delay_var, width=70,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")
        ctk.CTkLabel(r_delay, text="  (0.3 rápido / 0.5 seguro)",
                     font=ctk.CTkFont(size=9), text_color="#9CA3AF").pack(side="left")

        # Desde / Limite
        r_desde = _row("Empezar desde fila:")
        desde_var = ctk.StringVar(value="1")
        ctk.CTkEntry(r_desde, textvariable=desde_var, width=60,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")

        r_lim = _row("Límite de artículos:")
        lim_var = ctk.StringVar(value="")
        ctk.CTkEntry(r_lim, textvariable=lim_var, width=60,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")
        ctk.CTkLabel(r_lim, text="  (vacío = todos)",
                     font=ctk.CTkFont(size=9), text_color="#9CA3AF").pack(side="left")

        # Dry run
        dry_var = ctk.BooleanVar(value=False)
        r_dry = _row("Dry-run:")
        ctk.CTkSwitch(r_dry, text="Simular sin tocar PuTTY",
                      variable=dry_var, onvalue=True, offvalue=False).pack(side="left")

        # Log
        log_box = ctk.CTkTextbox(popup, height=200, fg_color="#1A1D23",
                                  text_color="#A3E635", font=("Consolas", 10))
        log_box.pack(fill="x", padx=20, pady=(0, 8))

        def _log(m):
            log_box.configure(state="normal")
            log_box.insert("end", m + "\n")
            log_box.see("end")
            popup.update_idletasks()

        # Aviso PuTTY
        aviso = ctk.CTkLabel(popup,
                              text="ANTES DE CARGAR: PuTTY debe estar abierto en menú 3-3-2",
                              font=ctk.CTkFont(size=10, weight="bold"),
                              text_color="#B45309")
        aviso.pack(pady=(0, 4))

        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(pady=4)

        def _previsualizar():
            ruta = excel_var.get().strip()
            if not ruta or not Path(ruta).exists():
                _log("Seleccioná el Excel primero.")
                return
            btn_prev.configure(state="disabled", text="Analizando...")
            log_box.delete("1.0", "end")

            def _tarea():
                try:
                    from robots.robot_articulos import leer_excel_articulos, asignar_categoris
                    arts = leer_excel_articulos(ruta, enc_var.get())
                    _log(f"Excel: {len(arts)} articulo(s) encontrado(s)")
                    arts = asignar_categoris(arts, cat_var.get().strip() or None, _log)
                    _log("\nPREVISUALIZACION:")
                    ok = sum(1 for a in arts if a["familia"])
                    _log(f"  Con categoria asignada: {ok}/{len(arts)}")
                    for a in arts[:10]:
                        conf = "✅" if a["familia"] else "❌"
                        _log(f"  {conf} {a['sku']} | {a['descripcion'][:30]} | "
                             f"FAM={a['familia']} DPT={a['dpto']} "
                             f"SEC={a['seccion']} GRP={a['grupo']}")
                    if len(arts) > 10:
                        _log(f"  ... y {len(arts)-10} más")
                except Exception as e:
                    _log(f"Error: {e}")
                finally:
                    popup.after(0, lambda: btn_prev.configure(
                        state="normal", text="Vista previa"))

            threading.Thread(target=_tarea, daemon=True).start()

        def _iniciar():
            ruta = excel_var.get().strip()
            if not ruta or not Path(ruta).exists():
                _log("Seleccioná el Excel primero.")
                return
            if not dry_var.get():
                import tkinter.messagebox as mb
                if not mb.askyesno(
                    "Confirmar carga",
                    "PuTTY debe estar abierto en menú 3-3-2.\n"
                    "El robot comenzará en 5 segundos.\n\n"
                    "¿Confirmar carga en PuTTY?"
                ):
                    return
            btn_ok.configure(state="disabled", text="Cargando...")
            log_box.delete("1.0", "end")

            try:
                delay = float(delay_var.get() or "0.4")
            except ValueError:
                delay = 0.4
            try:
                desde = int(desde_var.get() or "1")
            except ValueError:
                desde = 1
            try:
                limite = int(lim_var.get()) if lim_var.get().strip() else None
            except ValueError:
                limite = None

            def _tarea():
                try:
                    if not dry_var.get():
                        _log("Arrancando en 5 segundos — enfocá PuTTY ahora...")
                        for i in range(5, 0, -1):
                            _log(f"  {i}...")
                            time.sleep(1)
                    from robots.robot_articulos import ejecutar_carga_articulos
                    res = ejecutar_carga_articulos(
                        ruta_excel       = ruta,
                        tiene_encabezados= enc_var.get(),
                        ruta_categori    = cat_var.get().strip() or None,
                        delay            = delay,
                        dry_run          = dry_var.get(),
                        start_desde      = desde,
                        limite           = limite,
                        log_func         = _log,
                    )
                    self.log(f"Alta articulos: {res['ok']} OK | "
                             f"{res['errores']} errores | {res['saltados']} saltados")
                except Exception as e:
                    _log(f"Error: {e}")
                    self.log(f"Error robot articulos: {e}")
                finally:
                    popup.after(0, lambda: btn_ok.configure(
                        state="normal", text="Cargar en PuTTY"))

            self.run_in_background(_tarea)

        btn_prev = ctk.CTkButton(btn_row, text="Vista previa", width=130, height=34,
                                  fg_color="#7C3AED", hover_color="#6D28D9",
                                  command=_previsualizar)
        btn_prev.pack(side="left", padx=6)

        btn_ok = ctk.CTkButton(btn_row, text="Cargar en PuTTY", width=150, height=34,
                                fg_color="#16A34A", hover_color="#15803D",
                                command=_iniciar)
        btn_ok.pack(side="left", padx=6)

        ctk.CTkButton(btn_row, text="Cancelar", width=90, height=34,
                      fg_color="#6B7280", hover_color="#4B5563",
                      command=popup.destroy).pack(side="left", padx=6)

        popup.bind("<Escape>", lambda e: popup.destroy())

    def abrir_compartir_dashboard(self):
        """
        Popup para compartir dashboards via:
          - Red local  (misma WiFi) — siempre disponible
          - Ngrok      (internet)   — requiere ngrok instalado
        Muestra IP local, link ngrok y QR escaneable.
        """
        import socket
        import subprocess as _sp

        popup = ctk.CTkToplevel(self)
        popup.title("Compartir Dashboard")
        popup.geometry("560x600")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()

        ctk.CTkLabel(popup, text="\U0001f4f1  Compartir Dashboard",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#1A1D23").pack(pady=(16, 2))
        ctk.CTkLabel(popup,
                     text="Compartir por red local (WiFi) o por internet (ngrok).",
                     font=ctk.CTkFont(size=10), text_color="#9AA0AD").pack(pady=(0, 8))

        dashboards = [
            ("Business Intelligence",  8501),
            ("Quiebres de Stock",       8502),
            ("Pricing Intelligence",    8506),
            ("Conciliacion Bancaria",   8507),
            ("Normalizador Maestro",    8508),
        ]
        nombres = [d[0] for d in dashboards]

        sel_frame = ctk.CTkFrame(popup, fg_color="#F5F6F7", corner_radius=10)
        sel_frame.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(sel_frame, text="Dashboard a compartir:",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#374151").pack(anchor="w", padx=14, pady=(10, 2))
        dash_var = ctk.StringVar(value=nombres[0])
        ctk.CTkOptionMenu(sel_frame, variable=dash_var, values=nombres,
                          width=300, font=ctk.CTkFont(size=11)).pack(
                              anchor="w", padx=14, pady=(0, 10))

        def _get_puerto():
            return next((p for n, p in dashboards if n == dash_var.get()), 8501)

        def _get_ip_local():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]; s.close(); return ip
            except Exception:
                return "127.0.0.1"

        ip_local = _get_ip_local()

        # Panel red local
        local_frame = ctk.CTkFrame(popup, fg_color="#EFF6FF", corner_radius=10,
                                    border_width=1, border_color="#BFDBFE")
        local_frame.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(local_frame, text="Red local (misma WiFi)",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#1D4ED8").pack(anchor="w", padx=14, pady=(8, 2))
        lbl_local = ctk.CTkLabel(local_frame,
                                  text=f"http://{ip_local}:{_get_puerto()}",
                                  font=ctk.CTkFont(size=12, weight="bold"),
                                  text_color="#1E3A5F")
        lbl_local.pack(anchor="w", padx=14)
        ctk.CTkLabel(local_frame,
                     text="Enviar por WhatsApp — funciona solo en la misma red WiFi.",
                     font=ctk.CTkFont(size=9), text_color="#6B7280").pack(
                         anchor="w", padx=14, pady=(0, 4))

        def _actualizar_local(*_):
            lbl_local.configure(text=f"http://{ip_local}:{_get_puerto()}")
        dash_var.trace_add("write", _actualizar_local)

        def _copiar_local():
            url = f"http://{ip_local}:{_get_puerto()}"
            popup.clipboard_clear(); popup.clipboard_append(url)
            lbl_local.configure(text=url + "  (copiado)")
        ctk.CTkButton(local_frame, text="Copiar link", width=110, height=26,
                      fg_color="#1D4ED8", hover_color="#1E40AF",
                      command=_copiar_local).pack(anchor="w", padx=14, pady=(4, 10))

        # Panel ngrok
        ngrok_frame = ctk.CTkFrame(popup, fg_color="#F0FDF4", corner_radius=10,
                                    border_width=1, border_color="#BBF7D0")
        ngrok_frame.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(ngrok_frame, text="Internet (ngrok) — cualquier celular",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#065F46").pack(anchor="w", padx=14, pady=(8, 2))
        lbl_ngrok = ctk.CTkLabel(ngrok_frame,
                                  text="Presiona Generar link para crear el tunel",
                                  font=ctk.CTkFont(size=10), text_color="#6B7280")
        lbl_ngrok.pack(anchor="w", padx=14)
        qr_label = ctk.CTkLabel(ngrok_frame, text="", image=None)
        qr_label.pack(pady=4)

        _ngrok_proc = [None]

        def _iniciar_ngrok():
            puerto = _get_puerto()
            btn_ngrok.configure(state="disabled", text="Generando...")
            lbl_ngrok.configure(text="Iniciando tunel ngrok...")

            def _tarea():
                import shutil, json, time as _t
                import urllib.request

                ngrok_exe = shutil.which("ngrok")
                if not ngrok_exe:
                    rutas = [
                        "C:\\\\ngrok\\\\ngrok.exe",
                        "C:\\\\tools\\\\ngrok.exe",
                        str(Path.home() / "ngrok.exe"),
                    os.environ.get("NGROK_PATH", ""),
                        str(Path.home() / "Downloads" / "ngrok.exe"),
                    ]
                    for ruta in rutas:
                        if Path(ruta).exists():
                            ngrok_exe = ruta; break

                if not ngrok_exe:
                    popup.after(0, lambda: lbl_ngrok.configure(
                        text="ngrok no encontrado. Descargalo gratis en ngrok.com/download "
                             "y coloca ngrok.exe en C:\\ngrok\\"))
                    popup.after(0, lambda: btn_ngrok.configure(
                        state="normal", text="Generar link"))
                    return

                if _ngrok_proc[0]:
                    try: _ngrok_proc[0].terminate()
                    except Exception: pass

                try:
                    cr = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                    proc = _sp.Popen([ngrok_exe, "http", str(puerto)],
                                      creationflags=cr,
                                      stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                    _ngrok_proc[0] = proc
                    _t.sleep(2)

                    url_publica = None
                    for _ in range(10):
                        try:
                            req = urllib.request.urlopen(
                                "http://127.0.0.1:4040/api/tunnels", timeout=2)
                            data = json.loads(req.read())
                            for t in data.get("tunnels", []):
                                if "https" in t.get("public_url", ""):
                                    url_publica = t["public_url"]; break
                            if url_publica: break
                        except Exception:
                            _t.sleep(1)

                    if not url_publica:
                        popup.after(0, lambda: lbl_ngrok.configure(
                            text="Ngrok inicio. Abre http://127.0.0.1:4040 para ver la URL."))
                        popup.after(0, lambda: btn_ngrok.configure(
                            state="normal", text="Generar link"))
                        return

                    # Generar QR si qrcode esta instalado
                    try:
                        import qrcode, io as _io
                        from PIL import Image
                        qr = qrcode.QRCode(box_size=4, border=2)
                        qr.add_data(url_publica); qr.make(fit=True)
                        img = qr.make_image(fill_color="black", back_color="white")
                        buf = _io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
                        pil_img = Image.open(buf)
                        ctk_img = ctk.CTkImage(light_image=pil_img,
                                               dark_image=pil_img, size=(160, 160))
                        popup.after(0, lambda i=ctk_img: qr_label.configure(image=i))
                    except ImportError:
                        pass

                    def _set_ok(u=url_publica):
                        lbl_ngrok.configure(text=u + "  (copiado)")
                        popup.clipboard_clear(); popup.clipboard_append(u)
                        btn_ngrok.configure(state="normal", text="Generar nuevo link")
                    popup.after(0, _set_ok)
                    self.log(f"Compartir ngrok: {url_publica}")

                except Exception as e:
                    popup.after(0, lambda: lbl_ngrok.configure(
                        text=f"Error: {str(e)[:80]}"))
                    popup.after(0, lambda: btn_ngrok.configure(
                        state="normal", text="Generar link"))

            self.run_in_background(_tarea)

        btn_ngrok = ctk.CTkButton(ngrok_frame, text="Generar link",
                                   width=130, height=26,
                                   fg_color="#065F46", hover_color="#047857",
                                   command=_iniciar_ngrok)
        btn_ngrok.pack(anchor="w", padx=14, pady=(4, 4))
        ctk.CTkLabel(ngrok_frame,
                     text="Requiere ngrok.exe en PATH o en C:\\ngrok\\ — gratis en ngrok.com",
                     font=ctk.CTkFont(size=9), text_color="#9CA3AF").pack(
                         anchor="w", padx=14, pady=(0, 10))

        ctk.CTkLabel(popup,
                     text="El dashboard debe estar corriendo antes de compartirlo.",
                     font=ctk.CTkFont(size=9), text_color="#9CA3AF").pack(pady=(2, 2))

        def _on_close():
            if _ngrok_proc[0]:
                try: _ngrok_proc[0].terminate()
                except Exception: pass
            popup.destroy()

        ctk.CTkButton(popup, text="Cerrar", width=100, height=30,
                      fg_color="#6B7280", hover_color="#4B5563",
                      command=_on_close).pack(pady=(4, 12))
        popup.protocol("WM_DELETE_WINDOW", _on_close)
        popup.bind("<Escape>", lambda e: _on_close())

    def abrir_descarga_ventas(self):
        """Popup descarga de Ventas desde servidor MCANET."""
        self._popup_descarga_generica(
            titulo="Descargar Ventas",
            subtitulo="Descarga archivos de ventas semanales (CSV) del servidor.",
            destino_default="C:\\Clientes\\mbf\\Intercambio\\Estadistica",
            fn_sincronizar="ventas",
            color_btn="#1D4ED8",
        )

    def abrir_descarga_clientes(self):
        """Popup descarga de Clientes desde servidor MCANET."""
        self._popup_descarga_generica(
            titulo="Descargar Clientes",
            subtitulo="Descarga archivos de clientes (CSV) del servidor.",
            destino_default="C:\\Clientes\\mbf\\Intercambio\\Clientes",
            fn_sincronizar="clientes",
            color_btn="#065F46",
        )

    def _popup_descarga_generica(self, titulo, subtitulo, destino_default,
                                  fn_sincronizar, color_btn="#1D4ED8"):
        """Popup reutilizable para descarga SSH (Ventas o Clientes)."""
        popup = ctk.CTkToplevel(self)
        popup.title(titulo)
        popup.geometry("540x500")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()

        ctk.CTkLabel(popup, text=f"\u2193  {titulo}",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#1A1D23").pack(pady=(16, 2))
        ctk.CTkLabel(popup, text=subtitulo,
                     font=ctk.CTkFont(size=10), text_color="#9AA0AD").pack(pady=(0, 8))

        form = ctk.CTkFrame(popup, fg_color="#F5F6F7", corner_radius=10)
        form.pack(fill="x", padx=20, pady=(0, 8))

        def _row(label):
            r = ctk.CTkFrame(form, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=5)
            ctk.CTkLabel(r, text=label, width=130, anchor="w",
                         font=ctk.CTkFont(size=11),
                         text_color="#374151").pack(side="left")
            return r

        try:
            from config import get_ssh_config
            _cfg = get_ssh_config()
            _host, _port, _user, _pass_env = _cfg.host, _cfg.port, _cfg.user, _cfg.password
        except Exception:
            _host, _port, _user, _pass_env = "35.198.62.182", 9229, "mbf.andres", ""

        r_srv = _row("Servidor:")
        ctk.CTkLabel(r_srv, text=f"{_user}@{_host}:{_port}",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#1D3557").pack(side="left")

        r_pw = _row("Contrasena:")
        pw_var = ctk.StringVar(value=_pass_env)
        entry_pw = ctk.CTkEntry(r_pw, textvariable=pw_var, show="*",
                                width=200, fg_color="#FFFFFF",
                                border_color="#D1D5DB",
                                font=ctk.CTkFont(size=12))
        entry_pw.pack(side="left", padx=(0, 6))
        ojo_var = ctk.BooleanVar(value=False)
        def _toggle_ojo(ep=entry_pw, ov=ojo_var):
            ep.configure(show="" if ov.get() else "*")
        ctk.CTkCheckBox(r_pw, text="Mostrar", variable=ojo_var,
                        command=_toggle_ojo,
                        font=ctk.CTkFont(size=10),
                        checkbox_width=16, checkbox_height=16).pack(side="left")

        dest_var = ctk.StringVar(value=destino_default)
        r_dest = _row("Destino local:")
        ctk.CTkEntry(r_dest, textvariable=dest_var, width=280,
                     fg_color="#FFFFFF", border_color="#D1D5DB").pack(side="left")

        nuevo_var = ctk.BooleanVar(value=True)
        r_nv = _row("Solo nuevos:")
        ctk.CTkSwitch(r_nv, text="Saltar archivos ya descargados",
                      variable=nuevo_var, onvalue=True, offvalue=False).pack(side="left")

        log_frame = ctk.CTkTextbox(popup, height=150, fg_color="#1A1D23",
                                    text_color="#A3E635", font=("Consolas", 10))
        log_frame.pack(fill="x", padx=20, pady=(0, 8))

        def _log_popup(m):
            log_frame.configure(state="normal")
            log_frame.insert("end", m + "\n")
            log_frame.see("end")
            popup.update_idletasks()

        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(pady=6)

        def _iniciar(btn_ref=[None]):
            password = pw_var.get().strip()
            if not password:
                _log_popup("Ingresa la contrasena antes de descargar.")
                return
            if btn_ref[0]: btn_ref[0].configure(state="disabled", text="Descargando...")
            log_frame.delete("1.0", "end")
            _dest  = dest_var.get().strip()
            _nuevo = nuevo_var.get()
            _fn    = fn_sincronizar

            def _tarea():
                try:
                    if _fn == "ventas":
                        from robots.robot_descarga_ventas import descargar_ventas
                        archivos = descargar_ventas(
                            destino_local=_dest, solo_nuevos=_nuevo,
                            host=_host, port=_port, user=_user,
                            password=password, log_func=_log_popup)
                        tag = "Ventas"
                    else:
                        from robots.robot_descarga_clientes import descargar_clientes
                        archivos = descargar_clientes(
                            destino_local=_dest, solo_nuevos=_nuevo,
                            host=_host, port=_port, user=_user,
                            password=password, log_func=_log_popup)
                        tag = "Clientes"
                    self.log(f"MCANET {tag}: {len(archivos)} archivo(s)")
                except Exception as e:
                    _log_popup(f"Error: {e}")
                    self.log(f"Error descarga {_fn}: {e}")
                finally:
                    if btn_ref[0]:
                        popup.after(0, lambda: btn_ref[0].configure(
                            state="normal", text="Descargar"))

            self.run_in_background(_tarea)

        btn_ok = ctk.CTkButton(btn_row, text="Descargar", width=150, height=34,
                               fg_color=color_btn, hover_color="#1a3a5c",
                               command=_iniciar)
        btn_ok.pack(side="left", padx=6)
        _iniciar.__defaults__  # ensure closure works
        # pass btn ref via list trick
        btn_ok.configure(command=lambda b=btn_ok: _iniciar([b]) or _iniciar.__wrapped__ if False else _iniciar([b]))
        ctk.CTkButton(btn_row, text="Cancelar", width=90, height=34,
                      fg_color="#6B7280", hover_color="#4B5563",
                      command=popup.destroy).pack(side="left", padx=6)
        popup.bind("<Return>", lambda e: _iniciar([btn_ok]))
        popup.bind("<Escape>",  lambda e: popup.destroy())

    def abrir_panel_seguridad(self):

        """Panel de seguridad — cifrado .env, estado Git, auditoría."""
        from core.seguridad import (cifrar_env, descifrar_env, resumen_seguridad,
                                     asegurar_gitignore, verificar_integridad_env,
                                     registrar_acceso)

        popup = ctk.CTkToplevel(self)
        popup.title("🔐 Seguridad")
        popup.geometry("560x620")
        popup.resizable(False, False)
        popup.grab_set(); popup.lift(); popup.focus_force()

        ctk.CTkLabel(popup, text="🔐  Panel de Seguridad",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#1A1D23").pack(pady=(16, 2))
        ctk.CTkLabel(popup, text="AES-256-GCM · PBKDF2 · Integridad · Git seguro",
                     font=ctk.CTkFont(size=10), text_color="#6B7280").pack()

        # ── Estado ──────────────────────────────────────────
        frame_estado = ctk.CTkFrame(popup, fg_color="#F8FAFC",
                                     border_color="#E2E8F0", border_width=1,
                                     corner_radius=8)
        frame_estado.pack(fill="x", padx=20, pady=(12,6))

        lbl_estado = ctk.CTkLabel(frame_estado, text="Calculando...",
                                   font=ctk.CTkFont(size=11),
                                   text_color="#374151", justify="left")
        lbl_estado.pack(anchor="w", padx=14, pady=10)

        log_sec = ctk.CTkTextbox(popup, height=130, fg_color="#1A1D23",
                                  text_color="#A3E635", font=("Consolas", 9))
        log_sec.pack(fill="x", padx=16, pady=(0,6))

        def _log(m):
            log_sec.insert("end", m + "\n"); log_sec.see("end"); popup.update()

        def _actualizar_estado():
            estado = resumen_seguridad(_log)
            p      = estado["puntuacion"]
            color  = "#16A34A" if p >= 70 else "#D97706" if p >= 40 else "#DC2626"
            nivel  = "🟢 ALTO" if p >= 70 else "🟡 MEDIO" if p >= 40 else "🔴 BAJO"
            lineas = [
                f"Seguridad: {nivel} ({p}/100)",
                f"✅ .env cifrado (AES-256): {'Sí' if estado['env_enc_existe'] else 'No — usar Cifrar'}",
                f"✅ .gitignore protegido:   {'Sí' if estado['gitignore_ok'] else 'No — usar Proteger'}",
                f"✅ Integridad .env:        {'OK' if estado['env_integro'] else 'MODIFICADO sin cifrar'}",
                f"✅ Git configurado:        {'Sí' if estado['git_configurado'] else 'No'}",
                f"✅ cryptography instalada: {'Sí' if estado['crypto_disponible'] else 'No — pip install cryptography'}",
            ]
            lbl_estado.configure(text="\n".join(lineas), text_color=color)

        self.run_in_background(_actualizar_estado)

        # ── Cifrado .env ─────────────────────────────────────
        sep = ctk.CTkFrame(popup, height=1, fg_color="#E2E8F0"); sep.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(popup, text="Cifrado AES-256-GCM del .env",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#374151").pack(anchor="w", padx=20)

        frame_pass = ctk.CTkFrame(popup, fg_color="transparent"); frame_pass.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(frame_pass, text="Master password:", width=130,
                     font=ctk.CTkFont(size=11)).pack(side="left")
        entry_pass = ctk.CTkEntry(frame_pass, width=240, show="●",
                                   fg_color="#F5F6F7", border_color="#D1D5DB")
        entry_pass.pack(side="left", padx=6)

        def _cifrar():
            pw = entry_pass.get()
            if not pw:
                _log("❌ Ingresá una master password"); return
            _log("Cifrando .env con AES-256-GCM + PBKDF2...")
            registrar_acceso("CIFRAR_ENV", "usuario usó panel seguridad")
            def _t():
                ok = cifrar_env(pw, _log)
                if ok:
                    _log("✅ Guardá tu master password en lugar seguro")
                    popup.after(100, _actualizar_estado)
            self.run_in_background(_t)

        def _verificar_integridad():
            _log("Verificando integridad del .env...")
            ok = verificar_integridad_env(_log)
            _log("✅ Íntegro" if ok else "⚠️  Modificado desde último cifrado")

        def _proteger_gitignore():
            asegurar_gitignore(_log)
            popup.after(100, _actualizar_estado)

        btn_row2 = ctk.CTkFrame(popup, fg_color="transparent"); btn_row2.pack(fill="x", padx=20, pady=4)
        ctk.CTkButton(btn_row2, text="🔐 Cifrar .env", width=130, height=30,
                      fg_color="#1D3557", hover_color="#152744",
                      font=ctk.CTkFont(size=11), command=_cifrar).pack(side="left", padx=4)
        ctk.CTkButton(btn_row2, text="✅ Integridad", width=120, height=30,
                      fg_color="#059669", hover_color="#047857",
                      font=ctk.CTkFont(size=11), command=_verificar_integridad).pack(side="left", padx=4)
        ctk.CTkButton(btn_row2, text="🛡 .gitignore", width=120, height=30,
                      fg_color="#7C3AED", hover_color="#6D28D9",
                      font=ctk.CTkFont(size=11), command=_proteger_gitignore).pack(side="left", padx=4)

        # ── Info capas ────────────────────────────────────────
        sep2 = ctk.CTkFrame(popup, height=1, fg_color="#E2E8F0"); sep2.pack(fill="x", padx=20, pady=6)
        info = (
            "Capas de seguridad activas:\n"
            "  1. AES-256-GCM — cifrado simétrico del .env\n"
            "  2. PBKDF2-SHA256 100.000 iter — fuerza bruta inviable\n"
            "  3. .gitignore forzado — .env jamás sube a GitHub\n"
            "  4. Hash SHA-256 de integridad — detecta modificaciones\n"
            "  5. Verificación SSH previa (Paramiko) antes de abrir PuTTY\n"
            "  6. Log de auditoría en logs/seguridad_audit.log\n"
            "  7. Limpieza automática de portapapeles (30s)\n"
            "  8. Variables en memoria — no se loguean nunca"
        )
        ctk.CTkLabel(popup, text=info, font=ctk.CTkFont(size=10),
                     text_color="#4B5563", justify="left").pack(anchor="w", padx=20)

        ctk.CTkButton(popup, text="Cerrar", width=100, height=30,
                      fg_color="#6B7280", command=popup.destroy).pack(pady=10)

    # ══════════════════════════════════════════════════════════
    # CIERRE LIMPIO
    # ══════════════════════════════════════════════════════════

    def detener_dashboards(self):
        """Mata todos los procesos Streamlit abiertos al instante."""
        self.log("⏹ Deteniendo todos los dashboards activos...")
        cerrados = 0
        for attr in ["_streamlit_proc", "_streamlit_proc_quiebres", "_streamlit_proc_pricing",
                     "_streamlit_proc_pricing_intel", "_streamlit_proc_conciliacion",
                     "_streamlit_proc_normalizador", "_streamlit_proc_cxc"]:
            proc = getattr(self, attr, None)
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=1)
                    cerrados += 1
                except Exception:
                    try:
                        proc.kill()
                        cerrados += 1
                    except Exception:
                        pass
                setattr(self, attr, None)
        
        if cerrados > 0:
            self.log(f"✅ Se cerraron {cerrados} proceso(s) de Streamlit.")
        else:
            self.log("ℹ No había dashboards corriendo.")

    def on_closing(self):
        """Mata todos los procesos Streamlit al cerrar la GUI."""
        self.detener_dashboards()
        self.destroy()

if __name__ == "__main__":
    app = SuiteRPA()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()