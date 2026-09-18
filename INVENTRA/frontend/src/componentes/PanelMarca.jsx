/*
  Panel de marca de las pantallas de acceso.

  Es el mismo bloque azul en el acceso, el registro y la recuperacion: cambia el
  titular, la frase y las tres vinetas, y el resto se repite. Por eso es un
  componente con parametros y no codigo copiado tres veces.

  Los textos vienen del prototipo y del manual de marca; no se inventan.
*/

export default function PanelMarca({ titular, frase, vinetas }) {
  return (
    <div className="marca">
      <div className="logo logo-claro">
        <span className="mk" aria-hidden="true"></span> INVENTRA
      </div>

      <div>
        <div className="tg">{titular}</div>
        <div className="sb">{frase}</div>

        <div className="feat">
          {vinetas.map((v) => (
            <div key={v.texto}>
              <b aria-hidden="true">{v.marca}</b>
              {v.texto}
            </div>
          ))}
        </div>
      </div>

      <div className="pie">&copy; 2026 INVENTRA</div>
    </div>
  );
}
