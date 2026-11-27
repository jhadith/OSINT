/** Marca del equipo: escudo ESPEThreat y nombre del producto. Sin logos ni nombres institucionales del reto. */
export function Marca({ claro = true }: { claro?: boolean }) {
  return (
    <span className={`marca ${claro ? 'marca--clara' : ''}`}>
      <img src="/logo-espethreat-360.png" alt="" width={40} height={41} className="marca__logo" />
      <span className="marca__texto">
        Sentinel <b>Salud</b>
        <small>ESPEThreat</small>
      </span>
    </span>
  )
}
