/** Muestra un texto resaltando las etiquetas que reemplazan datos personales ([Cédula protegida], etc.). */
export function TextoProtegido({ texto }: { texto: string }) {
  const partes = texto.split(/(\[(?:Cédula|Nombre|Correo|Teléfono|Fecha) protegid[oa]\])/)
  return (
    <>
      {partes.map((p, i) =>
        i % 2 ? (
          <mark key={i} className="protegido">
            {p}
          </mark>
        ) : (
          p
        ),
      )}
    </>
  )
}
