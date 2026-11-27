"""Sentinel Salud · backend local.

Arranque (desde backend/):  uvicorn app.main:app --host 127.0.0.1 --port 8000
Documentación de la API:    http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Path, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from . import (
    analisis,
    bd,
    ci,
    config,
    datos,
    denuncias,
    ejecutivo,
    estado,
    exportes_apps,
    impacto,
    informe_pdf,
    listas,
    osint,
    realimentacion,
    reportes,
    riesgos,
    seguridad,
    telegram,
    tickets,
    verificar,
)
from .seguridad import ROLES, Sesion, requiere

app = FastAPI(title="Sentinel Salud API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=config.ORIGENES, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "Authorization"])
ID_CASO = Path(..., pattern=r"^C\d{1,3}$")


@app.middleware("http")
async def cabeceras(request: Request, call_next):
    r = await call_next(request)
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Referrer-Policy"] = "no-referrer"
    r.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    r.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' "
                                            "'unsafe-inline'; script-src 'self'; connect-src 'self'; "
                                            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if request.url.path.startswith("/api"):
        r.headers["Cache-Control"] = "no-store"
    return r


@app.exception_handler(HTTPException)
async def _error(_: Request, e: HTTPException):
    return PlainTextResponse(str(e.detail), status_code=e.status_code)


@app.exception_handler(RequestValidationError)
async def _invalido(_: Request, e: RequestValidationError):
    campos = ", ".join(".".join(str(x) for x in err["loc"][1:]) or "cuerpo" for err in e.errors())
    return PlainTextResponse(f"Revisa estos datos: {campos}.", status_code=422)


def _rol(s: Sesion) -> str:
    return ROLES[s.rol]["nombre"]


# ---------- acceso ----------
class Ingreso(BaseModel):
    usuario: str = Field(min_length=1, max_length=40)
    clave: str = Field(min_length=1, max_length=200)


@app.get("/api/acceso/roles")
def roles():
    return [{"rol": k, "nombre": v["nombre"], "descripcion": v["descripcion"], "permisos": v["permisos"]}
            for k, v in ROLES.items()]


@app.post("/api/acceso/ingresar")
def ingresar(i: Ingreso):
    token, s = seguridad.ingresar(i.usuario, i.clave)
    return {"token": token, "sesion": s.publica()}


@app.get("/api/acceso/yo")
def yo(s: Sesion = Depends(seguridad.sesion_actual)):
    return s.publica()


@app.post("/api/acceso/salir")
def salir(request: Request):
    seguridad.salir(request.headers.get("authorization", "").removeprefix("Bearer ").strip())
    return {"ok": True}


# ---------- cargar datos ----------
def _al_terminar(i: str) -> None:
    try:
        telegram.avisar_criticos(i, datos.casos())
    except HTTPException:
        pass


@app.get("/api/analisis")
def analisis_lista(s: Sesion = Depends(requiere("estrategico"))):
    return {"activo": analisis.activo_id(), "ocupado": analisis.ocupado(), "analisis": analisis.listar()}


@app.get("/api/analisis/fuentes")
def analisis_fuentes(s: Sesion = Depends(requiere("cargar_datos"))):
    return {"carpeta": str(config.datos()), "archivos": analisis.fuentes()}


@app.get("/api/analisis/{i}")
def analisis_uno(i: str, s: Sesion = Depends(requiere("estrategico"))):
    try:
        return analisis.obtener(i)
    except KeyError:
        raise HTTPException(404, "No existe ese análisis.")


def _reportes() -> list[str]:
    return list(denuncias.contactos_reportados())


@app.post("/api/analisis/desde-carpeta")
def analisis_carpeta(fw_origen: str = Form(...), fw: str = Form(...), med_origen: str = Form(...), med: str = Form(...),
                     citas_origen: str = Form(""), citas: str = Form(""),
                     s: Sesion = Depends(requiere("cargar_datos"))):
    try:
        rutas = [analisis.resolver_fuente(fw_origen, fw), analisis.resolver_fuente(med_origen, med),
                 analisis.resolver_fuente(citas_origen, citas) if citas else None]
        i = analisis.nuevo(s.nombre)
        meta = analisis.lanzar(i, s.nombre, rutas[0], rutas[1], rutas[2], _reportes(), _al_terminar)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))
    estado.bitacora(s.nombre, _rol(s), "Análisis iniciado", i, f"{analisis.mostrar(fw)} y {analisis.mostrar(med)}" +
                    (f" con {analisis.mostrar(citas)}" if citas else ""))
    return meta


@app.post("/api/analisis/subir")
def analisis_subir(firewall: UploadFile = File(...), sistema_medico: UploadFile = File(...),
                   agendamiento: UploadFile | None = File(None), s: Sesion = Depends(requiere("cargar_datos"))):
    for f in (firewall, sistema_medico, agendamiento):
        if f and not (f.filename or "").lower().endswith(".csv"):
            raise HTTPException(400, "Solo se aceptan archivos CSV.")
    if analisis.ocupado():
        raise HTTPException(400, "Ya hay un análisis en curso. Espera a que termine.")
    i = analisis.nuevo(s.nombre)
    try:
        fw = analisis.guardar_subida(i, "firewall", firewall.file)
        med = analisis.guardar_subida(i, "sistema_medico", sistema_medico.file)
        citas = analisis.guardar_subida(i, "agendamiento", agendamiento.file) if agendamiento else None
        meta = analisis.lanzar(i, s.nombre, fw, med, citas, _reportes(), _al_terminar)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))
    nombres = [analisis.mostrar(f.filename or "") if f else None for f in (firewall, sistema_medico, agendamiento)]
    meta["archivos"] = dict(zip(("firewall", "sistema_medico", "agendamiento"), nombres, strict=False))
    estado.bitacora(s.nombre, _rol(s), "Análisis iniciado", i, f"Archivos subidos: {nombres[0]} y {nombres[1]}")
    return meta


@app.post("/api/analisis/{i}/activar")
def analisis_activar(i: str, s: Sesion = Depends(requiere("cargar_datos"))):
    try:
        analisis.activar(i)
    except KeyError:
        raise HTTPException(404, "No existe ese análisis.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    estado.bitacora(s.nombre, _rol(s), "Análisis activado", i, "La consola muestra este análisis")
    return {"ok": True}


# ---------- estratégico ----------
@app.get("/api/ejecutivo")
def vista_ejecutiva(s: Sesion = Depends(requiere("estrategico"))):
    return ejecutivo.armar()


@app.get("/api/tablero")
def tablero(s: Sesion = Depends(requiere("estrategico"))):
    """Las cinco pestañas del tablero: resumen, amenazas internas, citas y fraude, externas e impacto en el negocio."""
    t = impacto.tablero()
    t["baseDatos"] = dict(bd.ULTIMO_MOTOR)
    return t


@app.get("/api/resumen")
def resumen(s: Sesion = Depends(requiere("estrategico"))):
    r = datos.consola("resumen")
    r["controlesConBrecha"] = sum(1 for c in _fijo("controles") if c["estado"] == "Brecha")
    r["archivos"] = datos.motor("resumen_motor.json", {}).get("archivos", {})
    r["analisis"] = analisis.activo_id()
    return r


@app.get("/api/riesgos")
def matriz(s: Sesion = Depends(requiere("estrategico"))):
    return {"riesgos": riesgos.calcular(), "controles": _fijo("controles"), "analisis": analisis.activo_id()}


@app.get("/api/threatpulse")
def tendencias(s: Sesion = Depends(requiere("estrategico"))):
    from . import threatpulse  # cambio confinado a este endpoint (S6c/T7)
    d = _fijo("tendencias")
    try:
        reales, meta = osint.tendencias_reales()                # solo lee la caché: jamás hace red
    except Exception:                                           # caché ilegible → el feed fijo manda
        reales, meta = [], None
    if not reales:                                              # sin datos reales: respuesta idéntica a hoy
        return {**d, "tendencias": threatpulse.evaluar(d["tendencias"])}
    fijas = [{**t, "sello": "simulado"} for t in d["tendencias"]]
    nota = (d["nota"] + f" Se integraron {meta['items']} lecturas reales de {meta['fuentes']} "
            "fuentes públicas con sello «real»; el resto sigue siendo hipótesis.")
    return {**d, "nota": nota, "tendencias": threatpulse.evaluar(fijas + reales), "osint": meta}


@app.post("/api/threatpulse/actualizar")
def threatpulse_actualizar(s: Sesion = Depends(requiere("tecnico"))):
    # Sincronización manual (S13): nada corre en import/startup y cada fuente falla aislada.
    try:
        r = osint.sincronizar()
    except Exception:
        raise HTTPException(500, "No se pudo actualizar desde las fuentes públicas. Inténtalo más tarde.")
    estado.bitacora(s.nombre, _rol(s), "OSINT actualizado", "THREATPULSE",
                    f"{r['actualizadas']} fuentes al día, {r['fallidas']} fallidas de {r['totales']}")
    return r


# ---------- operativo ----------
@app.get("/api/casos")
def casos(s: Sesion = Depends(requiere("operativo"))):
    campos = ["id", "titulo", "tipo", "gravedad", "inicio", "duracion", "ipOrigen", "cuenta", "protocolo", "estado",
              "detectadoPor", "alerta", "resumen"]
    return [{k: c[k] for k in campos} for c in datos.casos()]


@app.get("/api/casos/{caso_id}")
def caso(caso_id: str = ID_CASO, s: Sesion = Depends(requiere("operativo"))):
    return datos.caso(caso_id)


class Decision(BaseModel):
    estado: Literal["confirmado", "descartado"]
    motivo: str = Field(min_length=10, max_length=500)


@app.post("/api/casos/{caso_id}/decision")
def decidir(d: Decision, caso_id: str = ID_CASO, s: Sesion = Depends(requiere("decidir"))):
    datos.caso(caso_id)
    reg = estado.agregar("decisiones", {"clave": datos.clave_decision(caso_id), "casoId": caso_id, "estado": d.estado,
                                        "motivo": d.motivo.strip(), "analista": s.nombre, "fecha": estado.ahora()})
    estado.bitacora(s.nombre, _rol(s), f"Caso {d.estado}", caso_id, d.motivo.strip())
    return reg


@app.get("/api/serie")
def serie(s: Sesion = Depends(requiere("operativo"))):
    return datos.consola("serie")


@app.get("/api/anomalias")
def anomalias(fuente: Literal["firewall", "sistema_medico"] = Query(...), s: Sesion = Depends(requiere("operativo"))):
    return datos.consola(f"anomalias_{fuente}")


@app.get("/api/grafo")
def grafo(s: Sesion = Depends(requiere("operativo"))):
    return datos.consola("grafo")


@app.get("/api/agendamiento")
def agenda(s: Sesion = Depends(requiere("operativo"))):
    a = datos.agendamiento()
    if a is None:
        raise HTTPException(409, "Este análisis no incluyó registros del chatbot de citas.")
    return a


class Revision(BaseModel):
    decision: Literal["en_revision", "explicado", "descartado", "confirmado"]
    nota: str = Field(min_length=10, max_length=500)


@app.post("/api/agendamiento/{case_id}/revision")
def revisar_agenda(r: Revision, case_id: str = Path(..., pattern=r"^AG-[0-9A-F]{6}$"),
                   s: Sesion = Depends(requiere("decidir"))):
    a = datos.agendamiento()
    if not a or not any(c["case_id"] == case_id for c in a["casos"]):
        raise HTTPException(404, "No existe ese origen en el análisis activo.")
    reg = estado.agregar("revisiones_agenda", {"clave": f"{analisis.activo_id()}:{case_id}", "decision": r.decision,
                                               "nota": r.nota.strip(), "analista": s.nombre, "fecha": estado.ahora()})
    estado.bitacora(s.nombre, _rol(s), "Revisión de agendamiento", case_id, r.nota.strip())
    return reg


class PedidoReid(BaseModel):
    seudonimo: str = Field(pattern=r"^[A-Z]{1,3}-[0-9A-F]{6}$")
    motivo: str = Field(min_length=15, max_length=500)


@app.post("/api/reidentificar")
def reidentificar(p: PedidoReid, s: Sesion = Depends(requiere("reidentificar"))):
    d = analisis.restringido_activo()
    tabla = d / "tabla_reidentificacion.csv" if d else None
    if not tabla or not tabla.exists():
        raise HTTPException(409, "No hay tabla de reidentificación para el análisis activo.")
    with open(tabla, encoding="utf-8") as f:
        nombre = next((r["valor_real"] for r in csv.DictReader(f) if r["seudonimo"] == p.seudonimo), None)
    if nombre is None:
        raise HTTPException(404, f"No existe el seudónimo {p.seudonimo}.")
    e = estado.bitacora(s.nombre, _rol(s), "Reidentificación", p.seudonimo, p.motivo.strip())
    return {"seudonimo": p.seudonimo, "nombre": nombre, "registradoEn": e["fecha"]}


# ---------- denuncias ----------
class DenunciaPublica(BaseModel):
    tipo: Literal["venta_de_citas", "pedido_de_datos", "enlace_sospechoso", "uso_de_mis_datos", "otro"]
    descripcion: str = Field(default="", max_length=1500)
    cuando: str = Field(default="", max_length=40)
    medio: Literal["", "llamada", "whatsapp", "mensaje", "correo", "en_persona", "redes_sociales"] = ""
    contacto_sospechoso: str = Field(default="", max_length=80)
    enlace: str = Field(default="", max_length=500)
    responder_a: str = Field(default="", max_length=120)
    acepta_privacidad: bool


@app.post("/api/publico/denuncias")
def denunciar(d: DenunciaPublica, request: Request):
    if not d.acepta_privacidad:
        raise HTTPException(400, "Para enviar la denuncia necesitamos que aceptes el aviso de privacidad.")
    denuncias.limitar(request.client.host if request.client else "local")
    r = denuncias.crear(d.model_dump())
    return {"codigo": r["codigo"], "fecha": r["fecha"]}


@app.get("/api/publico/denuncias/{codigo}")
def seguimiento(codigo: str = Path(..., pattern=r"^DN-[0-9A-F]{6}$")):
    return denuncias.publica(codigo)


@app.get("/api/denuncias")
def bandeja(s: Sesion = Depends(requiere("ver_denuncias"))):
    vinculos = {}
    try:
        a = datos.agendamiento()
        for c in (a or {}).get("casos", []):
            for cod in c.get("denuncias_vinculadas", []):
                vinculos.setdefault(cod, []).append(c["case_id"])
    except HTTPException:
        pass
    ver_contacto = "gestionar_denuncias" in s.permisos
    out = []
    for d in denuncias.todas():
        x = {k: v for k, v in d.items() if k != "contacto_sospechoso_ref"}
        if not ver_contacto:
            x["responder_a"] = "••••" if d["responder_a"] else ""
        x["origenesAgendamiento"] = vinculos.get(d["codigo"], [])
        out.append(x)
    return out


class Gestion(BaseModel):
    estado: Literal["recibida", "en_revision", "atendida", "descartada"]
    respuesta_publica: str = Field(default="", max_length=600)
    nota_interna: str = Field(default="", max_length=600)


@app.post("/api/denuncias/{codigo}/gestion")
def gestionar(g: Gestion, codigo: str = Path(..., pattern=r"^DN-[0-9A-F]{6}$"),
              s: Sesion = Depends(requiere("gestionar_denuncias"))):
    d = denuncias.gestionar(codigo, g.estado, g.respuesta_publica.strip(), g.nota_interna.strip(), s.nombre, _rol(s))
    return {k: v for k, v in d.items() if k != "contacto_sospechoso_ref"}


# ---------- técnico ----------
@app.get("/api/inteligencia")
def inteligencia(s: Sesion = Depends(requiere("tecnico"))):
    return datos.consola("inteligencia")


# ---------- exportes de difusión (S10/T12) ----------
TABLAS_POWERBI_ESTADO = {
    "riesgos.csv": ["id", "nombre", "probabilidad", "impacto", "nivel", "tratamiento", "evidencia", "casos"],
    "controles.csv": ["id", "nombre", "hallazgo", "estado"],
    "decisiones.csv": ["casoId", "estado", "motivo", "analista", "fecha"],
}


def _csv_tabla(columnas: list[str], filas: list[dict]) -> str:
    b = io.StringIO()
    w = csv.DictWriter(b, fieldnames=columnas, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for f in filas:
        w.writerow({c: "" if f.get(c) is None else
                    ("; ".join(str(x) for x in f[c]) if isinstance(f.get(c), list) else f[c]) for c in columnas})
    return b.getvalue()


@app.get("/api/exportes/powerbi")
def exportar_powerbi(s: Sesion = Depends(requiere("tecnico"))):
    # datos._salidas resuelve el análisis activo o responde 409, igual que el resto de la consola.
    d = datos._salidas() / "powerbi"
    if not d.is_dir():
        raise HTTPException(409, "El análisis activo no tiene esta información.")
    tablas = {f.name: f.read_text(encoding="utf-8") for f in sorted(d.glob("*.csv"))}
    tablas["riesgos.csv"] = _csv_tabla(TABLAS_POWERBI_ESTADO["riesgos.csv"], riesgos.calcular())
    tablas["controles.csv"] = _csv_tabla(TABLAS_POWERBI_ESTADO["controles.csv"], _fijo("controles"))
    tablas["decisiones.csv"] = _csv_tabla(TABLAS_POWERBI_ESTADO["decisiones.csv"], estado.leer("decisiones"))
    libro = exportes_apps.powerbi_xlsx(tablas)
    estado.bitacora(s.nombre, _rol(s), "Exporte descargado", "POWERBI", "Libro de Excel para Power BI")
    return Response(libro, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="sentinel_powerbi.xlsx"'})


@app.get("/api/exportes/maltego")
def exportar_maltego(s: Sesion = Depends(requiere("tecnico"))):
    grafo = datos.consola("grafo")
    estado.bitacora(s.nombre, _rol(s), "Exporte descargado", "MALTEGO", "Grafo .mtgx")
    return Response(exportes_apps.maltego_mtgx(grafo), media_type="application/octet-stream",
                    headers={"Content-Disposition": 'attachment; filename="sentinel_maltego.mtgx"'})


# Informes HTML autocontenidos (S14/T16): se registran antes de /api/exportes/{tipo}
# para que la ruta con parámetro no se los coma, igual que powerbi/maltego.
@app.get("/api/exportes/gerencial")
def exportar_gerencial(s: Sesion = Depends(requiere("estrategico"))):
    pdf = informe_pdf.generar_gerencial()
    estado.bitacora(s.nombre, _rol(s), "Exporte descargado", "GERENCIAL", "Informe gerencial PDF")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="informe_gerencial.pdf"'})


@app.get("/api/exportes/presentacion")
def exportar_presentacion(s: Sesion = Depends(requiere("tecnico"))):
    html = reportes.informe_presentacion(reportes.datos_desde_estado())
    estado.bitacora(s.nombre, _rol(s), "Exporte descargado", "PRESENTACION", "Informe de presentación HTML")
    return Response(html, media_type="text/html",
                    headers={"Content-Disposition": 'attachment; filename="presentacion_soc.html"'})


@app.get("/api/exportes/informe-pdf")
def exportar_informe_pdf(s: Sesion = Depends(requiere("estrategico"))):
    """Reporte de inteligencia de amenazas con los 8 entregables del reto, en PDF."""
    pdf = informe_pdf.generar()
    estado.bitacora(s.nombre, _rol(s), "Exporte descargado", "INFORME PDF", "Reporte de inteligencia (8 entregables)")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="reporte_inteligencia_sentinel.pdf"'})


# Ruta con parámetro al final: registra la de {tipo} después de las concretas (powerbi, maltego).
@app.get("/api/exportes/{tipo}")
def exportar(tipo: Literal["stix", "misp", "sigma"], s: Sesion = Depends(requiere("tecnico"))):
    i = datos.consola("inteligencia")
    estado.bitacora(s.nombre, _rol(s), "Exporte descargado", tipo.upper(), "")
    if tipo == "sigma":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for r in i["sigma"]:
                z.writestr(f"{r['id']}_{r['titulo'].lower().replace(' ', '_')}.yml", r["yaml"])
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="reglas_sigma.zip"'})
    return Response(i[tipo], media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="sentinel_{tipo}.json"'})


# ---------- realimentación (S9/T18) ----------
class Recalibrar(BaseModel):
    motivo: str = Field(min_length=10, max_length=500)


@app.get("/api/realimentacion")
def realimentacion_metricas(s: Sesion = Depends(requiere("tecnico"))):
    return realimentacion.resumen()


@app.post("/api/realimentacion/recalibrar")
def realimentacion_recalibrar(r: Recalibrar, s: Sesion = Depends(requiere("tecnico"))):
    # Nunca corre solo: es la única vía que cambia umbrales y siempre deja la marca en bitácora.
    return realimentacion.recalibrar(motivo=r.motivo.strip(), actor=s.nombre, rol=_rol(s))


# ---------- listas de comparación (S15/T17b) ----------
# Permisos: seguridad.py no tiene un permiso de gestión de listas para el rol TI; el que TI
# ya tiene para aplicar indicadores en sus sistemas es «tecnico» (reportado en el handoff).
# Las altas, bajas, solicitudes y resoluciones las audita el propio repositorio (app.listas).
class IndicadorLista(BaseModel):
    tipo: Literal["blanca", "negra"]
    valor: str = Field(min_length=1, max_length=300)
    etiqueta: str = Field(default="", max_length=200)


class SolicitudLista(BaseModel):
    tipo: Literal["blanca", "negra"]
    valor: str = Field(min_length=1, max_length=300)
    justificacion: str = Field(min_length=1, max_length=1000)
    fuente: str = Field(default="", max_length=200)


class ResolucionLista(BaseModel):
    aprobar: bool
    motivo: str = Field(min_length=10, max_length=500)


@app.get("/api/listas/indicadores")
def listas_indicadores(s: Sesion = Depends(requiere("tecnico"))):
    return listas.listar()


@app.post("/api/listas/indicadores")
def listas_alta_indicador(i: IndicadorLista, s: Sesion = Depends(requiere("tecnico"))):
    try:
        return listas.añadir(i.tipo, i.valor, i.etiqueta, quien=s.nombre)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/listas/indicadores/{id}")
def listas_baja_indicador(id: int = Path(..., ge=1), s: Sesion = Depends(requiere("tecnico"))):
    try:
        return listas.quitar(id, quien=s.nombre)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/listas/solicitudes")
def listas_bandeja(estado_solicitud: Literal["PENDIENTE", "APROBADA", "RECHAZADA"] | None =
                   Query(None, alias="estado"), s: Sesion = Depends(requiere("tecnico"))):
    return listas.solicitudes(estado_solicitud)


@app.post("/api/listas/solicitudes")
def listas_solicitar(p: SolicitudLista, s: Sesion = Depends(requiere("tecnico"))):
    try:
        return listas.solicitar(p.tipo, p.valor, p.justificacion, p.fuente, quien=s.nombre)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/listas/solicitudes/{id}/resolver")
def listas_resolver(r: ResolucionLista, id: int = Path(..., ge=1),
                    s: Sesion = Depends(requiere("tecnico"))):
    try:
        return listas.resolver(id, r.aprobar, r.motivo, s.nombre)
    except ValueError as e:
        codigo = 404 if "desconocida" in str(e) else 400
        raise HTTPException(codigo, str(e))


# ---------- tickets de reglas (SOC → TI) ----------
class Ticket(BaseModel):
    tipo: Literal["nueva", "ajustar", "desactivar", "indicador"]
    regla: str = Field(min_length=2, max_length=120)
    titulo: str = Field(min_length=5, max_length=140)
    descripcion: str = Field(min_length=15, max_length=1500)
    prioridad: Literal["alta", "media", "baja"]
    caso: str = Field(default="", max_length=20)


class GestionTicket(BaseModel):
    estado: Literal["en_progreso", "aplicado", "rechazado"]
    respuesta: str = Field(min_length=10, max_length=800)


def _puede_tickets(s: Sesion) -> None:
    if not {"pedir_reglas", "gestionar_reglas"} & set(s.permisos):
        estado.bitacora(s.nombre, _rol(s), "Acceso denegado", "tickets", "Intentó abrir los tickets de reglas")
        raise HTTPException(403, "Tu rol no puede ver los tickets de reglas.")


@app.get("/api/tickets")
def tickets_lista(s: Sesion = Depends(seguridad.sesion_actual)):
    _puede_tickets(s)
    reglas = []
    try:
        reglas = [f"{r['id']} {r['titulo']}" for r in datos.consola("inteligencia").get("sigma", [])]
    except HTTPException:
        pass
    reglas += [f"Archivo rules/{f.name}" for f in sorted((config.PROYECTO / "rules").glob("*.yml"))]
    return {"tickets": tickets.todos(), "reglas": reglas, "tipos": tickets.TIPOS, "estados": tickets.ESTADOS}


@app.post("/api/tickets")
def tickets_crear(t: Ticket, s: Sesion = Depends(requiere("pedir_reglas"))):
    return tickets.crear(t.model_dump(), s.nombre, _rol(s))


@app.post("/api/tickets/{codigo}/gestion")
def tickets_gestionar(g: GestionTicket, codigo: str = Path(..., pattern=r"^TK-[0-9A-F]{6}$"),
                      s: Sesion = Depends(requiere("gestionar_reglas"))):
    return tickets.gestionar(codigo, g.estado, g.respuesta.strip(), s.nombre, _rol(s))


# ---------- estado de CI (solo equipo de TI) ----------
@app.get("/api/ci/estado")
def ci_estado(s: Sesion = Depends(requiere("ver_ci"))):
    return ci.estado()


# ---------- personal de salud ----------
class Enlace(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


@app.post("/api/verificar/enlace")
def verificar_enlace(e: Enlace, s: Sesion = Depends(requiere("verificar"))):
    return verificar.enlace(e.url)


@app.post("/api/verificar/imagen")
async def verificar_imagen(imagen: UploadFile = File(...), s: Sesion = Depends(requiere("verificar"))):
    contenido = await imagen.read(config.MAX_IMAGEN + 1)
    if len(contenido) > config.MAX_IMAGEN:
        raise HTTPException(413, "La imagen supera los 15 MB.")
    return verificar.imagen(imagen.filename or "imagen", contenido)


class Reporte(BaseModel):
    entrada: str = Field(max_length=500)
    veredicto: Literal["seguro", "sospechoso", "malicioso"]
    comentario: str = Field(default="", max_length=600)


@app.post("/api/verificar/reportar")
def reportar(r: Reporte, s: Sesion = Depends(requiere("verificar"))):
    d = denuncias.crear({"tipo": "contenido_reportado", "descripcion": r.comentario,
                         "enlace": r.entrada if r.entrada.startswith(("http", "www")) else "",
                         "actor": s.nombre}, origen="personal de salud")
    return {"codigo": d["codigo"], "fecha": d["fecha"]}


# ---------- auditoría ----------
@app.get("/api/bitacora")
def bitacora(s: Sesion = Depends(requiere("auditar"))):
    return list(reversed(estado.leer("bitacora")))


def _fijo(nombre: str):
    return json.loads((config.FIJOS / f"{nombre}.json").read_text(encoding="utf-8"))


# ---------- consola compilada (npm run build) ----------
if config.WEB_DIST.exists():
    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        if ruta == "api" or ruta.startswith("api/"):
            raise HTTPException(404, "Ruta de la API no encontrada.")
        f = (config.WEB_DIST / ruta).resolve()
        if ruta and f.is_file() and config.WEB_DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(config.WEB_DIST / "index.html")
