# Verdeazul · Identidad, captura, gestión y certificados

**Integración de aplicación: v4.0.0. Imagen de despliegue: v4.0.1.** Aplicación Django/PostgreSQL para CE-1115. Conserva el núcleo de firma y verificación de Olman, los certificados históricos y la captura sin conexión. La etiqueta `v4.0.1` identifica la imagen de Docker desplegada y no implica por sí sola cambios funcionales con respecto a la integración v4.0.0.

## Despliegue en la nube (Parte 2 de CE-1115)

Esta sección documenta la instalación que se configuró en Google Cloud y Neon. **No contiene secretos ni instrucciones para crear contraseñas de producción en GitHub.** Las instrucciones anteriores de Docker Compose siguen siendo válidas para el entorno local.

### Entorno desplegado

| Elemento | Configuración |
|---|---|
| Repositorio | [rafael9595/CE1115-Verdeazul-test](https://github.com/rafael9595/CE1115-Verdeazul-test), rama `main` |
| Proyecto Google Cloud | `ce1115-verdeazul` |
| Región Cloud Run / Artifact Registry | `us-central1` |
| Servicio Cloud Run | `verdeazul-gestion` |
| URL del servicio | <https://verdeazul-gestion-782721276810.us-central1.run.app/> |
| Base de datos | Neon PostgreSQL, base `neondb`, rama `production` |
| Registro de imágenes | `us-central1-docker.pkg.dev/ce1115-verdeazul/verdeazul-images` |
| Imagen etiquetada | `verdeazul-gestion:v4.0.1` |
| Cuenta de servicio de ejecución | `verdeazul-app@ce1115-verdeazul.iam.gserviceaccount.com` |
| Trigger de compilación | `verdeazul-docker-build` (Cloud Build) |

El servicio usa HTTPS proporcionado por Cloud Run. La conexión de la aplicación con Neon exige TLS con verificación del certificado del servidor. Las credenciales permanecen en Secret Manager y no se suben al repositorio.

### Versiones y trazabilidad de compilación

| Imagen | Commit de origen | Build ID | Verificación |
|---|---|---|---|
| `v4.0.1` | [`2a7c7fea61b6b211f0b50a63b155f61514e3c67d`](https://github.com/rafael9595/CE1115-Verdeazul-test/commit/2a7c7fea61b6b211f0b50a63b155f61514e3c67d) | `371d9e10-8b33-4d1e-9bd5-a9bf5d81f40b` | Compilación correcta; artefacto publicado en Artifact Registry |

El historial de Cloud Build demuestra la relación **commit → build → imagen**. Para comprobar el despliegue exacto en Cloud Run, comparar el *digest* de la revisión activa con el *digest* del artefacto registrado; la etiqueta por sí sola no demuestra esta última correspondencia.

### Compilación y actualización de la imagen

Requisitos: permisos de proyecto apropiados, integración del repositorio con Cloud Build y Dockerfile versionado en la raíz.

1. Confirmar que los cambios revisados están publicados en `main` y registrar el SHA del commit.
2. Ejecutar el trigger `verdeazul-docker-build` desde Cloud Build, o registrar una versión nueva en la configuración de compilación antes de iniciar el build.
3. Verificar que el build termine correctamente y que Artifact Registry contenga la **nueva etiqueta explícita** (por ejemplo, `v4.0.2`), junto con el digest.
4. Desplegar esa imagen desde **Cloud Run → Servicios → verdeazul-gestion → Editar y desplegar nueva revisión**, manteniendo las variables, volúmenes y cuenta de servicio correctos.
5. Comprobar la nueva revisión, sus registros, acceso HTTPS y funcionamiento de la aplicación. Documentar el SHA, la etiqueta y el digest desplegado.

No sobrescribir una versión existente con código nuevo: crear una etiqueta nueva en cada entrega. Para recuperar una versión, volver a desplegar una imagen identificada y verificada en Artifact Registry.

### Secret Manager y configuración de ejecución

| Secreto de Secret Manager | Uso en Cloud Run |
|---|---|
| `DATABASE_URL` | Variable secreta `DATABASE_URL` (Neon, sin incluir el valor en documentación) |
| `DJANGO_SECRET_KEY` | Variable secreta `DJANGO_SECRET_KEY` |
| `VERDEAZUL_IDENTITY_KEY` | Volumen: `/secrets/identity.key` |
| `VERDEAZUL_SIGNING_PRIVATE_KEY` | Volumen: `/secrets/signing/signing.pem` |
| `VERDEAZUL_TRUSTED_PUBLIC_KEYS` | Volumen: `/secrets/public/public.pem` |
| `DEMO_PASSWORD` | Contraseña temporal para la carga inicial de datos de demostración; no es necesaria para el servicio web |

Variables **sin contenido secreto** del servicio:

```dotenv
DJANGO_ALLOWED_HOSTS=verdeazul-gestion-782721276810.us-central1.run.app
DJANGO_LOCAL=0
VERDEAZUL_IDENTITY_KEY_FILE=/secrets/identity.key
VERDEAZUL_SIGNING_PRIVATE_KEY_FILE=/secrets/signing/signing.pem
VERDEAZUL_TRUSTED_PUBLIC_KEYS=/secrets/public/public.pem
```

**Seguridad:** la cuenta `verdeazul-app` debe tener acceso solo a los secretos necesarios. Los archivos privados `signing.pem`, `identity.key`, `.env`, contraseñas y tokens **no deben incorporarse a Git**. Los contenidos de los secretos no se muestran en capturas ni documentación. Verificar que las claves Ed25519 correspondan al mismo par y que los certificados emitidos puedan validarse.

### Preparación de la base de datos

La instancia de Neon se inicializó ejecutando las migraciones de Django desde un **Cloud Run Job** con la misma imagen del servicio. Las migraciones de `gestion` `0001` a `0007` se aplicaron correctamente; además se ejecutaron las migraciones estándar de Django. Los datos de demostración se cargaron una vez con `seed_demo`.

Procedimiento para una instalación **nueva**, sin ejecutar comandos de inicialización contra la base de producción existente:

1. Crear una base PostgreSQL en Neon y configurar una cadena `DATABASE_URL` con TLS verificado; almacenar la cadena solamente en Secret Manager.
2. Configurar la cuenta de servicio, variables y los secretos del Job de migración.
3. En **Cloud Run → Trabajos**, crear o editar un trabajo con la imagen versionada y sustituir el comando del contenedor por `python manage.py migrate` (comando y argumentos según los campos de la consola).
4. Ejecutar el trabajo, confirmar salida exitosa y revisar el historial de migraciones en PostgreSQL.
5. **Opcional, solo en instalaciones de prueba:** ejecutar una vez `python manage.py seed_demo` con `ALLOW_DEMO=1` y `DEMO_PASSWORD` obtenido de Secret Manager. Después quitar o desactivar `ALLOW_DEMO` y deshabilitar la operación de carga inicial. **No ejecutar `seed_demo` de nuevo sobre producción sin revisar sus efectos.**

Nunca ejecutar `scripts/setup_local.py` para reinicializar una base con datos existentes. La base de producción se preserva entre las revisiones de Cloud Run.

### Dependabot y pruebas de seguridad

Existe `.github/dependabot.yml` con actualizaciones de dependencias. En la configuración de GitHub se confirmó que **Dependency graph** y **Dependabot alerts** están activados. En la revisión del 20 de noviembre de 2026, GitHub mostraba **0 alertas abiertas y 0 cerradas**; las solicitudes de actualización de versiones son distintas de las alertas de vulnerabilidades. Revisar futuras alertas y probar cualquier actualización antes de fusionarla.

También se verificó en Neon la presencia de 22 triggers activos, una actualización rechazada por el trigger `event_append_only`, y la persistencia de usuarios, fincas, mediciones, versiones, certificados y eventos. La configuración del trigger de auditoría cubre `BEFORE UPDATE OR DELETE`; la prueba anterior de eliminación no produjo un error visible, por lo que no se presenta como prueba de bloqueo de `DELETE` en ejecución.

**Pruebas adicionales que siguen pendientes de evidencia:** emisión y verificación de certificados desde Cloud Run (incluida alteración), cobertura completa de permisos por rol, validación del digest en la revisión activa y acceso independiente desde otra red. Los resultados de las pruebas locales incluidos más abajo no equivalen a haber repetido todas esas pruebas en producción.

## Actualizar una instalación existente

Siga **[ACTUALIZAR_SIN_PERDER_DATOS.md](docs/ACTUALIZAR_SIN_PERDER_DATOS.md)**. Contiene los comandos para importar la configuración de la carpeta `(3)` a una extracción nueva. No ejecute `setup_local.py` sobre una instalación anterior. Conserve el nombre Compose `verdeazul-p3-p4`, el volumen de PostgreSQL, `.env` y `.local`.

Esta versión añade una clave independiente para proteger MFA; el helper `configurar_identidad.py` la prepara sin regenerar la clave de firma. Las migraciones 0006/0007 conservan los datos y cierran las sesiones anteriores. El primer acceso requiere configurar el segundo factor y elegir una contraseña individual. La clave inicial de `.local/credenciales.txt` deja de servir para cada cuenta una vez cambiada.

## Lo añadido para la persona 1

- Cuentas: alta con verificación registrada, activación de un solo uso, datos de identidad, roles múltiples y baja/reactivación por persona.
- Contraseñas: Argon2id, 15–128 caracteres, rechazo de claves comunes/comprometidas y recuperación autorizada.
- MFA: aplicación autenticadora con TOTP y QR generado localmente; secretos cifrados; ocho códigos de recuperación de un solo uso.
- Sesiones: consulta y revocación según O15, cierre al retirar acceso, 30 minutos de inactividad y máximo ocho horas.
- Acciones sensibles: contraseña y factor confirmados durante los últimos cinco minutos.
- Separación de funciones por identidad laboral, compartida entre cuentas e independiente de cambios de rol.
- Bitácora de altas, roles, autenticación, recuperación y revocación sin registrar contraseñas, tokens ni secretos MFA.

Se mantienen el catálogo de fincas, propietarios, asignaciones, captura/cifrado local, revisión, enmiendas, reportes y certificados. Flujo: **cuenta y permisos → captura → revisión independiente → certificado firmado**.

## Instalación nueva

Solo para quien todavía no tiene datos: Docker Desktop con contenedores Linux y Python 3.12/3.13. PowerShell dentro de `verdeazul_integrado`:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\.venv\Scripts\python.exe scripts\setup_local.py
docker compose up --build -d
docker compose logs --tail 40 web
Get-Content .local\credenciales.txt
```

Abra http://localhost:8000. Complete el primer acceso descrito en **[PRUEBA_PERSONA1.md](docs/PRUEBA_PERSONA1.md)**. Se requiere conexión a Internet para comprobar contraseñas nuevas contra la lista de filtraciones. Un fallo de esa consulta rechaza el cambio y conserva la contraseña anterior.

## Probar la integración completa

Primero configure la cuenta `administrador` en el navegador. Luego:

```powershell
.\.venv\Scripts\python.exe scripts\probar_identidad.py
```

Introduzca su contraseña individual y un código MFA nuevo cuando se soliciten. El script crea tres cuentas sintéticas, activa MFA, comprueba el cierre y la revocación de sesiones, captura una medición, la revisa con otra persona y verifica el certificado y su alteración. Al terminar deshabilita las cuentas creadas y conserva evidencia. No modifica las credenciales del administrador. Resultado esperado: `"resultado": "OK"`. Para repetir: `--out salida_identidad_2`.

Las pruebas anteriores `probar_integracion.py` y `probar_captura.py` siguen incluidas; ahora sus cuentas deben estar configuradas y sus accesos solicitan MFA. La prueba nueva evita preparar manualmente todas las cuentas demo para comprobar la integración.

## Validación realizada

| Comprobación | Resultado |
|---|---|
| Django/PostgreSQL | 161 pruebas correctas: 95 anteriores y 66 de identidad |
| Criptografía original | 31 pruebas correctas |
| Cifrado y cola JavaScript | 12 pruebas correctas |
| Migración 3.0.0 → 4.0.0 | Cuentas, versiones, eventos y certificado conservados |

**204 pruebas de suites**, más los recorridos adicionales descritos en `evidencia/LEEME.md`. Entorno: Python 3.12.14, Django 5.2.19, PostgreSQL 17.11 y Node 24.22.1. La prueba de esta entrega en Docker Desktop/Windows queda por realizar en el equipo del usuario; la confirmación previa corresponde a 3.0.0.

Para repetir las suites del servidor:

```powershell
docker compose exec web python -m unittest discover -s tests -v
docker compose exec web python manage.py test gestion.tests --noinput -v 2
```

Con Node instalado:

```powershell
node --test tests_js/vault.test.mjs
```

## Documentos y módulos

| Ruta | Contenido |
|---|---|
| `docs/ACTUALIZAR_SIN_PERDER_DATOS.md` | Actualización desde la carpeta anterior |
| `docs/PRUEBA_PERSONA1.md` | Primer acceso y pruebas manuales de identidad |
| `docs/PERSONA1_IDENTIDAD.md` | Reglas, matriz O1/O15, decisiones y conexión entre módulos |
| `docs/PRUEBA_PERSONA2.md` | Captura, cifrado local y recorrido sin conexión |
| `docs/COBERTURA_Y_LIMITES.md` | Cobertura y pendientes de toda la Parte 2 |
| `gestion/identity.py`, `identity_views.py`, `middleware.py` | Identidad, MFA y sesiones |
| `gestion/capture.py`, `assets/` | Captura y sincronización |
| `gestion/services.py`, `queries.py` | Gestión, revisión y reportes |
| `certificados/` | Firma y verificación originales, sin modificaciones |

## Detener y continuar

```powershell
docker compose stop
docker compose start
```

Después de actualizar código use `docker compose up --build -d`. No use `down -v` para detener: elimina la base de datos. Mantenga copia privada de `.local`, incluida `identity.key`, y respaldos de la base.

El despliegue HTTPS, la conexión con Neon, Secret Manager, el registro de imágenes y la configuración de Dependabot se documentan en la sección **Despliegue en la nube**. Quedan por verificar y documentar los controles cuyo resultado no está confirmado (por ejemplo, cobertura completa de roles, firmas verificadas en la nube, privilegios/RLS según el diseño y digest exacto de la revisión activa). Corresponde al equipo consolidar el informe y la presentación finales. `docs/etapa1`, `etapa2` y `etapa3` son archivos históricos.

Después de actualizar código use `docker compose up --build -d`. No use `down -v` para detener: elimina la base de datos. Mantenga copia privada de `.local`, incluida `identity.key`, y respaldos de la base.

Queda el trabajo de la **persona 5**: despliegue HTTPS, configuración de nube, RLS y privilegios de BD, auditoría independiente y alertas. También corresponde al equipo consolidar el informe y la presentación finales. Esta integración local no completa por sí sola toda la Parte 2. `docs/etapa1`, `etapa2` y `etapa3` son archivos históricos.
