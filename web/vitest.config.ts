import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Pruebas unitarias de la lógica de la consola (formato, navegación, cliente de la API y hooks).
// Las pantallas se prueban de punta a punta con Playwright (pruebas_dinamicas/e2e).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.{ts,tsx}'],
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      include: ['src/lib/**', 'src/api/**'],
      exclude: ['src/api/types.ts'],
      reporter: ['text', 'lcov', 'html'],
      reportsDirectory: 'coverage',
      thresholds: { lines: 95, statements: 95, functions: 95, branches: 95 },
    },
  },
})
