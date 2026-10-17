/*
  Cuanto dura en pantalla el aviso de una operacion.

  POR QUE AQUI Y NO EN CADA PANTALLA
  Cinco pantallas escriben avisos y ninguna los retiraba: «Producto
  actualizado» sobrevivia a abrir otro producto, y «Fecha corregida» seguia en
  el panel diez minutos despues. Cada una lo habria resuelto a su manera, o
  ninguna, que es lo que pasaba. Es el caso de `formato.js` y `texto.js`: una
  regla que vale para todas vive en un sitio (regla 14).

  LA REGLA
  Lo que salio bien se anuncia y se va: la persona lo vio, la pantalla ya
  muestra el resultado y el aviso solo estorba. Lo que fallo se queda hasta que
  se intente otra cosa, porque hay algo que leer y casi siempre algo que
  corregir, y un mensaje que se desvanece mientras se lee es peor que no
  tenerlo.

  SE USA COMO `useState`, a proposito: las pantallas siguen llamando a
  `setAviso({ tipo, texto })` igual que antes. Lo unico que cambia es quien
  decide cuanto dura.
*/

import { useCallback, useEffect, useRef, useState } from "react";

/* Milisegundos que permanece una confirmacion antes de retirarse sola. */
const DURACION = 6000;

export function useAviso() {
  const [aviso, escribir] = useState(null);
  const temporizador = useRef(null);

  const poner = useCallback((valor) => {
    // El temporizador anterior se cancela siempre: sin esto, un aviso nuevo
    // heredaria la cuenta atras del que acaba de sustituir.
    clearTimeout(temporizador.current);
    escribir(valor);
    if (valor && valor.tipo === "ok") {
      temporizador.current = setTimeout(() => escribir(null), DURACION);
    }
  }, []);

  // Al salir de la pantalla no queda ningun temporizador apuntando a un
  // componente que ya no existe.
  useEffect(() => () => clearTimeout(temporizador.current), []);

  return [aviso, poner];
}
