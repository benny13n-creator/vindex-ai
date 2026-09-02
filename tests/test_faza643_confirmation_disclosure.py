# -*- coding: utf-8 -*-
"""FAZA 6.4.3 — SEMANTIKA POTVRDE + GRANICA OTKRIVANJA PODATAKA.

STA OVAJ FAJL RADI
==================
Forenzicki zakljucava IZMERENO stanje posle 6.4.2. Ne uvodi politiku i ne
popravlja nalaze — dokazuje sta jeste, da se ne bi izgubilo.

TRI ODVOJENE KATEGORIJE (§10), koje se ranije mesalo:

  ACTION      sistem nesto IZVRSAVA   (email, SMS, Viber, WhatsApp, kalendar)
  DISCLOSURE  sistem OTKRIVA podatak  (klijentski portal, izvoz, API odgovor)
  INTERNAL    vidi samo ovlascen advokat (dashboard, kalendar, timeline)

FAZA 6.4.2 je zatvorila ACTION. Ovaj fajl meri DISCLOSURE — i nalazi da je
otvoren prema KLIJENTU.
"""
import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _izv(rel):
    return io.open(os.path.join(KOREN, rel), encoding="utf-8").read()


# ═══════════════════════════════════════════════════════════════════════════
# §2/§12 — POTVRDA JE VEZANA ZA TACAN ID, NI ZA STA DRUGO
# ═══════════════════════════════════════════════════════════════════════════

def test_potvrda_koristi_iskljucivo_rok_id_kao_identitet():
    s = _izv("shared/rok_potvrda.py")
    telo = s[s.index("async def _zapisi("):s.index("def potvrdjeni_ids(")]
    assert 'resource_id=str(rok_id)' in telo.replace(" ", "")
    for zabranjeno in ("datum", "naziv", "vaznost", "akter", "dokument"):
        assert zabranjeno not in telo, f"potvrda koristi `{zabranjeno}` kao identitet"


def test_citanje_potvrda_upareno_po_resource_id():
    """FAZA 6.5: jedini citac odluka je `odluke()`; `potvrdjeni_ids` je izveden
    iz njega. Ugovor je nepromenjen — samo je vlasnik citanja jedan."""
    s = _izv("shared/rok_potvrda.py")
    telo = s[s.index("def odluke("):s.index("def stanje_roka(")]
    assert '.in_("resource_id", ids)' in telo
    assert '.eq("resource_type", RESURS)' in telo
    for zabranjeno in ("datum", "naziv", "vaznost", "akter"):
        assert zabranjeno not in telo, f"citanje potvrda gleda `{zabranjeno}`"


@pytest.mark.parametrize("opis,a,b", [
    ("A  potvrda jednog ne potvrdjuje drugi",
     {"id": "rok-A"}, {"id": "rok-B"}),
    ("B  isti datum/naziv/vaznost, razlicit ID",
     {"id": "rok-1", "datum_iso": "2026-03-15", "dogadjaj": "Rok za žalbu", "vaznost": "kritičan"},
     {"id": "rok-2", "datum_iso": "2026-03-15", "dogadjaj": "Rok za žalbu", "vaznost": "kritičan"}),
    ("C  isti tip, razlicit datum",
     {"id": "rok-x", "dogadjaj": "Rok za žalbu", "datum_iso": "2026-03-15"},
     {"id": "rok-y", "dogadjaj": "Rok za žalbu", "datum_iso": "2026-06-15"}),
])
def test_potvrda_je_izolovana_po_roku(opis, a, b):
    from shared.rokovi import sme_pokrenuti_obavezu
    potvrde = {a["id"]}
    assert sme_pokrenuti_obavezu(a, potvrde) is True, opis
    assert sme_pokrenuti_obavezu(b, potvrde) is False, opis


# ═══════════════════════════════════════════════════════════════════════════
# §4/§5/§6 — POTVRDA NE MENJA POREKLO, AKTERA NI PRIORITET
# ═══════════════════════════════════════════════════════════════════════════

def test_potvrda_ne_dira_predmet_hronologija():
    """`_zapisi` pise ISKLJUCIVO u `audit_immutable`. Time su `izvor`, `akter`
    i `vaznost` ocuvani po konstrukciji — ne postoji kod koji ih menja."""
    s = _izv("shared/rok_potvrda.py")
    # Docstring modula OBJASNJAVA odnos prema `predmet_hronologija`, pa se meri
    # samo IZVRSNI kod: jedini upit sme biti nad `audit_immutable`.
    assert 'table("predmet_hronologija")' not in s, \
        "modul potvrde dira tabelu rokova — poreklo/akter/prioritet vise nisu ocuvani"
    assert s.count('table("audit_immutable")') == 1


def test_potvrdjen_ai_rok_ostaje_ai():
    """`AI_AUTONOMOUS` + potvrda NE postaje `HUMAN_DIRECT`."""
    from shared.rokovi import sme_pokrenuti_obavezu
    red = {"id": "r1", "izvor": "AI_AUTONOMOUS", "akter": "Sud u Beogradu",
           "vaznost": "važan"}
    assert sme_pokrenuti_obavezu(red, {"r1"}) is True
    # kapija ne vraca izmenjen red — nema mesta gde bi se poreklo prepisalo
    assert red["izvor"] == "AI_AUTONOMOUS"
    assert red["akter"] == "Sud u Beogradu"
    assert red["vaznost"] == "važan"


# ═══════════════════════════════════════════════════════════════════════════
# §16/§17/§18 — NEMA IMPLICITNE POTVRDE (jer nema NIJEDNE potvrde)
# ═══════════════════════════════════════════════════════════════════════════

def _pozivaoci_potvrde():
    nadjeni = []
    for k, _d, fs in os.walk(KOREN):
        if any(x in k for x in ("tests", ".git", "node_modules", "data", "__pycache__")):
            continue
        for ime in fs:
            if not ime.endswith((".py", ".js")):
                continue
            rel = os.path.relpath(os.path.join(k, ime), KOREN).replace(os.sep, "/")
            if rel == "shared/rok_potvrda.py":
                continue
            s = io.open(os.path.join(k, ime), encoding="utf-8", errors="replace").read()
            if re.search(r"\b(potvrdi_rok|odbij_rok)\b", s):
                nadjeni.append(rel)
    return nadjeni


def test_potvrdu_poziva_TACNO_JEDNA_povrsina():
    """FAZA 6.4.3 je izmerila NULA pozivaoca — advokat nije mogao nista da
    potvrdi, pa je izlazni sloj bio mrtav. FAZA 6.5 je dodala namensku rutu.

    Ovaj test je zato promenjen sa „nema nijednog" na „ima tacno jednog": to je
    nova, uza tvrdnja, ne slabija. Ako se pojavi drugi pozivalac — upload,
    Copilot, kreiranje predmeta, izvoz — test pada i mora se dokazati da nova
    povrsina ne uvodi implicitnu potvrdu."""
    assert _pozivaoci_potvrde() == ["routers/rok_odluka.py"], (
        "potvrdu poziva neko van namenske rute: %s" % _pozivaoci_potvrde())


def test_nijedan_pisac_hronologije_ne_upisuje_potvrdu():
    """Upis roka (bilo kog od 16 pisaca) ne sme sam sebe potvrditi."""
    for rel in ("api.py", "routers/case_dna.py", "routers/smart_intake.py",
                "routers/copilot.py", "routers/intake.py", "routers/rocista.py"):
        s = _izv(rel)
        assert "rok_potvrdjen" not in s, f"{rel} upisuje potvrdu pri kreiranju roka"
        assert "potvrdi_rok" not in s, f"{rel} potvrdjuje rok koji upisuje"


# ═══════════════════════════════════════════════════════════════════════════
# §15 — AUDIT DOVOLJNOST
# ═══════════════════════════════════════════════════════════════════════════

def test_audit_nosi_ko_sta_kada_koji_rok_i_redosled():
    """`audit_immutable` vec ima sva trazena polja — nova tabela nije potrebna."""
    s = _izv("shared/rok_potvrda.py")
    telo = s[s.index("async def _zapisi("):s.index("def potvrdjeni_ids(")]
    assert "user_id=user_id" in telo.replace(" ", "").replace("user_id=user_id", "user_id=user_id")
    assert "user_id" in telo          # KO
    assert "akcija" in telo           # STA (odluka)
    assert "resource_id" in telo      # KOJI tacno rok
    # KADA + REDOSLED dolaze iz same tabele:
    s2 = _izv("shared/rok_potvrda.py")
    assert '.order("seq")' in s2, "redosled odluka nije determinisan"


def test_poslednja_odluka_pobedjuje():
    s = _izv("shared/rok_potvrda.py")
    telo = s[s.index("def odluke("):s.index("def stanje_roka(")]
    assert '.order("seq")' in telo
    assert "poslednja" in telo


def test_potvrdjeni_ids_je_izveden_iz_odluke():
    """Dva nezavisna citaca bi se vremenom razisla — zato je samo jedan."""
    s = _izv("shared/rok_potvrda.py")
    telo = s[s.index("def potvrdjeni_ids("):s.index("async def potvrdjeni_ids_async(")]
    assert "odluke(" in telo
    assert "audit_immutable" not in telo, "`potvrdjeni_ids` ima svoj upit"


# ═══════════════════════════════════════════════════════════════════════════
# §7/§9/§11 — OTKRIVANJE PODATAKA
# ═══════════════════════════════════════════════════════════════════════════

def test_klijentski_portal_NE_cita_potvrdu():
    """IZMERENI NALAZ (§22 RED uslov).

    `GET /api/client-portal/view` je token-based BEZ logina — drzi ga klijent,
    dakle trece lice. Vraca do 50 redova hronologije (`dogadjaj, datum,
    datum_iso, akter, vaznost`) i do 10 „kriticnih rokova". Jedini filter je
    tekstualni prefiks `[INTERNI]` i `vaznost != "interni"`.

    Ni `izvor` ni potvrda se NE citaju — nepotvrdjen AI rok je vidljiv
    klijentu."""
    s = _izv("routers/client_portal.py")
    assert "potvrdjeni_ids" not in s and "_filtriraj_izvrsive" not in s
    assert 'table("predmet_hronologija")' in s
    assert "X-Portal-Token" in s, "portal vise nije token-based — proveriti nalaz"


def test_portal_filtrira_samo_po_tekstu_i_prioritetu():
    s = _izv("routers/client_portal.py")
    telo = s[s.index("hron_filtered = ["):s.index("roc_raw =")]
    assert "[INTERNI]" in telo and 'vaznost") != "interni"' in telo
    assert "izvor" not in telo, "filter gleda poreklo — nalaz je zastareo, proveriti"


#: Kanali koji ACTION izvrsavaju i citaju potvrdu (FAZA 6.4.2).
ACTION_SA_POTVRDOM = {
    "routers/email_notif.py", "routers/sms.py", "routers/notifications.py",
    "routers/viber.py", "routers/morning_briefing.py",
    "routers/whatsapp_notif.py", "routers/integrations.py",
}


def _moduli_sa_rutama_nad_rokovima():
    rok_re = re.compile("predmet_hronologija|rokovi_za_korisnika|rokovi_za_predmet|rok_po_id")
    ruta_re = re.compile(r"@(?:app|router)[.](?:get|post|patch|put)")
    out = {}
    for k, _d, fs in os.walk(KOREN):
        if any(x in k for x in ("tests", ".git", "node_modules", "data", "scripts", "__pycache__", "site")):
            continue
        for ime in fs:
            if not ime.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(k, ime), KOREN).replace(os.sep, "/")
            s = io.open(os.path.join(k, ime), encoding="utf-8", errors="replace").read()
            if rok_re.search(s) and ruta_re.search(s):
                out[rel] = bool(re.search("potvrdjeni_ids|_filtriraj_izvrsive", s))
    return out


def test_sedam_od_cetrdesettri_modula_cita_potvrdu():
    """IZMERENO: 43 modula sa rutama dodiruju rokove; potvrdu cita 7 — tacno
    oni koje je 6.4.2 gejtovala. Preostalih 36 su DISCLOSURE ili INTERNAL
    povrsine, za koje politika JOS NIJE definisana."""
    m = _moduli_sa_rutama_nad_rokovima()
    sa = {k for k, v in m.items() if v}
    assert sa == ACTION_SA_POTVRDOM, f"skup gejtovanih modula se promenio: {sa ^ ACTION_SA_POTVRDOM}"
    assert len(m) >= 40, f"popis se smanjio na {len(m)} — proveriti pretragu"


def test_action_i_disclosure_nisu_isti_skup():
    """§10: ne sme se ponoviti greska da se samo slanje smatra izvrsenjem."""
    m = _moduli_sa_rutama_nad_rokovima()
    disclosure = set(m) - ACTION_SA_POTVRDOM
    assert "routers/client_portal.py" in disclosure
    assert len(disclosure) > len(ACTION_SA_POTVRDOM), \
        "povrsina otkrivanja je manja od povrsine akcije — malo verovatno, proveriti"
