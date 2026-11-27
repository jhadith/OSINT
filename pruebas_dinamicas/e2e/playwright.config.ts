import { defineConfig, devices } from '@playwright/test'

// La app debe estar corriendo (backend sirviendo web/dist) en SENTINEL_URL, siempre en 127.0.0.1.
const BASE = process.env.SENTINEL_URL ?? 'http://127.0.0.1:8010'
// En local se puede usar el Chrome del sistema: PW_CHROME=/opt/google/chrome/chrome
const chrome = process.env.PW_CHROME

export default defineConfig({
  testDir: './tests',
  globalSetup: './global-setup.ts',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'reporte' }], ['junit', { outputFile: 'resultados/junit.xml' }]],
  outputDir: 'resultados/artefactos',
  use: {
    baseURL: BASE,
    locale: 'es-EC',
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: process.env.CI ? 'retain-on-failure' : 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, ...(chrome ? { launchOptions: { executablePath: chrome } } : {}) },
    },
  ],
})
