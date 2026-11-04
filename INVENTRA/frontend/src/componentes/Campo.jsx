/*
  Campo de formulario.

  Agrupa la etiqueta, el cuadro de texto y el mensaje de error. Se hace asi para
  no repetir la misma estructura en cada pantalla y, sobre todo, para que la
  accesibilidad quede resuelta en un solo lugar: la etiqueta queda asociada al
  campo por su identificador, y cuando hay error se marca con aria-invalid y el
  mensaje se anuncia a los lectores de pantalla.

  `minimo` lo usan los campos de fecha —marca el primer dia que el calendario
  deja elegir— y los numericos, donde impide que las flechas bajen de ese
  valor. Es una ayuda del navegador, no una validacion: la regla que de verdad
  rechaza un dato esta en el servidor.
*/

import { useState } from "react";

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
  /*
    La rueda del raton sobre una casilla numerica con el foco puesto CAMBIA SU
    VALOR. Es comportamiento del navegador, no del sistema, y en un formulario
    largo es una trampa: se escribe un precio, se baja para seguir leyendo y el
    precio cambia solo, sin que nadie lo toque y sin que se note.

    Quitarle el foco a la casilla antes de que el navegador procese la rueda
    deja pasar el desplazamiento de la pagina y no el cambio de valor. Se
    resuelve aqui y no en cada pantalla porque es de todas las casillas
    numericas del sistema, las de hoy y las de ventas.
  */
  function alGirarLaRueda(evento) {
    if (tipo === "number") evento.currentTarget.blur();
  }

  /*
    Mostrar u ocultar la contrasena. Escribir a ciegas una clave larga en un
    teclado de celular es la primera causa de que alguien no consiga entrar con
    la contrasena correcta, y el error no se ve hasta que el sistema la
    rechaza. Nace oculta, que es como tiene que estar mientras nadie pida lo
    contrario.
  */
  const [visible, setVisible] = useState(false);
  const esContrasena = tipo === "password";
  const tipoReal = esContrasena && visible ? "text" : tipo;

  return (
    <div className="field">
      <label htmlFor={id}>{etiqueta}</label>
      <div className={esContrasena ? "campo-con-ojo" : undefined}>
      <input
        id={id}
        name={id}
        type={tipoReal}
        value={valor}
        placeholder={marcador}
        min={minimo}
        onWheel={alGirarLaRueda}
        autoComplete={autoComplete}
        required={requerido}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? `${id}-error` : ayuda ? `${id}-ayuda` : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {esContrasena && (
        <button
          type="button"
          className="ojo"
          onClick={() => setVisible((v) => !v)}
          aria-pressed={visible}
          aria-label={visible ? "Ocultar la contraseña" : "Mostrar la contraseña"}
          title={visible ? "Ocultar" : "Mostrar"}
        >
          {visible ? "Ocultar" : "Mostrar"}
        </button>
      )}
      </div>
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
