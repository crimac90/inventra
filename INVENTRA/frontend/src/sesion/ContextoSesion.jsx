/*
  Estado de la sesion, compartido por toda la aplicacion.

  El problema: muchas pantallas necesitan saber quien entro y con que rol. Pasar
  ese dato de componente en componente seria insostenible. React resuelve esto
  con un «contexto»: un valor que se declara arriba del arbol y que cualquier
  componente de abajo puede leer sin recibirlo por parametro.

  Aqui viven tres cosas: el usuario de la sesion, si todavia se esta comprobando
  la sesion guardada, y las funciones para entrar y salir.
*/

import { createContext, useContext, useEffect, useState } from "react";

import { consultarPerfil, ingresar as ingresarApi, salir as salirApi } from "../api/seguridad";
import { tokenDeAcceso } from "../api/cliente";

const ContextoSesion = createContext(null);

export function ProveedorSesion({ children }) {
  const [usuario, setUsuario] = useState(null);
  const [comprobando, setComprobando] = useState(true);

  /*
    Al arrancar la aplicacion puede haber un token guardado de una visita
    anterior. Tener el token no basta: puede estar vencido o la cuenta pudo
    inactivarse. La unica forma de saberlo es preguntarle al servidor, y eso es
    lo que hace esta consulta al perfil.
  */
  useEffect(() => {
    if (!tokenDeAcceso()) {
      setComprobando(false);
      return;
    }

    let vigente = true;
    consultarPerfil()
      .then((datos) => {
        if (vigente) setUsuario(datos);
      })
      .catch(() => {
        if (vigente) setUsuario(null);
      })
      .finally(() => {
        if (vigente) setComprobando(false);
      });

    // Si el componente se desmonta antes de que llegue la respuesta, se evita
    // escribir en un estado que ya no existe.
    return () => {
      vigente = false;
    };
  }, []);

  async function entrar(credenciales, recordar) {
    const datos = await ingresarApi(credenciales, recordar);
    setUsuario(datos);
    return datos;
  }

  async function salir() {
    await salirApi();
    setUsuario(null);
  }

  return (
    <ContextoSesion.Provider value={{ usuario, setUsuario, comprobando, entrar, salir }}>
      {children}
    </ContextoSesion.Provider>
  );
}

/* Atajo para leer la sesion desde cualquier pantalla. */
export function useSesion() {
  const valor = useContext(ContextoSesion);
  if (valor === null) {
    throw new Error("useSesion se uso fuera del ProveedorSesion");
  }
  return valor;
}
