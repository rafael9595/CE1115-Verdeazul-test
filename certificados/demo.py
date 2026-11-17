"""Demostración con datos sintéticos; la clave privada solo vive en memoria."""

import copy
import json
from dataclasses import asdict
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .core import ISSUER, certificate_bytes, fingerprint, issue_certificate, verify_certificate


def sample_payload():
    return {
        "certificate_id": "00000000-0000-4000-8000-000000000001",
        "issuer": ISSUER,
        "issued_at": "2026-11-10T18:00:00Z",
        "farm": {
            "id": "00000000-0000-4000-8000-000000000002",
            "registry_number": "FINCA-DEMO-001",
            "name": "Finca de demostración (datos sintéticos)",
            "area_ha": "10.50",
            "country_code": "CR",
            "polygon_wgs84": [
                ["-84.0000", "10.0000"], ["-83.9990", "10.0000"],
                ["-83.9990", "10.0010"], ["-84.0000", "10.0000"],
            ],
        },
        "measurement": {
            "id": "00000000-0000-4000-8000-000000000003",
            "version_id": "00000000-0000-4000-8000-000000000004",
            "period_id": "00000000-0000-4000-8000-000000000005",
            "measured_at": "2026-11-09",
            "methodology": "METODO-DEMO: valor sintético; no acredita carbono real",
            "values": [{"name": "carbono_reportado", "value": "125.50", "unit": "tCO2e"}],
        },
        "approval": {
            "id": "00000000-0000-4000-8000-000000000006",
            "verifier_person_id": "00000000-0000-4000-8000-000000000007",
            "decided_at": "2026-11-10T17:59:00Z",
        },
        "technical_participants": ["00000000-0000-4000-8000-000000000008"],
        "predecessor_certificate_id": None,
    }


def run_demo(destination: Path):
    # No sobreescribir evidencia de una ejecución anterior.
    destination.mkdir(parents=True, exist_ok=False)
    key = Ed25519PrivateKey.generate()
    trusted = [fingerprint(key.public_key())]
    valid = issue_certificate(sample_payload(), key)
    altered = copy.deepcopy(valid)
    altered["payload"]["measurement"]["values"][0]["value"] = "9999.00"
    impostor = issue_certificate(sample_payload(), Ed25519PrivateKey.generate())
    documents = {"valido": valid, "alterado": altered, "otra_clave": impostor}
    results = {}
    for name, document in documents.items():
        raw = certificate_bytes(document)
        (destination / f"certificado_{name}.json").write_bytes(raw)
        results[name] = asdict(verify_certificate(raw, trusted))
    results["sin_clave_oficial"] = asdict(verify_certificate(certificate_bytes(valid)))
    (destination / "clave_publica_demo.pem").write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    (destination / "instantanea_demo.json").write_text(
        json.dumps(sample_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "resultados_demo.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return results
