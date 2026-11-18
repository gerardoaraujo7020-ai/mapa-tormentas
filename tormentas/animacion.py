"""Animaciones MP4 y GIF de la tormenta (cuadros con matplotlib, video con ffmpeg).

Requiere ffmpeg instalado (https://ffmpeg.org; en Windows: `winget install ffmpeg`).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import cartas


def _video(carpeta, salida_base, fps):
    """Arma .mp4 y .gif a partir de cuadro_%04d.png."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("Falta ffmpeg: instalalo para generar animaciones")
    patron = os.path.join(carpeta, "cuadro_%04d.png")
    mp4, gif = salida_base + ".mp4", salida_base + ".gif"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", patron,
                    "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2:color=white", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", mp4], check=True)
    paleta = os.path.join(carpeta, "paleta.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", patron,
                    "-vf", "scale=760:-1:flags=lanczos,palettegen=max_colors=128", paleta], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", patron, "-i", paleta,
                    "-lavfi", "scale=760:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4",
                    "-loop", "0", gif], check=True)
    return mp4, gif


def _pie(fig, fuente):
    fig.text(0.01, 0.012, fuente, fontsize=6.5, color=cartas.TINTA_2)
    fig.text(0.99, 0.012, cartas.MARCA, fontsize=6.5, color=cartas.TINTA_2, ha="right")


def topes_nube(topes, salida_base, fps=8, titulo="Topes de nube GOES-19"):
    """Animación del infrarrojo GOES-19 (un cuadro por imagen)."""
    cmap, v0, v1 = cartas._cmap_ir()
    tmp = tempfile.mkdtemp(prefix="anim_goes_")
    try:
        for k, da in enumerate(topes):
            fig, ax = plt.subplots(figsize=(6.4, 6.4))
            cf = ax.pcolormesh(da.lon, da.lat, da.values, cmap=cmap, vmin=v0, vmax=v1,
                               shading="nearest", rasterized=True)
            cartas.base(ax, titulo, cartas._hora_local(da.attrs["tiempo"]) + "  ·  temperatura del tope de nube")
            cb = fig.colorbar(cf, ax=ax, shrink=0.78, pad=0.02)
            cb.set_label("°C (debajo de −52 °C: tormenta profunda)", fontsize=8, color=cartas.TINTA_2)
            cb.ax.tick_params(labelsize=7)
            _pie(fig, "Fuente: NOAA GOES-19 ABI canal 13 · AWS Open Data")
            fig.savefig(os.path.join(tmp, f"cuadro_{k:04d}.png"), dpi=130, facecolor="white")
            plt.close(fig)
        return _video(tmp, salida_base, fps)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def satelite_y_lluvia(topes, lluvia, salida_base, fps=4):
    """Dos paneles por hora: satélite (izq.) y lluvia del modelo en esa hora + acumulada (der.)."""
    cmap_ir, v0, v1 = cartas._cmap_ir()
    norm_h = mcolors.BoundaryNorm([0.5, 1, 2, 5, 10, 20, 30, 50], 7)
    cmap_h = mcolors.ListedColormap(["#c3dbf3", "#9dc3ea", "#73a6de", "#4c88cf", "#2f6bb8",
                                     "#1f5299", "#0e2a57"]).with_extremes(under=(1, 1, 1, 0), over="#081a3a")
    tiempos = pd.to_datetime(lluvia.time.values)
    t_goes = pd.to_datetime([d.attrs["tiempo"][:16] for d in topes])
    acum = lluvia.cumsum("time")
    tmp = tempfile.mkdtemp(prefix="anim_mix_")
    try:
        for k, t in enumerate(tiempos):
            j = int(np.argmin(np.abs((t_goes - t).total_seconds())))
            da = topes[j]
            fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 5.9))
            c1 = a1.pcolormesh(da.lon, da.lat, da.values, cmap=cmap_ir, vmin=v0, vmax=v1,
                               shading="nearest", rasterized=True)
            cartas.base(a1, "Satélite GOES-19", cartas._hora_local(da.attrs["tiempo"]), localidades=False)
            ac = acum.isel(time=k)
            a2.contour(ac.longitude, ac.latitude, ac.values, levels=[10, 25, 50],
                       colors=["#9aa3ab", "#57606a", "#1f2328"], linewidths=[0.6, 0.8, 1.1], zorder=3)
            c2 = a2.pcolormesh(lluvia.longitude, lluvia.latitude, lluvia.isel(time=k).values,
                               cmap=cmap_h, norm=norm_h, shading="nearest", zorder=2)
            cartas.base(a2, "Lluvia del modelo en esa hora",
                        f"{cartas._hora_local(f'{t:%Y-%m-%d %H:%M}')}  ·  líneas: acumulado 10, 25 y 50 mm",
                        localidades=False)
            for n in ("Benito Juárez", "Tandil", "Necochea", "Bahía Blanca", "Pergamino", "La Plata"):
                la, lo = cartas.LOCALIDADES[n]
                for a in (a1, a2):
                    a.plot(lo, la, "o", ms=2.5, color=cartas.TINTA if a is a2 else "white", zorder=6)
                a2.text(lo + 0.08, la + 0.06, n, fontsize=6.3, color=cartas.TINTA, zorder=6)
            b1 = fig.colorbar(c1, ax=a1, shrink=0.7, pad=0.02)
            b1.set_label("Tope de nube (°C)", fontsize=7.5, color=cartas.TINTA_2)
            b2 = fig.colorbar(c2, ax=a2, shrink=0.7, pad=0.02, extend="max")
            b2.set_label("mm en la hora", fontsize=7.5, color=cartas.TINTA_2)
            for b in (b1, b2):
                b.ax.tick_params(labelsize=7)
            _pie(fig, "Fuentes: NOAA GOES-19 canal 13 y GFS 0,25° · AWS Open Data")
            fig.savefig(os.path.join(tmp, f"cuadro_{k:04d}.png"), dpi=120, facecolor="white")
            plt.close(fig)
        return _video(tmp, salida_base, fps)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
