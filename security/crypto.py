# -*- coding: utf-8 -*-
"""
Vindex AI — security/crypto.py

Field-level encryption (AES-256-GCM) i password hashing (Argon2id).

HARD RULES (ne sme se menjati):
  - JMBG, pasoš, PIB → encrypt_field() PRE upisa u bazu, NIKAD plaintext
  - Lozinke → hash_password()/verify_password() — NIKAD bcrypt/sha
  - Ključ iz FIELD_ENCRYPTION_KEY env var (32-byte, base64url)
  - Storage putanje → generate_storage_key() — randomizovani UUID, nikad ime fajla

Generisanje ključa (jednom, na serveru):
  python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
  → Dodaj u Render/Supabase env: FIELD_ENCRYPTION_KEY=<output>

FORMAT ENKRIPTOVANIH VREDNOSTI:
  Novi format (od v2):  enc_v1:k1:<base64url(nonce[12B] || ciphertext+tag)>
  Legacy format (v1):   enc_v1:<base64url(nonce[12B] || ciphertext+tag)>

  Oba formata se dekriptuju identično — legacy se tretira kao k1.
  Novi format uvodi KEY_ID u vrednost, što omogućava buduću rotaciju ključa
  bez ponovnog enkriptovanja svih zapisa odjednom (KEY_ROTATION_ANALYSIS.md).
"""
from __future__ import annotations

import base64
import logging
import os
import uuid

logger = logging.getLogger("vindex.security.crypto")

_KEY_ENV    = "FIELD_ENCRYPTION_KEY"
_KEY_ID_ENV = "FIELD_ENCRYPTION_KEY_ID"   # INT — aktivan key ID (default 1)
_ENC_PREFIX = "enc_v1:"
_NONCE_LEN  = 12   # 96-bit nonce za AES-GCM (standard)
_MIN_KEY_BYTES = 32


# ─── Startup validation ───────────────────────────────────────────────────────

def validate_field_encryption_key() -> None:
    """
    Fail-fast validacija FIELD_ENCRYPTION_KEY.
    Pozvati pri startu aplikacije — pre nego što server počne da prima zahteve.
    Ako ključ nije validan, ispisuje jasnu grešku i poziva sys.exit(1).

    Proverava:
      1. Ključ postoji (env var nije prazan)
      2. Ključ je validan base64url
      3. Ključ dekodira na min 32 bajta (256 bita)
      4. Smoke test enkripcije/dekripcije (AES-GCM radi sa ovim ključem)
    """
    import sys
    _ABORT_MSG = (
        "\n"
        "╔══════════════════════════════════════════════════════════╗\n"
        "║  STARTUP ABORTED — FIELD_ENCRYPTION_KEY missing/invalid  ║\n"
        "╚══════════════════════════════════════════════════════════╝\n"
        "{detail}\n\n"
        "Generisanje ispravnog kljuca:\n"
        '  python -c "import secrets,base64; '
        'print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"\n'
        "Dodajte rezultat u Render env vars i lokalni .env fajl.\n"
    )

    raw = (os.environ.get(_KEY_ENV) or "").strip()

    if not raw:
        print(_ABORT_MSG.format(detail=f"  Razlog: {_KEY_ENV} env var nije postavljen."))
        sys.exit(1)

    try:
        key_bytes = base64.urlsafe_b64decode(raw + "==")
    except Exception as e:
        print(_ABORT_MSG.format(detail=f"  Razlog: {_KEY_ENV} nije validan base64url string.\n  Greška: {e}"))
        sys.exit(1)

    if len(key_bytes) < _MIN_KEY_BYTES:
        print(_ABORT_MSG.format(
            detail=f"  Razlog: {_KEY_ENV} je {len(key_bytes)} bajta posle dekodiranja.\n"
                   f"  Potrebno: min {_MIN_KEY_BYTES} bajta (256-bit AES kljuc)."
        ))
        sys.exit(1)

    # Smoke test — provjeri da AES-GCM radi sa ovim ključem koristeći novi format
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = key_bytes[:_MIN_KEY_BYTES]
        nonce = os.urandom(_NONCE_LEN)
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, b"vindex_smoke_test", None)
        encoded = base64.urlsafe_b64encode(nonce + ct).decode("ascii")
        # Verifikuj novi format round-trip
        test_enc = f"enc_v1:k1:{encoded}"
        decrypted = decrypt_field(test_enc)
        if decrypted != "vindex_smoke_test":
            raise ValueError("Smoke test round-trip nije uspeo")
    except Exception as e:
        print(_ABORT_MSG.format(detail=f"  Razlog: AES-GCM smoke test nije uspeo.\n  Greška: {e}"))
        sys.exit(1)

    logger.info("[CRYPTO] FIELD_ENCRYPTION_KEY validacija prosla (key_len=%d bajta, kid=k%s).",
                len(key_bytes), os.environ.get(_KEY_ID_ENV, "1"))


# ─── AES-256-GCM Field Encryption ────────────────────────────────────────────

def _get_field_key() -> bytes:
    raw = (os.environ.get(_KEY_ENV) or "").strip()
    if not raw:
        raise RuntimeError(
            f"[CRYPTO] {_KEY_ENV} nije postavljen. "
            "Generišite ključ: python -c \"import secrets,base64; "
            "print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())\" "
            "i dodajte u .env kao FIELD_ENCRYPTION_KEY=<vrednost>"
        )
    try:
        key_bytes = base64.urlsafe_b64decode(raw + "==")
    except Exception as e:
        raise RuntimeError(f"[CRYPTO] {_KEY_ENV} nije validan base64url: {e}")
    if len(key_bytes) < _MIN_KEY_BYTES:
        raise RuntimeError(
            f"[CRYPTO] {_KEY_ENV} mora biti min {_MIN_KEY_BYTES} bajta posle dekodiranja "
            f"(dobijeno {len(key_bytes)})"
        )
    return key_bytes[:_MIN_KEY_BYTES]


def _get_active_key_id() -> int:
    """Vraća aktivan KEY_ID (int) iz env vara. Default je 1."""
    try:
        return int(os.environ.get(_KEY_ID_ENV, "1"))
    except (ValueError, TypeError):
        return 1


def encrypt_field(plaintext: str) -> str:
    """
    Enkriptuje string polje sa AES-256-GCM.

    Format: "enc_v1:k{kid}:<base64url(nonce[12B] || ciphertext+tag)>"
    Prazni string → vraća ""
    """
    if not plaintext:
        return ""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _get_field_key()
    kid = _get_active_key_id()
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    encoded = base64.urlsafe_b64encode(nonce + ct_with_tag).decode("ascii")
    return f"{_ENC_PREFIX}k{kid}:{encoded}"


def decrypt_field(ciphertext: str) -> str:
    """
    Dekriptuje polje enkriptovano sa encrypt_field().

    Podržava oba formata:
      - Novi:   enc_v1:k1:<base64data>  (od v2, KEY_ID eksplicitan)
      - Legacy: enc_v1:<base64data>     (v1, tretira se kao k1)

    Ako nije enkriptovano (ne počinje sa prefix), vraća as-is.
    Na grešci dekriptovanja: loguje i vraća sentinel string (ne crashuje).
    """
    if not ciphertext:
        return ""
    if not ciphertext.startswith(_ENC_PREFIX):
        return ciphertext
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        rest = ciphertext[len(_ENC_PREFIX):]

        # Razlikuj novi format (k{id}:data) od legacy (samo data)
        if rest.startswith("k") and ":" in rest:
            kid_str, data = rest.split(":", 1)
            # kid_str = "k1", "k2", itd. — za sada koristimo isti ključ (Faza 10a)
            # Faza 10b: _get_key_by_id(int(kid_str[1:])) za multi-key support
        else:
            # Legacy format bez KEY_ID — tretiramo kao k1
            data = rest

        key = _get_field_key()
        raw = base64.urlsafe_b64decode(data + "==")
        if len(raw) <= _NONCE_LEN:
            raise ValueError("ciphertext prekratak")
        nonce, ct_with_tag = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct_with_tag, None).decode("utf-8")
    except Exception as e:
        logger.error("[CRYPTO] decrypt_field greška: %s", e)
        return "[GREŠKA DEKRIPTOVANJA]"


def is_encrypted(value: str) -> bool:
    """Vraća True ako vrednost izgleda kao encrypt_field() output (oba formata)."""
    return bool(value) and value.startswith(_ENC_PREFIX)


def generate_storage_key() -> str:
    """
    Generiše randomizovani storage key za dokumente.

    Format: "encrypted_blob_<uuid4>"
    Nikad ne sadrži originalno ime fajla ni ekstenziju.
    """
    return f"encrypted_blob_{uuid.uuid4()}"


# ─── Argon2id Password Hashing ───────────────────────────────────────────────

def hash_password(plaintext: str) -> str:
    """
    Argon2id hash lozinke. NIKAD bcrypt, NIKAD sha.

    Parametri po OWASP preporuci (2024):
      time_cost=2, memory_cost=65536 (64MB), parallelism=2
    """
    from argon2 import PasswordHasher
    ph = PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=2,
        hash_len=32,
        salt_len=16,
    )
    return ph.hash(plaintext)


def verify_password(plaintext: str, hash_str: str) -> bool:
    """Verifikuje lozinku. Vraća False (ne baca izuzetak) na neuspeh."""
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
    ph = PasswordHasher()
    try:
        return ph.verify(hash_str, plaintext)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception as e:
        logger.error("[CRYPTO] verify_password neočekivana greška: %s", e)
        return False


def needs_rehash(hash_str: str) -> bool:
    """Vraća True ako hash koristi zastarele parametre i treba rehash."""
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    return ph.check_needs_rehash(hash_str)
