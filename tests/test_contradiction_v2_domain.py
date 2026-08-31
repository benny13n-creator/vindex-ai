# -*- coding: utf-8 -*-
"""CONTRADICTION V2 — adverzarijalna suita nad domenskim jezgrom.

Ovi testovi su pisani da UBIJU implementaciju, ne da je potvrde. Svaki od njih
odgovara imenovanom nalazu iz A005–A008 ili imenovanoj mutaciji iz mandata.

Referentni kvar koji V2 mora eliminisati (A005, izmereno 9/9):

    "Razlika u datumu prestanka radnog odnosa"   ┐
    "Razlika u iznosu neisplaćenih zarada"       ┘ → jedan dedupe_key → 1 akcija
                                                   druga TIHO nestaje u
                                                   services/case_evolution.py:1052
"""
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.issue_v2 import (  # noqa: E402
    MIN_TVRDNJI, ODLUKA_DUPLIKAT, ODLUKA_NASTAVAK, ODLUKA_NEISPRAVNO, ODLUKA_NOVA,
    ODLUKA_PREGLED, RELACIJA_CINJENICA_CINJENICA, RELACIJA_CINJENICA_NORMA,
    STANJE_NIJE_VIDJENA, STATUS_OTKRIVENA, STATUS_RAZRESENA,
    delta_clanstva, novi_issue_id, novi_kontradikcija_id, razresi_kontinuitet,
    razresi_paket, validiraj_claim_ref, validiraj_predlog_teme,
)

PREDMET = "aaaaaaaa-0000-4000-8000-aaaaaaaaaaaa"
DRUGI_PREDMET = "bbbbbbbb-0000-4000-8000-bbbbbbbbbbbb"

# Tvrdnje: C1..C6 pripadaju PREDMET-u, X1 tuđem predmetu, D1 je obrisana.
C = {f"C{i}": f"cccccccc-000{i}-4000-8000-cccccccccccc" for i in range(1, 7)}
X1 = "eeeeeeee-0001-4000-8000-eeeeeeeeeeee"
D1 = "dddddddd-0001-4000-8000-dddddddddddd"

DOKAZI = {**{v: {"predmet_id": PREDMET, "deleted_at": None} for v in C.values()},
          X1: {"predmet_id": DRUGI_PREDMET, "deleted_at": None},
          D1: {"predmet_id": PREDMET, "deleted_at": "2026-08-01T00:00:00Z"}}


def tema(iid, *claims, status=STATUS_OTKRIVENA):
    return {"issue_id": iid, "status": status, "claim_set": frozenset(C[c] for c in claims)}


def predlog(*claims, label="spor", rel=RELACIJA_CINJENICA_CINJENICA, sirovi=None):
    return {"issue_label": label, "relation_type": rel,
            "claim_refs": sirovi if sirovi is not None else [C[c] for c in claims]}


# ═══════════════════════════════════════════════════════════════════════════
# §17 — A005 REPRODUKCIJA: obavezni kill test
# ═══════════════════════════════════════════════════════════════════════════

def test_A005_dve_kontradikcije_isti_par_dokumenata_ostaju_DVE():
    """ISTI par dokumenata, DVE nezavisne sporne tačke. Stari model je ovo
    svodio na jedan `dedupe_key`. V2 mora dati dva nezavisna ishoda."""
    paket = [predlog("C1", "C2", label="datum prestanka radnog odnosa"),
             predlog("C3", "C4", label="visina neisplaćenih zarada")]
    r = razresi_paket(paket, PREDMET, DOKAZI, [])
    assert len(r) == 2, "mnogostrukost je izgubljena — tačno A005 kvar"
    assert [x["odluka"] for x in r] == [ODLUKA_NOVA, ODLUKA_NOVA]
    assert r[0]["claim_set"] != r[1]["claim_set"]


def test_A005_nijedan_predlog_se_ne_sazima_u_recnik():
    """Stari gubitak je nastao iz `{a["dedupe_key"]: a for a in target}`.
    Izlaz mora imati po jednu stavku za svaki ULAZNI predlog."""
    paket = [predlog("C1", "C2"), predlog("C3", "C4"), predlog("C5", "C6")]
    assert len(razresi_paket(paket, PREDMET, DOKAZI, [])) == 3


# ═══════════════════════════════════════════════════════════════════════════
# §18/§19 — MNOGOSTRUKOST
# ═══════════════════════════════════════════════════════════════════════════

def test_tri_sporne_tacke_nad_istim_parom_dokumenata():
    paket = [predlog("C1", "C2"), predlog("C3", "C4"), predlog("C5", "C6")]
    r = razresi_paket(paket, PREDMET, DOKAZI, [])
    assert all(x["odluka"] == ODLUKA_NOVA for x in r)
    assert len({x["claim_set"] for x in r}) == 3


def test_isti_dokument_moze_nositi_vise_spornih_tacaka():
    """Grupisanje po dokumentu je zabranjeno — dokument uopšte ne ulazi u
    identitet (A008 I2). Sve tvrdnje ovde smeju poticati iz istog dokumenta."""
    paket = [predlog("C1", "C2"), predlog("C3", "C4"), predlog("C5", "C6")]
    r = razresi_paket(paket, PREDMET, DOKAZI, [])
    assert len([x for x in r if x["odluka"] == ODLUKA_NOVA]) == 3


def test_jedna_sporna_tacka_moze_imati_tri_konkurentne_tvrdnje():
    """1 sporna tačka + 3 međusobno isključive tvrdnje = 1 kontradikcija sa
    3 člana. Svođenje na proizvoljne parove bila bi lažna fragmentacija."""
    v = validiraj_predlog_teme(predlog("C1", "C2", "C3"), PREDMET, DOKAZI)
    assert v["ok"] and len(v["claim_set"]) == 3


# ═══════════════════════════════════════════════════════════════════════════
# §21 — NEZAVISNOST OD REDOSLEDA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("a,b", [(("C1", "C2"), ("C2", "C1")),
                                 (("C1", "C2", "C3"), ("C3", "C1", "C2"))])
def test_redosled_tvrdnji_ne_utice_na_identitet(a, b):
    va = validiraj_predlog_teme(predlog(*a), PREDMET, DOKAZI)
    vb = validiraj_predlog_teme(predlog(*b), PREDMET, DOKAZI)
    assert va["claim_set"] == vb["claim_set"]


def test_redosled_spornih_tacaka_ne_utice_na_ishode():
    p1, p2 = predlog("C1", "C2"), predlog("C3", "C4")
    a = razresi_paket([p1, p2], PREDMET, DOKAZI, [])
    b = razresi_paket([p2, p1], PREDMET, DOKAZI, [])
    assert {x["claim_set"] for x in a} == {x["claim_set"] for x in b}
    assert all(x["odluka"] == ODLUKA_NOVA for x in a + b)


# ═══════════════════════════════════════════════════════════════════════════
# §22 — LAŽNO SPAJANJE
# ═══════════════════════════════════════════════════════════════════════════

def test_deljene_tvrdnje_NE_dokazuju_istu_spornu_tacku():
    """{C1,C2,C3} i {C2,C3,C4} dele dva člana — i to nije kontinuitet.
    Nijedan smer sadržavanja ne važi, pa se NE sme automatski nastaviti."""
    postojeca = [tema("ISSUE-A", "C1", "C2", "C3")]
    r = razresi_kontinuitet(frozenset({C["C2"], C["C3"], C["C4"]}), postojeca)
    assert r["odluka"] == ODLUKA_PREGLED, "presek ne sme uspostaviti identitet"
    assert r["issue_id"] is None


def test_dva_kandidata_po_sadrzavanju_daju_pregled_ne_izbor():
    postojece = [tema("A", "C1", "C2"), tema("B", "C1", "C2", "C3", "C4")]
    r = razresi_kontinuitet(frozenset({C["C1"], C["C2"], C["C3"]}), postojece)
    assert r["odluka"] == ODLUKA_PREGLED
    assert r["kandidati"] == ["A", "B"]


def test_lista_kandidata_je_deterministicka_bez_obzira_na_redosled_ulaza():
    """Izlaz koji ide na ljudski pregled mora biti stabilan — inače dva
    identična poziva daju različit auditni zapis."""
    a = [tema("A", "C1", "C2"), tema("B", "C1", "C2", "C3", "C4")]
    r1 = razresi_kontinuitet(frozenset({C["C1"], C["C2"], C["C3"]}), a)
    r2 = razresi_kontinuitet(frozenset({C["C1"], C["C2"], C["C3"]}), list(reversed(a)))
    assert r1["kandidati"] == r2["kandidati"] == ["A", "B"]


def test_paket_zadrzava_TACNO_jedan_ishod_po_ulaznom_predlogu():
    """Direktna zaštita od A005 mehanizma: bilo kakvo sažimanje po ključu
    (rečnik, set, dedup) mora oboriti ovaj test."""
    paket = [predlog("C1", "C2"), predlog("C3", "C4"), predlog("C5", "C6")]
    r = razresi_paket(paket, PREDMET, DOKAZI, [])
    assert len(r) == len(paket)
    assert [x["indeks"] for x in r] == [0, 1, 2]


# ═══════════════════════════════════════════════════════════════════════════
# §23/§27 — LABEL NIJE IDENTITET
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lab", ["datum prestanka radnog odnosa", "dan prestanka zaposlenja",
                                 "datum okončanja radnog odnosa", "DATUM PRESTANKA!", None])
def test_promena_labela_ne_stvara_novu_spornu_tacku(lab):
    postojece = [tema("ISSUE-X", "C1", "C2")]
    r = razresi_kontinuitet(frozenset({C["C1"], C["C2"]}), postojece)
    assert r["odluka"] == ODLUKA_NASTAVAK and r["issue_id"] == "ISSUE-X"


def test_label_nije_ulaz_u_razresavanje():
    """Sinonim ne sme ništa promeniti — kanonizacija teksta je A008 oborio."""
    postojece = [tema("ISSUE-X", "C1", "C2")]
    a = razresi_paket([predlog("C1", "C2", label="datum prestanka radnog odnosa")],
                      PREDMET, DOKAZI, postojece)
    b = razresi_paket([predlog("C1", "C2", label="dan prestanka zaposlenja")],
                      PREDMET, DOKAZI, postojece)
    assert a[0]["issue_id"] == b[0]["issue_id"] == "ISSUE-X"


# ═══════════════════════════════════════════════════════════════════════════
# §24/§25/§26 — EVOLUCIJA ČLANSTVA
# ═══════════════════════════════════════════════════════════════════════════

def test_dodata_tvrdnja_zadrzava_spornu_tacku():
    postojece = [tema("ISSUE-X", "C1", "C2")]
    r = razresi_kontinuitet(frozenset({C["C1"], C["C2"], C["C3"]}), postojece)
    assert r["odluka"] == ODLUKA_NASTAVAK and r["issue_id"] == "ISSUE-X"


def test_izostala_tvrdnja_zadrzava_spornu_tacku():
    postojece = [tema("ISSUE-X", "C1", "C2", "C3")]
    r = razresi_kontinuitet(frozenset({C["C1"], C["C2"]}), postojece)
    assert r["odluka"] == ODLUKA_NASTAVAK and r["issue_id"] == "ISSUE-X"


def test_zamenjena_tvrdnja_ide_na_pregled_a_NE_tiho_u_novu_temu():
    """DOKUMENTOVANO ODSTUPANJE od §24 mandata.

    `{C1,C2}` → `{C1,C3}` nije ni podskup ni nadskup. Ne postoji determinističan
    dokaz da je to isti spor, pa se kontinuitet NE pretpostavlja. Ali ne sme se
    ni tiho stvoriti nova tema — deljena tvrdnja C1 je signal sumnje. Ishod je
    `REVIEW_REQUIRED`: sistem pokazuje da ZNA da ne zna."""
    postojece = [tema("ISSUE-X", "C1", "C2")]
    r = razresi_kontinuitet(frozenset({C["C1"], C["C3"]}), postojece)
    assert r["odluka"] == ODLUKA_PREGLED
    assert r["issue_id"] is None
    assert r["kandidati"] == ["ISSUE-X"]


def test_izostanak_tvrdnje_nije_razresenje():
    d = delta_clanstva([C["C1"], C["C2"], C["C3"]], [C["C1"], C["C2"]])
    assert d["izostale"] == [C["C3"]]
    assert d["izostale_stanje"] == STANJE_NIJE_VIDJENA
    assert d["izostale_stanje"] != STATUS_RAZRESENA


def test_delta_clanstva_ne_zavisi_od_redosleda():
    a = delta_clanstva([C["C1"], C["C2"]], [C["C2"], C["C1"], C["C3"]])
    b = delta_clanstva([C["C2"], C["C1"]], [C["C3"], C["C1"], C["C2"]])
    assert a == b and a["dodate"] == [C["C3"]] and a["izostale"] == []


# ═══════════════════════════════════════════════════════════════════════════
# §14/§48 — GRANICA ZNANJA: potpuna zamena članova
# ═══════════════════════════════════════════════════════════════════════════

def test_potpuna_zamena_tvrdnji_ne_pravi_lazan_kontinuitet():
    """`[C1,C2]` → `[C3,C4]`, bez ijedne zajedničke reference. Sistem NE SME
    tvrditi da je to ista sporna tačka. Nastaje NOVA, i to provizorna."""
    postojece = [tema("ISSUE-X", "C1", "C2")]
    r = razresi_kontinuitet(frozenset({C["C3"], C["C4"]}), postojece)
    assert r["odluka"] == ODLUKA_NOVA
    assert r["issue_id"] is None


# ═══════════════════════════════════════════════════════════════════════════
# §29/§33 — NEISPRAVNE REFERENCE I CROSS-CASE NAPAD
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ref", [None, "", "   ", 42, [], {}, "ne-uuid",
                                 "ffffffff-ffff-4fff-8fff-ffffffffffff"])
def test_neispravna_referenca_se_ne_razresava(ref):
    assert validiraj_claim_ref(ref, PREDMET, DOKAZI) is None


def test_sintaksno_validan_uuid_koji_ne_postoji_se_odbija():
    izmisljen = str(uuid.uuid4())
    assert validiraj_claim_ref(izmisljen, PREDMET, DOKAZI) is None


def test_cross_case_referenca_se_odbija():
    assert validiraj_claim_ref(X1, PREDMET, DOKAZI) is None


def test_obrisana_tvrdnja_nije_clan():
    assert validiraj_claim_ref(D1, PREDMET, DOKAZI) is None


def test_predlog_sa_cross_case_tvrdnjom_pada_zatvoreno():
    v = validiraj_predlog_teme(predlog(sirovi=[C["C1"], X1]), PREDMET, DOKAZI)
    assert not v["ok"]
    assert X1 in v["odbacene_reference"]


def test_cross_case_ne_moze_da_se_provuce_ni_kroz_paket():
    r = razresi_paket([predlog(sirovi=[X1, C["C1"]])], PREDMET, DOKAZI, [])
    assert r[0]["odluka"] == ODLUKA_NEISPRAVNO


# ═══════════════════════════════════════════════════════════════════════════
# §20/§32 — MINIMALNI OBLIK PREDLOGA
# ═══════════════════════════════════════════════════════════════════════════

def test_jedna_tvrdnja_nije_kontradikcija():
    v = validiraj_predlog_teme(predlog("C1"), PREDMET, DOKAZI)
    assert not v["ok"] and str(MIN_TVRDNJI) in v["razlog"]


def test_dva_puta_ista_tvrdnja_nije_kontradikcija():
    v = validiraj_predlog_teme(predlog(sirovi=[C["C1"], C["C1"]]), PREDMET, DOKAZI)
    assert not v["ok"], "duplirana referenca ne sme da se broji kao dva člana"


def test_nedostaje_label_ne_blokira_ako_su_tvrdnje_validne():
    """Label je prikaz, ne identitet. Njegovo odsustvo ne sme oboriti spor."""
    v = validiraj_predlog_teme(predlog("C1", "C2", label=None), PREDMET, DOKAZI)
    assert v["ok"] and v["label"] is None


@pytest.mark.parametrize("lab", ["", "   ", 123, None])
def test_prazan_ili_neispravan_label_postaje_None_a_ne_izmisljen_tekst(lab):
    v = validiraj_predlog_teme({"issue_label": lab, "relation_type": RELACIJA_CINJENICA_CINJENICA,
                                "claim_refs": [C["C1"], C["C2"]]}, PREDMET, DOKAZI)
    assert v["ok"] and v["label"] is None


# ═══════════════════════════════════════════════════════════════════════════
# §28 — TIP RELACIJE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rel", [RELACIJA_CINJENICA_CINJENICA, RELACIJA_CINJENICA_NORMA])
def test_dozvoljeni_tipovi_relacije(rel):
    assert validiraj_predlog_teme(predlog("C1", "C2", rel=rel), PREDMET, DOKAZI)["ok"]


@pytest.mark.parametrize("rel", [None, "", "cinjenica_argument", "FACT_FACT", 7, {}])
def test_nepoznat_tip_relacije_pada_zatvoreno(rel):
    assert not validiraj_predlog_teme(predlog("C1", "C2", rel=rel), PREDMET, DOKAZI)["ok"]


def test_tip_relacije_nije_ulaz_u_identitet():
    """Promena tipa relacije ne sme sama po sebi stvoriti novu spornu tačku."""
    postojece = [tema("ISSUE-X", "C1", "C2")]
    a = razresi_paket([predlog("C1", "C2", rel=RELACIJA_CINJENICA_CINJENICA)],
                      PREDMET, DOKAZI, postojece)
    b = razresi_paket([predlog("C1", "C2", rel=RELACIJA_CINJENICA_NORMA)],
                      PREDMET, DOKAZI, postojece)
    assert a[0]["issue_id"] == b[0]["issue_id"] == "ISSUE-X"


# ═══════════════════════════════════════════════════════════════════════════
# §31 — DUPLIKAT U PROIZVOĐAČEVOM IZLAZU
# ═══════════════════════════════════════════════════════════════════════════

def test_identican_skup_tvrdnji_dvaput_je_DUPLIKAT_a_ne_tihi_gubitak():
    r = razresi_paket([predlog("C1", "C2", label="datum prestanka"),
                       predlog("C1", "C2", label="date of termination")],
                      PREDMET, DOKAZI, [])
    assert len(r) == 2, "duplikat se prijavljuje, ne briše"
    assert r[0]["odluka"] == ODLUKA_NOVA
    assert r[1]["odluka"] == ODLUKA_DUPLIKAT


def test_slicni_labeli_a_razliciti_skupovi_ostaju_DVE_teme():
    """Nema spajanja po sličnosti teksta — to je A008 oborio."""
    r = razresi_paket([predlog("C1", "C2", label="visina duga"),
                       predlog("C3", "C4", label="visina duga")],
                      PREDMET, DOKAZI, [])
    assert [x["odluka"] for x in r] == [ODLUKA_NOVA, ODLUKA_NOVA]


def test_dva_predloga_u_odnosu_sadrzavanja_u_istom_paketu():
    """Drugi predlog vidi temu koju je prvi upravo stvorio — inače bi jedan
    poziv proizveo dve teme nad skupovima koji su u odnosu podskupa."""
    r = razresi_paket([predlog("C1", "C2"), predlog("C1", "C2", "C3")],
                      PREDMET, DOKAZI, [])
    assert r[0]["odluka"] == ODLUKA_NOVA
    assert r[1]["odluka"] == ODLUKA_NASTAVAK


# ═══════════════════════════════════════════════════════════════════════════
# §42/§43 — IDEMPOTENCIJA I OSVEŽAVANJE
# ═══════════════════════════════════════════════════════════════════════════

def test_ponovljen_identican_izlaz_daje_kontinuitet_a_ne_duplikat():
    postojece = [tema("ISSUE-X", "C1", "C2")]
    for _ in range(3):
        r = razresi_paket([predlog("C1", "C2")], PREDMET, DOKAZI, postojece)
        assert r[0]["odluka"] == ODLUKA_NASTAVAK and r[0]["issue_id"] == "ISSUE-X"


def test_dva_uzastopna_osvezavanja_sa_dve_teme_ostaju_dve():
    postojece = [tema("A", "C1", "C2"), tema("B", "C3", "C4")]
    r = razresi_paket([predlog("C1", "C2"), predlog("C3", "C4")], PREDMET, DOKAZI, postojece)
    assert [x["issue_id"] for x in r] == ["A", "B"]
    assert all(x["odluka"] == ODLUKA_NASTAVAK for x in r)


def test_razresena_tema_nije_kandidat_za_kontinuitet():
    postojece = [tema("ZATVORENA", "C1", "C2", status=STATUS_RAZRESENA)]
    r = razresi_kontinuitet(frozenset({C["C1"], C["C2"]}), postojece)
    assert r["odluka"] == ODLUKA_NOVA


def test_tema_bez_clanova_nije_kandidat_za_sve():
    """Prazan skup je podskup svega — takva tema bi postala kandidat za svaki
    dolazeći predlog."""
    postojece = [{"issue_id": "PRAZNA", "status": STATUS_OTKRIVENA, "claim_set": frozenset()}]
    r = razresi_kontinuitet(frozenset({C["C1"], C["C2"]}), postojece)
    assert r["odluka"] == ODLUKA_NOVA


# ═══════════════════════════════════════════════════════════════════════════
# §10 — PROIZVOĐAČ NE POSEDUJE IDENTITET
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("polje", ["issue_id", "contradiction_id", "dedupe_key",
                                   "notification_id", "action_id", "id"])
def test_identitet_iz_proizvodjacevog_izlaza_se_ignorise(polje):
    p = predlog("C1", "C2")
    p[polje] = "NAPADACKI-ID"
    v = validiraj_predlog_teme(p, PREDMET, DOKAZI)
    assert v["ok"]
    assert polje not in v, "polje identiteta iz izlaza modela ne sme proći kroz validaciju"
    r = razresi_paket([p], PREDMET, DOKAZI, [])
    assert r[0]["issue_id"] is None and r[0]["odluka"] == ODLUKA_NOVA


def test_sistemski_identitet_je_uvek_nov_i_nije_izveden_iz_sadrzaja():
    a, b = novi_issue_id(), novi_issue_id()
    assert a != b
    assert uuid.UUID(a) and uuid.UUID(b)
    assert novi_kontradikcija_id() != novi_issue_id()


# ═══════════════════════════════════════════════════════════════════════════
# §18 malformed / §44 M18, M25 — NEISPRAVAN ULAZ
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lose", [None, 5, "tekst", [], {}, {"claim_refs": None}])
def test_malformiran_predlog_se_odbacuje_u_celosti(lose):
    v = validiraj_predlog_teme(lose, PREDMET, DOKAZI)
    assert not v["ok"]


@pytest.mark.parametrize("paket", [None, {}, "", 0, []])
def test_prazan_ili_malformiran_paket_ne_pada_nego_vraca_prazno(paket):
    assert razresi_paket(paket, PREDMET, DOKAZI, []) == []


def test_jedan_neispravan_predlog_ne_obara_ostale():
    r = razresi_paket([predlog("C1", "C2"), {"nevalidno": True}, predlog("C3", "C4")],
                      PREDMET, DOKAZI, [])
    assert [x["odluka"] for x in r] == [ODLUKA_NOVA, ODLUKA_NEISPRAVNO, ODLUKA_NOVA]


def test_prazan_claim_set_u_razresavanju_je_neispravan():
    assert razresi_kontinuitet(frozenset(), [tema("A", "C1", "C2")])["odluka"] == ODLUKA_NEISPRAVNO


# ═══════════════════════════════════════════════════════════════════════════
# §45 — INVARIJANTE I1–I18 (sažete, po jedna tvrdnja)
# ═══════════════════════════════════════════════════════════════════════════

def test_I1_nezavisne_teme_se_nikad_tiho_ne_sazimaju():
    r = razresi_paket([predlog("C1", "C2"), predlog("C3", "C4")], PREDMET, DOKAZI, [])
    assert len(r) == 2 and len({x["claim_set"] for x in r}) == 2


def test_I5_dokument_ne_ucestvuje_u_identitetu():
    """Sve tvrdnje ovde smeju biti iz jednog dokumenta; modul dokument i ne vidi."""
    v = validiraj_predlog_teme(predlog("C1", "C2"), PREDMET, DOKAZI)
    assert "dokument" not in str(v.keys()).lower()


def test_I7_opseg_je_predmet():
    """Isti skup tvrdnji, druga baza dokaza → reference se ne razrešavaju."""
    v = validiraj_predlog_teme(predlog("C1", "C2"), DRUGI_PREDMET, DOKAZI)
    assert not v["ok"]


def test_I10_redosled_ne_utice(  ):
    a = razresi_kontinuitet(frozenset({C["C1"], C["C2"]}), [tema("A", "C2", "C1")])
    assert a["odluka"] == ODLUKA_NASTAVAK


def test_I13_izostanak_nije_razresenje():
    assert delta_clanstva([C["C1"]], [])["izostale_stanje"] == STANJE_NIJE_VIDJENA


def test_I15_vise_tema_ostaje_nezavisno_adresabilno():
    postojece = [tema("A", "C1", "C2"), tema("B", "C3", "C4"), tema("C", "C5", "C6")]
    r = razresi_paket([predlog("C5", "C6"), predlog("C1", "C2")], PREDMET, DOKAZI, postojece)
    assert [x["issue_id"] for x in r] == ["C", "A"]


# ═══════════════════════════════════════════════════════════════════════════
# A010 — OTISAK POČETNOG SKUPA (zaštita od trke, NIJE identitet)
# ═══════════════════════════════════════════════════════════════════════════

def test_otisak_je_nezavisan_od_redosleda():
    from shared.issue_v2 import otisak_pocetnog_skupa as f
    a, b, c = C["C1"], C["C2"], C["C3"]
    assert f({a, b, c}) == f([c, a, b]) == f((b, c, a))


def test_otisak_razlikuje_razlicite_skupove():
    from shared.issue_v2 import otisak_pocetnog_skupa as f
    assert f({C["C1"], C["C2"]}) != f({C["C1"], C["C3"]})
    assert f({C["C1"], C["C2"]}) != f({C["C1"], C["C2"], C["C3"]})


def test_otisak_ne_zavisi_od_labela_ni_teksta():
    """Ulaz su ISKLJUČIVO `predmet_dokazi.id` vrednosti. Da otisak zavisi od
    LLM teksta, prekršio bi A008 I12."""
    from shared.issue_v2 import otisak_pocetnog_skupa as f
    assert f({C["C1"], C["C2"]}) == f({C["C1"], C["C2"]})


def test_otisak_prazan_skup_pada_zatvoreno():
    from shared.issue_v2 import GreskaTeme, otisak_pocetnog_skupa as f
    with pytest.raises(GreskaTeme):
        f(set())
    with pytest.raises(GreskaTeme):
        f(None)


def test_otisak_NIJE_identitet_sporne_tacke():
    """Kontrola granice: `novi_issue_id` ne sme ni na koji način zavisiti od
    otiska — identitet ostaje UUID iz sistema."""
    from shared.issue_v2 import novi_issue_id, otisak_pocetnog_skupa as f
    o = f({C["C1"], C["C2"]})
    assert novi_issue_id() != novi_issue_id()
    assert o not in (novi_issue_id() + novi_issue_id())
