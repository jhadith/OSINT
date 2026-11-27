import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Cliente = typeof import('../src/api/client')

/** Importa el cliente desde cero: el token inicial se lee de sessionStorage al cargar el módulo. */
async function cliente(): Promise<Cliente> {
  vi.resetModules()
  return import('../src/api/client')
}

function respuesta(status: number, cuerpo: unknown = {}, texto?: string) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(cuerpo),
    text: () => Promise.resolve(texto ?? JSON.stringify(cuerpo)),
    blob: () => Promise.resolve(new Blob(['contenido'])),
  } as unknown as Response
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  sessionStorage.clear()
  fetchMock = vi.fn(() => Promise.resolve(respuesta(200, { ok: true })))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

const ultimaLlamada = () => fetchMock.mock.calls.at(-1) as [string, RequestInit]

describe('sesión y cabeceras', () => {
  it('guarda el token y lo envía como Bearer', async () => {
    const c = await cliente()
    expect(c.hayToken()).toBe(false)
    c.fijarToken('abc')
    expect(sessionStorage.getItem('sentinel.token')).toBe('abc')
    expect(c.hayToken()).toBe(true)
    await c.api.yo()
    const [url, init] = ultimaLlamada()
    expect(url).toBe('/api/acceso/yo')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer abc')
    c.fijarToken(null)
    expect(sessionStorage.getItem('sentinel.token')).toBeNull()
  })

  it('recupera el token guardado al recargar la página', async () => {
    sessionStorage.setItem('sentinel.token', 'guardado')
    const c = await cliente()
    expect(c.hayToken()).toBe(true)
  })

  it('funciona aunque el navegador bloquee sessionStorage', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    const c = await cliente()
    expect(c.hayToken()).toBe(false)
    c.fijarToken('solo-en-memoria')
    expect(c.hayToken()).toBe(true)
  })

  it('envía JSON en los POST y deja que el navegador arme el FormData', async () => {
    const c = await cliente()
    await c.api.decidir('C3', 'confirmado', 'Evidencia en ambas fuentes')
    let [url, init] = ultimaLlamada()
    expect(url).toBe('/api/casos/C3/decision')
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({ estado: 'confirmado', motivo: 'Evidencia en ambas fuentes' })

    await c.api.verificarImagen(new File(['x'], 'a.png'))
    ;[url, init] = ultimaLlamada()
    expect(init.body).toBeInstanceOf(FormData)
    expect(new Headers(init.headers).get('Content-Type')).toBeNull()
  })
})

describe('errores', () => {
  it('convierte una respuesta de error en ApiError con el texto del servidor', async () => {
    const c = await cliente()
    fetchMock.mockResolvedValueOnce(respuesta(403, {}, 'Tu rol no tiene acceso a esta sección.'))
    await expect(c.api.casos()).rejects.toMatchObject({ status: 403, message: 'Tu rol no tiene acceso a esta sección.' })
  })

  it('usa un mensaje genérico si el servidor no explica el error', async () => {
    const c = await cliente()
    fetchMock.mockResolvedValueOnce(respuesta(500, {}, ''))
    await expect(c.api.casos()).rejects.toMatchObject({ status: 500, message: 'El servidor respondió 500.' })
    const sinTexto = { ok: false, status: 502, text: () => Promise.reject(new Error('x')) } as unknown as Response
    fetchMock.mockResolvedValueOnce(sinTexto)
    await expect(c.api.casos()).rejects.toMatchObject({ status: 502 })
  })

  it('avisa que la sesión venció ante un 401 con token, pero no al ingresar', async () => {
    const c = await cliente()
    const vencida = vi.fn()
    c.onSesionVencida(vencida)
    c.fijarToken('viejo')
    fetchMock.mockResolvedValueOnce(respuesta(401, {}, 'La sesión venció'))
    await expect(c.api.casos()).rejects.toBeInstanceOf(c.ApiError)
    expect(vencida).toHaveBeenCalledTimes(1)
    fetchMock.mockResolvedValueOnce(respuesta(401, {}, 'Usuario o contraseña incorrectos'))
    await expect(c.api.ingresar('jefe', 'mala')).rejects.toMatchObject({ status: 401 })
    expect(vencida).toHaveBeenCalledTimes(1)
  })

  it('explica cuando el backend está apagado', async () => {
    const c = await cliente()
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(c.api.roles()).rejects.toMatchObject({ status: 0 })
  })
})

describe('rutas de la API', () => {
  it('cada función llama a su ruta', async () => {
    const { api } = await cliente()
    const fuente = { origen: 'datos', nombre: 'fw.csv' } as never
    const casos: [() => Promise<unknown>, string][] = [
      [() => api.roles(), '/api/acceso/roles'],
      [() => api.ingresar('jefe', 'x'), '/api/acceso/ingresar'],
      [() => api.salir(), '/api/acceso/salir'],
      [() => api.analisis(), '/api/analisis'],
      [() => api.analisisUno('AN-1'), '/api/analisis/AN-1'],
      [() => api.fuentes(), '/api/analisis/fuentes'],
      [() => api.desdeCarpeta(fuente, fuente, null), '/api/analisis/desde-carpeta'],
      [() => api.desdeCarpeta(fuente, fuente, fuente), '/api/analisis/desde-carpeta'],
      [() => api.activar('AN-1'), '/api/analisis/AN-1/activar'],
      [() => api.ejecutivo(), '/api/ejecutivo'],
      [() => api.riesgos(), '/api/riesgos'],
      [() => api.tendencias(), '/api/threatpulse'],
      [() => api.casos(), '/api/casos'],
      [() => api.caso('C1'), '/api/casos/C1'],
      [() => api.serie(), '/api/serie'],
      [() => api.anomalias('firewall'), '/api/anomalias?fuente=firewall'],
      [() => api.grafo(), '/api/grafo'],
      [() => api.agenda(), '/api/agendamiento'],
      [() => api.revisarAgenda('AG-1', 'en_revision', 'nota de prueba'), '/api/agendamiento/AG-1/revision'],
      [() => api.reidentificar('P-1', 'motivo de prueba largo'), '/api/reidentificar'],
      [() => api.denunciar({ tipo: 'otro' }), '/api/publico/denuncias'],
      [() => api.seguimiento('DN-1'), '/api/publico/denuncias/DN-1'],
      [() => api.denuncias(), '/api/denuncias'],
      [() => api.gestionar('DN-1', 'atendida', 'gracias', ''), '/api/denuncias/DN-1/gestion'],
      [() => api.inteligencia(), '/api/inteligencia'],
      [() => api.ciEstado(), '/api/ci/estado'],
      [() => api.verificarEnlace('https://a.com'), '/api/verificar/enlace'],
      [() => api.reportar('https://a.com', 'malicioso', ''), '/api/verificar/reportar'],
      [() => api.bitacora(), '/api/bitacora'],
    ]
    for (const [llamar, ruta] of casos) {
      await llamar()
      expect(ultimaLlamada()[0]).toBe(ruta)
    }
  })

  it('cubre las rutas avanzadas incorporadas en V5', async () => {
    const { api } = await cliente()
    const casos: [() => Promise<unknown>, string][] = [
      [() => api.actualizarTendencias(), '/api/threatpulse/actualizar'],
      [() => api.tablero(), '/api/tablero'],
      [() => api.tickets(), '/api/tickets'],
      [() => api.crearTicket({ tipo: 'nueva', regla: 'X' }), '/api/tickets'],
      [() => api.gestionarTicket('TK-1', 'aplicado', 'listo'), '/api/tickets/TK-1/gestion'],
      [() => api.listasIndicadores(), '/api/listas/indicadores'],
      [() => api.listasAlta('blanca', 'ejemplo.com', 'prueba'), '/api/listas/indicadores'],
      [() => api.listasBaja(7), '/api/listas/indicadores/7'],
      [() => api.listasSolicitudes(), '/api/listas/solicitudes'],
      [() => api.listasSolicitudes('pendiente'), '/api/listas/solicitudes?estado=pendiente'],
      [() => api.listasSolicitar('negra', 'mal.com', 'motivo de prueba', 'fuente'), '/api/listas/solicitudes'],
      [() => api.listasResolver(3, true, 'aceptada'), '/api/listas/solicitudes/3/resolver'],
      [() => api.realimentacion(), '/api/realimentacion'],
      [() => api.recalibrar('ajuste de umbral'), '/api/realimentacion/recalibrar'],
    ]
    for (const [llamar, ruta] of casos) {
      await llamar()
      expect(ultimaLlamada()[0]).toBe(ruta)
    }
  })

  it('descarga los exportes como archivo', async () => {
    vi.useFakeTimers()
    const crear = vi.fn(() => 'blob:prueba')
    const revocar = vi.fn()
    const originales = { crear: URL.createObjectURL, revocar: URL.revokeObjectURL }
    URL.createObjectURL = crear
    URL.revokeObjectURL = revocar
    const clic = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const { api } = await cliente()
    await api.informePdf()
    expect(ultimaLlamada()[0]).toBe('/api/exportes/informe-pdf')
    for (const tipo of ['sigma', 'stix', 'misp', 'powerbi', 'maltego', 'gerencial', 'presentacion'] as const) {
      await api.exportar(tipo)
      expect(ultimaLlamada()[0]).toBe(`/api/exportes/${tipo}`)
    }
    expect(clic).toHaveBeenCalledTimes(8)
    vi.runAllTimers()
    expect(revocar).toHaveBeenCalledWith('blob:prueba')
    URL.createObjectURL = originales.crear
    URL.revokeObjectURL = originales.revocar
  })
})

describe('subida de archivos con progreso', () => {
  class XHRFalso {
    static ultimo: XHRFalso
    status = 0
    responseText = ''
    cabeceras: Record<string, string> = {}
    upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {}
    onload?: () => void
    onerror?: () => void
    open = vi.fn()
    send = vi.fn()
    constructor() {
      XHRFalso.ultimo = this
    }
    setRequestHeader(k: string, v: string) {
      this.cabeceras[k] = v
    }
  }

  beforeEach(() => vi.stubGlobal('XMLHttpRequest', XHRFalso))

  const archivos = () => [new File(['a'], 'fw.csv'), new File(['b'], 'med.csv')] as const

  it('informa el avance y devuelve el análisis', async () => {
    const c = await cliente()
    c.fijarToken('tok')
    const avance = vi.fn()
    const [fw, med] = archivos()
    const promesa = c.api.subirArchivos(fw, med, new File(['c'], 'citas.csv'), avance)
    const x = XHRFalso.ultimo
    expect(x.open).toHaveBeenCalledWith('POST', '/api/analisis/subir')
    expect(x.cabeceras.Authorization).toBe('Bearer tok')
    x.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 })
    x.upload.onprogress?.({ lengthComputable: false, loaded: 0, total: 0 })
    expect(avance).toHaveBeenCalledWith(0.5)
    expect(avance).toHaveBeenCalledTimes(1)
    x.status = 200
    x.responseText = JSON.stringify({ id: 'AN-1' })
    x.onload?.()
    await expect(promesa).resolves.toEqual({ id: 'AN-1' })
  })

  it('rechaza si el servidor responde con error', async () => {
    const c = await cliente()
    const [fw, med] = archivos()
    const promesa = c.api.subirArchivos(fw, med, null, () => undefined)
    const x = XHRFalso.ultimo
    expect(x.cabeceras.Authorization).toBeUndefined()
    x.status = 400
    x.responseText = 'Solo se aceptan archivos CSV.'
    x.onload?.()
    await expect(promesa).rejects.toMatchObject({ status: 400, message: 'Solo se aceptan archivos CSV.' })

    const otra = c.api.subirArchivos(fw, med, null, () => undefined)
    XHRFalso.ultimo.status = 500
    XHRFalso.ultimo.onload?.()
    await expect(otra).rejects.toMatchObject({ message: 'El servidor respondió 500.' })
  })

  it('rechaza si se corta la conexión', async () => {
    const c = await cliente()
    const [fw, med] = archivos()
    const promesa = c.api.subirArchivos(fw, med, null, () => undefined)
    XHRFalso.ultimo.onerror?.()
    await expect(promesa).rejects.toMatchObject({ status: 0 })
  })
})
