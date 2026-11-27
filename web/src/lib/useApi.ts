import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'

export type Estado<T> =
  | { estado: 'cargando' }
  | { estado: 'error'; mensaje: string; codigo: number }
  | { estado: 'listo'; datos: T }

/** Carga datos de `api.*` y expone cargando / error / listo, con reintento. */
export function useApi<T>(cargar: () => Promise<T>, deps: unknown[] = []) {
  const [st, setSt] = useState<Estado<T>>({ estado: 'cargando' })
  const [intento, setIntento] = useState(0)

  useEffect(() => {
    let vivo = true
    cargar()
      .then((datos) => vivo && setSt({ estado: 'listo', datos }))
      .catch(
        (e: unknown) =>
          vivo &&
          setSt({
            estado: 'error',
            mensaje: e instanceof Error ? e.message : 'Error desconocido.',
            codigo: e instanceof ApiError ? e.status : 0,
          }),
      )
    return () => {
      vivo = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intento, ...deps])

  const reintentar = useCallback(() => setIntento((n) => n + 1), [])
  const actualizar = useCallback(
    (fn: (d: T) => T) => setSt((s) => (s.estado === 'listo' ? { estado: 'listo', datos: fn(s.datos) } : s)),
    [],
  )
  return { st, reintentar, actualizar }
}
