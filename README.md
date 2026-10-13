# FERMO · Distribuidora de abarrotes (versión actual)

**Actividad:** distribuidora que abastece a tiendas de abarrotes. **Un almacén
central** para recibir, almacenar y vender mercancía.

**Módulos actuales:** inventario, ubicaciones del almacén, movimientos, historial,
ventas por mayoreo y menudeo (también en una sola orden), cuentas de proveedores,
recepción de compras y su costo, crédito/contado, cuentas por pagar, cuentas por
cobrar y registros de pagos.

**Cambio de datos de demostración:** `core/migrations/0008_convert_legacy_demo.py`
desactiva solamente productos previos `is_demo=True` con códigos `DEMO-`
y tiendas `is_demo=True`, cuando la base ya contiene esa demostración y existe
un administrador. Crea 50 productos de abarrotes `ABR-001` a `ABR-050` en
`FERMO-ALMACEN` con precios, costos y cantidades **ficticios**. Es idempotente,
no borra movimientos, folios, usuarios, ventas o productos reales. En una
instalación nueva sin esas muestras, el administrador puede inicializar el
catálogo desde el panel general.

**Almacén único:** ya no se crean sucursales desde el panel, y la importación
Excel solo acepta el almacén FERMO cuando ya existe. Puede haber varias
**ubicaciones internas** (estantes, repisas, pasillos). Las sucursales antiguas
persisten solo por integridad histórica.

**Finanzas, reglas importantes:**
- El administrador crea proveedores y clientes. Cada recepción registra un
  solo artículo con unidades, proveedor, costo unitario y contado/crédito; la
  recepción incrementa stock en una transacción y actualiza el costo vigente.
  Se registra una referencia `COMPRA-<id>` en movimientos.
- Compra **contado**: pago completo registrado junto con la entrada.
  Compra **crédito**: se crea cuenta por pagar con vencimiento; abonos parciales
  y liquidaciones verifican el saldo restante y registran usuario/fecha.
- Venta **contado**: su total queda cobrado al confirmar.
  Venta **crédito**: solo el administrador puede autorizarla, debe indicar
  vencimiento y se crea cuenta por cobrar asociada al cliente y folio; se
  registran cobros parciales posteriormente.
- Ventas realizadas **antes** de esta versión tienen el estado
  `SIN_CLASIFICAR`; no se presume ni deuda ni cobro, por integridad financiera.
- Las cuentas son operativas en MXN. **No son facturas, CFDI, contabilidad
  fiscal, conciliación bancaria ni estado de resultados.** No se calcula IVA,
  devoluciones, impuestos o gastos administrativos en esta fase.
- Solo cuentas administradoras acceden al panel Financiero y a abonos.
  Empleados registran ventas de contado y movimientos de inventario,
  pero no autorizan créditos ni ven saldos de proveedores.
- El formulario **Editar producto** usa un `dialog` centrado con scroll propio,
  evitando alterar el ancho de la tabla o salir de la pantalla.

---

# Inventario empresarial

Plataforma web para administración de productos, existencias, almacenes y sucursales.

## Estado actual

**Fase 1: estructura inicial del servidor.** Ya está preparado Django con:
- Autenticación por usuario y contraseña en `/cuentas/ingresar/`.
- Panel privado en `/` (requiere iniciar sesión).
- Administración nativa de Django en `/admin/` (solo personal autorizado).
- Endpoint sencillo de salud en `/salud/`.
- Configuración de PostgreSQL mediante variables de entorno.
- Archivos estáticos servidos mediante WhiteNoise.
- Preparación para despliegue en Render.

Aún **no** hay catálogo de productos, sucursales ni movimientos: se agregarán por fases.

## Arquitectura

- **Código:** GitHub (repositorio privado).
- **Web:** Render, Python 3.13, Django 5.2 LTS y Gunicorn.
- **Base de datos:** Neon PostgreSQL, enlazado a Render mediante DATABASE_URL.

## Variables que deben configurarse en Render

| Variable | Propósito |
| --- | --- |
| `SECRET_KEY` | Clave secreta aleatoria de Django. Nunca publicar. |
| `DATABASE_URL` | URL de conexión privada de PostgreSQL, con SSL. Nunca publicar. |
| `DEBUG` | `false` para producción. |
| `ALLOWED_HOSTS` | Dominios personalizados separados por coma (opcional; Render agrega el suyo). |
| `CSRF_TRUSTED_ORIGINS` | Orígenes HTTPS personalizados si se agregan (opcional). |

**Nunca colocar contraseñas, tokens o la URL con credenciales en GitHub.**

## Configuración futura del Web Service en Render

- Runtime: **Python**
- Build Command: `bash build.sh`
- Start Command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
- Health Check Path: `/salud/`

El endpoint `/salud/` verifica que la aplicación responda; no hace una consulta a PostgreSQL. Las migraciones de Django se ejecutan desde `build.sh` en cada despliegue.

## Crear el primer administrador (Render Free, sin Shell)

El proyecto incluye un comando `bootstrap_admin` para crear **solo el primer superusuario** después de ejecutar las migraciones. No modifica una cuenta administradora ya creada.

En **Render → Environment → Edit** añade TEMPORALMENTE:

| Variable | Valor |
| --- | --- |
| `BOOTSTRAP_ADMIN` | `true` |
| `DJANGO_SUPERUSER_USERNAME` | Nombre del primer administrador, por ejemplo `administrador`. |
| `DJANGO_SUPERUSER_EMAIL` | Correo del responsable. |
| `DJANGO_SUPERUSER_PASSWORD` | Contraseña única y robusta; solo en Render, nunca en GitHub. |

Asegúrate de que el servicio utilice **Build Command: `bash build.sh`**. Después realiza un **Deploy latest commit**.

En el registro del *build* debe aparecer `Primer administrador creado correctamente.` Si ya existe un administrador, no se modifica.

Accede a `/cuentas/ingresar/` con ese usuario y contraseña. Como superusuario también podrás usar `/admin/`.

**Inmediatamente después de verificar que la cuenta existe**, elimina en Render las cuatro variables temporales y guarda los cambios. No elimines `DATABASE_URL`, `SECRET_KEY` ni `DEBUG`. Cualquier redeploy posterior conserva el usuario en Neon y ya no requiere estas variables.

Las cuentas futuras se crearán con permisos específicos, no mediante este mecanismo excepcional.

## Próximas fases

1. Confirmar PostgreSQL y el despliegue inicial.
2. Crear el primer administrador; después usuarios, roles y permisos por sucursal.
3. Agregar productos, ubicaciones y existencias.
4. Registrar entradas, ventas, salidas, transferencias y auditoría.
5. Reportes, importaciones, alertas y control físico.

No modificar otros repositorios ni proyectos de la cuenta.


## Administración de usuarios en el mismo sitio

El administrador utiliza el **menú lateral → Usuarios y accesos** (ruta interna `/?seccion=administracion`). No necesita abrir el administrador técnico de Django.

- Alta de cuentas con usuario, nombre, correo, rol y contraseña.
- Roles iniciales: Administrador, Empleado e Invitado. Los permisos por sucursal y movimiento se definirán al implementar esos módulos.
- Cambio de contraseña de cuentas, reasignación de rol y activación o suspensión.
- El acceso a la sección y las acciones se verifica en el servidor mediante `is_superuser`, `POST` y protección CSRF.
- No se permite quitar el rol o desactivar el administrador autenticado.
- Los usuarios no se eliminan físicamente, para preservar su futura trazabilidad.
- El `/admin/` de Django se conserva únicamente como herramienta técnica de respaldo; no figura en la navegación principal.

Para crear usuarios nuevos, **no** necesitas agregar variables al entorno ni editar Neon manualmente: hazlo desde el panel.



## Inventario funcional (segunda etapa)

Los menús de la web principal ahora incluyen:

- **Panel general:** totales reales de productos, unidades, sucursales y movimientos, con actividad reciente.
- **Productos:** búsqueda, filtro por sucursal, alta y edición de productos y categorías; los cambios de existencias solo se hacen mediante movimientos.
- **Sucursales:** nuevas tiendas, bodegas y ubicaciones (estante / repisa), además de inventario por sucursal.
- **Movimientos:** entrada, salida, ajuste a cantidad final y traslado directo entre ubicaciones; todas las operaciones guardan usuario, fecha/hora, stock anterior y posterior.
- **Historial:** filtros por periodo, usuario, tipo de movimiento, sucursal y producto (máximo 250 por consulta).
- **Excel:** plantilla descargable y carga de archivos XLSX hasta 500 filas y 2 MB; la columna `cantidad` establece la existencia **final** por producto+ubicación, no agrega una compra. Las diferencias quedan auditadas.
- **Demostración:** botón visible al administrador para cargar voluntariamente 20 productos con prefijo `DEMO-` en 5 ubicaciones ficticias. Es una carga repetible (no duplica los movimientos originales). Estos registros son **datos de prueba** y comparten base de datos con los registros nuevos; no deben considerarse mercancía real.
- **Roles:** administrador crea y edita productos/ubicaciones/importaciones y usuarios; empleado registra entradas, salidas, ajustes y traslados; invitado solamente consulta. No borrar registros para conservar trazabilidad.

Las migraciones están versionadas en `core/migrations/0001_initial.py`. Un nuevo despliegue con `bash build.sh` crea las tablas sin eliminar las cuentas existentes.

### Plantilla de Excel

Columnas: `codigo,nombre,categoria,marca,unidad,precio,costo,sucursal,ubicacion,cantidad,minimo`.
Obligatorias: `codigo,nombre,sucursal,cantidad`. `ubicacion` es opcional y, si se omite, se utiliza `General`.
El código debe guardarse como texto si contiene ceros iniciales. En importaciones de productos ya existentes no se reemplaza automáticamente su nombre, marca o precio: solo se sincroniza la existencia de las ubicaciones incluidas en el archivo.
No se borran sucursales ni inventarios de otras ubicaciones omitidas del documento.

### Pendientes posteriores

- Permisos granulares por sucursal / empleado y protección de precios de costo.
- Proceso completo de traslado en tránsito y confirmación de recepción.
- Confirmación de inventario físico, lotes / seriales, proveedores y ventas comerciales.
- Reportes/exportaciones, paginación extensa y controles de respaldo/recuperación para producción.


## Identidad FERMO y ventas (fase de pruebas)

Razón social mostrada: **Fermo Comercializadora y Distribuidora S.A. de C.V.**.
Se incorporó una versión vectorizada del logotipo aportado por la empresa,
en `static/img/fermo-logo.svg`; aparece en login, sidebar y órdenes Word.

### Política de precios
- **Menudeo:** campo `price` existente del producto.
- **Mayoreo:** `wholesale_price` opcional y `wholesale_min_qty` (10 inicialmente), modificables en `Productos → Editar`.
- Una orden mayorista valida **cada renglón por separado**; si la cantidad de un producto no alcanza su umbral o no tiene precio mayoreo, no se confirma.
- No inventar descuentos, impuestos, IVA ni CFDI; el total de la orden es el subtotal de los productos. Definir política fiscal con la empresa antes de usarlo como documento contable.

### Flujo de ventas
1. Acceder a `Ventas y órdenes` como administrador o empleado.
2. Elegir menudeo/mayoreo, producto, sucursal, repisa y cantidad; agregar varios renglones al carrito.
3. No se permite mezclar sucursales ni modalidades dentro del mismo carrito.
4. Indicar cliente o razón social, contacto, fecha de salida y observaciones.
5. Al confirmar, se valida de nuevo la disponibilidad y los precios bajo transacción PostgreSQL.
6. Se guarda un folio `FER-VENTA-000001` y sus renglones con el precio congelado, se descuentan las existencias y cada salida aparece en Historial con referencia a la venta.
7. Descargar documento Word `.docx` con logotipo, cliente, folio, fecha, tabla de cantidades, precios y subtotal.

El carrito se guarda temporalmente en la sesión Django (persistida en PostgreSQL), **no reserva stock**. Otro usuario puede vender los últimos artículos antes de confirmar; en ese caso se rechaza toda la operación sin descontar parcialmente.

Por ahora la venta **descuenta existencias inmediatamente al confirmarse**, incluso si la fecha de entrega introducida es posterior. La fecha de salida es informativa; el proceso de apartados y entregas pendientes será un desarrollo posterior.

Las órdenes confirmadas son registros históricos; **todavía no se pueden cancelar, modificar o facturar** desde esta versión. Se añadirá un proceso de cancelación con reintegro auditable y autorizaciones antes de operar comercialmente con ventas reales.

Los invitados no tienen acceso al carrito, datos de clientes ni descargas de órdenes.


## Rediseño FERMO y mayoreo escalonado de prueba

La interfaz utiliza una paleta corporativa rojo carmín / grafito / marfil, con acceso
visualmente unificado en el login, menú, panel, carrito y orden Word. El panel
incluye accesos rápidos a las tareas principales.

### Buscador interactivo de ventas
- `GET /ventas/buscar/?q=...`: busca en PostgreSQL por SKU, nombre, marca o categoría
  y devuelve hasta 35 ubicaciones con existencias (solo usuarios autorizados).
- `GET /ventas/producto/<balance_id>/`: presenta existencias de la ubicación,
  menudeo, precio mayorista, cantidad mínima y existencias por cada sucursal;
  el frontend muestra cantidad restante y advierte si el stock quedará bajo.
- La interfaz impide añadir productos cuando supera el stock conocido; el servidor
  **vuelve a validar y bloquear existencias al confirmar**.
- La búsqueda usa JavaScript y no supone que el catálogo tiene menos de 400 registros.

### Regla temporal de mayoreo (solo para pruebas)
- El precio **mayorista base** continúa definido por cada producto.
- Se descuenta **2% adicional por cada diez unidades del mismo SKU**, máximo 10%.
- Descuentos: 0–9 (0%), 10–19 (2%), 20–29 (4%), 30–39 (6%), 40–49 (8%),
  50 o más (10%). Solo se puede registrar mayoreo si se cumple además el
  mínimo configurado para ese producto.
- Si el SKU ocupa varias repisas de la misma orden, las unidades se **suman**
  para determinar el escalón. Se comprueba stock por repisa.
- La liquidación redondea el **precio unitario descontado a dos decimales**,
  y entonces multiplica por cantidad. El descuento de línea es la diferencia
  entre el importe bruto y el importe final de esa línea.
- Precio base, porcentaje, ahorro e importe neto quedan congelados en cada
  `SaleItem`; `Sale` guarda bruto, ahorro total y total final.
- La migración `0004` conserva ventas anteriores asignándoles descuentos cero y
  precio base = precio unitario guardado.
- La migración `0005` asigna **solo a productos marcados DEMO** sin precio de
  mayoreo un precio ficticio 8% inferior al menudeo, con mínimo 10. **No toca
  precios mayoristas de productos reales ni precios ya configurados**.
- Los descuentos indicados son una **política de prueba**, no una autorización
  comercial ni una política de precios confirmada por FERMO.

### Documento Word
Se utiliza rojo FERMO en separador, encabezado de tabla y total final; incluye
producto, ubicación, precio bruto unitario, porcentaje de descuento, precio
unitario efectivo, importe, subtotales, descuentos, cliente y folio.

**Nota:** el carrito no aparta unidades y no se calcula IVA ni factura/CFDI.
No utilizar los importes como documentos fiscales sin aprobación contable.


## Ventas mixtas y ficha rápida (actualización)

- Una misma orden/FOLIO puede contener **menudeo y mayoreo**, escogidos por **renglón**.
- No se mezclan sucursales en una misma orden. Los renglones tienen el mismo
  cliente, fecha de salida y vendedor.
- Para distinguir artículos idénticos vendidos en ambas modalidades se crean
  líneas separadas y se muestra la modalidad tanto en el carrito como en Word.
- El descuento escalonado solo suma las cantidades del **mismo SKU bajo
  modalidad mayorista**, incluso cuando sale de varias repisas; piezas
  minoristas del mismo SKU **no aumentan el descuento mayorista**.
- La disponibilidad se valida con la **suma de todos los renglones del mismo
  producto y la misma ubicación**, sin importar la modalidad, antes de generar
  el folio y en una única transacción al confirmar la venta.
- Si se agrega un renglón mayorista que todavía no alcanza el mínimo, puede
  permanecer en el carrito para completarlo desde otra repisa de la sucursal,
  pero la venta no podrá confirmarse hasta cumplir el mínimo.
- El sistema identifica la orden global como `Mixta`, `Menudeo` o `Mayoreo`.
  La migración `0006` agrega modalidad a cada `SaleItem` y asigna
  automáticamente la modalidad previa a las órdenes existentes.
- La ficha de selección muestra cuatro datos esenciales (ubicación, stock,
  precio y total), con detalles de precios y stock de otras sucursales
  **desplegables**, para agilizar el uso diario.
