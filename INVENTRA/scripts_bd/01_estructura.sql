-- ============================================================
--  INVENTRA — Inventario y ventas para licoreras
--  Estructura de la base de datos (DDL)
-- ============================================================
--  Generado el 2026-10-08 con py manage.py generar_scripts_sql
--  Django 5.2.17 · motor mysql · base «inventra»
-- ============================================================

-- Generado a partir de las migraciones de Django. No se edita a mano:
-- se cambia el modelo, se crea la migración y se vuelve a generar.


-- ----------------------------------------------------------
-- contenttypes.0001_initial
-- ----------------------------------------------------------
--
-- Create model ContentType
--
CREATE TABLE `django_content_type` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `name` varchar(100) NOT NULL, `app_label` varchar(100) NOT NULL, `model` varchar(100) NOT NULL);
--
-- Alter unique_together for contenttype (1 constraint(s))
--
ALTER TABLE `django_content_type` ADD CONSTRAINT `django_content_type_app_label_model_76bd3d3b_uniq` UNIQUE (`app_label`, `model`);


-- ----------------------------------------------------------
-- contenttypes.0002_remove_content_type_name
-- ----------------------------------------------------------
--
-- Change Meta options on contenttype
--
-- (no-op)
--
-- Alter field name on contenttype
--
ALTER TABLE `django_content_type` MODIFY `name` varchar(100) NULL;
--
-- Raw Python operation
--
-- THIS OPERATION CANNOT BE WRITTEN AS SQL
--
-- Remove field name from contenttype
--
ALTER TABLE `django_content_type` DROP COLUMN `name`;


-- ----------------------------------------------------------
-- auth.0001_initial
-- ----------------------------------------------------------
--
-- Create model Permission
--
CREATE TABLE `auth_permission` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `name` varchar(50) NOT NULL, `content_type_id` integer NOT NULL, `codename` varchar(100) NOT NULL);
--
-- Create model Group
--
CREATE TABLE `auth_group` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `name` varchar(80) NOT NULL UNIQUE);
CREATE TABLE `auth_group_permissions` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `group_id` integer NOT NULL, `permission_id` integer NOT NULL);
--
-- Create model User
--
-- (no-op)
ALTER TABLE `auth_permission` ADD CONSTRAINT `auth_permission_content_type_id_codename_01ab375a_uniq` UNIQUE (`content_type_id`, `codename`);
ALTER TABLE `auth_permission` ADD CONSTRAINT `auth_permission_content_type_id_2f476e4b_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`);
ALTER TABLE `auth_group_permissions` ADD CONSTRAINT `auth_group_permissions_group_id_permission_id_0cd325b0_uniq` UNIQUE (`group_id`, `permission_id`);
ALTER TABLE `auth_group_permissions` ADD CONSTRAINT `auth_group_permissions_group_id_b120cbf9_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`);
ALTER TABLE `auth_group_permissions` ADD CONSTRAINT `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`);


-- ----------------------------------------------------------
-- auth.0002_alter_permission_name_max_length
-- ----------------------------------------------------------
--
-- Alter field name on permission
--
ALTER TABLE `auth_permission` MODIFY `name` varchar(255) NOT NULL;

-- auth.0003_alter_user_email_max_length: no produjo sentencias en este proyecto; sus operaciones (AlterField) no llegan a la base

-- auth.0004_alter_user_username_opts: no produjo sentencias en este proyecto; sus operaciones (AlterField) no llegan a la base

-- auth.0005_alter_user_last_login_null: no produjo sentencias en este proyecto; sus operaciones (AlterField) no llegan a la base

-- auth.0006_require_contenttypes_0002: sin operaciones; solo declara un orden de dependencias

-- auth.0007_alter_validators_add_error_messages: no produjo sentencias en este proyecto; sus operaciones (AlterField) no llegan a la base

-- auth.0008_alter_user_username_max_length: no produjo sentencias en este proyecto; sus operaciones (AlterField) no llegan a la base

-- auth.0009_alter_user_last_name_max_length: no produjo sentencias en este proyecto; sus operaciones (AlterField) no llegan a la base


-- ----------------------------------------------------------
-- auth.0010_alter_group_name_max_length
-- ----------------------------------------------------------
--
-- Alter field name on group
--
ALTER TABLE `auth_group` MODIFY `name` varchar(150) NOT NULL;

-- auth.0011_update_proxy_permissions: migración de datos, sin estructura

-- auth.0012_alter_user_first_name_max_length: no produjo sentencias en este proyecto; sus operaciones (AlterField) no llegan a la base


-- ----------------------------------------------------------
-- suscripciones.0001_initial
-- ----------------------------------------------------------
--
-- Create model Licorera
--
CREATE TABLE `licorera` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `nombre` varchar(100) NOT NULL, `nit` varchar(20) NULL UNIQUE, `direccion` varchar(150) NULL, `telefono` varchar(20) NULL, `correo` varchar(100) NOT NULL, `fecha_registro` datetime(6) NOT NULL, `activo` bool NOT NULL);
--
-- Create model Plan
--
CREATE TABLE `plan` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `nombre` varchar(30) NOT NULL UNIQUE, `precio_mensual` numeric(12, 2) NOT NULL, `maximo_sedes` integer UNSIGNED NULL CHECK (`maximo_sedes` >= 0), `maximo_usuarios` integer UNSIGNED NULL CHECK (`maximo_usuarios` >= 0), `permite_facturacion` bool NOT NULL, `permite_reportes_avanzados` bool NOT NULL, `activo` bool NOT NULL);
--
-- Create model Suscripcion
--
CREATE TABLE `suscripcion` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `estado` varchar(12) NOT NULL, `fecha_inicio` date NOT NULL, `fecha_fin` date NULL, `precio_pactado` numeric(12, 2) NOT NULL, `licorera_id` bigint NOT NULL, `plan_id` bigint NOT NULL);
ALTER TABLE `suscripcion` ADD CONSTRAINT `suscripcion_licorera_id_e266ca4f_fk_licorera_id` FOREIGN KEY (`licorera_id`) REFERENCES `licorera` (`id`);
ALTER TABLE `suscripcion` ADD CONSTRAINT `suscripcion_plan_id_1321714a_fk_plan_id` FOREIGN KEY (`plan_id`) REFERENCES `plan` (`id`);

-- suscripciones.0002_datos_planes: migración de datos, sin estructura

-- suscripciones.0003_alter_licorera_direccion_alter_licorera_telefono_and_more: no produjo sentencias en este proyecto; sus operaciones (AlterField) no llegan a la base

-- suscripciones.0004_alter_suscripcion_fecha_fin: no produjo sentencias en este proyecto; sus operaciones (AlterField) no llegan a la base


-- ----------------------------------------------------------
-- seguridad.0001_initial
-- ----------------------------------------------------------
--
-- Create model Rol
--
CREATE TABLE `rol` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `nombre` varchar(30) NOT NULL UNIQUE, `descripcion` varchar(150) NOT NULL);
--
-- Create model Usuario
--
CREATE TABLE `usuario` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `nombre_completo` varchar(100) NOT NULL, `correo` varchar(100) NOT NULL UNIQUE, `telefono` varchar(20) NULL, `contrasena_hash` varchar(255) NOT NULL, `intentos_fallidos` smallint UNSIGNED NOT NULL CHECK (`intentos_fallidos` >= 0), `bloqueado_hasta` datetime(6) NULL, `activo` bool NOT NULL, `fecha_creacion` datetime(6) NOT NULL, `ultimo_acceso` datetime(6) NULL, `licorera_id` bigint NULL, `rol_id` bigint NOT NULL);
ALTER TABLE `usuario` ADD CONSTRAINT `usuario_licorera_id_01ee3245_fk_licorera_id` FOREIGN KEY (`licorera_id`) REFERENCES `licorera` (`id`);
ALTER TABLE `usuario` ADD CONSTRAINT `usuario_rol_id_ac58b608_fk_rol_id` FOREIGN KEY (`rol_id`) REFERENCES `rol` (`id`);


-- ----------------------------------------------------------
-- sedes.0001_initial
-- ----------------------------------------------------------
--
-- Create model Sede
--
CREATE TABLE `sede` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `nombre` varchar(80) NOT NULL, `direccion` varchar(150) NULL, `telefono` varchar(20) NULL, `activo` bool NOT NULL, `licorera_id` bigint NOT NULL);
ALTER TABLE `sede` ADD CONSTRAINT `sede_licorera_id_d41300a4_fk_licorera_id` FOREIGN KEY (`licorera_id`) REFERENCES `licorera` (`id`);


-- ----------------------------------------------------------
-- inventario.0001_initial
-- ----------------------------------------------------------
--
-- Create model Categoria
--
CREATE TABLE `categoria` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `nombre` varchar(50) NOT NULL, `activo` bool NOT NULL, `licorera_id` bigint NOT NULL);
--
-- Create model Producto
--
CREATE TABLE `producto` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `nombre` varchar(120) NOT NULL, `presentacion` varchar(10) NOT NULL, `codigo_barras` varchar(50) NULL, `precio_venta` numeric(12, 2) NOT NULL, `stock_minimo` integer UNSIGNED NOT NULL CHECK (`stock_minimo` >= 0), `activo` bool NOT NULL, `fecha_creacion` datetime(6) NOT NULL, `categoria_id` integer NOT NULL, `licorera_id` bigint NOT NULL);
--
-- Create constraint categoria_unica_por_licorera on model categoria
--
ALTER TABLE `categoria` ADD CONSTRAINT `categoria_unica_por_licorera` UNIQUE (`licorera_id`, `nombre`);
--
-- Create constraint codigo_barras_unico_por_licorera on model producto
--
-- (no-op)
ALTER TABLE `categoria` ADD CONSTRAINT `categoria_licorera_id_59b4122c_fk_licorera_id` FOREIGN KEY (`licorera_id`) REFERENCES `licorera` (`id`);
ALTER TABLE `producto` ADD CONSTRAINT `producto_categoria_id_67131168_fk_categoria_id` FOREIGN KEY (`categoria_id`) REFERENCES `categoria` (`id`);
ALTER TABLE `producto` ADD CONSTRAINT `producto_licorera_id_26bf4b68_fk_licorera_id` FOREIGN KEY (`licorera_id`) REFERENCES `licorera` (`id`);


-- ----------------------------------------------------------
-- inventario.0002_remove_producto_codigo_barras_unico_por_licorera_and_more
-- ----------------------------------------------------------
--
-- Remove constraint codigo_barras_unico_por_licorera from model producto
--
-- (no-op)
--
-- Create constraint codigo_barras_unico_por_licorera on model producto
--
ALTER TABLE `producto` ADD CONSTRAINT `codigo_barras_unico_por_licorera` UNIQUE (`licorera_id`, `codigo_barras`);


-- ----------------------------------------------------------
-- inventario.0003_entradamercancia_loteinventario_movimientoinventario
-- ----------------------------------------------------------
--
-- Create model EntradaMercancia
--
CREATE TABLE `entrada_mercancia` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `proveedor` varchar(100) NULL, `fecha` datetime(6) NOT NULL, `observacion` varchar(255) NULL, `licorera_id` bigint NOT NULL, `sede_id` integer NOT NULL, `usuario_id` bigint NOT NULL);
--
-- Create model LoteInventario
--
CREATE TABLE `lote_inventario` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `origen` varchar(15) NOT NULL, `cantidad_inicial` integer UNSIGNED NOT NULL CHECK (`cantidad_inicial` >= 0), `cantidad_disponible` integer UNSIGNED NOT NULL CHECK (`cantidad_disponible` >= 0), `costo_unitario` numeric(12, 2) NOT NULL, `fecha_ingreso` datetime(6) NOT NULL, `entrada_id` integer NULL, `producto_id` integer NOT NULL, `sede_id` integer NOT NULL);
--
-- Create model MovimientoInventario
--
CREATE TABLE `movimiento_inventario` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `tipo` varchar(16) NOT NULL, `cantidad` integer NOT NULL, `costo_unitario` numeric(12, 2) NULL, `documento_tipo` varchar(10) NOT NULL, `documento_id` bigint NOT NULL, `motivo` varchar(255) NULL, `saldo_resultante` integer UNSIGNED NOT NULL CHECK (`saldo_resultante` >= 0), `fecha` datetime(6) NOT NULL, `licorera_id` bigint NOT NULL, `lote_id` integer NULL, `producto_id` integer NOT NULL, `sede_id` integer NOT NULL, `usuario_id` bigint NOT NULL);
ALTER TABLE `entrada_mercancia` ADD CONSTRAINT `entrada_mercancia_licorera_id_ef31828a_fk_licorera_id` FOREIGN KEY (`licorera_id`) REFERENCES `licorera` (`id`);
ALTER TABLE `entrada_mercancia` ADD CONSTRAINT `entrada_mercancia_sede_id_40200be9_fk_sede_id` FOREIGN KEY (`sede_id`) REFERENCES `sede` (`id`);
ALTER TABLE `entrada_mercancia` ADD CONSTRAINT `entrada_mercancia_usuario_id_223a7e75_fk_usuario_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuario` (`id`);
ALTER TABLE `lote_inventario` ADD CONSTRAINT `lote_inventario_entrada_id_c45cc5ca_fk_entrada_mercancia_id` FOREIGN KEY (`entrada_id`) REFERENCES `entrada_mercancia` (`id`);
ALTER TABLE `lote_inventario` ADD CONSTRAINT `lote_inventario_producto_id_01a8a1c9_fk_producto_id` FOREIGN KEY (`producto_id`) REFERENCES `producto` (`id`);
ALTER TABLE `lote_inventario` ADD CONSTRAINT `lote_inventario_sede_id_6cf74f46_fk_sede_id` FOREIGN KEY (`sede_id`) REFERENCES `sede` (`id`);
ALTER TABLE `movimiento_inventario` ADD CONSTRAINT `movimiento_inventario_licorera_id_0937b387_fk_licorera_id` FOREIGN KEY (`licorera_id`) REFERENCES `licorera` (`id`);
ALTER TABLE `movimiento_inventario` ADD CONSTRAINT `movimiento_inventario_lote_id_d15ba6a0_fk_lote_inventario_id` FOREIGN KEY (`lote_id`) REFERENCES `lote_inventario` (`id`);
ALTER TABLE `movimiento_inventario` ADD CONSTRAINT `movimiento_inventario_producto_id_4b5abd46_fk_producto_id` FOREIGN KEY (`producto_id`) REFERENCES `producto` (`id`);
ALTER TABLE `movimiento_inventario` ADD CONSTRAINT `movimiento_inventario_sede_id_57a6110a_fk_sede_id` FOREIGN KEY (`sede_id`) REFERENCES `sede` (`id`);
ALTER TABLE `movimiento_inventario` ADD CONSTRAINT `movimiento_inventario_usuario_id_d3de09d8_fk_usuario_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuario` (`id`);

-- seguridad.0002_datos_roles: migración de datos, sin estructura


-- ----------------------------------------------------------
-- seguridad.0003_usuario_correo_verificado_alter_rol_nombre_and_more
-- ----------------------------------------------------------
--
-- Add field correo_verificado to usuario
--
ALTER TABLE `usuario` ADD COLUMN `correo_verificado` bool DEFAULT b'0' NOT NULL;
ALTER TABLE `usuario` ALTER COLUMN `correo_verificado` DROP DEFAULT;
--
-- Alter field nombre on rol
--
-- (no-op)
--
-- Alter field fecha_creacion on usuario
--
-- (no-op)
--
-- Alter field last_login on usuario
--
-- (no-op)
--
-- Alter field nombre_completo on usuario
--
-- (no-op)
--
-- Alter field password on usuario
--
-- (no-op)
--
-- Alter field telefono on usuario
--
-- (no-op)


-- ----------------------------------------------------------
-- token_blacklist.0001_initial
-- ----------------------------------------------------------
--
-- Create model BlacklistedToken
--
CREATE TABLE `token_blacklist_blacklistedtoken` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `blacklisted_at` datetime(6) NOT NULL);
--
-- Create model OutstandingToken
--
CREATE TABLE `token_blacklist_outstandingtoken` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `jti` char(32) NOT NULL UNIQUE, `token` longtext NOT NULL, `created_at` datetime(6) NOT NULL, `expires_at` datetime(6) NOT NULL, `user_id` bigint NOT NULL);
--
-- Add field token to blacklistedtoken
--
ALTER TABLE `token_blacklist_blacklistedtoken` ADD COLUMN `token_id` integer NOT NULL UNIQUE , ADD CONSTRAINT `token_blacklist_blac_token_id_3cc7fe56_fk_token_bla` FOREIGN KEY (`token_id`) REFERENCES `token_blacklist_outstandingtoken`(`id`);
ALTER TABLE `token_blacklist_outstandingtoken` ADD CONSTRAINT `token_blacklist_outstandingtoken_user_id_83bc629a_fk_usuario_id` FOREIGN KEY (`user_id`) REFERENCES `usuario` (`id`);


-- ----------------------------------------------------------
-- token_blacklist.0002_outstandingtoken_jti_hex
-- ----------------------------------------------------------
--
-- Add field jti_hex to outstandingtoken
--
ALTER TABLE `token_blacklist_outstandingtoken` ADD COLUMN `jti_hex` varchar(255) NULL;

-- token_blacklist.0003_auto_20171017_2007: migración de datos, sin estructura


-- ----------------------------------------------------------
-- token_blacklist.0004_auto_20171017_2013
-- ----------------------------------------------------------
--
-- Alter field jti_hex on outstandingtoken
--
ALTER TABLE `token_blacklist_outstandingtoken` MODIFY `jti_hex` varchar(255) NOT NULL;
ALTER TABLE `token_blacklist_outstandingtoken` ADD CONSTRAINT `token_blacklist_outstandingtoken_jti_hex_d9bdf6f7_uniq` UNIQUE (`jti_hex`);


-- ----------------------------------------------------------
-- token_blacklist.0005_remove_outstandingtoken_jti
-- ----------------------------------------------------------
--
-- Remove field jti from outstandingtoken
--
ALTER TABLE `token_blacklist_outstandingtoken` DROP COLUMN `jti`;


-- ----------------------------------------------------------
-- token_blacklist.0006_auto_20171017_2113
-- ----------------------------------------------------------
--
-- Rename field jti_hex on outstandingtoken to jti
--
ALTER TABLE `token_blacklist_outstandingtoken` RENAME COLUMN `jti_hex` TO `jti`;


-- ----------------------------------------------------------
-- token_blacklist.0007_auto_20171017_2214
-- ----------------------------------------------------------
--
-- Alter field created_at on outstandingtoken
--
ALTER TABLE `token_blacklist_outstandingtoken` MODIFY `created_at` datetime(6) NULL;
--
-- Alter field user on outstandingtoken
--
ALTER TABLE `token_blacklist_outstandingtoken` DROP FOREIGN KEY `token_blacklist_outstandingtoken_user_id_83bc629a_fk_usuario_id`;
ALTER TABLE `token_blacklist_outstandingtoken` MODIFY `user_id` bigint NULL;
ALTER TABLE `token_blacklist_outstandingtoken` ADD CONSTRAINT `token_blacklist_outstandingtoken_user_id_83bc629a_fk_usuario_id` FOREIGN KEY (`user_id`) REFERENCES `usuario` (`id`);


-- ----------------------------------------------------------
-- token_blacklist.0008_migrate_to_bigautofield
-- ----------------------------------------------------------
--
-- Alter field id on blacklistedtoken
--
ALTER TABLE `token_blacklist_blacklistedtoken` MODIFY `id` bigint AUTO_INCREMENT NOT NULL;
--
-- Alter field id on outstandingtoken
--
ALTER TABLE `token_blacklist_blacklistedtoken` DROP FOREIGN KEY `token_blacklist_blacklistedtoken_token_id_3cc7fe56_fk`;
ALTER TABLE `token_blacklist_outstandingtoken` MODIFY `id` bigint AUTO_INCREMENT NOT NULL;
ALTER TABLE `token_blacklist_blacklistedtoken` MODIFY `token_id` bigint NOT NULL;
ALTER TABLE `token_blacklist_blacklistedtoken` ADD CONSTRAINT `token_blacklist_blacklistedtoken_token_id_3cc7fe56_fk` FOREIGN KEY (`token_id`) REFERENCES `token_blacklist_outstandingtoken` (`id`);

-- token_blacklist.0010_fix_migrate_to_bigautofield: no produjo sentencias en este proyecto; sus operaciones (AlterField) no llegan a la base

-- token_blacklist.0011_linearizes_history: sin operaciones; solo declara un orden de dependencias

-- token_blacklist.0012_alter_outstandingtoken_user: no produjo sentencias en este proyecto; sus operaciones (AlterField) no llegan a la base

-- token_blacklist.0013_alter_blacklistedtoken_options_and_more: no produjo sentencias en este proyecto; sus operaciones (AlterModelOptions) no llegan a la base

