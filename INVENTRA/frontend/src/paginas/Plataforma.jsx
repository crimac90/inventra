/*
  Panel del Administrador INVENTRA (punto 8.8 del documento de diseno, RF-SUS-05).

  Es la pantalla del operador de la plataforma, no la de un negocio. Muestra las
  licoreras registradas con su plan y su estado, las cifras globales, y las tres
  operaciones que le corresponden: dar de alta, abrir un periodo —renovar o
  subir de plan, que son lo mismo (D-26)— y corregir una fecha mal escrita.

  LO QUE NO ENSENA, Y NO ES UN OLVIDO
  Nada de la informacion comercial de ningun negocio: ni productos, ni ventas,
  ni importes suyos. El requisito lo prohibe y el backend no lo devuelve, asi
  que aqui no hay nada que ocultar; se dice para que nadie lo "complete" mas
  adelante.

  Los textos de los rechazos los escribe el servidor. Esta pantalla los muestra.
*/

import { useCallback, useEffect, useState } from "react";

import Campo from "../componentes/Campo";
import CampoSeleccion from "../componentes/CampoSeleccion";
import Disposicion from "../componentes/Disposicion";
import { mensajeDeError } from "../api/cliente";
import { fecha, moneda } from "../formato";
import {
  abrirPeriodo,
  consultarPlataforma,
  corregirVencimiento,
  darDeAltaLicorera,
} from "../api/plataforma";
import { consultarPlanes } from "../api/suscripciones";

/* La fecha de hoy en el formato que espera un campo de tipo date. */
function hoy() {
  return new Date().toISOString().slice(0, 10);
}

/* Un mes a partir de la fecha dada, que es lo que el formulario propone. */
function dentroDeUnMes(desde) {
  const d = desde ? new Date(`${desde}T00:00:00`) : new Date();
  d.setMonth(d.getMonth() + 1);
  return d.toISOString().slice(0, 10);
}

const TONO = {
  activa: "activo",
  en_prueba: "activo",
  en_mora: "inactivo",
  suspendida: "inactivo",
  cancelada: "inactivo",
};

export default function Plataforma() {
  const [datos, setDatos] = useState(null);
  const [planes, setPlanes] = useState([]);
  const [aviso, setAviso] = useState(null);
  const [ocupado, setOcupado] = useState(false);

  // Que formulario esta abierto: el alta, o una operacion sobre una licorera.
  const [alta, setAlta] = useState(false);
  const [gestionando, setGestionando] = useState(null); // { licorera, modo }

  const cargar = useCallback(() => {
    Promise.all([consultarPlataforma(), consultarPlanes()])
      .then(([panel, catalogo]) => {
        setDatos(panel);
        setPlanes(catalogo);
      })
      .catch((error) =>
        setAviso({
          tipo: "err",
          texto: mensajeDeError(error, "No se pudo cargar el panel."),
        }),
      );
  }, []);

  useEffect(cargar, [cargar]);

  async function ejecutar(accion, exito) {
    setOcupado(true);
    try {
      await accion();
      setAlta(false);
      setGestionando(null);
      setAviso({ tipo: "ok", texto: exito });
      cargar();
    } catch (error) {
      setAviso({
        tipo: "err",
        texto: mensajeDeError(error),
      });
    } finally {
      setOcupado(false);
    }
  }

  if (!datos) {
    return (
      <Disposicion titulo="Plataforma">
        <h1>Plataforma</h1>
        <div className="hs">{aviso ? aviso.texto : "Consultando…"}</div>
      </Disposicion>
    );
  }

  const m = datos.metricas;

  return (
    <Disposicion titulo="Plataforma">
      <div className="barra-herramientas">
        <div>
          <h1>Licoreras registradas</h1>
          <div className="hs" style={{ margin: "6px 0 0" }}>
            Planes, vigencia y cuentas de cada negocio. Sin acceso a su información comercial.
          </div>
        </div>

        {!alta && !gestionando && (
          <button className="btn btn-cta" type="button" onClick={() => setAlta(true)}>
            Dar de alta una licorera
          </button>
        )}
      </div>

      {aviso && (
        <div className={`aviso ${aviso.tipo}`} role={aviso.tipo === "err" ? "alert" : "status"}>
          {aviso.texto}
        </div>
      )}

      <div className="kpis">
        <div className="kpi">
          <div className="k">Licoreras registradas</div>
          <div className="v">{m.licoreras_registradas}</div>
          <div className="d">en toda la plataforma</div>
        </div>
        <div className="kpi">
          <div className="k">Cuentas activas</div>
          <div className="v">{m.cuentas_activas}</div>
          <div className="d">con suscripción vigente</div>
        </div>
        <div className="kpi">
          <div className="k">Ingresos mensuales</div>
          <div className="v" style={{ fontSize: "22px" }}>
            {moneda(m.ingresos_mensuales_recurrentes)}
          </div>
          <div className="d">suma de lo contratado y vigente</div>
        </div>
      </div>

      {alta && (
        <FormularioAlta
          planes={planes}
          ocupado={ocupado}
          onGuardar={(cuerpo) =>
            ejecutar(
              () => darDeAltaLicorera(cuerpo),
              `«${cuerpo.nombre_negocio}» quedó registrada. Se le envió a su administrador el enlace para definir su contraseña.`,
            )
          }
          onCancelar={() => setAlta(false)}
        />
      )}

      {gestionando && (
        <FormularioSuscripcion
          licorera={gestionando.licorera}
          modo={gestionando.modo}
          planes={planes}
          ocupado={ocupado}
          onGuardar={(cuerpo) =>
            gestionando.modo === "periodo"
              ? ejecutar(
                  () => abrirPeriodo(gestionando.licorera.id, cuerpo.plan, cuerpo.fecha_fin),
                  `Período abierto para «${gestionando.licorera.nombre}». Se avisó por correo a su administrador.`,
                )
              : ejecutar(
                  () => corregirVencimiento(gestionando.licorera.id, cuerpo.fecha_fin),
                  `Fecha corregida para «${gestionando.licorera.nombre}».`,
                )
          }
          onCancelar={() => setGestionando(null)}
        />
      )}

      <div className="tabla-caja">
        {datos.licoreras.length === 0 ? (
          <div className="vacio">Todavía no hay licoreras registradas.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Licorera</th>
                <th>Contacto</th>
                <th>Plan</th>
                <th>Estado</th>
                <th>Vigente hasta</th>
                <th>Cuentas</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {datos.licoreras.map((fila) => (
                <tr key={fila.id}>
                  <td>{fila.nombre}</td>
                  <td>{fila.correo}</td>
                  <td>{fila.plan || "—"}</td>
                  <td>
                    <span className={`estado ${TONO[fila.estado] || "inactivo"}`}>
                      {fila.estado_texto}
                    </span>
                  </td>
                  <td>
                    {fecha(fila.fecha_fin)}
                    {fila.dias_restantes != null && fila.puede_operar && (
                      <span className="hs" style={{ display: "block", fontSize: "12px" }}>
                        quedan {fila.dias_restantes} días
                      </span>
                    )}
                  </td>
                  <td>{fila.usuarios_activos}</td>
                  <td className="acciones-fila">
                    <button
                      className="btn btn-out btn-pequeno"
                      type="button"
                      disabled={ocupado}
                      onClick={() => setGestionando({ licorera: fila, modo: "periodo" })}
                    >
                      Renovar o subir
                    </button>
                    {/*
                      Corregir solo tiene sentido si hay una fecha que corregir.
                      Sin suscripcion, lo que corresponde es abrir un periodo.
                    */}
                    {fila.fecha_fin && (
                      <button
                        className="btn btn-out btn-pequeno"
                        type="button"
                        disabled={ocupado}
                        onClick={() => setGestionando({ licorera: fila, modo: "correccion" })}
                      >
                        Corregir fecha
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Disposicion>
  );
}

/* --- Alta de una licorera ------------------------------------------------ */

function FormularioAlta({ planes, ocupado, onGuardar, onCancelar }) {
  const [valores, setValores] = useState({
    nombre_negocio: "",
    nit: "",
    telefono: "",
    nombre_completo: "",
    correo: "",
    plan: "",
    fecha_fin: dentroDeUnMes(),
  });

  const cambiar = (campo) => (valor) => setValores((p) => ({ ...p, [campo]: valor }));
  const completo =
    valores.nombre_negocio && valores.nombre_completo && valores.correo && valores.plan;

  return (
    <form
      className="tarjeta"
      onSubmit={(e) => {
        e.preventDefault();
        onGuardar({ ...valores, plan: Number(valores.plan) });
      }}
    >
      <h2>Dar de alta una licorera</h2>
      <div className="hs">
        La cuenta de su administrador se crea sin contraseña: el sistema le envía el enlace
        para que la defina él mismo.
      </div>

      <Campo id="nombre_negocio" etiqueta="Nombre del negocio"
             valor={valores.nombre_negocio} onChange={cambiar("nombre_negocio")} />
      <Campo id="nit" etiqueta="NIT o cédula" requerido={false}
             valor={valores.nit} onChange={cambiar("nit")} />
      <Campo id="telefono" etiqueta="Teléfono" requerido={false}
             valor={valores.telefono} onChange={cambiar("telefono")} />
      <Campo id="nombre_completo" etiqueta="Nombre del administrador"
             valor={valores.nombre_completo} onChange={cambiar("nombre_completo")} />
      <Campo id="correo" etiqueta="Correo del administrador" tipo="email"
             valor={valores.correo} onChange={cambiar("correo")} />
      <CampoSeleccion id="plan" etiqueta="Plan contratado" valor={valores.plan}
                      onChange={cambiar("plan")}
                      opciones={planes.map((p) => ({ valor: String(p.id), texto: p.nombre }))} />
      <Campo id="fecha_fin" etiqueta="Vigente hasta" tipo="date" minimo={hoy()}
             valor={valores.fecha_fin} onChange={cambiar("fecha_fin")}
             ayuda="El negocio recibirá un correo con esta fecha." />

      <div className="acciones">
        <button className="btn btn-cta" type="submit" disabled={!completo || ocupado}>
          {ocupado ? "Guardando…" : "Dar de alta"}
        </button>
        <button className="btn btn-out" type="button" onClick={onCancelar} disabled={ocupado}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

/* --- Abrir un periodo, o corregir la fecha -------------------------------- */

function FormularioSuscripcion({ licorera, modo, planes, ocupado, onGuardar, onCancelar }) {
  const esPeriodo = modo === "periodo";
  const actual = planes.find((p) => p.nombre === licorera.plan);
  const [valores, setValores] = useState({
    plan: actual ? String(actual.id) : "",
    fecha_fin: esPeriodo ? dentroDeUnMes(licorera.fecha_fin) : licorera.fecha_fin || hoy(),
  });

  const cambiar = (campo) => (valor) => setValores((p) => ({ ...p, [campo]: valor }));

  return (
    <form
      className="tarjeta"
      onSubmit={(e) => {
        e.preventDefault();
        onGuardar({ ...valores, plan: Number(valores.plan) });
      }}
    >
      <h2>
        {esPeriodo ? "Renovar o subir de plan" : "Corregir la fecha de vencimiento"} ·{" "}
        {licorera.nombre}
      </h2>
      <div className="hs">
        {esPeriodo
          ? "Se cierra la suscripción actual y se abre una nueva con el plan y la fecha que indiques. Para bajar de plan, el cambio lo hace el propio negocio desde su cuenta."
          : "Cambia la fecha de la suscripción vigente, sin abrir una nueva. Es para arreglar una fecha mal escrita, no para renovar."}
      </div>

      {esPeriodo && (
        <CampoSeleccion id="plan" etiqueta="Plan" valor={valores.plan} onChange={cambiar("plan")}
                        opciones={planes.map((p) => ({ valor: String(p.id), texto: p.nombre }))} />
      )}
      {/*
        El calendario no deja bajar de hoy: una fecha de vencimiento no puede
        quedar en el pasado (D-25). Es una ayuda, no la regla; el servidor
        vuelve a comprobarlo y es ahi donde la regla esta de verdad.
      */}
      <Campo id="fecha_fin" etiqueta="Vigente hasta" tipo="date" minimo={hoy()}
             valor={valores.fecha_fin} onChange={cambiar("fecha_fin")}
             ayuda="No puede quedar en el pasado. El negocio recibirá un correo con esta fecha." />

      <div className="acciones">
        <button className="btn btn-cta" type="submit" disabled={!valores.fecha_fin || ocupado}>
          {ocupado ? "Guardando…" : esPeriodo ? "Abrir período" : "Corregir fecha"}
        </button>
        <button className="btn btn-out" type="button" onClick={onCancelar} disabled={ocupado}>
          Cancelar
        </button>
      </div>
    </form>
  );
}
