import { ArrowLeft, BellRing, EyeOff, ShieldAlert, UserSearch } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Caso, Evidencia } from '../api/types'
import { Carga, Gravedad, Pagina, Panel, Rango } from '../components/ui'
import { bandera, ESTADO_CASO, fFechaHora, num } from '../lib/format'
import { useSesion } from '../lib/sesion'
import { useApi } from '../lib/useApi'

export default function CasoDetalle() {
  const { id = '' } = useParams()
  const { st, reintentar, actualizar } = useApi(() => api.caso(id), [id])
  return (
    <Carga st={st} reintentar={reintentar} filas={8}>
      {(c) => <Detalle c={c} alDecidir={(d) => actualizar((x) => ({ ...x, estado: d.estado, decision: d }))} />}
    </Carga>
  )
}

function Detalle({ c, alDecidir }: { c: Caso; alDecidir: (d: NonNullable<Caso['decision']>) => void }) {
  const { puede } = useSesion()
  return (
    <Pagina
      titulo={c.titulo}
      bajada={
        <>
          <Link to="/casos" className="enlace">
            <ArrowLeft size={14} aria-hidden /> Casos
          </Link>{' '}
          {c.id}, {c.tipo}. Empezó el {fFechaHora(c.inicio)} y duró {c.duracion}.
        </>
      }
      acciones={
        <>
          <Gravedad g={c.gravedad} />
          <span className={`estado estado--${c.estado}`}>{ESTADO_CASO[c.estado]}</span>
        </>
      }
    >
      <div className="rejilla rejilla--caso">
        <div className="pila">
          <Panel titulo="Qué tan fuera de lo normal fue" bajada="Como un examen de laboratorio: la franja verde es el rango normal del mes.">
            <ul className="mediciones">
              {c.explicacion.map((m) => {
                const b = bandera(m.valor, m.refMin, m.refMax)
                return (
                  <li key={m.nombre}>
                    <div className="mediciones__fila">
                      <span>{m.nombre}</span>
                      <strong className={b ? 't-critica' : ''}>
                        {num(m.valor)} {m.unidad} {b && <span className="bandera">{b === 'H' ? 'Alto' : 'Bajo'}</span>}
                      </strong>
                    </div>
                    <Rango valor={m.valor} min={m.refMin} max={m.refMax} unidad={m.unidad} />
                    <div className="mediciones__ref">
                      Normal: {num(m.refMin)} a {num(m.refMax)} {m.unidad}
                      {m.nota ? `. ${m.nota}` : ''}
                    </div>
                  </li>
                )
              })}
            </ul>
          </Panel>

          <Panel titulo="Recorrido del caso" bajada="De los datos crudos a la decisión.">
            <ol className="recorrido">
              {c.recorrido.map((r) => (
                <li key={r.paso}>
                  <strong>{r.paso}</strong>
                  <span>{r.detalle}</span>
                </li>
              ))}
            </ol>
          </Panel>

          {c.firewall && <TablaEvidencia e={c.firewall} titulo="Lo que vio el firewall" />}
          {c.sistemaMedico && <TablaEvidencia e={c.sistemaMedico} titulo="Lo que vio el sistema médico" />}
        </div>

        <div className="pila">
          <Panel titulo="Qué hacer">
            <ol className="acciones">
              {c.acciones.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ol>
          </Panel>

          {puede('decidir') ? (
            <Decidir c={c} alDecidir={alDecidir} />
          ) : (
            c.decision && (
              <Panel titulo="Decisión del analista">
                <p>
                  <strong>{ESTADO_CASO[c.decision.estado]}</strong> por {c.decision.analista} el {fFechaHora(c.decision.fecha)}.
                </p>
                <p>{c.decision.motivo}</p>
              </Panel>
            )
          )}

          {c.alerta && (
            <Panel titulo={<><BellRing size={18} aria-hidden /> Aviso al equipo de guardia</>}>
              <p className="nota">
                {c.alerta.enviada ? 'Enviado por Telegram' : 'Generado en modo simulación (sin token de Telegram configurado)'} el{' '}
                {fFechaHora(c.alerta.fecha)}. No lleva datos personales.
              </p>
              <pre className="telegram">{c.alerta.texto}</pre>
            </Panel>
          )}

          <Panel titulo="Cómo se detectó">
            <p className="chips">
              {c.detectadoPor.map((d) => (
                <span key={d} className="etiqueta etiqueta--verde">
                  {d}
                </span>
              ))}
            </p>
            {c.modelo && (
              <p className="nota">
                El modelo lo puso en el puesto {num(c.modelo.puesto)} de {num(c.modelo.total)} ventanas de tiempo por lo raro que fue
                (puntuación {Math.round(c.modelo.puntuacion * 100)} de 100).
              </p>
            )}
            <h3>Técnicas de ataque (MITRE ATT&amp;CK)</h3>
            <ul className="tecnicas">
              {c.tecnicas.map((t) => (
                <li key={t.id}>
                  <span className="mono">{t.id}</span> {t.nombre}
                </li>
              ))}
            </ul>
            <p className="casos-ligados">
              Riesgos relacionados:{' '}
              {c.riesgos.map((r) => (
                <Link key={r} to="/riesgos" className="enlace">
                  {r}
                </Link>
              ))}
            </p>
          </Panel>

          {puede('reidentificar') && <Reidentificar seudonimo={c.seudonimo} />}
          {c.calidadDatos.length > 0 && (
            <Panel titulo="Calidad de los datos">
              <ul>
                {c.calidadDatos.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>
    </Pagina>
  )
}

const COLUMNA: Record<string, string> = {
  ip_origen: 'IP de origen',
  ip_destino: 'IP de destino',
  puerto: 'Puerto',
  protocolo: 'Protocolo',
  aplicacion: 'Aplicación',
  accion: 'Acción',
  cuenta: 'Cuenta',
  usuario: 'Persona (seudónimo)',
  evento: 'Evento',
  ip: 'IP',
}

function TablaEvidencia({ e, titulo }: { e: Evidencia; titulo: string }) {
  const cols = Object.keys(e.registros[0]?.campos ?? {})
  return (
    <Panel titulo={titulo} bajada={e.resumen}>
      <div className="tabla-scroll">
        <table className="tabla tabla--densa">
          <thead>
            <tr>
              <th>Hora</th>
              {cols.map((k) => (
                <th key={k}>{COLUMNA[k] ?? k.replace('_', ' ')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {e.registros.map((r, i) => (
              <tr key={i}>
                <td className="mono">{r.ts.slice(11)}</td>
                {cols.map((k) => (
                  <td key={k} className={/ip|puerto|cuenta|usuario/.test(k) ? 'mono' : ''}>
                    {r.campos[k]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="nota">
        <EyeOff size={14} aria-hidden /> Las personas aparecen con seudónimo; los nombres reales no salen del motor. Se muestran los primeros registros.
      </p>
    </Panel>
  )
}

function Decidir({ c, alDecidir }: { c: Caso; alDecidir: (d: NonNullable<Caso['decision']>) => void }) {
  const [motivo, setMotivo] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  async function decidir(estado: 'confirmado' | 'descartado') {
    setEnviando(true)
    setError('')
    try {
      const r = await api.decidir(c.id, estado, motivo)
      alDecidir({ estado: r.estado as 'confirmado' | 'descartado', motivo: r.motivo, analista: r.analista, fecha: r.fecha })
      setMotivo('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar.')
    } finally {
      setEnviando(false)
    }
  }
  return (
    <Panel titulo="Tu decisión" bajada="Confirmar o descartar cambia la matriz de riesgos y la vista ejecutiva.">
      {c.decision && (
        <p className="decision-previa">
          Última decisión: <strong>{ESTADO_CASO[c.decision.estado]}</strong> por {c.decision.analista}, {fFechaHora(c.decision.fecha)}.
          <br />
          {c.decision.motivo}
        </p>
      )}
      <label className="campo">
        Motivo (mínimo 10 caracteres)
        <textarea rows={3} value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={500} />
      </label>
      {error && <p className="error-linea">{error}</p>}
      <div className="botones">
        <button className="boton" disabled={motivo.trim().length < 10 || enviando} onClick={() => decidir('confirmado')}>
          Confirmar incidente
        </button>
        <button className="boton boton--secundario" disabled={motivo.trim().length < 10 || enviando} onClick={() => decidir('descartado')}>
          Descartar
        </button>
      </div>
    </Panel>
  )
}

function Reidentificar({ seudonimo }: { seudonimo: string }) {
  const [motivo, setMotivo] = useState('')
  const [r, setR] = useState<{ nombre: string; registradoEn: string } | null>(null)
  const [error, setError] = useState('')
  return (
    <Panel className="panel--sensible" titulo={<><UserSearch size={18} aria-hidden /> Ver la persona detrás del seudónimo</>}>
      <p className="nota">
        <ShieldAlert size={14} aria-hidden /> Solo con un motivo de investigación. Tu nombre, el motivo y la hora quedan en la bitácora
        que revisa auditoría.
      </p>
      {r ? (
        <div className="reid">
          <span className="mono">{seudonimo}</span> corresponde a <strong>{r.nombre}</strong>
          <p className="nota">Registrado en la bitácora el {fFechaHora(r.registradoEn)}.</p>
        </div>
      ) : (
        <>
          <label className="campo">
            <span>
              Motivo para ver a <span className="mono">{seudonimo}</span> (mínimo 15 caracteres)
            </span>
            <textarea rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={500} />
          </label>
          {error && <p className="error-linea">{error}</p>}
          <button
            className="boton boton--secundario"
            disabled={motivo.trim().length < 15}
            onClick={() =>
              api
                .reidentificar(seudonimo, motivo)
                .then(setR)
                .catch((e: Error) => setError(e.message))
            }
          >
            Reidentificar y registrar
          </button>
        </>
      )}
    </Panel>
  )
}
