# Guía completa · La Fábrica de Videos

> La versión corta está en el PDF (`guia/`). Aquí está todo, por si quieres entender cada paso.

## 1. La idea en 30 segundos

Un anuncio de video tiene tres partes: un **gancho** (los primeros segundos, que hacen que alguien se quede), uno o más **cuerpos** (lo que explicas) y un **llamado a la acción** (lo que quieres que haga).

Si escribes esas partes para que encajen entre sí, como piezas de Lego, con una sola grabación puedes armar cientos de anuncios distintos: el gancho 1 con los cuerpos 3 y 7, el gancho 4 con los cuerpos 2 y 9, y así. Meta necesita creativos nuevos todo el tiempo (cuando un anuncio se cansa, sube tu costo por cliente), y este es el camino más barato para darle volumen sin grabar todos los días.

Ojo: esto **no es inteligencia artificial generando videos**. Son tus tomas reales. Claude solo las encuentra, las corta y las combina.

## 2. Instalación

1. Descarga la app de Claude desde [claude.com/download](https://claude.com/download) e inicia sesión (necesitas un plan pagado: Pro o Max).
2. Entra a la pestaña **Code** y abre un chat nuevo.
3. Copia la caja que está en el `README.md` (o en la página 5 del PDF) y pégala.
4. Claude descarga el kit en tu carpeta Documentos, instala lo que falte (solo dentro de la carpeta del kit) y te avisa cuando diga **LISTO**.

La primera vez descarga un modelo de transcripción de unos 500 MB, que también queda dentro de la carpeta del kit. Después todo funciona sin internet.

## 3. Tu guion

Claude te hace preguntas sobre tu negocio, una a la vez: qué vendes, a quién, a cuánto, qué pruebas reales tienes y cómo hablas. Con eso escribe tu guion:

- **10 ganchos**: frases cortas para los primeros 3 segundos.
- **10 cuerpos**: cada uno con una sola idea (el problema, cómo funciona, una prueba real o la oferta).
- **3 llamados a la acción**.

Te lo muestra en una tabla. Cambia lo que quieras: es tu voz. Cuando lo apruebes, te deja un `teleprompter.txt` listo para leer.

Si quieres ver cómo se ve uno de verdad, mira `plantillas/guion.ejemplo.json`: es el de Benja, con 10 ganchos que salen de sus anuncios que mejor vendieron.

## 4. Cómo grabar

- Antes de partir, apaga el video HDR. En iPhone: Ajustes > Cámara > Grabar video > Video HDR. Si se te olvida, el kit lo convierte solo, pero sale mejor sin HDR.
- Todo en una sola sesión: misma ropa, misma luz, mismo encuadre.
- Celular en vertical, a la altura de los ojos.
- Lee cada pieza de corrido y quédate 2 segundos en silencio antes de la siguiente.
- Si te equivocas, para, espera 2 segundos y repite la pieza completa. **La última toma es la que se usa**: no tienes que borrar nada.
- No digas los códigos (G01, C03) en voz alta.

Puedes grabar todo en un solo video largo o en varios clips. Pásalos al computador por AirDrop, cable o Google Drive (por WhatsApp no: los comprime) y después arrástralos al chat con Claude, o a la carpeta `10_GRABACIONES`.

## 5. Cortar y armar

Dile "corta mi grabación". Claude transcribe, encuentra cada pieza y te cuenta qué encontró y qué faltó (está en `20_PIEZAS/REPORTE.md`). Si faltó algo, puedes grabar solo esa pieza.

Después dile "arma 3 de prueba". Míralos y pide cambios: subtítulos más grandes, en mayúsculas, de otro color, sin subtítulos, el recorte más arriba. Cuando te gusten, "arma 30 anuncios": no repite los de prueba.

Los videos quedan en `30_ANUNCIOS`, en 9:16 (Reels y Stories) y 4:5 (feed), con nombres que se leen solos: `20261007_PRECIOCONGELADO_LEGO_G06-C03-C07-CTA1_9x16.mp4`.

## 6. Subirlos a Meta

Lo más seguro es subirlos a mano en el Administrador de anuncios, dentro de tu campaña de prueba. Si tienes conectado el conector de **Meta Ads** en Claude, puedes pedirle que los suba él: todo queda **en pausa** hasta que tú lo actives.

Un consejo de la cuenta de Imperio: las variantes del mismo gancho van en el mismo conjunto de anuncios. Si cada una va suelta, el gasto se reparte en pedacitos y ninguna junta evidencia para ganar.

## 7. Preguntas frecuentes

**Necesito saber programar?** No. Claude corre todo. Tú solo respondes y grabas.

**Funciona en Windows?** Sí. Claude instala Python si falta y el resto queda dentro de la carpeta del kit.

**Cuánto cuesta?** El kit es gratis. Necesitas tu plan de Claude. La transcripción corre en tu computador, sin cobros extra.

**Y si grabé en horizontal?** Funciona, pero los videos verticales salen recortados al centro. Para la próxima, graba en vertical.

**Los subtítulos tienen una palabra mal escrita.** Pídele a Claude que la corrija en el guion y que vuelva a armar. Los subtítulos usan las palabras de tu guion con los tiempos de lo que dijiste.

**Se me olvidó una pieza.** Graba solo esa, déjala en `10_GRABACIONES` y pídele que corte de nuevo.

**Grabé con Video HDR.** No pasa nada: el kit lo pasa a color normal al cortar. Para la próxima, apágalo y te ahorras ese paso.

**Me equivoqué y empecé la frase de nuevo sin hacer la pausa.** El kit se queda con el último intento y te avisa en el reporte para que lo escuches.

---

Imperio Agéntico · Curso Claude para Meta Ads · skool.com/imperio
