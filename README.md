# Verdeazul · Identidad, captura, gestión y certificados

**Versión 4.0.0 — personas 1, 2, 3 y 4 integradas.** Aplicación Django/PostgreSQL para CE-1115. Conserva el núcleo de firma y verificación de Olman, los certificados históricos y la captura sin conexión.

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

Queda el trabajo de la **persona 5**: despliegue HTTPS, configuración de nube, RLS y privilegios de BD, auditoría independiente y alertas. También corresponde al equipo consolidar el informe y la presentación finales. Esta integración local no completa por sí sola toda la Parte 2. `docs/etapa1`, `etapa2` y `etapa3` son archivos históricos.
