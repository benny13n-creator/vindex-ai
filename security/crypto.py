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
"""
from __future__ import annotations

import base64
import logging
import os
import uuid

logger = logging.getLogger("vindex.security.crypto")

_KEY_ENV = "FIELD_ENCRYPTION_KEY"
_ENC_PREFIX = "enc_v1:"
_NONCE_LEN = 12  # 96-bit nonce za AES-GCM (standard)


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
    if len(key_bytes) < 32:
        raise RuntimeError(
            f"[CRYPTO] {_KEY_ENV} mora biti min 32 bajta posle dekodiranja "
            f"(dobijeno {len(key_bytes)})"
        )
    return key_bytes[:32]


def encrypt_field(plaintext: str) -> str:
    """
    Enkriptuje string polje sa AES-256-GCM.

    Format: "enc_v1:<base64url(nonce[12B] || ciphertext+tag)>"
    Prazni string → vraća ""
    """
    if not plaintext:
        return ""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _get_field_key()
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    encoded = base64.urlsafe_b64encode(nonce + ct_with_tag).decode("ascii")
    return f"{_ENC_PREFIX}{encoded}"


def decrypt_field(ciphertext: str) -> str:
    """
    Dekriptuje polje enkriptovano sa encrypt_field().

    - Ako nije enkriptovano (stari unos, ne počinje sa prefix), vraća as-is.
    - Na grešci dekriptovanja: loguje i vraća sentinel string (ne crashuje).
    """
    if not ciphertext:
        return ""
    if not ciphertext.startswith(_ENC_PREFIX):
        return ciphertext
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        key = _get_field_key()
        raw = base64.urlsafe_b64decode(ciphertext[len(_ENC_PREFIX):] + "==")
        if len(raw) <= _NONCE_LEN:
            raise ValueError("ciphertext prekratak")
        nonce, ct_with_tag = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct_with_tag, None).decode("utf-8")
    except Exception as e:
        logger.error("[CRYPTO] decrypt_field greška: %s", e)
        return "[GREŠKA DEKRIPTOVANJA]"


def is_encrypted(value: str) -> bool:
    """Vraća True ako vrednost izgleda kao encrypt_field() output."""
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
