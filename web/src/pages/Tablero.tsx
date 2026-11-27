import { ArrowUpRight, Database, Download, FileText, Maximize2, ShieldAlert, X } from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  LabelList,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api/client'
import type { Gravedad as TGravedad, HistoriaItem } from '../api/types'
import { Pulso } from '../components/Pulso'
import { Carga, Gravedad } from '../components/ui'
import { duracion, enPalabras, ESTADO_CASO, ESTADO_DENUNCIA, fFecha, fMesTitulo, num } from '../lib/format'
import { useSesion } from '../lib/sesion'
import { useApi } from '../lib/useApi'

// ---------- tipos del endpoint /api/tablero ----------
type Nivel = TGravedad
interface Amenaza {
  origen: string
  titulo: string
  gravedad: Nivel
  riesgos: string[]
  dimensiones: string[]
  ruta: string
  fecha: string
}
interface Dimension {
  id: string
  nombre: string
  pregunta: string
  exposicion: number
  nivel: Nivel
  riesgos: { riesgo: string; nombre: string; probabilidad: number; impacto: number; exposicion: number }[]
}
interface RiesgoNegocio {
  id: string
  nombre: string
  probabilidad: number
  impacto: number
  nivel: number
  proceso: string
  escenario: string
  operativa: string
  legal: string
  reputacional: string
  financiera: string
  decision: string
  impactos: Record<string, number>
}
interface DatosTablero {
  periodo: { desde: string; hasta: string }
  registros: number
  minutos: number
  indice: number
  baseDatos: { motor: string; detalle: string }
  resumen: {
    incidentes: number
    criticos: number
    pendientes: number
    confirmados: number
    extraccionesExitosas: number
    jornadasManuales: number
    historia: HistoriaItem[]
    pulso: { ts: string; v: number }[]
    denuncias: { recibidas: number; abiertas: number }
    agendamiento: { origenesEnRevision: number; citasAConfirmar: number; reservas: number; explicadosLegitimos: number } | null
  }
  amenazas: Amenaza[]
  internas: {
    casos: { id: string; titulo: string; gravedad: Nivel; inicio: string; estado: 'pendiente' | 'confirmado' | 'descartado'; ipOrigen: string; ambas: boolean }[]
    mitre: { tecnica: string; casos: number }[]
    porDia: { dia: string; fallidos: number; ssh: number; transferencias: number }[]
    activos: { activo: string; eventos: number }[]
    anomalias: Record<'firewall' | 'sistema_medico', { total: number; sospechosas: number; sinCaso: number }>
  }
  citas: {
    agenda: {
      resumen: { reservas: number; sesiones: number; puntos: number; estados: Record<string, number>; citas_en_revision: number }
      top: { case_id: string; status: string; risk_score: number; confidence: number; pattern_ids: string[]; pacientes: number; reservas: number; denuncias: number }[]
      evaluacion: { matriz: { vp: number; fp: number; fn: number; vn: number }; nota: string } | null
    } | null
    denunciasTipo: { tipo: string; n: number }[]
    denunciasEstado: Record<string, number>
    verificar: number
  }
  externas: {
    tendencias: { id: string; titulo: string; fuente: string; fecha: string; sello?: string; kev?: boolean; cvss?: number | null; exposicionLocal: string; tecnicas: string[]; score: number }[]
    porFuente: Record<string, number>
    reales: number
  }
  negocio: { dimensiones: Dimension[]; riesgos: RiesgoNegocio[]; indice: number; nota: string }
}

const COLOR: Record<Nivel, string> = {
  critica: 'var(--critica)',
  alta: 'var(--alta-relleno)',
  media: 'var(--media)',
  baja: 'var(--baja)',
}
const zona = (n: number): Nivel => (n >= 20 ? 'critica' : n >= 12 ? 'alta' : n >= 6 ? 'media' : 'baja')
const DIM_CORTO: Record<string, string> = {
  atencion: 'Atención',
  datos: 'Datos/LOPDP',
  citas: 'Citas',
  confianza: 'Reputación',
  costos: 'Costos',
}
const PESTANAS = [
  { id: 'resumen', nombre: 'Resumen' },
  { id: 'internas', nombre: 'Amenazas internas' },
  { id: 'citas', nombre: 'Citas y fraude' },
  { id: 'externas', nombre: 'Amenazas externas' },
  { id: 'negocio', nombre: 'Impacto en el negocio' },
] as const
type Pestana = (typeof PESTANAS)[number]['id']

export default function Tablero() {
  const { st, reintentar } = useApi(() => api.tablero() as Promise<DatosTablero>)
  return (
    <Carga st={st} reintentar={reintentar} filas={8}>
      {(d) => <Vista d={d} />}
    </Carga>
  )
}

// ---------- tarjeta que se expande ----------
interface TarjetaProps {
  titulo: string
  dato?: ReactNode
  area: string
  children: ReactNode
  grande?: ReactNode
  ruta?: string
  tono?: Nivel
}

function Tarjeta({ titulo, dato, area, children, grande, ruta, tono }: TarjetaProps) {
  const [abierta, setAbierta] = useState(false)
  useEffect(() => {
    if (!abierta) return
    const cerrar = (e: KeyboardEvent) => e.key === 'Escape' && setAbierta(false)
    window.addEventListener('keydown', cerrar)
    return () => window.removeEventListener('keydown', cerrar)
  }, [abierta])
  return (
    <>
      <section className={`tj ${tono ? `tj--${tono}` : ''}`} style={{ gridArea: area }}>
        <header className="tj__cab">
          <h2>{titulo}</h2>
          {dato && <span className="tj__dato">{dato}</span>}
          <button className="tj__ampliar" onClick={() => setAbierta(true)} aria-label={`Ampliar ${titulo}`} title="Ampliar">
            <Maximize2 size={15} />
          </button>
        </header>
        <div className="tj__cuerpo">{children}</div>
      </section>
      {abierta && (
        <div className="tj-modal" role="dialog" aria-modal="true" aria-label={titulo} onClick={() => setAbierta(false)}>
          <div className="tj-modal__caja" onClick={(e) => e.stopPropagation()}>
            <header className="tj-modal__cab">
              <h2>{titulo}</h2>
              {ruta && (
                <Link to={ruta} className="boton boton--secundario boton--chico">
                  Ir a la sección <ArrowUpRight size={14} aria-hidden />
                </Link>
              )}
              <button className="tj__ampliar" onClick={() => setAbierta(false)} aria-label="Cerrar">
                <X size={18} />
              </button>
            </header>
            <div className="tj-modal__cuerpo">{grande ?? children}</div>
          </div>
        </div>
      )}
    </>
  )
}

// ---------- vista ----------
function Vista({ d }: { d: DatosTablero }) {
  const [p, setP] = useState<Pestana>(() => {
    try {
      return (sessionStorage.getItem('sentinel.tablero') as Pestana) || 'resumen'
    } catch {
      return 'resumen'
    }
  })
  const [error, setError] = useState('')
  const [bajando, setBajando] = useState('')
  const elegir = (x: Pestana) => {
    setP(x)
    try {
      sessionStorage.setItem('sentinel.tablero', x)
    } catch {
      /* sin almacenamiento */
    }
  }
  const bajar = async (tipo: 'inteligencia' | 'gerencial') => {
    setBajando(tipo)
    setError('')
    try {
      await (tipo === 'inteligencia' ? api.informePdf() : api.exportar('gerencial'))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo generar el PDF.')
    } finally {
      setBajando('')
    }
  }
  const cuenta = (o: string) => d.amenazas.filter((a) => a.origen === o || (o === 'citas' && /Citas|Denuncias|Verificar/.test(a.origen))).length

  return (
    <div className="tablero">
      <div className="tablero__cab">
        <Indice valor={d.indice} />
        <div className="tablero__titulo">
          <h1>{fMesTitulo(d.periodo.desde)}</h1>
          <p>
            {enPalabras(d.registros)} registros revisados en {duracion(d.minutos)} · {d.amenazas.length} amenazas activas conectadas al negocio
          </p>
        </div>
        <div className="tablero__acciones">
          <span className={`bd bd--${d.baseDatos.motor}`} title={d.baseDatos.detalle}>
            <Database size={13} aria-hidden /> {d.baseDatos.motor === 'postgresql' ? 'PostgreSQL' : 'SQLite (respaldo)'}
          </span>
          <button className="boton boton--chico" onClick={() => bajar('inteligencia')} disabled={!!bajando}>
            <FileText size={15} aria-hidden /> {bajando === 'inteligencia' ? 'Generando…' : 'PDF inteligencia'}
          </button>
          <button className="boton boton--secundario boton--chico" onClick={() => bajar('gerencial')} disabled={!!bajando}>
            <Download size={15} aria-hidden /> {bajando === 'gerencial' ? 'Generando…' : 'PDF gerencial'}
          </button>
        </div>
      </div>
      {error && <p className="error-linea">{error}</p>}

      <nav className="tablero__tabs" role="tablist" aria-label="Pestañas del tablero">
        {PESTANAS.map((t) => {
          const n =
            t.id === 'internas'
              ? cuenta('Casos') + cuenta('Anomalías')
              : t.id === 'citas'
                ? cuenta('citas')
                : t.id === 'externas'
                  ? cuenta('Amenazas externas')
                  : t.id === 'resumen'
                    ? d.amenazas.length
                    : d.negocio.dimensiones.filter((x) => x.nivel === 'critica').length
          return (
            <button key={t.id} role="tab" aria-selected={p === t.id} onClick={() => elegir(t.id)}>
              {t.nombre}
              {n > 0 && <span className="tablero__n">{n}</span>}
            </button>
          )
        })}
      </nav>

      <div className={`tablero__grid tablero__grid--${p}`} role="tabpanel">
        {p === 'resumen' && <Resumen d={d} />}
        {p === 'internas' && <Internas d={d} />}
        {p === 'citas' && <Citas d={d} />}
        {p === 'externas' && <Externas d={d} />}
        {p === 'negocio' && <Negocio d={d} />}
      </div>
    </div>
  )
}

function Indice({ valor }: { valor: number }) {
  const t = valor >= 80 ? 'critica' : valor >= 48 ? 'alta' : valor >= 24 ? 'media' : 'baja'
  const ang = Math.PI * (1 - valor / 100)
  const x = 50 + 40 * Math.cos(ang)
  const y = 50 - 40 * Math.sin(ang)
  return (
    <div className="indice" title="Índice de riesgo: promedio del nivel de los 5 riesgos más altos de la matriz, de 0 a 100">
      <svg viewBox="0 0 100 58" aria-hidden>
        <path d="M10 50 A40 40 0 0 1 90 50" className="indice__pista" />
        <path d={`M10 50 A40 40 0 0 1 ${x.toFixed(1)} ${y.toFixed(1)}`} className={`indice__valor indice__valor--${t}`} />
      </svg>
      <div className="indice__num">
        <strong>{valor}</strong>
        <span>índice de riesgo</span>
      </div>
    </div>
  )
}

function ListaAmenazas({ items, max }: { items: Amenaza[]; max?: number }) {
  const ir = useNavigate()
  return (
    <ul className="amenazas">
      {items.slice(0, max ?? items.length).map((a, i) => (
        <li key={i}>
          <button onClick={() => ir(a.ruta)} className={`amenaza amenaza--${a.gravedad}`}>
            <span className="amenaza__origen">{a.origen}</span>
            <span className="amenaza__titulo">{a.titulo}</span>
            <span className="amenaza__dims">
              {a.dimensiones.map((x) => (
                <span key={x} className="dim">
                  {DIM_CORTO[x] ?? x}
                </span>
              ))}
              <span className="amenaza__r">{a.riesgos.join(' ')}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function BarrasDim({ dims, grande }: { dims: Dimension[]; grande?: boolean }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={dims} layout="vertical" margin={{ left: 0, right: 30, top: 2, bottom: 2 }}>
        <XAxis type="number" domain={[0, 25]} hide />
        <YAxis type="category" dataKey="nombre" width={grande ? 190 : 150} tick={{ fontSize: grande ? 14 : 12, fill: 'var(--tinta-2)' }} axisLine={false} tickLine={false} />
        <Tooltip formatter={(v) => [`${v} de 25`, 'Exposición']} cursor={{ fill: 'var(--neutro-fondo)' }} />
        <Bar dataKey="exposicion" radius={[0, 4, 4, 0]} barSize={grande ? 26 : 15} isAnimationActive={false}>
          {dims.map((x) => (
            <Cell key={x.id} fill={COLOR[x.nivel]} />
          ))}
          <LabelList dataKey="exposicion" position="right" style={{ fontWeight: 700, fontSize: grande ? 14 : 12, fill: 'var(--tinta)' }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ---------- pestañas ----------
function Resumen({ d }: { d: DatosTablero }) {
  const ir = useNavigate()
  const { puede } = useSesion()
  const r = d.resumen
  const pend = r.historia.filter((h) => h.estado === 'pendiente')
  return (
    <>
      <Tarjeta
        titulo="Pulso del mes"
        dato={`${r.incidentes} incidentes`}
        area="a"
        ruta="/linea"
        grande={
          <>
            <Pulso pulso={r.pulso} historia={r.historia} onElegir={puede('operativo') ? (id) => ir(`/casos/${id}`) : undefined} />
            <TablaHistoria h={r.historia} />
          </>
        }
      >
        <Pulso pulso={r.pulso} historia={r.historia} onElegir={puede('operativo') ? (id) => ir(`/casos/${id}`) : undefined} />
        <ul className="pulso-chips">
          {r.historia.map((h) => (
            <li key={h.id} className={`pulso-chips__i pulso-chips__i--${h.gravedad}`}>
              <Link to={`/casos/${h.id}`}>
                <b>{fFecha(h.inicio)}</b> {h.titulo}
              </Link>
            </li>
          ))}
        </ul>
      </Tarjeta>
      <Tarjeta titulo="Amenazas de todas las secciones" dato={`${d.amenazas.length}`} area="b" grande={<ListaAmenazas items={d.amenazas} />}>
        <ListaAmenazas items={d.amenazas} max={7} />
      </Tarjeta>
      <Tarjeta
        titulo="Impacto en el negocio"
        area="c"
        ruta="/riesgos"
        grande={<div style={{ height: 360 }}><BarrasDim dims={d.negocio.dimensiones} grande /></div>}
      >
        <BarrasDim dims={d.negocio.dimensiones} />
      </Tarjeta>
      <Tarjeta titulo={`Para decidir (${pend.length})`} area="d" ruta="/casos" grande={<TablaHistoria h={r.historia} />}>
        <div className="cifras-mini">
          <div className="cifra-mini cifra-mini--critica">
            <strong>{r.criticos}</strong>
            <span>críticos</span>
          </div>
          <div className="cifra-mini cifra-mini--critica">
            <strong>{r.extraccionesExitosas}</strong>
            <span>veces salió información</span>
          </div>
          <div className="cifra-mini">
            <strong>{r.agendamiento?.citasAConfirmar ?? 0}</strong>
            <span>citas a confirmar</span>
          </div>
          <div className="cifra-mini">
            <strong>{r.denuncias.abiertas}</strong>
            <span>denuncias abiertas</span>
          </div>
        </div>
        {r.extraccionesExitosas > 0 && (
          <p className="lopdp">
            <ShieldAlert size={15} aria-hidden /> Evaluar notificación LOPDP
          </p>
        )}
      </Tarjeta>
    </>
  )
}

function TablaHistoria({ h }: { h: HistoriaItem[] }) {
  return (
    <table className="tabla tabla--densa">
      <thead>
        <tr>
          <th>Fecha</th>
          <th>Incidente</th>
          <th>Gravedad</th>
          <th>Qué hacer</th>
          <th>Estado</th>
        </tr>
      </thead>
      <tbody>
        {h.map((x) => (
          <tr key={x.id}>
            <td className="nowrap">{fFecha(x.inicio)}</td>
            <td>
              <Link to={`/casos/${x.id}`} className="enlace">
                {x.id}
              </Link>{' '}
              {x.titulo}
              <div className="muted">{x.frase}</div>
            </td>
            <td>
              <Gravedad g={x.gravedad} />
            </td>
            <td>{x.accion}</td>
            <td>
              <span className={`estado estado--${x.estado}`}>{ESTADO_CASO[x.estado]}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Internas({ d }: { d: DatosTablero }) {
  const i = d.internas
  const confirmadas = i.casos.filter((c) => c.ambas).length
  const actividad = (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={i.porDia} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
        <XAxis dataKey="dia" tickFormatter={(x: string) => String(Number(x.slice(8)))} tick={{ fontSize: 11, fill: 'var(--tinta-3)' }} interval={4} axisLine={false} tickLine={false} />
        <YAxis width={42} tick={{ fontSize: 11, fill: 'var(--tinta-3)' }} axisLine={false} tickLine={false} tickFormatter={(v: number) => num(v)} />
        <Tooltip labelFormatter={(x) => fFecha(String(x))} />
        <Area type="monotone" dataKey="fallidos" name="Accesos fallidos" stackId="1" stroke="var(--critica)" fill="var(--critica)" fillOpacity={0.25} isAnimationActive={false} />
        <Area type="monotone" dataKey="ssh" name="Conexiones SSH" stackId="1" stroke="var(--azul)" fill="var(--azul)" fillOpacity={0.25} isAnimationActive={false} />
        <Area type="monotone" dataKey="transferencias" name="Transferencias" stackId="1" stroke="var(--verde)" fill="var(--verde)" fillOpacity={0.2} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
  const barras = (datos: { nombre: string; n: number }[], color: string, ancho = 150) => (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={datos} layout="vertical" margin={{ left: 0, right: 30, top: 0, bottom: 0 }}>
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis type="category" dataKey="nombre" width={ancho} tick={{ fontSize: 11.5, fill: 'var(--tinta-2)' }} axisLine={false} tickLine={false} />
        <Tooltip cursor={{ fill: 'var(--neutro-fondo)' }} />
        <Bar dataKey="n" fill={color} radius={[0, 4, 4, 0]} barSize={13} isAnimationActive={false}>
          <LabelList dataKey="n" position="right" style={{ fontSize: 11.5, fontWeight: 700, fill: 'var(--tinta)' }} formatter={(v) => num(Number(v))} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
  return (
    <>
      <Tarjeta titulo="Incidentes" dato={`${i.casos.length}`} area="a" ruta="/casos">
        <ul className="casos-mini">
          {i.casos.map((c) => (
            <li key={c.id} className={`casos-mini__i casos-mini__i--${c.gravedad}`}>
              <Link to={`/casos/${c.id}`} className="enlace">
                {c.id}
              </Link>
              <span className="casos-mini__t">{c.titulo}</span>
              <span className="muted">{fFecha(c.inicio)}</span>
              <Gravedad g={c.gravedad} />
              <span className={`estado estado--${c.estado}`}>{ESTADO_CASO[c.estado]}</span>
            </li>
          ))}
        </ul>
      </Tarjeta>
      <Tarjeta titulo="Actividad diaria del mes" area="b" ruta="/linea" grande={<div style={{ height: 420 }}>{actividad}</div>}>
        {actividad}
      </Tarjeta>
      <Tarjeta titulo="Técnicas MITRE ATT&CK" area="c" grande={<div style={{ height: 380 }}>{barras(i.mitre.map((m) => ({ nombre: m.tecnica, n: m.casos })), 'var(--alta-relleno)', 320)}</div>}>
        {barras(i.mitre.slice(0, 5).map((m) => ({ nombre: m.tecnica.split(' ')[0], n: m.casos })), 'var(--alta-relleno)', 80)}
      </Tarjeta>
      <Tarjeta titulo="Equipos de origen" area="d" ruta="/correlaciones">
        {barras(i.activos.map((a) => ({ nombre: a.activo, n: a.eventos })), 'var(--critica)', 100)}
      </Tarjeta>
      <Tarjeta titulo="Anomalías del modelo" area="e" ruta="/anomalias">
        <div className="cifras-mini cifras-mini--2">
          <div className="cifra-mini">
            <strong>{i.anomalias.firewall.sospechosas}</strong>
            <span>de {num(i.anomalias.firewall.total)} usuarios de red</span>
          </div>
          <div className="cifra-mini">
            <strong>{i.anomalias.sistema_medico.sospechosas}</strong>
            <span>de {num(i.anomalias.sistema_medico.total)} cuentas médicas</span>
          </div>
        </div>
        <p className="nota">{i.anomalias.firewall.sinCaso + i.anomalias.sistema_medico.sinCaso} sin caso abierto: vigilar.</p>
      </Tarjeta>
      <Tarjeta titulo="Correlación de fuentes" area="f" ruta="/correlaciones">
        <Anillo valor={confirmadas} total={i.casos.length} texto="confirmados en firewall y sistema médico" />
      </Tarjeta>
    </>
  )
}

function Anillo({ valor, total, texto }: { valor: number; total: number; texto: string }) {
  const datos = [
    { n: valor, c: 'var(--verde)' },
    { n: Math.max(0, total - valor), c: 'var(--neutro-fondo)' },
  ]
  return (
    <div className="anillo">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={datos} dataKey="n" innerRadius="62%" outerRadius="88%" startAngle={90} endAngle={-270} stroke="none" isAnimationActive={false}>
            {datos.map((x, i) => (
              <Cell key={i} fill={x.c} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="anillo__centro">
        <strong>
          {valor}/{total}
        </strong>
        <span>{texto}</span>
      </div>
    </div>
  )
}

const ESTADOS_AG: [string, string][] = [
  ['Revisión prioritaria', 'var(--critica)'],
  ['Requiere revisión', 'var(--alta-relleno)'],
  ['Indeterminado: falta información', 'var(--violeta)'],
  ['Observación', 'var(--azul)'],
  ['Explicado por contexto legítimo', 'var(--legitimo)'],
]

function Citas({ d }: { d: DatosTablero }) {
  const c = d.citas
  const ag = c.agenda
  const estados = ag ? ESTADOS_AG.map(([e, col]) => ({ nombre: e.split(':')[0], n: ag.resumen.estados[e] ?? 0, col })).filter((x) => x.n > 0) : []
  const tabla = (completa: boolean) => (
    <table className="tabla tabla--densa">
      <thead>
        <tr>
          <th>Origen</th>
          <th>Estado</th>
          <th className="num">Pacientes</th>
          <th className="num">Reservas</th>
          {completa && <th>Patrones</th>}
          <th className="num">Riesgo</th>
        </tr>
      </thead>
      <tbody>
        {ag?.top.map((x) => (
          <tr key={x.case_id}>
            <td className="mono">
              {x.case_id}
              {x.denuncias > 0 && <span className="pildora pildora--denuncia">denuncia</span>}
            </td>
            <td>{x.status.split(':')[0]}</td>
            <td className="num">{x.pacientes}</td>
            <td className="num">{x.reservas}</td>
            {completa && <td className="mono">{x.pattern_ids.join(' ')}</td>}
            <td className="num">
              <span className={`nivel nivel--${zona(x.risk_score)}`}>{x.risk_score}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
  return (
    <>
      <Tarjeta titulo="Orígenes del chatbot por estado" dato={ag ? `${num(ag.resumen.puntos)} orígenes` : undefined} area="a" ruta="/agendamiento">
        {ag ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={estados} layout="vertical" margin={{ left: 0, right: 40, top: 0, bottom: 0 }}>
              <XAxis type="number" hide scale="sqrt" />
              <YAxis type="category" dataKey="nombre" width={170} tick={{ fontSize: 12, fill: 'var(--tinta-2)' }} axisLine={false} tickLine={false} />
              <Tooltip cursor={{ fill: 'var(--neutro-fondo)' }} />
              <Bar dataKey="n" radius={[0, 4, 4, 0]} barSize={15} isAnimationActive={false}>
                {estados.map((x) => (
                  <Cell key={x.nombre} fill={x.col} />
                ))}
                <LabelList dataKey="n" position="right" style={{ fontSize: 12, fontWeight: 700, fill: 'var(--tinta)' }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="nota">El análisis activo no incluyó el chatbot de citas.</p>
        )}
      </Tarjeta>
      <Tarjeta titulo="Orígenes para revisar" dato={ag ? `${ag.top.length}` : '0'} area="b" ruta="/agendamiento" grande={tabla(true)}>
        <div className="tj__scroll">{tabla(false)}</div>
      </Tarjeta>
      <Tarjeta titulo="Denuncias por tipo" dato={`${c.denunciasTipo.reduce((a, x) => a + x.n, 0)}`} area="c" ruta="/denuncias">
        <ul className="lista-n">
          {c.denunciasTipo.map((x) => (
            <li key={x.tipo}>
              <span>{x.tipo}</span>
              <strong>{x.n}</strong>
            </li>
          ))}
          {!c.denunciasTipo.length && <li className="muted">Sin denuncias aún.</li>}
        </ul>
      </Tarjeta>
      <Tarjeta titulo="Seguimiento" area="d" ruta="/denuncias">
        <div className="cifras-mini">
          {(Object.keys(ESTADO_DENUNCIA) as (keyof typeof ESTADO_DENUNCIA)[]).map((k) => (
            <div key={k} className="cifra-mini">
              <strong>{c.denunciasEstado[k] ?? 0}</strong>
              <span>{ESTADO_DENUNCIA[k].toLowerCase()}</span>
            </div>
          ))}
        </div>
        <p className="nota">
          {c.verificar} contenidos reportados por el personal de salud · {ag ? num(ag.resumen.citas_en_revision) : 0} citas a confirmar
        </p>
      </Tarjeta>
    </>
  )
}

function Externas({ d }: { d: DatosTablero }) {
  const e = d.externas
  const fuentes = Object.entries(e.porFuente).map(([nombre, n]) => ({ nombre, n }))
  const lista = (max?: number) => (
    <ul className="externas">
      {e.tendencias.slice(0, max ?? e.tendencias.length).map((t) => (
        <li key={t.id}>
          <div className="externas__fila">
            <strong>{t.titulo}</strong>
            {t.kev && <span className="chip chip--critica">Explotada (KEV)</span>}
            {t.cvss != null && <span className="pildora">CVSS {t.cvss}</span>}
          </div>
          <span className="muted">
            {t.fuente} · {t.fecha ? fFecha(t.fecha) : 'sin fecha'} · {t.sello ?? 'simulado'}
          </span>
        </li>
      ))}
    </ul>
  )
  return (
    <>
      <Tarjeta titulo="Amenazas externas priorizadas" dato={`${e.tendencias.length}`} area="a" ruta="/tendencias" grande={lista()}>
        {lista(5)}
      </Tarjeta>
      <Tarjeta titulo="Fuentes oficiales" area="b" ruta="/tendencias">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={fuentes} layout="vertical" margin={{ left: 0, right: 26, top: 0, bottom: 0 }}>
            <XAxis type="number" hide allowDecimals={false} />
            <YAxis type="category" dataKey="nombre" width={120} tick={{ fontSize: 12, fill: 'var(--tinta-2)' }} axisLine={false} tickLine={false} />
            <Bar dataKey="n" fill="var(--azul)" radius={[0, 4, 4, 0]} barSize={14} isAnimationActive={false}>
              <LabelList dataKey="n" position="right" style={{ fontSize: 12, fontWeight: 700, fill: 'var(--tinta)' }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Tarjeta>
      <Tarjeta titulo="Procedencia" area="c">
        <div className="cifras-mini cifras-mini--2">
          <div className="cifra-mini">
            <strong>{e.reales}</strong>
            <span>lecturas reales de fuentes oficiales</span>
          </div>
          <div className="cifra-mini">
            <strong>{e.tendencias.filter((t) => t.kev).length}</strong>
            <span>con explotación confirmada</span>
          </div>
        </div>
        {e.reales === 0 && <p className="nota">Sin sincronizar: en Tendencias pulsa «Actualizar desde fuentes».</p>}
      </Tarjeta>
      <Tarjeta titulo="Qué tenemos expuesto" area="d" ruta="/tendencias">
        <ul className="lista-exp">
          {e.tendencias.slice(0, 3).map((t) => (
            <li key={t.id}>{t.exposicionLocal}</li>
          ))}
        </ul>
      </Tarjeta>
    </>
  )
}

function Negocio({ d }: { d: DatosTablero }) {
  const n = d.negocio
  const top = n.riesgos.slice(0, 4)
  return (
    <>
      <Tarjeta
        titulo="Exposición por dimensión del negocio"
        dato="probabilidad × impacto"
        area="a"
        ruta="/riesgos"
        grande={
          <>
            <div style={{ height: 300 }}>
              <BarrasDim dims={n.dimensiones} grande />
            </div>
            <table className="tabla tabla--densa">
              <thead>
                <tr>
                  <th>Dimensión</th>
                  <th>Pregunta</th>
                  <th>Riesgos que más pesan</th>
                </tr>
              </thead>
              <tbody>
                {n.dimensiones.map((x) => (
                  <tr key={x.id}>
                    <td>
                      <strong>{x.nombre}</strong>
                    </td>
                    <td>{x.pregunta}</td>
                    <td>{x.riesgos.slice(0, 3).map((r) => `${r.riesgo} ${r.nombre} (${r.exposicion})`).join(' · ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="nota">{n.nota}</p>
          </>
        }
      >
        <BarrasDim dims={n.dimensiones} />
      </Tarjeta>
      {top.map((r, i) => (
        <Tarjeta
          key={r.id}
          titulo={`${r.id} ${r.nombre}`}
          dato={<span className={`nivel nivel--${zona(r.nivel)}`}>{r.nivel}</span>}
          area={['b', 'c', 'd', 'e'][i]}
          ruta="/riesgos"
          tono={zona(r.nivel)}
          grande={<FichaRiesgo r={r} dims={n.dimensiones} />}
        >
          <p className="rn__proc">{r.proceso}</p>
          <p className="rn__esc">{r.escenario}</p>
          <p className="rn__dec">
            <strong>Decidir:</strong> {r.decision}
          </p>
        </Tarjeta>
      ))}
    </>
  )
}

function FichaRiesgo({ r, dims }: { r: RiesgoNegocio; dims: Dimension[] }) {
  return (
    <div className="ficha-riesgo">
      <p className="formula">
        <span>
          <b>{r.probabilidad}</b> probabilidad
        </span>
        <span>×</span>
        <span>
          <b>{r.impacto}</b> impacto
        </span>
        <span>=</span>
        <span className={`nivel nivel--${zona(r.nivel)} nivel--grande`}>{r.nivel}</span>
      </p>
      <dl className="ficha-riesgo__dl">
        <dt>Proceso afectado</dt>
        <dd>{r.proceso}</dd>
        <dt>Qué pasaría</dt>
        <dd>{r.escenario}</dd>
        <dt>En la operación</dt>
        <dd>{r.operativa}</dd>
        <dt>Legal (LOPDP)</dt>
        <dd>{r.legal}</dd>
        <dt>Reputación</dt>
        <dd>{r.reputacional}</dd>
        <dt>Costos</dt>
        <dd>{r.financiera}</dd>
        <dt>Decisión recomendada</dt>
        <dd>
          <strong>{r.decision}</strong>
        </dd>
      </dl>
      <div className="impactos">
        {dims.map((x) => (
          <div key={x.id} className="impactos__i">
            <span>{x.nombre}</span>
            <div className="impactos__puntos">
              {[1, 2, 3, 4, 5].map((k) => (
                <i key={k} className={k <= (r.impactos[x.id] ?? 0) ? `lleno lleno--${zona((r.impactos[x.id] ?? 0) * 5)}` : ''} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

