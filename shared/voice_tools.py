# -*- coding: utf-8 -*-
"""
Vindex AI — shared/voice_tools.py

KORAK A: Vindex Live & Voice-to-Action (2026-07-24)

Alati koje glasovni agent (services/voice_orchestrator.py) može pozivati
tokom realtime sesije. Svaki alat ima:
  - JSON schema definiciju u OpenAI Realtime API function-calling formatu
    (VOICE_TOOLS, prosleđuje se u session.update).
  - Async handler koji STVARNO izvršava akciju (TOOL_METADATA[name]["handler"]).
  - "mutates_data" zastavicu koja određuje da li orkestrator mora da traži
    glasovnu/UI potvrdu korisnika (Human-in-the-Loop) PRE izvršenja — v.
    services/voice_orchestrator.py::_handle_function_call.

Svaki handler NIKAD ne baca: greška se vraća kao {"ok": False, "error": ...}
i čita se korisniku naglas — isti fail-soft obrazac kao ostatak Vindex-a
(RAG retrieval, OCR, itd.). LLM pozivi koje ovi alati posredno pokreću
(drafting.router.generate_draft's _call_openai) su već @llm_retry-zaštićeni
na izvoru — ne duplira se ovde.
"""
import asyncio
import logging
from typing import Optional

from security.html_sanitize import sanitize_user_input
from shared.sentry import capture_exception as _sentry_capture

logger = logging.getLogger("vindex.voice_tools")


# ─── Tool schemas (OpenAI Realtime API function-calling format) ────────────

VOICE_TOOLS: list[dict] = [
    {
        "type": "function",
        "name": "pretraga_prakse_i_zakona",
        "description": (
            "Pretraži srpske zakone i sudsku praksu (RAG pretraga nad Pinecone "
            "indeksom). Koristi za svako pravno pitanje koje zahteva citat člana "
            "zakona ili presedan iz sudske prakse. Ne menja nikakve podatke."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "upit": {
                    "type": "string",
                    "description": "Pravno pitanje ili pojam za pretragu, na srpskom.",
                },
            },
            "required": ["upit"],
        },
    },
    {
        "type": "function",
        "name": "dodaj_belesku",
        "description": (
            "Dodaj tekstualnu belešku u konkretan predmet. MENJA PODATKE — "
            "korisnik mora glasovno ili u UI potvrditi pre nego što se beleška "
            "trajno sačuva u bazi."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "predmet_id": {
                    "type": "string",
                    "description": "ID predmeta u koji se beleška dodaje.",
                },
                "sadrzaj": {
                    "type": "string",
                    "description": "Tekst beleške koju treba sačuvati.",
                },
            },
            "required": ["predmet_id", "sadrzaj"],
        },
    },
    {
        "type": "function",
        "name": "kreiraj_nacrt",
        "description": (
            "Generiši nacrt pravnog dokumenta (tužba, žalba, ugovor, podnesak, "
            "urgencija). Ne čuva se automatski u predmet — vraća tekst nacrta "
            "koji korisnik dalje pregleda i eventualno sačuva u interfejsu."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vrsta": {
                    "type": "string",
                    "description": (
                        "Ključ tipa dokumenta iz šablonskog registra, npr. "
                        "'tuzba_naknada_stete', 'zalba', 'ugovor_neodredjeno'."
                    ),
                },
                "opis": {
                    "type": "string",
                    "description": "Slobodan opis situacije/zahteva za dokument, na srpskom.",
                },
            },
            "required": ["vrsta", "opis"],
        },
    },
]


# ─── Handleri ────────────────────────────────────────────────────────────────

async def _tool_rag_pretraga(args: dict, user: dict) -> dict:
    upit = (args.get("upit") or "").strip()
    if not upit:
        return {"ok": False, "error": "Nedostaje upit za pretragu."}
    try:
        from app.services.retrieve import retrieve_documents
        docs, meta = await asyncio.to_thread(retrieve_documents, upit, 4)
        return {
            "ok": True,
            "top_zakon": meta.get("top_law", ""),
            "top_clan": meta.get("top_article", ""),
            "pouzdanost": meta.get("confidence", "LOW"),
            "odlomci": docs[:4],
        }
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[VOICE_TOOLS] pretraga_prakse_i_zakona greška: %s", e)
        return {"ok": False, "error": "Pretraga trenutno nije dostupna."}


async def _tool_dodaj_belesku(args: dict, user: dict) -> dict:
    predmet_id = (args.get("predmet_id") or "").strip()
    sadrzaj = sanitize_user_input((args.get("sadrzaj") or "").strip()) or ""
    if not predmet_id or not sadrzaj:
        return {"ok": False, "error": "predmet_id i sadrzaj su obavezni."}
    try:
        from shared.deps import _get_supa
        supa = _get_supa()
        # Ista provera vlasništva kao HTTP dodaj_belesku (api.py, SEC-001 fix
        # 2026-07-23) -- predmet_id ne sme biti prihvaćen bez potvrde da
        # pripada korisniku koji je izdao glasovnu komandu.
        pred = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id")
                .eq("id", predmet_id)
                .eq("user_id", user.get("user_id"))
                .single()
                .execute()
        )
        if not pred.data:
            return {"ok": False, "error": "Predmet nije pronađen ili ne pripada vama."}

        row = await asyncio.to_thread(
            lambda: supa.table("predmet_beleske").insert({
                "predmet_id": predmet_id,
                "user_id":    user.get("user_id"),
                "sadrzaj":    sadrzaj,
            }).execute()
        )
        beleska = (row.data or [{}])[0]
        return {"ok": True, "beleska_id": beleska.get("id")}
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[VOICE_TOOLS] dodaj_belesku greška: %s", e)
        return {"ok": False, "error": "Beleška nije sačuvana zbog greške na serveru."}


async def _tool_kreiraj_nacrt(args: dict, user: dict) -> dict:
    vrsta = (args.get("vrsta") or "").strip()
    opis = (args.get("opis") or "").strip()
    if not vrsta or not opis:
        return {"ok": False, "error": "vrsta i opis su obavezni."}
    try:
        from drafting.router import generate_draft
        rezultat = await asyncio.to_thread(generate_draft, vrsta, opis, user.get("user_id", "") or "")
        if rezultat.get("status") != "success":
            return {"ok": False, "error": rezultat.get("message", "Generisanje nije uspelo.")}
        return {"ok": True, "nacrt": rezultat.get("data", "")}
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[VOICE_TOOLS] kreiraj_nacrt greška: %s", e)
        return {"ok": False, "error": "Generisanje nacrta trenutno nije dostupno."}


TOOL_METADATA: dict[str, dict] = {
    "pretraga_prakse_i_zakona": {"mutates_data": False, "handler": _tool_rag_pretraga},
    "dodaj_belesku":            {"mutates_data": True,  "handler": _tool_dodaj_belesku},
    "kreiraj_nacrt":            {"mutates_data": False, "handler": _tool_kreiraj_nacrt},
}


async def execute_tool(name: str, args: dict, user: dict) -> dict:
    """Izvršava alat po imenu. Nikad ne baca -- nepoznat alat ili bilo koja
    interna greška se vraća kao {"ok": False, "error": ...} tako da
    orkestrator uvek ima nešto smisleno da pročita korisniku."""
    meta = TOOL_METADATA.get(name)
    if not meta:
        return {"ok": False, "error": f"Nepoznat alat: {name}"}
    return await meta["handler"](args, user)


def requires_confirmation(name: str) -> bool:
    meta = TOOL_METADATA.get(name)
    return bool(meta and meta["mutates_data"])
