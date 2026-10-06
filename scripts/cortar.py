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
     Si dentro de una toma volviste a empezar la frase sin pausa, se queda con el último intento.
  4. Si una pieza se dijo varias veces, usa la ÚLTIMA (salvo que esa última esté
     claramente peor que una anterior: ahí usa la mejor y te avisa).
  5. Corta cada pieza a 20_PIEZAS/<ID>.mp4, todas del mismo tamaño, listas para unir.
     Si grabaste con Video HDR (iPhone), la pasa a color normal para que no se vea lavada.
Al final escribe 20_PIEZAS/piezas.json y 20_PIEZAS/REPORTE.md.
"""
import argparse
import bisect
import difflib
import warnings

from comun import (ETIQUETA_SDR, EXT_VIDEO, GRABACIONES, LIENZOS, PIEZAS, RAIZ, TRANSCRIPCIONES,
                   avisar, cargar_guion, correr, duracion, escribir_json, ffmpeg_bin, filtro_hdr,
                   hdr_de, leer_json, morir, normalizar, orientacion, tamano_visible, tiene_filtro)

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


def reubicar_palabras(palabras, regiones, pausa=0.9):
    """Whisper a veces pega la primera palabra de una frase a la frase anterior.
    - Si una palabra empieza en silencio, la movemos al comienzo del tramo de voz siguiente.
    - Si una palabra dudosa (Whisper le tiene poca confianza) queda estirada hacia el silencio
      y después viene una pausa larga, es la primera palabra de la toma siguiente: la movemos ahí."""
    if not regiones:
        return palabras
    out = [dict(w) for w in palabras]
    for i, w in enumerate(out):
        r = region_en(regiones, w["s"] + 0.05)
        if r is not None:
            fin = regiones[r][1]
            if w["e"] > fin + 0.25:  # cola estirada hacia el silencio
                sig = out[i + 1] if i + 1 < len(out) else None
                j = region_en(regiones, sig["s"] + 0.02) if sig else None
                if j is None and sig:
                    j = siguiente_region(regiones, sig["s"])
                if (sig and j is not None and j > r and w.get("p", 1.0) < 0.35
                        and sig["s"] - fin >= pausa and regiones[j][0] <= sig["s"] + 0.05):
                    nuevo_s = regiones[j][0]
                    w["s"] = round(nuevo_s, 3)
                    w["e"] = round(max(nuevo_s + 0.05, min(sig["s"], nuevo_s + 0.3)), 3)
                else:
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
            # palabras que se oyen pero no están en el guion: al principio o al final de la pieza
            # son casi siempre de la pieza vecina, así que no se muestran
            if j1 == 0 or j2 == len(palabras):
                continue
            for k in range(j2 - j1):
                out.append(dict(palabras[j1 + k]))
    return out


def palabras_de_mas(texto_guion, palabras):
    """Lo que se oye en medio de la pieza y no está en el guion (un tropiezo, una palabra extra)."""
    gn = [normalizar(x) for x in texto_guion.split()]
    tn = [normalizar(w["w"]) for w in palabras]
    extra = []
    sm = difflib.SequenceMatcher(None, gn, tn, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert" and j1 > 0 and j2 < len(palabras) and j2 - j1 >= 2:
            extra.append(" ".join(w["w"] for w in palabras[j1:j2]))
        elif tag == "replace" and (j2 - j1) > (i2 - i1) + 1:
            extra.append(" ".join(w["w"] for w in palabras[j1:j2]))
    return extra


def construir_candidatos(transcripciones, pausa, max_unir=3):
    cands = []
    for fi, t in enumerate(transcripciones):
        tomas = segmentar(t["palabras"], pausa)
        for i in range(len(tomas)):
            for k in range(1, max_unir + 1):
                if i + k > len(tomas):
                    break
                ws = [w for toma in tomas[i:i + k] for w in toma]
                bordes, acum = [], 0
                for toma in tomas[i:i + k]:
                    bordes.append(acum)
                    acum += len(toma)
                texto = " ".join(w["w"] for w in ws)
                cands.append({"fi": fi, "i": i, "k": k, "palabras": ws, "texto": texto, "bordes": bordes,
                              "norm": normalizar(texto), "s": ws[0]["s"], "e": ws[-1]["e"]})
    return cands


def se_pisan(a, b):
    return a["fi"] == b["fi"] and a["s"] < b["e"] and b["s"] < a["e"]


def ajustar_toma(pw, pn, c):
    """Recorta la toma a lo que de verdad es esta pieza, sin partir frases ajenas.
    - Si dentro de una misma toma volviste a empezar la frase sin pausa
      ("Te suscribes una... Te suscribes una sola vez"), parte desde el último comienzo.
    - Si al borde se colaron 1 o 2 palabras de la pieza vecina, las deja fuera.
    Prueba esos cortes y se queda con el que más se parece al guion."""
    tw = [normalizar(w["w"]) for w in c["palabras"]]
    n = len(tw)
    bordes = c.get("bordes") or [0]
    k = 2 if len(pw) >= 4 else 1
    cabeza, cola = " ".join(pw[:k]), " ".join(pw[-k:])

    def unir(a, b):
        return " ".join(x for x in tw[max(0, a):b] if x)

    def empieza_como_guion(i):
        return bool(tw[i]) and (unir(i, i + k + 1) + " ").startswith(cabeza + " ")

    def inicio_de_toma(i):
        return max(b for b in bordes if b <= i)

    def fin_de_toma(i):
        return min([b for b in bordes if b > i] + [n])

    inicios = [0]
    for i in range(1, n):
        if not empieza_como_guion(i):
            continue
        b = inicio_de_toma(i)
        # al comienzo de una toma, o a mitad de toma si lo anterior fue un intento de esta misma frase
        if i == b or i - b <= 2 or empieza_como_guion(b):
            inicios.append(i)
    finales = [n]
    for j in range(1, n):
        if not (tw[j - 1] and (" " + unir(j - k - 1, j)).endswith(" " + cola)):
            continue
        # al final de una toma, o dejando fuera como mucho 2 palabras que se colaron
        if j in bordes or fin_de_toma(j - 1) - j <= 2:
            finales.append(j)
    mejor = None
    for i in inicios:
        for j in finales:
            if j - i < max(1, len(pw) // 2):
                continue
            norm = unir(i, j)
            sim = parecido(pn, norm)
            if mejor is None or sim > mejor[0] + 1e-9 or (abs(sim - mejor[0]) <= 1e-9 and i > mejor[1]):
                mejor = (sim, i, j, norm)
    if mejor is None:
        return {**c, "sim": 0.0}
    sim, i, j, norm = mejor
    if i == 0 and j == n:
        return {**c, "sim": sim}
    ws = c["palabras"][i:j]
    reinicio = i not in bordes and empieza_como_guion(inicio_de_toma(i))
    return {**c, "palabras": ws, "texto": " ".join(w["w"] for w in ws), "norm": norm,
            "s": ws[0]["s"], "e": ws[-1]["e"], "sim": sim, "reinicio": reinicio}


def tomas_de(pieza, cands, umbral):
    pn = normalizar(pieza["texto"])
    pw = pn.split()
    encontradas = []
    for c in cands:
        # hasta 4 veces el largo: puede traer intentos repetidos sin pausa que se recortan abajo
        largo = len(c["norm"]) / max(1, len(pn))
        if largo < 0.6 or largo > 4.0:
            continue
        c = ajustar_toma(pw, pn, c)
        proporcion = len(c["norm"]) / max(1, len(pn))
        if proporcion < 0.6 or proporcion > 1.6:
            continue
        if c["sim"] >= umbral:
            encontradas.append(c)
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
        t["palabras"] = reubicar_palabras(t["palabras"], t["regiones"], a.pausa)
        t["hdr"] = hdr_de(v)
        transcripciones.append(t)

    ff = ffmpeg_bin()
    if not ff:
        morir("No encuentro ffmpeg. Corre: python3 scripts/doctor.py --arreglar")
    puede_hdr = tiene_filtro("zscale")
    hdr_vistos = sorted({t["ruta"].name for t in transcripciones if t["hdr"]})
    if hdr_vistos:
        avisar(("Tu grabación viene en HDR: la paso a color normal para Meta. " if puede_hdr else
                "Tu grabación viene en HDR y este ffmpeg no la puede convertir: los colores pueden "
                "verse lavados. ") + "Para la próxima, apaga Video HDR en la cámara.")
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
    salida = {"lienzo": [W, H], "orientacion": forma, "piezas": {}, "faltan": faltan,
              "hdr": {"archivos": hdr_vistos, "convertido": bool(hdr_vistos) and puede_hdr}}
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
        # primero a 30 cuadros y al tamaño final (así la conversión de color trabaja menos)
        vf = f"fps=30,scale={W}:{H}:force_original_aspect_ratio=decrease,"
        if trans["hdr"] and puede_hdr:
            vf += filtro_hdr(trans["hdr"]) + ","
        vf += f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p,{ETIQUETA_SDR}"
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
            "aviso_toma": no_es_la_ultima, "reinicio": bool(t.get("reinicio")),
            "de_mas": palabras_de_mas(p["texto"], t["palabras"]), "origen": trans["ruta"].name,
            "inicio": ini, "fin": fin, "palabras": rel}

    escribir_json(PIEZAS / "piezas.json", salida)
    escribir_reporte(salida, piezas)
    avisar(f"\nListo: {len(salida['piezas'])} piezas cortadas, {len(salida['faltan'])} sin encontrar.")
    avisar("Revisa 20_PIEZAS/REPORTE.md")


PARECIDO_OK = 0.90   # bajo esto, la pieza se marca para escucharla
GANCHO_MAX = 4.0     # segundos


def escribir_reporte(salida, piezas):
    lineas = ["# Reporte del corte", ""]
    ok = salida["piezas"]
    lineas.append(f"Piezas cortadas: **{len(ok)}** de {len(piezas)}. "
                  f"Lienzo {salida['lienzo'][0]}x{salida['lienzo'][1]} ({salida['orientacion']}).")
    lineas += ["", "| Pieza | Tipo | Duración | Tomas | Usada | Parecido | Lo que se oye |",
               "|---|---|---|---|---|---|---|"]
    revisar = []
    for p in piezas:
        d = ok.get(p["id"])
        if not d:
            continue
        motivos = []
        if d["aviso_toma"]:
            motivos.append("la última toma salió bastante peor que una anterior, así que usé la mejor")
        if d.get("de_mas"):
            motivos.append("se oye algo que no está en el guion: «" + " / ".join(d["de_mas"]) + "»")
        if d["parecido"] < PARECIDO_OK and not d.get("de_mas"):
            motivos.append(f"se parece {d['parecido']:.2f} al guion (puede ser una cifra dicha distinto)")
        if motivos:
            revisar.append((p["id"], motivos))
        marca = " ⚠️" if motivos else ""
        lineas.append(f"| {p['id']}{marca} | {d['tipo']} | {d['duracion']:.1f} s | {d['tomas_encontradas']} | "
                      f"{d['toma_usada']} | {d['parecido']:.2f} | {d['texto_dicho'][:90]} |")
    if revisar:
        lineas += ["", "## Escucha estas antes de armar", ""]
        for pid, motivos in revisar:
            lineas.append(f"- **{pid}**: " + "; ".join(motivos) + ".")
        lineas += ["", "Si no te gusta cómo quedó, graba solo esa pieza de nuevo y vuelve a cortar."]
    if salida["faltan"]:
        lineas += ["", "## No las encontré", "",
                   "Puede que no se hayan grabado, que se hayan dicho muy distinto al guion "
                   "o que no hubo silencio antes y después.", ""]
        for f in salida["faltan"]:
            lineas.append(f"- **{f['id']}** ({f['tipo']}, el más parecido llegó a "
                          f"{f['mejor_parecido']:.2f}): {f['texto']}")
    reinicios = [pid for pid, d in ok.items() if d.get("reinicio")]
    if reinicios:
        lineas += ["", "## Volviste a empezar sin pausa", "",
                   "En " + ", ".join(reinicios) + " empezaste la frase de nuevo sin dejar silencio: "
                   "usé el último intento y dejé fuera el anterior. Escúchalas igual, por si acaso."]
    largos = [(pid, d["duracion"]) for pid, d in ok.items()
              if d["tipo"] == "gancho" and round(d["duracion"], 1) > GANCHO_MAX]
    if largos:
        lineas += ["", "## Ganchos de más de 4 segundos", "",
                   ", ".join(f"{pid} ({dur:.1f} s)" for pid, dur in largos) + ". Funcionan, pero los ganchos "
                   "cortos retienen más. Ojo con las cifras: \"$16.990\" se dice en 5 palabras."]
    hdr = salida.get("hdr") or {}
    if hdr.get("archivos"):
        if hdr.get("convertido"):
            lineas += ["", "## Tu grabación venía en HDR", "",
                       "La pasé a color normal (SDR) para que en Meta no se vea lavada. Para la próxima, "
                       "apaga Video HDR (iPhone: Ajustes > Cámara > Grabar video > Video HDR)."]
        else:
            lineas += ["", "## ⚠️ Tu grabación viene en HDR", "",
                       "Este computador no la pudo convertir, así que los colores pueden verse lavados. "
                       "Apaga Video HDR (iPhone: Ajustes > Cámara > Grabar video > Video HDR) y vuelve a grabar, "
                       "o pídele a Claude que corra doctor.py --arreglar."]
    (PIEZAS / "REPORTE.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
