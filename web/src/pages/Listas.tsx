import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import type { EstadoSolicitud, TipoLista } from '../api/types'
import { Carga, Pagina, Panel } from '../components/ui'
import { fFechaHora } from '../lib/format'
import { useApi } from '../lib/useApi'

const ESTADO_SOLICITUD: Record<EstadoSolicitud, { texto: string; clase: string }> = {
  PENDIENTE: { texto: 'Pendiente', clase: 'estado' },
  APROBADA: { texto: 'Aprobada', clase: 'etiqueta etiqueta--verde' },
  RECHAZADA: { texto: 'Rechazada', clase: 'estado estado--confirmado' },
}

/** Mínimo del motivo de resolución, igual que en el backend (Field min_length=10). */
const MIN_MOTIVO = 10

export default function Listas() {
  const cat = useApi(api.listasIndicadores)
  const sol = useApi(api.listasSolicitudes)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')

  async function refrescar() {
    const [indicadores, solicitudes] = await Promise.all([api.listasIndicadores(), api.listasSolicitudes()])
    cat.actualizar(() => indicadores)
    sol.actualizar(() => solicitudes)
  }

  /** Ejecuta una operación y recarga ambas bandejas; el error queda en la página. */
  async function manejar(operacion: () => Promise<unknown>, mensaje: string) {
    setError('')
    setOk('')
    try {
      await operacion()
      await refrescar()
      setOk(mensaje)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo completar la operación.')
    }
  }

  /** Aprobar o rechazar: el motivo se pide con prompt y nunca baja de 10 caracteres. */
  function resolver(id: number, aprobar: boolean) {
    const motivo = window.prompt(
      aprobar
        ? 'Motivo para aprobar la solicitud (mínimo 10 caracteres):'
        : 'Motivo para rechazar la solicitud (mínimo 10 caracteres):',
      '',
    )
    if (motivo === null) return
    if (motivo.trim().length < MIN_MOTIVO) {
      setError(`El motivo debe tener al menos ${MIN_MOTIVO} caracteres. No se cambió nada.`)
      setOk('')
      return
    }
    manejar(
      () => api.listasResolver(id, aprobar, motivo.trim()),
      aprobar ? 'Solicitud aprobada: el indicador ya está activo.' : 'Solicitud rechazada.',
    )
  }

  return (
    <Pagina
      titulo="Listas de comparación"
      bajada="Catálogo dinámico de las listas blanca y negra que usa «Verificar contenido». Se edita aquí y se aplica al instante, sin reiniciar el servidor. Toda alta, baja y resolución queda en la bitácora."
    >
      {error && <p className="error-linea">{error}</p>}
      {ok && <p className="ok-linea">{ok}</p>}

      <Panel titulo="Catálogo de indicadores" bajada="Dominios permitidos (blanca) o bloqueados (negra), con la etiqueta que explique quién los puso y por qué.">
        <AltaIndicador onAlta={(tipo, valor, etiqueta) => manejar(() => api.listasAlta(tipo, valor, etiqueta), 'Indicador guardado: ya afecta a «Verificar contenido».')} />
        <Carga st={cat.st} reintentar={cat.reintentar}>
          {(indicadores) => (
            <div className="tabla-scroll">
              <table className="tabla">
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th>Valor</th>
                    <th>Etiqueta</th>
                    <th>
                      <span className="sr">Acciones</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {indicadores.map((i) => (
                    <tr key={i.id}>
                      <td>
                        <span className={`pildora ${i.tipo === 'blanca' ? 'pildora--revisado' : 'pildora--denuncia'}`}>{i.tipo}</span>
                      </td>
                      <td className="mono quiebre">{i.valor}</td>
                      <td>{i.etiqueta || <span className="muted">Sin etiqueta</span>}</td>
                      <td>
                        <button
                          className="boton boton--secundario"
                          onClick={() => manejar(() => api.listasBaja(i.id), 'Indicador dado de baja.')}
                        >
                          <Trash2 size={15} aria-hidden /> Quitar
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!indicadores.length && (
                    <tr>
                      <td colSpan={4} className="muted">
                        El catálogo está vacío: añade el primer indicador arriba.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Carga>
      </Panel>

      <Panel
        titulo="Solicitudes"
        bajada="Peticiones de inclusión o exclusión. Aprobar o rechazar siempre exige un motivo de al menos 10 caracteres, y el rechazo no toca el catálogo."
      >
        <Carga st={sol.st} reintentar={sol.reintentar}>
          {(solicitudes) =>
            !solicitudes.length ? (
              <div className="vacio">
                <h2>No hay solicitudes</h2>
                <p>Cuando alguien pida incluir o excluir un indicador, aparecerá aquí para su resolución.</p>
              </div>
            ) : (
              <ul className="origenes">
                {solicitudes.map((s) => (
                  <li key={s.id} className="origen">
                    <span className="origen__fila">
                      <span className={ESTADO_SOLICITUD[s.estado].clase}>{ESTADO_SOLICITUD[s.estado].texto}</span>
                      <span className={`pildora ${s.tipo === 'blanca' ? 'pildora--revisado' : 'pildora--denuncia'}`}>{s.tipo}</span>
                      <span className="mono quiebre">{s.valor}</span>
                      <span className="muted">{fFechaHora(s.creado_en)}</span>
                    </span>
                    <span className="origen__frase">
                      <strong>Justificación:</strong> {s.justificacion}
                      {s.fuente && <> · Fuente: {s.fuente}</>}
                    </span>
                    {s.estado === 'PENDIENTE' ? (
                      <span className="origen__pat">
                        <button className="boton" onClick={() => resolver(s.id, true)}>
                          <Plus size={15} aria-hidden /> Aprobar
                        </button>
                        <button className="boton boton--secundario" onClick={() => resolver(s.id, false)}>
                          Rechazar
                        </button>
                      </span>
                    ) : (
                      <span className="origen__pat">
                        <span className="muted">
                          Resuelta por {s.resuelto_por || 'el SOC'}
                          {s.resuelto_en ? ` el ${fFechaHora(s.resuelto_en)}` : ''}: {s.resolucion}
                        </span>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )
          }
        </Carga>
      </Panel>
    </Pagina>
  )
}

/** Alta de indicador: tipo de lista, valor (dominio o ruta) y etiqueta. */
function AltaIndicador({ onAlta }: { onAlta: (tipo: TipoLista, valor: string, etiqueta: string) => void }) {
  const [tipo, setTipo] = useState<TipoLista>('blanca')
  const [valor, setValor] = useState('')
  const [etiqueta, setEtiqueta] = useState('')

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (valor.trim()) {
          onAlta(tipo, valor.trim(), etiqueta.trim())
          setValor('')
          setEtiqueta('')
        }
      }}
    >
      <label className="campo">
        Tipo de lista
        <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoLista)}>
          <option value="blanca">Blanca (permitido)</option>
          <option value="negra">Negra (bloqueado)</option>
        </select>
      </label>
      <label className="campo">
        Valor (dominio o ruta)
        <input value={valor} onChange={(e) => setValor(e.target.value)} placeholder="ej: hospital.gob.ec" maxLength={300} />
      </label>
      <label className="campo">
        Etiqueta (opcional)
        <input value={etiqueta} onChange={(e) => setEtiqueta(e.target.value)} placeholder="Quién lo puso y por qué" maxLength={200} />
      </label>
      <button className="boton" disabled={!valor.trim()}>
        <Plus size={16} aria-hidden /> Añadir al catálogo
      </button>
    </form>
  )
}
