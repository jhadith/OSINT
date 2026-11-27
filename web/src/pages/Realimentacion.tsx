import { RefreshCw, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import type { CasoReferencia, Metrica, Realimentacion, ResultadoRecalibrar } from '../api/types'
import { Carga, Cifra, Pagina, Panel } from '../components/ui'
import { fFechaHora, pct } from '../lib/format'
import { useApi } from '../lib/useApi'

const ESTADO_CASO: Record<CasoReferencia['estado'], string> = {
  confirmada: 'Confirmada',
  descartada: 'Descartada',
  pendiente: 'Por decidir',
}

function Formula({ m, nombre }: { m: Metrica; nombre: string }) {
  return (
    <li>
      <strong>{nombre}:</strong> <span className="mono">{m.formula}</span>. {m.explicacion}
    </li>
  )
}

function Recalibraciones({ lista }: { lista: Realimentacion['recalibraciones'] }) {
  if (!lista.length)
    return (
      <p className="nota">
        Todavía no se ha recalibrado nada. Cada recalibración queda aquí con quién la hizo, por qué y
        qué umbral cambió; la bitácora conserva el detalle completo.
      </p>
    )
  return (
    <div className="tabla-scroll">
      <table className="tabla">
        <thead>
          <tr>
            <th>Cuándo</th>
            <th>Quién</th>
            <th>Motivo</th>
            <th>Umbrales ajustados</th>
            <th>Modelo</th>
          </tr>
        </thead>
        <tbody>
          {lista.map((r, i) => (
            <tr key={`${r.fecha}-${i}`}>
              <td className="mono">{fFechaHora(r.fecha)}</td>
              <td>
                {r.actor}
                <br />
                <span className="muted">{r.rol}</span>
              </td>
              <td>
                {r.motivo}
                <br />
                <span className="muted">{r.fps.length} falso(s) positivo(s) aplicados</span>
              </td>
              <td className="mono">
                {r.cambios.length
                  ? r.cambios.map((c) => `${c.clave}: ${c.antes} → ${c.despues}`).join('\n')
                  : '—'}
              </td>
              <td>
                {r.reentrenamiento && (r.reentrenamiento.firewall || r.reentrenamiento.sistema_medico)
                  ? 'Reentrenado con el histórico acumulado'
                  : 'Sin reentrenar'}
                {r.reentrenamiento?.notas?.length ? (
                  <>
                    <br />
                    <span className="muted">{r.reentrenamiento.notas.join(' ')}</span>
                  </>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Recalibrar({ alTerminar }: { alTerminar: () => void }) {
  const [motivo, setMotivo] = useState('')
  const [confirmando, setConfirmando] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState('')
  const [resultado, setResultado] = useState<ResultadoRecalibrar | null>(null)

  async function recalibrar() {
    setEnviando(true)
    setError('')
    try {
      const r = await api.recalibrar(motivo.trim())
      setResultado(r)
      setMotivo('')
      setConfirmando(false)
      alTerminar()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo recalibrar.')
      setConfirmando(false)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Panel
      titulo={
        <>
          <SlidersHorizontal size={18} aria-hidden /> Recalibrar umbrales
        </>
      }
      bajada="Nada se recalibra solo: este es el único camino que cambia rules/*.yml, y siempre con motivo."
    >
      <p className="nota">
        Se ajustará un paso del 10 % (mínimo 1) sobre el umbral de la regla que produjo cada falso
        positivo descartado. Los falsos positivos ya aplicados no se repiten. Todo queda en la
        bitácora con tu nombre, y de paso se acumulan las ventanas del análisis activo y se
        reentrena el modelo con el histórico.
      </p>
      <label className="campo">
        Motivo del ajuste (mínimo 10 caracteres)
        <textarea rows={3} value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={500} />
      </label>
      {error && <p className="error-linea">{error}</p>}
      <div className="botones">
        {confirmando ? (
          <>
            <button className="boton" disabled={enviando} onClick={recalibrar}>
              {enviando ? 'Recalibrando…' : 'Sí, editar rules/*.yml'}
            </button>
            <button className="boton boton--secundario" disabled={enviando} onClick={() => setConfirmando(false)}>
              Cancelar
            </button>
          </>
        ) : (
          <button className="boton" disabled={motivo.trim().length < 10 || enviando} onClick={() => setConfirmando(true)}>
            Recalibrar umbrales
          </button>
        )}
      </div>
      {confirmando && (
        <p className="nota">
          Vas a editar <span className="mono">rules/*.yml</span> en este equipo. ¿Confirmas el cambio?
        </p>
      )}
      {resultado && (
        <div className="aviso aviso--info" role="status">
          <RefreshCw size={20} aria-hidden />
          <div>
            <p>{resultado.nota}</p>
            {resultado.cambios.length > 0 && (
              <p className="mono">
                {resultado.cambios.map((c) => `${c.archivo} · ${c.clave}: ${c.antes} → ${c.despues}`).join(' · ')}
              </p>
            )}
            {resultado.sinUmbral.length > 0 && (
              <p>
                Sin umbral ajustable: {resultado.sinUmbral.map((s) => s.nota).join(' · ')}
              </p>
            )}
            {resultado.reentrenamiento?.notas?.length ? (
              <p className="muted">{resultado.reentrenamiento.notas.join(' ')}</p>
            ) : null}
          </div>
        </div>
      )}
    </Panel>
  )
}

export default function RealimentacionPagina() {
  const { st, reintentar } = useApi(api.realimentacion)
  return (
    <Pagina
      titulo="Realimentación del modelo y las reglas"
      bajada="Las decisiones del analista y los falsos positivos afinan umbrales y modelo. Aquí se ve qué mide cada métrica, qué se recalibró y cuándo; nada corre en automático."
      acciones={
        <button className="boton boton--secundario" onClick={reintentar}>
          Actualizar
        </button>
      }
    >
      <Carga st={st} reintentar={reintentar} filas={6}>
        {(d) => (
          <>
            <div className="cifras">
              <Cifra valor={pct(d.precision.valor)} etiqueta="Precisión" nota={d.precision.explicacion} />
              <Cifra valor={pct(d.recall.valor)} etiqueta="Exhaustividad (recall)" nota={d.recall.explicacion} />
              <Cifra valor={pct(d.f1.valor)} etiqueta="F1" nota={d.f1.explicacion} />
            </div>

            <Panel titulo="Cómo se calcula">
              <ul className="garantias">
                <Formula m={d.precision} nombre="Precisión" />
                <Formula m={d.recall} nombre="Exhaustividad (recall)" />
                <Formula m={d.f1} nombre="F1" />
              </ul>
              <p className="nota">
                Los casos de referencia son las alertas etiquetadas con <span className="mono">caso</span> (los casos
                del informe): el único ground truth disponible. Como esos casos los generó el propio sistema, el recall
                mide qué mantuvo el analista al revisarlos, no cuánto detectó el modelo. Si algo no es calculable, sale
                como «—» con la razón, nunca como un número inventado.
              </p>
              <p className="nota">
                Decisiones contadas: {d.precision.confirmadas ?? 0} confirmadas y {d.precision.descartadas ?? 0}{' '}
                descartadas · Casos de referencia: {d.recall.casosConocidos ?? 0} ({d.recall.decididos ?? 0} decididos,{' '}
                {d.recall.confirmados ?? 0} confirmados).
              </p>
            </Panel>

            <Panel titulo="Casos de referencia" bajada="Los casos etiquetados como caso en las alertas del análisis activo.">
              {d.casosConocidos.length ? (
                <div className="tabla-scroll">
                  <table className="tabla">
                    <thead>
                      <tr>
                        <th>Caso</th>
                        <th>Título</th>
                        <th>Estado de la decisión</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.casosConocidos.map((c) => (
                        <tr key={c.caso}>
                          <td className="mono">{c.caso}</td>
                          <td>{c.titulo}</td>
                          <td>
                            <span className="chip">{ESTADO_CASO[c.estado]}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="nota">Sin análisis activo: aún no hay casos de referencia que revisar.</p>
              )}
            </Panel>

            <Panel titulo="Histórico de recalibraciones" bajada="Desde la bitácora, que es solo-append: no se puede editar ni borrar.">
              <Recalibraciones lista={d.recalibraciones} />
            </Panel>

            <Panel titulo="Reentrenamiento con histórico" bajada="El modelo se reentrena con todas las ventanas acumuladas y la semilla de rules/ml.yml (42): mismos datos, mismo modelo.">
              <div className="cifras">
                <Cifra valor={d.historico.firewall} etiqueta="ventanas acumuladas del firewall" />
                <Cifra valor={d.historico.sistema_medico} etiqueta="ventanas acumuladas del sistema médico" />
              </div>
              <p className="nota">
                Las ventanas se acumulan (sin duplicar) solo cuando alguien recalibra de forma explícita; este panel no
                acumula ni reentrena nada por sí solo.
              </p>
            </Panel>

            <Recalibrar alTerminar={reintentar} />
          </>
        )}
      </Carga>
    </Pagina>
  )
}
