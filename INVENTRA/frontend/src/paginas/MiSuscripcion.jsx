/*
  Mi suscripcion (punto 8.7 del documento tecnico de diseno, RF-SUS-02 y 03).

  Dos cosas, en este orden: en que estado esta la suscripcion y hasta cuando
  vale, y despues que planes hay y cual se puede contratar.

  POR QUE EL CAMBIO SOLO BAJA
  Bajar de plan no cuesta dinero y lo hace el negocio desde aqui; subir implica
  cobrar y lo ejecuta el Administrador INVENTRA al confirmar el pago (D-23). La
  pantalla no esconde el plan superior: lo muestra y dice como se contrata, que
  es lo que el negocio necesita saber.

  Los textos de los rechazos NO se escriben aqui. El servidor sabe por que dijo
  que no —cuantos usuarios sobran, que la prueba esta en curso— y esta pantalla
  solo lo muestra. Traducir un codigo de estado a una frase fija fue un error
  que ya se corrigio una vez en la gestion de usuarios.
*/

import { useCallback, useEffect, useState } from "react";

import Disposicion from "../componentes/Disposicion";
import Modal from "../componentes/Modal";
import { ErrorApi } from "../api/cliente";
import {
  cambiarDePlan,
  consultarCambiosDePlan,
  consultarMiSuscripcion,
  consultarPlanes,
} from "../api/suscripciones";
import { useSesion } from "../sesion/ContextoSesion";

const MONEDA = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

function fecha(texto) {
  if (!texto) return "—";
  const [anio, mes, dia] = texto.split("-");
  return `${dia}/${mes}/${anio}`;
}

/* Lo que incluye cada plan, dicho con lo que el propio plan declara. */
function caracteristicas(plan) {
  const lista = [
    plan.maximo_usuarios === 1
      ? "Un solo usuario"
      : plan.maximo_usuarios
        ? `Hasta ${plan.maximo_usuarios} usuarios`
        : "Usuarios sin límite",
    plan.maximo_sedes === 1
      ? "Una sede"
      : plan.maximo_sedes
        ? `Hasta ${plan.maximo_sedes} sedes`
        : "Varias sedes",
  ];
  if (plan.permite_reportes_avanzados) lista.push("Reportes avanzados");
  if (plan.permite_facturacion) lista.push("Facturación electrónica");
  return lista;
}

export default function MiSuscripcion() {
  const { usuario } = useSesion();
  const esAdministrador = usuario.rol === "administrador_licorera";

  const [suscripcion, setSuscripcion] = useState(null);
  const [planes, setPlanes] = useState([]);
  // Veredicto del servidor para cada plan: si se puede cambiar y, si no, por que.
  const [veredictos, setVeredictos] = useState({});
  const [aviso, setAviso] = useState(null);
  const [porCambiar, setPorCambiar] = useState(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(() => {
    Promise.all([consultarMiSuscripcion(), consultarPlanes(), consultarCambiosDePlan()])
      .then(([estado, catalogo, cambios]) => {
        setSuscripcion(estado);
        setPlanes(catalogo);
        setVeredictos(Object.fromEntries(cambios.planes.map((c) => [c.plan, c])));
      })
      .catch(() => setAviso({ tipo: "err", texto: "No se pudo consultar tu suscripción." }));
  }, []);

  useEffect(cargar, [cargar]);

  async function confirmarCambio() {
    setOcupado(true);
    try {
      await cambiarDePlan(porCambiar.id);
      setPorCambiar(null);
      setAviso({ tipo: "ok", texto: `Tu licorera pasó al plan ${porCambiar.nombre}.` });
      cargar();
    } catch (error) {
      setPorCambiar(null);
      // El motivo lo da el servidor: cuántos usuarios sobran, o que la prueba
      // está en curso. Aquí no se interpreta el código, se muestra el texto.
      setAviso({
        tipo: "err",
        texto: error instanceof ErrorApi ? error.mensaje : "Ocurrió un error inesperado.",
      });
    } finally {
      setOcupado(false);
    }
  }

  if (!suscripcion) {
    return (
      <Disposicion titulo="Mi suscripción">
        <h1>Mi suscripción</h1>
        <div className="hs">Consultando…</div>
      </Disposicion>
    );
  }

  const actual = planes.find((p) => p.nombre === suscripcion.plan);

  return (
    <Disposicion titulo="Mi suscripción">
      <h1>Mi suscripción</h1>
      <div className="hs">El plan de tu licorera y hasta cuándo está vigente.</div>

      {aviso && (
        <div className={`aviso ${aviso.tipo}`} role="status">
          {aviso.texto}
        </div>
      )}

      <div className="kpis">
        <div className="kpi">
          <div className="k">Plan actual</div>
          <div className="v" style={{ fontSize: "22px" }}>{suscripcion.plan || "—"}</div>
          <div className="d">{suscripcion.estado_texto}</div>
        </div>

        <div className="kpi">
          <div className="k">
            {suscripcion.estado === "en_mora" ? "Se suspende en" : "Vigente hasta"}
          </div>
          <div className="v" style={{ fontSize: "22px" }}>
            {suscripcion.estado === "en_mora"
              ? `${suscripcion.dias_para_suspension} días`
              : fecha(suscripcion.fecha_fin)}
          </div>
          {/*
            `== null` y no `=== null`: cuando la licorera no tiene ninguna
            suscripción, estos campos llegan vacíos, y distinguir entre «nulo» y
            «no vino» no le importa a nadie aquí. Escrito con el triple igual, la
            pantalla llegó a mostrar «quedan undefined días».
          */}
          <div className="d">
            {!suscripcion.plan
              ? "ninguna suscripción registrada"
              : suscripcion.dias_restantes == null
                ? "sin fecha de vencimiento"
                : suscripcion.estado === "en_mora"
                  ? `venció el ${fecha(suscripcion.fecha_fin)}`
                  : `quedan ${suscripcion.dias_restantes} días`}
          </div>
        </div>
      </div>

      {!suscripcion.puede_operar && (
        <div className="aviso err" role="status">
          Tu suscripción no está vigente. Puedes consultar tu información, pero el sistema no
          admite registrar operaciones nuevas hasta que actives un plan.
        </div>
      )}

      <div className="tarjeta">
        <h2>Planes</h2>
        <div className="hs">
          Para contratar o subir de plan, comunícate con INVENTRA: la activación se hace al
          confirmar el pago.
        </div>

        {planes.map((plan) => {
          const esElSuyo = actual && plan.id === actual.id;
          const esMasBarato = actual && Number(plan.precio_mensual) < Number(actual.precio_mensual);
          const veredicto = veredictos[plan.id];

          return (
            <div key={plan.id} className="tarjeta" style={{ marginTop: "12px" }}>
              <h2 style={{ fontSize: "17px" }}>
                {plan.nombre}{" "}
                {esElSuyo && <span className="estado activo">Tu plan</span>}
              </h2>
              <div className="hs">{MONEDA.format(plan.precio_mensual)} al mes</div>

              <dl className="datos">
                {caracteristicas(plan).map((texto) => (
                  <div key={texto} style={{ display: "contents" }}>
                    <dt>•</dt>
                    <dd>{texto}</dd>
                  </div>
                ))}
              </dl>

              {/*
                El boton solo aparece si el servidor dice que el cambio procede.
                Cuando no procede se muestra su motivo, que trae la cifra
                concreta —cuantos usuarios sobran, o que la prueba esta en
                curso—. Ofrecer un boton que se va a rechazar hace trabajar al
                negocio para nada.

                De los planes mas caros no se dice nada aqui: el aviso de arriba
                ya explica que se contratan con INVENTRA, y repetirlo debajo de
                cada uno es ruido.
              */}
              {esAdministrador && !esElSuyo && esMasBarato && (
                veredicto && veredicto.se_puede ? (
                  <div className="acciones">
                    {/*
                      Boton primario: cambiar de plan es LA accion de esta
                      pantalla, y el punto 6.2 del documento fija que cada
                      pantalla tiene una sola accion principal expresada asi.
                      Estaba como secundario, de modo que la unica cosa que se
                      puede hacer aqui era la que menos se veia.
                    */}
                    <button
                      className="btn btn-cta btn-pequeno"
                      type="button"
                      onClick={() => setPorCambiar(plan)}
                    >
                      Cambiar al plan {plan.nombre}
                    </button>
                  </div>
                ) : (
                  veredicto && <div className="hs">{veredicto.motivo}</div>
                )
              )}
            </div>
          );
        })}
      </div>

      {porCambiar && (
        <Modal
          titulo={`Cambiar al plan ${porCambiar.nombre}`}
          mensaje={
            `Tu licorera pasará al plan ${porCambiar.nombre} y conservará la fecha de ` +
            `vencimiento que tiene hoy. Perderás lo que ese plan no incluye: ` +
            `${caracteristicas(porCambiar).join(", ").toLowerCase()}. ` +
            `Si tienes más usuarios o sedes de los que admite, el sistema te lo dirá y no ` +
            `cambiará nada.`
          }
          textoConfirmar={`Cambiar a ${porCambiar.nombre}`}
          ocupado={ocupado}
          onConfirmar={confirmarCambio}
          onCancelar={() => setPorCambiar(null)}
        />
      )}
    </Disposicion>
  );
}
