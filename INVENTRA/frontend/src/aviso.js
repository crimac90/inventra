/*
  Cuanto dura en pantalla el aviso de una operacion.

  La duracion vive aqui y no en cada pantalla porque es una sola regla y son
  siete las pantallas que escriben avisos: repartida, cada una la resolveria a
  su manera, y un «Producto actualizado» que sobrevive a abrir otro producto
  deja de informar y empieza a confundir. Es el mismo criterio con el que
  `formato.js` y `texto.js` guardan lo que vale para todas.

  Lo que salio bien se anuncia y se va: la persona lo vio, la pantalla ya
  muestra el resultado y el aviso solo estorba. Lo que fallo se queda hasta que
  se intente otra cosa, porque hay algo que leer y casi siempre algo que
  corregir, y un mensaje que se desvanece mientras se lee es peor que no
  tenerlo.

  Se usa como `useState`, a proposito: una pantalla llama a
  `setAviso({ tipo, texto })` sin tener que saber que detras hay un
  temporizador. Lo unico que decide este archivo es cuanto dura.
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
