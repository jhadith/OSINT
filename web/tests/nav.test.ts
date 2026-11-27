import { describe, expect, it } from 'vitest'
import { AREAS, inicioDe, NAV, TODAS } from '../src/lib/nav'

describe('navegación por rol', () => {
  it('lleva a cada rol a la primera pantalla que puede ver', () => {
    expect(inicioDe(['estrategico', 'operativo'])).toBe('/inicio')
    expect(inicioDe(['verificar'])).toBe('/verificar')
    expect(inicioDe(['auditar'])).toBe('/accesos')
  })
  it('sin permisos cae en la vista ejecutiva (el servidor igual lo bloquea)', () => {
    expect(inicioDe([])).toBe('/inicio')
  })
  it('no repite rutas y cada grupo tiene pantallas', () => {
    const rutas = TODAS.map((i) => i.ruta)
    expect(new Set(rutas).size).toBe(rutas.length)
    expect(NAV.every((g) => g.items.length > 0)).toBe(true)
  })
  it('las áreas del ingreso usan permisos reales', () => {
    expect(AREAS.map((a) => a.permiso)).toContain('reidentificar')
    expect(AREAS.length).toBeGreaterThan(5)
  })
})
