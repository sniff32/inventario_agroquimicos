# Sistema de inventario · Tienda de agroquímicos

Aplicación Django de gestión de una tienda o almacén agrícola independiente de la distribuidora de abarrotes original.

## Funciones conservadas

- Inicio de sesión, usuarios y roles (administrador, empleado e invitado).
- Inventario de productos, categorías, ubicaciones, movimientos y alertas de existencias.
- Compras y recepción de mercancía con costo.
- Ventas, órdenes y documentos Word.
- Finanzas: operaciones de contado/crédito, cuentas por pagar/cobrar y abonos.
- Importación/exportación mediante Excel.

## Demostración

El administrador puede cargar **50 productos agrícolas ficticios**, incluyendo fertilizantes, micronutrientes, bioestimulantes, herbicidas, insecticidas, fungicidas, semillas, sustratos y accesorios. Sus marcas, precios y existencias son **inventados para demostración**; no representan productos regulados específicos ni información de seguridad técnica.

Identificador de almacén: `AGRO-ALMACEN`. Códigos de prueba: `AGR-001` a `AGR-050`.

Esta etapa **no implementa trazabilidad reglamentaria de lotes, fichas de seguridad ni autorización sanitaria**. Esas funciones deben diseñarse y verificarse antes de utilizarlo como sistema de control de agroquímicos reales.

## Render / Neon

Crear una **base de datos PostgreSQL completamente independiente** de la que utiliza la abarrotera y configurar las variables de entorno exclusivamente en el nuevo servicio.

| Variable | Función |
| --- | --- |
| `DATABASE_URL` | Nueva URL PostgreSQL propia; jamás reutilizar la base de la abarrotera |
| `SECRET_KEY` | Secreto aleatorio distinto del servicio original |
| `DEBUG` | `false` |
| `ALLOWED_HOSTS` | Dominio personalizado, si aplica |

Servicio web Python:
- Build: `bash build.sh`
- Start: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
- Health check: `/salud/`

Para el primer administrador, añadir temporalmente `BOOTSTRAP_ADMIN=true` y `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`, hacer deploy y luego **eliminar las cuatro variables temporales**.

No subir al repositorio archivos `.env`, claves, contraseñas, bases de datos, certificados o URLs con credenciales.

## Alcance financiero

La sección de finanzas es un control operativo: no sustituye facturación CFDI, libros contables, cálculo de impuestos ni conciliación bancaria.

## Identidad gráfica

Paleta verde agrícola neutra, sin logotipo ni marca del cliente original. Se puede personalizar posteriormente.
