# -*- coding: utf-8 -*-
"""
AI Client factory — transparentno bira OpenAI ili Azure OpenAI, i (SEC-003)
centralno primenjuje Prompt Guard na SVAKI GPT poziv u aplikaciji.

Ako su AZURE_OPENAI_KEY i AZURE_OPENAI_ENDPOINT postavljeni u .env,
svi OpenAI pozivi idu na Azure (podaci ostaju u EU).
Ako nisu, koristi standardni OpenAI API.

Pozovi _patch_openai_module() i _patch_prompt_guard() na startu pre bilo kog
router importa. Azure deployment imena moraju da se poklapaju sa model imenima:
  - "gpt-4o"      → Azure deployment "gpt-4o"
  - "gpt-4o-mini" → Azure deployment "gpt-4o-mini"

SEC-003 — centralni guard:
  Umesto da se svako od ~130 pozivnih mesta (api.py + ~50 routers/services
  fajlova) samo seti da pozove security/prompt_guard.py, _patch_prompt_guard()
  presreće OpenAI SDK-ovu Completions.create/AsyncCompletions.create metodu
  direktno na klasi — TAČNO onu metodu koju svaki poziv u aplikaciji na kraju
  zove, bez obzira gde je klijent konstruisan. Ovo je ista tehnika koju
  _patch_openai_module() već koristi za Azure redirect (patch na klasu, ne
  na instancu), primenjena na bezbednosni sloj. Rezultat: nijedno pozivno
  mesto ne mora da se menja da bi bilo zaštićeno — zaštita je strukturna,
  ne zavisi od toga da li je autor te rute setio da doda proveru.
"""
import inspect
import logging
import os

logger = logging.getLogger("vindex.ai_client")

_patched = False
_guard_patched = False

# Governance Wave 4 — RAZDVOJENE DVE RAZLIČITE TVRDNJE.
#
# `_guard_patched` je oduvek značio „ne pokušavaj ponovo" (idempotencija). Ali
# se postavljao na True i kada patch NIJE uspeo (`:340`), pa je ista promenljiva
# tvrdila i „pokušano" i „aktivno". Posledica koja je merena, ne pretpostavljena:
# ako uvoz SDK klasa pukne, aplikacija se podigne bez ijednog prompt guard-a,
# bez Response Firewall-a, bez provenance-a i bez timeout-a — a jedini pokazatelj
# stanja tvrdi da je sve u redu. Nijedan health check to nije mogao da razlikuje.
#
# `_guard_active` nosi ISTINU: patch je stvarno instaliran i kontrole se
# izvršavaju. `governance_status()` ga izlaže, a `/api/version` ga objavljuje.
_guard_active = False
_guard_failure_reason: str | None = None

# Governance Wave 9 (§8) — FAIL-CLOSED NA AI GRANICI.
#
# Wave 4 je razdvojio „pokušano" od „aktivno" i pošteno objavljivao
# `active=false`. Ali je ponašanje ostalo isto kao pre: patch padne → log →
# aplikacija nastavlja da izvršava AI pozive potpuno neupravljano (bez prompt
# guard-a, bez Response Firewall-a, bez provenance-a, bez timeout-a). Mandat
# izričito zabranjuje stanje „patch failed → log error → continue AI execution".
#
# ZAŠTO NE RUŠIMO PROCES: uvicorn koji padne zbog neuspelog uvoza SDK klase
# obara i login, i naplatu, i pregled predmeta — governance kvar bi postao
# potpuni ispad. Fail-closed NA AI GRANICI daje istu bezbednosnu garanciju
# (nijedan neupravljan AI poziv se ne izvršava) uz očuvanu dostupnost svega
# ostalog u aplikaciji.
#
# KAKO: jedini način da se AI poziv desi jeste preko `openai` klijenta. Ako ne
# možemo da presretnemo `Completions.create`, možemo da sprečimo da klijent
# uopšte postoji — zamenom `openai.OpenAI`/`AsyncOpenAI` (i Azure parnjaka)
# klasama koje pri KONSTRUKCIJI dižu `GovernanceUnavailable`. Ista tehnika
# (patch na modul, ne na pozivno mesto) koju `_patch_openai_module` već koristi
# za Azure redirect. Ako ni `import openai` ne uspe, nijedan poziv ionako nije
# moguć — inherentno fail-closed.
_ai_blocked = False
_ai_block_reason: str | None = None
_ai_block_method: str | None = None
# Snimak originalnih konstruktora, da `_uninstall_prompt_guard()` može da vrati
# modul u prethodno stanje (v. C2 — testovi moraju moći da očiste za sobom).
_orig_openai_ctors: dict | None = None


class GovernanceUnavailable(RuntimeError):
    """AI granica je zatvorena jer governance sloj nije aktivan.

    Nasleđuje `RuntimeError` (ne `openai.APIError`) namerno: `shared/llm_retry.py`
    ponavlja samo provajderske greške, a ponavljanje ovoga bi bilo beskonačno
    petljanje oko stanja koje se ne menja samo od sebe.
    """


def governance_status() -> dict:
    """Stvarno stanje AI governance sloja, za health/verifikaciju.

    Ovo je jedina javna tvrdnja o tome da li su kontrole žive. Namerno vraća i
    razlog neuspeha — „nije aktivno" bez razloga ne može da se dijagnostikuje
    na produkciji gde se log možda ne čita.

    Wave 9: `ai_blocked` razdvaja dva bitno različita stanja koja su do sada
    oba izgledala kao `active=false`:

        active=false, ai_blocked=false → AI radi NEUPRAVLJANO (neprihvatljivo)
        active=false, ai_blocked=true  → guard nije aktivan, ali nijedan AI
                                         poziv ne može da se izvrši (fail-closed)
    """
    return {
        "attempted": _guard_patched,
        "active": _guard_active,
        "ai_blocked": _ai_blocked,
        "ai_block_method": _ai_block_method,
        "ai_block_reason": _ai_block_reason,
        "failure_reason": _guard_failure_reason,
    }


def _napravi_otrovnu_klasu(ime: str, poruka: str):
    """Vraća klasu koja pri konstrukciji diže `GovernanceUnavailable`.

    Zadržava originalno ime klase (`__name__`) da bi stack trace i log na
    produkciji i dalje pokazivali KOJI je klijent pokušan.
    """

    def __init__(self, *args, **kwargs):  # noqa: N807
        raise GovernanceUnavailable(poruka)

    return type(ime, (object,), {"__init__": __init__, "_vindex_poisoned": True})


def _install_ai_kill_switch(razlog: str) -> None:
    """Zatvara AI granicu kada instalacija guard-a nije uspela.

    Best-effort po dizajnu NIJE opcija ovde: ako i ovaj korak padne, to se
    zapisuje kao poseban razlog u `governance_status()` i loguje kao CRITICAL,
    jer tada AI granica OSTAJE otvorena i to mora da bude vidljivo spolja.
    """
    global _ai_blocked, _ai_block_reason, _ai_block_method, _orig_openai_ctors

    poruka = (
        "AI pozivi su zaustavljeni jer AI governance sloj nije aktivan "
        f"({razlog}). Ovo je namerna fail-closed brana, ne kvar provajdera."
    )

    try:
        import openai
    except Exception as exc:
        # Ako `import openai` ne uspe, nijedan AI poziv nije ni moguć — granica
        # je zatvorena samom nemogućnošću uvoza, ne našom branom.
        _ai_blocked = True
        _ai_block_method = "openai_uvoz_nemoguc"
        _ai_block_reason = (
            f"{razlog}; `import openai` takođe nije uspeo ({type(exc).__name__}) — "
            "nijedan AI poziv nije ni moguć"
        )
        logger.error("[AI_GUARD] %s", _ai_block_reason)
        return

    try:
        _orig_openai_ctors = {
            ime: getattr(openai, ime, None)
            for ime in ("OpenAI", "AsyncOpenAI", "AzureOpenAI", "AsyncAzureOpenAI")
        }
        # Azure parnjaci su OBAVEZNI, ne kozmetika: `langchain_openai`
        # (chat_models/azure.py:690, embeddings/azure.py:210, llms/azure.py:179)
        # konstruiše preko `openai.AzureOpenAI` / `openai.AsyncAzureOpenAI`, pa
        # bi otrov samo nad `OpenAI`/`AsyncOpenAI` ostavio živu zaobilaznicu.
        for ime in ("OpenAI", "AsyncOpenAI", "AzureOpenAI", "AsyncAzureOpenAI"):
            if getattr(openai, ime, None) is not None:
                setattr(openai, ime, _napravi_otrovnu_klasu(ime, poruka))
        _ai_blocked = True
        _ai_block_method = "otrovane_klijent_klase"
        _ai_block_reason = razlog
        logger.error(
            "[AI_GUARD] FAIL-CLOSED: guard nije aktivan (%s) — AI granica je "
            "zatvorena, konstrukcija OpenAI/Azure klijenta sada diže "
            "GovernanceUnavailable. Ostatak aplikacije radi normalno.",
            razlog,
        )
    except Exception as exc:
        _ai_blocked = False
        _ai_block_method = None
        _ai_block_reason = (
            f"{razlog}; instalacija fail-closed brane NIJE uspela "
            f"({type(exc).__name__}) — AI granica je OTVORENA"
        )
        logger.critical("[AI_GUARD] %s", _ai_block_reason)


def _restore_openai_ctors() -> None:
    """Vraća `openai.*` konstruktore na stanje pre fail-closed brane."""
    global _orig_openai_ctors, _ai_blocked, _ai_block_reason, _ai_block_method
    if _orig_openai_ctors:
        try:
            import openai
            for ime, klasa in _orig_openai_ctors.items():
                if klasa is not None:
                    setattr(openai, ime, klasa)
        except Exception as exc:  # pragma: no cover — samo dijagnostika
            logger.warning("[AI_GUARD] vraćanje openai konstruktora nije uspelo: %s", exc)
    _orig_openai_ctors = None
    _ai_blocked = False
    _ai_block_reason = None
    _ai_block_method = None


def _patch_openai_module() -> None:
    """
    Monkey-patchuje openai.OpenAI i openai.AsyncOpenAI da koriste Azure
    ako su Azure env var-ovi postavljeni. Mora se pozvati pre svih router importa.
    """
    global _patched
    if _patched:
        return

    azure_key      = os.getenv("AZURE_OPENAI_KEY", "").strip()
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()

    if not (azure_key and azure_endpoint):
        logger.info("[AI] Koristi standardni OpenAI API")
        _patched = True
        return

    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    endpoint    = azure_endpoint.rstrip("/")

    try:
        import openai
        from openai import AzureOpenAI as _AzSync, AsyncAzureOpenAI as _AzAsync

        class _PatchedSync(_AzSync):
            def __init__(self, api_key=None, **kwargs):
                super().__init__(
                    api_key=azure_key,
                    azure_endpoint=endpoint,
                    api_version=api_version,
                )

        class _PatchedAsync(_AzAsync):
            def __init__(self, api_key=None, **kwargs):
                super().__init__(
                    api_key=azure_key,
                    azure_endpoint=endpoint,
                    api_version=api_version,
                )

        openai.OpenAI      = _PatchedSync
        openai.AsyncOpenAI = _PatchedAsync

        logger.info("[AI] Azure OpenAI aktivan — endpoint: %s  version: %s", endpoint, api_version)

    except Exception as exc:
        logger.error("[AI] Patch neuspešan, koristim standardni OpenAI: %s", exc)

    _patched = True


def _extract_user_text(messages) -> str:
    """
    Spaja tekst svih 'user'-role poruka iz messages liste.

    ⚠️ ULOGA NIJE NIVO POVERENJA. Raniji docstring ovde je tvrdio da su
    „'system' poruke poverljive instrukcije koje autor rute kontroliše, ne
    korisnik/dokument". Ta tvrdnja je bila NETACNA i bila je korenski uzrok
    N1-NEW-3: `main.py` je slobodan tekst kancelarijske memorije prependovao
    u system prompt, pa je user-controlled sadrzaj zavrsavao u ulozi koju
    guard po definiciji preskace.

    Reprodukovano nad produkcijom `b0d074f0`:
        napad u tekstu koji guard analizira : False
        analyze(system_prompt).blocked      : True   <- da je gledao, blokirao bi
        pozicija napada u system poruci     : index 74 od 6139

    Poreklo se zato vise NE izvodi iz uloge. T3 sadrzaj nosi registrovanu
    granicu (v. `security.prompt_guard.razdvoji_po_poreklu`), a T1 sloj vise
    ne sme da primi user-controlled tekst (v. `_fetch_firm_memory_context`).

    Podržava i string i multimodalni (lista content-parts) format poruke.
    """
    if not messages:
        return ""
    parts: list[str] = []
    for m in messages:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
        if role != "user":
            continue
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", "") or "")
    return "\n".join(p for p in parts if p)


def _odluka_po_poreklu(text: str, _analiziraj, kanal: str):
    """SEC-003 odluka razdvojena po POREKLU, ne po ulozi.

    TARGET-2. SEC-003 se ne ukida, ne slabi globalno i ne zaobilazi -- dobija
    precizniji ugovor:

        T2  direktna korisnicka instrukcija -> analizira se, BLOKIRA
        T3  nepoverljiv dokaz u registrovanoj granici -> NE blokira se,
            ali ni ne dobija instrukcioni autoritet; belezi se

    Razlika koja je sustinska: T3 ne postaje POVERLJIV. T3 samo nema
    instrukcioni autoritet. Model sme da ga cita i pravno analizira; ne sme da
    izvrsi ono sto u njemu pise. Autoritet drzi `granica_autoriteta()` u
    system poruci, koju napadac ne moze da dosegne.

    Granica se priznaje SAMO ako je registrovana u ovom kontekstu, iz koda.
    Tekst koji samo lici na granicu ostaje T2 i ide na punu analizu -- pa
    napadac ne moze da sam sebi dodeli status dokaza.

    Vraca `(rezultat_ili_None, t3_nalazi)`. Rezultat != None znaci BLOKADA.
    """
    from security.prompt_guard import razdvoji_po_poreklu

    t2, t3 = razdvoji_po_poreklu(text)
    nalazi = []
    for oznaka, deo in t3:
        if not (deo or "").strip():
            continue
        r3 = _analiziraj(deo)
        if r3.blocked:
            # NIJE blokada: sadrzaj je izolovan i bez autoriteta. Zato se ovde
            # NE sme upisati „injection blocked" -- to bi bila lazna tvrdnja o
            # ishodu. Belezi se sto jeste: izolovan pokusaj u dokaznom sadrzaju.
            nalazi.append({"oznaka": oznaka.rsplit("_", 1)[0],
                           "score": round(float(r3.risk_score), 3)})
            logger.warning(
                "[AI_GUARD] T3 IZOLOVAN (%s) kanal=%s oznaka=%s score=%.2f — "
                "sadrzaj ide modelu kao PODATAK, bez instrukcionog autoriteta",
                kanal, _caller_hint(), nalazi[-1]["oznaka"], r3.risk_score,
            )
    if t2.strip():
        r2 = _analiziraj(t2)
        if r2.blocked:
            logger.warning(
                "[AI_GUARD] BLOCKED (%s) caller=%s score=%.2f flags=%d",
                kanal, _caller_hint(), r2.risk_score, len(r2.flags),
            )
            return r2, nalazi
    return None, nalazi


def _caller_hint(depth: int = 2) -> str:
    # Dijagnostika: koji fajl/funkcija je pozvao create() — korisno u
    # logovima kad se poziv blokira, s obzirom da patch ne zna koja je
    # ruta u pitanju (to je upravo poenta — ne zavisi od pozivnog mesta).
    # Mission Atlas (2026-08-03): isti mehanizam sada služi i kao automatski
    # 'module_name'/'operation_name' za AI Provenance kad pozivno mesto nije
    # eksplicitno postavilo shared/ai_provenance.py's case_context().
    try:
        frame = inspect.stack()[depth]
        return f"{frame.filename.split(os.sep)[-1]}:{frame.function}:{frame.lineno}"
    except Exception:
        return "unknown"


def _process_provider_name() -> str:
    """Provajder na nivou PROCESA ('azure' ako je Azure redirect aktivan).

    Manje precizno od `_client_provider_name(self)`, koji čita stvarnog
    roditeljskog klijenta — ali `_enforce_response(kwargs, response)` nema
    `self`, a njegov potpis je zaključan tvrdnjom u
    `tests/test_gov2_runtime_interception.py::test_e_...` (broji tačan tekst
    `return _enforce_response(kwargs, response)`). Po-pozivni identitet
    provajdera ionako već postoji u AI Provenance redu, koji `self` ima.
    """
    if os.getenv("AZURE_OPENAI_KEY", "").strip() and os.getenv("AZURE_OPENAI_ENDPOINT", "").strip():
        return "azure"
    return "openai"


def _client_provider_name(self) -> str:
    """'azure' ako je resurs vezan za AzureOpenAI/AsyncAzureOpenAI klijenta,
    inace 'openai' — cita se preko resursa._client, standardni openai SDK
    atribut (Completions/Embeddings instanca uvek drzi referencu na svog
    roditeljskog klijenta)."""
    try:
        client = getattr(self, "_client", None)
        if client is not None and "Azure" in type(client).__name__:
            return "azure"
    except Exception:
        pass
    return "openai"


# Mission Atlas (2026-08-03): _orig_create/_orig_acreate/_orig_embed/
# _orig_aembed su namerno modulskog nivoa (ne closure lokali unutar
# _patch_prompt_guard) da bi testovi mogli da ih monkeypatch-uju direktno
# (unittest.mock.patch("shared.ai_client._orig_create", ...)) i simuliraju
# uspesan odgovor bez pravog mrežnog poziva — bez ovoga, provenance-capture
# logika (koja treba PRAVI response objekat da izvuce model/tokene/sadržaj)
# ne bi bila testabilna bez stvarnog OpenAI pristupa.
_orig_create = None
_orig_acreate = None
_orig_embed = None
_orig_aembed = None
# Wave 9 (C2): audio originali su ranije bili lokali unutar `_patch_prompt_guard`,
# pa ih `_uninstall_prompt_guard()` nije mogao vratiti — teardown bi ostavio
# audio klase trajno obavijene i sledeći patch bi ih obavio drugi put.
_orig_stt = None
_orig_astt = None
_orig_tts = None
_orig_atts = None

# Wave 11 (G1) — ULAZNI GUARD SE MERI POSLEDICOM, NE OPALJIVANJEM.
#
# `security.prompt_guard.analyze` je bio uvezen JEDNOM i vezan u zatvorenju
# wrappera (`from ... import analyze as _analyze`, pa `result = _analyze(text)`).
# Posledica je izmerena, ne pretpostavljena: nijedan test nije mogao da zameni
# analizator špijunom a da pritom ne deinstalira ceo guard. Zato su sve dosadašnje
# tvrdnje bile posredne — „injection nije stigao do provajdera", što bi bilo
# tačno i da poziv nije stigao dotle iz nekog sasvim drugog razloga (pad u
# `_extract_user_text`, izuzetak pre `_orig_create`, pogrešno postavljen mok).
# Negativna kontrola (benigni tekst prolazi) sužava tu rupu, ali je ne zatvara.
#
# Rešenje je JEDAN nivo indirekcije, isti onaj koji `_orig_create` već ima i
# zbog kog je on testabilan (v. komentar iznad): modulska referenca koju wrapper
# čita PRI SVAKOM pozivu. Nije uveden novi mehanizam — primenjen je postojeći.
#
# INDIREKCIJA NE SME DA POSTANE RUPA. Prazna referenca NIJE dozvola da poziv
# prođe neproveren. `_dohvati_analizator()` ispod definiše tačno dva ishoda:
# analizator postoji (poziv se PROVERAVA) ili ga nigde nema (poziv se ODBIJA,
# `GovernanceUnavailable`). Trećeg ishoda — „nema analizatora, pusti dalje" —
# nema, i `tests/test_wave11_guard_and_provenance.py::test_g1_c1/c2` mere baš to.
_analyze_ref = None


def _dohvati_analizator():
    """Analizator za TEKUĆI poziv, ili `None` ako ga nigde nema.

    Redosled je namerno ovakav:

      1. modulska referenca `_analyze_ref` — postavlja je `_patch_prompt_guard`,
         i ona je jedina tačka koju test može da zameni špijunom (G1);
      2. ako je prazna — JEDAN pokušaj kanonskog uvoza.

    ZAŠTO KORAK 2 POSTOJI, IZMERENO A NE PRETPOSTAVLJENO. Prva verzija ove
    izmene je imala samo korak 1 i odbijala svaki poziv na praznoj referenci.
    Posledica: 12 dotad zelenih testova je palo sa `GovernanceUnavailable`
    (`test_wave9_governance.py::test_c3_*`, ceo `test_gov3_response_firewall.py`,
    `test_gov2_runtime_interception.py::test_c/test_ng`). Uzrok NIJE test-šum
    nego stvarna fragilnost koju bi izmena unela u produkcioni modul:
    `_uninstall_prompt_guard()` čisti referencu, a `Completions.create` je
    OBJEKAT koji pozivalac može nezavisno da snimi i vrati — što dve fixture u
    repou i rade, po obrascu koji docstring `_uninstall_prompt_guard()`-a
    izričito blagosilja. Wrapper se tako vrati na klasu bez svoje reference i
    AI granica ostane mrtva do kraja procesa, bez ijedne poruke o razlogu.
    To je ista klasa kvara (stanje raspoređeno na dva mesta koja se mogu
    razići) koju Wave 4 i Wave 9 već jednom čiste u ovom fajlu.

    KORAK 2 NIJE OMEKŠAVANJE. Bezbednosna tvrdnja je „nijedan neproveren poziv
    ne prolazi", a ne „referenca mora biti popunjena". Kroz korak 2 poziv i
    dalje ide kroz `security.prompt_guard.analyze` — dakle proveren je. Ako ni
    uvoz ne uspe (modul pokvaren, ciklična zavisnost, obrisan `analyze`),
    analizatora nema i poziv se ODBIJA.

    Rezultat se NAMERNO ne kešira nazad u `_analyze_ref`: referenca mora da
    ostane verno ogledalo onoga što je `_patch_prompt_guard`/
    `_uninstall_prompt_guard` u nju upisao, inače bi „počisti referencu" bila
    tvrdnja koja se sama poništava pri prvom sledećem pozivu.
    """
    if _analyze_ref is not None:
        return _analyze_ref
    try:
        from security.prompt_guard import analyze as _a
        return _a
    except Exception as exc:
        logger.error(
            "[AI_GUARD] ulazni analizator nije dostupan (%s) — poziv će biti odbijen",
            type(exc).__name__,
        )
        return None


def _capture_chat_provenance(self, kwargs: dict, response, latency_ms: int, error: Exception | None = None) -> None:
    """Gradi i (fire-and-forget, fail-soft) upisuje provenance zapis za JEDAN
    chat.completions.create poziv. Nikad ne baca — greška ovde ne sme
    da utiče na AI poziv koji je vec zavrsen (uspesno ili neuspesno)."""
    try:
        import asyncio
        from shared import ai_provenance as _prov
        from security.ai_forensics import log_provenance_from_wrapper

        ctx = _prov.current_context()
        messages = kwargs.get("messages") or []
        system_text = "\n".join(
            (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""
            for m in messages
            if (m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) == "system"
        )
        user_text = _extract_user_text(messages)

        output_text = None
        token_in = token_out = None
        model_reported = kwargs.get("model")
        if response is not None:
            try:
                output_text = (response.choices[0].message.content or "") if response.choices else ""
            except Exception:
                output_text = None
            usage = getattr(response, "usage", None)
            if usage is not None:
                token_in = getattr(usage, "prompt_tokens", None)
                token_out = getattr(usage, "completion_tokens", None)
            model_reported = getattr(response, "model", None) or model_reported

        record_kwargs = dict(
            module_name=ctx.get("module_name") or _caller_hint(depth=3),
            operation_name=ctx.get("operation_name"),
            model_provider=_client_provider_name(self),
            model_name=model_reported or "unknown",
            system_prompt_hash=_prov.sha256_text(system_text),
            user_prompt_hash=_prov.sha256_text(user_text),
            token_usage_input=token_in,
            token_usage_output=token_out,
            latency_ms=latency_ms,
            output_hash=_prov.sha256_text(output_text) if output_text else None,
            correlation_id=ctx.get("correlation_id") or _prov.new_correlation_id(),
            parent_event_id=ctx.get("parent_event_id"),
            user_id=ctx.get("user_id"),
            tenant_id=ctx.get("tenant_id"),
            predmet_id=ctx.get("predmet_id"),
            document_id=ctx.get("document_id"),
            knowledge_sources=ctx.get("knowledge_sources"),
            retrieved_context_ids=ctx.get("retrieved_context_ids"),
            retrieval_query=ctx.get("retrieval_query"),
            status="error" if error else "success",
            error_message=str(error)[:500] if error else None,
        )

        coro = log_provenance_from_wrapper(**record_kwargs)
        try:
            asyncio.get_running_loop()
            # S3-1 (2026-08-09): this was loop.create_task(coro) -- unreferenced,
            # so the AI provenance row could be garbage-collected before it was
            # written, and any failure inside log_provenance_from_wrapper was
            # never observed. The audit trail was written through the exact
            # pattern S1-1 exists to remove, which means every coverage figure
            # for AI auditing was conditional on tasks nobody was holding.
            from shared.bg import spawn as _spawn_bg
            _spawn_bg(coro, name="ai_provenance:write")
        except RuntimeError:
            asyncio.run(coro)
    except Exception as exc:
        logger.debug("[AI_PROVENANCE] capture greška (nije kritično): %s", exc)


def _capture_embedding_provenance(self, kwargs: dict, response, latency_ms: int, error: Exception | None = None) -> None:
    """Isto kao _capture_chat_provenance, za Embeddings.create — nema
    system/user razdvajanje ni izlazni tekst (vektor nije 'odgovor' u istom
    smislu), pa se hashuje ulazni tekst i broje tokeni ako su dostupni."""
    try:
        import asyncio
        from shared import ai_provenance as _prov
        from security.ai_forensics import log_provenance_from_wrapper

        ctx = _prov.current_context()
        input_val = kwargs.get("input")
        input_text = input_val if isinstance(input_val, str) else "\n".join(str(x) for x in (input_val or []))

        token_in = None
        model_reported = kwargs.get("model")
        if response is not None:
            usage = getattr(response, "usage", None)
            if usage is not None:
                token_in = getattr(usage, "prompt_tokens", None)
            model_reported = getattr(response, "model", None) or model_reported

        coro = log_provenance_from_wrapper(
            module_name=ctx.get("module_name") or _caller_hint(depth=3),
            operation_name=ctx.get("operation_name") or "embedding",
            model_provider=_client_provider_name(self),
            model_name=model_reported or "unknown",
            user_prompt_hash=_prov.sha256_text(input_text),
            token_usage_input=token_in,
            latency_ms=latency_ms,
            correlation_id=ctx.get("correlation_id") or _prov.new_correlation_id(),
            parent_event_id=ctx.get("parent_event_id"),
            user_id=ctx.get("user_id"),
            tenant_id=ctx.get("tenant_id"),
            predmet_id=ctx.get("predmet_id"),
            document_id=ctx.get("document_id"),
            retrieval_query=ctx.get("retrieval_query"),
            status="error" if error else "success",
            error_message=str(error)[:500] if error else None,
        )
        try:
            asyncio.get_running_loop()
            # S3-1 (2026-08-09): this was loop.create_task(coro) -- unreferenced,
            # so the AI provenance row could be garbage-collected before it was
            # written, and any failure inside log_provenance_from_wrapper was
            # never observed. The audit trail was written through the exact
            # pattern S1-1 exists to remove, which means every coverage figure
            # for AI auditing was conditional on tasks nobody was holding.
            from shared.bg import spawn as _spawn_bg
            _spawn_bg(coro, name="ai_provenance:write")
        except RuntimeError:
            asyncio.run(coro)
    except Exception as exc:
        logger.debug("[AI_PROVENANCE] embedding capture greška (nije kritično): %s", exc)


# ── S1-2 (2026-08-09): default per-request timeout ─────────────────────────
# 111 OpenAI/AsyncOpenAI constructions exist in application code and NOT ONE
# sets `timeout=` (verified by grep). The installed SDK's default is
# Timeout(connect=5, read=600) with max_retries=2 -- so one logical call could
# occupy up to 3 x 600s of wall time before @llm_retry even began its own 3
# attempts.
#
# That matters more here than it would elsewhere: production runs ONE uvicorn
# process (measured -- 24/24 parallel /health requests, same pid, workers:1),
# and the sync GPT calls are dispatched through asyncio.to_thread into the
# default executor, which is the SAME pool the ~1,500 Supabase call sites use.
# A degraded provider could therefore hold every worker thread and stop the app
# from serving anything at all.
#
# Applied HERE rather than at the 111 construction sites: every call already
# funnels through this patch, so one edit covers all of them and cannot be
# missed by a new call site added later.
#
# Overridable per call -- an explicit timeout= in kwargs always wins, so a
# deliberately long-running call can still opt out.
_DEFAULT_LLM_TIMEOUT_S = float(os.getenv("VINDEX_LLM_TIMEOUT_S", "60"))


def _with_timeout(kwargs: dict) -> dict:
    if "timeout" not in kwargs or kwargs.get("timeout") is None:
        kwargs["timeout"] = _DEFAULT_LLM_TIMEOUT_S
    return kwargs


def _patch_prompt_guard() -> None:
    """
    SEC-003 — presreće Completions.create/AsyncCompletions.create na nivou
    KLASE (ne instance), pre bilo kog OpenAI/AsyncOpenAI konstruktora u
    aplikaciji. Svaki od ~130 pozivnih mesta u api.py/routers//services/
    prolazi kroz ovu proveru, bez obzira da li je to pozivno mesto ikad
    čulo za security/prompt_guard.py.

    Ako je 'user'-role sadržaj poziva iznad BLOCK_THRESHOLD (security/
    prompt_guard.py::analyze), poziv OpenAI-u se NIKAD ne izvršava —
    PromptInjectionBlocked se podiže pre _orig_create/_orig_acreate.

    Mission Atlas (2026-08-03): isti presretnuti sloj sada dodatno beleži AI
    Provenance (shared/ai_provenance.py + security/ai_forensics.py) na SVAKI
    poziv koji stigne do OpenAI-a — isti "jedan ulaz, jedna implementacija"
    princip kao SEC-003, primenjen na sledljivost umesto bezbednosti. Ovo je
    NAMERNO isti patch point, ne paralelan mehanizam.
    """
    global _guard_patched, _guard_active, _guard_failure_reason
    global _orig_create, _orig_acreate, _orig_embed, _orig_aembed
    global _orig_stt, _orig_astt, _orig_tts, _orig_atts
    global _analyze_ref
    if _guard_patched:
        return

    # Wave 9 (§8): SVI uvozi od kojih zavisi chat guard su u JEDNOM try bloku.
    # Ranije je samo uvoz SDK klasa bio zaštićen; da je `security.prompt_guard`
    # ili `security.response_firewall` pukao (sintaksna greška, ciklična
    # zavisnost), izuzetak bi propagirao iz `_patch_prompt_guard()` koji se zove
    # na nivou modula u `api.py:28` — i oborio ceo uvicorn na uvozu. Sada je
    # ishod isti kao za bilo koji drugi neuspeh guard-a: fail-closed na AI
    # granici, ostatak aplikacije radi.
    try:
        from openai.resources.chat.completions.completions import (
            AsyncCompletions,
            Completions,
        )
        from security.prompt_guard import PromptInjectionBlocked
        from security.prompt_guard import analyze as _analyze
        # Governance Wave 3 — CANONICAL RESPONSE FIREWALL (v. komentar niže).
        from security.response_firewall import enforce as _fw_enforce
    except Exception as exc:
        logger.error("[AI_GUARD] Nisam mogao da uvezem governance zavisnosti, guard NIJE aktivan: %s", exc)
        # `_guard_patched = True` sprečava beskonačno ponavljanje pokušaja.
        # `_guard_active` OSTAJE False — to je jedina tvrdnja koja sme da kaže
        # da li kontrole rade. Razdvajanje je uvedeno u Wave 4 jer je jedna
        # promenljiva ranije tvrdila oboje, pa je neuspeh izgledao kao uspeh.
        _guard_patched = True
        _guard_active = False
        _guard_failure_reason = f"import governance zavisnosti nije uspeo: {type(exc).__name__}"
        # Wave 9: OVDE je razlika u odnosu na Wave 4. Ranije se ovde samo
        # vraćalo i aplikacija je nastavljala da izvršava AI pozive bez ijedne
        # kontrole. Sada se AI granica zatvara.
        _install_ai_kill_switch(_guard_failure_reason)
        return

    # Wave 11 (G1): referenca se postavlja ODMAH po uspešnom uvozu, PRE provere
    # idempotencije ispod. Da stoji niže, putanja „klase su već obavijene →
    # ranije se vrati" ostavila bi referencu praznom, a wrapperi koji na klasama
    # već stoje bi od tog trenutka odbijali svaki poziv. Ovde je invarijanta
    # prosta i doslovna: ako je uvoz prošao, analizator je dostupan.
    _analyze_ref = _analyze

    # Wave 9 (C2) — STRUKTURNA IDEMPOTENCIJA.
    #
    # `_guard_patched` je bila JEDINA brana protiv dvostrukog patch-ovanja. To
    # nije bila hipoteza nego izmeren kvar: test fixture je resetovao samo
    # zastavice, pa je drugi poziv patch-ovao VEĆ PATCH-OVANE klase —
    # `_orig_create` je postao već-obavijen `_guarded_create`, wrapper se
    # ugnezdio u samog sebe i oborio `tests/test_uploaded_doc_api.py`.
    #
    # Zastavica je tvrdnja O NAMERI. Atribut na samoj metodi je tvrdnja O
    # STANJU — i ostaje tačan i kada neko zaobiđe zastavicu.
    if getattr(Completions.create, "_vindex_guarded", False):
        # Guard JESTE aktivan (wrapper stoji na klasi), pa fail-closed brana —
        # ako je neki raniji pokušaj nju instalirao — više nema osnov i mora se
        # skloniti. Bez ovoga bi uspešan guard ostao sa otrovanim
        # konstruktorima i AI bi bio mrtav bez razloga.
        if _ai_blocked:
            _restore_openai_ctors()
        _guard_patched = True
        _guard_active = True
        _guard_failure_reason = None
        logger.debug("[AI_GUARD] chat klase su već obavijene — preskačem (bez ugnežđivanja)")
        return

    # Governance Wave 3 — CANONICAL RESPONSE FIREWALL.
    #
    # Ulazna strana (SEC-003) štiti šta ODLAZI provajderu. Do sada ništa nije
    # proveravalo šta se VRAĆA: izlazna kontrola je pokrivala 2 od 93
    # produkcione AI putanje (`main.py::_proveri_halucinaciju`, samo RAG).
    #
    # Firewall se veže ovde, a ne na 93 pojedinačna mesta, iz jednog merenog
    # razloga: zamenjuje se metoda SDK KLASE, pa i direktan
    # `client.chat.completions.create(...)` iz proizvoljnog fajla prolazi kroz
    # wrapper. Nema pozivnog mesta koje ga može slučajno preskočiti.
    #
    # NE pokriva: sirov WebSocket (`services/voice_orchestrator.py`) i Cohere
    # SDK (`app/services/retrieve.py`). Te dve putanje ga mogu zaobići i to je
    # deo ugovora, ne propust — v. `security/response_firewall.py`.
    # (`from security.response_firewall import enforce` je izvršen gore, u
    # zajedničkom fail-closed try bloku.)

    def _enforce_response(kwargs, response):
        """Primeni firewall, sa identitetom iz već postojećeg konteksta.

        `correlation_id` i `user_id` se čitaju iz `shared/ai_provenance`, koji
        je isti izvor koji `_capture_chat_provenance` već koristi — bez novog
        mehanizma i bez novog izvora istine.

        Wave 9 (C3) — ISPRAVKA IZMERENE GREŠKE: `user_id` se čitao preko
        `_prov.current_request_context()`, funkcije koja u
        `shared/ai_provenance.py` NE POSTOJI. `hasattr` je tiho vraćao False,
        pa je `uid` bio None na SVAKOM pozivu — uključujući potpuno
        autentifikovane zahteve. Posledica: firewall je svaki odgovor
        proglašavao ESCALATE („user_id nedostaje"), pa je degradacija bila
        konstantna i time bezvredna kao signal, a nijedan audit zapis nije
        mogao da se pripiše korisniku. Ispravan izvor je `current_context()`,
        koji spaja request i case kontekst — isti dict iz kog
        `_capture_chat_provenance` već čita `user_id` (`:227`).
        """
        cid = None
        uid = None
        try:
            import shared.ai_provenance as _prov
            _ctx = _prov.current_context() or {}
            cid = _ctx.get("correlation_id")
            uid = _ctx.get("user_id")
        except Exception:
            # Nedostatak identiteta je DEGRADACIJA, ne razlog za rušenje poziva —
            # firewall to prijavljuje kao ESCALATE. Zato ova grana sme da bude
            # tolerantna, za razliku od same provere odgovora.
            pass
        return _fw_enforce(
            response,
            kwargs=kwargs,
            operation=_caller_hint(),
            provider=_process_provider_name(),
            model=(kwargs or {}).get("model", ""),
            correlation_id=cid,
            user_id=uid,
        )

    _orig_create = Completions.create
    _orig_acreate = AsyncCompletions.create

    def _guarded_create(self, *args, **kwargs):
        # Wave 11 (G1): analizator se razrešava PRI SVAKOM pozivu, kroz
        # `_dohvati_analizator()` (v. njegov docstring). Nema analizatora →
        # nema poziva. `GovernanceUnavailable` je namerno isti tip koji ovaj
        # modul već koristi za zatvorenu AI granicu (nasleđuje `RuntimeError`,
        # pa ga `shared/llm_retry.py` ne ponavlja u krug).
        _analiziraj = _dohvati_analizator()
        if _analiziraj is None:
            raise GovernanceUnavailable(
                "Ulazni prompt guard nije dostupan — poziv je odbijen pre nego "
                "što je ijedan token poslat provajderu. Ovo je namerna "
                "fail-closed brana, ne kvar provajdera."
            )
        text = _extract_user_text(kwargs.get("messages"))
        if text:
            result, _ = _odluka_po_poreklu(text, _analiziraj, "sync")
            if result is not None:
                raise PromptInjectionBlocked(result.risk_score, result.flags)
        import time
        _t0 = time.monotonic()
        try:
            response = _orig_create(self, *args, **_with_timeout(kwargs))
        except Exception as exc:
            _capture_chat_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000), error=exc)
            raise
        # BETA-HARDENING-001 / FS-004 — PROVENANCE JE TVRDIO USPEH ZA ODBIJEN ODGOVOR.
        #
        # Redosled je bio: `_capture_chat_provenance(... uspeh ...)` pa tek onda
        # `_enforce_response(...)`. Kad response firewall odbije odgovor
        # (neispravan JSON, prazan sadrzaj, `content=None`, prazna lista izbora,
        # odbijanje provajdera), pozivalac dobije izuzetak -- a jedini forenzicki
        # trag o tom pozivu kaze `status="success"`.
        #
        # Za pravnu aplikaciju to je najgora vrsta netacnosti: revizija bi
        # pokazala uspesan AI poziv tamo gde korisnik nije dobio nista.
        #
        # Sada se provenance upisuje TEK kad se zna ishod provere, i to u obe
        # grane -- odbijen odgovor se belezi kao greska, ne kao uspeh.
        _ms = int((time.monotonic() - _t0) * 1000)
        try:
            _provereno = _enforce_response(kwargs, response)
        except Exception as _exc_fw:
            _capture_chat_provenance(self, kwargs, response, _ms, error=_exc_fw)
            raise
        _capture_chat_provenance(self, kwargs, response, _ms)
        return _provereno

    async def _guarded_acreate(self, *args, **kwargs):
        # Ista indirekcija i ista fail-closed brana kao u sync grani — async
        # putanja ne sme da bude slabija od sync putanje, jer je u ovom repou
        # brojnija (`AsyncOpenAI` je podrazumevani klijent u rutama).
        _analiziraj = _dohvati_analizator()
        if _analiziraj is None:
            raise GovernanceUnavailable(
                "Ulazni prompt guard nije dostupan — poziv je odbijen pre nego "
                "što je ijedan token poslat provajderu. Ovo je namerna "
                "fail-closed brana, ne kvar provajdera."
            )
        text = _extract_user_text(kwargs.get("messages"))
        if text:
            import asyncio
            # `_odluka_po_poreklu` cita `ContextVar` registar; `to_thread`
            # kopira kontekst pozivaoca, pa registar ostaje vidljiv.
            result, _ = await asyncio.to_thread(
                _odluka_po_poreklu, text, _analiziraj, "async")
            if result is not None:
                raise PromptInjectionBlocked(result.risk_score, result.flags)
        import time
        _t0 = time.monotonic()
        try:
            response = await _orig_acreate(self, *args, **_with_timeout(kwargs))
        except Exception as exc:
            _capture_chat_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000), error=exc)
            raise
        # Ista ispravka kao u sync grani (FS-004): async putanja ne sme da bude
        # slabija, a u ovom repou je brojnija.
        _ms = int((time.monotonic() - _t0) * 1000)
        try:
            _provereno = _enforce_response(kwargs, response)
        except Exception as _exc_fw:
            _capture_chat_provenance(self, kwargs, response, _ms, error=_exc_fw)
            raise
        _capture_chat_provenance(self, kwargs, response, _ms)
        return _provereno

    # Wave 9 (C2): marker STANJA na samim wrapperima. `_guard_patched` opisuje
    # nameru i može se resetovati spolja; ovo se ne može, jer živi na objektu
    # koji je zaista postavljen na SDK klasu.
    _guarded_create._vindex_guarded = True
    _guarded_acreate._vindex_guarded = True

    Completions.create = _guarded_create
    AsyncCompletions.create = _guarded_acreate

    try:
        from openai.resources.embeddings import AsyncEmbeddings, Embeddings

        if getattr(Embeddings.create, "_vindex_guarded", False):
            raise RuntimeError("embeddings su već obavijeni — ne ugnežđujem")

        _orig_embed = Embeddings.create
        _orig_aembed = AsyncEmbeddings.create

        # ── Wave 9 (C5): embeddings grana je bila JEDINA bez `_with_timeout` ──
        # Chat (`:642`) i audio (`:737,:749`) su prosleđivali podrazumevani
        # timeout; embeddings nije, pa je za njih važio SDK default
        # (read=600s, max_retries=2 → do 3×600s zauzeća niti po jednom
        # logičkom pozivu). To je ista rupa zbog koje S1-2 postoji, samo na
        # putanji koja se izvršava na SVAKI upload dokumenta i SVAKI RAG upit.
        #
        # ULAZNI GUARD NAMERNO NIJE DODAT. Embeddings ulaz je tekst pravnog
        # dokumenta koji se pretvara u vektor — model ne izvršava instrukcije
        # iz njega, nema izlaza koji bi injection mogao da preusmeri. Blokiranje
        # po injection score-u bi obaralo legitimno indeksiranje: pravni
        # podnesci, presude i ugovori prirodno sadrže citirane naredbe
        # („zanemari prethodno navedeno", „postupi po nalogu suda"), a
        # `security/prompt_guard.py` ih ocenjuje po obrascu, ne po nameri.
        # Cena lažno pozitivnog je trajno neindeksiran dokaz u predmetu; korist
        # je nula, jer nema instrukcijskog kanala koji bi se zloupotrebio.
        # Ista logika zabranjuje i „firewall nad odgovorom": vektor nije
        # odgovor, nema `choices[0].message` oblik (v. test_e2 u
        # tests/test_gov2_runtime_interception.py).
        def _tracked_embed(self, *args, **kwargs):
            import time
            _t0 = time.monotonic()
            try:
                response = _orig_embed(self, *args, **_with_timeout(kwargs))
            except Exception as exc:
                _capture_embedding_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000), error=exc)
                raise
            _capture_embedding_provenance(self, kwargs, response, int((time.monotonic() - _t0) * 1000))
            return response

        async def _tracked_aembed(self, *args, **kwargs):
            import time
            _t0 = time.monotonic()
            try:
                response = await _orig_aembed(self, *args, **_with_timeout(kwargs))
            except Exception as exc:
                _capture_embedding_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000), error=exc)
                raise
            _capture_embedding_provenance(self, kwargs, response, int((time.monotonic() - _t0) * 1000))
            return response

        _tracked_embed._vindex_guarded = True
        _tracked_aembed._vindex_guarded = True
        Embeddings.create = _tracked_embed
        AsyncEmbeddings.create = _tracked_aembed
    except Exception as exc:
        logger.warning("[AI_PROVENANCE] Embeddings provenance patch neuspešan (nije kritično): %s", exc)

    # ── S2-1 (2026-08-09): audio.* was not intercepted at all ──────────────
    # The patch covered Completions and Embeddings. It did NOT cover
    # audio.transcriptions.create or audio.speech.create, which routers/voice.py
    # calls directly (_pozovi_whisper_api, _pozovi_tts_api). Those two produced
    # ZERO provenance rows and carried no default timeout -- a whole modality
    # outside the audit surface, invisible to every coverage count because the
    # inventory regex looked for chat/embedding call shapes.
    #
    # What this does and does not give you, stated precisely:
    #   * provenance + timeout: yes, both paths, success and failure.
    #   * prompt-guard on Whisper: NOT APPLICABLE -- the input is audio bytes,
    #     not text. Guarding the resulting TRANSCRIPT is response-side work and
    #     belongs to the Response Firewall question, not here.
    #   * prompt-guard on TTS input: the text is produced by our own code paths,
    #     which are themselves already guarded upstream.
    try:
        from openai.resources.audio.speech import AsyncSpeech, Speech
        from openai.resources.audio.transcriptions import AsyncTranscriptions, Transcriptions

        if getattr(Transcriptions.create, "_vindex_guarded", False):
            raise RuntimeError("audio klase su već obavijene — ne ugnežđujem")

        _orig_stt = Transcriptions.create
        _orig_astt = AsyncTranscriptions.create
        _orig_tts = Speech.create
        _orig_atts = AsyncSpeech.create

        def _make_tracked_audio(orig, is_async: bool):
            if is_async:
                async def _tracked(self, *args, **kwargs):
                    import time
                    _t0 = time.monotonic()
                    try:
                        response = await orig(self, *args, **_with_timeout(kwargs))
                    except Exception as exc:
                        _capture_embedding_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000), error=exc)
                        raise
                    _capture_embedding_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000))
                    return response
                _tracked._vindex_guarded = True
                return _tracked

            def _tracked(self, *args, **kwargs):
                import time
                _t0 = time.monotonic()
                try:
                    response = orig(self, *args, **_with_timeout(kwargs))
                except Exception as exc:
                    _capture_embedding_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000), error=exc)
                    raise
                _capture_embedding_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000))
                return response
            _tracked._vindex_guarded = True
            return _tracked

        Transcriptions.create      = _make_tracked_audio(_orig_stt,  False)
        AsyncTranscriptions.create = _make_tracked_audio(_orig_astt, True)
        Speech.create              = _make_tracked_audio(_orig_tts,  False)
        AsyncSpeech.create         = _make_tracked_audio(_orig_atts, True)
    except Exception as exc:
        logger.warning("[AI_PROVENANCE] Audio provenance patch neuspešan (nije kritično): %s", exc)

    # Tek OVDE su chat klase stvarno zamenjene. Embeddings/audio grane iznad su
    # namerno ne-kritične (`logger.warning`, nastavlja) — one nose provenance, ne
    # zaštitu, pa njihov neuspeh ne obara tvrdnju o aktivnom guard-u. Da nose
    # zaštitu, ovaj red bi morao da zavisi i od njih.
    # Wave 9: ako je raniji pokušaj zatvorio AI granicu (fail-closed brana), a
    # ovaj je uspeo, brana se MORA skloniti — inače bi uspešan guard i dalje
    # imao otrovane konstruktore i AI bi ostao mrtav bez razloga. Ovo je jedina
    # putanja koja sme da otvori granicu: aktivan guard.
    if _ai_blocked:
        logger.info("[AI_GUARD] guard je sada aktivan — sklanjam fail-closed branu sa AI granice")
        _restore_openai_ctors()

    _guard_patched = True
    _guard_active = True
    _guard_failure_reason = None
    logger.info(
        "[AI_GUARD] Prompt Guard presreo Completions.create/AsyncCompletions.create "
        "— svi GPT pozivi u aplikaciji sada strukturno zaštićeni (SEC-003) i "
        "beleže AI Provenance (Mission Atlas)"
    )


def _uninstall_prompt_guard() -> None:
    """Vraća SVE zamenjene SDK metode na originale i resetuje globalno stanje.

    ZAŠTO OVO POSTOJI U PRODUKCIONOM MODULU, A NE U TEST FIXTURE-U (C2):

    Fixture u `tests/test_gov4_patch_lifecycle.py` je prvo resetovao samo
    zastavice. Pošto je `_patch_prompt_guard()` idempotentan preko
    `_guard_patched`, drugi poziv je onda patch-ovao VEĆ PATCH-OVANE klase:
    `_orig_create` je postao već-obavijen `_guarded_create`, wrapper se ugnezdio
    u samog sebe, i to se prelilo na kasnije testove u istoj sesiji — oborilo je
    dva nevezana, dotad zelena testa u `tests/test_uploaded_doc_api.py`.

    Zaključak koji je ovde primenjen: fixture ne sme da mora da poznaje interne
    detalje modula (koje su tačno četiri klase patch-ovane, kojim redom, i šta
    je snimljeno gde). Modul koji zna da se instalira mora da zna i da se
    deinstalira. Strukturna idempotencija (`_vindex_guarded`) je druga polovina
    iste odluke: čak i ako neko zaobiđe i zastavicu i ovu funkciju, ugnežđivanje
    je nemoguće.

    Bezbedno je pozvati je i kada patch nikad nije instaliran.
    """
    global _guard_patched, _guard_active, _guard_failure_reason
    global _orig_create, _orig_acreate, _orig_embed, _orig_aembed
    global _orig_stt, _orig_astt, _orig_tts, _orig_atts
    global _analyze_ref

    def _vrati(uvoz_putanja: str, imena_klasa: tuple, originali: tuple) -> None:
        try:
            import importlib
            modul = importlib.import_module(uvoz_putanja)
            for ime_klase, original in zip(imena_klasa, originali):
                if original is None:
                    continue
                setattr(getattr(modul, ime_klase), "create", original)
        except Exception as exc:  # pragma: no cover — samo dijagnostika
            logger.warning("[AI_GUARD] deinstalacija (%s) nije uspela: %s", uvoz_putanja, exc)

    _vrati(
        "openai.resources.chat.completions.completions",
        ("Completions", "AsyncCompletions"),
        (_orig_create, _orig_acreate),
    )
    _vrati("openai.resources.embeddings", ("Embeddings", "AsyncEmbeddings"), (_orig_embed, _orig_aembed))
    _vrati("openai.resources.audio.transcriptions", ("Transcriptions", "AsyncTranscriptions"), (_orig_stt, _orig_astt))
    _vrati("openai.resources.audio.speech", ("Speech", "AsyncSpeech"), (_orig_tts, _orig_atts))

    _restore_openai_ctors()

    _orig_create = _orig_acreate = _orig_embed = _orig_aembed = None
    _orig_stt = _orig_astt = _orig_tts = _orig_atts = None
    # Wave 11 (G1): i referenca na analizator je deo instaliranog stanja, pa je
    # teardown mora počistiti. Ostavljena referenca ne bi bila bezopasna: modul
    # bi tvrdio `active=False` a i dalje držao živ pokazivač na kontrolu koja
    # više nigde ne stoji — tačno ona vrsta polovičnog stanja zbog koje
    # `_uninstall_prompt_guard()` uopšte postoji (v. docstring iznad).
    _analyze_ref = None
    _guard_patched = False
    _guard_active = False
    _guard_failure_reason = None
