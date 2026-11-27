import { ArrowLeft, BadgeDollarSign, Check, Copy, KeyRound, Link2, MessageCircle, Search, UserX } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { DenunciaPublica } from '../api/types'
import { Marca } from '../components/Marca'
import { fFechaHora } from '../lib/format'

const TIPOS = [
  { id: 'venta_de_citas', texto: 'Me ofrecieron una cita médica a cambio de dinero', icono: BadgeDollarSign },
  { id: 'pedido_de_datos', texto: 'Me llamaron o escribieron pidiendo mis datos o claves', icono: KeyRound },
  { id: 'enlace_sospechoso', texto: 'Recibí un mensaje o enlace sospechoso', icono: Link2 },
  { id: 'uso_de_mis_datos', texto: 'Creo que alguien usó mis datos o mi cita', icono: UserX },
  { id: 'otro', texto: 'Otra situación', icono: MessageCircle },
] as const

const MEDIOS = [
  ['llamada', 'Llamada'],
  ['whatsapp', 'WhatsApp'],
  ['mensaje', 'Mensaje de texto'],
  ['correo', 'Correo'],
  ['en_persona', 'En persona'],
  ['redes_sociales', 'Redes sociales'],
] as const

type Tipo = (typeof TIPOS)[number]['id']

export default function Denuncia() {
  const [paso, setPaso] = useState<1 | 2 | 3>(1)
  const [tipo, setTipo] = useState<Tipo | null>(null)
  const [medio, setMedio] = useState('')
  const [cuando, setCuando] = useState('')
  const [contacto, setContacto] = useState('')
  const [enlace, setEnlace] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [responder, setResponder] = useState('')
  const [acepta, setAcepta] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState('')
  const [codigo, setCodigo] = useState<string | null>(null)
  const [copiado, setCopiado] = useState(false)

  async function enviar() {
    if (!tipo) return
    setEnviando(true)
    setError('')
    try {
      const r = await api.denunciar({
        tipo,
        medio,
        cuando,
        contacto_sospechoso: contacto,
        enlace,
        descripcion,
        responder_a: responder,
        acepta_privacidad: acepta,
      })
      setCodigo(r.codigo)
      setPaso(3)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo enviar la denuncia.')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="publico">
      <header className="publico__cabecera">
        <Marca claro={false} />
        <span>Canal de denuncias</span>
      </header>

      <main className="publico__cuerpo">
        <div className="publico__consejo">
          Pedir una cita médica es gratis. Nadie del personal de salud te pedirá dinero, tu contraseña ni códigos que te
          lleguen por mensaje.
        </div>

        {paso === 1 && (
          <section aria-labelledby="t1">
            <h1 id="t1">¿Qué te pasó?</h1>
            <p className="publico__bajada">Elige la opción que más se parezca. No necesitas dar tu nombre ni tu cédula.</p>
            <div className="tipos">
              {TIPOS.map((t) => (
                <button
                  key={t.id}
                  className={`tipo ${tipo === t.id ? 'tipo--sel' : ''}`}
                  onClick={() => {
                    setTipo(t.id)
                    setPaso(2)
                  }}
                >
                  <t.icono size={34} aria-hidden />
                  <span>{t.texto}</span>
                </button>
              ))}
            </div>
          </section>
        )}

        {paso === 2 && tipo && (
          <section aria-labelledby="t2">
            <button className="publico__volver" onClick={() => setPaso(1)}>
              <ArrowLeft size={20} aria-hidden /> Cambiar lo que pasó
            </button>
            <h1 id="t2">Cuéntanos un poco más</h1>
            <p className="publico__bajada">
              Elegiste: <strong>{TIPOS.find((t) => t.id === tipo)?.texto}</strong>. Todo lo que sigue es opcional, pero
              nos ayuda a encontrar a quien lo hizo.
            </p>

            <fieldset className="publico__grupo">
              <legend>¿Por dónde te contactaron?</legend>
              <div className="opciones">
                {MEDIOS.map(([id, texto]) => (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={medio === id}
                    className={`opcion ${medio === id ? 'opcion--sel' : ''}`}
                    onClick={() => setMedio(medio === id ? '' : id)}
                  >
                    {texto}
                  </button>
                ))}
              </div>
            </fieldset>

            <div className="publico__campos">
              <label>
                ¿Cuándo pasó?
                <input type="date" value={cuando} onChange={(e) => setCuando(e.target.value)} />
              </label>
              <label>
                Número, usuario o cuenta de quien te contactó
                <input
                  value={contacto}
                  onChange={(e) => setContacto(e.target.value)}
                  maxLength={80}
                  placeholder="Por ejemplo, el número de WhatsApp"
                />
                <small>Lo guardamos protegido: el equipo de seguridad solo ve los últimos 4 caracteres.</small>
              </label>
              {(tipo === 'enlace_sospechoso' || tipo === 'pedido_de_datos') && (
                <label>
                  Enlace que te enviaron
                  <input value={enlace} onChange={(e) => setEnlace(e.target.value)} maxLength={500} placeholder="Pégalo aquí. No lo abras." />
                </label>
              )}
              <label>
                ¿Qué pasó?
                <textarea
                  value={descripcion}
                  onChange={(e) => setDescripcion(e.target.value)}
                  maxLength={1500}
                  rows={4}
                  placeholder="Cuéntalo con tus palabras. No escribas tu cédula ni datos médicos."
                />
              </label>
              <label>
                ¿Quieres que te respondamos? (opcional)
                <input value={responder} onChange={(e) => setResponder(e.target.value)} maxLength={120} placeholder="Correo o teléfono" />
              </label>
            </div>

            <label className="publico__acepto">
              <input type="checkbox" checked={acepta} onChange={(e) => setAcepta(e.target.checked)} />
              <span>
                Entiendo que esta denuncia la revisa el equipo de seguridad, que no me piden cédula ni nombre, y que el
                número que reporto se guarda protegido.
              </span>
            </label>
            {error && (
              <p className="publico__error" role="alert">
                {error}
              </p>
            )}
            <button className="boton boton--enorme" disabled={!acepta || enviando} onClick={enviar}>
              {enviando ? 'Enviando…' : 'Enviar denuncia'}
            </button>
          </section>
        )}

        {paso === 3 && codigo && (
          <section className="recibida" aria-labelledby="t3">
            <Check size={44} aria-hidden className="recibida__ok" />
            <h1 id="t3">Recibimos tu denuncia</h1>
            <p>Guarda este código. Con él puedes ver cómo va tu denuncia y la respuesta del equipo de seguridad.</p>
            <div className="recibida__codigo">{codigo}</div>
            <button
              className="boton boton--secundario boton--grande"
              onClick={() => {
                navigator.clipboard?.writeText(codigo).then(() => setCopiado(true)).catch(() => undefined)
              }}
            >
              <Copy size={18} aria-hidden /> {copiado ? 'Código copiado' : 'Copiar código'}
            </button>
            <button
              className="publico__volver"
              onClick={() => {
                setPaso(1)
                setTipo(null)
                setCodigo(null)
                setAcepta(false)
                setContacto('')
                setEnlace('')
                setDescripcion('')
                setMedio('')
                setCuando('')
                setResponder('')
                setCopiado(false)
              }}
            >
              Hacer otra denuncia
            </button>
          </section>
        )}

        <Seguimiento key={codigo ?? 'nueva'} inicial={codigo ?? ''} />
      </main>
      <footer className="publico__pie">
        Prototipo académico con datos sintéticos. <Link to="/ingresar">Ingreso del personal</Link>
      </footer>
    </div>
  )
}

function Seguimiento({ inicial }: { inicial: string }) {
  const [codigo, setCodigo] = useState(inicial)
  const [r, setR] = useState<DenunciaPublica | null>(null)
  const [error, setError] = useState('')
  return (
    <section className="seguimiento" aria-labelledby="t-seg">
      <h2 id="t-seg">Consultar una denuncia</h2>
      <form
        onSubmit={async (e) => {
          e.preventDefault()
          setError('')
          setR(null)
          try {
            setR(await api.seguimiento(codigo.trim().toUpperCase()))
          } catch (err) {
            setError(err instanceof Error ? err.message : 'No se encontró esa denuncia.')
          }
        }}
      >
        <input
          value={codigo}
          onChange={(e) => setCodigo(e.target.value)}
          placeholder="DN-000000"
          aria-label="Código de la denuncia"
          pattern="[Dd][Nn]-[0-9A-Fa-f]{6}"
          required
        />
        <button className="boton boton--grande">
          <Search size={18} aria-hidden /> Consultar
        </button>
      </form>
      {error && <p className="publico__error">{error}</p>}
      {r && (
        <div className="seguimiento__res">
          <p>
            <strong>{r.codigo}</strong>, enviada el {fFechaHora(r.fecha)}
          </p>
          <p className="seguimiento__estado">{r.estado}</p>
          <p>{r.respuesta}</p>
        </div>
      )}
    </section>
  )
}
