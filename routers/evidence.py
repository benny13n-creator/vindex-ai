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
from shared.http_errors import NamerniHTTPException
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
  "pouzdanost": "visoka" | "srednja" | "niska",
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

"pouzdanost" je TVOJA sopstvena procena koliko si siguran/na u dodeljeni tip_dokaza -- "niska"
ako je dokument dvosmislen, delimično čitljiv, ili odgovara više od jedne kategorije podjednako
dobro.

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
        rezultat = json.loads(raw)
        # Program Phoenix, Mission 006 (LIVINGSYS-DEBT-022): "pouzdanost" was newly added to
        # the prompt above with zero enum-guard, unlike every sibling GPT-declared confidence
        # field this engagement already validates (client_twin.py's own pouzdanost, Genome's
        # genome_kompletnost, CIO's top-level pouzdanost, ...). Same fail-safe direction: an
        # unrecognized/missing value defaults to the least-confident bucket. Folded into
        # ai_tags (existing JSONB column) rather than a top-level field so it's visible
        # wherever ai_tags already is, no schema change.
        if isinstance(rezultat, dict):
            _pouzdanost = rezultat.get("pouzdanost")
            if _pouzdanost not in ("visoka", "srednja", "niska"):
                _pouzdanost = "niska"
            if not isinstance(rezultat.get("ai_tags"), dict):
                rezultat["ai_tags"] = {}
            rezultat["ai_tags"]["_klasifikacija_pouzdanost"] = _pouzdanost
        return rezultat
    except Exception as exc:
        _sentry_capture(exc)
        logger.warning("[EVIDENCE] Klasifikacija greška: %s", exc)
        # Program Phoenix, Mission 006 (LIVINGSYS-DEBT-009): this fallback used to be
        # persisted (tip_dokaza="ostalo", klasifikovan_at stamped) completely
        # indistinguishable from a genuine "ostalo" classification -- a real GPT failure was
        # silently laundered into a plausible-looking success. tip_dokaza stays "ostalo" (a
        # real, valid fallback value, so nothing downstream breaks), but ai_tags (an existing
        # JSONB column, no migration) now carries an explicit failure flag any future reader
        # can check -- the classification is no longer silently indistinguishable from a real
        # one.
        return {
            "tip_dokaza": "ostalo",
            "pravni_elementi": [],
            "ai_tags": {"_klasifikacija_greska": True},
            "kljucne_cinjenice": [],
        }


# ── Utemeljenje i snaga: kanonski izvor je shared/evidence_write.py ─────────
# IMPLEMENTATION TASK 001 (2026-08-27): `_lociraj_tvrdnju` i `_snaga_iz_lokacije`
# su preseljene u shared/evidence_write.py bez izmene ponašanja, da bi ih
# jedinstveni primitiv upisa mogao pozvati bez cirkularnog importa. Re-eksport
# ispod čuva stara imena jer na njih računaju DECISION_REGISTRY.md (DC-005),
# tests/test_decision_registry_completeness.py i tests/test_akcija2_faza4_*.py.
from shared.evidence_write import (              # noqa: E402
    KATEGORIJE,
    SNAGE,
    GreskaDokaza,
    lociraj_tvrdnju as _lociraj_tvrdnju,
    odredi_snagu,
    snaga_iz_lokacije as _snaga_iz_lokacije,
    upisi_dokaz,
    upisi_dokaze,
    _CHARS_PO_STRANICI,
    _PROBE_MAX_LEN,
    _SNAGA_MIN_TVRDNJA_LEN,
)


def klasifikuj_i_sacuvaj(predmet_id: str, dokument_id: str, naziv: str, tekst: str, user_id: str) -> dict:
    """Poziva se u pozadini posle uploada. Klasifikuje i upisuje u predmet_dokumenti.

    Reliability fix (2026-07-19, posle migracija 016/074): predmet_dokumenti
    update i predmet_dokazi insert su ranije delili JEDAN try/except — ako bi
    prvi pao (npr. buduci schema gap kao onaj koji je upravo ispravljen),
    drugi se NIKAD ne bi ni pokusao, iako su nezavisni upisi. Razdvojeno u
    dva bloka, isti obrazac kao vec dokazan u api.py-jevom document insert-u:
    delimican neuspeh vise ne blokira sve.

    Program Phoenix, Mission 006 (LIVINGSYS-DEBT-009): now returns `rezultat` (previously
    always None) so a synchronous caller (routers/evidence.py::reklasifikuj) can check
    rezultat["ai_tags"].get("_klasifikacija_greska") before deciding whether to charge --
    existing fire-and-forget callers (asyncio.create_task) are unaffected, they already
    ignore the return value."""
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
        # Program Sigma, Master Sprint 002 (2026-08-06) -- found and fixed:
        # same bug class as this file's own delete_dokaz's own deleted_at
        # fix (see that endpoint's own comment) -- the literal string
        # "now()" is not a value Postgres's timestamptz parser recognizes.
        # klasifikovan_at is the CANONICAL evidence-classification
        # timestamp, written on every single document classification --
        # this update either silently rejected the whole update or stored
        # an unusable value since whenever this code was written.
        from datetime import datetime as _dt, timezone as _tz
        supa.table("predmet_dokumenti").update({
            "tip_dokaza":      rezultat.get("tip_dokaza", "ostalo"),
            "pravni_elementi": rezultat.get("pravni_elementi", []),
            "ai_tags":         json.dumps(rezultat.get("ai_tags", {})),
            "klasifikovan_at": _dt.now(_tz.utc).isoformat(),
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
        # IMPLEMENTATION TASK 001 (2026-08-27): upis ide kroz JEDINSTVENI
        # primitiv shared/evidence_write.py::upisi_dokaze. Ovde se više ne
        # gradi red ručno, ne poziva se DC-005 direktno i ne radi se sopstveni
        # insert -- `izvor_tekst=tekst` je jedini signal koji primitivu treba
        # da bi utemeljio tvrdnje i izveo `snaga` po DC-005.
        #
        # `proveri_vlasnistvo=False`: ovaj poziv dolazi iz durable event toka
        # (services/case_evolution.py::_consequence_evidence_classify), koji je
        # vlasništvo već dokazao time što je učitao `predmet_dokumenti` red za
        # ovaj `dokument_id`. Dodatan upit po pozivu bio bi suvišan, a
        # `predmet_id`/`user_id` ovde ne dolaze iz korisničkog zahteva.
        stavke = [
            {
                "tvrdnja":        c,
                "kategorija":     "cinjenica",
                "dokument_id":    dokument_id,
                "pravni_element": pravni_elm[i] if i < len(pravni_elm) else None,
            }
            for i, c in enumerate(cinjenice[:5])
        ]
        if stavke:
            _rez_upisa = upisi_dokaze(
                supa,
                predmet_id=predmet_id,
                user_id=user_id,
                stavke=stavke,
                izvor_tekst=tekst,
                proveri_vlasnistvo=False,
            )
            _utemeljeno = sum(1 for o in _rez_upisa["odluke"] if o["lokacija_poznata"])
            logger.info(
                "[EVIDENCE] Upisano %d činjenica (%d utemeljeno u izvoru) za predmet=%s",
                len(_rez_upisa["odluke"]), _utemeljeno, predmet_id,
            )
    except Exception as exc:
        logger.warning("[EVIDENCE] Greška pri upisu predmet_dokazi: %s", exc)

    return rezultat


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
    # TASK 003A: BILO `str = "srednja"`. Taj default je odsustvo korisnikove
    # odluke pretvarao u vrednost, pa je `odredi_snagu` svaki zahtev bez
    # dokumenta klasifikovao kao `izvor_odluke='covek'` -- lažna tvrdnja da je
    # advokat procenio snagu (Gate 005). `None` znači „nije dostavljeno"; sama
    # vrednost i dalje ne dokazuje ništa, dokaz je `model_fields_set` u ruti.
    snaga:         Optional[str] = None
    pravni_element: Optional[str] = None
    napomena:      Optional[str] = None
    dokument_id:   Optional[str] = None


@router.post("/predmeti/{predmet_id}/dokaz")
@limiter.limit("20/minute")
async def add_dokaz(request: Request, predmet_id: str, req: DokazReq, user=Depends(require_user)):
    """Manuelno dodaje dokaznu stavku u Evidence Vault.

    IMPLEMENTATION TASK 001 (2026-08-27): ova ruta je bila DRUGI, neprijavljen
    autor odluke DC-005 -- prepisivala je `snaga` pravo iz tela zahteva, dok je
    automatska putanja istu kolonu IZVODILA iz utemeljenja u dokumentu. Ista
    skala, dve mere, a `calculate_procesni_rizik` ih je sabirao. Sada oba pisca
    idu kroz shared/evidence_write.py::upisi_dokaz, koji je jedini donosilac te
    odluke (v. `odredi_snagu`).

    Šta se promenilo za pozivaoca:
      • bez `dokument_id` — `snaga` iz tela zahteva se poštuje (advokat je
        autoritet tamo gde sistem nema šta da proveri), ALI samo ako je polje
        stvarno poslato. TASK 003A: ranije je ovde stajalo „UI šalje samo
        `tvrdnja`, pa za UI nema promene" -- to je bilo netačno u posledici,
        jer je Pydantic default popunjavao polje na serveru i UI unos je
        završavao kao `izvor_odluke='covek'`. Sada odsustvo polja daje
        `podrazumevano`.
      • sa `dokument_id` — tekst tog dokumenta se učitava, tvrdnja se u njemu
        traži i `snaga` se izvodi po DC-005; poslata vrednost se ignoriše.
        Odgovor to prijavljuje kroz `snaga_prepisana`, nikad tiho.
      • `dokument_id` koji ne pripada ovom predmetu se sada ODBIJA (400)
        umesto da se tiho postavi na NULL uz `{"ok": true}`."""
    import asyncio
    supa = get_supa()
    uid = user["user_id"]

    # TASK 003A -- dokaz ljudske procene je EKSPLICITNO PRISUSTVO polja u
    # zahtevu, nikad njegova vrednost. Vrednost može doći od schema default-a
    # (to je i bio kvar iz Gate 005); prisustvo u `model_fields_set` može doći
    # isključivo od pošiljaoca.
    _snaga_eksplicitna = "snaga" in req.model_fields_set
    if req.snaga is not None and not _snaga_eksplicitna:
        # Nedostižno dok je schema `Optional[str] = None`. Ako se default ikada
        # vrati, ovde puca glasno umesto da tiho fabrikuje ljudsku procenu.
        raise NamerniHTTPException(
            status_code=500,
            detail="Ulazni ugovor za `snaga` je nesaglasan: vrednost postoji bez eksplicitnog unosa.",
        )
    _snaga = req.snaga if _snaga_eksplicitna else None

    # Vlasništvo nad predmetom se proverava PRVO, pre dodirivanja dokumenta --
    # `upisi_dokaz` istu proveru radi i sam (INVARIANT 1), ali bi bez ove ruta
    # za nepostojeći/tuđi predmet sa zadatim `dokument_id` vratila 400 umesto
    # 404 kao do sada. Redosled odgovora ostaje nepromenjen.
    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid).limit(1).execute()
    )
    if not (pr.data or []):
        raise HTTPException(status_code=404)

    # Izvorni tekst se učitava SAMO kad je dokument zadat -- bez njega DC-005
    # nema ulaz i `odredi_snagu` pada na tvrdnju čoveka (v. njen docstring).
    izvor_tekst = None
    if req.dokument_id:
        dok = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("tekst_sadrzaj")
                .eq("id", req.dokument_id).eq("predmet_id", predmet_id)
                .limit(1).execute()
        )
        if not (dok.data or []):
            raise HTTPException(status_code=400, detail="Dokument ne pripada ovom predmetu.")
        izvor_tekst = (dok.data[0] or {}).get("tekst_sadrzaj") or None

    try:
        rez = await asyncio.to_thread(
            lambda: upisi_dokaz(
                supa,
                predmet_id=predmet_id,
                user_id=uid,
                tvrdnja=req.tvrdnja,
                kategorija=req.kategorija,
                snaga=_snaga,
                dokument_id=req.dokument_id,
                pravni_element=req.pravni_element,
                napomena=req.napomena,
                izvor_tekst=izvor_tekst,
            )
        )
    except GreskaDokaza as exc:
        raise HTTPException(status_code=exc.status, detail=exc.poruka)

    odluka = rez["odluka"]
    return {
        "ok": True,
        "id": (rez["red"] or {}).get("id"),
        "snaga": odluka.get("snaga"),
        "snaga_izvor": odluka.get("izvor_odluke"),
        "snaga_prepisana": odluka.get("snaga_prepisana", False),
        "lokacija_poznata": odluka.get("lokacija_poznata", False),
    }


@router.delete("/predmeti/{predmet_id}/dokaz/{dokaz_id}")
@limiter.limit("20/minute")
async def delete_dokaz(request: Request, predmet_id: str, dokaz_id: str, user=Depends(require_user)):
    import asyncio
    from datetime import datetime, timezone
    supa = get_supa()
    uid = user["user_id"]
    # Program Sigma, Master Sprint 002 (2026-08-06) -- found and fixed: the
    # literal string "now()" (with parentheses) is NOT a value Postgres's
    # timestamptz input parser recognizes (only the bare word "now" is a
    # documented special value) -- same bug class Program Omega Sprint 004
    # already found and fixed for case_actions.closed_at (see
    # services/case_evolution.py's own comment). This endpoint's own soft
    # delete was either rejected outright by Postgres or stored an unusable
    # value on every call. Fixed: a real, computed ISO-8601 timestamp.
    # F-V41-002: rezultat soft-delete-a se odbacivao i ruta je bezuslovno
    # vraćala {"ok": True} -- i za nepostojeći dokaz_id i za tuđi dokaz.
    # Korisnik dobija potvrdu da je dokaz uklonjen iz predmeta iako u bazi
    # nijedan red nije dirnut. Owner predikat je oduvek u samoj naredbi, pa
    # tuđi dokaz nije mogao biti obrisan; lažan je bio odgovor.
    r = await asyncio.to_thread(
        lambda: supa.table("predmet_dokazi")
            .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", dokaz_id).eq("user_id", uid).execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Dokaz nije pronađen.")
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
    #
    # Program Phoenix, Mission 006 (LIVINGSYS-DEBT-009): this used to fire-and-forget
    # (asyncio.create_task) and charge a credit immediately after, before the background
    # task had even started -- if OpenAI was down, the credit was spent for a document that
    # silently fell back to "ostalo" again, with no refund path. Now awaited synchronously
    # (matching every other GPT-consuming endpoint in this codebase's own request/response
    # convention -- this is a manual, occasional "fix a bad classification" action, not a
    # hot path, so the extra latency of one GPT call is a reasonable, low-risk tradeoff for
    # correct billing), and the charge is skipped when the classification genuinely failed.
    rezultat = await asyncio.to_thread(
        klasifikuj_i_sacuvaj, predmet_id, dok_id, d.get("naziv_fajla", ""),
        d.get("tekst_sadrzaj", "") or "", uid,
    )
    _greska = bool((rezultat or {}).get("ai_tags", {}).get("_klasifikacija_greska"))
    if _greska:
        return {"ok": False, "poruka": "Reklasifikacija nije uspela (AI greška). Pokušajte ponovo, kredit nije naplaćen."}

    await UsageService.consume(user["user_id"], user.get("email", ""), "evidence")
    return {"ok": True, "poruka": "Reklasifikacija završena."}
