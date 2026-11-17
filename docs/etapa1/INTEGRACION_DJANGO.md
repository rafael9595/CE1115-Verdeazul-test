# Contrato de integración con el backend Django

## Frontera del módulo

La Parte 1 define un **monolito modular**. La firma se incorpora como módulo interno de la aplicación Django; no se crea un endpoint público que firme cualquier JSON. El navegador solicita una aprobación usando un identificador de versión. La identidad y los datos del certificado se resuelven en el servidor.

La matriz reserva GE de O8 al servicio de emisión. El verificador puede aprobar bajo C3, y esa aprobación desencadena la emisión técnica. El administrador no obtiene permiso de firma o aprobación por ser administrador.

El módulo recibe una instantánea, valida su estructura y la firma. No tiene conexión a PostgreSQL, sesión ni conocimiento de las asignaciones. Por eso no puede comprobar si la aprobación existe o si otro certificado está vigente. Esas decisiones corresponden al servicio transaccional del backend. Una comprobación local de que los participantes difieren no sustituye consultar el historial completo en la base de datos.

## API Python disponible y probada

| Función | Entrada | Salida |
|---|---|---|
| `load_private_key_from_environment()` | Variable PEM o ruta externa configurada | Clave Ed25519 en memoria; excepción si falta configuración |
| `issue_certificate(payload, key)` | Instantánea autorizada y clave privada | Diccionario con contenido, clave pública y firma |
| `certificate_bytes(document)` | Documento firmado | Archivo JSON UTF-8 listo para persistir/descargar |
| `verify_certificate(raw, trusted_fingerprints)` | Archivo y huellas conocidas por un canal oficial | Integridad, confianza del emisor y código de resultado |
| `fingerprint(public_key)` | Clave Ed25519 pública | `sha256:` y 64 dígitos hexadecimales |

`ejemplos/instantanea_demo.json` muestra exactamente los campos aceptados. Los UUID de la muestra son sintéticos; deben reemplazarse con los identificadores reales. Todos los valores decimales son cadenas, obtenidas desde `Decimal` y no desde `float`.

## Secuencia obligatoria de aprobación y emisión

Implementar en el servicio de aplicación, utilizando los modelos reales del equipo:

1. Comprobar C1, permiso de aprobación y alcance del usuario. La cuenta se obtiene de la sesión.
2. Entrar en `transaction.atomic()`. Bloquear la finca con `select_for_update()` y después la versión a revisar. Todas las rutas que emitan, invaliden o alteren una condición de emisión deben seguir el mismo orden de bloqueo.
3. Consultar el identificador de operación de un reintento. Con identidad autorizada y contenido idéntico, devolver el resultado ya persistido. Si el mismo identificador se reutiliza con datos diferentes, rechazarlo.
4. Revalidar C3 dentro de la transacción: asignación vigente, versión ENVIADA, ausencia de decisión previa válida y verificador ausente de todos los autores/correctores de la cadena, incluso tras cambio de rol o cuenta.
5. Comprobar C9: datos completos, geometría válida y coherencia con localización, ausencia de otro certificado vigente para la finca. La validación de rangos del módulo no acredita consistencia geográfica ni metodología científica.
6. Si es reemplazo, comprobar antecedente invalidado y enmienda autorizada que corresponde a la cadena. No inferir autorización a partir de un UUID enviado por el cliente.
7. Crear la aprobación y construir la instantánea usando únicamente registros del servidor. El UUID del certificado y la fecha UTC los genera el servidor. Usar identificadores laborales/persona, sin contactos del dueño ni precios.
8. Llamar a `issue_certificate()` y `certificate_bytes()` dentro de la transacción. Persistir los bytes originales, la huella de clave, la relación de aprobación y el estado de vigencia.
9. Registrar el evento de emisión y el resultado de idempotencia en la misma transacción. Si falla la firma, la escritura del certificado o la auditoría local, propagar la excepción y revertir toda la aprobación/emisión.
10. Entregar la respuesta solo después del commit. Si se usa almacenamiento de archivos externo, no asumir que ese almacenamiento participa en la transacción de PostgreSQL: en este alcance conviene persistir los bytes en una columna binaria y descargar desde allí.

La firma no debe programarse con `transaction.on_commit()` si se pretende conservar la atomicidad de aprobación, certificado y evento. Si la firma falla después del commit, ya se habría confirmado una aprobación sin el archivo requerido.

## Persistencia que debe añadir Persona 3

Campos mínimos recomendados para la entidad del certificado: UUID, finca, aprobación/versiones, fecha de emisión, estado actual, antecedente, bytes originales firmados, huella pública y operación idempotente. Mantener un índice único parcial sobre la finca cuando el estado sea VIGENTE. La condición debe cubrir todos los períodos, como exige la Parte 1.

La aprobación de una misma versión también debe tener una restricción de unicidad apropiada. La idempotencia debe guardar una huella de la solicitud asociada a la identidad y a su UUID. Un bloqueo de aplicación sin restricciones en PostgreSQL no basta frente a rutas alternativas.

Guardar una instantánea histórica: editar el catálogo de finca después no altera el polígono ni los valores del archivo emitido. No reconstruir descargas usando el estado actual del catálogo.

No se incluyen migraciones porque no se adjuntó el repositorio Django ni sus modelos. Añadir modelos inventados en paralelo crearía dos fuentes de verdad. Este documento define el contrato para implementar las migraciones en el repositorio común.

## Lectura y descarga según O8

| Rol humano | Lectura directa O8 | Descarga directa O8 | Restricción |
|---|---|---|---|
| Técnico | Sí | Sí | Asignación o participación histórica en el objeto |
| Verificador | Sí | Sí | Asignación o participación histórica en el objeto |
| Administrador | Sí | Sí | Global; no obtiene aprobación técnica |
| Auditor | No | No | Accede a representación dentro de O11 proyectado, C6 y encargo vigente |
| Propietario | Sí | Sí | Finca propia o representación vigente, C4 |
| Gerente | Sí | Sí | Alcance global permitido; sin invalidación |
| Supervisor | Sí | No | O8 solo L; O11 tiene su propio permiso de reporte técnico |
| Seguridad | No | No | Accede a metadatos de seguridad, no al certificado técnico |

Toda consulta/descarga aplica C12, registra el evento y evalúa H1/H2. La proyección de un reporte no puede introducir campos privados que el archivo firmado excluye. La representación del certificado dentro de O11 debe mantener el enlace con el original y su huella; si se entrega el archivo original en ese flujo, sigue siendo una operación de O11 autorizada y auditada.

## Invalidación y verificación

Solo el administrador puede invalidar bajo C8: autenticación reciente (cinco minutos según la Parte 1), certificado vigente y motivo obligatorio. Modificar el estado y registrar el evento; conservar intactos los bytes firmados. Un certificado invalidado puede conservar una firma matemáticamente válida. El sistema debe mostrar por separado la firma y la vigencia consultada en PostgreSQL.

La herramienta de verificación local recibe un archivo ya proporcionado por el usuario y no consulta expedientes. Si se añade una pantalla web de verificación, puede limitarse a ese archivo, sin habilitar búsqueda por UUID o finca. Una futura consulta pública de vigencia sería una decisión adicional de alcance y privacidad; no se presupone un portal anónimo de expedientes.

## Pruebas pendientes de integración

| Caso | Resultado esperado en el backend completo |
|---|---|
| Técnico solicita aprobar o emitir directamente | Denegación del servidor y evento |
| Verificador participa en el historial de la cadena | Denegación C3, incluso tras cambio de rol |
| Dos emisiones diferentes de la misma finca | Solo una vigente; la otra se rechaza sin aprobación parcial |
| Reintento idéntico y todavía autorizado | Mismo certificado persistido; no se vuelve a firmar |
| Falla al cargar la clave, firmar, guardar o auditar | Rollback de aprobación y emisión |
| Supervisor solicita descarga directa O8 | Denegación; no basta ocultar botón |
| Propietario pide certificado de otra finca | Denegación sin revelar contenido |
| Gerente solicita invalidación | Denegación |
| Administrador invalida con C8 completo | Estado cambia; archivo original idéntico |
| Catálogo de finca cambia después de emisión | Descarga conserva los bytes y datos históricos |
| Archivo tiene precio o datos personales adicionales | Rechazo de formato del módulo |

Las pruebas del paquete validan el módulo criptográfico. Los casos de la tabla requieren el backend, la base de datos y las sesiones reales; no se presentan como ya ejecutados.
