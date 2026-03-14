"""
tools/pricing_ia_search.py — RPA Suite v5.9
============================================
Motor de pricing usando APIs VTEX públicas de supermercados argentinos.
Carrefour, Día, Jumbo, Changomás y Walmart exponen APIs VTEX sin auth.
Groq se usa opcionalmente para enriquecer/normalizar resultados.
"""
import json
import re
import time
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

LogFunc = Optional[callable]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-AR,es;q=0.9",
    "Referer": "https://www.google.com.ar/",
}

# APIs VTEX públicas — no requieren autenticación
VTEX_FUENTES = {
    # ── Supermercados ──────────────────────────────────────
    "Carrefour":   "https://www.carrefour.com.ar/api/catalog_system/pub/products/search",
    "Día":         "https://diaonline.supermercadosdia.com.ar/api/catalog_system/pub/products/search",
    "Jumbo":       "https://www.jumbo.com.ar/api/catalog_system/pub/products/search",
    "Changomás":   "https://www.changomas.com.ar/api/catalog_system/pub/products/search",
    "Walmart":     "https://www.walmart.com.ar/api/catalog_system/pub/products/search",
    "Vea":         "https://www.vea.com.ar/api/catalog_system/pub/products/search",
    "Disco":       "https://www.disco.com.ar/api/catalog_system/pub/products/search",
    # ── Mayoristas ─────────────────────────────────────────
    "Makro":       "https://www.makro.com.ar/api/catalog_system/pub/products/search",
    "Vital":       "https://www.vital.com.ar/api/catalog_system/pub/products/search",
    "MaxiConsumo": "https://www.maxiconsumo.com/api/catalog_system/pub/products/search",
    "Diarco":      "https://www.diarco.com.ar/api/catalog_system/pub/products/search",
}


def _parse_vtex(data: list, fuente: str, base_url: str) -> list:
    """Parsea respuesta estándar de API VTEX."""
    items = []
    for p in (data or []):
        try:
            precio = float(
                p["items"][0]["sellers"][0]["commertialOffer"]["Price"]
            )
        except (KeyError, IndexError, TypeError, ValueError):
            precio = 0.0
        titulo = p.get("productName") or p.get("productTitle", "")
        if not titulo:
            continue
        link = p.get("linkText", "")
        items.append({
            "fuente": fuente,
            "titulo": titulo,
            "precio": precio,
            "url":    f"{base_url}/{link}/p" if link else base_url,
            "marca":  p.get("brand", ""),
            "imagen": "",
        })
    return items


def _buscar_en_fuente(nombre: str, api_url: str, queries: list,
                       max_items: int, session) -> list:
    """Busca con cada variante de query y mergea resultados únicos."""
    todos = {}
    last_err = None
    base = api_url.replace("/api/catalog_system/pub/products/search", "")

    for q in queries:
        try:
            r = session.get(
                api_url,
                params={"ft": q, "_from": 0, "_to": max_items - 1},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    for item in _parse_vtex(data, nombre, base):
                        k = item["titulo"].lower()[:60]
                        if k not in todos:
                            todos[k] = item
            elif r.status_code in (403, 503):
                last_err = f"bloqueado (HTTP {r.status_code})"
                break  # no reintentar si bloqueado
        except Exception as e:
            last_err = str(e)[:80]

    if not todos and last_err:
        raise RuntimeError(last_err)
    return list(todos.values())


def buscar_precios_ia(
    query: str,
    max_resultados: int = 15,
    log_func: LogFunc = None,
) -> dict:
    """
    Busca precios en supermercados argentinos via APIs VTEX.
    Compatible con el formato de pricing_multifuente.
    """
    def _log(m):
        if log_func: log_func(m)

    try:
        import requests
    except ImportError:
        return _resultado_vacio("requests no instalado")

    session = requests.Session()
    session.headers.update(_HEADERS)

    # Variantes de búsqueda: query completo + cada palabra significativa
    palabras = [w for w in query.split() if len(w) > 2]
    queries  = list(dict.fromkeys([query] + palabras))

    _log(f"🔍 Buscando '{query}' en {len(VTEX_FUENTES)} supermercados")
    if len(queries) > 1:
        _log(f"   Variantes: {', '.join(queries)}")

    items_por_fuente = {}
    fuentes_ok    = []
    fuentes_error = []

    with ThreadPoolExecutor(max_workers=len(VTEX_FUENTES)) as pool:
        futuros = {
            pool.submit(_buscar_en_fuente, nombre, url, queries, max_resultados, session): nombre
            for nombre, url in VTEX_FUENTES.items()
        }
        for fut in as_completed(futuros, timeout=30):
            nombre = futuros[fut]
            try:
                result = fut.result(timeout=12)
                if result:
                    items_por_fuente[nombre] = result
                    fuentes_ok.append(nombre)
                    _log(f"  ✅ {nombre}: {len(result)} producto(s)")
                else:
                    fuentes_error.append(f"{nombre}: sin resultados")
                    _log(f"  ⚠  {nombre}: sin resultados para '{query}'")
            except Exception as e:
                err = str(e)[:70]
                fuentes_error.append(f"{nombre}: {err}")
                _log(f"  ❌ {nombre}: {err}")

    items_todos = [i for items in items_por_fuente.values() for i in items]

    if not items_todos:
        _log("")
        _log("⚠  Ningún supermercado devolvió resultados.")
        _log("   → Verificá tu conexión a internet")
        _log("   → Probá con un producto más genérico (ej: 'coca cola' en lugar de 'coca cola 2.25 litros')")
    else:
        _log(f"\n📊 Total: {len(items_todos)} precio(s) de {len(fuentes_ok)} fuente(s)")

    return _construir_resultado(items_por_fuente, items_todos, fuentes_ok, fuentes_error)


def _construir_resultado(items_por_fuente, items_todos, fuentes_ok, fuentes_error):
    estadisticas = {}
    todos_precios = []
    for fuente, items in items_por_fuente.items():
        precios = sorted([i["precio"] for i in items if i["precio"] > 0])
        if not precios:
            continue
        todos_precios.extend(precios)
        n = len(precios)
        estadisticas[fuente] = {
            "min":     precios[0],
            "max":     precios[-1],
            "mediana": precios[n // 2],
            "promedio": round(sum(precios) / n, 2),
            "n":       n,
        }
    mercado = {}
    if todos_precios:
        todos_precios.sort()
        n = len(todos_precios)
        mercado = {
            "min":     todos_precios[0],
            "max":     todos_precios[-1],
            "mediana": todos_precios[n // 2],
            "promedio": round(sum(todos_precios) / n, 2),
            "n_total": n,
        }
    return {
        "items_por_fuente": items_por_fuente,
        "items_todos":      items_todos,
        "estadisticas":     estadisticas,
        "fuentes_ok":       fuentes_ok,
        "fuentes_error":    fuentes_error,
        "mercado":          mercado,
    }


def _resultado_vacio(error=""):
    return {
        "items_por_fuente": {}, "items_todos": [],
        "estadisticas": {}, "fuentes_ok": [],
        "fuentes_error": [error] if error else [],
        "mercado": {}, "error": error,
    }
