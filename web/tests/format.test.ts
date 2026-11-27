import { describe, expect, it } from 'vitest'
import {
  bandera,
  corto,
  duracion,
  ESTADO_CASO,
  ESTADO_DENUNCIA,
  ESTADO_HBVF,
  enPalabras,
  fFecha,
  fFechaHora,
  fFechaLarga,
  fHora,
  fMes,
  fMesTitulo,
  GRAVEDAD,
  MEDIO,
  num,
  pct,
  plural,
} from '../src/lib/format'

describe('números', () => {
  it('agrupa miles con punto, como se escribe en Ecuador', () => {
    expect(num(2000)).toBe('2.000')
    expect(num(10023532)).toBe('10.023.532')
  })
  it('abrevia cantidades grandes', () => {
    expect(corto(1_500_000)).toMatch(/1,5/)
  })
  it('dice las cantidades en palabras para personas no técnicas', () => {
    expect(enPalabras(10_023_532)).toBe('10 millones')
    expect(enPalabras(1_000_000)).toBe('1 millón')
    expect(enPalabras(710_300)).toBe('710 mil')
    expect(enPalabras(950)).toBe('950')
  })
  it('expresa duraciones en segundos o minutos', () => {
    expect(duracion(0.2)).toBe('12 segundos')
    expect(duracion(0.001)).toBe('1 segundos')
    expect(duracion(1)).toBe('1 minuto')
    expect(duracion(2.9)).toBe('3 minutos')
  })
  it('muestra porcentajes y un guion cuando no hay dato', () => {
    expect(pct(0.25)).toBe('25 %')
    expect(pct(null)).toBe('—')
    expect(pct(undefined)).toBe('—')
  })
  it('usa singular o plural según la cantidad', () => {
    expect(plural(1, 'incidente', 'incidentes')).toBe('1 incidente')
    expect(plural(4, 'incidente', 'incidentes')).toBe('4 incidentes')
  })
})

describe('fechas', () => {
  it('formatea horas en 24 horas', () => {
    expect(fHora('2026-10-07T13:05:00')).toBe('13:05')
    expect(fFechaHora('2026-10-07T13:05:00')).toMatch(/13:05/)
  })
  it('una fecha sin hora no salta al día anterior', () => {
    expect(fFecha('2026-10-01')).toMatch(/^1 /)
    expect(fFechaLarga('2026-10-01')).toMatch(/octubre/)
  })
  it('nombra el mes dentro de una frase y al inicio de un título', () => {
    expect(fMes('2026-10-07')).toBe('octubre de 2026')
    expect(fMesTitulo('2026-10-07')).toBe('Octubre de 2026')
  })
})

describe('banderas y catálogos', () => {
  it('marca H si supera el rango, L si queda debajo y nada si está dentro', () => {
    expect(bandera(30, 0, 2)).toBe('H')
    expect(bandera(2, 40, 900)).toBe('L')
    expect(bandera(5, 0, 10)).toBeNull()
  })
  it('ordena la gravedad de crítica a baja', () => {
    const orden = Object.entries(GRAVEDAD).sort((a, b) => a[1].orden - b[1].orden).map(([k]) => k)
    expect(orden).toEqual(['critica', 'alta', 'media', 'baja'])
  })
  it('tiene textos para estados, medios y agendamiento', () => {
    expect(ESTADO_CASO.pendiente).toBe('Por decidir')
    expect(ESTADO_DENUNCIA.descartada).toBe('Cerrada')
    expect(MEDIO.whatsapp).toBe('WhatsApp')
    expect(ESTADO_HBVF['Revisión prioritaria'].orden).toBe(0)
  })
})
