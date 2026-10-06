"""Revisa (y con --arreglar instala) todo lo que necesita la Fábrica de Videos.

Uso:
    python3 scripts/doctor.py              solo revisa
    python3 scripts/doctor.py --arreglar   instala lo que falte y vuelve a revisar
    python3 scripts/doctor.py --arreglar --modelo small   además descarga el modelo de transcripción

Corre con el Python del sistema: no necesita nada instalado de antemano.
Todo lo que instala queda DENTRO de la carpeta del kit (.venv), no toca tu computador.
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VENV = RAIZ / ".venv"
ES_WINDOWS = platform.system() == "Windows"
PY_VENV = VENV / ("Scripts/python.exe" if ES_WINDOWS else "bin/python")

OK, MAL = "[OK]", "[FALTA]"


def linea(estado, texto):
    print(f"{estado:8} {texto}", flush=True)


def correr(cmd, mostrar=False, silencioso=False):
    r = subprocess.run([str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    salida = r.stdout.decode("utf-8", "replace")
    if mostrar or (r.returncode != 0 and not silencioso):
        print(salida[-3000:])
    return r.returncode == 0, salida


def revisar_python():
    v = sys.version_info
    bueno = v >= (3, 9)
    linea(OK if bueno else MAL, f"Python {v.major}.{v.minor}.{v.micro} (se necesita 3.9 o más nuevo)")
    return bueno


def revisar_venv(arreglar):
    if PY_VENV.exists():
        linea(OK, "Entorno propio del kit (.venv)")
        return True
    if not arreglar:
        linea(MAL, "Entorno propio del kit (.venv). Se crea con --arreglar")
        return False
    print("Creando el entorno del kit (.venv)...", flush=True)
    bueno, _ = correr([sys.executable, "-m", "venv", VENV])
    linea(OK if bueno else MAL, "Entorno propio del kit (.venv)")
    return bueno


PAQUETES = {"faster_whisper": "transcripción", "imageio_ffmpeg": "ffmpeg de respaldo",
            "PIL": "subtítulos", "av": "lectura de video"}


def revisar_paquetes(arreglar):
    if not PY_VENV.exists():
        linea(MAL, "Paquetes de Python (primero falta el .venv)")
        return False
    faltan = []
    for mod, para in PAQUETES.items():
        bueno, _ = correr([PY_VENV, "-c", f"import {mod}"], silencioso=True)
        if not bueno:
            faltan.append(mod)
    if faltan and arreglar:
        print("Instalando paquetes (puede tardar 1 a 3 minutos la primera vez)...", flush=True)
        correr([PY_VENV, "-m", "pip", "install", "--upgrade", "pip"])
        bueno, _ = correr([PY_VENV, "-m", "pip", "install", "-r", RAIZ / "requirements.txt"], mostrar=False)
        faltan = []
        for mod in PAQUETES:
            b, _ = correr([PY_VENV, "-c", f"import {mod}"], silencioso=True)
            if not b:
                faltan.append(mod)
    for mod, para in PAQUETES.items():
        linea(OK if mod not in faltan else MAL, f"Paquete {mod} ({para})")
    return not faltan


def revisar_ffmpeg():
    ff = shutil.which("ffmpeg")
    origen = "del sistema"
    if not ff and PY_VENV.exists():
        bueno, salida = correr([PY_VENV, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"])
        if bueno:
            ff = salida.strip().splitlines()[-1]
            origen = "incluido en el kit"
    if not ff:
        linea(MAL, "ffmpeg (se instala con --arreglar, viene dentro de imageio-ffmpeg)")
        return False
    bueno, salida = correr([ff, "-hide_banner", "-encoders"])
    tiene_x264 = "libx264" in salida
    linea(OK if tiene_x264 else MAL, f"ffmpeg {origen} con H.264 ({ff})")
    return tiene_x264


def revisar_fuente():
    f = RAIZ / "fuentes" / "Poppins-ExtraBold.ttf"
    linea(OK if f.exists() else MAL, "Tipografía de los subtítulos")
    return f.exists()


def revisar_carpetas():
    for nombre in ("10_GRABACIONES", "20_PIEZAS", "30_ANUNCIOS", "mi-negocio"):
        (RAIZ / nombre).mkdir(exist_ok=True)
    linea(OK, "Carpetas 10_GRABACIONES, 20_PIEZAS, 30_ANUNCIOS y mi-negocio")
    return True


def descargar_modelo(nombre):
    print(f"Descargando el modelo de transcripción '{nombre}' (una sola vez)...", flush=True)
    codigo = ("from faster_whisper import WhisperModel;"
              f"WhisperModel('{nombre}', device='cpu', compute_type='int8');print('listo')")
    bueno, _ = correr([PY_VENV, "-c", codigo], mostrar=False)
    linea(OK if bueno else MAL, f"Modelo de transcripción '{nombre}'")
    return bueno


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arreglar", action="store_true", help="instala lo que falte")
    ap.add_argument("--modelo", default=None, help="descarga este modelo de transcripción (ej: small)")
    a = ap.parse_args()
    print(f"\nFábrica de Videos · revisión del equipo ({platform.system()} {platform.machine()})\n", flush=True)
    resultados = [
        revisar_python(),
        revisar_venv(a.arreglar),
        revisar_paquetes(a.arreglar),
        revisar_ffmpeg(),
        revisar_fuente(),
        revisar_carpetas(),
    ]
    if a.modelo and all(resultados):
        resultados.append(descargar_modelo(a.modelo))
    print()
    if all(resultados):
        print("LISTO: la fábrica está instalada.")
        sys.exit(0)
    print("TODAVÍA NO: arregla lo marcado como [FALTA]" + ("" if a.arreglar else " (prueba con --arreglar)") + ".")
    sys.exit(1)


if __name__ == "__main__":
    main()
