// Antes de las pruebas: procesa los datos sintéticos de ejemplo para que la consola tenga un análisis activo.
import { request, type FullConfig } from '@playwright/test'
import { CLAVE } from './tests/ayuda'

export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL as string
  const api = await request.newContext({ baseURL })
  const ingreso = await api.post('/api/acceso/ingresar', { data: { usuario: 'analista', clave: CLAVE } })
  if (!ingreso.ok()) throw new Error(`No se pudo ingresar como analista: ${ingreso.status()} ${await ingreso.text()}`)
  const { token } = await ingreso.json()
  const headers = { Authorization: `Bearer ${token}` }

  const lista = await (await api.get('/api/analisis', { headers })).json()
  if (lista.activo && !lista.ocupado) return

  const fuentes = (await (await api.get('/api/analisis/fuentes', { headers })).json()).archivos as { origen: string; nombre: string; tipo: string }[]
  const de = (tipo: string) => fuentes.find((f) => f.tipo === tipo && f.origen === 'ejemplo')
  const fw = de('firewall')
  const med = de('sistema_medico')
  const citas = de('agendamiento')
  if (!fw || !med) throw new Error('Faltan los datos sintéticos de ejemplo (datos_ejemplo/).')

  const r = await api.post('/api/analisis/desde-carpeta', {
    headers,
    form: { fw_origen: fw.origen, fw: fw.nombre, med_origen: med.origen, med: med.nombre, citas_origen: citas?.origen ?? '', citas: citas?.nombre ?? '' },
  })
  if (!r.ok()) throw new Error(`No se pudo lanzar el análisis: ${r.status()} ${await r.text()}`)
  const { id } = await r.json()
  for (let i = 0; i < 180; i++) {
    const m = await (await api.get(`/api/analisis/${id}`, { headers })).json()
    if (m.estado === 'listo') {
      await api.post(`/api/analisis/${id}/activar`, { headers })
      return
    }
    if (m.estado === 'error') throw new Error(`El análisis terminó con error: ${m.error}`)
    await new Promise((ok) => setTimeout(ok, 1000))
  }
  throw new Error('El análisis de ejemplo no terminó a tiempo.')
}
