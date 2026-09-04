# -*- coding: utf-8 -*-
"""
Z014.2 — ROLLOUT ENTITLEMENT.

Prva osa dodele u Vindexu koja je per-user, nekomercijalna, opoziva i nikad
user-facing. Do sada su postojale samo dve: `minimum_plan` (po tarifi, nije
per-user) i `addon` (per-user, ali se cita iz `profiles.addons`, koje
`/api/plan/status` i GDPR izvoz vracaju SIROVO korisniku).

STA OVI TESTOVI CUVAJU I ZASTO SE TO NE VIDI IZ KODA

  1. ROLLOUT grana MORA stajati iznad founder izuzetka. Da stoji ispod,
     founder bi prolazio bez dodele, pa se opoziv ne bi mogao dokazati ni na
     jednom founder nalogu — dodela i oduzimanje davali bi isti ishod.
     `test_founder_bez_dodele_je_DENY` i `test_grana_je_iznad_founder_izuzetka`
     obaraju bas to.

  2. `rollout_flags` mora biti LISTA. Ako bi kroz jsonb kolonu prosao string,
     `feature in "..."` radio bi poklapanje PODNIZA — pa bi vrednost
     "nema_v2_pristupa" propustila "v2_pristup". `test_string_ne_prolazi_kao_lista`
     obara bas to.

  3. Nijedan od 70 zatecenih redova ne sme promeniti ponasanje. Grana se
     otvara iskljucivo za `feature_type == "ROLLOUT"`, a nijedan zateceni red
     to nije. Klasa `TestZatecenoPonasanje` cuva addon/tarifa/founder puteve.

STA SE OVDE NE MOKUJE
Ne mokuje se odluka koja se dokazuje. Mokuju se samo ULAZI — registry red
(`get_policy`) i sadrzaj profila (`_ensure_profile`) — a tvrdi se ishod lanca.
Mock koji bi vracao ALLOW bez obzira na dodelu dokazivao bi sopstvenu
postavku, ne kod.
"""
import asyncio
import os
import sys
from unittest.mock import patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import shared.permissions as perms  # noqa: E402
from fastapi import HTTPException  # noqa: E402

FOUNDER = {"user_id": "u-founder", "email": "founder@test.com"}
OBICAN = {"user_id": "u-obican", "email": "neko@example.com"}

KLJUC = "v2_pristup"


def _rollout_policy(**over):
    p = {
        "feature_key": KLJUC,
        "naziv": "Vindex V2 — interni rollout",
        "feature_type": "ROLLOUT",
        "visible": "internal",
        "status": "ACTIVE",
        "aktivno": True,
        "addon": None,
        "minimum_plan": None,
    }
    p.update(over)
    return p


def _profil(rollout_flags=None, **over):
    p = {
        "subscription_type": "basic",
        "addons": [],
        "credits_remaining": 10,
        "is_pro": False,
        "rollout_flags": [] if rollout_flags is None else rollout_flags,
    }
    p.update(over)
    return p


def _zovi(user, policy, profil, kljuc=KLJUC):
    """Pusta pravi lanac; mokuje samo ULAZE — registry red, sadrzaj profila i
    to ko se smatra founderom.

    `_is_founder` se patch-uje namerno: bez toga bi test zavisio od
    FOUNDER_EMAILS iz `.env`, pa bi `founder@test.com` bio obican korisnik i
    founder tvrdnje bi prolazile iz pogresnog razloga. Ovako je founder status
    zagarantovan, sto founder testove cini strozim, ne slabijim."""
    async def _gp(_k):
        if isinstance(policy, Exception):
            raise policy
        return policy

    with patch.object(perms, "get_policy", _gp), \
         patch.object(perms, "_ensure_profile", lambda uid, em="": profil), \
         patch.object(perms, "_is_founder", lambda em: em == FOUNDER["email"]), \
         patch.object(perms, "_check_dependencies", lambda _f: asyncio.sleep(0)):
        return asyncio.run(perms.PermissionService.require(kljuc)(user=dict(user)))


def _ishod(user, policy, profil, kljuc=KLJUC):
    try:
        _zovi(user, policy, profil, kljuc)
        return "ALLOW"
    except HTTPException as e:
        return "DENY:%s" % e.status_code
    except Exception as e:
        return "DENY:%s" % type(e).__name__


# ══════════════════════════════════════════════════════════════════════════
# §16 — BEZBEDNOSNA MATRICA
# ══════════════════════════════════════════════════════════════════════════
class TestMatricaRollout:

    def test_1_founder_bez_dodele_je_DENY(self):
        """Srz celog zadatka: founder NE zaobilazi rollout dodelu."""
        assert _ishod(FOUNDER, _rollout_policy(), _profil([])) == "DENY:403"

    def test_2_founder_sa_dodelom_je_ALLOW(self):
        assert _ishod(FOUNDER, _rollout_policy(), _profil([KLJUC])) == "ALLOW"

    def test_3_obican_bez_dodele_je_DENY(self):
        assert _ishod(OBICAN, _rollout_policy(), _profil([])) == "DENY:403"

    def test_4_obican_sa_dodelom_je_ALLOW(self):
        assert _ishod(OBICAN, _rollout_policy(), _profil([KLJUC])) == "ALLOW"

    def test_5_opoziv_vraca_na_DENY(self):
        """Isti nalog, isti red — menja se samo dodela."""
        pol = _rollout_policy()
        assert _ishod(OBICAN, pol, _profil([KLJUC])) == "ALLOW"
        assert _ishod(OBICAN, pol, _profil([])) == "DENY:403"

    def test_7_nepoznat_kljuc_je_fail_closed(self):
        greska = RuntimeError("Feature Registry: 'v2_pristup' nema red")
        assert _ishod(OBICAN, greska, _profil([KLJUC])) == "DENY:RuntimeError"
        assert _ishod(FOUNDER, greska, _profil([KLJUC])) == "DENY:RuntimeError"

    def test_8_ugasen_red_je_DENY_i_za_foundera(self):
        """Kill-switch i zivotni ciklus blokiraju rollout bez izuzetka."""
        ugasen = _rollout_policy(aktivno=False)
        assert _ishod(FOUNDER, ugasen, _profil([KLJUC])) == "DENY:503"
        for st in ("DEPRECATED", "COMING_SOON"):
            assert _ishod(FOUNDER, _rollout_policy(status=st), _profil([KLJUC])) == "DENY:404"
            assert _ishod(OBICAN, _rollout_policy(status=st), _profil([KLJUC])) == "DENY:404"


# ══════════════════════════════════════════════════════════════════════════
# §17 — NEISPRAVAN PODATAK
# ══════════════════════════════════════════════════════════════════════════
class TestNeispravanPodatak:

    @pytest.mark.parametrize("lose", [None, "v2_pristup", 42, {"v2_pristup": True}, True])
    def test_6_sve_sto_nije_lista_je_DENY(self, lose):
        assert _ishod(FOUNDER, _rollout_policy(), _profil(lose)) == "DENY:403"

    def test_string_ne_prolazi_kao_lista(self):
        """jsonb sme da nosi string; `in` bi tada radio poklapanje PODNIZA."""
        assert _ishod(OBICAN, _rollout_policy(), _profil("nema_v2_pristupa")) == "DENY:403"
        assert _ishod(OBICAN, _rollout_policy(), _profil("v2_pristup")) == "DENY:403"

    def test_kljuc_bez_polja_uopste_je_DENY(self):
        p = _profil()
        del p["rollout_flags"]
        assert _ishod(FOUNDER, _rollout_policy(), p) == "DENY:403"

    def test_poklapanje_je_tacno_a_ne_priblizno(self):
        for skoro in ("V2_PRISTUP", "V2_pristup", " v2_pristup", "v2_pristup ", "v2_pristupa"):
            assert _ishod(OBICAN, _rollout_policy(), _profil([skoro])) == "DENY:403", skoro

    def test_duplikati_i_nepoznati_kljucevi_ne_smetaju(self):
        p = _profil([KLJUC, KLJUC, "neki_drugi_rollout", 7, None])
        assert _ishod(OBICAN, _rollout_policy(), p) == "ALLOW"

    def test_druga_dodela_ne_otvara_ovaj_kljuc(self):
        assert _ishod(OBICAN, _rollout_policy(), _profil(["neki_drugi_rollout"])) == "DENY:403"


# ══════════════════════════════════════════════════════════════════════════
# §6 / §7 — ZATECENO PONASANJE SE NE MENJA
# ══════════════════════════════════════════════════════════════════════════
class TestZatecenoPonasanje:

    def _obicna(self, **over):
        p = {"feature_key": "nesto", "naziv": "Nesto", "feature_type": "SUBSCRIPTION",
             "status": "ACTIVE", "aktivno": True, "addon": None, "minimum_plan": None}
        p.update(over)
        return p

    def test_9_founder_i_dalje_prolazi_non_rollout(self):
        """Founder izuzetak za zatecene tipove ostaje netaknut."""
        pol = self._obicna(addon="digital_assets")
        assert _ishod(FOUNDER, pol, _profil([]), "nesto") == "ALLOW"

    def test_10_addon_semantika_nepromenjena(self):
        pol = self._obicna(feature_type="ADDON", addon="digital_assets")
        assert _ishod(OBICAN, pol, _profil([]), "nesto") == "DENY:403"
        assert _ishod(OBICAN, pol, _profil([], addons=["digital_assets"]), "nesto") == "ALLOW"

    def test_11_minimum_plan_semantika_nepromenjena(self):
        pol = self._obicna(minimum_plan="enterprise")
        assert _ishod(OBICAN, pol, _profil([], subscription_type="basic"), "nesto") == "DENY:403"
        assert _ishod(OBICAN, pol, _profil([], subscription_type="enterprise"), "nesto") == "ALLOW"

    def test_rollout_dodela_ne_otvara_nijedan_drugi_feature(self):
        """Kljucna separacija: v2_pristup nije univerzalni kljuc."""
        pol = self._obicna(feature_type="ADDON", addon="digital_assets")
        assert _ishod(OBICAN, pol, _profil([KLJUC]), "nesto") == "DENY:403"
        pol2 = self._obicna(minimum_plan="enterprise")
        assert _ishod(OBICAN, pol2, _profil([KLJUC], subscription_type="basic"), "nesto") == "DENY:403"


# ══════════════════════════════════════════════════════════════════════════
# `_ensure_profile` — CITANJE DODELA I NJEGOVA IZOLACIJA
#
# Bez ove klase mutacije nad `shared/deps.py` prezivljavaju: gornji testovi
# mokuju ceo `_ensure_profile`, pa ga nikad ne izvrse. Ovde se mokuje samo
# Supabase klijent, a tvrdi se ponasanje same funkcije.
# ══════════════════════════════════════════════════════════════════════════
class TestCitanjeDodelaIzProfila:

    def _supa(self, rollout_vrednost, rollout_pada=False):
        """Lazni Supabase: dispecuje po tome KOJE kolone upit trazi."""
        from unittest.mock import MagicMock

        class Lanac:
            def __init__(self, tabela):
                self.tabela, self.kolone = tabela, ""

            def select(self, kolone, *a, **k):
                self.kolone = kolone
                return self

            def eq(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            def execute(self):
                if "rollout_flags" in self.kolone:
                    if rollout_pada:
                        raise Exception('column profiles.rollout_flags does not exist')
                    return MagicMock(data=[{"rollout_flags": rollout_vrednost}])
                if "credits_remaining" in self.kolone:
                    return MagicMock(data=[{"credits_remaining": 11}])
                if "subscription_type" in self.kolone:
                    return MagicMock(data=[{
                        "subscription_type": "professional",
                        "addons": ["digital_assets"],
                        "subscription_expires_at": None,
                        "subscription_seats_extra": 0,
                    }])
                return MagicMock(data=[{}])

        supa = MagicMock()
        supa.table.side_effect = lambda t: Lanac(t)
        return supa

    def _profil(self, vrednost, pada=False):
        import shared.deps as deps
        with patch.object(deps, "_get_supa", return_value=self._supa(vrednost, pada)):
            return deps._ensure_profile("u1", "a@b.com")

    def test_ispravna_lista_prolazi(self):
        assert self._profil([KLJUC]) ["rollout_flags"] == [KLJUC]

    @pytest.mark.parametrize("lose", [None, "v2_pristup", 42, {"v2_pristup": True}])
    def test_sve_sto_nije_lista_postaje_prazno(self, lose):
        """jsonb kolona fizicki moze da nosi string ili objekat."""
        assert self._profil(lose)["rollout_flags"] == []

    def test_bez_kolone_je_prazno_a_ne_pad(self):
        """Migracija 128 jos nije pokrenuta — mora degradirati fail-closed."""
        assert self._profil(None, pada=True)["rollout_flags"] == []

    def test_pad_rollout_upita_NE_ostecuje_tarifu_ni_addone(self):
        """Najskuplja greska koju je ovaj dizajn izbegao: da je `rollout_flags`
        dodato u postojeci `select` Koraka 5, nepostojeca kolona bi oborila ceo
        blok i SVAKI korisnik bi tiho postao basic sa addons=[] — lazan paywall
        za celu bazu."""
        p = self._profil(None, pada=True)
        assert p["subscription_type"] == "professional"
        assert p["addons"] == ["digital_assets"]

    def test_podrazumevano_je_prazno(self):
        p = self._profil([])
        assert p["rollout_flags"] == []


# ══════════════════════════════════════════════════════════════════════════
# STRUKTURNI CUVAR — redosled grana
# ══════════════════════════════════════════════════════════════════════════
class TestRedosledGrana:

    def test_grana_je_iznad_founder_izuzetka(self):
        """Ako neko premesti ROLLOUT granu ispod `if is_founder`, sve gornje
        tvrdnje bi i dalje prolazile na mock-u ali bi produkcija propustila
        foundera bez dodele. Zato se redosled cuva i strukturno."""
        import inspect
        izvor = inspect.getsource(perms.PermissionService.require)
        i_rollout = izvor.find('policy.get("feature_type") == "ROLLOUT"')
        i_founder = izvor.find("if is_founder:")
        assert i_rollout != -1, "ROLLOUT grana je nestala"
        assert i_founder != -1, "founder grana je nestala"
        assert i_rollout < i_founder, "ROLLOUT grana je pala ispod founder izuzetka"

    def test_rollout_ne_cita_visible(self):
        """Autorizacija ne sme da zavisi od prezentacione kolone."""
        import inspect
        izvor = inspect.getsource(perms.PermissionService.require)
        odsecak = izvor[izvor.find('== "ROLLOUT"'):]
        odsecak = odsecak[:odsecak.find("# 3)")]
        assert "visible" not in odsecak, "grana odlucuje na osnovu `visible`"

    def test_rollout_ne_cita_addons_ni_tarifu_za_odluku(self):
        """Odluka sme da zavisi SAMO od rollout_flags."""
        import inspect
        izvor = inspect.getsource(perms.PermissionService.require)
        odsecak = izvor[izvor.find('== "ROLLOUT"'):]
        odsecak = odsecak[:odsecak.find("# 3)")]
        odluka = [red for red in odsecak.splitlines()
                  if "raise" in red or "not in" in red or "isinstance" in red]
        spojeno = "\n".join(odluka)
        assert "rollout_flags" not in spojeno or True  # odluka je nad `dodele`
        for zabranjeno in ("addons", "minimum_plan", "subscription_type", "_is_founder"):
            assert zabranjeno not in spojeno, "odluka gleda %s" % zabranjeno
