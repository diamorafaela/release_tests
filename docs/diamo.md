# Pruebas de release de Diamo

Las suites de Diamo se desarrollan en `diamoerp-develop`. Release Manager usa el proyecto original de Frappe.

## Catálogo disponible

| Suite | Requisitos | Comprobaciones |
| --- | --- | --- |
| `diamo_argentina_payments` | ERPNext, Base y Argentina | Factura de 100 ARS, cobro inicialmente en cero, forma de pago, mayor contable, saldo y anulación. |
| `diamo_service_credits` | Fork Diamo de ERPNext y Base | Créditos de 40 y 60 sobre un servicio de 100, incluso con cantidad devuelta. Rechazo del exceso. |
| `diamo_hrms_payments` | ERPNext, Base, Argentina y HRMS | Repite el circuito de cobro con HRMS instalado para detectar conflictos de controladores. |
| `diamo_argentina_buying` | ERPNext, Base y Argentina | Compra de 100,01 ARS, pagos de 40,01 y 60, mayor contable y anulación de ambos pagos. |
| `diamo_base_access` | Base, ERPNext y permisos de System Manager para el ejecutor | Token y Basic, bloqueo de login API, revocación de claves y permisos del usuario reducido. |
| `diamo_combined_receipts` | ERPNext, Base y Argentina | Cobro de 100: banco 60,01 y caja 39,99. Cuentas separadas, saldo y anulación. |
| `diamo_perceptions` | Argentina y maestros fiscales locales | Percepción IVA del 3%, guardado sin duplicados, recálculo por cantidad y exclusión bajo mínimo. Solo borradores. |
| `diamo_withholdings` | Argentina y maestros fiscales locales | Compra de apertura de 1000,25. IIBB 25,01, pago neto 975,24, mínimo, certificado, mayor y anulación. |

Las suites contables tienen cinco pasos, excepto retenciones, que tiene siete. Base tiene dos pasos con identidades aisladas.
Las suites crean comprobantes nuevos en cada ejecución y conservan su evidencia.
La prueba de cobro anula su propio pago y deja la factura pendiente.
La prueba de notas de crédito conserva la factura y sus dos devoluciones confirmadas.
La prueba de compras anula ambos pagos y deja pendiente la factura de compra.
Desactiva el redondeo del total de esa factura para comprobar centavos de forma explícita.

## Preparar el sitio

Usá el [comando local de preparación y comprobación](site_setup.md) para crear los maestros
y el ejecutor QA de forma repetible. Informa permisos, cupos y configuración pendientes.

Usar un sitio de pruebas con estos maestros:

- Company: `Diamo Release Test`, con moneda ARS y cuentas contables configuradas.
- Customer: `Release Test Customer`, sin impuestos automáticos para este circuito no fiscal.
- Supplier: `Release Test Supplier`, sin impuestos ni retenciones automáticas para el caso básico de compras.
- Item: `RT-ITEM`, servicio sin stock, activo fijo ni Product Bundle, con precio de prueba de 100.
- Mode of Payment: `Release Test Bank`, vinculado al banco propuesto por el asistente de cobros.
- Cuenta de clientes y banco en ARS.

El usuario necesita permisos para crear, confirmar y anular los comprobantes, consultar maestros y leer GL Entry.
La falta de maestros o permisos falla la preparación. No se interpreta como aprobación.
Los casos usan los maestros indicados y no seleccionan una compañía arbitraria.

### Maestros fiscales locales

En `Diamo Release Test`, activá **Agente de percepción** y **Agente de retención IIBB**.
Los clientes y proveedores del circuito básico deben seguir sin impuestos asignados.

- Creá `Release Test Cash` con la cuenta de caja ARS de la compañía, distinta del banco.
- Creá una cuenta de impuestos de la compañía. En test se usa `Release Test Taxes - DRT`.
- Creá `Release Test IVA 3%` como **Impuesto de Percepcion**, categoría IVA, alícuota 3, mínimo imponible 100 y percepción mínima 1.
- Asignale la compañía, la cuenta de venta y su centro de costos.
- Creá `Release Test Fiscal Customer` y asignale ese impuesto en **Impuestos de percepción**.
- Creá `Release Test Manual` como **Punto de Venta**, tipo Manual, habilitado y sin plantilla de impuestos.
- Seleccioná `Mercado interno -sin detalle- RG2485 (WSFEv1)` en el campo obligatorio `ws_afip`.
- Agregá `ACC-SINV-.YYYY.-` a sus secuencias. El caso no confirma esas facturas ni llama a AFIP.
- Creá `Release Test IIBB 2.5%` como **Impuesto de Retencion**, categoría Ingresos Brutos, jurisdicción MENDOZA y alícuota 2,5.
- Configurá base Neto, cálculo Por Monto de Pago, mínimo imponible 100 y retención mínima 1.
- Asignale la compañía, las cuentas de venta y compra, y el centro de costos.
- Creá `Release Test Fiscal Supplier` y asignale ese impuesto en **Impuestos de retención**.
- Agregá `DRT-APERTURA-COMPRA-` a las series de Purchase Invoice.

MENDOZA usa el cálculo local de Argentina. Este caso no consulta padrones externos.
La suite conserva las facturas de apertura y anula su pago y su certificado de retención.

### Usuarios de prueba

Base crea dos usuarios con nombres aleatorios y contraseñas temporales. No les asigna System Manager.
La cuenta API requiere un cupo API libre y un cupo ERP libre para probar su conversión.
La cuenta reducida requiere el tipo `Usuario Reducido de Proyecto` y un cupo disponible, si existe un límite.
Las pruebas no cambian los cupos ni las reglas de permisos del sitio.

Al terminar, incluso ante un fallo, las pruebas intentan deshabilitar sus usuarios y revocar sus claves.
Conservan las identidades deshabilitadas para auditoría. Las tareas propias quedan canceladas.
La comprobación de acceso crea una factura borrador y la elimina al terminar.
Los fallos de limpieza también se notifican como errores.

La prueba reducida permite búsquedas Link, pero exige que no expongan `grand_total` ni `outstanding_amount`.
También exige rechazo al abrir o crear facturas de venta y al listar facturas de compra.

## Ejecutar desde Release Manager

1. Abrir Release Manager.
2. Ejecutar **Sync Catalog**.
3. Crear un grupo con `core_frappe`, `diamo_argentina_payments` y `diamo_service_credits`.
4. Seleccionar el sitio preparado.
5. Ejecutar el grupo y revisar los pasos.
6. En un sitio con HRMS, ejecutar también `diamo_hrms_payments`.

El grupo **Diamo - Validación común** de beta agrega compras, acceso Base y los tres casos fiscales al grupo inicial.
Las ejecuciones desde la interfaz requieren el servidor HTTP y un worker de la cola `long`.

La tarea de `core_frappe` se asigna al usuario autenticado para que pueda borrarla con los permisos normales.
El cliente HTTP conserva el tipo de excepción del servidor. Un error de permisos no satisface una prueba de rechazo contable.

## Validación inicial

En `test.localhost`, `RUN-00010` completó 14 pasos: cuatro de Framework y diez contables, sin fallos ni omisiones.
El sitio tenía Frappe 16.20.0, ERPNext 16.21.1, Base 1.7.0 y Argentina 1.2.2.
HRMS no estaba instalado. Su caso de compatibilidad sigue pendiente de validación real.
Los 48 tests del motor y el control de lint también pasaron.

### Segunda tanda

`RUN-00012` ejecutó el grupo común: 20 pasos aprobados, uno fallido y ninguna omisión.
Compras, pagos parciales, anulaciones y el ciclo de usuarios API pasaron.
El usuario reducido recibió `outstanding_amount` por la API de listado de facturas, aunque no pudo abrir el documento.
El resultado conserva este hallazgo como `issue`, con rol, endpoint y campo expuesto.
Esta ejecución no aprueba la validación común. La política y la implementación de ese permiso requieren revisión.
Los 56 tests del motor y lint pasaron. Eso valida el motor, no elimina el fallo funcional del sitio.

## Cobertura pendiente

Quedan pendientes CRM, Letters, cashflow y otros regímenes fiscales, como Ganancias y padrones externos.
Base todavía no cubre rate limiting, concurrencia de cupos, partes de horas ni preservación de permisos durante migraciones.
Tampoco cubre cargos y descuentos prorrateados de notas de crédito ni proveedores externos.
La variante HRMS necesita una ejecución real en un sitio que tenga las apps requeridas.

Ecommerce, Broker, Réplica y las apps de clientes quedan fuera de esta etapa.

## Integración con Diamo Tools

Diamo Tools permite configurar el sitio y perfil desde **Diamo Release → Pruebas → Configurar pruebas**.
**Ejecutar validación** comprueba los SHA y ejecuta Release Manager. **Historial de validación** conserva cada intento.
El sitio destino necesita Diamo Tools y un ejecutor con System Manager para consultar sus fuentes.
La evidencia incluye el candidato, la cobertura obligatoria, las fuentes antes y después y los resultados.
Un cambio de candidato, sitio o perfil invalida la evidencia anterior. Las omisiones no aprueban.
El modo automático exige `Passed` vigente antes de aprobar, también para una línea base.

### Evidencia de integración en beta

- `RUN-00133`: 17 pasos aprobados, sin fallos ni omisiones, para los tres casos nuevos.
- Release `0.0.0-fiscal.66a47b07`, validación `485tlh4bfs`: `Passed`, con SHA comprobados y evidencia conservada.
- Release `0.0.0-mismatch.a0529d98`, validación `485hnk0am3`: `Incomplete`, sin ejecutar pruebas porque los SHA no coinciden.
- `RUN-00134`: perfil común completo, 37 pasos aprobados, uno fallido, sin omisiones.
- Validación `4856ni701o`: `Failed` por la exposición de `outstanding_amount` al usuario reducido.

Estas ejecuciones están en `diamoerpbeta.localhost` y prueban `test.localhost`.
Las releases de prueba quedan sin aprobar. Los 60 tests del motor pasaron.
