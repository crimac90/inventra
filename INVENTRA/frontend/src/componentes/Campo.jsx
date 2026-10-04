/*
  Campo de formulario.

  Agrupa la etiqueta, el cuadro de texto y el mensaje de error. Se hace asi para
  no repetir la misma estructura en cada pantalla y, sobre todo, para que la
  accesibilidad quede resuelta en un solo lugar: la etiqueta queda asociada al
  campo por su identificador, y cuando hay error se marca con aria-invalid y el
  mensaje se anuncia a los lectores de pantalla.

  `minimo` solo lo usan los campos de fecha: marca el primer dia que el
  calendario deja elegir. Es una ayuda del navegador, no una validacion; la
  regla que de verdad rechaza una fecha pasada esta en el servidor.
*/

export default function Campo({
  id,
  etiqueta,
  tipo = "text",
  valor,
  onChange,
  marcador,
  error,
  ayuda,
  autoComplete,
  requerido = true,
  minimo,
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{etiqueta}</label>
      <input
        id={id}
        name={id}
        type={tipo}
        value={valor}
        placeholder={marcador}
        min={minimo}
        autoComplete={autoComplete}
        required={requerido}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? `${id}-error` : ayuda ? `${id}-ayuda` : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {ayuda && !error && (
        <div className="ayuda" id={`${id}-ayuda`}>
          {ayuda}
        </div>
      )}
      {error && (
        <div className="msg err" id={`${id}-error`} role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
