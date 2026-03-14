"""
checkpoint.py — RPA Suite v5
==============================
Sistema de checkpoints y dry-run para todos los robots.
Permite:
  - Simular la ejecución sin tocar el sistema (dry-run)
  - Reanudar desde la fila donde se interrumpió (checkpoint)
  - Log detallado de cada operación simulada o ejecutada
"""
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime


# Ruta explícita desde core/ → subir un nivel → checkpoints/ en raíz
CHECKPOINT_DIR = Path(__file__).parent.parent / "checkpoints"
CHECKPOINT_DIR.mkdir(exist_ok=True)


@dataclass
class EstadoRobot:
    robot_nombre: str
    archivo_origen: str
    total_filas: int
    ultima_fila: int = 0
    filas_procesadas: list = field(default_factory=list)
    filas_error: list = field(default_factory=list)
    timestamp_inicio: str = field(default_factory=lambda: datetime.now().isoformat())
    timestamp_ultimo: str = field(default_factory=lambda: datetime.now().isoformat())
    completado: bool = False


class GestorCheckpoint:
    """Gestiona la persistencia del estado de un robot."""

    def __init__(self, robot_nombre: str, archivo_origen: str):
        self.robot_nombre = robot_nombre
        self._ruta = CHECKPOINT_DIR / f"{robot_nombre}_{Path(archivo_origen).stem}.json"

    def cargar(self) -> EstadoRobot | None:
        """Carga un checkpoint existente si lo hay."""
        if self._ruta.exists():
            try:
                data = json.loads(self._ruta.read_text(encoding='utf-8'))
                return EstadoRobot(**data)
            except Exception:
                return None
        return None

    def guardar(self, estado: EstadoRobot):
        """Persiste el estado actual."""
        estado.timestamp_ultimo = datetime.now().isoformat()
        self._ruta.write_text(
            json.dumps(asdict(estado), ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

    def limpiar(self):
        """Elimina el checkpoint al completar exitosamente."""
        if self._ruta.exists():
            self._ruta.unlink()

    def existe(self) -> bool:
        return self._ruta.exists()


class ContextoEjecucion:
    """
    Contexto de ejecución de un robot.
    Maneja dry-run, checkpoint y logging unificado.
    
    Uso:
        ctx = ContextoEjecucion("STOCK", ruta_archivo, dry_run=True, log_func=self.log)
        
        with ctx:
            for i, fila in ctx.iterar(df):
                ctx.simular_o_ejecutar(
                    descripcion=f"SKU {sku} → cantidad {cantidad}",
                    accion=lambda: robot.cargar_fila(sku, cantidad)
                )
    """

    def __init__(
        self,
        robot_nombre: str,
        archivo_origen: str,
        total_filas: int,
        dry_run: bool = False,
        reanudar: bool = True,
        log_func=print,
        progress_func=None,
    ):
        self.robot_nombre = robot_nombre
        self.archivo_origen = archivo_origen
        self.total_filas = total_filas
        self.dry_run = dry_run
        self.log_func = log_func
        self.progress_func = progress_func or (lambda x: None)

        self._gestor = GestorCheckpoint(robot_nombre, archivo_origen)
        self._estado = None
        self._reanudar = reanudar
        self._fila_inicio = 0

        self._dry_run_log: list[dict] = []

    def __enter__(self):
        prefijo = "🔍 [DRY-RUN]" if self.dry_run else "🚀 [EJECUCIÓN REAL]"
        self.log_func(f"{prefijo} Robot: {self.robot_nombre}")

        # Verificar checkpoint existente
        if self._reanudar and self._gestor.existe() and not self.dry_run:
            estado_previo = self._gestor.cargar()
            if estado_previo and not estado_previo.completado:
                self._fila_inicio = estado_previo.ultima_fila
                self._estado = estado_previo
                self.log_func(
                    f"⚡ Checkpoint encontrado. Reanudando desde fila {self._fila_inicio + 1} "
                    f"de {estado_previo.total_filas}."
                )
            else:
                self._iniciar_nuevo()
        else:
            self._iniciar_nuevo()

        return self

    def _iniciar_nuevo(self):
        self._fila_inicio = 0
        self._estado = EstadoRobot(
            robot_nombre=self.robot_nombre,
            archivo_origen=self.archivo_origen,
            total_filas=self.total_filas,
        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None and not self.dry_run:
            # Completado exitosamente
            self._estado.completado = True
            self._gestor.guardar(self._estado)
            self._gestor.limpiar()
            self.log_func(f"🏁 Robot {self.robot_nombre} completado. Checkpoint eliminado.")
        elif exc_type is not None and not self.dry_run:
            # Error: guardamos el checkpoint para reanudar
            self._gestor.guardar(self._estado)
            self.log_func(
                f"⚠️ Robot interrumpido en fila {self._estado.ultima_fila}. "
                f"Checkpoint guardado. Podés reanudar desde ahí."
            )

        if self.dry_run:
            self._exportar_dry_run()

        return False  # No suprimimos la excepción

    def iterar(self, df):
        """
        Generador que itera el DataFrame desde la fila de reanudación.
        Retorna (índice_real, fila).
        """
        for i in range(self._fila_inicio, len(df)):
            yield i, df.iloc[i]

    def registrar_ok(self, fila_idx: int, descripcion: str):
        """Registra una fila procesada correctamente."""
        if self._estado:
            self._estado.ultima_fila = fila_idx + 1
            self._estado.filas_procesadas.append(fila_idx)
        self.progress_func((fila_idx + 1) / self.total_filas)

    def registrar_error(self, fila_idx: int, descripcion: str, error: str):
        """Registra una fila con error (el robot continúa)."""
        if self._estado:
            self._estado.filas_error.append({
                "fila": fila_idx,
                "descripcion": descripcion,
                "error": error
            })
        self.log_func(f"⚠️ Fila {fila_idx + 1}: {error}")

    def simular_o_ejecutar(self, descripcion: str, accion, fila_idx: int = 0):
        """
        En dry-run: loguea la descripción sin ejecutar.
        En ejecución real: ejecuta la acción.
        """
        if self.dry_run:
            self._dry_run_log.append({
                "fila": fila_idx + 1,
                "accion": descripcion,
                "timestamp": time.strftime('%H:%M:%S')
            })
            self.log_func(f"   [SIM] Fila {fila_idx + 1}: {descripcion}")
            self.progress_func((fila_idx + 1) / self.total_filas)
        else:
            accion()
            self.registrar_ok(fila_idx, descripcion)
            if not self.dry_run and self._estado:
                # Checkpoint cada 10 filas
                if (fila_idx + 1) % 10 == 0:
                    self._gestor.guardar(self._estado)

    def _exportar_dry_run(self):
        """Exporta el resultado del dry-run a un archivo para revisión."""
        import pandas as pd
        if not self._dry_run_log:
            return
        ruta = Path(__file__).parent.parent / f"DRY_RUN_{self.robot_nombre}_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        pd.DataFrame(self._dry_run_log).to_excel(ruta, index=False)
        self.log_func(f"📋 Simulación exportada: {ruta}")
        self.log_func(
            f"📊 Resumen Dry-Run: {len(self._dry_run_log)} operaciones simuladas. "
            f"Revisá el archivo antes de ejecutar en real."
        )