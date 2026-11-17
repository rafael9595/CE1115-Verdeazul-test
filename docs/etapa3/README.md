# Verdeazul · Captura, gestión y certificados

**Versión 3.0.0 — personas 2, 3 y 4 integradas.** Aplicación Django/PostgreSQL para CE-1115. El núcleo de firma de Olman se conserva sin cambios.

## Si ya probó la versión anterior

Consulte primero **`docs/ACTUALIZAR_SIN_PERDER_DATOS.md`**. Conserve `.env`, `.local` y el volumen de PostgreSQL. No vuelva a generar las claves. Mantenga el nombre de proyecto Compose `verdeazul-p3-p4`: identifica el volumen que ya utiliza.

Copie los archivos de código de esta entrega sobre su carpeta anterior, conservando la configuración, y ejecute allí:

```powershell
docker compose up -d db
.\.venv\Scripts\python.exe scripts\respaldar_bd.py
docker compose up --build -d
docker compose logs --tail 40 web
```

El primer comando permite respaldar la base aunque antes hubiera detenido el proyecto. La migración añade campos/tablas y conserva el historial. Se comprobó una actualización desde la entrega 2.0.0 con un certificado emitido: el archivo firmado conservó exactamente su hash, y las cuentas, versiones y eventos permanecieron.

## Lo añadido para la persona 2

- Catálogo de fincas: alta y edición administrativa, número registral único y polígono validado.
- Propietarios: alta, contacto, vínculos de representación con referencia de verificación y finalización de vínculos.
- Asignaciones: técnicos por finca y verificadores independientes por medición; revocación sin borrar historia ni cambiar al autor original.
- Formulario de mediciones con variable, valor, unidad, fecha y metodología. Guardado en borrador y envío a revisión.
- Control de revisión para impedir sobrescrituras desde una pantalla o copia local obsoleta.
- Trabajo sin conexión: página precargada, perfiles cifrados en IndexedDB, frase local, bloqueo, respaldo/importación cifrados y pendientes visibles.
- Sincronización autenticada con UUID, huella del contenido, versión base, fecha de captura declarada y recepción del servidor. Reintentos sin duplicados y conflictos conservados.
- Estado de colas para técnico propio y administración/supervisión, limitado a conteos declarados por los dispositivos.

Se mantienen aprobación/devolución, enmiendas, invalidación, precios, reportes y certificados firmados de las personas 3/4. El flujo completo es: **finca → asignación → captura → envío → revisión → certificado**.

## Instalación nueva en Windows

Solo si todavía no tiene datos/configuración: Docker Desktop con contenedores Linux y Python 3.12/3.13. Abra PowerShell dentro de `verdeazul_integrado`:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\.venv\Scripts\python.exe scripts\setup_local.py
docker compose up --build -d
docker compose logs --tail 40 web
```

Abra **http://localhost:8000**. Credenciales de demostración:

```powershell
Get-Content .local\credenciales.txt
```

Son las mismas cuentas de la entrega anterior si conserva su configuración y base. No se incluyen secretos privados en este ZIP. `iniciar_integrado.ps1` automatiza el arranque conservando la configuración existente.

## Prueba de las tres partes

```powershell
.\.venv\Scripts\python.exe scripts\probar_captura.py
```

Debe indicar `"resultado": "OK"`. Crea registros sintéticos nuevos, de modo que funciona aunque ya haya utilizado las fincas A/B/C o cerrado su período anterior. Comprueba permisos, finca/propietario, asignación, captura, sincronización, conflicto de versión, revisión, firma y descarga. No elimina registros. La salida se guarda en `salida_captura`; para otra ejecución indique `--out salida_captura_2`.

**`docs/PRUEBA_PERSONA2.md`** contiene el recorrido manual y la prueba sin conexión. En **Trabajo sin conexión** hay una comprobación de cifrado/IndexedDB que ejecuta ocho verificaciones dentro de su navegador con datos temporales.

## Validación realizada

| Comprobación | Resultado |
|---|---|
| Criptografía original | 31 pruebas correctas |
| Django/PostgreSQL: gestión + captura | 95 pruebas correctas, incluidas concurrencia y controles negativos |
| JavaScript/Web Crypto en Node 24 | 12 pruebas correctas |
| Flujos HTTP | Gestión/firma anterior y captura → revisión → certificado correctos |
| Migración desde 2.0.0 | Certificado, cuentas, versiones y eventos preservados |

Total: **138 pruebas automatizadas** en las suites, más los recorridos HTTP y la comprobación de migración. Entorno: Python 3.12.14, Django 5.2.19, PostgreSQL 17.11, Node 24.22.1. Registros en `evidencia/`.

Las pruebas JavaScript utilizaron Web Crypto en Node; no sustituyen una ejecución de IndexedDB/Service Worker en un navegador. El entorno no permitió ejecutar Chromium ni descargar su variante headless. La comprobación de ocho casos y el recorrido offline quedan incluidos para ejecutarlos en Windows; Safari/iOS también requiere validación. La ejecución anterior en Windows fue confirmada por el usuario; la **versión 3.0.0** aún necesita esa comprobación. Docker, Cloud Run/Neon y GitHub Actions no se ejecutaron aquí.

Para repetir las suites del servidor:

```powershell
docker compose exec web python -m unittest discover -s tests -v
docker compose exec web python manage.py test gestion.tests --noinput -v 2
```

Si tiene Node instalado, desde la carpeta del proyecto:

```powershell
node --test tests_js/vault.test.mjs
```

## Detener y continuar

```powershell
docker compose stop
docker compose start
```

Se conservan los datos. Después de actualizar código use `up --build -d`, porque `start` reutiliza la imagen existente. No use `down -v` para detener: elimina el volumen de datos.

## Archivos y alcance

| Ruta | Contenido |
|---|---|
| `gestion/capture.py`, `capture_views.py`, `validation.py` | Operaciones, permisos, consultas y validación de persona 2 |
| `templates/capture/`, `assets/forms.js` | Formularios online |
| `assets/campo.html`, `campo.js`, `vault.js`, `sw.js` | Captura local cifrada y sincronización |
| `gestion/services.py`, `queries.py`, `policy.py` | Gestión, revisión, reportes y políticas de persona 3 |
| `certificados/` | Núcleo de firma y verificación original |
| `gestion/migrations/0004*`, `0005*` | Actualización del esquema e invariantes |
| `docs/ACTUALIZAR_SIN_PERDER_DATOS.md` | Actualización de una instalación existente |
| `docs/PRUEBA_PERSONA2.md` | Recorrido de fincas, captura y trabajo sin red |
| `docs/COBERTURA_Y_LIMITES.md` | Cobertura, decisiones y pendientes |
| `docs/INTEGRACION_EQUIPO.md` | Contratos de integración y responsabilidades restantes |

Todavía faltan el módulo completo de identidad de la persona 1 y la infraestructura, RLS, auditoría independiente y alertas de la persona 5. Esta entrega no equivale a completar toda la Parte 2 ni a un despliegue público. `docs/etapa1/` y `docs/etapa2/` conservan documentos históricos; el README actual y los documentos directamente en `docs/` describen esta versión.
