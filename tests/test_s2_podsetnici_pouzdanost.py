# -*- coding: utf-8 -*-
"""S2 (Sektor 2) — pouzdanost podsetnika za ročišta i potvrđene rokove: matrica od 10 slučajeva nad stvarnom
`posalji_podsetnike` (lažna baza, lažan SMTP, simulirani dani). NIJEDAN test ne šalje pravi email.

Ugovor (utvrđen čitanjem koda, ne izmišljen): jedno zakazano slanje dnevno (email-cron.yml 08:00 UTC); pragovi 7/3/1
dan pre TAČNOG datuma događaja; jedan grupisan email po korisniku i pragu; rezervacija UNIQUE(user_id, predmet_id,
datum_roka, dana_pre) PRE slanja = at-most-once pokušaj slanja, ne exactly-once isporuka."""
import html as _html
from unittest.mock import patch

import pytest

from tests import test_b10_reminder_claim as b10
from tests.test_g2_podsetnici_raspored import _baza, _dan, _na_dan, u_vreme
from tests.test_n4_podsetnici import P2, PID, UID, _roc, _rok


def _kvar(b, tabela):
    """Upiti nad `tabela` padaju (čitanje i upis)."""
    t = b.table

    def _table(ime):
        if ime == tabela:
            raise RuntimeError(f"{tabela} nedostupna")
        return t(ime)
    b.table = _table


def _drugi_korisnik(b, rokovi=(), rocista=()):
    b.tabele["korisnik_email_notif"].append({"user_id": "u-2", "aktivan": True, "dan_1": True, "dan_3": False, "dan_7": False})
    b.tabele["profiles"].append({"id": "u-2", "email": "drugi@example.invalid"})
    b.tabele["predmeti"].append({"id": "p-9", "user_id": "u-2", "status": "aktivan"})
    b.tabele["predmet_hronologija"].extend(dict(r, user_id="u-2", predmet_id="p-9") for r in rokovi)
    b.tabele["rocista"].extend(dict(r, user_id="u-2", predmet_id="p-9") for r in rocista)


def _telo(p):
    return _html.unescape(p[2])


# ── 1, 2, 3: osnovni slučajevi ─────────────────────────────────────────────────────────────────────────────────

def test_1_zakazano_rociste_salje_se_na_pragu():
    b = _baza(rocista=[_roc("h1", _dan(1))])
    rez, poslati = _na_dan(0, b)
    assert rez["poslato"] == 1 and "Ročište — Osnovni sud u Beogradu" in _telo(poslati[0])


def test_2_potvrdjen_rok_salje_nepotvrdjen_ne():
    b = _baza([_rok("r1", _dan(1)), _rok("r2", _dan(1), dogadjaj="AI predlog bez potvrde")])
    _, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert len(poslati) == 1 and "Rok za žalbu" in _telo(poslati[0]) and "AI predlog bez potvrde" not in _telo(poslati[0])


def test_3_rociste_i_rok_istog_predmeta_i_datuma_oba_u_istom_emailu():
    b = _baza([_rok("r1", _dan(1))], [_roc("h1", _dan(1))])
    _, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert len(poslati) == 1 and "Rok za žalbu" in _telo(poslati[0]) and "Osnovni sud" in _telo(poslati[0])


# ── 4, 5: V3-L1 i G — ISPRAVLJENO (migracija 142, odluke D2/D3) ──────────────────────────────────────────────

def test_4_kasni_drugi_dogadjaj_istog_dana_dobija_svoj_podsetnik_a_prvi_se_ne_ponavlja():
    """V3-L1: ranije drugo slanje ISTOG dana nije slalo rok potvrđen posle prvog (ključ bez identiteta događaja)."""
    b = _baza([_rok("r1", _dan(7))], [_roc("h1", _dan(7))], pragovi=(1, 3, 7))
    assert len(_na_dan(0, b)[1]) == 1                                       # prag 7: samo ročište
    _, poslati = _na_dan(0, b, potvrdjeni=("r1",))                          # isti dan, rok potvrđen
    assert len(poslati) == 1 and "Rok za žalbu" in _telo(poslati[0]) and "Osnovni sud" not in _telo(poslati[0])
    _, poslati = _na_dan(4, b, potvrdjeni=("r1",))                          # prag 3: oba, svaki svojim ključem
    assert len(poslati) == 1 and "Rok za žalbu" in _telo(poslati[0]) and "Osnovni sud" in _telo(poslati[0])


def test_5_dogadjaj_izvrsiv_posle_poslednjeg_praga_dobija_jedan_dodatni_podsetnik():
    """G: rok za sutra potvrđen posle današnjeg slanja i ročište za sutra zakazano posle njega. Ranije: nikad email.
    Sada sutrašnje dnevno slanje (09:00 Beograd) šalje JEDAN dodatni podsetnik: rok „ističe DANAS“, ročište u 10:00
    još predstoji."""
    b = _baza()
    assert _na_dan(0, b)[1] == []
    b.tabele["predmet_hronologija"].append(_rok("r1", _dan(1)))
    b.tabele["rocista"].append(_roc("h1", _dan(1)))
    _, poslati = _na_dan(1, b, potvrdjeni=("r1",))
    assert len(poslati) == 1 and poslati[0][1] == "Vindex AI — Podsetnik: rok i ročište uskoro"
    assert "zabeleženi datum roka: DANAS (vreme isteka nije zabeleženo)" in _telo(poslati[0]) and "u 10:00 — DANAS" in _telo(poslati[0])
    assert sorted((r["dogadjaj_id"], r["svrha"]) for r in b.log) == [("h1", "kasni"), ("r1", "kasni")]
    assert _na_dan(1, b, potvrdjeni=("r1",))[1] == []


def test_5b_propusteno_dnevno_slanje_nadoknadjuje_najkasniji_prag():
    """Dnevno slanje za dan 1 (prag 1 ročišta za dan 2) izostalo: dan 2 šalje dodatni podsetnik (ročište u 10:00,
    slanje u 09:00 Beograd). Ranije: izgubljeno."""
    b = _baza(rocista=[_roc("h1", _dan(2))])
    _, poslati = _na_dan(2, b)
    assert len(poslati) == 1 and "DANAS" in _telo(poslati[0])
    assert [(r["svrha"], r["stanje"]) for r in b.log] == [("kasni", "poslato")]


def test_5c_propusten_srednji_prag_ne_salje_dodatni_jer_najkasniji_jos_stize():
    b = _baza(rocista=[_roc("h1", _dan(3))], pragovi=(1, 3))
    assert _na_dan(1, b)[1] == []                                            # prag 3 (dan 0) izostao; dan 1: 2 dana pre
    assert len(_na_dan(2, b)[1]) == 1 and [r["svrha"] for r in b.log] == ["prag_1"]


# ── 6: prekinut proces ─────────────────────────────────────────────────────────────────────────────────────────

def test_6a_pad_pre_slanja_rezervacija_ne_uspe_nista_poslato_ponovo_moguce():
    b = _baza([_rok("r1", _dan(1))])
    b.insert_puca = True
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert poslati == [] and rez["greske"] == 1 and b.log == []
    b.insert_puca = False
    assert len(_na_dan(0, b, potvrdjeni=("r1",))[1]) == 1


def test_6b_smtp_pada_posle_rezervacije_neisporuceno_bez_ponavljanja():
    import routers.email_notif as en
    from tests.test_g2_podsetnici_raspored import _Dan
    from shared.rate import limiter
    b = _baza([_rok("r1", _dan(1))])
    limiter.reset()
    _Dan.pomak = 0

    def _pada(*a):
        raise TimeoutError("SMTP timeout posle DATA")
    import asyncio
    with u_vreme(_Dan.today()), patch.object(en, "_SMTP_HOST", "smtp.test.invalid"), \
         patch.object(en, "_get_supa", return_value=b), patch.object(en, "_smtp_send", _pada), \
         patch.object(en, "_potvrdjeni_ids", lambda ids: set(ids)):
        rez = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))
    assert rez["neisporuceno"] == 1 and rez["poslato"] == 0 and len(b.log) == 1
    rez2, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert poslati == [] and rez2["poslato"] == 0                            # at-most-once: nema ponovnog slanja


# ── 7: delimičan pad izvora ────────────────────────────────────────────────────────────────────────────────────

def test_7a_pad_citanja_rocista_prag_bez_rezervacije_ponovno_slanje_salje_sve():
    """S2-E F1: ranije (S1-C3) se slao rok i trošila rezervacija — ročište istog predmeta je tada zauvek izostajalo, a
    ponovno pokretanje bilo zeleno. Sada: ništa se ne rezerviše, greska je vidljiva, ponovno slanje šalje oba."""
    b = _baza([_rok("r1", _dan(1))], [_roc("h1", _dan(1))])
    tabela = b.table
    b.table = lambda ime: (_ for _ in ()).throw(RuntimeError("rocista nedostupna")) if ime == "rocista" else tabela(ime)
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert poslati == [] and rez["greske"] == 1 and b.log == []
    b.table = tabela
    _, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert len(poslati) == 1 and "Rok za žalbu" in _telo(poslati[0]) and "Osnovni sud" in _telo(poslati[0])


def test_7b_pad_citanja_rokova_ne_obara_cron_drugi_korisnik_dobija_email():
    """S2: ranije je izuzetak iz upita nad hronologijom prekidao ceo cron — nijedan korisnik nije dobio podsetnik.
    Pogođen korisnik: prag bez rezervacije (greska), pa ponovno slanje šalje i rok i ročište."""
    b = _baza([_rok("r1", _dan(1))], [_roc("h1", _dan(1))])
    _drugi_korisnik(b, rocista=[_roc("h9", _dan(1))])
    tabela = b.table
    pozivi = {"n": 0}

    def _table(ime):
        if ime == "predmet_hronologija":
            pozivi["n"] += 1
            if pozivi["n"] == 1:                       # samo prvi korisnik
                raise RuntimeError("predmet_hronologija nedostupna")
        return tabela(ime)
    b.table = _table
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert [p[0] for p in poslati] == ["drugi@example.invalid"] and rez["greske"] == 1, rez
    assert [r["user_id"] for r in b.log] == ["u-2"]
    _, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert len(poslati) == 1 and poslati[0][0] == b10.MAIL
    assert "Rok za žalbu" in _telo(poslati[0]) and "Osnovni sud" in _telo(poslati[0])


def test_7c_pad_lanca_potvrda_je_greska_predmet_sa_rokom_ceka_ostali_idu():
    """S2: `potvrdjeni_ids` je pri padu vraćao prazan skup → email samo sa ročištem, greske=0, posao zelen, rok
    zauvek izgubljen. Sada: predmet sa kandidat-rokom se ne šalje i ne rezerviše; predmet bez roka ide (uz upozorenje);
    posle oporavka ponovno slanje šalje i rok i ročište prvog predmeta."""
    import asyncio
    import routers.email_notif as en
    from shared import rok_potvrda
    from shared.rate import limiter
    from tests.test_g2_podsetnici_raspored import _Dan
    b = _baza([_rok("r1", _dan(1))], [_roc("h1", _dan(1)), _roc("h2", _dan(1), predmet=P2)])
    b.tabele["predmeti"].append({"id": P2, "user_id": UID, "status": "aktivan"})

    def _lanac_pada(*a, **k):
        raise RuntimeError("audit_immutable nedostupna")
    stvarna = en._potvrdjeni_ids
    limiter.reset()
    _Dan.pomak = 0
    poslati = []
    with patch.object(rok_potvrda, "procitaj_lanac", _lanac_pada), u_vreme(_Dan.today()),          patch.object(en, "_SMTP_HOST", "smtp.test.invalid"), patch.object(en, "_get_supa", return_value=b),          patch.object(en, "_smtp_send", lambda to, s, h: poslati.append((to, s, h))),          patch.object(en, "_potvrdjeni_ids", stvarna):
        rez = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))
    assert rez["greske"] == 1, rez
    assert len(poslati) == 1 and "Rok za žalbu" not in _telo(poslati[0]) and "možda nije potpun" in _telo(poslati[0])
    assert [r["dogadjaj_id"] for r in b.log] == ["h2"]
    _, poslati = _na_dan(0, b, potvrdjeni=("r1",))                         # lanac ponovo dostupan
    assert len(poslati) == 1 and "Rok za žalbu" in _telo(poslati[0]) and "Osnovni sud" in _telo(poslati[0])
    assert sorted(r["dogadjaj_id"] for r in b.log) == ["h1", "h2", "r1"]


def test_7d_lanac_potvrda_procitan_nepotvrdjen_rok_i_dalje_ne_salje_bez_greske():
    """Gejt INV-2 nepromenjen: uspešno pročitan lanac bez potvrde = rok se ne šalje i to NIJE greška."""
    import routers.email_notif as en
    from shared import rok_potvrda
    b = _baza([_rok("r1", _dan(1))])
    with patch.object(rok_potvrda, "procitaj_lanac", lambda *a, **k: []):
        stvarna = en._potvrdjeni_ids
        assert stvarna(["r1"]) == set()
    rez, poslati = _na_dan(0, b, potvrdjeni=())
    assert poslati == [] and rez["greske"] == 0 and b.log == []


@pytest.mark.parametrize("tabela_dnevnika", ["email_podsetnik_dogadjaj", "email_notif_log"])
def test_7e_pad_dnevnika_slanja_preskace_samo_tog_korisnika_bez_rezervacije(tabela_dnevnika):
    """Bez pročitanih ranijih rezervacija (nove ili stare tabele) ne zna se šta je već poslato ni da li je dodatni
    podsetnik potreban → korisnik se preskače BEZ rezervacije (greska); drugi korisnik ide; ponovno slanje šalje sve."""
    b = _baza([_rok("r1", _dan(1))])
    _drugi_korisnik(b, rokovi=[_rok("r9", _dan(1))])
    tabela = b.table
    pozivi = {"n": 0}

    def _table(ime):
        if ime == tabela_dnevnika:
            pozivi["n"] += 1
            # nova tabela: 1. poziv je globalna prijava nepoznatih ishoda, 2. je čitanje za prvog korisnika
            if pozivi["n"] == (2 if tabela_dnevnika == "email_podsetnik_dogadjaj" else 1):
                raise RuntimeError(f"{tabela_dnevnika} timeout")
        return tabela(ime)
    b.table = _table
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1", "r9"))
    assert [p[0] for p in poslati] == ["drugi@example.invalid"] and rez["greske"] == 1, rez
    assert [r["user_id"] for r in b.log] == ["u-2"]
    _, poslati = _na_dan(0, b, potvrdjeni=("r1", "r9"))
    assert [p[0] for p in poslati] == [b10.MAIL]


def test_7f_pad_rezervnog_upita_aktivnih_predmeta_ne_obara_druge_korisnike():
    """Pre migracije 114 (nema kolone) ide rezervni upit; i njegov pad je ranije prekidao ceo cron."""
    b = _baza([_rok("r1", _dan(1))])
    _drugi_korisnik(b, rokovi=[_rok("r9", _dan(1))])
    tabela = b.table
    pozivi = {"n": 0}

    def _table(ime):
        if ime == "predmeti":
            pozivi["n"] += 1
            if pozivi["n"] == 1:
                raise RuntimeError('{"code":"42703","message":"column predmeti.brisanje_zapoceto does not exist"}')
            if pozivi["n"] == 2:
                raise RuntimeError("connection reset by peer")
        return tabela(ime)
    b.table = _table
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1", "r9"))
    assert [p[0] for p in poslati] == ["drugi@example.invalid"] and rez["greske"] == 1, rez


# ── 8: otkazivanje i pomeranje ─────────────────────────────────────────────────────────────────────────────────

def test_8a_otkazano_posle_prvog_praga_ne_salje_sledeci():
    b = _baza(rocista=[_roc("h1", _dan(3))], pragovi=(1, 3))
    assert len(_na_dan(0, b)[1]) == 1
    b.tabele["rocista"][0]["status"] = "otkazano"
    assert _na_dan(2, b)[1] == []


def test_8b_pomereno_rociste_dobija_podsetnik_za_novi_datum_a_ne_za_stari():
    b = _baza(rocista=[_roc("h1", _dan(3))], pragovi=(1, 3))
    assert len(_na_dan(0, b)[1]) == 1
    b.tabele["rocista"][0]["datum"] = _dan(5)
    _, poslati = _na_dan(2, b)                    # dan 2: stari datum bi bio prag 1, novi datum je prag 3
    assert len(poslati) == 1 and _dan(5) in _telo(poslati[0]) and _dan(3) not in _telo(poslati[0])
    assert sorted((r["datum_dogadjaja"], r["svrha"]) for r in b.log) == [(_dan(3), "prag_3"), (_dan(5), "prag_3")]


def test_8c_ispravljen_rok_salje_tacan_datum():
    b = _baza([_rok("r-pred", _dan(1), dogadjaj="Predlog"), _rok("r-isp", _dan(3), dogadjaj="Ispravljen rok")], pragovi=(1, 3))
    assert _na_dan(0, b, potvrdjeni=("r-isp",))[1][0][2].count("Ispravljen rok") == 1
    assert "Predlog" not in _html.unescape(_na_dan(2, b, potvrdjeni=("r-isp",))[1][0][2])


# ── 9: istovremeni procesi ─────────────────────────────────────────────────────────────────────────────────────

def test_9a_potpuno_preklapanje_salje_samo_jedan():
    b = _baza([_rok("r1", _dan(1))])
    b.sakrij_log_od_select = True
    assert len(_na_dan(0, b, potvrdjeni=("r1",))[1]) == 1
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert poslati == [] and len(b.log) == 1


def test_9b_delimicno_preklapanje_ne_gasi_drugi_predmet():
    """S2: drugi proces rezerviše P1 posle našeg čitanja dnevnika. Ranije je atomski višeredni INSERT padao na P1 i
    podsetnik za P2 se za taj prag nikad nije slao (preskoceno, posao zelen)."""
    b = _baza([_rok("r1", _dan(1)), _rok("r2", _dan(1), predmet=P2, dogadjaj="Rok drugog predmeta")])
    b.tabele["predmeti"].append({"id": P2, "user_id": UID, "status": "aktivan"})
    upisi = b.upisi

    def _upisi(tabela, rows):
        if tabela == "email_podsetnik_dogadjaj" and not b.log:
            b.log.append({"user_id": UID, "predmet_id": PID, "tip": "rok", "dogadjaj_id": "r1", "datum_dogadjaja": _dan(1),
                          "svrha": "prag_1", "stanje": "rezervisano", "pokusaja": 1})                  # tuđi proces
        return upisi(tabela, rows)
    b.upisi = _upisi
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1", "r2"))
    assert len(poslati) == 1 and rez["poslato"] == 1 and rez["preskoceno"] == 1
    assert "Rok drugog predmeta" in _telo(poslati[0]) and "Rok za žalbu" not in _telo(poslati[0])   # P1 šalje drugi
    assert sorted(r["dogadjaj_id"] for r in b.log) == ["r1", "r2"]


def test_9c_pad_rezervacije_jednog_predmeta_ne_salje_njega_drugi_ide():
    b = _baza([_rok("r1", _dan(1)), _rok("r2", _dan(1), predmet=P2, dogadjaj="Rok drugog predmeta")])
    b.tabele["predmeti"].append({"id": P2, "user_id": UID, "status": "aktivan"})
    upisi = b.upisi

    def _upisi(tabela, rows):
        if tabela == "email_podsetnik_dogadjaj" and any(r["predmet_id"] == PID for r in rows):
            raise RuntimeError("connection reset by peer")
        return upisi(tabela, rows)
    b.upisi = _upisi
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1", "r2"))
    assert rez["greske"] == 1 and len(poslati) == 1
    assert "Rok drugog predmeta" in _telo(poslati[0]) and "Rok za žalbu" not in _telo(poslati[0])
    assert [r["predmet_id"] for r in b.log] == [P2]                            # P1 nije potrošen → ponovo moguće


# ── 10: razdvajanje korisnika ──────────────────────────────────────────────────────────────────────────────────

def test_10_isti_datumi_razliciti_korisnici_bez_mesanja():
    b = _baza([_rok("r1", _dan(1), dogadjaj="Rok korisnika A")], [_roc("h1", _dan(1))])
    _drugi_korisnik(b, rokovi=[dict(_rok("r9", _dan(1)), dogadjaj="Rok korisnika B")],
                    rocista=[dict(_roc("h9", _dan(1)), sud="Sud korisnika B")])
    _, poslati = _na_dan(0, b, potvrdjeni=("r1", "r9"))
    po_adresi = {p[0]: _telo(p) for p in poslati}
    assert set(po_adresi) == {b10.MAIL, "drugi@example.invalid"}
    assert "Rok korisnika B" not in po_adresi[b10.MAIL] and "Sud korisnika B" not in po_adresi[b10.MAIL]
    assert "Rok korisnika A" not in po_adresi["drugi@example.invalid"]
    assert sorted((r["user_id"], r["predmet_id"], r["dogadjaj_id"]) for r in b.log) == \
        [("u-1", PID, "h1"), ("u-1", PID, "r1"), ("u-2", "p-9", "h9"), ("u-2", "p-9", "r9")]


def test_10b_tudja_potvrda_ne_otvara_rok_drugog_korisnika():
    """Potvrda je po id-u reda; red drugog korisnika ne ulazi u upit (user_id filter), pa ni njegova potvrda."""
    b = _baza()
    _drugi_korisnik(b, rokovi=[_rok("r9", _dan(1))])
    b.tabele["korisnik_email_notif"][1]["aktivan"] = False                     # B nije uključio podsetnike
    rez, poslati = _na_dan(0, b, potvrdjeni=("r9",))
    assert poslati == [] and b.log == []


# ── S2-D: ovlašćenje za pokretanje slanja ──────────────────────────────────────────────────────────────────────

def _ovlascenje(headers, token_payload=None, tajna="tajna-cron-test", bearer=None):
    import asyncio
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    import routers.email_notif as en

    class _Req:
        def __init__(self, h):
            self.headers = h
    kred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=bearer) if bearer else None
    with patch.object(en, "_CRON_SECRET", tajna), patch.object(en, "_verify_token", lambda t: token_payload), \
         patch.object(en, "FOUNDER_EMAILS", {"osnivac@example.invalid"}):
        try:
            return asyncio.run(en._require_cron_or_founder(_Req(headers), kred))
        except HTTPException as exc:
            return exc.status_code


@pytest.mark.parametrize("headers,payload,bearer", [
    ({}, None, None),                                                         # bez ičega
    ({"X-Cron-Key": "pogresan"}, None, None),                                 # odbijen ključ
    ({}, None, "istekao.ili.neispravan"),                                     # istekao / neispravan JWT
    ({}, {"sub": "u-1", "email": "advokat@example.invalid"}, "validan"),      # običan korisnik
])
def test_s2d_neovlasceno_pokretanje_je_403(headers, payload, bearer):
    assert _ovlascenje(headers, payload, bearer=bearer) == 403


def test_s2d_prazna_serverska_tajna_ne_prihvata_ni_prazan_ni_bilo_koji_kljuc():
    assert _ovlascenje({"X-Cron-Key": ""}, tajna="") == 403
    assert _ovlascenje({"X-Cron-Key": "bilo-sta"}, tajna="") == 403


def test_s2d_ispravan_kljuc_i_osnivac_prolaze():
    assert _ovlascenje({"X-Cron-Key": "tajna-cron-test"})["user_id"] == "cron-scheduler"
    assert _ovlascenje({}, {"sub": "f-1", "email": "osnivac@example.invalid"}, bearer="validan")["user_id"] == "f-1"


def test_s2d_iskljucen_profil_ili_prag_ne_salje():
    b = _baza([_rok("r1", _dan(1))])
    b.tabele["korisnik_email_notif"][0]["aktivan"] = False
    assert _na_dan(0, b, potvrdjeni=("r1",))[1] == []
    b = _baza(pragovi=())                                                    # svi pragovi isključeni
    b.tabele["predmet_hronologija"].append(_rok("r1", _dan(1)))
    assert _na_dan(0, b, potvrdjeni=("r1",))[1] == [] and b.log == []
    b = _baza([_rok("r1", _dan(4))], pragovi=(3, 7))                          # dan_1 isključen, prag 3 još stiže
    assert _na_dan(0, b, potvrdjeni=("r1",))[1] == [] and b.log == []
    b = _baza([_rok("r1", _dan(1))])
    b.tabele["korisnik_email_notif"].clear()                                 # korisnik bez profila
    assert _na_dan(0, b, potvrdjeni=("r1",))[0]["napomena"] == "Nema aktivnih profila"
