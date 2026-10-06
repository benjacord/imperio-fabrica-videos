# CLAUDE.md · Fábrica de Videos (el sistema Lego)

Este archivo es para ti, Claude. Explica qué hace este kit, cómo lo operas y las reglas que no se rompen.
Es un recurso de Imperio Agéntico para el curso "Claude para Meta Ads" de Benja (@bencord).

## A quién estás ayudando

A una persona que NO es técnica. Puede que nunca haya abierto una terminal.

- Haz todo tú: instalar, correr scripts, mover archivos. Nunca le pidas que escriba un comando ni que edite un archivo a mano.
- Habla en español simple y en tú. Explica cada paso en una frase antes de hacerlo.
- Mantén una lista de tareas visible y ve marcando lo que terminas.
- Pregunta UNA cosa a la vez. Si te pasa un archivo (una grabación, un logo), muévelo tú a la carpeta que corresponde.
- Si algo pide permiso para instalarse, explícale qué es y que puede tocar "Permitir".
- Nunca borres sus grabaciones (10_GRABACIONES) ni su carpeta mi-negocio.

## Qué hace el kit

Graba UNA sesión leyendo un guion modular: ganchos, cuerpos y llamados a la acción (CTA) que encajan entre sí como piezas de Lego. El kit encuentra cada pieza en la grabación, la corta y arma cientos de combinaciones listas para Meta, en 9:16 y 4:5, con subtítulos quemados.

10 ganchos, 10 cuerpos (de a 2 por anuncio) y 3 CTA ya dan más de 1.000 anuncios posibles. En la cuenta de Imperio, 74 anuncios armados así trajeron 113 compras a $73 cada una (desde el 28 de agosto de 2026), contra $83 de promedio de la cuenta: úsalo para motivar, no para prometer. No necesitas tantos: con 20 a 40 buenos alcanzas para llenar el laboratorio un mes.

## Carpetas

| Carpeta | Qué hay |
|---|---|
| `mi-negocio/` | Lo de la persona: `perfil.md`, `guion.json`, `teleprompter.txt`, `combos.json`, `textos-meta.md` |
| `10_GRABACIONES/` | Aquí van sus videos crudos (uno largo o varios clips, da igual) |
| `20_PIEZAS/` | Las piezas cortadas, `piezas.json` y `REPORTE.md` |
| `30_ANUNCIOS/` | Los anuncios terminados y `INDICE.csv` |
| `plantillas/` | `guion.ejemplo.json` (el de Benja, con ganchos reales de sus anuncios ganadores) y `perfil-negocio.md` |
| `scripts/` | El motor. No hace falta editarlo |

## Cómo correr los scripts

La primera vez: `python3 scripts/doctor.py --arreglar --modelo small` (en Windows: `py scripts\doctor.py --arreglar --modelo small`). Crea `.venv` dentro del kit, instala lo necesario (faster-whisper, ffmpeg de respaldo, Pillow) y descarga el modelo de transcripción (unos 500 MB, una sola vez). Repite hasta que diga LISTO.

Después, siempre con el Python del kit:
- Mac y Linux: `.venv/bin/python scripts/<script>.py`
- Windows: `.venv\Scripts\python scripts\<script>.py`

Si en Windows no hay Python, instálalo con `winget install Python.Python.3.12` y vuelve a correr doctor. En Mac, si `python3` pide instalar las herramientas de desarrollador, acepta ese diálogo.

## El flujo completo

### 1. Conocer el negocio (entrevista, una pregunta a la vez)

Llena `mi-negocio/perfil.md` usando `plantillas/perfil-negocio.md`. Lo mínimo:
1. Cómo se llama el negocio y qué vende (producto o servicio, en una frase).
2. Precio y oferta actual (lo que de verdad existe hoy: no inventes descuentos ni garantías).
3. A quién le vende y qué problema le resuelve.
4. Pruebas reales: clientes, cifras, testimonios, premios. Si no tiene, se dice y se trabaja con demostración en vez de prueba.
5. Objeciones que escucha seguido.
6. A dónde manda el anuncio (web, WhatsApp, formulario) y qué acción quiere (comprar, agendar, escribir).
7. Cómo habla: formal o cercano, de tú o de usted, alguna palabra que use mucho. Pídele un video o un audio suyo si quiere que el guion suene más a él.

### 2. Escribir el guion modular

Escribe `mi-negocio/guion.json` con el formato de `plantillas/guion.ejemplo.json`:

```json
{
  "negocio": "Nombre",
  "ganchos": [{"id": "G01", "angulo": "precio congelado", "texto": "..."}],
  "cuerpos": [{"id": "C01", "rol": "problema", "texto": "..."}],
  "ctas": [{"id": "CTA1", "texto": "..."}]
}
```

Para partir: **10 ganchos, 10 cuerpos y 3 CTA**. Muéstraselo en una tabla legible (no el JSON), ajústalo con la persona y recién ahí corre `scripts/teleprompter.py`, que deja `mi-negocio/teleprompter.txt` listo para leer en cámara.

**Reglas del guion (salen de la cuenta real de Imperio, que invirtió más de $200.000 en Meta):**

- **Cada pieza se tiene que poder pegar con cualquier otra.** Un cuerpo no puede decir "como te dije", "eso que viste" ni depender de un gancho en particular. Si lo lees después de cualquier gancho, tiene que sonar natural.
- **Gancho:** 1 o 2 frases, menos de 4 segundos (unas 15 palabras como máximo). Abre una pregunta en la cabeza del que mira. Las familias que mejor le vendieron a Imperio: precio y urgencia con dato, testimonio con cifra, demostración, historia personal y autoridad (un premio, un ranking). Cada gancho lleva un "angulo" corto, que se usa para nombrar el archivo.
- **Evita la confrontación y el miedo** ("te van a pasar por encima", "los flojos van a ganar"): en la cuenta de Imperio fue el 8% del gasto a más del triple del costo por compra normal.
- **Cuerpo:** una sola idea, 5 a 9 segundos. Cada uno lleva un "rol": `problema`, `mecanismo` (cómo funciona), `prueba` (resultado real) u `oferta` (qué incluye y cuánto cuesta). El armador respeta ese orden.
- **CTA:** una sola acción, menos de 4 segundos ("Toca el botón de abajo y agenda tu hora").
- **Duración final:** 20 a 30 segundos. En la cuenta de Imperio fueron los que mejor vendieron; los de menos de 20 segundos fueron los peores aunque enganchaban más.
- **Cifras en números** ("$59", "3.800", "14 minutos"): así salen bien en los subtítulos.
- **Nunca inventes prueba:** ni clientes, ni cifras, ni testimonios. Si no existe, no va.
- Escribe como habla la persona, no como un anuncio.

### 3. Grabar

Explícale cómo grabar (está también al inicio de `teleprompter.txt`):
- Una sola sesión, misma ropa, misma luz, mismo encuadre. Celular en vertical a la altura de los ojos.
- Lee cada pieza de corrido y quédate 2 segundos en silencio antes de la siguiente.
- Si se equivoca: para, 2 segundos de silencio y repite la pieza completa. **La última toma manda**, no hay que borrar nada.
- No decir los códigos (G01, C03) en voz alta.
- Al terminar, que te pase el video (o los clips) y tú los dejas en `10_GRABACIONES/`.

### 4. Cortar

1. `scripts/transcribir.py` (transcribe en el computador, sin internet).
2. `scripts/cortar.py` encuentra cada pieza, usa la última toma y deja todo en `20_PIEZAS/`.
3. Lee `20_PIEZAS/REPORTE.md` y cuéntale en simple qué salió y qué no.
   - Si faltan piezas: o no se grabaron, o se dijeron muy distinto. Opciones: grabar solo esas, ajustar el texto del guion a lo que dijo y volver a cortar, o bajar `--umbral` a 0.65.
   - Las marcadas con ⚠️ se parecen menos al guion: suele ser una cifra dicha distinto. Escucha el texto y decide.

### 5. Armar

1. `scripts/combinar.py --cantidad 30` decide las combinaciones (`mi-negocio/combos.json`).
2. `scripts/armar.py --solo 3` arma 3 de prueba. Muéstraselos (abre la carpeta `30_ANUNCIOS`) y pregúntale qué ajustar: subtítulos en mayúsculas (`--mayusculas`), solo la frase sin pintar palabra por palabra (`--subtitulos frase`), sin subtítulos (`--subtitulos no`), otro color (`--color "#00E5FF"`), recorte más arriba o más abajo (`--recorte-y 0.3`).
3. Con su OK, `scripts/armar.py` arma el resto. Por defecto saca 9:16 (Reels y Stories) y 4:5 (feed).

Los nombres siguen la regla `AAAAMMDD_ANGULO_LEGO_PIEZAS_FORMATO.mp4`. Explícale por qué: si un anuncio se llama `IMG_1873.MOV`, en un mes nadie sabe qué era. Con el nombre se lee el ángulo y las piezas sin abrirlo.

### 6. Textos para Meta

Escribe `mi-negocio/textos-meta.md`: por cada ángulo, un texto principal (2 a 5 líneas, con la oferta real y el precio si corresponde) y un titular de menos de 40 caracteres. Con la voz de la persona.

### 7. Subir

- **A mano (lo más seguro):** en el Administrador de anuncios, crea los anuncios dentro de la campaña de prueba y arrastra los videos de `30_ANUNCIOS`. Pon el mismo gancho en el mismo conjunto para no fragmentar el gasto.
- **Con el conector de Meta (opcional):** si la persona tiene conectado "Meta Ads" en Claude, puedes intentar subirlos tú. Reglas: todo se crea **EN PAUSA**, nunca actives nada sin su OK explícito, y si la subida de video falla, vuelve al método a mano sin insistir.

## Si algo falla

| Pasa esto | Haz esto |
|---|---|
| doctor dice FALTA | Corre `doctor.py --arreglar` otra vez y lee el error. En Mac, acepta instalar las herramientas de desarrollador si aparece el diálogo |
| Transcribe muy lento | Usa `--modelo base`. Es más rápido y alcanza para encontrar las piezas |
| No encuentra piezas | Revisa que haya 2 segundos de silencio entre piezas. Prueba `cortar.py --umbral 0.65` |
| Se come el inicio o el final de una palabra | `cortar.py --margen-inicio 0.2 --margen-fin 0.45` |
| Subtítulo mal escrito | Corrige el texto de esa pieza en `guion.json` y vuelve a correr `cortar.py` y `armar.py` |
| Grabó en horizontal | Funciona, pero el 9:16 sale recortado al centro. Recomiéndale grabar en vertical la próxima vez |

## Lo que nunca haces

- Inventar testimonios, cifras, clientes, premios, garantías o descuentos.
- Borrar sus grabaciones o su carpeta `mi-negocio`.
- Publicar o activar anuncios sin su OK.
- Pedirle que corra comandos o edite archivos.
