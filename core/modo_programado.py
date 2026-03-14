"""
core/modo_programado.py — RPA Suite v5.6
==========================================
Modo programado: ejecuta robots a hora fija sin intervención manual.

Uso desde la GUI:
    from core.modo_programado import Scheduler
    sched = Scheduler(log_func=self.log)
    sched.agregar_tarea("STOCK", hora="08:00", callback=self.run_robot_auto)
    sched.iniciar()   # corre en thread daemon
    sched.detener()

Persiste tareas en config.toml bajo [scheduler].
"""
import threading
import time
from datetime import datetime, date
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional
import json

_SCHED_FILE = Path(__file__).parent.parent / "scheduler_tasks.json"


@dataclass
class Tarea:
    robot:    str          # "STOCK", "PRECIOS", "AJUSTE", "CHEQUES"
    hora:     str          # "HH:MM" en 24h
    activa:   bool = True
    dias:     list = field(default_factory=lambda: ["lun","mar","mie","jue","vie"])  # días de la semana
    ultimo_run: str = ""   # "YYYY-MM-DD" de la última ejecución


DIAS_MAP = {
    0: "lun", 1: "mar", 2: "mie", 3: "jue",
    4: "vie", 5: "sab", 6: "dom",
}


class Scheduler:
    """
    Scheduler simple que corre en background y dispara callbacks a la hora indicada.
    """

    def __init__(self, log_func=None):
        self._log      = log_func or print
        self._tareas:  list[Tarea] = []
        self._callbacks: dict[str, Callable] = {}
        self._running  = False
        self._thread:  Optional[threading.Thread] = None
        self._cargar()

    # ── Persistencia ──────────────────────────────────────────

    def _cargar(self):
        if _SCHED_FILE.exists():
            try:
                data = json.loads(_SCHED_FILE.read_text(encoding="utf-8"))
                self._tareas = [Tarea(**t) for t in data]
                self._log(f"  📅 Scheduler: {len(self._tareas)} tarea(s) cargadas")
            except Exception as e:
                self._log(f"  ⚠ Scheduler: error cargando tareas: {e}")

    def _guardar(self):
        try:
            _SCHED_FILE.write_text(
                json.dumps([asdict(t) for t in self._tareas], ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            self._log(f"  ⚠ Scheduler: error guardando: {e}")

    # ── API pública ───────────────────────────────────────────

    def agregar_tarea(self, robot: str, hora: str,
                      dias: list = None, callback: Callable = None) -> Tarea:
        """Agrega o actualiza una tarea programada."""
        # Eliminar si ya existe el mismo robot
        self._tareas = [t for t in self._tareas if t.robot != robot]
        tarea = Tarea(robot=robot, hora=hora,
                      dias=dias or ["lun","mar","mie","jue","vie"])
        self._tareas.append(tarea)
        if callback:
            self._callbacks[robot] = callback
        self._guardar()
        self._log(f"  ✅ Tarea programada: {robot} a las {hora} ({', '.join(tarea.dias)})")
        return tarea

    def registrar_callback(self, robot: str, callback: Callable):
        """Registra la función a llamar cuando llegue la hora."""
        self._callbacks[robot] = callback

    def eliminar_tarea(self, robot: str):
        self._tareas = [t for t in self._tareas if t.robot != robot]
        self._callbacks.pop(robot, None)
        self._guardar()
        self._log(f"  🗑 Tarea eliminada: {robot}")

    def listar_tareas(self) -> list[Tarea]:
        return list(self._tareas)

    def iniciar(self):
        """Inicia el loop en background (thread daemon)."""
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True, name="Scheduler")
        self._thread.start()
        self._log("  🟢 Scheduler iniciado")

    def detener(self):
        self._running = False
        self._log("  🔴 Scheduler detenido")

    # ── Loop interno ──────────────────────────────────────────

    def _loop(self):
        while self._running:
            ahora = datetime.now()
            hh_mm = ahora.strftime("%H:%M")
            dia   = DIAS_MAP[ahora.weekday()]
            hoy   = date.today().isoformat()

            for tarea in self._tareas:
                if not tarea.activa:
                    continue
                if tarea.hora != hh_mm:
                    continue
                if dia not in tarea.dias:
                    continue
                if tarea.ultimo_run == hoy:
                    continue  # ya corrió hoy

                # ¡Disparar!
                self._log(f"\n⏰ Scheduler: ejecutando {tarea.robot} (programado {tarea.hora})")
                tarea.ultimo_run = hoy
                self._guardar()

                cb = self._callbacks.get(tarea.robot)
                if cb:
                    try:
                        threading.Thread(target=cb, kwargs={"robot": tarea.robot},
                                         daemon=True).start()
                    except Exception as e:
                        self._log(f"  ❌ Scheduler error al ejecutar {tarea.robot}: {e}")
                else:
                    self._log(f"  ⚠ Sin callback registrado para {tarea.robot}")

            # Esperar hasta el próximo minuto
            segundos_al_cambio = 60 - ahora.second
            time.sleep(segundos_al_cambio)
