import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, fijarToken, hayToken, onSesionVencida } from '../api/client'
import type { Permiso, Sesion } from '../api/types'

interface Ctx {
  sesion: Sesion | null
  cargando: boolean
  entrar: (usuario: string, clave: string) => Promise<Sesion>
  salir: () => Promise<void>
  puede: (p: Permiso) => boolean
}

const SesionCtx = createContext<Ctx | null>(null)

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [sesion, setSesion] = useState<Sesion | null>(null)
  const [cargando, setCargando] = useState(hayToken())

  useEffect(() => {
    onSesionVencida(() => {
      fijarToken(null)
      setSesion(null)
    })
    if (!hayToken()) return
    api
      .yo()
      .then(setSesion)
      .catch(() => fijarToken(null))
      .finally(() => setCargando(false))
  }, [])

  const entrar = useCallback(async (usuario: string, clave: string) => {
    const r = await api.ingresar(usuario, clave)
    fijarToken(r.token)
    setSesion(r.sesion)
    return r.sesion
  }, [])

  const salir = useCallback(async () => {
    await api.salir().catch(() => undefined)
    fijarToken(null)
    setSesion(null)
  }, [])

  const puede = useCallback((p: Permiso) => Boolean(sesion?.permisos.includes(p)), [sesion])

  return <SesionCtx.Provider value={{ sesion, cargando, entrar, salir, puede }}>{children}</SesionCtx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSesion() {
  const c = useContext(SesionCtx)
  if (!c) throw new Error('useSesion fuera de ProveedorSesion')
  return c
}
