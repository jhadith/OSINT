import { Circle, ImagePlus, Loader2, Mic, PenLine, RotateCcw, Square, Trash2 } from 'lucide-react'
import { type ChangeEvent, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { TextoProtegido } from './TextoProtegido'

/** Grabación o foto de la denuncia. Se sube al momento y vuelve como texto con los datos personales protegidos. */
export interface Adjunto {
  nombre: string
  tipo: 'audio' | 'imagen'
  blob: Blob
  url: string
  estado: 'subiendo' | 'listo' | 'pendiente'
  id?: string
  texto?: string | null
}

type Modo = 'texto' | 'voz'
const MAX_ADJUNTOS = 3
const TOPE_MB = { imagen: 15, audio: 25 } as const
const DURACION = 180 // segundos de nota de voz

const FORMATOS = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm', 'audio/mp4']

function extension(mime: string) {
  if (mime.includes('ogg')) return 'ogg'
  if (mime.includes('mp4')) return 'm4a'
  return 'webm'
}

function tipoDe(f: File): Adjunto['tipo'] | null {
  if (f.type.startsWith('image/')) return 'imagen'
  if (f.type.startsWith('audio/')) return 'audio'
  return null
}

/** El navegador solo deja usar micrófono y cámara en localhost o con HTTPS. */
function puedeGrabar() {
  return typeof window !== 'undefined' && window.isSecureContext && !!navigator.mediaDevices?.getUserMedia && 'MediaRecorder' in window
}

interface Props {
  descripcion: string
  setDescripcion: (v: string) => void
  adjuntos: Adjunto[]
  setAdjuntos: (fn: (a: Adjunto[]) => Adjunto[]) => void
}

/** «¿Cómo quieres contarlo?»: escribir o grabar una nota de voz, más fotos o capturas. */
export function Contar({ descripcion, setDescripcion, adjuntos, setAdjuntos }: Props) {
  const [modo, setModo] = useState<Modo>('texto')
  const [error, setError] = useState('')
  const lleno = adjuntos.length >= MAX_ADJUNTOS

  const agregar = (a: Adjunto) => {
    if (a.blob.size > TOPE_MB[a.tipo] * 1024 * 1024) {
      URL.revokeObjectURL(a.url)
      setError(`El archivo pesa más de ${TOPE_MB[a.tipo]} MB. Prueba con uno más corto.`)
      return
    }
    setError('')
    setAdjuntos((l) => (l.length >= MAX_ADJUNTOS ? l : [...l, { ...a, estado: 'subiendo' }]))
    // se sube de una vez: el servidor lo pasa a texto en este equipo y devuelve el texto protegido
    api
      .subirAdjunto(a.blob, a.nombre)
      .then((r) =>
        setAdjuntos((l) =>
          l.map((x) =>
            x.url === a.url ? { ...x, id: r.id, texto: r.texto, estado: r.estado === 'procesado' ? 'listo' : 'pendiente' } : x,
          ),
        ),
      )
      .catch((e: Error) => {
        URL.revokeObjectURL(a.url)
        setAdjuntos((l) => l.filter((x) => x.url !== a.url))
        setError(e.message || 'No se pudo subir el archivo. Inténtalo otra vez.')
      })
  }

  const elegir = (e: ChangeEvent<HTMLInputElement>) => {
    for (const f of Array.from(e.target.files ?? [])) {
      const tipo = tipoDe(f)
      if (!tipo) {
        setError('Solo se aceptan fotos o notas de voz. Si tienes un video, cuéntalo por voz o por escrito.')
        continue
      }
      agregar({ nombre: f.name, tipo, blob: f, url: URL.createObjectURL(f), estado: 'subiendo' })
    }
    e.target.value = ''
  }

  return (
    <fieldset className="contar">
      <legend>¿Cómo quieres contarlo?</legend>
      <div className="contar__modos" role="tablist" aria-label="Forma de contar lo que pasó">
        {(
          [
            ['texto', 'Escribir', PenLine],
            ['voz', 'Grabar voz', Mic],
          ] as const
        ).map(([id, texto, Icono]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={modo === id}
            className={`contar__modo ${modo === id ? 'contar__modo--sel' : ''}`}
            onClick={() => setModo(id)}
          >
            <Icono size={26} aria-hidden />
            {texto}
          </button>
        ))}
      </div>

      <div className="contar__panel" role="tabpanel">
        {modo === 'texto' && (
          <label className="contar__texto">
            ¿Qué pasó?
            <textarea
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              maxLength={1500}
              rows={5}
              placeholder="Cuéntalo con tus palabras. No escribas tu cédula ni datos médicos."
            />
          </label>
        )}
        {modo === 'voz' && <Grabadora deshabilitada={lleno} alTerminar={agregar} alFallar={setError} />}
        {modo === 'voz' && (
          <p className="contar__nota">
            Lo que grabes se pasa a texto y el audio se borra. Al equipo de seguridad solo le llega lo que pasó: si mencionas una
            cédula, un nombre o un teléfono, sale como [Cédula protegida], [Nombre protegido] o [Teléfono protegido].
          </p>
        )}
      </div>

      <div className="contar__extra">
        <label className={`boton boton--secundario ${lleno ? 'boton--apagado' : ''}`}>
          <ImagePlus size={18} aria-hidden /> Adjuntar foto, captura o audio
          <input type="file" accept="image/*,audio/*" onChange={elegir} disabled={lleno} hidden multiple />
        </label>
        <span className="contar__cupo">
          {adjuntos.length} de {MAX_ADJUNTOS} archivos
        </span>
      </div>
      {error && (
        <p className="publico__error" role="alert">
          {error}
        </p>
      )}

      {adjuntos.length > 0 && (
        <ul className="contar__lista">
          {adjuntos.map((a, i) => (
            <li key={a.url}>
              {a.tipo === 'imagen' && <img src={a.url} alt={`Adjunto ${i + 1}`} />}
              {a.tipo === 'audio' && <audio src={a.url} controls />}
              <span className="contar__nombre">
                {a.tipo === 'audio' ? 'Nota de voz' : 'Foto'} ·{' '}
                {(a.blob.size / 1024 / 1024).toFixed(1)} MB
              </span>
              <div className={`contar__llega contar__llega--${a.estado}`} aria-live="polite">
                {a.estado === 'subiendo' ? (
                  <span>
                    <Loader2 size={16} aria-hidden className="gira" /> Pasando a texto en este equipo…
                  </span>
                ) : a.estado === 'listo' ? (
                  <>
                    <strong>Así le llega al equipo de seguridad:</strong>
                    <p>{a.texto ? <TextoProtegido texto={a.texto} /> : 'No se reconoció texto. Puedes escribirlo en «Escribir».'}</p>
                  </>
                ) : (
                  <span>Recibido. El equipo de seguridad lo pasará a texto, con tus datos personales protegidos.</span>
                )}
              </div>
              <button
                type="button"
                className="boton boton--fantasma boton--chico"
                onClick={() => {
                  URL.revokeObjectURL(a.url)
                  setAdjuntos((l) => l.filter((x) => x.url !== a.url))
                }}
              >
                <Trash2 size={15} aria-hidden /> Quitar
              </button>
            </li>
          ))}
        </ul>
      )}
    </fieldset>
  )
}

function Grabadora({
  deshabilitada,
  alTerminar,
  alFallar,
}: {
  deshabilitada: boolean
  alTerminar: (a: Adjunto) => void
  alFallar: (m: string) => void
}) {
  const [fase, setFase] = useState<'listo' | 'pidiendo' | 'grabando' | 'grabado'>('listo')
  const [segundos, setSegundos] = useState(0)
  const [toma, setToma] = useState<Adjunto | null>(null)
  const flujo = useRef<MediaStream | null>(null)
  const grabador = useRef<MediaRecorder | null>(null)
  const reloj = useRef<number | null>(null)

  const apagar = () => {
    if (reloj.current) window.clearInterval(reloj.current)
    reloj.current = null
    flujo.current?.getTracks().forEach((t) => t.stop())
    flujo.current = null
  }
  useEffect(() => apagar, [])

  if (!puedeGrabar())
    return (
      <div className="grabadora grabadora--sin">
        <p>
          Este navegador no deja grabar desde aquí (hace falta abrir la página en el mismo equipo o con una conexión segura).
          Puedes grabar una nota de voz con tu teléfono y adjuntarla abajo, o escribir lo que pasó.
        </p>
      </div>
    )

  const empezar = async () => {
    setFase('pidiendo')
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      flujo.current = s
      const mime = FORMATOS.find((f) => MediaRecorder.isTypeSupported(f)) ?? ''
      const r = new MediaRecorder(s, mime ? { mimeType: mime, audioBitsPerSecond: 64_000 } : undefined)
      const partes: Blob[] = []
      r.ondataavailable = (e) => e.data.size && partes.push(e.data)
      r.onstop = () => {
        apagar()
        const tipo = r.mimeType || mime || 'audio/webm'
        const blob = new Blob(partes, { type: tipo })
        const a: Adjunto = {
          nombre: `nota-de-voz.${extension(tipo)}`,
          tipo: 'audio',
          blob,
          url: URL.createObjectURL(blob),
          estado: 'subiendo',
        }
        setToma(a)
        setFase('grabado')
      }
      grabador.current = r
      r.start(1000)
      setSegundos(0)
      setFase('grabando')
      const inicio = Date.now()
      reloj.current = window.setInterval(() => {
        const seg = Math.floor((Date.now() - inicio) / 1000)
        setSegundos(seg)
        if (seg >= DURACION && r.state === 'recording') r.stop()
      }, 500)
    } catch {
      apagar()
      setFase('listo')
      alFallar('No pudimos usar el micrófono. Revisa que le diste permiso al navegador.')
    }
  }

  const detener = () => grabador.current?.state === 'recording' && grabador.current.stop()
  const mm = (n: number) => `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`

  return (
    <div className={`grabadora grabadora--${fase}`}>
      {fase === 'grabado' && toma && (
        <>
          <audio src={toma.url} controls className="grabadora__audio" />
          <div className="grabadora__acciones">
            <button
              type="button"
              className="boton boton--grande"
              disabled={deshabilitada}
              onClick={() => {
                alTerminar(toma)
                setToma(null)
                setFase('listo')
              }}
            >
              Usar esta grabación
            </button>
            <button
              type="button"
              className="boton boton--secundario boton--grande"
              onClick={() => {
                URL.revokeObjectURL(toma.url)
                setToma(null)
                setFase('listo')
              }}
            >
              <RotateCcw size={18} aria-hidden /> Grabar de nuevo
            </button>
          </div>
        </>
      )}
      {fase !== 'grabado' && (
        <div className="grabadora__control">
          {fase === 'grabando' ? (
            <button type="button" className="grabadora__boton grabadora__boton--parar" onClick={detener}>
              <Square size={30} aria-hidden fill="currentColor" />
              <span className="sr">Detener</span>
            </button>
          ) : (
            <button
              type="button"
              className="grabadora__boton"
              onClick={empezar}
              disabled={deshabilitada || fase === 'pidiendo'}
              aria-label="Empezar a grabar la voz"
            >
              <Mic size={34} aria-hidden />
            </button>
          )}
          <div className="grabadora__estado" aria-live="polite">
            {fase === 'grabando' ? (
              <>
                <Circle size={12} aria-hidden fill="currentColor" className="grabadora__rec" /> Grabando {mm(segundos)} de{' '}
                {mm(DURACION)}. Toca el cuadrado para terminar.
              </>
            ) : fase === 'pidiendo' ? (
              'Dale permiso al navegador para usar el micrófono.'
            ) : deshabilitada ? (
              'Ya tienes 3 archivos. Quita uno para grabar otro.'
            ) : (
              `Toca el micrófono y cuéntanos qué pasó. Hasta ${DURACION / 60} minutos.`
            )}
          </div>
        </div>
      )}
    </div>
  )
}
