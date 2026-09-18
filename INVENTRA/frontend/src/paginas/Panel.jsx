/*
  Panel principal.

  En este bloque cumple una funcion concreta: comprobar de punta a punta que la
  sesion funciona. Muestra los datos que devuelve la API para el usuario que
  entro y permite cerrar sesion. El panel completo —barra lateral, indicadores y
  accesos a los modulos, tal como esta en el punto 8.2 del documento de diseno—
  se construye en el bloque SEG-4c.
*/

import { useSesion } from "../sesion/ContextoSesion";

const ROLES = {
  administrador_licorera: "Administrador de licorera",
  vendedor: "Vendedor",
  administrador_inventra: "Administrador de INVENTRA",
};

export default function Panel() {
  const { usuario, salir } = useSesion();

  return (
    <div style={{ minHeight: "100vh", padding: "var(--e8) var(--e6)" }}>
      <div style={{ maxWidth: "760px", margin: "0 auto" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "var(--e6)",
          }}
        >
          <div className="logo">
            <span className="mk" aria-hidden="true"></span> INVENTRA
          </div>
          <button className="btn btn-out" type="button" onClick={salir}>
            Cerrar sesión
          </button>
        </div>

        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radio-grande)",
            padding: "var(--e6)",
          }}
        >
          <h1 style={{ fontSize: "22px", fontWeight: 700 }}>
            Hola, {usuario.nombre_completo}
          </h1>
          <p style={{ color: "var(--muted)", fontSize: "14px", marginTop: "6px" }}>
            Sesión iniciada correctamente.
          </p>

          <dl
            style={{
              marginTop: "var(--e6)",
              display: "grid",
              gridTemplateColumns: "auto 1fr",
              gap: "var(--e2) var(--e4)",
              fontSize: "14px",
            }}
          >
            <dt style={{ color: "var(--muted)" }}>Correo</dt>
            <dd>{usuario.correo}</dd>

            <dt style={{ color: "var(--muted)" }}>Rol</dt>
            <dd>{ROLES[usuario.rol] || usuario.rol}</dd>

            <dt style={{ color: "var(--muted)" }}>Licorera</dt>
            <dd>{usuario.licorera_nombre || "Sin licorera asignada"}</dd>
          </dl>
        </div>
      </div>
    </div>
  );
}
