# -*- coding: utf-8 -*-
"""S2 FINAL — dodatni (kasni) podsetnik, hitna provera posle radnje, vreme (Europe/Belgrade, UTC granica, DST),
kompatibilnost sa starim `email_notif_log` i granice ponavljanja. Baza u memoriji (FakeBaza), lažan SMTP, sat se
zadaje (`_sada`). NIJEDAN test ne šalje pravi email."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tests import test_b10_reminder_claim as b10
from tests.test_n4_podsetnici import PID, UID, _roc, _rok

UTC = timezone.utc
DAN = date(2026, 11, 2)                       # ponedeljak, CET (UTC+1)


def _d(n, od=DAN):
    return (od + timedelta(days=n)).isoformat()


def _baza(rokovi=(), rocista=(), pragovi=(1, 3, 7)):
    b = b10.FakeBaza(list(rokovi))
    b.tabele["rocista"] = list(rocista)
    for p in (1, 3, 7):
        b.tabele["korisnik_email_notif"][0][f"dan_{p}"] = p in pragovi
    return b


class _Smtp:
    def __init__(self, puca=None):
        self.poslati, self.puca = [], puca

    def __call__(self, to, subj, html):
        if self.puca:
            raise self.puca
        self.poslati.append((to, subj, html))


def _okruzenje(b, sada, potvrdjeni, smtp):
    import contextlib
    import routers.email_notif as en
    s = contextlib.ExitStack()
    s.enter_context(patch.object(en, "_SMTP_HOST", "smtp.test.invalid"))
    s.enter_context(patch.object(en, "_get_supa", return_value=b))
    s.enter_context(patch.object(en, "_smtp_send", smtp))
    s.enter_context(patch.object(en, "_potvrdjeni_ids", lambda ids: {i for i in ids if i in set(potvrdjeni)}))
    s.enter_context(patch.object(en, "_sada", lambda: sada))
    return s


def _cron(b, sada, potvrdjeni=(), smtp=None):
    import routers.email_notif as en
    from shared.rate import limiter
    limiter.reset()
    smtp = smtp or _Smtp()
    with _okruzenje(b, sada, potvrdjeni, smtp):
        rez = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))
    return rez, smtp.poslati


def _hitno(b, sada, potvrdjeni=(), smtp=None, uid=UID):
    import routers.email_notif as en
    smtp = smtp or _Smtp()
    with _okruzenje(b, sada, potvrdjeni, smtp):
        rez = en.proveri_hitne_podsetnike(uid)
    return rez, smtp.poslati


def _t(dan, sat, minut=0):
    return datetime(dan.year, dan.month, dan.day, sat, minut, tzinfo=UTC)


def _svrhe(b):
    return sorted((r["dogadjaj_id"], r["svrha"], r["stanje"]) for r in b.log)


# ── vreme: Beograd, UTC granica, DST ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("utc,ocekivano", [
    (datetime(2026, 11, 2, 22, 30, tzinfo=UTC), datetime(2026, 11, 2, 23, 30)),        # CET +1
    (datetime(2026, 11, 2, 23, 30, tzinfo=UTC), datetime(2026, 11, 3, 0, 30)),         # preko ponoći u Beogradu
    (datetime(2026, 7, 1, 22, 30, tzinfo=UTC), datetime(2026, 7, 2, 0, 30)),           # CEST +2
    (datetime(2026, 10, 25, 0, 30, tzinfo=UTC), datetime(2026, 10, 25, 2, 30)),        # pre kraja DST (01:00 UTC)
    (datetime(2026, 10, 25, 1, 30, tzinfo=UTC), datetime(2026, 10, 25, 2, 30)),        # posle kraja DST
    (datetime(2027, 3, 28, 0, 30, tzinfo=UTC), datetime(2027, 3, 28, 1, 30)),          # pre početka DST
    (datetime(2027, 3, 28, 1, 30, tzinfo=UTC), datetime(2027, 3, 28, 3, 30)),          # posle početka DST
])
def test_vreme_beograd(utc, ocekivano):
    import routers.email_notif as en
    assert en._beograd(utc) == ocekivano and en._danas_beograd(utc) == ocekivano.date()


def test_utc_granica_dogadjaj_danas_u_beogradu_nije_sutra():
    """F4: ranije `date.today()` serverski — u 23:30 UTC (00:30 Beograd) ročište za beogradski DANAS je dobijalo
    „Sutra“. Sada je dan beogradski: ročište u 10:00 je DANAS i dobija dodatni podsetnik (prag 1 nije poslat)."""
    b = _baza(rocista=[_roc("h1", _d(1))], pragovi=(1,))
    rez, poslati = _cron(b, datetime(2026, 11, 2, 23, 30, tzinfo=UTC))
    assert len(poslati) == 1 and "Sutra" not in poslati[0][1] and "DANAS" in poslati[0][2]
    b = _baza(rocista=[_roc("h1", _d(1))], pragovi=(1,))
    rez, poslati = _cron(b, datetime(2026, 11, 2, 22, 30, tzinfo=UTC))            # 23:30 Beograd, isti dan
    assert len(poslati) == 1 and poslati[0][1] == "Vindex AI — Sutra: ročište"


def test_dst_rociste_istog_jutra_posle_promene_sata():
    """2026-10-25: sat se vraća 03:00 CEST → 02:00 CET. Ročište u 02:45 lokalno u 01:30 UTC (= 02:30 lokalno) predstoji;
    ročište u 02:15 je prošlo."""
    dan = date(2026, 10, 25)
    b = _baza(rocista=[dict(_roc("h1", dan.isoformat()), vreme="02:45:00"),
                       dict(_roc("h2", dan.isoformat()), vreme="02:15:00", sud="Prošlo")], pragovi=(1,))
    _, poslati = _cron(b, datetime(2026, 10, 25, 1, 30, tzinfo=UTC))
    assert len(poslati) == 1 and "u 02:45" in poslati[0][2] and "Prošlo" not in poslati[0][2]


# ── dodatni podsetnik (D2) ─────────────────────────────────────────────────────────────────────────────────────

def test_rociste_zakazano_d2_posle_poslednjeg_ukljucenog_praga_dobija_odmah_dodatni():
    """Uključeni samo 3 i 7: ročište za 2 dana — nijedan uključen prag više ne stiže → hitna provera šalje odmah."""
    b = _baza(rocista=[_roc("h1", _d(2))], pragovi=(3, 7))
    _, poslati = _hitno(b, _t(DAN, 12))
    assert len(poslati) == 1 and "za 2 dana" in poslati[0][2]
    assert _svrhe(b) == [("h1", "kasni", "poslato")]
    assert _cron(b, _t(DAN + timedelta(days=1), 8))[1] == []                 # sutra: ne ponavlja se


def test_rociste_d2_sa_ukljucenim_pragom_1_ceka_redovni_bez_dodatnog():
    b = _baza(rocista=[_roc("h1", _d(2))], pragovi=(1, 3, 7))
    assert _hitno(b, _t(DAN, 12))[1] == [] and b.log == []
    _, poslati = _cron(b, _t(DAN + timedelta(days=1), 8))
    assert len(poslati) == 1 and poslati[0][1] == "Vindex AI — Sutra: ročište"
    assert _svrhe(b) == [("h1", "prag_1", "poslato")]


def test_rok_potvrdjen_d1_pre_dnevnog_slanja_ceka_ga_a_posle_slanja_ide_odmah():
    b = _baza([_rok("r1", _d(1))])
    assert _hitno(b, _t(DAN, 6), potvrdjeni=("r1",))[1] == []                # dnevno slanje tek dolazi
    assert len(_cron(b, _t(DAN, 13), potvrdjeni=("r1",))[1]) == 1            # i ono ga šalje (zakasnelo, 13 h UTC)
    b = _baza()
    _cron(b, _t(DAN, 13))                                                     # dnevno slanje prošlo, ništa dospelo
    b.tabele["predmet_hronologija"].append(_rok("r1", _d(1)))
    _, poslati = _hitno(b, _t(DAN, 15), potvrdjeni=("r1",))                  # potvrđen posle → odmah, redovni prag 1
    assert len(poslati) == 1 and poslati[0][1] == "Vindex AI — Sutra ističe rok!"
    assert _cron(b, _t(DAN, 16), potvrdjeni=("r1",))[1] == []                # ručno ponovljeno dnevno slanje: ništa


def test_d0_rociste_pre_i_posle_pocetka_i_bez_vremena():
    b = _baza(rocista=[dict(_roc("h1", _d(0)), vreme="14:00:00"),
                       dict(_roc("h2", _d(0)), vreme="09:00:00", sud="Počelo"),
                       dict(_roc("h3", _d(0)), vreme=None, sud="Bez vremena")])
    _, poslati = _hitno(b, _t(DAN, 11))                                      # 12:00 Beograd
    assert len(poslati) == 1 and "u 14:00 — DANAS" in poslati[0][2]
    assert "Počelo" not in poslati[0][2] and "Bez vremena" not in poslati[0][2]
    assert _svrhe(b) == [("h1", "kasni", "poslato")]


def test_d0_rok_samo_datum_istice_danas():
    b = _baza()
    b.tabele["predmet_hronologija"].append(_rok("r1", _d(0)))
    _, poslati = _hitno(b, _t(DAN, 21), potvrdjeni=("r1",))                   # 22:00 Beograd — rok ističe na kraju dana
    assert len(poslati) == 1 and "ističe DANAS" in poslati[0][2] and poslati[0][1] == "Vindex AI — Podsetnik: rok uskoro"


def test_prosao_dogadjaj_se_ne_salje():
    b = _baza([_rok("r1", _d(-1))], [_roc("h1", _d(-1))])
    assert _cron(b, _t(DAN, 8), potvrdjeni=("r1",))[1] == [] and b.log == []


def test_zakasnelo_dnevno_slanje_ne_salje_vec_odrzano_rociste():
    """Dnevno slanje pokrenuto u 17:00 UTC (18:00 Beograd): ročište danas u 15:00 je prošlo → ništa (ne prikazuje se kao
    pravovremen podsetnik); ročište sutra i dalje dobija redovni prag 1."""
    b = _baza(rocista=[dict(_roc("h1", _d(0)), vreme="15:00:00", sud="Danas"), _roc("h2", _d(1))], pragovi=(1,))
    _, poslati = _cron(b, _t(DAN, 17))
    assert len(poslati) == 1 and poslati[0][1] == "Vindex AI — Sutra: ročište" and "Danas" not in poslati[0][2]


def test_dva_kasna_dogadjaja_jedan_grupisan_email_po_pozivu():
    b = _baza([_rok("r1", _d(0))], [dict(_roc("h1", _d(0)), vreme="20:00:00")])
    _, poslati = _hitno(b, _t(DAN, 9), potvrdjeni=("r1",))
    assert len(poslati) == 1 and poslati[0][1] == "Vindex AI — Podsetnik: rok i ročište uskoro"


# ── istovremenost, ponovljene radnje, tuđi korisnik ──────────────────────────────────────────────────────────

def test_ponovljena_i_istovremena_hitna_provera_salje_jednom():
    b = _baza(rocista=[_roc("h1", _d(0))], pragovi=(1,))
    b.tabele["rocista"][0]["vreme"] = "20:00:00"
    _, prvi = _hitno(b, _t(DAN, 9))
    b.sakrij_log_od_select = True                                            # drugi proces nije video prvu rezervaciju
    rez, drugi = _hitno(b, _t(DAN, 9))
    assert len(prvi) == 1 and drugi == [] and rez["preskoceno"] == 1 and len(b.log) == 1


def test_hitna_provera_tudjeg_korisnika_ne_dira_prvog():
    b = _baza(rocista=[dict(_roc("h1", _d(0)), vreme="20:00:00")])
    rez, poslati = _hitno(b, _t(DAN, 9), uid="u-2")                          # u-2 nema profil
    assert poslati == [] and b.log == []


# ── ponavljanje posle sigurnog neuspeha (D4) i ponovna provera uslova ─────────────────────────────────────────

def _neuspeh_pa(b, izmena):
    import routers.email_notif as en
    _cron(b, _t(DAN, 8), potvrdjeni=("r1",), smtp=_Smtp(puca=en._NijePredato("prijava: SMTPAuthenticationError")))
    assert [(r["stanje"], r["pokusaja"]) for r in b.log] == [("neuspeh", 1)]
    izmena(b)
    return _cron(b, _t(DAN, 9), potvrdjeni=("r1",))


def test_posle_sigurnog_neuspeha_ponavlja_se_i_isporucuje_jednom():
    b = _baza([_rok("r1", _d(1))])
    rez, poslati = _neuspeh_pa(b, lambda b: None)
    assert len(poslati) == 1 and [(r["stanje"], r["pokusaja"]) for r in b.log] == [("poslato", 2)]


@pytest.mark.parametrize("izmena", [
    lambda b: b.tabele["korisnik_email_notif"][0].update(aktivan=False),       # odjava pre ponavljanja
    lambda b: b.tabele["korisnik_email_notif"][0].update(dan_1=False, dan_3=False, dan_7=False),   # svi pragovi isključeni
    lambda b: b.tabele["predmeti"][0].update(status="arhiviran"),              # predmet više nije aktivan
    lambda b: b.tabele["predmeti"][0].update(brisanje_zapoceto="2026-11-02T08:30:00+00:00"),
    lambda b: b.tabele["predmeti"][0].update(user_id="drugi-vlasnik"),        # gubitak vlasništva
    lambda b: b.tabele["predmet_hronologija"].clear(),                         # rok uklonjen
])
def test_ponavljanje_ponovo_proverava_sve_uslove(izmena):
    b = _baza([_rok("r1", _d(1))])
    rez, poslati = _neuspeh_pa(b, izmena)
    assert poslati == [] and [r["stanje"] for r in b.log] == ["neuspeh"]


def test_promena_pragova_posle_neuspeha_prag_1_se_ne_ponavlja_a_najkasniji_ukljuceni_nadoknadjuje():
    """Pravilo D2: `prag_1` posle isključenja dana 1 se NE ponavlja. Najkasniji UKLJUČEN prag (3) za ovaj rok nikad nije
    poslat, a više ne može da stigne → jedan dodatni podsetnik (isti kao za rok potvrđen kasno)."""
    b = _baza([_rok("r1", _d(1))])
    rez, poslati = _neuspeh_pa(b, lambda b: b.tabele["korisnik_email_notif"][0].update(dan_1=False))
    assert len(poslati) == 1 and poslati[0][1] == "Vindex AI — Podsetnik: rok uskoro"
    assert _svrhe(b) == [("r1", "kasni", "poslato"), ("r1", "prag_1", "neuspeh")]


def test_odbijen_rok_posle_neuspeha_se_ne_ponavlja():
    import routers.email_notif as en
    b = _baza([_rok("r1", _d(1))])
    _cron(b, _t(DAN, 8), potvrdjeni=("r1",), smtp=_Smtp(puca=en._NijePredato("veza")))
    assert _cron(b, _t(DAN, 9), potvrdjeni=())[1] == []                      # potvrda više ne važi (odbijen)


def test_otkazano_rociste_posle_neuspeha_se_ne_ponavlja():
    import routers.email_notif as en
    b = _baza(rocista=[_roc("h1", _d(1))])
    _cron(b, _t(DAN, 8), smtp=_Smtp(puca=en._NijePredato("veza")))
    b.tabele["rocista"][0]["status"] = "otkazano"
    assert _cron(b, _t(DAN, 9))[1] == []


def test_iscrpljeni_pokusaji_su_vidljiva_greska():
    import routers.email_notif as en
    b = _baza([_rok("r1", _d(1))])
    for sat in range(8, 8 + en._MAX_POKUSAJA):
        _cron(b, _t(DAN, sat), potvrdjeni=("r1",), smtp=_Smtp(puca=en._NijePredato("veza")))
    rez, poslati = _cron(b, _t(DAN, 20), potvrdjeni=("r1",))
    assert poslati == [] and rez["greske"] == 1 and b.log[0]["pokusaja"] == en._MAX_POKUSAJA


def test_nepoznat_ishod_se_ne_ponavlja_ni_kao_dodatni_sutra():
    b = _baza([_rok("r1", _d(1))], pragovi=(1,))
    rez, _ = _cron(b, _t(DAN, 8), potvrdjeni=("r1",), smtp=_Smtp(puca=TimeoutError("posle DATA")))
    assert rez["neisporuceno"] == 1
    assert _cron(b, _t(DAN, 9), potvrdjeni=("r1",))[1] == []                 # isti dan
    assert _cron(b, _t(DAN + timedelta(days=1), 8), potvrdjeni=("r1",))[1] == []   # sutra (d=0): prag 1 „možda poslat“


# ── stari `email_notif_log` (pre migracije 142) ───────────────────────────────────────────────────────────────

def _stari(b, predmet, datum, prag, poslato_at):
    b.stari_log.append({"user_id": UID, "predmet_id": predmet, "datum_roka": datum, "dana_pre": prag, "poslato_at": poslato_at})


def test_stari_red_pokriva_dogadjaj_izvrsiv_pre_njega_a_ne_kasniji():
    """Stari kod je istog dana poslao podsetnik za predmet (08:05). Ročište upisano pre toga je bilo u emailu →
    ne ponavlja se; ročište upisano posle NIJE moglo biti u njemu → šalje se (V3-L1 i za istoriju)."""
    b = _baza(rocista=[dict(_roc("h1", _d(1)), created_at="2026-11-01T10:00:00+00:00"),
                       dict(_roc("h2", _d(1)), created_at="2026-11-02T09:00:00+00:00", sud="Kasnije upisano")])
    _stari(b, PID, _d(1), 1, "2026-11-02T08:05:00+00:00")
    _, poslati = _cron(b, _t(DAN, 10))
    assert len(poslati) == 1 and "Kasnije upisano" in poslati[0][2] and "Osnovni sud" not in poslati[0][2]
    assert _svrhe(b) == [("h2", "prag_1", "poslato")]


def test_stari_red_rok_potvrdjen_posle_slanja_nije_pokriven():
    import routers.email_notif as en
    b = _baza([dict(_rok("r1", _d(1)), created_at="2026-10-20T10:00:00+00:00")])
    _stari(b, PID, _d(1), 1, "2026-11-02T08:05:00+00:00")
    with patch.object(en, "_vremena_potvrda", lambda ids: {"r1": "2026-11-02T09:30:00+00:00"}):
        _, poslati = _cron(b, _t(DAN, 10), potvrdjeni=("r1",))
    assert len(poslati) == 1
    b = _baza([dict(_rok("r1", _d(1)), created_at="2026-10-20T10:00:00+00:00")])
    _stari(b, PID, _d(1), 1, "2026-11-02T08:05:00+00:00")
    with patch.object(en, "_vremena_potvrda", lambda ids: {"r1": "2026-10-21T09:30:00+00:00"}):
        assert _cron(b, _t(DAN, 10), potvrdjeni=("r1",))[1] == []           # potvrđen pre slanja: pokriven


def test_stari_red_bez_vremena_pokriva_bez_duplikata():
    b = _baza(rocista=[_roc("h1", _d(1))])                                    # nema created_at
    _stari(b, PID, _d(1), 1, "2026-11-02T08:05:00+00:00")
    assert _cron(b, _t(DAN, 10))[1] == []


def test_stari_najkasniji_prag_sprecava_dodatni_sutra():
    b = _baza(rocista=[dict(_roc("h1", _d(1)), created_at="2026-10-01T10:00:00+00:00")], pragovi=(1,))
    _stari(b, PID, _d(1), 1, "2026-11-02T08:05:00+00:00")                      # stari kod poslao prag 1 juče
    assert _cron(b, _t(DAN + timedelta(days=1), 7))[1] == []                  # d=0: nema dodatnog (već podsećen)


def test_bez_migracije_142_nista_se_ne_salje_i_posao_je_crven():
    b = _baza([_rok("r1", _d(1))])
    tabela = b.table

    def _table(ime):
        if ime == "email_podsetnik_pokretanje":
            raise RuntimeError('{"code":"42P01","message":"relation \\"public.email_podsetnik_pokretanje\\" does not exist"}')
        return tabela(ime)
    b.table = _table
    rez, poslati = _cron(b, _t(DAN, 8), potvrdjeni=("r1",))
    assert poslati == [] and rez["greske"] == 1 and "142" in rez["napomena"]
    assert all(type(rez[k]) is int and rez[k] >= 0 for k in ("poslato", "greske", "preskoceno", "neisporuceno"))


# ── F3: `informativan` ostaje neoperativan i kad je potvrđen ─────────────────────────────────────────────────

def test_potvrdjen_informativan_rok_nije_operativna_obaveza():
    b = _baza([dict(_rok("r1", _d(1)), vaznost="informativan")])
    assert _cron(b, _t(DAN, 8), potvrdjeni=("r1",))[1] == [] and b.log == []
    b = _baza([dict(_rok("r1", _d(0)), vaznost="informativan")])
    assert _hitno(b, _t(DAN, 8), potvrdjeni=("r1",))[1] == []


# ── nezavisna revizija S2-F: F1–F4 ───────────────────────────────────────────────────────────────────────────

def test_rev_f1_pomereno_ili_vraceno_rociste_nije_pokriveno_starim_redom():
    """Stari red (08:00) za predmet/datum; ročište upisano davno, ali POMERENO na taj datum (updated_at 15:00) → nije
    bilo u starom emailu → dobija podsetnik."""
    b = _baza(rocista=[dict(_roc("h1", _d(9)), created_at="2026-10-01T10:00:00+00:00",
                            updated_at="2026-10-01T10:00:00+00:00")], pragovi=(1,))
    _stari(b, PID, _d(1), 1, "2026-11-02T08:00:00+00:00")                      # stari kod: drugo ročište predmeta
    assert _cron(b, _t(DAN, 8, 30))[1] == []                                  # dnevno slanje prošlo
    b.tabele["rocista"][0].update(datum=_d(1), updated_at="2026-11-02T15:00:00+00:00")   # pomereno na sutra
    _, poslati = _hitno(b, _t(DAN, 15, 5))
    assert len(poslati) == 1 and poslati[0][1] == "Vindex AI — Sutra: ročište"


def test_rev_f2_nepoznat_ishod_hitne_provere_crveni_sledece_dnevno_slanje_jednom():
    b = _baza(pragovi=(1,))
    _cron(b, _t(DAN, 8))                                                      # dnevno slanje (kraj ~08:00)
    b.tabele["predmet_hronologija"].append(_rok("r1", _d(0)))
    rez, _ = _hitno(b, _t(DAN, 10), potvrdjeni=("r1",), smtp=_Smtp(puca=ConnectionResetError("posle DATA")))
    assert rez["neisporuceno"] == 1 and _svrhe(b) == [("r1", "kasni", "nepoznato")]
    rez, poslati = _cron(b, _t(DAN + timedelta(days=1), 8), potvrdjeni=("r1",))
    assert poslati == [] and rez["neisporuceno"] == 1 and rez["zaostalo_nepoznato"] == 1, rez   # posao CRVEN
    rez, _ = _cron(b, _t(DAN + timedelta(days=2), 8), potvrdjeni=("r1",))
    assert rez["zaostalo_nepoznato"] == 0                                    # ne prijavljuje se dvaput


def test_rev_f2b_zaglavljena_rezervacija_prekinutog_procesa_se_prijavljuje():
    b = _baza([_rok("r1", _d(2))], pragovi=(1,))
    _cron(b, _t(DAN, 8))
    b.log.append({"id": "x", "user_id": UID, "predmet_id": PID, "tip": "rok", "dogadjaj_id": "r1",
                  "datum_dogadjaja": _d(2), "svrha": "kasni", "stanje": "rezervisano", "pokusaja": 1,
                  "rezervisano_at": "2026-11-02T10:00:00+00:00", "azurirano_at": "2026-11-02T10:00:00+00:00"})
    rez, _ = _cron(b, _t(DAN + timedelta(days=1), 8), potvrdjeni=("r1",))
    assert rez["zaostalo_nepoznato"] == 1 and rez["neisporuceno"] >= 1, rez


def test_rev_f2c_sopstveni_nepoznat_ishod_dnevnog_slanja_se_ne_broji_ponovo_sutra():
    b = _baza([_rok("r1", _d(1)), _rok("r2", _d(4))], pragovi=(1, 3))
    rez, _ = _cron(b, _t(DAN, 8), potvrdjeni=("r1", "r2"), smtp=_Smtp(puca=TimeoutError("posle DATA")))
    assert rez["neisporuceno"] == 1
    rez, _ = _cron(b, _t(DAN + timedelta(days=1), 8), potvrdjeni=("r1", "r2"))
    assert rez["zaostalo_nepoznato"] == 0, rez


def test_rev_f3_pad_citanja_vremena_potvrda_preskace_korisnika_bez_rezervacije():
    import routers.email_notif as en
    b = _baza([dict(_rok("r2", _d(1)), created_at="2026-11-02T09:00:00+00:00")])
    _stari(b, PID, _d(1), 1, "2026-11-02T08:05:00+00:00")

    def _pada(ids):
        raise RuntimeError("audit_immutable nedostupna")
    with patch.object(en, "_vremena_potvrda", _pada):
        rez, poslati = _cron(b, _t(DAN, 10), potvrdjeni=("r2",))
    assert poslati == [] and rez["greske"] == 1 and b.log == []
    with patch.object(en, "_vremena_potvrda", lambda ids: {"r2": "2026-11-02T09:30:00+00:00"}):
        assert len(_cron(b, _t(DAN, 11), potvrdjeni=("r2",))[1]) == 1         # oporavak: šalje


def test_rev_f4_promena_pragova_posle_poslatog_bliskog_praga_bez_dodatnog():
    b = _baza([_rok("r1", _d(1))], pragovi=(1,))
    assert len(_cron(b, _t(DAN, 8), potvrdjeni=("r1",))[1]) == 1              # prag 1 poslat
    b.tabele["korisnik_email_notif"][0].update(dan_1=False, dan_3=True)
    assert _cron(b, _t(DAN + timedelta(days=1), 8), potvrdjeni=("r1",))[1] == []
    assert _svrhe(b) == [("r1", "prag_1", "poslato")]


def test_brisanje_predmeta_cisti_i_rezervacije_podsetnika():
    from shared.predmet_deletion import TABELE_BEZ_FK
    assert "email_podsetnik_dogadjaj" in TABELE_BEZ_FK and "email_notif_log" in TABELE_BEZ_FK


def test_rev_f2d_prethodno_slanje_racuna_se_od_KRAJA_ne_od_pocetka():
    """Ishod upisan TOKOM dnevnog slanja (posle početka, pre kraja) prijavilo je to slanje — sutra se ne broji ponovo."""
    b = _baza([_rok("r1", _d(1)), _rok("r2", _d(4))], pragovi=(1, 3))
    _cron(b, _t(DAN, 8), potvrdjeni=("r1", "r2"), smtp=_Smtp(puca=TimeoutError("posle DATA")))
    b.log[0]["azurirano_at"] = "2026-11-02T08:01:00+00:00"                     # sat je tekao tokom slanja
    b.tabele["email_podsetnik_pokretanje"][0]["zavrseno_at"] = "2026-11-02T08:02:00+00:00"
    rez, _ = _cron(b, _t(DAN + timedelta(days=1), 8), potvrdjeni=("r1", "r2"))
    assert rez["zaostalo_nepoznato"] == 0, rez


def test_rev_f3b_stvarna_vremena_potvrda_iz_lanca():
    """Bez zamene `_vremena_potvrda`: vreme potvrde iz lanca (posle starog slanja) → šalje; pad lanca → preskok + greska."""
    from shared import rok_potvrda
    b = _baza([dict(_rok("r2", _d(1)), created_at="2026-10-20T09:00:00+00:00")])
    _stari(b, PID, _d(1), 1, "2026-11-02T08:05:00+00:00")

    def _pada(*a, **k):
        raise RuntimeError("audit_immutable nedostupna")
    with patch.object(rok_potvrda, "procitaj_lanac", _pada):
        rez, poslati = _cron(b, _t(DAN, 10), potvrdjeni=("r2",))
    assert poslati == [] and rez["greske"] == 1 and b.log == []
    lanac = [{"action": rok_potvrda.AKCIJA_POTVRDA, "resource_id": "r2", "seq": 1, "created_at": "2026-11-02T09:30:00+00:00"}]
    with patch.object(rok_potvrda, "procitaj_lanac", lambda *a, **k: lanac):
        assert len(_cron(b, _t(DAN, 11), potvrdjeni=("r2",))[1]) == 1
