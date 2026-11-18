"""GFS 0.25° desde el bucket público de NOAA en AWS (sin credenciales).

Baja sólo las variables pedidas usando el índice .idx + pedidos HTTP por rango de
bytes, y recorta a la caja de la provincia. Sirve para:
  * "casi-observado": encadenar los plazos f001..f006 de cada corrida (00/06/12/18 UTC)
  * pronóstico: una sola corrida con plazos f000..f120
"""
from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timedelta

import numpy as np
import requests
import xarray as xr

BUCKET = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
# Caja de trabajo: provincia de Buenos Aires con margen
CAJA = dict(lon_min=-64.5, lon_max=-55.5, lat_min=-41.5, lat_max=-32.5)

_S = requests.Session()
# reintentos ante cortes momentáneos de red
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
_S.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1.5, status_forcelist=(500, 502, 503, 504))))


def _url(ciclo: datetime, plazo: int) -> str:
    return (f"{BUCKET}/gfs.{ciclo:%Y%m%d}/{ciclo:%H}/atmos/"
            f"gfs.t{ciclo:%H}z.pgrb2.0p25.f{plazo:03d}")


def _rangos(idx_txt: str, patrones: list[str]) -> list[tuple[int, int | None, str]]:
    lineas = [l for l in idx_txt.strip().splitlines() if l]
    out = []
    for i, l in enumerate(lineas):
        partes = l.split(":")
        clave = ":".join(partes[3:6])
        if any(re.search(p, clave) for p in patrones):
            ini = int(partes[1])
            fin = int(lineas[i + 1].split(":")[1]) - 1 if i + 1 < len(lineas) else None
            out.append((ini, fin, clave))
    return out


def bajar_campos(ciclo: datetime, plazo: int, patrones: list[str],
                 cache_dir: str, caja: dict | None = None) -> xr.Dataset | None:
    """Devuelve un Dataset recortado a CAJA con los campos que matchean los patrones
    (regex sobre 'VAR:nivel:plazo' del .idx). None si el archivo no existe."""
    os.makedirs(cache_dir, exist_ok=True)
    tag = re.sub(r"[^A-Za-z0-9]+", "_", "_".join(patrones))[:60]
    if caja is not None and caja != CAJA:
        tag += "_%g_%g_%g_%g" % (caja["lon_min"], caja["lon_max"], caja["lat_min"], caja["lat_max"])
    caja = caja or CAJA
    nc = os.path.join(cache_dir, f"gfs_{ciclo:%Y%m%d%H}_f{plazo:03d}_{tag}.nc")
    if os.path.exists(nc):
        return xr.open_dataset(nc).load()
    r = _S.get(_url(ciclo, plazo) + ".idx", timeout=60)
    if r.status_code != 200:
        return None
    rangos = _rangos(r.text, patrones)
    if not rangos:
        return None
    dsets = []
    for ini, fin, clave in rangos:
        h = {"Range": f"bytes={ini}-{'' if fin is None else fin}"}
        b = _S.get(_url(ciclo, plazo), headers=h, timeout=120).content
        with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as t:
            t.write(b)
            path = t.name
        try:
            ds = xr.open_dataset(path, engine="cfgrib",
                                 backend_kwargs={"indexpath": ""}).load()
        finally:
            os.remove(path)
        ds = ds.assign_coords(longitude=(((ds.longitude + 180) % 360) - 180)).sortby("longitude")
        ds = ds.sel(longitude=slice(caja["lon_min"], caja["lon_max"]),
                    latitude=slice(caja["lat_max"], caja["lat_min"]))
        keep = [v for v in ds.data_vars]
        ds = ds[keep].drop_vars([c for c in ds.coords if c not in ("latitude", "longitude")])
        # nombre corto según la clave del idx
        var = clave.split(":")[0].lower()
        acc = re.search(r"(\d+)-(\d+) hour (acc|ave)", clave)
        if acc:
            var = f"{var}_{acc.group(1)}_{acc.group(2)}{acc.group(3)}"
        ds = ds.rename({list(ds.data_vars)[0]: var})
        dsets.append(ds)
    out = xr.merge(dsets, compat="override")
    out.attrs.update(ciclo=f"{ciclo:%Y-%m-%d %HZ}", plazo=plazo)
    out.to_netcdf(nc)
    return out


def lluvia_y_rafagas_observadas(inicio: datetime, fin: datetime, cache_dir: str):
    """Encadena corridas cada 6 h (plazos 1..6) para armar series horarias
    'casi-observadas' de lluvia (mm/h) y ráfaga (km/h) entre inicio y fin (UTC).
    Devuelve (lluvia[time,lat,lon], rafaga[time,lat,lon])."""
    t = inicio.replace(minute=0, second=0, microsecond=0)
    t = t - timedelta(hours=t.hour % 6)
    lluvias, rafagas = [], []
    while t < fin:
        prev = None
        for f in range(1, 7):
            ds = bajar_campos(t, f, [r"^APCP:surface:0-\d+ hour acc", r"^GUST:surface"], cache_dir)
            if ds is None:
                break
            tiempo = t + timedelta(hours=f)
            acc_var = [v for v in ds.data_vars if v.startswith("apcp_0_")][0]
            acc = ds[acc_var]
            mmh = acc - prev if prev is not None else acc
            prev = acc
            lluvias.append(mmh.clip(min=0).expand_dims(time=[np.datetime64(tiempo)]))
            rafagas.append((ds["gust"] * 3.6).expand_dims(time=[np.datetime64(tiempo)]))
        t += timedelta(hours=6)
    lluvia = xr.concat(lluvias, "time").rename("lluvia_mm")
    rafaga = xr.concat(rafagas, "time").rename("rafaga_kmh")
    sel = (lluvia.time > np.datetime64(inicio)) & (lluvia.time <= np.datetime64(fin))
    return lluvia.sel(time=sel), rafaga.sel(time=sel)


def pronostico(ciclo: datetime, horas: int, cache_dir: str, paso: int = 3, caja: dict | None = None):
    """Pronóstico GFS de una corrida: lluvia por paso (mm) y ráfaga (km/h)."""
    lluvias, rafagas, prev = [], [], None
    for f in range(paso, horas + 1, paso):
        ds = bajar_campos(ciclo, f, [r"^APCP:surface:\d+-\d+ hour acc", r"^GUST:surface"], cache_dir, caja)
        if ds is None:
            continue
        # GFS acumula en ventanas de 6 h (0-3, 0-6, 6-9, 6-12...): usar la ventana más corta
        acc_var = max([v for v in ds.data_vars if v.startswith("apcp_")],
                      key=lambda v: int(v.split("_")[1]))
        acc = ds[acc_var]
        ini = int(acc_var.split("_")[1])
        paso_mm = acc if (prev is None or ini == f - paso) else acc - prev
        prev = acc
        tiempo = np.datetime64(ciclo + timedelta(hours=f))
        lluvias.append(paso_mm.clip(min=0).expand_dims(time=[tiempo]))
        rafagas.append((ds["gust"] * 3.6).expand_dims(time=[tiempo]))
    return (xr.concat(lluvias, "time").rename("lluvia_mm"),
            xr.concat(rafagas, "time").rename("rafaga_kmh"))
