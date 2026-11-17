# Verdeazul · Parte 2 · Módulo de certificados

**Responsable propuesto: Olman. Versión: 1.0.0.**

Módulo funcional de firma y verificación de certificados para integrarlo en la aplicación Django de la Parte 1. Incluye código, pruebas, demostración, reparto entre cinco integrantes y guía de integración. Se eligió este módulo porque tiene un alcance definido y permite demostrar un certificado correcto y uno alterado.

**Estado real:** se ejecutaron 31 pruebas en Python 3.12.14 con cryptography 50.0.0 y pasaron. Los archivos de `ejemplos/` provienen de una ejecución real con datos sintéticos. La clave privada de esa demostración nunca se escribió a disco. Este paquete no es el sistema completo ni está desplegado en Cloud Run. No incluye cuentas de usuarios ni una conexión a Neon. Docker y la ejecución en Python 3.13 quedan por comprobar en el entorno del equipo.

## 1. Empezar en Windows / PowerShell

Descomprima el ZIP. Abra PowerShell dentro de la carpeta `verdeazul_certificados` que contiene este README.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m certificados demo --out demo_salida
```

Si solo tiene Python 3.12, cambie únicamente el primer comando por `py -3.12 -m venv .venv`. No es necesario activar el entorno virtual ni cambiar permanentemente la política de PowerShell. La primera instalación requiere internet para descargar la dependencia.

Resultado esperado de la demostración:

```text
valido: VALIDO
alterado: FIRMA_INVALIDA
otra_clave: EMISOR_NO_CONFIABLE
sin_clave_oficial: SIN_ANCLA_DE_CONFIANZA
```

Los mensajes completos explican cada resultado. `demo_salida/` contiene tres certificados, una clave pública, la instantánea de ejemplo y los resultados. Para repetir sin sobrescribir evidencia, cambie `--out demo_salida_2`.

También se incluye `iniciar_demo.ps1`, que ejecuta instalación, pruebas y demostración. Si Windows impide ejecutar scripts, utilice los cuatro comandos anteriores.

## 2. Comprobar los archivos uno por uno

```powershell
.\.venv\Scripts\python.exe -m certificados verify .\demo_salida\certificado_valido.json --trusted-key .\demo_salida\clave_publica_demo.pem
$LASTEXITCODE

.\.venv\Scripts\python.exe -m certificados verify .\demo_salida\certificado_alterado.json --trusted-key .\demo_salida\clave_publica_demo.pem
$LASTEXITCODE

.\.venv\Scripts\python.exe -m certificados verify .\demo_salida\certificado_otra_clave.json --trusted-key .\demo_salida\clave_publica_demo.pem
$LASTEXITCODE
```

Los códigos esperados son **0, 2 y 3**, respectivamente. Un resultado negativo en los dos últimos casos demuestra el comportamiento esperado; no es un fallo de instalación. La segunda copia conserva la firma del original pero cambia `125.50` por `9999.00` en una medición. La tercera está firmada correctamente con una clave diferente, que no pertenece a la lista de confianza de la prueba.

Para usar directamente las muestras incluidas, reemplace `demo_salida` por `ejemplos`.

| Código de salida | Significado |
|---|---|
| 0 | Firma correcta y clave reconocida; o comando de creación completado |
| 1 | Error de archivo, configuración o generación |
| 2 | Firma o formato inválido |
| 3 | Firma correcta, pero el emisor no se autentica con la lista externa |

El campo `current_status: NO_CONSULTADO` siempre aparece porque esta herramienta no consulta la vigencia comercial en la base de datos.

## 3. Qué está implementado

- Firma Ed25519 del contenido completo, del algoritmo, de la versión de formato y de la clave pública.
- Clave pública incrustada y huella SHA-256 para identificarla.
- Verificación sin clave privada ni conexión a la base de datos.
- Comprobación independiente de confianza en el emisor mediante una o varias claves públicas conocidas.
- Validación estricta del formato, tamaño máximo de 1 MiB, rechazo de propiedades duplicadas y campos adicionales.
- Exclusión estructural de datos personales del dueño, precio, credenciales y sesiones.
- Lectura de la clave privada desde una variable de entorno o archivo externo; nunca hay una clave fija en el código.
- Pruebas automáticas, CLI, Dockerfile de la herramienta y configuración de Dependabot/CI.

Una firma válida demuestra que el contenido corresponde a la clave que firmó. Para atribuir esa clave a Verdeazul, la clave pública oficial debe obtenerse de un canal independiente y confiable. La clave incluida en un archivo recibido no se vuelve confiable por sí sola.

**El certificado firmado es un archivo JSON, no una firma manuscrita ni un PDF PAdES.** La consigna permite un archivo verificable y no fija un formato. Si después se genera una vista PDF, debe identificarse como representación del JSON firmado; no se puede afirmar que sus bytes estén firmados con este módulo.

## 4. Archivos importantes

| Archivo | Uso |
|---|---|
| `certificados/core.py` | Validación, firma, lectura de claves y verificación |
| `certificados/cli.py` | Comandos `demo`, `keys`, `sign`, `verify` y `fingerprint` |
| `certificados/demo.py` | Datos sintéticos y generación de los casos de demostración |
| `tests/test_certificados.py` | 31 pruebas, incluyendo alteración y suplantación de clave |
| `docs/REPARTO_5_PERSONAS.md` | Reparto, cobertura de objetos y calendario propuesto |
| `docs/INTEGRACION_DJANGO.md` | Contrato con el backend y condiciones C3, C8 y C9 |
| `docs/SECRETOS_Y_DESPLIEGUE.md` | Clave privada, Secret Manager y responsabilidades de despliegue |
| `docs/FORMATO_Y_DECISIONES.md` | Esquema, serialización y límites |
| `docs/GUION_OLMAN.md` | Secuencia para la demostración y explicación oral |
| `docs/APORTE_INFORME.md` | Texto de este módulo y tabla de evidencia, sin afirmar despliegue |
| `evidencia/pruebas.txt` | Salida de las pruebas ejecutadas durante la preparación |
| `ejemplos/` | Certificados sintéticos y resultados verificables |

## 5. Llamarlo desde Python / Django

Copie `certificados/` al repositorio del backend e incorpore la dependencia de `requirements.txt`. También puede instalar este proyecto con `python -m pip install .` en un entorno con acceso al repositorio de paquetes.

```python
from certificados import (
    certificate_bytes,
    issue_certificate,
    load_private_key_from_environment,
)

# Esta instantánea debe construirse con los registros autorizados de PostgreSQL.
# No se toma directamente de request.POST ni del JSON enviado por el navegador.
key = load_private_key_from_environment()
document = issue_certificate(instantanea_autorizada, key)
archivo = certificate_bytes(document)
```

Este fragmento es el punto de llamada, no una vista ni una implementación completa de autorización. El servicio de negocio debe conservar `archivo` en la misma transacción que la aprobación y su evento de auditoría. El flujo preciso está en `docs/INTEGRACION_DJANGO.md`.

## 6. Qué falta para la entrega grupal

La consigna exige el sistema público por HTTPS en Cloud Run, PostgreSQL en Neon, todos los permisos de la matriz, credenciales de prueba para los ocho roles, auditoría, imágenes en Artifact Registry, Secret Manager, Dependabot activo, informe de 6 a 10 páginas y presentación de 15 minutos el 19 de noviembre.

El paquete resuelve la parte criptográfica y su demostración local. Quedan por integrar la emisión con aprobación real, la persistencia, los permisos de descarga, la invalidación y los registros de auditoría. También quedan por desplegar y verificar los recursos de nube. Los archivos de configuración no demuestran por sí solos que esos servicios estén activos.

## 7. Fuentes de implementación

- Consigna adjunta: `Proyecto_Parte2_Implementacion_CE1115.pdf`, secciones 2.2, 2.3, 3, 5 y 6.
- Diseño adjunto: `P1_Matriz_grupo3.tex`, O8, C3, C8 y C9; `P1_Arquitectura_grupo3.tex`, monolito modular y emisión transaccional; `P1_Politicas_grupo3.tex`, proyecciones y conservación.
- API oficial Ed25519: https://cryptography.io/en/50.0.0/hazmat/primitives/asymmetric/ed25519/
- Transacciones Django: https://docs.djangoproject.com/en/5.2/topics/db/transactions/
- Secretos en Cloud Run: https://docs.cloud.google.com/run/docs/configuring/services/secrets

Consulta de documentación técnica: 10 de noviembre de 2026. La versión fijada de cryptography es la utilizada en las pruebas; no implica que todas las dependencias del sistema grupal hayan sido auditadas.
