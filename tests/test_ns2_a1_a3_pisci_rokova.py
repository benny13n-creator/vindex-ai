# -*- coding: utf-8 -*-
"""
Night Sprint II — A1 (budući pisci rokova) + A3 (Copilot relativni rok).

A1 — PROBLEM (dokazan): V2 Danas prepoznaje rok SAMO po `vrsta='rok'`
(migracija 129, `shared/rokovi.je_rok`). Tri eksplicitne putanje STVARANJA
roka upisivale su red bez `vrsta`, pa rok koji je advokat izričito tražio nije
bio rok ni za jedan pregled:

    routers/copilot.py::_handle_akcija_rok      ("Dodaj rok ...")
    routers/intake.py::intake_kreiraj           (polje `prvi_rok` čarobnjaka)
    api.py::predmet_confirm_links               (`dodaj_rok` sa confirm-card-a)

Ugovor koji ovi testovi zaključavaju:
    * red nosi `vrsta='rok'` preko POSTOJEĆEG fragmenta `shared.rokovi.oznake`
      (isti koji koriste case_dna / rokovi_lanac / case_pipeline / smart_intake);
    * `stanje` se NE upisuje — klik "Kreiraj predmet" / "Sačuvaj" / "Potvrdi
      veze" NIJE kanonska potvrda; rok ostaje UNCONFIRMED (audit lanac);
    * pre migracije 129 fragment je prazan i upis radi kao ranije;
    * redovi koji NISU izričito stvaranje roka (šablon) ostaju bez `vrsta`;
    * nijedan izlazni kanal (ACTION / EXPORT_EXTERNAL / CLIENT) ne dobija rok.

A3 — PROBLEM (dokazan): Copilot prompt je glasio „Relativne datume pretvori u
apsolutne." i model je mogao da upiše IZRAČUNAT pravni datum. Sada:
    * datum se upisuje SAMO ako je izričito (dan, mesec, godina) naveden u
      poruci advokata, kalendarski ispravan, jedini, i ako se model slaže;
    * relativan izraz, nepotpun / nepostojeći datum, više datuma ili datum
      modela koji nije u poruci -> istinito pojašnjenje, NULA upisa.
"""
import asyncio
import json
import os
import sys
import types

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-test-key")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from shared import rokovi  # noqa: E402

UID = "uid-ns2-a"
PRED = "pred-ns2-1"


@pytest.fixture(autouse=True)
def _danas_fiksiran(monkeypatch):
    """NS2-A3 runda 5 (F3): granice godine računaju se od `_rok_danas()`; testovi
    gramatike fiksiraju „danas" na 2026-10-14 da bi bili deterministični."""
    from datetime import date
    from routers import copilot as cp
    monkeypatch.setattr(cp, "_rok_danas", lambda: date(2026, 10, 14))


from routers import copilot as _cp_modul  # noqa: E402
_ROK_DANAS_ORIG = _cp_modul._rok_danas   # uhvaćen pri uvozu, pre autouse zamene


def _ROK_DANAS_PRAVI():
    return _ROK_DANAS_ORIG()


# ─── lažna baza ──────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, data):
        self.data = data


class _Supa:
    """Minimalni Supabase koji beleži svaki upis po tabeli.

    `sema_129`  — da li `select("vrsta, stanje")` prolazi (migracija primenjena).
    `vlasnik`   — da li predmet pripada pozivaocu (filter `user_id`).
    `insert_puca` / `prazan_insert` — pad upisa / upis bez vraćenog reda.
    """

    def __init__(self, *, sema_129=True, vlasnik=True, insert_puca=False, prazan_insert=False,
                 novi_predmet=None):
        self.upisi = {}
        self.sema_129 = sema_129
        self.vlasnik = vlasnik
        self.insert_puca = insert_puca
        self.prazan_insert = prazan_insert
        self.novi_predmet = novi_predmet or {"id": PRED, "user_id": UID, "naziv": "x"}
        self.filteri = []

    def table(self, ime):
        spolja = self

        class _Q:
            def __init__(self):
                self._red = None
                self._kolone = ""
                self._delete = False
                self._single = False

            def select(self, kolone="*", *a, **k):
                self._kolone = kolone
                if ime == "predmet_hronologija" and "vrsta" in kolone and not spolja.sema_129:
                    raise RuntimeError('column predmet_hronologija.vrsta does not exist (42703)')
                return self

            def eq(self, kol, val):
                spolja.filteri.append((ime, kol, val))
                return self

            def gte(self, *a, **k):
                return self

            def in_(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            def order(self, *a, **k):
                return self

            def single(self):
                return self

            def maybe_single(self):
                self._single = True
                return self

            def delete(self):
                self._delete = True
                return self

            def insert(self, red):
                if ime == "predmet_hronologija" and spolja.insert_puca:
                    raise RuntimeError("baza nedostupna")
                self._red = red
                if not (ime == "predmet_hronologija" and spolja.prazan_insert):
                    spolja.upisi.setdefault(ime, []).append(red)
                return self

            def execute(self):
                if self._red is not None:
                    if ime == "predmeti":
                        return _Res([spolja.novi_predmet])
                    if ime == "predmet_hronologija" and spolja.prazan_insert:
                        return _Res([])
                    redovi = self._red if isinstance(self._red, list) else [self._red]
                    return _Res([dict(r, id=f"h-{i}") for i, r in enumerate(redovi)])
                if ime == "predmeti":
                    if "id, naziv" in self._kolone or self._kolone == "id":
                        return _Res({"id": PRED} if spolja.vlasnik else None)
                    return _Res([])          # provera duplikata u čarobnjaku
                if ime == "klijenti":
                    return _Res({"id": "kl-1"} if self._single else [])
                return _Res([])

        return _Q()

    def hron(self):
        return self.upisi.get("predmet_hronologija", [])


def _gpt(payload):
    async def _f(oai, **kw):
        return types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content=json.dumps(payload)))])
    return _f


def _copilot(poruka, model_izlaz, supa, *, predmet_id=PRED, uid=UID):
    from routers import copilot as cp
    gpt_pozivi = []
    osnovni = _gpt(model_izlaz)

    async def _brojac(oai, **kw):
        gpt_pozivi.append(kw)
        return await osnovni(oai, **kw)

    async def _run():
        with patch.object(cp, "_get_supa", return_value=supa), \
             patch.object(cp, "_pozovi_gpt4o_mini", new=_brojac), \
             patch("openai.AsyncOpenAI"), \
             patch("shared.audit_immutable.log_action", new=AsyncMock()):
            return await cp._handle_akcija_rok(poruka, predmet_id, uid)

    return asyncio.run(_run()), gpt_pozivi


# ═════════════════════════════════════════════════════════════════════════════
# A1 — COPILOT: izričit rok postaje prepoznatljiv kandidat
# ═════════════════════════════════════════════════════════════════════════════

def test_A1_copilot_upisuje_vrstu_rok_bez_stanja():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za odgovor do 20.11.2026",
                    {"dogadjaj": "Odgovor na tužbu", "datum_iso": "2026-11-20", "vaznost": "kritičan"}, supa)
    assert r["uspeh"] is True, r
    assert len(supa.hron()) == 1
    red = supa.hron()[0]
    assert red["vrsta"] == rokovi.VRSTA_ROK
    assert "stanje" not in red, "klik na Copilot NIJE potvrda — stanje se ne izjavljuje"
    assert red["datum_iso"] == "2026-11-20" and red["datum"] == "2026-11-20"
    assert red["izvor"] == rokovi.IZVOR_AI_ASSISTED     # postojeća provenijencija nepromenjena
    assert red["user_id"] == UID and red["predmet_id"] == PRED
    assert rokovi.je_rok(red)
    assert rokovi.stanje_zapisa(dict(red, id="h-0"), {}) == rokovi.STANJE_KANDIDAT


def test_A1_copilot_pre_migracije_129_upis_radi_bez_vrste():
    supa = _Supa(sema_129=False)
    r, _ = _copilot("Dodaj rok za podnesak do 20.11.2026",
                    {"dogadjaj": "Podnesak", "datum_iso": "2026-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is True
    assert len(supa.hron()) == 1
    assert "vrsta" not in supa.hron()[0] and "stanje" not in supa.hron()[0]


# ═════════════════════════════════════════════════════════════════════════════
# A1 — INTAKE ČAROBNJAK: `prvi_rok`
# ═════════════════════════════════════════════════════════════════════════════

def _fake_request(path="/api/intake/kreiraj"):
    from starlette.requests import Request as _SReq
    return _SReq({"type": "http", "method": "POST", "headers": [], "query_string": b"",
                  "path": path, "client": ("1.2.3.4", 1), "app": MagicMock(), "state": MagicMock()})


def _intake(supa, **polja):
    from routers.intake import IntakeKreirajReq, intake_kreiraj
    req = IntakeKreirajReq(klijent_id="kl-1", naziv="Spor NS2", **polja)

    async def _run():
        with patch("routers.intake._get_supa", return_value=supa), \
             patch("shared.audit_immutable.log_action", new=AsyncMock()), \
             patch("services.case_pipeline.run_case_pipeline", new=AsyncMock()):
            return await intake_kreiraj(req, _fake_request(), {"user_id": UID, "email": "a@b.rs"})

    return asyncio.run(_run())


def test_A1_intake_prvi_rok_nosi_vrstu_rok_bez_stanja():
    supa = _Supa()
    r = _intake(supa, prvi_rok="2026-12-01", rok_opis="Rok za dopunu tužbe")
    assert r["rok_dodat"] is True
    assert len(supa.hron()) == 1
    red = supa.hron()[0]
    assert red["vrsta"] == rokovi.VRSTA_ROK
    assert "stanje" not in red
    assert red["datum_iso"] == "2026-12-01"
    assert red["izvor"] == rokovi.IZVOR_AI_ASSISTED
    assert red["user_id"] == UID


def test_A1_intake_bez_prvog_roka_nema_upisa():
    supa = _Supa()
    r = _intake(supa)
    assert r["rok_dodat"] is False
    assert supa.hron() == []


def test_A1_intake_pre_129_bez_vrste():
    supa = _Supa(sema_129=False)
    r = _intake(supa, prvi_rok="2026-12-01", rok_opis="Rok")
    assert r["rok_dodat"] is True
    assert "vrsta" not in supa.hron()[0]


def test_A1_intake_sablon_ostaje_bez_vrste():
    """Šablon NIJE izričito stvaranje roka (datum = danas + pomeraj iz kataloga):
    njegovi redovi ostaju neizjavljeni — samo prijavljeno, ne odlučeno."""
    from routers.intake import _TEMPLATES
    tpl = next(t for t in _TEMPLATES if t.get("hronologija_predlozi"))
    supa = _Supa()
    r = _intake(supa, template_id=tpl["id"])
    assert r["rok_dodat"] is False
    redovi = [x for grupa in supa.hron() for x in (grupa if isinstance(grupa, list) else [grupa])]
    assert redovi, "šablon nije upisao hronologiju — test ne meri ništa"
    assert all("vrsta" not in x and "stanje" not in x for x in redovi)


# ═════════════════════════════════════════════════════════════════════════════
# A1 — CONFIRM-LINKS: `dodaj_rok`
# ═════════════════════════════════════════════════════════════════════════════

def _confirm(supa, dodaj_rok, *, uid=UID):
    import api
    from starlette.requests import Request as _SReq
    req = api.ConfirmLinksReq(klijent_ids=[], uloga="stranka", dodaj_rok=dodaj_rok)
    request = _SReq({"type": "http", "method": "POST", "path": f"/api/predmeti/{PRED}/confirm-links",
                     "headers": [], "query_string": b"", "client": ("1.2.3.4", 1), "app": api.app,
                     "scheme": "http", "server": ("t", 80), "root_path": ""})

    async def _run():
        with patch.object(api, "_get_supa", return_value=supa), \
             patch.object(api, "_audit", new=lambda *a, **k: asyncio.sleep(0)):
            return await api.predmet_confirm_links(predmet_id=PRED, req=req, request=request,
                                                   user={"user_id": uid, "email": "a@b.rs"})

    return asyncio.run(_run())


def test_A1_confirm_links_rok_nosi_vrstu_bez_stanja():
    supa = _Supa()
    r = _confirm(supa, {"naziv": "Žalba", "datum_iso": "2026-11-05", "vaznost": "važan"})
    assert r["success"] is True and r["rok_dodat"] is True
    red = supa.hron()[0]
    assert red["vrsta"] == rokovi.VRSTA_ROK
    assert "stanje" not in red, "klik 'Potvrdi veze' NIJE kanonska potvrda roka"
    assert red["izvor"] == rokovi.IZVOR_AI_ASSISTED


def test_A1_confirm_links_bez_roka_nema_upisa():
    supa = _Supa()
    r = _confirm(supa, None)
    assert r["success"] is True and r["rok_dodat"] is False
    assert supa.hron() == []


def test_A1_confirm_links_pre_129_bez_vrste():
    supa = _Supa(sema_129=False)
    r = _confirm(supa, {"naziv": "Žalba", "datum_iso": "2026-11-05", "vaznost": "važan"})
    assert r["rok_dodat"] is True
    assert "vrsta" not in supa.hron()[0]


def test_A1_confirm_links_tudji_predmet_404_bez_upisa():
    from fastapi import HTTPException
    supa = _Supa(vlasnik=False)
    with pytest.raises(HTTPException) as e:
        _confirm(supa, {"naziv": "Žalba", "datum_iso": "2026-11-05", "vaznost": "važan"}, uid="uid-tudji")
    assert e.value.status_code == 404
    assert supa.hron() == []
    assert ("predmeti", "user_id", "uid-tudji") in supa.filteri


# ═════════════════════════════════════════════════════════════════════════════
# A1 — nijedan novi kandidat ne prolazi izlazne kanale (bez potvrde)
# ═════════════════════════════════════════════════════════════════════════════

def test_A1_novi_kandidati_ne_prolaze_akciju_izvoz_ni_klijenta():
    supa = _Supa()
    _copilot("Dodaj rok 20.11.2026", {"dogadjaj": "Rok", "datum_iso": "2026-11-20", "vaznost": "kritičan"}, supa)
    _intake(supa, prvi_rok="2026-12-01", rok_opis="Rok")
    _confirm(supa, {"naziv": "Žalba", "datum_iso": "2026-11-05", "vaznost": "kritičan"})
    redovi = [dict(r, id=f"h-{i}") for i, r in enumerate(supa.hron())]
    assert len(redovi) == 3 and all(rokovi.je_rok(r) for r in redovi)
    for r in redovi:
        for potrosac in (rokovi.POTROSAC_AKCIJA, rokovi.POTROSAC_IZVOZ_SPOLJA, rokovi.POTROSAC_KLIJENT):
            assert rokovi.sme_pristupiti(r, {}, potrosac=potrosac) is False, (potrosac, r)
        assert rokovi.sme_pristupiti(r, {}, potrosac=rokovi.POTROSAC_INTERNI) is True
        assert rokovi.sme_pokrenuti_obavezu(r, set()) is False
    assert rokovi.filtriraj_izvrsive(redovi, set()) == []


# ═════════════════════════════════════════════════════════════════════════════
# A3 — COPILOT: nula tiho izračunatih pravnih datuma
# ═════════════════════════════════════════════════════════════════════════════

def test_A3_prompt_ne_trazi_pretvaranje_relativnih_datuma():
    import inspect
    from routers import copilot as cp
    telo = inspect.getsource(cp._handle_akcija_rok)
    assert "pretvori u apsolutne" not in telo
    assert "Danas je" not in telo, "datum 'danas' u promptu poziva model da računa rok"


def test_A3_izricit_iso_datum_se_upisuje():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za podnesak do 2026-11-20",
                    {"dogadjaj": "Podnesak", "datum_iso": "2026-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is True and r["datum"] == "2026-11-20"
    assert supa.hron()[0]["datum_iso"] == "2026-11-20"
    assert "nije potvrđen" in r["odgovor"]


def test_A3_izricit_tekstualni_datum_se_upisuje():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za pripremu do 1. septembra 2027",
                    {"dogadjaj": "Priprema", "datum_iso": "2027-09-01", "vaznost": "važan"}, supa)
    assert r["uspeh"] is True
    assert supa.hron()[0]["datum_iso"] == "2027-09-01"


@pytest.mark.parametrize("poruka", ["Dodaj rok 31.02.2026 za podnesak",
                                     "Dodaj rok 2026-02-31 za podnesak",
                                     "Dodaj rok 31. februara 2026"])
def test_A3_nepostojeci_kalendarski_datum_nema_upisa(poruka):
    supa = _Supa()
    r, gpt = _copilot(poruka, {"dogadjaj": "Podnesak", "datum_iso": "2026-03-03", "vaznost": "važan"}, supa)
    assert r["uspeh"] is False and r["razlog"] == "nevalidan_datum"
    assert r["potrebno_pojasnjenje"] is True
    assert supa.hron() == []
    assert gpt == [], "deterministička provera mora da odluči pre modela"


@pytest.mark.parametrize("poruka", [
    "Dodaj rok za odgovor za sedam dana",
    "Dodaj rok: dostaviti dokaze u roku od mesec dana",
    "Dodaj rok za žalbu, 15 dana od dostave presude",
    "Dodaj rok za žalbu od dana dostave",
    "Dodaj rok za podnesak sutra",
])
def test_A3_relativan_rok_bez_okidaca_nema_datuma(poruka):
    supa = _Supa()
    # Model se ponaša kao stari prompt: izračuna datum (danas + N).
    r, gpt = _copilot(poruka, {"dogadjaj": "Rok", "datum_iso": "2026-10-21", "vaznost": "kritičan"}, supa)
    assert r["uspeh"] is False and r["razlog"] == "relativni_rok", r
    assert supa.hron() == []
    assert gpt == []
    assert "ne računa" in r["odgovor"]


def test_A3_rok_zalbe_zavisan_od_dostave_sa_datumom_dostave_nema_upisa():
    """Jedini datum u poruci je datum DOSTAVE (okidač), ne datum isteka. Model koji
    vrati baš taj datum ne sme da ga upiše kao rok, a izračunat datum još manje."""
    poruka = "Dodaj rok za žalbu, presuda dostavljena 01.10.2026, rok 15 dana od dostave"
    for model_datum in ("2026-10-01", "2026-10-16"):
        supa = _Supa()
        r, _ = _copilot(poruka, {"dogadjaj": "Žalba", "datum_iso": model_datum, "vaznost": "kritičan"}, supa)
        assert r["uspeh"] is False and r["razlog"] == "relativni_rok"
        assert supa.hron() == []


def test_A3_vise_datuma_nema_upisa():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za podnesak 10.11.2026, 20.11.2026",
                    {"dogadjaj": "Podnesak", "datum_iso": "2026-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is False and r["razlog"] == "vise_datuma"
    assert supa.hron() == []


def test_A3_isti_datum_dva_zapisa_nije_konflikt():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok 20.11.2026 (2026-11-20) za podnesak",
                    {"dogadjaj": "Podnesak", "datum_iso": "2026-11-20", "vaznost": "važan"}, supa)
    # runda 4: nije konflikt datuma (razlog nije „vise_datuma"), ali oblik nije u gramatici
    assert r["uspeh"] is False and r["razlog"] == "oblik_roka" and supa.hron() == []


def test_A3_nepotpun_datum_bez_godine_nema_upisa():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za pripremu do 1. septembra",
                    {"dogadjaj": "Priprema", "datum_iso": "2026-09-01", "vaznost": "važan"}, supa)
    assert r["uspeh"] is False and r["razlog"] == "nepotpun_datum"
    assert supa.hron() == []
    supa = _Supa()
    r, _ = _copilot("Dodaj rok 20.11. za podnesak",
                    {"dogadjaj": "Podnesak", "datum_iso": "2026-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is False and r["razlog"] == "nepotpun_datum"
    assert supa.hron() == []


def test_A3_bez_datuma_nema_upisa():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za pripremu podneska",
                    {"dogadjaj": "Priprema", "datum_iso": None, "vaznost": "važan"}, supa)
    assert r["uspeh"] is False and r["razlog"] == "bez_datuma"
    assert supa.hron() == []


@pytest.mark.parametrize("model_datum", ["2026-11-21", "2027-11-20", "21.11.2026", "nije-datum", None])
def test_A3_falsifikovan_izlaz_modela_ne_stvara_datum(model_datum):
    """Poruka ima tačno jedan izričit datum; model vraća drugi (ili ništa).
    Server ne veruje modelu: nema upisa."""
    supa = _Supa()
    r, gpt = _copilot("Dodaj rok za podnesak do 20.11.2026",
                      {"dogadjaj": "Podnesak", "datum_iso": model_datum, "vaznost": "važan"}, supa)
    assert len(gpt) == 1
    assert r["uspeh"] is False and r["razlog"] == "datum_nije_u_poruci", r
    assert supa.hron() == []


def test_A3_model_u_drugom_formatu_isti_datum_prolazi():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za podnesak do 20.11.2026",
                    {"dogadjaj": "Podnesak", "datum_iso": "20.11.2026", "vaznost": "važan"}, supa)
    assert r["uspeh"] is True
    assert supa.hron()[0]["datum_iso"] == "2026-11-20", "upisuje se kanonski ISO iz poruke"


def test_A3_neovlascen_predmet_nema_upisa():
    supa = _Supa(vlasnik=False)
    r, _ = _copilot("Dodaj rok 20.11.2026", {"dogadjaj": "Rok", "datum_iso": "2026-11-20", "vaznost": "važan"},
                    supa, predmet_id="pred-tudji", uid="uid-napadac")
    assert r["uspeh"] is False and r["odgovor"] == "Predmet nije pronađen."
    assert supa.hron() == []
    assert ("predmeti", "user_id", "uid-napadac") in supa.filteri
    assert ("predmeti", "id", "pred-tudji") in supa.filteri


def test_A3_pad_upisa_nije_uspeh():
    supa = _Supa(insert_puca=True)
    r, _ = _copilot("Dodaj rok 20.11.2026", {"dogadjaj": "Rok", "datum_iso": "2026-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is False
    assert "dodat" not in r["odgovor"].lower()


def test_A3_upis_bez_vracenog_reda_nije_uspeh():
    supa = _Supa(prazan_insert=True)
    r, _ = _copilot("Dodaj rok 20.11.2026", {"dogadjaj": "Rok", "datum_iso": "2026-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is False
    assert "dodat" not in r["odgovor"].lower()


def test_A3_ponovljen_zahtev_dokumentovano_ponasanje():
    """IDEMPOTENTNOST — DOKUMENTOVANO, NE MENJANO: Copilot nema deduplikaciju;
    isti zahtev dva puta pravi DVA nepotvrđena kandidata (svaki traži sopstvenu
    odluku advokata). Nijedan ne postaje potvrđen ni izvršiv. Promena ovog
    ponašanja bila bi novo proizvodno ponašanje (van opsega A3)."""
    supa = _Supa()
    izlaz = {"dogadjaj": "Podnesak", "datum_iso": "2026-11-20", "vaznost": "važan"}
    r1, _ = _copilot("Dodaj rok za podnesak do 20.11.2026", izlaz, supa)
    r2, _ = _copilot("Dodaj rok za podnesak do 20.11.2026", izlaz, supa)
    assert r1["uspeh"] is True and r2["uspeh"] is True
    assert len(supa.hron()) == 2
    assert all("stanje" not in x for x in supa.hron())


# ─── čista funkcija odluke ───────────────────────────────────────────────────

@pytest.mark.parametrize("poruka,model,ocekivano", [
    ("rok 20.11.2026", "2026-11-20", ("2026-11-20", None)),
    ("rok 1.8.2026", "2026-08-01", ("2026-08-01", None)),
    ("rok 15. maja 2027", "2027-05-15", ("2027-05-15", None)),
    ("rok petnaestog maja 2027", "2027-05-15", ("2027-05-15", None)),
    ("rok 29.02.2027", "2027-03-01", (None, "nevalidan_datum")),
    ("rok 29.02.2028", "2028-02-29", ("2028-02-29", None)),
    ("rok za 7 dana", "2026-10-21", (None, "relativni_rok")),
    ("рок за седам дана", "2026-10-21", (None, "relativni_rok")),
    ("rok", None, (None, "bez_datuma")),
])
def test_A3_odluka_o_datumu(poruka, model, ocekivano):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka, model) == ocekivano


# ═════════════════════════════════════════════════════════════════════════════
# A3 — NEZAVISNI PREGLED ec812793 (F1/F2/F3 + rupa u mutacijama)
#
# F1 (HIGH): izričit datum koji je OKIDAČ/SIDRO (datum presude, dostave, ročišta,
# broj predmeta) bio je upisan kao rok — „osam dana pre ročišta 20.11.2026" je
# postajalo rok 20.11.2026, tj. 8 dana KASNO. Sada: svaka količina trajanja
# -> relativni_rok; datum vezan za događaj/dokument -> datum_je_dogadjaj.
# Probni skup recenzenta (44 ulaza) je ovde preuzet doslovno.
# ═════════════════════════════════════════════════════════════════════════════

PREGLED_PROBA = [
    ("Dodaj rok: rok je 20.11.2026 ili 8 dana od prijema", (None, "relativni_rok")),
    ("Dodaj rok za odgovor do 20.11.2026", ("2026-11-20", None)),
    ("Dodaj rok: najkasnije osam dana pre ročišta 20.11.2026", (None, "relativni_rok")),
    ("Dodaj rok: najkasnije 8 dana pre ročišta 20.11.2026", (None, "relativni_rok")),
    ("Dodaj rok 15 dana, ročište 20.11.2026", (None, "relativni_rok")),
    ("Dodaj rok: rok 15 dana, ročište 20.11.2026", (None, "relativni_rok")),
    ("Додај рок: петнаестог маја 2027", (None, "nepodrzan_format")),
    ("Додај рок за жалбу 20.11.2026", (None, "oblik_roka")),  # runda 4: svrha bez oznake
    ("Додај рок: осам дана пре рочишта 20.11.2026", (None, "relativni_rok")),
    ("Dodaj rok: petnaestog maja 2027", ("2027-05-15", None)),
    ("Dodaj rok 20.11.", (None, "nepotpun_datum")),
    ("Dodaj rok 20/11/2026", (None, "nepodrzan_format")),
    ("Dodaj rok 2026-11-20T10:00", (None, "oblik_roka")),  # runda 4: vreme nije u gramatici
    ("Dodaj rok 20.11.2026.", ("2026-11-20", None)),
    ("Dodaj rok ٢٠.11.2026", (None, "nepodrzan_format")),
    ("Dodaj rok u predmetu P 20.11/2026", (None, "nepodrzan_format")),
    ("Dodaj rok po broju 12.03.2025", (None, "datum_je_dogadjaj")),
    ("Dodaj rok za žalbu na presudu od 12.03.2025", (None, "datum_je_dogadjaj")),
    ("Dodaj rok za žalbu na presudu donetu 12.03.2025", (None, "datum_je_dogadjaj")),
    ("Dodaj rok za žalbu, presuda dostavljena 12.03.2025", (None, "datum_je_dogadjaj")),
    ("Dodaj rok za žalbu, presuda primljena 12.03.2025", (None, "datum_je_dogadjaj")),
    ("Dodaj rok: 15 dana od 12.03.2025", (None, "relativni_rok")),
    ("Dodaj rok: petnaest dana od 12.03.2025", (None, "relativni_rok")),
    ("Dodaj rok: 15 dana računajući od 12.03.2025", (None, "relativni_rok")),
    ("Dodaj rok: rok ističe 15 dana posle 12.03.2025", (None, "relativni_rok")),
    ("Dodaj rok: tri nedelje posle ročišta 12.03.2025", (None, "relativni_rok")),
    ("Dodaj rok: 8 dana pre 20.11.2026", (None, "relativni_rok")),
    ("Dodaj rok: dan pre ročišta 20.11.2026", (None, "datum_je_dogadjaj")),
    ("Dodaj rok: prekosutra", (None, "relativni_rok")),
    ("Dodaj rok: idućeg ponedeljka", (None, "relativni_rok")),
    ("Dodaj rok: krajem meseca", (None, "relativni_rok")),
    ("Dodaj rok: do kraja godine 2026", (None, "relativni_rok")),
    ("Dodaj rok: 31.12.2026 ili ranije ako sud odluči", (None, "uslovni_rok")),
    ("Dodaj rok: 20. novembar 2026", ("2026-11-20", None)),
    ("Dodaj rok: 20. novembra 2026. godine", ("2026-11-20", None)),
    ("Dodaj rok 20 . 11 . 2026", ("2026-11-20", None)),
    ("Dodaj rok 2026/11/20", (None, "nepodrzan_format")),
    ("Dodaj rok 20-11-2026", (None, "nepodrzan_format")),
    ("Dodaj rok: 30.02.2027", (None, "nevalidan_datum")),
    ("Dodaj rok: 20.11.26", (None, "nepotpun_datum")),
    ("Dodaj rok: dva dana pred ročište 20.11.2026", (None, "relativni_rok")),
    ("Dodaj rok za dopunu 8 dana nakon ročišta 20.11.2026", (None, "relativni_rok")),
    ("Dodaj rok: u roku od 15 dana, ročište 20.11.2026", (None, "relativni_rok")),
    ("Dodaj rok: petnaestodnevni rok od 12.03.2025", (None, "relativni_rok")),
]


def test_A3P_proba_ima_44_ulaza():
    assert len(PREGLED_PROBA) == 44


@pytest.mark.parametrize("poruka,ocekivano", PREGLED_PROBA)
def test_A3P_probni_skup_recenzenta(poruka, ocekivano):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == ocekivano


# Šta OSTAJE prihvaćeno, i zašto (runda 3 — dozvoljena lista): jedini datum,
# bez trajanja, NEPOSREDNO uveden oznakom isteka („do", „ističe", „rok <datum>",
# „rok za <svrha> <datum>"). Vidi `_rok_izricit_istek` u routers/copilot.py.
PRIHVACENO = [
    ("Dodaj rok: rok ističe 20.11.2026", "2026-11-20"),
    ("Dodaj rok do 20.11.2026", "2026-11-20"),
    ("Dodaj rok za podnesak do 20.11.2026", "2026-11-20"),
    ("Dodaj rok za podnesak do 20. 11. 2026", "2026-11-20"),
    # runda 4: ranije prihvaćeni „rok 20.11.2026 za dopunu tužbe", „rok za podnesak
    # 20.11.2026", „rok za odgovor na tužbu do ..." su PITANJE — vidi BIVSI_UPISI.
]


@pytest.mark.parametrize("poruka,iso", PRIHVACENO)
def test_A3P_izricit_rok_ostaje_prihvacen(poruka, iso):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == (iso, None)
    assert _odluka_o_datumu_roka(poruka, iso) == (iso, None)
    supa = _Supa()
    r, _ = _copilot(poruka, {"dogadjaj": "Rok", "datum_iso": iso, "vaznost": "važan"}, supa)
    assert r["uspeh"] is True and supa.hron()[0]["datum_iso"] == iso


# Recenzentov e2e skup — tamo je „prolaz" značio LAŽAN UPIS. Ovde mora biti nula upisa.
PREGLED_E2E = [
    ("Dodaj rok za žalbu na presudu od 12.03.2025", "2025-03-12"),
    ("Dodaj rok za žalbu, presuda dostavljena 01.10.2026", "2026-10-01"),
    ("Dodaj rok: petnaest dana od 01.10.2026", "2026-10-01"),
    ("Dodaj rok: najkasnije osam dana pre ročišta 20.11.2026", "2026-11-20"),
    ("Dodaj rok: 15 dana računajući od 01.10.2026", "2026-10-01"),
    ("Dodaj rok: 8 dana pre 20.11.2026", "2026-11-20"),
    ("Dodaj rok: dva dana pred ročište 20.11.2026", "2026-11-20"),
    ("Додај рок: осам дана пре рочишта 20.11.2026", "2026-11-20"),
    ("Dodaj rok: rok 15 dana, ročište 20.11.2026", "2026-11-20"),
    ("Dodaj rok po broju 12.03.2025", "2025-03-12"),
]


@pytest.mark.parametrize("poruka,datum", PREGLED_E2E)
def test_A3P_okidac_nikad_nije_upisan_kao_rok(poruka, datum):
    supa = _Supa()
    r, gpt = _copilot(poruka, {"dogadjaj": "Žalba", "datum_iso": datum, "vaznost": "kritičan"}, supa)
    assert r["uspeh"] is False and r["potrebno_pojasnjenje"] is True, r
    assert r["razlog"] in ("relativni_rok", "datum_je_dogadjaj")
    assert supa.hron() == []
    assert gpt == [], "odluka je deterministička, pre modela"


def test_A3P_poruka_datum_je_dogadjaj_je_jasna():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za žalbu na presudu od 12.03.2025",
                    {"dogadjaj": "Žalba", "datum_iso": "2025-03-12", "vaznost": "kritičan"}, supa)
    assert r["razlog"] == "datum_je_dogadjaj"
    assert "datum događaja ili dokumenta" in r["odgovor"] and "ne kao datum isteka roka" in r["odgovor"]
    assert "„rok za žalbu ističe 20.11.2026“" in r["odgovor"] and "„rok za podnesak do 20.11.2026“" in r["odgovor"]
    assert "Rok nije sačuvan" in r["odgovor"]


def test_A3P_forsirana_polja_modela_se_ignorisu():
    """Recenzentova proba: model vraća `vrsta`/`stanje`/`izvor`/tuđi id — upis ih ne preuzima."""
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za odgovor do 20.11.2026",
                    {"dogadjaj": "X", "datum_iso": "2026-11-20", "vaznost": "kritičan",
                     "vrsta": "dogadjaj", "stanje": rokovi.STANJE_POTVRDJEN, "izvor": "manual",
                     "predmet_id": "tudji", "user_id": "tudji", "akter": "Advokat"}, supa)
    assert r["uspeh"] is True
    red = supa.hron()[0]
    assert red["predmet_id"] == PRED and red["user_id"] == UID
    assert "stanje" not in red and red["izvor"] == rokovi.IZVOR_AI_ASSISTED and red["akter"] == "Copilot (AI)"
    assert red["vrsta"] == rokovi.VRSTA_ROK


# F3 — datum u prošlosti se ne blokira, ali se ne prećutkuje.
def test_A3P_datum_u_proslosti_je_naglasen():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok 01.01.2026", {"dogadjaj": "X", "datum_iso": "2026-01-01", "vaznost": "važan"}, supa)
    assert r["uspeh"] is True
    assert "u prošlosti" in r["odgovor"]
    assert "stanje" not in supa.hron()[0]


def test_A3P_buduci_datum_bez_upozorenja():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok 20.11.2030", {"dogadjaj": "X", "datum_iso": "2030-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is True and "u prošlosti" not in r["odgovor"]


# Rupa u mutacijama (recenzent): drugi, nezavisni detektor relativnog roka —
# postojeći parser rokova — mora sam da drži liniju kad regularni izrazi ne vide izraz.
def test_A3P_parser_rokova_je_nezavisna_odbrana(monkeypatch):
    import re as _re
    from routers import copilot as cp
    nikad = _re.compile(r"(?!x)x")
    monkeypatch.setattr(cp, "_ROK_TRAJANJE_RE", nikad)
    monkeypatch.setattr(cp, "_ROK_RELATIVNI_RE", nikad)
    assert cp._odluka_o_datumu_roka("Dodaj rok: u roku od 15 dana, do 20.11.2026")[1] == "relativni_rok"


def test_A3P_regex_trajanja_je_nezavisna_odbrana(monkeypatch):
    from routers import copilot as cp
    monkeypatch.setattr(cp, "_rok_relativni_parser", lambda tekst: False)
    assert cp._odluka_o_datumu_roka("Dodaj rok: petnaest dana, do 20.11.2026")[1] == "relativni_rok"


@pytest.mark.parametrize("poruka,razlog", [
    # sidro POSLE datuma (imenica događaja iza datuma)
    ("Dodaj rok 12.03.2025 (presuda)", "datum_je_dogadjaj"),
    ("Dodaj rok 20.11.2026 ročište", "datum_je_dogadjaj"),
    # sidro ima prednost nad „više datuma": tačniji razlog advokatu
    ("Dodaj rok 20.11.2026, presuda od 12.03.2025", "datum_je_dogadjaj"),
    # ćirilično trajanje BEZ sidra — samo detektor ćiriličnih brojeva ga hvata
    ("Додај рок: осам дана, до 20.11.2026", "relativni_rok"),
    ("Dodaj rok: tromesečni, do 20.11.2026", "relativni_rok"),
])
def test_A3P_sidro_i_trajanje_dodatno(poruka, razlog):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == (None, razlog)


# ═════════════════════════════════════════════════════════════════════════════
# A3 — RUNDA 3 (pregled d276e739: NO-GO). Pravilo je OBRNUTO: upis samo kad je
# jedini datum NEPOSREDNO uveden oznakom isteka (dozvoljena lista,
# `_rok_izricit_istek`); sve ostalo je pitanje. Recenzentove tabele (runda 2)
# su ovde doslovno, sa očekivanim ishodom.
# ═════════════════════════════════════════════════════════════════════════════

DOG = (None, "datum_je_dogadjaj")
REL = (None, "relativni_rok")
S20 = ("2026-11-20", None)
OBL = (None, "oblik_roka")

# HIGH (PROVEN u rundi 2): datum događaja je bio upisan kao rok. Sada: nikad.
RUNDA2_HIGH = [
    ("Dodaj rok za žalbu, primili smo je 01.10.2026", "2026-10-01"),
    ("Dodaj rok za žalbu, zaprimljeno 01.10.2026", "2026-10-01"),
    ("Dodaj rok za žalbu na odluku iz 12.03.2025", "2025-03-12"),
    ("Додај рок за жалбу на одлуку из 12.03.2025", "2025-03-12"),
    ("Dodaj rok za žalbu, glavna rasprava održana 12.03.2025", "2025-03-12"),
    ("Додај рок, расправа одржана 12.03.2025", "2025-03-12"),
    ("Dodaj rok, pretres zakazan za 20.11.2026", "2026-11-20"),
    ("Dodaj rok: saslušanje 20.11.2026", "2026-11-20"),
    ("Dodaj rok: tužba je predata 12.03.2025", "2025-03-12"),
    ("Dodaj rok za žalbu, stiglo nam 01.10.2026", "2026-10-01"),
    ("Dodaj rok za žalbu na presudu Višeg suda u Beogradu u parnici tužioca protiv tuženog, datum 12.03.2025",
     "2025-03-12"),
    ("Dodaj rok 12.03.2025 — to je dan kada je stigla presuda", "2025-03-12"),
]


def test_A3R3_high_ima_12_ulaza():
    assert len(RUNDA2_HIGH) == 12


@pytest.mark.parametrize("poruka,datum", RUNDA2_HIGH)
def test_A3R3_high_datum_dogadjaja_nikad_nije_rok(poruka, datum):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == DOG
    assert _odluka_o_datumu_roka(poruka, datum) == DOG
    supa = _Supa()
    r, gpt = _copilot(poruka, {"dogadjaj": "Žalba", "datum_iso": datum, "vaznost": "kritičan"}, supa)
    assert r["uspeh"] is False and r["potrebno_pojasnjenje"] is True and r["razlog"] == "datum_je_dogadjaj", r
    assert supa.hron() == [] and gpt == []


# Ceo probni skup recenzenta iz runde 2 (40 ulaza), sa očekivanim ishodom.
RUNDA2_PROBA = [
    ("Dodaj rok za žalbu, primili smo je 01.10.2026", DOG),
    ("Dodaj rok za žalbu, zaprimljeno 01.10.2026", DOG),
    ("Dodaj rok za žalbu na odluku iz 12.03.2025", DOG),
    ("Dodaj rok za žalbu, glavna rasprava održana 12.03.2025", DOG),
    ("Dodaj rok, pretres zakazan za 20.11.2026", DOG),
    ("Dodaj rok: tužba je predata 12.03.2025", DOG),
    ("Dodaj rok za žalbu, stiglo nam 01.10.2026", DOG),
    ("Dodaj rok za žalbu na presudu Višeg suda u Beogradu u parnici tužioca protiv tuženog, datum 12.03.2025", DOG),
    ("Dodaj rok 12.03.2025 — to je dan kada je stigla presuda", DOG),
    ("Додај рок за жалбу на одлуку из 12.03.2025", DOG),
    ("Додај рок, расправа одржана 12.03.2025", DOG),
    ("Dodaj rok za žalbu, presuda je od dvanaestog marta 2025", DOG),
    ("Dodaj rok za žalbu, presuda je doneta 12. marta 2025.", DOG),
    ("Dodaj rok: saslušanje 20.11.2026", DOG),
    # MEDIUM: trajanje (približno, „mesec i po", sati) -> relativni_rok
    ("Dodaj rok: dvadesetak dana, do 20.11.2026", REL),
    ("Dodaj rok: desetak dana od 12.03.2025", REL),
    ("Dodaj rok: mesec i po, do 20.11.2026", REL),
    ("Dodaj rok: 48 sati, do 20.11.2026", REL),
    ("Dodaj rok: osmog dana od 12.03.2025", REL),
    ("Dodaj rok: u roku od 15 dana do 20.11.2026", REL),
    ("Dodaj rok: dvadeset i jedan dan, do 20.11.2026", REL),
    ("Додај рок: двадесетак дана, до 20.11.2026", REL),
    ("Додај рок: у року од петнаест дана од 12.03.2025", REL),
    # dva datuma / broj predmeta / prošlost
    ("Dodaj rok do 20.11.2026 a ročište je 25.11.2026", DOG),
    ("Dodaj rok do 20.11.2026, predmet P 1234/2026", DOG),  # runda 4
    ("Dodaj rok do 20.11.2026, br. predmeta 12.03.2025", DOG),
    ("Dodaj rok 01.01.2025", (None, "datum_van_opsega")),  # runda 5 F3: > 1 godine u prošlosti
    ("DODAJ ROK ZA ZALBU NA PRESUDU OD 12.03.2025", DOG),
    # izričit istek — upis (uklj. LOW over-clarification iz runde 2 koji su sada upis)
    ("Dodaj rok: najkasnije do 20.11.2026", S20),
    ("Dodaj rok za odgovor na žalbu do 20.11.2026", S20),
    ("Dodaj rok za dostavu dokaza do 20.11.2026", S20),  # runda 5 F2: „dostavu" kao prva reč svrhe
    ("Dodaj rok za žalbu na rešenje do 20.11.2026", S20),  # runda 5 F2: „rešenje" odmah posle „na"
    # ostaje PITANJE: slaba oznaka „rok <datum>" + imenica dokumenta (presuda) u poruci
    ("Dodaj rok 20.11.2026 za žalbu na presudu", OBL),
    ("Dodaj rok: poslednji dan roka je 20.11.2026", S20),
    ("Dodaj rok do petka 20.11.2026", S20),
    ("Dodaj rok za pripremu za ročište do 20.11.2026", DOG),  # runda 4: „ročišt" u svrsi
    ("Dodaj rok za uplatu sudske takse do 20.11.2026", S20),
    ("Додај рок до 20.11.2026", S20),
    ("Dodaj rok: rok za izjašnjenje ističe 20. novembra 2026.", S20),
    ("Dodaj rok za podnošenje predloga do 20.11.2026 godine", S20),
]


def test_A3R3_proba_runde2_ima_40_ulaza():
    assert len(RUNDA2_PROBA) == 40


@pytest.mark.parametrize("poruka,ocekivano", RUNDA2_PROBA)
def test_A3R3_probni_skup_runde2(poruka, ocekivano):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == ocekivano


# Sopstveni protivnički ulazi (latinica + ćirilica).
SOPSTVENI = [
    # jaka oznaka, ali klauza POSLE datuma ga objašnjava kao događaj
    ("Dodaj rok do 20.11.2026 (ročište)", DOG),
    ("Dodaj rok do 20.11.2026 — to je dan kada je ročište", DOG),
    ("Додај рок: 20.11.2026 — то је дан када је стигла пресуда", DOG),
    ("Додај рок 20.11.2026 (саслушање)", DOG),
    # glagol događaja bilo gde -> pitanje čak i uz jaku oznaku (namerno konzervativno)
    ("Presuda je doneta, rok ističe 20.11.2026", DOG),
    # slaba oznaka: posle datuma sme samo „za <svrha>" — nepoznata reč događaja u zagradi = pitaj
    ("Dodaj rok 12.03.2025 (izveštaj veštaka)", OBL),
    ("Додај рок 12.03.2025 (извештај вештака)", OBL),
    ("Dodaj rok 20.11.2026, predmet P 1234/2026", DOG),
    # svrha sa „na <predmet>" neposredno ispred datuma (imenica nije na listi) = pitaj
    ("Dodaj rok za žalbu na nalog 12.03.2025", OBL),
    ("Додај рок за жалбу на налог 12.03.2025", OBL),
    # glagol događaja poništava i jaku oznaku
    ("Dodaj rok, sastanak zakazan do 20.11.2026", DOG),
    # objašnjenje datuma kao događaja posle zareza (jaka oznaka ne pomaže)
    ("Dodaj rok do 20.11.2026, kada je i sednica veća", DOG),
    ("Додај рок до 20.11.2026, када је и седница већа", DOG),
    # predlog računanja ili imenica događaja neposredno ispred datuma
    ("Dodaj rok pre 20.11.2026", DOG),
    ("Dodaj rok, ročište 20.11.2026", DOG),
    ("Dodaj rok za ročište 20.11.2026", DOG),
    ("Dodaj rok za odgovor na tužbu 20.11.2026", DOG),
    ("Dodaj rok za žalbu 20.11.2026, presuda u prilogu", DOG),
    ("20.11.2026", OBL),
    ("Додај рок, претрес заказан за 20.11.2026", DOG),
    ("Додај рок за жалбу, примили смо је 01.10.2026", DOG),
    # više datuma: „pre" ispred drugog datuma -> događaj (ubija mutant M10)
    ("Dodaj rok do 20.11.2026, pre 25.11.2026", DOG),
    ("Dodaj rok do 20.11.2026, 25.11.2026", (None, "vise_datuma")),
    ("Dodaj rok za žalbu, odluka iz 12.03.2025, rok ističe 20.11.2026", DOG),
    # dan u nedelji: mora da se slaže sa datumom (20.11.2026 je petak)
    ("Dodaj rok do petka 21.11.2026", REL),
    ("Додај рок до петка 20.11.2026", S20),
    ("Dodaj rok do subote 21.11.2026", ("2026-11-21", None)),
    # trajanja — približna, razlomljena, sati/časovi, „nedelju/godinu dana"
    ("Додај рок: десетак дана, до 20.11.2026", REL),
    ("Додај рок: месец и по, до 20.11.2026", REL),
    ("Додај рок: 48 сати, до 20.11.2026", REL),
    ("Dodaj rok: pola meseca, do 20.11.2026", REL),
    ("Dodaj rok: nedelju dana, do 20.11.2026", REL),
    ("Dodaj rok: godinu dana, do 20.11.2026", REL),
    ("Dodaj rok: petnaestak dana, do 20.11.2026", REL),
    ("Dodaj rok: 72 časa, do 20.11.2026", REL),
    ("Додај рок: осмог дана, до 20.11.2026", REL),
    # izričit istek — upis
    ("Dodaj rok 20.11.2026", S20),
    ("Dodaj rok: 20.11.2026 ističe", OBL),  # runda 4: oznaka posle datuma
    ("Dodaj rok zaključno sa 20.11.2026", S20),
    ("Додај рок закључно са 20.11.2026", S20),
    ("Dodaj rok: istek roka je 20.11.2026", S20),
    ("Dodaj rok do dana 20.11.2026", S20),
    ("Додај рок: рок је 20.11.2026", S20),
    ("Додај рок за одговор 20.11.2026", OBL),  # runda 4: svrha bez oznake
]


@pytest.mark.parametrize("poruka,ocekivano", SOPSTVENI)
def test_A3R3_sopstveni_protivnicki(poruka, ocekivano):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == ocekivano


@pytest.mark.parametrize("poruka,ocekivano", [p for p in RUNDA2_PROBA + SOPSTVENI if p[1][0]])
def test_A3R3_upis_end_to_end_samo_izricit_istek(poruka, ocekivano):
    supa = _Supa()
    r, _ = _copilot(poruka, {"dogadjaj": "Rok", "datum_iso": ocekivano[0], "vaznost": "važan"}, supa)
    assert r["uspeh"] is True and supa.hron()[0]["datum_iso"] == ocekivano[0]
    assert "stanje" not in supa.hron()[0]


def test_A3R3_proslost_i_dalje_naglasena_uz_novo_pravilo():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok 01.01.2026", {"dogadjaj": "X", "datum_iso": "2026-01-01", "vaznost": "važan"}, supa)
    assert r["uspeh"] is True and "u prošlosti" in r["odgovor"]


def test_A3R3_model_ne_moze_da_nametne_datum_uz_jaku_oznaku():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za žalbu do 20.11.2026",
                    {"dogadjaj": "Žalba", "datum_iso": "2026-11-21", "vaznost": "kritičan"}, supa)
    assert r["uspeh"] is False and r["razlog"] == "datum_nije_u_poruci" and supa.hron() == []


# Svaki deo dozvoljene liste kao NEZAVISNA odbrana (mutacije ih moraju videti).
def test_A3R3_glagol_dogadjaja_sam_drzi_liniju(monkeypatch):
    from routers import copilot as cp
    # Bez imenica: „primili smo je 01.10.2026" ne sme proći ni preko slabe oznake.
    assert cp._odluka_o_datumu_roka("Dodaj rok, primili smo ga do 01.10.2026") == DOG


def test_A3R3_slaba_oznaka_ne_vazi_uz_imenicu_dogadjaja():
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka("Dodaj rok 20.11.2026 za odluku") == OBL  # runda 5: razlog
    # runda 4: datum mora biti poslednji — „rok <datum> za <svrha>" je pitanje
    assert _odluka_o_datumu_roka("Dodaj rok 20.11.2026 za odgovor") == OBL
    assert _odluka_o_datumu_roka("Dodaj rok za odgovor do 20.11.2026") == S20


# ═════════════════════════════════════════════════════════════════════════════
# A1 — napomena pregleda: datum roka iz čarobnjaka i confirm-card-a se proverava
# na serveru PRE upisa (kolona `datum_iso` je DATE).
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("los", ["15.11.2025", "2026-02-31", "sutra", "2026-1-5", "20261120", "  "])
def test_A1N_intake_nevalidan_prvi_rok_422_bez_predmeta(los):
    from fastapi import HTTPException
    supa = _Supa()
    with pytest.raises(HTTPException) as e:
        _intake(supa, prvi_rok=los, rok_opis="Rok")
    assert e.value.status_code == 422
    assert "Datum roka nije ispravan" in e.value.detail and "Predmet nije kreiran" in e.value.detail
    assert supa.upisi == {}, "ništa se ne upisuje — ni predmet, ni rok"


def test_A1N_intake_prazan_prvi_rok_kao_ranije():
    supa = _Supa()
    r = _intake(supa, prvi_rok="", rok_opis="Rok")
    assert r["rok_dodat"] is False and supa.hron() == []


@pytest.mark.parametrize("los", ["", None, "sutra", "31.02.2026", "2026-13-01", "20/11/2026",
                                 "15. novembra 2025", "2026-11-20T10:00"])
def test_A1N_confirm_links_nevalidan_datum_nula_upisa_jasna_poruka(los):
    supa = _Supa()
    r = _confirm(supa, {"naziv": "Žalba", "datum_iso": los, "vaznost": "važan"})
    assert r["rok_dodat"] is False and r["success"] is False
    assert "datum roka nije ispravan" in r["rok_greska"]
    assert supa.hron() == []


@pytest.mark.parametrize("ulaz,iso", [("2026-11-05", "2026-11-05"), ("05.11.2026", "2026-11-05"),
                                      ("5.11.2026.", "2026-11-05")])
def test_A1N_confirm_links_upisuje_kanonski_iso(ulaz, iso):
    """„05.11.2026" bi baza (DateStyle MDY) pročitala kao 11. maj — upisuje se kanonski ISO."""
    supa = _Supa()
    r = _confirm(supa, {"naziv": "Žalba", "datum_iso": ulaz, "vaznost": "važan"})
    assert r["success"] is True and r["rok_dodat"] is True
    assert supa.hron()[0]["datum_iso"] == iso and supa.hron()[0]["datum"] == iso


# ═════════════════════════════════════════════════════════════════════════════
# A3 — RUNDA 4 (pregled bab5046d: NO-GO). Promenjena KLASA odluke: upis samo
# kad CELA poruka odgovara gramatici `_ROK_GRAMATIKA_RE` (posle normalizacije);
# sve ostalo je pitanje sa tačnim oblikom koji se prihvata.
# ═════════════════════════════════════════════════════════════════════════════

# HIGH/MEDIUM iz runde 3 (recenzent + zadatak): nijedan ne sme da upiše rok.
RUNDA3_HIGH = [
    ("Dodaj rok, rok za žalbu počinje 01.10.2026", "2026-10-01"),
    ("Додај рок, рок за жалбу почиње 01.10.2026", "2026-10-01"),
    ("Dodaj rok, rok za žalbu teče 01.10.2026", "2026-10-01"),
    ("Dodaj rok, rok za žalbu kreće 01.10.2026", "2026-10-01"),
    ("Dodaj rok, rok za žalbu se računa 01.10.2026", "2026-10-01"),
    ("rok za žalbu počinje 01.10.2026", "2026-10-01"),
    ("rok za žalbu teče 01.10.2026", "2026-10-01"),
    ("rok za žalbu kreće 01.10.2026", "2026-10-01"),
    ("rok za žalbu se računa 01.10.2026", "2026-10-01"),
    ("Dodaj rok, rok nije do 20.11.2026", "2026-11-20"),
    ("rok nije do 20.11.2026", "2026-11-20"),
    ("Dodaj rok, nije rok 20.11.2026", "2026-11-20"),
    ("Dodaj rok za suđenje 20.11.2026", "2026-11-20"),
    ("Dodaj rok, suđenje do 20.11.2026", "2026-11-20"),
    ("Dodaj rok do 20.11.2026, a ročište je tada", "2026-11-20"),
    ("Dodaj rok, presuda je bila do 01.10.2026 kod sudije", "2026-10-01"),
    ("Dodaj rok, sudija na odmoru do 20.11.2026", "2026-11-20"),
    ("Presuda je do 01.10.2026 bila u pisarnici, dodaj rok", "2026-10-01"),
    ("Dodaj rok do ročišta 20.11.2026", "2026-11-20"),
    ("Dodaj rok do 20.11.2026 ročište", "2026-11-20"),
    ("Dodaj rok do 20.11.2026 jer tada počinje suđenje", "2026-11-20"),
]


@pytest.mark.parametrize("poruka,datum", RUNDA3_HIGH)
def test_A3R4_runda3_high_nikad_upis(poruka, datum):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka)[0] is None
    assert _odluka_o_datumu_roka(poruka, datum)[0] is None
    supa = _Supa()
    r, gpt = _copilot(poruka, {"dogadjaj": "Rok", "datum_iso": datum, "vaznost": "važan"}, supa)
    assert r["uspeh"] is False and r["potrebno_pojasnjenje"] is True, r
    assert supa.hron() == [] and gpt == []


# Ceo probni skup recenzenta runde 3 (rev3_a3_probe + _rev3_probe_test):
# (poruka, očekivanje recenzenta S/C/?, ishod runde 4).
RUNDA3_PROBA = [
    ('Dodaj rok do: 20.11.2026', 'S', ('2026-11-20', None)),
    ('Dodaj rok do — 20.11.2026', 'S', ('2026-11-20', None)),
    ('Dodaj rok do20.11.2026', '?', (None, 'oblik_roka')),
    ('DODAJ ROK DO 20.11.2026', 'S', ('2026-11-20', None)),
    ('dodaj rok istice 20.11.2026', 'S', ('2026-11-20', None)),
    ('dodaj rok za zalbu do 20. 11. 2026.', 'S', ('2026-11-20', None)),
    ('Dodaj rok do 20. novembra 2026.', 'S', ('2026-11-20', None)),
    ('Додај рок до 20. новембра 2026.', 'S', (None, 'nepodrzan_format')),
    ('Додај рок за жалбу истиче 20.11.2026', 'S', ('2026-11-20', None)),
    ('Dodaj rok: rok je 20.11.2026', 'S', ('2026-11-20', None)),
    ('Dodaj rok, najkasnije do petka 20.11.2026', 'S', ('2026-11-20', None)),
    ('Dodaj rok do petka 21.11.2026', 'C', (None, 'relativni_rok')),
    ('Dodaj rok za žalbu do Apelacionog suda 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dostaviti do suda 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok do daljeg 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok: dostaviti podnesak do suda, 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Rok za žalbu do višeg suda 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok od 01.10.2026 do 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok u periodu od 01.10.2026. do 20.11.2026.', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, presuda dostavljena do 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Rešenje stiglo do nas 01.10.2026, dodaj rok', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, rešenje došlo do nas 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Presuda je do 01.10.2026 bila u pisarnici, dodaj rok', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, presudu smo dobili 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, presuda je uručena advokatu 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok - presuda nam je došla 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, dobili smo rešenje 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, ugovor ističe 20.11.2026', '?', (None, 'oblik_roka')),
    ('Dodaj rok: zakup ističe 20.11.2026', '?', (None, 'oblik_roka')),
    ('Dodaj rok, punomoćje ističe 20.11.2026', '?', (None, 'oblik_roka')),
    ('Dodaj rok, garancija istice 20.11.2026', '?', (None, 'oblik_roka')),
    ('Dodaj rok, rok je bio 12.03.2025', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, rok nije do 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, ne do 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, nije rok 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, rok više nije 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, rok nije 20.11.2026 nego kasnije', 'C', (None, 'oblik_roka')),
    ('Dodaj rok "presuda od 12.03.2025" do 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok za žalbu. Ročište 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 za žalbu na presudu od 12.03.2025', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 za presudu', '?', (None, 'oblik_roka')),
    ('Dodaj rok do 20.11.2026 za ročište', '?', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 kada je ročište', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 jer je tada ročište', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026, tada je ročište', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026. Ročište.', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 ročište', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 i ročište', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 - ročište', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 kad počinje rasprava', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 jer tada počinje suđenje', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 — tada je glavna rasprava', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok ročište do 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, ročište je do 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, suđenje do 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, rasprava zakazana do 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, rok je 20.11.2026 jer je tad ročište', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do dana ročišta 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do ročišta 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do ročišta, 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do rasprave 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do suđenja 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do pretresa 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Додај рок до рочишта 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do glavne rasprave 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do sledećeg ročišta 20.11.2026', 'C', (None, 'relativni_rok')),
    ('Dodaj rok pre ročišta 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, ročište je 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, suđenje je 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, sud je zakazao 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok: saslušanje svedoka 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok za saslušanje 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok za ročište 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok za suđenje 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok za veštačenje 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok za sastanak sa klijentom 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('rok za izlazak na uviđaj 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok 20.11.2026', 'S', ('2026-11-20', None)),
    ('rok: 20.11.2026', 'S', ('2026-11-20', None)),
    ('rok za podnesak 20.11.2026', 'S', (None, 'oblik_roka')),
    ('rok za odgovor 20.11.2026', 'S', (None, 'oblik_roka')),
    ('rocište 20.11.2026 dodaj rok', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok 20.11.2026 ročište', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok 20.11.2026 suđenje', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok 20.11.2026 sastanak', 'C', (None, 'datum_je_dogadjaj')),
    ('rok sednica 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('rok ročište 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('rok sudjenje 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('rok za glavni pretres 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Klijent je zvao i pitao za stanje predmeta. Rok je 20.11.2026.', 'S', (None, 'oblik_roka')),
    ('Dodaj rok. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Klijent je zvao. Ročište 20.11.2026.', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok istice dvadesetog novembra 2026', '?', ('2026-11-20', None)),
    ('Dodaj rok do 20 nov 2026', '?', (None, 'bez_datuma')),
    ('Додај рок, рок је 20. новембар 2026.', 'S', (None, 'nepodrzan_format')),
    ('Додај рок, рочиште је 20. новембра 2026.', 'C', (None, 'nepodrzan_format')),
    ('Додај рок, суђење 20. новембра 2026.', 'C', (None, 'nepodrzan_format')),
    ('Dodaj рок до 20.11.2026', 'S', ('2026-11-20', None)),
    ('Dodaj rok до рочишта 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 u 10:00 ročište', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok 20.11.2026 u 10:00', '?', (None, 'oblik_roka')),
    ('Dodaj rok do 20.11.2026 do 15h', '?', (None, 'oblik_roka')),
    ('Dodaj rok: rok je istekao 20.11.2025', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, rok je počeo 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, rok je tekao od 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, rok počinje 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, rok teče od 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, rok počinje da teče 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, početak roka 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, početak je 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, rok kreće 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok koji počinje 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, rok za žalbu počinje 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok za početak 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, datum dostave 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, klijent je dobio pismo 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, pismo je dobijeno 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok: tužba podneta 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok: tužbu smo poslali 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok za žalbu, odluka od 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok za žalbu, odluka 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok za žalbu (presuda 01.10.2026)', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, poslednji dan je 20.11.2026', 'S', ('2026-11-20', None)),
    ('Dodaj rok, poslednji dan za uplatu je 20.11.2026', '?', (None, 'oblik_roka')),
    ('Dodaj rok zaključno sa 20.11.2026', 'S', ('2026-11-20', None)),
    ('Dodaj rok zakljucno sa 20.11.2026', 'S', ('2026-11-20', None)),
    ('Dodaj rok, poslednji dan ročišta je 20.11.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok za žalbu do 20.11.2026, presuda je od 12.03.2025', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 (presuda)', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026 za odgovor na tužbu', '?', (None, 'oblik_roka')),
    ('Dodaj rok do 20.11.2026 za žalbu, ročište', '?', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, sledeće ročište do 20.11.2026', 'C', (None, 'relativni_rok')),
    ('Dodaj rok, sud zaseda do 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, sudija na odmoru do 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, klijent u inostranstvu do 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, kancelarija zatvorena do 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, svedok nedostupan do 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, pritvor traje do 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, mera zabrane važi do 20.11.2026', '?', (None, 'oblik_roka')),
    ('Dodaj rok, prekid postupka do 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Dodaj rok, zastoj do 20.11.2026', 'C', (None, 'oblik_roka')),
    ('Додај рок, рок за жалбу почиње 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, rok za žalbu teče 01.10.2026', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok do 20.11.2026, a ročište je tada', 'C', (None, 'datum_je_dogadjaj')),
    ('Dodaj rok, presuda je bila do 01.10.2026 kod sudije', 'C', (None, 'oblik_roka')),
]


def test_A3R4_proba_runde3_ima_144_ulaza():
    assert len(RUNDA3_PROBA) == 144


@pytest.mark.parametrize("poruka,rec,ocekivano", RUNDA3_PROBA)
def test_A3R4_probni_skup_runde3(poruka, rec, ocekivano):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == ocekivano
    if rec == "C":
        assert ocekivano[0] is None, "recenzent: mora pitanje"


# Sopstveni protivnički ulazi runde 4 — svaki je POKUŠAJ da se gramatika
# zaobiđe (svrha nosi glagol/negaciju/događaj, višak teksta, homoglif...).
SOPSTVENI_R4 = [
    ("rok za žalbu počinje do 01.10.2026", DOG),
    ("rok za žalbu teče do 01.10.2026", DOG),
    ("rok za žalbu se računa do 01.10.2026", OBL),
    ("rok za žalbu nije do 20.11.2026", OBL),
    ("rok za žalbu ne ističe 20.11.2026", OBL),
    ("rok za suđenje do 20.11.2026", DOG),
    ("rok za sudjenje do 20.11.2026", DOG),
    ("rok za sudenje do 20.11.2026", DOG),
    ("рок за суђење до 20.11.2026", DOG),
    ("ROK ZA ROČIŠTE DO 20.11.2026", DOG),
    ("rok za žalbu bio je do 01.10.2026", OBL),
    ("rok za žalbu je bio do 01.10.2026", OBL),
    ("rok za žalbu pisala do 01.10.2026", OBL),        # glagolski pridev radni (-la)
    ("rok za žalbu odobrena do 20.11.2026", OBL),      # glagolski pridev trpni (-ena)
    ("rok za žalbu uzeta do 20.11.2026", OBL),         # trpni (-eta)
    ("rok za žalbu pao do 20.11.2026", OBL),           # radni (-ao)
    ("rok za žalbu od 01.10.2026", DOG),
    ("rok za žalbu nakon presude do 20.11.2026", DOG),
    ("rok do 20.11.2026 za žalbu", OBL),
    ("rok za žalbu do 20.11.2026, presuda je od 12.03.2025", DOG),
    ("rok za žalbu u periodu do 20.11.2026", OBL),
    ("rok za žalbu do sledećeg ročišta 20.11.2026", REL),
    ("rok za pritvor do 20.11.2026", OBL),
    ("rok za žalbu kada je ročište do 20.11.2026", DOG),
    ("Dodaj rok za rok do 20.11.2026", OBL),
    ("rok za žalbu do petka 21.11.2026", REL),
    ("rok je bio 12.03.2025", OBL),
    ("rok za odgovor do 20.11.2026 godine kod sudije", OBL),
    ("Dodaj rok, sudija na odmoru do 20.11.2026", OBL),
    ("rok za žalbu tek do 20.11.2026", OBL),
    ("rok za žalbu pоčinje do 01.10.2026", DOG),       # ćirilično „о" kao homoglif
    ("rok​do 20.11.2026", OBL),                    # nevidljiv znak
    ("rok za žalbu do 20.11.2026\nročište", DOG),
    ("rok za pripremu izmenu dopunu ispravku uplatu odgovor podnesak do 20.11.2026", OBL),  # 7 reči
    ("rok za žalbu do 20.11.2026 godine.", S20),
    ("dodaj rok za žalbu do 20.11.2026 2026", OBL),
    ("rok za žalbu do 2026-11-20 u 10:00", OBL),
    ("Dodaj rok \"do 20.11.2026\"", OBL),
    ("Dodaj novi rok do 20.11.2026", OBL),
    ("rok za presudu ističe 20.11.2026", OBL),
    # svaka lista zabrana mora sama da drži liniju (mutacije M1c/M1d/M1f/M2d/M3d)
    ("rok za žalbu će biti do 20.11.2026", OBL),        # pomoćni glagol
    ("rok za žalbu kada sud odredi do 20.11.2026", DOG),  # veznik
    ("rok za žalbu traje do 20.11.2026", OBL),           # glagol stanja
    ("rok za meru zabrane važi do 20.11.2026", OBL),
    ("rok za žalbu stiže do 20.11.2026", DOG),           # glagol događaja (osnova)
    ("rok za odgovor potpisan do 20.11.2026", OBL),      # trpni pridev (-an)
]


@pytest.mark.parametrize("poruka,ocekivano", SOPSTVENI_R4)
def test_A3R4_sopstveni_protivnicki(poruka, ocekivano):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == ocekivano


# Šta se UPISUJE (gramatika — svaka komanda, svaka oznaka, oba pisma).
SACUVANO_R4 = [
    ("Dodaj rok za odgovor do 20.11.2026", "2026-11-20"),
    ("Dodaj rok za žalbu ističe 20.11.2026", "2026-11-20"),
    ("Dodaj rok za žalbu isteče 20.11.2026", "2026-11-20"),
    ("rok za podnesak do 20.11.2026", "2026-11-20"),
    ("Dodaj rok najkasnije do 20.11.2026", "2026-11-20"),
    ("Dodaj rok: najkasnije do 20.11.2026", "2026-11-20"),
    ("Upiši rok za uplatu sudske takse do 20.11.2026", "2026-11-20"),
    ("Unesi rok za dopunu do 20.11.2026", "2026-11-20"),
    ("Zabeleži rok: rok je 20.11.2026", "2026-11-20"),
    ("Zapiši rok, rok ističe 20.11.2026", "2026-11-20"),
    ("Postavi rok za reviziju do 20.11.2026", "2026-11-20"),
    ("Додај рок за жалбу истиче 20.11.2026", "2026-11-20"),
    ("Упиши рок за одговор до 20.11.2026", "2026-11-20"),
    ("Dodaj rok za izjašnjenje zaključno sa 20.11.2026", "2026-11-20"),
    ("Dodaj rok zaključno do 20.11.2026", "2026-11-20"),
    ("Dodaj rok za podnošenje predloga je do 20.11.2026 godine", "2026-11-20"),
    ("Dodaj rok: poslednji dan roka je 20.11.2026", "2026-11-20"),
    ("Dodaj rok, poslednji dan je 20.11.2026", "2026-11-20"),
    ("Dodaj rok: istek roka je 20.11.2026", "2026-11-20"),
    ("Dodaj rok do petka 20.11.2026", "2026-11-20"),
    ("Dodaj rok do dana 20.11.2026", "2026-11-20"),
    ("Dodaj rok 20.11.2026", "2026-11-20"),
    ("rok 2026-11-20", "2026-11-20"),
    ("Dodaj rok za žalbu do 20. novembra 2026.", "2026-11-20"),
    ("Dodaj rok do 20.11.2026. godine.", "2026-11-20"),
    ("Dodaj rok do dvadesetog novembra 2026", "2026-11-20"),
    ("DODAJ ROK ZA ZALBU DO 20.11.2026", "2026-11-20"),
    ("Dodaj rok za odgovor na žalbu do 20.11.2026", "2026-11-20"),
    ("rok za pripremu izmenu dopunu ispravku uplatu odgovor do 20.11.2026", "2026-11-20"),  # 6 reči
    ("Dodaj   rok   za  žalbu   do 20.11.2026", "2026-11-20"),
]


@pytest.mark.parametrize("poruka,iso", SACUVANO_R4)
def test_A3R4_gramatika_upisuje(poruka, iso):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == (iso, None)
    supa = _Supa()
    r, _ = _copilot(poruka, {"dogadjaj": "Rok", "datum_iso": iso, "vaznost": "važan"}, supa)
    assert r["uspeh"] is True and supa.hron()[0]["datum_iso"] == iso
    assert "stanje" not in supa.hron()[0] and "nije potvrđen" in r["odgovor"]


# Cena preciznosti: ranije UPISANO (runda 3), sada PITANJE. Svaka je namerna:
# datum nije poslednji, svrha bez oznake isteka, oznaka posle datuma, vreme,
# ili svrha sadrži imenicu dokumenta/događaja (tužb, rešenj, dostav, ročišt).
BIVSI_UPISI = [
    ("Dodaj rok 20.11.2026 za dopunu tužbe", OBL),
    ("Dodaj rok za podnesak 20.11.2026", OBL),
    ("Dodaj rok za odgovor 20.11.2026", OBL),
    ("Dodaj rok 20.11.2026 za podnesak", OBL),
    ("Dodaj rok za podnesak 2026-11-20", OBL),
    ("Dodaj rok 20. 11. 2026 za podnesak", OBL),
    ("Dodaj rok 20.11.2026 (2026-11-20) za podnesak", OBL),
    ("Додај рок за жалбу 20.11.2026", OBL),
    ("Додај рок за одговор 20.11.2026", OBL),
    ("Dodaj rok 2026-11-20T10:00", OBL),
    ("Dodaj rok: 20.11.2026 ističe", OBL),
    ("Dodaj rok za pripremu za ročište do 20.11.2026", DOG),
    ("Dodaj rok do 20.11.2026, predmet P 1234/2026", DOG),
]


@pytest.mark.parametrize("poruka,ocekivano", BIVSI_UPISI)
def test_A3R4_bivsi_upisi_su_pitanje_sa_oblikom(poruka, ocekivano):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == ocekivano
    supa = _Supa()
    r, gpt = _copilot(poruka, {"dogadjaj": "Rok", "datum_iso": "2026-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is False and supa.hron() == [] and gpt == []
    assert "„rok za žalbu ističe 20.11.2026“" in r["odgovor"] and "Rok nije sačuvan" in r["odgovor"]


def test_A3R4_poruka_oblik_roka_tacan_oblik():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za podnesak 20.11.2026", {"dogadjaj": "X", "datum_iso": "2026-11-20",
                                                         "vaznost": "važan"}, supa)
    assert r["razlog"] == "oblik_roka" and r["potrebno_pojasnjenje"] is True
    assert r["odgovor"] == ("Rok nije sačuvan. Napišite ga u obliku: „rok za žalbu ističe 20.11.2026“ "
                            "ili „rok za podnesak do 20.11.2026“.")


def test_A3R4_gramatika_proverava_datum_i_dan_nezavisno(monkeypatch):
    """Provera datuma i dana u nedelji u `_rok_po_gramatici` drži liniju i kada
    detektori relativnosti (koji inače hvataju neslaganje dana) ne vide ništa."""
    import re as _re
    from routers import copilot as cp
    assert cp._rok_po_gramatici("rok do 20.11.2026", "2026-11-21") is False
    nikad = _re.compile(r"(?!x)x")
    monkeypatch.setattr(cp, "_ROK_RELATIVNI_RE", nikad)
    monkeypatch.setattr(cp, "_ROK_TRAJANJE_RE", nikad)
    monkeypatch.setattr(cp, "_rok_relativni_parser", lambda tekst: False)
    assert cp._odluka_o_datumu_roka("Dodaj rok do petka 21.11.2026")[0] is None
    assert cp._odluka_o_datumu_roka("Dodaj rok do petka 20.11.2026") == S20


def test_A3R4_proslost_i_model_i_dalje_vaze():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za žalbu do 01.01.2026", {"dogadjaj": "X", "datum_iso": "2026-01-01",
                                                          "vaznost": "važan"}, supa)
    assert r["uspeh"] is True and "u prošlosti" in r["odgovor"]
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za žalbu ističe 20.11.2026", {"dogadjaj": "X", "datum_iso": "2026-11-27",
                                                              "vaznost": "važan"}, supa)
    assert r["uspeh"] is False and r["razlog"] == "datum_nije_u_poruci" and supa.hron() == []


# ═════════════════════════════════════════════════════════════════════════════
# A3 runda 5 — napomene pregleda runde 4 (F1–F5). „Danas" je fiksiran na
# 2026-10-14 (autouse `_danas_fiksiran`).
# ═════════════════════════════════════════════════════════════════════════════
VAN = (None, "datum_van_opsega")

# F1 — uz SVRHU gola „je" nije oznaka isteka (datum događaja: licitacija, medijacija...).
F1_GOLO_JE = [
    "rok za ispitivanje svedoka je 20.11.2026",
    "rok za licitaciju je 20.11.2026",
    "rok za javnu prodaju je 20.11.2026",
    "rok za medijaciju je 20.11.2026",
    "rok za konferenciju je 20.11.2026",
    "rok za glasanje je 20.11.2026",
    "rok za zastarelost je 20.11.2026",
    "rok za prekluziju je 20.11.2026",
    "rok za žalbu je 01.10.2026",
    "rok za zalbu je 20.11.2026",
    "dodaj rok za podnesak je 20.11.2026",
    # izuzeci svrhe (F2) nikad ne važe uz golo „je"
    "rok za zalbu na presudu je 20.11.2026",
    "rok za odgovor na tuzbu je 20.11.2026",
    "rok za dostavu dokaza je 20.11.2026",
    "rok za uredjenje tuzbe je 20.11.2026",
    "rok za zalbu na resenje o izvrsenju je 20.11.2026",
]


@pytest.mark.parametrize("poruka", F1_GOLO_JE)
def test_A3R5_F1_golo_je_uz_svrhu_je_pitanje(poruka):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == OBL
    supa = _Supa()
    r, gpt = _copilot(poruka, {"dogadjaj": "X", "datum_iso": "2026-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is False and r["razlog"] == "oblik_roka" and supa.hron() == [] and gpt == []
    assert "„rok za žalbu ističe 20.11.2026“" in r["odgovor"]


@pytest.mark.parametrize("poruka", [
    "rok je 20.11.2026",
    "Dodaj rok: rok je 20.11.2026",
    "rok je 01.10.2026 godine",
    "rok za zalbu je do 20.11.2026",
    "rok za zalbu poslednji dan je 20.11.2026",
    "rok za zalbu poslednji dan roka je 20.11.2026",
    "rok za zalbu istek roka je 20.11.2026",
    "Dodaj rok: istek roka je 20.11.2026",
])
def test_A3R5_F1_je_bez_svrhe_i_jake_oznake_ostaju(poruka):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka)[0] is not None


# F2 — uske dozvole u svrsi; važe SAMO uz jaku oznaku.
SACUVANO_R5 = [
    "rok za odgovor na tuzbu do 20.11.2026",
    "rok za zalbu na presudu do 20.11.2026",
    "rok za zalbu na resenje istice 20.11.2026",
    "rok za dostavu dokaza do 20.11.2026",
    "rok za uredjenje tuzbe do 20.11.2026",
    "rok za prigovor na resenje o izvrsenju do 20.11.2026",
    "Dodaj rok za odgovor na tužbu do 20.11.2026",
    "Dodaj rok za žalbu na rešenje do 20.11.2026",
    "Dodaj rok za dostavu dokaza do 20.11.2026",
    "Dodaj rok za žalbu na rešenje ističe 20.11.2026",
    "Додај рок за одговор на тужбу до 20.11.2026",
    "rok za odgovor na tuzbu najkasnije do 20.11.2026",
    "rok za zalbu na odluku zakljucno sa 20.11.2026",
    "rok za prigovor na zakljucak do dana 20.11.2026",
    "rok za podnosenje tuzbe istece 20.11.2026",
    "rok za dopunu tuzbe do 20.11.2026",
    "rok za zalbu na presudu poslednji dan je 20.11.2026",
]


@pytest.mark.parametrize("poruka", SACUVANO_R5)
def test_A3R5_F2_uske_dozvole_upisuju(poruka):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == S20
    supa = _Supa()
    r, _ = _copilot(poruka, {"dogadjaj": "Rok", "datum_iso": "2026-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is True and supa.hron()[0]["datum_iso"] == "2026-11-20"
    assert "stanje" not in supa.hron()[0] and supa.hron()[0]["vrsta"] == rokovi.VRSTA_ROK


# Reč van svog tačnog mesta, datum dokumenta („od"), glagolski pridev, negacija,
# bez oznake — i dalje pitanje.
F2_I_DALJE_PITANJE = [
    ("rok za presudu do 20.11.2026", OBL),
    ("rok za tuzbu do 20.11.2026", OBL),
    ("rok za resenje do 20.11.2026", OBL),
    ("rok za tuzbe do 20.11.2026", OBL),
    ("rok za zalbu tuzbe do 20.11.2026", OBL),
    ("rok za zalbu dostavu do 20.11.2026", OBL),
    ("rok za dostavu presude do 20.11.2026", OBL),
    ("rok za zalbu na presude do 20.11.2026", OBL),
    ("rok za zalbu po presudi do 20.11.2026", OBL),
    ("rok za zalbu na dostavu do 20.11.2026", OBL),
    ("rok za zalbu na rociste do 20.11.2026", DOG),
    ("rok za zalbu na presudu od 12.03.2025 do 20.11.2026", DOG),
    ("rok za zalbu na presudu od 20.11.2026", DOG),
    ("rok za zalbu na presudu donetu do 20.11.2026", DOG),
    ("rok za zalbu na presudu primljenu do 20.11.2026", DOG),
    ("rok za zalbu na resenje koje je doneto do 20.11.2026", DOG),
    ("rok za zalbu na resenje ne do 20.11.2026", OBL),
    ("rok za podnosenje tuzbe protiv do 20.11.2026", OBL),
    ("rok za dostavu dokaza nije do 20.11.2026", OBL),
    ("rok za dostavu dokaza 20.11.2026", OBL),
    ("rok za zalbu na presudu 20.11.2026", DOG),  # (d) imenica dokumenta uz datum
]


@pytest.mark.parametrize("poruka,ocekivano", F2_I_DALJE_PITANJE)
def test_A3R5_F2_van_mesta_i_dalje_pitanje(poruka, ocekivano):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == ocekivano
    supa = _Supa()
    r, gpt = _copilot(poruka, {"dogadjaj": "X", "datum_iso": "2026-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is False and supa.hron() == [] and gpt == []


# F2 — razlog: „datum_je_dogadjaj" samo uz signal događaja; sama imenica dokumenta
# u svrsi -> „oblik_roka" (tačan oblik, bez tvrdnje o događaju).
@pytest.mark.parametrize("poruka,ocekivano", [
    ("Dodaj rok do 20.11.2026 za odgovor na tužbu", OBL),       # imenica u svrsi, nije uz datum
    ("Dodaj rok 20.11.2026 za dopunu tužbe", OBL),
    ("Dostaviti do suda 20.11.2026", OBL),
    ("Dodaj rok, presuda primljena 01.10.2026", DOG),            # (b) glagolski pridev događaja
    ("Dodaj rok, presudu smo dobili 01.10.2026", DOG),
    ("Dodaj rok za žalbu na presudu od 12.03.2025", DOG),  # (a) „od"
    ("Dodaj rok 20.11.2026 ročište", DOG),                       # (c) zakazan događaj
    ("Dodaj rok za žalbu (presuda 01.10.2026)", DOG),            # (d) imenica dokumenta uz datum
    ("Dodaj rok, datum dostave 01.10.2026", DOG),
    ("Dodaj rok do 20.11.2026 (presuda)", DOG),
    ("Dodaj rok za žalbu na presudu Višeg suda, datum 12.03.2025", DOG),
])
def test_A3R5_F2_razlog_po_signalu_dogadjaja(poruka, ocekivano):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == ocekivano


# F3 — granice godine: [danas − 1 godina, danas + 10 godina], uključivo.
@pytest.mark.parametrize("poruka,ocekivano", [
    ("rok do 13.10.2025", VAN),
    ("rok do 14.10.2025", ("2025-10-14", None)),
    ("rok do 14.10.2036", ("2036-10-14", None)),
    ("rok do 15.10.2036", VAN),
    ("rok do 20.11.2099", VAN),
    ("rok do 20.11.1999", VAN),
    ("rok do 20.11.0001", VAN),
    ("rok je 12.03.2025", VAN),
    ("rok istice 12.03.2025", VAN),
    ("rok do 2099-11-20", VAN),
    ("rok istice dvadesetog novembra 2099", VAN),
])
def test_A3R5_F3_granice_godine(poruka, ocekivano):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == ocekivano


def test_A3R5_F3_poruka_proverite_godinu_bez_upisa():
    supa = _Supa()
    r, gpt = _copilot("Dodaj rok do 20.11.2099", {"dogadjaj": "X", "datum_iso": "2099-11-20", "vaznost": "važan"}, supa)
    assert r["uspeh"] is False and r["razlog"] == "datum_van_opsega" and supa.hron() == [] and gpt == []
    assert r["odgovor"].startswith("Datum 20.11.2099 je neuobičajeno daleko — proverite godinu.")
    r, _ = _copilot("rok do 2099-11-20", {"dogadjaj": "X", "datum_iso": "2099-11-20", "vaznost": "važan"}, _Supa())
    assert "Datum 20.11.2099 je" in r["odgovor"]


def test_A3R5_F3_upozorenje_za_proslost_unutar_godine_ostaje():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za žalbu do 14.10.2025", {"dogadjaj": "X", "datum_iso": "2025-10-14",
                                                          "vaznost": "važan"}, supa)
    assert r["uspeh"] is True and "u prošlosti" in r["odgovor"]


def test_A3R5_F3_granice_prate_stvarni_danas(monkeypatch):
    import datetime as _dt

    class _Datum(_dt.date):
        @classmethod
        def today(cls):
            return cls(2031, 3, 5)

    monkeypatch.setattr(_dt, "date", _Datum)
    assert _ROK_DANAS_PRAVI() == _dt.date(2031, 3, 5)


def test_A3R5_F3_prestupna_godina(monkeypatch):
    from datetime import date
    from routers import copilot as cp
    monkeypatch.setattr(cp, "_rok_danas", lambda: date(2028, 2, 29))
    assert cp._rok_godina_u_opsegu("2027-02-28") and not cp._rok_godina_u_opsegu("2027-02-27")
    assert cp._rok_godina_u_opsegu("2038-02-28") and not cp._rok_godina_u_opsegu("2038-03-01")


# F4 — NFC, završni „!"/„?", navodnici na ivicama; nulta širina i pune cifre i dalje odbijeni.
@pytest.mark.parametrize("poruka,ocekivano", [
    ("rok za žalbu do 20.11.2026", S20),                    # NFD kvačica
    ("rok za žalbu je 20.11.2026", OBL),
    ("rok do 20.11.2026!", S20),
    ("rok do 20.11.2026?", S20),
    ("rok do 20.11.2026!?", S20),
    ('"rok do 20.11.2026"', S20),
    ("„rok do 20.11.2026“", S20),
    ("'rok do 20.11.2026'", S20),
    ("Dodaj rok za žalbu ističe 20.11.2026.!", S20),
    ("rok nije do 20.11.2026!", OBL),
    ("rok do 20.11​.2026", (None, "bez_datuma")),
    ("rok do ２０.１１.２０２６", (None, "nepodrzan_format")),
    ("rok do „20.11.2026“", OBL),                                # navodnici oko datuma: nije olabavljeno
    ("rok! do 20.11.2026", OBL),
])
def test_A3R5_F4_normalizacija(poruka, ocekivano):
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka(poruka) == ocekivano


# F5 — pad modela predlaže prihvaćen oblik; redni datum bez fantomskog 01.10.
def test_A3R5_F5_pad_modela_predlaze_prihvacen_oblik():
    from routers import copilot as cp

    async def _pada(oai, **kw):
        raise RuntimeError("model nedostupan")

    supa = _Supa()

    async def _run():
        with patch.object(cp, "_get_supa", return_value=supa), \
             patch.object(cp, "_pozovi_gpt4o_mini", new=_pada), \
             patch("openai.AsyncOpenAI"), patch.object(cp, "_sentry_capture"):
            return await cp._handle_akcija_rok("Dodaj rok za žalbu ističe 20.11.2026", PRED, UID)

    r = asyncio.run(_run())
    assert r["uspeh"] is False and supa.hron() == []
    assert r["odgovor"] == "Nisam uspeo da prepoznam rok. Pokušajte: „rok za žalbu ističe 20.11.2026“."
    assert cp._odluka_o_datumu_roka("rok za žalbu ističe 20.11.2026") == S20
    assert "ročište" not in r["odgovor"]


def test_A3R5_F5_redni_datum_bez_fantoma():
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka("rok istice trideset prvog oktobra 2026") == OBL
    r, gpt = _copilot("rok istice trideset prvog oktobra 2026",
                      {"dogadjaj": "X", "datum_iso": "2026-10-31", "vaznost": "važan"}, _Supa())
    assert r["uspeh"] is False and gpt == [] and "01.10.2026" not in r["odgovor"]
    r, _ = _copilot("rok do dvadeset prvog oktobra 2026 i 05.11.2026",
                    {"dogadjaj": "X", "datum_iso": "2026-10-21", "vaznost": "važan"}, _Supa())
    assert r["razlog"] == "vise_datuma"
    assert "21.10.2026" in r["odgovor"] and "05.11.2026" in r["odgovor"] and "01.10.2026" not in r["odgovor"]


def test_A3R5_nevalidan_datum_i_dalje_naveden_u_poruci():
    r, _ = _copilot("Dodaj rok do 31.11.2026", {"dogadjaj": "X", "datum_iso": None, "vaznost": "važan"}, _Supa())
    assert r["razlog"] == "nevalidan_datum" and "31.11.2026" in r["odgovor"]


def test_A3R5_drugi_predlog_iz_poruke_je_prihvacen():
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka("Dodaj rok za pripremu do 15.07.2027") == ("2027-07-15", None)


def test_A3R5_F4_nfc_pre_detektora_relativnosti():
    """NFC se primenjuje na celu poruku PRE detektora relativnosti, ne samo u gramatici."""
    from routers.copilot import _odluka_o_datumu_roka
    assert _odluka_o_datumu_roka("Dodaj rok: četiri dana, do 20.11.2026") == (None, "relativni_rok")
    assert _odluka_o_datumu_roka("Dodaj rok: šest dana, do 20.11.2026") == (None, "relativni_rok")


def test_A3R5_F4_norma_sama_primenjuje_nfc():
    from routers.copilot import _rok_norm
    assert _rok_norm("Rok za žalbu do 20.11.2026!") == "rok za zalbu do 20.11.2026"
