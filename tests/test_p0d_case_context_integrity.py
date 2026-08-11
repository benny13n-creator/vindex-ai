# -*- coding: utf-8 -*-
"""
P0-D — integritet konteksta predmeta (BTM-P0-07).

ŠTA JE BIO DEFEKT

`strategija.py:666` i `:676` su glasili:

    tekst_za_revizor = "\\n\\n---\\n\\n".join(dokumenti) if dokumenti else opis_predmeta

To je ISKLJUČIVO ILI, ne spajanje. Čim bi dokumenti postojali, `opis_predmeta`
bi nestao — tiho. A koraci 4-6 (Red Team, debata, presuda, sinteza) dobijali su
SAMO `opis_predmeta`, nikad dokumente. Posledica: **nijedan korak u celom lancu
nikada nije video i opis i dokumente istovremeno.** Red Team, obe strane debate,
presuda i sinteza rezonovali su o predmetu čije dokumente nisu videli.

ZAŠTO GA NIJEDAN TEST NIJE UHVATIO

Nijedan od 13 postojećih poziva orkestratora ne prosleđuje `dokumenti` ni
`iskazi_svedoka` — grep za `iskazi_svedoka` u `tests/` daje 0 pogodaka. Grana
`if dokumenti:` bila je mrtva i u produkciji (frontend je nikad nije popunio) i
u testovima. Test koji nikad ne uđe u granu ne može da prijavi da je grana
pogrešna.

METOD OVIH TESTOVA

Svaki izvor nosi JEDINSTVEN, neponovljiv marker. Presreće se
`strategija._pozovi_strategija_api` — jedina tačka kroz koju prolaze i
`_gpt_json` i `_gpt_text` — i hvata se DOSLOVAN tekst poslat modelu. Ne
proverava se izvorni kod nego stvarni sadržaj prompta.

`tests/conftest.py:86-138` blokira DNS ka naplativim hostovima, pa promašen
mock ne može da potroši novac — pao bi glasno.
"""
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import strategija  # noqa: E402

# Markeri koje je nemoguće pobrkati ni međusobno ni sa prirodnim tekstom.
M_OPIS = "OPIS-MARKER-ALFA-7719"
M_DOKUMENT = "DOKUMENT-MARKER-BETA-4402"
M_DOKUMENT_2 = "DOKUMENT-MARKER-GAMA-8815"
M_KANONSKI = "KANONSKI-MARKER-DELTA-2036"

_OPIS = (
    f"{M_OPIS}. Stranka tvrdi da je ugovor raskinut 15.07.2026. zbog kašnjenja u isporuci. "
    "Protivna strana osporava osnovanost raskida i tvrdi da je rok bio produžen usmenim "
    "dogovorom. Vrednost spora je 4.200.000 dinara. Postupak je u prvostepenoj fazi pred "
    "Privrednim sudom, a rocište još nije zakazano."
)


def _resp(sadrzaj):
    m = MagicMock()
    m.usage = None            # bez ovoga shared.cost.record_cost dobija MagicMock tokene
    m.choices = [MagicMock(message=MagicMock(content=sadrzaj))]
    return m


_JSON_ODGOVOR = json.dumps({"confidence": "SREDNJA", "summary": "test"})


class _Hvatac:
    """Presreće svaki GPT poziv i pamti doslovno šta je poslato."""

    def __init__(self):
        self.pozivi = []          # [(system, user)]

    def __call__(self, client, **kwargs):
        poruke = kwargs.get("messages") or []
        system = next((p["content"] for p in poruke if p["role"] == "system"), "")
        user = next((p["content"] for p in poruke if p["role"] == "user"), "")
        self.pozivi.append((system, user))
        return _resp(_JSON_ODGOVOR)

    @property
    def user_poruke(self):
        return [u for _, u in self.pozivi]


def _pokreni(**kwargs):
    """Pokreće orkestrator sa presretnutim GPT pozivima."""
    h = _Hvatac()
    with patch("strategija._pozovi_strategija_api", side_effect=h):
        strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta=kwargs.pop("opis_predmeta", _OPIS),
            api_key="sk-test",
            **kwargs,
        )
    return h


# ─── 1. CENTRALNA INVARIJANTA ───────────────────────────────────────────────

def test_a_opis_i_dokument_koegzistiraju_u_SVAKOM_koraku():
    """Srž P0-D.

    Pre popravke ovaj test pada na PRVOM koraku: `strategija.py:666` je
    odbacivao opis čim dokumenti postoje. Posle popravke oba markera moraju
    biti u svakoj user poruci — jer svaki korak tvrdi da rezonuje o predmetu.
    """
    h = _pokreni(dokumenti=[f"{M_DOKUMENT}: Član 7 ugovora određuje rok od 30 dana."])
    assert h.user_poruke, "nijedan GPT poziv nije napravljen"

    for i, poruka in enumerate(h.user_poruke, start=1):
        assert M_OPIS in poruka, (
            f"GPT poziv #{i} NE sadrži opis predmeta — to je tačno defekt P0-D "
            f"(strategija.py:666 je odbacivao opis kad dokumenti postoje)"
        )
        assert M_DOKUMENT in poruka, (
            f"GPT poziv #{i} NE sadrži tekst dokumenta — koraci 4-6 su ranije "
            f"dobijali samo opis, nikad dokazni materijal"
        )


def test_b_kanonski_kontekst_stize_do_svakog_koraka():
    """Blok iz `build_case_context` mora proći ceo lanac, ne samo prvi korak."""
    h = _pokreni(case_context_blok=f"[IDENTITET PREDMETA]\n{M_KANONSKI} — Privredni sud")
    for i, poruka in enumerate(h.user_poruke, start=1):
        assert M_KANONSKI in poruka, f"GPT poziv #{i} ne vidi kanonski kontekst predmeta"


def test_c_sva_tri_izvora_istovremeno():
    """Opis + dokument + kanonski kontekst — nijedan ne potiskuje drugi."""
    h = _pokreni(
        dokumenti=[f"{M_DOKUMENT}: Član 7 ugovora."],
        case_context_blok=f"[IZVEDENO IZ BAZE — izračunao sistem, nije iskaz stranke]\n- {M_KANONSKI}",
    )
    for i, poruka in enumerate(h.user_poruke, start=1):
        nedostaje = [m for m in (M_OPIS, M_DOKUMENT, M_KANONSKI) if m not in poruka]
        assert not nedostaje, f"GPT poziv #{i} ne sadrži: {nedostaje}"


def test_d_poreklo_je_razlucivo():
    """Kriterijum prihvatanja: dovučeno znanje mora ostati razlučivo od dokaza.

    Model ne sme da čita sopstveni izračun sistema kao tvrdnju stranke. Zato
    svaki izvor nosi svoju oznaku, a ne slepljen tekst.
    """
    h = _pokreni(
        dokumenti=[f"{M_DOKUMENT}: Član 7."],
        case_context_blok=f"[IZVEDENO IZ BAZE — izračunao sistem, nije iskaz stranke]\n- {M_KANONSKI}",
    )
    prva = h.user_poruke[0]
    assert strategija._OSNOVA_OPIS in prva, "opis nije označen kao iskaz advokata"
    assert strategija._OSNOVA_DOKAZ in prva, "dokument nije označen kao dokaz"
    assert "IZVEDENO IZ BAZE" in prva, "izvedeni podaci nisu označeni kao izvedeni"
    # Oznake moraju stajati PRE svog sadržaja, inače ne označavaju ništa.
    assert prva.index(strategija._OSNOVA_OPIS) < prva.index(M_OPIS)
    assert prva.index(strategija._OSNOVA_DOKAZ) < prva.index(M_DOKUMENT)


# ─── 2. NEGATIVNI SLUČAJEVI ─────────────────────────────────────────────────

def test_e_samo_opis_bez_dokumenata():
    """Zatečeno ponašanje mora ostati netaknuto — to je 100% današnjeg saobraćaja."""
    h = _pokreni()
    assert all(M_OPIS in p for p in h.user_poruke)
    prva = h.user_poruke[0]
    assert strategija._OSNOVA_DOKAZ not in prva, (
        "prazna sekcija dokaza ne sme se pojaviti — model bi dobio naslov bez "
        "sadržaja i popunio ga pretpostavkom"
    )


def test_f_samo_dokumenti_bez_opisa():
    """Prazan opis ne sme da proizvede izmišljen opis ni da obori analizu."""
    h = _Hvatac()
    with patch("strategija._pozovi_strategija_api", side_effect=h):
        strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="", api_key="sk-test",
            dokumenti=[f"{M_DOKUMENT}: Član 7 ugovora."],
        )
    assert h.user_poruke
    prva = h.user_poruke[0]
    assert M_DOKUMENT in prva
    assert strategija._OSNOVA_OPIS not in prva, "prazan opis je dobio oznaku bez sadržaja"


def test_g_vise_dokumenata_zadrzava_identitet():
    """Dokumenti se ne smeju stopiti u jedan neraspoznatljiv blok."""
    h = _pokreni(dokumenti=[
        f"{M_DOKUMENT}: Prvi dokument, član 7.",
        f"{M_DOKUMENT_2}: Drugi dokument, aneks.",
    ])
    prva = h.user_poruke[0]
    assert M_DOKUMENT in prva and M_DOKUMENT_2 in prva
    assert "---" in prva, "dokumenti nemaju razdvajač"


@pytest.mark.parametrize("prazno", [[], None, [""], ["   "]])
def test_h_prazan_skup_dokumenata_ne_kvari_kontekst(prazno):
    """Prazna lista, None i lista praznih stringova moraju se ponašati isto."""
    h = _pokreni(dokumenti=prazno)
    prva = h.user_poruke[0]
    assert M_OPIS in prva
    assert strategija._OSNOVA_DOKAZ not in prva


def test_i_prazan_kanonski_kontekst_ne_dodaje_nista():
    for vrednost in ("", None, "   "):
        h = _pokreni(case_context_blok=vrednost)
        assert M_OPIS in h.user_poruke[0]


# ─── 3. SIGNATURA — zaštita od tihog loma u produkciji ──────────────────────

def test_j_case_context_blok_je_KEYWORD_ONLY():
    """Najopasniji način da se ovaj sprint pokvari.

    `routers/strategija.py:394-400` zove orkestrator POZICIJSKI, kroz
    `asyncio.to_thread`, u background job-u obavijenom širokim `except
    Exception`. Da je `case_context_blok` dodat kao pozicioni parametar, stari
    poziv bi mu vezao pogrešnu vrednost i otkazao bi NEVIDLJIVO u produkciji —
    a svih 13 postojećih testova koristi keyword pozive i to ne bi uhvatilo.

    `*` čini takvo vezivanje sintaksno nemogućim. Ovaj test to zaključava.
    """
    import inspect
    sig = inspect.signature(strategija.orkestrator_kompletna_analiza_sync)
    p = sig.parameters

    pozicijski = [i for i, x in p.items()
                  if x.kind in (x.POSITIONAL_ONLY, x.POSITIONAL_OR_KEYWORD)]
    assert pozicijski == ["opis_predmeta", "api_key", "dokumenti", "iskazi_svedoka"], (
        f"pozicijski redosled je promenjen: {pozicijski} — routers/strategija.py:394 "
        f"vezuje prva 4 argumenta po poziciji"
    )
    assert p["case_context_blok"].kind == p["case_context_blok"].KEYWORD_ONLY
    assert p["case_context_blok"].default is None, "novi parametar mora biti opcion"


def test_k_stari_pozicijski_poziv_i_dalje_radi():
    """Kompatibilnost unazad, dokazana izvršavanjem a ne čitanjem potpisa."""
    h = _Hvatac()
    with patch("strategija._pozovi_strategija_api", side_effect=h):
        rez = strategija.orkestrator_kompletna_analiza_sync(
            _OPIS, "sk-test", None, None,      # tačno kao routers/strategija.py:394-400
        )
    assert "koraci" in rez and "sinteza" in rez
    assert M_OPIS in h.user_poruke[0]


def test_l_pozicijsko_prosledjivanje_petog_argumenta_je_NEMOGUCE():
    """Diskriminišući dokaz da `*` stvarno štiti, a ne samo dokumentuje nameru."""
    with pytest.raises(TypeError):
        strategija.orkestrator_kompletna_analiza_sync(
            _OPIS, "sk-test", None, None, "peti-pozicijski",
        )


# ─── 4. MARKERI SE POKLAPAJU SA KANONSKIM MODULOM ──────────────────────────

def test_m_markeri_se_poklapaju_sa_kanonskim():
    """`strategija.py` ponavlja oznake kao literale umesto da ih uvozi.

    Uvoz bi vezao modul koji se izvršava u radničkoj niti za `shared.case_context`
    i njegov lanac zavisnosti (Supabase, risk engine, gap engine). Cena tog
    izbora je da se dva literala mogu razići — ovaj test je to plaća.
    """
    from shared.case_context import CTX_MARKER_DOKAZ
    assert strategija._OSNOVA_DOKAZ == CTX_MARKER_DOKAZ, (
        "oznaka dokaza se raziši̶la između strategija.py i shared/case_context.py"
    )


# ─── 5. NEGATIVNA KONTROLA ──────────────────────────────────────────────────

def test_ng_stari_defekt_bi_oborio_ove_testove():
    """Dokaz da testovi mere baš defekt, a ne nešto uz njega.

    Reprodukuje se TAČNO stara logika (`dokumenti if dokumenti else opis`) i
    proverava da bi ona pala na `test_a`. Bez ovoga bi `test_a` mogao prolaziti
    iz nekog nevezanog razloga.
    """
    stara_osnova = "\n\n---\n\n".join([f"{M_DOKUMENT}: Član 7."])
    assert M_DOKUMENT in stara_osnova
    assert M_OPIS not in stara_osnova, "stara logika je gubila opis — to je bio defekt"

    nova_osnova = strategija._sastavi_dokaznu_osnovu(
        _OPIS, [f"{M_DOKUMENT}: Član 7."], None,
    )
    assert M_OPIS in nova_osnova and M_DOKUMENT in nova_osnova


def test_ng_hvatac_stvarno_hvata():
    """Ako bi mock promašio, testovi bi prolazili prazno."""
    h = _pokreni()
    assert len(h.pozivi) == 7, (
        f"očekivano 7 GPT poziva bez iskaza svedoka, viđeno {len(h.pozivi)} — "
        f"ako je broj koraka namerno promenjen, ispravi i ovaj broj svesno"
    )
    assert all(s for s, _ in h.pozivi), "neki poziv nema system prompt"


def test_ng_witness_grana_dodaje_osmi_poziv():
    h = _pokreni(iskazi_svedoka=["Svedok tvrdi da je isporuka kasnila 12 dana."])
    assert len(h.pozivi) == 8, f"sa iskazima očekivano 8 poziva, viđeno {len(h.pozivi)}"


# ─── 6. NEDEFINISANA IMENA ──────────────────────────────────────────────────

@pytest.mark.parametrize("modul", [
    "strategija.py",
    "routers/strategija.py",
    "shared/case_context.py",
])
def test_n_nema_nedefinisanih_imena(modul):
    """Hvata razred greške koji je ovaj sprint zamalo isporučio.

    Prilikom uvođenja `_osnova`, zamena `replace_all` nad izrazom
    `f"Predmet:\\n\\n{opis_predmeta}\\n\\n"` pogodila je i `ai_judge_v2_sync`
    (`strategija.py:431,444`) — potpuno DRUGU funkciju, koja `_osnova` nema.
    To bi bio `NameError` na živoj putanji AI Sudije.

    `python -m py_compile` to NE vidi: nedefinisano ime je runtime greška, ne
    sintaksna. Uhvaćeno je ručnim čitanjem diffa; ovaj test čini da sledeći put
    ne zavisi od toga da li je neko pažljivo gledao.

    Proverava se ISKLJUČIVO F821 (undefined name). Neiskorišćeni importi i
    slična higijena namerno se ne diraju — to bi bilo šire čišćenje van P0-D.
    """
    pyflakes = pytest.importorskip("pyflakes.api")
    reporter = pytest.importorskip("pyflakes.reporter")
    import io

    putanja = os.path.join(os.path.dirname(__file__), "..", *modul.split("/"))
    out, err = io.StringIO(), io.StringIO()
    pyflakes.checkPath(putanja, reporter.Reporter(out, err))

    nedefinisana = [r for r in out.getvalue().splitlines() if "undefined name" in r]
    assert not nedefinisana, "nedefinisana imena:\n  " + "\n  ".join(nedefinisana)
