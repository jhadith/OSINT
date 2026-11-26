import { LockKeyhole } from 'lucide-react'
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Permiso } from '../api/types'
import { inicioDe } from '../lib/nav'
import { useSesion } from '../lib/sesion'

const PRUEBA: Partial<Record<Permiso, () => Promise<unknown>>> = {
  estrategico: api.ejecutivo,
  operativo: api.casos,
  ver_denuncias: api.denuncias,
  cargar_datos: api.fuentes,
  tecnico: api.inteligencia,
  auditar: api.bitacora,
}

/** Pantalla cerrada. Además hace la llamada al servidor para que el intento quede en la bitácora. */
export function SinPermiso({ permiso }: { permiso: Permiso }) {
  const { sesion } = useSesion()
  useEffect(() => {
    PRUEBA[permiso]?.().catch(() => undefined)
  }, [permiso])
  return (
    <div className="cerrado">
      <LockKeyhole size={56} aria-hidden />
      <h1>Esta sección está cerrada para tu rol</h1>
      <p>
        Ingresaste como <strong>{sesion?.rolNombre}</strong>. El servidor rechazó la solicitud y el intento quedó registrado en la
        bitácora de auditoría.
      </p>
      <Link className="boton boton--grande" to={sesion ? inicioDe(sesion.permisos) : '/ingresar'}>
        Volver a mis secciones
      </Link>
    </div>
  )
}
