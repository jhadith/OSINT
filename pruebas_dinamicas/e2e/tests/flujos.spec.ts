// Flujos principales de la demo, de punta a punta en un navegador real.
import { expect, test } from '@playwright/test'
import { ingresar, sinDatosSensibles } from './ayuda'

test.describe('Ingreso', () => {
  test('muestra los roles y rechaza una contraseña equivocada', async ({ page }) => {
    await page.goto('/ingresar')
    await expect(page.getByRole('radiogroup', { name: 'Rol' })).toBeVisible()
    await page.locator('input[autocomplete="username"]').fill('jefe')
    await page.locator('input[type="password"]').fill('equivocada')
    await page.locator('form.ingreso__campos button').click()
    await expect(page.getByText(/incorrectos/i)).toBeVisible()
    await expect(page).toHaveURL(/\/ingresar$/)
  })
})

test.describe('Analista del SOC', () => {
  test('la vista ejecutiva resume los incidentes del análisis', async ({ page }) => {
    await ingresar(page, 'analista')
    await page.goto('/inicio')
    await expect(page.getByText(/incidentes?/).first()).toBeVisible()
    await expect(page.getByText(/críticos?/).first()).toBeVisible()
    await sinDatosSensibles(page)
  })

  test('no se puede decidir un caso sin motivo; al confirmar queda registrado', async ({ page }) => {
    await ingresar(page, 'analista')
    await page.goto('/casos')
    const caso = page.locator('a[href^="/casos/"]').first()
    await expect(caso).toBeVisible()
    await caso.click()
    await expect(page).toHaveURL(/\/casos\/.+/)

    const confirmar = page.getByRole('button', { name: 'Confirmar incidente' })
    const motivo = page.getByLabel('Motivo (mínimo 10 caracteres)')
    await expect(confirmar).toBeVisible()
    await expect(confirmar).toBeDisabled()
    await motivo.fill('corto')
    await expect(confirmar).toBeDisabled()
    await motivo.fill('Evidencia revisada en ambas fuentes (prueba E2E).')
    await expect(confirmar).toBeEnabled()
    const respuesta = page.waitForResponse((r) => r.url().includes('/decision') && r.request().method() === 'POST')
    await confirmar.click()
    expect((await respuesta).status()).toBe(200)
    await expect(page.locator('.decision-previa')).toContainText('Evidencia revisada en ambas fuentes (prueba E2E).')
    await expect(page.locator('.decision-previa')).toContainText('Confirmad')
    await sinDatosSensibles(page)
  })

  test('reidentificar exige un motivo de al menos 15 caracteres', async ({ page }) => {
    await ingresar(page, 'analista')
    await page.goto('/casos')
    await page.locator('a[href^="/casos/"]').first().click()
    const boton = page.getByRole('button', { name: 'Reidentificar y registrar' })
    await expect(boton).toBeDisabled()
    const motivo = page.locator('.panel--sensible textarea')
    await motivo.fill('muy corto')
    await expect(boton).toBeDisabled()
    await motivo.fill('Notificación LOPDP del caso (prueba E2E)')
    await expect(boton).toBeEnabled()
  })
})

test.describe('Control de acceso por rol', () => {
  test('el personal de salud no ve los casos del SOC', async ({ page }) => {
    await ingresar(page, 'salud')
    await page.goto('/casos')
    await expect(page.getByRole('heading', { name: 'Esta sección está cerrada para tu rol' })).toBeVisible()
  })

  test('el personal de salud puede verificar un enlace sospechoso', async ({ page }) => {
    await ingresar(page, 'salud')
    await page.goto('/verificar')
    await page.getByPlaceholder('https://…').fill('http://secure-login-portal.xyz/verificar-cuenta')
    await page.getByRole('button', { name: 'Revisar enlace' }).click()
    await expect(page.locator('.veredicto')).toBeVisible()
  })

  test('la auditoría ve las decisiones en la bitácora', async ({ page }) => {
    await ingresar(page, 'auditor')
    await page.goto('/accesos')
    await expect(page.getByText(/Caso confirmado|Análisis iniciado/).first()).toBeVisible()
  })
})

test.describe('Portal público de denuncias', () => {
  test('una persona denuncia sin sesión y recibe un código; el SOC la ve en su bandeja', async ({ page }) => {
    await page.goto('/denuncia')
    await page.locator('.tipo').first().click()
    await page.locator('textarea').fill('Me pidieron dinero por una cita (prueba E2E).')
    await page.locator('.publico__acepto input').check()
    await page.locator('.boton--enorme').click()
    const codigo = (await page.locator('.recibida__codigo').innerText()).trim()
    expect(codigo.length).toBeGreaterThan(3)

    await ingresar(page, 'analista')
    await page.goto('/denuncias')
    await expect(page.getByText(codigo).first()).toBeVisible()
  })

  test('un texto con HTML malicioso no se ejecuta en la bandeja del SOC (XSS)', async ({ page }) => {
    await page.goto('/denuncia')
    await page.locator('.tipo').first().click()
    await page.locator('textarea').fill('<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>')
    await page.locator('.publico__acepto input').check()
    await page.locator('.boton--enorme').click()
    const codigo = (await page.locator('.recibida__codigo').innerText()).trim()

    await ingresar(page, 'analista')
    await page.goto('/denuncias')
    await page.getByText(codigo).first().click()
    await expect(page.locator('blockquote.cita')).toContainText('<img src=x')
    expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined()
  })
})
