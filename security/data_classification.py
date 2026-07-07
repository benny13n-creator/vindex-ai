# -*- coding: utf-8 -*-
"""
Vindex AI — security/data_classification.py

Klasifikacija osetljivosti podataka u skladu sa advokatskim standardima.

Hijerarhija (rastuća osetljivost):
  PUBLIC (0)              — Javni pravni sadržaj (zakoni, sudske odluke)
  INTERNAL (1)            — Interni metapodaci platforme, statistike
  CONFIDENTIAL (2)        — Kontakt podaci klijenata, nazivi predmeta
  ATTORNEY_PRIVILEGED (3) — Sadržaj predmeta, dokumenti, pravna strategija
  HIGHLY_RESTRICTED (4)   — Enkriptovana polja (JMBG, pasoš, PIB)

Svaka operacija sa podacima treba biti označena odgovarajućim nivoom.
AI model sme da vidi samo do ATTORNEY_PRIVILEGED i samo uz eksplicitnu saglasnost.
HIGHLY_RESTRICTED nikad ne sme da se šalje AI modelu u plaintext obliku.
"""
from __future__ import annotations

import functools
import logging
from enum import IntEnum
from typing import Callable

logger = logging.getLogger("vindex.security.classification")


class DataSensitivity(IntEnum):
    PUBLIC             = 0   # Javni sadržaj — zakoni, sudske odluke
    INTERNAL           = 1   # Metapodaci platforme, usage statistike
    CONFIDENTIAL       = 2   # Kontakt podaci klijenata, nazivi predmeta
    ATTORNEY_PRIVILEGED = 3  # Sadržaj predmeta, dokumenti, strategija
    HIGHLY_RESTRICTED  = 4   # JMBG, pasoš, PIB — uvek enkriptovano


# Labele za logovanje i poruke greške
_LABELS = {
    DataSensitivity.PUBLIC:              "JAVNO",
    DataSensitivity.INTERNAL:           "INTERNO",
    DataSensitivity.CONFIDENTIAL:       "POVERLJIVO",
    DataSensitivity.ATTORNEY_PRIVILEGED: "ADVOKATSKA TAJNA",
    DataSensitivity.HIGHLY_RESTRICTED:  "STROGO OGRANIČENO",
}

# Mapiranje resursa → klasifikacija
RESOURCE_CLASSIFICATION: dict[str, DataSensitivity] = {
    # AI i pravni sadržaj
    "laws":             DataSensitivity.PUBLIC,
    "court_decisions":  DataSensitivity.PUBLIC,
    "ai_forensics":     DataSensitivity.INTERNAL,
    "audit_log":        DataSensitivity.INTERNAL,
    "audit_immutable":  DataSensitivity.INTERNAL,
    "usage_events":     DataSensitivity.INTERNAL,

    # Klijentski podaci
    "klijenti":         DataSensitivity.CONFIDENTIAL,
    "profiles":         DataSensitivity.CONFIDENTIAL,

    # Predmeti i dokumenti — advokatska tajna
    "predmeti":         DataSensitivity.ATTORNEY_PRIVILEGED,
    "dokumenti":        DataSensitivity.ATTORNEY_PRIVILEGED,
    "predmet_beleske":  DataSensitivity.ATTORNEY_PRIVILEGED,
    "predmet_istorija": DataSensitivity.ATTORNEY_PRIVILEGED,
    "ai_sessions":      DataSensitivity.ATTORNEY_PRIVILEGED,
    "evidence":         DataSensitivity.ATTORNEY_PRIVILEGED,
    "biljeske":         DataSensitivity.ATTORNEY_PRIVILEGED,
    "komentari":        DataSensitivity.ATTORNEY_PRIVILEGED,

    # Finansijski podaci
    "billing":          DataSensitivity.CONFIDENTIAL,
    "fakture":          DataSensitivity.CONFIDENTIAL,

    # Strogo ograničeno — enkriptovana polja nikad ne idu u AI
    "jmbg":             DataSensitivity.HIGHLY_RESTRICTED,
    "passport":         DataSensitivity.HIGHLY_RESTRICTED,
    "pib":              DataSensitivity.HIGHLY_RESTRICTED,
}


def get_classification(resource_type: str) -> DataSensitivity:
    """Vraća nivo osetljivosti za tip resursa."""
    return RESOURCE_CLASSIFICATION.get(resource_type, DataSensitivity.CONFIDENTIAL)


def label(sensitivity: DataSensitivity) -> str:
    return _LABELS.get(sensitivity, str(sensitivity))


def can_send_to_ai(sensitivity: DataSensitivity) -> bool:
    """
    Određuje da li se podaci mogu slati AI modelu.
    HIGHLY_RESTRICTED nikad ne sme ići AI-u u nešifrovanom obliku.
    """
    return sensitivity < DataSensitivity.HIGHLY_RESTRICTED


def require_classification(
    max_sensitivity: DataSensitivity,
    resource_types: list[str],
) -> bool:
    """
    Proverava da li svi resursi zadovoljavaju ograničenje osetljivosti.
    Vraća True ako je sve u redu, False ako je potrebna dodatna zaštita.
    """
    for rt in resource_types:
        cls = get_classification(rt)
        if cls > max_sensitivity:
            logger.warning(
                "[CLASSIFICATION] %s (%s) prelazi dozvoljeni nivo %s",
                rt, label(cls), label(max_sensitivity),
            )
            return False
    return True


def classify_decorator(resource_type: str):
    """
    Dekorator za FastAPI endpoint funkcije.
    Automatski loguje klasifikaciju pristupljenog resursa.

    Upotreba:
        @app.get("/api/predmeti/{id}/dokumenti")
        @classify_decorator("dokumenti")
        async def get_dokumenti(id: str, user: dict = Depends(get_current_user)):
            ...
    """
    def decorator(func: Callable) -> Callable:
        sensitivity = get_classification(resource_type)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get("user") or {}
            uid_short = (user.get("user_id") or "?")[:8]
            logger.info(
                "[CLASSIFICATION] uid=%.8s pristupa %s [%s]",
                uid_short, resource_type, label(sensitivity),
            )
            if sensitivity >= DataSensitivity.ATTORNEY_PRIVILEGED:
                logger.info(
                    "[CLASSIFICATION] ADVOKATSKA TAJNA pristup uid=%.8s endpoint=%s",
                    uid_short, func.__name__,
                )
            return await func(*args, **kwargs)

        return wrapper
    return decorator


# ─── Polja koja NIKAD ne smeju ići AI-u ──────────────────────────────────────

RESTRICTED_FIELD_NAMES: set[str] = {
    "jmbg", "maticni_broj", "passport_number", "broj_pasosa",
    "pib", "field_encryption_key", "password", "lozinka",
    "bank_account", "broj_racuna", "iban", "credit_card",
}


def sanitize_for_ai(data: dict) -> dict:
    """
    Uklanja HIGHLY_RESTRICTED polja iz dict-a pre slanja AI modelu.
    Zamenjuje vrednosti sa [ZAŠTIĆENO].
    """
    result = {}
    for k, v in data.items():
        if k.lower() in RESTRICTED_FIELD_NAMES:
            result[k] = "[ZAŠTIĆENO]"
            logger.info("[CLASSIFICATION] polje '%s' maskirano pre slanja AI-u", k)
        elif isinstance(v, str) and v.startswith("enc_v1:"):
            result[k] = "[ENKRIPTOVANO]"
        else:
            result[k] = v
    return result
