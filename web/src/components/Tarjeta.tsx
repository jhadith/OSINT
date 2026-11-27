import { ArrowUpRight, Maximize2, X } from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Gravedad } from '../api/types'

// ---------- tarjeta que se expande ----------
export interface TarjetaProps {
  titulo: string
  dato?: ReactNode
  area: string
  children: ReactNode
  grande?: ReactNode
  ruta?: string
  tono?: Gravedad
}

export function Tarjeta({ titulo, dato, area, children, grande, ruta, tono }: TarjetaProps) {
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

