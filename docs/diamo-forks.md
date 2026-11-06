# Regresión de los forks Diamo

El perfil **Diamo Forks** ejecuta contratos de Base y Argentina sobre los forks de Frappe y ERPNext.
Su lista está en `release_tests/diamo_contracts.py`. No depende de nombres de ramas ni de la marca upstream `Sidebar`.

## Instalar el perfil en el control

Actualizá `release_tests` en el bench `pilot` y en el bench `releases`.
Desde el bench de control, ejecutá:

```bash
bench --site SITIO_CONTROL execute release_tests.profiles.install_diamo
```

Reemplazá `SITIO_CONTROL` por el nombre real del sitio de control.
El comando requiere Administrator y Release Manager. Sincroniza el catálogo y crea **Diamo Forks**.
Conserva el grupo **Diamo** existente. Si **Diamo Forks** ya existe con otra selección, informa el conflicto.

## Preparar el destino

Desde `sites` del bench `releases`:

```bash
/home/frappe/pilot/benches/releases/env/bin/python \
  -m frappe.utils.bench_helper frappe \
  --site test.releases.diamo.com.ar execute release_tests.site_setup.prepare \
  --kwargs '{"suites":"diamo"}'
```

Para comprobar sin guardar datos, reemplazá `prepare` por `check`.
Seleccioná **Diamo Forks** como perfil de la release en Tools.
Usá las credenciales del ejecutor `release-qa@example.com` en Testing Site.

## Contratos cubiertos

| Área | Evidencia |
|---|---|
| Pagos de Argentina | Mapper público, cobro inicial cero, medios de pago, importes, asignación, libro mayor y saldo. |
| Compras y ventas | Circuitos completos con órdenes, recepciones, entregas, facturas y pagos. |
| Compras multimoneda | Orden en ARS facturada en USD con enlaces conservados y conversión explícita. |
| Comprobantes de compra | Compra no fiscal válida y rechazo de identificadores fiscales incompletos. |
| Contabilidad Diamo | Pagos parciales, cobros combinados, percepciones, retenciones, créditos y cancelaciones. |
| Stock y fabricación | Existencias, lotes, números de serie, BOM y Work Order con usuario QA. |
| Personalizaciones | Campos efectivos de User, facturas, pagos, clientes y proveedores mediante la API de Base. |
| Límites administrativos | QA no puede crear Custom Field, Client Script ni Server Script. |
| Acceso Base | Autenticación API, revocación, bloqueo de login y límites del usuario reducido. |
| Frappe | Filtros SQL, rango Python con `>=` y `<=`, Jinja y permisos de documentos propios. |
| Composición de apps | `check` verifica veinte controladores efectivos, mixins de Journal Entry/Payment Request y RPC críticos. |

La prueba multimoneda conserva el precio nominal de la orden. Respeta `maintain_same_rate`.
No prueba una excepción a esa política de precios.
Los circuitos contables locales no envían comprobantes a ARCA ni pagos a proveedores externos.

La verificación de controladores detecta overrides desplazados o ausentes. No sustituye una prueba funcional de cada método.
Todavía falta cobertura funcional dedicada de suscripciones, conciliación bancaria y proveedores de pago externos.

## Funciones upstream y apps opcionales

El candidato Frappe 16.20 no implementa `between` en `evaluate_filters`.
`diamo_frappe_filters` prueba el rango equivalente con operadores Python soportados y sus límites SQL.
`frappe_filters` conserva la exigencia upstream de `between` Python. Si se selecciona, la discrepancia sigue siendo un fallo.

Las suites `v16p_*` verifican funciones de la rama upstream “polished”.
No integran este perfil porque esas funciones no forman parte del contrato actual de los forks.
Cuando se incorporen, agregá sus contratos al perfil y comprobá los requisitos administrativos.

CRM, Helpdesk y HRMS pueden agregarse en un perfil ampliado.
Pasá ese perfil exportado a `prepare/check` con `profile_path`, para comprobar el mismo alcance.
La preparación asigna los roles HR activos si el perfil contiene suites HRMS.
Los requisitos HRMS aún no cubiertos se informan como bloqueos.

`customisations` sigue disponible para probar personalizaciones creadas por Administrator en un sitio dedicado.
`diamo_customizations` prueba las personalizaciones de las apps y las restricciones de Base con el usuario operativo.

## Validar un upgrade

1. Instalá la misma revisión del motor en los benches de control y destino.
2. Prepará una base QA y guardá un respaldo.
3. Ejecutá el perfil contra la versión vigente. Conservá los resultados y los SHA.
4. Desplegá los SHA candidatos en el bench destino.
5. Restaurá la base QA y ejecutá las migraciones del candidato.
6. Ejecutá `check` con el mismo perfil y usuario.
7. Ejecutá una nueva validación desde Tools.
8. Compará los pasos, los errores y la cobertura con la ejecución de referencia.

Un paso omitido no prueba compatibilidad. Un fallo conocido, como la exposición del saldo al usuario reducido, sigue bloqueando aprobación.
No cambies una expectativa solo para aceptar el candidato. Revisá primero si cambió el contrato del producto.

## Pruebas del motor

```bash
pytest -q
bench --site test.localhost run-tests --app release_tests \
  --module release_tests.site_setup.test_fork_flows
```

Las pruebas locales ejecutan RPC reales, sus overrides y los controladores bajo el usuario QA.
Serializan las respuestas y revierten las solicitudes fallidas como una petición HTTP.
No verifican el transporte HTTP de Pilot. Esa evidencia la proporciona la validación remota.
