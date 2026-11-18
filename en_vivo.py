"""Nubosidad en vivo GOES-19 sobre la provincia de Buenos Aires (visible + topes nubosos).

Uso:
  python en_vivo.py              # corre sin parar, actualiza cada 10 minutos
  python en_vivo.py --una-vez    # una sola actualización (para el Programador de tareas)
Después abrí en_vivo/index.html en el navegador: se recarga solo.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import time
import traceback
from datetime import datetime, timedelta, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from tormentas import cartas, envivo

AQUI = os.path.dirname(os.path.abspath(__file__))
LOCALIDADES = {**cartas.LOCALIDADES, "Montevideo": (-34.90, -56.16), "Rosario": (-32.95, -60.65),
               "Santa Rosa": (-36.62, -64.29), "Viedma": (-40.81, -62.99), "Río Cuarto": (-33.12, -64.35),
               "Paraná": (-31.73, -60.53), "Punta del Este": (-34.96, -54.95)}


def _hoa(t):
    return cartas._hora_local(f"{t:%Y-%m-%d %H:%M}")


def _cuadro(v, lat, lon, t, canal, path):
    fig, ax = plt.subplots(figsize=(7.4, 6.8))
    if canal == 2:
        img = np.sqrt(np.clip(v, 0, 1.1) / 1.1)  # gamma para realzar nubes finas
        ax.pcolormesh(lon, lat, img, cmap="gray", vmin=0, vmax=1, shading="nearest", rasterized=True)
        titulo = "Visible · GOES-19 canal 2"
        noche = np.nanmean(v) < 0.03
        sub = _hoa(t) + ("  ·  de noche el visible no muestra nubes: mirá los topes" if noche else "")
    else:
        cmap, v0, v1 = cartas._cmap_ir()
        cf = ax.pcolormesh(lon, lat, v, cmap=cmap, vmin=v0, vmax=v1, shading="nearest", rasterized=True)
        titulo = "Topes nubosos · GOES-19 canal 13 realzado"
        sub = _hoa(t) + "  ·  amarillo a violeta: tormentas, más frío = más alto"
        cax = ax.inset_axes([0.62, 0.035, 0.35, 0.025])
        cb = fig.colorbar(cf, cax=cax, orientation="horizontal", ticks=[-80, -60, -40, -20, 0, 20])
        cb.ax.tick_params(labelsize=6, colors="white", length=2)
        cb.outline.set_edgecolor("white")
        cax.set_title("°C", fontsize=6, color="white", pad=2)
    cartas.base(ax, titulo, sub, localidades=False, caja=envivo.CAJA)
    lc = "white"
    for n, (la, lo) in LOCALIDADES.items():
        if n in ("Pergamino", "Pehuajó", "Coronel Suárez", "Dolores", "Paraná"):
            continue  # menos etiquetas para que el mapa grande no se cargue
        dx, dy, ha = cartas.DESPLAZ.get(n, (0.1, 0.07, "left"))
        if n == "Punta del Este":
            dx, dy, ha = (-0.1, -0.25, "right")
        ax.plot(lo, la, "o", ms=2.6, mfc="#00e5ff" if canal == 2 else "white", mec="black", mew=0.4, zorder=7)
        ax.text(lo + dx, la + dy, n, ha=ha, fontsize=6.5, color=lc, zorder=7,
                path_effects=[matplotlib.patheffects.withStroke(linewidth=1.6, foreground="black")])
    # límites en color claro para que se vean sobre fondo oscuro
    for coll in ax.collections:
        if isinstance(coll, matplotlib.collections.LineCollection):
            coll.set_color("#ffd54f" if canal == 2 else "#00e5ff")
    fig.text(0.01, 0.01, "Fuente: NOAA GOES-19 ABI · AWS Open Data", fontsize=6.3, color=cartas.TINTA_2)
    fig.text(0.99, 0.01, cartas.MARCA, fontsize=6.3, color=cartas.TINTA_2, ha="right")
    fig.savefig(path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def actualizar(salida: str, horas: float):
    salida = os.path.abspath(salida)
    os.makedirs(os.path.join(salida, "cuadros"), exist_ok=True)
    hechos = 0
    for canal, pref in ((13, "ir"), (2, "vis")):
        for key in envivo.ultimas_claves(canal, horas):
            t = envivo._inicio(key)
            path = os.path.join(salida, "cuadros", f"{pref}_{t:%Y%m%d_%H%M}.png")
            if os.path.exists(path):
                continue
            v, lat, lon, t = envivo.leer_recorte(key, canal)
            _cuadro(v, lat, lon, t, canal, path)
            hechos += 1
            print(f"  {pref} {_hoa(t)}")
    # borrar cuadros más viejos que la ventana
    limite = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=horas + 0.5)
    for p in glob.glob(os.path.join(salida, "cuadros", "*.png")):
        t = datetime.strptime(os.path.basename(p)[-17:-4], "%Y%m%d_%H%M")
        if t < limite:
            os.remove(p)
    cuadros = {pref: sorted(os.path.basename(p) for p in glob.glob(os.path.join(salida, "cuadros", f"{pref}_*.png")))
               for pref in ("vis", "ir")}
    for pref in ("vis", "ir"):
        if cuadros[pref]:
            shutil.copy(os.path.join(salida, "cuadros", cuadros[pref][-1]), os.path.join(salida, f"ultimo_{pref}.png"))
            _gif(salida, pref, cuadros[pref])
    _visor(salida, cuadros)
    return hechos


def _gif(salida, pref, lista):
    if shutil.which("ffmpeg") is None:
        return
    txt = os.path.join(salida, f"_lista_{pref}.txt")
    with open(txt, "w") as fh:
        for n in lista:
            fh.write(f"file 'cuadros/{n}'\nduration 0.25\n")
        fh.write(f"file 'cuadros/{lista[-1]}'\nduration 1.5\nfile 'cuadros/{lista[-1]}'\n")
    out = os.path.join(salida, f"animacion_{pref}.gif")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", txt, "-vf",
                    "scale=700:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=160[p];[b][p]paletteuse=dither=bayer",
                    "-loop", "0", out], check=False, cwd=salida)
    os.remove(txt)


def _visor(salida, cuadros):
    plantilla = open(os.path.join(AQUI, "datos", "visor.html"), encoding="utf-8").read()
    html = plantilla.replace("/*CUADROS*/null", json.dumps(cuadros)).replace(
        "/*ACTUALIZADO*/", _hoa(datetime.now(timezone.utc).replace(tzinfo=None)))
    with open(os.path.join(salida, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default="en_vivo")
    ap.add_argument("--horas", type=float, default=3, help="horas de animación (por defecto 3)")
    ap.add_argument("--cada", type=int, default=10, help="minutos entre actualizaciones")
    ap.add_argument("--una-vez", action="store_true")
    a = ap.parse_args()
    while True:
        print(f"Actualizando ({datetime.now():%H:%M})…")
        try:
            n = actualizar(a.salida, a.horas)
            print(f"  {n} imágenes nuevas. Visor: {os.path.abspath(os.path.join(a.salida, 'index.html'))}")
        except Exception:
            traceback.print_exc()
        if a.una_vez:
            break
        time.sleep(a.cada * 60)


if __name__ == "__main__":
    import matplotlib.collections  # noqa: F401
    import matplotlib.patheffects  # noqa: F401
    main()
