# -*- coding: utf-8 -*-
"""
N09 — Legal Reliability: ratio decidendi i poređenje dve odluke
(`routers/praksa.py`, /api/praksa/ratio i /api/praksa/uporedi).

Svi spoljni servisi su mokovani (Pinecone indeks = lažni korpus sa stvarnim
`$eq` filtriranjem po `decision_number`; OpenAI = zakrpljen `_pozovi_*_api`;
Supabase keš = rečnik u memoriji). Testovi su deterministički.

Invarijante koje se ovde dokazuju:
  * odluka se dohvata po TAČNOM broju (bez fuzzy poklapanja);
  * delovi dve RAZLIČITE odluke istog broja (različiti sudovi) se nikad ne
    spajaju u jedan tekst (DEFEKT N09-D2, popravljen);
  * „pretraga nije izvršena" nikad ne postaje „odluka ne postoji"
    (DEFEKT N09-D1, popravljen);
  * keširani ratio je izveden iz TEKSTA koji je poslat, ne iz tuđeg teksta
    pod istim brojem odluke (DEFEKT N09-D3, popravljen);
  * činjenice/tekst A i B se ne mešaju; A/B redosled i datumi se ne menjaju.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routers.praksa as praksa  # noqa: E402


# ─── lažni korpus ─────────────────────────────────────────────────────────

def _chunk(dn, court, date, section, text, idx, ns="sudska_praksa"):
    return {"ns": ns, "md": {
        "decision_number": dn, "court": court, "decision_date": date,
        "matter": "Građanska", "section": section, "text": text, "chunk_index": idx,
    }}


class FakeIndex:
    """Pinecone `query` sa stvarnim `$eq` filterom po decision_number.
    `down` = skup namespace-ova koji dižu grešku (nedostupni)."""

    def __init__(self, chunks, down=()):
        self.chunks = chunks
        self.down = set(down)
        self.calls = []

    def query(self, vector, top_k, namespace, include_metadata, filter):
        self.calls.append((namespace, filter))
        if namespace in self.down:
            raise ConnectionError(f"pinecone {namespace} unreachable")
        dn = filter["decision_number"]["$eq"]
        out = []
        for c in self.chunks:
            if c["ns"] == namespace and c["md"]["decision_number"] == dn:
                m = MagicMock()
                m.metadata = dict(c["md"])
                out.append(m)
        return MagicMock(matches=out[:top_k])


class DownFor:
    """Indeks koji je nedostupan samo dok se traži određena odluka."""

    def __init__(self, base, down_dns):
        self.base, self.down_dns = base, set(down_dns)

    def query(self, **kw):
        if kw["filter"]["decision_number"]["$eq"] in self.down_dns:
            raise ConnectionError("pinecone unreachable")
        return self.base.query(**kw)


REV_123 = [
    _chunk("Rev 123/2020", "Vrhovni kasacioni sud", "2020-05-01", "IZREKA", "ODBIJA SE revizija tuženog AAA.", 0),
    _chunk("Rev 123/2020", "Vrhovni kasacioni sud", "2020-05-01", "OBRAZLOŽENJE", "Zastarelost potraživanja naknade štete teče od saznanja za štetu AAA.", 1),
]
REV_1234 = [
    _chunk("Rev 1234/2020", "Vrhovni kasacioni sud", "2020-09-09", "IZREKA", "USVAJA SE revizija tužioca BBB.", 0),
    _chunk("Rev 1234/2020", "Vrhovni kasacioni sud", "2020-09-09", "OBRAZLOŽENJE", "Ugovorna kazna se ne može smanjiti po službenoj dužnosti BBB.", 1),
]
REV_999 = [
    _chunk("Rev 999/2021", "Vrhovni kasacioni sud", "2021-02-02", "IZREKA", "ODBIJA SE revizija CCC.", 0),
    _chunk("Rev 999/2021", "Vrhovni kasacioni sud", "2021-02-02", "OBRAZLOŽENJE", "Činjenice: zakup stana CCC. Stav: otkaz zakupa je pravilan CCC.", 1),
]
GZ_BG = [
    _chunk("Gž 77/2020", "Apelacioni sud u Beogradu", "2020-03-03", "IZREKA", "POTVRĐUJE SE presuda BEOGRAD.", 0),
    _chunk("Gž 77/2020", "Apelacioni sud u Beogradu", "2020-03-03", "OBRAZLOŽENJE", "Stav Beograda: ugovor je ništav BEOGRAD.", 1),
]
GZ_NI = [
    _chunk("Gž 77/2020", "Apelacioni sud u Nišu", "2020-11-11", "IZREKA", "PREINAČUJE SE presuda NIŠ.", 0),
    _chunk("Gž 77/2020", "Apelacioni sud u Nišu", "2020-11-11", "OBRAZLOŽENJE", "Stav Niša: ugovor je punovažan NIŠ.", 1),
]
CORPUS = REV_123 + REV_1234 + REV_999 + GZ_BG + GZ_NI


def _uporedi(a, b, index, analiza="## 1. PRAVNA PITANJA\nanaliza"):
    """Pokreće `_uporedi_sync` sa lažnim indeksom i hvata prompt ka modelu."""
    sent = {}

    def fake_llm(user_msg):
        sent["msg"] = user_msg
        return analiza

    with patch("app.services.retrieve._get_index", return_value=index), \
         patch.object(praksa, "_pozovi_uporedi_api", side_effect=fake_llm), \
         patch.object(praksa, "_sentry_capture"):
        out = praksa._uporedi_sync(a, b)
    return out, sent.get("msg")


def _blokovi(msg):
    a_part, rest = msg.split("\n\n---\n\n", 1)
    b_part = rest.split("\n\n---\n\n", 1)[0]
    return a_part, b_part


# ─── 1. sličan broj odluke ───────────────────────────────────────────────

def test_01_slican_broj_dohvata_tacnu_odluku():
    out, msg = _uporedi("Rev 123/2020", "Rev 999/2021", FakeIndex(CORPUS))
    assert set(out) == {"odluka_a", "odluka_b", "analiza"}
    assert out["odluka_a"]["broj"] == "Rev 123/2020"
    a, b = _blokovi(msg)
    assert "AAA" in a and "BBB" not in msg  # Rev 1234/2020 nikad ne ulazi


def test_01b_neegzaktan_broj_se_ne_dopunjava_fuzzy():
    out, msg = _uporedi("Rev 12/2020", "Rev 999/2021", FakeIndex(CORPUS))
    assert msg is None and "nije pronađena" in out["error"]


# ─── 2. isti broj, različiti sudovi ──────────────────────────────────────

def test_02_isti_broj_razliciti_sudovi_se_ne_spajaju():
    out, msg = _uporedi("Gž 77/2020", "Rev 999/2021", FakeIndex(CORPUS))
    assert msg is None, "model ne sme dobiti spojen tekst dve različite odluke"
    assert set(out) == {"error"}
    assert "više" in out["error"] and "nije pronađena" not in out["error"]


def test_02b_fetch_dize_viseznacnost_kao_valueerror_podklasu():
    with patch("app.services.retrieve._get_index", return_value=FakeIndex(CORPUS)), \
         patch.object(praksa, "_sentry_capture"):
        with pytest.raises(praksa.OdlukaViseznacna) as ei:
            praksa._fetch_decision_chunks("Gž 77/2020")
    assert isinstance(ei.value, ValueError)  # postojeći pozivaoci (radar) i dalje ne tvrde ništa
    assert "Apelacioni sud u Beogradu" in str(ei.value) and "Apelacioni sud u Nišu" in str(ei.value)


def test_02c_isti_sud_dva_namespace_nije_viseznacno():
    dup = REV_999 + [dict(c, ns="upravna_praksa") for c in REV_999]
    out, msg = _uporedi("Rev 999/2021", "Rev 123/2020", FakeIndex(dup + REV_123))
    assert "analiza" in out and msg is not None


# ─── 3. nepotpuno obrazloženje ───────────────────────────────────────────

def test_03_samo_izreka_daje_izreka_only_bez_modela():
    with patch.object(praksa, "_get_ratio_from_cache", return_value=None), \
         patch.object(praksa, "_pozovi_ratio_api") as llm, \
         patch.object(praksa, "_save_ratio_to_cache") as save:
        out = praksa._extract_ratio_sync("Rev 1/2020", "ODBIJA SE revizija.")
    assert out == praksa._IZREKA_ONLY and not llm.called and not save.called


def test_03b_model_kaze_nije_dostupno_nista_se_ne_kesira():
    with patch.object(praksa, "_get_ratio_from_cache", return_value=None), \
         patch.object(praksa, "_pozovi_ratio_api",
                      return_value="Obrazloženje nije dostupno u dostavljenom tekstu."), \
         patch.object(praksa, "_save_ratio_to_cache") as save:
        out = praksa._extract_ratio_sync("Rev 1/2020", "x" * 200)
    assert out == "" and not save.called


# ─── 4. izreka u sukobu sa obrazloženjem ─────────────────────────────────

def test_04_izreka_i_obrazlozenje_idu_odvojeno_i_doslovno():
    out, msg = _uporedi("Rev 1234/2020", "Rev 123/2020", FakeIndex(CORPUS))
    a, _ = _blokovi(msg)
    assert "USVAJA SE revizija tužioca BBB." in a
    assert "Ugovorna kazna se ne može smanjiti po službenoj dužnosti BBB." in a
    assert a.index("USVAJA SE") < a.index("Ugovorna kazna")


# ─── 5. obrnut hronološki redosled ───────────────────────────────────────

def test_05_obrnut_redosled_cuva_a_b_i_datume():
    out, msg = _uporedi("Rev 999/2021", "Rev 123/2020", FakeIndex(CORPUS))
    assert out["odluka_a"]["datum"] == "2021-02-02" and out["odluka_b"]["datum"] == "2020-05-01"
    assert msg.startswith("ODLUKA A: Rev 999/2021 (2021-02-02, Vrhovni kasacioni sud)")
    assert "ODLUKA B: Rev 123/2020 (2020-05-01, Vrhovni kasacioni sud)" in msg


def test_05b_nepoznat_sud_i_datum_ostaju_nepoznati():
    bez = [_chunk("Rev 5/2022", "", "", "OBRAZLOŽENJE", "Stav bez zaglavlja DDD " * 5, 0)]
    out, msg = _uporedi("Rev 5/2022", "Rev 123/2020", FakeIndex(bez + REV_123))
    assert "ODLUKA A: Rev 5/2022 (nepoznat datum, nepoznat sud)" in msg
    assert out["odluka_a"]["sud"] == "" and out["odluka_a"]["datum"] == ""


# ─── 6. citat nepostojeće odredbe (karakterizacija) ──────────────────────

def test_06_analiza_modela_se_vraca_bez_verifikacije_citata():
    """KARAKTERIZACIJA (rizik, ne ugovor): backend ne proverava odredbe koje
    model navede u analizi. Odgovor nema polje koje bi tvrdilo verifikaciju."""
    out, _ = _uporedi("Rev 123/2020", "Rev 999/2021", FakeIndex(CORPUS),
                      analiza="Primenjuje se član 9999 ZOO.")
    assert out["analiza"] == "Primenjuje se član 9999 ZOO."
    assert set(out) == {"odluka_a", "odluka_b", "analiza"}


# ─── 7/8. nedostupan izvor ───────────────────────────────────────────────

def test_07_jedan_izvor_nedostupan_nije_odluka_ne_postoji():
    idx = DownFor(FakeIndex(CORPUS), {"Rev 999/2021"})
    out, msg = _uporedi("Rev 123/2020", "Rev 999/2021", idx)
    assert msg is None and set(out) == {"error"}
    assert "nije pronađena" not in out["error"]
    assert "nedostupn" in out["error"].lower()


def test_08_oba_izvora_nedostupna():
    out, msg = _uporedi("Rev 123/2020", "Rev 999/2021",
                        FakeIndex(CORPUS, down=("sudska_praksa", "upravna_praksa")))
    assert msg is None and "nije pronađena" not in out["error"]
    assert "nedostupn" in out["error"].lower()


def test_08b_jedan_namespace_pao_odluka_nadjena_u_drugom_radi():
    out, msg = _uporedi("Rev 123/2020", "Rev 999/2021",
                        FakeIndex(CORPUS, down=("upravna_praksa",)))
    assert "analiza" in out and "AAA" in msg


def test_08c_stvarno_nepostojeca_odluka_i_dalje_nije_pronadjena():
    out, msg = _uporedi("Rev 123/2020", "Rev 4242/2024", FakeIndex(CORPUS))
    assert msg is None and "nije pronađena" in out["error"]


# ─── 9. izdvojeno mišljenje / navodi stranke ─────────────────────────────

def test_09_ratio_se_ne_pripisuje_iz_tudjeg_teksta_pod_istim_brojem():
    """Keš je deljen među korisnicima. Ranije: ključ = samo broj odluke →
    ratio izveden iz TUĐEG (npr. navodi stranke / izdvojeno mišljenje)
    teksta poslatog pod brojem odluke služio se svima za tu odluku."""
    store = {}
    calls = []

    def llm(t):
        calls.append(t)
        return "Sud je zauzeo stav: " + t[:20]

    with patch.object(praksa, "_get_ratio_from_cache", side_effect=lambda k: store.get(k)), \
         patch.object(praksa, "_save_ratio_to_cache", side_effect=lambda k, r: store.__setitem__(k, r)), \
         patch.object(praksa, "_pozovi_ratio_api", side_effect=llm):
        otrovan = praksa._extract_ratio_sync(
            "Rev 123/2020", "IZDVOJENO MIŠLJENJE sudije: revizija je trebalo da se usvoji " * 3)
        pravi = praksa._extract_ratio_sync(
            "Rev 123/2020", "Zastarelost potraživanja naknade štete teče od saznanja " * 3)
        ponovo = praksa._extract_ratio_sync(
            "Rev 123/2020", "Zastarelost potraživanja naknade štete teče od saznanja " * 3)
    assert "IZDVOJENO" in otrovan
    assert "IZDVOJENO" not in pravi and "Zastarelost" in pravi
    assert ponovo == pravi and len(calls) == 2  # isti tekst → keš i dalje radi


def test_09b_kljuc_kesa_vezan_za_broj_i_tekst():
    k1 = praksa._ratio_cache_key("Gž 77/2020", "tekst Beograd")
    k2 = praksa._ratio_cache_key("Gž 77/2020", "tekst Niš")
    assert k1 != k2 and k1.startswith("Gž 77/2020#")
    assert praksa._ratio_cache_key("Gž 77/2020", "tekst Beograd") == k1
    assert k1 != "Gž 77/2020"  # stari (samo-broj) unosi se više ne čitaju


# ─── 10. naizgled suprotni stavovi, različite činjenice ──────────────────

def test_10_cinjenice_a_i_b_se_ne_mesaju():
    out, msg = _uporedi("Rev 999/2021", "Rev 1234/2020", FakeIndex(CORPUS))
    a, b = _blokovi(msg)
    assert "CCC" in a and "CCC" not in b
    assert "BBB" in b and "BBB" not in a
    assert out["odluka_a"]["broj"] == "Rev 999/2021" and out["odluka_b"]["broj"] == "Rev 1234/2020"


# ─── 11. nalazi nezavisne recenzije: identitet suda ──────────────────────

def _fetch(dn, corpus):
    with patch("app.services.retrieve._get_index", return_value=FakeIndex(corpus)), \
         patch.object(praksa, "_sentry_capture"):
        return praksa._fetch_decision_chunks(dn)


def test_11_opsti_naziv_suda_nije_most_izmedju_dva_suda():
    # „Apelacioni sud" je podniz oba konkretna naziva; ranije je spajao Beograd i Niš u jedan tekst.
    opsti = [_chunk("Gž 77/2020", "Apelacioni sud", "2020-03-03", "HEADER", "Gž 77/2020 OPŠTI deo.", 0)]
    with pytest.raises(praksa.OdlukaViseznacna):
        _fetch("Gž 77/2020", opsti + GZ_BG + GZ_NI)
    out, msg = _uporedi("Gž 77/2020", "Rev 999/2021", FakeIndex(opsti + GZ_BG + GZ_NI + REV_999))
    assert msg is None and "više" in out["error"]


def test_11b_opsti_i_konkretan_naziv_se_odbijaju_fail_safe():
    opsti = [_chunk("Gž 77/2020", "Apelacioni sud", "2020-03-03", "HEADER", "Gž 77/2020 OPŠTI deo.", 0)]
    with pytest.raises(praksa.OdlukaViseznacna):
        _fetch("Gž 77/2020", opsti + GZ_BG)


def test_11c_prazan_sud_uz_imenovan_sud_se_odbija():
    # Dokumentovano ponašanje: deo bez naziva suda se ne pripisuje imenovanom sudu bez dokaza.
    bez = [_chunk("Gž 77/2020", "", "2020-03-03", "OBRAZLOŽENJE", "Deo bez suda NEPOZNATO.", 5)]
    with pytest.raises(praksa.OdlukaViseznacna) as ei:
        _fetch("Gž 77/2020", GZ_BG + bez)
    assert "sud nije naveden" in str(ei.value)


def test_11d_svi_delovi_bez_suda_se_prihvataju():
    bez = [dict(c, md=dict(c["md"], court="")) for c in REV_999]
    meta, tekst = _fetch("Rev 999/2021", bez)
    assert "CCC" in tekst


def test_11e_cirilica_i_latinica_istog_suda_se_spajaju():
    cir = [_chunk("Gž 77/2020", "Апелациони суд у Београду", "2020-03-03", "OBRAZLOŽENJE", "Ćirilični deo BEOGRAD2.", 2)]
    meta, tekst = _fetch("Gž 77/2020", GZ_BG + cir)
    assert "BEOGRAD" in tekst and "BEOGRAD2" in tekst


def test_11f_razlika_samo_u_velikim_slovima_i_razmacima_nije_viseznacnost():
    var = [_chunk("Gž 77/2020", "  APELACIONI   SUD U BEOGRADU ", "2020-03-03", "OBRAZLOŽENJE", "Varijanta BEOGRAD3.", 3)]
    meta, tekst = _fetch("Gž 77/2020", GZ_BG + var)
    assert "BEOGRAD3" in tekst
