# Guion de Olman · aproximadamente 3 minutos

La demo local sirve para preparar y probar este módulo. Para la presentación final, usar el certificado que haya emitido la aplicación desplegada. Mostrar solo este paquete local no satisface el requisito de sistema público en la nube.

## Preparación

Ejecutar los pasos del README antes de grabar. Tener a mano un certificado válido, su copia alterada y una clave pública oficial conocida. Para ensayar se puede usar `ejemplos/` o generar una carpeta nueva. No mostrar variables de entorno, claves privadas o pantallas con el valor de un secreto.

## 0:00-0:40 · Propósito y punto de emisión

**En pantalla:** la aprobación en el sistema integrado o, durante el ensayo local, `ejemplos/instantanea_demo.json`.

> Mi parte es la firma y verificación de los certificados de carbono. El objetivo es que una persona que recibe un archivo pueda comprobar si su contenido coincide con el que fue firmado. En el sistema, el verificador aprueba una versión y el servicio interno de emisión firma la instantánea. Antes de ese paso, el backend debe comprobar la asignación, la independencia del verificador y que no exista otro certificado vigente para la finca.

Durante un ensayo donde todavía no exista integración, decir “el backend deberá comprobar” y no afirmar que esos controles ya se ejecutaron.

## 0:40-1:10 · Claves y archivo

**En pantalla:** propiedades `algorithm`, `key_id`, `public_key` y `signature` del archivo de ejemplo.

> Usamos Ed25519. La clave privada se mantiene fuera del código y, en el despliegue, se configura en Secret Manager. El certificado lleva la clave pública para verificar la firma. También incluye la finca, la versión de la medición, la aprobación y los responsables mediante sus identificadores. No incluye precio ni datos personales del propietario.

No decir “está en Secret Manager” hasta que realmente exista la configuración; en ese caso se puede cambiar “se configura” por “está configurada”.

## 1:10-1:45 · Archivo válido y alterado

**En pantalla:** ejecutar `verify` sobre `certificado_valido.json` y `certificado_alterado.json` con la misma clave confiable, como indica el README.

> Primero verificamos el original. La firma es válida y la clave coincide con la que conocemos como oficial. Ahora verificamos una copia donde cambiamos el valor de una medición y conservamos la firma anterior. La comprobación falla porque el contenido ya no coincide con lo firmado. No necesitamos la clave privada para hacer esta verificación.

## 1:45-2:15 · Intento con otra clave

**En pantalla:** verificar `certificado_otra_clave.json` con la clave de confianza de la demostración.

> Este tercer archivo tiene una firma matemáticamente correcta, pero fue firmado con otra clave. Por eso lo rechazamos como emisor no confiable. Incluir una clave pública dentro del archivo no basta para demostrar que pertenece a Verdeazul. La comparamos con la clave publicada por un canal oficial independiente.

En la demo incluida la clave es de prueba, no una credencial oficial real de la empresa del caso.

## 2:15-2:45 · Firma y vigencia

**En pantalla:** `current_status: NO_CONSULTADO` y, cuando exista, el estado del certificado en la aplicación.

> También distinguimos la firma de la vigencia. Un certificado puede haber sido invalidado administrativamente y conservar una firma correcta. La firma demuestra integridad; la vigencia se consulta en el sistema. Por eso la invalidación conserva el archivo original y registra un evento, en lugar de editar lo que ya se había firmado.

## 2:45-3:00 · Evidencia y enlace con el resto

**En pantalla:** resultado de las pruebas y, en la aplicación integrada, evento de emisión/descarga.

> El módulo tiene 31 pruebas automatizadas que pasaron en el entorno de preparación. Comprueban el caso válido, alteraciones, claves distintas y entradas inválidas. La integración debe guardar el certificado, la aprobación y el evento en una misma transacción para evitar resultados parciales.

Cuando la integración esté probada, sustituir la última frase por una descripción de la transacción y la evidencia reales.

## Respuestas para defender el módulo

| Pregunta | Respuesta |
|---|---|
| ¿La firma cifra el certificado? | No. El contenido permanece legible; los permisos de descarga protegen el acceso |
| ¿Se necesita la clave privada para verificar? | No, solo la pública; para autenticar al emisor se necesita además confiar en esa pública |
| ¿Por qué SHA-256 y Ed25519? | SHA-256 identifica la clave pública; Ed25519 firma y verifica el mensaje |
| ¿Puede el administrador firmar directamente? | La matriz asigna GE al servicio interno. El administrador no tiene aprobación técnica por su rol |
| ¿Qué pasa si se cambia un espacio del JSON? | El contenido se serializa de forma determinista; la indentación no altera el contenido lógico. Cambiar un dato sí se detecta |
| ¿Qué pasa si alguien firma con su propia clave? | La firma puede ser correcta, pero la lista de confianza rechaza al emisor desconocido |
| ¿Esto prueba que la cantidad de carbono es real? | No. La veracidad científica depende de medición, metodología y revisión |
| ¿Cómo se comprueba que no haya dos certificados vigentes? | En PostgreSQL, con transacción, bloqueo de finca e índice único parcial; no mediante criptografía |
| ¿Por qué no se entregó un PDF firmado? | Se eligió JSON verificable; la consigna no obliga un formato. Un PDF requeriría su propia firma o presentarse como vista del original |
