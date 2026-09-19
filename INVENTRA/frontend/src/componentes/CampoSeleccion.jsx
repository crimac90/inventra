/*
  Lista desplegable, con la misma estructura y la misma accesibilidad que Campo.

  Se separa del campo de texto porque el elemento del navegador es otro, pero
  comparte etiqueta, mensaje de error y marcado, de modo que los dos se ven y se
  comportan igual dentro de un formulario.
*/

export default function CampoSeleccion({ id, etiqueta, valor, onChange, opciones, error }) {
  return (
    <div className="field">
      <label htmlFor={id}>{etiqueta}</label>
      <select
        id={id}
        name={id}
        value={valor}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => onChange(e.target.value)}
      >
        {opciones.map((o) => (
          <option key={o.valor} value={o.valor}>
            {o.texto}
          </option>
        ))}
      </select>
      {error && (
        <div className="msg err" id={`${id}-error`} role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
