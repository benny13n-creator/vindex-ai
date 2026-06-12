# -*- coding: utf-8 -*-
"""
Klijenti CRM — FastAPI router (8 faza).

Faza 1  — Klijent profil (sa predmetima, tabovi, confidential reveal)
Faza 2  — Audit log za svaku akciju (append-only)
Faza 3  — Conflict of Interest check
Faza 4  — Dokumentacioni trezor (encrypted blob storage)
Faza 5  — Role-based permissions (partner/advokat/pripravnik/sekretarica)
Faza 6  — Field-level AES-256-GCM enkripcija + PDF watermark + Argon2id check
Faza 7  — Komunikacioni dosije + Timeline
Faza 8  — Retention/GDPR (arhiviranje, pravni osnov, zastarelost)

Montirati u api.py:
  from klijenti.router import router as klijenti_router
  app.include_router(klijenti_router)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from klijenti.permissions import (
    Role, ROLE_STR, ROLE_NAMES, filter_klijent, can_perform,
    can_access_field, DEFAULT_ROLE, FC,
)
from klijenti.audit import Akcija, log_event, get_client_ip
from security.crypto import encrypt_field, decrypt_field, is_encrypted, generate_storage_key
from shared.deps import _get_supa, _is_founder, _verify_token

logger = logging.getLogger("vindex.klijenti")

router = APIRouter(tags=["klijenti"])


def _get_role(user_id: str, email: str) -> Role:
    if _is_founder(email):
        return Role.PARTNER
    try:
        supa = _get_supa()
        res = supa.table("user_roles").select("rola").eq("user_id", user_id).execute()
        if res.data:
            return ROLE_STR.get(res.data[0].get("rola", ""), DEFAULT_ROLE)
    except Exception as e:
        logger.warning("[PERMISSIONS] user_roles read greška: %s", e)
    return DEFAULT_ROLE


async def _enrich_user(user: dict) -> dict:
    """Dodaje 'role' i 'role_str' na user dict."""
    role = await asyncio.to_thread(_get_role, user["user_id"], user.get("email", ""))
    user["role"] = role
    user["role_str"] = ROLE_NAMES.get(role, "advokat")
    return user


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _verify_owns_klijent(supa, klijent_id: str, user_id: str) -> bool:
    """
    Potvrđuje da klijent postoji I pripada ovom korisniku.
    Ovo sprečava horizontal access (user A čita podatke user B).
    Uvek pozivati pre pristupa resursima vezanim za klijenta.
    """
    try:
        res = await asyncio.to_thread(
            lambda: supa.table("klijenti")
                        .select("id")
                        .eq("id", klijent_id)
                        .eq("user_id", user_id)
                        .single()
                        .execute()
        )
        return bool(res.data)
    except Exception:
        return False


def _normalize_name(s: str) -> str:
    """Normalizuje ime za fuzzy matching: lowercase, bez dijakritike, bez interpunkcije."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip_confidential_from_log(d: dict) -> dict:
    """Uklanja vrednosti CONFIDENTIAL polja iz audit detalji."""
    from klijenti.permissions import KLIJENT_FIELD_CLASS, FC
    safe = {}
    for k, v in d.items():
        cls = KLIJENT_FIELD_CLASS.get(k, FC.INTERNAL)
        safe[k] = "[REDACTED]" if cls in (FC.CONFIDENTIAL, FC.HIGHLY_CONFIDENTIAL) else v
    return safe


# ─── Pydantic modeli ──────────────────────────────────────────────────────────

class KlijentCreateReq(BaseModel):
    tip: str = Field(default="fizicko_lice")
    ime: str = Field(..., min_length=2, max_length=200)
    prezime: str = Field(default="", max_length=200)
    firma: str = Field(default="", max_length=300)
    email: str = Field(default="", max_length=200)
    telefon: str = Field(default="", max_length=50)
    adresa: str = Field(default="", max_length=500)
    napomena: str = Field(default="", max_length=2000)
    maticni_broj: str = Field(default="", max_length=30)
    pravni_osnov_obrade: str = Field(default="legitimni_interes", max_length=30)
    # CONFIDENTIAL — biće enkriptovani pre upisa
    jmbg: str = Field(default="", max_length=15)
    broj_pasosa: str = Field(default="", max_length=20)
    pib: str = Field(default="", max_length=15)
    # FAZA 8: Saglasnost (ako pravni_osnov == saglasnost)
    saglasnost_datum: Optional[str] = Field(default=None, max_length=30)

    @field_validator("tip")
    @classmethod
    def _tip(cls, v: str) -> str:
        allowed = {"fizicko_lice", "pravno_lice", "fizicko", "pravno"}
        if v not in allowed:
            raise ValueError(f"tip mora biti jedan od: {sorted(allowed)}")
        return v

    @field_validator("pravni_osnov_obrade")
    @classmethod
    def _osnov(cls, v: str) -> str:
        allowed = {"ugovor", "zakonska_obaveza", "legitimni_interes", "saglasnost"}
        if v not in allowed:
            raise ValueError(f"pravni_osnov_obrade mora biti jedan od: {sorted(allowed)}")
        return v


class KlijentUpdateReq(KlijentCreateReq):
    ime: str = Field(default="", max_length=200)


class LinkPredmetReq(BaseModel):
    predmet_id: str = Field(..., max_length=64)
    uloga_klijenta: str = Field(default="stranka", max_length=30)

    @field_validator("uloga_klijenta")
    @classmethod
    def _uloga(cls, v: str) -> str:
        allowed = {
            "tuzilac", "tuzeni", "stranka", "protivna_strana",
            "advokat_protivne", "svedok", "ostalo", "protivna_stranka",
        }
        if v not in allowed:
            raise ValueError(f"uloga_klijenta mora biti jedna od: {sorted(allowed)}")
        return v


class KomunikacijaReq(BaseModel):
    tip: str = Field(..., max_length=20)
    datum_vreme: str = Field(..., max_length=30)
    kratak_opis: str = Field(default="", max_length=500)

    @field_validator("tip")
    @classmethod
    def _tip(cls, v: str) -> str:
        allowed = {"poziv", "email", "sastanak", "whatsapp", "viber", "beleska", "ostalo"}
        if v not in allowed:
            raise ValueError(f"tip mora biti jedan od: {sorted(allowed)}")
        return v


class ConflictCheckReq(BaseModel):
    ime: str = Field(..., min_length=2, max_length=200)
    prezime: str = Field(default="", max_length=200)
    firma: str = Field(default="", max_length=300)
    jmbg: str = Field(default="", max_length=15)
    pib: str = Field(default="", max_length=15)


# ─── FAZA 1: Klijent CRUD sa confidential support ────────────────────────────

@router.post("/klijenti")
async def create_klijent(
    req: KlijentCreateReq,
    request: Request,
):
    """Faza 1 — Kreira novog klijenta sa enkripcijom CONFIDENTIAL polja."""
    user = await _auth_from_request(request)

    supa = _get_supa()
    ip = get_client_ip(request)

    # Enkriptuj CONFIDENTIAL polja pre upisa
    row = {
        "user_id":                 user["user_id"],
        "tip":                     req.tip,
        "ime":                     req.ime.strip(),
        "prezime":                 req.prezime.strip(),
        "firma":                   req.firma.strip(),
        "email":                   req.email.strip(),
        "telefon":                 req.telefon.strip(),
        "adresa":                  req.adresa.strip(),
        "napomena":                req.napomena.strip(),
        "maticni_broj":            req.maticni_broj.strip(),
        "pravni_osnov_obrade":     req.pravni_osnov_obrade,
        "status":                  "aktivan",
        "datum_nastanka":          _now_iso(),
        "datum_poslednje_aktivnosti": _now_iso(),
    }
    # NIKAD plaintext za CONFIDENTIAL polja
    if req.jmbg:
        row["jmbg_encrypted"] = await asyncio.to_thread(encrypt_field, req.jmbg)
    if req.broj_pasosa:
        row["broj_pasosa_encrypted"] = await asyncio.to_thread(encrypt_field, req.broj_pasosa)
    if req.pib:
        row["pib_encrypted"] = await asyncio.to_thread(encrypt_field, req.pib)
    if req.saglasnost_datum and req.pravni_osnov_obrade == "saglasnost":
        row["saglasnost_datum"] = req.saglasnost_datum

    res = await asyncio.to_thread(
        lambda: supa.table("klijenti").insert(row).execute()
    )
    klijent = res.data[0] if res.data else {}

    asyncio.create_task(log_event(
        supa=supa, user_id=user["user_id"], user_email=user.get("email", ""),
        user_role=user.get("role_str", "advokat"), akcija=Akcija.CREATE,
        entitet_id=klijent.get("id"), detalji={"tip": req.tip}, ip_adresa=ip,
    ))

    return {"status": "kreiran", "klijent": filter_klijent(klijent, user["role"])}


@router.get("/klijenti")
async def list_klijenti(
    request: Request,
    pretraga: str = "",
    status_filter: str = "",
):
    """Faza 1 — Lista klijenata filtrirana po roli."""
    user = await _auth_from_request(request)
    supa = _get_supa()

    def _fetch():
        q = (supa.table("klijenti")
                 .select("id,tip,ime,prezime,firma,email,telefon,status,aktivan,datum_poslednje_aktivnosti,kreirano")
                 .eq("user_id", user["user_id"]))
        # Isključi soft-deleted
        q = q.neq("status", "soft_deleted")
        if pretraga:
            q = q.ilike("ime", f"%{pretraga}%")
        if status_filter:
            q = q.eq("status", status_filter)
        return q.order("kreirano", desc=True).execute()

    res = await asyncio.to_thread(_fetch)
    klijenti = [filter_klijent(k, user["role"]) for k in (res.data or [])]
    return {"klijenti": klijenti}


@router.get("/klijenti/retention-check")
async def retention_check(
    request: Request,
    threshold_years: int = 10,
):
    """
    Faza 8 — GDPR retention check.
    MORA biti registrovana PRE /klijenti/{klijent_id} da ne bude zasencena.
    Vraća klijente kojima je datum_poslednje_aktivnosti stariji od threshold_years.
    Ne arhivira automatski — samo predlaže advokatima.
    """
    from datetime import timedelta
    user = await _auth_from_request(request)
    supa = _get_supa()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=365 * threshold_years)).isoformat()

    res = await asyncio.to_thread(
        lambda: supa.table("klijenti")
                    .select("id, ime, prezime, firma, datum_poslednje_aktivnosti, status")
                    .eq("user_id", user["user_id"])
                    .eq("status", "aktivan")
                    .lt("datum_poslednje_aktivnosti", cutoff)
                    .order("datum_poslednje_aktivnosti")
                    .execute()
    )
    candidates = res.data or []
    return {
        "kandidati_za_arhiviranje": [filter_klijent(c, user["role"]) for c in candidates],
        "ukupno": len(candidates),
        "threshold_godina": threshold_years,
        "napomena": "Pregled za arhiviranje — advokat odlučuje za svaki slučaj",
    }


@router.get("/klijenti/{klijent_id}")
async def get_klijent(
    klijent_id: str,
    request: Request,
    reveal_confidential: bool = False,
):
    """
    Faza 1+6 — Detalji klijenta.

    ?reveal_confidential=true → dekriptuje CONFIDENTIAL polja + audit log.
    CONFIDENTIAL nikad nije u plain responsu bez eksplicitnog zahteva.
    """
    user = await _auth_from_request(request)
    supa = _get_supa()
    ip = get_client_ip(request)

    res = await asyncio.to_thread(
        lambda: supa.table("klijenti")
                    .select("*")
                    .eq("id", klijent_id)
                    .eq("user_id", user["user_id"])
                    .neq("status", "soft_deleted")
                    .single()
                    .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Klijent nije pronađen.")
    klijent = dict(res.data)

    # Audit za VIEW
    asyncio.create_task(log_event(
        supa=supa, user_id=user["user_id"], user_email=user.get("email", ""),
        user_role=user.get("role_str", "advokat"), akcija=Akcija.VIEW,
        entitet_id=klijent_id, ip_adresa=ip,
    ))

    if reveal_confidential:
        # Provera permisije
        if not can_perform(user["role"], "access_confidential"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nemate pravo uvida u poverljive podatke.",
            )
        # Audit MORA biti pre dekriptovanja i pre return-a
        await log_event(
            supa=supa, user_id=user["user_id"], user_email=user.get("email", ""),
            user_role=user.get("role_str", "advokat"), akcija=Akcija.VIEW_CONFIDENTIAL,
            entitet_id=klijent_id,
            detalji={"polja": ["jmbg", "broj_pasosa", "pib"]},
            ip_adresa=ip,
        )
        # Dekriptuj CONFIDENTIAL polja, pa ukloni encrypted verzije iz response
        # (ne sme da se vrate i enc_v1:... i plaintext u istom response)
        for enc_field, plain_key in [
            ("jmbg_encrypted",        "jmbg"),
            ("broj_pasosa_encrypted", "broj_pasosa"),
            ("pib_encrypted",         "pib"),
        ]:
            raw = klijent.pop(enc_field, "") or ""
            if raw:
                klijent[plain_key] = await asyncio.to_thread(decrypt_field, raw)

    # Dohvati predmete za ovog klijenta
    try:
        pred_res = await asyncio.to_thread(
            lambda: supa.table("predmet_klijenti")
                        .select("predmet_id, uloga_klijenta, predmeti(id, naziv, status, tip)")
                        .eq("klijent_id", klijent_id)
                        .execute()
        )
        predmeti_raw = pred_res.data or []
    except Exception:
        predmeti_raw = []

    aktivni = [p for p in predmeti_raw if (p.get("predmeti") or {}).get("status") not in ("zatvoren", "arhiviran")]
    zavrseni = [p for p in predmeti_raw if (p.get("predmeti") or {}).get("status") in ("zatvoren", "arhiviran")]

    # Update datum_poslednje_aktivnosti
    asyncio.create_task(_update_activity(supa, klijent_id, user["user_id"]))

    return {
        "klijent":  filter_klijent(klijent, user["role"]) if not reveal_confidential else klijent,
        "aktivni_predmeti":   aktivni,
        "zavrseni_predmeti":  zavrseni,
    }


@router.put("/klijenti/{klijent_id}")
async def update_klijent(
    klijent_id: str,
    req: KlijentUpdateReq,
    request: Request,
):
    """Faza 1+6 — Ažurira klijenta sa enkripcijom CONFIDENTIAL polja."""
    user = await _auth_from_request(request)
    supa = _get_supa()
    ip = get_client_ip(request)

    stara_vrednost = await asyncio.to_thread(
        lambda: supa.table("klijenti").select("*").eq("id", klijent_id).eq("user_id", user["user_id"]).single().execute()
    )
    if not stara_vrednost.data:
        raise HTTPException(status_code=404, detail="Klijent nije pronađen.")

    update_row: dict = {}
    if req.ime:
        update_row["ime"] = req.ime.strip()
    if req.prezime is not None:
        update_row["prezime"] = req.prezime.strip()
    if req.firma is not None:
        update_row["firma"] = req.firma.strip()
    if req.email is not None:
        update_row["email"] = req.email.strip()
    if req.telefon is not None:
        update_row["telefon"] = req.telefon.strip()
    if req.adresa is not None:
        update_row["adresa"] = req.adresa.strip()
    if req.napomena is not None:
        update_row["napomena"] = req.napomena.strip()
    if req.maticni_broj is not None:
        update_row["maticni_broj"] = req.maticni_broj.strip()
    if req.pravni_osnov_obrade:
        update_row["pravni_osnov_obrade"] = req.pravni_osnov_obrade

    # CONFIDENTIAL — enkriptuj
    if req.jmbg:
        update_row["jmbg_encrypted"] = await asyncio.to_thread(encrypt_field, req.jmbg)
    if req.broj_pasosa:
        update_row["broj_pasosa_encrypted"] = await asyncio.to_thread(encrypt_field, req.broj_pasosa)
    if req.pib:
        update_row["pib_encrypted"] = await asyncio.to_thread(encrypt_field, req.pib)

    update_row["azurirano"] = _now_iso()
    update_row["datum_poslednje_aktivnosti"] = _now_iso()

    await asyncio.to_thread(
        lambda: supa.table("klijenti")
                    .update(update_row)
                    .eq("id", klijent_id)
                    .eq("user_id", user["user_id"])
                    .execute()
    )

    asyncio.create_task(log_event(
        supa=supa, user_id=user["user_id"], user_email=user.get("email", ""),
        user_role=user.get("role_str", "advokat"), akcija=Akcija.EDIT,
        entitet_id=klijent_id,
        detalji={"izmenjena_polja": _strip_confidential_from_log(update_row)},
        ip_adresa=ip,
    ))
    return {"status": "azuriran"}


@router.delete("/klijenti/{klijent_id}")
async def delete_klijent(
    klijent_id: str,
    request: Request,
):
    """
    Faza 1+5 — Soft delete (samo PARTNER rola).
    NIKAD hard DELETE na klijentima.
    """
    user = await _auth_from_request(request)
    if not can_perform(user["role"], "soft_delete_client"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Samo partner može brisati klijente.",
        )
    supa = _get_supa()
    ip = get_client_ip(request)
    now = _now_iso()

    res = await asyncio.to_thread(
        lambda: supa.table("klijenti")
                    .update({"status": "soft_deleted", "deleted_at": now, "aktivan": False})
                    .eq("id", klijent_id)
                    .eq("user_id", user["user_id"])
                    .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Klijent nije pronađen.")
    asyncio.create_task(log_event(
        supa=supa, user_id=user["user_id"], user_email=user.get("email", ""),
        user_role=user.get("role_str", "advokat"), akcija=Akcija.SOFT_DELETE,
        entitet_id=klijent_id, ip_adresa=ip,
    ))
    return {"status": "obrisan"}


@router.post("/klijenti/{klijent_id}/restore")
async def restore_klijent(
    klijent_id: str,
    request: Request,
):
    """
    Faza 1+5 — Vraća soft-deleted klijenta u aktivni status (samo PARTNER rola).
    Samo klijenti sa status='soft_deleted' mogu biti restaurirani.
    """
    user = await _auth_from_request(request)
    if not can_perform(user["role"], "soft_delete_client"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Samo partner može restaurirati obrisane klijente.",
        )
    if not await _verify_owns_klijent(_get_supa(), klijent_id, user["user_id"]):
        raise HTTPException(status_code=404, detail="Klijent nije pronađen.")

    supa = _get_supa()
    ip = get_client_ip(request)

    res = await asyncio.to_thread(
        lambda: supa.table("klijenti")
                    .update({"status": "aktivan", "deleted_at": None, "aktivan": True})
                    .eq("id", klijent_id)
                    .eq("user_id", user["user_id"])
                    .eq("status", "soft_deleted")
                    .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=404,
            detail="Klijent nije pronađen ili nije u statusu 'soft_deleted'.",
        )

    asyncio.create_task(log_event(
        supa=supa, user_id=user["user_id"], user_email=user.get("email", ""),
        user_role=user.get("role_str", "partner"), akcija=Akcija.RESTORE,
        entitet_id=klijent_id, ip_adresa=ip,
    ))
    return {"status": "restauriran"}


# ─── FAZA 3: Conflict of Interest check ──────────────────────────────────────

@router.post("/klijenti/check-conflict")
async def check_conflict(
    req: ConflictCheckReq,
    request: Request,
):
    """
    Faza 3 — Provera sukoba interesa.

    Proverava:
    a) Da li je ovo lice/firma na suprotnoj strani postojećeg predmeta
    b) Fuzzy match po imenu (dijakritika-insensitive, case-insensitive)
    c) PIB match (ako dostupan)
    """
    user = await _auth_from_request(request)
    if not can_perform(user["role"], "view_conflict_results"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nema prava za proveru konflikta.",
        )
    supa = _get_supa()
    ip = get_client_ip(request)

    name_query = _normalize_name(f"{req.ime} {req.prezime}".strip())
    firma_query = _normalize_name(req.firma) if req.firma else ""

    conflicts = []

    try:
        # Dohvati sve klijente ovog korisnika
        all_clients_res = await asyncio.to_thread(
            lambda: supa.table("klijenti")
                        .select("id, ime, prezime, firma, pib_encrypted, jmbg_encrypted")
                        .eq("user_id", user["user_id"])
                        .neq("status", "soft_deleted")
                        .execute()
        )
        all_clients = all_clients_res.data or []

        for c in all_clients:
            c_name = _normalize_name(f"{c.get('ime', '')} {c.get('prezime', '')}".strip())
            c_firma = _normalize_name(c.get("firma") or "")

            # Fuzzy name match (substring ili obrnuto)
            name_match = (
                (name_query and (name_query in c_name or c_name in name_query)) or
                (firma_query and (firma_query in c_firma or c_firma in firma_query))
            )
            if not name_match:
                continue

            # Proveri ulogu u predmetima
            pk_res = await asyncio.to_thread(
                lambda cid=c["id"]: supa.table("predmet_klijenti")
                                        .select("predmet_id, uloga_klijenta")
                                        .eq("klijent_id", cid)
                                        .execute()
            )
            for pk in (pk_res.data or []):
                uloga = pk.get("uloga_klijenta", "")
                if uloga in ("protivna_strana", "protivna_stranka", "tuzeni", "advokat_protivne"):
                    conflicts.append({
                        "klijent_id":   c["id"],
                        "tip_konflikta": "protivna_strana",
                        "detalji":       f"Klijent '{c.get('ime','')} {c.get('prezime','')}' je na suprotnoj strani predmeta {pk['predmet_id'][:8]}...",
                        "predmet_id":    pk["predmet_id"],
                    })
                elif uloga in ("stranka", "tuzilac"):
                    conflicts.append({
                        "klijent_id":   c["id"],
                        "tip_konflikta": "duplikat_ili_vec_klijent",
                        "detalji":       f"Postoji klijent sa sličnim imenom: '{c.get('ime','')} {c.get('prezime','')}' (uloga: {uloga})",
                        "predmet_id":    pk["predmet_id"],
                    })

    except Exception as e:
        logger.error("[CONFLICT] greška: %s", e)

    conflict_detected = len(conflicts) > 0

    if conflict_detected:
        asyncio.create_task(log_event(
            supa=supa, user_id=user["user_id"], user_email=user.get("email", ""),
            user_role=user.get("role_str", "advokat"), akcija=Akcija.CONFLICT_FLAGGED,
            detalji={"ime": req.ime, "broj_konflikata": len(conflicts)}, ip_adresa=ip,
        ))

    return {
        "conflict_detected": conflict_detected,
        "conflict_types":    list({c["tip_konflikta"] for c in conflicts}),
        "details":           conflicts[:10],
    }


# ─── FAZA 2: Audit log pregled ────────────────────────────────────────────────

@router.get("/klijenti/{klijent_id}/audit")
async def get_klijent_audit(
    klijent_id: str,
    request: Request,
    limit: int = 50,
):
    """Faza 2 — Audit log za klijenta (samo PARTNER)."""
    user = await _auth_from_request(request)
    if not can_perform(user["role"], "view_audit_log"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Samo partner može videti audit log.",
        )
    supa = _get_supa()
    # Horizontal access guard — klijent mora pripadati ovom korisniku
    if not await _verify_owns_klijent(supa, klijent_id, user["user_id"]):
        raise HTTPException(status_code=404, detail="Klijent nije pronađen.")

    res = await asyncio.to_thread(
        lambda: supa.table("klijenti_audit")
                    .select("*")
                    .eq("entitet_id", klijent_id)
                    .order("timestamp", desc=True)
                    .limit(min(limit, 200))
                    .execute()
    )
    return {"audit": res.data or [], "ukupno": len(res.data or [])}


# ─── FAZA 4: Dokumentacioni trezor ───────────────────────────────────────────

class DokumentUploadReq(BaseModel):
    tip_dokumenta: str = Field(..., max_length=30)
    predmet_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("tip_dokumenta")
    @classmethod
    def _tip(cls, v: str) -> str:
        allowed = {"lk", "pasos", "ugovor", "presuda", "resenje", "punomocje", "ostalo", "medicina", "finansije"}
        if v not in allowed:
            raise ValueError(f"tip_dokumenta mora biti jedan od: {sorted(allowed)}")
        return v


@router.post("/klijenti/{klijent_id}/dokumenti")
async def upload_klijent_dokument(
    klijent_id: str,
    request: Request,
    tip_dokumenta: str = "ostalo",
    predmet_id: Optional[str] = None,
):
    """
    Faza 4 — Upload dokumenta za klijenta.
    Storage key je randomizovani encrypted_blob_<uuid> — nikad originalno ime.
    Naziv fajla se enkriptuje pre čuvanja u metadata tabeli.
    """
    user = await _auth_from_request(request)
    if not can_perform(user["role"], "upload_document"):
        raise HTTPException(status_code=403, detail="Nedovoljno prava za upload dokumenata.")
    supa = _get_supa()
    # Horizontal access guard
    if not await _verify_owns_klijent(supa, klijent_id, user["user_id"]):
        raise HTTPException(status_code=404, detail="Klijent nije pronađen.")

    ip = get_client_ip(request)

    # Čitaj fajl iz multipart (direktan poziv jer smo u custom endpoint)
    form = await request.form()
    file_field = form.get("file")
    if not file_field:
        raise HTTPException(status_code=422, detail="Fajl je obavezan (multipart 'file' field).")

    raw = await file_field.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fajl je prevelik (max 10MB).")

    original_name = getattr(file_field, "filename", "") or "dokument"
    mime_type = getattr(file_field, "content_type", "application/octet-stream")

    # Randomizovani storage key — nikad originalno ime
    storage_key = generate_storage_key()

    # Enkriptuj sadržaj fajla pre upload-a
    import base64
    from security.crypto import _get_field_key
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = _get_field_key()
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        encrypted_bytes = aesgcm.encrypt(nonce, raw, None)
        upload_data = base64.urlsafe_b64encode(nonce + encrypted_bytes)
    except Exception as e:
        logger.error("[TREZOR] Enkripcija fajla neuspešna: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri enkripciji dokumenta.")

    # Upload na Supabase Storage (bucket: klijent-dokumenti)
    try:
        bucket = supa.storage.from_("klijent-dokumenti")
        await asyncio.to_thread(
            lambda: bucket.upload(
                path=storage_key,
                file=upload_data,
                file_options={"content-type": "application/octet-stream", "upsert": "false"},
            )
        )
    except Exception as e:
        logger.error("[TREZOR] Storage upload greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri upload-u: {str(e)[:100]}")

    # Enkriptuj naziv fajla
    naziv_encrypted = await asyncio.to_thread(encrypt_field, original_name)

    # Upiši metadata u klijent_dokumenti
    meta_res = await asyncio.to_thread(
        lambda: supa.table("klijent_dokumenti").insert({
            "klijent_id":        klijent_id,
            "predmet_id":        predmet_id,
            "storage_key":       storage_key,
            "tip_dokumenta":     tip_dokumenta,
            "naziv_fajla_encrypted": naziv_encrypted,
            "mime_type":         mime_type,
            "velicina":          len(raw),
            "uploaded_by":       user["user_id"],
        }).execute()
    )
    doc = meta_res.data[0] if meta_res.data else {}

    asyncio.create_task(log_event(
        supa=supa, user_id=user["user_id"], user_email=user.get("email", ""),
        user_role=user.get("role_str", "advokat"), akcija=Akcija.UPLOAD,
        entitet_tip="dokument", entitet_id=doc.get("id"),
        detalji={"tip": tip_dokumenta, "velicina": len(raw), "storage_key": storage_key[:20] + "..."},
        ip_adresa=ip,
    ))

    return {
        "status": "uploadovan",
        "doc_id": doc.get("id"),
        "tip_dokumenta": tip_dokumenta,
        "storage_key": storage_key,
    }


@router.get("/klijenti/{klijent_id}/dokumenti")
async def list_klijent_dokumenti(klijent_id: str, request: Request):
    """Faza 4 — Lista dokumenata klijenta (bez plaintext naziva)."""
    user = await _auth_from_request(request)
    supa = _get_supa()
    if not await _verify_owns_klijent(supa, klijent_id, user["user_id"]):
        raise HTTPException(status_code=404, detail="Klijent nije pronađen.")

    res = await asyncio.to_thread(
        lambda: supa.table("klijent_dokumenti")
                    .select("id, tip_dokumenta, mime_type, velicina, uploaded_at, uploaded_by")
                    .eq("klijent_id", klijent_id)
                    .is_("deleted_at", "null")
                    .order("uploaded_at", desc=True)
                    .execute()
    )
    return {"dokumenti": res.data or []}


@router.get("/klijenti/{klijent_id}/dokumenti/{doc_id}/download")
async def download_klijent_dokument(
    klijent_id: str,
    doc_id: str,
    request: Request,
):
    """
    Faza 4+6 — Preuzimanje dokumenta sa:
    1. Dekriptovanjem blob-a on-the-fly
    2. Watermark-om za PDF (user_email + timestamp + "Vindex AI poverljivo")
    3. Audit log entry MORA biti pre vraćanja fajla
    """
    user = await _auth_from_request(request)
    if not can_perform(user["role"], "download_document"):
        raise HTTPException(status_code=403, detail="Nedovoljno prava za preuzimanje dokumenata.")

    supa = _get_supa()
    ip = get_client_ip(request)

    # Horizontal access guard — potvrdi da klijent pripada ovom korisniku
    if not await _verify_owns_klijent(supa, klijent_id, user["user_id"]):
        raise HTTPException(status_code=404, detail="Klijent nije pronađen.")

    # Dohvati metadata
    meta_res = await asyncio.to_thread(
        lambda: supa.table("klijent_dokumenti")
                    .select("*")
                    .eq("id", doc_id)
                    .eq("klijent_id", klijent_id)
                    .is_("deleted_at", "null")
                    .single()
                    .execute()
    )
    if not meta_res.data:
        raise HTTPException(status_code=404, detail="Dokument nije pronađen.")
    meta = meta_res.data

    # AUDIT LOG MORA biti pre vraćanja fajla
    await log_event(
        supa=supa, user_id=user["user_id"], user_email=user.get("email", ""),
        user_role=user.get("role_str", "advokat"), akcija=Akcija.DOWNLOAD,
        entitet_tip="dokument", entitet_id=doc_id,
        detalji={"storage_key": meta["storage_key"][:20] + "..."},
        ip_adresa=ip,
    )

    # Preuzmi enkriptovani blob
    try:
        import base64
        bucket = supa.storage.from_("klijent-dokumenti")
        raw_encrypted = await asyncio.to_thread(
            lambda: bucket.download(meta["storage_key"])
        )
        # Dekriptuj
        from security.crypto import _get_field_key
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = _get_field_key()
        blob_raw = base64.urlsafe_b64decode(raw_encrypted + b"==")
        nonce, ct = blob_raw[:12], blob_raw[12:]
        aesgcm = AESGCM(key)
        file_bytes = aesgcm.decrypt(nonce, ct, None)
    except Exception as e:
        logger.error("[TREZOR] Download/decrypt greška za doc_id=%s: %s", doc_id, e)
        raise HTTPException(status_code=500, detail="Greška pri preuzimanju dokumenta.")

    mime = meta.get("mime_type", "application/octet-stream")
    naziv_raw = await asyncio.to_thread(decrypt_field, meta.get("naziv_fajla_encrypted", ""))
    naziv = naziv_raw or f"dokument_{doc_id[:8]}"

    # Watermark za PDF
    if mime == "application/pdf":
        try:
            file_bytes = await asyncio.to_thread(
                _add_pdf_watermark,
                file_bytes,
                user.get("email", ""),
            )
        except Exception as e:
            logger.warning("[TREZOR] PDF watermark greška (non-blocking): %s", e)

    return StreamingResponse(
        iter([file_bytes]),
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{naziv}"',
            "X-Vindex-Watermarked": "1",
        },
    )


def _add_pdf_watermark(pdf_bytes: bytes, user_email: str) -> bytes:
    """
    Dodaje watermark tekst na svaku stranu PDF-a.
    Tekst: "{user_email} — {timestamp} — Vindex AI poverljivo"
    """
    import io
    from datetime import datetime
    from reportlab.lib.colors import Color
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas

    try:
        import pypdf
    except ImportError:
        import pypdf as pypdf

    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    watermark_text = f"{user_email} — {timestamp_str} — Vindex AI poverljivo"

    # Kreira watermark PDF
    wm_buf = io.BytesIO()
    c = rl_canvas.Canvas(wm_buf, pagesize=A4)
    c.setFont("Helvetica", 9)
    c.setFillColor(Color(0.5, 0.5, 0.5, alpha=0.3))
    c.saveState()
    c.translate(300, 420)
    c.rotate(45)
    c.drawCentredString(0, 0, watermark_text)
    c.restoreState()
    c.save()
    wm_buf.seek(0)

    wm_pdf = pypdf.PdfReader(wm_buf)
    orig_pdf = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    writer = pypdf.PdfWriter()

    for page in orig_pdf.pages:
        wm_page = wm_pdf.pages[0]
        page.merge_page(wm_page)
        writer.add_page(page)

    out_buf = io.BytesIO()
    writer.write(out_buf)
    return out_buf.getvalue()


# ─── FAZA 7: Komunikacioni dosije ────────────────────────────────────────────

@router.post("/klijenti/{klijent_id}/komunikacija")
async def add_komunikacija(
    klijent_id: str,
    req: KomunikacijaReq,
    request: Request,
):
    """Faza 7 — Ručni unos komunikacije (bez auto-log sadržaja)."""
    user = await _auth_from_request(request)
    supa = _get_supa()
    if not await _verify_owns_klijent(supa, klijent_id, user["user_id"]):
        raise HTTPException(status_code=404, detail="Klijent nije pronađen.")
    ip = get_client_ip(request)

    res = await asyncio.to_thread(
        lambda: supa.table("klijent_komunikacija").insert({
            "klijent_id":  klijent_id,
            "tip":         req.tip,
            "datum_vreme": req.datum_vreme,
            "ucesnik_id":  user["user_id"],
            "kratak_opis": req.kratak_opis[:500],
        }).execute()
    )
    asyncio.create_task(log_event(
        supa=supa, user_id=user["user_id"], user_email=user.get("email", ""),
        user_role=user.get("role_str", "advokat"), akcija=Akcija.KOMUNIKACIJA_ADD,
        entitet_id=klijent_id, detalji={"tip": req.tip}, ip_adresa=ip,
    ))
    return {"status": "dodato", "id": (res.data or [{}])[0].get("id")}


@router.get("/klijenti/{klijent_id}/timeline")
async def get_timeline(klijent_id: str, request: Request):
    """
    Faza 7 — Timeline klijenta.
    Agregira: klijent_komunikacija + ključni predmet eventi, hronološki.
    """
    user = await _auth_from_request(request)
    supa = _get_supa()
    if not await _verify_owns_klijent(supa, klijent_id, user["user_id"]):
        raise HTTPException(status_code=404, detail="Klijent nije pronađen.")
    events: list[dict] = []

    # Komunikacija eventi
    try:
        kom_res = await asyncio.to_thread(
            lambda: supa.table("klijent_komunikacija")
                        .select("id, tip, datum_vreme, kratak_opis, ucesnik_id")
                        .eq("klijent_id", klijent_id)
                        .order("datum_vreme", desc=True)
                        .limit(100)
                        .execute()
        )
        for k in (kom_res.data or []):
            events.append({
                "id":        k.get("id"),
                "tip":       k.get("tip"),
                "datum":     k.get("datum_vreme"),
                "opis":      k.get("kratak_opis", ""),
                "izvor":     "komunikacija",
                "ikona":     _tip_ikona(k.get("tip", "")),
            })
    except Exception as e:
        logger.warning("[TIMELINE] komunikacija greška: %s", e)

    # Predmet eventi (komentari, status promene)
    try:
        pk_res = await asyncio.to_thread(
            lambda: supa.table("predmet_klijenti")
                        .select("predmet_id, uloga_klijenta, predmeti(naziv, status, created_at, updated_at)")
                        .eq("klijent_id", klijent_id)
                        .execute()
        )
        for pk in (pk_res.data or []):
            pred = pk.get("predmeti") or {}
            if pred.get("created_at"):
                events.append({
                    "tip":   "predmet_otvoren",
                    "datum": pred["created_at"],
                    "opis":  f"Predmet '{pred.get('naziv', '')}' otvoren (uloga: {pk.get('uloga_klijenta', '')})",
                    "izvor": "predmet",
                    "ikona": "📁",
                })
            if pred.get("status") in ("zatvoren", "arhiviran") and pred.get("updated_at"):
                events.append({
                    "tip":   "predmet_zatvoren",
                    "datum": pred["updated_at"],
                    "opis":  f"Predmet '{pred.get('naziv', '')}' zatvoren",
                    "izvor": "predmet",
                    "ikona": "✅",
                })
    except Exception as e:
        logger.warning("[TIMELINE] predmeti greška: %s", e)

    # Sortiraj hronološki (najnoviji prvi)
    events.sort(key=lambda e: e.get("datum") or "", reverse=True)

    # Grupiši po godini
    by_year: dict[str, list] = {}
    for ev in events:
        year = (ev.get("datum") or "")[:4] or "Nepoznato"
        by_year.setdefault(year, []).append(ev)

    return {
        "timeline": events,
        "by_year":  by_year,
        "ukupno":   len(events),
    }


def _tip_ikona(tip: str) -> str:
    return {
        "poziv": "📞", "email": "✉️", "sastanak": "🤝",
        "whatsapp": "💬", "viber": "💬", "beleska": "📝",
    }.get(tip, "📌")


# ─── FAZA 8: Arhiviranje + Retention ─────────────────────────────────────────

@router.post("/klijenti/{klijent_id}/arhiviraj")
async def arhiviraj_klijent(klijent_id: str, request: Request):
    """Faza 8 — Arhivira klijenta (status → arhiviran). Ne briše ništa."""
    user = await _auth_from_request(request)
    if not can_perform(user["role"], "archive_client"):
        raise HTTPException(status_code=403, detail="Nedovoljno prava za arhiviranje.")
    supa = _get_supa()
    ip = get_client_ip(request)

    await asyncio.to_thread(
        lambda: supa.table("klijenti")
                    .update({"status": "arhiviran", "azurirano": _now_iso()})
                    .eq("id", klijent_id)
                    .eq("user_id", user["user_id"])
                    .execute()
    )
    asyncio.create_task(log_event(
        supa=supa, user_id=user["user_id"], user_email=user.get("email", ""),
        user_role=user.get("role_str", "advokat"), akcija=Akcija.ARCHIVE,
        entitet_id=klijent_id, ip_adresa=ip,
    ))
    return {"status": "arhiviran"}


# ─── Role management endpoint ────────────────────────────────────────────────

@router.put("/api/users/{target_user_id}/role")
async def set_user_role(
    target_user_id: str,
    request: Request,
    rola: str = "advokat",
):
    """Faza 5 — Podešava rolu korisnika (samo PARTNER može menjati role)."""
    user = await _auth_from_request(request)
    if user["role"] < Role.PARTNER:
        raise HTTPException(status_code=403, detail="Samo partner može menjati role korisnika.")
    if rola not in ROLE_STR:
        raise HTTPException(status_code=422, detail=f"Nevažeća rola: {rola}. Dozvoljeno: {list(ROLE_STR.keys())}")

    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("user_roles").upsert({
            "user_id": target_user_id,
            "rola":    rola,
        }, on_conflict="user_id").execute()
    )
    return {"status": "postavljeno", "user_id": target_user_id, "rola": rola}


@router.get("/api/my-role")
async def get_my_role(request: Request):
    """Vraća rolu prijavljenog korisnika."""
    user = await _auth_from_request(request)
    return {
        "role":     user.get("role_str", "advokat"),
        "role_int": int(user.get("role", DEFAULT_ROLE)),
    }


# ─── Intake Wizard ────────────────────────────────────────────────────────────


class IntakeWizardReq(BaseModel):
    tip_predmeta: str = Field(..., description="radni/civilni/krivicni/opsti/porodični/privredni")
    opis_situacije: str = Field(..., min_length=20, max_length=2000)
    tip_klijenta: str = Field(default="fizicko_lice", description="fizicko_lice/pravno_lice")
    hitnost: str = Field(default="normalno", description="hitno/normalno/planiranje")


@router.post("/klijenti/intake-wizard")
async def intake_wizard(req: IntakeWizardReq, request: Request):
    """
    AI onboarding assistant — za dati tip predmeta i opis situacije vraća:
    - Preporučena dokumenta za prikupljanje
    - Ključni rokovi koje treba proveriti
    - Relevantni zakoni (zakon + član)
    - Moguće pravne zahteve / tužbene osnove
    - Potrebne informacije za dalje
    """
    user = await _auth_from_request(request)
    import openai as _oai

    client = _oai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

    system_prompt = (
        "Ti si AI pravni asistent specijalizovan za srpsko pravo. "
        "Daje se tip predmeta i opis situacije novog klijenta. "
        "Odgovori ISKLJUČIVO u JSON formatu bez ikakvog teksta van JSON-a. "
        "Struktura odgovora:\n"
        "{\n"
        '  "dokumenta": [{"naziv": str, "razlog": str}],\n'
        '  "rokovi": [{"naziv": str, "trajanje": str, "zakon": str}],\n'
        '  "zakoni": [{"zakon": str, "clan": str, "kratak_opis": str}],\n'
        '  "zahtevi": [{"naziv": str, "opis": str}],\n'
        '  "pitanja_za_klijenta": [str]\n'
        "}\n"
        "Koristi isključivo važeće srpske propise. Maksimalno 5 stavki po kategoriji."
    )

    user_msg = (
        f"Tip predmeta: {req.tip_predmeta}\n"
        f"Tip klijenta: {req.tip_klijenta}\n"
        f"Hitnost: {req.hitnost}\n\n"
        f"Opis situacije:\n{req.opis_situacije}"
    )

    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        import json as _json
        preporuke = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        logger.error("[INTAKE-WIZARD] OpenAI greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri generisanju preporuka.")

    asyncio.create_task(log_event(
        supa=_get_supa(),
        user_id=user["user_id"],
        user_email=user.get("email", ""),
        user_role=user.get("role_str", "advokat"),
        akcija=Akcija.VIEW,
        entitet_tip="intake_wizard",
        entitet_id=None,
        detalji={"tip_predmeta": req.tip_predmeta, "hitnost": req.hitnost},
        ip_adresa=get_client_ip(request),
    ))

    return {
        "tip_predmeta": req.tip_predmeta,
        "preporuke": preporuke,
    }


# ─── Internal helpers ─────────────────────────────────────────────────────────

async def _auth_from_request(request: Request) -> dict:
    """Autentifikuje korisnika iz request-a i dodaje rolu."""
    from fastapi.security import HTTPBearer as _Bearer
    bearer = _Bearer(auto_error=False)
    creds = await bearer(request)
    if not creds:
        raise HTTPException(status_code=401, detail="Prijava je obavezna.")
    payload = await asyncio.to_thread(_verify_token, creds.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Nevažeći token.")
    email = (
        payload.get("email") or
        payload.get("user_metadata", {}).get("email") or ""
    )
    user = {"user_id": payload.get("sub"), "email": email}
    return await _enrich_user(user)


async def _update_activity(supa, klijent_id: str, user_id: str) -> None:
    try:
        await asyncio.to_thread(
            lambda: supa.table("klijenti")
                        .update({"datum_poslednje_aktivnosti": _now_iso()})
                        .eq("id", klijent_id)
                        .eq("user_id", user_id)
                        .execute()
        )
    except Exception:
        pass
