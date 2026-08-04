# -*- coding: utf-8 -*-
"""
Evidence Vault — automatska klasifikacija dokumenata i matrica dokaza.
"""
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from fastapi import Security
from shared.llm_retry import llm_retry
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.sentry import capture_exception as _sentry_capture
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


@llm_retry
def _pozovi_evidence_api(client, user_msg: str):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške."""
    return client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=600,
        messages=[
            {"role": "system", "content": _CLASSIFY_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
    )


def _klasifikuj_dokument(naziv: str, tekst_izvod: str) -> dict:
    """GPT-4o-mini klasifikuje dokument. Vraća dict sa tip_dokaza, pravni_elementi, ai_tags, kljucne_cinjenice."""
    try:
        from openai import OpenAI
        import json
        client = OpenAI()
        user_msg = f"Naziv dokumenta: {naziv}\n\nTekst (izvod, max 1500 znakova):\n{tekst_izvod[:1500]}"
        resp = _pozovi_evidence_api(client, user_msg)
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))
        return json.loads(raw)
    except Exception as exc:
        _sentry_capture(exc)
        logger.warning("[EVIDENCE] Klasifikacija greška: %s", exc)
        return {
            "tip_dokaza": "ostalo",
            "pravni_elementi": [],
            "ai_tags": {},
            "kljucne_cinjenice": [],
        }


_CHARS_PO_STRANICI = 2500  # gruba procena (12pt font, A4, standardni razmak)
_PROBE_MAX_LEN = 100  # _lociraj_tvrdnju proverava SAMO prvih ovoliko karaktera tvrdnje


def _lociraj_tvrdnju(tekst: str, tvrdnja: str) -> dict:
    """AKCIJA 2 (2026-07-24): programski pronalazi GDE se tvrdnja nalazi u
    izvornom dokumentu -- isti substring-matching princip kao
    analiza/validator.py::validate_clause_excerpts (ne teoretsko poverenje
    LLM-u), primenjen na Evidence Vault. Ako tvrdnja nije doslovno
    pronađena (GPT je parafrazirao umesto citirao), vraća sve None --
    kolone su NULLABLE upravo zbog ovoga (fail-soft, nikad izmišljena
    lokacija samo da bi polje bilo popunjeno)."""
    prazno = {"stranica": None, "paragraf": None, "start_offset": None, "end_offset": None}
    if not tekst or not tvrdnja:
        return prazno

    probe = re.sub(r"\.{2,}$|…$", "", tvrdnja.strip()).rstrip()[:_PROBE_MAX_LEN]
    if not probe:
        return prazno

    # Pokušaj 1: tačan (case-insensitive) substring na ORIGINALNOM tekstu --
    # daje TAČAN offset kad GPT citira sa istim razmacima kao izvor.
    pos = tekst.lower().find(probe.lower())
    if pos >= 0:
        start_offset, end_offset = pos, pos + len(probe)
    else:
        # Pokušaj 2: whitespace-normalizovano pretraživanje (isti obrazac
        # kao validate_clause_excerpts), sa proporcionalnim mapiranjem
        # nazad na originalni tekst -- aproksimacija, dovoljno dobra za
        # "otprilike koja stranica/segment", ne za karakter-precizan offset.
        try:
            from analiza.validator import _normalize_ws
            tekst_norm = _normalize_ws(tekst)
            probe_norm = _normalize_ws(probe)
            npos = tekst_norm.find(probe_norm)
        except Exception:
            npos = -1
        if npos < 0:
            return prazno
        razmera = len(tekst) / max(len(tekst_norm), 1)
        start_offset = int(npos * razmera)
        end_offset = int((npos + len(probe_norm)) * razmera)

    stranica = (start_offset // _CHARS_PO_STRANICI) + 1

    paragraf = None
    try:
        from analiza.segmenter import segment_document
        segmented = segment_document(tekst)
        for seg in segmented.segments:
            if seg.start_offset >= 0 and seg.start_offset <= start_offset < seg.end_offset:
                paragraf = seg.id
                break
    except Exception:
        pass

    return {
        "stranica": stranica,
        "paragraf": paragraf,
        "start_offset": start_offset,
        "end_offset": end_offset,
    }


_SNAGA_MIN_TVRDNJA_LEN = 20  # ispod ovoga, substring poklapanje je previse opste (npr. samo ime stranke) da bi bio pouzdan signal


def _snaga_iz_lokacije(tvrdnja: str, lokacija: dict) -> str:
    """Program Beta (2026-08-04) — `snaga` je ranije bila fiksna "srednja" za
    SVAKU tvrdnju, bez obzira da li je _lociraj_tvrdnju uopšte mogla da je
    pronađe u izvornom dokumentu -- odbačen već-izračunat signal (isti obrazac
    kao shared/genome_validator.py::compute_snaga_score, treći potvrđeni
    slučaj istog principa u ovom repou). Tvrdnja pronađena doslovno u izvoru
    je genuinely jača dokazna osnova nego neverifikovana -- ali "nije
    pronađeno" NE znači nužno "netačno" (GPT je mogao parafrazirati), zato
    default za neverifikovano ostaje neutralno "srednja", ne "slaba".

    Olympus Faza 10 governance nalaz (2026-08-04, AI Grounding + AI Quality
    Auditor nezavisno potvrdili isti rizik): "jaka" se dodeljuje SAMO kad je
    CELA tvrdnja duž provere -- ne prekratka (generička fraza kao samo ime
    stranke može slučajno poklopiti nepovezano mesto u tekstu) i ne duža od
    _PROBE_MAX_LEN (_lociraj_tvrdnju proverava SAMO prvih 100 karaktera --
    duža tvrdnja čiji je REP izmišljen/parafraziran bi inače dobila "jaka" na
    osnovu poklapanja samo prefiksa, nikad proveravajući ostatak)."""
    if lokacija.get("start_offset") is None:
        return "srednja"
    duzina = len((tvrdnja or "").strip())
    if duzina < _SNAGA_MIN_TVRDNJA_LEN or duzina > _PROBE_MAX_LEN:
        return "srednja"
    return "jaka"


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
    # Mission Migration (2026-08-03) -- Canonical AI Infrastructure Adoption:
    # case_context() works from a plain sync function too (not just async) --
    # this runs inside asyncio.to_thread(klasifikuj_i_sacuvaj, ...), which
    # copies the caller's contextvars into the executor thread, so this
    # nested context correctly layers predmet_id/document_id on top of
    # whatever request-level correlation_id the upload endpoint already set.
    from shared.ai_provenance import case_context as _ai_case_ctx
    with _ai_case_ctx(predmet_id=predmet_id, document_id=dokument_id, module_name="evidence", operation_name="klasifikacija"):
        rezultat = _klasifikuj_dokument(naziv, tekst)

    try:
        supa.table("predmet_dokumenti").update({
            "tip_dokaza":      rezultat.get("tip_dokaza", "ostalo"),
            "pravni_elementi": rezultat.get("pravni_elementi", []),
            "ai_tags":         json.dumps(rezultat.get("ai_tags", {})),
            "klasifikovan_at": "now()",
        }).eq("id", dokument_id).execute()
        logger.info("[EVIDENCE] Klasifikovan dokument=%s tip=%s", dokument_id, rezultat.get("tip_dokaza"))
        # klasifikuj_i_sacuvaj is a plain sync function invoked via
        # asyncio.to_thread() from a worker thread with NO running event
        # loop of its own -- asyncio.create_task() would raise RuntimeError
        # here (unlike shared/ai_client.py's async capture path). Use
        # log_action_sync instead, the same sync-context sibling
        # shared/audit_immutable.py already provides for exactly this case.
        from shared.audit_immutable import log_action_sync
        log_action_sync(
            action="evidence_klasifikacija", user_id=user_id,
            resource_type="predmet_dokumenti", resource_id=dokument_id,
        )
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
            # AKCIJA 2 (2026-07-24): lokacijsko utemeljenje -- migracija 080
            # (predmet_dokazi.stranica/paragraf/start_offset/end_offset,
            # čeka pokretanje). _lociraj_tvrdnju vraća sve None kad tvrdnja
            # nije doslovno pronađena u tekst-u -- ne izmišljena lokacija.
            lokacija = _lociraj_tvrdnju(tekst, c)
            rows.append({
                "predmet_id":    predmet_id,
                "dokument_id":   dokument_id,
                "user_id":       user_id,
                "tvrdnja":       c,
                "kategorija":    "cinjenica",
                "snaga":         _snaga_iz_lokacije(c, lokacija),
                "pravni_element": pravni_elm[i] if i < len(pravni_elm) else None,
                **lokacija,
            })
        if rows:
            try:
                supa.table("predmet_dokazi").insert(rows).execute()
                logger.info("[EVIDENCE] Upisano %d činjenica za predmet=%s", len(rows), predmet_id)
            except Exception as exc_grounding:
                # Migracija 080 (stranica/paragraf/start_offset/end_offset)
                # možda još nije pokrenuta u produkciji -- degradiraj na
                # insert bez grounding kolona umesto da izgubi CEO upis dok
                # migracija ne prođe (fail-soft, isti princip kao ostatak
                # ove funkcije).
                logger.warning(
                    "[EVIDENCE] Insert sa grounding kolonama neuspešan (%s) — pokušavam bez njih",
                    exc_grounding,
                )
                legacy_rows = [
                    {k: v for k, v in r.items() if k not in ("stranica", "paragraf", "start_offset", "end_offset")}
                    for r in rows
                ]
                supa.table("predmet_dokazi").insert(legacy_rows).execute()
                logger.info(
                    "[EVIDENCE] Upisano %d činjenica (bez grounding kolona) za predmet=%s",
                    len(legacy_rows), predmet_id,
                )
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
            lambda: supa.table("predmet_dokumenti").select("naziv_fajla,pinecone_namespace,tekst_sadrzaj").eq("id", dok_id).eq("user_id", uid).execute()
        ),
    )
    if not pr.data:
        raise HTTPException(status_code=404)
    if not dok.data:
        raise HTTPException(status_code=404, detail="Dokument nije pronađen.")

    d = dok.data[0]
    # BUG FIX (2026-07-24): select nije ni tražio "tekst_sadrzaj", pa je
    # reklasifikacija UVEK slala prazan string umesto stvarnog teksta
    # dokumenta -- efektivno nikad nije videla sadržaj koji treba da
    # reklasifikuje, samo naziv fajla.
    asyncio.create_task(
        asyncio.to_thread(
            klasifikuj_i_sacuvaj, predmet_id, dok_id, d.get("naziv_fajla", ""),
            d.get("tekst_sadrzaj", "") or "", uid,
        )
    )
    await UsageService.consume(user["user_id"], user.get("email", ""), "evidence")
    return {"ok": True, "poruka": "Reklasifikacija pokrenuta u pozadini."}
