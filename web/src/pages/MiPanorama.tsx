import { BellRing, CheckCheck, FileSearch, Lightbulb, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import type { Aviso, Gravedad, PanoramaSalud } from '../api/types'
import { Tarjeta } from '../components/Tarjeta'
import { Carga } from '../components/ui'
import { fFecha, fFechaHora, fMesTitulo, num } from '../lib/format'
import { useSesion } from '../lib/sesion'
import { useApi } from '../lib/useApi'

const NIVEL: Record<Gravedad, string> = { critica: 'Muy alto', alta: 'Alto', media: 'Medio', baja: 'Bajo' }
const TONO_AVISO = { alto: 'critica', medio: 'alta', info: 'baja' } as const

/** Panel del personal de salud: solo cantidades y frases simples, filtradas en el servidor. */
export default function MiPanorama() {
  const { st, reintentar, actualizar } = useApi(api.panoramaSalud)
  return (
    <Carga st={st} reintentar={reintentar} filas={6}>
      {(d) => (
        <Vista
          d={d}
          alLeer={(codigo) =>
            actualizar((x) => ({ ...x, avisos: x.avisos.map((a) => (a.codigo === codigo ? { ...a, leido: true } : a)) }))
          }
        />
      )}
    </Carga>
  )
}

function Vista({ d, alLeer }: { d: PanoramaSalud; alLeer: (codigo: string) => void }) {
  const { sesion } = useSesion()
  const sinLeer = d.avisos.filter((a) => !a.leido).length
  return (
    <div className="tablero panorama">
      <div className="tablero__cab">
        <div className="panorama__saludo">
          <ShieldAlert size={34} aria-hidden />
        </div>
        <div className="tablero__titulo">
          <h1>Tu panorama de seguridad{d.periodo ? `: ${fMesTitulo(d.periodo.desde)}` : ''}</h1>
          <p>
            {sesion?.nombre}. {sinLeer ? `Tienes ${sinLeer} ${sinLeer === 1 ? 'aviso' : 'avisos'} sin leer. ` : 'Estás al día con los avisos. '}
            Aquí ves lo que necesitas saber, sin datos de pacientes ni detalles técnicos.
          </p>
        </div>
        <div className="tablero__acciones">
          <Link to="/verificar" className="boton boton--chico">
            <FileSearch size={15} aria-hidden /> Verificar un enlace o imagen
          </Link>
        </div>
      </div>

      <div className="tablero__grid panorama__grid">
        <Tarjeta
          titulo="Avisos para ti"
          dato={sinLeer ? `${sinLeer} sin leer` : 'al día'}
          area="a"
          tono={d.avisos.some((a) => !a.leido && a.nivel === 'alto') ? 'critica' : undefined}
          grande={<ListaAvisos avisos={d.avisos} alLeer={alLeer} />}
        >
          <div className="tj__scroll">
            <ListaAvisos avisos={d.avisos} alLeer={alLeer} />
          </div>
        </Tarjeta>

        <Tarjeta
          titulo="Qué está pasando este mes"
          dato={d.hayAnalisis ? `${d.total} señales` : 'sin datos aún'}
          area="b"
          grande={
            <div className="panorama__dos">
              <div style={{ height: 320 }}>
                <BarrasAmenazas d={d} grande />
              </div>
              <div style={{ height: 320 }}>
                <IntentosPorDia d={d} />
              </div>
            </div>
          }
        >
          {d.hayAnalisis ? (
            <div className="panorama__dos">
              <BarrasAmenazas d={d} />
              <IntentosPorDia d={d} />
            </div>
          ) : (
            <p className="muted">El equipo de seguridad todavía no cargó el análisis del mes.</p>
          )}
        </Tarjeta>

        <Tarjeta titulo="Cómo afecta a tu trabajo" area="c" grande={<Dimensiones d={d} grande />}>
          <Dimensiones d={d} />
        </Tarjeta>

        <Tarjeta titulo="Amenazas en el sector salud" area="d" grande={<Sector d={d} />}>
          <div className="tj__scroll">
            <Sector d={d} />
          </div>
        </Tarjeta>

        <Tarjeta titulo="Lo que tú reportaste" dato={`${d.misReportes.length}`} area="e" grande={<Reportes d={d} />}>
          <div className="tj__scroll">
            <Reportes d={d} />
          </div>
        </Tarjeta>

        <Tarjeta titulo="Qué hacer" area="f" grande={<Consejos d={d} />}>
          <div className="tj__scroll">
            <Consejos d={d} />
          </div>
        </Tarjeta>
      </div>
    </div>
  )
}

function ListaAvisos({ avisos, alLeer }: { avisos: Aviso[]; alLeer: (codigo: string) => void }) {
  const [enviando, setEnviando] = useState('')
  const [error, setError] = useState('')
  if (!avisos.length)
    return (
      <div className="panorama__vacio">
        <BellRing size={26} aria-hidden />
        <p>No hay avisos. Cuando el equipo de seguridad detecte algo que te afecte, aparecerá aquí.</p>
      </div>
    )
  return (
    <ul className="avisos">
      {avisos.map((a) => (
        <li key={a.codigo} className={`aviso-salud aviso-salud--${TONO_AVISO[a.nivel]} ${a.leido ? 'aviso-salud--leido' : ''}`}>
          <div className="aviso-salud__cab">
            <strong>{a.titulo}</strong>
            <span className="muted">{fFechaHora(a.fecha)}</span>
          </div>
          <p>{a.texto}</p>
          {a.consejo && <p className="aviso-salud__consejo">{a.consejo}</p>}
          {a.leido ? (
            <span className="aviso-salud__ok">
              <CheckCheck size={15} aria-hidden /> Leído
            </span>
          ) : (
            <button
              className="boton boton--chico"
              disabled={enviando === a.codigo}
              onClick={() => {
                setEnviando(a.codigo)
                setError('')
                api
                  .avisoLeido(a.codigo)
                  .then(() => {
                    alLeer(a.codigo)
                    window.dispatchEvent(new Event('sentinel:avisos'))
                  })
                  .catch((e: Error) => setError(e.message))
                  .finally(() => setEnviando(''))
              }}
            >
              Entendido
            </button>
          )}
        </li>
      ))}
      {error && <li className="error-linea">{error}</li>}
    </ul>
  )
}

function BarrasAmenazas({ d, grande }: { d: PanoramaSalud; grande?: boolean }) {
  const datos = [...d.amenazas].sort((a, b) => b.n - a.n)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={datos} layout="vertical" margin={{ left: 0, right: 34, top: 2, bottom: 2 }}>
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="nombre"
          width={grande ? 250 : 190}
          tick={{ fontSize: grande ? 14 : 12, fill: 'var(--tinta-2)' }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip formatter={(v) => [`${v}`, 'Señales este mes']} cursor={{ fill: 'var(--neutro-fondo)' }} />
        <Bar dataKey="n" fill="var(--verde)" radius={[0, 4, 4, 0]} barSize={grande ? 24 : 13} isAnimationActive={false}>
          <LabelList dataKey="n" position="right" style={{ fontWeight: 700, fontSize: grande ? 14 : 12, fill: 'var(--tinta)' }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function IntentosPorDia({ d }: { d: PanoramaSalud }) {
  if (!d.porDia.length) return null
  return (
    <figure className="panorama__serie">
      <figcaption>Intentos de ingreso fallidos por día</figcaption>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={d.porDia} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
          <XAxis dataKey="dia" tickFormatter={(x: string) => x.slice(8)} tick={{ fontSize: 11, fill: 'var(--tinta-3)' }} interval="preserveStartEnd" />
          <YAxis hide />
          <Tooltip labelFormatter={(x) => fFecha(String(x))} formatter={(v) => [num(Number(v)), 'Intentos fallidos']} />
          <Area type="monotone" dataKey="intentos" stroke="var(--verde)" strokeWidth={2} fill="var(--verde-claro)" isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </figure>
  )
}

function Dimensiones({ d, grande }: { d: PanoramaSalud; grande?: boolean }) {
  if (!d.dimensiones.length) return <p className="muted">Se calcula cuando haya un análisis del mes.</p>
  return (
    <ul className="dims-salud">
      {d.dimensiones.map((x) => (
        <li key={x.id}>
          <div className="dims-salud__cab">
            <strong>{x.nombre}</strong>
            <span className={`nivel-pildora nivel-pildora--${x.nivel}`}>{NIVEL[x.nivel]}</span>
          </div>
          <div className="dims-salud__barra" role="img" aria-label={`${x.exposicion} de 25`}>
            <span className={`dims-salud__lleno dims-salud__lleno--${x.nivel}`} style={{ width: `${(x.exposicion / 25) * 100}%` }} />
          </div>
          {(grande || d.dimensiones.length <= 3) && <p>{x.explicacion}</p>}
        </li>
      ))}
    </ul>
  )
}

function Sector({ d }: { d: PanoramaSalud }) {
  if (!d.sector.length) return <p className="muted">Sin novedades de las fuentes oficiales.</p>
  return (
    <ul className="sector">
      {d.sector.map((t) => (
        <li key={t.titulo}>
          <strong>{t.titulo}</strong>
          <p>{t.resumen}</p>
          <span className="muted">
            {t.fuente}
            {t.fecha ? `, ${fFecha(t.fecha)}` : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}

function Reportes({ d }: { d: PanoramaSalud }) {
  if (!d.misReportes.length)
    return (
      <p className="muted">
        Todavía no reportaste nada. Si te llega un enlace o una imagen dudosa, revísala en <Link to="/verificar">Verificar contenido</Link> y
        repórtala desde ahí.
      </p>
    )
  return (
    <ul className="mis-reportes">
      {d.misReportes.map((r) => (
        <li key={r.codigo}>
          <div>
            <span className="mono quiebre">{r.que}</span>
            <span className="muted">{fFechaHora(r.fecha)}</span>
          </div>
          <span className="mis-reportes__estado">{r.estado}</span>
          {r.respuesta && <p>{r.respuesta}</p>}
        </li>
      ))}
    </ul>
  )
}

function Consejos({ d }: { d: PanoramaSalud }) {
  return (
    <ul className="consejos">
      {d.consejos.map((c) => (
        <li key={c}>
          <Lightbulb size={17} aria-hidden />
          <span>{c}</span>
        </li>
      ))}
    </ul>
  )
}
