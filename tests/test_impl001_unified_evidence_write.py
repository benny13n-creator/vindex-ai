# -*- coding: utf-8 -*-
"""
IMPLEMENTATION TASK 001 (2026-08-27) — jedinstvena putanja upisa u Evidence Vault.

Ovi testovi dokazuju INVARIJANTE, ne implementaciju. Svaki od njih pada na
kodu od pre ovog zadatka (tada su postojala DVA pisca sa različitom semantikom
`snaga`, ručna putanja nije utemeljivala tvrdnje i tiho je gutala tuđi
`dokument_id`).

Mapiranje na traženu matricu:
  TEST A — automatska ekstrakcija pravi jedan validan red
  TEST B — ručni unos pravi jedan validan red
  TEST C — obe putanje daju IDENTIČNU semantiku `snaga`
  TEST D — izvorni dokument je sačuvan
  TEST E — lokacija je sačuvana kad postoji
  TEST F — lokacija koja ne postoji ostaje eksplicitno nepoznata (NULL)
  TEST G — cross-case upis je odbijen
  TEST H — retry/idempotentnost ne pravi neželjeno duplo stanje
  TEST I — formula rizika dobija kanonsku semantiku
  TEST J — postojeće nevezano ponašanje ne regresira
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.evidence_write import (  # noqa: E402
    GreskaDokaza,
    KATEGORIJE,
    SNAGE,
    odredi_snagu,
    upisi_dokaz,
    upisi_dokaze,
)

# Tvrdnja duga 20–100 znakova (opseg u kome DC-005 sme da da "jaka").
TVRDNJA = "Tuženi nije isplatio zaradu za decembar 2025. godine."
TEKST = "A" * 300 + TVRDNJA + "B" * 300

PREDMET = "11111111-1111-1111-1111-111111111111"
DRUGI_PREDMET = "22222222-2222-2222-2222-222222222222"
KORISNIK = "33333333-3333-3333-3333-333333333333"
DOKUMENT = "44444444-4444-4444-4444-444444444444"
TUDJ_DOKUMENT = "55555555-5555-5555-5555-555555555555"


class _Upit:
    """Verni dvojnik PostgREST lanca: .select().eq().limit().execute().

    Namerno poštuje SVE `.eq()` predikate — dvojnik koji ih ignoriše pretvorio
    bi TEST G u lažno zeleno (v. feedback: testovi koji mere jednu stranu
    ugovora)."""

    def __init__(self, tabela, redovi, dnevnik):
        self._tabela = tabela
        self._redovi = redovi
        self._dnevnik = dnevnik
        self._filteri = {}

    def select(self, *_a, **_k):
        return self

    def eq(self, kolona, vrednost):
        self._filteri[kolona] = vrednost
        return self

    def is_(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        rez = [
            r for r in self._redovi
            if all(r.get(k) == v for k, v in self._filteri.items())
        ]
        self._dnevnik.append(("select", self._tabela, dict(self._filteri), len(rez)))
        return type("R", (), {"data": rez})()


class _Insert:
    def __init__(self, tabela, redovi, dnevnik, sink, greska_na_grounding=False):
        self._tabela = tabela
        self._redovi = redovi
        self._dnevnik = dnevnik
        self._sink = sink
        self._greska = greska_na_grounding

    def insert(self, redovi):
        self._dnevnik.append(("insert", self._tabela, len(redovi), None))
        if self._greska and any("start_offset" in r for r in redovi):
            raise RuntimeError('column "start_offset" does not exist')
        upisani = []
        for i, r in enumerate(redovi):
            red = dict(r)
            red.setdefault("id", f"dokaz-{len(self._sink) + i}")
            upisani.append(red)
        self._sink.extend(upisani)
        return type("E", (), {"execute": lambda _s=None: type("R", (), {"data": upisani})()})()


class FakeSupa:
    """Minimalna, ali verna baza: `predmeti`, `predmet_dokumenti`, `predmet_dokazi`."""

    def __init__(self, *, predmeti=None, dokumenti=None, greska_na_grounding=False):
        self.predmeti = predmeti if predmeti is not None else [
            {"id": PREDMET, "user_id": KORISNIK},
            {"id": DRUGI_PREDMET, "user_id": KORISNIK},
        ]
        self.dokumenti = dokumenti if dokumenti is not None else [
            {"id": DOKUMENT, "predmet_id": PREDMET, "tekst_sadrzaj": TEKST},
            {"id": TUDJ_DOKUMENT, "predmet_id": DRUGI_PREDMET, "tekst_sadrzaj": TEKST},
        ]
        self.dokazi = []
        self.dnevnik = []
        self._greska = greska_na_grounding

    def table(self, naziv):
        if naziv == "predmeti":
            return _Upit(naziv, self.predmeti, self.dnevnik)
        if naziv == "predmet_dokumenti":
            return _Upit(naziv, self.dokumenti, self.dnevnik)
        if naziv == "predmet_dokazi":
            return _Insert(naziv, None, self.dnevnik, self.dokazi, self._greska)
        raise AssertionError(f"neocekivana tabela: {naziv}")


# ═══════════════════════════════════════════════════════════════════════════
# TEST A — automatska ekstrakcija
# ═══════════════════════════════════════════════════════════════════════════

def test_a_automatska_ekstrakcija_pravi_jedan_validan_red():
    supa = FakeSupa()
    rez = upisi_dokaze(
        supa, predmet_id=PREDMET, user_id=KORISNIK,
        stavke=[{"tvrdnja": TVRDNJA, "kategorija": "cinjenica", "dokument_id": DOKUMENT}],
        izvor_tekst=TEKST, proveri_vlasnistvo=False,
    )
    assert len(supa.dokazi) == 1
    red = supa.dokazi[0]
    assert red["predmet_id"] == PREDMET
    assert red["user_id"] == KORISNIK
    assert red["tvrdnja"] == TVRDNJA
    assert red["kategorija"] in KATEGORIJE
    assert red["snaga"] in SNAGE
    assert rez["odluke"][0]["izvor_odluke"] == "dc005"


# ═══════════════════════════════════════════════════════════════════════════
# TEST B — ručni unos
# ═══════════════════════════════════════════════════════════════════════════

def test_b_rucni_unos_pravi_jedan_validan_red():
    supa = FakeSupa()
    rez = upisi_dokaz(
        supa, predmet_id=PREDMET, user_id=KORISNIK,
        tvrdnja=TVRDNJA, kategorija="dokaz", snaga="slaba",
    )
    assert len(supa.dokazi) == 1
    red = supa.dokazi[0]
    assert red["kategorija"] == "dokaz"
    # Bez izvornog dokumenta DC-005 nema ulaz -> advokatova procena vazi.
    assert red["snaga"] == "slaba"
    assert rez["odluka"]["izvor_odluke"] == "covek"


def test_b2_rucni_unos_bez_snage_dobija_neutralnu_podrazumevanu():
    """UI danas šalje SAMO `tvrdnja` — ovaj put mora ostati nepromenjen."""
    supa = FakeSupa()
    rez = upisi_dokaz(supa, predmet_id=PREDMET, user_id=KORISNIK, tvrdnja=TVRDNJA)
    assert supa.dokazi[0]["snaga"] == "srednja"
    assert rez["odluka"]["izvor_odluke"] == "podrazumevano"


def test_b3_nevalidna_snaga_i_kategorija_se_odbijaju_a_ne_tiho_ispravljaju():
    supa = FakeSupa()
    with pytest.raises(GreskaDokaza):
        upisi_dokaz(supa, predmet_id=PREDMET, user_id=KORISNIK, tvrdnja=TVRDNJA, snaga="ogromna")
    with pytest.raises(GreskaDokaza):
        upisi_dokaz(supa, predmet_id=PREDMET, user_id=KORISNIK, tvrdnja=TVRDNJA, kategorija="izmisljena")
    assert supa.dokazi == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST C — identična semantika `snaga` na obe putanje  (SRŽ ZADATKA)
# ═══════════════════════════════════════════════════════════════════════════

def test_c_obe_putanje_daju_istu_snagu_za_isti_ulaz():
    """Ista tvrdnja + isti izvorni dokument => ista `snaga`, bez obzira na to
    koja putanja upisuje i šta je pozivalac tvrdio.

    Ovo je test koji pada na starom kodu: ručna putanja je vraćala vrednost iz
    tela zahteva ("slaba"), automatska "jaka"."""
    auto = FakeSupa()
    upisi_dokaze(
        auto, predmet_id=PREDMET, user_id=KORISNIK,
        stavke=[{"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT}],
        izvor_tekst=TEKST, proveri_vlasnistvo=False,
    )
    rucno = FakeSupa()
    rez = upisi_dokaz(
        rucno, predmet_id=PREDMET, user_id=KORISNIK, tvrdnja=TVRDNJA,
        dokument_id=DOKUMENT, izvor_tekst=TEKST,
        snaga="slaba",  # pozivalac tvrdi suprotno — DC-005 je merodavan
    )
    assert auto.dokazi[0]["snaga"] == rucno.dokazi[0]["snaga"] == "jaka"
    # Prepisivanje mora biti EKSPLICITNO, nikad tiho.
    assert rez["odluka"]["snaga_prepisana"] is True
    assert rez["odluka"]["izvor_odluke"] == "dc005"


def test_c2_postoji_tacno_jedan_donosilac_odluke_o_snazi():
    """Struktura, ne ponašanje: ako se pojavi nov pisac koji sam računa `snaga`,
    ovaj test to prijavljuje."""
    import subprocess
    koren = os.path.join(os.path.dirname(__file__), "..")
    izlaz = subprocess.run(
        [sys.executable, "-c",
         "import pathlib,re,sys;"
         "p=pathlib.Path('.');"
         "hits=[f'{f}:{i+1}' for f in list(p.glob('routers/*.py'))+list(p.glob('services/*.py'))+list(p.glob('shared/*.py'))+[pathlib.Path('api.py')]"
         " for i,l in enumerate(f.read_text(encoding='utf-8').splitlines())"
         " if 'snaga_iz_lokacije(' in l and 'def ' not in l and 'import' not in l];"
         "print('|'.join(hits))"],
        cwd=koren, capture_output=True, text=True,
    )
    pozivi = [h for h in (izlaz.stdout or "").strip().split("|") if h]
    # Jedini dozvoljeni poziv je iz `odredi_snagu` u kanonskom modulu.
    assert all(h.startswith("shared\\evidence_write.py") or h.startswith("shared/evidence_write.py")
               for h in pozivi), f"DC-005 se poziva van kanonskog modula: {pozivi}"


# ═══════════════════════════════════════════════════════════════════════════
# TEST D — izvorni dokument je sačuvan
# ═══════════════════════════════════════════════════════════════════════════

def test_d_izvorni_dokument_je_sacuvan_na_obe_putanje():
    auto = FakeSupa()
    upisi_dokaze(
        auto, predmet_id=PREDMET, user_id=KORISNIK,
        stavke=[{"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT}],
        izvor_tekst=TEKST, proveri_vlasnistvo=False,
    )
    assert auto.dokazi[0]["dokument_id"] == DOKUMENT

    rucno = FakeSupa()
    upisi_dokaz(rucno, predmet_id=PREDMET, user_id=KORISNIK, tvrdnja=TVRDNJA, dokument_id=DOKUMENT)
    assert rucno.dokazi[0]["dokument_id"] == DOKUMENT


# ═══════════════════════════════════════════════════════════════════════════
# TEST E — lokacija sačuvana kad postoji
# ═══════════════════════════════════════════════════════════════════════════

def test_e_lokacija_je_sacuvana_kad_je_tvrdnja_nadjena_u_izvoru():
    supa = FakeSupa()
    upisi_dokaze(
        supa, predmet_id=PREDMET, user_id=KORISNIK,
        stavke=[{"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT}],
        izvor_tekst=TEKST, proveri_vlasnistvo=False,
    )
    red = supa.dokazi[0]
    assert red["start_offset"] == TEKST.find(TVRDNJA)
    assert red["end_offset"] == red["start_offset"] + len(TVRDNJA)
    assert red["stranica"] == (red["start_offset"] // 2500) + 1


def test_e2_rucni_unos_sada_takodje_utemeljuje():
    """Pre ovog zadatka ručna putanja NIJE upisivala nijednu lokacijsku kolonu,
    čak i kad je `dokument_id` bio zadat."""
    supa = FakeSupa()
    upisi_dokaz(
        supa, predmet_id=PREDMET, user_id=KORISNIK, tvrdnja=TVRDNJA,
        dokument_id=DOKUMENT, izvor_tekst=TEKST,
    )
    assert supa.dokazi[0]["start_offset"] == TEKST.find(TVRDNJA)


# ═══════════════════════════════════════════════════════════════════════════
# TEST F — nepoznata lokacija ostaje NULL, nikad izmišljena
# ═══════════════════════════════════════════════════════════════════════════

def test_f_nedostajuca_lokacija_ostaje_eksplicitno_nepoznata():
    supa = FakeSupa()
    rez = upisi_dokaze(
        supa, predmet_id=PREDMET, user_id=KORISNIK,
        stavke=[{"tvrdnja": "Ova tvrdnja se nigde ne pojavljuje u izvornom tekstu.",
                 "dokument_id": DOKUMENT}],
        izvor_tekst=TEKST, proveri_vlasnistvo=False,
    )
    red = supa.dokazi[0]
    for kolona in ("stranica", "paragraf", "start_offset", "end_offset"):
        assert red[kolona] is None, f"{kolona} je izmišljena"
    assert rez["odluke"][0]["lokacija_poznata"] is False
    # Neverifikovano NIJE isto što i slabo.
    assert red["snaga"] == "srednja"


def test_f2_bez_izvornog_teksta_nema_nijedne_lokacijske_kolone():
    supa = FakeSupa()
    upisi_dokaz(supa, predmet_id=PREDMET, user_id=KORISNIK, tvrdnja=TVRDNJA)
    red = supa.dokazi[0]
    assert (red["stranica"], red["paragraf"], red["start_offset"], red["end_offset"]) == (None, None, None, None)


def test_f3_prazan_izvorni_tekst_nije_dostupan_izvor():
    """Prazan tekst ne sme da se računa kao „provereno i nije nađeno" — inače bi
    advokatova procena bila tiho pregažena bez ijedne stvarne provere."""
    snaga, izvor = odredi_snagu(TVRDNJA, {"start_offset": None}, izvor_dostupan=False, snaga_tvrdi_covek="jaka")
    assert (snaga, izvor) == ("jaka", "covek")


# ═══════════════════════════════════════════════════════════════════════════
# TEST G — cross-case upis odbijen  (INVARIANT 1)
# ═══════════════════════════════════════════════════════════════════════════

def test_g_upis_u_tudj_predmet_je_odbijen():
    supa = FakeSupa()
    with pytest.raises(GreskaDokaza) as exc:
        upisi_dokaz(supa, predmet_id=PREDMET, user_id="99999999-9999-9999-9999-999999999999", tvrdnja=TVRDNJA)
    assert exc.value.status == 404
    assert supa.dokazi == []


def test_g2_dokument_iz_drugog_predmeta_je_odbijen_a_ne_tiho_ponisten():
    """Staro ponašanje: `dokument_id` se tiho postavljao na NULL i ruta je
    vraćala `{"ok": True}` — dokaz bez izvora uz potvrdu uspeha."""
    supa = FakeSupa()
    with pytest.raises(GreskaDokaza) as exc:
        upisi_dokaz(supa, predmet_id=PREDMET, user_id=KORISNIK, tvrdnja=TVRDNJA, dokument_id=TUDJ_DOKUMENT)
    assert exc.value.status == 400
    assert supa.dokazi == []


def test_g3_svaki_upisan_red_pripada_tacno_jednom_predmetu():
    supa = FakeSupa()
    upisi_dokaze(
        supa, predmet_id=PREDMET, user_id=KORISNIK,
        stavke=[{"tvrdnja": f"{TVRDNJA} ({i})"} for i in range(3)],
    )
    assert {r["predmet_id"] for r in supa.dokazi} == {PREDMET}
    assert {r["user_id"] for r in supa.dokazi} == {KORISNIK}


# ═══════════════════════════════════════════════════════════════════════════
# TEST H — idempotentnost
# ═══════════════════════════════════════════════════════════════════════════

def test_h_primitiv_ne_uvodi_drugi_sistem_idempotentnosti():
    """INVARIANT 4 traži da se POSTOJEĆI mehanizam poštuje, a ne da se izmisli
    drugi. Idempotentnost ovog toka drži `predmet_dokumenti.klasifikovan_at`,
    koji `_consequence_evidence_classify` proverava PRE poziva. Primitiv zato
    NE sme sam da deduplicira — dva namerna poziva daju dva reda."""
    supa = FakeSupa()
    for _ in range(2):
        upisi_dokaz(supa, predmet_id=PREDMET, user_id=KORISNIK, tvrdnja=TVRDNJA)
    assert len(supa.dokazi) == 2
    assert not any(d[0] == "select" and d[1] == "predmet_dokazi" for d in supa.dnevnik), \
        "primitiv pravi sopstvenu dedup proveru — konkurentan sistem idempotentnosti"


def test_h2_postojeci_guard_i_dalje_sprecava_ponovnu_klasifikaciju():
    """Dokaz da se stari mehanizam nije pomerio: `klasifikovan_at` i dalje
    kratko spaja posledicu pre nego što ijedan upis krene."""
    # Modul se NE uvozi: `services.case_evolution` ima cirkularnu zavisnost sa
    # `services.event_bus` kada se učita van pune aplikacije. Provera se radi
    # nad izvornim tekstom, što je za strukturnu tvrdnju dovoljno i stabilnije.
    izvor = io.open(
        os.path.join(os.path.dirname(__file__), "..", "services", "case_evolution.py"),
        encoding="utf-8",
    ).read()
    telo = izvor[izvor.index("async def _consequence_evidence_classify"):]
    telo = telo[:telo.index("\nasync def ", 10)]
    assert 'if before_data.get("klasifikovan_at"):' in telo
    assert 'return "skipped_already_classified"' in telo


# ═══════════════════════════════════════════════════════════════════════════
# TEST I — formula rizika dobija kanonsku semantiku
# ═══════════════════════════════════════════════════════════════════════════

def test_i_risk_engine_dobija_iskljucivo_dozvoljene_vrednosti():
    from services.risk_engine import calculate_procesni_rizik
    from shared.constants import EXPECTED_DOCS

    supa = FakeSupa()
    upisi_dokaze(
        supa, predmet_id=PREDMET, user_id=KORISNIK,
        stavke=[
            {"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT},
            {"tvrdnja": "Tvrdnja koje nema u izvornom dokumentu nikako.", "dokument_id": DOKUMENT},
        ],
        izvor_tekst=TEKST, proveri_vlasnistvo=False,
    )
    # TASK 004A: projekcija sada nosi i `izvor_snage` -- tačno kao stvarni
    # potrošači posle TASK-a 004. Bez njega bi svaki red bio neprocenjen.
    dokazi = [{"snaga": r["snaga"], "kategorija": r["kategorija"],
               "pravni_element": r.get("pravni_element"),
               "izvor_snage": r.get("izvor_snage")}
              for r in supa.dokazi]
    assert all(d["snaga"] in SNAGE for d in dokazi)

    rizik = calculate_procesni_rizik(dokazi=dokazi, dokumenti=[], rocista=[],
                                     tip_predmeta="ostalo", expected_docs=EXPECTED_DOCS)
    # TASK 004A — tvrdnja je usklađena sa F4 ugovorom, ne oslabljena.
    # STARO: `sum(snaga_detalji) == len(dokazi)` — počivalo je na pravilu
    # „svaki upisan red se broji u dokaznu snagu", koje su gate-ovi 006/007
    # oborili. Druga tvrdnja OVDE nije pronađena u dokumentu, pa je njen
    # `izvor_snage` = `podrazumevano` (DC-005 „nije našao" NIJE procena) i
    # legitimno ne ulazi u imenilac.
    # NOVO: nijedna vrednost PROCENJENOG reda ne sme „ispasti" kao nepoznata.
    assert rizik["broj_tvrdnji"] == len(dokazi) == 2
    assert rizik["broj_procenjenih"] == 1
    assert sum(rizik["snaga_detalji"].values()) == rizik["broj_procenjenih"]
    assert rizik["snaga_detalji"]["jaka"] == 1      # pronađena tvrdnja -> dc005
    assert rizik["snaga_detalji"]["srednja"] == 0   # nepronađena -> podrazumevano


def test_i2_svaka_moguca_izlazna_vrednost_je_poznata_risk_engine_u():
    """Iscrpno: nijedna grana `odredi_snagu` ne može proizvesti vrednost koju
    `calculate_procesni_rizik` ne broji."""
    from services.risk_engine import calculate_procesni_rizik
    from shared.constants import EXPECTED_DOCS
    moguce = set()
    for izvor_dostupan in (True, False):
        for lok in ({"start_offset": 5}, {"start_offset": None}):
            for covek in (None, "jaka", "srednja", "slaba"):
                s, _ = odredi_snagu(TVRDNJA, lok, izvor_dostupan=izvor_dostupan, snaga_tvrdi_covek=covek)
                moguce.add(s)
    assert moguce <= SNAGE
    # TASK 004A: Fixture explicitly represents assessed evidence items.
    # Tvrdnja testa je o VOKABULARU (nijedna vrednost koju `odredi_snagu` može
    # da emituje ne sme biti nepoznata formuli), pa redovi moraju biti
    # procenjeni da bi uopšte stigli do brojača. `covek` je jedina provenance
    # važeća za sve tri vrednosti -- `slaba` se kroz DC-005 ne može proizvesti.
    r = calculate_procesni_rizik(
        dokazi=[{"snaga": s, "kategorija": "cinjenica", "izvor_snage": "covek"} for s in moguce],
        dokumenti=[], rocista=[], tip_predmeta="ostalo", expected_docs=EXPECTED_DOCS,
    )
    assert sum(r["snaga_detalji"].values()) == len(moguce)


# ═══════════════════════════════════════════════════════════════════════════
# TEST J — nevezano ponašanje ne regresira
# ═══════════════════════════════════════════════════════════════════════════

def test_j_soft_delete_ostaje_van_putanje_upisa():
    """INVARIANT 5: primitiv ne dira `deleted_at` ni pri jednom upisu."""
    supa = FakeSupa()
    upisi_dokaz(supa, predmet_id=PREDMET, user_id=KORISNIK, tvrdnja=TVRDNJA)
    assert "deleted_at" not in supa.dokazi[0]

    import inspect
    from routers import evidence
    izvor = inspect.getsource(evidence.delete_dokaz)
    assert '"deleted_at"' in izvor and ".eq(\"user_id\", uid)" in izvor


def test_j2_legacy_fallback_bez_grounding_kolona_i_dalje_radi():
    """Okruženje bez migracije 080 ne sme da izgubi ceo upis."""
    supa = FakeSupa(greska_na_grounding=True)
    upisi_dokaze(
        supa, predmet_id=PREDMET, user_id=KORISNIK,
        stavke=[{"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT}],
        izvor_tekst=TEKST, proveri_vlasnistvo=False,
    )
    assert len(supa.dokazi) == 1
    assert "start_offset" not in supa.dokazi[0]
    assert supa.dokazi[0]["tvrdnja"] == TVRDNJA


def test_j3_dc005_je_i_dalje_uvozljiv_pod_starim_imenom():
    """DECISION_REGISTRY.md i postojeći testovi uvoze iz routers.evidence."""
    from routers.evidence import _lociraj_tvrdnju, _snaga_iz_lokacije
    assert callable(_lociraj_tvrdnju) and callable(_snaga_iz_lokacije)
    assert _snaga_iz_lokacije(TVRDNJA, {"start_offset": 3}) == "jaka"
    assert _snaga_iz_lokacije(TVRDNJA, {"start_offset": None}) == "srednja"


def test_j4_prazne_stavke_ne_diraju_bazu():
    supa = FakeSupa()
    rez = upisi_dokaze(supa, predmet_id=PREDMET, user_id=KORISNIK, stavke=[])
    assert rez == {"redovi": [], "odluke": []}
    assert supa.dnevnik == []


def test_j5_prazna_tvrdnja_se_odbija():
    supa = FakeSupa()
    with pytest.raises(GreskaDokaza):
        upisi_dokaz(supa, predmet_id=PREDMET, user_id=KORISNIK, tvrdnja="   ")
    assert supa.dokazi == []
