"""
core/trazabilidad.py — RPA Suite v5.9
=======================================
Sistema de trazabilidad posicional ultra-detallado para robots PuTTY/Paramiko.

CONCEPTO:
  Cada robot declara su propio "mapa de pasos" — una secuencia de etapas
  con nombre, descripción y qué se espera ver en pantalla.
  El Trazador registra en qué etapa está el robot en CADA MOMENTO,
  con timestamp, duración y resultado.

  Así, cuando algo falla, sabés exactamente:
    - En qué etapa estaba
    - Cuánto tiempo llevaba en esa etapa
    - Qué estaba esperando ver
    - Qué pasó en los últimos N pasos

SALIDA:
  - Log en tiempo real en la GUI (color por nivel)
  - Archivo de sesión en logs/trazabilidad/YYYYMMDD_HHMMSS_ROBOT.jsonl
  - Reporte final al terminar (resumen + tabla de etapas)
"""

import json
import time
import threading
import traceback
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, List
from enum import Enum

_LOG_DIR = Path(__file__).parent.parent / "logs" / "trazabilidad"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

LogFunc = Optional[Callable[[str], None]]


class Estado(str, Enum):
    PENDIENTE  = "PENDIENTE"
    EN_CURSO   = "EN_CURSO"
    OK         = "OK"
    ERROR      = "ERROR"
    ADVERTENCIA= "ADVERTENCIA"
    SALTADO    = "SALTADO"


@dataclass
class Paso:
    id:            int
    nombre:        str
    descripcion:   str
    estado:        Estado      = Estado.PENDIENTE
    ts_inicio:     float       = 0.0
    ts_fin:        float       = 0.0
    duracion_seg:  float       = 0.0
    detalle:       str         = ""
    fila_actual:   int         = 0
    fila_total:    int         = 0
    sku_actual:    str         = ""
    captura:       str         = ""   # texto de pantalla si está disponible


@dataclass
class SesionTrazabilidad:
    robot:         str
    archivo:       str
    ts_inicio:     float      = field(default_factory=time.time)
    ts_fin:        float      = 0.0
    pasos:         List[Paso] = field(default_factory=list)
    paso_actual:   int        = -1
    total_filas:   int        = 0
    filas_ok:      int        = 0
    filas_error:   int        = 0
    dry_run:       bool       = False
    estado_global: Estado     = Estado.EN_CURSO
    log_path:      str        = ""


class Trazador:
    """
    Trazador posicional para robots RPA.

    Uso:
        t = Trazador("STOCK", "mi_archivo.xlsx", total_filas=200, log_func=self.log)
        t.iniciar()

        with t.etapa("LOGIN", "Ingresando usuario y clave en PuTTY"):
            # código de login
            pass

        with t.etapa("IMPRESORAS", "Seleccionando impresoras (Enter x4)"):
            # código de impresoras
            pass

        with t.etapa("FILA", f"SKU {sku}", fila=i, sku=sku):
            # código de carga
            pass

        t.finalizar()
    """

    def __init__(self,
                 robot: str,
                 archivo: str,
                 total_filas: int = 0,
                 dry_run: bool = False,
                 log_func: LogFunc = None):
        self.robot       = robot
        self.archivo     = archivo
        self.total_filas = total_filas
        self.dry_run     = dry_run
        self._log_func   = log_func
        self._lock       = threading.Lock()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = _LOG_DIR / f"{ts}_{robot}.jsonl"

        self.sesion = SesionTrazabilidad(
            robot=robot,
            archivo=str(archivo),
            total_filas=total_filas,
            dry_run=dry_run,
            log_path=str(log_path),
        )
        self._log_file = open(log_path, "a", encoding="utf-8")
        self._paso_counter = 0
        self._paso_activo: Optional[Paso] = None

    # ── Logging ────────────────────────────────────────────────

    def _log(self, msg: str, nivel: str = "INFO"):
        """Log a GUI + archivo."""
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        iconos = {
            "INFO":  "  ",
            "OK":    "✅",
            "ERROR": "❌",
            "WARN":  "⚠️",
            "PASO":  "▶",
            "POS":   "📍",
            "DATA":  "📊",
        }
        icono = iconos.get(nivel, "  ")
        linea = f"[{ts}] {icono} {msg}"
        if self._log_func:
            self._log_func(linea)
        # Escribir JSONL
        try:
            self._log_file.write(json.dumps({
                "ts": time.time(), "nivel": nivel, "msg": msg,
                "paso": self.sesion.paso_actual,
            }, ensure_ascii=False) + "\n")
            self._log_file.flush()
        except Exception:
            pass

    # ── API Principal ──────────────────────────────────────────

    def iniciar(self):
        modo = "[DRY-RUN]" if self.dry_run else "[REAL]"
        self._log(f"{'='*55}", "INFO")
        self._log(f"ROBOT: {self.robot} {modo}", "PASO")
        self._log(f"Archivo: {Path(self.archivo).name}", "DATA")
        self._log(f"Total filas: {self.total_filas}", "DATA")
        self._log(f"Log: {Path(self.sesion.log_path).name}", "DATA")
        self._log(f"{'='*55}", "INFO")

    def etapa(self,
              nombre: str,
              descripcion: str = "",
              fila: int = 0,
              sku: str = "",
              esperado: str = ""):
        """Context manager para una etapa del robot."""
        return _ContextoEtapa(self, nombre, descripcion, fila, sku, esperado)

    def _iniciar_etapa(self, nombre: str, descripcion: str,
                       fila: int, sku: str, esperado: str) -> Paso:
        with self._lock:
            self._paso_counter += 1
            paso = Paso(
                id=self._paso_counter,
                nombre=nombre,
                descripcion=descripcion,
                estado=Estado.EN_CURSO,
                ts_inicio=time.time(),
                fila_actual=fila,
                fila_total=self.total_filas,
                sku_actual=sku,
            )
            self.sesion.pasos.append(paso)
            self.sesion.paso_actual = self._paso_counter
            self._paso_activo = paso

        # Log posicional
        fila_info = f" [{fila}/{self.total_filas}]" if fila else ""
        sku_info  = f" SKU={sku}" if sku else ""
        esp_info  = f" → esperando: {esperado}" if esperado else ""
        self._log(f"▶ {nombre}{fila_info}{sku_info}: {descripcion}{esp_info}", "PASO")
        return paso

    def _finalizar_etapa(self, paso: Paso, estado: Estado,
                          detalle: str = "", exc: Exception = None):
        with self._lock:
            paso.estado      = estado
            paso.ts_fin      = time.time()
            paso.duracion_seg= round(paso.ts_fin - paso.ts_inicio, 3)
            paso.detalle     = detalle

        nivel = "OK" if estado == Estado.OK else \
                "ERROR" if estado == Estado.ERROR else \
                "WARN"

        dur = f" ({paso.duracion_seg:.2f}s)"
        if estado == Estado.OK:
            self.sesion.filas_ok += 1
            self._log(f"  ✓ {paso.nombre}{dur}", "OK")
        elif estado == Estado.ERROR:
            self.sesion.filas_error += 1
            self._log(f"  ✗ {paso.nombre}{dur} — {detalle}", "ERROR")
            if exc:
                tb = traceback.format_exc()
                self._log(f"    Traceback: {tb.strip()[-200:]}", "ERROR")
        elif estado == Estado.ADVERTENCIA:
            self._log(f"  ⚠ {paso.nombre}{dur} — {detalle}", "WARN")

    def registrar_posicion(self, descripcion: str, nivel: str = "POS"):
        """
        Registra la posición actual del robot de forma explícita.
        Usalo antes de cada acción crítica:
            t.registrar_posicion("Cursor en campo COSTO, escribiendo 1234.56")
        """
        self._log(f"📍 {descripcion}", nivel)

    def registrar_dato(self, label: str, valor):
        """Registra un dato procesado."""
        self._log(f"   {label}: {valor}", "DATA")

    def registrar_popup(self, descripcion: str):
        """Alerta específica para popups detectados."""
        self._log(f"🚨 POPUP DETECTADO: {descripcion}", "WARN")

    def registrar_espera(self, descripcion: str, segundos: float):
        """Registra una pausa intencional."""
        self._log(f"⏳ Esperando {segundos:.1f}s — {descripcion}", "INFO")

    def finalizar(self, estado_global: Estado = None):
        """Cierra la sesión y escribe el reporte final."""
        self.sesion.ts_fin = time.time()
        dur_total = self.sesion.ts_fin - self.sesion.ts_inicio

        # Estado global automático
        if estado_global is None:
            if self.sesion.filas_error == 0:
                estado_global = Estado.OK
            elif self.sesion.filas_ok > 0:
                estado_global = Estado.ADVERTENCIA
            else:
                estado_global = Estado.ERROR
        self.sesion.estado_global = estado_global

        # Reporte final
        self._log(f"{'='*55}", "INFO")
        self._log(f"ROBOT {self.robot} — FINALIZADO", "PASO")
        self._log(f"Duración total:  {dur_total:.1f}s ({dur_total/60:.1f} min)", "DATA")
        self._log(f"Filas OK:        {self.sesion.filas_ok}", "DATA")
        self._log(f"Filas con error: {self.sesion.filas_error}", "DATA")
        self._log(f"Pasos totales:   {len(self.sesion.pasos)}", "DATA")
        self._log(f"Estado global:   {estado_global.value}", "DATA")
        self._log(f"Log guardado en: {Path(self.sesion.log_path).name}", "DATA")

        # Tabla de errores si hubo
        errores = [p for p in self.sesion.pasos if p.estado == Estado.ERROR]
        if errores:
            self._log(f"\n  ERRORES DETECTADOS:", "ERROR")
            for p in errores:
                self._log(f"    Paso {p.id}: {p.nombre} — SKU={p.sku_actual} — {p.detalle}", "ERROR")

        # Pasos más lentos
        pasos_lentos = sorted(
            [p for p in self.sesion.pasos if p.duracion_seg > 3],
            key=lambda x: x.duracion_seg, reverse=True
        )[:5]
        if pasos_lentos:
            self._log(f"\n  PASOS MÁS LENTOS:", "WARN")
            for p in pasos_lentos:
                self._log(f"    {p.nombre}: {p.duracion_seg:.1f}s", "WARN")

        self._log(f"{'='*55}", "INFO")

        # Guardar resumen JSON
        try:
            resumen_path = Path(self.sesion.log_path).with_suffix(".json")
            with open(resumen_path, "w", encoding="utf-8") as f:
                json.dump({
                    "robot":       self.sesion.robot,
                    "archivo":     self.sesion.archivo,
                    "inicio":      datetime.fromtimestamp(self.sesion.ts_inicio).isoformat(),
                    "fin":         datetime.fromtimestamp(self.sesion.ts_fin).isoformat(),
                    "duracion_seg":round(dur_total, 1),
                    "filas_ok":    self.sesion.filas_ok,
                    "filas_error": self.sesion.filas_error,
                    "estado":      estado_global.value,
                    "pasos":       [asdict(p) for p in self.sesion.pasos],
                }, f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass

        try:
            self._log_file.close()
        except Exception:
            pass


class _ContextoEtapa:
    """Context manager interno para cada etapa."""
    def __init__(self, trazador: Trazador, nombre: str, descripcion: str,
                 fila: int, sku: str, esperado: str):
        self.t    = trazador
        self.n    = nombre
        self.d    = descripcion
        self.f    = fila
        self.s    = sku
        self.e    = esperado
        self.paso = None

    def __enter__(self):
        self.paso = self.t._iniciar_etapa(self.n, self.d, self.f, self.s, self.e)
        return self.paso

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.t._finalizar_etapa(self.paso, Estado.OK)
        else:
            self.t._finalizar_etapa(
                self.paso, Estado.ERROR,
                detalle=str(exc_val)[:200],
                exc=exc_val,
            )
        return False   # NO suprimir la excepción


# ══════════════════════════════════════════════════════════════
# MAPAS DE PASOS PRE-DEFINIDOS POR ROBOT
# ══════════════════════════════════════════════════════════════
# Usados para mostrar en la GUI el "mapa de navegación"
# antes de que el robot arranque.

MAPA_LOGIN_PUTTY = [
    ("CONECTAR_SSH",  "Conectar al servidor vía Paramiko SSH"),
    ("ABRIR_PUTTY",   "Abrir ventana PuTTY"),
    ("USUARIO",       "Escribir usuario mbf.andres"),
    ("PASSWORD",      "Escribir contraseña"),
    ("IMPRESORA_1",   "Impresora 1 — Enter"),
    ("IMPRESORA_2",   "Impresora 2 — Enter"),
    ("IMPRESORA_3",   "Impresora 3 — Enter"),
    ("IMPRESORA_4",   "Impresora 4 — Enter"),
    ("MENU_PRINCIPAL","Esperar menú principal"),
]

MAPA_STOCK = MAPA_LOGIN_PUTTY + [
    ("NAV_3",         "Navegar → 3"),
    ("NAV_6",         "Navegar → 6"),
    ("NAV_1",         "Navegar → 1 (Carga Stock)"),
    ("CABECERA_ID",   "Ingresar ID de pedido"),
    ("CABECERA_OBS",  "Ingresar observación"),
    ("CABECERA_TIPO", "Ingresar tipo de ingreso"),
    ("BUCLE_ITEMS",   "Bucle de carga de artículos"),
    ("GRABAR",        "Grabar F5"),
    ("SALIR",         "Volver al menú"),
]

MAPA_PRECIOS = MAPA_LOGIN_PUTTY + [
    ("NAV_3",         "Navegar → 3"),
    ("NAV_4",         "Navegar → 4"),
    ("NAV_2",         "Navegar → 2 (Precios)"),
    ("BUCLE_PRECIOS", "Bucle de carga de precios"),
    ("CIERRE",        "Cierre y salida"),
]

MAPA_AJUSTE = MAPA_LOGIN_PUTTY + [
    ("NAV_3",         "Navegar → 3"),
    ("NAV_6",         "Navegar → 6"),
    ("NAV_2",         "Navegar → 2 (Ajuste)"),
    ("CABECERA_ID",   "Ingresar ID de control"),
    ("CABECERA_OBS",  "Ingresar observación"),
    ("CABECERA_TIPO", "Ingresar tipo de ingreso"),
    ("BUCLE_AJUSTE",  "Bucle de ajustes"),
    ("GRABAR",        "Grabar F5"),
    ("SALIR",         "Volver al menú"),
]
