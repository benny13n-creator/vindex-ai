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
from tests.test_g2_podsetnici_raspored import _baza, _dan, _na_dan
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


# ── 4, 5: V3-L1 i G — izmereno ponašanje (ograničenje ugovora, ne prolaz) ─────────────────────────────────────

def test_4_kasni_drugi_dogadjaj_istog_dana_ne_dopunjuje_ali_ulazi_u_sledeci_prag():
    """V3-L1: drugo slanje ISTOG dana ne šalje rok potvrđen posle prvog (ključ nema identitet događaja → migracija).
    Pri jednom slanju dnevno ulazi u sledeći uključen prag; ako sledećeg praga nema, email izostaje (slučaj 5)."""
    b = _baza([_rok("r1", _dan(7))], [_roc("h1", _dan(7))], pragovi=(1, 3, 7))
    assert len(_na_dan(0, b)[1]) == 1                                       # prag 7: samo ročište
    assert _na_dan(0, b, potvrdjeni=("r1",))[1] == []                       # isti dan, rok potvrđen → ništa
    _, poslati = _na_dan(4, b, potvrdjeni=("r1",))                          # prag 3
    assert len(poslati) == 1 and "Rok za žalbu" in _telo(poslati[0])


def test_5_dogadjaj_izvrsiv_posle_poslednjeg_praga_nema_email():
    """G: rok za sutra potvrđen posle današnjeg slanja, i ročište zakazano za danas, nemaju više nijedno slanje.
    Ispravka traži novu politiku slanja (odluka osnivača) — ovde se samo meri."""
    b = _baza()
    assert _na_dan(0, b)[1] == []
    b.tabele["predmet_hronologija"].append(_rok("r1", _dan(1)))
    b.tabele["rocista"].append(_roc("h1", _dan(1)))
    assert _na_dan(1, b, potvrdjeni=("r1",))[1] == [] and b.log == []


def test_5b_propusteno_dnevno_slanje_gubi_taj_prag():
    """G (raspored): ako slanje za dan izostane (cron nije pokrenut), prag 1 za sutrašnji događaj se ne nadoknađuje."""
    b = _baza(rocista=[_roc("h1", _dan(2))])
    # dan 1 (prag 1) — slanje se nije dogodilo
    assert _na_dan(2, b)[1] == [] and b.log == []


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
    with patch.object(en, "date", _Dan), patch.object(en, "_SMTP_HOST", "smtp.test.invalid"), \
         patch.object(en, "_get_supa", return_value=b), patch.object(en, "_smtp_send", _pada), \
         patch.object(en, "_potvrdjeni_ids", lambda ids: set(ids)):
        rez = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))
    assert rez["neisporuceno"] == 1 and rez["poslato"] == 0 and len(b.log) == 1
    rez2, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert poslati == [] and rez2["poslato"] == 0                            # at-most-once: nema ponovnog slanja


# ── 7: delimičan pad izvora ────────────────────────────────────────────────────────────────────────────────────

def test_7a_pad_citanja_rocista_rok_se_salje_greska_vidljiva_email_upozorava():
    b = _baza([_rok("r1", _dan(1))])
    _kvar(b, "rocista")
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert len(poslati) == 1 and "Rok za žalbu" in _telo(poslati[0]) and rez["greske"] == 1
    assert "možda nije potpun" in _telo(poslati[0])


def test_7b_pad_citanja_rokova_ne_obara_cron_rociste_i_drugi_korisnik_dobijaju_email():
    """S2: ranije je izuzetak iz upita nad hronologijom prekidao ceo cron — nijedan korisnik nije dobio podsetnik."""
    b = _baza([_rok("r1", _dan(1))], [_roc("h1", _dan(1))])
    _drugi_korisnik(b, rocista=[_roc("h9", _dan(1))])
    _kvar(b, "predmet_hronologija")
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert sorted(p[0] for p in poslati) == ["drugi@example.invalid", b10.MAIL]
    assert rez["greske"] == 2 and all("možda nije potpun" in _telo(p) for p in poslati)


def test_7c_pad_lanca_potvrda_je_greska_a_ne_tiho_nepotvrdjen_rok():
    """S2: `potvrdjeni_ids` je pri padu vraćao prazan skup → email samo sa ročištem, greske=0, posao zelen."""
    import routers.email_notif as en
    from shared import rok_potvrda
    b = _baza([_rok("r1", _dan(1))], [_roc("h1", _dan(1))])

    def _lanac_pada(*a, **k):
        raise RuntimeError("audit_immutable nedostupna")
    with patch.object(rok_potvrda, "procitaj_lanac", _lanac_pada):
        stvarna = en._potvrdjeni_ids
        from tests.test_g2_podsetnici_raspored import _Dan
        from shared.rate import limiter
        import asyncio
        limiter.reset()
        _Dan.pomak = 0
        poslati = []
        with patch.object(en, "date", _Dan), patch.object(en, "_SMTP_HOST", "smtp.test.invalid"), \
             patch.object(en, "_get_supa", return_value=b), \
             patch.object(en, "_smtp_send", lambda to, s, h: poslati.append((to, s, h))), \
             patch.object(en, "_potvrdjeni_ids", stvarna):
            rez = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))
    assert rez["greske"] == 1, rez
    assert len(poslati) == 1 and "Rok za žalbu" not in _telo(poslati[0]) and "možda nije potpun" in _telo(poslati[0])


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


def test_7e_pad_dnevnika_slanja_ne_obara_druge_korisnike():
    b = _baza([_rok("r1", _dan(1))])
    _drugi_korisnik(b, rokovi=[_rok("r9", _dan(1))])
    tabela = b.table
    pozivi = {"n": 0}

    def _table(ime):
        if ime == "email_notif_log":
            pozivi["n"] += 1
            if pozivi["n"] == 1:                       # samo PRVO čitanje dnevnika (prvi korisnik) pada
                raise RuntimeError("email_notif_log timeout")
        return tabela(ime)
    b.table = _table
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1", "r9"))
    assert sorted(p[0] for p in poslati) == ["drugi@example.invalid", b10.MAIL], rez
    assert len(b.log) == 2                                                   # rezervacija je i dalje obavezna


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
    assert sorted((r["datum_roka"], r["dana_pre"]) for r in b.log) == [(_dan(3), 3), (_dan(5), 3)]


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
        if tabela == "email_notif_log" and not b.log:
            b.log.append({"user_id": UID, "predmet_id": PID, "datum_roka": _dan(1), "dana_pre": 1})   # tuđi proces
        return upisi(tabela, rows)
    b.upisi = _upisi
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1", "r2"))
    assert len(poslati) == 1 and rez["poslato"] == 1
    assert "Rok drugog predmeta" in _telo(poslati[0]) and "Rok za žalbu" not in _telo(poslati[0])   # P1 šalje drugi
    assert sorted(r["predmet_id"] for r in b.log) == [PID, P2]


def test_9c_pad_rezervacije_jednog_predmeta_ne_salje_njega_drugi_ide():
    b = _baza([_rok("r1", _dan(1)), _rok("r2", _dan(1), predmet=P2, dogadjaj="Rok drugog predmeta")])
    b.tabele["predmeti"].append({"id": P2, "user_id": UID, "status": "aktivan"})
    upisi = b.upisi

    def _upisi(tabela, rows):
        if tabela == "email_notif_log" and any(r["predmet_id"] == PID for r in rows):
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
    assert sorted((r["user_id"], r["predmet_id"]) for r in b.log) == [("u-1", PID), ("u-2", "p-9")]


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
    b = _baza([_rok("r1", _dan(1))], pragovi=(3, 7))                          # dan_1 isključen
    assert _na_dan(0, b, potvrdjeni=("r1",))[1] == [] and b.log == []
    b = _baza([_rok("r1", _dan(1))])
    b.tabele["korisnik_email_notif"].clear()                                 # korisnik bez profila
    assert _na_dan(0, b, potvrdjeni=("r1",))[0]["napomena"] == "Nema aktivnih profila"
