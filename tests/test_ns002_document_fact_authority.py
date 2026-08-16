# -*- coding: utf-8 -*-
"""
NS002 / NS001-P0-001 — KARAKTERIZACIJA, NE POPRAVKA.

STATUS: 🟡 BLOKIRANO. Produkcijski kod NIJE menjan (v. `docs/beta_gate/
NS002_DOCUMENT_FACT_DETERMINISM.md`). Ovi testovi ZAKLJUČAVAJU IZMERENO
PONAŠANJE dva mehanizma koji zajedno obaraju P0 tok, da bi sledeća izmena
morala da bude svesna.

════════════════════════════════════════════════════════════════════════════
ŠTA JE DOKAZANO
════════════════════════════════════════════════════════════════════════════

Advokat pita nešto što piše ISKLJUČIVO u njegovom dokumentu. Retrieval radi —
to je dokazano u NS001 (direktna pretraga indeksa nalazi pasus; log pokazuje
identičan retrieval u svakom pokušaju). Ipak, odgovor često ne sadrži činjenicu.
Uzroka ima DVA, i oba su izmerena.

── MEHANIZAM 1 — DOC GATE se ne izvršava za kanonski tok ───────────────────

`main.py::ask_agent` ima „DOC GATE BIAS": kad pasus advokatovog dokumenta ima
skor ≥ 0.5, pojas pouzdanosti se podiže za jedan stepen, da odgovor ne bi bio
odbijen samo zato što je zakonski korpus slabo pogodio pitanje.

Taj mehanizam je zaključan iza `if extra_namespaces:` — parametra STARE šeme
(`tmp_<session>`, firmin namespace). Od BR-003 dokumenti predmeta stižu drugim
putem: vlasnički namespace se IZVODI unutar `retrieve_documents` iz identiteta,
pa je `extra_namespaces` za kanonsko pitanje o predmetu `None`. Dakle mehanizam
se za taj tok **ne izvršava nijednom**.

Posledica: kad zakonski `top_score` padne ispod praga, `ask_agent` KORAK 2
(`main.py`, `if confidence == "LOW"`) vraća instant odbijanje **pre ijednog LLM
poziva i bez gledanja u `docs`** — „Nemam pouzdan odgovor u trenutnoj bazi
zakona", za činjenicu koja doslovno piše u dokumentu.

── MEHANIZAM 2 — blokada odgovora odnosi i činjenicu iz dokumenta ──────────

Ako se sinteza ipak pokrene, pasus dokumenta stigne modelu i model vrati
činjenicu. Ali kada anti-halucinacioni guard (`[MEDIUM→BLOCK] Commit3 guard`)
obori odgovor, ceo tekst se zamenjuje kanonskim „Opšta pravna logika — nema
direktnog člana u bazi". Blokada je sve-ili-ništa, pa nestaje i činjenica iz
dokumenta, koja nikad nije bila sporna.

TAČAN OKIDAČ BLOKADE U PRODUKCIJI NIJE DOKAZAN i ovde se NE tvrdi. Izmereno je
samo da se blokada dešava (ista log linija, 9 od 10 pokušaja scenarija J) i da
uz nju odlazi i dokumentarna činjenica.

Mereno stvarnim E2E prolaskom (pravi model, prava baza, pravi Pinecone), isti
dokument i isto pitanje, 10 pokušaja:

    A  „Koliki je iznos ugovorne kazne prema dokumentu?"        10/10 PASS
    J  „Koji je zakonski rok ... i koji rok piše u dokumentu?"   1/10 PASS

Devet od deset J odgovora je doslovno „nema direktnog člana u bazi".

════════════════════════════════════════════════════════════════════════════
ZAŠTO POPRAVKA NIJE UŠLA
════════════════════════════════════════════════════════════════════════════

Uklanjanje `extra_namespaces` uslova je izvedeno i izmereno. Ono zatvara
MEHANIZAM 1, ali time više pitanja stiže do sinteze — pa ih MEHANIZAM 2 obori.
Izmereno posle te izmene: J je pao sa 4/5 na 1/10. Popravka koja merljivo
pogoršava stvarni scenario nije popravka, pa je vraćena.

Zatvaranje zahteva odluku koju ovaj sprint nema pravo da donese: sme li
odgovor da pretekne sa POTVRĐENOM činjenicom iz dokumenta kada je njegov PRAVNI
deo neproverljiv. To je slabljenje bezbednosnog mehanizma i pripada vlasniku
proizvoda.

════════════════════════════════════════════════════════════════════════════
KAKO ČITATI OVE TESTOVE
════════════════════════════════════════════════════════════════════════════

Oni tvrde ono što sistem DANAS radi, uključujući ono što radi POGREŠNO. Kada se
blocker zatvori, testovi označeni `# KVAR` MORAJU da padnu — i tada se prepisuju
uz obrazloženje. Zeleni prolaz ovog fajla NE znači da tok radi.
"""
import os
import sys
from unittest.mock import patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)

import pytest  # noqa: E402

CINJENICA = "Ugovorna kazna iznosi 17.350 EUR po danu zakasnjenja."
PASUS = ("KORISNIKOV DOKUMENT (OVAJ PREDMET) [ugovor.docx, chunk 0]\n\n"
         "Clan 2. " + CINJENICA)


def _meta(conf="LOW", law_score=0.31, doc_score=0.62, sa_dokumentom=True):
    return {
        "confidence": conf,
        "top_score": law_score,
        "top_article": "Član 266",
        "top_law": "zakon o obligacionim odnosima",
        "confidence_detail": {},
        "izvori": [],
        "doc_passages": ([{"score": doc_score, "text_snippet": CINJENICA,
                           "same_case": True, "predmet_id": "p1"}]
                         if sa_dokumentom else []),
        "praksa_matches": [],
        "match_breakdown": [],
    }


def _vozi(meta, docs, extra_namespaces=None, odgovor_modela=None, vrati_meta=None):
    """Vozi PRAVI `ask_agent`; beleži da li je sinteza uopšte pokrenuta i šta je
    stvarno otišlo modelu."""
    import main as M

    z = {"model_pozvan": False, "kontekst": ""}

    def _lazni_model(*a, **k):
        # `_pozovi_openai(system_prompt, user_content, ...)` prima i vraća STRING.
        z["model_pozvan"] = True
        sp = k.get("system_prompt") or (a[0] if len(a) > 0 else "")
        uc = k.get("user_content") or (a[1] if len(a) > 1 else "")
        z["kontekst"] = str(sp) + chr(10) + str(uc)
        return odgovor_modela or (
            "--- HIJERARHIJA IZVORA" + chr(10) + "Opsti propis." + chr(10) * 2
            + "--- PRAVNI ZAKLJUCAK" + chr(10) + CINJENICA + chr(10) * 2
            + "--- PRAVNI OSNOV" + chr(10) + "ZOO cl. 266" + chr(10)
        )

    _meta_ruta = vrati_meta if vrati_meta is not None else dict(meta)
    with patch.object(M, "retrieve_documents", return_value=(docs, _meta_ruta)), \
         patch.object(M, "_cache_get", return_value=None), \
         patch.object(M, "_cache_set", lambda *a, **k: None), \
         patch.object(M, "_pozovi_openai", _lazni_model), \
         patch.object(M, "retrieve_sudska_praksa", return_value=[]), \
         patch.object(M, "retrieve_misljenja", return_value=[]):
        try:
            rez = M.ask_agent("Koliki je iznos ugovorne kazne?", None, extra_namespaces)
        except Exception as e:
            rez = {"status": "error", "message": str(e)}
    return rez, z


def _je_instant_odbijanje(rez) -> bool:
    """LOW grana: odbijanje PRE ijednog LLM poziva, koje ne gleda `docs`."""
    return "Nemam pouzdan odgovor" in str(rez.get("data") or rez.get("message") or "")


# ═══════════════════════════════════════════════════════════════════════════
# 1 — MEHANIZAM 1: DOC GATE JE VEZAN ZA STARI PARAMETAR
# ═══════════════════════════════════════════════════════════════════════════

def test_1_KVAR_doc_gate_se_NE_izvrsava_za_vlasnicki_namespace():
    """# KVAR — ovo je izmereno stanje, ne željeno.

    `extra_namespaces=None` je STVARNO stanje kanonskog pitanja o predmetu
    (BR-003 izvodi namespace unutar retrieval-a). Pasus dokumenta ima skor 0.62,
    znatno iznad praga 0.5 — a odgovor se svejedno odbija pre modela.
    """
    rez, z = _vozi(_meta(conf="LOW"), [PASUS], extra_namespaces=None)
    assert _je_instant_odbijanje(rez), (
        "DOC GATE sada radi i za vlasnički namespace — MEHANIZAM 1 je zatvoren; "
        "prepiši ovaj test uz obrazloženje"
    )
    assert z["model_pozvan"] is False, "sinteza je pokrenuta — MEHANIZAM 1 zatvoren"


def test_1b_stari_put_radi():
    """Kontrola nad merenjem: mehanizam POSTOJI i radi — samo za staru šemu.
    Bez ovoga se test_1 mogao objasniti i time da DOC GATE uopšte ne funkcioniše."""
    rez, z = _vozi(_meta(conf="LOW"), [PASUS], extra_namespaces=["tmp_x"])
    assert not _je_instant_odbijanje(rez), rez
    assert z["model_pozvan"] is True


def test_1c_bez_dokumenta_LOW_ostaje_odbijanje():
    """Ispravno fail-closed ponašanje koje se NE sme oslabiti pri popravci."""
    rez, z = _vozi(_meta(conf="LOW", sa_dokumentom=False), ["ZAKON: tekst " * 20])
    assert _je_instant_odbijanje(rez), rez
    assert z["model_pozvan"] is False


def test_1d_slab_pasus_dokumenta_ne_podize_pojas():
    """Prag 0.5 je deo ugovora — slab pasus ne sme da gasi fail-closed."""
    rez, z = _vozi(_meta(conf="LOW", doc_score=0.31), [PASUS], extra_namespaces=["tmp_x"])
    assert _je_instant_odbijanje(rez), rez
    assert z["model_pozvan"] is False


@pytest.mark.parametrize("ulaz,izlaz", [("LOW", "MEDIUM"), ("MEDIUM", "HIGH"),
                                        ("HIGH", "HIGH")])
def test_1e_band_mapa(ulaz, izlaz):
    """Mapa pojaseva — referentna vrednost za buduću popravku."""
    meta = _meta(conf=ulaz)
    _vozi(meta, [PASUS], extra_namespaces=["tmp_x"], vrati_meta=meta)
    assert meta["confidence"] == izlaz, meta["confidence"]


def test_1f_izvor_kvara_je_imenovan():
    """Brava nad TAČNIM uslovom, da sledeća izmena bude svesna."""
    import inspect
    import main as M

    izvor = inspect.getsource(M.ask_agent)
    poz = izvor.index("DOC GATE BIAS")
    kraj = izvor.index('confidence        = retrieval_meta["confidence"]', poz)
    isecak = chr(10).join(l for l in izvor[poz:kraj].splitlines()
                          if not l.strip().startswith("#"))
    assert "if extra_namespaces:" in isecak, (
        "uslov je uklonjen — MEHANIZAM 1 je zatvoren; prepiši test_1 i ovaj test"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2 — MEHANIZAM 2: GUARD OBARA CEO ODGOVOR ZBOG PRAVNE REFERENCE
# ═══════════════════════════════════════════════════════════════════════════

def test_2_KVAR_kad_guard_blokira_nestaje_i_cinjenica_iz_dokumenta():
    """# KVAR — izmereno stanje.

    Sinteza se pokrece i pasus dokumenta stize modelu, ali kada guard
    (`[MEDIUM->BLOCK] Commit3 guard`) obori odgovor, ceo tekst se zamenjuje
    kanonskim `ODGOVOR_NIJE_PRONADJEN` — pa nestaje i cinjenica iz dokumenta,
    koja nikad nije bila sporna. Blokada je sve-ili-nista.

    GRANICA OVOG TESTA, izricito: ovde guard puca zato sto lazni model vraca
    obican tekst umesto JSON-a (`[COMMIT3] JSON parse greska`). U stvarnom E2E
    prolasku model vraca ispravan JSON, a blokada se svejedno desava — ista log
    linija, 9 od 10 pokusaja scenarija J. TACAN OKIDAC u produkciji NIJE
    dokazan ovim harness-om i zato se ovde NE tvrdi. Dokazano je samo ono sto
    ovaj test meri: kad guard blokira, cinjenica iz dokumenta ide s njim.
    """
    rez, z = _vozi(_meta(conf="LOW"), [PASUS], extra_namespaces=["tmp_x"])
    assert z["model_pozvan"] is True
    assert "17.350" in z["kontekst"], "cinjenica nije ni stigla modelu"
    tekst = str(rez.get("data") or "")
    assert rez.get("blocked") is True, rez.get("blocked")
    assert "17.350" not in tekst, (
        "cinjenica iz dokumenta sada prezivljava blokadu — prepisi ovaj test"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3 — PASUS DOKUMENTA STVARNO STIŽE MODELU (retrieval nije uzrok)
# ═══════════════════════════════════════════════════════════════════════════

def test_3_cinjenica_je_u_model_inputu():
    """Zatvara alternativno objašnjenje: nije da model ne vidi činjenicu."""
    _rez, z = _vozi(_meta(conf="LOW"), [PASUS], extra_namespaces=["tmp_x"])
    assert z["model_pozvan"] is True
    assert "17.350" in z["kontekst"], z["kontekst"][:400]
