# -*- coding: utf-8 -*-
"""B4-M2 — INTEGRITET ČINJENICE IZ KORISNIKOVOG DOKUMENTA.

Dokazan kvar (HEAD 84fb7f96, pre popravke): `main._dokumentarne_cinjenice`
poštovao je budžet `_DOK_CITAT_MAX` tako što je telo pasusa SEKAO na
proizvoljnom znaku, a fragment je zatim dobijao iste oznake kao ceo navod
(`source_type=USER_DOCUMENT`, `verification_state=READ_OK`) i stizao u UI pod
naslovom „Doslovan navod iz dokumenta koji ste dostavili" (static/vindex.js).

Izmereno na produkcionoj vrednosti `_DOK_CITAT_MAX = 1200`:

    dokument kaže:      "Kazna je 500.000,00 dinara."
    advokat je video:   "Kazna je 500.0"          verification_state=READ_OK
    dokument kaže:      "Zakljucen 14.03.2026. godine."
    advokat je video:   "Zakljucen 14.03.2026."   (datum bez godine)

To nije IZGUBLJENA činjenica nego IZMENJENA — pola miliona prikazano kao 500,0,
potpisano kao pročitano iz dokumenta. Tačno ono što B4 zabranjuje: „ne gubi, ne
menja i ne potiskuje originalnu činjenicu".

Ovaj paket NE meri „da li odgovor izgleda dobro". Meri PROVENANCE: da svaki
emitovan navod odgovara DOSLOVNO telu pasusa iz kog je izveden, i da nijedan
odsečen fragment ne može biti potpisan sa READ_OK.

Napomena o granicama: `cinjenice_iz_dokumenta` gradi backend iz `docs`, bez
učešća modela, pa se ovde model namerno NE poziva — nema šta da se mokuje.
Testovi koji pokrivaju put kroz model, sheme i API granicu žive u
`tests/test_b4m2_document_authority.py` i ne diraju se.
"""
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main as M  # noqa: E402

L_ISTI = "KORISNIKOV DOKUMENT (OVAJ PREDMET)"
L_RANIJI = "KORISNIKOV DOKUMENT (RANIJI PREDMET IZ KANCELARIJE)"
L_GOLI = "KORISNIKOV DOKUMENT"

MAX = M._DOK_CITAT_MAX


def _pasus(fajl, chunk, telo, label=L_ISTI):
    """Isti oblik koji piše `app.services.doc_formatter.format_doc_passage`."""
    return "%s [%s, chunk %d]\n\n%s" % (label, fajl, chunk, telo)


def _telo(pasus):
    return pasus.partition("\n")[2].strip()


def _zakon(n=1):
    """Zakonski pasus — namerno DUŽI od činjenice i pun konkurentskih brojeva,
    datuma i rokova, da bi svaki test proveravao baš potiskivanje."""
    telo = (
        "Ugovorna kazna ne može biti ugovorena za novčane obaveze. "
        "Rok zastarelosti iznosi tri godine od dana dospelosti. "
        "Zakon je stupio na snagu 01.01.1978. godine. "
        "Kamata se obračunava po stopi od 9,50 procenata. "
        "Predmet broj P-9999/99 nije relevantan za ovu odredbu. "
    ) * 12
    return "ZAKON O OBLIGACIONIM ODNOSIMA, član 277 [zoo, chunk %d]\n\n%s" % (n, telo)


# ═══════════════════════════════════════════════════════════════════════════
# 1 — KVAR → REGRESIJA: ODSEČENA VREDNOST SE NIKAD NE EMITUJE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ostatak,telo,vrednost", [
    (14, "Kazna je 500.000,00 dinara.", "500.000,00"),
    (16, "Kazna je 500.000,00 dinara.", "500.000,00"),
    (19, "Kazna je 500.000,00 dinara.", "500.000,00"),
    (22, "Zakljucen 14.03.2026. godine.", "14.03.2026"),
    (25, "Zakljucen 14.03.2026. godine.", "14.03.2026"),
    (12, "Rok za ispunjenje je 30 dana.", "30 dana"),
])
def test_odsecena_vrednost_se_ne_emituje(ostatak, telo, vrednost):
    """Za SVAKI ostatak budžeta: ili ceo navod, ili ništa. Nikad fragment.

    Pre popravke je ovde izlazilo npr. 'Kazna je 500.0' sa READ_OK.
    """
    docs = [_pasus("prvi.pdf", 0, "X" * (MAX - ostatak)),
            _pasus("drugi.pdf", 1, telo)]
    c = M._dokumentarne_cinjenice(docs, [])
    drugi = [x for x in c if x["dokument"] == "drugi.pdf"]
    if drugi:
        assert drugi[0]["navod"] == telo, (
            "emitovan ODSEČEN navod %r umesto celog %r — sistem tvrdi da "
            "dokument kaže nešto što ne kaže" % (drugi[0]["navod"], telo))
        assert vrednost in drugi[0]["navod"]
    # Odsustvo je dozvoljeno (budžet), izmena nije.


def test_nijedan_emitovan_navod_nije_fragment_svog_pasusa():
    """Nasumično, ali determinističko (seed) — 400 kombinacija dužina.

    Ovo je test koji bi pao na SVAKOJ varijanti sečenja, ne samo na onoj koju
    smo izmerili.
    """
    random.seed(20260821)
    for _ in range(400):
        tela = ["".join(random.choice("abcdefg 0123456789.,")
                        for _ in range(random.randint(40, 900)))
                for _ in range(random.randint(1, 6))]
        docs = [_pasus("d%d.pdf" % i, i, t) for i, t in enumerate(tela)]
        for x in M._dokumentarne_cinjenice(docs, []):
            i = int(x["dokument"][1:-4])
            assert x["navod"] == tela[i].strip(), (
                "navod je odsečen: %d znakova umesto %d"
                % (len(x["navod"]), len(tela[i].strip())))


def test_budzet_i_dalje_vazi():
    """Popravka ne sme da otvori budžet — inače bi rešila integritet tako što
    bi napravila drugi problem (neograničen kontekst)."""
    docs = [_pasus("d%d.pdf" % i, i, "A" * 400) for i in range(10)]
    c = M._dokumentarne_cinjenice(docs, [])
    assert sum(len(x["navod"]) for x in c) <= MAX


def test_kraca_cinjenica_iza_preskocene_i_dalje_ulazi():
    """`continue`, ne `break`: preskakanje jedne prevelike činjenice ne sme da
    ubije sve iza nje — inače popravka gubi VIŠE nego kvar."""
    docs = [_pasus("dugi.pdf", 0, "Y" * (MAX - 40)),
            _pasus("nestaje.pdf", 1, "Z" * 100),
            _pasus("stane.pdf", 2, "Kazna 500.000,00 din")]
    imena = [x["dokument"] for x in M._dokumentarne_cinjenice(docs, [])]
    assert "stane.pdf" in imena, (
        "činjenica iza preskočene je izgubljena — `break` umesto `continue`")


# ═══════════════════════════════════════════════════════════════════════════
# 2 — ADVERSARIAL MATRICA: DOKUMENT vs DUGAČAK PRAVNI KONTEKST
# ═══════════════════════════════════════════════════════════════════════════

CINJENICE = [
    ("datum",          "Ugovor je zaključen 14.03.2026. godine.",          "14.03.2026"),
    ("rok",            "Rok za ispunjenje obaveze je 30 dana od potpisa.", "30 dana"),
    ("iznos",          "Ugovorna kazna iznosi 500.000,00 dinara.",         "500.000,00"),
    ("subjekt",        "Dužnik je PRIVREDNO DRUŠTVO ALFA DOO Beograd.",    "ALFA DOO"),
    ("broj_predmeta",  "Predmet se vodi pod brojem P-1234/26.",            "P-1234/26"),
    ("tvrdnja",        "Isporuka nije izvršena do ugovorenog roka.",       "nije izvršena"),
]


@pytest.mark.parametrize("naziv,telo,vrednost", CINJENICE,
                         ids=[c[0] for c in CINJENICE])
def test_cinjenica_prezivljava_dugacak_pravni_kontekst(naziv, telo, vrednost):
    """Šest zakonskih pasusa, svaki duži od činjenice i sa konkurentskim
    brojevima/datumima. Činjenica iz dokumenta mora izaći DOSLOVNO."""
    docs = [_zakon(i) for i in range(6)] + [_pasus("ugovor.pdf", 0, telo)]
    c = M._dokumentarne_cinjenice(docs, [])
    assert len(c) == 1, "pasus dokumenta je potisnut pravnim kontekstom"
    assert c[0]["navod"] == telo
    assert vrednost in c[0]["navod"]


@pytest.mark.parametrize("naziv,telo,vrednost", CINJENICE,
                         ids=[c[0] for c in CINJENICE])
def test_zakonski_pasus_ne_moze_da_se_predstavi_kao_cinjenica(naziv, telo, vrednost):
    """Obrnut smer: ništa iz zakonskog korpusa ne sme da uđe u kanal dokumenta.
    Zakon sadrži 9,50 / 01.01.1978 / P-9999/99 — nijedno ne sme da se pojavi.

    KRATAK zakonski pasus je OBAVEZAN u ovom skupu: dugi (`_zakon()`) ionako ne
    stane u budžet, pa bi ispao i bez provere labele — i mutacija „ukloni
    proveru labele" bi preživela. Kratak pasus u vernom `_formatiraj_match`
    obliku je jedini koji ovaj invariant stvarno meri.
    """
    kratak_zakon = ("ZAKON: Zakon o obligacionim odnosima\nČLAN: 277\n\n"
                    "CITABILNI TEKST: Kamata je 9,50 procenata od 01.01.1978. "
                    "Predmet P-9999/99, rok zastarelosti tri godine.\n")
    docs = [_zakon(i) for i in range(6)] + [kratak_zakon,
                                            _pasus("ugovor.pdf", 0, telo)]
    spojeno = " ".join(x["navod"] for x in M._dokumentarne_cinjenice(docs, []))
    for tudje in ("9,50", "01.01.1978", "P-9999/99", "zastarelosti"):
        assert tudje not in spojeno, (
            "vrednost iz ZAKONA je isporučena kao činjenica iz dokumenta: %r" % tudje)


def test_slab_pravni_rezultat_ne_menja_cinjenicu():
    """Slab/nerelevantan legal retrieval — dokument je i dalje pročitan isto."""
    telo = "Ugovorna kazna iznosi 500.000,00 dinara."
    bogato = [_zakon(i) for i in range(6)] + [_pasus("u.pdf", 0, telo)]
    oskudno = [_pasus("u.pdf", 0, telo)]
    assert (M._dokumentarne_cinjenice(bogato, [])
            == M._dokumentarne_cinjenice(oskudno, [])), (
        "količina pravnog konteksta menja šta sistem tvrdi da dokument kaže")


def test_razlicita_terminologija_ne_potiskuje_dokument():
    """Dokument kaže „penal", zakon kaže „ugovorna kazna" — različita reč za
    isti pojam ne sme da izbaci dokument iz kanala."""
    telo = "Ugovoreni penal je 500.000,00 dinara."
    docs = [_zakon(1), _pasus("u.pdf", 0, telo)]
    c = M._dokumentarne_cinjenice(docs, [])
    assert len(c) == 1 and c[0]["navod"] == telo


def test_konflikt_dokument_protiv_opsteg_pravila():
    """Dokument tvrdi ono što opšte pravilo zabranjuje. Kanal dokumenta mora
    ostati nepromenjen — rešavanje konflikta je posao odgovora, ne provenance."""
    telo = "Ugovorena je kazna za novčanu obavezu u iznosu od 500.000,00 dinara."
    docs = [_zakon(1), _pasus("u.pdf", 0, telo)]   # zakon: „ne može za novčane"
    c = M._dokumentarne_cinjenice(docs, [])
    assert c[0]["navod"] == telo, "pravno pravilo je prepisalo navod dokumenta"
    assert c[0]["verification_state"] == M.VERIF_READ_OK
    assert c[0]["source_type"] == M.SOURCE_USER_DOCUMENT


# ═══════════════════════════════════════════════════════════════════════════
# 3 — PROVENANCE OSTAJE BACKEND-OWNED
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("label", [L_ISTI, L_RANIJI, L_GOLI])
def test_sve_tri_labele_ulaze_u_kanal(label):
    """`format_doc_passage` piše tri labele; sve tri su korisnikov dokument."""
    telo = "Ugovorna kazna iznosi 500.000,00 dinara."
    c = M._dokumentarne_cinjenice([_pasus("u.pdf", 0, telo, label=label)], [])
    assert len(c) == 1 and c[0]["navod"] == telo


def test_svaki_emitovan_unos_nosi_pun_provenance():
    docs = [_pasus("a.pdf", 0, "Rok je 30 dana."), _pasus("b.pdf", 1, "Iznos 12,50.")]
    for x in M._dokumentarne_cinjenice(docs, []):
        assert x["source_type"] == M.SOURCE_USER_DOCUMENT
        assert x["verification_state"] == M.VERIF_READ_OK
        assert set(x) == {"navod", "dokument", "chunk", "source_type", "verification_state"}


def test_pad_pretrage_dokumenata_ne_daje_nijednu_cinjenicu():
    """INVARIANT 5/6 — netaknut popravkom: neuspeh nije prazan rezultat."""
    from app.services.retrieve import IZVOR_DOKUMENTI
    docs = [_pasus("u.pdf", 0, "Ugovorna kazna iznosi 500.000,00 dinara.")]
    assert M._dokumentarne_cinjenice(docs, [IZVOR_DOKUMENTI]) == []


def test_uobicajen_slucaj_je_bajt_identican():
    """Kad sve staje u budžet — a to je uobičajen slučaj — popravka ne menja
    ništa. Bez ovoga bi „integritet" mogao biti kupljen tihim gubitkom."""
    telo = ("Ugovor je zaključen 14.03.2026. Kazna 500.000,00 dinara. "
            "Rok 30 dana. Dužnik ALFA DOO. Predmet P-1234/26.")
    docs = [_pasus("ugovor.pdf", 7, telo)]
    c = M._dokumentarne_cinjenice(docs, [])
    assert c == [{
        "navod": telo,
        "dokument": "ugovor.pdf",
        "chunk": 7,
        "source_type": "USER_DOCUMENT",
        "verification_state": "READ_OK",
    }]
    assert c[0]["navod"] == _telo(docs[0])


# ═══════════════════════════════════════════════════════════════════════════
# 4 — NALAZ 2: PROVENANCE PREŽIVLJAVA BLOKIRANE IZLAZE
#
# OLD (`ed02b29f`, karakterizacija kvara): tri testa u ovoj sekciji tvrdila su
#     da `cinjenice_iz_dokumenta` NE POSTOJI na izlazima `filtrirani == []`,
#     „pravna greška" i „guard block". Nosili su izričitu uputu da MORAJU pasti
#     kad se blokator zatvori i da se tada ZAMENJUJU dokazom pokrivenosti.
#
# NEW: blokator je zatvoren. Isti izlazi sada nose kanal, pa ova sekcija tvrdi
#     suprotno — činjenica iz dokumenta preživljava blokadu pravnog dela.
#
# WHY: kanal je postojao na HIGH i LOW putu, a nedostajao je baš na blokiranim
#     izlazima — dakle tačno kad pravni deo padne, što je situacija zbog koje je
#     B4 i otvoren. Advokat je dobijao odbijanje bez ijednog traga o tome šta
#     njegov dokument kaže.
#
# GRANICA KOJU OVI TESTOVI ČUVAJU: dodavanje provenance-a NE SME da promeni
# odluku guard-a. Zato svaki test ispod tvrdi i `blocked`, i da tekst odgovora
# nije dobio nijednu novu tvrdnju.
# ═══════════════════════════════════════════════════════════════════════════

import contextlib  # noqa: E402
from unittest.mock import patch  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_b4_source_authority import _ask, _meta  # noqa: E402

_DOK_PASUS = ("KORISNIKOV DOKUMENT (OVAJ PREDMET) [ugovor.pdf, chunk 0]\n\n"
              "Ugovorna kazna iznosi 500.000,00 dinara. Ugovor zaključen 14.03.2026. "
              "Rok za ispunjenje je 30 dana. Dužnik ALFA DOO. Predmet P-1234/26.")
# Zakon namerno nosi DRUGE brojeve i DRUGI datum od dokumenta (§11 conflict).
#
# HARNESS FORENSICS: prva verzija ovog fixture-a bila je JEDNOLINIJSKA. Zbog
# toga je `telo` posle `partition("\n")` bilo prazno, pa je zakonski pasus
# ispadao iz `_dokumentarne_cinjenice` čak i kad se provera labele UKLONI —
# mutacija „zakon ulazi u kanal dokumenta" je preživela, a test je izgledao
# zeleno. Stvarni pasus iz `_formatiraj_match` je VIŠELINIJSKI, pa je fixture
# sada veran njegovom obliku. Bez toga INVARIANT B nije bio meren.
_ZAK_PASUS = ("ZAKON: Zakon o obligacionim odnosima\nČLAN: 262\n\n"
              "CITABILNI TEKST: Ugovorna kazna ne može preći 50.000,00 dinara. "
              "Zakon je stupio na snagu 01.01.1978. Rok zastarelosti je tri "
              "godine. Predmet P-9999/99.\n")


def _ask_bez_kesa(pitanje, dodatni_patch=None, conf="HIGH", top=0.9, docs=None):
    """`ask_agent` sa ISKLJUČENIM L1+L2 kešom.

    HARNESS FORENSICS: bez ovoga svaki naredni scenario dobija keširan odgovor
    prethodnog (`Cache HIT L1`), pa bi svi izgledali kao da nose kanal — a i
    upisivalo bi se u produkcionu `ai_cache` tabelu. Mereno, ne pretpostavljeno.
    """
    M._CACHE.clear()
    with contextlib.ExitStack() as st:
        st.enter_context(patch.object(M, "_supa_cache_get", return_value=None))
        st.enter_context(patch.object(M, "_supa_cache_set", return_value=None))
        if dodatni_patch is not None:
            st.enter_context(dodatni_patch)
        rez, _ = _ask(docs if docs is not None else [_ZAK_PASUS, _DOK_PASUS],
                      _meta(conf, top), pitanje=pitanje)
    M._CACHE.clear()
    return rez


def _navodi(rez):
    return " ".join(x["navod"] for x in (rez.get("cinjenice_iz_dokumenta") or []))


# ── kontrola harnessa ──────────────────────────────────────────────────────

def test_referenca_HIGH_i_LOW_put_NOSE_kanal():
    """Bez ove kontrole testovi ispod bi mogli da prolaze zbog pokvarenog
    harnessa, a ne zbog ispravnog koda."""
    assert "cinjenice_iz_dokumenta" in _ask_bez_kesa("B4M2 kontrola HIGH")
    assert "cinjenice_iz_dokumenta" in _ask_bez_kesa(
        "B4M2 kontrola LOW", conf="LOW", top=0.2)


# ── tri zatvorena izlaza ───────────────────────────────────────────────────

_BLOKIRANI = [
    ("filtrirani_prazan", lambda: patch.object(M, "_filtriraj_kontekst", return_value=[]), None),
    ("pravna_greska", lambda: patch.object(M, "_verifikuj_pravne_greske",
                                           return_value=(False, "izmišljen član")), True),
    ("guard_block", lambda: patch.object(M, "_parsiraj_strukturni_odgovor",
                                         return_value=(False, "BLOKIRANO")), True),
]


@pytest.mark.parametrize("naziv,mk,ocekivan_blocked", _BLOKIRANI,
                         ids=[b[0] for b in _BLOKIRANI])
def test_blokiran_izlaz_nosi_cinjenicu_iz_dokumenta(naziv, mk, ocekivan_blocked):
    rez = _ask_bez_kesa("B4M2 zatvoren %s" % naziv, mk())
    assert "cinjenice_iz_dokumenta" in rez, (
        "činjenica iz dokumenta ponovo nestaje sa blokadom pravnog dela")
    assert "500.000,00" in _navodi(rez)
    assert "14.03.2026" in _navodi(rez)


@pytest.mark.parametrize("naziv,mk,ocekivan_blocked", _BLOKIRANI,
                         ids=[b[0] for b in _BLOKIRANI])
def test_guard_ostaje_guard(naziv, mk, ocekivan_blocked):
    """INVARIANT C/D: provenance ne sme da promeni odluku guard-a niti da
    blokiran odgovor pretvori u odgovor."""
    rez = _ask_bez_kesa("B4M2 guard %s" % naziv, mk())
    assert rez.get("blocked") is ocekivan_blocked, (
        "guard odluka je promenjena dodavanjem provenance-a")


@pytest.mark.parametrize("naziv,mk,ocekivan_blocked", _BLOKIRANI,
                         ids=[b[0] for b in _BLOKIRANI])
def test_legal_context_ne_postaje_dokumentarna_cinjenica(naziv, mk, ocekivan_blocked):
    """INVARIANT B: zakon nosi 50.000,00 / 01.01.1978 / P-9999/99 — nijedno ne
    sme da se pojavi kao ono što DOKUMENT navodi."""
    nav = _navodi(_ask_bez_kesa("B4M2 izvor %s" % naziv, mk()))
    for tudje in ("50.000,00", "01.01.1978", "P-9999/99", "zastarelosti"):
        assert tudje not in nav, (
            "vrednost iz ZAKONA je isporučena kao činjenica iz dokumenta: %r" % tudje)


@pytest.mark.parametrize("naziv,mk,ocekivan_blocked", _BLOKIRANI,
                         ids=[b[0] for b in _BLOKIRANI])
def test_bez_dokumenta_kanal_je_PRAZAN_a_ne_izmisljen(naziv, mk, ocekivan_blocked):
    """INVARIANT A: kad dokumenta nema, kanal je prazna lista — ne izmišljena
    činjenica i ne prepisan zakon. `[]` znači „pročitano, nema ničega"."""
    rez = _ask_bez_kesa("B4M2 bez dokumenta %s" % naziv, mk(), docs=[_ZAK_PASUS])
    assert rez.get("cinjenice_iz_dokumenta") == []


@pytest.mark.parametrize("naziv,mk,ocekivan_blocked", _BLOKIRANI,
                         ids=[b[0] for b in _BLOKIRANI])
def test_tekst_odgovora_ne_dobija_novu_tvrdnju(naziv, mk, ocekivan_blocked):
    """§10 C: provenance se prenosi u ODVOJENOM polju. Tekst koji guard
    kontroliše ne sme dobiti nijedan znak više."""
    bez = _ask_bez_kesa("B4M2 tekst %s" % naziv, mk(), docs=[_ZAK_PASUS])
    sa = _ask_bez_kesa("B4M2 tekst %s" % naziv, mk())
    assert (bez.get("data") or "") == (sa.get("data") or ""), (
        "tekst odgovora se menja kad dokument postoji — provenance je procurio "
        "u polje koje guard kontroliše")


# ── API granica ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("naziv,mk,ocekivan_blocked", _BLOKIRANI,
                         ids=[b[0] for b in _BLOKIRANI])
def test_provenance_prelazi_API_granicu_i_na_blokiranom_putu(naziv, mk, ocekivan_blocked):
    """Popravka u `ask_agent` je bezvredna ako polje umre u `normalizuj_rezultat`.

    Tačno to se već jednom dogodilo: bela lista u `api.py` gutala je i
    `izvori_neuspeh` i `cinjenice_iz_dokumenta`, pa je popravka postojala u
    agentu i u `vindex.js`, a klijent je nikad nije video.
    """
    import api

    rez = _ask_bez_kesa("B4M2 API %s" % naziv, mk())
    resp = api.normalizuj_rezultat(rez, credits_remaining=5)
    assert "cinjenice_iz_dokumenta" in resp, (
        "provenance je umro na API granici — klijent ga ne vidi")
    assert "500.000,00" in " ".join(x["navod"] for x in resp["cinjenice_iz_dokumenta"])
    assert resp["cinjenice_iz_dokumenta"][0]["source_type"] == "USER_DOCUMENT"
