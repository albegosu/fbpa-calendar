# fbpa-ics

Feed `.ics` autoactualizable con los partidos de un equipo en una competición de [fbpa.es](https://www.fbpa.es).

Un workflow de GitHub Actions descarga la página de la competición 3 veces al día, regenera
`docs/calendar.ics` y solo hace commit si algo ha cambiado (horarios, pabellones, resultados).
GitHub Pages sirve el fichero en una URL pública a la que Google Calendar se suscribe.

## Puesta en marcha

1. Crea un repo **público** (Pages gratis lo requiere) y sube este contenido.
2. Settings → Pages → *Deploy from a branch* → `main` / `/docs`.
3. Actions → *Actualizar calendario* → **Run workflow** para la primera ejecución real.
4. Google Calendar → Otros calendarios → **+** → *Desde URL*:
   `https://<usuario>.github.io/<repo>/calendar.ics`

## Probar en local

```bash
pip install -r requirements.txt
python fbpa_ics.py \
  --url "https://www.fbpa.es/competicion-17433/competiciones-federadas-" \
  --categoria "PRIMERA FBPA Fem" \
  --team "GIJON BASKET 2015 CORPI" \
  --out docs/calendar.ics
```

## Otro equipo o competición

Cambia `COMPETITION_URL`, `CATEGORIA`, `TEAM` y `CAL_NAME` en `.github/workflows/update-calendar.yml`.

La página de competición carga por defecto la primera categoría del desplegable (p. ej. *PRIMERA FBPA Mas*);
`CATEGORIA` elige otra por su nombre en el desplegable o por su id. Un mismo club puede tener equipos con
el mismo nombre en varias categorías, así que no basta con `TEAM`. Si la categoría no existe, el error lista
las disponibles. Nombres de categoría y equipo se comparan sin tildes ni mayúsculas.

## Comportamiento

- UID estable por jornada (`<equipo>-j<N>`): si cambia la hora, Google actualiza el evento en vez de duplicarlo.
- Partidos jugados: el resultado aparece en el título.
- Jornadas de descanso: se omiten. Partido sin hora: evento de día completo.
- Si el parser no encuentra ningún partido del equipo, el workflow falla (GitHub te avisa por email) y no se sobrescribe el feed.
