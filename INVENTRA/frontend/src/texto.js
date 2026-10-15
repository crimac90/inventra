/*
  Ayudas de redaccion de la interfaz.

  El manual de marca fija que se escribe el plural y no «(s)». Con el plural
  viene la concordancia: «1 cuentas registradas» hace dudar al lector de que el
  sistema haya contado bien, que es lo contrario de lo que un indicador debe
  transmitir.

  Es el gemelo de `suscripciones/texto.py`, que hace lo mismo para los mensajes
  que salen por consola.
*/

export function plural(cantidad, singular, pluralIrregular) {
  if (cantidad === 1) return `${cantidad} ${singular}`;
  return `${cantidad} ${pluralIrregular || `${singular}s`}`;
}
