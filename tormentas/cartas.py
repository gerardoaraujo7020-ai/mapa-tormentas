"""Cartas PNG de la provincia de Buenos Aires (matplotlib puro, sin cartopy)."""
from __future__ import annotations

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from shapely.geometry import shape

from .gfs import CAJA

AQUI = os.path.dirname(os.path.abspath(__file__))
LIMITES = os.path.join(AQUI, "..", "datos", "limites.geojson")
MARCA = "El Viejo Viento · seguimiento de tormentas"

LOCALIDADES = {
    "Benito Juárez": (-37.68, -59.80), "Tandil": (-37.32, -59.13),
    "Necochea": (-38.55, -58.74), "Tres Arroyos": (-38.38, -60.28),
    "Azul": (-36.78, -59.86), "Olavarría": (-36.89, -60.32),
    "Bahía Blanca": (-38.72, -62.27), "Mar del Plata": (-38.00, -57.56),
    "La Plata": (-34.92, -57.95), "Junín": (-34.59, -60.95),
    "Pehuajó": (-35.81, -61.90), "Coronel Suárez": (-37.46, -61.93),
    "Dolores": (-36.31, -57.68), "Pergamino": (-33.89, -60.57),
}

# desplazamiento de etiquetas para que no se pisen
DESPLAZ = {"Olavarría": (-0.08, 0.06, "right"), "Azul": (0.08, 0.08, "left"),
           "Necochea": (0.08, -0.22, "left"), "Tres Arroyos": (-0.08, 0.08, "right")}

TINTA = "#1f2328"
TINTA_2 = "#57606a"

# Lluvia: una sola gama (azules), de claro a oscuro
LLUVIA_NIVELES = [1, 5, 10, 20, 30, 40, 50, 75, 100, 150]
LLUVIA_CMAP = mcolors.ListedColormap(
    ["#e3eefa", "#c3dbf3", "#9dc3ea", "#73a6de", "#4c88cf", "#2f6bb8",
     "#1f5299", "#163d78", "#0e2a57", "#081a3a"])
# Ráfagas: una sola gama (naranjas)
RAFAGA_NIVELES = [30, 40, 50, 60, 70, 80, 90, 100, 120]
RAFAGA_CMAP = mcolors.ListedColormap(
    ["#fdf0e1", "#fbdcb8", "#f8c28a", "#f4a35d", "#ea8136", "#d5601d",
     "#b34612", "#8a320c", "#5e2108"])
# % de la normal: divergente marrón (seco) – gris – verde azulado (húmedo)
ANOM_NIVELES = [0, 10, 25, 50, 75, 100, 150, 200]
ANOM_CMAP = mcolors.ListedColormap(
    ["#f4f6f8", "#d7e9e4", "#aed4ca", "#7fbcae", "#4fa28f", "#2c8270", "#145f51", "#0b3d34"])


def _cmap_ir():
    """Realce IR: grises para topes tibios, amarillo→rojo→violeta para topes fríos."""
    pts = [(-90, "#ffffff"), (-80, "#7b1fa2"), (-72, "#c62828"), (-64, "#f57c00"),
           (-56, "#fbc02d"), (-52, "#fff176"), (-45, "#d9d9d9"), (-20, "#8c8c8c"), (30, "#141414")]
    v0, v1 = pts[0][0], pts[-1][0]
    return mcolors.LinearSegmentedColormap.from_list(
        "ir", [((v - v0) / (v1 - v0), c) for v, c in pts]), v0, v1


def _limites():
    feats = json.load(open(LIMITES))["features"]
    segs_ba, segs_otros = [], []
    for f in feats:
        g = shape(f["geometry"])
        polys = getattr(g, "geoms", [g])
        for p in polys:
            if p.geom_type != "Polygon":
                continue
            xy = np.asarray(p.exterior.coords)
            (segs_ba if f["properties"]["nombre"] in ("Buenos Aires", "Ciudad de Buenos Aires")
             else segs_otros).append(xy)
    return segs_ba, segs_otros


_SEGS = None


def base(ax, titulo: str, subtitulo: str = "", localidades=True, caja=None):
    caja = caja or CAJA
    global _SEGS
    if _SEGS is None:
        _SEGS = _limites()
    ba, otros = _SEGS
    ax.add_collection(LineCollection(otros, colors="#9aa3ab", linewidths=0.5, zorder=4))
    ax.add_collection(LineCollection(ba, colors=TINTA, linewidths=1.0, zorder=5))
    m = 0.5 if caja is CAJA else 0.0
    ax.set_xlim(caja["lon_min"] + m, caja["lon_max"] - m)
    ax.set_ylim(caja["lat_min"] + m, caja["lat_max"] - (0.4 if m else 0))
    ax.set_aspect(1 / np.cos(np.deg2rad((caja["lat_min"] + caja["lat_max"]) / 2)))
    ax.tick_params(labelsize=7, colors=TINTA_2)
    xt = [x for x in range(-71, -48, 2) if caja["lon_min"] < x < caja["lon_max"]]
    yt = [y for y in range(-45, -26, 2) if caja["lat_min"] < y < caja["lat_max"]]
    ax.set_xticks(xt)
    ax.set_xticklabels([f"{-x}°O" for x in xt])
    ax.set_yticks(yt)
    ax.set_yticklabels([f"{-y}°S" for y in yt])
    for s in ax.spines.values():
        s.set_color("#c9d1d9")
    if localidades:
        for n, (la, lo) in LOCALIDADES.items():
            dx, dy, ha = DESPLAZ.get(n, (0.08, 0.06, "left"))
            ax.plot(lo, la, "o", ms=2.5, color=TINTA, zorder=6)
            ax.text(lo + dx, la + dy, n, ha=ha, fontsize=6.3, color=TINTA, zorder=6,
                    bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.6))
    ax.set_title(titulo, loc="left", fontsize=11, color=TINTA, fontweight="bold",
                 pad=15 if subtitulo else 6)
    if subtitulo:
        ax.text(0, 1.012, subtitulo, transform=ax.transAxes, fontsize=7.5, color=TINTA_2, va="bottom")


def _guardar(fig, path, fuente):
    fig.text(0.01, 0.008, fuente, fontsize=6.3, color=TINTA_2)
    fig.text(0.99, 0.008, MARCA, fontsize=6.3, color=TINTA_2, ha="right")
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def campo(da, path, titulo, subtitulo, niveles, cmap, etiqueta, fuente, extend="max",
          marcar_max=True, mascara=None):
    fig, ax = plt.subplots(figsize=(6.4, 6.2))
    norm = mcolors.BoundaryNorm(niveles, cmap.N, extend=extend)
    if extend == "max":
        cm = cmap.copy(); cm.set_under("white")
    else:
        cm = cmap
    cf = ax.pcolormesh(da.longitude, da.latitude, da.values, cmap=cm, norm=norm,
                       shading="nearest", zorder=1)
    base(ax, titulo, subtitulo)
    cb = fig.colorbar(cf, ax=ax, shrink=0.8, pad=0.02, extend=extend)
    cb.set_label(etiqueta, fontsize=8, color=TINTA_2)
    cb.ax.tick_params(labelsize=7)
    if marcar_max:
        v = np.where(mascara, da.values, np.nan) if mascara is not None else da.values
        i = np.unravel_index(np.nanargmax(v), v.shape)
        lo, la = float(da.longitude[i[1]]), float(da.latitude[i[0]])
        ax.annotate(f"máx. {np.nanmax(v):.0f}", (lo, la), xytext=(-40, -28),
                    textcoords="offset points", fontsize=7.5, color=TINTA, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#9aa3ab", lw=0.5),
                    arrowprops=dict(arrowstyle="-", color=TINTA, lw=0.8), zorder=7)
    return _guardar(fig, path, fuente)


def tope_nube(da, path, titulo, subtitulo, fuente):
    cmap, v0, v1 = _cmap_ir()
    fig, ax = plt.subplots(figsize=(6.4, 6.2))
    cf = ax.pcolormesh(da.lon, da.lat, da.values, cmap=cmap, vmin=v0, vmax=v1,
                       shading="nearest", zorder=1, rasterized=True)
    base(ax, titulo, subtitulo)
    cb = fig.colorbar(cf, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("Temperatura de tope de nube (°C)", fontsize=8, color=TINTA_2)
    cb.ax.tick_params(labelsize=7)
    return _guardar(fig, path, fuente)


def mosaico_topes(lista, path, titulo, fuente):
    cmap, v0, v1 = _cmap_ir()
    n = len(lista)
    cols = 3
    filas = int(np.ceil(n / cols))
    fig, axs = plt.subplots(filas, cols, figsize=(9.6, 3.3 * filas))
    for ax, da in zip(np.ravel(axs), lista):
        ax.pcolormesh(da.lon, da.lat, da.values, cmap=cmap, vmin=v0, vmax=v1,
                      shading="nearest", rasterized=True)
        base(ax, "", localidades=False)
        hora = da.attrs["tiempo"]
        ax.set_title(_hora_local(hora), fontsize=8.5, loc="left", color=TINTA)
        ax.tick_params(labelsize=5.5)
    for ax in np.ravel(axs)[n:]:
        ax.axis("off")
    fig.suptitle(titulo, x=0.01, ha="left", fontsize=12, fontweight="bold", color=TINTA)
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    return _guardar(fig, path, fuente)


def frecuencia(lista, umbral):
    tb = np.stack([d.values for d in lista])
    return 100 * np.nanmean(tb < umbral, axis=0)


def frecuencia_topes_frios(lista, path, umbral, titulo, subtitulo, fuente):
    frec = frecuencia(lista, umbral)
    d0 = lista[0]
    fig, ax = plt.subplots(figsize=(6.4, 6.2))
    niveles = [5, 10, 20, 30, 40, 50, 60]
    cmap = mcolors.ListedColormap(["#efe6f5", "#d9c3ea", "#bf9bdc", "#a172c9", "#8150b0", "#5f3590"])
    cm = cmap.copy(); cm.set_under("white"); cm.set_over("#3f1f66")
    cf = ax.pcolormesh(d0.lon, d0.lat, frec, cmap=cm,
                       norm=mcolors.BoundaryNorm(niveles, cmap.N),
                       shading="nearest", rasterized=True)
    base(ax, titulo, subtitulo)
    cb = fig.colorbar(cf, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label(f"% de imágenes horarias con tope < {umbral} °C", fontsize=8, color=TINTA_2)
    cb.ax.tick_params(labelsize=7)
    return _guardar(fig, path, fuente)


def sinoptica(ds, path, titulo, subtitulo, fuente):
    fig, ax = plt.subplots(figsize=(6.4, 6.2))
    cape = ds["cape"]
    niveles = [250, 500, 1000, 1500, 2000, 3000]
    cmap = mcolors.ListedColormap(["#fff3c4", "#ffe08a", "#fdc35a", "#f59e3a", "#e0702a"])
    cm = cmap.copy(); cm.set_under("white"); cm.set_over("#b8471c")
    cf = ax.pcolormesh(ds.longitude, ds.latitude, cape, cmap=cm,
                       norm=mcolors.BoundaryNorm(niveles, cmap.N), shading="nearest")
    cs = ax.contour(ds.longitude, ds.latitude, ds["prmsl"] / 100, levels=range(980, 1040, 2),
                    colors=TINTA, linewidths=0.7, zorder=3)
    ax.clabel(cs, fontsize=6.5, fmt="%d")
    s = slice(None, None, 3)
    ax.barbs(ds.longitude[s], ds.latitude[s], ds["u10"].values[s, s] * 1.944,
             ds["v10"].values[s, s] * 1.944, length=4.6, lw=0.5, color="#33475b", zorder=4)
    base(ax, titulo, subtitulo, localidades=False)
    cb = fig.colorbar(cf, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("CAPE (J/kg) · isobaras hPa · viento 10 m (nudos)", fontsize=8, color=TINTA_2)
    cb.ax.tick_params(labelsize=7)
    return _guardar(fig, path, fuente)


def _hora_local(utc_txt: str) -> str:
    from datetime import datetime, timedelta
    t = datetime.strptime(utc_txt[:16], "%Y-%m-%d %H:%M") - timedelta(hours=3)
    dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    return f"{dias[t.weekday()]} {t:%d/%m %H:%M} HOA"


def series_localidades(lluvia, rafaga, nombres, path, titulo, fuente):
    """Lluvia horaria (barras) y ráfaga (línea) en paneles separados: nunca doble eje."""
    import pandas as pd
    n = len(nombres)
    fig, axs = plt.subplots(n, 2, figsize=(9.6, 1.65 * n + 0.6), sharex=True)
    t = pd.to_datetime(lluvia.time.values) - pd.Timedelta(hours=3)
    for k, nom in enumerate(nombres):
        la, lo = LOCALIDADES[nom]
        p = lluvia.sel(latitude=la, longitude=lo, method="nearest").values
        g = rafaga.sel(latitude=la, longitude=lo, method="nearest").values
        a1, a2 = axs[k]
        a1.bar(t, p, width=0.035, color="#2f6bb8", edgecolor="white", linewidth=0.3)
        a1.text(0.01, 0.92, f"{nom} · total {np.nansum(p):.0f} mm", transform=a1.transAxes,
                fontsize=8, va="top", color=TINTA, fontweight="bold")
        a2.plot(t, g, color="#d5601d", lw=1.6)
        a2.text(0.01, 0.92, f"{nom} · ráfaga máx. {np.nanmax(g):.0f} km/h", transform=a2.transAxes,
                fontsize=8, va="top", color=TINTA, fontweight="bold")
        a1.set_ylim(0, max(5, np.nanmax(p) * 1.35))
        a2.set_ylim(0, max(60, np.nanmax(g) * 1.3))
        for a in (a1, a2):
            a.grid(axis="y", color="#e6e9ec", lw=0.6)
            a.tick_params(labelsize=7, colors=TINTA_2)
            for s in ("top", "right"):
                a.spines[s].set_visible(False)
        a1.set_ylabel("mm/h", fontsize=7, color=TINTA_2)
        a2.set_ylabel("km/h", fontsize=7, color=TINTA_2)
    import matplotlib.dates as mdates
    for a in axs[-1]:
        a.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%H h"))
    fig.suptitle(titulo, x=0.01, ha="left", fontsize=12, fontweight="bold", color=TINTA)
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    return _guardar(fig, path, fuente)
