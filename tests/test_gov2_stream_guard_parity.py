# -*- coding: utf-8 -*-
"""
Governance Wave 2 — `/api/pitanje/stream` dobija istu ulaznu zaštitu kao blizanac.

NALAZ

`/api/pitanje` (`api.py:3045-3064`) eksplicitno zove `prompt_guard.analyze`,
blokira, i upisuje `injection_attempt_blocked` u hash-chained ledger sa
autentifikovanim `user_id`-om.

`/api/pitanje/stream` to nije radio. Oslanjao se isključivo na SDK monkey-patch
(`shared/ai_client.py`), koji opali tek na samom GPT pozivu. Dve merene
posledice:

  1. Napadački prompt bi PRE blokade bio embedovan i poslat Pinecone-u
     (`app/services/retrieve.py:610`). `_tracked_embed` radi provenance, ali NE
     poziva `analyze()` — embeddings grana patch-a nema guard (izmereno). Sadržaj
     bi dakle napustio sistem pre nego što bi ijedna kontrola reagovala.

  2. Blokada sa nivoa SDK patch-a nema pristup autentifikovanom identitetu, pa
     fallback na `api.py:893-905` upisuje `user_id="unknown"`. Pokušaj injekcije
     ostajao je bez traga koji se može pripisati korisniku.

ZAŠTO OVO NIJE PROGLAŠENO KRITIČNIM
`/api/pitanje/stream` nema nijednog pozivaoca u frontendu — `static/vindex.js`
zove `/api/pitanje` na tri mesta, `/stream` nijednom. Endpoint je ipak javan i
autentifikovan, pa je popravka odbrana u dubinu, ne gašenje požara.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _telo_funkcije(ime: str) -> str:
    src = open(os.path.join(_KOREN, "api.py"), encoding="utf-8").read()
    m = re.search(
        r"async def " + re.escape(ime) + r"\(.*?\n(.*?)(?=\n@app\.|\n@router\.|\nasync def |\ndef )",
        src, re.S,
    )
    assert m, f"{ime} nije pronađena u api.py"
    return m.group(1)


def _kod_bez_dokumentacije(telo: str) -> str:
    """Telo bez docstring-a i `#` komentara.

    Nužno, i to je već jednom izmereno: `test_d` je u prvoj verziji našao
    `ask_agent(` u DOCSTRING-u funkcije (`api.py:3189` doslovno objašnjava da
    „ask_agent() se izvršava do kraja"), pa je zaključio da guard stoji posle
    njega. Isti razred greške kao P0-D2, gde je test merio komentar umesto koda.
    """
    bez_ds = re.sub(r'"""(?:.|\n)*?"""', "", telo)
    return "\n".join(l for l in bez_ds.splitlines() if not l.strip().startswith("#"))


# ─── 1. PARITET SA SESTRINSKIM ENDPOINTOM ───────────────────────────────────

@pytest.mark.parametrize("endpoint", ["pitanje", "pitanje_stream"])
def test_a_oba_endpointa_zovu_guard_eksplicitno(endpoint):
    """Oba moraju zvati `analyze` sama, ne se oslanjati na SDK patch.

    Patch opali tek na GPT pozivu — posle embedding-a. Ulazna zaštita mora
    stajati pre svakog odlaska sadržaja iz sistema.
    """
    telo = _telo_funkcije(endpoint)
    assert "prompt_guard import analyze" in telo, (
        f"{endpoint} ne zove prompt_guard.analyze eksplicitno — oslanja se na "
        f"SDK patch, koji opali tek posle embedding poziva Pinecone-u"
    )


@pytest.mark.parametrize("endpoint", ["pitanje", "pitanje_stream"])
def test_b_oba_upisuju_pripisiv_audit_trag(endpoint):
    """Blokada mora ostaviti trag vezan za KORISNIKA.

    SDK-level fallback (`api.py:893-905`) upisuje `user_id="unknown"` jer nema
    pristup autentifikovanom identitetu. Trag bez identiteta ne služi ničemu u
    reviziji.
    """
    telo = _telo_funkcije(endpoint)
    assert "injection_attempt_blocked" in telo, f"{endpoint} ne upisuje audit trag"
    assert 'user_id=user["user_id"]' in telo, (
        f"{endpoint} upisuje audit bez autentifikovanog identiteta"
    )


def test_c_akcija_je_u_registru():
    """`log_action` tiho vraća None za akciju van `AUDITABLE_ACTIONS`.

    Bez ove provere bi audit poziv izgledao ispravno a ne bi upisivao ništa —
    to je tačno defekt F-V39-001 iz ranijih sprintova.
    """
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "injection_attempt_blocked" in AUDITABLE_ACTIONS


# ─── 2. REDOSLED — zaštita pre nego što sadržaj napusti sistem ──────────────

def test_d_guard_stoji_pre_dovlacenja_i_naplate():
    """Redosled je ovde cela poenta.

    Da guard stoji posle `retrieve_documents`, napadački tekst bi već bio
    embedovan i poslat Pinecone-u. Da stoji posle `consume`, korisnik bi platio
    blokiran pokušaj.
    """
    telo = _kod_bez_dokumentacije(_telo_funkcije("pitanje_stream"))
    poz_guard = telo.index("_guard_analyze_s")
    for kasnije in ("retrieve_documents(", "UsageService.consume", "ask_agent("):
        if kasnije in telo:
            assert poz_guard < telo.index(kasnije), (
                f"guard stoji POSLE `{kasnije}` — sadržaj napušta sistem pre provere"
            )


def test_e_blokada_ne_otvara_SSE_tok():
    """Poruka o odbijanju ne sme stići kao komad odgovora.

    Unutar SSE toka sve izgleda kao sadržaj. Klijent proverava `res.ok` pre
    nego što počne da čita, pa 400 pre otvaranja toka stiže kao poruka.
    """
    telo = _telo_funkcije("pitanje_stream")
    odsecak = telo[telo.index("_guard_s.blocked"):][:900]
    assert "status_code=400" in odsecak, "blokada ne vraća 400 pre otvaranja toka"
    assert "StreamingResponse" not in odsecak, (
        "blokada otvara SSE tok — poruka o odbijanju bi stigla kao sadržaj odgovora"
    )


# ─── 3. NEGATIVNA KONTROLA ──────────────────────────────────────────────────

def test_ng_detektor_bi_uhvatio_odsustvo_guarda():
    """Dokaz da `_telo_funkcije` stvarno izoluje telo, a ne ceo fajl.

    Da vraća ceo `api.py`, svi testovi iznad bi prolazili vakuumski — jer
    `/api/pitanje` guard postoji negde u fajlu bez obzira na stream granu.
    """
    telo_stream = _telo_funkcije("pitanje_stream")
    telo_pitanje = _telo_funkcije("pitanje")
    assert telo_stream != telo_pitanje, "izolacija tela ne radi — vraća isto"
    assert len(telo_stream) < len(open(os.path.join(_KOREN, "api.py"), encoding="utf-8").read()) / 2, (
        "izolovano telo je prevelko — verovatno obuhvata pola fajla"
    )
    # Marker koji postoji SAMO u streaming grani.
    assert "SSE" in telo_stream or "[DONE]" in telo_stream
