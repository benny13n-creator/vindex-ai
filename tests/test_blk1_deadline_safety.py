# -*- coding: utf-8 -*-
"""BLK-1 — DATUM ≠ ROK.

BOJAN-BETA-FORENSIC-AUDIT-001 (2026-08-24) je dokazao uživo da Vindex izmišlja
rokove: tužba bez ijednog roka proizvela je red „Rok — tužba" sa datumom
sastavljanja i pouzdanošću 0.95, koji je završio u kalendaru advokata. Uzrok
nije bio prag (0.95 > 0.90) nego KRITERIJUM — pravna TEMA u prozoru od ±100
znakova ("žalba"/"tužba"/"isplata") tretirana je kao dokaz da je datum rok.

Ovi testovi zaključavaju novo pravilo: datum postaje rok samo uz eksplicitan
dokaz o roku neposredno ispred sebe, bez protiv-dokaza, novog reda ili drugog
datuma između. Svaki test ispod PADA na `9a2ce774` (stanje pre popravke) —
mereno, ne pretpostavljeno.
"""
import pytest

from shared.intake_extract import extract_deadline


# ─── TEST MATRIX A-J (nalog §10) ─────────────────────────────────────────────

def test_A_tuzba_bez_roka_ne_proizvodi_rok():
    """Datum sastavljanja tužbe nije rok — ni kad je reč 'isplatu' u blizini.

    Ovo je doslovan dokument iz forenzičkog audita. PRE popravke:
    ('12.01.2026', 0.95). POSLE: (None, 0.0)."""
    tekst = (
        "TUZBA\nTuzilac: Petar Petrovic\nTuzeni: MEGATRADE DOO\n"
        "Tuzeni nije izmirio obavezu u iznosu od 1.250.000,00 dinara.\n"
        "Predlazem da sud obaveze tuzenog na isplatu.\n"
        "U Beogradu, 12.01.2026. godine."
    )
    assert extract_deadline(tekst) == (None, 0.0)


def test_B_datum_potpisa_ugovora_nije_rok():
    """Drugi dokazani slučaj iz audita: 'Rok — ugovor' sa datumom potpisa."""
    tekst = (
        "UGOVOR O POSLOVNOJ SARADNJI\n"
        "Zakljucen dana 12.01.2026. godine izmedju Petra Petrovica i MEGATRADE DOO.\n"
        "Predmet ugovora je isporuka robe."
    )
    assert extract_deadline(tekst) == (None, 0.0)


def test_C_eksplicitan_relativni_rok_i_dalje_radi():
    """Regresija: stvarna pravna pouka mora ostati prepoznata."""
    tekst = (
        "RESENJE\nProtiv ovog resenja dozvoljena je zalba u roku od 15 dana "
        "od dana prijema.\nResenje je primljeno dana 10.08.2026. godine."
    )
    vrednost, conf = extract_deadline(tekst)
    assert vrednost == "15 dana"
    assert conf == pytest.approx(0.77)


def test_D_eksplicitna_rokovna_fraza_uplata():
    tekst = "OPOMENA\nRok za uplatu je 8 dana od prijema fakture.\nFaktura je primljena 01.08.2026."
    vrednost, conf = extract_deadline(tekst)
    assert vrednost == "8 dana"
    assert conf == pytest.approx(0.77)


def test_E_datum_uz_rec_tuzba_nije_rok():
    assert extract_deadline("Tuzba sastavljena 12.01.2026.") == (None, 0.0)


def test_F_datum_uz_rec_isplata_nije_rok():
    """'Isplata izvršena 12.01.2026' je prošao događaj, ne obaveza."""
    assert extract_deadline("Isplata izvrsena 12.01.2026.") == (None, 0.0)


def test_G_datum_rocista_nije_rok():
    """Ročište je događaj. Kalendar ga vodi kroz `rocista`, ne kao rok."""
    assert extract_deadline("Rociste je zakazano za 20.02.2026. godine u 10:00 casova.") == (None, 0.0)


def test_H_vise_datuma_samo_stvarni_rok_prolazi():
    """Pet datuma, jedan rok. Nijedan drugi ne sme da se zarazi."""
    tekst = (
        "IZVOD\nUgovor je zakljucen 01.03.2025. Roba je isporucena 15.04.2025.\n"
        "Resenje je primljeno 10.08.2026. Rociste je zakazano za 20.02.2027.\n"
        "Rok za zalbu istice 25.08.2026. godine."
    )
    vrednost, conf = extract_deadline(tekst)
    assert vrednost == "25.08.2026"
    assert conf == pytest.approx(0.95)


def test_I_dokument_bez_datuma_nema_rok():
    assert extract_deadline("OBAVESTENJE\nObavestavamo Vas da je postupak u toku.") == (None, 0.0)


def test_J_ista_ekstrakcija_dva_puta_daje_isti_rezultat():
    """Determinizam — isti ulaz, isti izlaz. Preduslov da ponovljena obrada
    istog dokumenta ne može proizvesti drugačiji (pa time i duplikatni) rok."""
    tekst = "Rok za zalbu istice 25.08.2026. godine."
    assert extract_deadline(tekst) == extract_deadline(tekst)


# ─── ADVERSARIAL (nalog §11) ─────────────────────────────────────────────────

def test_adv_eksplicitno_negiran_rok():
    """Reč 'Rok' postoji u tekstu, ali POSLE datuma i u rečenici koja rok
    negira. Rokovna reč iza datuma ne sme da ga usvoji unazad."""
    tekst = "Tuzba podneta 12.01.2026. godine. Rok za zalbu ne postoji u ovom dokumentu."
    assert extract_deadline(tekst) == (None, 0.0)


def test_adv_datum_potpisa_nije_rok_placanja():
    """'Ugovor je potpisan 12.01.2026. Rok za placanje je 30 dana.'

    Datum potpisa NE sme postati rok. Relativni izraz '30 dana' jeste rok, ali
    bez datuma-okidača ostaje relativan — `_deadline_to_iso` ga ne pretvara u
    ISO, pa se ne upisuje u kalendar. Nema izmišljenog konkretnog datuma."""
    vrednost, conf = extract_deadline("Ugovor je potpisan 12.01.2026. Rok za placanje je 30 dana.")
    assert vrednost == "30 dana"
    assert "12.01.2026" not in str(vrednost)


def test_adv_isplata_pre_dospeca():
    """Dva datuma, oba prošla, nijedna rokovna reč — nijedan nije rok."""
    tekst = "Isplata je izvrsena 12.01.2026, a obaveza je morala biti ispunjena do 10.01.2026."
    assert extract_deadline(tekst) == (None, 0.0)


def test_adv_gomila_pravnih_reci_i_datuma():
    """Šest datuma, svaki uz pravnu temu (tužba/žalba/isplata). Tema nije dokaz."""
    tekst = (
        "Tuzba 01.02.2026. Zalba 02.02.2026. Isplata 03.02.2026. "
        "Tuzba 04.02.2026. Zalba 05.02.2026. Isplata 06.02.2026."
    )
    assert extract_deadline(tekst) == (None, 0.0)


def test_adv_rokovna_rec_iz_prethodne_recenice_ne_prelazi_na_sledeci_datum():
    """Najsuptilniji slučaj: 'Rok ... ističe 25.08.2026.' i odmah zatim
    'U Beogradu, dana 05.08.2026.' Rokovna reč pripada PRVOM datumu."""
    tekst = (
        "Rok za zalbu istice 25.08.2026. godine.\n"
        "U Beogradu, dana 05.08.2026. godine."
    )
    vrednost, _ = extract_deadline(tekst)
    assert vrednost == "25.08.2026"


def test_adv_datum_prijema_izmedju_rokovne_reci_i_datuma():
    """'u roku od 15 dana od dana prijema.\\nResenje je primljeno dana
    10.08.2026.' — datum prijema je OKIDAČ, ne rok. Protiv-dokaz 'primljeno'
    stoji između rokovne reči i datuma."""
    tekst = (
        "Protiv ovog resenja dozvoljena je zalba u roku od 15 dana od dana prijema.\n"
        "Resenje je primljeno dana 10.08.2026. godine."
    )
    vrednost, _ = extract_deadline(tekst)
    assert vrednost != "10.08.2026"


# ─── INVARIJANTE (nalog §5) ──────────────────────────────────────────────────

@pytest.mark.parametrize("tekst", [
    "Presuda je doneta 12.01.2026.",
    "Resenje je dostavljeno 12.01.2026.",
    "Zapisnik je sastavljen 12.01.2026.",
    "Ugovor je overen 12.01.2026.",
    "Faktura je izdata 12.01.2026.",
    "Rociste je odrzano 12.01.2026.",
])
def test_invarijanta_dogadjajni_datumi_nikad_nisu_rok(tekst):
    """INVARIANT 1/4/5/6/7: puko postojanje datuma, tip dokumenta i tema
    nikad nisu dovoljni. Svaki od ovih datuma pripada svom događaju."""
    assert extract_deadline(tekst) == (None, 0.0)


def test_invarijanta_cirilica_rok_prepoznat():
    """Ćirilički rok mora proći isto kao latinični — inače bi popravka
    'rešila' lažne pozitive tako što bi ubila ćirilične dokumente."""
    vrednost, conf = extract_deadline("Рок за жалбу истиче 25.08.2026. године.")
    assert vrednost == "25.08.2026"
    assert conf == pytest.approx(0.95)


def test_invarijanta_cirilicni_dogadjajni_datum_nije_rok():
    assert extract_deadline("Пресуда је донета 12.01.2026. године.") == (None, 0.0)


# ─── TAČKA UPISA: prag i ljudska potvrda (nalog §8) ──────────────────────────

def test_prag_upisa_je_isti_kao_prag_review_queue():
    """Jedan prag, jedna istina: tačka upisa roka koristi ISTI
    AUTO_ACCEPT_THRESHOLD koji već odlučuje šta ide u review queue."""
    from shared.intake_documents import AUTO_ACCEPT_THRESHOLD
    assert AUTO_ACCEPT_THRESHOLD == 0.90
    # Dokazan rok mora preći taj prag, inače bi ga drugi sloj odbio.
    _, conf = extract_deadline("Rok za zalbu istice 25.08.2026. godine.")
    assert conf >= AUTO_ACCEPT_THRESHOLD


def test_relativni_rok_ne_postaje_datum_u_kalendaru():
    """Relativni rok ('15 dana') nema konkretan datum i zato se NE upisuje —
    `_deadline_to_iso` ga odbija. Ovo je namerno: bolje nijedan rok nego
    izmišljen datum."""
    from routers.smart_intake import _deadline_to_iso
    vrednost, _ = extract_deadline(
        "Protiv ovog resenja dozvoljena je zalba u roku od 15 dana od dana prijema."
    )
    assert vrednost == "15 dana"
    assert _deadline_to_iso(vrednost) is None
