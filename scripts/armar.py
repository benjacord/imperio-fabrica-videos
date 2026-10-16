"""Arma los anuncios finales: une las piezas, recorta al formato de Meta y quema los subtítulos.

Uso:
    .venv/bin/python scripts/armar.py
    --formatos 9x16,4x5        9x16 (Reels y Stories), 4x5 (feed), 1x1, 16x9
    --subtitulos palabra       palabra (la palabra que suena se pinta) · frase · no
    --mayusculas               subtítulos en mayúsculas
    --solo 3                   arma solo los 3 primeros (para probar)
    --recorte-y 0.5            al recortar alto: 0 deja la parte de arriba, 1 la de abajo
    --color "#FFD43B"          color de la palabra activa
    --rehacer                  vuelve a armar aunque ya existan
    --titulo "TEXTO"           título fijo arriba si el gancho no trae "titulo" en guion.json
    --musica cancion.mp3       música de fondo bajita (si no la das, usa la que esté en
                               mi-negocio/musica/; --sin-musica la apaga)
    --volumen-musica 0.08      volumen de la música, relativo a la voz
    --union 0.17               silencio entre pieza y pieza (-1 = sin recortar)

Lee mi-negocio/combos.json y 20_PIEZAS/piezas.json. Deja los videos en 30_ANUNCIOS/
con el nombre AAAAMMDD_ANGULO_LEGO_PIEZAS_FORMATO.mp4 y un INDICE.csv para subirlos.
Si un anuncio ya está armado con las mismas piezas y el mismo estilo, no lo vuelve a hacer
(así "arma el resto" no repite los de prueba). Si cambias el estilo, se rehacen solos.
"""
import argparse
import csv
import datetime
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from comun import (ANUNCIOS, ETIQUETA_SDR, FUENTE, NEGOCIO, PIEZAS, RAIZ, avisar, cargar_guion,
                   correr, ffmpeg_bin, leer_json, morir, slug)

FORMATOS = {"9x16": (1080, 1920), "4x5": (1080, 1350), "1x1": (1080, 1080), "16x9": (1920, 1080)}
ALTURA_SUB = {"9x16": 0.64, "4x5": 0.76, "1x1": 0.78, "16x9": 0.82}


def recorte(W, H, tw, th, recorte_y):
    r = tw / th
    if W / H > r:
        cw, ch = int(round(H * r)) // 2 * 2, H
        cx, cy = (W - cw) // 2, 0
    else:
        cw, ch = W, int(round(W / r)) // 2 * 2
        cx, cy = 0, int((H - ch) * recorte_y) // 2 * 2
    return cw, ch, cx, cy


def bloques(palabras, max_palabras=4, max_letras=22, corte=0.6):
    grupos, actual = [], []
    for w in palabras:
        if actual:
            largo = len(" ".join(x["w"] for x in actual + [w]))
            pausa = w["s"] - actual[-1]["e"]
            if (len(actual) >= max_palabras or largo > max_letras or pausa > corte
                    or actual[-1]["w"][-1:] in ".?!,:;"
                    or w.get("pieza") != actual[-1].get("pieza")):  # nunca mezcla dos piezas
                grupos.append(actual)
                actual = []
        actual.append(w)
    if actual:
        grupos.append(actual)
    return grupos


class Rotulador:
    """Dibuja los subtítulos como imágenes transparentes del mismo tamaño."""

    def __init__(self, ancho, mayusculas, color):
        from PIL import ImageFont
        self.W = ancho
        self.fs = int(ancho * 0.068) if ancho <= 1200 else int(ancho * 0.042)
        self.font = ImageFont.truetype(str(FUENTE), self.fs)
        self.borde = max(4, self.fs // 9)
        asc, desc = self.font.getmetrics()
        self.lh = int((asc + desc) * 1.06)
        self.H = self.lh * 2 + self.borde * 2 + 12
        self.mayus = mayusculas
        self.color = tuple(int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

    def vacio(self, ruta):
        from PIL import Image
        Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0)).save(ruta)

    def dibujar(self, grupo, activo, ruta):
        from PIL import Image, ImageDraw
        textos = [w["w"].upper() if self.mayus else w["w"] for w in grupo]
        esp = self.font.getlength(" ")
        anchos = [self.font.getlength(t) for t in textos]
        maxw = self.W * 0.86
        lineas, linea, acum = [], [], 0.0
        for i, aw in enumerate(anchos):
            extra = aw if not linea else aw + esp
            if linea and acum + extra > maxw:
                lineas.append(linea)
                linea, acum = [i], aw
            else:
                linea.append(i)
                acum += extra
        if linea:
            lineas.append(linea)
        lineas = lineas[:2]
        im = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        alto_texto = self.lh * len(lineas)
        y = (self.H - alto_texto) / 2
        for ln in lineas:
            total = sum(anchos[i] for i in ln) + esp * (len(ln) - 1)
            x = (self.W - total) / 2
            for i in ln:
                color = self.color if i == activo else (255, 255, 255)
                d.text((x, y), textos[i], font=self.font, fill=color + (255,),
                       stroke_width=self.borde, stroke_fill=(0, 0, 0, 255))
                x += anchos[i] + esp
            y += self.lh
        im.save(ruta)


_VOZ = {}


def voz_de(ruta):
    """Tramos con voz de una pieza (el mismo detector que usa cortar.py), guardados en memoria."""
    if ruta not in _VOZ:
        import warnings
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        from cortar import regiones_de_voz
        _VOZ[ruta] = regiones_de_voz(ruta)
    return _VOZ[ruta]


def musica_por_defecto():
    """La primera canción de mi-negocio/musica/ (mp3, m4a, wav o aac), o "" si no hay."""
    carpeta = NEGOCIO / "musica"
    if not carpeta.is_dir():
        return ""
    canciones = sorted(p for p in carpeta.iterdir()
                       if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".aac") and not p.name.startswith("."))
    return str(canciones[0]) if canciones else ""


ALTURA_TITULO = {"9x16": 0.17, "4x5": 0.10, "1x1": 0.10, "16x9": 0.10}


def dibujar_titulo(texto, ancho, ruta, mayusculas=True):
    """Título fijo (Always On): caja blanca redondeada con texto negro, hasta 2 líneas."""
    from PIL import Image, ImageDraw, ImageFont
    texto = texto.upper() if mayusculas else texto
    fs = int(ancho * 0.052)
    font = ImageFont.truetype(str(FUENTE), fs)
    maxw = ancho * 0.80
    lineas, linea = [], ""
    for p in texto.split():
        prueba = f"{linea} {p}".strip()
        if linea and font.getlength(prueba) > maxw:
            lineas.append(linea)
            linea = p
        else:
            linea = prueba
    if linea:
        lineas.append(linea)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.02)
    pad_x, pad_y = int(fs * 0.55), int(fs * 0.35)
    caja_w = int(max(font.getlength(l) for l in lineas) + pad_x * 2)
    caja_h = lh * len(lineas) + pad_y * 2
    im = Image.new("RGBA", (ancho, caja_h + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0 = (ancho - caja_w) // 2
    d.rounded_rectangle((x0, 0, x0 + caja_w, caja_h), radius=int(fs * 0.35), fill=(255, 255, 255, 245))
    y = pad_y
    for l in lineas:
        d.text(((ancho - font.getlength(l)) / 2, y), l, font=font, fill=(0, 0, 0, 255))
        y += lh
    im.save(ruta)
    return im.size[1]


def lista_subtitulos(palabras, total, rot, modo, carpeta):
    """Arma la lista ffconcat de imágenes con su duración exacta."""
    tramos = []
    n = 0
    grupos = bloques(palabras)
    for gi, g in enumerate(grupos):
        fin_grupo = g[-1]["e"] + 0.25
        if gi + 1 < len(grupos):
            sig = grupos[gi + 1][0]["s"]
            # si el siguiente bloque llega luego, el subtítulo se queda hasta que aparezca
            fin_grupo = sig if sig - g[-1]["e"] < 0.8 else min(fin_grupo, sig)
        if modo == "frase":
            n += 1
            ruta = carpeta / f"s{n:04d}.png"
            rot.dibujar(g, None, ruta)
            tramos.append((g[0]["s"], fin_grupo, ruta))
        else:
            for k, w in enumerate(g):
                n += 1
                ruta = carpeta / f"s{n:04d}.png"
                rot.dibujar(g, k, ruta)
                hasta = g[k + 1]["s"] if k + 1 < len(g) else fin_grupo
                tramos.append((w["s"], hasta, ruta))
    vacio = carpeta / "vacio.png"
    rot.vacio(vacio)
    lineas = ["ffconcat version 1.0"]
    cursor = 0.0
    for a, b, ruta in sorted(tramos, key=lambda x: x[0]):
        a, b = max(a, cursor), min(b, total)
        if b - a < 0.02:
            continue
        if a - cursor > 0.001:
            lineas += [f"file '{vacio.as_posix()}'", f"duration {a - cursor:.3f}"]
        lineas += [f"file '{ruta.as_posix()}'", f"duration {b - a:.3f}"]
        cursor = b
    if total - cursor > 0.001:
        lineas += [f"file '{vacio.as_posix()}'", f"duration {total - cursor:.3f}"]
    lineas.append(f"file '{vacio.as_posix()}'")
    archivo = carpeta / "subtitulos.ffconcat"
    archivo.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return archivo


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--formatos", default="9x16,4x5")
    ap.add_argument("--subtitulos", default="palabra", choices=["palabra", "frase", "no"])
    ap.add_argument("--mayusculas", action="store_true")
    ap.add_argument("--solo", type=int, default=0)
    ap.add_argument("--recorte-y", type=float, default=0.5)
    ap.add_argument("--color", default="#FFD43B")
    ap.add_argument("--fecha", default=datetime.date.today().strftime("%Y%m%d"))
    ap.add_argument("--combos", default=str(NEGOCIO / "combos.json"))
    ap.add_argument("--rehacer", action="store_true")
    ap.add_argument("--titulo", default="", help="título fijo arriba (si el combo o el gancho no traen uno)")
    ap.add_argument("--musica", default="", help="mp3 de fondo, en loop (por defecto, el de mi-negocio/musica/)")
    ap.add_argument("--sin-musica", action="store_true", help="arma sin música aunque haya una en mi-negocio/musica/")
    ap.add_argument("--volumen-musica", type=float, default=0.08, help="0 a 1, relativo a la voz")
    ap.add_argument("--union", type=float, default=0.17,
                    help="segundos de silencio entre una pieza y la siguiente (-1 = sin recortar)")
    a = ap.parse_args()
    if a.sin_musica:
        a.musica = ""
    elif not a.musica:
        a.musica = musica_por_defecto()
        if a.musica:
            avisar(f"Música de fondo: {Path(a.musica).name} (de mi-negocio/musica/, volumen {a.volumen_musica})")
    if a.musica and not Path(a.musica).exists():
        morir(f"No encuentro la música: {a.musica}")

    ff = ffmpeg_bin()
    if not ff:
        morir("No encuentro ffmpeg. Corre: python3 scripts/doctor.py --arreglar")
    if a.subtitulos != "no" and not FUENTE.exists():
        morir("Falta la tipografía de subtítulos en fuentes/.")
    _, piezas_guion = cargar_guion()
    por_id = {p["id"]: p for p in piezas_guion}
    cortes = leer_json(PIEZAS / "piezas.json")
    if not cortes:
        morir("Primero corta las piezas (scripts/cortar.py).")
    combos = (leer_json(a.combos) or {}).get("anuncios", [])
    if not combos:
        morir("No hay combinaciones. Corre primero scripts/combinar.py")
    if a.solo:
        combos = combos[:a.solo]
    formatos = [f.strip() for f in a.formatos.split(",") if f.strip()]
    for f in formatos:
        if f not in FORMATOS:
            morir(f"Formato desconocido: {f}. Usa {', '.join(FORMATOS)}")

    W, H = cortes["lienzo"]
    ANUNCIOS.mkdir(parents=True, exist_ok=True)
    indice = ANUNCIOS / "INDICE.csv"
    previas = leer_indice(indice)
    filas, saltados = [], 0
    tmp_raiz = Path(tempfile.mkdtemp(prefix="fabrica-"))
    try:
        for ci, combo in enumerate(combos, 1):
            faltan = [p for p in combo["piezas"] if p not in cortes["piezas"]]
            if faltan:
                avisar(f"Salto {combo['id']}: faltan piezas {', '.join(faltan)}")
                continue
            # lista de piezas y palabras con su tiempo dentro del anuncio
            # cada pieza se recorta a su voz real: entre pieza y pieza queda solo la pausa de --union
            lista, palabras, t0 = [], [], 0.0
            for n_pieza, pid in enumerate(combo["piezas"]):
                d = cortes["piezas"][pid]
                ruta = (RAIZ / d["archivo"]).resolve()
                a_ini, a_fin = 0.0, d["duracion"]
                r = voz_de(ruta) if a.union >= 0 else None
                if r and d["palabras"]:
                    pw, uw = d["palabras"][0], d["palabras"][-1]
                    a_ini = max(0.0, r[0][0] - max(0.08, a.union * 0.35))
                    # el final de frase se dice suave y el detector lo pierde: manda la última palabra
                    a_fin = min(d["duracion"], max(r[-1][1] + a.union * 0.65, uw["e"] - 0.02))
                    if n_pieza == len(combo["piezas"]) - 1:
                        a_fin = d["duracion"]   # el CTA cierra el video: se deja completo
                lista.append((ruta, round(a_ini, 3), round(a_fin - a_ini, 3)))
                for w in d["palabras"]:
                    palabras.append({"w": w["w"], "s": round(t0 + max(0.0, w["s"] - a_ini), 3),
                                     "e": round(t0 + min(a_fin, w["e"]) - a_ini, 3), "pieza": n_pieza})
                t0 += a_fin - a_ini
            total = round(t0, 3)
            gancho = por_id.get(combo["piezas"][0], {})
            angulo = slug(gancho.get("angulo") or gancho.get("texto") or combo["piezas"][0], 20)
            titulo = (combo.get("titulo") or gancho.get("titulo") or a.titulo or "").strip()
            for fmt in formatos:
                tw, th = FORMATOS[fmt]
                carpeta = tmp_raiz / f"{combo['id']}_{fmt}"
                carpeta.mkdir(parents=True, exist_ok=True)
                nombre = f"{a.fecha}_{angulo}_LEGO_{'-'.join(combo['piezas'])}_{fmt}.mp4"
                destino = ANUNCIOS / nombre
                estilo = firma(a, fmt, [cortes["piezas"][pid] for pid in combo["piezas"]], titulo)
                fila = {
                    "archivo": nombre, "formato": fmt, "duracion_s": f"{total:.1f}", "titulo": titulo,
                    "gancho": combo["piezas"][0], "cuerpos": " ".join(combo["piezas"][1:-1]),
                    "cta": combo["piezas"][-1],
                    "texto": " ".join(por_id[p]["texto"] for p in combo["piezas"] if p in por_id),
                    "estilo": estilo}
                vieja = previas.get(clave_de(nombre))
                vieja_ruta = ANUNCIOS / vieja["archivo"] if vieja else None
                if (vieja and not a.rehacer and vieja.get("estilo") == estilo and vieja_ruta.exists()):
                    saltados += 1   # ya está hecho igual (aunque sea de otro día): se conserva
                    filas.append({**fila, "archivo": vieja["archivo"]})
                    continue
                cw, ch, cx, cy = recorte(W, H, tw, th, a.recorte_y)
                cmd = [ff, "-y", "-v", "error"]
                for ruta, desde, largo in lista:
                    cmd += ["-ss", f"{desde:.3f}", "-t", f"{largo:.3f}", "-i", str(ruta)]
                k = len(lista)
                grafo = ("".join(f"[{i}:a]afade=t=in:d=0.015,afade=t=out:st={max(0.0, l - 0.03):.3f}:d=0.03[a{i}];"
                                 for i, (_, _, l) in enumerate(lista))
                         + "".join(f"[{i}:v][a{i}]" for i in range(k)) + f"concat=n={k}:v=1:a=1[cv][ca];"
                         f"[cv]crop={cw}:{ch}:{cx}:{cy},scale={tw}:{th},setsar=1[base]")
                capa, n_in = "[base]", k
                if a.subtitulos != "no" and palabras:
                    rot = Rotulador(tw, a.mayusculas, a.color)
                    subs = lista_subtitulos(palabras, total, rot, a.subtitulos, carpeta)
                    cmd += ["-f", "concat", "-safe", "0", "-i", str(subs)]
                    y = int(th * ALTURA_SUB[fmt] - rot.H / 2)
                    grafo += (f";[{n_in}:v]format=rgba[sub];{capa}[sub]overlay=0:{y}:eof_action=pass:format=auto[consub]")
                    capa, n_in = "[consub]", n_in + 1
                if titulo:
                    png = carpeta / "titulo.png"
                    alto_t = dibujar_titulo(titulo, tw, png)
                    cmd += ["-loop", "1", "-i", str(png)]
                    yt = int(th * ALTURA_TITULO[fmt] - alto_t / 2)
                    grafo += f";[{n_in}:v]format=rgba[tit];{capa}[tit]overlay=0:{yt}:shortest=1[contit]"
                    capa, n_in = "[contit]", n_in + 1
                grafo += f";{capa}format=yuv420p,{ETIQUETA_SDR}[v]"
                salida_v = "[v]"
                grafo += ";[ca]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000"
                if a.musica:
                    cmd += ["-stream_loop", "-1", "-i", str(Path(a.musica).resolve())]
                    fade = max(total - 1.2, 0)
                    grafo += (f"[voz];[{n_in}:a]aresample=48000,volume={a.volumen_musica},"
                              f"afade=t=in:d=0.5,afade=t=out:st={fade:.2f}:d=1.2[mus];"
                              f"[voz][mus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
                    n_in += 1
                else:
                    grafo += "[a]"
                cmd += ["-filter_complex", grafo, "-map", salida_v, "-map", "[a]",
                        "-t", f"{total:.3f}", "-r", "30", "-c:v", "libx264", "-preset", "fast",
                        "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                        "-ac", "2", "-movflags", "+faststart", str(destino)]
                avisar(f"[{ci}/{len(combos)}] {nombre} ({total:.1f} s)")
                correr(cmd)
                if vieja and vieja["archivo"] != nombre and vieja_ruta.exists():
                    vieja_ruta.unlink()   # la versión anterior de este mismo anuncio
                filas.append(fila)
    finally:
        shutil.rmtree(tmp_raiz, ignore_errors=True)

    if filas:
        escribir_indice(indice, previas, filas)
    hechos = len(filas) - saltados
    avisar(f"\nListo: {hechos} videos nuevos en 30_ANUNCIOS/"
           + (f" ({saltados} ya estaban hechos igual y no los repetí)" if saltados else "")
           + ". Detalle en 30_ANUNCIOS/INDICE.csv.")


CAMPOS = ["archivo", "formato", "duracion_s", "titulo", "gancho", "cuerpos", "cta", "texto", "estilo"]


def firma(a, fmt, datos_piezas, titulo=""):
    """Huella de cómo se armó un video: si cambian las piezas o el estilo, cambia la huella."""
    base = {"fmt": fmt, "subtitulos": a.subtitulos, "mayusculas": a.mayusculas,
            "recorte_y": a.recorte_y, "color": a.color.upper(), "titulo": titulo,
            "musica": Path(a.musica).name if a.musica else "", "vol": a.volumen_musica, "union": a.union,
            "piezas": [[d["archivo"], d.get("origen"), d.get("inicio"), d.get("fin"), d.get("texto_guion")]
                       for d in datos_piezas]}
    return hashlib.sha1(json.dumps(base, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]


def clave_de(nombre):
    """El nombre sin la fecha: identifica el mismo anuncio aunque se haya armado otro día."""
    return nombre.split("_", 1)[1] if "_" in nombre else nombre


def leer_indice(ruta):
    if not ruta.exists():
        return {}
    with open(ruta, newline="", encoding="utf-8") as f:
        return {clave_de(fila["archivo"]): fila for fila in csv.DictReader(f) if fila.get("archivo")}


def escribir_indice(ruta, previas, filas):
    """Un renglón por anuncio, sin repetidos: los nuevos reemplazan a los viejos."""
    todas = dict(previas)
    for fila in filas:
        todas[clave_de(fila["archivo"])] = fila
    existentes = {k: v for k, v in todas.items() if (ANUNCIOS / v["archivo"]).exists()}
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, extrasaction="ignore")
        w.writeheader()
        for fila in existentes.values():
            w.writerow({c: fila.get(c, "") for c in CAMPOS})


if __name__ == "__main__":
    main()
