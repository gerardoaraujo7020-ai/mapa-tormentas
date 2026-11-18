"""Mapa interactivo del tiempo (estilo Windy / SMN) para la web de El Viejo Viento.

Genera una página estática (Leaflet) con capas animadas:
  * Topes nubosos GOES-19 (IR realzado), últimas 3 h, cada 10 min
  * Visible GOES-19, últimas 3 h, cada 10 min
  * Lluvia pronosticada GFS, próximas 72 h en pasos de 3 h
Uso:
  python mapa_vivo.py              # actualiza cada 10 min sin parar
  python mapa_vivo.py --una-vez    # una actualización (GitHub Actions / Programador de tareas)
Resultado en mapa/ : abrí mapa/index.html o subí la carpeta a cualquier hosting estático.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import time
import traceback
from datetime import datetime, timedelta, timezone

import numpy as np

from tormentas import envivo, gfs, mapa

AQUI = os.path.dirname(os.path.abspath(__file__))
# Ancho en píxeles de cada capa: "baja" para animar, "alta" (resolución nativa) al pausar
ANCHO = {2: 1900, 13: 1100}
ANCHO_HD = {2: 4400, 13: 2000}
CALIDAD = {"baja": 74, "alta": 84, "cont": 66}
ANCHO_CONT = 1200          # capas de toda Sudamérica (se ven al alejar el mapa)
PASO_VIENTO = 4            # grilla de partículas/clic: 1 de cada 4 puntos GFS (1°) para que el archivo no pese demasiado
LUGARES = [("Benito Juárez", -37.68, -59.80), ("Tandil", -37.32, -59.13), ("Necochea", -38.55, -58.74),
           ("Tres Arroyos", -38.38, -60.28), ("Azul", -36.78, -59.86), ("Olavarría", -36.89, -60.32),
           ("Bahía Blanca", -38.72, -62.27), ("Junín", -34.59, -60.95), ("Pehuajó", -35.81, -61.90), ("Pergamino", -33.89, -60.57),
           ]


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _webp(png_func, datos, path, calidad=74, **kw):
    mapa.CALIDAD_WEBP = calidad
    png_func(*datos, path, **kw) if isinstance(datos, tuple) else png_func(datos, path, **kw)


def satelite(capas, horas):
    nuevos = 0
    for canal, pref, func in ((13, "ir", mapa.png_topes), (2, "vis", mapa.png_visible_pleno)):
        for key in envivo.ultimas_claves(canal, horas):
            t = envivo._inicio(key)
            path = os.path.join(capas, f"{pref}_{t:%Y%m%d_%H%M}.webp")
            if os.path.exists(path):
                continue
            (v, vhd), t = mapa.leer_goes_mercator(key, canal, (ANCHO[canal], ANCHO_HD[canal]))
            _webp(func, v, path, CALIDAD["baja"])
            os.makedirs(os.path.join(capas, "hd"), exist_ok=True)
            _webp(func, vhd, os.path.join(capas, "hd", os.path.basename(path)), CALIDAD["alta"])
            nuevos += 1
            print(f"  {pref} {t:%d/%m %H:%M} UTC")
    nuevos += satelite_continente(capas, horas)
    limite = _ahora() - timedelta(hours=horas + 0.25)
    for p in glob.glob(os.path.join(capas, "cont", "*.webp")):
        if datetime.strptime(os.path.basename(p)[-18:-5], "%Y%m%d_%H%M") < limite:
            os.remove(p)
    for p in glob.glob(os.path.join(capas, "ir_*.webp")) + glob.glob(os.path.join(capas, "vis_*.webp")):
        if datetime.strptime(os.path.basename(p)[-18:-5], "%Y%m%d_%H%M") < limite:
            os.remove(p)
            hd = os.path.join(capas, "hd", os.path.basename(p))
            if os.path.exists(hd):
                os.remove(hd)
    return nuevos


def satelite_continente(capas, horas, max_por_corrida=8):
    """Capas de toda Sudamérica (2 km, más livianas) para cuando se aleja el mapa.
    Topes: canal 13. Visible: canal 2 del archivo multibanda (MCMIPF, ya a 2 km).
    Hace como mucho `max_por_corrida` cuadros nuevos por capa en cada corrida, de los más nuevos a los más viejos,
    para que la primera corrida no tarde demasiado (las siguientes completan los que falten)."""
    os.makedirs(os.path.join(capas, "cont"), exist_ok=True)
    nuevos = 0
    for pref, canal, producto, var, func in (("ir", 13, "CMIPF", "CMI", mapa.png_topes),
                                             ("vis", 2, "MCMIPF", "CMI_C02", mapa.png_visible_pleno)):
        hechos = 0
        try:
            claves = envivo.ultimas_claves(canal, horas, producto=producto)
        except Exception:
            traceback.print_exc()
            continue
        for key in reversed(claves):
            t = envivo._inicio(key)
            path = os.path.join(capas, "cont", f"{pref}_{t:%Y%m%d_%H%M}.webp")
            if os.path.exists(path):
                continue
            if hechos >= max_por_corrida:
                break
            try:
                v, _ = mapa.leer_goes_mercator(key, canal, ANCHO_CONT, caja=mapa.CAJA_CONT, var=var)
                _webp(func, v, path, CALIDAD["cont"])
                hechos += 1
                nuevos += 1
                print(f"  continente {pref} {t:%d/%m %H:%M} UTC")
            except Exception:
                traceback.print_exc()
    return nuevos


def _campos_viento(t, f, cache):
    ds = gfs.bajar_campos(t, f, [r"^UGRD:10 m above", r"^VGRD:10 m above", r"^GUST:surface"], cache, mapa.CAJA_CONT)
    return ds


def _grilla_velocity(ds, var, numero, t):
    """Formato que entiende leaflet-velocity (como grib2json)."""
    la, lo = ds.latitude.values, ds.longitude.values
    return {"header": {"parameterCategory": 2, "parameterNumber": numero, "nx": int(lo.size), "ny": int(la.size),
                       "lo1": float(lo[0]), "la1": float(la[0]), "lo2": float(lo[-1]), "la2": float(la[-1]),
                       "dx": float(abs(lo[1] - lo[0])), "dy": float(abs(la[1] - la[0])), "refTime": t},
            "data": [round(float(x), 1) for x in ds[var].values.ravel()]}


def pronostico(capas, cache):
    """Lluvia y viento GFS de la última corrida: 0 a 72 h cada 3 h."""
    t = _ahora().replace(minute=0, second=0, microsecond=0)
    t -= timedelta(hours=t.hour % 6)
    import requests
    for _ in range(4):  # última corrida con 72 h disponibles
        if requests.head(gfs._url(t, 72) + ".idx", timeout=30).status_code == 200:
            break
        t -= timedelta(hours=6)
    else:
        return None
    marca = os.path.join(capas, f"pron_c_{t:%Y%m%d%H}.json")
    if not os.path.exists(marca):
        for p in glob.glob(os.path.join(capas, "pron_*")) + glob.glob(os.path.join(capas, "viento_*")):
            os.remove(p)
        print(f"  pronóstico GFS {t:%d/%m %H} UTC…")
        lluvia, _ = gfs.pronostico(t, 72, cache, paso=3, caja=mapa.CAJA_CONT)
        pasos, viento = [], []
        for f in range(3, 73, 3):
            ti = t + timedelta(hours=f)
            sel = lluvia.sel(time=np.datetime64(ti))
            fn_ll = f"pron_{t:%Y%m%d%H}_{f:03d}.webp"
            _webp(mapa.png_lluvia, (sel.values, lluvia.latitude.values, lluvia.longitude.values),
                  os.path.join(capas, fn_ll), ancho=1000, caja=mapa.CAJA_CONT)
            ds = _campos_viento(t, f, cache)
            vel = np.hypot(ds["ugrd"], ds["vgrd"]).values * 3.6
            fn_vi = f"viento_{t:%Y%m%d%H}_{f:03d}.webp"
            _webp(mapa.png_viento, (vel, ds.latitude.values, ds.longitude.values), os.path.join(capas, fn_vi),
                  ancho=1000, caja=mapa.CAJA_CONT)
            ds = ds.isel(latitude=slice(None, None, PASO_VIENTO), longitude=slice(None, None, PASO_VIENTO))
            iso = ti.isoformat(timespec="minutes")
            pasos.append({"f": "capas/" + fn_ll, "v": "capas/" + fn_vi, "t": iso, "desde": (ti - timedelta(hours=3)).isoformat(timespec="minutes")})
            # datos por punto para el clic: ráfaga y lluvia en la grilla del viento
            ll = sel.interp(latitude=ds.latitude, longitude=ds.longitude, method="nearest")
            viento.append({"t": iso,
                           "uv": [_grilla_velocity(ds, "ugrd", 2, iso), _grilla_velocity(ds, "vgrd", 3, iso)],
                           "raf": [int(round(x * 3.6)) for x in ds["gust"].values.ravel()],
                           "mm": [round(float(x), 1) for x in np.nan_to_num(ll.values).ravel()]})
        with open(os.path.join(capas, f"viento_{t:%Y%m%d%H}.js"), "w", encoding="utf-8") as fh:
            fh.write("window.VIENTO = " + json.dumps(viento, separators=(",", ":")) + ";")
        json.dump({"corrida": t.isoformat(timespec="minutes"), "pasos": pasos}, open(marca, "w"))
    info = json.load(open(marca))
    info["leyenda"] = [[v, c] for v, c in mapa.LEYENDA_LLUVIA]
    info["leyenda_viento"] = [[v, c] for v, c in mapa.LEYENDA_VIENTO]
    info["viento_js"] = f"capas/viento_{t:%Y%m%d%H}.js"
    return info


def actualizar(salida, horas, cache):
    salida = os.path.abspath(salida)
    capas = os.path.join(salida, "capas")
    os.makedirs(capas, exist_ok=True)
    # archivos fijos de la página
    plantilla = os.path.join(AQUI, "datos", "mapa")
    shutil.copy(os.path.join(plantilla, "index.html"), salida)
    shutil.copytree(os.path.join(plantilla, "lib"), os.path.join(salida, "lib"), dirs_exist_ok=True)
    with open(os.path.join(salida, "limites.js"), "w", encoding="utf-8") as fh:
        fh.write("window.LIMITES = " + open(os.path.join(AQUI, "datos", "limites_mapa.geojson"), encoding="utf-8").read() + ";")
    # si cambió el área del mapa, las imágenes viejas no sirven: se borran
    firma = json.dumps([mapa.CAJA_MAPA, ANCHO, ANCHO_HD], sort_keys=True)
    fpath = os.path.join(capas, "area.json")
    if not os.path.exists(fpath) or open(fpath).read() != firma:
        shutil.rmtree(capas, ignore_errors=True)
        os.makedirs(capas, exist_ok=True)
        open(fpath, "w").write(firma)

    n = satelite(capas, horas)
    try:
        pron = pronostico(capas, cache)
    except Exception:
        traceback.print_exc()
        pron = None

    def lista(pref):
        out = []
        for p in sorted(glob.glob(os.path.join(capas, f"{pref}_*.webp"))):
            b = os.path.basename(p)
            d = {"f": "capas/" + b, "a": "capas/hd/" + b,
                 "t": datetime.strptime(b[-18:-5], "%Y%m%d_%H%M").isoformat(timespec="minutes")}
            if os.path.exists(os.path.join(capas, "cont", b)):
                d["c"] = "capas/cont/" + b
            out.append(d)
        return out

    c, k = mapa.CAJA_MAPA, mapa.CAJA_CONT
    datos = {"bounds": [[c["lat_min"], c["lon_min"]], [c["lat_max"], c["lon_max"]]],
             "bounds_cont": [[k["lat_min"], k["lon_min"]], [k["lat_max"], k["lon_max"]]],
             "ir": lista("ir"), "vis": lista("vis"), "pron": pron,
             "lugares": LUGARES, "actualizado": _ahora().isoformat(timespec="minutes")}
    with open(os.path.join(salida, "capas.js"), "w", encoding="utf-8") as fh:
        fh.write("window.CAPAS = " + json.dumps(datos, ensure_ascii=False) + ";")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default="mapa")
    ap.add_argument("--cache", default="cache/gfs")
    ap.add_argument("--horas", type=float, default=3)
    ap.add_argument("--cada", type=int, default=10)
    ap.add_argument("--una-vez", action="store_true")
    a = ap.parse_args()
    while True:
        print(f"Actualizando mapa ({datetime.now():%H:%M})…")
        try:
            n = actualizar(a.salida, a.horas, a.cache)
            print(f"  {n} imágenes satelitales nuevas → {os.path.abspath(os.path.join(a.salida, 'index.html'))}")
        except Exception:
            traceback.print_exc()
            if a.una_vez:
                raise SystemExit(1)   # que GitHub Actions marque la corrida como fallida
        if a.una_vez:
            break
        time.sleep(a.cada * 60)


if __name__ == "__main__":
    main()
