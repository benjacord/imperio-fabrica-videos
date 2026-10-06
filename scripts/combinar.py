"""Decide qué gancho va con qué cuerpos y qué llamado a la acción (CTA).

Uso:
    .venv/bin/python scripts/combinar.py --cantidad 30
    --cuerpos 2        cuántos cuerpos por anuncio (1, 2, 3 o un rango como 2-3)
    --min 18 --max 35  duración permitida de cada anuncio, en segundos
                       (en la cuenta de Imperio, los de 20 a 30 s fueron los que mejor vendieron)
    --semilla 7        cambia el número para obtener otra mezcla

Reglas:
  - Todos los ganchos salen la misma cantidad de veces (más o menos).
  - Si los cuerpos tienen "rol", el orden respeta el embudo:
    problema y mecanismo primero, prueba y oferta después.
  - Nunca repite la misma combinación.
Escribe mi-negocio/combos.json. Usa las duraciones reales si ya cortaste (20_PIEZAS/piezas.json).
"""
import argparse
import datetime
import itertools
import random

from comun import NEGOCIO, PIEZAS, avisar, cargar_guion, escribir_json, leer_json, morir

ORDEN_ROL = {"problema": 0, "mecanismo": 1, "prueba": 2, "oferta": 3}


def estimar(texto):
    return round(len(texto.split()) / 2.6 + 0.4, 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cantidad", type=int, default=30)
    ap.add_argument("--cuerpos", default="2")
    ap.add_argument("--min", type=float, default=18)
    ap.add_argument("--max", type=float, default=35)
    ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--guion", default=None)
    a = ap.parse_args()

    _, piezas = cargar_guion(a.guion)
    cortes = (leer_json(PIEZAS / "piezas.json") or {}).get("piezas", {})
    dur = {}
    for p in piezas:
        if cortes:
            if p["id"] in cortes:
                dur[p["id"]] = cortes[p["id"]]["duracion"]
        else:
            dur[p["id"]] = estimar(p["texto"])
    ganchos = [p for p in piezas if p["tipo"] == "gancho" and p["id"] in dur]
    cuerpos = [p for p in piezas if p["tipo"] == "cuerpo" and p["id"] in dur]
    ctas = [p for p in piezas if p["tipo"] == "cta" and p["id"] in dur]
    if not ganchos or not cuerpos or not ctas:
        morir("Necesito al menos 1 gancho, 1 cuerpo y 1 CTA disponibles (cortados o en el guion).")

    if "-" in a.cuerpos:
        lo, hi = (int(x) for x in a.cuerpos.split("-"))
    else:
        lo = hi = int(a.cuerpos)
    hi = min(hi, len(cuerpos))
    lo = min(lo, hi)

    rnd = random.Random(a.semilla)
    usados, anuncios = set(), []
    intentos, i_cta = 0, 0
    tope = a.cantidad * 400
    while len(anuncios) < a.cantidad and intentos < tope:
        intentos += 1
        g = ganchos[len(anuncios) % len(ganchos)]
        n = rnd.randint(lo, hi)
        elegidos = rnd.sample(cuerpos, n)
        elegidos.sort(key=lambda c: ORDEN_ROL.get(c.get("rol"), 1.5))
        c = ctas[i_cta % len(ctas)]
        clave = (g["id"], tuple(x["id"] for x in elegidos), c["id"])
        if clave in usados:
            continue
        total = round(dur[g["id"]] + sum(dur[x["id"]] for x in elegidos) + dur[c["id"]], 2)
        if total < a.min or total > a.max:
            continue
        usados.add(clave)
        i_cta += 1
        anuncios.append({"id": f"A{len(anuncios) + 1:02d}",
                         "piezas": [g["id"]] + [x["id"] for x in elegidos] + [c["id"]],
                         "duracion": total})

    posibles = len(ganchos) * sum(
        len(list(itertools.permutations(range(len(cuerpos)), k))) for k in range(lo, hi + 1)) * len(ctas)
    escribir_json(NEGOCIO / "combos.json", {
        "generado": datetime.date.today().isoformat(),
        "reglas": {"cuerpos": a.cuerpos, "min": a.min, "max": a.max, "semilla": a.semilla},
        "anuncios": anuncios})
    avisar(f"{len(anuncios)} combinaciones en mi-negocio/combos.json "
           f"(con estas piezas se pueden armar hasta ~{posibles}).")
    if len(anuncios) < a.cantidad:
        avisar("No alcancé la cantidad pedida con esa duración: prueba con --min o --max más amplios.")


if __name__ == "__main__":
    main()
