"""Boletín PDF de la tormenta (reportlab)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

TINTA = colors.HexColor("#1f2328")
TINTA_2 = colors.HexColor("#57606a")
ACENTO = colors.HexColor("#1f5299")
BORDE = colors.HexColor("#d0d7de")

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=TINTA)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=TINTA,
                    spaceBefore=6, spaceAfter=4)
TX = ParagraphStyle("tx", fontName="Helvetica", fontSize=9.2, leading=12.5, textColor=TINTA,
                    alignment=TA_LEFT)
CHICO = ParagraphStyle("ch", parent=TX, fontSize=7.5, leading=9.5, textColor=TINTA_2)
NUM = ParagraphStyle("num", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=TINTA)
ETQ = ParagraphStyle("etq", fontName="Helvetica", fontSize=7.5, leading=9, textColor=TINTA_2)


def _f(x, d=0):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _cabecera(c, doc):
    c.saveState()
    c.setFillColor(ACENTO)
    c.rect(0, A4[1] - 9 * mm, A4[0], 9 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(15 * mm, A4[1] - 6 * mm, "EL VIEJO VIENTO · Seguimiento de tormentas · Provincia de Buenos Aires")
    c.setFillColor(TINTA_2)
    c.setFont("Helvetica", 7)
    c.drawString(15 * mm, 8 * mm, f"Generado el {datetime.now(timezone(timedelta(hours=-3))):%d/%m/%Y %H:%M} (hora argentina) con fuentes satelitales y de modelo de acceso libre")
    c.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Pág. {doc.page}")
    c.restoreState()


def _img(path, ancho):
    from PIL import Image as PI
    w, h = PI.open(path).size
    return Image(path, width=ancho, height=ancho * h / w)


def _tiles(items):
    celdas = [[Paragraph(v, NUM) for v, _ in items], [Paragraph(e, ETQ) for _, e in items]]
    t = Table(celdas, colWidths=[45 * mm] * len(items))
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, BORDE), ("LINEAFTER", (0, 0), (-2, -1), 0.6, BORDE),
        ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _resumen_texto(r):
    l, g, an, go = r["lluvia"], r["rafaga"], r["anomalia"], r["goes"]
    locs = sorted(r["localidades"].items(), key=lambda kv: -kv[1]["lluvia"])
    top = ", ".join(f"{n} ~{_f(v['lluvia'])} mm" for n, v in locs[:3])
    contraste = ""
    if go.get("dist_km", 0) > 150:
        contraste = (
            f" <b>Ojo:</b> el satélite muestra la convección más persistente cerca de {go['frec_cerca']} "
            f"(topes bajo −52 °C en el {_f(go['frec_max'])} % de las horas), mientras que el modelo ubica la "
            f"lluvia máxima cerca de {l['max_cerca']}, a unos {_f(go['dist_km'])} km. Donde no coinciden, "
            f"es probable que el modelo haya subestimado la lluvia convectiva: conviene contrastar con pluviómetros.")
    return (
        f"Entre el {r['periodo'].replace('→', 'y el')} un sistema de tormentas atravesó la provincia. "
        f"El modelo estima un promedio provincial de <b>{_f(l['media_prov'], 1)} mm</b>, con un máximo de "
        f"<b>{_f(l['max'])} mm</b> cerca de {abs(l['max_lat']):.1f}°S {abs(l['max_lon']):.1f}°O. "
        f"El {_f(l['area_20'])} % del territorio superó los 20 mm y el {_f(l['area_50'])} % los 50 mm. "
        f"La lluvia más intensa se dio alrededor del <b>{r['pico']}</b>. "
        f"En las localidades seguidas: {top}. "
        f"Las ráfagas llegaron a <b>{_f(g['max'])} km/h</b> en el modelo. "
        f"En el satélite GOES-19 los topes de nube bajaron hasta <b>{_f(go['min_tb'])} °C</b> ({go['hora']}), "
        f"señal de convección profunda con posible granizo y actividad eléctrica. "
        f"En promedio, la tormenta aportó el {_f(an['pct_media'])} % de la lluvia normal de {r['mes']} "
        f"para la provincia." + contraste)


def armar_boletin(r, path):
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title=r["nombre"], author="El Viejo Viento")
    W = A4[0] - 30 * mm
    c = r["cartas"]
    s = [Paragraph(r["nombre"], H1), Paragraph(r["periodo"] + " · hora argentina", CHICO), Spacer(1, 5 * mm),
         _tiles([(f"{_f(r['lluvia']['max'])} mm", "lluvia máxima en la provincia"),
                 (f"{_f(r['lluvia']['area_20'])} %", "del territorio con 20 mm o más"),
                 (f"{_f(r['rafaga']['max'])} km/h", "ráfaga máxima (modelo)"),
                 (f"{_f(r['goes']['min_tb'])} °C", "tope de nube más frío (GOES-19)")]),
         Spacer(1, 4 * mm), Paragraph("Resumen", H2), Paragraph(_resumen_texto(r), TX), Spacer(1, 3 * mm)]
    fila = Table([[_img(c["lluvia"], W / 2 - 2 * mm), _img(c["rafaga"], W / 2 - 2 * mm)]],
                 colWidths=[W / 2] * 2)
    fila.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    s += [fila]

    # Tabla de localidades
    filas = [["Localidad", "Lluvia (mm)", "% normal del mes", "Ráfaga máx. (km/h)"]]
    for n, v in r["localidades"].items():
        filas.append([n, _f(v["lluvia"]), f"{_f(v['pct_normal'])} %", _f(v["rafaga"])])
    tab = Table(filas, colWidths=[55 * mm, 35 * mm, 40 * mm, 40 * mm])
    tab.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), TINTA), ("LINEBELOW", (0, 0), (-1, 0), 0.8, TINTA),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, BORDE), ("ALIGN", (1, 0), (-1, -1), "RIGHT")]))

    s += [PageBreak(), Paragraph("Localidades", H2), tab, Spacer(1, 3 * mm),
          _img(c["series"], W)]
    s += [PageBreak(), Paragraph("Satélite: topes de nube GOES-19", H2),
          Paragraph("Temperatura de brillo del canal infrarrojo (10,3 µm). Cuanto más fría, más alta la nube: "
                    "por debajo de −52 °C indica cumulonimbos de desarrollo profundo; debajo de −70 °C, "
                    "núcleos muy intensos con riesgo de granizo y ráfagas.", TX),
          Spacer(1, 2 * mm), _img(c["goes_secuencia"], W)]
    fila2 = Table([[_img(c["goes_pico"], W / 2 - 2 * mm), _img(c["goes_frecuencia"], W / 2 - 2 * mm)]],
                  colWidths=[W / 2] * 2)
    fila2.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    s += [fila2]
    fila3 = Table([[_img(c["anomalia"], W / 2 - 2 * mm), _img(c["sinoptica"], W / 2 - 2 * mm)]],
                  colWidths=[W / 2] * 2)
    fila3.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    s += [PageBreak(), Paragraph("Anomalía y situación sinóptica", H2),
          Paragraph(f"A la izquierda, lo que llovió en el evento como porcentaje de la lluvia normal de "
                    f"{r['mes']} (1991-2020). A la derecha, presión al nivel del mar, viento y energía "
                    f"disponible para tormentas (CAPE) cerca de la hora pico.", TX), Spacer(1, 2 * mm), fila3]

    if "pronostico" in r:
        p = r["pronostico"]
        txt = (f"Corrida GFS de las {p['corrida']}. Para las próximas 72 horas el modelo marca hasta "
               f"<b>{_f(p['lluvia_max'])} mm</b> en la provincia y ráfagas de hasta <b>{_f(p['rafaga_max'])} km/h</b>. "
               + " ".join(f"{n}: {_f(v['lluvia'])} mm, ráfaga {_f(v['rafaga'])} km/h."
                          for n, v in p["localidades"].items()))
        s += [Spacer(1, 4 * mm), Paragraph("Qué viene: próximas 72 horas", H2), Paragraph(txt, TX),
              Spacer(1, 2 * mm), _img(c["pronostico"], W * 0.62)]

    s += [Spacer(1, 4 * mm), Paragraph("Fuentes y alcance", H2), Paragraph(
        "Todas las fuentes son públicas y gratuitas, sin registro: NOAA GOES-19 ABI (AWS Open Data), "
        "NOAA GFS 0,25° (AWS Open Data) y GPCP v2.3 mensual (NOAA Climate Data Record). "
        "La lluvia y las ráfagas del evento salen del modelo GFS en sus primeras horas de cada corrida "
        "(lo más parecido a un análisis): sirven para ver dónde y cuándo cayó, pero no reemplazan a los "
        "pluviómetros. Las cifras puntuales son de la celda de 25 km más cercana.", CHICO)]
    doc.build(s, onFirstPage=_cabecera, onLaterPages=_cabecera)
    return path
