"""Nubosidad en vivo GOES-19 sobre la provincia de Buenos Aires.

Lee del bucket público de NOAA sólo los bytes del recorte de la provincia (pedidos por
rango con fsspec + h5py), sin bajar el disco completo:
  * canal 2 (visible rojo, 0,5 km; se muestra a 1 km): ~25-35 MB por imagen
  * canal 13 (infrarrojo, 2 km) realzado para topes nubosos: ~2-3 MB por imagen
GOES-19 escanea el disco completo cada 10 minutos y aparece en AWS ~5-10 min después.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import fsspec
import h5py
import numpy as np
import requests
from pyproj import Proj

# Recorte del visor en vivo: provincia de Buenos Aires y alrededores
# (La Pampa, sur de Córdoba, Santa Fe y Entre Ríos, Uruguay, norte de Río Negro)
CAJA = dict(lon_min=-66.0, lon_max=-53.0, lat_min=-42.0, lat_max=-31.0)

BUCKET = "https://noaa-goes19.s3.amazonaws.com"
_S = requests.Session()
_VENTANA = {}


def _inicio(key):
    s = re.search(r"_s(\d{13})", key).group(1)
    return datetime.strptime(s, "%Y%j%H%M%S")


def ultimas_claves(canal: int, horas: float = 3, ahora: datetime | None = None) -> list[str]:
    """Claves de las imágenes del canal en las últimas `horas`, de la más vieja a la más nueva."""
    ahora = ahora or datetime.now(timezone.utc).replace(tzinfo=None)
    desde = ahora - timedelta(hours=horas)
    keys, t = [], desde.replace(minute=0, second=0, microsecond=0)
    while t <= ahora:
        pref = f"ABI-L2-CMIPF/{t:%Y}/{t.timetuple().tm_yday:03d}/{t:%H}/"
        xml = _S.get(f"{BUCKET}/?list-type=2&prefix={pref}", timeout=60).text
        keys += [k for k in re.findall(r"<Key>([^<]+)</Key>", xml) if f"M6C{canal:02d}_" in k]
        t += timedelta(hours=1)
    return sorted([k for k in keys if _inicio(k) >= desde], key=_inicio)


def _ventana(h, canal, paso):
    """Filas/columnas del disco que cubren CAJA (se calcula una vez por canal)."""
    if canal in _VENTANA:
        return _VENTANA[canal]
    p = h["goes_imager_projection"].attrs
    alt = float(p["perspective_point_height"][0])
    proj = Proj(proj="geos", h=alt, lon_0=float(p["longitude_of_projection_origin"][0]),
                sweep=p["sweep_angle_axis"].decode() if isinstance(p["sweep_angle_axis"], bytes) else str(p["sweep_angle_axis"]),
                a=float(p["semi_major_axis"][0]), b=float(p["semi_minor_axis"][0]))
    xs = h["x"]
    ys = h["y"]
    x = xs[:] * xs.attrs["scale_factor"][0] + xs.attrs["add_offset"][0]
    y = ys[:] * ys.attrs["scale_factor"][0] + ys.attrs["add_offset"][0]
    # muestreo grueso para ubicar la ventana
    g = 16
    X, Y = np.meshgrid(x[::g] * alt, y[::g] * alt)
    lon, lat = proj(X, Y, inverse=True)
    ok = ((lon >= CAJA["lon_min"]) & (lon <= CAJA["lon_max"]) &
          (lat >= CAJA["lat_min"]) & (lat <= CAJA["lat_max"]) & (np.abs(lon) < 400))
    rr, cc = np.where(ok)
    r0, r1 = max(0, (rr.min() - 1) * g), min(len(y), (rr.max() + 2) * g)
    c0, c1 = max(0, (cc.min() - 1) * g), min(len(x), (cc.max() + 2) * g)
    X, Y = np.meshgrid(x[c0:c1:paso] * alt, y[r0:r1:paso] * alt)
    lon, lat = proj(X, Y, inverse=True)
    lon[np.abs(lon) > 400] = np.nan
    lat[np.abs(lat) > 400] = np.nan
    _VENTANA[canal] = (r0, r1, c0, c1, lat.astype("float32"), lon.astype("float32"))
    return _VENTANA[canal]


def leer_recorte(key: str, canal: int):
    """Devuelve (valores, lat, lon, tiempo_utc). Canal 2: reflectancia 0-1; canal 13: °C."""
    paso = 2 if canal == 2 else 1  # visible: 0,5 km -> 1 km
    with fsspec.open(f"{BUCKET}/{key}", block_size=4 * 2**20, cache_type="bytes").open() as f:
        with h5py.File(f, "r") as h:
            r0, r1, c0, c1, lat, lon = _ventana(h, canal, paso)
            d = h["CMI"]
            crudo = d[r0:r1, c0:c1][::paso, ::paso].astype("float32")
            fill = d.attrs.get("_FillValue", [None])[0]
            v = crudo * d.attrs["scale_factor"][0] + d.attrs["add_offset"][0]
            if fill is not None:
                v[crudo == fill] = np.nan
    if canal != 2:
        v = v - 273.15
    return v, lat, lon, _inicio(key)
