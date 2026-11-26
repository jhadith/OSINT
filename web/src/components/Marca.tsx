/** Marca propia del proyecto: un latido sobre un escudo. No usa logos ni nombres institucionales. */
export function Marca({ claro = true }: { claro?: boolean }) {
  return (
    <span className={`marca ${claro ? 'marca--clara' : ''}`}>
      <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden>
        <path d="M16 2.5 4.5 7v8.2c0 7.2 4.9 12.4 11.5 14.3 6.6-1.9 11.5-7.1 11.5-14.3V7L16 2.5Z" fill="currentColor" opacity=".16" />
        <path
          d="M16 2.5 4.5 7v8.2c0 7.2 4.9 12.4 11.5 14.3 6.6-1.9 11.5-7.1 11.5-14.3V7L16 2.5Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
        />
        <path d="M7.5 16.5h4.2l1.9-5 3 9.5 2.2-6.4 1.3 1.9h4.4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="marca__texto">
        Sentinel <b>Salud</b>
      </span>
    </span>
  )
}
