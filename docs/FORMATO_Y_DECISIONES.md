# Formato y decisiones del módulo

Este documento describe exclusivamente el núcleo `certificados/`, conservado de la entrega anterior. La aplicación Django que ahora lo utiliza se documenta en `README.md` y `docs/COBERTURA_Y_LIMITES.md`.

## Qué se firma

El sobre tiene seis propiedades obligatorias: `format`, `algorithm`, `key_id`, `public_key`, `payload` y `signature`. La firma se calcula sobre todas excepto `signature`, precedidas por un separador de dominio fijo que identifica certificados Verdeazul versión 1. La verificación reconstruye exactamente ese mensaje.

Se utiliza Ed25519 mediante la biblioteca `cryptography`; no se implementa la matemática criptográfica del algoritmo. La clave pública cruda tiene 32 bytes y la firma 64 bytes, representados en Base64 estándar. `key_id` es la huella SHA-256 de los 32 bytes públicos. El hash identifica la clave; por sí solo no reemplaza la firma.

## Instantánea de negocio

| Sección | Contenido y origen esperado |
|---|---|
| Identificación | UUID generado por servidor, emisor fijo y fecha UTC de emisión |
| Finca | UUID, número registral, nombre, área, país y polígono histórico |
| Medición | UUID de medición, versión y período; fecha de campo, metodología y valores/unidades |
| Aprobación | UUID de decisión, identidad laboral del verificador y fecha UTC |
| Participantes | Identificadores de las personas autoras/correctoras de toda la cadena |
| Antecedente | UUID del certificado reemplazado o `null` |

Los campos siguen el diccionario propuesto en la Parte 1. `carbono_reportado` y `tCO2e` de la demostración son datos sintéticos para probar la firma; no son una metodología ni reglas científicas de certificación aprobadas. El área y el polígono de prueba tampoco acreditan un levantamiento real.

Los datos personales del propietario y el precio no forman parte del formato. El nombre de finca y la metodología deben provenir de campos de negocio validados: la lista de propiedades no detecta que alguien haya escrito deliberadamente datos personales dentro de un campo de texto permitido.

## Serialización determinista

- JSON UTF-8 sin BOM, propiedades ordenadas, sin espacios estructurales.
- Solo objetos, listas, cadenas y `null`. Los decimales y coordenadas se escriben como cadenas, por ejemplo `"125.50"`.
- UUID en minúsculas con guiones; fechas de emisión/revisión en UTC `AAAA-MM-DDTHH:MM:SSZ`.
- Se rechazan propiedades repetidas, campos desconocidos, números JSON, booleanos, NaN, infinito, UTF-8 inválido y caracteres de control.
- Máximo de 1 MiB y límites de profundidad, cantidad y longitud.
- El orden de listas sí forma parte del contenido. Un cambio de `"125.50"` a `"125.500"` también cambia el contenido firmado.
- La representación escapada de un carácter y ese mismo carácter UTF-8 representan el mismo texto. Cambiar indentación u orden de propiedades no altera el contenido lógico ni invalida la firma.

Es un formato específico del proyecto, no una implementación de JWS, JCS/RFC 8785 ni de firma PDF. No añadir propiedades al sobre o al contenido sin versionar el formato y actualizar el verificador.

## Tres resultados diferentes

1. **Integridad:** Ed25519 comprueba el mensaje y la firma con la clave incluida.
2. **Confianza del emisor:** la huella de la clave incluida debe coincidir con una clave oficial obtenida independientemente. Un atacante puede generar su propio par y firmar un documento que diga Verdeazul; la lista externa evita aceptarlo como emisor reconocido.
3. **Vigencia:** un estado de negocio que puede cambiar por invalidación. No se puede inferir del resultado criptográfico offline. La herramienta siempre indica `NO_CONSULTADO` para este punto.

Una firma no prueba que los datos de campo sean verdaderos, que el firmante conserve control de su clave ni que una clave comprometida deba seguir aceptándose. La revisión, la custodia y la política de confianza completan el sistema.

## Límites deliberados

- El módulo valida rangos y cierre básico de un anillo WGS84, pero no autointersecciones, área, pertenencia a Costa Rica ni concordancia catastral. El backend debe validar esa parte de C9 con biblioteca/fuente cartográfica identificadas.
- La lista de participantes se contrasta estructuralmente con el verificador, pero solo PostgreSQL aporta el historial confiable de autores/correctores.
- El núcleo no ofrece endpoint público de firma ni administra usuarios. En esta entrega, Django comprueba permisos y vigencia, persiste los documentos y llama al núcleo desde la operación de aprobación; el verificador de archivos continúa siendo independiente de esos estados.
- La identidad de emisión es una responsabilidad interna del monolito. El módulo no aísla la clave frente a un compromiso completo del proceso Django.
- Ed25519 se utiliza para firma, no para cifrado. El archivo conserva contenido legible y debe descargarse aplicando permisos de la matriz.
- No se implementan sellado de tiempo externo, PKI de autoridad certificadora ni validación jurídica de firma digital. La fecha está firmada, pero la establece el servidor.

## Rotación

Una nueva emisión puede usar una nueva versión de clave. Conservar las claves públicas históricas para verificar documentos anteriores. El comando `verify` admite varias opciones `--trusted-key`. No volver a firmar ni sustituir archivos históricos cuando rota la clave.

Si una clave se compromete, retirar su confianza según la política de incidente; mantener su material público para investigación, sin seguir mostrándola como confiable. Una firma antigua con esa clave puede seguir siendo matemáticamente correcta. La lista de confianza no contiene secretos, pero su integridad debe protegerse y su distribución debe ser auténtica.
