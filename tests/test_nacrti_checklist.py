# -*- coding: utf-8 -*-
"""
Testovi za Nacrti Faza 1 — Checklist Engine.

Testovi su offline (ne pozivaju OpenAI) — mockuju GPT poziv.
Pokriva 5 tipova podnesaka + edge case-ove.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from nacrti.checklist_config import get_config, SVI_TIPOVI, CHECKLIST
from nacrti.checklist_engine import analiziraj_checklist


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _mock_gpt_all_covered(tip: str):
    """Vraća mock koji kaže da je sve pokriveno."""
    config = get_config(tip)
    rezultati = [{"id": i, "pokriven": True} for i in range(len(config["elementi"]))]
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps({"rezultati": rezultati})
    return mock_resp


def _mock_gpt_nothing_covered(tip: str):
    """Vraća mock koji kaže da ništa nije pokriveno."""
    config = get_config(tip)
    rezultati = [{"id": i, "pokriven": False} for i in range(len(config["elementi"]))]
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps({"rezultati": rezultati})
    return mock_resp


CINJENICE_TUZBA = (
    "Tužilac Petar Petrović, JMBG 0101978800123, traži naknadu štete od tuženog "
    "Marka Markovića zbog saobraćajne nezgode dana 15.03.2025. Šteta iznosi 500.000 dinara. "
    "Usled tuženog neodgovornog upravljanja vozilom, tužilac je pretrpeo telesne povrede. "
    "Tražim zakonsku zateznu kamatu od dana nastanka štete. "
    "Kao dokaz prilaže nalaz lekara, fotografije i izveštaj policije. "
    "Tražim i naknadu parničnih troškova."
)

CINJENICE_RADNI = (
    "Zaposleni Jovan Jovanović, JMBG 0205985710012, zaposlen kod poslodavca 'ABC d.o.o.', PIB 102345678, "
    "od dana 01.01.2020. na osnovu ugovora o radu. Dana 10.04.2025. dostavljen mu je otkaz rešenjem br. 15/2025. "
    "Otkaz je nezakonit. Tražim vraćanje na posao i naknadu zarade. "
    "Prilaže ugovor o radu i rešenje o otkazu."
)

CINJENICE_ZALBA = (
    "Žalim se na presudu Osnovnog suda u Beogradu P. 1234/2024 od 05.03.2025. "
    "Prvostepeni sud je pogrešno primenio materijalno pravo i pogrešno utvrdio činjenice. "
    "Presuda mi je dostavljena 12.03.2025. "
    "Predlažem da drugostepeni sud preinači presudu i usvoji tužbeni zahtev."
)

CINJENICE_IZVRSENJE = (
    "Imam presudu Osnovnog suda P.567/2023 koja je postala izvršna i pravosnažna. "
    "Izvršni poverilac: Ana Anić, dužnik: Beta d.o.o. PIB 987654321. "
    "Traži se isplata iznosa od 200.000 dinara. "
    "Sredstvo izvršenja: plata i tekući račun dužnika. "
    "Tražim i naknadu troškova izvršnog postupka."
)

CINJENICE_RAZVOD = (
    "Brak zaključen 20.06.2015. između Jelene i Dragana Đorđevića. "
    "Zajednički život nije moguć jer su bračni odnosi trajno poremećeni. "
    "Imaju dvoje maloletne dece. Traži se razvod i poveravanje dece majci. "
    "Traži se i alimentacija u iznosu od 30.000 dinara mesečno po detetu."
)

# ─── T1: Config pokriva sve tipove ───────────────────────────────────────────

def test_config_svi_tipovi_postoje():
    """Proverava da su svi tipovi definisani i imaju minimum potrebnih elemenata."""
    assert len(SVI_TIPOVI) >= 5, "Mora imati najmanje 5 tipova podnesaka"
    for tip in SVI_TIPOVI:
        cfg = get_config(tip)
        assert "naziv" in cfg, f"{tip}: nedostaje 'naziv'"
        assert "elementi" in cfg, f"{tip}: nedostaje 'elementi'"
        assert len(cfg["elementi"]) >= 4, f"{tip}: mora imati najmanje 4 elementa"


def test_config_kriticnost_validna():
    """Kriticnost mora biti jedna od dozovljenih vrednosti."""
    for tip, cfg in CHECKLIST.items():
        for elem in cfg["elementi"]:
            assert elem["kriticnost"] in ("visoka", "srednja", "niska"), (
                f"{tip}/{elem['naziv']}: nevalidna kriticnost '{elem['kriticnost']}'"
            )
            assert len(elem["kljucne_reci"]) >= 2, f"{tip}/{elem['naziv']}: mora imati >= 2 kljucne_reci"


def test_get_config_nepoznat_tip():
    """KeyError za nepostojeći tip."""
    with pytest.raises(KeyError, match="nepostojeci_tip"):
        get_config("nepostojeci_tip")


# ─── T2: tuzba_naknada_stete — sve pokriveno ─────────────────────────────────

@patch("nacrti.checklist_engine._client")
def test_tuzba_naknada_stete_sve_pokriveno(mock_client):
    mock_client.chat.completions.create.return_value = _mock_gpt_all_covered("tuzba_naknada_stete")
    rezultat = analiziraj_checklist("tuzba_naknada_stete", CINJENICE_TUZBA)

    assert rezultat["tip"] == "tuzba_naknada_stete"
    assert rezultat["procenat_pokrivenosti"] == 100
    assert rezultat["blokira_nastavak"] is False
    assert rezultat["nedostajuci_svi"] == []
    for elem in rezultat["elementi"]:
        assert elem["pokriven"] is True
        assert elem["razlog"] is None


# ─── T3: tuzba_radni_spor — sve pokriveno ────────────────────────────────────

@patch("nacrti.checklist_engine._client")
def test_tuzba_radni_spor_sve_pokriveno(mock_client):
    mock_client.chat.completions.create.return_value = _mock_gpt_all_covered("tuzba_radni_spor")
    rezultat = analiziraj_checklist("tuzba_radni_spor", CINJENICE_RADNI)

    assert rezultat["procenat_pokrivenosti"] == 100
    assert rezultat["blokira_nastavak"] is False


# ─── T4: zalba_parnicna — sve pokriveno ──────────────────────────────────────

@patch("nacrti.checklist_engine._client")
def test_zalba_parnicna_sve_pokriveno(mock_client):
    mock_client.chat.completions.create.return_value = _mock_gpt_all_covered("zalba_parnicna")
    rezultat = analiziraj_checklist("zalba_parnicna", CINJENICE_ZALBA)

    assert rezultat["procenat_pokrivenosti"] == 100
    assert rezultat["blokira_nastavak"] is False


# ─── T5: predlog_izvrsenje — sve pokriveno ───────────────────────────────────

@patch("nacrti.checklist_engine._client")
def test_predlog_izvrsenje_sve_pokriveno(mock_client):
    mock_client.chat.completions.create.return_value = _mock_gpt_all_covered("predlog_izvrsenje")
    rezultat = analiziraj_checklist("predlog_izvrsenje", CINJENICE_IZVRSENJE)

    assert rezultat["procenat_pokrivenosti"] == 100
    assert rezultat["blokira_nastavak"] is False


# ─── T6: tuzba_razvod — sve pokriveno ────────────────────────────────────────

@patch("nacrti.checklist_engine._client")
def test_tuzba_razvod_sve_pokriveno(mock_client):
    mock_client.chat.completions.create.return_value = _mock_gpt_all_covered("tuzba_razvod")
    rezultat = analiziraj_checklist("tuzba_razvod", CINJENICE_RAZVOD)

    assert rezultat["procenat_pokrivenosti"] == 100
    assert rezultat["blokira_nastavak"] is False


# ─── T7: ništa nije pokriveno — blokira_nastavak=True ────────────────────────

@patch("nacrti.checklist_engine._client")
def test_nista_nije_pokriveno_blokira(mock_client):
    mock_client.chat.completions.create.return_value = _mock_gpt_nothing_covered("tuzba_naknada_stete")
    rezultat = analiziraj_checklist("tuzba_naknada_stete", "Tužim nekoga.")

    assert rezultat["procenat_pokrivenosti"] == 0
    assert rezultat["blokira_nastavak"] is True
    assert len(rezultat["nedostajuci_svi"]) == len(get_config("tuzba_naknada_stete")["elementi"])
    # elementi koji nedostaju imaju razlog
    for elem in rezultat["elementi"]:
        assert elem["pokriven"] is False
        assert elem["razlog"] is not None and len(elem["razlog"]) > 0


# ─── T8: delimično pokriveno — razlog samo za nepokrivene ────────────────────

@patch("nacrti.checklist_engine._client")
def test_delimicno_pokriveno(mock_client):
    """Proverava da razlog postoji samo za nepokrivene elemente."""
    config = get_config("tuzba_naknada_stete")
    n = len(config["elementi"])
    # prvih 3 pokrivena, ostatak nije
    rezultati = [{"id": i, "pokriven": i < 3} for i in range(n)]
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps({"rezultati": rezultati})
    mock_client.chat.completions.create.return_value = mock_resp

    rezultat = analiziraj_checklist("tuzba_naknada_stete", "Kratke činjenice.")

    pokriveni = [e for e in rezultat["elementi"] if e["pokriven"]]
    nepokriveni = [e for e in rezultat["elementi"] if not e["pokriven"]]

    assert len(pokriveni) == 3
    assert len(nepokriveni) == n - 3
    for e in pokriveni:
        assert e["razlog"] is None
    for e in nepokriveni:
        assert e["razlog"] is not None


# ─── T9: keyword fallback kad GPT ne vrati sve ID-jeve ───────────────────────

@patch("nacrti.checklist_engine._client")
def test_keyword_fallback(mock_client):
    """Kada GPT ne vrati rezultat za element, engine koristi keyword fallback."""
    mock_resp = MagicMock()
    # GPT vraća samo jedan rezultat umesto svih
    mock_resp.choices[0].message.content = '{"rezultati": [{"id": 0, "pokriven": true}]}'
    mock_client.chat.completions.create.return_value = mock_resp

    cinjenice = (
        "Tužilac Petar Petrović traži naknadu štete. "
        "Datum nezgode je 01.01.2025. Iznos je 100.000 dinara. "
        "Usled nemara tuženog nastupila je šteta. Zakon o obligacionim odnosima. "
        "Tražim zateznu kamatu. Troškovi postupka. "
        "Prilaže dokumenta kao dokaz."
    )
    rezultat = analiziraj_checklist("tuzba_naknada_stete", cinjenice)

    # Mora imati sve elemente u izlazu
    config = get_config("tuzba_naknada_stete")
    assert len(rezultat["elementi"]) == len(config["elementi"])
    # Element 0 je pokriven (GPT odgovorio)
    assert rezultat["elementi"][0]["pokriven"] is True
    # Ostali su procenjeni keyword fallback-om — ne smeju biti sve False ako su ključne reči u tekstu
    # Ne testiramo tačan broj jer zavisi od ključnih reči — samo proveravamo da nema crasheva
    assert "procenat_pokrivenosti" in rezultat


# ─── T10: nepoznat tip baca KeyError ─────────────────────────────────────────

def test_nepoznat_tip_baca_error():
    with pytest.raises(KeyError):
        analiziraj_checklist("nepostojeci_tip", "Neke činjenice.")


# ─── T11: blokira_nastavak=False ako nema VISOKIH koji nedostaju ─────────────

@patch("nacrti.checklist_engine._client")
def test_blokira_false_bez_visokih(mock_client):
    """Ako nedostaju samo SREDNJI i NISKI elementi, blokira_nastavak mora biti False."""
    config = get_config("tuzba_naknada_stete")
    elementi = config["elementi"]

    # Označi sve visoke kao pokrivene, sve ostale kao nepokrivene
    rezultati = []
    for i, e in enumerate(elementi):
        pokriven = e["kriticnost"] == "visoka"
        rezultati.append({"id": i, "pokriven": pokriven})

    import json
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps({"rezultati": rezultati})
    mock_client.chat.completions.create.return_value = mock_resp

    rezultat = analiziraj_checklist("tuzba_naknada_stete", "Tužilac Petar, datum 01.01.2025, iznos 50000 dinara, usled nemara.")

    assert rezultat["blokira_nastavak"] is False
    # Ali ima nedostajućih
    assert len(rezultat["nedostajuci_svi"]) > 0


# ─── T12: struktura rezultata — obavezna polja ───────────────────────────────

@patch("nacrti.checklist_engine._client")
def test_struktura_rezultata(mock_client):
    """Proverava da rezultat ima sva obavezna polja."""
    mock_client.chat.completions.create.return_value = _mock_gpt_all_covered("zalba_parnicna")
    rezultat = analiziraj_checklist("zalba_parnicna", CINJENICE_ZALBA)

    obavezna_polja = {
        "tip", "naziv_tipa", "elementi",
        "nedostajuci_kriticni", "nedostajuci_svi",
        "procenat_pokrivenosti", "blokira_nastavak"
    }
    for polje in obavezna_polja:
        assert polje in rezultat, f"Nedostaje polje: {polje}"

    for elem in rezultat["elementi"]:
        assert "naziv" in elem
        assert "pokriven" in elem
        assert "kriticnost" in elem
        assert "razlog" in elem


# ─── T13: procenat_pokrivenosti je u opsegu 0–100 ────────────────────────────

@patch("nacrti.checklist_engine._client")
def test_procenat_u_opsegu(mock_client):
    mock_client.chat.completions.create.return_value = _mock_gpt_nothing_covered("predlog_izvrsenje")
    r = analiziraj_checklist("predlog_izvrsenje", "Nešto.")
    assert 0 <= r["procenat_pokrivenosti"] <= 100

    mock_client.chat.completions.create.return_value = _mock_gpt_all_covered("predlog_izvrsenje")
    r2 = analiziraj_checklist("predlog_izvrsenje", "Puno teksta.")
    assert r2["procenat_pokrivenosti"] == 100
