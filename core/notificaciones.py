"""
notificaciones.py — RPA Suite v5.4
=====================================
Notificaciones de escritorio para Windows.
Solo se muestra si la ventana está minimizada.

Dependencia opcional: plyer (pip install plyer)
Si no está instalado, falla silenciosamente.
"""

from __future__ import annotations
import sys
import threading
from typing import Optional


def _ventana_minimizada(tk_root) -> bool:
    """Devuelve True si la ventana principal está iconificada/minimizada."""
    try:
        return str(tk_root.state()) in ("iconic", "withdrawn")
    except Exception:
        return False


def notificar(
    titulo: str,
    mensaje: str,
    tk_root=None,
    solo_si_minimizada: bool = True,
    icono: str = "info",   # "info" | "warning" | "error"
    duracion: int = 5,
) -> None:
    """
    Muestra notificación de escritorio.
    
    Args:
        titulo:              Título de la notificación.
        mensaje:             Cuerpo del mensaje.
        tk_root:             Ventana principal (para chequear si está minimizada).
        solo_si_minimizada:  Si True, solo notifica cuando la ventana no está visible.
        icono:               Tipo de ícono.
        duracion:            Segundos que se muestra.
    """
    if solo_si_minimizada and tk_root is not None:
        if not _ventana_minimizada(tk_root):
            return  # ventana visible → no notificar

    def _enviar():
        try:
            from plyer import notification
            notification.notify(
                title=titulo,
                message=mensaje,
                app_name="RPA Suite",
                timeout=duracion,
            )
        except ImportError:
            # plyer no instalado — intentar con win10toast como fallback
            try:
                from win10toast import ToastNotifier
                t = ToastNotifier()
                t.show_toast(titulo, mensaje, duration=duracion, threaded=True)
            except ImportError:
                # Ninguno disponible — silencioso
                pass
        except Exception:
            pass

    threading.Thread(target=_enviar, daemon=True).start()


def notificar_exito(robot: str, archivos: int, filas: int, tk_root=None) -> None:
    notificar(
        titulo=f"✅ {robot} completado",
        mensaje=f"{archivos} archivo(s) procesado(s) — {filas} filas en total.",
        tk_root=tk_root,
        icono="info",
    )


def notificar_error(robot: str, detalle: str, tk_root=None) -> None:
    notificar(
        titulo=f"❌ Error en {robot}",
        mensaje=detalle[:200],
        tk_root=tk_root,
        icono="error",
    )
