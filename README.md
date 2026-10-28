# INVENTRA

Aplicación web para la gestión de inventarios y ventas en licoreras de Medellín.

INVENTRA es una solución de software, en modalidad SaaS, dirigida a licoreras y pequeños comercios del sector. Permite administrar el inventario por lotes con valoración PEPS, registrar ventas en un punto de venta, controlar múltiples sedes y usuarios, generar reportes y emitir facturación electrónica.

Este repositorio reúne la documentación y el código fuente del proyecto, desarrollado como trabajo de grado del programa Análisis y Desarrollo de Software del SENA.

## El sistema en funcionamiento

**https://appinventra.pythonanywhere.com**

Cuentas de prueba, todas con la contraseña `Inventra2026`:

| Rol | Correo |
|---|---|
| Administrador de licorera | `admin@demo.inventra.co` |
| Vendedor | `vendedor@demo.inventra.co` |
| Administrador de otra licorera | `vecino@demo.inventra.co` |
| Administrador de INVENTRA | `plataforma@demo.inventra.co` |

Las dos primeras cuentas trabajan sobre la misma licorera, con el catálogo surtido y ocho jornadas de ventas; la tercera existe para comprobar que un negocio no ve los datos de otro.

## Estado del proyecto

Construcción avanzada. El análisis y el diseño están terminados, y de los ocho módulos especificados están construidos y probados los cuatro que sostienen la operación diaria: seguridad y acceso (SEG), suscripciones (SUS), inventario con valoración PEPS (INV) y ventas con cierre de caja (VEN). Los módulos de reportes, multisede, facturación electrónica y auditoría quedan especificados, diseñados y modelados, y su construcción continúa después de la entrega.

## Puesta en marcha

Para levantar el sistema en un equipo local —instalación de MySQL, entorno virtual, variables de entorno, carga de datos y puesta en marcha del backend y del frontend— están las instrucciones completas en `DESPLIEGUE_LOCAL.md`.

### Despliegue en servidor

El sistema se publica en un alojamiento con Python y MySQL. El servidor entrega la API y la interfaz desde la misma dirección, de modo que no hay dos dominios que coordinar ni peticiones entre orígenes.

1. **Base de datos.** Crear una base MySQL 8 y anotar su nombre, su servidor y sus credenciales.
2. **Código.** Clonar el repositorio, crear un entorno virtual con Python 3.11 o posterior e instalar `INVENTRA/backend/requirements.txt`.
3. **Variables de entorno.** Crear `INVENTRA/backend/.env` a partir de `.env.example`, con la clave secreta generada para esa instalación, `DJANGO_DEBUG=False`, el dominio en `DJANGO_ALLOWED_HOSTS`, los datos de la base y el correo saliente. `CORS_ORIGENES` queda vacío: la interfaz se sirve desde el mismo dominio.
4. **Base y datos iniciales.** `python manage.py migrate` crea la estructura. Para una instalación de demostración, `python manage.py cargar_datos_demo --si-estoy-seguro` siembra las licoreras de prueba; la orden exige esa confirmación cuando el modo de depuración está apagado, porque crea cuentas con contraseñas publicadas.
5. **Interfaz.** Compilar con `npm run build` en `INVENTRA/frontend`. La compilación cuelga de `/static/`, de modo que los archivos entran al mismo almacén que los de Django. Si el alojamiento no tiene Node —es el caso de los alojamientos centrados en Python— se compila en el equipo de desarrollo y se publica el contenido de `frontend/dist`.
6. **Archivos estáticos.** `python manage.py collectstatic` los reúne en `backend/staticfiles`, que es la única carpeta que el servidor web necesita servir, bajo la dirección `/static/`.
7. **Aplicación.** Configurar el servidor WSGI apuntando a `config.wsgi`, con la carpeta del backend en la ruta de búsqueda y la variable `DJANGO_SETTINGS_MODULE` en `config.settings`.
8. **HTTPS.** Activarlo en el alojamiento. Las protecciones que dependen de él —redirección, HSTS y galletas seguras— se activan solas cuando el modo de depuración está apagado.

La comprobación final es `/api/estado/`, que responde sin autenticación y confirma que la API está en línea.

## Flujo de trabajo del repositorio

El desarrollo se registra en este repositorio desde el 7 de septiembre de 2026 y cubre un lapso mínimo de ocho semanas de trabajo continuo, con commits en la mayoría de los días hábiles. Cada bloque de construcción se desarrolla en una rama propia, nombrada por el módulo y el trabajo que contiene —`modulo-seg-autenticacion`, `modulo-sus-bloque-0`, `doc-diseno-pantallas`—, y se integra en `main` al terminarlo. Los mensajes de commit describen en una línea qué resuelve el cambio, y el cuerpo, cuando lo lleva, explica por qué.

## Tecnologías

- Backend: Python, Django y Django REST Framework (API REST).
- Base de datos: MySQL.
- Frontend: React (Node.js) con Vite.

## Estructura del repositorio

Los archivos se nombran sin espacios, con las palabras separadas por guiones bajos.

- `docs/analisis`: requisitos (IEEE 830), historias de usuario, product backlog, y mapa de empatía con lean canvas.
- `docs/diseno`: análisis y diseño en UML, diseño de la base de datos (MER, modelo relacional y diccionario de datos) y documento técnico de diseño de la interfaz.
- `docs/proyecto-de-grado`: documento del proyecto de grado (norma ICONTEC).
- `docs/gestion`: propuesta técnica y económica del proyecto.
- `docs/manuales`: manuales dirigidos al usuario final.
- `INVENTRA`: código fuente del sistema (`backend`, `frontend`) y scripts de creación de la base de datos (`scripts_bd`).
- `DESPLIEGUE_LOCAL.md`: instalación y puesta en marcha del sistema en un equipo local.
- `Diagramas`: diagramas en formato editable (SVG) y de imagen (PNG).
- `prototipo`: prototipo de la interfaz (HTML).
- `negocio`: modelo de negocio (formato Fondo Emprender).

## Autor

Cristian Darío Macías Espitia.
Análisis y Desarrollo de Software — SENA, Centro de Formación en Diseño, Confección y Moda. Medellín, 2026.

## Derechos de autor

© 2026 Cristian Darío Macías Espitia. Todos los derechos reservados. El contenido de este repositorio es material académico del trabajo de grado; su uso o reproducción requiere autorización del autor. Las normas, marcas y formatos de terceros citados pertenecen a sus respectivos propietarios.
