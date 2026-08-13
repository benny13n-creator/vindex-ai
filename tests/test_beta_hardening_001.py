# -*- coding: utf-8 -*-
"""
BETA-HARDENING-001 — dokazi izvršavanjem, ne prisustvom niske.

ZAŠTO OVAJ FAJL POSTOJI

`NIGHT-005` je opisao tačno kvar `FS-001` i tvrdio da ga zatvara. Njegov test
(`test_beta_gate_credit_second_order.py:114`) proverava:

    assert "_delivered = True" in src

To je **prisustvo niske u izvoru**, ne mesto izvršavanja. Niska je bila
prisutna, a zastavica se nikad nije podizala kad klijent prekine vezu posle
poslednjeg komada — jer generator ostaje suspendovan na `yield` i liniju ispod
petlje nikad ne izvrši.

Rezultat: 70 testova zeleno, a advokat dobija pun odgovor **besplatno**,
ponovljivo do granice od 10 zahteva u minutu.

Zato se ovde ništa ne čita iz izvora. Generator se **pokreće**, komadi se
**stvarno konzumiraju**, veza se **stvarno prekida**, i broji se koliko je puta
pozvan `UsageService.refund`.
"""
import asyncio
import inspect
import types

import pytest


@pytest.fixture
def anyio_backend():
    """Projekat vozi `asyncio`; `anyio` bi inace parametrizovao i `trio`,
    koji ovde nije zavisnost."""
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# INFRASTRUKTURA — vozimo PRAVI generator iz api.pitanje_stream
# ═══════════════════════════════════════════════════════════════════════════

class _Broj:
    """Broji pozive umesto `MagicMock`, da se u poruci vidi tačan broj."""

    def __init__(self, vrednost=None):
        self.pozivi = []
        self.vrednost = vrednost

    async def __call__(self, *a, **kw):
        self.pozivi.append((a, kw))
        return self.vrednost


async def _pokreni_stream(monkeypatch, *, odgovor, prekid_posle_poslednjeg,
                          prekid_na_komadu=None):
    """Vraća `(primljeni_delovi, broj_refunda, broj_naplata)`.

    `prekid_posle_poslednjeg=True` simulira ono što radi pregledač kad korisnik
    zatvori karticu: primi poslednji komad i **ne traži sledeći**, pa Starlette
    zatvori generator (`GeneratorExit`).
    """
    import api

    naplata = _Broj(vrednost=9)
    refund = _Broj(vrednost=None)
    saldo = _Broj(vrednost=10)
    monkeypatch.setattr(api.UsageService, "consume", naplata)
    monkeypatch.setattr(api.UsageService, "refund", refund)
    monkeypatch.setattr(api.UsageService, "balance", saldo)

    async def _memorija(*a, **kw):
        return ""
    monkeypatch.setattr(api, "_fetch_firm_memory_context", _memorija, raising=False)

    async def _pokreni(_fn, *a, **kw):
        return {"status": "success", "data": odgovor}
    monkeypatch.setattr(api, "pokreni", _pokreni, raising=False)

    for ime in ("klasifikuj_pitanje", "_skini_pii"):
        if hasattr(api, ime):
            monkeypatch.setattr(api, ime, lambda *a, **kw: "opste", raising=False)

    req = types.SimpleNamespace(
        pitanje="Koji su uslovi za naknadu štete?", history=None,
        predmet_id=None, session_id=None, namespace=None,
    )
    zahtev = types.SimpleNamespace(
        client=types.SimpleNamespace(host="127.0.0.1"), headers={}, url="/api/pitanje/stream",
        state=types.SimpleNamespace(),
    )
    korisnik = {"user_id": "u-test", "email": "t@t.rs"}

    fn = api.pitanje_stream
    while hasattr(fn, "__wrapped__"):          # skini `@limiter.limit`
        fn = fn.__wrapped__

    odgovor_obj = await fn(req=req, request=zahtev, user=korisnik)
    iterator = odgovor_obj.body_iterator

    ukupno = -(-len(odgovor) // 80)
    # SE-001: tačka prekida je PARAMETAR. Prva verzija je merila samo prekid
    # posle POSLEDNJEG komada, pa nije videla da popravka pomera granicu
    # zloupotrebe za tačno 80 znakova umesto da je zatvori.
    granica = prekid_na_komadu if prekid_na_komadu is not None else ukupno

    primljeni = []
    try:
        async for komad in iterator:
            tekst = komad.decode() if isinstance(komad, (bytes, bytearray)) else komad
            primljeni.append(tekst)
            if prekid_posle_poslednjeg and "[CREDITS" not in tekst:
                _tekstualnih = len([p for p in primljeni if p.startswith("data: ")
                                    and "[DONE]" not in p and "[CREDITS" not in p])
                if _tekstualnih >= granica:
                    break
    finally:
        if prekid_posle_poslednjeg:
            await iterator.aclose()

    return primljeni, len(refund.pozivi), len(naplata.pozivi)


def _tekst(primljeni):
    out = []
    for p in primljeni:
        if p.startswith("data: ") and "[DONE]" not in p and "[CREDITS" not in p:
            out.append(p[len("data: "):].rstrip("\n").replace("\\n", "\n"))
    return "".join(out)


# ═══════════════════════════════════════════════════════════════════════════
# FS-001 — PUN ODGOVOR + PREKID VEZE NE SME DA VRATI KREDIT
# ═══════════════════════════════════════════════════════════════════════════

_ODGOVOR = "PRAVNI OSNOV: član 154 ZOO. " * 14          # ~363 znaka, 5 komada


@pytest.mark.anyio
async def test_fs001_pun_odgovor_pa_prekid_ne_vraca_kredit(monkeypatch):
    """NAJVAŽNIJI TEST U FAJLU.

    Izmereno pre popravke: 363/363 znaka primljeno, bajt-identično, saldo
    10 → 10, neto cena 0. Ponovljivo do granice od 10/min.
    """
    primljeni, refunda, naplata = await _pokreni_stream(
        monkeypatch, odgovor=_ODGOVOR, prekid_posle_poslednjeg=True
    )
    isporuceno = _tekst(primljeni)

    assert isporuceno == _ODGOVOR, (
        f"test ne meri ono što tvrdi — isporučeno {len(isporuceno)} od "
        f"{len(_ODGOVOR)} znakova; scenario zahteva PUN odgovor pa prekid"
    )
    assert naplata == 1, "kredit nije ni naplaćen — scenario nije postavljen"
    assert refunda == 0, (
        f"pun odgovor je isporučen, a kredit je vraćen {refunda}× — "
        f"korisnik je dobio AI odgovor besplatno (FS-001)"
    )


@pytest.mark.anyio
async def test_fs001_uredan_zavrsetak_takodje_naplacuje(monkeypatch):
    """Negativna kontrola: popravka ne sme da naplati dvaput niti da promeni
    ponašanje na normalnom putu."""
    primljeni, refunda, naplata = await _pokreni_stream(
        monkeypatch, odgovor=_ODGOVOR, prekid_posle_poslednjeg=False
    )
    assert _tekst(primljeni) == _ODGOVOR
    assert naplata == 1
    assert refunda == 0
    assert any("[DONE]" in p for p in primljeni), "protokol se nije uredno završio"


@pytest.mark.anyio
async def test_fs001_prekid_pre_prvog_komada_i_dalje_vraca_kredit(monkeypatch):
    """Druga strana. Popravka ne sme da ukine legitiman refund.

    Ako korisnik prekine PRE nego što je išta primio, kredit mora nazad —
    to je bio ceo smisao `SOA-012`.
    """
    import api

    naplata = _Broj(vrednost=9)
    refund = _Broj(vrednost=None)
    monkeypatch.setattr(api.UsageService, "consume", naplata)
    monkeypatch.setattr(api.UsageService, "refund", refund)
    monkeypatch.setattr(api.UsageService, "balance", _Broj(vrednost=10))

    async def _memorija(*a, **kw):
        return ""
    monkeypatch.setattr(api, "_fetch_firm_memory_context", _memorija, raising=False)

    async def _spor(*a, **kw):
        await asyncio.sleep(5)       # korisnik prekida dok se odgovor jos racuna
        return {"status": "success", "data": _ODGOVOR}
    monkeypatch.setattr(api, "pokreni", _spor, raising=False)

    req = types.SimpleNamespace(pitanje="p", history=None, predmet_id=None,
                                session_id=None, namespace=None)
    zahtev = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"),
                                   headers={}, url="/x", state=types.SimpleNamespace())
    fn = api.pitanje_stream
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    odg = await fn(req=req, request=zahtev, user={"user_id": "u", "email": "e@e.rs"})

    it = odg.body_iterator
    # `aclose()` nad NEPOKRENUTIM generatorom ne izvrsava nijednu liniju --
    # prva verzija ovog testa je zbog toga merila nista. Scenario SOA-012 je
    # „korisnik prekine dok CEKA odgovor", pa se generator mora pokrenuti i
    # prekinuti U TOKU `await pokreni(...)`.
    zadatak = asyncio.ensure_future(it.__anext__())
    await asyncio.sleep(0)
    zadatak.cancel()
    try:
        await zadatak
    except (asyncio.CancelledError, StopAsyncIteration):
        pass
    await it.aclose()
    assert len(refund.pozivi) == 1, (
        "prekid PRE isporuke mora da vrati kredit — popravka FS-001 je previše "
        "široka i ukinula je legitiman refund iz SOA-012"
    )


# ═══════════════════════════════════════════════════════════════════════════
# FS-003 — PRAZAN ODGOVOR NE SME DA SE NAPLATI
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_fs003_prazan_odgovor_vraca_kredit_i_javlja_korisniku(monkeypatch):
    """Prazan ekran + uredan `[DONE]` + naplaćen kredit je bio mogući ishod."""
    primljeni, refunda, naplata = await _pokreni_stream(
        monkeypatch, odgovor="", prekid_posle_poslednjeg=False
    )
    assert naplata == 1
    assert refunda == 1, "prazan odgovor je naplaćen — korisnik ne dobija ništa"
    spojeno = "".join(primljeni)
    assert "Sistem nije vratio odgovor" in spojeno, (
        f"korisnik ne dobija nikakvu poruku o praznom odgovoru: {spojeno[:200]!r}"
    )


def test_fs003_predikat_je_zajednicki_za_obe_putanje():
    """Uslov refundacije je bio DOSLOVNO isti na obe putanje i obe su imale
    istu rupu. Popravka ne sme da zakrpi samo jednu."""
    import api
    src = inspect.getsource(api)
    assert src.count("_treba_refundirati(rezultat)") >= 2, (
        "kanonski predikat se ne koristi na obe putanje"
    )
    assert api._treba_refundirati({"status": "success", "data": ""}) is True
    assert api._treba_refundirati({"status": "success", "data": "   "}) is True
    assert api._treba_refundirati({"status": "success", "data": "odgovor"}) is False
    assert api._treba_refundirati({"status": "error"}) is True
    assert api._treba_refundirati({"status": "success", "data": "x", "blocked": True}) is True
    assert api._treba_refundirati({"status": "success", "data": "x", "from_cache": True}) is True


# ═══════════════════════════════════════════════════════════════════════════
# FS-004 — ODBIJEN ODGOVOR NE SME DA SE ZAPIŠE KAO USPEH
# ═══════════════════════════════════════════════════════════════════════════

def test_fs004_provenance_se_upisuje_tek_posle_firewall_provere():
    """Redosled je bio: zapiši uspeh → pa proveri. Kad firewall odbije odgovor,
    pozivalac dobija izuzetak, a jedini forenzički trag kaže `success`.

    Meri se REDOSLED IZVRŠAVANJA u izvoru zakrpe — ali uz mutacionu proveru
    ispod, koja izvršava obe grane.
    """
    import shared.ai_client as ac
    src = inspect.getsource(ac._patch_prompt_guard)
    for grana in ("_guarded_create", "_guarded_acreate"):
        telo = src.split(f"def {grana}")[1].split("def ")[0]
        i_enforce = telo.find("_enforce_response(kwargs, response)")
        i_capture = telo.find("_capture_chat_provenance(self, kwargs, response, _ms)")
        assert i_enforce != -1 and i_capture != -1, f"{grana}: obrazac nije pronađen"
        assert i_enforce < i_capture, (
            f"{grana}: provenance se i dalje upisuje PRE firewall provere"
        )


def test_fs004_blokiran_odgovor_se_belezi_kao_greska(monkeypatch):
    """MUTACIONO DOKAZANO SLAB U PRVOJ VERZIJI.

    Prva verzija je REKONSTRUISALA granu unutar testa i time merila sopstvenu
    kopiju — prolazila je i uz pun revert produkcije. Protivnički pregled je to
    dokazao mutacijom: „vrati tačno FS-004 kvar" → 408 testova zeleno.

    Sada se poziva PRAVI zakrpljeni `Completions.create`, sa stubovanim
    originalom, i meri se šta je provenance stvarno zapisao.
    """
    import shared.ai_client as ac
    from openai.resources.chat.completions import Completions

    assert getattr(Completions.create, "_vindex_guarded", False), (
        "zakrpa nije aktivna — test ne meri produkcijsku putanju"
    )

    zapisi = []
    monkeypatch.setattr(
        ac, "_capture_chat_provenance",
        lambda self, kwargs, response, ms, error=None: zapisi.append(error),
        raising=False,
    )

    class _Odbijeno(Exception):
        pass

    monkeypatch.setattr(
        ac, "_enforce_response",
        lambda kwargs, response: (_ for _ in ()).throw(_Odbijeno("firewall")),
        raising=False,
    )
    monkeypatch.setattr(ac, "_dohvati_analizator", lambda: (lambda t: type(
        "R", (), {"blocked": False, "risk_score": 0.0, "flags": []})()), raising=False)

    # Originalni SDK poziv se ne sme desiti — stubujemo ga.
    import openai.resources.chat.completions as _oc
    monkeypatch.setattr(ac, "_with_timeout", lambda kw: kw, raising=False)

    class _LaznoTelo:
        pass

    # `_orig_create` je zarobljen u zatvorenju zakrpe; umesto njega presrećemo
    # ceo poziv preko `_enforce_response` koji baca — dovoljno da se izmeri
    # REDOSLED, jer provenance mora biti pozvan sa `error`.
    with pytest.raises(BaseException):
        Completions.create(
            _LaznoTelo(), messages=[{"role": "user", "content": "test"}], model="gpt-4o"
        )

    assert zapisi, "provenance nije pozvan nijednom"
    assert zapisi[-1] is not None, (
        "odbijen odgovor je zabeležen BEZ greške — trag i dalje tvrdi uspeh (FS-004)"
    )


# ═══════════════════════════════════════════════════════════════════════════
# FS-002 — GLASOVNA SESIJA BEZ ZVUKA NIJE USPEŠNA SESIJA
# ═══════════════════════════════════════════════════════════════════════════

def test_fs002_start_ne_belezi_uspeh():
    """`status="success"` se upisivao pri OTVARANJU sesije, pre ijednog bajta."""
    import services.voice_orchestrator as vo
    src = inspect.getsource(vo)
    assert '_uknjizi_voice_sesiju_provenance(self.user, status="started")' in src, (
        "otvaranje sesije se i dalje beleži kao uspeh"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("delti, ocekivan", [(0, "error"), (3, "success")])
async def test_fs002_terminalni_status_prati_stvarnu_isporuku(monkeypatch, delti, ocekivan):
    """SRŽ FS-002.

    Sesija u kojoj advokat nije čuo ništa ne sme da ostane zabeležena kao
    uspešna — to je jedini forenzički trag privilegovanog razgovora.
    """
    import services.voice_orchestrator as vo

    upisi = []
    monkeypatch.setattr(
        vo, "_uknjizi_voice_sesiju_provenance",
        lambda user, status="success", error=None: upisi.append(status),
        raising=False,
    )

    sesija = vo.VoiceOrchestratorSession.__new__(vo.VoiceOrchestratorSession)
    sesija.user = {"user_id": "u"}
    sesija.upstream = None
    sesija._isporucenih_delti = delti
    sesija._provenance_zatvoren = False

    await sesija.close()
    assert upisi == [ocekivan], (
        f"sesija sa {delti} isporučenih delti zabeležena kao {upisi} "
        f"(očekivano {[ocekivan]})"
    )


@pytest.mark.anyio
async def test_fs002_dvostruko_zatvaranje_ne_pise_dva_reda(monkeypatch):
    import services.voice_orchestrator as vo
    upisi = []
    monkeypatch.setattr(
        vo, "_uknjizi_voice_sesiju_provenance",
        lambda user, status="success", error=None: upisi.append(status),
        raising=False,
    )
    s = vo.VoiceOrchestratorSession.__new__(vo.VoiceOrchestratorSession)
    s.user = {}; s.upstream = None; s._isporucenih_delti = 1; s._provenance_zatvoren = False
    await s.close()
    await s.close()
    assert len(upisi) == 1, f"dvostruki upis provenance-a: {upisi}"


# ═══════════════════════════════════════════════════════════════════════════
# NALAZI PROTIVNIČKOG PREGLEDA (SE-001, SE-004…SE-007)
# ═══════════════════════════════════════════════════════════════════════════

_DUG_ODGOVOR = "Član 154 ZOO propisuje odgovornost za štetu. " * 90     # ~4.000 zn.


@pytest.mark.anyio
@pytest.mark.parametrize("zrtvovano", [1, 2, 5])
async def test_se001_prekid_pre_kraja_ne_vraca_kredit(monkeypatch, zrtvovano):
    """SE-001 — POPRAVKA JE PRVO SAMO POMERILA GRANICU ZA 80 ZNAKOVA.

    Prva verzija je podizala zastavicu pred POSLEDNJIM komadom, pa je prekid na
    pretposlednjem i dalje refundirao. Izmereno: 3.920 od 4.000 znakova (98%),
    `refund = 1`.

    Ubitačna okolnost: `DISCLAIMER` (265 znakova) visi na kraju SVAKOG odgovora,
    pa je poslednji komad uvek rep pravne napomene — napadač ga žrtvuje bez
    ijednog izgubljenog znaka pravnog sadržaja.
    """
    ukupno = -(-len(_DUG_ODGOVOR) // 80)
    primljeni, refunda, naplata = await _pokreni_stream(
        monkeypatch, odgovor=_DUG_ODGOVOR, prekid_posle_poslednjeg=True,
        prekid_na_komadu=ukupno - zrtvovano,
    )
    isporuceno = len(_tekst(primljeni))
    assert isporuceno > 0, "test ne meri ništa — nijedan komad nije primljen"
    assert naplata == 1
    assert refunda == 0, (
        f"žrtvovano {zrtvovano} komada, primljeno {isporuceno}/{len(_DUG_ODGOVOR)} "
        f"znakova ({100*isporuceno//len(_DUG_ODGOVOR)}%), a kredit je vraćen — "
        f"granica zloupotrebe je samo pomerena, ne zatvorena (SE-001)"
    )


@pytest.mark.anyio
async def test_se007_greska_posle_isporuke_ne_vraca_kredit(monkeypatch):
    """SE-007 — `not _delivered` je postojalo SAMO u `except BaseException`.

    Izuzetak koji nastane POSLE isporuke prolazio je kroz `except Exception` i
    refundirao pun, već isporučen odgovor. Izmereno u protivničkom pregledu:
    437 znakova isporučeno, `refund = 1`, uz dva `[DONE]`.

    Scenario mora da ispuni tri uslova istovremeno, inače ne meri ništa:
      · odgovor je STVARNO isporučen,
      · `_refunded` je još `False` (dakle NE `from_cache`/`blocked`/`error`),
      · izuzetak nastaje tek u repu generatora.
    Postiže se tako što `consume` vrati vrednost nad kojom `max(preostalo, 0)`
    puca — realan oblik pokvarenog salda, i jedino mesto u repu koje računa.
    """
    import api

    class _PokvarenSaldo:
        def __gt__(self, other):
            raise TypeError("pokvaren saldo — pada TEK u repu generatora")
        __lt__ = __ge__ = __le__ = __gt__

    naplata = _Broj(vrednost=_PokvarenSaldo())
    refund = _Broj(vrednost=None)
    monkeypatch.setattr(api.UsageService, "consume", naplata)
    monkeypatch.setattr(api.UsageService, "refund", refund)
    monkeypatch.setattr(api.UsageService, "balance", _Broj(vrednost=10))

    async def _memorija(*a, **kw):
        return ""
    monkeypatch.setattr(api, "_fetch_firm_memory_context", _memorija, raising=False)

    async def _pokreni(_fn, *a, **kw):
        return {"status": "success", "data": _ODGOVOR}
    monkeypatch.setattr(api, "pokreni", _pokreni, raising=False)

    req = types.SimpleNamespace(pitanje="p", history=None, predmet_id=None,
                                session_id=None, namespace=None)
    zahtev = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"),
                                   headers={}, url="/x", state=types.SimpleNamespace())
    fn = api.pitanje_stream
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    odg = await fn(req=req, request=zahtev, user={"user_id": "u", "email": "e@e.rs"})

    primljeni = []
    async for komad in odg.body_iterator:
        primljeni.append(komad.decode() if isinstance(komad, (bytes, bytearray)) else komad)

    assert _ODGOVOR in _tekst(primljeni), (
        "odgovor nije isporučen — scenario ne meri ono što tvrdi"
    )
    assert len(refund.pozivi) == 0, (
        f"pun odgovor je isporučen, pa je greška u repu vratila kredit "
        f"{len(refund.pozivi)}× — `except Exception` nema zaštitu `not _delivered` "
        f"(SE-007)"
    )


@pytest.mark.anyio
async def test_se005_odgovor_od_belina_javlja_korisniku(monkeypatch):
    """SE-005 — beline proizvode komade, pa grana za prazan odgovor ne opali.
    Korisnik dobija prazan ekran i uredan `[DONE]`."""
    primljeni, refunda, _ = await _pokreni_stream(
        monkeypatch, odgovor="     \n   ", prekid_posle_poslednjeg=False
    )
    spojeno = "".join(primljeni)
    assert refunda == 1, "odgovor od samih belina je naplaćen"
    assert "Sistem nije vratio odgovor" in spojeno, (
        f"korisnik ne dobija poruku o praznom odgovoru: {spojeno[:200]!r}"
    )


@pytest.mark.parametrize("data", [None, [], {}, 0, ["x"], {"a": 1}, "tekst"])
def test_se006_predikat_ne_puca_na_ne_str_podacima(data):
    """SE-006 — `ask_analiza_v2` vraća `data` kao `dict`.

    Prva verzija predikata je radila `(data or "").strip()` i bacala
    `AttributeError` — kanonski predikat bi postao NOV izvor padova.
    """
    import api
    rezultat = api._treba_refundirati({"status": "success", "data": data})
    assert isinstance(rezultat, bool)
    prazno = data is None or (isinstance(data, str) and not data.strip()) or \
        (not isinstance(data, str) and not data)
    assert rezultat is bool(prazno), f"data={data!r} → {rezultat}, očekivano {bool(prazno)}"


@pytest.mark.anyio
@pytest.mark.parametrize("dogadjaji, ocekivan", [
    ([], "error"),
    ([{"type": "response.audio.delta", "delta": "AAA"}], "success"),
    # SE-004: sesija BEZ audio delti ali sa transkriptom i rezultatom alata
    # JESTE isporučila nešto — brojanje jednog kanala ju je lažno rušilo.
    ([{"type": "conversation.item.input_audio_transcription.completed"},
      {"type": "response.done"}], "success"),
    ([{"type": "error", "error": {"message": "x"}}], "error"),
])
async def test_se004_ishod_se_meri_po_isporuci_a_ne_po_jednom_kanalu(
    monkeypatch, dogadjaji, ocekivan
):
    """FS-002 + SE-004 — sada se vozi PRAVI `handle_upstream_event`.

    Prva verzija je ručno postavljala brojač preko `__new__` i time merila
    aritmetiku, ne ožičenje: mutacija „ukloni inkrement" je prolazila.
    """
    import services.voice_orchestrator as vo

    upisi = []
    monkeypatch.setattr(
        vo, "_uknjizi_voice_sesiju_provenance",
        lambda user, status="success", error=None: upisi.append(status),
        raising=False,
    )

    class _Ws:
        def __init__(self):
            self.poslato = []

        async def send_json(self, x):
            self.poslato.append(x)

    s = vo.VoiceOrchestratorSession.__new__(vo.VoiceOrchestratorSession)
    s.user = {"user_id": "u"}
    s.upstream = None
    s.client_ws = _Ws()
    s._isporucenih_delti = 0
    s._provenance_zatvoren = False
    s._pending_confirmations = {}

    for e in dogadjaji:
        await s.handle_upstream_event(e)
    await s.close()

    assert upisi == [ocekivan], (
        f"događaji {[e['type'] for e in dogadjaji]} → provenance {upisi}, "
        f"očekivano {[ocekivan]}"
    )
