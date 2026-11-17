import base64
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from certificados import (
    CertificateError, certificate_bytes, fingerprint, issue_certificate,
    load_private_key_from_environment, parse_json, verify_certificate,
)
from certificados.cli import generate_keys, main
from certificados.core import MAX_FILE_BYTES, canonical_json, load_private_key
from certificados.demo import run_demo, sample_payload


class SignatureTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.payload = sample_payload()
        self.doc = issue_certificate(self.payload, self.key)
        self.trusted = [fingerprint(self.key.public_key())]

    def verify(self, doc=None):
        return verify_certificate(certificate_bytes(self.doc if doc is None else doc), self.trusted)

    def test_original_accepts_trusted_key(self):
        result = self.verify()
        self.assertTrue(result.accepted)
        self.assertEqual(result.current_status, "NO_CONSULTADO")

    def test_embedded_key_allows_verification_without_private_key(self):
        raw = certificate_bytes(self.doc)
        del self.key
        self.assertTrue(verify_certificate(raw, self.trusted).accepted)

    def test_changes_to_each_business_section_are_detected(self):
        changes = [
            lambda p: p.update(certificate_id="00000000-0000-4000-8000-000000000099"),
            lambda p: p.update(issued_at="2026-11-10T18:01:00Z"),
            lambda p: p["farm"].update(registry_number="OTRA-FINCA"),
            lambda p: p["farm"]["polygon_wgs84"][1].__setitem__(0, "-83.9980"),
            lambda p: p["measurement"]["values"][0].update(value="9999.00"),
            lambda p: p["approval"].update(decided_at="2026-11-10T17:58:00Z"),
            lambda p: p.update(technical_participants=["00000000-0000-4000-8000-000000000098"]),
            lambda p: p.update(predecessor_certificate_id="00000000-0000-4000-8000-000000000097"),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                altered = copy.deepcopy(self.doc)
                change(altered["payload"])
                self.assertEqual(self.verify(altered).code, "FIRMA_INVALIDA")

    def test_signature_bit_change_fails(self):
        raw = bytearray(base64.b64decode(self.doc["signature"]))
        raw[0] ^= 1
        self.doc["signature"] = base64.b64encode(raw).decode()
        self.assertEqual(self.verify().code, "FIRMA_INVALIDA")

    def test_replace_embedded_key_and_fingerprint_fails(self):
        other = issue_certificate(self.payload, Ed25519PrivateKey.generate())
        self.doc["public_key"] = other["public_key"]
        self.doc["key_id"] = other["key_id"]
        self.assertEqual(self.verify().code, "FIRMA_INVALIDA")

    def test_resigned_impostor_is_not_trusted(self):
        fake = issue_certificate(self.payload, Ed25519PrivateKey.generate())
        result = self.verify(fake)
        self.assertTrue(result.signature_valid)
        self.assertFalse(result.issuer_trusted)
        self.assertFalse(result.accepted)

    def test_without_trust_anchor_never_claims_authenticity(self):
        result = verify_certificate(certificate_bytes(self.doc))
        self.assertTrue(result.signature_valid)
        self.assertIsNone(result.issuer_trusted)
        self.assertFalse(result.accepted)

    def test_rotation_accepts_old_and_new_public_keys(self):
        new_key = Ed25519PrivateKey.generate()
        trusted = self.trusted + [fingerprint(new_key.public_key())]
        new_doc = issue_certificate(self.payload, new_key)
        for doc in (self.doc, new_doc):
            self.assertTrue(verify_certificate(certificate_bytes(doc), trusted).accepted)

    def test_removed_key_is_not_trusted(self):
        other_trusted = [fingerprint(Ed25519PrivateKey.generate().public_key())]
        self.assertFalse(verify_certificate(certificate_bytes(self.doc), other_trusted).accepted)

    def test_key_fingerprint_tampering_fails(self):
        self.doc["key_id"] = "sha256:" + "0" * 64
        self.assertEqual(self.verify().code, "FORMATO_INVALIDO")

    def test_algorithm_substitution_is_rejected(self):
        self.doc["algorithm"] = "none"
        self.assertFalse(self.verify().accepted)

    def test_unknown_envelope_field_is_rejected(self):
        self.doc["status"] = "VIGENTE"
        self.assertFalse(self.verify().accepted)

    def test_payload_rejects_private_owner_and_price_fields(self):
        for field in ("owner", "price", "password", "session_token"):
            with self.subTest(field=field):
                payload = copy.deepcopy(self.payload)
                payload[field] = "NO-DEBE-SALIR"
                with self.assertRaises(CertificateError):
                    issue_certificate(payload, self.key)

    def test_signer_does_not_reference_mutable_input(self):
        self.payload["farm"]["name"] = "modificado después"
        self.assertTrue(self.verify().accepted)
        self.assertNotEqual(self.payload["farm"]["name"], self.doc["payload"]["farm"]["name"])

    def test_whitespace_and_key_order_do_not_change_content(self):
        reversed_doc = dict(reversed(list(self.doc.items())))
        raw = json.dumps(reversed_doc, ensure_ascii=True, indent=4).encode()
        self.assertTrue(verify_certificate(raw, self.trusted).accepted)

    def test_truncated_and_invalid_base64_are_rejected(self):
        for value in ("%%%", "", "a" * 88):
            with self.subTest(value=value):
                self.doc["signature"] = value
                self.assertFalse(self.verify().accepted)

    def test_duplicate_json_keys_rejected_at_all_levels(self):
        for raw in (b'{"a":"uno","a":"dos"}', b'{"a":{"b":"uno","b":"dos"}}'):
            with self.assertRaises(CertificateError):
                parse_json(raw)

    def test_numbers_nan_infinity_and_bool_are_rejected(self):
        for value in ("1", "1.0", "NaN", "Infinity", "true"):
            with self.subTest(value=value), self.assertRaises(CertificateError):
                parse_json(('{"x":' + value + '}').encode())

    def test_invalid_json_and_oversized_files_fail_safely(self):
        for raw in (b"", b"[]", b"\xff", b"{} " * MAX_FILE_BYTES,
                    b'{"a":"\\ud800"}', b"[" * 2000):
            with self.subTest(length=len(raw)):
                self.assertFalse(verify_certificate(raw, self.trusted).accepted)

    def test_excessive_nesting_is_rejected(self):
        value = "x"
        for _ in range(20):
            value = {"a": value}
        result = verify_certificate(json.dumps(value).encode(), self.trusted)
        self.assertEqual(result.code, "FORMATO_INVALIDO")

    def test_invalid_coordinate_range_and_unclosed_ring_fail(self):
        for coordinate in ("181", "NaN", "abc"):
            payload = copy.deepcopy(self.payload)
            payload["farm"]["polygon_wgs84"][1][0] = coordinate
            with self.assertRaises(CertificateError):
                issue_certificate(payload, self.key)
        self.payload["farm"]["polygon_wgs84"][-1][0] = "-85"
        with self.assertRaises(CertificateError):
            issue_certificate(self.payload, self.key)

    def test_self_approval_visible_in_snapshot_is_rejected(self):
        self.payload["approval"]["verifier_person_id"] = self.payload["technical_participants"][0]
        with self.assertRaises(CertificateError):
            issue_certificate(self.payload, self.key)

    def test_bad_dates_and_future_approval_relative_to_issue_are_rejected(self):
        for value in ("2026-11-11T18:00:00Z", "2026-11-10T18:00:00-06:00", "ayer"):
            payload = copy.deepcopy(self.payload)
            payload["approval"]["decided_at"] = value
            with self.assertRaises(CertificateError):
                issue_certificate(payload, self.key)

    def test_negative_area_and_invalid_decimal_fail(self):
        for value in ("-1", "0", "01.0", "1e3", "nan", "1,25"):
            self.payload["farm"]["area_ha"] = value
            with self.assertRaises(CertificateError):
                issue_certificate(self.payload, self.key)

    def test_secret_source_must_be_explicit_and_unique(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(CertificateError):
            load_private_key_from_environment()
        with patch.dict(os.environ, {"VERDEAZUL_SIGNING_PRIVATE_KEY_PEM": "x",
                                    "VERDEAZUL_SIGNING_PRIVATE_KEY_FILE": "y"}, clear=True):
            with self.assertRaises(CertificateError):
                load_private_key_from_environment()

    def test_private_key_can_load_from_secret_environment(self):
        pem = self.key.private_bytes(serialization.Encoding.PEM,
                                     serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()).decode()
        with patch.dict(os.environ, {"VERDEAZUL_SIGNING_PRIVATE_KEY_PEM": pem}, clear=True):
            loaded = load_private_key_from_environment()
        self.assertEqual(fingerprint(loaded.public_key()), self.trusted[0])

    def test_invalid_private_key_does_not_leak_secret(self):
        secret = b"FAKE_SECRET_DO_NOT_ECHO"
        with self.assertRaises(CertificateError) as ctx:
            load_private_key(secret)
        self.assertNotIn(secret.decode(), str(ctx.exception))

    def test_trust_list_format_is_validated(self):
        result = verify_certificate(certificate_bytes(self.doc), ["invalid"])
        self.assertFalse(result.accepted)


class WorkflowTests(unittest.TestCase):
    def test_demo_produces_expected_results_without_private_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "demo"
            results = run_demo(path)
            self.assertEqual(results["valido"]["code"], "VALIDO")
            self.assertEqual(results["alterado"]["code"], "FIRMA_INVALIDA")
            self.assertEqual(results["otra_clave"]["code"], "EMISOR_NO_CONFIABLE")
            self.assertEqual(results["sin_clave_oficial"]["code"], "SIN_ANCLA_DE_CONFIANZA")
            for file in path.iterdir():
                self.assertNotIn(b"PRIVATE KEY", file.read_bytes())
            with self.assertRaises(FileExistsError):
                run_demo(path)

    def test_key_generation_and_sign_verify_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            private, public = root / "priv.pem", root / "pub.pem"
            generate_keys(private, public)
            if os.name != "nt":
                self.assertEqual(private.stat().st_mode & 0o777, 0o600)
            snapshot, cert = root / "snapshot.json", root / "certificate.json"
            snapshot.write_bytes(canonical_json(sample_payload()))
            with patch.dict(os.environ, {"VERDEAZUL_SIGNING_PRIVATE_KEY_FILE": str(private)}, clear=True):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["sign", str(snapshot), "--out", str(cert)]), 0)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["verify", str(cert), "--trusted-key", str(public)]), 0)
                self.assertEqual(main(["verify", str(cert)]), 3)
            original_key = private.read_bytes()
            with self.assertRaises(CertificateError):
                generate_keys(private, public)
            self.assertEqual(private.read_bytes(), original_key)
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["verify", str(root / "missing.json")]), 1)

    def test_subprocess_exit_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "demo"
            run_demo(path)
            for name, code in (("valido", 0), ("alterado", 2), ("otra_clave", 3)):
                process = subprocess.run(
                    [sys.executable, "-m", "certificados", "verify",
                     str(path / f"certificado_{name}.json"), "--trusted-key",
                     str(path / "clave_publica_demo.pem")], capture_output=True, text=True)
                self.assertEqual(process.returncode, code, process.stderr)
                self.assertIn("signature_valid", json.loads(process.stdout))


if __name__ == "__main__":
    unittest.main()
