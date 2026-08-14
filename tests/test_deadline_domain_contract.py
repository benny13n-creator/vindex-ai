# -*- coding: utf-8 -*-
"""
BETA-DEADLINE-DOMAIN-001 §A — UGOVOR KANONSKOG SLOJA ZA ROKOVE.

Ovi testovi zaključavaju jednu razliku koju je ceo domen godinu dana brisao:

    upit izvršen, nema redova   →  PRAZNO   (sme se prikazati kao „nema rokova")
    upit NIJE izvršen           →  NEUSPEH  (NE sme se prikazati kao „nema rokova")

Trinaest zatečenih pozivalaca radilo je `except: return []`, `except: pass` ili
je puštalo 500. Sva tri ishoda su na ekranu izgledala isto — kao prazan dan.

Lažni Supabase ovde odbija nepostojeće kolone tačno kao PostgREST, i sadrži
IZMERENU produkcionu šemu `predmet_hronologija` (10 kolona). Test koji dopušta
proizvoljno ime kolone ne bi uhvatio ni jedan od nalaza ovog sprinta.
"""
import asyncio
import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from shared import rokovi as R  # noqa: E402

UID = "uid-advokat"
PRED = "pred-1"

# Izmerene produkcione kolone `predmet_hronologija` (OpenAPI koren, 2026-08-14).
SEMA_HRONOLOGIJA = {"akter", "created_at", "datum", "datum_iso", "dogadjaj",
                    "dokument_naziv", "id", "predmet_id", "user_id", "vaznost"}

DANAS = date.today()


class _Supa:
    """Lažni Supabase koji STVARNO primenjuje šemu i filtere."""

    def __init__(self, redovi=None, puca=False, sirov_odgovor=None):
        self.redovi = redovi if redovi is not None else []
        self.puca = puca
        self.sirov_odgovor = sirov_odgovor
        self.trazene_kolone = set()
        self.filtri = {}
        self.tabele = []

    def table(self, ime):
        spolja = self
        spolja.tabele.append(ime)

        class _Q:
            def __init__(self):
                self.f = {}

            def select(self, izraz, *a, **k):
                kolone = {c.strip() for c in izraz.split(",") if c.strip()}
                spolja.trazene_kolone |= kolone
                nepoznate = kolone - SEMA_HRONOLOGIJA
                if nepoznate:
                    raise RuntimeError("column %s.%s does not exist (42703)"
                                       % (ime, sorted(nepoznate)[0]))
                return self

            def eq(self, k, v):
                self.f[k] = v
                return self

            def gte(self, k, v):
                self.f["gte_" + k] = v
                return self

            def lte(self, k, v):
                self.f["lte_" + k] = v
                return self

            def order(self, *a, **k):
                return self

            def limit(self, n):
                self.f["limit"] = n
                return self

            def execute(self):
                spolja.filtri = dict(self.f)
                if spolja.puca:
                    raise RuntimeError("baza nedostupna")
                if spolja.sirov_odgovor is not None:
                    return MagicMock(data=spolja.sirov_odgovor)
                izlaz = []
                for r in spolja.redovi:
                    if "user_id" in self.f and r.get("user_id") != self.f["user_id"]:
                        continue
                    if "predmet_id" in self.f and r.get("predmet_id") != self.f["predmet_id"]:
                        continue
                    if "id" in self.f and r.get("id") != self.f["id"]:
                        continue
                    d = str(r.get("datum_iso") or "")
                    if "gte_datum_iso" in self.f and d < self.f["gte_datum_iso"]:
                        continue
                    if "lte_datum_iso" in self.f and d > self.f["lte_datum_iso"]:
                        continue
                    izlaz.append(r)
                return MagicMock(data=izlaz[: self.f.get("limit", 1000)])
        return _Q()


def _red(dana_od_danas=1, vaznost="kritičan", dogadjaj="Rok: žalba",
         predmet_id=PRED, user_id=UID, rid="h1", **kw):
    d = (DANAS + timedelta(days=dana_od_danas)).isoformat()
    red = {"id": rid, "predmet_id": predmet_id, "user_id": user_id,
           "dogadjaj": dogadjaj, "datum_iso": d, "vaznost": vaznost,
           "akter": "Automatski"}
    red.update(kw)
    return red


# ═══════════════════════════════════════════════════════════════════════════
# 1. SRŽ — PRAZNO I NEUSPEH SU RAZLIČITA STANJA
# ═══════════════════════════════════════════════════════════════════════════

def test_prazno_je_PRAZNO_a_ne_neuspeh():
    r = asyncio.run(R.rokovi_za_korisnika(_Supa(redovi=[]), UID))
    assert r.stanje is R.Stanje.PRAZNO
    assert r.uspeh is True
    assert r.rokovi == []


def test_pad_baze_je_NEUSPEH_a_ne_prazno():
    """NAJVAŽNIJI TEST U FAJLU.

    Ovo je tačno mesto na kom je trinaest pozivalaca radilo `return []`.
    """
    r = asyncio.run(R.rokovi_za_korisnika(_Supa(puca=True), UID))
    assert r.stanje is R.Stanje.NEUSPEH
    assert r.uspeh is False
    assert r.rokovi == [], "neuspeh ipak nosi listu — zato se lista ne sme čitati bez `uspeh`"


def test_prazna_lista_bez_provere_uspeha_ne_razlikuje_dva_stanja():
    """Dokaz da `uspeh` NIJE ukras: obe grane vraćaju istu listu."""
    a = asyncio.run(R.rokovi_za_korisnika(_Supa(redovi=[]), UID))
    b = asyncio.run(R.rokovi_za_korisnika(_Supa(puca=True), UID))
    assert a.rokovi == b.rokovi == []
    assert a.uspeh != b.uspeh


def test_neispravan_oblik_odgovora_nije_prazno():
    r = asyncio.run(R.rokovi_za_korisnika(_Supa(sirov_odgovor={"nije": "lista"}), UID))
    assert r.stanje is R.Stanje.NEISPRAVAN_PODATAK
    assert r.uspeh is False


def test_bez_korisnika_je_neispravan_subjekt():
    r = asyncio.run(R.rokovi_za_korisnika(_Supa(), ""))
    assert r.stanje is R.Stanje.NEISPRAVAN_SUBJEKT
    assert r.uspeh is False


def test_bez_predmeta_je_neispravan_subjekt():
    r = asyncio.run(R.rokovi_za_predmet(_Supa(), UID, ""))
    assert r.stanje is R.Stanje.NEISPRAVAN_SUBJEKT


def test_obrnut_prozor_je_neispravan_subjekt():
    r = asyncio.run(R.rokovi_za_korisnika(
        _Supa(), UID, od=DANAS, do=DANAS - timedelta(days=1)))
    assert r.stanje is R.Stanje.NEISPRAVAN_SUBJEKT


# ═══════════════════════════════════════════════════════════════════════════
# 2. ŠEMA — SLOJ SME DA TRAŽI SAMO ONO ŠTO POSTOJI
# ═══════════════════════════════════════════════════════════════════════════

def test_cita_iz_kanonske_tabele():
    supa = _Supa(redovi=[_red()])
    asyncio.run(R.rokovi_za_korisnika(supa, UID))
    assert supa.tabele == [R.TABELA] == ["predmet_hronologija"]


def test_nijedna_trazena_kolona_ne_izlazi_iz_izmerene_seme():
    """Brava nad izvorom kvara celog sprinta."""
    supa = _Supa(redovi=[_red()])
    asyncio.run(R.rokovi_za_korisnika(supa, UID))
    asyncio.run(R.rokovi_za_predmet(supa, UID, PRED))
    asyncio.run(R.rok_po_id(supa, UID, "h1"))
    visak = supa.trazene_kolone - SEMA_HRONOLOGIJA
    assert not visak, f"kanonski sloj traži nepostojeće kolone: {sorted(visak)}"


def test_ne_dodiruje_rocista_ni_zadatke():
    """Ročišta i zadaci su dokazano zaseban domen (šest mesta ih dohvata u
    istom `gather`-u i prikazuje odvojeno). Spajanje bi bilo dvostruko
    brojanje na ekranu koji sprečava propušten dan."""
    supa = _Supa(redovi=[_red()])
    asyncio.run(R.rokovi_za_korisnika(supa, UID))
    assert "rocista" not in supa.tabele
    assert "zadaci" not in supa.tabele


def test_ne_dodiruje_nepostojecu_tabelu_rokovi():
    supa = _Supa(redovi=[_red()])
    asyncio.run(R.rokovi_za_korisnika(supa, UID))
    assert "rokovi" not in supa.tabele


# ═══════════════════════════════════════════════════════════════════════════
# 3. IZOLACIJA — FILTER PO VLASNIKU JE JEDINA BRANA
# ═══════════════════════════════════════════════════════════════════════════

def test_tudji_rokovi_se_ne_vracaju():
    """Backend radi sa `service_role` ključem, pa je RLS zaobiđen; ovaj filter
    je jedina brana između kancelarija."""
    supa = _Supa(redovi=[_red(rid="moj"), _red(rid="tudji", user_id="drugi-advokat")])
    r = asyncio.run(R.rokovi_za_korisnika(supa, UID))
    assert [x.izvor_id for x in r.rokovi] == ["moj"]
    assert supa.filtri.get("user_id") == UID


def test_predmet_upit_zadrzava_i_filter_po_korisniku():
    supa = _Supa(redovi=[_red()])
    asyncio.run(R.rokovi_za_predmet(supa, UID, PRED))
    assert supa.filtri.get("user_id") == UID
    assert supa.filtri.get("predmet_id") == PRED


def test_rok_po_id_tudji_je_NEDOZVOLJENO_a_ne_prazno():
    supa = _Supa(redovi=[_red(rid="tudji", user_id="drugi-advokat")])
    r = asyncio.run(R.rok_po_id(supa, UID, "tudji"))
    assert r.stanje is R.Stanje.NEDOZVOLJENO
    assert r.rokovi == []


def test_rok_po_id_svoj_prolazi():
    supa = _Supa(redovi=[_red(rid="moj")])
    r = asyncio.run(R.rok_po_id(supa, UID, "moj"))
    assert r.stanje is R.Stanje.OK
    assert r.rokovi[0].izvor_id == "moj"


# ═══════════════════════════════════════════════════════════════════════════
# 4. NORMALIZACIJA
# ═══════════════════════════════════════════════════════════════════════════

def test_prozor_je_podrazumevano_sedam_dana():
    supa = _Supa(redovi=[_red(dana_od_danas=3), _red(dana_od_danas=30, rid="daleko")])
    r = asyncio.run(R.rokovi_za_korisnika(supa, UID))
    assert [x.izvor_id for x in r.rokovi] == ["h1"]


def test_prekoracen_i_dana_do_se_racunaju_ovde():
    """Trinaest pozivalaca je ovo računalo svaki za sebe."""
    supa = _Supa(redovi=[_red(dana_od_danas=-3, rid="prosli")],
                 )
    r = asyncio.run(R.rokovi_za_korisnika(
        supa, UID, od=DANAS - timedelta(days=10), do=DANAS))
    assert r.rokovi[0].prekoracen is True
    assert r.rokovi[0].dana_do == -3


def test_sortiranje_po_datumu_pa_po_vaznosti():
    supa = _Supa(redovi=[
        _red(dana_od_danas=2, vaznost="informativan", rid="b"),
        _red(dana_od_danas=1, vaznost="informativan", rid="a"),
        _red(dana_od_danas=2, vaznost="kritičan", rid="c"),
    ])
    r = asyncio.run(R.rokovi_za_korisnika(supa, UID))
    assert [x.izvor_id for x in r.rokovi] == ["a", "c", "b"]


def test_red_bez_datuma_se_preskace_a_ne_popravlja():
    """Red bez `datum_iso` nije rok. Ne sme se prikazati kao rok „danas"."""
    supa = _Supa(redovi=[_red(rid="dobar"), _red(rid="los", datum_iso=None)])
    r = asyncio.run(R.rokovi_za_korisnika(supa, UID))
    assert [x.izvor_id for x in r.rokovi] == ["dobar"]


def test_nepoznata_vaznost_se_ne_presl1kava_u_informativan():
    """Tiho snižavanje kritičnog roka bi bilo gore od nepoznate vrednosti."""
    supa = _Supa(redovi=[_red(vaznost="izmisljena")])
    r = asyncio.run(R.rokovi_za_korisnika(supa, UID))
    assert r.rokovi[0].vaznost == "izmisljena"


def test_limit_je_ogranicen_odozgo():
    supa = _Supa(redovi=[_red()])
    asyncio.run(R.rokovi_za_korisnika(supa, UID, limit=100000))
    assert supa.filtri["limit"] <= 200


# ═══════════════════════════════════════════════════════════════════════════
# 5. `zahtevaj` — NEUSPEH POSTAJE HTTP GREŠKA, PRAZNO PROLAZI
# ═══════════════════════════════════════════════════════════════════════════

def test_zahtevaj_prazno_prolazi():
    assert R.zahtevaj(asyncio.run(R.rokovi_za_korisnika(_Supa(redovi=[]), UID))) == []


def test_zahtevaj_neuspeh_dize_503():
    with pytest.raises(HTTPException) as e:
        R.zahtevaj(asyncio.run(R.rokovi_za_korisnika(_Supa(puca=True), UID)))
    assert e.value.status_code == 503
    assert "NE znači" in e.value.detail


def test_zahtevaj_nedozvoljeno_dize_404():
    supa = _Supa(redovi=[_red(rid="tudji", user_id="drugi")])
    with pytest.raises(HTTPException) as e:
        R.zahtevaj(asyncio.run(R.rok_po_id(supa, UID, "tudji")))
    assert e.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 6. POTROŠAČI — DEGRADIRANO STANJE MORA DA STIGNE DO KORISNIKA
# ═══════════════════════════════════════════════════════════════════════════
#
# Mutacija „`rokovi_dostupni = True` bez obzira na ishod" u `morning_briefing`
# je PREŽIVELA prvi krug — nijedan test nije merio šta brifing kaže kad rokovi
# nisu pročitani. Ovi testovi zatvaraju tu rupu.


def _brifing_supa_koji_puca():
    class _Puca:
        def table(self, ime):
            q = MagicMock()
            if ime == "predmet_hronologija":
                q.select.side_effect = RuntimeError("baza nedostupna")
            else:
                for lanac in (
                    q.select.return_value.eq.return_value,
                    q.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value,
                ):
                    lanac.execute.return_value = MagicMock(data=[])
                q.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                q.select.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.execute.return_value = MagicMock(data=[])
                q.select.return_value.eq.return_value.eq.return_value.gte.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                q.insert.return_value.execute.return_value = MagicMock(data=[{"id": "x"}])
            return q
    return _Puca()


def test_brifing_ne_tvrdi_miran_dan_kad_rokovi_nisu_procitani():
    """NAJVAŽNIJI POTROŠAČKI TEST.

    Jutarnji brifing je prvi ekran koji advokat vidi. Ako rokovi nisu
    pročitani, on NE sme reći „miran dan" — to je tačno lažno-zelena tvrdnja
    zbog koje ceo ovaj domen postoji.
    """
    import routers.morning_briefing as mb

    def _pao(client, **kwargs):
        raise RuntimeError("openai down")   # rezervni tekst umesto AI sinteze

    async def _log(*a, **k):
        return None

    with patch.object(mb, "_pozovi_briefing_sync_api", new=_pao), \
         patch("shared.audit_immutable.log_action", new=_log):
        brifing = asyncio.run(mb._generiši_briefing(UID, _brifing_supa_koji_puca()))

    assert brifing["rokovi_dostupni"] is False
    assert "miran dan" not in brifing["ai_briefing"].lower(), brifing["ai_briefing"][:200]
    assert "nisu dostupni" in brifing["ai_briefing"]


def test_brifing_sa_ispravnim_rokovima_ostaje_normalan():
    """Negativna kontrola: popravka ne sme da uvede trajno upozorenje."""
    import routers.morning_briefing as mb

    supa = _Supa(redovi=[])

    class _Prazan:
        def table(self, ime):
            if ime == "predmet_hronologija":
                return supa.table(ime)
            q = MagicMock()
            q.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            q.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            q.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            q.select.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.execute.return_value = MagicMock(data=[])
            q.select.return_value.eq.return_value.eq.return_value.gte.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            q.insert.return_value.execute.return_value = MagicMock(data=[{"id": "x"}])
            return q

    def _pao(client, **kwargs):
        raise RuntimeError("openai down")

    async def _log(*a, **k):
        return None

    with patch.object(mb, "_pozovi_briefing_sync_api", new=_pao), \
         patch("shared.audit_immutable.log_action", new=_log):
        brifing = asyncio.run(mb._generiši_briefing(UID, _Prazan()))

    assert brifing["rokovi_dostupni"] is True
    assert "nisu dostupni" not in brifing["ai_briefing"]


# ═══════════════════════════════════════════════════════════════════════════
# 7. PISCI — VREDNOSTI KOJE BAZA STVARNO PRIHVATA
# ═══════════════════════════════════════════════════════════════════════════

def test_normalizuj_vaznost_pokriva_sve_recnike_pisaca():
    """Četiri pisca kanonske tabele upisivala su `bitan`/`kljucan` — vrednosti
    koje CHECK odbija (`supabase_setup.sql:415`). Svaki takav upis je padao i
    bio progutan u `logger.warning`."""
    for ulaz in ("bitan", "kljucan", "normalan", "info", "ostalo", None, "izmisljeno"):
        assert R.normalizuj_vaznost(ulaz) in R.VAZNOST_DOZVOLJENE, ulaz


def test_normalizuj_vaznost_ne_snizava_kriticno():
    assert R.normalizuj_vaznost("kljucan") == "kritičan"
    assert R.normalizuj_vaznost("kritičan") == "kritičan"


def test_normalizuj_vaznost_cuva_visok_prioritet():
    assert R.normalizuj_vaznost("bitan") == "važan"
    assert R.normalizuj_vaznost("važan") == "važan"


def test_nijedan_pisac_ne_upisuje_nedozvoljenu_vaznost():
    """Brava nad izvorom: literal koji CHECK odbija ne sme se vratiti u kod."""
    import glob
    import io as _io
    import re as _re
    prekrsaji = []
    for f in glob.glob("routers/*.py") + glob.glob("services/**/*.py", recursive=True) + ["api.py"]:
        t = _io.open(f, encoding="utf-8", errors="replace").read()
        # Samo STVARNI upisi u kanonsku tabelu. Prompt sabloni koji nabrajaju
        # recnik (`"vaznost": "kritičan|važan|informativan"`) nisu upisi, a
        # `zakon_monitoring` pise u svoju tabelu sa svojim recnikom.
        for m in _re.finditer(
                r'table\(\s*"predmet_hronologija"\s*\)\s*\.insert\(\{(.{0,600}?)\}\)',
                t, _re.S):
            blok = m.group(1)
            for mv in _re.finditer(r'"vaznost":\s*"([^"|]+)"', blok):
                v = mv.group(1)
                if v not in R.VAZNOST_DOZVOLJENE:
                    prekrsaji.append(f"{f}: {v}")
    assert not prekrsaji, f"pisci upisuju vrednosti koje CHECK odbija: {prekrsaji}"
