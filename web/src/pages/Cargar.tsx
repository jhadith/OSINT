import { Check, CircleAlert, CircleDashed, FileUp, FolderOpen, LoaderCircle, Minus, Play } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Analisis, Fuente, ListaAnalisis, Paso } from '../api/types'
import { Carga, Pagina, Panel } from '../components/ui'
import { duracion, fFechaHora, fMes, fMesTitulo, num, plural } from '../lib/format'
import { useSesion } from '../lib/sesion'
import { useApi } from '../lib/useApi'

type Slot = 'firewall' | 'sistema_medico' | 'agendamiento'
const SLOTS: { id: Slot; nombre: string; ayuda: string; opcional?: boolean }[] = [
  { id: 'firewall', nombre: 'Registros del firewall', ayuda: 'Quién se conectó, desde dónde y a qué puerto.' },
  { id: 'sistema_medico', nombre: 'Registros del sistema médico', ayuda: 'Qué cuenta hizo qué acción y a qué hora.' },
  { id: 'agendamiento', nombre: 'Registros del chatbot de citas', ayuda: 'Reservas, cancelaciones y sesiones. Sintético.', opcional: true },
]

export default function Cargar() {
  const { st, reintentar } = useApi(api.analisis)
  const [siguiendo, setSiguiendo] = useState<string | null>(null)

  return (
    <Pagina
      titulo="Cargar datos"
      bajada="Sube los registros del mes y mira cada paso: lectura, limpieza, protección de datos personales y detección. Nada sale de este equipo."
    >
      <Carga st={st} reintentar={reintentar}>
        {(l) => {
          const enCurso = siguiendo ?? (l.ocupado ? l.analisis.find((a) => a.estado === 'en_curso')?.id ?? null : null)
          return (
            <>
              {enCurso ? (
                <Progreso id={enCurso} alTerminar={reintentar} alCerrar={() => setSiguiendo(null)} />
              ) : (
                <Nuevo alIniciar={(id) => setSiguiendo(id)} />
              )}
              <Historial l={l} alCambiar={reintentar} />
            </>
          )
        }}
      </Carga>
    </Pagina>
  )
}

// ---------- nuevo análisis ----------
function Nuevo({ alIniciar }: { alIniciar: (id: string) => void }) {
  const [modo, setModo] = useState<'subir' | 'carpeta'>('carpeta')
  return (
    <Panel
      titulo="Nuevo análisis"
      extra={
        <div className="pestanas" role="tablist">
          <button role="tab" aria-selected={modo === 'carpeta'} onClick={() => setModo('carpeta')}>
            <FolderOpen size={16} aria-hidden /> Desde la carpeta de datos
          </button>
          <button role="tab" aria-selected={modo === 'subir'} onClick={() => setModo('subir')}>
            <FileUp size={16} aria-hidden /> Subir archivos
          </button>
        </div>
      }
    >
      {modo === 'subir' ? <Subir alIniciar={alIniciar} /> : <DesdeCarpeta alIniciar={alIniciar} />}
    </Panel>
  )
}

function Subir({ alIniciar }: { alIniciar: (id: string) => void }) {
  const [archivos, setArchivos] = useState<Partial<Record<Slot, File>>>({})
  const [avance, setAvance] = useState<number | null>(null)
  const [error, setError] = useState('')
  const listo = archivos.firewall && archivos.sistema_medico

  async function procesar() {
    if (!archivos.firewall || !archivos.sistema_medico) return
    setError('')
    setAvance(0)
    try {
      const a = await api.subirArchivos(archivos.firewall, archivos.sistema_medico, archivos.agendamiento ?? null, setAvance)
      alIniciar(a.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo subir.')
      setAvance(null)
    }
  }

  return (
    <div>
      <div className="zonas">
        {SLOTS.map((s) => (
          <Zona key={s.id} slot={s} archivo={archivos[s.id]} alElegir={(f) => setArchivos((a) => ({ ...a, [s.id]: f }))} />
        ))}
      </div>
      {avance !== null && (
        <div className="subida" aria-live="polite">
          <div className="subida__fila">
            <span>{avance < 1 ? 'Subiendo archivos al servidor local' : 'Archivos recibidos, empezando el análisis'}</span>
            <strong>{Math.round(avance * 100)} %</strong>
          </div>
          <div className="medidor__pista">
            <div className="medidor__barra medidor__barra--verde" style={{ width: `${avance * 100}%` }} />
          </div>
        </div>
      )}
      {error && (
        <p className="error-linea" role="alert">
          {error}
        </p>
      )}
      <button className="boton boton--grande" disabled={!listo || avance !== null} onClick={procesar}>
        <Play size={18} aria-hidden /> Procesar
      </button>
    </div>
  )
}

function Zona({ slot, archivo, alElegir }: { slot: (typeof SLOTS)[number]; archivo?: File; alElegir: (f: File) => void }) {
  const [encima, setEncima] = useState(false)
  return (
    <label
      className={`zona ${archivo ? 'zona--lista' : ''} ${encima ? 'zona--encima' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setEncima(true)
      }}
      onDragLeave={() => setEncima(false)}
      onDrop={(e) => {
        e.preventDefault()
        setEncima(false)
        const f = e.dataTransfer.files[0]
        if (f) alElegir(f)
      }}
    >
      <input type="file" accept=".csv,text/csv" className="sr" onChange={(e) => e.target.files?.[0] && alElegir(e.target.files[0])} />
      <span className="zona__nombre">
        {slot.nombre}
        {slot.opcional && <em> (opcional)</em>}
      </span>
      <span className="zona__ayuda">{slot.ayuda}</span>
      {archivo ? (
        <span className="zona__archivo">
          <Check size={16} aria-hidden /> {archivo.name.replace(/iess/gi, 'inst')}, {num(Math.round(archivo.size / 1e5) / 10)} MB
        </span>
      ) : (
        <span className="zona__accion">Arrastra el CSV aquí o haz clic para elegirlo</span>
      )}
    </label>
  )
}

function DesdeCarpeta({ alIniciar }: { alIniciar: (id: string) => void }) {
  const { st, reintentar } = useApi(api.fuentes)
  const [eleccion, setEleccion] = useState<Partial<Record<Slot, string>>>({})
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  return (
    <Carga st={st} reintentar={reintentar} filas={3}>
      {({ carpeta, archivos }) => {
        const clave = (f: Fuente) => `${f.origen}/${f.nombre}`
        const porDefecto = (s: Slot) => {
          const del = archivos.filter((f) => f.tipo === s)
          return (del.find((f) => f.origen === 'datos') ?? del[0]) as Fuente | undefined
        }
        const valor = (s: Slot) => eleccion[s] ?? (porDefecto(s) ? clave(porDefecto(s) as Fuente) : '')
        const fuente = (s: Slot) => archivos.find((f) => clave(f) === valor(s)) ?? null
        const listo = fuente('firewall') && fuente('sistema_medico')
        return (
          <div>
            <p className="nota">
              Archivos CSV en <code>{carpeta}</code> y ejemplos sintéticos incluidos. Para grandes volúmenes es más rápido que
              subirlos por el navegador.
            </p>
            <div className="zonas">
              {SLOTS.map((s) => (
                <label key={s.id} className={`zona ${fuente(s.id) ? 'zona--lista' : ''}`}>
                  <span className="zona__nombre">
                    {s.nombre}
                    {s.opcional && <em> (opcional)</em>}
                  </span>
                  <span className="zona__ayuda">{s.ayuda}</span>
                  <select value={valor(s.id)} onChange={(e) => setEleccion((x) => ({ ...x, [s.id]: e.target.value }))}>
                    <option value="">{s.opcional ? 'No incluir' : 'Elige un archivo'}</option>
                    {archivos.map((f) => (
                      <option key={clave(f)} value={clave(f)}>
                        {f.etiqueta} ({num(f.mb)} MB{f.origen === 'ejemplo' ? ', ejemplo sintético' : ''})
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            {error && (
              <p className="error-linea" role="alert">
                {error}
              </p>
            )}
            <button
              className="boton boton--grande"
              disabled={!listo || enviando}
              onClick={async () => {
                setEnviando(true)
                setError('')
                try {
                  const a = await api.desdeCarpeta(fuente('firewall') as Fuente, fuente('sistema_medico') as Fuente, fuente('agendamiento'))
                  alIniciar(a.id)
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'No se pudo iniciar.')
                } finally {
                  setEnviando(false)
                }
              }}
            >
              <Play size={18} aria-hidden /> Procesar
            </button>
          </div>
        )
      }}
    </Carga>
  )
}

// ---------- progreso en vivo ----------
const n = (v: unknown) => num(Number(v ?? 0))

/** Cada paso contado en lenguaje claro con los números que entrega el motor. */
function frase(p: Paso): string | null {
  const d = p.datos
  if (p.estado === 'omitido') return p.id === 'agendamiento' ? 'No se incluyó el archivo del chatbot.' : 'Se omitió en esta corrida.'
  if (!Object.keys(d).length) return null
  switch (p.id) {
    case 'recepcion':
      return `${n(d.mb)} MB recibidos.`
    case 'validacion':
      if (p.estado === 'en_curso')
        return d.filas ? `Leyendo ${d.fuente === 'firewall' ? 'el firewall' : 'el sistema médico'}: ${n(d.filas)} filas…` : 'Leyendo…'
      return `${n(d.filas_firewall)} filas del firewall y ${n(d.filas_sistema_medico)} del sistema médico. ${
        Number(d.filas_descartadas) ? `${n(d.filas_descartadas)} filas dañadas apartadas.` : 'Ninguna fila dañada.'
      }`
    case 'normalizacion':
      return `${n(d.fechas_unificadas)} fechas en un formato común, ${n(d.usuarios_firewall)} usuarios de red, ${n(
        d.cuentas_sistema_medico,
      )} cuentas del sistema médico y ${n(d.ips_mal_escritas)} IPs mal escritas marcadas.`
    case 'reglas':
      return `${n(d.rafagas_firewall)} ráfagas en la red, ${n(d.hallazgos_sistema_medico)} hallazgos en el sistema médico y ${n(
        d.debilidades_configuracion,
      )} debilidades de configuración.`
    case 'cruce':
      return `${n(d.ataques_confirmados_en_ambas_fuentes)} ataques aparecen en las dos fuentes a la vez.${
        Number(d.relojes_corregidos) ? ' Se corrigió el desfase de reloj de una fuente.' : ''
      }`
    case 'modelo':
      return `${n(Number(d.ventanas_firewall) + Number(d.ventanas_sistema_medico))} ventanas de tiempo comparadas entre ${n(
        d.usuarios,
      )} usuarios y ${n(d.cuentas)} cuentas.`
    case 'agendamiento':
      return `${n(d.sesiones)} sesiones agrupadas en ${n(d.puntos)} orígenes; ${n(d.revision_requerida)} requieren revisión humana.`
    case 'priorizacion':
      return `${plural(Number(d.alertas ?? 0), 'alerta', 'alertas')}: ${plural(Number(d.critica ?? 0), 'crítica', 'críticas')}, ${plural(
        Number(d.alta ?? 0),
        'alta',
        'altas',
      )}, ${plural(Number(d.media ?? 0), 'media', 'medias')} y ${plural(Number(d.baja ?? 0), 'baja', 'bajas')}.`
    case 'proteccion':
      return `${n(d.seudonimos_generados)} seudónimos creados. Los nombres reales quedan en una tabla aparte que solo se abre con un motivo registrado.`
    case 'listo':
      return `Terminado en ${duracion(Number(d.minutos ?? 0))}.`
    default:
      return null
  }
}

function IconoPaso({ e }: { e: Paso['estado'] }) {
  if (e === 'listo') return <Check size={18} aria-hidden />
  if (e === 'en_curso') return <LoaderCircle size={18} className="gira" aria-hidden />
  if (e === 'omitido') return <Minus size={18} aria-hidden />
  if (e === 'error') return <CircleAlert size={18} aria-hidden />
  return <CircleDashed size={18} aria-hidden />
}

function Progreso({ id, alTerminar, alCerrar }: { id: string; alTerminar: () => void; alCerrar: () => void }) {
  const [a, setA] = useState<Analisis | null>(null)
  const [inicio] = useState(() => Date.now())
  const [ahora, setAhora] = useState(() => Date.now())
  const avisado = useRef(false)

  useEffect(() => {
    let vivo = true
    let t: ReturnType<typeof setTimeout>
    const tick = async () => {
      try {
        const r = await api.analisisUno(id)
        if (!vivo) return
        setA(r)
        setAhora(Date.now())
        if (r.estado === 'en_curso') t = setTimeout(tick, 700)
        else if (!avisado.current) {
          avisado.current = true
          alTerminar()
        }
      } catch {
        if (vivo) t = setTimeout(tick, 1500)
      }
    }
    tick()
    return () => {
      vivo = false
      clearTimeout(t)
    }
  }, [id, alTerminar])

  const pasos = a?.pasos ?? []
  const hechos = pasos.filter((p) => p.estado === 'listo' || p.estado === 'omitido').length
  const segundos = Math.round((ahora - inicio) / 1000)

  return (
    <Panel
      className="panel--progreso"
      titulo={a?.estado === 'listo' ? 'Análisis terminado' : a?.estado === 'error' ? 'El análisis se detuvo' : 'Analizando'}
      bajada={a ? `${a.id}, iniciado por ${a.autor}` : 'Preparando…'}
      extra={
        <span className="contador" aria-live="off">
          {hechos} de {pasos.length || 11} pasos{a?.estado === 'en_curso' ? `, ${segundos} s` : ''}
        </span>
      }
    >
      <ol className="pasos">
        {pasos.map((p, i) => {
          const f = frase(p)
          return (
            <li key={p.id} className={`paso paso--${p.estado}`}>
              <span className="paso__icono">
                <IconoPaso e={p.estado} />
              </span>
              <div>
                <div className="paso__nombre">
                  <span className="paso__num">{i + 1}</span> {p.nombre}
                </div>
                <div className="paso__expl">{p.explicacion}</div>
                {f && <div className="paso__dato">{f}</div>}
              </div>
            </li>
          )
        })}
      </ol>
      {a?.estado === 'error' && (
        <div className="aviso aviso--error" role="alert">
          <CircleAlert size={20} aria-hidden />
          <div>
            <strong>{a.error ?? 'El motor terminó con un error.'}</strong>
            <p>Revisa que los archivos tengan las columnas esperadas y vuelve a intentar.</p>
            <button className="boton boton--secundario" onClick={alCerrar}>
              Volver
            </button>
          </div>
        </div>
      )}
      {a?.estado === 'listo' && (
        <div className="fin">
          <p>
            {a.resumen && (
              <>
                {num(a.resumen.registros)} registros de {fMes(a.resumen.periodo.desde)} analizados. La consola ya muestra este
                análisis.
              </>
            )}
          </p>
          <div className="fin__acciones">
            <Link className="boton boton--grande" to="/inicio">
              Ver la vista ejecutiva
            </Link>
            <Link className="boton boton--secundario boton--grande" to="/riesgos">
              Ver cómo cambió la matriz de riesgos
            </Link>
            <button className="boton boton--fantasma" onClick={alCerrar}>
              Cargar otro
            </button>
          </div>
        </div>
      )}
    </Panel>
  )
}

// ---------- historial ----------
function Historial({ l, alCambiar }: { l: ListaAnalisis; alCambiar: () => void }) {
  const { puede } = useSesion()
  const [error, setError] = useState('')
  const filas = useMemo(() => l.analisis, [l])
  if (!filas.length) return null
  return (
    <Panel titulo="Análisis anteriores" bajada="La consola muestra uno a la vez. Puedes volver a uno anterior para comparar.">
      {error && <p className="error-linea">{error}</p>}
      <div className="tabla-scroll">
        <table className="tabla">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Periodo</th>
              <th>Archivos</th>
              <th className="num">Registros</th>
              <th>Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filas.map((a) => (
              <tr key={a.id} className={a.activo ? 'fila--activa' : ''}>
                <td>
                  {fFechaHora(a.creado)}
                  <div className="muted mono">{a.id}</div>
                </td>
                <td>{a.resumen ? fMesTitulo(a.resumen.periodo.desde) : '—'}</td>
                <td className="archivos">
                  {[a.archivos.firewall, a.archivos.sistema_medico, a.archivos.agendamiento].filter(Boolean).join(', ')}
                </td>
                <td className="num">{a.resumen ? num(a.resumen.registros) : '—'}</td>
                <td>{a.estado === 'listo' ? 'Terminado' : a.estado === 'error' ? 'Con error' : 'En curso'}</td>
                <td>
                  {a.activo ? (
                    <span className="etiqueta etiqueta--verde">En la consola</span>
                  ) : (
                    a.estado === 'listo' &&
                    puede('cargar_datos') && (
                      <button
                        className="boton boton--secundario boton--chico"
                        onClick={() =>
                          api
                            .activar(a.id)
                            .then(alCambiar)
                            .catch((e: Error) => setError(e.message))
                        }
                      >
                        Mostrar este
                      </button>
                    )
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
