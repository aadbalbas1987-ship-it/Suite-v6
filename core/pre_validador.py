"""
pre_validador.py — RPA Suite v5.4
===================================
Validaciones pre-ejecución para todos los robots.
Se ejecutan ANTES de tocar PuTTY y generan un reporte
que se muestra en el popup de confirmación.

Cada función recibe un DataFrame y retorna:
    PreValidacion(ok, resumen, detalles, advertencias)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Optional
import pandas as pd

from pathlib import Path
import json

# ──────────────────────────────────────────────────────────────
# SNAPSHOT DE PRECIOS — para comparar delta entre cargas
# ──────────────────────────────────────────────────────────────
_SNAPSHOT_DIR = Path(__file__).parent.parent / "procesados" / "PRECIOS"

def guardar_snapshot_precios(df: pd.DataFrame, archivo: str = "") -> None:
    """Guarda un snapshot del DataFrame de precios para comparar la próxima vez."""
    try:
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        snap = {}
        for _, row in df.iterrows():
            sku = _limpiar_sku(row.iloc[0])
            if not sku or sku.lower() in ("none", "nan", ""):
                continue
            p_salon = _to_float(row.iloc[2]) if len(row) > 2 else None
            costo   = _to_float(row.iloc[1]) if len(row) > 1 else None
            if p_salon:
                snap[sku] = {"p_salon": p_salon, "costo": costo}
        path = _SNAPSHOT_DIR / "ultimo_snapshot_precios.json"
        path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def cargar_snapshot_precios() -> dict:
    """Carga el snapshot anterior de precios. Retorna dict {sku: {p_salon, costo}}."""
    try:
        path = _SNAPSHOT_DIR / "ultimo_snapshot_precios.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}



# ──────────────────────────────────────────────────────────────
# RESULTADO DE VALIDACIÓN
# ──────────────────────────────────────────────────────────────
@dataclass
class PreValidacion:
    ok: bool                          # False = bloquear ejecución
    resumen: str                      # Una línea para el título del popup
    detalles: list[str] = field(default_factory=list)       # Líneas informativas ✅
    advertencias: list[str] = field(default_factory=list)   # Líneas ⚠
    errores: list[str] = field(default_factory=list)        # Líneas ❌ (bloquean)
    preview_filas: list[dict] = field(default_factory=list) # Primeras N filas para tabla

    def to_text(self) -> str:
        lines = [self.resumen, ""]
        for d in self.detalles:
            lines.append(f"  ✅ {d}")
        for w in self.advertencias:
            lines.append(f"  ⚠  {w}")
        for e in self.errores:
            lines.append(f"  ❌ {e}")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ──────────────────────────────────────────────────────────────
def _limpiar_sku(val) -> str:
    try:
        f = float(str(val).replace(",", "."))
        return str(int(f)) if f == int(f) else str(f)
    except Exception:
        return str(val).strip()


def _to_float(val) -> Optional[float]:
    try:
        return float(str(val).replace(",", ".").replace("$", "").strip())
    except Exception:
        return None


def _detectar_duplicados(skus: list[str]) -> list[str]:
    seen, dupes = set(), set()
    for s in skus:
        if s in seen:
            dupes.add(s)
        seen.add(s)
    return sorted(dupes)


# ──────────────────────────────────────────────────────────────
# VALIDADOR STOCK (Robot_Putty)
# ──────────────────────────────────────────────────────────────
def validar_stock(df: pd.DataFrame, archivo: str = "") -> PreValidacion:
    """
    Valida archivo de carga de stock.
    Col A = SKU, Col B = Cantidad, Col C = ID Control, Col D = gramaje (opt)
    """
    v = PreValidacion(ok=True, resumen="")
    skus, cantidades = [], []
    filas_invalidas = 0

    # Detectar y saltar cabecera (primeras 3 filas) si existe
    tiene_cabecera = False
    if len(df) > 0 and not str(df.iloc[0, 0]).strip().isdigit():
        tiene_cabecera = True
        
    start_idx = 3 if tiene_cabecera else 0
    for i, fila in df.iloc[start_idx:].iterrows():
        sku = _limpiar_sku(fila.iloc[0])
        if not sku or sku.lower() in ("none", "nan", ""):
            continue
        cant = _to_float(fila.iloc[1]) if len(fila) > 1 else None
        if cant is None:
            filas_invalidas += 1
            continue
        skus.append(sku)
        cantidades.append(cant)

    total_filas = len(skus)
    suma_control = sum(cantidades)
    dupes = _detectar_duplicados(skus)

    v.resumen = f"📦 STOCK — {total_filas} SKUs | Suma total: {suma_control:,.0f} unidades"
    v.detalles.append(f"{total_filas} filas válidas encontradas")
    v.detalles.append(f"Suma de control: {suma_control:,.0f} unidades")

    if filas_invalidas:
        v.advertencias.append(f"{filas_invalidas} filas con cantidad inválida (serán saltadas)")

    if dupes:
        v.advertencias.append(f"SKUs duplicados en este archivo: {', '.join(dupes[:5])}" +
                               (f" (+{len(dupes)-5} más)" if len(dupes) > 5 else ""))

    # Preview primeras 5 filas
    for i, fila in df.head(5).iterrows():
        sku = _limpiar_sku(fila.iloc[0])
        if sku and sku.lower() not in ("none", "nan", ""):
            v.preview_filas.append({
                "SKU": sku,
                "Cantidad": fila.iloc[1] if len(fila) > 1 else "-",
                "ID Control": fila.iloc[2] if len(fila) > 2 else "-",
            })

    return v


# ──────────────────────────────────────────────────────────────
# VALIDADOR AJUSTE (ajuste.py)
# ──────────────────────────────────────────────────────────────
def validar_ajuste(df: pd.DataFrame, archivo: str = "") -> PreValidacion:
    """
    Valida archivo de ajuste NC.
    Fila 0 = cabecera (ID, Obs, Tipo). Filas 1+ = SKU, Delta, _, gramaje
    """
    v = PreValidacion(ok=True, resumen="")

    # Leer cabecera
    try:
        id_control = str(int(float(df.iloc[0, 2])))
        observacion = str(df.iloc[1, 2]).strip()
        tipo_ingreso = str(df.iloc[2, 2]).strip().upper()
    except Exception:
        v.errores.append("No se pudo leer la cabecera (filas 0-2, col C)")
        v.ok = False
        v.resumen = "❌ AJUSTE — Error en cabecera"
        return v

    tipos_validos = {"A", "B", "C", "D", "E", "F", "I", "M", "R", "V"}
    if tipo_ingreso not in tipos_validos:
        v.advertencias.append(f"Tipo de ingreso '{tipo_ingreso}' no reconocido")

    skus, deltas = [], []
    filas_invalidas = 0
    for i, fila in df.iloc[3:].iterrows():
        sku = _limpiar_sku(fila.iloc[0])
        if not sku or sku.lower() in ("none", "nan", ""):
            continue
        delta = _to_float(fila.iloc[1]) if len(fila) > 1 else None
        if delta is None:
            filas_invalidas += 1
            continue
        skus.append(sku)
        deltas.append(delta)

    total_filas = len(skus)
    suma_positiva = sum(d for d in deltas if d > 0)
    suma_negativa = sum(d for d in deltas if d < 0)
    delta_neto = sum(deltas)
    dupes = _detectar_duplicados(skus)

    v.resumen = f"🔧 AJUSTE — {total_filas} SKUs | Delta neto: {delta_neto:+,.0f}"
    v.detalles.append(f"ID Control: {id_control} | Obs: {observacion} | Tipo: {tipo_ingreso}")
    v.detalles.append(f"{total_filas} movimientos válidos")
    v.detalles.append(f"Entradas: +{suma_positiva:,.0f} | Salidas: {suma_negativa:,.0f} | Neto: {delta_neto:+,.0f}")

    if filas_invalidas:
        v.advertencias.append(f"{filas_invalidas} filas con delta inválido")
    if dupes:
        v.advertencias.append(f"SKUs duplicados: {', '.join(dupes[:5])}")

    # Preview
    for i, fila in df.iloc[3:8].iterrows():
        sku = _limpiar_sku(fila.iloc[0])
        if sku and sku.lower() not in ("none", "nan", ""):
            v.preview_filas.append({
                "SKU": sku,
                "Delta": fila.iloc[1] if len(fila) > 1 else "-",
                "Gramaje": fila.iloc[3] if len(fila) > 3 else "-",
            })

    return v


# ──────────────────────────────────────────────────────────────
# VALIDADOR PRECIOS (Precios_V2)
# ──────────────────────────────────────────────────────────────
def validar_precios(
    df: pd.DataFrame,
    archivo: str = "",
    margen_minimo: float = 0.10,
    snapshot_anterior: Optional[pd.DataFrame] = None,
) -> PreValidacion:
    # Auto-cargar snapshot si no se pasa uno explícito
    _snap_dict_auto = cargar_snapshot_precios() if snapshot_anterior is None else {}
    """
    Valida archivo de precios.
    Col A=SKU, B=Costo, C=Precio Salon, D=Mayorista, E=Galpon (opt)
    """
    v = PreValidacion(ok=True, resumen="")
    skus = []
    alertas_margen = []
    alertas_negativo = []
    filas_invalidas = 0
    deltas_vs_anterior = []

    # Snapshot anterior — usa el cargado automáticamente o el pasado explícitamente
    snap_dict = _snap_dict_auto  # ya es {sku: {p_salon, costo}}
    if snapshot_anterior is not None:
        snap_dict = {}
        for _, row in snapshot_anterior.iterrows():
            sku = _limpiar_sku(row.iloc[0])
            precio = _to_float(row.iloc[2]) if len(row) > 2 else None
            if sku and precio:
                snap_dict[sku] = {"p_salon": precio, "costo": None}

    for i, fila in df.iterrows():
        sku = _limpiar_sku(fila.iloc[0])
        if not sku or sku.lower() in ("none", "nan", ""):
            continue
        costo = _to_float(fila.iloc[1]) if len(fila) > 1 else None
        p_salon = _to_float(fila.iloc[2]) if len(fila) > 2 else None

        if costo is None or p_salon is None:
            filas_invalidas += 1
            continue

        skus.append(sku)

        # Validar margen
        if p_salon > 0 and costo > 0:
            margen = (p_salon - costo) / p_salon
            if margen < 0:
                alertas_negativo.append(f"SKU {sku}: margen NEGATIVO (costo ${costo:,.0f} > precio ${p_salon:,.0f})")
            elif margen < margen_minimo:
                alertas_margen.append(f"SKU {sku}: margen {margen*100:.1f}% < mínimo {margen_minimo*100:.0f}%")

        # Comparar vs snapshot anterior
        if sku in snap_dict:
            entry = snap_dict[sku]
            precio_ant = entry["p_salon"] if isinstance(entry, dict) else entry
            if precio_ant and precio_ant > 0:
                delta_pct = (p_salon - precio_ant) / precio_ant * 100
                if abs(delta_pct) > 20:
                    deltas_vs_anterior.append(f"SKU {sku}: {delta_pct:+.1f}% ({precio_ant:,.0f} → {p_salon:,.0f})")

    total_filas = len(skus)
    dupes = _detectar_duplicados(skus)

    v.resumen = f"💰 PRECIOS — {total_filas} artículos"
    v.detalles.append(f"{total_filas} artículos válidos")

    if filas_invalidas:
        v.advertencias.append(f"{filas_invalidas} filas con datos inválidos")
    if dupes:
        v.advertencias.append(f"SKUs duplicados: {', '.join(dupes[:3])}")
    if alertas_negativo:
        for a in alertas_negativo[:3]:
            v.errores.append(a)
        if len(alertas_negativo) > 3:
            v.errores.append(f"... y {len(alertas_negativo)-3} más con margen negativo")
        v.ok = False  # bloquear si hay margen negativo
    if alertas_margen:
        for a in alertas_margen[:3]:
            v.advertencias.append(a)
        if len(alertas_margen) > 3:
            v.advertencias.append(f"... y {len(alertas_margen)-3} más con margen bajo")
    if deltas_vs_anterior:
        for d in deltas_vs_anterior[:3]:
            v.advertencias.append(f"Cambio >20%: {d}")
        if len(deltas_vs_anterior) > 3:
            v.advertencias.append(f"... y {len(deltas_vs_anterior)-3} más con cambios grandes")

    # Preview
    for i, fila in df.head(5).iterrows():
        sku = _limpiar_sku(fila.iloc[0])
        if sku and sku.lower() not in ("none", "nan", ""):
            v.preview_filas.append({
                "SKU": sku,
                "Costo": fila.iloc[1] if len(fila) > 1 else "-",
                "P.Salon": fila.iloc[2] if len(fila) > 2 else "-",
                "Mayorista": fila.iloc[3] if len(fila) > 3 else "-",
            })

    return v


# ──────────────────────────────────────────────────────────────
# VALIDADOR CHEQUES
# ──────────────────────────────────────────────────────────────
def validar_cheques(df: pd.DataFrame, archivo: str = "") -> PreValidacion:
    """
    Valida archivo de cheques.
    Fila 0: [Entidad, Comision, ...]
    Filas 1+: [_, Ref, Serie, Nro, Fecha_Em, Fecha_Vto, Banco, Nombre, CUIT, Monto]
    """
    v = PreValidacion(ok=True, resumen="")
    hoy = date.today()

    try:
        entidad = str(df.iloc[0, 0])
        comision = _to_float(df.iloc[0, 1]) or 0.0
    except Exception:
        v.errores.append("No se pudo leer cabecera (fila 0)")
        v.ok = False
        v.resumen = "❌ CHEQUES — Error en cabecera"
        return v

    cheques = []
    vencidos = []
    montos = []
    por_banco: dict[str, float] = {}

    for i, fila in df.iloc[1:].iterrows():
        if pd.isna(fila.iloc[1]):
            break
        try:
            nro = str(fila.iloc[3])
            fecha_vto_raw = str(fila.iloc[5])
            banco = str(fila.iloc[6])
            nombre = str(fila.iloc[7])
            monto = _to_float(fila.iloc[9]) or 0.0

            # Parsear fecha vencimiento
            fecha_vto = None
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
                try:
                    fecha_vto = datetime.strptime(fecha_vto_raw, fmt).date()
                    break
                except Exception:
                    pass

            if fecha_vto and fecha_vto < hoy:
                vencidos.append(f"Cheque #{nro} de {nombre} vto {fecha_vto_raw}")

            montos.append(monto)
            por_banco[banco] = por_banco.get(banco, 0) + monto

            cheques.append({
                "Nro": nro,
                "Banco": banco,
                "Nombre": nombre[:20],
                "Vto": fecha_vto_raw,
                "Monto": f"${monto:,.0f}",
            })
        except Exception:
            continue

    total = sum(montos)
    promedio = total / len(montos) if montos else 0
    atipicos = [m for m in montos if m > promedio * 3 and m > 10000]

    v.resumen = f"📋 CHEQUES — {len(cheques)} cheques | Total: ${total:,.0f} | Entidad: {entidad}"
    v.detalles.append(f"Entidad: {entidad} | Comisión: ${comision:,.2f}")
    v.detalles.append(f"Total cartera: ${total:,.0f} | APF: ${total - comision:,.0f}")

    # Resumen por banco
    for banco, monto in sorted(por_banco.items(), key=lambda x: -x[1])[:4]:
        v.detalles.append(f"  {banco}: ${monto:,.0f}")

    if vencidos:
        for venc in vencidos[:3]:
            v.errores.append(f"VENCIDO: {venc}")
        if len(vencidos) > 3:
            v.errores.append(f"... y {len(vencidos)-3} más vencidos")
        v.ok = False

    if atipicos:
        v.advertencias.append(f"{len(atipicos)} cheque(s) con monto atípico (>3x promedio)")

    v.preview_filas = cheques[:5]

    return v


# ──────────────────────────────────────────────────────────────
# DISPATCHER: elige validador según modo
# ──────────────────────────────────────────────────────────────
def validar_por_modo(
    modo: str,
    df: pd.DataFrame,
    archivo: str = "",
    **kwargs,
) -> PreValidacion:
    """Punto de entrada unificado."""
    modo = modo.upper()
    if modo in ("STOCK", "STOCK_PARAMIKO"):
        return validar_stock(df, archivo)
    elif modo in ("AJUSTE", "AJUSTE_ANALITICO", "AJUSTE_PARAMIKO"):
        return validar_ajuste(df, archivo)
    elif modo in ("PRECIOS", "PRECIOS_PARAMIKO"):
        return validar_precios(df, archivo, **kwargs)
    elif modo == "CHEQUES":
        return validar_cheques(df, archivo)
    else:
        return PreValidacion(
            ok=True,
            resumen=f"Modo {modo} — sin validación específica",
            detalles=["Validación genérica: archivo cargado OK"],
        )
