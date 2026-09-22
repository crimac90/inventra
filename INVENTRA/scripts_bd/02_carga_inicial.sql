-- ============================================================
--  INVENTRA — Inventario y ventas para licoreras
--  Carga inicial de datos
-- ============================================================
--  Generado el 2026-09-21 con py manage.py generar_scripts_sql
--  Django 5.2.17 · motor mysql · base «inventra»
-- ============================================================

-- Los roles y los planes no son datos de ejemplo: sin ellos el sistema no
-- funciona, porque no se puede registrar a nadie. Por eso viajan con la
-- estructura. Las cuentas de prueba NO están aquí: se cargan aparte, con
-- el comando cargar_datos_demo, para no crearlas nunca sin querer.


-- Roles del sistema
INSERT INTO rol (id, nombre, descripcion) VALUES (1, 'administrador_licorera', 'Dueño o encargado de la licorera; gestiona productos, inventario, usuarios, reportes y configuración.');
INSERT INTO rol (id, nombre, descripcion) VALUES (2, 'vendedor', 'Registra las ventas y consulta existencias.');
INSERT INTO rol (id, nombre, descripcion) VALUES (3, 'administrador_inventra', 'Administra la plataforma: licoreras, planes y estado de las suscripciones.');

-- Planes de suscripción
INSERT INTO plan (id, nombre, precio_mensual, maximo_sedes, maximo_usuarios, permite_facturacion, permite_reportes_avanzados, activo) VALUES (1, 'Básico', 59900.00, 1, 1, 0, 0, 1);
INSERT INTO plan (id, nombre, precio_mensual, maximo_sedes, maximo_usuarios, permite_facturacion, permite_reportes_avanzados, activo) VALUES (2, 'Pro', 109900.00, NULL, NULL, 1, 1, 1);
