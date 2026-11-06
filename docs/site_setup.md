# Preparar un sitio QA de Diamo

Para los forks de Diamo, usá el [perfil de regresión Diamo Forks](diamo-forks.md).
`prepare/check --kwargs '{"suites":"diamo"}'` selecciona sus contratos de Base, Argentina, Frappe y ERPNext.

`release_tests.site_setup` prepara los datos locales que usan las suites Diamo.
Se ejecuta en el bench del sitio de pruebas como Administrator. No expone métodos HTTP.
El paquete `release_tests` debe estar disponible en el entorno Python del bench.
No requiere instalar Tools ni Release Manager en el sitio destino.

## Preparar

```bash
bench --site test.releases.diamo.com.ar execute release_tests.site_setup.prepare
```

El comando crea los registros que faltan:

- Compañía `Diamo Release Test`, abreviatura DRT, moneda ARS y plan estándar numerado.
- Cuentas, cliente, proveedor, servicio `RT-ITEM` y medios de pago Bank/Cash.
- Maestros de percepción IVA y retención IIBB cuando se seleccionan sus suites.
- Usuario API `release-qa@example.com`, con roles operativos y System Manager.
- Server Script `RT Filter Probe`, cuando se selecciona filtros y los scripts están habilitados.

Conserva las credenciales del usuario y no las imprime ni las genera.
No asigna permisos globales de escritura, no modifica cupos y no habilita roles desactivados.
Si encuentra un maestro incompatible, se detiene con `Fixture conflict` y revierte la transacción.
Revisá el registro indicado antes de repetir. No elimina comprobantes ni reinicia el sitio.

El resultado incluye `ready`, `blockers`, `suites` y `user`. Los bloqueos de preparación
no son resultados funcionales ni sustituyen las pruebas de la release.

## Elegir suites

El conjunto predeterminado incluye Framework, CRM, ERPNext contable, filtros y las suites
Diamo de pagos, compras, créditos, cobros combinados, percepciones, retenciones y acceso Base.
La lista exacta se devuelve en `suites`. Para elegir otra lista:

```bash
bench --site test.releases.diamo.com.ar execute release_tests.site_setup.prepare \
  --kwargs '{"suites":["core_frappe","erpnext","diamo_argentina_payments"]}'
```

La preparación contable crea los maestros básicos aunque solo se seleccione una suite.
Los maestros fiscales se agregan si se seleccionan `diamo_perceptions` o `diamo_withholdings`.
El comprobador informa como bloqueantes las suites cuyos requisitos aún no cubre,
por ejemplo las suites `v16p_*`. No las declara listas por tener sus apps instaladas.

## Resolver los requisitos externos

1. Asigná cupos API suficientes: uno para QA y otro libre para `diamo_base_access`.
   Esa suite también necesita un cupo ERP libre para convertir su usuario temporal y un
   cupo de Usuario Reducido de Proyecto, si existe un límite para ese tipo.
2. Generá las claves del usuario QA desde User como Administrator y cargalas en Testing Site.
   No uses las claves de Integración Diamo para ejecutar los circuitos contables.
3. Para `frappe_filters`, habilitá los scripts en el bench dedicado de pruebas:

```bash
bench --site test.releases.diamo.com.ar set-config -g server_script_enabled 1
```

Esta opción es del bench y afecta a todos sus sitios. Volvé a ejecutar `prepare` después
de cambiarla para crear el probe. Un probe existente con contenido distinto se informa;
no se sobrescribe.

Base reserva Custom Field, Client Script y Server Script para Administrator.
Por eso un usuario QA con roles operativos no puede ejecutar la suite `customisations`.
El comprobador informa esa restricción. Preparar el probe localmente no elimina la restricción.
La suite de personalizaciones requiere una ejecución con Administrator mediante login y
`Allow Customisations` en Testing Site; mantené ese alcance en un perfil separado.

## Comprobar sin modificar

### Usar el perfil real de la validación

Exportá el JSON de `Diamo Release Validation` desde el control.
Guardalo como `/home/frappe/release-validation.json` en el servidor destino.
También se acepta un archivo con el array de `profile_snapshot`.

```bash
bench --site test.releases.diamo.com.ar execute release_tests.site_setup.check \
  --kwargs '{"profile_path":"/home/frappe/release-validation.json"}'
```

`prepare` acepta el mismo argumento. No combines `profile_path` con `suites`.
El archivo define las suites exactas. El comando no consulta el perfil del control por HTTP.
Sin estos argumentos, el comando comprueba solo las suites predeterminadas, no todo el grupo Diamo.
Las suites sin requisitos cubiertos siguen apareciendo como bloqueos.

### Comprobar el conjunto predeterminado

```bash
bench --site test.releases.diamo.com.ar execute release_tests.site_setup.check
```

Usá la misma selección de suites y el mismo ejecutor que en Testing Site:

```bash
bench --site test.releases.diamo.com.ar execute release_tests.site_setup.check \
  --kwargs '{"suites":["core_frappe","erpnext"],"user":"release-qa@example.com"}'
```

Este comando solo consulta registros, permisos, configuración y cupos. No prueba las
credenciales guardadas en Tools ni la conectividad HTTP. `ready: true` significa que
pasaron estas comprobaciones previas; las suites todavía deben ejecutarse.
Los comandos no están conectados automáticamente al flujo de validación de Tools.

### Compañía y motor de pruebas

Las suites genéricas prefieren `Diamo Release Test` cuando existe y el ejecutor puede verla.
La preparación configura sus cuentas de inventario, mercadería recibida sin facturar y ajuste de stock.
En sitios sin esa compañía, las suites conservan la selección anterior.
Actualizá `release_tests` en ambos benches: el control ejecuta las suites y el destino ejecuta la preparación.
La suite de filtros usa una marca distinta por ejecución. Conserva los ToDos anteriores como evidencia.

## Pilot sin `bench` en PATH

Desde `sites` del bench de pruebas:

```bash
cd /home/frappe/pilot/benches/releases/sites
../env/bin/python -m frappe.utils.bench_helper frappe \
  --site test.releases.diamo.com.ar execute release_tests.site_setup.prepare
```

Para comprobar, reemplazá `prepare` por `check`. Para habilitar scripts, usá el mismo
prefijo con `set-config -g server_script_enabled 1`.

## Repetir y guardar una base

La preparación es repetible. No borra el historial ni revoca claves existentes.
Guardá un respaldo del sitio preparado para las validaciones finales reproducibles.
Restaurar un respaldo no cambia los SHA del bench: desplegá el candidato y migrá el sitio
antes de ejecutar las suites.

## Verificación del código

Pruebas sin Frappe: `pytest tests/test_site_setup_contract.py`.
Pruebas de integración en un sitio local con ERPNext, Base y Argentina:

```bash
bench --site test.localhost run-tests --app release_tests \
  --module release_tests.site_setup.test_setup
```
