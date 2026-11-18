# Mapa del tiempo en la web de El Viejo Viento

`mapa_vivo.py` arma un mapa interactivo (zoom, desplazamiento, capas animadas) como página
estática: `index.html` + imágenes. No necesita servidor propio ni base de datos.

**Capas incluidas (todas gratis, sin clave):**
- **Topes nubosos** GOES-19 (infrarrojo realzado), últimas 3 h cada 10 min, de día y de noche.
- **Visible** GOES-19, últimas 3 h cada 10 min (sólo de día).
- **Lluvia pronosticada** GFS, próximas 72 h en pasos de 3 h.
- Mapa base oscuro de Esri (gratis, sin clave, con la atribución que ya figura abajo a la derecha).

Se puede abrir una capa directa con `?capa=ir`, `?capa=vis` o `?capa=pron`.

## Publicarlo y que se actualice solo (GitHub, gratis)
1. Crear una cuenta en github.com (si no tenés) y un repositorio **público**, por ejemplo `mapa`.
2. Subir el contenido de esta carpeta (`tormentas_ba/`, incluida la carpeta oculta `.github/`).
3. En el repo: **Actions** > habilitar workflows > "Mapa del tiempo en vivo" > **Run workflow**
   (la primera corrida tarda ~5 min).
4. **Settings > Pages** > Source: *Deploy from a branch* > rama `gh-pages`, carpeta `/ (root)` > Save.
5. Queda en `https://TU-USUARIO.github.io/mapa/`. Desde ahí se actualiza cada 10 minutos.

## Embeberlo en la web
WordPress: bloque "HTML personalizado". Wix: "Insertar código". Otros: pegar el HTML.

```html
<iframe src="https://TU-USUARIO.github.io/mapa/" title="Mapa del tiempo · El Viejo Viento"
        style="width:100%;height:80vh;min-height:560px;border:0;border-radius:12px" loading="lazy"></iframe>
```

Con dominio propio (ej. `mapa.elviejoviento.com.ar`): Settings > Pages > Custom domain + un registro
CNAME en tu proveedor de dominio.

## Opción rápida: widget de Windy
Windy deja embeber su mapa gratis (con su logo). Sirve para viento, lluvia, tormentas eléctricas, etc.:

```html
<iframe src="https://embed.windy.com/embed2.html?lat=-37.7&lon=-59.8&detailLat=-37.68&detailLon=-59.80&zoom=6&level=surface&overlay=rain&product=ecmwf&menu=&message=&marker=&calendar=now&pressure=true&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1"
        style="width:100%;height:560px;border:0" loading="lazy"></iframe>
```
Se arma a gusto en https://www.windy.com/-Embed-widget-on-page/widgets. No es propio ni lleva tu
marca, pero complementa bien al mapa satelital.

## Límites
- Atraso: NOAA publica cada imagen 15-20 min después; GitHub dispara cada "10 min" con algunos
  minutos de demora. En total, 20-30 min. Para algo más inmediato: un VPS (~5 USD/mes) corriendo
  `python mapa_vivo.py` sin parar y sirviendo la carpeta `mapa/`.
- **Radar**: no hay radar argentino abierto (los del SMN/SINARAME no publican datos libres).
  Haría falta un convenio con el SMN. La lluvia del mapa es pronóstico de modelo.
- GitHub pausa los workflows programados si el repo pasa 60 días sin cambios: entrar y hacer
  "Enable workflow" lo reactiva.
- Mencionar siempre "Fuente: NOAA GOES-19 / GFS" (ya está en la página).
