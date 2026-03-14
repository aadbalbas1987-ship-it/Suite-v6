"""
tools/pricing_research.py — RPA Suite v5.5
============================================
Motor de Pricing Analysis y Market Research.

NUEVO en v5.5:
  - expansor_queries_ia(): Claude genera variantes antes de buscar en ML
  - analisis_marca_ia(): análisis completo de marca/producto con IA
  - precio_optimo_ia(): precio sugerido dado costo + competencia ML
  - busqueda_masiva_desde_excel(): procesa lista interna completa
  - semaforo de competitividad en analizar_precios
  - Fallback robusto si pytrends falla
"""

import json
import time
import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Callable

try:
    from pytrends.request import TrendReq as _TrendReq
    PYTRENDS_OK = True
except ImportError:
    _TrendReq = None
    PYTRENDS_OK = False

_ROOT        = Path(__file__).parent.parent
_PRICING_DIR = _ROOT / "pricing_data"
_PRICING_DIR.mkdir(exist_ok=True)
_SNAPSHOTS_FILE = _PRICING_DIR / "snapshots.json"
_HISTORY_FILE   = _PRICING_DIR / "price_history.json"

LogFunc = Optional[Callable[[str], None]]

def _log(msg, log_func=None):
    if log_func: log_func(msg)
    else: print(msg)

def _ia_post(prompt, max_tokens=400):
    """
    Llama a la API de IA con fallback automático:
    1. Anthropic Claude (principal)
    2. Groq (fallback si Claude falla o no tiene key)
    """
    import requests
    import os

    # ── Intento 1: Anthropic Claude ──────────────────────────
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": max_tokens,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception as e_claude:
        pass  # intentar Groq

    # ── Intento 2: Groq (fallback) ───────────────────────────
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}",
                         "Content-Type": "application/json"},
                json={"model": "llama3-8b-8192", "max_tokens": max_tokens,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e_groq:
            raise RuntimeError(f"Claude falló y Groq también falló: {e_groq}")

    raise RuntimeError("Sin API disponible. Configurá GROQ_API_KEY en .env como fallback.")

# ══════════════════════════════════════════════════════════════
# EXPANSOR DE QUERIES CON IA
# ══════════════════════════════════════════════════════════════

def expansor_queries_ia(termino, contexto="distribuidora mayorista Argentina", n_variantes=5, log_func=None):
    _log(f"🤖 Expandiendo: '{termino}'...", log_func)
    prompt = f"""Para una {contexto}, generá {n_variantes} variantes de búsqueda para MercadoLibre Argentina del producto: "{termino}"
Considerá presentaciones, tamaños, sabores, nombres alternativos.
Respondé SOLO con JSON array de strings, sin markdown ni explicaciones.
Ejemplo: ["término 1", "término 2"]"""
    try:
        texto = _ia_post(prompt, 300)
        texto = re.sub(r"```json|```", "", texto).strip()
        variantes = json.loads(texto)
        if isinstance(variantes, list) and variantes:
            _log(f"  ✅ {len(variantes)} variantes", log_func)
            for v in variantes: _log(f"     → {v}", log_func)
            return variantes
    except Exception as e:
        _log(f"  ⚠ IA no disponible: {e}", log_func)
    return [termino]

def expansor_lista_ia(terminos, contexto="distribuidora mayorista Argentina", log_func=None):
    if not terminos: return {}
    _log(f"🤖 Expandiendo {len(terminos)} términos...", log_func)
    lista_str = "\n".join(f"- {t}" for t in terminos)
    prompt = f"""Para una {contexto}, generá 3 variantes de búsqueda en MercadoLibre Argentina para cada producto:
{lista_str}
Respondé SOLO con JSON object. Clave=término original, valor=array de 3 strings.
Sin markdown ni explicaciones."""
    try:
        texto = _ia_post(prompt, 800)
        texto = re.sub(r"```json|```", "", texto).strip()
        resultado = json.loads(texto)
        if isinstance(resultado, dict):
            _log("  ✅ Expansión completa", log_func)
            return resultado
    except Exception as e:
        _log(f"  ⚠ IA no disponible: {e}", log_func)
    return {t: [t] for t in terminos}

# ══════════════════════════════════════════════════════════════
# SCRAPING
# ══════════════════════════════════════════════════════════════

def scrape_mercadolibre(query, max_items=20, precio_min=None, precio_max=None, min_ventas=0, log_func=None):
    try: import requests
    except ImportError: return []
    _log(f"  🛒 ML: '{query}'...", log_func)
    params = {"q": query, "limit": min(max_items, 50), "condition": "new"}
    if precio_min: params["price_min"] = precio_min
    if precio_max: params["price_max"] = precio_max
    try:
        resp = requests.get("https://api.mercadolibre.com/sites/MLA/search",
                            params=params, headers={"User-Agent": "RPASuite/5.5"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        _log(f"  ❌ Error ML: {e}", log_func)
        return []
    resultados = []
    for item in data.get("results", []):
        try:
            precio = item.get("price", 0)
            vendidos = item.get("sold_quantity", 0)
            if not precio: continue
            if min_ventas and vendidos < min_ventas: continue
            resultados.append({
                "id_ml": item.get("id", ""), "titulo": item.get("title", ""),
                "precio": float(precio), "moneda": item.get("currency_id", "ARS"),
                "vendedor": item.get("seller", {}).get("nickname", ""),
                "condicion": item.get("condition", ""),
                "disponibles": item.get("available_quantity", 0),
                "vendidos": vendidos, "url": item.get("permalink", ""),
                "thumbnail": item.get("thumbnail", ""),
                "fecha": datetime.now().isoformat(), "query": query,
            })
        except Exception: continue
    _log(f"     → {len(resultados)} resultados", log_func)
    return resultados

def scrape_multiple_queries(queries, max_por_query=15, log_func=None, **kwargs):
    resultados = {}
    for i, q in enumerate(queries, 1):
        resultados[q] = scrape_mercadolibre(q, max_por_query, log_func=log_func, **kwargs)
        if i < len(queries): time.sleep(0.8)
    return resultados

def scrape_con_expansion_ia(termino, max_items=20, contexto="distribuidora mayorista Argentina", log_func=None):
    _log(f"🔍 Buscando: '{termino}'", log_func)
    variantes = expansor_queries_ia(termino, contexto, log_func=log_func)
    ml_data   = scrape_multiple_queries(variantes, max_items, log_func)
    todos = [item for items in ml_data.values() for item in items]
    vistos, unicos = set(), []
    for item in todos:
        if item["id_ml"] not in vistos:
            vistos.add(item["id_ml"]); unicos.append(item)
    precios = [i["precio"] for i in unicos if i["precio"] > 0]
    resumen = {
        "termino_original": termino, "variantes_buscadas": variantes,
        "total_resultados": len(unicos),
        "precio_min":      min(precios) if precios else 0,
        "precio_max":      max(precios) if precios else 0,
        "precio_promedio": round(sum(precios)/len(precios), 2) if precios else 0,
        "precio_mediana":  sorted(precios)[len(precios)//2] if precios else 0,
        "items": unicos, "por_variante": ml_data,
    }
    _log(f"  ✅ '{termino}': {len(unicos)} únicos — "
         f"${resumen['precio_min']:,.0f} a ${resumen['precio_max']:,.0f}", log_func)
    return resumen

# ══════════════════════════════════════════════════════════════
# ANÁLISIS IA
# ══════════════════════════════════════════════════════════════

def analisis_marca_ia(termino, resumen_ml, contexto="distribuidora mayorista Argentina", log_func=None):
    _log("🤖 Analizando marca con IA...", log_func)
    items = resumen_ml.get("items", [])[:15]
    items_str = "\n".join(
        f"- {i['titulo']} | ${i['precio']:,.0f} | Vendidos: {i['vendidos']}"
        for i in items)
    prompt = f"""Experto en pricing para {contexto}.
Búsqueda: "{termino}" en MercadoLibre Argentina.
Resultados: {resumen_ml.get('total_resultados',0)} productos.
Precios: ${resumen_ml.get('precio_min',0):,.0f} – ${resumen_ml.get('precio_max',0):,.0f} (mediana ${resumen_ml.get('precio_mediana',0):,.0f})

Productos encontrados:
{items_str}

Analizá en 5 puntos con bullets y negrita (máx 350 palabras):
1. **Perfil del producto/marca**
2. **Análisis de precios** (rango competitivo, referencia recomendada)
3. **Oportunidades** (qué conviene stockear, mejor rotación)
4. **Riesgo/Advertencias**
5. **Acción recomendada**"""
    try:
        texto = _ia_post(prompt, 800)
        _log("  ✅ Análisis generado", log_func)
        return texto
    except Exception as e:
        _log(f"  ❌ Error IA: {e}", log_func)
        return f"Error: {e}"

def precio_optimo_ia(termino, costo, resumen_ml, margen_minimo=0.15, contexto="distribuidora mayorista Argentina", log_func=None):
    _log("🤖 Calculando precio óptimo...", log_func)
    prompt = f"""Experto en pricing para {contexto}.
Producto: "{termino}" | Costo: ${costo:,.2f} | Margen mínimo: {margen_minimo*100:.0f}%
Precios ML: min=${resumen_ml.get('precio_min',0):,.0f} mediana=${resumen_ml.get('precio_mediana',0):,.0f} max=${resumen_ml.get('precio_max',0):,.0f}
Competidores: {resumen_ml.get('total_resultados',0)}

Respondé SOLO con JSON (sin markdown):
{{"precio_sugerido": <número>, "margen_pct": <0-100>, "posicionamiento": "BAJO|MEDIO|ALTO", "justificacion": "<1 oración>", "alerta": null}}"""
    try:
        texto = _ia_post(prompt, 200)
        texto = re.sub(r"```json|```", "", texto).strip()
        r = json.loads(texto)
        _log(f"  ✅ Precio óptimo: ${r.get('precio_sugerido',0):,.0f}", log_func)
        return r
    except Exception as e:
        _log(f"  ⚠ Fallback cálculo simple: {e}", log_func)
        p = round(costo / (1 - margen_minimo), 2)
        return {"precio_sugerido": p, "margen_pct": round(margen_minimo*100,1),
                "posicionamiento": "MEDIO", "justificacion": "Cálculo con margen mínimo (IA no disponible)", "alerta": None}

def recomendaciones_ia(analisis, contexto_negocio="distribuidora mayorista Argentina", log_func=None):
    _log("🤖 Generando recomendaciones...", log_func)
    stats   = analisis.get("estadisticas", {})
    alertas = analisis.get("alertas", [])[:10]
    df_comp = analisis.get("comparacion")
    resumen_alertas = "\n".join(
        f"- [{a['prioridad']}] {a['tipo']}: {a['articulo']} — {a['mensaje']}"
        for a in alertas) or "Sin alertas."
    top_margen = ""
    if df_comp is not None and not df_comp.empty and "margen_pct" in df_comp.columns:
        top5 = df_comp.nlargest(5,"margen_pct")[["articulo","margen_pct","precio_interno"]]
        low5 = df_comp.nsmallest(5,"margen_pct")[["articulo","margen_pct","precio_interno"]]
        top_margen = f"Top margen alto:\n{top5.to_string(index=False)}\nTop margen bajo:\n{low5.to_string(index=False)}"
    prompt = f"""Experto en pricing para {contexto_negocio}.
Artículos: {stats.get('total_articulos',0)} | Con ML: {stats.get('con_comparacion_ml',0)} | Alertas: {stats.get('alertas_total',0)} | Margen prom: {stats.get('margen_promedio','N/D')}%
{resumen_alertas}
{top_margen}
Recomendaciones concretas (máx 400 palabras):
1. Qué precios ajustar urgente
2. Oportunidades de margen
3. Estrategia general
4. 3 acciones inmediatas"""
    try:
        texto = _ia_post(prompt, 1000)
        _log("  ✅ Recomendaciones generadas", log_func)
        return texto
    except Exception as e:
        return f"Error: {e}"

# ══════════════════════════════════════════════════════════════
# ANÁLISIS COMPARATIVO
# ══════════════════════════════════════════════════════════════

def analizar_precios(df_interno, resultados_ml, margen_minimo=0.15, umbral_desactualizacion=0.10, log_func=None):
    try: import pandas as pd
    except ImportError: return {}
    _log("📊 Analizando precios...", log_func)
    alertas, rows = [], []
    ml_stats = {}
    for query, items in resultados_ml.items():
        precios = [i["precio"] for i in items if i["precio"] > 0]
        if precios:
            ml_stats[query] = {
                "precio_min": min(precios), "precio_max": max(precios),
                "precio_promedio": sum(precios)/len(precios),
                "precio_mediana": sorted(precios)[len(precios)//2],
                "n_competidores": len(precios), "items": items,
            }
    for _, row in df_interno.iterrows():
        articulo = str(row.get("articulo", row.get("descripcion", "Sin nombre")))
        precio_i = float(row.get("precio_venta", row.get("precio", 0)) or 0)
        costo    = float(row.get("costo", 0) or 0)
        if precio_i <= 0: continue
        margen_pct = ((precio_i - costo) / precio_i) if costo > 0 else None
        mejor_match, mejor_score = None, 0
        for query, stats in ml_stats.items():
            comunes = set(articulo.lower().split()) & set(query.lower().split())
            score   = len(comunes) / max(len(query.lower().split()), 1)
            if score > mejor_score and score > 0.3:
                mejor_score = score; mejor_match = (query, stats)
        fila = {"articulo": articulo, "precio_interno": precio_i, "costo": costo,
                "margen_pct": round(margen_pct*100,1) if margen_pct is not None else None}
        if mejor_match:
            q, stats = mejor_match
            med = stats["precio_mediana"]
            dif = (precio_i - med) / med
            fila.update({
                "precio_ml_min": round(stats["precio_min"],2), "precio_ml_max": round(stats["precio_max"],2),
                "precio_ml_med": round(med,2), "n_competidores": stats["n_competidores"],
                "diferencia_pct": round(dif*100,1), "match_query": q,
                "semaforo": ("🔴 MUY CARO" if dif>0.25 else "🟡 ALGO CARO" if dif>0.10
                             else "🟢 COMPETITIVO" if dif>=-0.10 else "🔵 BAJO ML"),
            })
            if dif > umbral_desactualizacion:
                alertas.append({"tipo":"PRECIO_ALTO","articulo":articulo,"prioridad":"ALTA" if dif>0.25 else "MEDIA",
                                 "mensaje":f"Precio {dif*100:.1f}% sobre ML"})
            elif dif < -umbral_desactualizacion:
                alertas.append({"tipo":"OPORTUNIDAD","articulo":articulo,"prioridad":"MEDIA",
                                 "mensaje":f"Precio {abs(dif)*100:.1f}% bajo ML — podés subir"})
        else:
            fila.update({"precio_ml_min":None,"precio_ml_max":None,"precio_ml_med":None,
                         "n_competidores":0,"diferencia_pct":None,"match_query":None,"semaforo":"⚪ SIN DATOS"})
        if margen_pct is not None and margen_pct < margen_minimo:
            alertas.append({"tipo":"MARGEN_BAJO","articulo":articulo,"prioridad":"ALTA",
                             "mensaje":f"Margen {margen_pct*100:.1f}% bajo mínimo"})
        rows.append(fila)
    import pandas as pd
    df_comp = pd.DataFrame(rows)
    return {
        "comparacion": df_comp,
        "alertas": alertas,
        "ranking_margen": df_comp[df_comp["margen_pct"].notna()].sort_values("margen_pct",ascending=False),
        "estadisticas": {
            "total_articulos": len(df_comp),
            "con_comparacion_ml": int(df_comp["precio_ml_med"].notna().sum()) if "precio_ml_med" in df_comp else 0,
            "alertas_total": len(alertas),
            "alertas_alta": sum(1 for a in alertas if a["prioridad"]=="ALTA"),
            "margen_promedio": round(df_comp["margen_pct"].mean(),1) if "margen_pct" in df_comp else None,
            "fecha_analisis": datetime.now().isoformat(),
        },
        "ml_stats": ml_stats,
    }

# ══════════════════════════════════════════════════════════════
# BÚSQUEDA MASIVA
# ══════════════════════════════════════════════════════════════

def busqueda_masiva_desde_excel(df, col_nombre="articulo", col_costo="costo",
                                 max_por_producto=10, usar_ia=True,
                                 contexto="distribuidora mayorista Argentina", log_func=None):
    nombres = df[col_nombre].dropna().astype(str).tolist()[:20]
    _log(f"📋 Búsqueda masiva: {len(nombres)} artículos", log_func)
    mapa = expansor_lista_ia(nombres, contexto, log_func) if usar_ia else {n:[n] for n in nombres}
    resultados = {}
    for i, nombre in enumerate(nombres, 1):
        _log(f"[{i}/{len(nombres)}] {nombre}", log_func)
        variantes = mapa.get(nombre, [nombre])
        ml_data   = scrape_multiple_queries(variantes, max_por_producto, log_func)
        todos = [item for items in ml_data.values() for item in items]
        vistos, unicos = set(), []
        for item in todos:
            if item["id_ml"] not in vistos: vistos.add(item["id_ml"]); unicos.append(item)
        precios = [i["precio"] for i in unicos if i["precio"] > 0]
        resultados[nombre] = {
            "variantes": variantes, "total": len(unicos),
            "precio_min": min(precios) if precios else 0,
            "precio_max": max(precios) if precios else 0,
            "precio_promedio": round(sum(precios)/len(precios),2) if precios else 0,
            "precio_mediana": sorted(precios)[len(precios)//2] if precios else 0,
            "items": unicos,
        }
        time.sleep(0.5)
    _log(f"✅ Masiva completa: {len(resultados)} artículos", log_func)
    return resultados

# ══════════════════════════════════════════════════════════════
# TENDENCIAS + RANKING
# ══════════════════════════════════════════════════════════════

def obtener_tendencias_pytrends(keywords, timeframe="today 3-m", log_func=None):
    if not PYTRENDS_OK:
        _log("⚠ pytrends no instalado (pip install pytrends)", log_func)
        return {}
    _log(f"📈 Google Trends: {keywords}...", log_func)
    try:
        pt = _TrendReq(hl="es-AR", tz=-180, timeout=(10,25))
        resultado = {}
        for chunk in [keywords[i:i+5] for i in range(0,len(keywords),5)]:
            try:
                pt.build_payload(chunk, timeframe=timeframe, geo="AR")
                df = pt.interest_over_time()
                if not df.empty:
                    for kw in chunk:
                        if kw in df.columns:
                            resultado[kw] = {
                                "promedio": round(float(df[kw].mean()),1),
                                "maximo": int(df[kw].max()),
                                "tendencia": "SUBE" if df[kw].iloc[-1]>df[kw].iloc[0] else "BAJA",
                                "serie": df[kw].tolist(),
                            }
                time.sleep(2)
            except Exception: continue
        return resultado
    except Exception as e:
        _log(f"⚠ Google Trends no disponible: {e}", log_func)
        return {}

def ranking_mas_vendidos_ml(categoria="electronica", max_items=30, log_func=None):
    try: import requests
    except ImportError: return []
    _log(f"🏆 Ranking: {categoria}...", log_func)
    try:
        resp = requests.get("https://api.mercadolibre.com/sites/MLA/search",
                            params={"q":categoria,"sort":"sold_quantity_desc","limit":min(max_items,50),"condition":"new"},
                            timeout=15)
        resp.raise_for_status()
        return [{
            "posicion": i+1, "titulo": it.get("title",""), "precio": it.get("price",0),
            "vendidos": it.get("sold_quantity",0), "disponibles": it.get("available_quantity",0),
            "vendedor": it.get("seller",{}).get("nickname",""),
            "thumbnail": it.get("thumbnail",""), "url": it.get("permalink",""),
        } for i, it in enumerate(resp.json().get("results",[])[:max_items])]
    except Exception as e:
        _log(f"❌ Error ranking: {e}", log_func)
        return []

# ══════════════════════════════════════════════════════════════
# HISTORIAL
# ══════════════════════════════════════════════════════════════

def guardar_snapshot(resultados_ml, etiqueta="", log_func=None):
    historial = []
    if _HISTORY_FILE.exists():
        try: historial = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception: historial = []
    historial.append({"fecha":datetime.now().isoformat(),"etiqueta":etiqueta or date.today().isoformat(),"datos":resultados_ml})
    historial = historial[-90:]
    _HISTORY_FILE.write_text(json.dumps(historial,ensure_ascii=False,indent=2),encoding="utf-8")
    _log(f"💾 Snapshot guardado ({len(historial)} en historial)", log_func)

def cargar_historial_precios(query):
    if not _HISTORY_FILE.exists(): return []
    try: historial = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception: return []
    serie = []
    for snap in historial:
        datos_q = snap["datos"].get(query,[])
        if datos_q:
            precios = [i["precio"] for i in datos_q if i["precio"]>0]
            if precios:
                serie.append({"fecha":snap["fecha"][:10],"precio_min":min(precios),
                               "precio_max":max(precios),"precio_promedio":round(sum(precios)/len(precios),2),"n":len(precios)})
    return serie

# ══════════════════════════════════════════════════════════════
# ORQUESTADOR
# ══════════════════════════════════════════════════════════════

def ejecutar_market_research(queries, df_interno=None, incluir_tendencias=False,
                              incluir_ia=True, max_por_query=20,
                              usar_expansion_ia=True,
                              contexto="distribuidora mayorista Argentina",
                              log_func=None):
    resultado = {}
    _log("─"*50, log_func)
    _log("🛒 FASE 1: Scraping MercadoLibre", log_func)
    if usar_expansion_ia and incluir_ia:
        resumenes = {q: scrape_con_expansion_ia(q, max_por_query, contexto, log_func) for q in queries}
        resultado["resumenes_ia"] = resumenes
        ml_data = {}
        for q, res in resumenes.items():
            for variante, items in res.get("por_variante",{}).items():
                ml_data[variante] = items
    else:
        ml_data = scrape_multiple_queries(queries, max_por_query, log_func)
    resultado["ml_data"] = ml_data
    if incluir_tendencias:
        _log("─"*50, log_func)
        _log("📈 FASE 2: Google Trends", log_func)
        resultado["tendencias"] = obtener_tendencias_pytrends(queries, log_func=log_func)
    if df_interno is not None:
        _log("─"*50, log_func)
        _log("📊 FASE 3: Análisis precios internos", log_func)
        resultado["analisis"] = analizar_precios(df_interno, ml_data, log_func=log_func)
    _log("─"*50, log_func)
    _log("🏆 FASE 4: Ranking más vendidos", log_func)
    resultado["ranking"] = ranking_mas_vendidos_ml(queries[0] if queries else "productos", log_func=log_func)
    if incluir_ia and "analisis" in resultado:
        _log("─"*50, log_func)
        _log("🤖 FASE 5: Recomendaciones IA", log_func)
        resultado["recomendaciones_ia"] = recomendaciones_ia(resultado["analisis"], contexto, log_func=log_func)
    guardar_snapshot(ml_data, log_func=log_func)
    _log("─"*50, log_func)
    _log("✅ Market Research completo.", log_func)
    return resultado

def exportar_excel(resultado, nombre="", log_func=None):
    try: import pandas as pd
    except ImportError: return ""
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _PRICING_DIR / f"pricing_research_{nombre or ts}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        an = resultado.get("analisis", {})
        if an.get("comparacion") is not None and not an["comparacion"].empty:
            an["comparacion"].to_excel(writer, sheet_name="Comparacion ML", index=False)
        if an.get("alertas"):
            pd.DataFrame(an["alertas"]).to_excel(writer, sheet_name="Alertas", index=False)
        if resultado.get("ranking"):
            pd.DataFrame(resultado["ranking"]).to_excel(writer, sheet_name="Ranking MasVendidos", index=False)
        ml_rows = [dict(**item, query_busqueda=q)
                   for q, items in resultado.get("ml_data",{}).items() for item in items]
        if ml_rows:
            pd.DataFrame(ml_rows).to_excel(writer, sheet_name="Precios ML", index=False)
        if resultado.get("recomendaciones_ia"):
            pd.DataFrame([{"Recomendaciones": resultado["recomendaciones_ia"]}]).to_excel(
                writer, sheet_name="Recomendaciones IA", index=False)
    _log(f"📂 Excel exportado: {path.name}", log_func)
    return str(path)

# ══════════════════════════════════════════════════════════════
# EXPORTAR PARA ROBOT DE PRECIOS  ← NUEVO v5.5
# ══════════════════════════════════════════════════════════════

def exportar_para_robot(
    items_con_precio: list[dict],
    archivo_destino: str = None,
    log_func: LogFunc = None,
) -> str:
    """
    Convierte resultados del Pricing Research al formato que espera
    el robot Precios_V2.py para carga directa.

    Formato de salida (columnas):
      A: SKU | B: Costo | C: Precio Salon | D: Precio Mayorista | E: Precio Galpon (opcional)

    items_con_precio: lista de dicts con keys:
      sku, costo, precio_salon, precio_mayorista, precio_galpon (opcional)

    Retorna: ruta del archivo generado.
    """
    try:
        import pandas as pd
    except ImportError:
        _log("❌ pandas no disponible", log_func)
        return ""

    if not items_con_precio:
        _log("❌ Sin items para exportar", log_func)
        return ""

    _log(f"📤 Generando archivo para robot de precios ({len(items_con_precio)} artículos)...", log_func)

    rows = []
    for item in items_con_precio:
        rows.append({
            "SKU":              item.get("sku", ""),
            "Costo":            item.get("costo", 0),
            "Precio Salon":     item.get("precio_salon", 0),
            "Precio Mayorista": item.get("precio_mayorista", 0),
            "Precio Galpon":    item.get("precio_galpon", 0),
        })

    df = pd.DataFrame(rows)

    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(archivo_destino) if archivo_destino else _PRICING_DIR / f"precios_{ts}.xlsx"

    df.to_excel(path, index=False, engine="openpyxl")
    _log(f"  ✅ Archivo robot generado: {path.name}", log_func)
    _log(f"     Copialo a input/ con nombre: precios_{ts}.xlsx", log_func)
    return str(path)


def exportar_precio_optimo_para_robot(
    resultados_optimos: dict,
    log_func: LogFunc = None,
) -> str:
    """
    Convierte el resultado de precio_optimo_ia() en lote al formato del robot.
    resultados_optimos: {sku: {costo, precio_sugerido, ...}}
    """
    items = []
    for sku, r in resultados_optimos.items():
        precio = r.get("precio_sugerido", 0)
        costo  = r.get("costo", 0)
        items.append({
            "sku":              sku,
            "costo":            costo,
            "precio_salon":     precio,
            "precio_mayorista": round(precio * 0.90, 2),  # mayorista 10% menos por default
            "precio_galpon":    0,
        })
    return exportar_para_robot(items, log_func=log_func)


# ══════════════════════════════════════════════════════════════
# COMPARAR CON SNAPSHOT ANTERIOR (delta %)  ← NUEVO v5.5
# ══════════════════════════════════════════════════════════════

def comparar_con_snapshot_anterior(
    resultados_ml_actual: dict,
    fecha_anterior: str = None,
    log_func: LogFunc = None,
) -> dict:
    """
    Compara los precios actuales de ML con el snapshot anterior.
    Retorna dict con delta % por query.

    fecha_anterior: "YYYY-MM-DD" o None (usa el penúltimo snapshot).
    """
    if not _HISTORY_FILE.exists():
        _log("⚠ Sin historial para comparar", log_func)
        return {}

    try:
        historial = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if len(historial) < 2:
        _log("⚠ Se necesitan al menos 2 snapshots para comparar", log_func)
        return {}

    # Buscar snapshot anterior
    snap_anterior = None
    if fecha_anterior:
        for snap in historial:
            if snap["fecha"][:10] == fecha_anterior:
                snap_anterior = snap
                break
    if not snap_anterior:
        # Usar penúltimo snapshot
        snap_anterior = historial[-2]

    _log(f"📊 Comparando con snapshot del {snap_anterior['fecha'][:10]}...", log_func)

    comparacion = {}
    for query, items_actual in resultados_ml_actual.items():
        items_ant = snap_anterior["datos"].get(query, [])

        precios_act = [i["precio"] for i in items_actual if i["precio"] > 0]
        precios_ant = [i["precio"] for i in items_ant if i["precio"] > 0]

        if not precios_act or not precios_ant:
            continue

        med_act = sorted(precios_act)[len(precios_act) // 2]
        med_ant = sorted(precios_ant)[len(precios_ant) // 2]
        delta   = (med_act - med_ant) / med_ant if med_ant > 0 else 0

        comparacion[query] = {
            "precio_mediana_actual":   round(med_act, 2),
            "precio_mediana_anterior": round(med_ant, 2),
            "delta_pct":               round(delta * 100, 1),
            "fecha_anterior":          snap_anterior["fecha"][:10],
            "tendencia":               "🔺 SUBE" if delta > 0.02 else "🔻 BAJA" if delta < -0.02 else "➡ ESTABLE",
            "n_actual":                len(precios_act),
            "n_anterior":              len(precios_ant),
        }

    _log(f"  ✅ Comparación: {len(comparacion)} productos con delta", log_func)
    return comparacion
