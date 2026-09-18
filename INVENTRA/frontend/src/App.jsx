/*
  Mapa de rutas de la aplicacion.

  Cada direccion del navegador se corresponde con una pantalla. Las publicas son
  las del acceso; las internas van envueltas en RutaPrivada, que exige sesion.
*/

import { Navigate, Route, Routes } from "react-router-dom";

import Acceso from "./paginas/Acceso";
import Panel from "./paginas/Panel";
import Registro from "./paginas/Registro";
import RutaPrivada from "./sesion/RutaPrivada";

export default function App() {
  return (
    <Routes>
      {/* La raiz manda al acceso; si ya hay sesion, RutaPrivada deja pasar al panel. */}
      <Route path="/" element={<Navigate to="/acceso" replace />} />

      <Route path="/acceso" element={<Acceso />} />
      <Route path="/registro" element={<Registro />} />

      <Route
        path="/panel"
        element={
          <RutaPrivada>
            <Panel />
          </RutaPrivada>
        }
      />

      {/* Cualquier direccion desconocida vuelve al acceso. */}
      <Route path="*" element={<Navigate to="/acceso" replace />} />
    </Routes>
  );
}
