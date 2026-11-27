import { CircleAlert, FolderInput, Lock } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { EstadoHBVF, Gravedad } from '../api/types'
import { ESTADO_HBVF, GRAVEDAD } from '../lib/format'
import type { Estado } from '../lib/useApi'

export function Pagina({
  titulo,
  bajada,
  acciones,
  children,
}: {
  titulo: string
  bajada?: ReactNode
  acciones?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="pagina">
      <header className="pagina__cabecera">
        <div>
          <h1>{titulo}</h1>
          {bajada && <p className="pagina__bajada">{bajada}</p>}
        </div>
        {acciones && <div className="pagina__acciones">{acciones}</div>}
      </header>
      {children}
    </div>
  )
}

export function Panel({
  titulo,
  bajada,
  extra,
  children,
  className = '',
}: {
  titulo?: ReactNode
  bajada?: ReactNode
  extra?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`panel ${className}`}>
      {(titulo || extra) && (
        <header className="panel__cabecera">
          <div>
            {titulo && <h2>{titulo}</h2>}
            {bajada && <p className="panel__bajada">{bajada}</p>}
          </div>
          {extra}
        </header>
      )}
      {children}
    </section>
  )
}

/** Muestra cargando / error / vacío según el estado de useApi. */
export function Carga<T>({
  st,
  reintentar,
  children,
  filas = 4,
}: {
  st: Estado<T>
  reintentar: () => void
  children: (d: T) => ReactNode
  filas?: number
}) {
  if (st.estado === 'cargando')
    return (
      <div className="esqueleto" aria-busy="true" aria-label="Cargando">
        {Array.from({ length: filas }, (_, i) => (
          <div key={i} className="esqueleto__fila" style={{ width: `${92 - ((i * 17) % 35)}%` }} />
        ))}
      </div>
    )
  if (st.estado === 'error') {
    if (st.codigo === 409) return <SinAnalisis mensaje={st.mensaje} />
    if (st.codigo === 403)
      return (
        <div className="vacio">
          <Lock size={28} aria-hidden />
          <h2>Esta sección no es para tu rol</h2>
          <p>{st.mensaje}</p>
        </div>
      )
    return (
      <div className="aviso aviso--error" role="alert">
        <CircleAlert size={20} aria-hidden />
        <div>
          <strong>No se pudo cargar esta sección.</strong>
          <p>{st.mensaje}</p>
          <button className="boton boton--secundario" onClick={reintentar}>
            Reintentar
          </button>
        </div>
      </div>
    )
  }
  return <>{children(st.datos)}</>
}

export function SinAnalisis({ mensaje }: { mensaje: string }) {
  return (
    <div className="vacio">
      <FolderInput size={30} aria-hidden />
      <h2>Aún no hay datos para mostrar</h2>
      <p>{mensaje}</p>
      <Link className="boton" to="/cargar">
        Ir a cargar datos
      </Link>
    </div>
  )
}

export function Gravedad({ g }: { g: Gravedad }) {
  return <span className={`chip chip--${g}`}>{GRAVEDAD[g].texto}</span>
}

export function EstadoAgenda({ e }: { e: EstadoHBVF }) {
  const x = ESTADO_HBVF[e]
  return <span className={`chip chip--${x.clase}`}>{e}</span>
}

export function Cifra({ valor, etiqueta, nota }: { valor: ReactNode; etiqueta: ReactNode; nota?: ReactNode }) {
  return (
    <div className="cifra">
      <div className="cifra__valor">{valor}</div>
      <div className="cifra__etiqueta">{etiqueta}</div>
      {nota && <div className="cifra__nota">{nota}</div>}
    </div>
  )
}

/** Barra 0–1 con texto: puntuaciones separadas (anomalía, confianza, riesgo). */
export function Medidor({ valor, max = 1, texto, tono = 'verde' }: { valor: number; max?: number; texto: string; tono?: string }) {
  const p = Math.max(0, Math.min(1, valor / max))
  return (
    <div className="medidor">
      <div className="medidor__fila">
        <span>{texto}</span>
        <strong>{max === 1 ? `${Math.round(valor * 100)} %` : `${valor} de ${max}`}</strong>
      </div>
      <div className="medidor__pista" role="meter" aria-valuemin={0} aria-valuemax={max} aria-valuenow={valor} aria-label={texto}>
        <div className={`medidor__barra medidor__barra--${tono}`} style={{ width: `${p * 100}%` }} />
      </div>
    </div>
  )
}

/** Valor contra su rango normal, como en un examen de laboratorio. */
export function Rango({ valor, min, max, unidad }: { valor: number; min: number; max: number; unidad: string }) {
  const tope = Math.max(valor, max) * 1.08 || 1
  const fuera = valor > max || valor < min
  return (
    <div className="rango" aria-label={`Valor ${valor}${unidad}, normal entre ${min} y ${max}`}>
      <div className="rango__pista">
        <div className="rango__normal" style={{ left: `${(min / tope) * 100}%`, width: `${((max - min) / tope) * 100}%` }} />
        <div className={`rango__marca ${fuera ? 'rango__marca--fuera' : ''}`} style={{ left: `${(valor / tope) * 100}%` }} />
      </div>
    </div>
  )
}
