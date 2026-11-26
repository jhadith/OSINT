import { Check, Lock } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type { EntradaBitacora, Rol } from '../api/types'
import { Carga, Cifra, Pagina, Panel } from '../components/ui'
import { fFechaHora, num } from '../lib/format'
import { AREAS } from '../lib/nav'
import { useSesion } from '../lib/sesion'
import { useApi } from '../lib/useApi'

const CATEGORIAS: { id: string; nombre: string; prueba: (e: EntradaBitacora) => boolean }[] = [
  { id: 'todo', nombre: 'Todo', prueba: () => true },
  { id: 'acceso', nombre: 'Ingresos y bloqueos', prueba: (e) => /ingreso|salida|bloquead|denegado/i.test(e.accion) },
  { id: 'reid', nombre: 'Reidentificaciones', prueba: (e) => e.accion === 'Reidentificación' },
  { id: 'datos', nombre: 'Datos y análisis', prueba: (e) => /análisis|exporte/i.test(e.accion) },
  { id: 'decisiones', nombre: 'Decisiones', prueba: (e) => /^caso|revisión/i.test(e.accion) },
  { id: 'denuncias', nombre: 'Denuncias y alertas', prueba: (e) => /denuncia|alerta/i.test(e.accion) },
]

function tono(e: EntradaBitacora) {
  if (/bloquead|denegado/i.test(e.accion)) return 'critica'
  if (/fallido/i.test(e.accion)) return 'alta'
  if (e.accion === 'Reidentificación') return 'sensible'
  return ''
}

export default function Accesos() {
  const roles = useApi(api.roles)
  const bit = useApi(api.bitacora)
  return (
    <Pagina
      titulo="Accesos y bitácora"
      bajada="Quién puede ver qué, y quién hizo qué. La bitácora solo se agrega: nadie puede borrar ni editar una entrada desde la consola."
      acciones={
        <button className="boton boton--secundario" onClick={bit.reintentar}>
          Actualizar
        </button>
      }
    >
      <Carga st={bit.st} reintentar={bit.reintentar}>
        {(b) => <Contadores b={b} />}
      </Carga>
      <Carga st={roles.st} reintentar={roles.reintentar}>
        {(r) => <MatrizRoles roles={r} />}
      </Carga>
      <Panel titulo="Cómo se protege el acceso">
        <ul className="garantias">
          <li>
            <strong>Contraseñas cifradas.</strong> Se guardan con PBKDF2-SHA256 y 600 000 iteraciones; nunca en texto plano.
          </li>
          <li>
            <strong>Bloqueo por intentos.</strong> Cinco contraseñas equivocadas bloquean la cuenta 5 minutos.
          </li>
          <li>
            <strong>Permisos en el servidor.</strong> Aunque alguien escriba la dirección de una pantalla, el servidor revisa su rol y
            registra el intento.
          </li>
          <li>
            <strong>Sesiones de 8 horas.</strong> Al vencer, hay que volver a ingresar.
          </li>
          <li>
            <strong>Nombres reales solo con motivo.</strong> Los casos muestran seudónimos; ver el nombre exige un motivo que queda aquí.
          </li>
        </ul>
      </Panel>
      <Carga st={bit.st} reintentar={bit.reintentar} filas={8}>
        {(b) => <Bitacora b={b} />}
      </Carga>
    </Pagina>
  )
}

function Contadores({ b }: { b: EntradaBitacora[] }) {
  const cuenta = (re: RegExp) => b.filter((e) => re.test(e.accion)).length
  return (
    <div className="cifras">
      <Cifra valor={num(cuenta(/^Ingreso a la consola$/))} etiqueta="ingresos" />
      <Cifra valor={num(cuenta(/fallido/i))} etiqueta="intentos fallidos" />
      <Cifra valor={num(cuenta(/bloqueada/i))} etiqueta="bloqueos de cuenta" />
      <Cifra valor={num(cuenta(/denegado/i))} etiqueta="accesos denegados" />
      <Cifra valor={num(cuenta(/^Reidentificación$/))} etiqueta="nombres reales consultados" />
    </div>
  )
}

function MatrizRoles({ roles }: { roles: Rol[] }) {
  const { sesion } = useSesion()
  return (
    <Panel titulo="Quién puede ver qué" bajada="Cada rol abre solo lo que necesita. Tu fila está resaltada.">
      <div className="tabla-scroll">
        <table className="tabla tabla--accesos">
          <thead>
            <tr>
              <th>Rol</th>
              {AREAS.map((a) => (
                <th key={a.permiso} className="centro">
                  <a.icono size={18} aria-hidden />
                  <span>{a.nombre}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {roles.map((r) => (
              <tr key={r.rol} className={sesion?.rol === r.rol ? 'fila--activa' : ''}>
                <th scope="row">
                  {r.nombre}
                  <div className="muted">{r.descripcion}</div>
                </th>
                {AREAS.map((a) => {
                  const si = r.permisos.includes(a.permiso)
                  return (
                    <td key={a.permiso} className={`centro acceso acceso--${si ? 'si' : 'no'}`}>
                      {si ? <Check size={20} aria-label="Con acceso" /> : <Lock size={16} aria-label="Bloqueado" />}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function Bitacora({ b }: { b: EntradaBitacora[] }) {
  const [cat, setCat] = useState('todo')
  const filtradas = useMemo(() => b.filter(CATEGORIAS.find((c) => c.id === cat)?.prueba ?? (() => true)), [b, cat])
  return (
    <Panel
      titulo="Bitácora"
      bajada={`${num(b.length)} entradas, de la más reciente a la más antigua.`}
      extra={
        <div className="pestanas" role="tablist">
          {CATEGORIAS.map((c) => (
            <button key={c.id} role="tab" aria-selected={cat === c.id} onClick={() => setCat(c.id)}>
              {c.nombre}
            </button>
          ))}
        </div>
      }
    >
      <div className="tabla-scroll">
        <table className="tabla">
          <thead>
            <tr>
              <th>Cuándo</th>
              <th>Quién</th>
              <th>Qué hizo</th>
              <th>Sobre qué</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {filtradas.slice(0, 200).map((e) => (
              <tr key={e.id} className={tono(e) ? `fila--${tono(e)}` : ''}>
                <td className="nowrap">{fFechaHora(e.fecha)}</td>
                <td>
                  {e.actor}
                  {e.rol !== '-' && <div className="muted">{e.rol}</div>}
                </td>
                <td>
                  <strong>{e.accion}</strong>
                </td>
                <td className="mono">{e.objetivo}</td>
                <td>{e.detalle}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
