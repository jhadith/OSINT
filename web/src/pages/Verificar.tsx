import { CircleCheck, ImageUp, Link2, OctagonAlert, Send, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import type { Verificacion } from '../api/types'
import { Pagina } from '../components/ui'

const VEREDICTO = {
  seguro: { titulo: 'No encontramos señales de peligro', icono: CircleCheck },
  sospechoso: { titulo: 'Tiene señales sospechosas', icono: TriangleAlert },
  malicioso: { titulo: 'Es peligroso: no lo abras', icono: OctagonAlert },
} as const

export default function Verificar() {
  const [url, setUrl] = useState('')
  const [res, setRes] = useState<Verificacion | null>(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState('')

  async function revisar(p: Promise<Verificacion>) {
    setCargando(true)
    setError('')
    setRes(null)
    try {
      setRes(await p)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo revisar.')
    } finally {
      setCargando(false)
    }
  }

  return (
    <Pagina
      titulo="Verificar contenido"
      bajada="¿Te llegó un enlace o una imagen y no estás seguro? Revísalo aquí antes de abrirlo. El enlace no se abre ni se consulta en internet."
    >
      <div className="verificar">
        <form
          className="verificar__caja"
          onSubmit={(e) => {
            e.preventDefault()
            if (url.trim()) revisar(api.verificarEnlace(url.trim()))
          }}
        >
          <Link2 size={28} aria-hidden />
          <h2>Un enlace</h2>
          <label className="campo">
            Pega el enlace que te enviaron
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" maxLength={2000} />
          </label>
          <button className="boton boton--grande" disabled={!url.trim() || cargando}>
            Revisar enlace
          </button>
        </form>
        <label className="verificar__caja verificar__caja--imagen">
          <ImageUp size={28} aria-hidden />
          <h2>Una imagen o captura</h2>
          <span>Revisamos qué tipo de archivo es en realidad, no lo que dice su nombre.</span>
          <span className="boton boton--grande boton--secundario">Elegir imagen</span>
          <input type="file" accept="image/*" className="sr" onChange={(e) => e.target.files?.[0] && revisar(api.verificarImagen(e.target.files[0]))} />
        </label>
      </div>

      {cargando && <p className="nota">Revisando…</p>}
      {error && <p className="error-linea">{error}</p>}
      {res && <Resultado key={res.entrada + res.puntuacion} r={res} />}
    </Pagina>
  )
}

function Resultado({ r }: { r: Verificacion }) {
  const v = VEREDICTO[r.veredicto]
  const [comentario, setComentario] = useState('')
  const [codigo, setCodigo] = useState<string | null>(null)
  const [error, setError] = useState('')
  return (
    <section className={`veredicto veredicto--${r.veredicto}`} aria-live="polite">
      <v.icono size={40} aria-hidden />
      <div className="veredicto__cuerpo">
        <h2>{v.titulo}</h2>
        <p className="veredicto__recomendacion">{r.recomendacion}</p>
        <p className="mono quiebre muted">{r.entrada}</p>
        <ul className="senales">
          {r.senales.map((s) => (
            <li key={s.texto} className={`senal senal--${s.tipo}`}>
              {s.texto}
            </li>
          ))}
        </ul>
        {codigo ? (
          <p className="ok-linea">
            Enviado al equipo de seguridad con el código <strong className="mono">{codigo}</strong>. Gracias por avisar.
          </p>
        ) : (
          r.veredicto !== 'seguro' && (
            <div className="reportar">
              <label className="campo">
                ¿Quieres avisar al equipo de seguridad? Cuéntales dónde lo recibiste (opcional)
                <input value={comentario} onChange={(e) => setComentario(e.target.value)} maxLength={600} placeholder="Por ejemplo: llegó por correo a todo el servicio de pediatría" />
              </label>
              {error && <p className="error-linea">{error}</p>}
              <button
                className="boton"
                onClick={() =>
                  api
                    .reportar(r.entrada, r.veredicto, comentario)
                    .then((x) => setCodigo(x.codigo))
                    .catch((e: Error) => setError(e.message))
                }
              >
                <Send size={16} aria-hidden /> Avisar a seguridad
              </button>
            </div>
          )
        )}
      </div>
    </section>
  )
}
