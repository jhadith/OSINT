import { Database, KeyRound, Lock, LogOut, Menu, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { ListaAnalisis } from '../api/types'
import { fMes } from '../lib/format'
import { accede, AREAS, NAV } from '../lib/nav'
import { useSesion } from '../lib/sesion'
import { Marca } from './Marca'

export function Shell() {
  const { sesion, salir, puede } = useSesion()
  const [abierto, setAbierto] = useState(false)
  const [acceso, setAcceso] = useState(false)
  const [lista, setLista] = useState<ListaAnalisis | null>(null)
  const [pendientes, setPendientes] = useState(0)
  const loc = useLocation()
  const ir = useNavigate()

  useEffect(() => {
    setAbierto(false)
    setAcceso(false)
    if (puede('estrategico')) api.analisis().then(setLista).catch(() => setLista(null))
    if (puede('gestionar_reglas'))
      api
        .tickets()
        .then((t) => setPendientes(t.tickets.filter((x) => x.estado === 'abierto' || x.estado === 'en_progreso').length))
        .catch(() => setPendientes(0))
  }, [loc.pathname, puede])

  if (!sesion) return null
  const activo = lista?.analisis.find((a) => a.id === lista.activo)

  return (
    <div className={`shell ${abierto ? 'shell--menu' : ''}`}>
      <aside className="lateral" aria-label="Navegación principal">
        <div className="lateral__marca">
          <Marca />
          <button className="lateral__cerrar" onClick={() => setAbierto(false)} aria-label="Cerrar menú">
            <X size={20} />
          </button>
        </div>
        <nav>
          {NAV.map((g) => {
            const visibles = g.items.filter((i) => accede(i, sesion.permisos))
            // Las secciones a las que el rol no tiene acceso no se muestran; un grupo sin secciones desaparece.
            if (!visibles.length) return null
            return (
              <div key={g.nivel} className="lateral__grupo">
                <div className="lateral__nivel">
                  {g.nivel} <span>{g.para}</span>
                </div>
                {visibles.map((i) => (
                  <NavLink key={i.ruta} to={i.ruta} className="lateral__item">
                    <i.icono size={18} aria-hidden />
                    <span>{i.nombre}</span>
                    {i.ruta === '/tickets' && pendientes > 0 && (
                      <span className="lateral__aviso" title="Tickets abiertos para TI">
                        {pendientes}
                      </span>
                    )}
                  </NavLink>
                ))}
              </div>
            )
          })}
        </nav>
        <a className="lateral__publico" href="/denuncia" target="_blank" rel="noreferrer">
          Portal de denuncias
        </a>
      </aside>

      <div className="principal">
        <header className="barra">
          <button className="barra__menu" onClick={() => setAbierto(true)} aria-label="Abrir menú">
            <Menu size={22} />
          </button>
          {activo?.resumen ? (
            <button className="barra__datos" onClick={() => puede('cargar_datos') && ir('/cargar')} title="Análisis que muestra la consola">
              <Database size={16} aria-hidden />
              <span>
                Datos de <strong>{fMes(activo.resumen.periodo.desde)}</strong>
              </span>
              <span className="barra__id">{activo.id}</span>
            </button>
          ) : lista ? (
            <span className="barra__datos barra__datos--vacio">
              <Database size={16} aria-hidden /> Sin análisis activo
            </span>
          ) : (
            <span />
          )}
          <div className="barra__der">
            <div className="pase-mini">
              <button className="pase-mini__boton" onClick={() => setAcceso((v) => !v)} aria-expanded={acceso}>
                <KeyRound size={16} aria-hidden />
                <span className="pase-mini__rol">{sesion.rolNombre}</span>
                <span className="pase-mini__nombre">{sesion.nombre}</span>
              </button>
              {acceso && (
                <div className="pase-mini__panel" role="dialog" aria-label="Tu acceso">
                  <p className="pase-mini__titulo">Tu acceso en esta sesión</p>
                  <ul>
                    {AREAS.map((a) => {
                      const si = sesion.permisos.includes(a.permiso)
                      return (
                        <li key={a.permiso} className={si ? 'si' : 'no'}>
                          {si ? <a.icono size={16} aria-hidden /> : <Lock size={16} aria-hidden />}
                          {a.nombre}
                          <span className="sr">{si ? ' permitido' : ' bloqueado'}</span>
                        </li>
                      )
                    })}
                  </ul>
                  <p className="pase-mini__vence">
                    La sesión vence a las {new Date(sesion.vence * 1000).toLocaleTimeString('es-EC', { hour: '2-digit', minute: '2-digit' })}.
                    Cada acción queda en la bitácora.
                  </p>
                </div>
              )}
            </div>
            <button
              className="boton boton--fantasma"
              onClick={async () => {
                await salir()
                ir('/ingresar')
              }}
            >
              <LogOut size={16} aria-hidden /> Salir
            </button>
          </div>
        </header>
        <main id="contenido">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
