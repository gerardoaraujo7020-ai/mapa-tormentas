"""Seguimiento de una tormenta en la provincia de Buenos Aires.

Uso:
  python correr.py --inicio 2026-11-12T18 --fin 2026-11-14T12 --nombre "Tormenta 13-14 nov"
Horas en UTC (hora argentina + 3). Todo sale de buckets públicos de NOAA en AWS:
no hace falta cuenta ni clave.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import requests
from shapely.geometry import shape
from shapely import vectorized

from tormentas import cartas, clima, gfs, goes
from tormentas.boletin import armar_boletin

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTE_GFS = "Fuente: NOAA GFS 0,25° (corridas encadenadas, plazos 1-6 h) · AWS Open Data"
FUENTE_GOES = "Fuente: NOAA GOES-19 ABI canal 13 (10,3 µm) · AWS Open Data"


def _mascara_ba(lat, lon):
    feats = json.load(open(os.path.join(AQUI, "datos", "limites.geojson")))["features"]
    ba = [shape(f["geometry"]) for f in feats if f["properties"]["nombre"] == "Buenos Aires"][0]
    lo, la = np.meshgrid(lon, lat)
    return vectorized.contains(ba, lo, la)


def _mascara_ba_pts(lat, lon):
    feats = json.load(open(os.path.join(AQUI, "datos", "limites.geojson")))["features"]
    ba = [shape(f["geometry"]) for f in feats if f["properties"]["nombre"] == "Buenos Aires"][0]
    ok = np.isfinite(lat) & np.isfinite(lon)
    out = np.zeros(lat.shape, bool)
    out[ok] = vectorized.contains(ba, lon[ok], lat[ok])
    return out


def _dist_km(la1, lo1, la2, lo2):
    dy = (la1 - la2) * 111.2
    dx = (lo1 - lo2) * 111.2 * np.cos(np.deg2rad((la1 + la2) / 2))
    return float(np.hypot(dx, dy))


def _mas_cercana(la, lo):
    return min(cartas.LOCALIDADES, key=lambda n: _dist_km(la, lo, *cartas.LOCALIDADES[n]))


def _hoa(t: datetime) -> str:
    return cartas._hora_local(f"{t:%Y-%m-%d %H:%M}")


def ultima_corrida_gfs() -> datetime:
    t = datetime.now(timezone.utc).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    t -= timedelta(hours=t.hour % 6)
    for _ in range(8):
        if requests.head(gfs._url(t, 120) + ".idx", timeout=30).status_code == 200:
            return t
        t -= timedelta(hours=6)
    raise RuntimeError("No encontré una corrida GFS completa")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", required=True, help="UTC, ej. 2026-11-12T18")
    ap.add_argument("--fin", required=True, help="UTC, ej. 2026-11-14T12")
    ap.add_argument("--nombre", default="Tormenta en la provincia de Buenos Aires")
    ap.add_argument("--salida", default="salida")
    ap.add_argument("--cache", default="cache")
    ap.add_argument("--goes-cada", type=int, default=1, help="horas entre imágenes GOES")
    ap.add_argument("--localidades", default="Benito Juárez,Tandil,Necochea,Tres Arroyos,Azul")
    ap.add_argument("--sin-pronostico", action="store_true")
    ap.add_argument("--sin-animaciones", action="store_true")
    ap.add_argument("--anim-cada", type=int, default=30,
                    help="minutos entre cuadros de la animación satelital (10, 20, 30, 60)")
    a = ap.parse_args()

    ini = datetime.fromisoformat(a.inicio)
    fin = datetime.fromisoformat(a.fin)
    os.makedirs(a.salida, exist_ok=True)
    C = lambda n: os.path.join(a.salida, n)
    periodo = f"{_hoa(ini)} → {_hoa(fin)}"
    r = {"nombre": a.nombre, "periodo": periodo, "cartas": {}}

    # 1) Lluvia y ráfagas "casi-observadas" (GFS encadenado)
    print("GFS: lluvia y ráfagas…")
    lluvia, rafaga = gfs.lluvia_y_rafagas_observadas(ini, fin, os.path.join(a.cache, "gfs"))
    total = lluvia.sum("time")
    rafmax = rafaga.max("time")
    m = _mascara_ba(total.latitude.values, total.longitude.values)
    tv = total.values
    i = np.unravel_index(np.where(m, tv, -1).argmax(), tv.shape)
    r["lluvia"] = dict(media_prov=float(tv[m].mean()), max=float(tv[m].max()),
                       max_lat=float(total.latitude[i[0]]), max_lon=float(total.longitude[i[1]]),
                       area_20=float(100 * (tv[m] >= 20).mean()), area_50=float(100 * (tv[m] >= 50).mean()))
    gv = rafmax.values
    j = np.unravel_index(np.where(m, gv, -1).argmax(), gv.shape)
    r["rafaga"] = dict(max=float(gv[m].max()), max_lat=float(rafmax.latitude[j[0]]),
                       max_lon=float(rafmax.longitude[j[1]]), area_60=float(100 * (gv[m] >= 60).mean()))
    # hora pico de lluvia en la provincia
    serie_prov = lluvia.where(m).mean(("latitude", "longitude")).values
    tpico = lluvia.time.values[int(np.nanargmax(serie_prov))].astype("datetime64[s]").item()
    r["pico"] = _hoa(tpico)

    r["cartas"]["lluvia"] = cartas.campo(
        total, C("01_lluvia_acumulada.png"), "Lluvia acumulada", periodo,
        cartas.LLUVIA_NIVELES, cartas.LLUVIA_CMAP, "mm", FUENTE_GFS, mascara=m)
    r["cartas"]["rafaga"] = cartas.campo(
        rafmax, C("02_rafaga_maxima.png"), "Ráfaga máxima", periodo,
        cartas.RAFAGA_NIVELES, cartas.RAFAGA_CMAP, "km/h", FUENTE_GFS, mascara=m)

    # 2) Anomalía: % de la lluvia normal del mes (GPCP 1991-2020)
    print("GPCP: normal del mes…")
    normal = clima.normal_mensual(ini.month, os.path.join(a.cache, "gpcp"))
    nor = clima.a_grilla(normal, total.latitude, total.longitude)
    pct = total.copy(data=100 * tv / nor)
    r["anomalia"] = dict(normal_media=float(np.nanmean(nor[m])), pct_media=float(np.nanmean(pct.values[m])))
    meses = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    r["mes"] = meses[ini.month]
    r["cartas"]["anomalia"] = cartas.campo(
        pct, C("03_porcentaje_normal.png"), f"La tormenta en % de la lluvia normal de {meses[ini.month]}",
        periodo + " · normal 1991-2020", cartas.ANOM_NIVELES, cartas.ANOM_CMAP, "% de la normal mensual",
        "Fuentes: lluvia GFS 0,25°; normal GPCP v2.3 (NOAA CDR, 2,5°) · AWS Open Data", mascara=m)

    # 3) GOES-19: topes de nube
    print("GOES-19: topes de nube…")
    topes = goes.serie_topes(ini, fin, a.goes_cada, os.path.join(a.cache, "goes"))
    mins = [float(np.nanmin(np.where(np.isfinite(d.values), d.values, 99))) for d in topes]
    k = int(np.argmin(mins))
    r["goes"] = dict(min_tb=mins[k], hora=cartas._hora_local(topes[k].attrs["tiempo"]), n=len(topes))
    r["cartas"]["goes_pico"] = cartas.tope_nube(
        topes[k], C("04_goes19_tope_nube_pico.png"), "Tope de nube más frío del evento",
        f"GOES-19 · {r['goes']['hora']} · mín. {mins[k]:.0f} °C", FUENTE_GOES)
    paso = max(1, len(topes) // 6)
    sel = topes[::paso][:6]
    r["cartas"]["goes_secuencia"] = cartas.mosaico_topes(
        sel, C("05_goes19_secuencia.png"), "Evolución de los topes de nube (GOES-19)", FUENTE_GOES)
    # ¿dónde fue más persistente la convección según el satélite? (para contrastar con el modelo)
    frec = cartas.frecuencia(topes, -52)
    d0 = topes[0]
    mg = _mascara_ba_pts(d0.lat.values, d0.lon.values)
    q = np.unravel_index(np.nanargmax(np.where(mg, frec, -1)), frec.shape)
    r["goes"]["frec_max"] = float(frec[q])
    r["goes"]["frec_cerca"] = _mas_cercana(float(d0.lat.values[q]), float(d0.lon.values[q]))
    r["lluvia"]["max_cerca"] = _mas_cercana(r["lluvia"]["max_lat"], r["lluvia"]["max_lon"])
    r["goes"]["dist_km"] = _dist_km(float(d0.lat.values[q]), float(d0.lon.values[q]),
                                    r["lluvia"]["max_lat"], r["lluvia"]["max_lon"])
    r["cartas"]["goes_frecuencia"] = cartas.frecuencia_topes_frios(
        topes, C("06_goes19_frecuencia_topes_frios.png"), -52, "Persistencia de convección profunda",
        periodo, FUENTE_GOES)

    # 4) Carta sinóptica en la hora pico (corrida GFS previa, plazo 3 o 6)
    print("GFS: carta sinóptica…")
    tp = tpico.replace(minute=0)
    ciclo = tp - timedelta(hours=1)
    ciclo = ciclo - timedelta(hours=ciclo.hour % 6)
    plazo = int((tp - ciclo).total_seconds() // 3600)
    ds = gfs.bajar_campos(ciclo, plazo, [r"^PRMSL:mean sea level", r"^UGRD:10 m above",
                                         r"^VGRD:10 m above", r"^CAPE:surface"], os.path.join(a.cache, "gfs"))
    ds = ds.rename({"ugrd": "u10", "vgrd": "v10"})
    tsin = ciclo + timedelta(hours=plazo)
    r["cartas"]["sinoptica"] = cartas.sinoptica(
        ds, C("07_carta_sinoptica.png"), "Situación en superficie", f"{_hoa(tsin)} · GFS",
        "Fuente: NOAA GFS 0,25° · AWS Open Data")

    # 5) Series en localidades
    noms = [n.strip() for n in a.localidades.split(",")]
    r["localidades"] = {}
    for n in noms:
        la, lo = cartas.LOCALIDADES[n]
        r["localidades"][n] = dict(
            lluvia=float(lluvia.sel(latitude=la, longitude=lo, method="nearest").sum()),
            rafaga=float(rafaga.sel(latitude=la, longitude=lo, method="nearest").max()),
            pct_normal=float(pct.sel(latitude=la, longitude=lo, method="nearest")))
    r["cartas"]["series"] = cartas.series_localidades(
        lluvia, rafaga, noms, C("08_series_localidades.png"),
        "Lluvia horaria y ráfagas por localidad (hora argentina)", FUENTE_GFS)

    # 6) Pronóstico próximas 72 h
    if not a.sin_pronostico:
        print("GFS: pronóstico…")
        c = ultima_corrida_gfs()
        pl, pr = gfs.pronostico(c, 72, os.path.join(a.cache, "gfs"))
        pt = pl.sum("time")
        r["pronostico"] = dict(corrida=f"{c:%d/%m %H} UTC", desde=_hoa(c), hasta=_hoa(c + timedelta(hours=72)),
                               lluvia_max=float(pt.values[m].max()), rafaga_max=float(pr.max("time").values[m].max()),
                               localidades={n: dict(
                                   lluvia=float(pt.sel(latitude=cartas.LOCALIDADES[n][0], longitude=cartas.LOCALIDADES[n][1], method="nearest")),
                                   rafaga=float(pr.sel(latitude=cartas.LOCALIDADES[n][0], longitude=cartas.LOCALIDADES[n][1], method="nearest").max()))
                                   for n in noms})
        r["cartas"]["pronostico"] = cartas.campo(
            pt, C("09_pronostico_lluvia_72h.png"), "Lluvia pronosticada próximas 72 h",
            f"GFS corrida {c:%d/%m %H} UTC · {_hoa(c)} → {_hoa(c + timedelta(hours=72))}",
            cartas.LLUVIA_NIVELES, cartas.LLUVIA_CMAP, "mm", "Fuente: NOAA GFS 0,25° · AWS Open Data", mascara=m)

    # 7) Animaciones (MP4 + GIF)
    if not a.sin_animaciones:
        from tormentas import animacion
        print("Animaciones…")
        cuadros = goes.serie_topes_min(ini, fin, a.anim_cada, os.path.join(a.cache, "goes"))
        r["animaciones"] = {
            "goes": animacion.topes_nube(cuadros, C("10_animacion_goes19")),
            "satelite_y_lluvia": animacion.satelite_y_lluvia(topes, lluvia, C("11_animacion_satelite_y_lluvia")),
        }

    json.dump(r, open(C("resumen.json"), "w"), ensure_ascii=False, indent=2)
    pdf = armar_boletin(r, C("boletin_tormenta.pdf"))
    print("Listo:", pdf)


if __name__ == "__main__":
    main()
