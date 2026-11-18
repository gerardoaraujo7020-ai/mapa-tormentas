"""Capas PNG transparentes para el mapa interactivo (Leaflet, proyección Web Mercator).

Cada capa es una imagen RGBA alineada a la caja CAJA_MAPA en Web Mercator, lista para
L.imageOverlay. Las nubes se pintan con transparencia para que se vea el mapa debajo.
"""
from __future__ import annotations

import fsspec
import h5py
import numpy as np
from PIL import Image
from pyproj import Proj

from . import cartas
from .envivo import BUCKET, _inicio

CAJA_MAPA = dict(lon_min=-68.0, lon_max=-52.0, lat_min=-43.0, lat_max=-30.0)
_R = 6378137.0


def _merc_y(lat):
    return _R * np.log(np.tan(np.pi / 4 + np.deg2rad(lat) / 2))


def grilla_mercator(ancho: int):
    """lat/lon de cada píxel de una imagen de `ancho` px que cubre CAJA_MAPA en Web Mercator."""
    c = CAJA_MAPA
    x0, x1 = np.deg2rad(c["lon_min"]) * _R, np.deg2rad(c["lon_max"]) * _R
    y0, y1 = _merc_y(c["lat_min"]), _merc_y(c["lat_max"])
    alto = int(round(ancho * (y1 - y0) / (x1 - x0)))
    xs = x0 + (np.arange(ancho) + 0.5) * (x1 - x0) / ancho
    ys = y1 - (np.arange(alto) + 0.5) * (y1 - y0) / alto  # fila 0 = norte
    lon = np.rad2deg(xs / _R)
    lat = np.rad2deg(2 * np.arctan(np.exp(ys / _R)) - np.pi / 2)
    return np.meshgrid(lon, lat)


_IDX = {}


def _indices(h, canal, ancho):
    """Fila/columna (fraccionarias) del disco completo para cada píxel de la grilla Mercator."""
    clave = (canal, ancho)
    if clave in _IDX:
        return _IDX[clave]
    p = h["goes_imager_projection"].attrs
    alt = float(p["perspective_point_height"][0])
    sweep = p["sweep_angle_axis"]
    sweep = sweep.decode() if isinstance(sweep, bytes) else str(sweep)
    proj = Proj(proj="geos", h=alt, lon_0=float(p["longitude_of_projection_origin"][0]), sweep=sweep,
                a=float(p["semi_major_axis"][0]), b=float(p["semi_minor_axis"][0]))
    lon, lat = grilla_mercator(ancho)
    X, Y = proj(lon, lat)
    xs, ys = h["x"], h["y"]
    sx, ox = xs.attrs["scale_factor"][0], xs.attrs["add_offset"][0]
    sy, oy = ys.attrs["scale_factor"][0], ys.attrs["add_offset"][0]
    col = (X / alt - ox) / sx
    fila = (Y / alt - oy) / sy
    n = xs.shape[0]
    ok = np.isfinite(X) & np.isfinite(Y) & (col >= 0) & (col < n - 1) & (fila >= 0) & (fila < n - 1)
    r0, r1 = int(np.floor(fila[ok].min())), int(np.ceil(fila[ok].max())) + 2
    c0, c1 = int(np.floor(col[ok].min())), int(np.ceil(col[ok].max())) + 2
    # cuántos píxeles nativos entran en un píxel de salida (para suavizar antes de achicar)
    escala = float(np.nanmedian(np.abs(np.diff(np.where(ok, col, np.nan), axis=1))))
    _IDX[clave] = (ok, fila - r0, col - c0, r0, min(r1, n), c0, min(c1, n), escala)
    return _IDX[clave]


def leer_goes_mercator(key: str, canal: int, anchos):
    """Valores del canal (reflectancia 0-1 o °C) remuestreados a una o varias grillas Mercator.

    Interpolación bilineal; si la salida es más gruesa que el dato nativo, primero se suaviza
    (filtro gaussiano) para evitar el "serruchado". Devuelve ([campos], tiempo)."""
    from scipy.ndimage import gaussian_filter, map_coordinates
    unico = isinstance(anchos, int)
    anchos = [anchos] if unico else list(anchos)
    with fsspec.open(f"{BUCKET}/{key}", block_size=8 * 2**20, cache_type="bytes").open() as f:
        with h5py.File(f, "r") as h:
            idx = [_indices(h, canal, a) for a in anchos]
            r0 = min(i[3] for i in idx); r1 = max(i[4] for i in idx)
            c0 = min(i[5] for i in idx); c1 = max(i[6] for i in idx)
            d = h["CMI"]
            crudo = d[r0:r1, c0:c1]
            fill = d.attrs.get("_FillValue", [None])[0]
            esc, off = d.attrs["scale_factor"][0], d.attrs["add_offset"][0]
    campo = crudo.astype("float32") * esc + off
    malo = (crudo == fill) if fill is not None else np.zeros(crudo.shape, bool)
    campo[malo] = np.nanmean(campo[~malo]) if (~malo).any() else 0
    salidas = []
    for (ok, fi, co, a0, _, b0, _, escala) in idx:
        z = gaussian_filter(campo, sigma=0.45 * escala) if escala > 1.2 else campo
        out = np.full(ok.shape, np.nan, dtype="float32")
        out[ok] = map_coordinates(z, [fi[ok] + (a0 - r0), co[ok] + (b0 - c0)], order=1, mode="nearest")
        if canal != 2:
            out -= 273.15
        salidas.append(out)
    return (salidas[0] if unico else salidas), _inicio(key)


CALIDAD_WEBP = 76


def _guardar(img, path):
    """Guarda en WebP (con calidad CALIDAD_WEBP) o PNG según la extensión."""
    if path.endswith(".webp"):
        img.save(path, quality=CALIDAD_WEBP, method=4)
    else:
        img.save(path)


def png_visible(refl, path):
    """Nubes blancas sobre el mapa: la opacidad sigue al brillo (suelo oscuro = transparente)."""
    b = np.sqrt(np.clip(refl, 0, 1.1) / 1.1)
    b = np.nan_to_num(b, nan=0.0)
    gris = (b * 255).astype(np.uint8)
    alfa = np.clip((b - 0.28) / 0.35, 0, 1) * 255
    rgba = np.dstack([gris, gris, gris, alfa.astype(np.uint8)])
    _guardar(Image.fromarray(rgba, "RGBA"), path)


def png_visible_pleno(refl, path):
    """Visible opaco en grises (como lo muestra el SMN)."""
    b = np.sqrt(np.clip(np.nan_to_num(refl, nan=0), 0, 1.1) / 1.1)
    g = (b * 255).astype(np.uint8)
    _guardar(Image.fromarray(g, "L"), path)


def png_topes(tb, path):
    """IR realzado: nubes bajas grises semitransparentes; topes fríos en color y opacos."""
    cmap, v0, v1 = cartas._cmap_ir()
    t = np.nan_to_num(tb, nan=30.0)
    rgba = (cmap((t - v0) / (v1 - v0)) * 255).astype(np.uint8)
    alfa = np.clip((5 - t) / 40, 0, 1)            # transparente sobre +5 °C, opaco bajo −35 °C
    alfa = np.where(t < -45, 1.0, alfa * 0.85)
    rgba[..., 3] = (alfa * 255).astype(np.uint8)
    _guardar(Image.fromarray(rgba, "RGBA"), path)


# Lluvia: misma gama de azules que las cartas, transparente por debajo de 0,5 mm
_LL_NIV = [0.5, 2, 5, 10, 20, 30, 50, 75]
_LL_COL = ["#9dc3ea", "#73a6de", "#4c88cf", "#2f6bb8", "#1f5299", "#163d78", "#7b1fa2", "#c2185b"]


def png_lluvia(mm, lat, lon, path, ancho=700):
    """Campo de lluvia GFS (grilla regular) -> PNG Mercator suavizado."""
    from scipy.interpolate import RegularGridInterpolator
    la = np.asarray(lat)
    lo = np.asarray(lon)
    v = np.asarray(mm)
    if la[0] > la[-1]:
        la, v = la[::-1], v[::-1]
    f = RegularGridInterpolator((la, lo), v, bounds_error=False, fill_value=0.0)
    LON, LAT = grilla_mercator(ancho)
    z = f(np.stack([LAT.ravel(), LON.ravel()], -1)).reshape(LAT.shape)
    rgba = np.zeros(z.shape + (4,), np.uint8)
    for k, nivel in enumerate(_LL_NIV):
        c = _LL_COL[k].lstrip("#")
        rgb = [int(c[i:i + 2], 16) for i in (0, 2, 4)]
        m = z >= nivel
        rgba[m, :3] = rgb
        rgba[m, 3] = 200 if k else 150
    _guardar(Image.fromarray(rgba, "RGBA"), path)


LEYENDA_LLUVIA = list(zip(_LL_NIV, _LL_COL))
