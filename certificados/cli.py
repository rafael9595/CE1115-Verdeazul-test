"""Interfaz de pruebas y verificación; no se expone por HTTP."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .core import (
    CertificateError, certificate_bytes, fingerprint, issue_certificate,
    load_private_key_from_environment, load_public_key, parse_json,
    read_limited, verify_certificate,
)
from .demo import run_demo


def _write_new(path: Path, data: bytes, *, private=False):
    # O_EXCL evita sobreescrituras y seguimiento de enlaces a archivos existentes.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600 if private else 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def generate_keys(private_path: Path, public_path: Path):
    if private_path.resolve() == public_path.resolve():
        raise CertificateError("Las rutas de clave privada y pública deben ser diferentes.")
    if private_path.exists() or public_path.exists():
        raise CertificateError("No se sobrescriben claves existentes.")
    for path in (private_path, public_path):
        if not path.parent.is_dir():
            raise CertificateError("Cree primero las carpetas de destino de las claves.")
    key = Ed25519PrivateKey.generate()
    private_bytes = key.private_bytes(serialization.Encoding.PEM,
                                     serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption())
    public_bytes = key.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    _write_new(private_path, private_bytes, private=True)
    try:
        _write_new(public_path, public_bytes)
    except OSError:
        private_path.unlink(missing_ok=True)
        raise
    return fingerprint(key.public_key())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verdeazul: firma y verificación de certificados")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Genera casos sintéticos sin guardar la clave privada")
    demo.add_argument("--out", type=Path, default=Path("demo_salida"))
    keys = commands.add_parser("keys", help="Crea un par Ed25519; no sobrescribe archivos")
    keys.add_argument("--private-out", type=Path, required=True)
    keys.add_argument("--public-out", type=Path, required=True)
    sign = commands.add_parser("sign", help="Firma una instantánea para pruebas internas")
    sign.add_argument("snapshot", type=Path)
    sign.add_argument("--out", type=Path, required=True)
    verify = commands.add_parser("verify", help="Verifica un archivo sin clave privada ni base de datos")
    verify.add_argument("certificate", type=Path)
    verify.add_argument("--trusted-key", type=Path, action="append", default=[],
                        help="PEM público obtenido por un canal oficial; repetible para rotación")
    fp = commands.add_parser("fingerprint", help="Muestra la huella SHA-256 de una clave pública")
    fp.add_argument("public_key", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            results = run_demo(args.out)
            for name, result in results.items():
                print(f"{name}: {result['code']} - {result['message']}")
            print(f"Archivos de demostración: {args.out}")
            return 0
        if args.command == "keys":
            key_id = generate_keys(args.private_out, args.public_out)
            print(f"Claves creadas. Huella pública: {key_id}")
            return 0
        if args.command == "sign":
            snapshot = parse_json(read_limited(args.snapshot))
            document = issue_certificate(snapshot, load_private_key_from_environment())
            _write_new(args.out, certificate_bytes(document))
            print(f"Archivo firmado: {args.out}. No implica persistencia ni aprobación en el sistema.")
            return 0
        if args.command == "fingerprint":
            print(fingerprint(load_public_key(read_limited(args.public_key, 16_384))))
            return 0
        trusted = [fingerprint(load_public_key(read_limited(p, 16_384))) for p in args.trusted_key]
        result = verify_certificate(read_limited(args.certificate), trusted)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return 0 if result.accepted else (3 if result.signature_valid else 2)
    except (CertificateError, OSError) as exc:
        # No imprimir contenido de claves, variables de entorno o archivos.
        message = str(exc) if isinstance(exc, CertificateError) else "No se pudo leer o crear el archivo; revise ruta y permisos."
        print(f"ERROR: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
