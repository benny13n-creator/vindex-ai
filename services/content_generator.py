# -*- coding: utf-8 -*-
"""
Vindex AI — services/content_generator.py

KORAK D: Legal Thought Leadership & Content Agent (2026-07-24)

Generiše nacrt stručnog LinkedIn/Blog posta na osnovu JAVNO DOSTUPNE sudske
prakse (Pinecone sudska_praksa namespace, već objavljene odluke) ili
zakonskih izmena (zakoni_monitoring tabela, v. routers/zakon_monitoring.py).

NAMERNA arhitektonska granica: ovaj servis NIKAD ne prima predmet_id ili
case_dna kao izvor sadržaja. Ulaz je isključivo javni pravni materijal --
to je prva i najjača linija odbrane protiv curenja poverljivih podataka
klijenta u javni post, pre bilo kakve anonimizacije teksta. oblast_prava
(npr. "Radno pravo") sme da se prosledi kao SAMO tematski filter, nikad
konkretan sadržaj predmeta.

Dva odvojena LLM poziva (oba @llm_retry):
  1. Generisanje posta iz javnog izvora.
  2. NEZAVISNA etička provera generisanog teksta (Kodeks profesionalne
     etike advokata Srbije -- zabrana garancije uspeha, reklamiranja,
     poređenja sa drugim advokatima, otkrivanja podataka o strankama).
     etika_ok=False NE briše nacrt -- HITL pregled (routers/marketing_agent.py)
     ostaje obavezan u svakom slučaju, ovo je samo dodatni signal upozorenja
     prikazan advokatu pre accept-a.

Dodatna anonimizacija: main._skini_pii (JMBG/PIB/telefon/IBAN/email/adresa)
PLUS lokalna heuristika za dvočlana/tročlana imena velikim slovom (SEC-006:
_skini_pii NE hvata imena osoba) -- oba prolaza su best-effort, ne
kriptografska garancija; zato etička provera i HITL ostaju obavezni.
"""
import asyncio
import json
import logging
import re
from typing import Optional

from shared.llm_retry import llm_retry
from shared.sentry import capture_exception as _sentry_capture

logger = logging.getLogger("vindex.content_generator")

_MAX_IZVOR_CHARS = 3000

# Heuristika: Ime Prezime (2-3 reči, svaka počinje velikim slovom, bez
# poznatih pravnih termina koji takođe počinju velikim slovom na početku
# rečenice) -- namerno konzervativna (radije previdi neko ime nego maskira
# pravne pojmove poput "Vrhovni sud" ili "Zakon o radu").
_IME_PREZIME_RE = re.compile(
    r"\b(?!Vrhovni\b|Apelacioni\b|Osnovni\b|Viši\b|Privredni\b|Ustavni\b|Prekršajni\b|"
    r"Republika\b|Republički\b|Zakon\b|Ustav\b|Član\b)"
    r"[A-ZŠĐČĆŽ][a-zšđčćž]+\s+[A-ZŠĐČĆŽ][a-zšđčćž]+(?:ić|ov|ova|in|ina)\b"
)


def _dodatna_anonimizacija(tekst: str) -> str:
    return _IME_PREZIME_RE.sub("[STRANKA]", tekst or "")


def anonimizuj(tekst: str) -> str:
    """Dva prolaza: main._skini_pii (brojevi/kontakti) + lokalna heuristika
    za imena. Best-effort -- v. napomenu u docstring-u modula."""
    from main import _skini_pii
    return _dodatna_anonimizacija(_skini_pii(tekst or ""))


# ─── Izvor: javno dostupna sudska praksa ────────────────────────────────────

async def _dohvati_izvor_sudska_praksa(oblast_prava: str) -> Optional[dict]:
    try:
        from app.services.retrieve import retrieve_sudska_praksa, process_praksa_chunks
        raw = await asyncio.to_thread(retrieve_sudska_praksa, oblast_prava or "sudska praksa", 20)
        odluke = process_praksa_chunks(raw, k=1)
        if not odluke:
            return None
        o = odluke[0]
        return {
            "opis": f"{o.get('court', '')} {o.get('date', '')} — {o.get('decision_number', '')}",
            "tekst": anonimizuj(o.get("text", ""))[:_MAX_IZVOR_CHARS],
        }
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[CONTENT_GEN] sudska_praksa izvor greška: %s", e)
        return None


async def _dohvati_izvor_zakonska_izmena(oblast_prava: str, supa) -> Optional[dict]:
    try:
        q = supa.table("zakoni_monitoring").select("naziv_zakona,sazetak,datum_objave,oblasti_prava").order("datum_objave", desc=True).limit(20)
        r = await asyncio.to_thread(q.execute)
        rows = r.data or []
        if oblast_prava:
            filtered = [row for row in rows if oblast_prava.lower() in " ".join(row.get("oblasti_prava") or []).lower()]
            rows = filtered or rows
        if not rows:
            return None
        row = rows[0]
        return {
            "opis": f"{row.get('naziv_zakona', '')} ({row.get('datum_objave', '')})",
            "tekst": anonimizuj(row.get("sazetak", ""))[:_MAX_IZVOR_CHARS],
        }
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[CONTENT_GEN] zakonska_izmena izvor greška: %s", e)
        return None


# ─── Generisanje posta ───────────────────────────────────────────────────────

_GENERISI_SYSTEM = """Ti pomažeš srpskim advokatima da izgrade stručni autoritet
kroz edukativne LinkedIn/Blog objave zasnovane na JAVNOJ sudskoj praksi ili
zakonskim izmenama.

Vrati SAMO JSON: {"naslov": "...", "tekst": "..."}

PRAVILA (Kodeks profesionalne etike advokata Srbije + zdrav razum):
- Edukativan ton -- objašnjavaš PRAVNI PRINCIP iz izvora, ne prodaješ uslugu.
- NIKAD ne garantuj ishod niti tvrdiš "uvek pobeđujemo" ili slično.
- NIKAD ne pominji ili ne implicira imena stranaka, čak i ako su u izvoru.
- NIKAD ne upoređuj sa drugim advokatima/kancelarijama, ne omalovažavaj sud.
- NIKAD ne otkrivaj detalje bilo kog KONKRETNOG predmeta advokata koji piše --
  izvor je isključivo javno dostupan materijal prosleđen ispod.
- Za LinkedIn: 150-250 reči, 1 jasna pravna poenta, poziv na razmišljanje na
  kraju (ne poziv na kontakt/reklamu).
- Za Blog: 300-500 reči, malo detaljnije, i dalje edukativno.
- Bez markdown blokova u JSON odgovoru, samo čist tekst u "tekst" polju."""


@llm_retry
def _pozovi_generisanje_api(izvor_opis: str, izvor_tekst: str, platforma: str, oblast_prava: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        max_tokens=900,
        timeout=25.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _GENERISI_SYSTEM},
            {"role": "user", "content": (
                f"PLATFORMA: {platforma}\nOBLAST: {oblast_prava or 'opšte'}\n\n"
                f"JAVNI IZVOR: {izvor_opis}\n{izvor_tekst}"
            )},
        ],
    )
    return (r.choices[0].message.content or "{}").strip()


# ─── Etička provera (nezavisan, drugi LLM poziv) ────────────────────────────

_ETIKA_SYSTEM = """Ti si revizor usklađenosti sa Kodeksom profesionalne etike
advokata Srbije. Dobijaš gotov nacrt LinkedIn/Blog posta advokata. Proveri:

1. Da li garantuje ili implicira garantovan ishod postupka?
2. Da li sadrži reklamni/prodajni jezik neprimeren strukovnoj etici
   (superlativi, "najbolji", pozivi tipa "kontaktirajte nas odmah")?
3. Da li upoređuje ili omalovažava druge advokate/kancelarije/sudove?
4. Da li otkriva ili implicira identitet konkretne stranke/klijenta?

Vrati SAMO JSON: {"ok": true|false, "problemi": ["kratak opis problema 1", ...]}
Prazan niz problemi ako je sve u redu."""


@llm_retry
def _pozovi_etika_api(tekst: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=300,
        timeout=15.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _ETIKA_SYSTEM},
            {"role": "user", "content": tekst},
        ],
    )
    return (r.choices[0].message.content or "{}").strip()


async def _proveri_etiku(tekst: str) -> dict:
    """Vraća {"ok": bool|None, "problemi": [...]}. ok=None znači da provera
    tehnički nije uspela (LLM greška/timeout) -- NIKAD se tretira kao
    "ok=True" (fail-soft za dostupnost sistema, fail-CLOSED za etičku
    ocenu -- HITL reviewer mora videti da provera nije izvršena, ne lažno
    "prošla")."""
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_pozovi_etika_api, tekst), timeout=20.0)
        parsed = json.loads(raw)
        problemi = parsed.get("problemi") if isinstance(parsed.get("problemi"), list) else []
        return {"ok": bool(parsed.get("ok", False)), "problemi": [str(p)[:300] for p in problemi[:10]]}
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[CONTENT_GEN] etička provera neuspešna: %s", e)
        return {"ok": None, "problemi": ["Etička provera tehnički nije uspela — potreban je pažljiviji ručni pregled."]}


def _parsiraj_generisani_post(raw: str) -> Optional[dict]:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    tekst = (parsed.get("tekst") or "").strip() if isinstance(parsed, dict) else ""
    if not tekst:
        return None
    return {
        "naslov": (parsed.get("naslov") or "").strip()[:200],
        "tekst": tekst,
    }


# ─── Glavna ulazna tačka ─────────────────────────────────────────────────────

async def generate_post(
    izvor_tip: str,
    oblast_prava: Optional[str],
    platforma: str,
    user_id: str,
    supa,
) -> dict:
    """Vraća {"ok": bool, "draft": {...}|None, "error": str|None}. Nikad ne
    baca -- pozivalac (routers/marketing_agent.py) tretira "ok": False kao
    čist fail-soft ishod (npr. nema dovoljno javnog materijala danas)."""
    if izvor_tip == "sudska_praksa":
        izvor = await _dohvati_izvor_sudska_praksa(oblast_prava or "")
    elif izvor_tip == "zakonska_izmena":
        izvor = await _dohvati_izvor_zakonska_izmena(oblast_prava or "", supa)
    else:
        return {"ok": False, "draft": None, "error": f"Nepoznat izvor_tip: {izvor_tip}"}

    if not izvor:
        return {"ok": False, "draft": None, "error": "Nema dostupnog javnog materijala za zadatu oblast trenutno."}

    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(_pozovi_generisanje_api, izvor["opis"], izvor["tekst"], platforma, oblast_prava or ""),
            timeout=30.0,
        )
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[CONTENT_GEN] generisanje neuspešno uid=%.8s: %s", (user_id or "")[:8], e)
        return {"ok": False, "draft": None, "error": "Generisanje sadržaja trenutno nije dostupno."}

    generisano = _parsiraj_generisani_post(raw)
    if not generisano:
        return {"ok": False, "draft": None, "error": "Model nije vratio validan sadržaj — pokušajte ponovo."}

    # Dodatni anonimizacioni prolaz i nad GENERISANIM tekstom (ne samo
    # izvorom) -- model ponekad parafrazira izvor tako da ponovo uvede
    # detalj koji je izvor već imao maskiran, ili unese sopstveni primer.
    naslov = anonimizuj(generisano["naslov"])
    tekst = anonimizuj(generisano["tekst"])

    etika = await _proveri_etiku(tekst)

    row = {
        "user_id":        user_id,
        "izvor_tip":      izvor_tip,
        "izvor_opis":     izvor["opis"][:500],
        "oblast_prava":   oblast_prava,
        "platforma":      platforma,
        "naslov":         naslov,
        "tekst":          tekst,
        "etika_ok":       etika["ok"],
        "etika_problemi": etika["problemi"],
    }

    try:
        result = await asyncio.to_thread(lambda: supa.table("marketing_content_drafts").insert(row).execute())
        draft = (result.data or [{}])[0]
        return {"ok": True, "draft": draft, "error": None}
    except Exception as e:
        _sentry_capture(e)
        logger.error("[CONTENT_GEN] upis nacrta neuspešan: %s", e)
        return {"ok": False, "draft": None, "error": "Nacrt je generisan ali nije sačuvan zbog greške na serveru."}
