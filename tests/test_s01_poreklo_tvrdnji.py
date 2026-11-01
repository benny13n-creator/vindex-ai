# -*- coding: utf-8 -*-
"""S01 / B5 — poreklo tvrdnje: navod koji model izvuče sme dobiti „Iz dokumenta“ (SOURCE_FACT) samo ako dokument
zaista to kaže.

Reprodukovan kvar (a45b34ba): `lociraj_tvrdnju` je prihvatala pogodak USRED rečenice. Tvrdnja „isplatio zaradu za mart
2026. godine.“ iz rečenice „Tuzeni nije isplatio zaradu …“ dobijala je `egzaktan` → SOURCE_FACT → u V2 „Iz dokumenta“,
„pronađeno u dokumentu“ — obrnut smisao izvora. Isto za izostavljeno pripisivanje („Tuzilac tvrdi da je …“).
Pravilo: pogodak mora početi na početku rečenice (. ! ? ispred razmaka, ili prelom reda koji ne nastavlja rečenicu).
Kraj rečenice se ne zahteva (izostavljen nastavak ograđuje, ne obrće) — ograničenje je zapisano u ledgeru S01.

Matrica A–K (ugovor sprinta S01): ovde A–F, K i E kroz stvaran prijem; G–J pokrivaju postojeći testovi
(`test_impl001_unified_evidence_write`, `test_vcr002_t03_visedokumentni_predmet`, `test_mir001_t03_kontinuitet`,
`test_vcr002_rc_fix1_migracija137_pg`, `test_ns006_t4_evidence_graph`).
"""
import pytest

from shared.evidence_write import NACIN_EGZAKTAN, NACIN_NIJE, NACIN_NORMALIZOVAN, lociraj_tvrdnju
from shared.genome_contract import AI_ANALYSIS, SOURCE_FACT, poreklo_tvrdnje

IZVOR = ("OSNOVNI SUD U NISU\n"
         "Tuzeni nije isplatio zaradu za mart 2026. godine.\n"
         "Tuzilac tvrdi da je zakup placen 01.02.2026. godine.\n"
         "Iznos duga je 125.000,00 dinara.\n"
         "Zarada je isplacena samo delimicno.\n"
         "Rok za uplatu sudske takse istice 04.12.2026. godine.")


def _klasa(tekst, tvrdnja):
    lok = lociraj_tvrdnju(tekst, tvrdnja)
    return lok["nacin"], poreklo_tvrdnje({"dokument_id": "d1", "nacin_pronalaska": lok["nacin"],
                                          "izvor_tvrdnje": "ai_klasifikacija"})[0]


@pytest.mark.parametrize("slucaj, tvrdnja, nacin, poreklo", [
    ("A doslovna rečenica", "Tuzeni nije isplatio zaradu za mart 2026. godine.", NACIN_EGZAKTAN, SOURCE_FACT),
    ("B veličina slova i razmaci", "tuzeni  nije isplatio   zaradu za mart 2026. godine.", NACIN_NORMALIZOVAN, SOURCE_FACT),
    ("C parafraza", "Poslodavac nije platio martovsku platu.", NACIN_NIJE, AI_ANALYSIS),
    ("D obrnuta negacija", "Tuzeni je isplatio zaradu za mart 2026. godine.", NACIN_NIJE, AI_ANALYSIS),
    ("D deo rečenice posle negacije", "isplatio zaradu za mart 2026. godine.", NACIN_NIJE, AI_ANALYSIS),
    ("D kratak deo bez negacije", "isplatio zaradu", NACIN_NIJE, AI_ANALYSIS),
    ("F tačan iznos", "Iznos duga je 125.000,00 dinara.", NACIN_EGZAKTAN, SOURCE_FACT),
    ("F pogrešno pročitan iznos", "Iznos duga je 152.000,00 dinara.", NACIN_NIJE, AI_ANALYSIS),
    ("F pogrešno pročitan datum", "Rok za uplatu sudske takse istice 04.12.2025. godine.", NACIN_NIJE, AI_ANALYSIS),
    ("K navod stranke ceo", "Tuzilac tvrdi da je zakup placen 01.02.2026. godine.", NACIN_EGZAKTAN, SOURCE_FACT),
    ("K navod bez pripisivanja", "zakup placen 01.02.2026. godine.", NACIN_NIJE, AI_ANALYSIS),
    ("rečenica bez završne tačke", "Iznos duga je 125.000,00 dinara", NACIN_EGZAKTAN, SOURCE_FACT),
    ("izričito delimičan citat od početka", "Tuzeni nije isplatio zaradu…", NACIN_EGZAKTAN, SOURCE_FACT),
    ("delimičan citat posle negacije", "isplatio zaradu…", NACIN_NIJE, AI_ANALYSIS),
    ("više rečenica od početka do kraja", "Iznos duga je 125.000,00 dinara.\nZarada je isplacena samo delimicno.",
     NACIN_EGZAKTAN, SOURCE_FACT),
])
def test_poreklo_tvrdnje_prati_smisao_izvora(slucaj, tvrdnja, nacin, poreklo):
    assert _klasa(IZVOR, tvrdnja) == (nacin, poreklo), slucaj


def test_normalizovan_pogodak_preko_preloma_reda_i_dalje_vazi_na_granici_recenice():
    # OCR prelama rečenicu u dva reda; tvrdnja je cela rečenica → normalizovan pogodak ostaje SOURCE_FACT.
    tekst = "RESENJE\nTuzeni nije isplatio\nzaradu za mart 2026. godine.\nKraj."
    assert _klasa(tekst, "Tuzeni nije isplatio zaradu za mart 2026. godine.") == (NACIN_NORMALIZOVAN, SOURCE_FACT)
    # ...a isti deo posle negacije, koji počinje usred reda, i dalje nije navod dokumenta.
    assert _klasa(tekst, "isplatio zaradu za mart 2026. godine.") == (NACIN_NIJE, AI_ANALYSIS)


def test_normalizovan_pogodak_usred_recenice_ne_postaje_navod_dokumenta():
    tekst = "Tuzilac   tvrdi da je\nzakup placen 01.02.2026. godine."
    assert _klasa(tekst, "Zakup placen 01.02.2026. godine.") == (NACIN_NIJE, AI_ANALYSIS)


def test_rec_prelomljena_u_dva_reda_ne_otvara_granicu():
    # Prelom reda usred rečenice (OCR) nije granica: negacija u prethodnom redu ostaje deo rečenice.
    tekst = "RESENJE\nTuzeni nije\nisplatio zaradu za mart 2026. godine.\nKraj."
    assert _klasa(tekst, "isplatio zaradu za mart 2026. godine.") == (NACIN_NIJE, AI_ANALYSIS)
    # Isto i kad red završava zarezom (nabrajanje se nastavlja u sledećem redu).
    assert _klasa("Tuzilac navodi,\nda je zakup placen.", "da je zakup placen.") == (NACIN_NIJE, AI_ANALYSIS)
    assert _klasa(tekst, "Tuzeni nije isplatio zaradu za mart 2026. godine.") == (NACIN_NORMALIZOVAN, SOURCE_FACT)


def test_red_zaglavlja_bez_tacke_pa_nova_recenica_jeste_granica():
    # PDF/OCR: red-zaglavlje završava malim slovom bez tačke, sledeći red je nova rečenica velikim slovom.
    tekst = "Tuzeni: Primer Gradnja DOO iz Cacka\nResenje o otkazu je uruceno tuziocu 17.03.2025. godine."
    assert _klasa(tekst, "Resenje o otkazu je uruceno tuziocu 17.03.2025. godine.") == (NACIN_EGZAKTAN, SOURCE_FACT)


# ── Nalazi nezavisnog pregleda (S01) ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("tekst, tvrdnja", [
    # FP1: prelom reda ispred velikog slova nije granica ako prethodni red nije zatvoren (negacija ostaje u rečenici)
    ("Nije tacno da\nTuzeni duguje tuziocu 125.000,00 dinara.", "Tuzeni duguje tuziocu 125.000,00 dinara."),
    ("Nije tacno da\r\nTuzeni duguje tuziocu 125.000,00 dinara.", "Tuzeni duguje tuziocu 125.000,00 dinara."),
    ("Није тачно да\nТужени дугује тужиоцу 125.000,00 динара.", "Тужени дугује тужиоцу 125.000,00 динара."),
    ("Nije tacno da   je\n  Tuzeni  duguje tuziocu 125.000,00 dinara.", "Tuzeni duguje tuziocu 125.000,00 dinara."),
    ("Tuzeni nije dana 01.02.2026\nisplatio zaradu.", "isplatio zaradu."),
    ("Tuzilac tvrdi da je\n„zakup placen u celosti“.", "zakup placen u celosti"),
    # FP2: pogodak ne sme da preseče broj ili reč
    ("Ugovorna kazna iznosi 5000 dinara po danu.", "Ugovorna kazna iznosi 500"),
    ("Iznos duga je 125.000,00 dinara.", "Iznos duga je 125"),
    ("Rok istice 04.12.2026. godine.", "Rok istice 04.12.202"),
    # FP3: tačka u datumu, skraćenici ili inicijalu nije kraj rečenice
    ("Nije tacno da je 01.02.2026. tuzeni isplatio zaradu.", "tuzeni isplatio zaradu."),
    ("Nije tacno da je dr. Petar Petrovic pregledao tuzioca.", "Petar Petrovic pregledao tuzioca."),
    # Drugi krug pregleda: oznaka govornika kao uvod u navod, datum pred velikim slovom, hiljade sa razmakom,
    # preširoka pravila „zatvorenog reda“.
    ("Punomocnik tuzenog: Nije tacno da je\nTuzeni primio robu dana 01.02.2026. godine.",
     "Tuzeni primio robu dana 01.02.2026. godine."),
    ("Svedok Petrovic: Ne secam se da je\r\nTuzeni isplatio zaradu.", "Tuzeni isplatio zaradu."),
    ("Сведок Петровић: Не сећам се да је\nТужени исплатио зараду.", "Тужени исплатио зараду."),
    ("Tuzilac tvrdi da je dana 01.02.2026. Tuzeni preuzeo robu.", "Tuzeni preuzeo robu."),
    ("Nije tacno da je 01.02.2026. Tuzeni isplatio zaradu.", "Tuzeni isplatio zaradu."),
    ("Ugovorna kazna iznosi 500 000 dinara.", "Ugovorna kazna iznosi 500"),
    ("Ugovorna kazna iznosi 500\u00a0000 dinara.", "Ugovorna kazna iznosi 500"),
    ("Nije tacno da je 15.03.2026\nTuzeni isplatio zaradu.", "Tuzeni isplatio zaradu."),
    ("Nije tacno da JP EPS i NIS AD\nTuzenom duguju 125.000,00 dinara.", "Tuzenom duguju 125.000,00 dinara."),
    ("Tuzilac tvrdi da je iznos od\n125.000,00\nTuzeni platio.", "Tuzeni platio."),
    ("Nije\nTuzeni platio zaradu.", "Tuzeni platio zaradu."),
    # Treći krug: red koji se samo ZAVRŠAVA referencom nije broj predmeta; red velikim slovima koji se završava
    # veznikom/glagolom nije zaglavlje.
    ("Nije tacno da je ugovorom br. 15/2026\nTuzeni preuzeo obavezu placanja.", "Tuzeni preuzeo obavezu placanja."),
    ("Tuzilac tvrdi da je po fakturi 118/26\nTuzeni platio 125.000,00 dinara.", "Tuzeni platio 125.000,00 dinara."),
    ("Nije sporno da u predmetu P 5101/2026\nTuzilac nije dostavio dokaz.", "Tuzilac nije dostavio dokaz."),
    ("Није тачно да је уговором бр. 15/2026\nТужени преузео обавезу.", "Тужени преузео обавезу."),
    ("NIJE TACNO DA JE\nTuzeni isplatio zaradu.", "Tuzeni isplatio zaradu."),
    ("Po ugovoru br. 15/2026\nTuzeni duguje 500 dinara.", "Tuzeni duguje 500 dinara."),
    ("TUZENI\nisplatio zaradu za mart 2026. godine.", "isplatio zaradu za mart 2026. godine."),
    # Red velikim slovima (inače zaglavlje) pa nastavak malim slovom — ista rečenica.
    ("TUZENI NIJE\nisplatio zaradu za mart 2026. godine.", "isplatio zaradu za mart 2026. godine."),
    ("Nije tacno da je Primer DOO (Tuzeni)\nTuziocu isplatio zaradu.", "Tuziocu isplatio zaradu."),
    # Red koji uvodi navod („…navodi:“) nije zatvoren: navod u sledećem redu nosi pripisivanje.
    ("Tuzilac navodi:\nZakup je placen u celosti.", "Zakup je placen u celosti."),
    # FP5: tri tačke usred rečenice
    ("Tuzeni nije... isplatio zaradu.", "Isplatio zaradu."),
])
def test_deo_recenice_ostaje_ai_analiza(tekst, tvrdnja):
    assert _klasa(tekst, tvrdnja) == (NACIN_NIJE, AI_ANALYSIS)


@pytest.mark.parametrize("tekst, tvrdnja", [
    ("IZREKA\n1) Tuzeni je duzan da isplati 125.000,00 dinara.", "Tuzeni je duzan da isplati 125.000,00 dinara."),
    ("Ugovor\n(1) Zakupnina iznosi 50.000 dinara mesecno.", "Zakupnina iznosi 50.000 dinara mesecno."),
    ("ИЗРЕКА\n1) Тужени је дужан да исплати 125.000,00 динара.", "Тужени је дужан да исплати 125.000,00 динара."),
    ("PRESUDA\nI Obavezuje se tuzeni da isplati dug.", "Obavezuje se tuzeni da isplati dug."),
    ("TUZBA radi naknade stete (SINTETICKI PREDMET)\nTuzilac: Alfa Fiktiv DOO, Primergrad", "Tuzilac: Alfa Fiktiv DOO, Primergrad"),
    # Zaglavlja iz stvarnih sintetičkih produkcionih predmeta (P7714, 11eaeffc) — tvrdnje modela posle njih ostaju navod.
    ("SAMO ZA TESTIRANJE OCR-a I TOKA PREDMETA\nNije izdao nijedan sud ili drzavni organ.", "Nije izdao nijedan sud ili drzavni organ."),
    ("OSNOVNI SUD U BEOGRADU\nPosl. br. Р 7714/2026\nOdluka je doneta 20.10.2026. godine.", "Odluka je doneta 20.10.2026. godine."),
    ("Iznos duga je 125.000,00 dinara.", "Iznos duga je 125.000,00 dinara"),
    ("Datum tuzbe: 10.02.2026. godine.", "Datum tuzbe: 10.02.2026."),
    ("Clan 1. Ugovorna kazna iznosi 500.000 RSD.", "Ugovorna kazna iznosi 500.000 RSD."),
    ("Zakupac se obavezuje:\n1) Zakupnina iznosi 50.000 dinara.", "Zakupnina iznosi 50.000 dinara."),
    ("Zakupac se obavezuje:\na) Zakupnina iznosi 50.000 dinara.", "Zakupnina iznosi 50.000 dinara."),
    ("Tuzeni: Primer Gradnja DOO iz Cacka\nResenje je uruceno 17.03.2025. godine.", "Resenje je uruceno 17.03.2025. godine."),
    ("Rok istice 04.12.2026. Tuzeni je duzan da plati.", "Rok istice 04.12.2026."),
    ("Iznos je 125 000 dinara.", "Iznos je 125 000 dinara."),
    ("PRESUDA\nObrazlozenje\nSud je utvrdio da je ugovor zakljucen.", "Sud je utvrdio da je ugovor zakljucen."),
    ("Broj: Gž 12/2025\nSud je odbio zalbu.", "Sud je odbio zalbu."),
    ("P 4711/2026\nTuzilac je podneo tuzbu.", "Tuzilac je podneo tuzbu."),
])
def test_cela_recenica_posle_nabrajanja_zaglavlja_ili_oznake_ostaje_navod(tekst, tvrdnja):
    assert _klasa(tekst, tvrdnja)[1] == SOURCE_FACT


def test_naslov_u_posebnom_redu_ne_smeta():
    tekst = "OPIS TESTNOG SLUCAJA\nOvaj dokument je vestacki generisan."
    assert _klasa(tekst, "Ovaj dokument je vestacki generisan.") == (NACIN_EGZAKTAN, SOURCE_FACT)


def test_nabrajanje_i_navodnici_ispred_pocetka_ne_smetaju():
    tekst = "Utvrdjeno je sledece.\n1. „Iznos duga je 125.000,00 dinara.“\n- Rok je 04.12.2026. godine."
    assert _klasa(tekst, "Iznos duga je 125.000,00 dinara.")[1] == SOURCE_FACT
    assert _klasa(tekst, "Rok je 04.12.2026. godine.")[1] == SOURCE_FACT


# ── E + D kroz stvaran prijem: dva različita `scan.pdf`, model vraća delove i tuđe rečenice ─────────────────────
from tests.test_osb002_solo_tok import A, _do_kraja_dogadjaja, _pdf, _prijem_dokumenta, solo  # noqa: E402,F401

SCAN_1 = ["RESENJE", "Broj predmeta: P 5101/2026",
          "Tuzeni nije isplatio zaradu za mart 2026. godine.",
          "Rok za izjasnjenje istice 04.12.2026. godine."]
SCAN_2 = ["ZAPISNIK", "Broj predmeta: P 5101/2026",
          "Tuzilac tvrdi da je zakup placen 01.02.2026. godine.",
          "Rok za uplatu takse istice 04.12.2026. godine."]
# Model (zamena) za SVAKI dokument vraća: celu rečenicu, deo posle negacije/pripisivanja i rečenicu DRUGOG dokumenta.
MODEL = {
    "P 5101/2026\nTuzeni": ["Tuzeni nije isplatio zaradu za mart 2026. godine.", "isplatio zaradu za mart 2026. godine.",
                           "Rok za uplatu takse istice 04.12.2026. godine."],
    "P 5101/2026\nTuzilac": ["Tuzilac tvrdi da je zakup placen 01.02.2026. godine.", "zakup placen 01.02.2026. godine.",
                            "Rok za izjasnjenje istice 04.12.2026. godine."],
}


def _model_tvrdnji(naziv, tekst):
    kljuc = next(k for k in MODEL if k.split("\n")[1] in tekst)
    return {"tip_dokaza": "dopis", "pravni_elementi": [], "ai_tags": {}, "kljucne_cinjenice": MODEL[kljuc]}


def test_dva_scan_pdf_tvrdnje_ostaju_svom_dokumentu_a_delovi_recenica_nisu_navod(solo, monkeypatch):
    k, b = solo
    import routers.evidence as ev
    monkeypatch.setattr(ev, "_klasifikuj_dokument", _model_tvrdnji)
    p = k.post("/api/predmeti", json={"naziv": "S01 poreklo", "tip": "Radni spor"}, headers=A)
    assert p.status_code == 200, p.text
    pid = p.json()["predmet"]["id"]
    for redovi in (SCAN_1, SCAN_2):
        _, fin = _prijem_dokumenta(k, b, pid, sadrzaj=_pdf(redovi), ime="scan.pdf")
        assert fin["dokumenata_povezano"] == 1, fin
        _do_kraja_dogadjaja(b, najvise=10)
    dok = {d["id"]: d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid}
    assert len(dok) == 2 and {d["naziv_fajla"] for d in dok.values()} == {"scan.pdf"}
    d1 = next(i for i, d in dok.items() if "Tuzeni nije" in (d.get("tekst_sadrzaj") or ""))
    d2 = next(i for i in dok if i != d1)

    g = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A)
    assert g.status_code == 200, g.text
    tv = {(t["dokument_id"], t["vrednost"]): t["poreklo"] for t in g.json()["dokazi"]["tvrdnje"]}
    assert tv == {
        (d1, "Tuzeni nije isplatio zaradu za mart 2026. godine."): SOURCE_FACT,
        (d1, "isplatio zaradu za mart 2026. godine."): AI_ANALYSIS,           # D: negacija izostavljena
        (d1, "Rok za uplatu takse istice 04.12.2026. godine."): AI_ANALYSIS,   # E: rečenica DRUGOG scan.pdf
        (d2, "Tuzilac tvrdi da je zakup placen 01.02.2026. godine."): SOURCE_FACT,
        (d2, "zakup placen 01.02.2026. godine."): AI_ANALYSIS,                 # K: pripisivanje izostavljeno
        (d2, "Rok za izjasnjenje istice 04.12.2026. godine."): AI_ANALYSIS,    # E: rečenica DRUGOG scan.pdf
    }
    # Trajni red nosi isti ishod (`nacin_pronalaska`) — ne samo projekcija.
    redovi = {(r["dokument_id"], r["tvrdnja"]): r for r in b.tabele["predmet_dokazi"] if r["predmet_id"] == pid}
    assert redovi[(d1, "isplatio zaradu za mart 2026. godine.")]["nacin_pronalaska"] == NACIN_NIJE
    assert redovi[(d1, "isplatio zaradu za mart 2026. godine.")].get("start_offset") is None
    assert redovi[(d1, "Tuzeni nije isplatio zaradu za mart 2026. godine.")]["nacin_pronalaska"] == NACIN_EGZAKTAN
