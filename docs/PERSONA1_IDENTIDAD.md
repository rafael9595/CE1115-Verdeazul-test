# Persona 1 · Identidad y acceso

Versión 4.0.0. Integrada a captura (persona 2), gestión (persona 3) y certificados (Olman/persona 4). Se tomaron como fuentes las instrucciones de Parte 2 y los documentos de Parte 1: Arquitectura, Atributo DI, Control de Acceso, Matriz y Políticas del grupo 3.

## Qué se implementó

La cuenta de acceso (`Account`) se vincula a una identidad laboral (`Person`). La identidad conserva autoría, asignaciones e historial aunque cambien la contraseña, las cuentas o los roles. El identificador laboral y el vínculo cuenta-persona son inmutables mediante guardas SQL. Una segunda cuenta para el mismo identificador comparte los roles y las restricciones históricas.

El administrador registra el alta, motivo y referencia de verificación de identidad. La cuenta se crea sin contraseña utilizable. El sistema entrega una sola vez un código aleatorio que vence en 30 minutos; solo su hash se guarda. El titular introduce el código en `/identity/recover/`, elige su contraseña y configura el factor. No se incluyen códigos en enlaces ni en bitácora. La entrega privada y la comprobación de identidad son tareas del administrador; escribir una referencia no sustituye una verificación real.

La baja afecta todas las cuentas de la persona, revoca sus sesiones y finaliza las asignaciones vigentes de técnico, verificador, propietario y auditor. Se conservan los registros históricos. Habilitar nuevamente no restaura esas asignaciones: deben autorizarse otra vez. No se permite retirar al último administrador sin que otra persona administradora tenga contraseña individual y MFA configurados.

## Contraseñas, MFA y recuperación

- Argon2id para almacenar contraseñas; longitud de 15 a 128 caracteres, sin reglas artificiales de composición ni cambios periódicos obligatorios.
- Lista de contraseñas comunes de Django y comprobación de filtraciones mediante Pwned Passwords. El servidor envía cinco caracteres del SHA-1, solicita relleno y compara el sufijo localmente. No envía la contraseña ni el hash completo. SHA-1 solo se utiliza para esa consulta; el almacenamiento utiliza Argon2id.
- Si la consulta externa no está disponible, el alta/cambio se rechaza con 503 y la contraseña anterior se conserva. La lectura de datos y los accesos ya configurados no dependen de esa consulta.
- TOTP de seis dígitos, intervalos de 30 segundos y tolerancia de un intervalo. El último contador aceptado se guarda bajo bloqueo: un código usado no puede reutilizarse, incluso en solicitudes concurrentes.
- La aplicación genera el QR localmente con Segno. No lo envía a un generador externo. El secreto TOTP se cifra mediante Fernet con una clave independiente en `identity.key`.
- Ocho códigos de recuperación aleatorios de 128 bits, guardados solo como hash, de un solo uso. Renovarlos invalida los anteriores. El usuario debe guardarlos fuera del dispositivo autenticador.
- Diez fallos dentro de quince minutos provocan una pausa de quince minutos. El contador está en PostgreSQL y se comparte entre cuentas de la misma persona y entre procesos del servidor.

MFA es obligatorio para administrador, gerente, supervisor, verificador, seguridad y auditor. Técnico y propietario lo necesitan para recuperación y operaciones sensibles. Toda cuenta que ya tenga MFA configurado lo utiliza en cada acceso. La preparación de contraseñas individuales de las cuentas demo exige MFA también a técnico/propietario, porque cambiar credenciales es una operación sensible.

Si se pierde el autenticador, un código de recuperación permite entrar y solicitar la sustitución por el procedimiento autorizado. Si se pierde también la contraseña, otro administrador verifica la identidad y emite una recuperación temporal. Puede autorizar explícitamente reemplazar el factor perdido; sin esa autorización, se exige el factor anterior al canjear el código. Después debe confirmarse el factor con un código nuevo para entrar.

Conviene preparar una segunda persona administradora y custodiar códigos de recuperación. Si el único administrador pierde todos sus medios de acceso, se requiere un procedimiento controlado del operador del despliegue; no existe una contraseña universal ni un endpoint de bypass. El correo del perfil es contacto: no se implementó envío automático de enlaces por correo.

## Roles, herencia y separación de funciones

Cada persona tiene rol principal y roles adicionales. Las cuentas comparten esa lista. Al entrar se activa el rol principal; `Mi cuenta → Función activa` permite escoger otro rol asignado con autenticación reciente. Las operaciones usan esa función activa, evitando mezclar permisos de todas las funciones en una misma petición. La herencia de administrador incluye gerente, supervisor y seguridad mediante las capacidades ya autorizadas por la matriz; no incluye técnico, verificador, propietario ni auditor.

Técnico y verificador no pueden asignarse simultáneamente a una persona, ni usando cuentas distintas. Cambiar de técnico a verificador puede autorizarse para funciones futuras, pero no habilita a aprobar mediciones donde esa persona participó como autor/corrector. Las guardas y los servicios conservan ese rechazo por identidad histórica.

Cambiar roles incrementa la versión de identidad y revoca todas sus sesiones. Retirar una función finaliza sus asignaciones vigentes. Cambiar contraseña o recuperar acceso incrementa la versión de credencial de la cuenta y revoca sus sesiones. El servidor comprueba nuevamente esas versiones al ejecutar los servicios.

## Correspondencia O1/O15

| Rol activo | O1: cuentas y perfil | O15: sesiones |
|---|---|---|
| Administrador | Alta, lectura y gestión global; perfil propio; roles, baja/reactivación, recuperación verificada | Lectura global y revocación global; revocación ajena con autenticación reciente |
| Gerente | Lectura de perfil propio, contacto y credenciales propias | Lectura y revocación propias |
| Supervisor | Igual al perfil propio | Lectura y revocación propias |
| Técnico | Igual al perfil propio; cambios sensibles con MFA | Lectura y revocación propias |
| Verificador | Igual al perfil propio | Lectura y revocación propias |
| Propietario | Igual al perfil propio; no cambia identidad legal ni titularidad | Lectura y revocación propias |
| Auditor | Igual al perfil propio, con encargo vigente para el acceso | Lectura y revocación propias |
| Seguridad | Igual al perfil propio | Lectura global de metadatos, sin revocar sesiones mediante O15 |

La vista propia de sesiones comprende las cuentas de la misma identidad. Seguridad puede salir de su propia sesión mediante Salir, como cualquier usuario, pero la acción administrativa de revocación O15 no está autorizada para ese rol. Las vistas no exponen tokens de sesión, hashes de contraseña, claves, secretos TOTP ni códigos de recuperación guardados.

O1 no permite que el usuario se cambie nombre legal, rol, estado o vínculos de propietario. La baja conserva la cuenta para trazabilidad; no existe borrado destructivo de identidad.

## Sesiones y auditoría

Las sesiones duran como máximo ocho horas y vencen tras treinta minutos sin actividad. La autenticación sensible vence a los cinco minutos; navegar no prolonga esa autorización. `Renovar autenticación` pide contraseña y un código MFA nuevo. La lista de sesiones incluye identificador de registro, cuenta, identidad, función, inicio, última actividad y estado. El identificador del registro sirve para revocar; no sirve para iniciar sesión.

`AuthSession` almacena el hash del identificador de sesión, no el token. Django mantiene su sesión en PostgreSQL. La revocación se verifica en la próxima solicitud y antes de las operaciones protegidas; no deshace una transacción que ya se hubiese confirmado.

Se registran creación de cuenta, consulta/cambio de perfil, cambios de rol, bajas, habilitaciones, emisión/canje de recuperación, MFA, fallos de acceso, inicios/cierres de sesión, reautenticación y revocaciones. Los eventos se integran a la bitácora existente. Copia independiente, retención, alertas H1/H2 y resistencia frente al administrador de BD pertenecen al alcance pendiente de persona 5.

## Conexión con las otras partes

1. El acceso valida contraseña, factor, cuenta, identidad, función y vigencia del encargo de auditor cuando corresponde.
2. El middleware valida la sesión y sus versiones; los servicios vuelven a comprobar el actor dentro de sus transacciones.
3. Captura utiliza la persona y función autenticadas para crear/editar la medición. La cola local conserva su frase y cifrado propios.
4. Sincronizar exige una sesión válida actual. Una baja, retiro de asignación o cambio de rol rechaza la sincronización; no convierte datos locales en información aprobada.
5. Revisión verifica separación de funciones e historial antes de llamar al firmador original. La persona 1 no sustituye la firma ni cambia el formato del certificado.

## Rutas principales

| Ruta | Uso |
|---|---|
| `/login/`, `/logout/`, `/reauth/` | Entrada, salida y renovación de autenticación |
| `/identity/profile/`, `/identity/password/`, `/identity/role/` | Perfil, contraseña y función activa |
| `/identity/mfa/`, `/identity/mfa/setup/`, `/identity/mfa/qr/` | Confirmación, alta y QR privado |
| `/identity/recover/`, `/identity/recovery-codes/` | Activación/recuperación y renovación de códigos |
| `/identity/accounts/`, `/api/identity/accounts/` | Administración de cuentas |
| `/identity/sessions/`, `/api/identity/sessions/` | Consulta de sesiones |
| `/api/identity/action/<acción>/<id o new>/` | POST JSON: create, roles, profile, disable, enable, recovery, grant |
| `/api/identity/sessions/<UUID>/revoke/` | POST: revocar una sesión autorizada |

Todas las mutaciones web requieren CSRF. Los campos aceptados son explícitos. El cambio de roles incluye `expected_version` para rechazar una pantalla obsoleta. Las altas tienen usuario único; los códigos temporales se consumen una vez. No se presenta este módulo como un proveedor OAuth/OIDC ni como una plataforma de correo.

## Archivos y despliegue

`gestion/identity.py` contiene las reglas; `identity_views.py` las vistas; `middleware.py` valida sesiones; `policy.py` propaga la identidad de la petición de forma aislada entre solicitudes. Los modelos nuevos y migraciones son 0006/0007. Las plantillas están en `templates/identity/` y las pruebas en `gestion/tests/test_identity.py`.

La persona 5 debe proporcionar `VERDEAZUL_IDENTITY_KEY_FILE` con la clave MFA desde almacenamiento de secretos, además del secreto Django y la clave de firma. No se pueden regenerar las claves MFA al reiniciar un contenedor. La rotación requiere recifrar los secretos existentes y probar la recuperación. La configuración local monta los archivos de `.local` en modo lectura.

Fuentes técnicas: https://docs.djangoproject.com/en/5.2/topics/auth/default/ ; https://pyauth.github.io/pyotp/ ; https://haveibeenpwned.com/API/v3 ; https://pypi.org/project/segno/1.6.6/ . Las reglas del proyecto provienen de los documentos de Parte 1, no de estas bibliotecas.
