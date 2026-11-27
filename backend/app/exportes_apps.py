"""Exportes en el formato nativo de cada aplicación, un solo archivo por aplicación.

- Power BI: un libro de Excel (.xlsx) con una hoja y una tabla de Excel por cada tabla del modelo.
  En Power BI Desktop: Obtener datos > Libro de Excel > marcar las tablas.
- Maltego: un grafo .mtgx (zip con GraphML de Maltego). En Maltego: File > Open.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape, quoteattr

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


def _numero(v: str):
    if v is None or v == "":
        return None
    if re.fullmatch(r"-?\d+", v):
        try:
            return int(v)
        except ValueError:
            return v
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    return v


def powerbi_xlsx(tablas: dict[str, str]) -> bytes:
    """tablas: {"casos.csv": texto CSV, ...} → libro .xlsx con una tabla de Excel por hoja."""
    wb = Workbook()
    wb.remove(wb.active)
    encabezado = Font(bold=True, color="FFFFFF")
    relleno = PatternFill("solid", fgColor="00713D")
    for nombre in sorted(tablas):
        hoja = nombre.rsplit(".", 1)[0][:31]
        ws = wb.create_sheet(hoja)
        filas = list(csv.reader(io.StringIO(tablas[nombre])))
        if not filas:
            continue
        ws.append(filas[0])
        for f in filas[1:]:
            ws.append([_numero(v) for v in f])
        for c in ws[1]:
            c.font, c.fill = encabezado, relleno
        ws.freeze_panes = "A2"
        for i, col in enumerate(filas[0], start=1):
            largo = max([len(str(col))] + [len(str(f[i - 1])) for f in filas[1:200] if len(f) >= i])
            ws.column_dimensions[get_column_letter(i)].width = min(60, max(10, largo + 2))
        ultima = max(2, len(filas))                       # una tabla de Excel necesita al menos una fila de datos
        if len(filas) == 1:
            ws.append([None] * len(filas[0]))
        nombre_tabla = "T_" + re.sub(r"\W", "_", hoja)
        t = Table(displayName=nombre_tabla, ref=f"A1:{get_column_letter(len(filas[0]))}{ultima}")
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium7", showRowStripes=True)
        ws.add_table(t)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- Maltego ----------
TIPO_MALTEGO = {
    "ip": ("maltego.IPv4Address", "ipv4-address", "IP Address"),
    "servidor": ("maltego.IPv4Address", "ipv4-address", "IP Address"),
    "cuenta": ("maltego.Alias", "alias", "Alias"),
}


def _propiedad(nombre: str, titulo: str, valor: str) -> str:
    return (f'<mtg:Property displayName={quoteattr(titulo)} hidden="false" name={quoteattr(nombre)} nullable="true" '
            f'readonly="false" type="string"><mtg:Value>{escape(str(valor))}</mtg:Value></mtg:Property>')


def maltego_mtgx(grafo: dict) -> bytes:
    """Grafo de la consola ({nodos, aristas}) → archivo .mtgx que Maltego abre con File > Open."""
    ids = {n["id"]: f"n{i}" for i, n in enumerate(grafo.get("nodos", []))}
    nodos = []
    for n in grafo.get("nodos", []):
        tipo, prop, titulo = TIPO_MALTEGO.get(n.get("tipo"), TIPO_MALTEGO["cuenta"])
        props = [_propiedad(prop, titulo, n.get("etiqueta", n["id"]))]
        if n.get("detalle"):
            props.append(_propiedad("sentinel.detalle", "Detalle", n["detalle"]))
        if n.get("casoId"):
            props.append(_propiedad("sentinel.caso", "Caso", n["casoId"]))
        if n.get("gravedad"):
            props.append(_propiedad("sentinel.gravedad", "Gravedad", n["gravedad"]))
        nodos.append(f'<node id="{ids[n["id"]]}"><data key="d0"><mtg:MaltegoEntity id="{uuid.uuid4().hex}" '
                     f'type="{tipo}"><mtg:Properties>{"".join(props)}</mtg:Properties></mtg:MaltegoEntity>'
                     f'</data></node>')
    aristas = []
    for k, a in enumerate(grafo.get("aristas", [])):
        if a.get("origen") not in ids or a.get("destino") not in ids:
            continue
        etiqueta = f'{a.get("etiqueta", "")} ({a.get("eventos", 0)} eventos)'
        aristas.append(f'<edge id="e{k}" source="{ids[a["origen"]]}" target="{ids[a["destino"]]}"><data key="d1">'
                       f'<mtg:MaltegoLink id="{uuid.uuid4().hex}" type="maltego.link.manual-link"><mtg:Properties>'
                       f'{_propiedad("maltego.link.manual.type", "Label", etiqueta)}'
                       f'{_propiedad("maltego.link.manual.description", "Description", a.get("etiqueta", ""))}'
                       f'</mtg:Properties></mtg:MaltegoLink></data></edge>')
    graphml = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
               '<graphml xmlns="http://graphml.graphdrawing.org/xmlns" '
               'xmlns:mtg="http://maltego.paterva.com/xml/mtgx">'
               '<key attr.name="MaltegoEntity" for="node" id="d0"/>'
               '<key attr.name="MaltegoLink" for="edge" id="d1"/>'
               f'<graph edgedefault="directed" id="G">{"".join(nodos)}{"".join(aristas)}</graph></graphml>')
    version = (f"#{datetime.now():%a %b %d %H:%M:%S %Y}\n"
               "maltego.client.version=4.6.0\nmaltego.client.name=Sentinel Salud\n"
               "maltego.mtz.version=1.0\nmaltego.graph.version=1.2\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Version.properties", version)
        z.writestr("Graphs/Graph1.graphml", graphml)
    return buf.getvalue()
