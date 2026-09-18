/*
  Guardia de las pantallas internas.

  Envuelve una ruta y decide si se puede ver. Mientras se comprueba la sesion
  guardada no se decide nada, porque en ese instante «usuario» todavia es nulo y
  se expulsaria a alguien que si tiene sesion valida.

  Aclaracion importante para la sustentacion: esto NO es la seguridad del
  sistema, es comodidad de la interfaz. Quien quiera puede saltarse una
  comprobacion hecha en el navegador. La seguridad real esta en el backend, que
  exige el token en cada peticion y filtra por licorera en cada consulta.
*/

import { Navigate } from "react-router-dom";

import { useSesion } from "./ContextoSesion";

export default function RutaPrivada({ children }) {
  const { usuario, comprobando } = useSesion();

  if (comprobando) {
    return <div style={{ padding: "32px", color: "var(--muted)" }}>Cargando…</div>;
  }

  if (!usuario) {
    return <Navigate to="/acceso" replace />;
  }

  return children;
}
