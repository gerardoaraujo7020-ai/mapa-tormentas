# Mapa del tiempo en vivo · El Viejo Viento

Mapa interactivo de la provincia de Buenos Aires y alrededores con capas animadas:
topes nubosos y visible del satélite GOES-19 (últimas 3 h, cada 10 min) y lluvia
pronosticada y viento GFS (72 h). Fuentes públicas de NOAA, sin claves.

- Se actualiza solo cada 10 minutos con GitHub Actions (`.github/workflows/mapa_en_vivo.yml`)
  y se publica en GitHub Pages desde la rama `gh-pages`.
- Para correrlo en una compu: `pip install -r requirements.txt` y `python mapa_vivo.py`.
- Embeberlo en otra web y límites: ver `WEB.md`. Resto de herramientas (boletín de tormentas,
  placas, animaciones): ver `LEEME.md`.
