# -*- coding: utf-8 -*-
"""
Vindex AI — routers/sef.py

SEF (Sistem E-Faktura) — integracija sa srpskim sistemom za e-fakture.
Dokumentacija SEF API: https://efaktura.mfin.gov.rs/api/publicApi

SQL migracija (pokrenuti u Supabase SQL editoru):
─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.sef_podesavanja (
    user_id     UUID PRIMARY KEY REFERENCES auth.users(id),
    api_key     TEXT NOT NULL,
    seller_pib  VARCHAR(9) NOT NULL,
    seller_naziv TEXT NOT NULL,
    seller_adresa TEXT DEFAULT '',
    seller_mesto  TEXT DEFAULT 'Beograd',
    updated_at  TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.sef_podesavanja ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sef_own" ON public.sef_podesavanja USING (user_id = auth.uid());

CREATE TABLE IF NOT EXISTS public.sef_log (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id),
    faktura_id  UUID NOT NULL,
    sef_id      BIGINT,
    sef_status  VARCHAR(50) DEFAULT 'pending',
    greska      TEXT,
    xml_bytes   INT,
    poslato_at  TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.sef_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sef_log_own" ON public.sef_log USING (user_id = auth.uid());
─────────────────────────────────────────────────────────────────────────

Endpoints:
GET  /api/sef/podesavanja            — dohvata SEF konfiguraciju (API key maskiran)
POST /api/sef/podesavanja            — čuva SEF API key i podatke o prodavcu
POST /api/sef/posalji/{faktura_id}   — generiše UBL XML i šalje na SEF
GET  /api/sef/log/{faktura_id}       — istorija slanja za fakturu
GET  /api/sef/pregled-xml/{faktura_id} — preuzima UBL XML bez slanja (sandbox/preview)
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response as _Resp
from pydantic import BaseModel, Field, field_validator

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter
from security.crypto import encrypt_field, decrypt_field

logger = logging.getLogger("vindex.sef")
router = APIRouter(prefix="/api/sef", tags=["sef"])

SEF_API_BASE = "https://efaktura.mfin.gov.rs/api/publicApi"
SEF_INVOICE_ENDPOINT = f"{SEF_API_BASE}/SalesInvoice"


# ─── Pydantic modeli ──────────────────────────────────────────────────────────

class SefPodesavanjaReq(BaseModel):
    api_key:       Optional[str] = Field(default=None, min_length=10, max_length=500)
    seller_pib:    str = Field(..., min_length=9, max_length=9)
    seller_naziv:  str = Field(..., min_length=2, max_length=200)
    seller_adresa: str = Field(default="", max_length=300)
    seller_mesto:  str = Field(default="Beograd", max_length=100)

    @field_validator("seller_pib")
    @classmethod
    def _val_pib(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) != 9:
            raise ValueError("PIB mora biti tačno 9 cifara")
        return v


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _db(fn):
    return await asyncio.to_thread(fn)


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return key[:4] + "***" + key[-4:]


def _sef_post(api_key: str, xml_bytes: bytes, filename: str) -> dict:
    """
    Šalje UBL XML na SEF API kao multipart/form-data.
    Blokira — pozivati unutar asyncio.to_thread.
    """
    import email.mime.multipart as _mm

    boundary = "VindexSEFBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="invoice"; filename="{filename}"\r\n'
        f"Content-Type: application/xml\r\n\r\n"
    ).encode("utf-8") + xml_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Authorization": f"ApiKey {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }

    req = urllib.request.Request(
        SEF_INVOICE_ENDPOINT,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return {"ok": True, "data": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            err_data = json.loads(raw)
        except Exception:
            err_data = {"raw": raw}
        logger.warning("[SEF] HTTP %d: %s", e.code, raw[:300])
        return {"ok": False, "status_code": e.code, "error": err_data}
    except urllib.error.URLError as e:
        logger.warning("[SEF] URL error: %s", e.reason)
        return {"ok": False, "error": str(e.reason)}
    except Exception as e:
        logger.exception("[SEF] Unexpected error")
        return {"ok": False, "error": str(e)}


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/podesavanja")
@limiter.limit("30/minute")
async def get_sef_podesavanja(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Dohvata SEF konfiguraciju. API key je maskiran."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await _db(lambda: supa.table("sef_podesavanja")
                      .select("seller_pib,seller_naziv,seller_adresa,seller_mesto,api_key,updated_at")
                      .eq("user_id", uid)
                      .maybe_single()
                      .execute())
        if not r.data:
            return {"konfigurisano": False, "podaci": None}
        d = r.data
        raw_key = d.get("api_key", "")
        try:
            plain_key = decrypt_field(raw_key) if raw_key.startswith("enc_v1:") else raw_key
        except Exception:
            plain_key = raw_key
        return {
            "konfigurisano":  True,
            "podaci": {
                "seller_pib":    d.get("seller_pib", ""),
                "seller_naziv":  d.get("seller_naziv", ""),
                "seller_adresa": d.get("seller_adresa", ""),
                "seller_mesto":  d.get("seller_mesto", ""),
                "api_key_preview": _mask_key(plain_key),
                "updated_at":    d.get("updated_at"),
            },
        }
    except Exception as e:
        logger.warning("[SEF] podesavanja get greška: %s", e)
        return {"konfigurisano": False, "podaci": None, "napomena": "Tabela sef_podesavanja ne postoji — pokrenite SQL migraciju."}


@router.post("/podesavanja")
@limiter.limit("10/minute")
async def post_sef_podesavanja(
    body: SefPodesavanjaReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Čuva SEF API key i podatke o prodavcu (upsertion)."""
    uid  = user["user_id"]
    supa = _get_supa()

    # Ako api_key nije poslat, zadržati postojeći enkriptovani
    final_api_key_enc = None
    if not body.api_key:
        try:
            existing = await _db(lambda: supa.table("sef_podesavanja")
                                 .select("api_key")
                                 .eq("user_id", uid)
                                 .maybe_single()
                                 .execute())
            if existing.data and existing.data.get("api_key"):
                final_api_key_enc = existing.data["api_key"]
            else:
                raise HTTPException(status_code=422, detail="SEF API ključ je obavezan pri prvom čuvanju podešavanja.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DB greška pri proveri API ključa: {e}")
    else:
        final_api_key_enc = encrypt_field(body.api_key)

    row = {
        "user_id":       uid,
        "api_key":       final_api_key_enc,
        "seller_pib":    body.seller_pib,
        "seller_naziv":  body.seller_naziv,
        "seller_adresa": body.seller_adresa,
        "seller_mesto":  body.seller_mesto,
        "updated_at":    "now()",
    }

    try:
        r = await _db(lambda: supa.table("sef_podesavanja").upsert(row, on_conflict="user_id").execute())
        if not r.data:
            raise HTTPException(status_code=500, detail="Čuvanje SEF podešavanja nije uspelo.")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("[SEF] podesavanja upsert greška: %s", e)
        raise HTTPException(status_code=500, detail=f"DB greška: {e}")

    logger.info("[SEF] podesavanja saved uid=%.8s pib=%s", uid, body.seller_pib)
    return {"ok": True, "seller_pib": body.seller_pib, "seller_naziv": body.seller_naziv}


@router.get("/pregled-xml/{faktura_id}")
@limiter.limit("20/minute")
async def get_pregled_xml(
    faktura_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Generiše i preuzima UBL XML bez slanja na SEF (sandbox / preview)."""
    uid  = user["user_id"]
    supa = _get_supa()

    faktura, entries, sef_pod = await asyncio.gather(
        _db(lambda: supa.table("fakture").select("*").eq("id", faktura_id).eq("user_id", uid).maybe_single().execute()),
        _db(lambda: supa.table("billing_entries").select("*").eq("faktura_id", faktura_id).eq("user_id", uid).order("datum").execute()),
        _db(lambda: supa.table("sef_podesavanja").select("seller_pib,seller_naziv,seller_adresa,seller_mesto").eq("user_id", uid).maybe_single().execute()),
    )

    if not faktura.data:
        raise HTTPException(status_code=404, detail="Faktura nije pronađena.")

    if not sef_pod.data:
        raise HTTPException(status_code=400, detail="SEF podešavanja nisu konfigurisana. Unesite PIB i ostale podatke u SEF sekciji.")

    pod = sef_pod.data
    from sef_ubl import generiši_ubl_xml
    xml_bytes = generiši_ubl_xml(
        faktura   = faktura.data,
        entries   = entries.data or [],
        seller_pib    = pod.get("seller_pib", ""),
        seller_naziv  = pod.get("seller_naziv", ""),
        seller_adresa = pod.get("seller_adresa", ""),
        seller_mesto  = pod.get("seller_mesto", "Beograd"),
    )

    broj = (faktura.data.get("broj_fakture") or "faktura").replace("/", "-")
    filename = f"sef_{broj}.xml"
    return _Resp(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/posalji/{faktura_id}")
@limiter.limit("10/minute")
async def sef_posalji(
    faktura_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Generiše UBL 2.1 XML i šalje fakturu na SEF sistem.

    Faktura mora biti u statusu 'izdata' (ne 'nacrt').
    Klijent mora imati PIB (klijent_pib) u fakturi za B2B transakcije.
    SEF API podešavanja moraju biti prethodno konfigurisana.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    faktura_r, entries_r, pod_r = await asyncio.gather(
        _db(lambda: supa.table("fakture").select("*").eq("id", faktura_id).eq("user_id", uid).maybe_single().execute()),
        _db(lambda: supa.table("billing_entries").select("*").eq("faktura_id", faktura_id).eq("user_id", uid).order("datum").execute()),
        _db(lambda: supa.table("sef_podesavanja").select("*").eq("user_id", uid).maybe_single().execute()),
    )

    if not faktura_r.data:
        raise HTTPException(status_code=404, detail="Faktura nije pronađena.")

    faktura = faktura_r.data
    entries = entries_r.data or []

    if faktura.get("status") == "nacrt":
        raise HTTPException(status_code=400, detail="Faktura je u statusu 'nacrt'. Izdajte fakturu pre slanja na SEF.")

    if faktura.get("status") == "stornirana":
        raise HTTPException(status_code=400, detail="Stornirana faktura ne može biti poslata na SEF.")

    if not pod_r.data:
        raise HTTPException(status_code=400, detail="SEF podešavanja nisu konfigurisana. Unesite PIB i API ključ u SEF sekciji.")

    pod = pod_r.data
    _raw_key = pod.get("api_key", "")
    if not _raw_key:
        raise HTTPException(status_code=400, detail="SEF API ključ nije podešen.")
    try:
        api_key = decrypt_field(_raw_key) if _raw_key.startswith("enc_v1:") else _raw_key
    except Exception:
        api_key = _raw_key

    if not faktura.get("klijent_pib"):
        raise HTTPException(status_code=400, detail="Klijent nema PIB u fakturi. SEF zahteva PIB primaoca za B2B fakture.")

    # Dedup: sprečiti duple slanje — proveri da li faktura već ima Sent/Approved status u sef_log
    try:
        dedup_r = await _db(lambda: supa.table("sef_log")
                            .select("id,sef_status")
                            .eq("user_id", uid)
                            .eq("faktura_id", faktura_id)
                            .in_("sef_status", ["Sent", "Approved"])
                            .limit(1)
                            .execute())
        if dedup_r.data:
            raise HTTPException(status_code=409, detail="Faktura je već poslata na SEF.")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("[SEF] dedup provera greška: %s", e)

    # Generate UBL XML
    from sef_ubl import generiši_ubl_xml
    try:
        xml_bytes = generiši_ubl_xml(
            faktura       = faktura,
            entries       = entries,
            seller_pib    = pod.get("seller_pib", ""),
            seller_naziv  = pod.get("seller_naziv", ""),
            seller_adresa = pod.get("seller_adresa", ""),
            seller_mesto  = pod.get("seller_mesto", "Beograd"),
        )
    except Exception as e:
        logger.exception("[SEF] UBL generisanje neuspelo faktura=%s", faktura_id)
        raise HTTPException(status_code=500, detail=f"Generisanje UBL XML nije uspelo: {e}")

    broj = (faktura.get("broj_fakture") or "faktura").replace("/", "-")
    filename = f"vindex_faktura_{broj}.xml"

    # Send to SEF
    sef_resp = await asyncio.to_thread(_sef_post, api_key, xml_bytes, filename)

    sef_id     = None
    sef_status = "greška"
    greška_txt = None

    if sef_resp.get("ok"):
        data = sef_resp.get("data") or {}
        sef_id     = data.get("InvoiceId") or data.get("invoiceId")
        sef_status = data.get("Status") or data.get("status") or "Sent"
        logger.info("[SEF] faktura=%s sef_id=%s status=%s", faktura_id, sef_id, sef_status)
    else:
        err = sef_resp.get("error") or {}
        if isinstance(err, dict):
            model_errors = err.get("ModelErrors") or err.get("modelErrors") or {}
            greška_txt = "; ".join(
                f"{k}: {', '.join(v) if isinstance(v, list) else v}"
                for k, v in model_errors.items()
            ) or str(err)[:300]
        else:
            greška_txt = str(err)[:300]
        logger.warning("[SEF] slanje neuspelo faktura=%s: %s", faktura_id, greška_txt)

    # Log to DB
    log_row = {
        "user_id":    uid,
        "faktura_id": faktura_id,
        "sef_id":     sef_id,
        "sef_status": sef_status,
        "greska":     greška_txt,
        "xml_bytes":  len(xml_bytes),
    }
    try:
        await _db(lambda: supa.table("sef_log").insert(log_row).execute())
    except Exception as e:
        logger.warning("[SEF] log insert greška: %s", e)

    if not sef_resp.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=f"SEF je vratio grešku: {greška_txt or 'Nepoznata greška'}",
        )

    return {
        "ok":           True,
        "sef_id":       sef_id,
        "sef_status":   sef_status,
        "faktura_id":   faktura_id,
        "broj_fakture": faktura.get("broj_fakture"),
        "xml_bytes":    len(xml_bytes),
        "poruka":       f"Faktura br. {faktura.get('broj_fakture')} je uspešno poslata na SEF. ID: {sef_id}",
    }


@router.get("/status/{faktura_id}")
@limiter.limit("30/minute")
async def get_sef_status(
    faktura_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Dohvata poslednji SEF status za datu fakturu iz sef_log tabele."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        log_r = await _db(lambda: supa.table("sef_log")
                          .select("id,sef_id,sef_status,greska,poslato_at")
                          .eq("user_id", uid)
                          .eq("faktura_id", faktura_id)
                          .order("poslato_at", desc=True)
                          .limit(1)
                          .maybe_single()
                          .execute())
    except Exception as e:
        logger.warning("[SEF] status fetch greška: %s", e)
        raise HTTPException(status_code=500, detail=f"DB greška: {e}")

    if not log_r.data:
        raise HTTPException(status_code=404, detail="Faktura nije poslata na SEF.")

    log_row = log_r.data
    return {
        "faktura_id": faktura_id,
        "sef_id":     log_row.get("sef_id"),
        "sef_status": log_row.get("sef_status"),
        "greska":     log_row.get("greska"),
        "poslato_at": log_row.get("poslato_at"),
    }


@router.get("/log/{faktura_id}")
@limiter.limit("30/minute")
async def get_sef_log(
    faktura_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Istorija SEF slanja za datu fakturu."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await _db(lambda: supa.table("sef_log")
                      .select("sef_id,sef_status,greska,xml_bytes,poslato_at")
                      .eq("user_id", uid)
                      .eq("faktura_id", faktura_id)
                      .order("poslato_at", desc=True)
                      .limit(20)
                      .execute())
        return {"log": r.data or [], "faktura_id": faktura_id}
    except Exception as e:
        logger.warning("[SEF] log fetch greška: %s", e)
        return {"log": [], "faktura_id": faktura_id, "napomena": "sef_log tabela ne postoji — pokrenite SQL migraciju."}
