"""GOES-19 ABI desde el bucket público de NOAA en AWS (sin credenciales).

Canal 13 (infrarrojo limpio, 10.3 µm) del disco completo -> temperatura de brillo
del tope de nube (°C). Topes por debajo de -52 °C ~ convección profunda.
Cada archivo pesa ~25 MB; se baja, se recorta a la caja y se guarda el recorte.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

import numpy as np
import requests
import xarray as xr
from pyproj import Proj

from .gfs import CAJA

BUCKET = "https://noaa-goes19.s3.amazonaws.com"
_S = requests.Session()


def _listar(producto: str, t: datetime) -> list[str]:
    pref = f"{producto}/{t:%Y}/{t.timetuple().tm_yday:03d}/{t:%H}/"
    xml = _S.get(f"{BUCKET}/?list-type=2&prefix={pref}", timeout=60).text
    return re.findall(r"<Key>([^<]+)</Key>", xml)


def _inicio(key: str) -> datetime:
    s = re.search(r"_s(\d{13})", key).group(1)
    return datetime.strptime(s[:13], "%Y%j%H%M%S")


def _latlon(ds):
    p = ds["goes_imager_projection"].attrs
    h = p["perspective_point_height"]
    proj = Proj(proj="geos", h=h, lon_0=p["longitude_of_projection_origin"],
                sweep=p["sweep_angle_axis"], a=p["semi_major_axis"], b=p["semi_minor_axis"])
    X, Y = np.meshgrid(ds["x"].values * h, ds["y"].values * h)
    lon, lat = proj(X, Y, inverse=True)
    lon[np.abs(lon) > 360] = np.nan
    lat[np.abs(lat) > 90] = np.nan
    return lat, lon


_IDX = {}


def tope_nube(t: datetime, cache_dir: str, canal: int = 13) -> xr.DataArray | None:
    """Temperatura de brillo (°C) recortada a CAJA para la imagen más cercana a t."""
    os.makedirs(cache_dir, exist_ok=True)
    keys = [k for k in _listar("ABI-L2-CMIPF", t) if f"M6C{canal:02d}_" in k]
    if not keys:
        return None
    key = min(keys, key=lambda k: abs((_inicio(k) - t).total_seconds()))
    t0 = _inicio(key)
    out = os.path.join(cache_dir, f"goes19_C{canal}_{t0:%Y%m%d%H%M}.nc")
    if os.path.exists(out):
        return xr.open_dataarray(out).load()
    tmp = out + ".full"
    with _S.get(f"{BUCKET}/{key}", stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for c in r.iter_content(1 << 20):
                fh.write(c)
    try:
        ds = xr.open_dataset(tmp, engine="netcdf4")
        if "full" not in _IDX:
            # la grilla del disco completo es fija: calculo el recorte una sola vez
            lat, lon = _latlon(ds)
            m = ((lon >= CAJA["lon_min"]) & (lon <= CAJA["lon_max"]) &
                 (lat >= CAJA["lat_min"]) & (lat <= CAJA["lat_max"]))
            rows, cols = np.where(m)
            r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
            _IDX["full"] = (r0, r1, c0, c1, lat[r0:r1, c0:c1], lon[r0:r1, c0:c1])
        r0, r1, c0, c1, la, lo = _IDX["full"]
        tb = ds["CMI"].values[r0:r1, c0:c1] - 273.15
        da = xr.DataArray(tb.astype("float32"), dims=("fila", "col"),
                          coords={"lat": (("fila", "col"), la.astype("float32")),
                                  "lon": (("fila", "col"), lo.astype("float32"))},
                          name="tb_c", attrs={"tiempo": f"{t0:%Y-%m-%d %H:%M} UTC", "canal": canal})
        ds.close()
    finally:
        os.remove(tmp)
    da.to_netcdf(out)
    return da


def serie_topes(inicio: datetime, fin: datetime, cada_h: int, cache_dir: str):
    t, out = inicio, []
    while t <= fin:
        da = tope_nube(t, cache_dir)
        if da is not None:
            out.append(da)
        t += timedelta(hours=cada_h)
    return out


def serie_topes_min(inicio: datetime, fin: datetime, cada_min: int, cache_dir: str):
    """Igual que serie_topes pero con paso en minutos (para animaciones; GOES-19 da 10 min)."""
    t, out, vistos = inicio, [], set()
    while t <= fin:
        da = tope_nube(t, cache_dir)
        if da is not None and da.attrs["tiempo"] not in vistos:
            vistos.add(da.attrs["tiempo"])
            out.append(da)
        t += timedelta(minutes=cada_min)
    return out
