# -*- coding: utf-8 -*-
"""
Evidence Vault — automatska klasifikacija dokumenata i matrica dokaza.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from fastapi import Security
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

def get_supa(): return _get_supa()
require_user = get_current_user

logger = logging.getLogger("vindex.evidence")
router = APIRouter(prefix="/api/evidence", tags=["evidence"])

_CLASSIFY_SYSTEM = """Ti si pravni asistent koji klasifikuje pravne dokumente.

Za dati dokument (naziv + tekst izvod) vrati JSON objekat:
{
  "tip_dokaza": "<tip>",
  "pravni_elementi": ["<element1>", "<element2>"],
  "ai_tags": {
    "stranke": ["<stranka1>"],
    "datumi": ["<datum1>"],
    "iznosi": ["<iznos1>"],
    "sud_organ": "<naziv>",
    "referenca": "<broj predmeta/ugovora>"
  },
  "kljucne_cinjenice": ["<cinjenica1>", "<cinjenica2>", "<cinjenica3>"]
}

Dozvoljeni tipovi za tip_dokaza:
- sudska_odluka (presuda, rešenje, zaključak suda)
- podnesak (tužba, žalba, prigovor, zahtev stranke)
- ugovor (ugovor o radu, kupoprodajni, zakup, zastupanje)
- dopis (pismena komunikacija, obaveštenje, upozorenje)
- medicinska_dokumentacija (nalaz, izveštaj, otpusna lista)
- finansijska_dokumentacija (izvod, faktura, potvrda o plaćanju)
- javna_isprava (izvod iz matičnih knjiga, uverenje, potvrda organa)
- vestacki_nalaz (mišljenje veštaka)
- ostalo

Pravni elementi su konkretni uslovi koje ovaj dokument pokriva (npr. "uzročna veza", "visina štete", "poslovna sposobnost").

Vrati SAMO JSON bez markdown fenci."""


def _klasifikuj_dokument(naziv: str, tekst_izvod: str) -> dict:
    """GPT-4o-mini klasifikuje dokument. Vraća dict sa tip_dokaza, pravni_elementi, ai_tags, kljucne_cinjenice."""
    try:
        from openai import OpenAI
        import json
        client = OpenAI()
        user_msg = f"Naziv dokumenta: {naziv}\n\nTekst (izvod, max 1500 znakova):\n{tekst_izvod[:1500]}"
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=600,
            messages=[
                {"role": "system", "content": _CLASSIFY_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))
        return json.loads(raw)
    except Exception as exc:
        logger.warning("[EVIDENCE] Klasifikacija greška: %s", exc)
        return {
            "tip_dokaza": "ostalo",
            "pravni_elementi": [],
            "ai_tags": {},
            "kljucne_cinjenice": [],
        }


def klasifikuj_i_sacuvaj(predmet_id: str, dokument_id: str, naziv: str, tekst: str, user_id: str) -> None:
    """Poziva se u pozadini posle uploada. Klasifikuje i upisuje u predmet_dokumenti.

    Reliability fix (2026-07-19, posle migracija 016/074): predmet_dokumenti
    update i predmet_dokazi insert su ranije delili JEDAN try/except — ako bi
    prvi pao (npr. buduci schema gap kao onaj koji je upravo ispravljen),
    drugi se NIKAD ne bi ni pokusao, iako su nezavisni upisi. Razdvojeno u
    dva bloka, isti obrazac kao vec dokazan u api.py-jevom document insert-u:
    delimican neuspeh vise ne blokira sve."""
    import json
    supa = get_supa()
    rezultat = _klasifikuj_dokument(naziv, tekst)

    try:
        supa.table("predmet_dokumenti").update({
            "tip_dokaza":      rezultat.get("tip_dokaza", "ostalo"),
            "pravni_elementi": rezultat.get("pravni_elementi", []),
            "ai_tags":         json.dumps(rezultat.get("ai_tags", {})),
            "klasifikovan_at": "now()",
        }).eq("id", dokument_id).execute()
        logger.info("[EVIDENCE] Klasifikovan dokument=%s tip=%s", dokument_id, rezultat.get("tip_dokaza"))
    except Exception as exc:
        logger.warning("[EVIDENCE] Greška pri upisu klasifikacije predmet_dokumenti: %s", exc)

    try:
        # Upiši ključne činjenice kao predmet_dokazi — nezavisno od gornjeg
        # bloka: cak i ako predmet_dokumenti update padne, kljucne cinjenice
        # su i dalje vredne upisati ako je predmet_dokazi tabela zdrava.
        cinjenice = rezultat.get("kljucne_cinjenice", [])
        pravni_elm = rezultat.get("pravni_elementi", [])
        rows = []
        for i, c in enumerate(cinjenice[:5]):
            rows.append({
                "predmet_id":    predmet_id,
                "dokument_id":   dokument_id,
                "user_id":       user_id,
                "tvrdnja":       c,
                "kategorija":    "cinjenica",
                "snaga":         "srednja",
                "pravni_element": pravni_elm[i] if i < len(pravni_elm) else None,
            })
        if rows:
            supa.table("predmet_dokazi").insert(rows).execute()
            logger.info("[EVIDENCE] Upisano %d činjenica za predmet=%s", len(rows), predmet_id)
    except Exception as exc:
        logger.warning("[EVIDENCE] Greška pri upisu predmet_dokazi: %s", exc)


@router.get("/predmeti/{predmet_id}")
@limiter.limit("30/minute")
async def get_evidence(request: Request, predmet_id: str, user=Depends(require_user)):
    """Vraća Evidence Vault za predmet — dokumente sa klasifikacijom i matricu dokaza."""
    import asyncio
    supa = get_supa()
    uid = user["user_id"]

    # Provera vlasništva
    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid).execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    # Dokumenti + matrica dokaza paralelno
    dok_r, dokaz_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti").select(
                "id,naziv_fajla,tip_dokaza,pravni_elementi,ai_tags,velicina_kb,status,klasifikovan_at,created_at"
            ).eq("predmet_id", predmet_id).order("created_at", desc=False).execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_dokazi").select("*").eq("predmet_id", predmet_id).is_("deleted_at", "null").order("created_at", desc=True).execute()
        ),
    )

    # Statistika po tipu
    dokumenti = dok_r.data or []
    tip_stat: dict = {}
    for d in dokumenti:
        tip = d.get("tip_dokaza") or "neklafikovan"
        tip_stat[tip] = tip_stat.get(tip, 0) + 1

    return {
        "dokumenti":    dokumenti,
        "dokazi":       dokaz_r.data or [],
        "tip_stat":     tip_stat,
        "ukupno_dok":   len(dokumenti),
        "klasifikovano": sum(1 for d in dokumenti if d.get("tip_dokaza")),
    }


class DokazReq(BaseModel):
    tvrdnja:       str
    kategorija:    str = "cinjenica"
    snaga:         str = "srednja"
    pravni_element: Optional[str] = None
    napomena:      Optional[str] = None
    dokument_id:   Optional[str] = None


@router.post("/predmeti/{predmet_id}/dokaz")
@limiter.limit("20/minute")
async def add_dokaz(request: Request, predmet_id: str, req: DokazReq, user=Depends(require_user)):
    """Manuelno dodaje dokaznu stavku u Evidence Vault."""
    import asyncio
    supa = get_supa()
    uid = user["user_id"]

    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid).execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404)

    row = {
        "predmet_id":    predmet_id,
        "user_id":       uid,
        "tvrdnja":       req.tvrdnja,
        "kategorija":    req.kategorija,
        "snaga":         req.snaga,
        "pravni_element": req.pravni_element,
        "napomena":      req.napomena,
        "dokument_id":   req.dokument_id,
    }
    res = await asyncio.to_thread(
        lambda: supa.table("predmet_dokazi").insert(row).execute()
    )
    return {"ok": True, "id": (res.data or [{}])[0].get("id")}


@router.delete("/predmeti/{predmet_id}/dokaz/{dokaz_id}")
@limiter.limit("20/minute")
async def delete_dokaz(request: Request, predmet_id: str, dokaz_id: str, user=Depends(require_user)):
    import asyncio
    supa = get_supa()
    uid = user["user_id"]
    await asyncio.to_thread(
        lambda: supa.table("predmet_dokazi").update({"deleted_at": "now()"}).eq("id", dokaz_id).eq("user_id", uid).execute()
    )
    return {"ok": True}


@router.post("/predmeti/{predmet_id}/reklasifikuj/{dok_id}")
@limiter.limit("10/minute")
async def reklasifikuj(request: Request, predmet_id: str, dok_id: str, user=Depends(PermissionService.require("evidence"))):
    """Pokreće reklasifikaciju dokumenta (ako je auto-klasifikacija bila loša)."""
    import asyncio
    supa = get_supa()
    uid = user["user_id"]

    pr, dok = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid).execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti").select("naziv_fajla,pinecone_namespace").eq("id", dok_id).eq("user_id", uid).execute()
        ),
    )
    if not pr.data:
        raise HTTPException(status_code=404)
    if not dok.data:
        raise HTTPException(status_code=404, detail="Dokument nije pronađen.")

    d = dok.data[0]
    asyncio.create_task(
        asyncio.to_thread(klasifikuj_i_sacuvaj, predmet_id, dok_id, d.get("naziv_fajla", ""), "", uid)
    )
    await UsageService.consume(user["user_id"], user.get("email", ""), "evidence")
    return {"ok": True, "poruka": "Reklasifikacija pokrenuta u pozadini."}
