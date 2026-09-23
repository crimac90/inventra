# INVENTRA

Aplicación web para la gestión de inventarios y ventas en licoreras de Medellín.

INVENTRA es una solución de software, en modalidad SaaS, dirigida a licoreras y pequeños comercios del sector. Permite administrar el inventario por lotes con valoración PEPS, registrar ventas en un punto de venta, controlar múltiples sedes y usuarios, generar reportes y emitir facturación electrónica.

Este repositorio reúne la documentación y el código fuente del proyecto, desarrollado como trabajo de grado del programa Análisis y Desarrollo de Software del SENA.

## Estado del proyecto

Fase de construcción. El análisis y el diseño están terminados y el desarrollo avanza por módulos; el primero, seguridad y acceso, ya está construido y probado. Las instrucciones para levantar el sistema en un equipo local están en `DESPLIEGUE_LOCAL.md`. El despliegue en servidor se documentará al cierre de la construcción.

## Tecnologías

- Backend: Python, Django y Django REST Framework (API REST).
- Base de datos: MySQL.
- Frontend: React (Node.js) con Vite.

## Estructura del repositorio

Los archivos se nombran sin espacios, con las palabras separadas por guiones bajos.

- `docs/analisis`: requisitos (IEEE 830), historias de usuario, product backlog, y mapa de empatía con lean canvas.
- `docs/diseno`: análisis y diseño en UML, diseño de la base de datos (MER, modelo relacional y diccionario de datos) y documento técnico de diseño de la interfaz.
- `docs/proyecto-de-grado`: documento del proyecto de grado (norma ICONTEC).
- `docs/gestion`: hoja de ruta del proyecto, guía del tablero SCRUM y propuesta técnica y económica.
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
