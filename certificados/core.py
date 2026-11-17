"""Formato VA-CARBON-1: Ed25519 sobre JSON restringido y determinista.

No implementa autenticación de usuarios, C3/C9, base de datos ni estado de vigencia.
Solo el servicio interno de emisión puede llamar issue_certificate después de
comprobar las reglas de negocio con datos de PostgreSQL.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable
from uuid import UUID

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

FORMAT = "VA-CARBON-1"
ISSUER = "Verdeazul Carbono S.A."
MAX_FILE_BYTES = 1_048_576
DOMAIN = b"VERDEAZUL-CARBON-CERTIFICATE-V1\x00"
DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?\Z")
FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")


class CertificateError(ValueError):
    """Entrada o configuración inválida; el mensaje no contiene secretos."""


@dataclass(frozen=True)
class VerificationResult:
    signature_valid: bool
    issuer_trusted: bool | None
    code: str
    message: str
    key_id: str | None = None
    certificate_id: str | None = None
    current_status: str = "NO_CONSULTADO"

    @property
    def accepted(self) -> bool:
        return self.signature_valid and self.issuer_trusted is True


def _reject_number(value: str):
    raise CertificateError("Los números se representan como cadenas decimales.")


def _unique_object(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise CertificateError("El JSON contiene una propiedad duplicada.")
        output[key] = value
    return output


def _tree(value, depth=0):
    if depth > 12:
        raise CertificateError("El JSON excede la profundidad permitida.")
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise CertificateError("Texto Unicode inválido.") from exc
        if len(value) > 20_000 or any(ord(c) < 32 for c in value):
            raise CertificateError("Texto demasiado largo o con controles no admitidos.")
    elif value is None:
        return
    elif isinstance(value, dict):
        if len(value) > 100:
            raise CertificateError("Demasiadas propiedades.")
        for key, item in value.items():
            if not isinstance(key, str):
                raise CertificateError("Las propiedades deben ser cadenas.")
            _tree(key, depth + 1)
            _tree(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 500:
            raise CertificateError("Demasiados elementos.")
        for item in value:
            _tree(item, depth + 1)
    else:
        raise CertificateError("Solo se admiten objetos, listas, cadenas y null.")


def canonical_json(value) -> bytes:
    _tree(value)
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise CertificateError("JSON inválido.") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise CertificateError("El documento excede 1 MiB.")
    return raw


def parse_json(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or len(raw) > MAX_FILE_BYTES:
        raise CertificateError("Se requiere un archivo de hasta 1 MiB.")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_float=_reject_number, parse_int=_reject_number,
                           parse_constant=_reject_number)
        _tree(value)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, CertificateError):
            raise
        raise CertificateError("El archivo no contiene JSON válido.") from exc
    if not isinstance(value, dict):
        raise CertificateError("La raíz del archivo debe ser un objeto.")
    return value


def _fields(obj, names: set[str], label: str):
    if not isinstance(obj, dict) or set(obj) != names:
        raise CertificateError(f"Campos incompletos o no permitidos en {label}.")


def _text(value, label, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise CertificateError(f"Texto inválido en {label}.")


def _uuid(value, label):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise CertificateError(f"UUID inválido en {label}.") from exc


def _decimal(value, label):
    if not isinstance(value, str) or not DECIMAL.fullmatch(value):
        raise CertificateError(f"Decimal inválido en {label}; utilice una cadena.")
    return Decimal(value)


def _utc(value, label):
    if not isinstance(value, str):
        raise CertificateError(f"Fecha UTC inválida en {label}.")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError
        return dt
    except ValueError as exc:
        raise CertificateError(f"Fecha UTC inválida en {label}.") from exc


def validate_payload(payload: dict):
    canonical_json(payload)
    _fields(payload, {"certificate_id", "issuer", "issued_at", "farm", "measurement",
                      "approval", "technical_participants", "predecessor_certificate_id"},
            "certificado")
    _uuid(payload["certificate_id"], "certificate_id")
    if payload["issuer"] != ISSUER:
        raise CertificateError("Emisor no admitido en este formato.")
    issued = _utc(payload["issued_at"], "issued_at")
    farm = payload["farm"]
    _fields(farm, {"id", "registry_number", "name", "area_ha", "country_code",
                   "polygon_wgs84"}, "finca")
    _uuid(farm["id"], "farm.id")
    _text(farm["registry_number"], "registry_number", 80)
    _text(farm["name"], "name", 160)
    if _decimal(farm["area_ha"], "area_ha") <= 0:
        raise CertificateError("El área debe ser positiva.")
    if farm["country_code"] != "CR":
        raise CertificateError("Esta versión académica admite fincas de Costa Rica.")
    polygon = farm["polygon_wgs84"]
    if not isinstance(polygon, list) or not 4 <= len(polygon) <= 500:
        raise CertificateError("Se requiere un anillo de 4 a 500 coordenadas.")
    points = []
    for pair in polygon:
        if not isinstance(pair, list) or len(pair) != 2:
            raise CertificateError("Cada coordenada es [longitud, latitud].")
        lon, lat = (_decimal(pair[0], "longitud"), _decimal(pair[1], "latitud"))
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise CertificateError("Coordenadas fuera de rango WGS84.")
        points.append((lon, lat))
    if points[0] != points[-1] or len(set(points[:-1])) < 3:
        raise CertificateError("El anillo debe cerrar y tener tres vértices distintos.")
    # No se sustituye la comprobación topológica/geográfica C9 del backend.
    measurement = payload["measurement"]
    _fields(measurement, {"id", "version_id", "period_id", "measured_at",
                          "methodology", "values"}, "medición")
    for name in ("id", "version_id", "period_id"):
        _uuid(measurement[name], f"measurement.{name}")
    try:
        measured = date.fromisoformat(measurement["measured_at"])
        if measured.isoformat() != measurement["measured_at"]:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise CertificateError("Fecha de medición inválida.") from exc
    _text(measurement["methodology"], "methodology", 300)
    values = measurement["values"]
    if not isinstance(values, list) or not 1 <= len(values) <= 50:
        raise CertificateError("Se requieren de 1 a 50 valores de medición.")
    names = set()
    for item in values:
        _fields(item, {"name", "value", "unit"}, "valor de medición")
        _text(item["name"], "name", 80)
        _text(item["unit"], "unit", 40)
        _decimal(item["value"], "value")
        if item["name"] in names:
            raise CertificateError("Nombre de medición duplicado.")
        names.add(item["name"])
    approval = payload["approval"]
    _fields(approval, {"id", "verifier_person_id", "decided_at"}, "aprobación")
    _uuid(approval["id"], "approval.id")
    _uuid(approval["verifier_person_id"], "verifier_person_id")
    decided = _utc(approval["decided_at"], "decided_at")
    # measured_at es fecha civil de campo; no se compara con fecha UTC de revisión.
    if decided > issued:
        raise CertificateError("La aprobación no puede ser posterior a la emisión.")
    participants = payload["technical_participants"]
    if not isinstance(participants, list) or not 1 <= len(participants) <= 100:
        raise CertificateError("Se requieren participantes técnicos de la cadena.")
    for person in participants:
        _uuid(person, "technical_participants")
    if len(set(participants)) != len(participants):
        raise CertificateError("Participante técnico duplicado.")
    if approval["verifier_person_id"] in participants:
        raise CertificateError("El verificador figura entre los autores/correctores.")
    predecessor = payload["predecessor_certificate_id"]
    if predecessor is not None:
        _uuid(predecessor, "predecessor_certificate_id")
        if predecessor == payload["certificate_id"]:
            raise CertificateError("Un certificado no puede ser su propio antecedente.")


def public_key_bytes(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def fingerprint(key: Ed25519PublicKey) -> str:
    return "sha256:" + hashlib.sha256(public_key_bytes(key)).hexdigest()


def load_private_key(raw: bytes) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(raw, password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise CertificateError("La clave privada no es un PEM PKCS8 Ed25519 válido.") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise CertificateError("La clave privada debe ser Ed25519.")
    return key


def load_public_key(raw: bytes) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(raw)
    except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise CertificateError("La clave pública no es un PEM Ed25519 válido.") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise CertificateError("La clave pública debe ser Ed25519.")
    return key


def read_limited(path: Path, limit=MAX_FILE_BYTES) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise CertificateError("El archivo excede el tamaño permitido.")
    return raw


def load_private_key_from_environment() -> Ed25519PrivateKey:
    """Secret Manager inyecta PEM; la ruta alternativa sirve para montaje/local."""
    pem = os.environ.get("VERDEAZUL_SIGNING_PRIVATE_KEY_PEM")
    path = os.environ.get("VERDEAZUL_SIGNING_PRIVATE_KEY_FILE")
    if bool(pem) == bool(path):
        raise CertificateError("Configure exactamente una fuente de clave privada.")
    try:
        raw = pem.encode("ascii") if pem else read_limited(Path(path), 16_384)
        if len(raw) > 16_384:
            raise CertificateError("Clave privada demasiado grande.")
        return load_private_key(raw)
    except (OSError, UnicodeError) as exc:
        raise CertificateError("No se pudo cargar la clave privada configurada.") from exc


def issue_certificate(payload: dict, key: Ed25519PrivateKey) -> dict:
    """Firma una instantánea ya autorizada por el backend; no acepta peticiones HTTP."""
    if not isinstance(key, Ed25519PrivateKey):
        raise CertificateError("Se requiere una clave privada Ed25519.")
    validate_payload(payload)
    snapshot = parse_json(canonical_json(payload))  # copia independiente del llamador
    public = key.public_key()
    document = {
        "format": FORMAT,
        "algorithm": "Ed25519",
        "key_id": fingerprint(public),
        "public_key": base64.b64encode(public_key_bytes(public)).decode("ascii"),
        "payload": snapshot,
    }
    document["signature"] = base64.b64encode(
        key.sign(DOMAIN + canonical_json(document))
    ).decode("ascii")
    canonical_json(document)
    return document


def certificate_bytes(document: dict) -> bytes:
    """El archivo JSON UTF-8 es el original firmado; no un PDF ni una imagen."""
    return canonical_json(document) + b"\n"


def _decode(value, length):
    try:
        if not isinstance(value, str):
            raise ValueError
        raw = base64.b64decode(value, validate=True)
        if len(raw) != length or base64.b64encode(raw).decode("ascii") != value:
            raise ValueError
        return raw
    except (ValueError, binascii.Error) as exc:
        raise CertificateError("Clave pública o firma con formato inválido.") from exc


def verify_certificate(raw: bytes, trusted_fingerprints: Iterable[str] = ()) -> VerificationResult:
    """Verifica integridad y, si hay lista externa, la confianza en el emisor.

    Nunca se considera confiable una huella porque venga dentro del certificado.
    Una firma correcta no demuestra que el certificado continúe vigente.
    """
    try:
        trusted = frozenset(trusted_fingerprints)
        if any(not isinstance(item, str) or not FINGERPRINT.fullmatch(item) for item in trusted):
            raise CertificateError("La lista externa de confianza tiene huellas inválidas.")
        document = parse_json(raw)
        _fields(document, {"format", "algorithm", "key_id", "public_key", "payload", "signature"},
                "sobre firmado")
        if document["format"] != FORMAT or document["algorithm"] != "Ed25519":
            raise CertificateError("Formato o algoritmo no admitido.")
        validate_payload(document["payload"])
        key = Ed25519PublicKey.from_public_bytes(_decode(document["public_key"], 32))
        key_id = fingerprint(key)
        if document["key_id"] != key_id:
            raise CertificateError("La huella no coincide con la clave incrustada.")
        signature = _decode(document["signature"], 64)
        body = {name: value for name, value in document.items() if name != "signature"}
        try:
            key.verify(signature, DOMAIN + canonical_json(body))
        except InvalidSignature:
            return VerificationResult(False, None, "FIRMA_INVALIDA",
                                      "Firma inválida: el contenido o la firma no coincide.", key_id)
        certificate_id = document["payload"]["certificate_id"]
        if not trusted:
            return VerificationResult(True, None, "SIN_ANCLA_DE_CONFIANZA",
                                      "Firma válida; falta una clave oficial conocida para autenticar al emisor.",
                                      key_id, certificate_id)
        if key_id not in trusted:
            return VerificationResult(True, False, "EMISOR_NO_CONFIABLE",
                                      "Firma válida con una clave que no está en la lista oficial.",
                                      key_id, certificate_id)
        return VerificationResult(True, True, "VALIDO",
                                  "Firma válida y clave del emisor reconocida. Vigencia no consultada.",
                                  key_id, certificate_id)
    except (CertificateError, ValueError, TypeError, RecursionError, UnsupportedAlgorithm) as exc:
        message = str(exc) if isinstance(exc, CertificateError) else "Documento no admitido."
        return VerificationResult(False, None, "FORMATO_INVALIDO", message)
