"""Transcribe tus grabaciones con la marca de tiempo de cada palabra.

Uso:
    .venv/bin/python scripts/transcribir.py                 todo lo que hay en 10_GRABACIONES
    .venv/bin/python scripts/transcribir.py archivo.mp4     solo ese archivo
    --modelo small (por defecto) · base es más rápido · medium es más preciso

Corre en tu computador, sin internet (salvo la primera vez, que descarga el modelo).
Deja el resultado en 20_PIEZAS/_transcripciones/.
"""
import argparse
import re
import time
import warnings
from pathlib import Path

from comun import (EXT_VIDEO, GRABACIONES, MODELOS, TRANSCRIPCIONES, avisar, escribir_json, morir)

warnings.filterwarnings("ignore", category=RuntimeWarning)


def limpiar(palabras):
    """Une cifras partidas ("3" + ".800" = "3.800") y saca los signos de apertura."""
    out = []
    for w in palabras:
        t = w["w"].replace("¿", "").replace("¡", "").strip()
        if not t:
            continue
        if out and re.match(r"^[.,]\d", t) and re.search(r"\d$", out[-1]["w"]):
            out[-1]["w"] += t
            out[-1]["e"] = w["e"]
            continue
        out.append({**w, "w": t})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archivos", nargs="*")
    ap.add_argument("--modelo", default="small")
    ap.add_argument("--idioma", default="es")
    ap.add_argument("--rehacer", action="store_true", help="vuelve a transcribir aunque ya exista")
    a = ap.parse_args()

    if a.archivos:
        archivos = [Path(x) for x in a.archivos]
    else:
        archivos = sorted(p for p in GRABACIONES.iterdir() if p.suffix.lower() in EXT_VIDEO)
    if not archivos:
        morir("No hay videos en 10_GRABACIONES. Arrastra ahí tu grabación y vuelve a intentarlo.")

    from faster_whisper import WhisperModel
    avisar(f"Cargando el modelo '{a.modelo}'...")
    modelo = WhisperModel(a.modelo, device="cpu", compute_type="int8", download_root=str(MODELOS))
    TRANSCRIPCIONES.mkdir(parents=True, exist_ok=True)

    for f in archivos:
        if not f.exists():
            morir(f"No existe {f}")
        destino = TRANSCRIPCIONES / (f.stem + ".json")
        if destino.exists() and not a.rehacer and destino.stat().st_mtime > f.stat().st_mtime:
            avisar(f"Ya estaba transcrito: {f.name}")
            continue
        t0 = time.time()
        avisar(f"Transcribiendo {f.name}...")
        segmentos, info = modelo.transcribe(
            str(f), language=a.idioma, word_timestamps=True, beam_size=5,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 400},
            condition_on_previous_text=False)
        palabras = []
        for s in segmentos:
            for w in (s.words or []):
                texto = w.word.strip()
                if texto:
                    palabras.append({"w": texto, "s": round(w.start, 3), "e": round(w.end, 3),
                                     "p": round(w.probability, 3)})
        palabras = limpiar(palabras)
        escribir_json(destino, {"archivo": f.name, "duracion": round(info.duration, 3),
                                "modelo": a.modelo, "palabras": palabras})
        (TRANSCRIPCIONES / (f.stem + ".txt")).write_text(
            " ".join(w["w"] for w in palabras), encoding="utf-8")
        avisar(f"OK {f.name}: {len(palabras)} palabras en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
