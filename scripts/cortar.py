"""Encuentra cada pieza del guion en tus grabaciones y la corta. La última toma manda.

Uso:
    .venv/bin/python scripts/cortar.py
    --guion mi-negocio/guion.json   (por defecto)
    --umbral 0.72    qué tan parecido a tu guion tiene que ser lo que dijiste (0 a 1)
    --pausa 0.9      silencio (segundos) que separa una toma de la siguiente

Cómo decide:
  1. Lee las transcripciones de 20_PIEZAS/_transcripciones (corre antes transcribir.py).
  2. Escucha el audio para saber exactamente dónde hay voz y dónde hay silencio.
  3. Parte cada grabación en tomas usando los silencios y compara cada toma con el guion.
  4. Si una pieza se dijo varias veces, usa la ÚLTIMA (salvo que esa última esté
     claramente peor que una anterior: ahí usa la mejor y te avisa).
  5. Corta cada pieza a 20_PIEZAS/<ID>.mp4, todas del mismo tamaño, listas para unir.
Al final escribe 20_PIEZAS/piezas.json y 20_PIEZAS/REPORTE.md.
"""
import argparse
import bisect
import difflib
import warnings

from comun import (EXT_VIDEO, GRABACIONES, LIENZOS, PIEZAS, RAIZ, TRANSCRIPCIONES, avisar,
                   cargar_guion, correr, duracion, escribir_json, ffmpeg_bin, leer_json, morir,
                   normalizar, orientacion, tamano_visible)

warnings.filterwarnings("ignore", category=RuntimeWarning)


# ---------- dónde hay voz ----------

def regiones_de_voz(ruta, paso=0.02, silencio_min=0.35, voz_min=0.08):
    """Tramos (inicio, fin) donde hay voz, medidos en el audio real."""
    import numpy as np
    from faster_whisper.audio import decode_audio
    audio = decode_audio(str(ruta), sampling_rate=16000)
    n = int(16000 * paso)
    m = len(audio) // n
    if m == 0:
        return []
    rms = np.sqrt((audio[:m * n].reshape(m, n) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    piso = float(np.percentile(db, 10))
    umbral = min(max(piso + 12.0, -55.0), -28.0)
    voz = db > umbral
    tramos, ini = [], None
    for i, v in enumerate(voz):
        if v and ini is None:
            ini = i
        elif not v and ini is not None:
            tramos.append([ini * paso, i * paso])
            ini = None
    if ini is not None:
        tramos.append([ini * paso, m * paso])
    unidos = []
    for t in tramos:
        if unidos and t[0] - unidos[-1][1] < silencio_min:
            unidos[-1][1] = t[1]
        else:
            unidos.append(t)
    return [(round(a, 3), round(b, 3)) for a, b in unidos if b - a >= voz_min]


def region_en(regiones, t):
    """Índice del tramo de voz que contiene t, o None."""
    inicios = [r[0] for r in regiones]
    i = bisect.bisect_right(inicios, t) - 1
    if i >= 0 and regiones[i][0] <= t <= regiones[i][1]:
        return i
    return None


def siguiente_region(regiones, t):
    for i, r in enumerate(regiones):
        if r[0] >= t:
            return i
    return None


def reubicar_palabras(palabras, regiones):
    """Whisper a veces 'estira' la primera palabra de una frase hacia el silencio anterior.
    Si una palabra empieza en silencio, la movemos al comienzo del tramo de voz siguiente."""
    if not regiones:
        return palabras
    out = [dict(w) for w in palabras]
    for i, w in enumerate(out):
        r = region_en(regiones, w["s"] + 0.05)
        if r is not None:
            fin = regiones[r][1]
            if w["e"] > fin + 0.25:  # cola estirada de la última palabra de una frase
                w["e"] = round(fin + 0.05, 3)
            continue
        j = siguiente_region(regiones, w["s"])
        if j is None:
            continue
        nuevo_s = regiones[j][0]
        tope = out[i + 1]["s"] if i + 1 < len(out) else regiones[j][1]
        if tope < nuevo_s:
            continue
        largo = min(max(0.15, w["e"] - w["s"]), 0.6)
        w["s"] = round(nuevo_s, 3)
        w["e"] = round(max(nuevo_s + 0.05, min(tope, nuevo_s + largo)), 3)
    return out


# ---------- comparar con el guion ----------

def segmentar(palabras, pausa):
    tomas, actual = [], []
    for w in palabras:
        if actual and w["s"] - actual[-1]["e"] > pausa:
            tomas.append(actual)
            actual = []
        actual.append(w)
    if actual:
        tomas.append(actual)
    return tomas


def parecido(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def alinear(texto_guion, palabras, inicio_voz=None):
    """Subtítulos con las palabras del guion (bien escritas) y los tiempos reales."""
    g = texto_guion.split()
    gn = [normalizar(x) for x in g]
    tn = [normalizar(w["w"]) for w in palabras]
    out = []
    sm = difflib.SequenceMatcher(None, gn, tn, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal" or (tag == "replace" and (i2 - i1) == (j2 - j1)):
            for k in range(j2 - j1):
                out.append({**palabras[j1 + k], "w": g[i1 + k]})
        elif tag in ("replace", "delete"):
            if tag == "replace":
                s, e = palabras[j1]["s"], palabras[j2 - 1]["e"]
            else:
                s = out[-1]["e"] if out else (inicio_voz if inicio_voz is not None else
                                              (palabras[0]["s"] - 0.3 if palabras else 0.0))
                e = palabras[j1]["s"] if j1 < len(palabras) else s + 0.3 * (i2 - i1)
            n = i2 - i1
            if e - s < 0.1 * n:
                s = max(0.0, e - 0.15 * n)
            dt = (e - s) / n
            for k in range(n):
                out.append({"w": g[i1 + k], "s": round(s + k * dt, 3), "e": round(s + (k + 1) * dt, 3)})
        elif tag == "insert":
            for k in range(j2 - j1):
                out.append(dict(palabras[j1 + k]))
    return out


def construir_candidatos(transcripciones, pausa, max_unir=3):
    cands = []
    for fi, t in enumerate(transcripciones):
        tomas = segmentar(t["palabras"], pausa)
        for i in range(len(tomas)):
            for k in range(1, max_unir + 1):
                if i + k > len(tomas):
                    break
                ws = [w for toma in tomas[i:i + k] for w in toma]
                texto = " ".join(w["w"] for w in ws)
                cands.append({"fi": fi, "i": i, "k": k, "palabras": ws, "texto": texto,
                              "norm": normalizar(texto), "s": ws[0]["s"], "e": ws[-1]["e"]})
    return cands


def se_pisan(a, b):
    return a["fi"] == b["fi"] and a["s"] < b["e"] and b["s"] < a["e"]


def tomas_de(pieza, cands, umbral):
    pn = normalizar(pieza["texto"])
    encontradas = []
    for c in cands:
        proporcion = len(c["norm"]) / max(1, len(pn))
        if proporcion < 0.6 or proporcion > 1.6:
            continue
        sim = parecido(pn, c["norm"])
        if sim >= umbral:
            encontradas.append({**c, "sim": sim})
    encontradas.sort(key=lambda c: -c["sim"])
    limpias = []
    for c in encontradas:
        if not any(se_pisan(c, x) for x in limpias):
            limpias.append(c)
    limpias.sort(key=lambda c: (c["fi"], c["s"]))
    return limpias


def mejor_parecido(pieza, cands):
    pn = normalizar(pieza["texto"])
    return max((parecido(pn, c["norm"]) for c in cands), default=0.0)


def elegir(tomas, ocupados, margen_peor=0.15):
    """La última toma manda, salvo que sea claramente peor que la mejor."""
    if not tomas:
        return None, False
    mejor = max(t["sim"] for t in tomas)
    orden = list(reversed(tomas))
    for t in orden:
        if any(se_pisan(t, o) for o in ocupados):
            continue
        if t["sim"] < mejor - margen_peor:
            continue
        return t, t is not orden[0]
    return None, False


def limites(t, trans, margen_inicio, margen_fin):
    """Inicio y fin del corte: pegados a la voz real, sin comerse a las piezas vecinas."""
    todas = trans["palabras"]
    regiones = trans["regiones"]
    i0 = todas.index(t["palabras"][0])
    i1 = todas.index(t["palabras"][-1])
    antes = todas[i0 - 1]["e"] + 0.04 if i0 > 0 else 0.0
    despues = todas[i1 + 1]["s"] - 0.04 if i1 + 1 < len(todas) else trans["dur"]
    ini = t["s"] - margen_inicio
    fin = t["e"] + margen_fin
    r0 = region_en(regiones, t["palabras"][0]["s"] + 0.02) if regiones else None
    if r0 is None and regiones:
        r0 = siguiente_region(regiones, t["palabras"][0]["s"])
    if r0 is not None:
        ini = min(ini, regiones[r0][0] - 0.08)
    r1 = region_en(regiones, max(t["palabras"][-1]["s"], t["palabras"][-1]["e"] - 0.05)) if regiones else None
    if r1 is not None:
        fin = min(max(regiones[r1][1] + 0.15, t["e"] + 0.05), t["e"] + margen_fin + 0.4)
    ini = max(ini, antes, 0.0)
    fin = min(fin, despues, trans["dur"])
    inicio_voz = regiones[r0][0] if r0 is not None else None
    return round(ini, 3), round(fin, 3), inicio_voz


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--guion", default=None)
    ap.add_argument("--umbral", type=float, default=0.72)
    ap.add_argument("--pausa", type=float, default=0.9)
    ap.add_argument("--margen-inicio", type=float, default=0.12)
    ap.add_argument("--margen-fin", type=float, default=0.30)
    a = ap.parse_args()

    _, piezas = cargar_guion(a.guion)
    videos = sorted(p for p in GRABACIONES.iterdir() if p.suffix.lower() in EXT_VIDEO)
    if not videos:
        morir("No hay videos en 10_GRABACIONES.")
    transcripciones = []
    for v in videos:
        t = leer_json(TRANSCRIPCIONES / (v.stem + ".json"))
        if not t:
            morir(f"Falta la transcripción de {v.name}. Corre primero scripts/transcribir.py")
        avisar(f"Escuchando {v.name}...")
        t["ruta"] = v
        t["dur"] = duracion(v)
        t["regiones"] = regiones_de_voz(v)
        t["palabras"] = reubicar_palabras(t["palabras"], t["regiones"])
        transcripciones.append(t)

    ff = ffmpeg_bin()
    if not ff:
        morir("No encuentro ffmpeg. Corre: python3 scripts/doctor.py --arreglar")
    W0, H0 = tamano_visible(videos[0])
    forma = orientacion(W0, H0)
    W, H = LIENZOS[forma]
    avisar(f"Grabación {forma} ({W0}x{H0}). Las piezas quedan en {W}x{H}.")

    cands = construir_candidatos(transcripciones, a.pausa)
    ocupados, resultado, faltan = [], {}, []
    for p in piezas:
        tomas = tomas_de(p, cands, a.umbral)
        elegida, no_es_la_ultima = elegir(tomas, ocupados)
        if not elegida:
            faltan.append({"id": p["id"], "tipo": p["tipo"], "texto": p["texto"],
                           "mejor_parecido": round(mejor_parecido(p, cands), 2)})
            continue
        ocupados.append(elegida)
        resultado[p["id"]] = (p, elegida, len(tomas), tomas.index(elegida) + 1, no_es_la_ultima)

    PIEZAS.mkdir(parents=True, exist_ok=True)
    for viejo in PIEZAS.glob("*.mp4"):
        viejo.unlink()
    salida = {"lienzo": [W, H], "orientacion": forma, "piezas": {}, "faltan": faltan}
    for p in piezas:
        if p["id"] not in resultado:
            continue
        p, t, n_tomas, n_usada, no_es_la_ultima = resultado[p["id"]]
        pid = p["id"]
        trans = transcripciones[t["fi"]]
        ini, fin, inicio_voz = limites(t, trans, a.margen_inicio, a.margen_fin)
        dur = round(fin - ini, 3)
        if dur <= 0.2:
            faltan.append({"id": pid, "tipo": p["tipo"], "texto": p["texto"], "mejor_parecido": round(t["sim"], 2)})
            continue
        destino = PIEZAS / f"{pid}.mp4"
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=yuv420p")
        af = (f"aresample=48000,afade=t=in:st=0:d=0.03,"
              f"afade=t=out:st={max(0.0, dur - 0.06):.3f}:d=0.06")
        avisar(f"Cortando {pid} ({dur:.1f} s, toma {n_usada} de {n_tomas}, parecido {t['sim']:.2f})")
        correr([ff, "-y", "-v", "error", "-ss", f"{ini:.3f}", "-i", str(trans["ruta"]), "-t", f"{dur:.3f}",
                "-vf", vf, "-af", af, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart", str(destino)])
        palabras = alinear(p["texto"], t["palabras"], inicio_voz)
        rel = [{"w": w["w"], "s": round(max(0.0, w["s"] - ini), 3), "e": round(max(0.0, w["e"] - ini), 3)}
               for w in palabras]
        salida["piezas"][pid] = {
            "tipo": p["tipo"], "rol": p.get("rol"), "angulo": p.get("angulo"),
            "archivo": str(destino.relative_to(RAIZ)), "duracion": round(duracion(destino), 3),
            "texto_guion": p["texto"], "texto_dicho": " ".join(w["w"] for w in t["palabras"]),
            "parecido": round(t["sim"], 3), "tomas_encontradas": n_tomas, "toma_usada": n_usada,
            "aviso_toma": no_es_la_ultima, "origen": trans["ruta"].name,
            "inicio": ini, "fin": fin, "palabras": rel}

    escribir_json(PIEZAS / "piezas.json", salida)
    escribir_reporte(salida, piezas)
    avisar(f"\nListo: {len(salida['piezas'])} piezas cortadas, {len(salida['faltan'])} sin encontrar.")
    avisar("Revisa 20_PIEZAS/REPORTE.md")


def escribir_reporte(salida, piezas):
    lineas = ["# Reporte del corte", ""]
    ok = salida["piezas"]
    lineas.append(f"Piezas cortadas: **{len(ok)}** de {len(piezas)}. "
                  f"Lienzo {salida['lienzo'][0]}x{salida['lienzo'][1]} ({salida['orientacion']}).")
    lineas += ["", "| Pieza | Tipo | Duración | Tomas | Usada | Parecido | Lo que se oye |",
               "|---|---|---|---|---|---|---|"]
    for p in piezas:
        d = ok.get(p["id"])
        if not d:
            continue
        marca = " ⚠️" if d["aviso_toma"] or d["parecido"] < 0.8 else ""
        lineas.append(f"| {p['id']}{marca} | {d['tipo']} | {d['duracion']:.1f} s | {d['tomas_encontradas']} | "
                      f"{d['toma_usada']} | {d['parecido']:.2f} | {d['texto_dicho'][:90]} |")
    if salida["faltan"]:
        lineas += ["", "## No las encontré", "",
                   "Puede que no se hayan grabado, que se hayan dicho muy distinto al guion "
                   "o que no hubo silencio antes y después.", ""]
        for f in salida["faltan"]:
            lineas.append(f"- **{f['id']}** ({f['tipo']}, el más parecido llegó a "
                          f"{f['mejor_parecido']:.2f}): {f['texto']}")
    avisos = [pid for pid, d in ok.items() if d["aviso_toma"]]
    if avisos:
        lineas += ["", "## Ojo", "",
                   "En estas piezas la última toma salió bastante peor que una anterior, así que usé la mejor: "
                   + ", ".join(avisos) + ". Míralas antes de armar."]
    bajas = [pid for pid, d in ok.items() if d["parecido"] < 0.8]
    if bajas:
        lineas += ["", "Las marcadas con ⚠️ se parecen menos al guion: escúchalas (puede ser solo una cifra "
                       "dicha distinto): " + ", ".join(bajas) + "."]
    (PIEZAS / "REPORTE.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
