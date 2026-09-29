/*
  Estado del modo claro/oscuro para los componentes.

  Devuelve el modo vigente y la funcion que lo cambia. El estado real no vive
  aqui sino en el atributo `data-tema` del <html>, que es lo que el navegador
  pinta; este gancho solo lo refleja para que el interruptor muestre el icono
  correcto y se vuelva a dibujar cuando el modo cambia.

  No hay contexto ni proveedor porque en ningun momento hay dos interruptores en
  pantalla a la vez: el de las pantallas de acceso y el de la barra lateral
  nunca coinciden. Si algun dia hiciera falta un tercero simultaneo, el sitio de
  ese contexto es este archivo.
*/

import { useEffect, useState } from "react";

import { alCambiarElSistema, alternar, pintar, temaVigente } from "./tema";

export default function useTema() {
  const [tema, setTema] = useState(temaVigente);

  useEffect(() => {
    // El sistema operativo puede cambiar de modo con la sesion abierta.
    return alCambiarElSistema((nuevo) => {
      pintar(nuevo);
      setTema(nuevo);
    });
  }, []);

  return { tema, alternarTema: () => setTema(alternar()) };
}
