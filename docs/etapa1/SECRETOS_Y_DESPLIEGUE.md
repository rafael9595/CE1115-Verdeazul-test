# Claves y preparación del despliegue

Esta guía corresponde al módulo de certificados. No se han creado recursos de Google Cloud ni de Neon, ni se ha ejecutado el Dockerfile. Los pasos se realizan sobre el proyecto y servicio del equipo. Nunca colocar una clave privada en GitHub, en el informe, en una captura, en el Dockerfile ni en el ZIP de entrega.

## Claves para desarrollo

La demostración genera una clave efímera en memoria. Para integrar una clave propia de desarrollo, cree una carpeta fuera del repositorio, con acceso limitado a su cuenta:

```powershell
$PrivateDir = Join-Path $env:USERPROFILE 'VerdeazulSecrets'
New-Item -ItemType Directory -Force $PrivateDir | Out-Null

.\.venv\Scripts\python.exe -m certificados keys --private-out "$PrivateDir\firma_desarrollo.pem" --public-out "$PrivateDir\publica_desarrollo.pem"

$env:VERDEAZUL_SIGNING_PRIVATE_KEY_FILE = "$PrivateDir\firma_desarrollo.pem"
.\.venv\Scripts\python.exe -m certificados sign .\ejemplos\instantanea_demo.json --out .\certificado_prueba.json
.\.venv\Scripts\python.exe -m certificados verify .\certificado_prueba.json --trusted-key "$PrivateDir\publica_desarrollo.pem"

Remove-Item Env:\VERDEAZUL_SIGNING_PRIVATE_KEY_FILE
```

El generador no sobrescribe claves. La privada se escribe en PEM PKCS8 sin contraseña para que el proceso pueda cargarla sin interacción. En sistemas POSIX se crea con permisos 0600. En Windows se heredan las ACL de la carpeta: compruebe en sus propiedades de seguridad que otras cuentas no puedan leerla. En producción, la protección y el acceso se gestionan con Secret Manager e IAM.

La clave pública puede distribuirse; la privada no. La privada de desarrollo no debe convertirse automáticamente en clave de producción.

## Variables que reconoce el código

| Variable | Uso |
|---|---|
| `VERDEAZUL_SIGNING_PRIVATE_KEY_PEM` | Contenido PEM inyectado por Secret Manager en Cloud Run |
| `VERDEAZUL_SIGNING_PRIVATE_KEY_FILE` | Ruta de archivo montado o clave local fuera del repositorio |

Configure exactamente una de ellas. Si faltan ambas o existen ambas, la emisión falla explícitamente. Los mensajes no imprimen el secreto. No incluir secretos reales en archivos `.env.example`; este paquete no necesita un `.env`.

## Configuración en Secret Manager y Cloud Run

1. Persona 5 crea un secreto exclusivo para la clave de firma y una primera versión con el PEM de producción.
2. Asigna a la cuenta de servicio usada por el backend el permiso de lectura del secreto, limitado a ese secreto. La documentación de Cloud Run utiliza `roles/secretmanager.secretAccessor` para la identidad del servicio.
3. Configura `VERDEAZUL_SIGNING_PRIVATE_KEY_PEM` como referencia al secreto en el servicio Django. Fija un número de versión, por ejemplo `1`, para asociar una revisión concreta a una clave concreta.
4. La cuenta de usuarios humanos de la aplicación no recibe acceso al secreto. La interfaz no muestra ni exporta la privada.
5. Obtiene la clave pública correspondiente y publica su huella por un canal oficial controlado. La lista de confianza del verificador se configura independientemente de los archivos recibidos.
6. Realiza una emisión autorizada y verifica el archivo descargado con la clave pública de esa versión. Conserva la evidencia sin mostrar contenido secreto.

Esquema de comando para actualizar **un servicio Django que ya existe**:

```powershell
gcloud run services update NOMBRE_SERVICIO --project ID_PROYECTO --region REGION --update-secrets VERDEAZUL_SIGNING_PRIVATE_KEY_PEM=NOMBRE_SECRETO:1
```

Los nombres en mayúsculas deben sustituirse por los recursos reales. El comando no crea Neon, Artifact Registry ni el resto del sistema. No ejecutarlo sobre un proyecto distinto al del equipo.

La Parte 1 proponía montar secretos como archivos. Usar variables inyectadas por Secret Manager cumple la instrucción específica de la Parte 2 y debe anotarse como cambio de mecanismo. La aplicación continúa leyendo el secreto al ejecutar, fuera del código y de la imagen.

## Docker y versionado

El Dockerfile incluido empaqueta **la herramienta de línea de comandos**, ejecutada con UID 10001. Sirve para probar la CLI y como referencia de mínimo privilegio; no escucha un puerto y por tanto no se despliega tal cual como servicio HTTP de Cloud Run.

Para el despliegue final, copiar `certificados/` e instalar su dependencia en la imagen del backend Django. Esa imagen sí debe atender el puerto que Cloud Run proporciona. Publicarla en Artifact Registry con etiqueta de versión o hash del commit, por ejemplo `backend:v1.0.0`, y registrar también el digest. No usar solo `latest`.

La imagen base declarada usa la línea Python 3.13. Antes de liberar la imagen final, resolver y fijar su digest y comprobar vulnerabilidades; no se ha ejecutado aquí ese análisis. El código está probado en Python 3.12 y la CI propuesta cubre 3.12/3.13 cuando se ejecute en GitHub.

## Dependabot y repositorio

Se incluye `.github/dependabot.yml` para Python, Docker y GitHub Actions, más un workflow de pruebas. Copiar esos archivos al repositorio común y ajustar `directory` si el módulo queda en una subcarpeta. Habilitar alertas de Dependabot en la configuración del repositorio y comprobar su estado real. Si aparece una alerta durante el proyecto, atender y documentar al menos una según la consigna. No inventar una alerta o una corrección si no ocurrió.

## Desviaciones que debe registrar el informe grupal

| Diseño de Parte 1 | Exigencia/decisión para Parte 2 | Implicación que debe explicarse |
|---|---|---|
| Máquinas virtuales y dos nodos de datos gestionados por el equipo | Cloud Run y PostgreSQL en Neon | Cambia quién opera la infraestructura; comprobar garantías reales del plan, sin prometer la réplica síncrona y RPO=0 del diseño original |
| Nginx como entrada HTTPS | Cloud Run termina TLS | Decidir y justificar qué funciones conserva el proxy y dónde se aplican límites, hosts y cabeceras. Si se elimina Nginx, declararlo expresamente |
| Secretos montados como archivos | Secret Manager inyectado por entorno, según consigna | Cambia el mecanismo de entrega; conservar mínimo privilegio y exclusión del repositorio |
| Certificado e instantánea sin formato criptográfico concreto | JSON versionado firmado con Ed25519 | Verificación independiente del sistema; la vista PDF, si existe, no es por sí misma el original firmado |

No suponer que Neon gratuito incluye cualquier período de recuperación, restricción por IP, región o garantía de continuidad. Persona 5 debe documentar las opciones realmente disponibles y elegidas en el proyecto, con evidencia de configuración. Las tarifas, cuotas y condiciones del plan deben comprobarse al configurar los servicios.
