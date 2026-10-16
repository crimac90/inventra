/*
  Espera antes de actuar sobre lo que se esta escribiendo.

  Un buscador que consulta al servidor en cada tecla manda una peticion por
  letra, y la que contesta de ultima no tiene por que ser la del texto
  completo: el resultado que queda en pantalla puede ser el de «aguardien».
  Esperando a que la escritura se detenga sale una sola peticion, la buena.

  Lo usan la lista de productos y el selector de producto de la entrada de
  mercancia.
*/

import { useEffect, useState } from "react";

/* Devuelve el valor recibido, pero solo despues de que deje de cambiar. */
export function useEspera(valor, milisegundos = 300) {
  const [reposado, setReposado] = useState(valor);

  useEffect(() => {
    const temporizador = setTimeout(() => setReposado(valor), milisegundos);
    // Cada tecla cancela la espera anterior: por eso solo sale la ultima.
    return () => clearTimeout(temporizador);
  }, [valor, milisegundos]);

  return reposado;
}
