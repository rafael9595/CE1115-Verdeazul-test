# Cobertura y límites de la integración

## Fuentes y alcance

Se utilizaron las instrucciones `Proyecto_Parte2_Implementacion_CE1115.pdf` y los cinco documentos de Parte 1: Arquitectura, Atributo DI, Control de Acceso, Matriz y Políticas, grupo 3. Esta entrega implementa captura/catálogo/sincronización de la persona 2, gestión/revisión/reportes de la persona 3 y firma de Olman. El acceso local es un apoyo de prueba; no equivale a completar los módulos 1/5.

## Controles implementados

| Regla/objeto | Implementación | Evidencia en `gestion/tests/test_integration.py` |
|---|---|---|
| C3 / O6 | Verificador asignado, versión enviada, sin decisión previa, no autor/corrector de ninguna versión por identidad laboral | Autorización, rol cambiado, cuenta duplicada e historial |
| C2 / O5 | Borrador editable por técnico original asignado; enviado inmutable; devolución conserva origen y crea versión | Corrección, edición prohibida, técnico no disponible |
| O4 | Crear y cerrar períodos para administrador/gerente; no reabrir cerrados | Permisos y trigger de no reapertura |
| C7 / O7 | Solicitud y autorización específica; administrador con autenticación ≤5 minutos; técnico original; sin reapertura general | Flujo completo con período cerrado y roles negativos |
| C8 / O8 | Invalidar con motivo, autor y fecha; bytes originales preservados | Firma válida tras invalidación y guardas SQL |
| C9 | Un vigente por finca entre todos los períodos; firma y persistencia transaccionales; reemplazo con enmienda/antecedente invalidado | Restricción única, concurrencia, rollback de firma/auditoría |
| C9 / geografía | Polígono cerrado, simple, con área geométrica positiva y contenido en Costa Rica según Natural Earth | Rechazo de geometría inválida; límites de cartografía documentados |
| O8 | Descarga original restringida; auditor/supervisor/seguridad sin descarga directa | Matriz de descarga |
| O10 | Precio: escritura administrador/gerente, lectura adicional de propietario propio | Proyecciones positivas/negativas |
| O11 | Reporte según ámbito; auditor con encargo vigente y sin propietario/precio; cadena y original firmado preservados | Encargo vencido, propietario ajeno, historial sin acceso futuro |
| Integridad | Revisiones/eventos/operaciones de solo anexado; versiones enviadas y archivos firmados protegidos por triggers | UPDATE/DELETE rechazados; datos históricos preservados |
| Reintentos | UUID por persona + digest de petición; reautorización actual | Repetición, reutilización distinta, revocación y concurrencia |
| Apoyo C1 | Argon2, sesión inactiva 30 min/máxima 8 h, cambio de rol, CSRF, reautenticación y límite simple de intentos | Sesión, acceso real con contraseña, rol y CSRF |

## Diferencias y decisiones que deben registrarse

1. **Correcciones:** una devolución crea una versión nueva; no se sobrescribe la versión devuelta. Mantiene la trazabilidad y exige ajustar cualquier texto previo que suponga edición sobre el mismo registro.
2. **Identidad:** se utiliza un rol primario por persona con capacidades explícitas. No se ha implementado un motor de múltiples roles acumulables; el equipo debe acordar esa correspondencia al integrar identidad.
3. **Certificado:** se conserva el formato JSON `VA-CARBON-1` firmado con Ed25519 y clave pública incrustada. No es PDF firmado, JWS, una PKI comercial ni una validación jurídica de firma digital.
4. **Geografía:** Natural Earth 1:10m es una referencia general. No prueba concordancia catastral ni equivalencia entre el área declarada y el polígono. Cerca de límites/costas puede rechazar geometrías legítimas; el origen debe mejorarse si la validación exigida requiere precisión catastral. Los valores y polígonos de demo no son mediciones reales.
5. **Auditoría:** los triggers impiden cambios ordinarios de registros, pero un propietario/superusuario de BD puede alterar el esquema. No se afirma resistencia frente a ese administrador ni existencia de una copia independiente.
6. **Autorización:** los servicios y consultas aplican controles de fila y proyecciones en Django. **No se implementaron políticas PostgreSQL RLS** ni se verificaron roles de BD de mínimos privilegios en producción. Deben coordinarse entre personas 1/5 antes de afirmar conformidad completa con la arquitectura de Parte 1.
7. **Vigencia:** la firma offline no consulta revocaciones. El panel/reporte indica el estado de negocio. La invalidación anterior y la aprobación del reemplazo son dos actos autorizados; entre ellos puede no haber certificado vigente.
8. **Entorno:** ejecución comprobada en Python 3.12.14/PostgreSQL 17.11. La imagen propone Python 3.13, de acuerdo con la arquitectura; su construcción/ejecución sigue por comprobar en Docker.

## Lo que sigue pendiente para toda la Parte 2

| Componente pendiente | Responsable principal |
|---|---|
| Registro/administración de cuentas, recuperación, MFA según diseño, administración de sesiones y matriz completa O1/O15 | 1 |
| Validación de IndexedDB/Service Worker y recorrido offline en Windows y Safari/iOS; ajuste de precisión cartográfica según requerimientos finales | 2 con todos |
| RLS, separación de credenciales de ejecución/migración y pruebas con rol restringido | 5 con 1 y 3 |
| Bitácora completa de todos los módulos, copia independiente/retención y alertas H1/H2 | 5 |
| Cloud Run, PostgreSQL Neon cifrado, Secret Manager, Artifact Registry y URL HTTPS accesible | 5 |
| Activación/evidencia de Dependabot y revisión de alertas reales en repositorio | 5 con todos |
| Cobertura celda por celda de toda la matriz, informe final de 6–10 páginas y presentación de 15 minutos | Todos |

Las 138 pruebas automatizadas de las suites demuestran los casos definidos para estos módulos, no todas las celdas del proyecto. No se desplegó ningún servicio en nube, no se verificó acceso desde otra red y no se ejecutó GitHub Actions. Tampoco se probaron recuperación ante desastre, carga sostenida ni el recorrido offline completo en un navegador. Se probaron el cifrado con Web Crypto en Node y el protocolo de sincronización en PostgreSQL/HTTP; la comprobación IndexedDB se incluye para ejecución en el navegador del usuario.

## Cobertura añadida en 3.0.0

| Regla/objeto | Implementación | Verificación |
|---|---|---|
| O2/C5 | Catálogo administrativo y lectura asignada/histórica/propia; sin propietario/contacto en proyección técnica | Matriz de roles, finca sin historia tras revocación y preservación de instantánea firmada |
| O3 | Asignación por administrador/supervisor, rol activo, verificador independiente, finalización histórica | Rol incorrecto, gestor no autorizado, autor histórico y guardas SQL |
| O9/C4 | Alta administrativa; contacto propio; nombre legal solo administrador; vínculo con referencia y revocación | Contacto propio/ajeno, cambio legal denegado, vigencia del vínculo |
| O5/C2 | Captura técnica asignada, período abierto, autor desde sesión, borrador validado | Campos extra, captura por otros roles, datos incompletos y cierre |
| Edición concurrente | Revisión esperada de catálogo/contacto/borrador; actualización dentro de bloqueo | Revisión obsoleta sin sobrescritura |
| O16/C11 | Cola propia cifrada, UUID/huella, revisión base, fechas separadas, constancia durable | Reintentos idénticos/diferentes, autor falso, asignación/cuenta revocada, dos solicitudes concurrentes |
| C7/C11 | Se admite sincronizar una corrección ya creada y autorizada en período cerrado | Prueba positiva de enmienda y negativas de captura ordinaria/cierre/versión enviada |
| Pendientes | Error o respuesta no confirmada conserva payload; confirmación válida permite retirar payload y guardar constancia | Pruebas de transición de cola y cifrado; prueba IndexedDB disponible para navegador |
| Estado de cola | Técnico propio y administrador/supervisor; solo conteos y fecha de recepción | Roles prohibidos y ausencia de valores |

`gestion/tests/test_capture.py` añade 44 casos a los 51 anteriores; `tests_js/vault.test.mjs` añade 12 pruebas de criptografía/cola local. La página de ocho comprobaciones de navegador es una herramienta de validación pendiente por plataforma, no evidencia ejecutada aquí.

## Decisiones específicas de captura

- Sincronizar guarda un borrador; enviar a revisión continúa siendo una operación explícita online. La edición local no cambia permisos ni certifica datos.
- La frase local es distinta de la contraseña del servidor. La pérdida de la frase sin recuperación externa de los datos es un riesgo residual; no se implementa una puerta de recuperación que permita al administrador leer borradores ajenos.
- Solo se precargan fincas asignadas y borradores editables. El almacén conserva pendientes aunque el catálogo preparado cambie o la sesión venza.
- La resolución de conflictos de revisión requiere comparar explícitamente ambos contenidos y crear otro intento. No se usa último escritor gana. Casos con estado enviado/aprobado o permisos retirados conservan el pendiente para tramitación autorizada.
- El estado global de cola es el último conteo informado por el dispositivo; no representa conocimiento en tiempo real de equipos sin conexión.
- La exportación/importación es cifrada y la importación no sobrescribe un perfil existente. Las constancias confirmadas se limpian al desbloquear después de siete días; los pendientes no tienen borrado automático.
- La aplicación no afirma que una referencia escrita por el administrador verifique por sí sola un documento legal, ni que los datos sintéticos certifiquen carbono real.
