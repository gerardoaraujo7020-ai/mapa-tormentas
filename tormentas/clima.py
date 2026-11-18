"""Climatología de lluvia mensual (GPCP v2.3, NOAA CDR, bucket público en AWS).

Sirve para expresar la lluvia de la tormenta como % de la lluvia normal del mes
(normal 1991-2020). GPCP es 2.5°: es una referencia regional, no local.
"""
from __future__ import annotations

import os
import re

import numpy as np
import requests
import xarray as xr

BUCKET = "https://noaa-cdr-precip-gpcp-monthly-pds.s3.amazonaws.com"
_S = requests.Session()


def normal_mensual(mes: int, cache_dir: str, desde: int = 1991, hasta: int = 2020) -> xr.DataArray:
    """Lluvia media del mes (mm/mes), grilla 2.5°, lon en -180..180."""
    os.makedirs(cache_dir, exist_ok=True)
    out = os.path.join(cache_dir, f"gpcp_normal_{mes:02d}_{desde}_{hasta}.nc")
    if os.path.exists(out):
        return xr.open_dataarray(out).load()
    campos = []
    for anio in range(desde, hasta + 1):
        xml = _S.get(f"{BUCKET}/?list-type=2&prefix=data/{anio}/", timeout=60).text
        keys = [k for k in re.findall(r"<Key>([^<]+)</Key>", xml) if f"_d{anio}{mes:02d}_" in k]
        if not keys:
            continue
        tmp = os.path.join(cache_dir, "tmp_gpcp.nc")
        with open(tmp, "wb") as fh:
            fh.write(_S.get(f"{BUCKET}/{keys[-1]}", timeout=120).content)
        ds = xr.open_dataset(tmp, engine="netcdf4")
        p = ds["precip"].squeeze(drop=True).load()  # mm/día
        ds.close()
        os.remove(tmp)
        dias = 30 if mes in (4, 6, 9, 11) else (28 if mes == 2 else 31)
        campos.append(p * dias)
    clim = xr.concat(campos, "anio").mean("anio")
    clim = clim.assign_coords(longitude=(((clim.longitude + 180) % 360) - 180)).sortby("longitude")
    clim = clim.rename("normal_mm")
    clim.to_netcdf(out)
    return clim


def a_grilla(clim: xr.DataArray, lat, lon) -> np.ndarray:
    """Interpola la normal a la grilla del campo de lluvia."""
    return clim.interp(latitude=lat, longitude=lon, method="linear").values
