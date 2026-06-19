# -*- coding: utf-8 -*-
"""
Tests za templates/podnesci.py — 6 strukturisanih šablona podnesaka.

Pokriva:
  - Konzistentnost sva 4 rečnika (TIPOVI, SABLONI, EKSTRAKCIONI, OBOGACIVANJE)
  - popuni_sablon: nepoznat tip, minimalan output, placeholder fallback
  - Specifični testovi za 3 nova tipa: radni spor, razvod, prigovor platni nalog
  - Uslovna sekcija DECA_SEKCIJA u tuzba_razvod
  - VKS analiza sufiks u tuzba_naknada_stete i tuzba_radni_spor
"""
import pytest
from templates.podnesci import (
    TIPOVI,
    SABLONI,
    EKSTRAKCIONI_PROMPTOVI,
    OBOGACIVANJE_PROMPTOVI,
    popuni_sablon,
)

_OCEKIVANI_TIPOVI = [
    "tuzba_naknada_stete",
    "zalba_parnicna",
    "predlog_izvrsenje",
    "tuzba_radni_spor",
    "tuzba_razvod",
    "prigovor_platni_nalog",
    "krivicna_prijava",
    "predlog_privremena_mera",
]

# ─── Konzistentnost rečnika ──────────────────────────────────────────────────

def test_svi_recnici_imaju_iste_kljuceve():
    k_t = set(TIPOVI.keys())
    k_s = set(SABLONI.keys())
    k_e = set(EKSTRAKCIONI_PROMPTOVI.keys())
    k_o = set(OBOGACIVANJE_PROMPTOVI.keys())
    assert k_t == k_s == k_e == k_o, (
        f"Rečnici nisu sinhronizovani:\n"
        f"  TIPOVI: {k_t}\n  SABLONI: {k_s}\n"
        f"  EKSTRAKCIONI: {k_e}\n  OBOGACIVANJE: {k_o}"
    )


def test_svi_ocekivani_tipovi_prisutni():
    missing = [t for t in _OCEKIVANI_TIPOVI if t not in TIPOVI]
    assert not missing, f"Nedostaju tipovi u TIPOVI: {missing}"


def test_tacno_8_tipova():
    assert len(TIPOVI) == 8, f"Očekivano 8 tipova, ima {len(TIPOVI)}"


# ─── popuni_sablon: osnovna validacija ───────────────────────────────────────

def test_nepoznat_tip_vraca_poruku():
    r = popuni_sablon("nepostojeci_tip_xyz", {}, {})
    assert r == "Nepoznat tip podneska."


@pytest.mark.parametrize("tip", _OCEKIVANI_TIPOVI)
def test_prazan_input_daje_neprazan_output(tip):
    r = popuni_sablon(tip, {}, {})
    assert len(r) > 300, f"{tip}: output prekratak ({len(r)} chars)"


@pytest.mark.parametrize("tip", _OCEKIVANI_TIPOVI)
def test_sablon_nema_neresenih_viticicaste_zagrade(tip):
    """Nijedan {PLACEHOLDER} ne sme ostati — svi se zamenjuju ili praznim ili [POPUNITI]."""
    r = popuni_sablon(tip, {}, {})
    # Pronalazi neresene {PLACEHOLDER} koji nisu niti [POPUNITI] niti sadržaj
    import re
    nereseni = re.findall(r'\{[A-Z_]+\}', r)
    assert not nereseni, f"{tip}: nereseni placeholderi: {nereseni}"


@pytest.mark.parametrize("tip", _OCEKIVANI_TIPOVI)
def test_napomena_sistema_u_outputu(tip):
    r = popuni_sablon(tip, {}, {})
    assert "NAPOMENA SISTEMA" in r, f"{tip}: nema NAPOMENA SISTEMA"


# ─── Popunjavanje podataka ────────────────────────────────────────────────────

def test_tuzba_naknada_stete_popunjava_stranke():
    e = {"tuzilac_ime": "Marko Marković", "tuzeni_ime": "XY Osiguranje d.o.o."}
    r = popuni_sablon("tuzba_naknada_stete", e, {})
    assert "Marko Marković" in r
    assert "XY Osiguranje d.o.o." in r


def test_tuzba_naknada_stete_vks_analiza():
    r = popuni_sablon("tuzba_naknada_stete", {}, {}, vks_analiza="VKS TEST 123")
    assert "VKS TEST 123" in r


def test_zalba_parnicna_popunjava_sud():
    e = {"prvostepeni_sud_naziv": "Osnovni sud u Nišu", "broj_predmeta": "P. 77/2026"}
    r = popuni_sablon("zalba_parnicna", e, {})
    assert "Osnovni sud u Nišu" in r
    assert "P. 77/2026" in r


def test_predlog_izvrsenje_popunjava_iznos():
    e = {"iznos_glavnice": "500000", "trazilac_ime": "Ana Anić"}
    r = popuni_sablon("predlog_izvrsenje", e, {})
    assert "500000" in r
    assert "Ana Anić" in r


# ─── Novi tip: tuzba_radni_spor ──────────────────────────────────────────────

def test_tuzba_radni_spor_sadrzi_zakonske_reference():
    r = popuni_sablon("tuzba_radni_spor", {}, {})
    assert "radni spor" in r.lower() or "radnog" in r.lower()


def test_tuzba_radni_spor_popunjava_stranke():
    e = {
        "tuzilac_ime": "Petar Petrović",
        "tuzeni_ime": "ABC d.o.o. Beograd",
        "vrednost_spora": "1200000",
    }
    r = popuni_sablon("tuzba_radni_spor", e, {})
    assert "Petar Petrović" in r
    assert "ABC d.o.o. Beograd" in r
    assert "1200000" in r


def test_tuzba_radni_spor_obogacivanje_popunjava_zahtev():
    o = {"tuzbeni_zahtev": "Poništiti odluku broj 55/2026."}
    r = popuni_sablon("tuzba_radni_spor", {}, o)
    assert "Poništiti odluku broj 55/2026." in r


def test_tuzba_radni_spor_vks_analiza():
    r = popuni_sablon("tuzba_radni_spor", {}, {}, vks_analiza="RADNI SPOR VKS")
    assert "RADNI SPOR VKS" in r


# ─── Novi tip: tuzba_razvod ───────────────────────────────────────────────────

def test_tuzba_razvod_bez_dece_nema_deca_sekcije():
    e = {"ima_dece": False, "deca_raw": "Ana, rod. 2018"}
    r = popuni_sablon("tuzba_razvod", e, {})
    assert "Ana, rod. 2018" not in r


def test_tuzba_razvod_sa_decom_ukljucuje_deca_raw():
    e = {"ima_dece": True, "deca_raw": "Ana, rod. 2018"}
    r = popuni_sablon("tuzba_razvod", e, {})
    assert "Ana, rod. 2018" in r


def test_tuzba_razvod_porodicni_zakon_u_sablonu():
    r = popuni_sablon("tuzba_razvod", {}, {})
    assert "Porodičnog zakona" in r or "PZ" in r


def test_tuzba_razvod_popunjava_datum_braka():
    e = {"datum_braka": "15.06.2010", "tuzilac_ime": "Jovana Jovanović"}
    r = popuni_sablon("tuzba_razvod", e, {})
    assert "15.06.2010" in r
    assert "Jovana Jovanović" in r


def test_tuzba_razvod_uslovni_petitum_bez_dece():
    e = {"ima_dece": False}
    o = {"petitum_starateljstvo": "Dete se poverava tužiocu."}
    r = popuni_sablon("tuzba_razvod", e, o)
    # petitum_starateljstvo goes through regardless of ima_dece — controlled by AI
    assert "Dete se poverava tužiocu." in r


# ─── Novi tip: prigovor_platni_nalog ─────────────────────────────────────────

def test_prigovor_platni_nalog_rok_8_dana():
    r = popuni_sablon("prigovor_platni_nalog", {}, {})
    assert "8 dana" in r


def test_prigovor_platni_nalog_zpp_clan():
    r = popuni_sablon("prigovor_platni_nalog", {}, {})
    assert "462" in r


def test_prigovor_platni_nalog_popunjava_stranke():
    e = {
        "tuzeni_ime": "Nikola Nikolić",
        "tuzilac_ime": "ABC Banka a.d.",
        "iznos_platnog_naloga": "300000",
        "broj_predmeta": "Pl. 5/2026",
    }
    r = popuni_sablon("prigovor_platni_nalog", e, {})
    assert "Nikola Nikolić" in r
    assert "ABC Banka a.d." in r
    assert "300000" in r
    assert "Pl. 5/2026" in r


def test_prigovor_platni_nalog_razlozi_iz_obogacivanja():
    o = {"razlozi_prigovora": "Dug je zastareo pre tri godine."}
    r = popuni_sablon("prigovor_platni_nalog", {}, o)
    assert "Dug je zastareo pre tri godine." in r


# ─── Promptovi: osnovna validacija ───────────────────────────────────────────

@pytest.mark.parametrize("tip", _OCEKIVANI_TIPOVI)
def test_ekstrakcioni_prompt_sadrzi_json(tip):
    prompt = EKSTRAKCIONI_PROMPTOVI[tip]
    assert "{" in prompt and "}" in prompt, f"{tip}: ekstrakcioni prompt ne sadrži JSON strukturu"


@pytest.mark.parametrize("tip", _OCEKIVANI_TIPOVI)
def test_obogacivanje_prompt_neprazan(tip):
    prompt = OBOGACIVANJE_PROMPTOVI[tip]
    assert len(prompt) > 200, f"{tip}: obogacivanje prompt prekratak"


def test_ekstrakcioni_rok_radni_spor():
    """Ekstrakcioni prompt za radni spor mora pomenuti rok od 60 dana (čl. 195 ZR)."""
    prompt = EKSTRAKCIONI_PROMPTOVI["tuzba_radni_spor"]
    assert "60" in prompt


def test_ekstrakcioni_rok_prigovor():
    """Ekstrakcioni prompt za prigovor mora pomenuti rok od 8 dana (čl. 462 ZPP)."""
    prompt = EKSTRAKCIONI_PROMPTOVI["prigovor_platni_nalog"]
    assert "8" in prompt and "462" in prompt


# ─── Novi tip: krivicna_prijava ───────────────────────────────────────────────

def test_krivicna_prijava_zkp_u_sablonu():
    r = popuni_sablon("krivicna_prijava", {}, {})
    assert "280" in r or "ZKP" in r


def test_krivicna_prijava_popunjava_stranke():
    e = {
        "prijavljivac_ime": "Milica Milić",
        "okrivljeni_ime": "Igor Igić",
        "kz_clan_naziv": "Prevara",
        "kz_clan_broj": "208",
        "tuzilac_naziv": "Osnovno javno tužilaštvo u Beogradu",
    }
    r = popuni_sablon("krivicna_prijava", e, {})
    assert "Milica Milić" in r
    assert "Igor Igić" in r
    assert "Prevara" in r
    assert "208" in r
    assert "Osnovno javno tužilaštvo u Beogradu" in r


def test_krivicna_prijava_jmbg_okrivljenog():
    e = {"okrivljeni_jmbg": "1234567890123"}
    r = popuni_sablon("krivicna_prijava", e, {})
    assert "1234567890123" in r


def test_krivicna_prijava_bez_jmbg_nema_placeholder():
    e = {}
    r = popuni_sablon("krivicna_prijava", e, {})
    assert "OKRIVLJENI_JMBG_RED" not in r


def test_krivicna_prijava_obogacivanje():
    o = {
        "cinjenicno_stanje": "Prijavljeni je prevarom uzeo novac.",
        "predlog_tuzilac": "Podigne optužnicu.",
    }
    r = popuni_sablon("krivicna_prijava", {}, o)
    assert "Prijavljeni je prevarom uzeo novac." in r
    assert "Podigne optužnicu." in r


def test_ekstrakcioni_krivicna_pominje_kz():
    prompt = EKSTRAKCIONI_PROMPTOVI["krivicna_prijava"]
    assert "KZ" in prompt or "Krivičnog zakonika" in prompt


# ─── Novi tip: predlog_privremena_mera ───────────────────────────────────────

def test_predlog_privremena_mera_zio_u_sablonu():
    r = popuni_sablon("predlog_privremena_mera", {}, {})
    assert "ZIO" in r or "283" in r


def test_predlog_privremena_mera_fumus_i_periculum():
    r = popuni_sablon("predlog_privremena_mera", {}, {})
    assert "fumus boni iuris" in r.lower() or "fumus" in r.lower()
    assert "periculum in mora" in r.lower() or "periculum" in r.lower()


def test_predlog_privremena_mera_popunjava_stranke():
    e = {
        "predlagac_ime": "Zorana Zorić",
        "protivnik_ime": "XY d.o.o.",
        "vrednost_potrazivanja": "800000",
        "sud_naziv": "Viši sud u Beogradu",
    }
    r = popuni_sablon("predlog_privremena_mera", e, {})
    assert "Zorana Zorić" in r
    assert "XY d.o.o." in r
    assert "800000" in r
    assert "Viši sud u Beogradu" in r


def test_predlog_privremena_mera_obogacivanje():
    o = {
        "fumus_boni_iuris": "Predlagač raspolaže ugovorom.",
        "periculum_in_mora": "Protivnik prodaje imovinu.",
        "vrsta_mere": "Zabrana otuđenja nepokretnosti.",
        "predlog_resenja": "Odredi privremenu meru.",
    }
    r = popuni_sablon("predlog_privremena_mera", {}, o)
    assert "Predlagač raspolaže ugovorom." in r
    assert "Protivnik prodaje imovinu." in r
    assert "Zabrana otuđenja nepokretnosti." in r
    assert "Odredi privremenu meru." in r


def test_ekstrakcioni_privremena_mera_pominje_fumus_periculum():
    prompt = EKSTRAKCIONI_PROMPTOVI["predlog_privremena_mera"]
    assert "fumus" in prompt.lower() or "verovatnost" in prompt.lower()
    assert "periculum" in prompt.lower() or "opasnost" in prompt.lower()
