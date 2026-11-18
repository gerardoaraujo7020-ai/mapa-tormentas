# Seguimiento de tormentas · provincia de Buenos Aires (El Viejo Viento)

Dado un rango de fechas, baja datos satelitales y de modelo **gratuitos y sin registro**
y arma cartas PNG + un boletín PDF para la provincia.

## Instalar (una vez)
    pip install -r requirements.txt

## Correr
    python correr.py --inicio 2026-11-12T18 --fin 2026-11-14T12 --nombre "Tormenta del 13 y 14 de noviembre"

- Horas en **UTC** (hora argentina + 3). Ej.: 15 h de Argentina = 18 UTC.
- `--localidades "Benito Juárez,Tandil,Necochea"` elige qué localidades van a la tabla y los gráficos
  (la lista está en `tormentas/cartas.py`, se pueden agregar más).
- `--goes-cada 2` baja una imagen satelital cada 2 h en vez de cada 1 (más rápido).
- `--sin-pronostico` saltea el pronóstico de 72 h.
- `--sin-animaciones` saltea los videos; `--anim-cada 10` hace la animación satelital cada 10 min (más fluida, baja más).
- Las animaciones necesitan **ffmpeg** instalado (Windows: `winget install ffmpeg`).
- Sale todo en `salida/` (o lo que pongas en `--salida`). Los datos bajados quedan en `cache/`.

Un evento de 2 días baja ~1 GB de satélite (se recorta y se borra al vuelo) y tarda unos minutos.

## Qué produce
| Archivo | Qué es | Fuente |
|---|---|---|
| 01_lluvia_acumulada.png | lluvia total del evento | GFS 0,25° (plazos 1-6 h encadenados) |
| 02_rafaga_maxima.png | ráfaga máxima | GFS |
| 03_porcentaje_normal.png | lluvia del evento como % de la normal del mes | GFS + GPCP 1991-2020 |
| 04_goes19_tope_nube_pico.png | imagen IR con el tope más frío | GOES-19 ABI canal 13 |
| 05_goes19_secuencia.png | 6 imágenes a lo largo del evento | GOES-19 |
| 06_goes19_frecuencia_topes_frios.png | % de horas con topes < −52 °C | GOES-19 |
| 07_carta_sinoptica.png | presión, viento y CAPE en la hora pico | GFS |
| 08_series_localidades.png | lluvia horaria y ráfagas por localidad | GFS |
| 09_pronostico_lluvia_72h.png | lluvia prevista próximas 72 h | GFS última corrida |
| 10_animacion_goes19.mp4 / .gif | topes de nube cada 30 min | GOES-19 |
| 11_animacion_satelite_y_lluvia.mp4 / .gif | satélite y lluvia del modelo lado a lado, hora a hora | GOES-19 + GFS |
| boletin_tormenta.pdf | todo junto con resumen automático | |
| resumen.json | los números, para reusar (redes, placas) | |

Todo sale de buckets públicos de NOAA en Amazon (AWS Open Data): `noaa-goes19`,
`noaa-gfs-bdp-pds`, `noaa-cdr-precip-gpcp-monthly-pds`.

## Límites a tener en cuenta
- La lluvia y las ráfagas del evento son del **modelo** (lo más cercano a un análisis), no de pluviómetros.
  En tormentas convectivas el modelo puede errar la ubicación: por eso el boletín compara contra el
  satélite y avisa cuando no coinciden.
- La normal GPCP es de 2,5° (~250 km): sirve como referencia regional, no por partido.
- Fuentes que se pueden sumar y necesitan algo de tu lado:
  - **IMERG** (lluvia satelital NASA, 10 km, cada 30 min): cuenta gratis en NASA Earthdata.
  - **FIRMS** (focos de calor): clave gratis (MAP_KEY) en firms.modaps.eosdis.nasa.gov.
  - **CHIRPS** y **ERA5-Land vía Open-Meteo**: libres, sin cuenta.
  - El producto de lluvia satelital de GOES-19 (RRQPE) en AWS dejó de publicarse el 2/11/2026.

## Nubosidad en vivo (visible + topes nubosos)
    python en_vivo.py            # actualiza cada 10 min, sin parar
    python en_vivo.py --una-vez  # una sola vez
Abrí `en_vivo/index.html`: animación de las últimas 3 h, visible y topes, provincia y alrededores.
Para publicarlo en la web sin depender de tu compu, ver `WEB.md`.

## Mapa del tiempo interactivo (para la web)
    python mapa_vivo.py            # actualiza cada 10 min
    python mapa_vivo.py --una-vez
Abrí `mapa/index.html`: mapa con zoom, topes nubosos, visible y lluvia pronosticada, animados.
Para publicarlo en la web, ver `WEB.md`.
