import { expect, type Page } from '@playwright/test'

export const CLAVE = process.env.SENTINEL_CLAVE_DEMO ?? 'demo2026'

/** Ingresa por la pantalla de inicio, como lo haría una persona. */
export async function ingresar(page: Page, usuario: 'jefe' | 'analista' | 'ti' | 'salud' | 'auditor') {
  await page.goto('/ingresar')
  await page.evaluate(() => {
    localStorage.clear()
    sessionStorage.clear()
  })
  await page.goto('/ingresar')
  const campo = page.locator('input[autocomplete="username"]')
  await campo.fill(usuario)
  await page.locator('input[type="password"]').fill(CLAVE)
  await page.locator('form.ingreso__campos button').click()
  await expect(page).not.toHaveURL(/\/ingresar$/)
}

/** Ningún texto institucional ni nombres reales: solo seudónimos. */
export async function sinDatosSensibles(page: Page) {
  const texto = (await page.locator('body').innerText()).toLowerCase()
  expect(texto).not.toContain('iess')
}
