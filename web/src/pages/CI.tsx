import { CircleCheck, CircleX, GitBranch, GitCommitHorizontal, Play, ShieldCheck } from 'lucide-react'
import { api } from '../api/client'
import type { CheckCI, EstadoCI, ResultadoCI } from '../api/types'
import { Carga, Cifra, Pagina, Panel } from '../components/ui'
import { useApi } from '../lib/useApi'

/** Cada job de Actions se resume con una etiqueta y el color del sistema ya existente. */
const RESULTADO: Record<ResultadoCI, { texto: string; chip: string }> = {
  success: { texto: 'Pasó', chip: 'legitimo' },
  failure: { texto: 'Falló', chip: 'critica' },
  cancelled: { texto: 'Cancelado', chip: 'critica' },
  skipped: { texto: 'Omitido', chip: 'neutro' },
}

const RESUMEN: Record<EstadoCI['estado'], { titulo: string; detalle: string; aviso: string }> = {
  correcto: {
    titulo: 'Todas las pruebas pasaron',
    detalle: 'La última ejecución terminó sin fallos ni pasos omitidos.',
    aviso: 'aviso--info',
  },
  parcial: {
    titulo: 'Hay pruebas omitidas',
    detalle: 'Ninguna prueba falló, pero algunos jobs no llegaron a ejecutarse. Revisa por qué antes de liberar.',
    aviso: 'aviso--hipotesis',
  },
  fallido: {
    titulo: 'Hay pruebas que fallaron',
    detalle: 'La ejecución no está en verde. Revisa los jobs marcados en rojo antes de liberar.',
    aviso: 'aviso--error',
  },
  sin_datos: {
    titulo: 'Sin resultados todavía',
    detalle: 'El resumen de la ejecución aún no está disponible.',
    aviso: 'aviso--info',
  },
}

function Fila({ check }: { check: CheckCI }) {
  const r = RESULTADO[check.resultado]
  return (
    <tr className={check.resultado === 'failure' || check.resultado === 'cancelled' ? 'fila--alerta' : ''}>
      <td className="mono nowrap">{check.id || '—'}</td>
      <td>{check.nombre || '—'}</td>
      <td>
        <span className={`chip chip--${r.chip}`}>{r.texto}</span>
      </td>
      <td>{check.detalle || '—'}</td>
    </tr>
  )
}

export default function CI() {
  const { st, reintentar } = useApi(api.ciEstado)
  return (
    <Pagina
      titulo="Estado de CI"
      bajada="Resultado de los controles automáticos de GitHub Actions en la última ejecución. Lo genera el pipeline; no se consulta GitHub en vivo."
      acciones={
        <button className="boton boton--secundario" onClick={reintentar}>
          Actualizar
        </button>
      }
    >
      <Carga st={st} reintentar={reintentar}>
        {(d) => {
          if (!d.disponible)
            return (
              <div className="aviso aviso--info" role="status">
                <ShieldCheck size={20} aria-hidden />
                <div>
                  <strong>{RESUMEN[d.estado].titulo}</strong>
                  <p>{RESUMEN[d.estado].detalle}</p>
                </div>
              </div>
            )
          const total = d.checks.length
          const pasaron = d.checks.filter((c) => c.resultado === 'success').length
          const fallaron = d.checks.filter((c) => c.resultado === 'failure' || c.resultado === 'cancelled').length
          const omitidos = d.checks.filter((c) => c.resultado === 'skipped').length
          const resumen = RESUMEN[d.estado]
          return (
            <>
              <div className={`aviso ${resumen.aviso}`} role={d.estado === 'fallido' ? 'alert' : 'status'}>
                {d.estado === 'fallido' ? (
                  <CircleX size={20} aria-hidden />
                ) : d.estado === 'sin_datos' ? (
                  <ShieldCheck size={20} aria-hidden />
                ) : (
                  <CircleCheck size={20} aria-hidden />
                )}
                <div>
                  <strong>{resumen.titulo}</strong>
                  <p>{resumen.detalle}</p>
                </div>
              </div>

              <div className="rejilla rejilla--dos">
                <Panel titulo="Última ejecución" bajada="De dónde viene este resumen">
                  <dl className="ficha-datos">
                    <div>
                      <dt>Generado</dt>
                      <dd className="mono">{d.generado || '—'}</dd>
                    </div>
                    <div>
                      <dt>Ejecución</dt>
                      <dd className="mono">{d.ejecucion || '—'}</dd>
                    </div>
                    <div>
                      <dt>
                        <GitBranch size={14} aria-hidden /> Rama
                      </dt>
                      <dd className="mono">{d.rama || '—'}</dd>
                    </div>
                    <div>
                      <dt>
                        <GitCommitHorizontal size={14} aria-hidden /> Commit
                      </dt>
                      <dd className="mono">{d.commit || '—'}</dd>
                    </div>
                    <div>
                      <dt>Origen</dt>
                      <dd className="mono">{d.origen || '—'}</dd>
                    </div>
                  </dl>
                </Panel>
                <Panel titulo="Resultado general" bajada="Conteo de los jobs del pipeline">
                  <div className="rejilla rejilla--ejecutiva">
                    <Cifra valor={total} etiqueta="Controles" />
                    <Cifra valor={pasaron} etiqueta="Pasaron" />
                    <Cifra valor={fallaron} etiqueta="Fallaron o se cancelaron" />
                    <Cifra valor={omitidos} etiqueta="Omitidos" />
                  </div>
                  <p className="nota">
                    <Play size={14} aria-hidden /> Un job omitido puede significar que se saltó una puerta de seguridad.
                  </p>
                </Panel>
              </div>

              <Panel titulo="Controles ejecutados" bajada="Uno por job del workflow de DevSecOps">
                <div className="tabla-scroll">
                  <table className="tabla">
                    <thead>
                      <tr>
                        <th>Job</th>
                        <th>Control</th>
                        <th>Resultado</th>
                        <th>Detalle</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.checks.map((check) => (
                        <Fila key={check.id} check={check} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>

              <p className="nota">
                {d.origen === 'ejemplo'
                  ? 'Estos datos son de ejemplo para probar la pantalla. Al terminar la siguiente ejecución, el pipeline los reemplaza con los resultados reales.'
                  : 'Los datos los escribe el job resumen-ci al terminar la ejecución.'}
              </p>
            </>
          )
        }}
      </Carga>
    </Pagina>
  )
}
