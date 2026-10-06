"""Piezas compartidas por todos los scripts de la Fábrica de Videos.

Rutas del kit, cómo encontrar ffmpeg, cómo medir un video y cómo normalizar texto
para comparar lo que dijiste con lo que decía el guion.
"""
import functools
import io
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GRABACIONES = RAIZ / "10_GRABACIONES"
PIEZAS = RAIZ / "20_PIEZAS"
ANUNCIOS = RAIZ / "30_ANUNCIOS"
NEGOCIO = RAIZ / "mi-negocio"
TRANSCRIPCIONES = PIEZAS / "_transcripciones"
MODELOS = RAIZ / ".modelos"   # el modelo de transcripción también queda dentro del kit
FUENTE = RAIZ / "fuentes" / "Poppins-ExtraBold.ttf"
EXT_VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".3gp"}

# Lienzo estándar según cómo grabaste
LIENZOS = {
    "vertical": (1080, 1920),
    "horizontal": (1920, 1080),
    "cuadrado": (1080, 1080),
}


def avisar(msg):
    print(msg, flush=True)


def morir(msg, codigo=1):
    print("\nERROR: " + msg, file=sys.stderr, flush=True)
    sys.exit(codigo)


def _texto_de(cmd):
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return r.stdout.decode("utf-8", "replace")
    except OSError:
        return ""


@functools.lru_cache(maxsize=None)
def ffmpeg_bin():
    """El ffmpeg que trae el kit (imageio-ffmpeg); si no está, el del sistema.
    Tiene que poder exportar H.264 (libx264): si uno no puede, prueba con el otro."""
    candidatos = []
    try:
        import imageio_ffmpeg
        candidatos.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    sistema = shutil.which("ffmpeg")
    if sistema:
        candidatos.append(sistema)
    for ff in candidatos:
        if "libx264" in _texto_de([ff, "-hide_banner", "-encoders"]):
            return ff
    return None


@functools.lru_cache(maxsize=None)
def tiene_filtro(nombre):
    """True si el ffmpeg elegido trae ese filtro (por ejemplo zscale, para convertir HDR)."""
    ff = ffmpeg_bin()
    if not ff:
        return False
    return any(l.split()[1:2] == [nombre] for l in _texto_de([ff, "-hide_banner", "-filters"]).splitlines()
               if len(l.split()) > 1)


def hdr_de(ruta):
    """Si el video viene en HDR (lo normal en iPhone), devuelve su curva: 'arib-std-b67' (HLG)
    o 'smpte2084' (PQ). Si viene en color normal (SDR), devuelve None."""
    ff = ffmpeg_bin()
    if not ff:
        return None
    for linea in _texto_de([ff, "-hide_banner", "-i", str(ruta)]).splitlines():
        if "Video:" in linea:
            for curva in ("arib-std-b67", "smpte2084"):
                if curva in linea:
                    return curva
            return None
    return None


def filtro_hdr(curva):
    """Pasa un video HDR a color normal (SDR, bt709) para que en Meta no se vea lavado ni quemado.
    El blanco de referencia del HDR (203 nits) queda como blanco normal y las luces muy altas
    se comprimen suave en vez de quemarse."""
    return (f"zscale=tin={curva}:pin=bt2020:min=bt2020nc:t=linear:npl=203,format=gbrpf32le,"
            f"zscale=p=bt709,tonemap=tonemap=mobius:param=0.85:desat=0:peak=4.9,"
            f"zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


# Último filtro de cada video: lo marca como color normal (SDR, bt709). Así ningún video
# sale marcado como HDR por error (las opciones -color_trc de ffmpeg 7 no siempre se graban).
ETIQUETA_SDR = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"


def correr(cmd):
    """Corre un comando y, si falla, muestra el final del error en español."""
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        cola = r.stderr.decode("utf-8", "replace")[-2500:]
        raise RuntimeError("ffmpeg no pudo terminar este paso.\n" + cola)
    return r


def duracion(ruta):
    """Duración en segundos (usa PyAV, que viene con faster-whisper)."""
    import av
    with av.open(str(ruta)) as c:
        if c.duration:
            return c.duration / 1_000_000
        mejor = 0.0
        for s in c.streams:
            if s.duration and s.time_base:
                mejor = max(mejor, float(s.duration * s.time_base))
        return mejor


def tamano_visible(ruta):
    """Ancho y alto como se VE el video (ya girado, como lo grabó el celular)."""
    ff = ffmpeg_bin()
    r = subprocess.run(
        [ff, "-v", "error", "-i", str(ruta), "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "png", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("No pude leer un cuadro de " + str(ruta))
    from PIL import Image
    im = Image.open(io.BytesIO(r.stdout))
    return im.size


def orientacion(ancho, alto):
    if alto > ancho * 1.15:
        return "vertical"
    if ancho > alto * 1.15:
        return "horizontal"
    return "cuadrado"


def normalizar(texto):
    """minúsculas, sin tildes ni signos: para comparar guion con transcripción."""
    t = unicodedata.normalize("NFKD", str(texto).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def leer_json(ruta, defecto=None):
    ruta = Path(ruta)
    if not ruta.exists():
        return defecto
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def escribir_json(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def cargar_guion(ruta=None):
    """Lee mi-negocio/guion.json y devuelve la lista plana de piezas."""
    ruta = Path(ruta) if ruta else NEGOCIO / "guion.json"
    g = leer_json(ruta)
    if not g:
        morir("No encontré el guion en " + str(ruta) + ". Pídele a Claude que lo escriba primero.")
    piezas = []
    for tipo, clave in (("gancho", "ganchos"), ("cuerpo", "cuerpos"), ("cta", "ctas")):
        for p in g.get(clave, []):
            if not p.get("id") or not p.get("texto"):
                morir("Hay una pieza sin id o sin texto en " + clave + ".")
            piezas.append({**p, "tipo": tipo})
    ids = [p["id"] for p in piezas]
    repetidos = {i for i in ids if ids.count(i) > 1}
    if repetidos:
        morir("Hay ids repetidos en el guion: " + ", ".join(sorted(repetidos)))
    return g, piezas


def slug(texto, largo=24):
    t = normalizar(texto).upper().replace(" ", "")
    return t[:largo] or "ANUNCIO"
