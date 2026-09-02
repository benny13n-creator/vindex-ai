# -*- coding: utf-8 -*-
"""FAZA 6.4.2 — AUTORIZACIONA GRANICA: nista ne izlazi bez ljudske potvrde.

STA JE BILO POGRESNO (FAZA 6.4.1, dokazano)
===========================================
RED-1: `IZVOR_SME_BEZ_POTVRDE = (AI_ASSISTED, HUMAN_DIRECT, DETERMINISTIC,
SYSTEM)` — cetiri od sest klasa porekla prolazile su kapiju NEPOTVRDJENE. Polje
koje OPISUJE zapis dobilo je moc da ga ODOBRI. To je ista greska koju su faze
6.1–6.3 razotkrile kod `akter`, samo premestena na `izvor`.

RED-2: `routers/viber.py` je citao rokove po `vaznost="kritičan"` i slao ih
kroz Viber bez ijedne kapije.

STA JE SADA
===========
`sme_pokrenuti_obavezu` gleda ISKLJUCIVO stanje ovlascenja. Ni `izvor`, ni
`akter`, ni `vaznost` ne ucestvuju u odluci. Pojam „klase koje smeju bez
potvrde" je UKLONJEN — ne zamenjen drugom listom.

Popis izlaznih puteva je prosiren sa 7 na **12**: FAZA 6.4.1 je nasla Viber,
ova faza jos cetiri (email brifing, WhatsApp x2, izvoz u Google Calendar) koji
su rokove citali kroz kanonski domenski citac `shared/rokovi.py`.

POSLEDICA KOJU TREBA ZNATI
==========================
Dok ne postoji povrsina kojom advokat potvrdjuje rok, NIJEDAN kanal ne salje
nista. To je namerno stanje — fail-closed — a ne kvar.
"""
import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.rokovi import IZVOR_DOZVOLJENI, sme_pokrenuti_obavezu  # noqa: E402

KOREN = os.path.join(os.path.dirname(__file__), "..")


def _izv(rel):
    return io.open(os.path.join(KOREN, rel), encoding="utf-8").read()


def _r(izvor="AI_AUTONOMOUS", vaznost="kritičan", rid="r-1", akter="DOO Alfa Trejd"):
    return {"id": rid, "izvor": izvor, "vaznost": vaznost, "akter": akter,
            "predmet_id": "p-1", "dogadjaj": "Rok", "datum_iso": "2026-03-15"}


# ═══════════════════════════════════════════════════════════════════════════
# §4 — UNCONFIRMED = NO ACTION, za SVAKU klasu i SVAKU vaznost
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("izvor", list(IZVOR_DOZVOLJENI))
@pytest.mark.parametrize("vaznost", ["kritičan", "važan", "informativan"])
def test_unconfirmed_je_uvek_NO_ACTION(izvor, vaznost):
    assert sme_pokrenuti_obavezu(_r(izvor, vaznost), set()) is False


@pytest.mark.parametrize("izvor", list(IZVOR_DOZVOLJENI))
@pytest.mark.parametrize("vaznost", ["kritičan", "važan", "informativan"])
def test_confirmed_otkljucava_jednako_za_sve(izvor, vaznost):
    assert sme_pokrenuti_obavezu(_r(izvor, vaznost), {"r-1"}) is True


@pytest.mark.parametrize("izvor", [None, "", "FUTURE_AGENT", "human_direct", 0, 42])
def test_nepoznato_i_odsutno_je_NO_ACTION(izvor):
    assert sme_pokrenuti_obavezu(_r(izvor), set()) is False
    assert sme_pokrenuti_obavezu({"id": "r-1", "vaznost": "kritičan"}, set()) is False


# ═══════════════════════════════════════════════════════════════════════════
# §14 — ADVERSARIAL MUTACIJE (napadi na model, ne na implementaciju)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("iz_stare,u_novu", [
    ("AI_AUTONOMOUS", "HUMAN_DIRECT"),      # M1
    ("AI_ASSISTED",   "HUMAN_DIRECT"),      # M2
    ("LEGACY_UNKNOWN", "DETERMINISTIC"),    # M3
    ("AI_AUTONOMOUS", "SYSTEM"),
    ("LEGACY_UNKNOWN", "AI_ASSISTED"),
])
def test_promena_provenijencije_NE_daje_ovlascenje(iz_stare, u_novu):
    """Napadac koji moze da promeni `izvor` ne dobija nista — ishod je isti."""
    pre = sme_pokrenuti_obavezu(_r(iz_stare), set())
    posle = sme_pokrenuti_obavezu(_r(u_novu), set())
    assert pre is False and posle is False, f"{iz_stare} -> {u_novu}"


def test_M9_povlacenje_potvrde_zaustavlja_sve():
    r = _r("HUMAN_DIRECT")
    assert sme_pokrenuti_obavezu(r, {"r-1"}) is True
    assert sme_pokrenuti_obavezu(r, set()) is False


@pytest.mark.parametrize("akter", [
    "Advokat", "Genome (AI)", "DOO Alfa Trejd", "", None, "Sud u Beogradu"])
def test_akter_ne_utice_ni_u_jednom_smeru(akter):
    assert sme_pokrenuti_obavezu(_r(akter=akter), set()) is False
    assert sme_pokrenuti_obavezu(_r(akter=akter), {"r-1"}) is True


# ═══════════════════════════════════════════════════════════════════════════
# §5 — zabranjeni oblici NE SMEJU postojati u kodu kapije
# ═══════════════════════════════════════════════════════════════════════════

def test_kapija_ne_grana_po_sadrzaju_reda():
    s = _izv("shared/rokovi.py")
    telo = s[s.index("def sme_pokrenuti_obavezu("):s.index("def filtriraj_izvrsive(")]
    if '"""' in telo:
        a = telo.index('"""')
        b = telo.index('"""', a + 3) + 3
        telo = telo[:a] + telo[b:]
    kod = "\n".join(l for l in telo.split("\n") if not l.strip().startswith("#"))
    for zabranjeno in ("izvor", "vaznost", "akter", "SAFE", "WHITELIST"):
        assert zabranjeno not in kod, f"kapija grana po `{zabranjeno}`:\n{kod}"


def test_nijedna_lista_bezbednih_izvora_ne_postoji():
    import shared.rokovi as _R
    for ime in dir(_R):
        if ime.startswith("IZVOR_") and ime != "IZVOR_DOZVOLJENI":
            vrednost = getattr(_R, ime)
            assert not isinstance(vrednost, (tuple, list, set)), \
                f"`{ime}` je nova lista izvora — to je povratak RED-1"


# ═══════════════════════════════════════════════════════════════════════════
# §6/§15 — KOMPLETAN POPIS IZLAZNIH PUTEVA, svaki kroz ISTU kapiju
# ═══════════════════════════════════════════════════════════════════════════

#: (modul, broj poziva kanonske kapije, kanal)
IZLAZNI_PUTEVI = [
    ("routers/email_notif.py",   3, "email"),
    ("routers/sms.py",           2, "SMS"),
    ("routers/notifications.py", 2, "notifikacija"),
    ("routers/viber.py",         1, "Viber"),            # RED-2, zatvoren
    ("routers/morning_briefing.py", 2, "email brifing"),  # nadjeno u 6.4.2
    ("routers/whatsapp_notif.py",   2, "WhatsApp"),       # nadjeno u 6.4.2
    ("routers/integrations.py",     1, "Google Calendar"),# nadjeno u 6.4.2
]


@pytest.mark.parametrize("modul,n,kanal", IZLAZNI_PUTEVI)
def test_svaki_izlazni_put_zove_kanonsku_kapiju(modul, n, kanal):
    s = _izv(modul)
    assert "from shared.rokovi import filtriraj_izvrsive" in s, \
        f"{kanal}: ne uvozi kanonsku kapiju"
    assert s.count("_filtriraj_izvrsive(") == n, \
        f"{kanal}: {s.count('_filtriraj_izvrsive(')} poziva, ocekivano {n}"


def test_ukupno_trinaest_poziva_kapije_u_sedam_modula():
    """13 poziva kapije preko 7 modula i 7 kanala.

    FAZA 6.2 je tvrdila 7 poziva (email 3, SMS 2, notifikacije 2). FAZA 6.4.1
    je nasla osmi (Viber). Ova faza jos pet: email brifing x2, WhatsApp x2,
    izvoz u Google Calendar x1 — svi su rokove citali kroz kanonski domenski
    citac, pa ih pretraga po `predmet_hronologija` nikad nije videla."""
    assert sum(n for _m, n, _k in IZLAZNI_PUTEVI) == 13
    assert len(IZLAZNI_PUTEVI) == 7
    assert len({k for _m, _n, k in IZLAZNI_PUTEVI}) == 7


@pytest.mark.parametrize("modul,_n,kanal", IZLAZNI_PUTEVI)
def test_nijedan_kanal_nema_sopstvenu_semantiku(modul, _n, kanal):
    """§10: nema `email gate`/`SMS gate`/`Viber gate` sa razlicitim pravilima.
    Svi zovu isti helper i nijedan ne definise svoju verziju."""
    s = _izv(modul)
    assert "def filtriraj_izvrsive" not in s, f"{kanal} ima SVOJU kopiju kapije"
    assert "def sme_pokrenuti_obavezu" not in s, f"{kanal} ima SVOJU kapiju"
    # kanal ne sme sam da odlucuje po poreklu
    for linija in s.split("\n"):
        if "AI_AUTONOMOUS" in linija and "izvor" in linija and "==" in linija:
            raise AssertionError(f"{kanal} grana po klasi porekla: {linija.strip()}")


# ═══════════════════════════════════════════════════════════════════════════
# §16/§17 — traziti izlaz koji CITA rok pa SALJE, a ne zove kapiju
# ═══════════════════════════════════════════════════════════════════════════

#: Moduli koji citaju rokove ali NISU izlazni put. Svaki mora imati razlog.
NIJE_IZLAZ = {
    "routers/client_portal.py": "read-only prikaz klijentu; emailovi ne nose rokove (§12 rizik)",
    "api.py":                   "pogoci su `include_router`, ne slanje",
    "services/case_evolution.py": "notifikacije se projektuju iz `case_actions`, ne iz hronologije",
    "routers/ccc.py":           "analiticki prikaz",
    "routers/search.py":        "pretraga",
    "routers/intake.py":        "upis, ne slanje",
}


def test_nema_nepopisanog_izlaznog_puta():
    """Cuvar arhitekture: novi modul koji cita rokove I ima odlazni kanal mora
    biti ili u `IZLAZNI_PUTEVI` (gejtovan) ili u `NIJE_IZLAZ` (obrazlozen).

    Ovo je odgovor na §23: buduci developer koji napravi nov izlaz bez kapije
    obara ovaj test, umesto da tiho otvori rupu."""
    gejtovani = {m for m, _n, _k in IZLAZNI_PUTEVI}
    kanal_re = re.compile(
        r"smtplib|sendmail|_smtp_send|twilio|viber_send|_posalji_viber|whatsapp|"
        r"requests\.post|httpx\.post|googleapis", re.I)
    rok_re = re.compile(r"predmet_hronologija|rokovi_za_korisnika|rokovi_za_predmet|rok_po_id")

    nepokriveni = []
    for koren, _d, fajlovi in os.walk(KOREN):
        if any(x in koren for x in ("tests", ".git", "node_modules", "scripts", "data")):
            continue
        for ime in fajlovi:
            if not ime.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(koren, ime), KOREN).replace("\\", "/")
            if rel in gejtovani or rel in NIJE_IZLAZ:
                continue
            try:
                s = io.open(os.path.join(koren, ime), encoding="utf-8").read()
            except Exception:
                continue
            if rok_re.search(s) and kanal_re.search(s):
                nepokriveni.append(rel)
    assert not nepokriveni, (
        "moduli citaju rokove i imaju odlazni kanal, a nisu ni gejtovani ni "
        "obrazlozeni: %s" % nepokriveni)
