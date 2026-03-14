"""
tools/pricing_multifuente.py — RPA Suite v5.9
===============================================
Motor de pricing multi-fuente para retail argentino.
Extrae precios de supermercados, mayoristas y Google Shopping.

Fuentes soportadas:
  - Carrefour AR    (carrefour.com.ar)
  - Coto            (coto.com.ar)
  - Dia             (diasonline.com.ar)
  - Jumbo           (jumbo.com.ar)
  - Changomas       (changomas.com.ar)
  - Makro           (makro.com.ar)
  - Google Shopping (vía scraping)
  - Lista proveedor (PDF / Excel upload)

Cada scraper es independiente y falla silenciosamente si el sitio
cambia su estructura — el motor sigue con las demás fuentes.
"""
import re
import time
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    _REQ = True
except ImportError:
    _REQ = False

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False

_CACHE_DIR = Path(__file__).parent.parent / "pricing_data" / "cache_multifuente"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_TTL_HORAS = 6   # cache de 6hs — precios no cambian tan seguido

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

LogFunc = Optional[callable]


# ══════════════════════════════════════════════════════════════
# SESIÓN HTTP con retry
# ══════════════════════════════════════════════════════════════

def _session() -> "requests.Session":
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://",  HTTPAdapter(max_retries=retry))
    s.headers.update(_HEADERS)
    return s


# ══════════════════════════════════════════════════════════════
# CACHE
# ══════════════════════════════════════════════════════════════

def _cache_key(fuente: str, query: str) -> str:
    return hashlib.md5(f"{fuente}:{query}".encode()).hexdigest()

def _cache_get(fuente: str, query: str) -> Optional[list]:
    key  = _cache_key(fuente, query)
    path = _CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        edad_horas = (time.time() - data["ts"]) / 3600
        if edad_horas < _CACHE_TTL_HORAS:
            return data["items"]
    except Exception:
        pass
    return None

def _cache_set(fuente: str, query: str, items: list):
    key  = _cache_key(fuente, query)
    path = _CACHE_DIR / f"{key}.json"
    path.write_text(
        json.dumps({"ts": time.time(), "fuente": fuente, "query": query, "items": items},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ══════════════════════════════════════════════════════════════
# NORMALIZACIÓN DE PRECIOS
# ══════════════════════════════════════════════════════════════

def _parse_precio(texto: str) -> float:
    """Extrae float de strings como '$1.234,50' o '1234.5'."""
    if not texto:
        return 0.0
    # Remover símbolo de moneda y espacios
    t = re.sub(r'[^\d.,]', '', str(texto))
    # Formato argentino: 1.234,50
    if ',' in t and '.' in t:
        t = t.replace('.', '').replace(',', '.')
    elif ',' in t:
        t = t.replace(',', '.')
    try:
        return float(t)
    except Exception:
        return 0.0


# ══════════════════════════════════════════════════════════════
# SCRAPERS POR FUENTE
# ══════════════════════════════════════════════════════════════

def _scrape_carrefour(query: str, max_items: int = 10) -> list[dict]:
    """
    Carrefour AR — usa su API interna de búsqueda.
    Endpoint: https://www.carrefour.com.ar/api/catalog_system/pub/products/search
    """
    if not _REQ:
        return []
    cached = _cache_get("carrefour", query)
    if cached is not None:
        return cached

    items = []
    try:
        s   = _session()
        url = "https://www.carrefour.com.ar/api/catalog_system/pub/products/search"
        params = {"ft": query, "_from": 0, "_to": max_items - 1}
        r = s.get(url, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        for p in data[:max_items]:
            precio = 0.0
            try:
                precio = p["items"][0]["sellers"][0]["commertialOffer"]["Price"]
            except (KeyError, IndexError):
                pass
            items.append({
                "fuente":    "Carrefour",
                "titulo":    p.get("productName", ""),
                "precio":    precio,
                "url":       f"https://www.carrefour.com.ar/{p.get('linkText','')}/p",
                "marca":     p.get("brand", ""),
                "imagen":    (p.get("items",[{}])[0].get("images",[{}])[0].get("imageUrl","")
                              if p.get("items") else ""),
            })
    except Exception as _e:
        _scraper_err = str(_e)

    _cache_set("carrefour", query, items)
    return items


def _scrape_coto(query: str, max_items: int = 10) -> list[dict]:
    """
    Coto — scraping HTML de su buscador.
    """
    if not _REQ or not _BS4:
        return []
    cached = _cache_get("coto", query)
    if cached is not None:
        return cached

    items = []
    try:
        s   = _session()
        url = f"https://www.coto.com.ar/search?q={requests.utils.quote(query)}&start=0&count={max_items}"
        r   = s.get(url, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for card in soup.select(".product-item, .item-product, [class*='product-card']")[:max_items]:
            nombre = card.select_one("[class*='name'], [class*='title'], h3, h2")
            precio = card.select_one("[class*='price'], [class*='precio']")
            link   = card.select_one("a")
            if not nombre or not precio:
                continue
            p = _parse_precio(precio.get_text())
            if p <= 0:
                continue
            items.append({
                "fuente":  "Coto",
                "titulo":  nombre.get_text(strip=True),
                "precio":  p,
                "url":     "https://www.coto.com.ar" + (link["href"] if link and link.get("href","").startswith("/") else ""),
                "marca":   "",
                "imagen":  "",
            })
    except Exception as _e:
        _scraper_err = str(_e)

    _cache_set("coto", query, items)
    return items


def _scrape_dia(query: str, max_items: int = 10) -> list[dict]:
    """Dia Online — API REST."""
    if not _REQ:
        return []
    cached = _cache_get("dia", query)
    if cached is not None:
        return cached

    items = []
    try:
        s   = _session()
        url = "https://www.diasonline.com.ar/api/catalog_system/pub/products/search"
        params = {"ft": query, "_from": 0, "_to": max_items - 1}
        r = s.get(url, params=params, timeout=12)
        r.raise_for_status()
        for p in r.json()[:max_items]:
            try:
                precio = p["items"][0]["sellers"][0]["commertialOffer"]["Price"]
            except (KeyError, IndexError):
                precio = 0.0
            if precio <= 0:
                continue
            items.append({
                "fuente":  "Dia",
                "titulo":  p.get("productName", ""),
                "precio":  precio,
                "url":     f"https://www.diasonline.com.ar/{p.get('linkText','')}/p",
                "marca":   p.get("brand", ""),
                "imagen":  (p["items"][0]["images"][0]["imageUrl"]
                            if p.get("items") and p["items"][0].get("images") else ""),
            })
    except Exception as _e:
        _scraper_err = str(_e)

    _cache_set("dia", query, items)
    return items


def _scrape_jumbo(query: str, max_items: int = 10) -> list[dict]:
    """Jumbo AR — API REST (misma plataforma VTEX que Dia/Carrefour)."""
    if not _REQ:
        return []
    cached = _cache_get("jumbo", query)
    if cached is not None:
        return cached

    items = []
    try:
        s   = _session()
        url = "https://www.jumbo.com.ar/api/catalog_system/pub/products/search"
        params = {"ft": query, "_from": 0, "_to": max_items - 1}
        r = s.get(url, params=params, timeout=12)
        r.raise_for_status()
        for p in r.json()[:max_items]:
            try:
                precio = p["items"][0]["sellers"][0]["commertialOffer"]["Price"]
            except (KeyError, IndexError):
                precio = 0.0
            if precio <= 0:
                continue
            items.append({
                "fuente":  "Jumbo",
                "titulo":  p.get("productName", ""),
                "precio":  precio,
                "url":     f"https://www.jumbo.com.ar/{p.get('linkText','')}/p",
                "marca":   p.get("brand", ""),
                "imagen":  (p["items"][0]["images"][0]["imageUrl"]
                            if p.get("items") and p["items"][0].get("images") else ""),
            })
    except Exception as _e:
        _scraper_err = str(_e)

    _cache_set("jumbo", query, items)
    return items


def _scrape_changomas(query: str, max_items: int = 10) -> list[dict]:
    """Changomas / Walmart AR — VTEX."""
    if not _REQ:
        return []
    cached = _cache_get("changomas", query)
    if cached is not None:
        return cached

    items = []
    try:
        s   = _session()
        url = "https://www.changomas.com.ar/api/catalog_system/pub/products/search"
        params = {"ft": query, "_from": 0, "_to": max_items - 1}
        r = s.get(url, params=params, timeout=12)
        r.raise_for_status()
        for p in r.json()[:max_items]:
            try:
                precio = p["items"][0]["sellers"][0]["commertialOffer"]["Price"]
            except (KeyError, IndexError):
                precio = 0.0
            if precio <= 0:
                continue
            items.append({
                "fuente":  "Changomas",
                "titulo":  p.get("productName", ""),
                "precio":  precio,
                "url":     f"https://www.changomas.com.ar/{p.get('linkText','')}/p",
                "marca":   p.get("brand", ""),
                "imagen":  "",
            })
    except Exception as _e:
        _scraper_err = str(_e)

    _cache_set("changomas", query, items)
    return items


def _scrape_makro(query: str, max_items: int = 10) -> list[dict]:
    """Makro AR — scraping HTML."""
    if not _REQ or not _BS4:
        return []
    cached = _cache_get("makro", query)
    if cached is not None:
        return cached

    items = []
    try:
        s   = _session()
        url = f"https://www.makro.com.ar/search?q={requests.utils.quote(query)}"
        r   = s.get(url, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for card in soup.select("[class*='product'], [class*='item']")[:max_items * 2]:
            nombre = card.select_one("[class*='name'], [class*='title'], h3")
            precio = card.select_one("[class*='price'], [class*='precio']")
            if not nombre or not precio:
                continue
            p = _parse_precio(precio.get_text())
            if p <= 0:
                continue
            items.append({
                "fuente":  "Makro",
                "titulo":  nombre.get_text(strip=True),
                "precio":  p,
                "url":     "https://www.makro.com.ar",
                "marca":   "",
                "imagen":  "",
            })
            if len(items) >= max_items:
                break
    except Exception as _e:
        _scraper_err = str(_e)

    _cache_set("makro", query, items)
    return items


def _scrape_google_shopping(query: str, max_items: int = 10) -> list[dict]:
    """
    Google Shopping — scraping del HTML de resultados.
    Más robusto que una API pagada para uso ocasional.
    """
    if not _REQ or not _BS4:
        return []
    cached = _cache_get("google_shopping", query)
    if cached is not None:
        return cached

    items = []
    try:
        s    = _session()
        q_enc = requests.utils.quote(f"{query} precio argentina")
        url  = f"https://www.google.com/search?q={q_enc}&tbm=shop&hl=es&gl=ar"
        r    = s.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        # Google Shopping cards
        for card in soup.select(".sh-dgr__content, .Xjkr3b, [class*='sh-dlr']")[:max_items]:
            nombre = card.select_one("h3, .tAxDx, [aria-label]")
            precio_el = card.select_one(".a8Pemb, .kHxwFf, [class*='price']")
            tienda = card.select_one(".aULzUe, .E5ocAb, [class*='merchant']")
            if not nombre or not precio_el:
                continue
            p = _parse_precio(precio_el.get_text())
            if p <= 0:
                continue
            items.append({
                "fuente":  f"Google Shopping ({tienda.get_text(strip=True) if tienda else 'tienda'})",
                "titulo":  nombre.get_text(strip=True),
                "precio":  p,
                "url":     "",
                "marca":   "",
                "imagen":  "",
            })
    except Exception as _e:
        _scraper_err = str(_e)

    _cache_set("google_shopping", query, items)
    return items


# ══════════════════════════════════════════════════════════════
# LECTOR DE LISTAS DE PROVEEDORES (PDF / Excel)
# ══════════════════════════════════════════════════════════════

def leer_lista_proveedor(
    ruta: str,
    col_descripcion: str = None,
    col_precio: str = None,
    log_func: LogFunc = None,
) -> list[dict]:
    """
    Lee una lista de precios de proveedor (Excel o PDF) y retorna
    lista de {titulo, precio, fuente, marca}.

    Para Excel: detecta automáticamente las columnas de descripción y precio.
    Para PDF: extrae tablas con pdfplumber.
    """
    def _log(m):
        if log_func: log_func(m)

    ruta_p = Path(ruta)
    ext    = ruta_p.suffix.lower()
    fuente = f"Proveedor ({ruta_p.name})"
    items  = []

    if ext in [".xlsx", ".xls", ".csv"]:
        try:
            import pandas as pd
            df = pd.read_excel(ruta, engine="openpyxl") if ext != ".csv" else pd.read_csv(ruta)

            # Auto-detectar columnas
            cols_lower = {c.lower(): c for c in df.columns}
            col_desc = col_descripcion
            col_prec = col_precio

            if not col_desc:
                for cand in ["descripcion","descripción","articulo","artículo","producto","nombre","desc"]:
                    if cand in cols_lower:
                        col_desc = cols_lower[cand]; break
                if not col_desc:
                    col_desc = df.columns[0]

            if not col_prec:
                for cand in ["precio","price","costo","pvp","p.vta","p. vta","importe","valor"]:
                    if cand in cols_lower:
                        col_prec = cols_lower[cand]; break
                if not col_prec:
                    # Buscar primera columna numérica
                    for c in df.columns:
                        if pd.to_numeric(df[c], errors='coerce').notna().sum() > len(df) * 0.5:
                            col_prec = c; break

            if not col_desc or not col_prec:
                _log(f"  ⚠ No se detectaron columnas en {ruta_p.name}")
                return []

            _log(f"  📋 {ruta_p.name}: usando '{col_desc}' (desc) y '{col_prec}' (precio)")
            import numpy as np
            for _, row in df.iterrows():
                titulo = str(row[col_desc]).strip()
                precio = float(pd.to_numeric(row[col_prec], errors='coerce') or 0)
                if not titulo or titulo in ["nan", "None"] or precio <= 0:
                    continue
                items.append({"fuente": fuente, "titulo": titulo,
                               "precio": precio, "url": "", "marca": ""})

        except Exception as e:
            _log(f"  ❌ Error leyendo Excel: {e}")

    elif ext == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(ruta) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        if not table or len(table) < 2:
                            continue
                        # Usar primera fila como header si parece texto
                        header = [str(c).lower().strip() for c in table[0]]
                        desc_idx = next((i for i, h in enumerate(header)
                                        if any(k in h for k in ["desc","articu","produc","nombre"])), 0)
                        prec_idx = next((i for i, h in enumerate(header)
                                        if any(k in h for k in ["precio","costo","pvp","valor","importe"])), -1)
                        if prec_idx == -1:
                            # Buscar última columna numérica
                            for i in range(len(header)-1, -1, -1):
                                sample = [row[i] for row in table[1:5] if len(row) > i and row[i]]
                                if any(_parse_precio(str(s)) > 0 for s in sample):
                                    prec_idx = i; break
                        if prec_idx == -1:
                            continue
                        for row in table[1:]:
                            if len(row) <= max(desc_idx, prec_idx):
                                continue
                            titulo = str(row[desc_idx] or "").strip()
                            precio = _parse_precio(str(row[prec_idx] or ""))
                            if titulo and precio > 0:
                                items.append({"fuente": fuente, "titulo": titulo,
                                              "precio": precio, "url": "", "marca": ""})
        except ImportError:
            _log("  ⚠ pdfplumber no instalado. Ejecutá: pip install pdfplumber")
        except Exception as e:
            _log(f"  ❌ Error leyendo PDF: {e}")

    _log(f"  ✅ {fuente}: {len(items)} productos cargados")
    return items


# ══════════════════════════════════════════════════════════════
# MATCHING INTELIGENTE CON IA
# ══════════════════════════════════════════════════════════════

def _similitud_basica(a: str, b: str) -> float:
    """Similitud simple por palabras comunes (sin IA)."""
    wa = set(re.sub(r'[^\w\s]', '', a.lower()).split())
    wb = set(re.sub(r'[^\w\s]', '', b.lower()).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def matching_ia(
    query_original: str,
    items_todas_fuentes: list[dict],
    umbral_similitud: float = 0.35,
    log_func: LogFunc = None,
) -> list[dict]:
    """
    Filtra y rankea items usando similitud semántica.
    Primero hace matching básico (rápido), luego para los borderline
    usa IA para confirmar si es el mismo producto.

    Retorna items ordenados por relevancia.
    """
    def _log(m):
        if log_func: log_func(m)

    if not items_todas_fuentes:
        return []

    # Paso 1: filtro rápido por similitud de palabras
    candidatos = []
    for item in items_todas_fuentes:
        sim = _similitud_basica(query_original, item["titulo"])
        item["_similitud"] = sim
        if sim >= umbral_similitud:
            candidatos.append(item)

    # Si hay pocos candidatos con umbral alto, bajar el umbral
    if len(candidatos) < 3:
        candidatos = [i for i in items_todas_fuentes if i["_similitud"] >= 0.15]

    # Paso 2: para los borderline (0.15-0.4), usar IA para confirmar
    borderline = [i for i in candidatos if 0.15 <= i["_similitud"] < 0.4]
    if borderline and len(borderline) <= 10:
        try:
            import requests as _req
            import os
            prompt = (
                f"Producto buscado: '{query_original}'\n\n"
                f"¿Cuáles de estos items son el mismo producto o equivalente directo? "
                f"Responde SOLO con una lista JSON de índices (0-based) de los que SÍ son equivalentes.\n\n"
                + "\n".join(f"{i}. {it['titulo']}" for i, it in enumerate(borderline))
            )
            r = _req.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 100,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=10,
            )
            if r.status_code == 200:
                texto = r.json()["content"][0]["text"]
                indices = json.loads(re.search(r'\[[\d,\s]*\]', texto).group())
                confirmados = [borderline[i] for i in indices if i < len(borderline)]
                # Reemplazar borderline con solo los confirmados por IA
                candidatos = [i for i in candidatos if i["_similitud"] >= 0.4] + confirmados
        except Exception:
            pass  # si IA falla, quedarse con el filtro básico

    # Ordenar: primero por similitud desc, luego por precio asc
    candidatos.sort(key=lambda x: (-x["_similitud"], x["precio"]))
    _log(f"  🔗 Matching: {len(candidatos)} productos relevantes de {len(items_todas_fuentes)} totales")
    return candidatos



def _scrape_vea(query: str, max_items: int = 10) -> list[dict]:
    """Vea (Cencosud) — VTEX."""
    cached = _cache_get("vea", query)
    if cached is not None:
        return cached
    if not _REQ:
        return []
    try:
        url = "https://www.vea.com.ar/api/catalog_system/pub/products/search"
        r = _session().get(url, params={"ft": query, "_from": 0, "_to": max_items - 1}, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = []
        for p in (data if isinstance(data, list) else []):
            try:
                precio = float(p["items"][0]["sellers"][0]["commertialOffer"]["Price"])
            except (KeyError, IndexError, TypeError, ValueError):
                precio = 0.0
            titulo = p.get("productName") or p.get("productTitle", "")
            if not titulo:
                continue
            items.append({"fuente": "🛒 Vea", "titulo": titulo, "precio": precio,
                          "url": f"https://www.vea.com.ar/{p.get('linkText','')}/p",
                          "marca": p.get("brand", ""), "imagen": ""})
        _cache_set("vea", query, items)
        return items
    except Exception as _e:
        raise RuntimeError(f"Vea: {_e}") from _e


def _scrape_disco(query: str, max_items: int = 10) -> list[dict]:
    """Disco (Cencosud) — VTEX."""
    cached = _cache_get("disco", query)
    if cached is not None:
        return cached
    if not _REQ:
        return []
    try:
        url = "https://www.disco.com.ar/api/catalog_system/pub/products/search"
        r = _session().get(url, params={"ft": query, "_from": 0, "_to": max_items - 1}, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = []
        for p in (data if isinstance(data, list) else []):
            try:
                precio = float(p["items"][0]["sellers"][0]["commertialOffer"]["Price"])
            except (KeyError, IndexError, TypeError, ValueError):
                precio = 0.0
            titulo = p.get("productName") or p.get("productTitle", "")
            if not titulo:
                continue
            items.append({"fuente": "🛒 Disco", "titulo": titulo, "precio": precio,
                          "url": f"https://www.disco.com.ar/{p.get('linkText','')}/p",
                          "marca": p.get("brand", ""), "imagen": ""})
        _cache_set("disco", query, items)
        return items
    except Exception as _e:
        raise RuntimeError(f"Disco: {_e}") from _e


def _scrape_vital(query: str, max_items: int = 10) -> list[dict]:
    """Vital Mayorista — VTEX."""
    cached = _cache_get("vital", query)
    if cached is not None:
        return cached
    if not _REQ:
        return []
    try:
        url = "https://www.vital.com.ar/api/catalog_system/pub/products/search"
        r = _session().get(url, params={"ft": query, "_from": 0, "_to": max_items - 1}, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = []
        for p in (data if isinstance(data, list) else []):
            try:
                precio = float(p["items"][0]["sellers"][0]["commertialOffer"]["Price"])
            except (KeyError, IndexError, TypeError, ValueError):
                precio = 0.0
            titulo = p.get("productName") or p.get("productTitle", "")
            if not titulo:
                continue
            items.append({"fuente": "🏭 Vital", "titulo": titulo, "precio": precio,
                          "url": f"https://www.vital.com.ar/{p.get('linkText','')}/p",
                          "marca": p.get("brand", ""), "imagen": ""})
        _cache_set("vital", query, items)
        return items
    except Exception as _e:
        raise RuntimeError(f"Vital: {_e}") from _e


def _scrape_maxiconsumo(query: str, max_items: int = 10) -> list[dict]:
    """MaxiConsumo — VTEX mayorista."""
    cached = _cache_get("maxiconsumo", query)
    if cached is not None:
        return cached
    if not _REQ:
        return []
    try:
        url = "https://www.maxiconsumo.com/api/catalog_system/pub/products/search"
        r = _session().get(url, params={"ft": query, "_from": 0, "_to": max_items - 1}, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = []
        for p in (data if isinstance(data, list) else []):
            try:
                precio = float(p["items"][0]["sellers"][0]["commertialOffer"]["Price"])
            except (KeyError, IndexError, TypeError, ValueError):
                precio = 0.0
            titulo = p.get("productName") or p.get("productTitle", "")
            if not titulo:
                continue
            items.append({"fuente": "🏭 MaxiConsumo", "titulo": titulo, "precio": precio,
                          "url": f"https://www.maxiconsumo.com/{p.get('linkText','')}/p",
                          "marca": p.get("brand", ""), "imagen": ""})
        _cache_set("maxiconsumo", query, items)
        return items
    except Exception as _e:
        raise RuntimeError(f"MaxiConsumo: {_e}") from _e

# ══════════════════════════════════════════════════════════════
# MOTOR PRINCIPAL — BÚSQUEDA MULTI-FUENTE
# ══════════════════════════════════════════════════════════════

FUENTES_DISPONIBLES = {
    # ── Supermercados ──────────────────────────────────────
    "carrefour":       (_scrape_carrefour,      "🛒 Carrefour"),
    "coto":            (_scrape_coto,           "🛒 Coto"),
    "dia":             (_scrape_dia,            "🛒 Dia"),
    "jumbo":           (_scrape_jumbo,          "🛒 Jumbo"),
    "changomas":       (_scrape_changomas,      "🛒 Changomás"),
    "vea":             (_scrape_vea,            "🛒 Vea"),
    "disco":           (_scrape_disco,          "🛒 Disco"),
    # ── Mayoristas ─────────────────────────────────────────
    "makro":           (_scrape_makro,          "🏭 Makro"),
    "vital":           (_scrape_vital,          "🏭 Vital"),
    "maxiconsumo":     (_scrape_maxiconsumo,    "🏭 MaxiConsumo"),
    # ── Búsqueda web ───────────────────────────────────────
    "google_shopping": (_scrape_google_shopping,"🔍 Google Shopping"),
}


def buscar_multifuente(
    query: str,
    fuentes: list[str] = None,
    max_items_por_fuente: int = 8,
    listas_proveedor: list[str] = None,
    usar_matching_ia: bool = False,  # desactivado por defecto — filtraba demasiado
    timeout_fuente: float = 15.0,
    log_func: LogFunc = None,
) -> dict:
    """
    Busca un producto en todas las fuentes en paralelo.

    Args:
        query:                Descripción del producto a buscar
        fuentes:              Lista de keys de FUENTES_DISPONIBLES (None = todas)
        max_items_por_fuente: Máx resultados por fuente
        listas_proveedor:     Lista de rutas a Excel/PDF de proveedores
        usar_matching_ia:     Si True, usa IA para filtrar resultados relevantes
        timeout_fuente:       Segundos máximos por fuente

    Retorna dict con:
        items_por_fuente: {fuente: [items]}
        items_todos:      lista plana con todos los items relevantes
        estadisticas:     precios min/max/mediana por fuente
        fuentes_ok:       fuentes que respondieron
        fuentes_error:    fuentes que fallaron
    """
    def _log(m):
        if log_func: log_func(m)

    if not _REQ:
        return {"error": "requests no instalado. pip install requests beautifulsoup4"}

    fuentes_a_usar = fuentes or list(FUENTES_DISPONIBLES.keys())
    # Construir queries: búsqueda completa + palabras clave individuales
    palabras_sig = [p for p in query.split() if len(p) > 2]
    queries_a_buscar = list(dict.fromkeys([query] + palabras_sig))  # sin duplicados
    _log(f"🔍 Buscando '{query}' en {len(fuentes_a_usar)} fuente(s)")
    _log(f"   Palabras clave: {', '.join(palabras_sig)}")
    if listas_proveedor:
        _log(f"   + {len(listas_proveedor)} lista(s) de proveedor")

    items_por_fuente = {}
    fuentes_ok    = []
    fuentes_error = []

    # ── Scrapers en paralelo ──────────────────────────────────
    def _run_scraper(key):
        fn, nombre = FUENTES_DISPONIBLES[key]
        # Buscar con query completo + palabras individuales, mergear resultados
        todos = {}
        for q in queries_a_buscar:
            try:
                parcial = fn(q, max_items_por_fuente)
                for item in parcial:
                    k = item["titulo"].lower()[:60]
                    if k not in todos:
                        todos[k] = item
            except Exception as e:
                return key, nombre, [], str(e)
        return key, nombre, list(todos.values()), None

    with ThreadPoolExecutor(max_workers=len(fuentes_a_usar)) as pool:
        futuros = {pool.submit(_run_scraper, k): k for k in fuentes_a_usar
                   if k in FUENTES_DISPONIBLES}
        for fut in as_completed(futuros, timeout=timeout_fuente * 1.5):
            try:
                key, nombre, result, err = fut.result(timeout=timeout_fuente)
                if err:
                    fuentes_error.append(f"{nombre}: {err[:80]}")
                    _log(f"  ❌ {nombre}: {err[:80]}")
                elif result:
                    items_por_fuente[nombre] = result
                    fuentes_ok.append(nombre)
                    _log(f"  ✅ {nombre}: {len(result)} producto(s)")
                else:
                    fuentes_error.append(f"{nombre}: sin resultados")
                    _log(f"  ⚠  {nombre}: sin resultados")
            except Exception as e:
                fuentes_error.append(f"timeout/error: {str(e)[:40]}")
                _log(f"  ⏱  timeout en alguna fuente: {str(e)[:40]}")

    # ── Listas de proveedores ─────────────────────────────────
    for ruta_prov in (listas_proveedor or []):
        try:
            items_prov = leer_lista_proveedor(ruta_prov, log_func=log_func)
            # Filtrar por similitud básica
            relevantes = [i for i in items_prov
                          if _similitud_basica(query, i["titulo"]) >= 0.15]  # permisivo — incluir coincidencias parciales
            if relevantes:
                nombre_prov = items_prov[0]["fuente"] if items_prov else "Proveedor"
                items_por_fuente[nombre_prov] = relevantes
                fuentes_ok.append(nombre_prov)
                _log(f"  ✅ {nombre_prov}: {len(relevantes)} coincidencias")
        except Exception as e:
            fuentes_error.append(f"Proveedor: {str(e)[:60]}")

    # ── Todos los items planos ────────────────────────────────
    items_todos = [item for items in items_por_fuente.values() for item in items]

    # ── Matching IA ───────────────────────────────────────────
    if usar_matching_ia and items_todos:
        items_todos = matching_ia(query, items_todos, log_func=log_func)
        # Reconstruir por fuente con solo los filtrados
        titulos_ok = {i["titulo"] for i in items_todos}
        items_por_fuente = {
            f: [i for i in items if i["titulo"] in titulos_ok]
            for f, items in items_por_fuente.items()
        }
        items_por_fuente = {f: v for f, v in items_por_fuente.items() if v}

    # ── Estadísticas por fuente ───────────────────────────────
    estadisticas = {}
    for fuente, items in items_por_fuente.items():
        precios = sorted([i["precio"] for i in items if i["precio"] > 0])
        if not precios:
            continue
        n = len(precios)
        estadisticas[fuente] = {
            "min":     precios[0],
            "max":     precios[-1],
            "mediana": precios[n // 2],
            "promedio":round(sum(precios) / n, 2),
            "n":       n,
        }

    # ── Precio de mercado global ──────────────────────────────
    todos_precios = sorted([i["precio"] for i in items_todos if i["precio"] > 0])
    n = len(todos_precios)
    mercado = {
        "min":         todos_precios[0]    if todos_precios else 0,
        "max":         todos_precios[-1]   if todos_precios else 0,
        "mediana":     todos_precios[n//2] if todos_precios else 0,
        "promedio":    round(sum(todos_precios)/n, 2) if todos_precios else 0,
        "n_total":     n,
        "n_fuentes":   len(fuentes_ok),
    }

    _log(f"\n  📊 Total: {n} precios de {len(fuentes_ok)} fuente(s)")
    if mercado["mediana"] > 0:
        _log(f"  💰 Mediana mercado: ${mercado['mediana']:,.0f} | Rango: ${mercado['min']:,.0f}–${mercado['max']:,.0f}")

    return {
        "query":           query,
        "items_por_fuente":items_por_fuente,
        "items_todos":     items_todos,
        "estadisticas":    estadisticas,
        "mercado":         mercado,
        "fuentes_ok":      fuentes_ok,
        "fuentes_error":   fuentes_error,
        "timestamp":       datetime.now().isoformat(),
    }


# ══════════════════════════════════════════════════════════════
# COMPARACIÓN TU PRECIO vs MERCADO
# ══════════════════════════════════════════════════════════════

def comparar_precio_vs_mercado(
    tu_precio: float,
    tu_costo: float,
    resultado_multifuente: dict,
    margen_minimo_pct: float = 15.0,
) -> dict:
    """
    Compara tu precio contra el mercado y calcula:
    - Si estás caro, barato o en línea
    - Tu margen actual
    - Precio sugerido para ser competitivo con margen mínimo
    - Oportunidad de subir precio sin perder competitividad
    """
    mercado = resultado_multifuente.get("mercado", {})
    med     = mercado.get("mediana", 0)
    minimo  = mercado.get("min", 0)

    if med <= 0:
        return {"estado": "sin_datos", "mensaje": "Sin precios de mercado para comparar"}

    # Posición relativa
    diff_pct = (tu_precio - med) / med * 100 if med > 0 else 0

    if diff_pct > 10:
        estado = "🔴 MUY CARO"
    elif diff_pct > 3:
        estado = "🟡 ALGO CARO"
    elif diff_pct < -10:
        estado = "🔵 MUY BARATO"
    elif diff_pct < -3:
        estado = "🟢 COMPETITIVO BAJO"
    else:
        estado = "✅ EN LÍNEA"

    # Margen actual
    margen_actual = (tu_precio - tu_costo) / tu_precio * 100 if tu_precio > 0 else 0
    margen_sobre_costo = (tu_precio - tu_costo) / tu_costo * 100 if tu_costo > 0 else 0

    # Precio mínimo para cubrir margen sobre mediana de mercado
    precio_con_margen  = tu_costo * (1 + margen_minimo_pct / 100)
    precio_competitivo = min(med * 0.98, mercado.get("max", med))  # 2% bajo la mediana

    # Oportunidad de subida
    precio_oportunidad = None
    if diff_pct < -5 and tu_precio < med * 0.93:
        precio_oportunidad = round(med * 0.97, 2)  # subir hasta 3% bajo mediana

    # Alerta de pérdida
    perdida = tu_precio < tu_costo if tu_costo > 0 else False

    return {
        "estado":              estado,
        "tu_precio":           tu_precio,
        "tu_costo":            tu_costo,
        "precio_mediana_mkt":  med,
        "precio_min_mkt":      minimo,
        "diff_pct":            round(diff_pct, 1),
        "margen_actual_pct":   round(margen_actual, 1),
        "margen_sobre_costo":  round(margen_sobre_costo, 1),
        "precio_sugerido":     round(precio_competitivo, 2),
        "precio_minimo_margen":round(precio_con_margen, 2),
        "oportunidad_subida":  precio_oportunidad,
        "perdida":             perdida,
        "n_fuentes":           mercado.get("n_fuentes", 0),
    }


# ══════════════════════════════════════════════════════════════
# ANÁLISIS MASIVO — LISTA COMPLETA vs MERCADO
# ══════════════════════════════════════════════════════════════

def analizar_lista_vs_mercado(
    items_lista: list[dict],
    fuentes: list[str] = None,
    listas_proveedor: list[str] = None,
    margen_minimo_pct: float = 15.0,
    max_workers: int = 3,
    delay_entre_items: float = 1.0,
    log_func: LogFunc = None,
) -> list[dict]:
    """
    Analiza una lista completa de artículos contra el mercado multi-fuente.

    items_lista: lista de dicts con keys: descripcion, tu_precio, tu_costo
    Retorna lista con comparacion_precio_vs_mercado para cada item.
    """
    def _log(m):
        if log_func: log_func(m)

    resultados = []
    total = len(items_lista)

    for i, item in enumerate(items_lista, 1):
        desc      = item.get("descripcion", item.get("titulo", ""))
        tu_precio = float(item.get("tu_precio", 0) or 0)
        tu_costo  = float(item.get("tu_costo", 0) or 0)

        _log(f"\n  [{i}/{total}] {desc[:50]}")

        res_mf = buscar_multifuente(
            query=desc,
            fuentes=fuentes,
            listas_proveedor=listas_proveedor,
            usar_matching_ia=True,
            log_func=log_func,
        )

        comparacion = comparar_precio_vs_mercado(
            tu_precio=tu_precio,
            tu_costo=tu_costo,
            resultado_multifuente=res_mf,
            margen_minimo_pct=margen_minimo_pct,
        )

        resultados.append({
            "descripcion":   desc,
            **comparacion,
            "fuentes_ok":    res_mf.get("fuentes_ok", []),
            "mercado_raw":   res_mf.get("mercado", {}),
        })

        if i < total:
            time.sleep(delay_entre_items)

    _log(f"\n  ✅ Análisis completo: {total} artículos procesados")
    return resultados
