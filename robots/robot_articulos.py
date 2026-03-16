"""
robots/robot_articulos.py — RPA Suite v5.9
==========================================
Robot de creacion masiva de articulos via PyAutoGUI en PuTTY.
Lee el Excel de carga (CARGA_ARTICULOS_TEMPLATE.xlsx) y asigna
automaticamente el categori usando Categori.txt + IA (Groq).

PRE-REQUISITO: PuTTY abierto en menu 3-3-2

FLUJO POR ARTICULO:
  1.  SKU            → Enter x2
  2.  UXB            → Enter x3
  3.  FAMILIA        → Enter  (asignado por IA desde Categori.txt)
  4.  DPTO           → Enter
  5.  SECCION        → Enter
  6.  GRUPO          → Enter x2
  7.  MARCA          → Enter x4
  8.  DESCRIPCION    → Enter x6
  9.  PESABLE (0/1)  → Enter
  10. Si PESABLE=1:
        → Enter x2 → PESO_ESTANDAR → Enter
        → BULTOS_PALET (si existe) → Enter x2
        → DIAS_VENCIM (si existe)  → Enter
        → 30 (dias minimo)         → Enter x2
        → UXB (unid minima compra) → Enter x5  (sale popup)
  11. 1 (categoria IVA) → Enter
  12. B (jurisdiccion)  → Enter x4 → Enter x6
  13. Si BARCODE:
        → S → Enter → barcode → Enter
        → CU → Enter → 1 → Enter x4
        → S + Enter  (repetir 6 veces)
        → F5 → Enter → End
  14. Enter x8
  15. COD_PROVEEDOR → Enter
  16. P (proveedor principal) → Enter → F5
  17. "CREACION DE PRODUCTO NUEVO" → F5
"""

import time
import os
import sys
from pathlib import Path
from datetime import datetime

try:
    import pyautogui
    import pyperclip
    _PYAUTOGUI_OK = True
except ImportError:
    _PYAUTOGUI_OK = False

DELAY_DEFAULT      = 0.4   # segundos entre acciones
DELAY_PRODUCTO     = 1.2   # pausa entre productos
COUNTDOWN_SECS     = 5
MOTIVO_NOVEDAD     = "CREACION DE PRODUCTO NUEVO"


# ══════════════════════════════════════════════════════════════
# HELPERS DE INPUT
# ══════════════════════════════════════════════════════════════

def _paste(texto, delay):
    """Copia al portapapeles y pega con Ctrl+V."""
    pyperclip.copy(str(texto))
    time.sleep(delay * 0.4)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(delay)

def _enter(n=1, delay=DELAY_DEFAULT):
    for _ in range(n):
        pyautogui.press("enter")
        time.sleep(delay * 0.4)

def _key(k, delay=DELAY_DEFAULT):
    pyautogui.press(k)
    time.sleep(delay * 0.4)

def _type(texto, delay=DELAY_DEFAULT):
    """Escribe texto caracter a caracter (para strings cortos/seguros)."""
    pyautogui.typewrite(str(texto), interval=0.05)
    time.sleep(delay * 0.4)


# ══════════════════════════════════════════════════════════════
# LEER EXCEL DE CARGA
# ══════════════════════════════════════════════════════════════

def leer_excel_articulos(ruta_excel: str, tiene_encabezados: bool = True) -> list[dict]:
    """
    Lee el Excel de carga masiva de articulos.
    Columnas esperadas (en orden):
      A=SKU, B=UXB, C=MARCA, D=DESCRIPCION, E=DESCRIPCION_IA,
      F=PESABLE, G=PESO_ESTANDAR, H=BULTOS_PALET, I=DIAS_VENCIM,
      J=BARCODE, K=COD_PROVEEDOR
    """
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl no instalado: pip install openpyxl")

    wb = openpyxl.load_workbook(ruta_excel, data_only=True)
    ws = wb.active

    articulos = []
    fila_inicio = 2 if tiene_encabezados else 1

    for row in ws.iter_rows(min_row=fila_inicio, values_only=True):
        # Saltar filas completamente vacias
        if not any(c for c in row if c is not None):
            continue

        def _val(idx, default=None):
            try:
                v = row[idx]
                return str(v).strip() if v is not None else default
            except IndexError:
                return default

        def _int(idx, default=None):
            try:
                v = row[idx]
                return int(float(str(v))) if v is not None else default
            except (ValueError, TypeError, IndexError):
                return default

        def _float(idx, default=None):
            try:
                v = row[idx]
                return float(str(v).replace(",", ".")) if v is not None else default
            except (ValueError, TypeError, IndexError):
                return default

        sku = _val(0)
        if not sku:
            continue

        desc = _val(3, "")
        col_4 = _val(4, "")
        col_5 = _val(5, "")

        # Auto-detectar plantilla vieja (donde Col E era PESABLE en vez de DESCRIPCION_IA)
        if col_4 in ["0", "1", "0.0", "1.0"] and col_5 not in ["0", "1", "0.0", "1.0"]:
            offset = -1
            desc_ia = ""
        else:
            offset = 0
            desc_ia = col_4

        art = {
            "sku":            sku,
            "uxb":            _int(1),
            "marca":          _val(2, ""),
            "descripcion":    desc,
            "descripcion_ia": desc_ia or desc,
            "pesable":        _int(5 + offset, 0),
            "peso_estandar":  _float(6 + offset),
            "bultos_palet":   _int(7 + offset),
            "dias_vencim":    _int(8 + offset),
            "barcode":        _val(9 + offset),
            "cod_proveedor":  _val(10 + offset, ""),
            # categori se asigna luego
            "familia":  None,
            "dpto":     None,
            "seccion":  None,
            "grupo":    None,
            "desc_match": None,
            "categori_metodo": None,
        }
        articulos.append(art)

    return articulos


# ══════════════════════════════════════════════════════════════
# ASIGNAR CATEGORIS EN LOTE (con Groq + Categori.txt)
# ══════════════════════════════════════════════════════════════

def asignar_categoris(articulos: list[dict],
                       ruta_categori=None,
                       log_func=None) -> list[dict]:
    """
    Asigna FAMILIA/DPTO/SECCION/GRUPO a cada articulo usando categori_matcher.
    Modifica la lista in-place y la retorna.
    """
    def _log(m):
        if log_func: log_func(m)

    try:
        from tools.categori_matcher import asignar_categori, cargar_categori
    except ImportError:
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from tools.categori_matcher import asignar_categori, cargar_categori
        except ImportError:
            _log("  categori_matcher no disponible — categoris vacias")
            return articulos

    ruta = ruta_categori or (Path(__file__).parent.parent / "Categori.txt")
    try:
        items_cat = cargar_categori(ruta)
        _log(f"  Categori.txt cargado: {len(items_cat)} productos")
    except FileNotFoundError:
        _log(f"  Categori.txt no encontrado en {ruta}")
        return articulos

    for i, art in enumerate(articulos, 1):
        desc = art["descripcion_ia"] or art["descripcion"]
        _log(f"  [{i}/{len(articulos)}] Categorizando: {desc}")
        res = asignar_categori(desc, items_precargados=items_cat, log_func=log_func)
        art["familia"]         = res["familia"]
        art["dpto"]            = res["dpto"]
        art["seccion"]         = res["seccion"]
        art["grupo"]           = res["grupo"]
        art["desc_match"]      = res["descripcion_match"]
        art["categori_metodo"] = res["metodo"]
        conf = "✅" if res["confianza_alta"] else "⚠"
        _log(f"    {conf} FAM={res['familia']} DPT={res['dpto']} "
             f"SEC={res['seccion']} GRP={res['grupo']} "
             f"→ {res['descripcion_match'][:40]}")

    return articulos


# ══════════════════════════════════════════════════════════════
# CARGAR UN ARTICULO EN PUTTY
# ══════════════════════════════════════════════════════════════

def cargar_articulo(art: dict, delay: float = DELAY_DEFAULT,
                     dry_run: bool = False, log_func=None):
    """
    Ejecuta la secuencia completa de carga de un articulo en PuTTY (menu 3-3-2).
    """
    def _log(m):
        if log_func: log_func(m)

    if dry_run:
        _log(f"  [DRY-RUN] SKU={art['sku']} UXB={art['uxb']} "
             f"FAM={art['familia']} MARCA={art['marca']}")
        return

    d = delay

    # ── 1. SKU → Enter x2
    _paste(art["sku"], d); _enter(2, d)

    # ── 2. UXB → Enter x3
    _paste(art["uxb"], d); _enter(3, d)

    # ── 3. FAMILIA → Enter
    _paste(art["familia"], d); _enter(1, d)

    # ── 4. DPTO → Enter
    _paste(art["dpto"], d); _enter(1, d)

    # ── 5. SECCION → Enter
    _paste(art["seccion"], d); _enter(1, d)

    # ── 6. GRUPO → Enter x2
    _paste(art["grupo"], d); _enter(2, d)

    # ── 7. MARCA → Enter x4
    _paste(art["marca"], d); _enter(4, d)

    # ── 8. DESCRIPCION → Enter x6
    _paste(art["descripcion"], d); _enter(6, d)

    # ── 9. PESABLE (0 o 1) → Enter
    _paste(art["pesable"], d); _enter(1, d)

    # ── 10. Popup pesable (solo si PESABLE=1)
    if art["pesable"] == 1:
        _enter(2, d)
        # Peso estandar
        if art["peso_estandar"] is not None:
            _paste(str(art["peso_estandar"]).replace(",", "."), d)
        _enter(1, d)
        # Bultos por palet (opcional)
        if art["bultos_palet"]:
            _paste(art["bultos_palet"], d)
        _enter(2, d)
        # Dias vencimiento (opcional)
        if art["dias_vencim"]:
            _paste(art["dias_vencim"], d)
        _enter(1, d)
        # Dias minimo vencimiento — siempre 30
        _paste("30", d); _enter(1, d)
        # Unidades minima compra — siempre = UXB
        _enter(2, d)
        _paste(art["uxb"], d)
        _enter(1, d)
        # 5 Enter para salir del popup de pesable
        _enter(5, d)

    # ── 11. Categoria IVA = 1 → Enter
    _paste("1", d); _enter(1, d)

    # ── 12. Jurisdiccion = B → Enter x4 → Enter x6
    _type("B", d); _enter(4, d); _enter(6, d)

    # ── 13. Codigo de barras (opcional)
    barcode = art.get("barcode")
    if barcode and str(barcode).strip() not in ["", "None"]:
        _type("S", d); _enter(1, d)          # tiene barcode
        _paste(barcode, d); _enter(1, d)     # escribir barcode
        _type("CU", d); _enter(1, d)         # tipo CU
        _paste("1", d); _enter(4, d)         # cantidad 1
        _type("S", d); _enter(1, d)          # confirmar
        for _ in range(6):                   # repetir S+Enter 6 veces
            _type("S", d); _enter(1, d)
        _key("f5", d); _enter(1, d); _key("end", d)  # salir popup barcode

    # ── 14. Enter x8 (llegar a campo proveedor)
    _enter(8, d)

    # ── 15. Codigo proveedor → Enter
    _paste(art["cod_proveedor"], d); _enter(1, d)

    # ── 16. P (proveedor principal) → Enter → F5
    _type("P", d); _enter(1, d); _key("f5", d)

    # ── 17. Motivo novedad → F5
    _paste(MOTIVO_NOVEDAD, d); _key("f5", d)

    _log(f"  OK: {art['sku']} — {art['descripcion'][:40]}")


# ══════════════════════════════════════════════════════════════
# FUNCION PRINCIPAL
# ══════════════════════════════════════════════════════════════

def ejecutar_carga_articulos(
    ruta_excel: str,
    tiene_encabezados: bool = True,
    ruta_categori: str = None,
    delay: float = DELAY_DEFAULT,
    dry_run: bool = False,
    start_desde: int = 1,
    limite: int = None,
    log_func=None,
) -> dict:
    """
    Funcion principal del robot de carga masiva.
    Retorna dict con ok, errores, saltados, total.
    """
    def _log(m):
        if log_func: log_func(m)

    if not _PYAUTOGUI_OK and not dry_run:
        _log("pyautogui no instalado: pip install pyautogui pyperclip")
        return {"ok": 0, "errores": 0, "saltados": 0, "total": 0}

    # 1. Leer Excel
    _log(f"Leyendo Excel: {ruta_excel}")
    try:
        articulos = leer_excel_articulos(ruta_excel, tiene_encabezados)
    except Exception as e:
        _log(f"Error leyendo Excel: {e}")
        return {"ok": 0, "errores": 1, "saltados": 0, "total": 0}

    if not articulos:
        _log("El Excel no tiene articulos validos.")
        return {"ok": 0, "errores": 0, "saltados": 0, "total": 0}

    _log(f"  {len(articulos)} articulo(s) encontrado(s) en el Excel")

    # 2. Asignar categoris con IA
    _log("\nAsignando categorias con IA...")
    articulos = asignar_categoris(articulos, ruta_categori, log_func)

    # 3. Aplicar start_desde y limite
    idx_start = max(0, start_desde - 1)
    articulos = articulos[idx_start:]
    if limite:
        articulos = articulos[:limite]
    total = len(articulos)
    _log(f"\nArticulos a cargar: {total}")

    # 4. Verificar campos minimos
    saltados = []
    a_cargar = []
    for art in articulos:
        faltantes = []
        if not art["sku"]:            faltantes.append("SKU")
        if not art["uxb"]:            faltantes.append("UXB")
        if not art["marca"]:          faltantes.append("MARCA")
        if not art["descripcion"]:    faltantes.append("DESCRIPCION")
        if not art["cod_proveedor"]:  faltantes.append("COD_PROVEEDOR")
        if not art["familia"]:        faltantes.append("FAMILIA (sin match en Categori.txt)")
        if faltantes:
            _log(f"  SALTADO {art['sku']}: faltan {', '.join(faltantes)}")
            saltados.append(art["sku"])
        else:
            a_cargar.append(art)

    if not a_cargar:
        _log("Sin articulos validos para cargar.")
        return {"ok": 0, "errores": 0, "saltados": len(saltados), "total": total}

    _log(f"\n  A cargar: {len(a_cargar)} | Saltados: {len(saltados)}")

    if dry_run:
        _log("\nMODO DRY-RUN — sin tocar PuTTY\n")

    # 5. Loop de carga
    ok = 0
    errores = []
    for i, art in enumerate(a_cargar, 1):
        _log(f"\n[{i}/{len(a_cargar)}] {art['sku']} — {art['descripcion'][:40]}")
        _log(f"  Categori: FAM={art['familia']} DPT={art['dpto']} "
             f"SEC={art['seccion']} GRP={art['grupo']}")
        _log(f"  Match: {art['desc_match']} ({art['categori_metodo']})")

        try:
            cargar_articulo(art, delay=delay, dry_run=dry_run, log_func=log_func)
            ok += 1
            time.sleep(DELAY_PRODUCTO)

        except Exception as e:
            _log(f"  ERROR en {art['sku']}: {e}")
            errores.append(art["sku"])
            time.sleep(DELAY_PRODUCTO)

    _log(f"\n{'='*50}")
    _log(f"RESULTADO: {ok} OK | {len(errores)} errores | {len(saltados)} saltados")
    if errores:
        _log(f"Errores: {', '.join(errores)}")
    if saltados:
        _log(f"Saltados: {', '.join(saltados)}")

    return {
        "ok":       ok,
        "errores":  len(errores),
        "saltados": len(saltados),
        "total":    total,
    }
