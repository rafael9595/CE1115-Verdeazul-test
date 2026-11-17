# Verdeazul · Gestión y certificados integrados

Entrega de las personas 3 y 4 para CE-1115. Incluye una aplicación Django con PostgreSQL y el módulo de firma de Olman. La carpeta `certificados/` conserva el código de la entrega anterior; ahora el backend lo llama al aprobar una medición.

## Qué funciona

- Aprobación o devolución por un verificador asignado e independiente de todos los autores/correctores de la cadena.
- Persistencia conjunta de aprobación, firma, certificado y eventos: si falla la firma o el registro del evento, se revierte la operación.
- Un certificado vigente por finca, incluso entre períodos; reintentos sin duplicar documentos y pruebas de concurrencia.
- Períodos, correcciones mediante versiones nuevas, enmiendas autorizadas e invalidación con motivo e historial.
- Precios y reportes filtrados por rol, finca propia, asignación e historial; el auditor recibe el reporte de su encargo vigente, sin precio ni datos del propietario.
- Descarga del archivo firmado original, verificación de firma y clave de confianza, y detección de alteraciones.
- Interfaz de prueba, acceso con cuentas locales, Argon2, sesiones, CSRF y bitácora de operaciones.

Esto cubre el módulo de la persona 3 y su conexión con la persona 4. No equivale a completar toda la Parte 2. Los pendientes compartidos están en `docs/COBERTURA_Y_LIMITES.md` y `docs/INTEGRACION_EQUIPO.md`.

## Arranque en Windows

Requisitos: Docker Desktop iniciado con contenedores Linux y Python 3.12 o 3.13 instalado con el lanzador `py`. Extraiga el ZIP y abra PowerShell **dentro de `verdeazul_integrado`**, donde están `compose.yaml` y este README.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\.venv\Scripts\python.exe scripts\setup_local.py
docker compose up --build -d
docker compose logs --tail 40 web
```

Abra **http://localhost:8000**. Los usuarios y la contraseña aleatoria se crean en **`.local\credenciales.txt`**; puede leerla con:

```powershell
Get-Content .local\credenciales.txt
```

Cada copia tiene sus propias claves y contraseñas. No se incluyen claves privadas ni contraseñas en el ZIP. El archivo `.env` y la carpeta `.local` se conservan al reiniciar. No los suba a Git ni los comparta.

Como alternativa, `iniciar_integrado.ps1` ejecuta estos pasos y conserva la configuración existente. Si PowerShell bloquea scripts, utilice los comandos anteriores; no es necesario cambiar la política del sistema.

## Primera prueba integrada

Con una base recién creada, ejecute una vez:

```powershell
.\.venv\Scripts\python.exe scripts\probar_integracion.py
```

Debe finalizar con `"resultado": "OK"`. Comprueba rechazo al técnico, aprobación del verificador, descarga, firma, alteración, reintento y auditoría sobre la finca A. También recorre devolución, corrección, envío y aprobación mediante los formularios HTTP sobre la finca B. No borra datos: si esas fincas ya fueron procesadas, avisa y se detiene.

La carpeta `salida_prueba` contiene el original, la copia alterada, la clave pública y el resultado. En **Verificar archivo**, cargue ambos JSON: el original debe indicar `VALIDO` y el alterado `FIRMA_INVALIDA`.

Siga `docs/PRUEBA_PASO_A_PASO.md` para comprobar las pantallas, los roles y la enmienda con período cerrado.

## Pruebas automatizadas

```powershell
docker compose exec web python -m unittest discover -s tests -v
docker compose exec web python manage.py test gestion.tests --noinput -v 2
```

La suite Django utiliza una base temporal `test_verdeazul`; no reinicia la base de demostración. Resultado obtenido en el entorno de desarrollo: **31 pruebas criptográficas y 51 de gestión correctas**, con PostgreSQL 17.11 real, Python 3.12.14 y Django 5.2.19. Se ejecutó además la prueba HTTP contra Gunicorn con dos procesos. Los registros están en `evidencia/`.

Docker Desktop, Windows, el contenedor Python 3.13 y el flujo de GitHub Actions quedan por ejecutar en sus entornos respectivos; no se presentan como pruebas ya realizadas. El renderizado de las plantillas y los manejadores de formularios se comprobaron con Django/HTTP; no se completó una inspección visual en navegador porque el entorno de ejecución bloqueó su inicio.

## Detener y continuar después

```powershell
docker compose stop
docker compose start
```

El volumen de PostgreSQL conserva los datos. No use `down -v` para detener: elimina ese volumen. Si cambió código, reconstruya con `docker compose up --build -d`.

## Archivos principales

| Archivo o carpeta | Función |
|---|---|
| `gestion/models.py`, `gestion/migrations/` | Entidades, restricciones, índices y protección del historial |
| `gestion/services.py` | Operaciones transaccionales y enlace con la firma |
| `gestion/policy.py`, `gestion/queries.py` | Alcance por persona/rol y reportes filtrados |
| `gestion/views.py`, `templates/` | Rutas HTTP y pantallas de prueba |
| `certificados/` | Firma Ed25519, formato y verificador original |
| `gestion/tests/`, `tests/` | Pruebas de gestión y criptografía |
| `docs/PRUEBA_PASO_A_PASO.md` | Recorrido de prueba en Windows |
| `docs/INTEGRACION_EQUIPO.md` | Contratos para conectar el trabajo del equipo |
| `docs/COBERTURA_Y_LIMITES.md` | Relación con Parte 1/Parte 2 y pendientes |
| `docs/APORTE_INFORME.md` | Explicación del aporte y resultados obtenidos |
| `docs/etapa1/` | Documentación histórica de la entrega del módulo aislado |

`iniciar_demo.ps1` mantiene la demostración criptográfica aislada anterior. Para la aplicación con base de datos use `iniciar_integrado.ps1` o los comandos de este README. Los certificados de `ejemplos/` y `ejemplos_integracion/` son evidencia histórica sintética con sus propias claves públicas; no corresponden a las claves nuevas generadas en su computadora.
