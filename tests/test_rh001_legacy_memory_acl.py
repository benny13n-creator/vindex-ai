# -*- coding: utf-8 -*-
"""RH001 Faza C — legacy `/api/firma-memorija/*` i `/api/memory-graph/*` kroz STVARNE rute.

NS008 Law Brain primenjuje kanonsku granicu na iste tabele (`memory_entries`, `memory_graph_edges`): beleška ili
veza vezana za PREDMET vidljiva je samo onome ko taj predmet sme da vidi (`shared/rag_acl.dozvoljeni_predmeti`:
vlasnik + aktivna delegacija), vezana za KLIJENTA samo vlasniku klijenta; opšti entiteti (sudija, firma, partner,
argument, strategija) su izričit put deljenja u kancelariji. Prolazna Law Brain ACL matrica NE dokazuje ništa o
legacy rutama nad istim tabelama — ovaj test dokazuje.

Svet: A i B u kancelariji K1, B NIJE delegiran. A ima privatan predmet, belešku uz taj predmet, belešku uz svog
klijenta i vezu u grafu sa ishodom. Opšta beleška o sudiji i opšta veza su namerno deljene.
Pravilo bajt-identičnosti: svaki B-ov odgovor je isti u svetu SA i BEZ A-ovih privatnih podataka.
"""
import json
import types

import pytest

import tests.ns008_fake as f8

K1 = "e1e1e1e1-1919-4000-8000-000000000001"
PA = "aaaaaaaa-1919-4000-8000-0000000000a1"
PB = "bbbbbbbb-1919-4000-8000-0000000000b1"
KL_A = "c1c1c1c1-1919-4000-8000-0000000000c1"
TAJNO = ("Petrović protiv Gradnja Invest DOO", "Klijent A popušta pod pritiskom", "Klijent Marković izbegava ročišta",
         "Zastarelost u predmetu A", PA, KL_A, "m-pred", "m-klij", "g-tajna")


def _svet(sa_a=True):
    t = {
        "predmeti": [{"id": PB, "user_id": "uid-B", "naziv": "B tekući", "tip": "radni", "status": "aktivan",
                      "opis": "B opis"}],
        "klijenti": [], "predmet_delegiranja": [],
        "kancelarije": [{"id": K1, "admin_uid": "uid-X"}],
        "kancelarija_clanovi": [{"kancelarija_id": K1, "user_id": "uid-A", "status": "ACTIVE"},
                                {"kancelarija_id": K1, "user_id": "uid-B", "status": "ACTIVE"}],
        "memory_entries": [{"id": "m-opsta", "kancelarija_id": K1, "user_id": "uid-A", "entity_type": "sudija",
                            "entity_id": "Petrović", "entity_name": "Sudija Petrović", "tip": "obrazac",
                            "sadrzaj": "Sudija traži tabelu rokova.", "vaznost": "normalna", "aktivan": True,
                            "izvor": "manual", "potvrde_count": 1, "zastarela": False, "confidence": 0.9, "created_at": "2026-09-01T00:00:00+00:00"}],
        "memory_graph_edges": [{"id": "g-opsta", "kancelarija_id": K1, "from_type": "argument", "from_id": "rok",
                                "from_naziv": "Propušten rok", "to_type": "sudija", "to_id": "Petrović",
                                "to_naziv": "Sudija Petrović", "relacija": "koristio_argument", "predmet_id": None,
                                "ishod": None, "snaga": 0.5, "kontekst": None, "created_at": "2026-09-01T00:00:00+00:00"}],
        "judge_patterns": [], "client_memory": [], "partner_profiles": [],
    }
    if sa_a:
        t["predmeti"].append({"id": PA, "user_id": "uid-A", "naziv": TAJNO[0], "tip": "radni", "status": "zatvoren",
                              "opis": "A opis"})
        t["klijenti"].append({"id": KL_A, "user_id": "uid-A", "ime": "Marković"})
        t["memory_entries"] += [
            {"id": "m-pred", "kancelarija_id": K1, "user_id": "uid-A", "entity_type": "predmet", "entity_id": PA,
             "entity_name": TAJNO[0], "tip": "napomena", "sadrzaj": TAJNO[1], "vaznost": "visoka", "aktivan": True,
             "izvor": "manual", "potvrde_count": 1, "zastarela": False, "confidence": 0.9, "created_at": "2026-09-02T00:00:00+00:00"},
            {"id": "m-klij", "kancelarija_id": K1, "user_id": "uid-A", "entity_type": "klijent", "entity_id": KL_A,
             "entity_name": "Marković", "tip": "preferencija", "sadrzaj": TAJNO[2], "vaznost": "visoka", "aktivan": True,
             "izvor": "manual", "potvrde_count": 1, "zastarela": False, "confidence": 0.9, "created_at": "2026-09-03T00:00:00+00:00"},
        ]
        t["memory_graph_edges"].append(
            {"id": "g-tajna", "kancelarija_id": K1, "from_type": "argument", "from_id": "zast", "from_naziv": TAJNO[3],
             "to_type": "predmet", "to_id": PA, "to_naziv": TAJNO[0], "relacija": "pobedio_pred", "predmet_id": PA,
             "ishod": "pobeda", "snaga": 0.9, "kontekst": "Klijent A popustio", "created_at": "2026-09-04T00:00:00+00:00"})
    return t


@pytest.fixture
def svet(monkeypatch):
    stanje = {"promptovi": []}

    def _napravi(sa_a=True):
        if "k" in stanje:
            f8.ocisti()
        stanje["k"], stanje["b"] = f8.pripremi(monkeypatch, _svet(sa_a))
        stanje["promptovi"] = []
        import shared.permissions as perm
        import shared.usage as us
        import routers.memory_graph as mg

        async def _politika(feature):
            return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

        async def _nista(*a, **kw):
            return None

        async def _model(oai, **kw):
            stanje["promptovi"].append(json.dumps(kw.get("messages"), ensure_ascii=False))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="odgovor"))])
        monkeypatch.setattr(perm, "get_policy", _politika)
        monkeypatch.setattr(perm, "_check_dependencies", _nista)
        monkeypatch.setattr(us.UsageService, "consume", staticmethod(_nista))
        monkeypatch.setattr(mg, "_pozovi_mg_api", _model)
        try:
            from shared.rate import limiter
            monkeypatch.setattr(limiter, "enabled", False)
        except Exception:
            pass
        return stanje["k"], stanje["b"]
    yield _napravi, stanje
    f8.ocisti()


def H(ko):
    return {"Authorization": f"Bearer tok-{ko}"}      # tests/ns005_harness.TOKENI: tok-A → uid-A, tok-B → uid-B


# Svaka B-ova legacy čitajuća ruta (i one koje vraćaju postojanje kroz status: potvrdi, brisanje).
CITANJA = [
    ("GET", "/api/firma-memorija/sve"),
    ("GET", "/api/firma-memorija/sve?entity_type=predmet"),
    ("GET", "/api/firma-memorija/sve?limit=1"),           # tuđe „visoka" beleške su prve: limit PRE filtera bi odao postojanje
    ("GET", "/api/firma-memorija/pretrazi?limit=1"),
    ("GET", "/api/firma-memorija/pretrazi"),
    ("GET", "/api/firma-memorija/pretrazi?q=klijent"),
    ("GET", f"/api/firma-memorija/pretrazi?entity_type=predmet&entity_id={PA}"),
    ("GET", f"/api/firma-memorija/pretrazi?entity_type=klijent&entity_id={KL_A}"),
    ("GET", "/api/firma-memorija/sudija/Petrović"),
    ("GET", f"/api/firma-memorija/klijent/{KL_A}"),
    ("GET", f"/api/firma-memorija/kontekst-za-ai?sudija_ime=Petrović&klijent_ime={KL_A}"),
    ("GET", f"/api/memory-graph/entitet/predmet/{PA}"),
    ("GET", "/api/memory-graph/entitet/argument/zast"),
    ("GET", "/api/memory-graph/entitet/sudija/Petrović"),
    ("GET", "/api/memory-graph/upit?q=koji+argumenti+su+uspeli"),
    ("GET", f"/api/memory-graph/preporuka/{PB}"),
]
PISANJA_TUDJEG = [("POST", "/api/firma-memorija/potvrdi/m-pred"), ("POST", "/api/firma-memorija/potvrdi/m-klij"),
                  ("DELETE", "/api/firma-memorija/m-pred"), ("DELETE", "/api/firma-memorija/m-klij")]


def _odgovori(k, ko, rute):
    out = {f"{m} {p}": (r.status_code, r.text) for m, p in rute for r in [k.request(m, p, headers=H(ko))]}
    # zaštita od prazne provere: odbijena autentifikacija bi „sakrila" sve i test bi prošao bez ijedne provere
    assert not [r for r, (kod, _) in out.items() if kod in (401, 403, 429)], out
    return out


def test_B_ne_vidi_tudje_predmetne_i_klijentske_beleske_ni_veze(svet):
    napravi, st = svet
    k, _ = napravi(True)
    sa = _odgovori(k, "B", CITANJA)
    for ruta, (kod, telo) in sa.items():
        for t in TAJNO:
            if t in ruta:            # eho onoga što je B SAM poslao (npr. "entitet": {"id": ...}) nije otkriće
                continue
            assert t not in telo, (ruta, t)
    for p in st["promptovi"]:
        for t in TAJNO:
            assert t not in p, ("prompt modela", t)


def test_B_odgovori_bajt_identicni_sa_i_bez_A(svet):
    """Ni brojevi, ni redosled, ni status ne smeju da odaju da A-ovi privatni podaci postoje."""
    napravi, st = svet
    k, _ = napravi(True)
    sa, prompt_sa = _odgovori(k, "B", CITANJA + PISANJA_TUDJEG), list(st["promptovi"])
    k, _ = napravi(False)
    bez, prompt_bez = _odgovori(k, "B", CITANJA + PISANJA_TUDJEG), list(st["promptovi"])
    razlike = [r for r in sa if sa[r] != bez[r]]
    assert razlike == [], razlike
    assert prompt_sa == prompt_bez


def test_B_ne_moze_da_potvrdi_ni_obrise_tudju_belesku(svet):
    napravi, _ = svet
    k, b = napravi(True)
    for m, p in PISANJA_TUDJEG:
        assert k.request(m, p, headers=H("B")).status_code == 404, p
    redovi = {r["id"]: r for r in b.tabele["memory_entries"]}
    assert redovi["m-pred"]["aktivan"] is True and redovi["m-klij"]["aktivan"] is True
    assert int(redovi["m-pred"].get("potvrde_count") or 0) == 1


def test_opsta_znanja_kancelarije_i_dalje_deljena(svet):
    """Postojeći ugovor: beleška o sudiji i opšta veza su vidljive kolegi; B može da ih potvrdi."""
    napravi, _ = svet
    k, _ = napravi(True)
    sve = k.get("/api/firma-memorija/sve", headers=H("B")).json()
    assert [m["id"] for m in sve["memorije"]] == ["m-opsta"] and sve["by_type"] == {"sudija": 1}
    assert "Sudija traži tabelu rokova." in k.get("/api/firma-memorija/sudija/Petrović", headers=H("B")).text
    e = k.get("/api/memory-graph/entitet/sudija/Petrović", headers=H("B")).json()
    assert e["ukupno_veza"] == 1
    assert k.post("/api/firma-memorija/potvrdi/m-opsta", headers=H("B")).status_code == 200


def test_vlasnik_A_vidi_sve_svoje(svet):
    napravi, st = svet
    k, _ = napravi(True)
    sve = k.get("/api/firma-memorija/sve", headers=H("A")).json()
    assert {m["id"] for m in sve["memorije"]} == {"m-opsta", "m-pred", "m-klij"}
    e = k.get(f"/api/memory-graph/entitet/predmet/{PA}", headers=H("A")).json()
    assert e["ukupno_veza"] == 1
    k.get("/api/memory-graph/upit?q=koji+argumenti+su+uspeli", headers=H("A"))
    assert TAJNO[3] in st["promptovi"][-1]


def test_delegiranje_otvara_predmetnu_belesku_a_opoziv_je_zatvara(svet):
    """Delegat vidi belešku i vezu delegiranog predmeta (kanonski ACL); klijent ostaje vlasnikov. Opoziv važi odmah."""
    napravi, _ = svet
    k, b = napravi(True)
    b.tabele["predmet_delegiranja"].append({"predmet_id": PA, "na_user_id": "uid-B", "status": "aktivno"})
    ids = {m["id"] for m in k.get("/api/firma-memorija/sve", headers=H("B")).json()["memorije"]}
    assert ids == {"m-opsta", "m-pred"}
    assert k.get(f"/api/memory-graph/entitet/predmet/{PA}", headers=H("B")).json()["ukupno_veza"] == 1
    b.tabele["predmet_delegiranja"][0]["status"] = "opozvano"
    ids = {m["id"] for m in k.get("/api/firma-memorija/sve", headers=H("B")).json()["memorije"]}
    assert ids == {"m-opsta"}


def test_chat_kontekst_kolege_bez_tudjih_beleski(svet):
    """`api._fetch_firm_memory_context` ubacuje memoriju u SISTEMSKU poruku chata. B-ov kontekst ne sme da sadrži
    A-ove predmetne/klijentske beleške i mora biti isti sa i bez njih; A-ov sadrži svoje."""
    import asyncio
    import api
    napravi, _ = svet
    napravi(True)
    sa = asyncio.run(api._fetch_firm_memory_context("uid-B", pitanje="klijent popušta predmet Petrović"))
    za_a = asyncio.run(api._fetch_firm_memory_context("uid-A", pitanje="klijent popušta predmet Petrović"))
    napravi(False)
    bez = asyncio.run(api._fetch_firm_memory_context("uid-B", pitanje="klijent popušta predmet Petrović"))
    import re
    bez_nonce = lambda x: re.sub(r"_[0-9a-f]{12}>", "_N>", x or "")     # nasumičan omotač protiv injekcije
    assert bez_nonce(sa) == bez_nonce(bez) and "Sudija traži tabelu rokova." in (sa or "")
    for t in TAJNO:
        assert t not in (sa or ""), t
    assert TAJNO[1] in (za_a or "") and TAJNO[2] in (za_a or "")


# ─── RH002 A2: upis veze (`POST /api/memory-graph/dodaj-vezu`) ────────────────────────────────────────────────
# Čitanje je zatvoreno, ali upis je proveravao samo `predmet_id`. Čvor tipa predmet/klijent u `from_id`/`to_id` je
# ulazio neproveren: B je mogao da pripoji vezu (ishod, kontekst — slobodan tekst) TUĐEM predmetu/klijentu, a A je
# zatim vidi u svom grafu i u promptu `/upit`/`/preporuka` (integritet i ubacivanje sadržaja u tuđ predmet).
# Ugovor upisa je isti kao `POST /api/firma-memorija/dodaj` (CONF-011): predmet/klijent mora biti korisnikov,
# odbijanje je 404 istog tela kao za nepostojeći resurs (bez proročišta postojanja).
NEPOSTOJECI = "dddddddd-1919-4000-8000-0000000000d1"


def _veza(**kw):
    v = {"from_type": "argument", "from_id": "rok", "to_type": "sudija", "to_id": "Petrović",
         "relacija": "koristio_argument", "kontekst": "UBACENO-OD-B", "ishod": "pobeda"}
    v.update(kw)
    return v


NEOVLASCENE_VEZE = [
    _veza(from_type="predmet", from_id=PA),
    _veza(to_type="predmet", to_id=PA),
    _veza(from_type="klijent", from_id=KL_A),
    _veza(to_type="klijent", to_id=KL_A),
    _veza(from_type="predmet", from_id=PA, predmet_id=PB),          # sopstveni predmet_id ne „pokriva" tuđ čvor
    _veza(to_type="predmet", to_id=PA, predmet_id=None),
    _veza(predmet_id=PA),
]


@pytest.mark.parametrize("telo", NEOVLASCENE_VEZE, ids=lambda t: f"{t['from_type']}>{t['to_type']}:{t.get('predmet_id')}")
def test_B_ne_moze_da_pripoji_vezu_tudjem_predmetu_ili_klijentu(svet, telo):
    napravi, _ = svet
    k, b = napravi(True)
    pre = len(b.tabele["memory_graph_edges"])
    r = k.post("/api/memory-graph/dodaj-vezu", headers=H("B"), json=telo)
    assert r.status_code == 404, r.text
    assert len(b.tabele["memory_graph_edges"]) == pre
    # A ne vidi ubačeni sadržaj u svom predmetu
    assert "UBACENO-OD-B" not in k.get(f"/api/memory-graph/entitet/predmet/{PA}", headers=H("A")).text


def test_odbijanje_veze_ne_odaje_postojanje(svet):
    """Tuđ i nepostojeći predmet/klijent daju isti odgovor."""
    napravi, _ = svet
    k, _ = napravi(True)
    for strana in ("from", "to"):
        for tip, tudj in (("predmet", PA), ("klijent", KL_A)):
            r1 = k.post("/api/memory-graph/dodaj-vezu", headers=H("B"), json=_veza(**{f"{strana}_type": tip, f"{strana}_id": tudj}))
            r2 = k.post("/api/memory-graph/dodaj-vezu", headers=H("B"), json=_veza(**{f"{strana}_type": tip, f"{strana}_id": NEPOSTOJECI}))
            assert (r1.status_code, r1.text) == (r2.status_code, r2.text) == (404, r2.text)


def test_vlasnik_dodaje_vezu_svom_predmetu_i_klijentu(svet):
    napravi, _ = svet
    k, b = napravi(True)
    r = k.post("/api/memory-graph/dodaj-vezu", headers=H("A"),
               json=_veza(from_type="klijent", from_id=KL_A, to_type="predmet", to_id=PA, predmet_id=PA, kontekst="A-VEZA"))
    assert r.status_code == 200, r.text
    assert "A-VEZA" in k.get(f"/api/memory-graph/entitet/predmet/{PA}", headers=H("A")).text
    # opšta veza bez predmeta/klijenta ostaje dostupna svakom članu (postojeći ugovor)
    assert k.post("/api/memory-graph/dodaj-vezu", headers=H("B"), json=_veza(kontekst="opste")).status_code == 200
    assert k.post("/api/memory-graph/dodaj-vezu", headers=H("B"),
                  json=_veza(from_type="predmet", from_id=PB, predmet_id=PB)).status_code == 200


def test_delegat_upisuje_kao_i_kroz_predmet_id(svet):
    """Bez nove semantike deljenja: upis čvora prati postojeći CONF-011 ugovor za `predmet_id` (vlasnik). Delegat koga
    `predmet_id` odbija ne sme da prođe kroz `from_id`/`to_id` — ista odluka na obe ulazne tačke."""
    napravi, _ = svet
    k, b = napravi(True)
    b.tabele["predmet_delegiranja"].append({"predmet_id": PA, "na_user_id": "uid-B", "status": "aktivno"})
    kroz_predmet_id = k.post("/api/memory-graph/dodaj-vezu", headers=H("B"), json=_veza(predmet_id=PA)).status_code
    kroz_cvor = k.post("/api/memory-graph/dodaj-vezu", headers=H("B"), json=_veza(to_type="predmet", to_id=PA)).status_code
    assert kroz_predmet_id == kroz_cvor


# ─── RH002 FINAL: memorija u STVARNOJ poruci modela kroz `POST /api/pitanje` ─────────────────────────────────
# Test iznad meri povratnu vrednost `_fetch_firm_memory_context`. Ovaj meri ono što model zaista dobija: stvarna
# ruta → stvarno sklapanje memorije (`vidljive_beleske`, bez zamene) → stvarni `ask_agent` → `_pozovi_openai`,
# koji je jedini zamenjen (hvata system/user poruku). Zamenjene su još samo spoljne pretrage korpusa.
def test_chat_ruta_poruka_modela_bez_tudjih_beleski_i_acl_greska_zatvara(svet, monkeypatch):
    import contextlib
    from unittest.mock import MagicMock, patch
    import api
    import shared.rag_acl as rag_acl
    import shared.usage as us
    from security.prompt_guard import IZVOR_MEMORIJA
    napravi, _ = svet
    OPSTA = "Sudija traži tabelu rokova."

    async def _kredit(*a, **kw):
        return 10

    async def _nista(*a, **kw):
        return None
    k, _ = napravi(True)       # fiksture postavlja `consume` → None; ruta za chat računa sa saldom, pa ide posle
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_kredit))
    monkeypatch.setattr(us.UsageService, "refund", staticmethod(_nista))
    monkeypatch.setattr(api, "_get_firma_namespace", _nista, raising=False)
    monkeypatch.setattr(api, "klasifikuj_pitanje", lambda *a, **kw: "opste", raising=False)
    assert api._fetch_firm_memory_context.__module__ == "api"      # sklapanje memorije NIJE zamenjeno

    meta = {"confidence": "HIGH", "top_score": 0.71, "top_article": "Član 200", "top_law": "zakon o obligacionim odnosima",
            "doc_passages": [], "praksa_matches": []}
    docs = ["Zakon o obligacionim odnosima, Član 200: Svako ko drugome prouzrokuje štetu dužan je da je naknadi." * 2]

    @contextlib.contextmanager
    def _model():
        poruke = []

        def _pozovi(system_prompt, user_content, **kw):
            poruke.append(system_prompt + "\n" + user_content)
            return "Prema Članu 200 Zakona o obligacionim odnosima, šteta se naknađuje."
        zamene = {"retrieve_documents": MagicMock(return_value=(docs, meta)),
                  "retrieve_sudska_praksa": MagicMock(return_value=[]), "retrieve_misljenja": MagicMock(return_value=[]),
                  "ekstrakcija_clana": MagicMock(return_value=(None, None)),
                  "_direktan_fetch_clana": MagicMock(return_value=[]), "_pozovi_openai": _pozovi}
        for ime in zamene:
            assert ime in api.ask_agent.__globals__, ime
        with patch.dict(api.ask_agent.__globals__, zamene):
            yield poruke

    def _pitaj(k, ko, n):
        # različito pitanje po zahtevu: keš odgovora ne sme da preskoči sklapanje konteksta
        with _model() as poruke:
            r = k.post("/api/pitanje", headers=H(ko),
                       json={"pitanje": f"Kako sudija vodi ročište o naknadi štete po Članu 200, slučaj {n}?"})
        assert r.status_code == 200, r.text
        assert poruke, f"{ko}: model nije pozvan — poruka modela nije izmerena (prazna provera)"
        return "\n".join(poruke)

    za_a, za_b = _pitaj(k, "A", 1), _pitaj(k, "B", 2)
    # A: sopstvena predmetna i klijentska beleška stižu do modela (pozitivna kontrola)
    assert TAJNO[1] in za_a and TAJNO[2] in za_a and OPSTA in za_a
    # B: opšta beleška kancelarije stiže (dokaz da je memorija sklopljena), A-ove privatne ne
    assert IZVOR_MEMORIJA in za_b and OPSTA in za_b
    for t in TAJNO:
        assert t not in za_b, ("poruka modela za B", t)

    # Greška ACL-a (npr. pad upita delegacija) zatvara: nijedna beleška ne ide modelu, zahtev i dalje prolazi.
    def _pad(*a, **kw):
        raise RuntimeError("ACL nedostupan")
    monkeypatch.setattr(rag_acl, "dozvoljeni_predmeti", _pad)
    for ko, n in (("A", 3), ("B", 4)):
        p = _pitaj(k, ko, n)
        assert IZVOR_MEMORIJA not in p, (ko, "memorija prošla uprkos grešci ACL-a")
        for t in TAJNO:
            assert t not in p, (ko, t)
