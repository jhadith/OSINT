import { CircleHelp, Megaphone, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Agenda, CasoAgenda, EstadoHBVF } from '../api/types'
import { Carga, Cifra, EstadoAgenda, Medidor, Pagina, Panel } from '../components/ui'
import { ESTADO_HBVF, fFecha, fFechaHora, num, pct } from '../lib/format'
import { useSesion } from '../lib/sesion'
import { useApi } from '../lib/useApi'

const FAMILIA: Record<string, string> = {
  volumen: 'Volumen',
  ritmo: 'Ritmo',
  ciclo_de_cita: 'Ciclo de la cita',
  momento: 'Momento',
  tecnica: 'Técnica (vale la mitad)',
  externa: 'Reporte externo',
}
const PATRON_ESTADO = {
  presente: { texto: 'Presente', clase: 'presente' },
  ausente: { texto: 'No', clase: 'ausente' },
  desconocido: { texto: 'Sin datos', clase: 'desconocido' },
  explicado: { texto: 'Explicado', clase: 'explicado' },
} as const
const CANAL: Record<string, string> = { web: 'chat de la página web', whatsapp: 'WhatsApp', call_center: 'centro de llamadas' }

type Filtro = 'revision' | 'observacion' | 'explicado' | 'todos'

export default function Agendamiento() {
  const { st, reintentar, actualizar } = useApi(api.agenda)
  return (
    <Pagina
      titulo="Citas del chatbot"
      bajada="Buscamos orígenes que reservan citas para muchos pacientes, como lo haría un tramitador. Nada se cancela ni se bloquea solo: cada caso pasa por una persona."
    >
      <Carga st={st} reintentar={reintentar} filas={8}>
        {(a) => (
          <Vista
            a={a}
            alRevisar={(id, rev) =>
              actualizar((x) => ({ ...x, casos: x.casos.map((c) => (c.case_id === id ? { ...c, revision: rev } : c)) }))
            }
          />
        )}
      </Carga>
    </Pagina>
  )
}

function Vista({ a, alRevisar }: { a: Agenda; alRevisar: (id: string, r: NonNullable<CasoAgenda['revision']>) => void }) {
  const [filtro, setFiltro] = useState<Filtro>('revision')
  const casos = useMemo(
    () =>
      [...a.casos].sort(
        (x, y) => ESTADO_HBVF[x.status].orden - ESTADO_HBVF[y.status].orden || y.risk_score - x.risk_score || y.confidence - x.confidence,
      ),
    [a],
  )
  const grupos: Record<Filtro, CasoAgenda[]> = {
    revision: casos.filter((c) => c.review_required),
    observacion: casos.filter((c) => c.status === 'Observación'),
    explicado: casos.filter((c) => c.status === 'Explicado por contexto legítimo'),
    todos: casos,
  }
  const lista = grupos[filtro]
  const [sel, setSel] = useState<string | null>(null)
  const elegido = lista.find((c) => c.case_id === sel) ?? lista[0]
  const r = a.resumen
  const totalEstados = Object.values(r.estados).reduce((s, n) => s + (n ?? 0), 0) || 1

  return (
    <>
      <div className="cifras">
        <Cifra valor={num(r.reservas)} etiqueta="reservas en el periodo" nota={`${fFecha(r.periodo.desde)} a ${fFecha(r.periodo.hasta)}`} />
        <Cifra valor={num(r.sesiones)} etiqueta="conversaciones con el chatbot" />
        <Cifra valor={num(r.puntos)} etiqueta="orígenes distintos" nota="Agrupaciones, no personas" />
        <Cifra valor={num(r.revision_requerida)} etiqueta="orígenes para revisar" />
        <Cifra valor={num(r.citas_en_revision)} etiqueta="citas para confirmar con el afiliado" />
      </div>

      <Panel titulo="Cómo quedaron los orígenes" bajada="Cada origen recibe un solo estado. Los que se explican por un cuidador u operador autorizado no se marcan.">
        <div className="barra-estados" role="img" aria-label="Distribución de estados">
          {(Object.keys(ESTADO_HBVF) as EstadoHBVF[]).map((e) => {
            const n = r.estados[e] ?? 0
            if (!n) return null
            return <span key={e} className={`barra-estados__parte fondo--${ESTADO_HBVF[e].clase}`} style={{ flexGrow: Math.max(n / totalEstados, 0.025) }} />
          })}
        </div>
        <ul className="leyenda leyenda--estados">
          {(Object.keys(ESTADO_HBVF) as EstadoHBVF[]).map((e) => (
            <li key={e}>
              <span className={`punto fondo--${ESTADO_HBVF[e].clase}`} aria-hidden /> {e}: <strong>{num(r.estados[e] ?? 0)}</strong>
            </li>
          ))}
        </ul>
      </Panel>

      <div className="pestanas pestanas--grandes" role="tablist">
        {(
          [
            ['revision', 'Para revisar'],
            ['observacion', 'Observaciones'],
            ['explicado', 'Explicados'],
            ['todos', 'Todos'],
          ] as [Filtro, string][]
        ).map(([id, t]) => (
          <button key={id} role="tab" aria-selected={filtro === id} onClick={() => { setFiltro(id); setSel(null) }}>
            {t} <span className="contador">{grupos[id].length}</span>
          </button>
        ))}
      </div>

      <div className="rejilla rejilla--agenda">
        <ul className="origenes">
          {lista.map((c) => (
            <li key={c.case_id}>
              <button className={`origen ${elegido?.case_id === c.case_id ? 'origen--sel' : ''}`} onClick={() => setSel(c.case_id)}>
                <span className="origen__fila">
                  <EstadoAgenda e={c.status} />
                  <span className="mono">{c.case_id}</span>
                </span>
                <span className="origen__frase">
                  {num(c.resumen.pacientes)} pacientes distintos, {num(c.resumen.reservas)} reservas por {CANAL[c.resumen.canales] ?? c.resumen.canales}
                </span>
                <span className="origen__pat">
                  {c.pattern_ids.map((p) => (
                    <span key={p} className="pildora">
                      {p}
                    </span>
                  ))}
                  {c.denuncias_vinculadas.length > 0 && (
                    <span className="pildora pildora--denuncia">
                      <Megaphone size={12} aria-hidden /> denuncia
                    </span>
                  )}
                  {c.revision && <span className="pildora pildora--revisado">revisado</span>}
                </span>
              </button>
            </li>
          ))}
          {!lista.length && <li className="muted">No hay orígenes en este grupo.</li>}
        </ul>
        {elegido && <DetalleOrigen key={elegido.case_id} c={elegido} a={a} alRevisar={alRevisar} />}
      </div>

      <Panel titulo="Patrones que buscamos" bajada="Indicadores de la misma familia no cuentan como pruebas independientes. Si falta un dato, el patrón queda «sin datos», nunca como culpa.">
        <div className="tabla-scroll">
          <table className="tabla">
            <thead>
              <tr>
                <th>Patrón</th>
                <th>Familia</th>
                <th>Puede ser legítimo si…</th>
                <th>Se valida con</th>
              </tr>
            </thead>
            <tbody>
              {a.catalogo.map((p) => (
                <tr key={p.id}>
                  <td>
                    <strong className="mono">{p.id}</strong> {p.nombre}
                    <div className="muted">{p.fuente}</div>
                  </td>
                  <td>{FAMILIA[p.familia] ?? p.familia}</td>
                  <td>{p.contexto_legitimo}</td>
                  <td>{p.validacion}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="rejilla rejilla--dos">
        {a.evaluacion && (
          <Panel titulo="Prueba preliminar" bajada={a.evaluacion.nota}>
            <div className="confusion">
              <div className="confusion__celda confusion__celda--bien">
                <strong>{a.evaluacion.matriz.vp}</strong> tramitadores encontrados
              </div>
              <div className="confusion__celda confusion__celda--mal">
                <strong>{a.evaluacion.matriz.fn}</strong> tramitadores no encontrados
              </div>
              <div className="confusion__celda confusion__celda--mal">
                <strong>{a.evaluacion.matriz.fp}</strong> personas legítimas marcadas
              </div>
              <div className="confusion__celda confusion__celda--bien">
                <strong>{num(a.evaluacion.matriz.vn)}</strong> legítimos sin marcar
              </div>
            </div>
            <p className="nota">
              Precisión {pct(a.evaluacion.precision)}, sensibilidad {pct(a.evaluacion.sensibilidad)}, falsos positivos{' '}
              {pct(a.evaluacion.tasa_falsos_positivos)}, F1 {pct(a.evaluacion.f1)}. Con datos sintéticos no se demuestra eficacia real.
            </p>
          </Panel>
        )}
        <Panel titulo={<><ShieldCheck size={18} aria-hidden /> Reglas que respetamos</>}>
          <ul className="principios">
            {a.principios.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  )
}

function DetalleOrigen({
  c,
  a,
  alRevisar,
}: {
  c: CasoAgenda
  a: Agenda
  alRevisar: (id: string, r: NonNullable<CasoAgenda['revision']>) => void
}) {
  const { puede } = useSesion()
  const s = c.resumen
  const datos: [string, string][] = [
    ['Canal', CANAL[s.canales] ?? s.canales],
    ['Conversaciones', num(s.sesiones)],
    ['Pacientes distintos', num(s.pacientes)],
    ['Reservas', num(s.reservas)],
    ['Reservas en los primeros minutos de agenda', num(s.reservas_al_abrir)],
    ['Cancelaciones', num(s.cancelaciones)],
    ['Citas reasignadas enseguida', num(s.reasignaciones)],
    ['IPs distintas', s.ips ? num(s.ips) : 'Sin datos técnicos'],
    ['Tiempo de respuesta típico', s.respuesta_mediana_ms != null ? `${num(Math.round(s.respuesta_mediana_ms / 100) / 10)} s` : 'Sin datos'],
    ['Representación autorizada', s.representacion_autorizada ? `Sí (${s.rol_declarado ?? 'registrada'})` : 'No registrada'],
  ]
  return (
    <Panel
      className="detalle-origen"
      titulo={
        <>
          <span className="mono">{c.case_id}</span> <EstadoAgenda e={c.status} />
        </>
      }
      bajada={`Activo del ${fFechaHora(s.inicio)} al ${fFechaHora(s.fin)}. Un origen es una agrupación de sesiones, no una persona identificada.`}
    >
      <div className="medidores">
        <Medidor valor={c.anomaly_score} texto="Qué tan raro es comparado con el resto" tono="azul" />
        <Medidor valor={c.confidence} texto="Qué tan sólida es la evidencia" tono="verde" />
        <Medidor valor={c.risk_score} max={25} texto="Riesgo (probabilidad × impacto)" tono={c.risk_score >= 20 ? 'rojo' : c.risk_score >= 12 ? 'naranja' : 'amarillo'} />
      </div>

      <h3>Patrones</h3>
      <ul className="patrones">
        {a.catalogo.map((p) => {
          const e = c.patrones[p.id] ?? 'ausente'
          const x = PATRON_ESTADO[e]
          return (
            <li key={p.id} className={`patron patron--${x.clase}`}>
              <span className="patron__estado">{x.texto}</span>
              <span>
                <span className="mono">{p.id}</span> {p.nombre}
              </span>
            </li>
          )
        })}
      </ul>

      <dl className="ficha-datos">
        {datos.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>

      {c.denuncias_vinculadas.length > 0 && (
        <div className="aviso aviso--info">
          <Megaphone size={20} aria-hidden />
          <div>
            <strong>Un afiliado denunció este contacto.</strong> El número que reportó coincide con el que usa este origen.{' '}
            {c.denuncias_vinculadas.map((d) => (
              <Link key={d} to="/denuncias" className="enlace mono">
                {d}
              </Link>
            ))}
          </div>
        </div>
      )}

      {c.legitimate_explanations.length > 0 && (
        <>
          <h3>
            <CircleHelp size={16} aria-hidden /> Antes de actuar, descarta que sea…
          </h3>
          <ul className="lista-evidencia">
            {c.legitimate_explanations.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </>
      )}

      {c.recommendations.length > 0 && (
        <>
          <h3>Qué hacer (ninguna acción es automática)</h3>
          <ol className="acciones">
            {c.recommendations.map((m) => (
              <li key={m.id}>{m.texto}</li>
            ))}
          </ol>
        </>
      )}

      {c.citas_en_revision.length > 0 && (
        <p className="nota">
          {num(c.citas_en_revision.length)} citas para confirmar con el afiliado: <span className="mono">{c.citas_en_revision.slice(0, 4).join(', ')}</span>
          {c.citas_en_revision.length > 4 ? '…' : ''}
        </p>
      )}

      {c.revision && (
        <p className="decision-previa">
          Revisado por {c.revision.analista} el {fFechaHora(c.revision.fecha)}: <strong>{REV[c.revision.decision] ?? c.revision.decision}</strong>.{' '}
          {c.revision.nota}
        </p>
      )}
      {puede('decidir') && c.status !== 'Sin hallazgo' && <Revisar c={c} alRevisar={alRevisar} />}
    </Panel>
  )
}

const REV: Record<string, string> = {
  en_revision: 'En revisión',
  explicado: 'Explicado, es legítimo',
  descartado: 'Descartado',
  confirmado: 'Tramitador confirmado',
}

function Revisar({ c, alRevisar }: { c: CasoAgenda; alRevisar: (id: string, r: NonNullable<CasoAgenda['revision']>) => void }) {
  const [decision, setDecision] = useState('en_revision')
  const [nota, setNota] = useState('')
  const [error, setError] = useState('')
  return (
    <div className="revisar">
      <h3>Tu revisión</h3>
      <div className="opciones">
        {Object.entries(REV).map(([k, t]) => (
          <button key={k} type="button" className={`opcion ${decision === k ? 'opcion--sel' : ''}`} aria-pressed={decision === k} onClick={() => setDecision(k)}>
            {t}
          </button>
        ))}
      </div>
      <label className="campo">
        Nota (mínimo 10 caracteres)
        <textarea rows={2} value={nota} onChange={(e) => setNota(e.target.value)} maxLength={500} />
      </label>
      {error && <p className="error-linea">{error}</p>}
      <button
        className="boton"
        disabled={nota.trim().length < 10}
        onClick={() =>
          api
            .revisarAgenda(c.case_id, decision, nota)
            .then((r) => {
              alRevisar(c.case_id, r)
              setNota('')
            })
            .catch((e: Error) => setError(e.message))
        }
      >
        Guardar revisión
      </button>
    </div>
  )
}
