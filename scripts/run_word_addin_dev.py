#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — scripts/run_word_addin_dev.py

Lokalni HTTPS dev server za MS Word Add-in testiranje (2026-07-25).

Word zahteva HTTPS za sideload-ovane add-in-e — ovaj skript pokreće CEO
FastAPI app (api.py) preko uvicorn-a sa samopotpisanim TLS sertifikatom,
umesto zasebnog statičkog servera. To znači da su i taskpane.html/
adapter.js (servirani preko api.py's app.mount("/word_addin", ...)) I
POST /api/copilot/ambient/analyze na ISTOM originu (https://localhost:8000)
-- adapter.js-ov fetch() poziv je zato SAME-ORIGIN, bez potrebe za CORS
podešavanjem lokalno.

Samopotpisan sertifikat NEĆE biti automatski poverljiv u Word-u/WebView2 --
prvi put kad se otvori taskpane, moguće je upozorenje o sertifikatu.
Najpouzdaniji način da se to izbegne je Microsoft-ov zvaničan alat:
    npx office-addin-dev-certs install
(instalira i OS-nivo poverljiv lokalni sertifikat za tačno ovu namenu).
Ovaj skript i dalje radi bez njega -- samo generiše sopstveni samopotpisan
par ako ga office-addin-dev-certs ne pronađe, kao portabilan fallback bez
Node.js zavisnosti.

Pokretanje:
  python scripts/run_word_addin_dev.py
  python scripts/run_word_addin_dev.py --port 8000 --host 127.0.0.1
  python scripts/run_word_addin_dev.py --regenerate-cert
"""
from __future__ import annotations

import argparse
import datetime
import ipaddress
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_CERT_DIR = Path(__file__).resolve().parent / "word_addin_dev_certs"
_CERT_PATH = _CERT_DIR / "localhost.crt"
_KEY_PATH = _CERT_DIR / "localhost.key"


def _ensure_dev_cert(regenerate: bool = False) -> tuple[Path, Path]:
    """Generiše samopotpisan TLS sertifikat za localhost ako ne postoji
    (ili ako je --regenerate-cert prosleđen). Koristi `cryptography`
    (već postojeća zavisnost, v. requirements.txt) -- ne zahteva OpenSSL
    CLI instaliran odvojeno, portabilnije na Windows-u."""
    if _CERT_PATH.exists() and _KEY_PATH.exists() and not regenerate:
        return _CERT_PATH, _KEY_PATH

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    _CERT_DIR.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Vindex AI (lokalni dev sertifikat)"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))  # ~ najduži period koji vecina browsera/WebView2 prihvata
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    _KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    _CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"[DEV CERT] Novi samopotpisan sertifikat generisan: {_CERT_PATH}")
    return _CERT_PATH, _KEY_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Vindex AI — lokalni HTTPS dev server za Word Add-in")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--regenerate-cert", action="store_true", help="Prisilno generiše nov samopotpisan sertifikat.")
    parser.add_argument("--no-reload", action="store_true", help="Isključi auto-reload (podrazumevano uključen za dev).")
    args = parser.parse_args()

    cert_path, key_path = _ensure_dev_cert(regenerate=args.regenerate_cert)

    print("=" * 72)
    print("Vindex AI — Word Add-in lokalni dev server")
    print("=" * 72)
    print(f"Taskpane:   https://{args.host}:{args.port}/word_addin/taskpane.html")
    print(f"Manifest:   {_PROJECT_ROOT / 'integrations' / 'word_addin' / 'manifest.xml'}")
    print(f"API (isti proces): https://{args.host}:{args.port}/api/copilot/ambient/analyze")
    print(f"Sertifikat: {cert_path} (samopotpisan — v. napomenu u docstring-u modula)")
    print("=" * 72)
    print("Sideload uputstvo: v. docs ili poruku koju je agent ispisao u razgovoru.")
    print("Ctrl+C za zaustavljanje.")
    print("=" * 72)

    import uvicorn
    uvicorn.run(
        "api:app",
        host=args.host,
        port=args.port,
        ssl_keyfile=str(key_path),
        ssl_certfile=str(cert_path),
        reload=not args.no_reload,
        app_dir=str(_PROJECT_ROOT),
    )


if __name__ == "__main__":
    main()
