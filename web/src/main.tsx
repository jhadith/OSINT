import '@fontsource/atkinson-hyperlegible-next/400.css'
import '@fontsource/atkinson-hyperlegible-next/600.css'
import '@fontsource/atkinson-hyperlegible-next/700.css'
import '@fontsource/atkinson-hyperlegible-mono/400.css'
import './index.css'
import { StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { Permiso } from './api/types'
import { Shell } from './components/Shell'
import { SinPermiso } from './components/SinPermiso'
import { inicioDe } from './lib/nav'
import { ProveedorSesion, useSesion } from './lib/sesion'
import Accesos from './pages/Accesos'
import Agendamiento from './pages/Agendamiento'
import Anomalias from './pages/Anomalias'
import Cargar from './pages/Cargar'
import CasoDetalle from './pages/CasoDetalle'
import Casos from './pages/Casos'
import Denuncia from './pages/Denuncia'
import Denuncias from './pages/Denuncias'
import Ejecutiva from './pages/Ejecutiva'
import Ingreso from './pages/Ingreso'
import Inteligencia from './pages/Inteligencia'
import LineaTiempo from './pages/LineaTiempo'
import Relaciones from './pages/Relaciones'
import Riesgos from './pages/Riesgos'
import Tendencias from './pages/Tendencias'
import Verificar from './pages/Verificar'

function Protegida() {
  const { sesion, cargando } = useSesion()
  const loc = useLocation()
  if (cargando) return null
  if (!sesion) return <Navigate to="/ingresar" replace state={{ desde: loc.pathname }} />
  return <Shell />
}

/** La pantalla se muestra solo si el rol tiene el permiso; el servidor vuelve a comprobarlo en cada llamada. */
function Con({ p, children }: { p: Permiso; children: ReactNode }) {
  const { puede } = useSesion()
  return puede(p) ? <>{children}</> : <SinPermiso permiso={p} />
}

function Raiz() {
  const { sesion, cargando } = useSesion()
  if (cargando) return null
  return <Navigate to={sesion ? inicioDe(sesion.permisos) : '/ingresar'} replace />
}

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <ProveedorSesion>
      <BrowserRouter>
        <Routes>
          <Route path="/ingresar" element={<Ingreso />} />
          <Route path="/denuncia" element={<Denuncia />} />
          <Route element={<Protegida />}>
            <Route path="/inicio" element={<Con p="estrategico"><Ejecutiva /></Con>} />
            <Route path="/riesgos" element={<Con p="estrategico"><Riesgos /></Con>} />
            <Route path="/tendencias" element={<Con p="estrategico"><Tendencias /></Con>} />
            <Route path="/casos" element={<Con p="operativo"><Casos /></Con>} />
            <Route path="/casos/:id" element={<Con p="operativo"><CasoDetalle /></Con>} />
            <Route path="/agendamiento" element={<Con p="operativo"><Agendamiento /></Con>} />
            <Route path="/denuncias" element={<Con p="ver_denuncias"><Denuncias /></Con>} />
            <Route path="/linea" element={<Con p="operativo"><LineaTiempo /></Con>} />
            <Route path="/anomalias" element={<Con p="operativo"><Anomalias /></Con>} />
            <Route path="/relaciones" element={<Con p="operativo"><Relaciones /></Con>} />
            <Route path="/cargar" element={<Con p="cargar_datos"><Cargar /></Con>} />
            <Route path="/inteligencia" element={<Con p="tecnico"><Inteligencia /></Con>} />
            <Route path="/verificar" element={<Con p="verificar"><Verificar /></Con>} />
            <Route path="/accesos" element={<Con p="auditar"><Accesos /></Con>} />
          </Route>
          <Route path="*" element={<Raiz />} />
        </Routes>
      </BrowserRouter>
    </ProveedorSesion>
  </StrictMode>,
)
