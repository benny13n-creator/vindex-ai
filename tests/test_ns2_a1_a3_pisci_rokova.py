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
    r, _ = _copilot("Dodaj rok za odgovor na tužbu 20.11.2026",
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
    r, _ = _copilot("Dodaj rok 20.11.2026 za podnesak",
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
    r, _ = _copilot("Dodaj rok za podnesak 2026-11-20",
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
    assert r["uspeh"] is True and supa.hron()[0]["datum_iso"] == "2026-11-20"


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
    r, gpt = _copilot("Dodaj rok za podnesak 20.11.2026",
                      {"dogadjaj": "Podnesak", "datum_iso": model_datum, "vaznost": "važan"}, supa)
    assert len(gpt) == 1
    assert r["uspeh"] is False and r["razlog"] == "datum_nije_u_poruci", r
    assert supa.hron() == []


def test_A3_model_u_drugom_formatu_isti_datum_prolazi():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za podnesak 20.11.2026",
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
    r1, _ = _copilot("Dodaj rok 20.11.2026 za podnesak", izlaz, supa)
    r2, _ = _copilot("Dodaj rok 20.11.2026 za podnesak", izlaz, supa)
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
    ("Додај рок за жалбу 20.11.2026", ("2026-11-20", None)),
    ("Додај рок: осам дана пре рочишта 20.11.2026", (None, "relativni_rok")),
    ("Dodaj rok: petnaestog maja 2027", ("2027-05-15", None)),
    ("Dodaj rok 20.11.", (None, "nepotpun_datum")),
    ("Dodaj rok 20/11/2026", (None, "nepodrzan_format")),
    ("Dodaj rok 2026-11-20T10:00", ("2026-11-20", None)),
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


# Šta OSTAJE prihvaćeno, i zašto: jedini datum u poruci, bez trajanja, bez
# predloga računanja (od/pre/pred/posle/nakon/računajući) i bez imenice događaja
# (presuda/rešenje/dostava/prijem/uručenje/donet/ročište/podnet/zapisnik/broj)
# u kratkom prozoru oko datuma. „do" i „ističe" opisuju KRAJ roka, ne okidač.
PRIHVACENO = [
    ("Dodaj rok 20.11.2026 za dopunu tužbe", "2026-11-20"),
    ("Dodaj rok: rok ističe 20.11.2026", "2026-11-20"),
    ("Dodaj rok do 20.11.2026", "2026-11-20"),
    ("Dodaj rok za podnesak 20.11.2026", "2026-11-20"),
    ("Dodaj rok za odgovor na tužbu 20.11.2026", "2026-11-20"),
    ("Dodaj rok 20. 11. 2026 za podnesak", "2026-11-20"),
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
    assert "datum događaja ili dokumenta" in r["odgovor"] and "do kog ističe rok" in r["odgovor"]


def test_A3P_forsirana_polja_modela_se_ignorisu():
    """Recenzentova proba: model vraća `vrsta`/`stanje`/`izvor`/tuđi id — upis ih ne preuzima."""
    supa = _Supa()
    r, _ = _copilot("Dodaj rok za odgovor 20.11.2026",
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
    r, _ = _copilot("Dodaj rok 01.01.2020", {"dogadjaj": "X", "datum_iso": "2020-01-01", "vaznost": "važan"}, supa)
    assert r["uspeh"] is True
    assert "u prošlosti" in r["odgovor"]
    assert "stanje" not in supa.hron()[0]


def test_A3P_buduci_datum_bez_upozorenja():
    supa = _Supa()
    r, _ = _copilot("Dodaj rok 20.11.2099", {"dogadjaj": "X", "datum_iso": "2099-11-20", "vaznost": "važan"}, supa)
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
