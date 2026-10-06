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
    a = ap.parse_args()

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
            lista = ["ffconcat version 1.0"]
            palabras, t0 = [], 0.0
            for n_pieza, pid in enumerate(combo["piezas"]):
                d = cortes["piezas"][pid]
                ruta = (RAIZ / d["archivo"]).resolve()
                lista.append(f"file '{ruta.as_posix()}'")
                for w in d["palabras"]:
                    palabras.append({"w": w["w"], "s": round(t0 + w["s"], 3), "e": round(t0 + w["e"], 3),
                                     "pieza": n_pieza})
                t0 += d["duracion"]
            total = round(t0, 3)
            gancho = por_id.get(combo["piezas"][0], {})
            angulo = slug(gancho.get("angulo") or gancho.get("texto") or combo["piezas"][0], 20)
            for fmt in formatos:
                tw, th = FORMATOS[fmt]
                carpeta = tmp_raiz / f"{combo['id']}_{fmt}"
                carpeta.mkdir(parents=True, exist_ok=True)
                lista_piezas = carpeta / "piezas.ffconcat"
                lista_piezas.write_text("\n".join(lista) + "\n", encoding="utf-8")
                nombre = f"{a.fecha}_{angulo}_LEGO_{'-'.join(combo['piezas'])}_{fmt}.mp4"
                destino = ANUNCIOS / nombre
                estilo = firma(a, fmt, [cortes["piezas"][pid] for pid in combo["piezas"]])
                fila = {
                    "archivo": nombre, "formato": fmt, "duracion_s": f"{total:.1f}",
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
                cmd = [ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lista_piezas)]
                grafo = f"[0:v]crop={cw}:{ch}:{cx}:{cy},scale={tw}:{th},setsar=1[base]"
                if a.subtitulos != "no" and palabras:
                    rot = Rotulador(tw, a.mayusculas, a.color)
                    subs = lista_subtitulos(palabras, total, rot, a.subtitulos, carpeta)
                    cmd += ["-f", "concat", "-safe", "0", "-i", str(subs)]
                    y = int(th * ALTURA_SUB[fmt] - rot.H / 2)
                    grafo += (f";[1:v]format=rgba[sub];[base][sub]overlay=0:{y}:eof_action=pass:format=auto,"
                              f"format=yuv420p,{ETIQUETA_SDR}[v]")
                    salida_v = "[v]"
                else:
                    grafo += f";[base]format=yuv420p,{ETIQUETA_SDR}[v]"
                    salida_v = "[v]"
                grafo += ";[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]"
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


CAMPOS = ["archivo", "formato", "duracion_s", "gancho", "cuerpos", "cta", "texto", "estilo"]


def firma(a, fmt, datos_piezas):
    """Huella de cómo se armó un video: si cambian las piezas o el estilo, cambia la huella."""
    base = {"fmt": fmt, "subtitulos": a.subtitulos, "mayusculas": a.mayusculas,
            "recorte_y": a.recorte_y, "color": a.color.upper(),
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
