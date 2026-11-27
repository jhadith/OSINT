import { CheckCircle2, CircleDot, Clock3, Send, XCircle } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import type { EstadoTicket, ListaTickets, TicketRegla } from '../api/types'
import { Carga, Cifra, Pagina, Panel } from '../components/ui'
import { fFechaHora, num } from '../lib/format'
import { useSesion } from '../lib/sesion'
import { useApi } from '../lib/useApi'

const ICONO: Record<EstadoTicket, typeof CircleDot> = {
  abierto: CircleDot,
  en_progreso: Clock3,
  aplicado: CheckCircle2,
  rechazado: XCircle,
}
const PRIORIDAD = { alta: 'Alta', media: 'Media', baja: 'Baja' } as const

export default function Tickets() {
  const { puede } = useSesion()
  const { st, reintentar } = useApi(api.tickets)
  const esTi = puede('gestionar_reglas')
  return (
    <Pagina
      titulo="Tickets de reglas"
      bajada={
        esTi
          ? 'Lo que el SOC pide cambiar en las reglas de detección. Cada ticket llega con su justificación; tú decides si se aplica.'
          : 'Pide a TI que cree, ajuste o desactive una regla. El ticket le llega a TI con un aviso y queda en la bitácora.'
      }
    >
      <Carga st={st} reintentar={reintentar}>
        {(d) => <Vista d={d} esTi={esTi} puedePedir={puede('pedir_reglas')} alCambiar={reintentar} />}
      </Carga>
    </Pagina>
  )
}

function Vista({ d, esTi, puedePedir, alCambiar }: { d: ListaTickets; esTi: boolean; puedePedir: boolean; alCambiar: () => void }) {
  const cuenta = (e: EstadoTicket) => d.tickets.filter((t) => t.estado === e).length
  const [sel, setSel] = useState<string | null>(null)
  const elegido = d.tickets.find((t) => t.codigo === sel) ?? d.tickets[0]
  return (
    <>
      <div className="cifras">
        <Cifra valor={num(cuenta('abierto'))} etiqueta="abiertos, esperan a TI" />
        <Cifra valor={num(cuenta('en_progreso'))} etiqueta="en progreso" />
        <Cifra valor={num(cuenta('aplicado'))} etiqueta="aplicados" />
        <Cifra valor={num(cuenta('rechazado'))} etiqueta="rechazados" />
      </div>
      <div className="rejilla rejilla--agenda">
        <div className="pila">
          {puedePedir && <Nuevo d={d} alCrear={alCambiar} />}
          <ul className="origenes">
            {d.tickets.map((t) => {
              const I = ICONO[t.estado]
              return (
                <li key={t.codigo}>
                  <button className={`origen ${elegido?.codigo === t.codigo ? 'origen--sel' : ''}`} onClick={() => setSel(t.codigo)}>
                    <span className="origen__fila">
                      <span className={`ticket-estado ticket-estado--${t.estado}`}>
                        <I size={14} aria-hidden /> {d.estados[t.estado]}
                      </span>
                      <span className="mono">{t.codigo}</span>
                      <span className={`pildora prioridad--${t.prioridad}`}>Prioridad {PRIORIDAD[t.prioridad].toLowerCase()}</span>
                    </span>
                    <span className="origen__frase">
                      <strong>{t.titulo}</strong>
                    </span>
                    <span className="muted">
                      {t.regla} · {fFechaHora(t.fecha)}
                    </span>
                  </button>
                </li>
              )
            })}
            {!d.tickets.length && <li className="muted">Todavía no hay tickets.</li>}
          </ul>
        </div>
        {elegido ? <Detalle key={elegido.codigo} t={elegido} d={d} esTi={esTi} alCambiar={alCambiar} /> : <div />}
      </div>
    </>
  )
}

function Nuevo({ d, alCrear }: { d: ListaTickets; alCrear: () => void }) {
  const [abierto, setAbierto] = useState(false)
  const [tipo, setTipo] = useState('ajustar')
  const [regla, setRegla] = useState(d.reglas[0] ?? '')
  const [titulo, setTitulo] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [prioridad, setPrioridad] = useState('media')
  const [caso, setCaso] = useState('')
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  if (!abierto)
    return (
      <button className="boton boton--grande" onClick={() => setAbierto(true)}>
        <Send size={18} aria-hidden /> Nuevo ticket para TI
      </button>
    )
  return (
    <Panel titulo="Nuevo ticket para TI">
      <div className="opciones">
        {Object.entries(d.tipos).map(([k, v]) => (
          <button key={k} type="button" className={`opcion ${tipo === k ? 'opcion--sel' : ''}`} aria-pressed={tipo === k} onClick={() => setTipo(k)}>
            {v.split(' (')[0]}
          </button>
        ))}
      </div>
      <label className="campo">
        Regla
        {tipo === 'nueva' ? (
          <input value={regla} onChange={(e) => setRegla(e.target.value)} placeholder="Nombre de la regla nueva" maxLength={120} />
        ) : (
          <select value={regla} onChange={(e) => setRegla(e.target.value)}>
            {d.reglas.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        )}
      </label>
      <label className="campo">
        Qué se pide
        <input value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={140} placeholder="Ej.: bajar el umbral de fuerza bruta" />
      </label>
      <label className="campo">
        Por qué (evidencia)
        <textarea rows={3} value={descripcion} onChange={(e) => setDescripcion(e.target.value)} maxLength={1500} placeholder="Qué viste en los datos y qué cambio propones" />
      </label>
      <div className="dos-campos">
        <label className="campo">
          Prioridad
          <select value={prioridad} onChange={(e) => setPrioridad(e.target.value)}>
            <option value="alta">Alta</option>
            <option value="media">Media</option>
            <option value="baja">Baja</option>
          </select>
        </label>
        <label className="campo">
          Caso relacionado (opcional)
          <input value={caso} onChange={(e) => setCaso(e.target.value.toUpperCase())} maxLength={20} placeholder="C1" />
        </label>
      </div>
      {error && <p className="error-linea">{error}</p>}
      {ok && <p className="ok-linea">{ok}</p>}
      <div className="botones">
        <button
          className="boton"
          disabled={titulo.trim().length < 5 || descripcion.trim().length < 15 || regla.trim().length < 2}
          onClick={() =>
            api
              .crearTicket({ tipo, regla, titulo, descripcion, prioridad, caso })
              .then((t) => {
                setOk(`Ticket ${t.codigo} enviado a TI.`)
                setTitulo('')
                setDescripcion('')
                setCaso('')
                alCrear()
              })
              .catch((e: Error) => setError(e.message))
          }
        >
          <Send size={16} aria-hidden /> Enviar a TI
        </button>
        <button className="boton boton--fantasma" onClick={() => setAbierto(false)}>
          Cerrar
        </button>
      </div>
    </Panel>
  )
}

function Detalle({ t, d, esTi, alCambiar }: { t: TicketRegla; d: ListaTickets; esTi: boolean; alCambiar: () => void }) {
  const [estado, setEstado] = useState<'en_progreso' | 'aplicado' | 'rechazado'>(t.estado === 'abierto' ? 'en_progreso' : 'aplicado')
  const [respuesta, setRespuesta] = useState('')
  const [error, setError] = useState('')
  const cerrado = t.estado === 'aplicado' || t.estado === 'rechazado'
  return (
    <Panel
      className="detalle-origen"
      titulo={
        <>
          <span className="mono">{t.codigo}</span> <span className={`ticket-estado ticket-estado--${t.estado}`}>{d.estados[t.estado]}</span>
        </>
      }
      bajada={`${t.tipo_texto}. Pedido por ${t.autor} el ${fFechaHora(t.fecha)}.`}
    >
      <h3>{t.titulo}</h3>
      <dl className="ficha-datos">
        <div>
          <dt>Regla</dt>
          <dd>{t.regla}</dd>
        </div>
        <div>
          <dt>Prioridad</dt>
          <dd>{PRIORIDAD[t.prioridad]}</dd>
        </div>
        <div>
          <dt>Caso</dt>
          <dd>{t.caso || 'Sin caso'}</dd>
        </div>
      </dl>
      <blockquote className="cita">{t.descripcion}</blockquote>
      {t.respuesta && (
        <p className="decision-previa">
          <strong>Respuesta de TI</strong> ({t.atendido_por}, {fFechaHora(t.actualizado)}): {t.respuesta}
        </p>
      )}
      {esTi && !cerrado && (
        <div className="revisar">
          <h3>Atender el ticket</h3>
          <div className="opciones">
            {(['en_progreso', 'aplicado', 'rechazado'] as const).map((k) => (
              <button key={k} type="button" className={`opcion ${estado === k ? 'opcion--sel' : ''}`} aria-pressed={estado === k} onClick={() => setEstado(k)}>
                {d.estados[k]}
              </button>
            ))}
          </div>
          <label className="campo">
            Respuesta para el SOC (mínimo 10 caracteres)
            <textarea rows={2} value={respuesta} onChange={(e) => setRespuesta(e.target.value)} maxLength={800} />
          </label>
          {error && <p className="error-linea">{error}</p>}
          <button
            className="boton"
            disabled={respuesta.trim().length < 10}
            onClick={() =>
              api
                .gestionarTicket(t.codigo, estado, respuesta)
                .then(alCambiar)
                .catch((e: Error) => setError(e.message))
            }
          >
            Guardar
          </button>
        </div>
      )}
      {!esTi && !cerrado && <p className="nota">TI recibió el aviso. Aquí verás su respuesta.</p>}
    </Panel>
  )
}
