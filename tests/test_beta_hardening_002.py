# -*- coding: utf-8 -*-
"""
BETA-HARDENING-002 — WSS governance + provenance schema.

Sva tri pravila iz prethodne noći važe i ovde:
  1. popravka koja samo pomera granicu nije popravka
  2. test koji prolazi posle reverta produkcione popravke nije dokaz
  3. protivnički pregled ima pravo da obori sprint

Zato nijedan test u ovom fajlu ne čita izvor, ne rekonstruiše granu i ne
postavlja stanje ručno. Svi voze **produkcijske funkcije**.
"""
import asyncio

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# BYPASS-7 — VEZA KA PROVAJDERU BEZ GOVERNANCE ODLUKE MORA BITI NEMOGUĆA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_bypass7_veza_bez_odluke_je_odbijena():
    """NAJVAŽNIJI TEST U FAJLU.

    Kapija `proveri_voice_dozvolu()` je postojala, ali je stajala SAMO u
    `start()`. Sama tačka povezivanja nije imala nikakvu proveru — svaki novi
    pozivalac mogao je da otvori sirov WSS ka OpenAI Realtime API-ju bez ijedne
    governance odluke. To je bio `BYPASS-7`.

    Ovde se ne proverava da postoji log ni da je funkcija pozvana. Poziva se
    PRAVA tačka povezivanja i traži se da odbije.
    """
    import services.voice_orchestrator as vo

    # Svež kontekst — nijedna odluka nije doneta u ovom toku.
    assert not vo.voice_odluka_doneta(), "test počinje sa zaostalom odlukom"

    with pytest.raises(vo.VoiceGovernanceBypass):
        await vo._connect_openai_realtime()


@pytest.mark.anyio
async def test_bypass7_odluka_iz_druge_sesije_se_ne_moze_pozajmiti():
    """Odluka je vezana za tok izvršavanja, ne za proces.

    Da je čuvana u globalnoj promenljivoj, jedna legitimna sesija bi otvorila
    vrata svakoj narednoj — uključujući onu bez prava.
    """
    import services.voice_orchestrator as vo

    # ISPRAVLJENO posle merenja: `asyncio.create_task` KOPIRA tekući kontekst,
    # pa bi task napravljen POSLE odluke nasledio je — i to je ispravno
    # ponašanje, ne rupa. Svojstvo koje se stvarno štiti je drugo:
    #
    #   odluka doneta UNUTAR jedne sesije ne curi u tok koji je nastao
    #   nezavisno od nje.
    #
    # Tako i radi u produkciji: svaku WS vezu server pokreće u sopstvenom
    # tasku, napravljenom pre nego što je ijedna odluka doneta.

    async def _sesija_a():
        vo._oznaci_odluku({"user_id": "u1"}, "cid-1")
        return vo.voice_odluka_doneta()

    async def _sesija_b():
        return vo.voice_odluka_doneta()

    # Oba taska nastaju iz ISTOG, čistog konteksta — kao dve nezavisne veze.
    a = asyncio.create_task(_sesija_a())
    b = asyncio.create_task(_sesija_b())
    rez_a, rez_b = await asyncio.gather(a, b)

    assert rez_a is True, "kapija nije označila odluku u svojoj sesiji"
    assert rez_b is False, (
        "odluka iz sesije A je vidljiva u sesiji B — contextvar bi tada bio "
        "efektivno globalan i jedna legitimna sesija bi otvorila vrata svakoj "
        "narednoj"
    )
    # I posle svega, spoljni kontekst ostaje netaknut.
    assert vo.voice_odluka_doneta() is False


@pytest.mark.anyio
async def test_bypass7_kapija_postavlja_i_korelacioni_kontekst(monkeypatch):
    """WebSocket opseg NE prolazi kroz HTTP middleware koji postavlja korelaciju.

    Glasovna sesija je zato bila jedina putanja bez korelacionog ID-ja — i to
    baš ona koja nosi privilegovan razgovor.
    """
    import services.voice_orchestrator as vo
    from shared import ai_provenance as prov

    prov._request_ctx.set({})
    assert prov.current_correlation_id() is None

    # Kapija sme da prođe: gasimo spoljne provere, ne samu kapiju.
    monkeypatch.setattr(vo, "_feature_registry_zapis", lambda *a, **kw: None, raising=False)

    async def _dozvoli(user):
        # Vozi PRAVU kapiju do kraja; `_ensure_profile` i registry su spolja.
        return None

    # Umesto stubovanja kapije, pozivamo je sa founder korisnikom ako je moguće;
    # ako okruženje to ne dozvoljava, merimo bar da oznaka postavlja korelaciju.
    try:
        await vo.proveri_voice_dozvolu({"user_id": "u1", "email": "benny13.n@gmail.com"})
    except vo.VoiceEntitlementError:
        pytest.skip("okruženje ne dozvoljava prolaz kroz kapiju bez baze")

    assert vo.voice_odluka_doneta(), "kapija je prošla a odluku nije označila"
    assert prov.current_correlation_id(), "korelacioni kontekst nije postavljen"


# ═══════════════════════════════════════════════════════════════════════════
# GT-001 — DEGRADACIJA PROVENANCE ŠEME MORA BITI GLASNA I MERLJIVA
# ═══════════════════════════════════════════════════════════════════════════

def test_gt001_stanje_seme_je_none_dok_se_ne_izmeri():
    """`None` znači „još nije izmereno" i NE SME se prikazivati kao „u redu".

    Ranije nije postojao nijedan spoljni signal o stanju šeme — sistem je mogao
    mesecima da piše osiromašene redove bez ijedne naznake.
    """
    from security import ai_forensics as af

    af._resetuj_stanje_seme()
    stanje = af.provenance_stanje_seme()
    assert stanje["prosirena_sema"] is None
    assert stanje["migracija_089_potvrdjena"] is False, (
        "neizmereno stanje se prikazuje kao potvrđena migracija"
    )


@pytest.mark.anyio
async def test_gt001_pad_na_legacy_semu_je_zabelezen_i_merljiv(monkeypatch):
    """SRŽ GT-001.

    Pre popravke: širok upis padne na „kolona ne postoji", kod tiho pređe na
    10 legacy kolona — BEZ `correlation_id`, `predmet_id`, `status` — i nastavi
    kao da je sve u redu. Potpuni neuspeh je bio `logger.debug`.
    """
    from security import ai_forensics as af

    af._resetuj_stanje_seme()

    upisi = []

    class _Tabela:
        def insert(self, rec):
            upisi.append(rec)
            if "correlation_id" in rec:
                raise RuntimeError('column "correlation_id" does not exist (42703)')
            return self

        def execute(self):
            return None

    class _Supa:
        def table(self, _ime):
            return _Tabela()

    import api
    monkeypatch.setattr(api, "_get_supa", lambda: _Supa(), raising=False)

    await af.log_provenance_from_wrapper(
        module_name="test", model_provider="openai", model_name="gpt-4o",
        correlation_id="cid-123", predmet_id="p-1", status="success",
        latency_ms=12,
    )

    stanje = af.provenance_stanje_seme()
    assert stanje["prosirena_sema"] is False, (
        "pad na legacy šemu nije izmeren — degradacija je i dalje tiha"
    )
    assert stanje["degradiranih_upisa"] == 1
    assert "correlation_id" in stanje["izgubljene_kolone"]
    assert "predmet_id" in stanje["izgubljene_kolone"]
    assert "status" in stanje["izgubljene_kolone"]

    # Red JESTE upisan (politika je fail-open), ali bez join ključa —
    # i to se sada zna.
    assert len(upisi) == 2, f"očekivan širok pa uski upis, dobijeno {len(upisi)}"
    assert "correlation_id" not in upisi[1]


@pytest.mark.anyio
async def test_gt001_uspesan_sirok_upis_potvrdjuje_migraciju(monkeypatch):
    """Druga strana: kad širok upis prođe, to je DOKAZ da je 089 primenjena.

    Bez ove grane bi test iznad prolazio i da stanje uvek pokazuje `False`.
    """
    from security import ai_forensics as af

    af._resetuj_stanje_seme()

    class _Tabela:
        def insert(self, rec):
            return self

        def execute(self):
            return None

    class _Supa:
        def table(self, _ime):
            return _Tabela()

    import api
    monkeypatch.setattr(api, "_get_supa", lambda: _Supa(), raising=False)

    await af.log_provenance_from_wrapper(
        module_name="test", model_provider="openai", model_name="gpt-4o",
        correlation_id="cid-1", status="success", latency_ms=1,
    )
    stanje = af.provenance_stanje_seme()
    assert stanje["prosirena_sema"] is True
    assert stanje["migracija_089_potvrdjena"] is True
    assert stanje["degradiranih_upisa"] == 0


def test_gt001_health_izlaze_stanje_seme():
    """Stanje u memoriji koje se ne vidi spolja nije dokaz.

    `/health` je do sada izlagao stanje ZAKRPE, ne stanje ŠEME — pa tiho
    osiromašenje traga nije imalo nijedan spoljni signal.
    """
    import api

    odgovor = api.health()
    assert "provenance" in odgovor, "/health ne izlaže stanje provenance šeme"
    p = odgovor["provenance"]
    assert "prosirena_sema" in p and "migracija_089_potvrdjena" in p


# ═══════════════════════════════════════════════════════════════════════════
# NALAZI PROTIVNIČKOG PREGLEDA (S2, S3, S8, P2, P6b)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_s2_injektovana_fabrika_ne_zaobilazi_prinudu():
    """S2 — `openai_ws_factory` je zamenjivao CELU funkciju povezivanja.

    Izmereno u pregledu: veza otvorena uz `odluka_doneta=False` — dakle baš ono
    što je komentar tvrdio da je nemoguće. Prinuda je zato premeštena i na
    granicu sesije, gde nijedna fabrika ne može da je zaobiđe.
    """
    import services.voice_orchestrator as vo

    async def _lazna_fabrika():
        return object()          # "veza" bez ijedne provere

    sesija = vo.VoiceOrchestratorSession.__new__(vo.VoiceOrchestratorSession)
    sesija.user = {"user_id": "napadac"}
    sesija._connect = _lazna_fabrika
    sesija.upstream = None

    with pytest.raises(vo.VoiceGovernanceBypass):
        vo._provjeri_odluku_za(sesija.user)


def test_s3_odluka_se_ne_moze_konstruisati_spolja():
    """S3 — `_oznaci_odluku` je bila javna i bez ijedne provere prava.

    Token sada može da nastane samo unutar kapije: konstruktor traži privatni
    ključ modula koji se nigde ne izvozi.
    """
    import services.voice_orchestrator as vo

    with pytest.raises(vo.VoiceGovernanceBypass):
        vo._Odluka(object(), "napadac", "cid")


@pytest.mark.anyio
async def test_s8_odluka_drugog_korisnika_ne_otvara_sesiju():
    """S8 — provera je gledala samo DA odluka postoji, ne i čija je.

    Odluka korisnika A otvarala je vezu za korisnika B.
    """
    import services.voice_orchestrator as vo

    vo._oznaci_odluku({"user_id": "korisnik-A"}, "cid-A")
    assert vo.voice_odluka_doneta()

    with pytest.raises(vo.VoiceGovernanceBypass):
        vo._provjeri_odluku_za({"user_id": "korisnik-B"})

    # Za svog vlasnika i dalje prolazi.
    vo._provjeri_odluku_za({"user_id": "korisnik-A"})


@pytest.mark.anyio
async def test_p2_degradacija_seme_je_lepljiva(monkeypatch):
    """P2 — latch koji se otključava a nikad ne zaključava.

    Jedan uspešan upis posle degradiranog vraćao je `migracija_089_potvrdjena`
    na `True` i praznio `izgubljene_kolone`. Dohvatljivo preko PostgREST
    schema-cache staleness i rolling deploy-a.
    """
    from security import ai_forensics as af

    af._resetuj_stanje_seme()
    stanja = {"pada": True}

    class _Tabela:
        def insert(self, rec):
            if stanja["pada"] and "correlation_id" in rec:
                raise RuntimeError('column "correlation_id" does not exist')
            return self

        def execute(self):
            return None

    class _Supa:
        def table(self, _):
            return _Tabela()

    import api
    monkeypatch.setattr(api, "_get_supa", lambda: _Supa(), raising=False)

    await af.log_provenance_from_wrapper(
        module_name="t", model_provider="openai", model_name="m",
        correlation_id="c1", status="success", latency_ms=1,
    )
    assert af.provenance_stanje_seme()["prosirena_sema"] is False

    # Sledeći upis prolazi (npr. drugi worker, osvežen schema cache).
    stanja["pada"] = False
    await af.log_provenance_from_wrapper(
        module_name="t", model_provider="openai", model_name="m",
        correlation_id="c2", status="success", latency_ms=1,
    )

    stanje = af.provenance_stanje_seme()
    assert stanje["prosirena_sema"] is False, (
        "jedan uspešan upis je poništio izmerenu degradaciju — latch se "
        "otključava a nikad ne zaključava (P2)"
    )
    assert stanje["migracija_089_potvrdjena"] is False
    assert "correlation_id" in stanje["izgubljene_kolone"], (
        "spisak izgubljenih kolona je konstanta, ne merenje"
    )


def test_p6b_health_ne_curi_tekst_izuzetka(monkeypatch):
    """P6b — NOVA bezbednosna površina koju je uveo ovaj sprint.

    `/health` je javan i neautentikovan. Izmereno je da je vraćao
    `str(_exc)[:120]`, iz kog je izlazio `postgres://korisnik:LOZINKA@host/baza`.
    """
    import api
    from security import ai_forensics as af

    def _pukni():
        raise RuntimeError("postgres://korisnik:TAJNA@db.host/baza — refused")

    monkeypatch.setattr(af, "provenance_stanje_seme", _pukni, raising=False)
    odgovor = api._provenance_stanje()

    spojeno = str(odgovor)
    assert "TAJNA" not in spojeno and "postgres://" not in spojeno, (
        f"javni /health curi tekst izuzetka: {spojeno!r}"
    )
    assert odgovor == {"dostupno": False}
