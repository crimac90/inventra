/*
  Guardia de las pantallas internas.

  Envuelve una ruta y decide si se puede ver. Mientras se comprueba la sesion
  guardada no se decide nada, porque en ese instante «usuario» todavia es nulo y
  se expulsaria a alguien que si tiene sesion valida.

  Acepta ademas la lista de roles a los que pertenece la pantalla: a quien no
  esta en ella se le devuelve a su propia pantalla de inicio. Sin lista, la
  pantalla es de cualquiera que tenga sesion, como el perfil.

  Aclaracion importante para la sustentacion: esto NO es la seguridad del
  sistema, es comodidad de la interfaz. Quien quiera puede saltarse una
  comprobacion hecha en el navegador. La seguridad real esta en el backend, que
  exige el token en cada peticion y filtra por licorera en cada consulta.
*/

import { Navigate } from "react-router-dom";

import { destinoTrasEntrar } from "./roles";
import { useSesion } from "./ContextoSesion";

export default function RutaPrivada({ children, roles }) {
  const { usuario, comprobando } = useSesion();

  if (comprobando) {
    return <div style={{ padding: "32px", color: "var(--muted)" }}>Cargando…</div>;
  }

  if (!usuario) {
    return <Navigate to="/acceso" replace />;
  }

  /*
    Cada pantalla declara a que roles pertenece. A quien no esta en la lista no
    se le ensena un error: se le manda a la suya, que es la que si le sirve.
    Vale aqui la misma aclaracion de arriba: esto es comodidad, el backend
    responde 403 igual.

    No puede haber rebote entre dos pantallas, porque el destino sale siempre de
    `destinoTrasEntrar` y esa pantalla admite por definicion al rol que la pide.
  */
  if (roles && !roles.includes(usuario.rol)) {
    return <Navigate to={destinoTrasEntrar(usuario)} replace />;
  }

  return children;
}
