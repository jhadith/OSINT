import { Check, Lock, LockKeyhole, Megaphone, ShieldAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { Rol, Sesion } from '../api/types'
import { Marca } from '../components/Marca'
import { AREAS, inicioDe } from '../lib/nav'
import { useSesion } from '../lib/sesion'

const PARA_QUIEN: Record<string, string> = {
  jefe: 'Gerencia y jefatura',
  analista: 'Centro de operaciones (SOC)',
  ti: 'Infraestructura',
  salud: 'Médicos y enfermería',
  auditor: 'Control interno',
}

export default function Ingreso() {
  const { sesion, entrar } = useSesion()
  const [roles, setRoles] = useState<Rol[]>([])
  const [usuario, setUsuario] = useState('')
  const [clave, setClave] = useState('')
  const [error, setError] = useState<{ texto: string; bloqueo: boolean } | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [pase, setPase] = useState<Sesion | null>(null)
  const claveRef = useRef<HTMLInputElement>(null)
  const ir = useNavigate()

  useEffect(() => {
    api.roles().then(setRoles).catch(() => setRoles([]))
  }, [])

  if (sesion && !pase) return <Navigate to={inicioDe(sesion.permisos)} replace />

  const elegido = roles.find((r) => r.rol === usuario)

  async function enviar(e: React.FormEvent) {
    e.preventDefault()
    setEnviando(true)
    setError(null)
    try {
      const s = await entrar(usuario, clave)
      setPase(s)
      const reducido = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      setTimeout(() => ir(inicioDe(s.permisos), { replace: true }), reducido ? 600 : 2200)
    } catch (err) {
      const st = err instanceof ApiError ? err.status : 0
      setError({ texto: err instanceof Error ? err.message : 'No se pudo ingresar.', bloqueo: st === 423 })
      setClave('')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="ingreso">
      <section className="ingreso__lado">
        <Marca />
        <div className="ingreso__mensaje">
          <h1>Cada persona ve solo lo que necesita para su trabajo.</h1>
          <p>
            Sentinel Salud vigila los registros del sistema médico y de la red para proteger los datos de salud de
            afiliados y jubilados. El acceso se concede por rol: lo demás queda bloqueado y cada acción queda registrada.
          </p>
        </div>
        <Link to="/denuncia" className="ingreso__publico">
          <Megaphone size={22} aria-hidden />
          <span>
            <strong>¿Eres afiliado o jubilado?</strong>
            Denuncia la venta de citas o una llamada sospechosa sin iniciar sesión.
          </span>
        </Link>
        <svg className="ingreso__ecg" viewBox="0 0 600 60" aria-hidden preserveAspectRatio="none">
          <path d="M0 40h150l8-14 8 24 10-46 10 50 8-14h120l8-14 8 24 10-46 10 50 8-14h232" />
        </svg>
      </section>

      <section className="ingreso__form" aria-labelledby="t-ingreso">
        <h2 id="t-ingreso">¿Con qué rol vas a ingresar?</h2>
        <p className="ingreso__ayuda">Elige tu rol: verás de inmediato qué áreas se abren y cuáles quedan cerradas.</p>
        <div className="roles" role="radiogroup" aria-label="Rol">
          {roles.map((r) => {
            const sel = r.rol === usuario
            return (
              <button
                key={r.rol}
                type="button"
                role="radio"
                aria-checked={sel}
                className={`rol ${sel ? 'rol--sel' : ''}`}
                onClick={() => {
                  setUsuario(r.rol)
                  setError(null)
                  setTimeout(() => claveRef.current?.focus(), 0)
                }}
              >
                <span className="rol__para">{PARA_QUIEN[r.rol] ?? ''}</span>
                <span className="rol__nombre">{r.nombre}</span>
                <span className="rol__desc">{r.descripcion}</span>
                <span className="rol__areas" aria-label="Áreas">
                  {AREAS.map((a) => {
                    const si = r.permisos.includes(a.permiso)
                    return (
                      <span key={a.permiso} className={si ? 'si' : 'no'} title={`${a.nombre}: ${si ? 'con acceso' : 'bloqueado'}`}>
                        {si ? <a.icono size={15} aria-hidden /> : <Lock size={13} aria-hidden />}
                      </span>
                    )
                  })}
                </span>
                {sel && <Check className="rol__check" size={18} aria-hidden />}
              </button>
            )
          })}
        </div>

        <form onSubmit={enviar} className="ingreso__campos">
          <label>
            Usuario
            <input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" required />
          </label>
          <label>
            Contraseña
            <input
              ref={claveRef}
              type="password"
              value={clave}
              onChange={(e) => setClave(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <button className="boton boton--grande" disabled={enviando || !usuario || !clave}>
            {enviando ? 'Verificando…' : elegido ? `Ingresar como ${elegido.nombre}` : 'Ingresar'}
          </button>
          {error &&
            (error.bloqueo ? (
              <div className="bloqueo" role="alert">
                <LockKeyhole size={34} aria-hidden />
                <div>
                  <strong>Cuenta bloqueada temporalmente</strong>
                  <p>{error.texto}</p>
                </div>
              </div>
            ) : (
              <p className="ingreso__error" role="alert">
                <ShieldAlert size={18} aria-hidden /> {error.texto}
              </p>
            ))}
          <p className="ingreso__demo">
            Demostración: los usuarios son <code>jefe</code>, <code>analista</code>, <code>ti</code>, <code>salud</code> y{' '}
            <code>auditor</code>; la contraseña es <code>demo2026</code>. Cinco intentos fallidos bloquean la cuenta 5 minutos.
          </p>
        </form>
      </section>

      {pase && (
        <div className="pase" role="status" aria-live="polite">
          <div className="pase__tarjeta">
            <p className="pase__ok">Acceso concedido</p>
            <p className="pase__rol">{pase.rolNombre}</p>
            <p className="pase__nombre">{pase.nombre}</p>
            <ul>
              {AREAS.map((a, i) => {
                const si = pase.permisos.includes(a.permiso)
                return (
                  <li key={a.permiso} className={si ? 'si' : 'no'} style={{ animationDelay: `${300 + i * 140}ms` }}>
                    {si ? <Check size={18} aria-hidden /> : <Lock size={16} aria-hidden />}
                    <span>{a.nombre}</span>
                    <em>{si ? 'abierto' : 'cerrado'}</em>
                  </li>
                )
              })}
            </ul>
            <p className="pase__pie">La sesión dura 8 horas y queda registrada en la bitácora.</p>
          </div>
        </div>
      )}
    </div>
  )
}
