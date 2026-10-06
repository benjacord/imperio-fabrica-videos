"""Convierte tu guion en un texto listo para leer en cámara (teleprompter).

Uso:
    .venv/bin/python scripts/teleprompter.py
Escribe mi-negocio/teleprompter.txt: primero los ganchos, después los cuerpos y al final los CTA,
con una pausa marcada entre cada pieza. Ábrelo en cualquier app de teleprompter o en tu pantalla.
"""
import datetime

from comun import NEGOCIO, avisar, cargar_guion

REGLAS = """CÓMO GRABAR (léelo una vez antes de partir)

1. Graba todo en UNA sesión, con la misma ropa, la misma luz y el mismo encuadre.
2. Celular en vertical, a la altura de los ojos. La cara en el tercio de arriba.
3. Lee cada pieza de corrido y quédate callado 2 segundos antes de la siguiente.
4. Si te equivocas: para, cuenta 2 segundos en silencio y repite la pieza COMPLETA.
   La última toma es la que se usa, no tienes que borrar nada.
5. No digas en voz alta los códigos (G01, C03, CTA1): son solo para ti.
6. Cada gancho tiene que sonar como el comienzo de un video. Cada cuerpo, como si
   viniera después de cualquier gancho. Mira a la cámara, no al texto, al empezar.
"""


def main():
    g, piezas = cargar_guion()
    nombre = g.get("negocio", "tu negocio")
    lineas = [f"GUION LEGO · {nombre} · {datetime.date.today().isoformat()}", "", REGLAS, "=" * 48, ""]
    titulos = {"gancho": "GANCHOS", "cuerpo": "CUERPOS", "cta": "LLAMADOS A LA ACCIÓN"}
    actual = None
    for p in piezas:
        if p["tipo"] != actual:
            actual = p["tipo"]
            lineas += ["", f"---  {titulos[actual]}  ---", ""]
        lineas += [f"[{p['id']}]", p["texto"].strip(), "", "[PAUSA 2 SEGUNDOS]", ""]
    lineas += ["", "FIN. Gracias. Arrastra el video (o los videos) a la carpeta 10_GRABACIONES."]
    destino = NEGOCIO / "teleprompter.txt"
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    total = sum(len(p["texto"].split()) for p in piezas)
    avisar(f"Listo: {destino.name} con {len(piezas)} piezas (~{total / 2.6 / 60:.0f} minutos de lectura).")


if __name__ == "__main__":
    main()
