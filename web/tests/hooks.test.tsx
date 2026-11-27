import { act, render, renderHook, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const sesionDemo = { usuario: 'analista', nombre: 'Analista SOC', rol: 'analista', rolNombre: 'Analista', permisos: ['operativo'] }

const mocks = vi.hoisted(() => ({
  token: null as string | null,
  vencer: null as null | (() => void),
  api: { yo: vi.fn(), ingresar: vi.fn(), salir: vi.fn() },
}))

vi.mock('../src/api/client', async (original) => {
  const real = await original<typeof import('../src/api/client')>()
  return {
    ...real,
    api: mocks.api,
    hayToken: () => Boolean(mocks.token),
    fijarToken: (t: string | null) => {
      mocks.token = t
    },
    onSesionVencida: (fn: () => void) => {
      mocks.vencer = fn
    },
  }
})

const { ApiError } = await import('../src/api/client')
const { useApi } = await import('../src/lib/useApi')
const { ProveedorSesion, useSesion } = await import('../src/lib/sesion')

beforeEach(() => {
  mocks.token = null
  mocks.vencer = null
  mocks.api.yo.mockReset()
  mocks.api.ingresar.mockReset()
  mocks.api.salir.mockReset()
})

describe('useApi', () => {
  it('pasa de cargando a listo y permite actualizar los datos', async () => {
    const { result } = renderHook(() => useApi(() => Promise.resolve({ n: 1 })))
    expect(result.current.st.estado).toBe('cargando')
    await waitFor(() => expect(result.current.st).toEqual({ estado: 'listo', datos: { n: 1 } }))
    act(() => result.current.actualizar((d) => ({ n: d.n + 1 })))
    expect(result.current.st).toEqual({ estado: 'listo', datos: { n: 2 } })
  })

  it('expone el código del error de la API', async () => {
    const { result } = renderHook(() => useApi(() => Promise.reject(new ApiError(409, 'Todavía no hay un análisis.'))))
    await waitFor(() =>
      expect(result.current.st).toEqual({ estado: 'error', mensaje: 'Todavía no hay un análisis.', codigo: 409 }),
    )
    act(() => result.current.actualizar((d) => d))
    expect(result.current.st.estado).toBe('error')
  })

  it('maneja errores que no son de la API y permite reintentar', async () => {
    const cargar = vi.fn().mockRejectedValueOnce('texto').mockRejectedValueOnce(new Error('falló')).mockResolvedValue(7)
    const { result } = renderHook(() => useApi(cargar))
    await waitFor(() => expect(result.current.st).toEqual({ estado: 'error', mensaje: 'Error desconocido.', codigo: 0 }))
    act(() => result.current.reintentar())
    await waitFor(() => expect(result.current.st).toEqual({ estado: 'error', mensaje: 'falló', codigo: 0 }))
    act(() => result.current.reintentar())
    await waitFor(() => expect(result.current.st).toEqual({ estado: 'listo', datos: 7 }))
  })

  it('ignora respuestas que llegan después de desmontar la pantalla', async () => {
    let resolver!: (v: number) => void
    let rechazar!: (e: Error) => void
    const { result, unmount } = renderHook(() => useApi(() => new Promise<number>((ok) => (resolver = ok))))
    unmount()
    await act(async () => resolver(1))
    expect(result.current.st.estado).toBe('cargando')
    const otro = renderHook(() => useApi(() => new Promise<number>((_, mal) => (rechazar = mal))))
    otro.unmount()
    await act(async () => rechazar(new Error('tarde')))
    expect(otro.result.current.st.estado).toBe('cargando')
  })
})

describe('sesión', () => {
  const envoltura = ({ children }: { children: ReactNode }) => <ProveedorSesion>{children}</ProveedorSesion>

  it('sin token no consulta al servidor; al entrar y salir actualiza la sesión', async () => {
    mocks.api.ingresar.mockResolvedValue({ token: 'nuevo', sesion: sesionDemo })
    mocks.api.salir.mockRejectedValue(new Error('sin red'))
    const { result } = renderHook(() => useSesion(), { wrapper: envoltura })
    expect(result.current.cargando).toBe(false)
    expect(mocks.api.yo).not.toHaveBeenCalled()
    await act(() => result.current.entrar('analista', 'clave'))
    expect(mocks.token).toBe('nuevo')
    expect(result.current.sesion?.nombre).toBe('Analista SOC')
    expect(result.current.puede('operativo' as never)).toBe(true)
    expect(result.current.puede('auditar' as never)).toBe(false)
    await act(() => result.current.salir())
    expect(result.current.sesion).toBeNull()
    expect(mocks.token).toBeNull()
  })

  it('con token guardado recupera la sesión y la cierra si vence', async () => {
    mocks.token = 'guardado'
    mocks.api.yo.mockResolvedValue(sesionDemo)
    const { result } = renderHook(() => useSesion(), { wrapper: envoltura })
    expect(result.current.cargando).toBe(true)
    await waitFor(() => expect(result.current.cargando).toBe(false))
    expect(result.current.sesion?.usuario).toBe('analista')
    act(() => mocks.vencer?.())
    expect(result.current.sesion).toBeNull()
    expect(mocks.token).toBeNull()
  })

  it('si el token guardado ya no sirve, lo borra', async () => {
    mocks.token = 'viejo'
    mocks.api.yo.mockRejectedValue(new ApiError(401, 'venció'))
    const { result } = renderHook(() => useSesion(), { wrapper: envoltura })
    await waitFor(() => expect(result.current.cargando).toBe(false))
    expect(mocks.token).toBeNull()
    expect(result.current.sesion).toBeNull()
  })

  it('avisa si se usa fuera del proveedor', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    function Suelto() {
      useSesion()
      return null
    }
    expect(() => render(<Suelto />)).toThrow('useSesion fuera de ProveedorSesion')
    render(
      <ProveedorSesion>
        <span>dentro</span>
      </ProveedorSesion>,
    )
    expect(screen.getByText('dentro')).toBeTruthy()
  })
})
