# -*- coding: utf-8 -*-
"""
B4 — NEUSPEH IZVORA NIJE PRAZAN IZVOR; MODEL NIJE AUTORITET NAD STANJEM BAZE.

ŠTA JE BILO — reprodukovano determinističkim harnessom (B4 forenzika, 2026-08-18)

Tri mesta su `FAILED` kolabirala u `EMPTY`, a `retrieval_meta` nije imao NIJEDNO
polje kojim bi razliku preneo dalje:

  1. app/services/retrieve.py::_pretraga_ns        except -> return []
     (popravka: izuzetak se PROPUSTA; potpis nepromenjen -- v. test_A)
  2. app/services/retrieve.py  (sakupljanje NS-a)  except -> logger.warning
     — uključujući `TimeoutError` iz `.result(timeout=5.0)`
  3. app/services/retrieve.py  (pad embeddinga)    except -> return [], {LOW, …}

Posledice koje su izmerene, ne pretpostavljene:

  * pad embeddinga -> `ask_agent` vraća `status:"success"` i tekst
    „Nemam pouzdan odgovor … u trenutnoj bazi zakona … pitanje izlazi iz
    indeksiranih oblasti" — dakle ISPAD SERVISA se isporučuje kao TVRDNJA O
    SADRŽAJU PRAVNOG KORPUSA, uz 0 poziva modelu;
  * zakon USPEO + dokumenti PALI -> tok stiže do sinteze kao da je sve u redu,
    kontekst poslat modelu ne pominje pad, a odgovor nema nijedno polje kojim
    bi se pad izrazio (ključevi: confidence, confidence_detail, data, izvori,
    status, top_article, top_law, top_score).

UGOVOR KOJI OVI TESTOVI ZAKLJUČAVAJU

    izvor OK            -> nema oznake, model se zove
    izvor PRAZAN        -> nema oznake (prazno JESTE nalaz)
    dokumenti PALI      -> odgovor se isporučuje, ali NOSI oznaku `izvori_neuspeh`
    zakonski korpus PAO -> fail-closed, BEZ modela, bez tvrdnje o korpusu
    LOW + bilo koji pad -> ne sme se tvrditi odsustvo

ZAŠTO SOPSTVENI HARNESS (FAZA 5 — harness forensics)

Mock koji vraća iste redove bez obzira na `namespace` ne može reprodukovati
parcijalni ispad. `_Index` ispod pada SELEKTIVNO po namespace-u, pa je scenario
„zakon OK + dokumenti PALI" stvarno izvršen, a ne simuliran.
Broj poziva modela se MERI (`_llm.n`) — bez toga bi test „model nije pozvan"
prolazio i kad se model ne zove nikada, pa `test_H_*` postoji kao kontrola.
Nijedan test u ovom fajlu ne pravi mrežni poziv: rerank/CRAG/HyDE/dekompozicija
su eksplicitno zamenjeni (inače stvarno gađaju OpenAI — izmereno: HTTP 401).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "admin@vindex.ai")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.services.retrieve as R  # noqa: E402
import main as M  # noqa: E402

ZAKON = R.IZVOR_ZAKON
DOKUMENTI = R.IZVOR_DOKUMENTI

VLASNICKI_NS = "user_x"


@pytest.fixture(autouse=True)
def _bez_kesa():
    """`ask_agent` kešira odgovor po tekstu pitanja (`main.py:183 _CACHE`).

    HARNESS FORENSICS: bez ovoga drugi test sa istim pitanjem dobija keširan
    rezultat PRVOG, `retrieve_documents` se uopšte ne izvrši, a `llm.n` ostaje
    0 — pa bi testovi „model se ne zove" prolazili iz potpuno pogrešnog
    razloga. Nađeno merenjem (`from_cache: True` u odgovoru), ne čitanjem.
    """
    M._CACHE.clear()
    with patch.object(M, "_supa_cache_get", return_value=None), \
         patch.object(M, "_supa_cache_set", return_value=None):
        yield
    M._CACHE.clear()


class _Match:
    def __init__(self, ns, score=0.9):
        self.id = "v1"
        self.score = score
        self.metadata = {
            "text": "Član 262 ZOO: ugovorna kazna se može ugovoriti…",
            "zakon": "ZOO", "article_label": "262", "type": "case_doc",
            "chunk_index": 0, "predmet_id": "p1", "origin": "client_doc",
        }


class _Index:
    """Pinecone koji pada SELEKTIVNO po namespace-u — bez toga nema parcijalnog ispada."""

    def __init__(self, puca_ns=None, prazan_ns=None):
        self.puca_ns = set(puca_ns or ())
        self.prazan_ns = set(prazan_ns or ())

    def query(self, **kw):
        ns = kw.get("namespace") or ""
        if ns in self.puca_ns:
            raise RuntimeError(f"simuliran ispad namespace-a {ns}")

        class _R:
            matches = [] if ns in self.prazan_ns else [_Match(ns)]
        return _R()


def _retrieve(puca_ns=None, prazan_ns=None, embedding_puca=False):
    """PRAVI `retrieve_documents`, bez ijednog mrežnog poziva."""
    _emb = (lambda _q: (_ for _ in ()).throw(RuntimeError("embedding 503"))) \
        if embedding_puca else (lambda _q: [0.1] * 8)
    with patch.object(R, "_ugradi_query", side_effect=_emb), \
         patch.object(R, "_get_index", return_value=_Index(puca_ns, prazan_ns)), \
         patch.object(R, "_pretraga_praksa", return_value=[]), \
         patch.object(R, "_dekomponuj_query", return_value=[]), \
         patch.object(R, "decompose_query", return_value=[]), \
         patch.object(R, "_generiši_hyde", return_value=""), \
         patch.object(R, "_gpt_rerank", side_effect=lambda q, m, k=3: m[:k]), \
         patch.object(R, "_cohere_rerank", side_effect=lambda q, m, k=3: m[:k]), \
         patch.object(R, "_oceni_relevantnost", return_value="RELEVANTNO"), \
         patch.object(R, "_prosiri_pretragu_crag", return_value=[]), \
         patch.object(R, "_prosiri_query_gpt_wrapper", return_value=[]), \
         patch.object(R, "_vlasnicki_opseg_iz_konteksta",
                      return_value=(VLASNICKI_NS, ["p1"])):
        return R.retrieve_documents("Koliko iznosi ugovorna kazna po mom ugovoru?", k=5)


class _Brojac:
    def __init__(self, odgovor='{"pravni_zakljucak":"x"}'):
        self.n = 0
        self.kontekst = ""
        self.odgovor = odgovor

    def __call__(self, system_prompt, user_content, **kw):
        self.n += 1
        self.kontekst = user_content
        return self.odgovor


def _ask(docs, meta, pitanje="Koliko iznosi ugovorna kazna po mom ugovoru i šta kaže zakon?"):
    """PRAVI `ask_agent` sa izmerenim brojem poziva modela."""
    llm = _Brojac()
    with patch.object(M, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(M, "_pozovi_openai", side_effect=llm), \
         patch.object(M, "retrieve_sudska_praksa", return_value=[]), \
         patch.object(M, "retrieve_misljenja", return_value=[]):
        rez = M.ask_agent(pitanje)
    return rez, llm


def _meta(confidence="HIGH", top=0.9, neuspeh=None, izvori=None):
    return {
        "top_score": top, "top_article": "262", "top_law": "ZOO",
        "top_text": "Ugovorna kazna…", "confidence": confidence,
        "confidence_detail": {"band": confidence},
        "izvori": izvori if izvori is not None else [{"zakon": "ZOO", "clan": "262"}],
        "doc_passages": [], "praksa_matches": [], "match_breakdown": [],
        "izvori_neuspeh": list(neuspeh or []),
    }


DOCS = ["[ZOO član 262] Ugovorna kazna se može ugovoriti u novcu " + "x" * 80]


# ═══════════════════════════════════════════════════════════════════════════
# A. PRE-STATE REPRODUCTION
# ═══════════════════════════════════════════════════════════════════════════

def test_A_pretraga_ns_vise_ne_guta_neuspeh():
    """Potpis je NEPROMENJEN; menja se samo to da neuspeh vise nije `[]`.

    Sva tri produkcijska pozivaoca vec hvataju izuzetak, pa se njihovo
    ponasanje ne menja -- ali sada MOGU da razlikuju pad od praznog rezultata.
    """
    with patch.object(R, "_get_index", return_value=_Index(puca_ns={"ns1"})):
        with pytest.raises(Exception):
            R._pretraga_ns([0.0] * 8, "ns1", 5)
    with patch.object(R, "_get_index", return_value=_Index(prazan_ns={"ns1"})):
        assert R._pretraga_ns([0.0] * 8, "ns1", 5) == []


def test_A2_pad_i_prazno_vise_NISU_isti_ishod():
    """Jezgro B4, mereno kroz PRAVI `retrieve_documents`."""
    _d1, pao = _retrieve(puca_ns={VLASNICKI_NS})
    _d2, prazan = _retrieve(prazan_ns={VLASNICKI_NS})

    assert pao["doc_passages"] == prazan["doc_passages"] == []   # rezultat isti…
    assert pao["izvori_neuspeh"] == [DOKUMENTI]                  # …stanje nije
    assert prazan["izvori_neuspeh"] == []


def test_A3_pad_embeddinga_vise_ne_izgleda_kao_validan_LOW():
    docs, meta = _retrieve(embedding_puca=True)
    assert docs == []
    assert set(meta["izvori_neuspeh"]) == {ZAKON, DOKUMENTI}


# ═══════════════════════════════════════════════════════════════════════════
# B/D/F. HAPPY PATH · PRAZNO · OK+PRAZNO
# ═══════════════════════════════════════════════════════════════════════════

def test_B_svi_izvori_OK_nema_oznake():
    docs, meta = _retrieve()
    assert meta["izvori_neuspeh"] == []
    assert docs, "zakonski korpus nije vratio kontekst — test ne bi merio ništa"


def test_D_prazan_vlasnicki_namespace_NIJE_neuspeh():
    docs, meta = _retrieve(prazan_ns={VLASNICKI_NS})
    assert meta["izvori_neuspeh"] == [], "prazan izvor je pogrešno prijavljen kao pao"


def test_F_zakon_OK_dokumenti_PRAZNI_nema_oznake():
    _docs, meta = _retrieve(prazan_ns={VLASNICKI_NS})
    assert meta["izvori_neuspeh"] == []
    assert meta["confidence"] in ("LOW", "MEDIUM", "HIGH")


# ═══════════════════════════════════════════════════════════════════════════
# C/E/G/K. FAILED · PARCIJALNI ISPAD · VIŠE ISPADA
# ═══════════════════════════════════════════════════════════════════════════

def test_C_pao_vlasnicki_namespace_se_IMENUJE():
    _docs, meta = _retrieve(puca_ns={VLASNICKI_NS})
    assert meta["izvori_neuspeh"] == [DOKUMENTI]


def test_E_zakon_OK_dokumenti_PALI_parcijalni_ispad_je_vidljiv():
    """FAZA C iz forenzike: ranije je ovo bilo neraspoznatljivo od punog uspeha."""
    docs, meta = _retrieve(puca_ns={VLASNICKI_NS})
    assert docs, "zakonski deo mora i dalje raditi"
    assert meta["confidence"] == "HIGH"
    assert meta["izvori_neuspeh"] == [DOKUMENTI]


def test_K_kombinovano_pitanje_ne_maskira_parcijalni_ispad():
    """Odgovor se isporučuje, ali NIKAD kao potpuno proveren."""
    _docs, meta = _retrieve(puca_ns={VLASNICKI_NS})
    rez, llm = _ask(DOCS, meta)

    assert rez["izvori_neuspeh"] == [DOKUMENTI], (
        f"parcijalni ispad nije stigao do odgovora: {sorted(rez.keys())}")
    assert llm.n == 1, "parcijalni odgovor je dozvoljen — model se sme zvati"
    assert DOKUMENTI in llm.kontekst and "NISU provereni" in llm.kontekst, (
        "model je i dalje video pao izvor kao PRAZAN izvor")


def test_G_vise_ispada_zaustavlja_tok_fail_closed():
    docs, meta = _retrieve(embedding_puca=True)
    rez, llm = _ask(docs, meta)

    assert rez["status"] == "error"
    assert rez["retrieval_unavailable"] is True
    assert llm.n == 0


# ═══════════════════════════════════════════════════════════════════════════
# H/I. KADA SME, A KADA NE SME BITI POZVAN MODEL
# ═══════════════════════════════════════════════════════════════════════════

def test_H_model_SE_ZOVE_kad_su_svi_izvori_procitani():
    """Kontrola: bez ovoga bi `test_I` prolazio i da se model ne zove nikad."""
    rez, llm = _ask(DOCS, _meta())
    assert llm.n == 1
    assert rez["status"] == "success"


def test_I_model_se_NE_ZOVE_kad_zakonski_korpus_nije_pretrazen():
    rez, llm = _ask(DOCS, _meta(neuspeh=[ZAKON]))
    assert llm.n == 0, "model je pozvan iako korpus nije pretražen"
    assert rez["status"] == "error"
    assert rez["retrieval_unavailable"] is True


def test_I2_model_se_NE_ZOVE_na_LOW_uz_nepretrazen_izvor():
    rez, llm = _ask([], _meta(confidence="LOW", top=0.1, neuspeh=[DOKUMENTI], izvori=[]))
    assert llm.n == 0
    assert rez["status"] == "error"
    assert rez["retrieval_unavailable"] is True


# ═══════════════════════════════════════════════════════════════════════════
# J. NIKAD TVRDNJA O ODSUSTVU IZ UPITA KOJI NIJE USPEO
# ═══════════════════════════════════════════════════════════════════════════

_ZABRANJENE = ["u trenutnoj bazi zakona", "izlazi iz indeksiranih oblasti"]


@pytest.mark.parametrize("neuspeh", [[ZAKON], [DOKUMENTI], [ZAKON, DOKUMENTI]])
def test_J_pao_izvor_ne_daje_tvrdnju_o_odsustvu(neuspeh):
    rez, _llm = _ask([], _meta(confidence="LOW", top=0.1, neuspeh=neuspeh, izvori=[]))
    tekst = (rez.get("data") or "")
    for fraza in _ZABRANJENE:
        assert fraza not in tekst, (
            f"ZABRANJENO: izvor {neuspeh} nije proveren, a sistem tvrdi `{fraza}` -> {tekst!r}")
    assert "NE tvrdim" in tekst or "NIJE tvrdnja" in tekst


def test_J2_legitiman_LOW_i_dalje_sme_da_kaze_da_nema_odgovora():
    """Regresija: bez pada izvora zatečena poruka mora ostati nepromenjena."""
    rez, llm = _ask([], _meta(confidence="LOW", top=0.1, neuspeh=[], izvori=[]))
    assert rez["status"] == "success"
    assert "u trenutnoj bazi zakona" in rez["data"]
    assert llm.n == 0


# ═══════════════════════════════════════════════════════════════════════════
# L/M. REGRESIJA
# ═══════════════════════════════════════════════════════════════════════════

def test_L_single_domain_pitanje_nepromenjeno():
    # Namerno BEZ izričitog broja člana: `ekstrakcija_clana` bi pokrenula
    # `_direktan_fetch_clana`, koji je zaseban (i već zaštićen) put — ovaj test
    # meri B4 ponašanje na običnom jednodomenskom pitanju, ne taj guard.
    rez, llm = _ask(DOCS, _meta(), pitanje="Šta je ugovorna kazna po ZOO?")
    assert rez["status"] == "success"
    assert llm.n == 1
    assert "UPOZORENJE O IZVORIMA" not in llm.kontekst


def test_M_uspesan_odgovor_zadrzava_postojeci_oblik():
    rez, _llm = _ask(DOCS, _meta())
    for k in ("status", "data", "confidence", "top_score", "top_article", "top_law", "izvori"):
        assert k in rez, f"nedostaje postojeće polje `{k}`"
    assert rez["izvori_neuspeh"] == []


# ═══════════════════════════════════════════════════════════════════════════
# N/O. NEGATIVNE INVARIJANTE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("neuspeh,conf", [
    ([ZAKON], "HIGH"), ([ZAKON], "MEDIUM"), ([ZAKON], "LOW"),
    ([ZAKON, DOKUMENTI], "HIGH"), ([DOKUMENTI], "LOW"),
])
def test_N_required_source_failed_ne_daje_autorizovan_rezultat(neuspeh, conf):
    """REQUIRED_SOURCE_FAILED ⇒ NOT AUTHORIZED_RESULT."""
    rez, llm = _ask(DOCS, _meta(confidence=conf, neuspeh=neuspeh))
    autorizovan = (
        rez.get("status") == "success"
        and not rez.get("izvori_neuspeh")
        and not rez.get("retrieval_unavailable")
    )
    assert not autorizovan, (
        f"ZABRANJENO STANJE: izvori {neuspeh} nisu provereni, a odgovor je "
        f"isporučen kao potpuno proveren -> {sorted(rez.keys())}")


def test_O_source_failed_nije_source_empty():
    """SOURCE_FAILED ⇒ NOT SOURCE_EMPTY — na nivou retrieval sloja."""
    _d1, pao = _retrieve(puca_ns={VLASNICKI_NS})
    _d2, prazan = _retrieve(prazan_ns={VLASNICKI_NS})

    assert pao["doc_passages"] == prazan["doc_passages"] == []
    assert pao["izvori_neuspeh"] != prazan["izvori_neuspeh"], (
        "pao i prazan izvor daju identično stanje — B4 je otvoren")


def test_O2_meta_uvek_nosi_polje_o_stanju_izvora():
    for kw in ({}, {"puca_ns": {VLASNICKI_NS}}, {"prazan_ns": {VLASNICKI_NS}},
               {"embedding_puca": True}):
        _docs, meta = _retrieve(**kw)
        assert "izvori_neuspeh" in meta, f"meta bez polja o stanju izvora ({kw})"
        assert isinstance(meta["izvori_neuspeh"], list)
