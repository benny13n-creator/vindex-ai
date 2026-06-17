# -*- coding: utf-8 -*-
"""
Vindex AI — routers/client_portal.py

Klijentski portal — read-only pogled na predmet + upload dokumenata.

SQL migracija (pokrenuti JEDNOM u Supabase SQL editor):
  migrations/010_client_portal.sql  — tabela client_portal_tokens
  migrations/013_client_portal_uploads.sql — tabela client_portal_uploads

Endpoints:
  POST   /api/client-portal/token/{predmet_id}      — advokat generiše link za klijenta
  GET    /api/client-portal/tokens/{predmet_id}      — lista aktivnih tokena
  DELETE /api/client-portal/token/{token_id}         — opoziv tokena
  GET    /api/client-portal/view                     — klijent gleda predmet (bez auth)
  POST   /api/client-portal/dokument                 — klijent upload fajla (bez auth)
  GET    /api/client-portal/uploads/{predmet_id}     — advokat vidi uploadovane fajlove
  PATCH  /api/client-portal/uploads/{upload_id}/pregledano — advokat označi kao pregledano
  DELETE /api/client-portal/uploads/{upload_id}      — advokat briše upload

Bezbednost:
  - Token = HMAC-SHA256(SECRET_KEY, "{predmet_id}:{user_id}:{exp_unix}") enkodiran u hex
  - Čuva se samo SHA-256 hash tokena u DB (kao password hash → čak i DB leak ne otkriva token)
  - Backend verifikuje: HMAC validan + predmet_id u tokenu mora biti isti → nema IDOR
  - Klijent ne vidi: user_id, billing, šifrovana polja (JMBG/pasoš), napomene ročišta (interne)
  - Advokat može opozvati token u bilo kom trenutku (is_active = false)
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.client_portal")
router = APIRouter(tags=["client-portal"])

_DEFAULT_VALJANOST_DANA = 30
_MAX_VALJANOST_DANA     = 90


# ─── Token helpers ────────────────────────────────────────────────────────────

def _secret_key() -> bytes:
    key = os.getenv("SECRET_KEY", "").strip()
    if not key:
        raise RuntimeError("SECRET_KEY env var nije postavljen")
    return key.encode()


def _generiši_token(predmet_id: str, user_id: str, exp_unix: int) -> str:
    """Generiše HMAC-SHA256 token. Nikad ne čuva u DB — čuva se samo hash."""
    msg = f"{predmet_id}:{user_id}:{exp_unix}".encode()
    sig = hmac.new(_secret_key(), msg, hashlib.sha256).hexdigest()
    payload = f"{predmet_id}:{user_id}:{exp_unix}"
    import base64
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{encoded}.{sig}"


def _parsiraj_token(token: str) -> tuple[str, str, int, str]:
    """Parsira token → (predmet_id, user_id, exp_unix, sig). Baca ValueError ako malformirano."""
    import base64
    try:
        parts = token.split(".")
        if len(parts) != 2:
            raise ValueError("token format neispravan")
        encoded, sig = parts
        payload = base64.urlsafe_b64decode(encoded.encode() + b"==").decode()
        predmet_id, user_id, exp_str = payload.split(":")
        exp_unix = int(exp_str)
        return predmet_id, user_id, exp_unix, sig
    except Exception:
        raise ValueError("token nije validan")


def _verifikuj_token(token: str) -> tuple[str, str]:
    """
    Verifikuje HMAC potpis + rok trajanja.
    Vraća (predmet_id, advokat_user_id) ako validan.
    Baca HTTPException 401 ako nije.
    """
    try:
        predmet_id, user_id, exp_unix, sig = _parsiraj_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Nevažeći token.")

    if time.time() > exp_unix:
        raise HTTPException(status_code=401, detail="Token je istekao.")

    msg = f"{predmet_id}:{user_id}:{exp_unix}".encode()
    ocekivani = hmac.new(_secret_key(), msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, ocekivani):
        raise HTTPException(status_code=401, detail="Nevažeći token.")

    return predmet_id, user_id


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ─── Modeli ───────────────────────────────────────────────────────────────────

class GeneriišiTokenReq(BaseModel):
    klijent_email:  Optional[str] = Field(default=None, max_length=200)
    valjanost_dana: int           = Field(default=_DEFAULT_VALJANOST_DANA, ge=1, le=_MAX_VALJANOST_DANA)


# ─── Advokat endpoints ────────────────────────────────────────────────────────

@router.post("/api/client-portal/token/{predmet_id}")
@limiter.limit("10/minute")
async def generiši_portal_token(
    predmet_id: str,
    body: GeneriišiTokenReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Advokat generiše share link za klijenta. Token važi `valjanost_dana` dana."""
    uid  = user["user_id"]
    supa = _get_supa()

    # Verifikuj vlasništvo predmeta
    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id, naziv, status")
            .eq("id", predmet_id)
            .eq("user_id", uid)
            .execute()
    )
    if not pred_r.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    exp_unix = int(time.time()) + body.valjanost_dana * 86400
    token    = _generiši_token(predmet_id, uid, exp_unix)
    t_hash   = _token_hash(token)
    exp_iso  = datetime.fromtimestamp(exp_unix, tz=timezone.utc).isoformat()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("client_portal_tokens").insert({
                "predmet_id":    predmet_id,
                "user_id":       uid,
                "token_hash":    t_hash,
                "klijent_email": body.klijent_email,
                "is_active":     True,
                "expires_at":    exp_iso,
            }).execute()
        )
        token_id = r.data[0]["id"] if r.data else None
    except Exception as exc:
        logger.error("[CLIENT_PORTAL] DB greška pri čuvanju tokena: %s", exc)
        raise HTTPException(status_code=500, detail="Greška pri generisanju tokena.")

    base_url = os.getenv("APP_BASE_URL", "https://vindex-ai.up.railway.app")
    portal_url = f"{base_url}/portal?token={token}"

    logger.info("[CLIENT_PORTAL] Token kreiran: predmet=%s advokat=%.8s token_id=%s exp=%s",
                predmet_id, uid, token_id, exp_iso)
    return {
        "ok":         True,
        "token":      token,
        "token_id":   token_id,
        "portal_url": portal_url,
        "expires_at": exp_iso,
        "predmet_naziv": pred_r.data[0]["naziv"],
    }


@router.get("/api/client-portal/tokens/{predmet_id}")
@limiter.limit("30/minute")
async def lista_portal_tokena(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Lista aktivnih tokena za predmet (advokat vidi sve koje je kreirao)."""
    uid  = user["user_id"]
    supa = _get_supa()

    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id")
            .eq("id", predmet_id)
            .eq("user_id", uid)
            .execute()
    )
    if not pred_r.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("client_portal_tokens")
                .select("id, klijent_email, is_active, created_at, expires_at")
                .eq("predmet_id", predmet_id)
                .eq("user_id", uid)
                .order("created_at", desc=True)
                .limit(20)
                .execute()
        )
        tokeni = r.data or []
    except Exception as exc:
        logger.warning("[CLIENT_PORTAL] DB greška lista tokena: %s", exc)
        return {"tokeni": [], "napomena": "Tabela client_portal_tokens ne postoji — pokrenite SQL migraciju."}

    return {"tokeni": tokeni}


@router.delete("/api/client-portal/token/{token_id}")
@limiter.limit("20/minute")
async def opozovi_portal_token(
    token_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Opoziva token (is_active = false). Klijent više ne može pristupiti."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("client_portal_tokens")
                .update({"is_active": False})
                .eq("id", token_id)
                .eq("user_id", uid)
                .execute()
        )
        if not r.data:
            raise HTTPException(status_code=404, detail="Token nije pronađen.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[CLIENT_PORTAL] Greška opoziva tokena: %s", exc)
        raise HTTPException(status_code=500, detail="Greška pri opozivanju tokena.")

    logger.info("[CLIENT_PORTAL] Token opozvan: id=%s advokat=%.8s", token_id, uid)
    return {"ok": True, "token_id": token_id, "is_active": False}


# ─── Klijent endpoint (bez auth) ──────────────────────────────────────────────

@router.get("/api/client-portal/view")
@limiter.limit("30/minute")
async def client_portal_view(
    request: Request,
    x_portal_token: Optional[str] = Header(default=None, alias="X-Portal-Token"),
):
    """
    Klijent pregledava predmet. Ne zahteva login — koristi portal token.
    Token se šalje u X-Portal-Token headeru (ne u URL-u da se smanji log leakage).
    """
    if not x_portal_token:
        raise HTTPException(status_code=401, detail="X-Portal-Token header je obavezan.")

    predmet_id, advokat_uid = _verifikuj_token(x_portal_token)
    t_hash = _token_hash(x_portal_token)
    supa   = _get_supa()

    # Proveri da je token aktivan u DB (opoziv)
    try:
        tok_r = await asyncio.to_thread(
            lambda: supa.table("client_portal_tokens")
                .select("id, is_active, expires_at")
                .eq("token_hash", t_hash)
                .eq("predmet_id", predmet_id)
                .maybe_single()
                .execute()
        )
        tok_data = tok_r.data if tok_r else None
        if not tok_data:
            raise HTTPException(status_code=401, detail="Token nije validan.")
        if not tok_data.get("is_active", False):
            raise HTTPException(status_code=401, detail="Token je opozvan od strane advokata.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[CLIENT_PORTAL] DB provera tokena nije uspela: %s — nastavljamo", exc)

    # Dohvati predmet, hronologiju i ročišta paralelno
    predmet_r, hron_r, roc_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("naziv, opis, tip, status, created_at")
                .eq("id", predmet_id)
                .eq("user_id", advokat_uid)
                .maybe_single()
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_hronologija")
                .select("dogadjaj, datum, datum_iso, akter, vaznost")
                .eq("predmet_id", predmet_id)
                .eq("user_id", advokat_uid)
                .order("datum_iso", desc=False)
                .limit(50)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("sud, datum, vreme, sudnica, broj_predmeta_suda, status")
                .eq("predmet_id", predmet_id)
                .eq("user_id", advokat_uid)
                .order("datum", desc=False)
                .limit(20)
                .execute()
        ),
    )

    predmet = predmet_r.data if predmet_r else None
    if not predmet:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    # Filter hronologije — skrivamo internu tehničku vaznost "interni" (ako postoji)
    # i dogadjaje koji počinju "[INTERNI]" prefiksom (konvencija za buduće interne beleške)
    hron_raw = hron_r.data if hron_r else []
    hron_filtered = [
        h for h in hron_raw
        if not (h.get("dogadjaj") or "").startswith("[INTERNI]")
        and h.get("vaznost") != "interni"
    ]

    roc_raw = roc_r.data if roc_r else []
    # Buduca ročišta (status=zakazano) i prošla (status=odrzano) — sve sem otkazanih
    roc_vidljiva = [r for r in roc_raw if r.get("status") != "otkazano"]

    return {
        "predmet": {
            "naziv":      predmet.get("naziv"),
            "opis":       predmet.get("opis"),
            "tip":        predmet.get("tip"),
            "status":     predmet.get("status"),
            "kreiran":    predmet.get("created_at"),
        },
        "hronologija": hron_filtered,
        "rocista":     roc_vidljiva,
        "token_expires_at": tok_data.get("expires_at") if tok_data else None,
    }


# ─── Klijent: upload dokumenta ────────────────────────────────────────────────

_DOZVOLJENI_TIPOVI = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
}
_MAX_VELICINA_MB = 10
_MAX_VELICINA_B  = _MAX_VELICINA_MB * 1024 * 1024


@router.post("/api/client-portal/dokument")
@limiter.limit("5/minute")
async def client_portal_upload(
    request: Request,
    fajl:    UploadFile        = File(...),
    napomena: Optional[str]    = Form(default=None, max_length=500),
    x_portal_token: Optional[str] = Header(default=None, alias="X-Portal-Token"),
):
    """
    Klijent upload-uje dokument putem portal tokena. Ne zahteva login.
    Fajl se čuva u Supabase Storage bucket 'portal-uploads'.
    Advokat vidi upload u workspace-u (GET /api/client-portal/uploads/{predmet_id}).

    Ograničenja: maks 10 MB, dozvoljeni tipovi: PDF, DOCX, DOC, JPG, PNG, WEBP, TXT.
    """
    if not x_portal_token:
        raise HTTPException(status_code=401, detail="X-Portal-Token header je obavezan.")

    predmet_id, advokat_uid = _verifikuj_token(x_portal_token)
    t_hash = _token_hash(x_portal_token)
    supa   = _get_supa()

    # Proveri aktivan token u DB
    try:
        tok_r = await asyncio.to_thread(
            lambda: supa.table("client_portal_tokens")
                .select("id, is_active")
                .eq("token_hash", t_hash)
                .eq("predmet_id", predmet_id)
                .maybe_single()
                .execute()
        )
        tok_data = tok_r.data if tok_r else None
        if not tok_data or not tok_data.get("is_active"):
            raise HTTPException(status_code=401, detail="Token nije validan ili je opozvan.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[PORTAL_UPLOAD] DB token provera greška: %s", exc)
        raise HTTPException(status_code=500, detail="Interna greška — pokušajte ponovo.")

    # Validacija fajla
    content_type = fajl.content_type or "application/octet-stream"
    if content_type not in _DOZVOLJENI_TIPOVI:
        raise HTTPException(
            status_code=415,
            detail=f"Tip fajla nije dozvoljen. Dozvoljen: PDF, DOCX, JPG, PNG, WEBP, TXT."
        )

    sadrzaj = await fajl.read()
    if len(sadrzaj) > _MAX_VELICINA_B:
        raise HTTPException(
            status_code=413,
            detail=f"Fajl je prevelik. Maks {_MAX_VELICINA_MB} MB."
        )
    if len(sadrzaj) == 0:
        raise HTTPException(status_code=422, detail="Fajl je prazan.")

    import re
    bezbedan_naziv = re.sub(r"[^\w\-\. ]", "_", fajl.filename or "dokument")[:100]
    import uuid as _uuid_mod
    storage_path = f"{advokat_uid}/{predmet_id}/{_uuid_mod.uuid4().hex}_{bezbedan_naziv}"

    # Upload u Supabase Storage
    try:
        await asyncio.to_thread(
            lambda: supa.storage.from_("portal-uploads").upload(
                path=storage_path,
                file=sadrzaj,
                file_options={"content-type": content_type},
            )
        )
    except Exception as exc:
        logger.error("[PORTAL_UPLOAD] Storage upload greška: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Greška pri čuvanju fajla. Kontaktirajte advokata direktno."
        )

    # Snimi metadata u DB
    try:
        ins_r = await asyncio.to_thread(
            lambda: supa.table("client_portal_uploads").insert({
                "predmet_id":      predmet_id,
                "advokat_user_id": advokat_uid,
                "token_hash":      t_hash,
                "fajl_naziv":      bezbedan_naziv,
                "fajl_velicina":   len(sadrzaj),
                "content_type":    content_type,
                "storage_path":    storage_path,
                "napomena":        (napomena or "")[:500],
                "pregledano":      False,
            }).execute()
        )
        upload_id = ins_r.data[0]["id"] if ins_r.data else None
    except Exception as exc:
        logger.error("[PORTAL_UPLOAD] DB insert greška: %s — fajl u storage ali nema zapisa", exc)
        upload_id = None

    logger.info("[PORTAL_UPLOAD] predmet=%s velicina=%d naziv=%r", predmet_id, len(sadrzaj), bezbedan_naziv)
    return {
        "ok":        True,
        "upload_id": upload_id,
        "poruka":    "Dokument je uspešno dostavljen advokatu.",
        "fajl_naziv": bezbedan_naziv,
    }


# ─── Advokat: pregled i upravljanje uploadima ─────────────────────────────────

@router.get("/api/client-portal/uploads/{predmet_id}")
@limiter.limit("30/minute")
async def client_portal_lista_uploada(
    predmet_id: str,
    request:    Request,
    user:       dict = Depends(get_current_user),
):
    """Advokat vidi sve dokumente koje je klijent uploadovao za predmet."""
    uid  = user["user_id"]
    supa = _get_supa()

    # Verifikuj vlasništvo predmeta
    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id")
            .eq("id", predmet_id)
            .eq("user_id", uid)
            .execute()
    )
    if not pred_r.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    try:
        upl_r = await asyncio.to_thread(
            lambda: supa.table("client_portal_uploads")
                .select("id, fajl_naziv, fajl_velicina, content_type, storage_path, napomena, pregledano, uploaded_at")
                .eq("predmet_id", predmet_id)
                .eq("advokat_user_id", uid)
                .order("uploaded_at", desc=True)
                .limit(50)
                .execute()
        )
        uploadi = upl_r.data or []
    except Exception as exc:
        logger.warning("[PORTAL_UPLOADS] DB greška: %s", exc)
        return {"uploadi": [], "napomena": "Tabela client_portal_uploads ne postoji — pokrenite migraciju 013."}

    # Generisi signed URL za svaki fajl (važi 60 min)
    rezultat = []
    for u in uploadi:
        signed_url = None
        if u.get("storage_path"):
            try:
                url_r = await asyncio.to_thread(
                    lambda _p=u["storage_path"]: supa.storage.from_("portal-uploads")
                        .create_signed_url(_p, 3600)
                )
                signed_url = url_r.get("signedURL") or url_r.get("signedUrl")
            except Exception:
                pass
        rezultat.append({
            "id":           u["id"],
            "fajl_naziv":   u.get("fajl_naziv"),
            "fajl_velicina": u.get("fajl_velicina"),
            "content_type": u.get("content_type"),
            "napomena":     u.get("napomena"),
            "pregledano":   u.get("pregledano", False),
            "uploaded_at":  u.get("uploaded_at"),
            "download_url": signed_url,
        })

    nepregledano = sum(1 for u in rezultat if not u["pregledano"])
    return {
        "uploadi":     rezultat,
        "ukupno":      len(rezultat),
        "nepregledano": nepregledano,
    }


@router.patch("/api/client-portal/uploads/{upload_id}/pregledano")
@limiter.limit("30/minute")
async def client_portal_oznaci_pregledano(
    upload_id: str,
    request:   Request,
    user:      dict = Depends(get_current_user),
):
    """Advokat označava upload kao pregledan."""
    uid  = user["user_id"]
    supa = _get_supa()

    r = await asyncio.to_thread(
        lambda: supa.table("client_portal_uploads")
            .update({"pregledano": True})
            .eq("id", upload_id)
            .eq("advokat_user_id", uid)
            .execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Upload nije pronađen.")
    return {"ok": True, "upload_id": upload_id}


@router.delete("/api/client-portal/uploads/{upload_id}")
@limiter.limit("20/minute")
async def client_portal_obrisi_upload(
    upload_id: str,
    request:   Request,
    user:      dict = Depends(get_current_user),
):
    """Advokat briše klijentov upload (i iz storage-a i iz DB)."""
    uid  = user["user_id"]
    supa = _get_supa()

    # Dohvati storage_path pre brisanja
    meta_r = await asyncio.to_thread(
        lambda: supa.table("client_portal_uploads")
            .select("id, storage_path")
            .eq("id", upload_id)
            .eq("advokat_user_id", uid)
            .maybe_single()
            .execute()
    )
    if not meta_r.data:
        raise HTTPException(status_code=404, detail="Upload nije pronađen.")

    storage_path = meta_r.data.get("storage_path")

    # Briši iz storage-a (ne-fatalno ako ne uspe)
    if storage_path:
        try:
            await asyncio.to_thread(
                lambda: supa.storage.from_("portal-uploads").remove([storage_path])
            )
        except Exception as exc:
            logger.warning("[PORTAL_DELETE] Storage brisanje nije uspelo: %s", exc)

    # Briši iz DB
    await asyncio.to_thread(
        lambda: supa.table("client_portal_uploads")
            .delete()
            .eq("id", upload_id)
            .eq("advokat_user_id", uid)
            .execute()
    )

    logger.info("[PORTAL_DELETE] upload_id=%s uid=%.8s", upload_id, uid)
    return {"ok": True, "upload_id": upload_id}
