# -*- coding: utf-8 -*-
"""
GDPR Data Export — korisnik preuzima svoje zapise iz tabela navedenih u README-u.
GET /api/export/complete → ZIP sa JSON fajlovima (bez originalnih fajlova dokumenata).
"""
import asyncio
import io
import json
import logging
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.data_export")
router = APIRouter(prefix="/api/export", tags=["export"])

_README = """VINDEX AI — Export podataka
Datum: {datum}
Korisnik: {email}

Sadržaj:
  predmeti.json       — svi predmeti
  klijenti.json       — svi klijenti
  billing.json        — sve stavke naplate
  dokumenti.json      — metadata dokumenata (bez fajlova); polje tekst_sadrzaj,
                        gde postoji, je izvučeni tekst — nije original
  beleske.json        — beleške uz predmete
  rocista.json        — ročišta
  hronologija.json    — automatski generisana hronologija
  komentari.json      — komentari uz predmete

Napomena: Fajlovi dokumenata (PDF, DOCX...) nisu uključeni u ovaj export.
Za preuzimanje fajlova kontaktirajte: benny13.n@gmail.com

Prava: Imate pravo na prenosivost podataka prema ZZPL čl. 36 i GDPR čl. 20.
"""


class ExportIncomplete(Exception):
    """One or more tables could not be read for a portability export.

    S4-4 (2026-08-09). _fetch swallowed every read error into [], and the
    endpoint shipped the ZIP regardless. So a transient database error meant the
    data subject received an export that was MISSING ENTIRE TABLES, labelled by
    its own README as a complete ZZPL čl. 36 / GDPR čl. 20 portability export.

    An incomplete export presented as complete is worse than no export: the
    recipient has no way to know what is absent, and completeness is the entire
    point of the right being exercised. Fail instead, and name the tables.
    """


#: PostgREST/Supabase `max-rows` (podrazumevano 1000): odgovor bez straničenja
#: se TIHO seče na tu granicu. Strana ne sme biti veća od nje.
_STRANA = 1000

#: NS3-C: gornja granica cekanja na kanonski audit upis (sekunde). Upis su dva
#: kratka poziva baze (+ do 5 ponavljanja na prev_hash sudar). `asyncio.to_thread`
#: se NE MOZE prekinuti: posle isteka nit moze i dalje da upise red -- ishod je
#: NEPOZNAT, pa se izvoz ne salje (fail-closed).
_AUDIT_TIMEOUT_S = 15.0

#: NS3-C: istinita privremena greska kada upis u audit log nije dokazan.
#: Ne tvrdi ni da je izvoz poslat ni da je zapis upisan.
_PORUKA_AUDIT_NEDOKAZAN = (
    "Izvoz vam nije poslat jer upis u nepromenjivi audit log nije potvrđen. "
    "Pokušajte ponovo za koji minut."
)


def _kljuc_redosleda(order: str):
    """Redosled u izvozu kao ranije `order(<kolona>)` (rastuće, NULL na kraju),
    sa `id` kao stabilnim razbijačem nerešenog."""
    def k(r):
        v = r.get(order)
        return (v is None, "" if v is None else str(v), str(r.get("id")))
    return k


async def _fetch(supa, table: str, uid: str, order: str = "created_at",
                 errors: list | None = None) -> list:
    """Svi redovi korisnika iz tabele, po stranama.

    C1-F1 (Night Sprint II): jedan upit bez opsega PostgREST seče na `max-rows`
    (1000) bez ikakve greške -- izvoz je bio „uspešan" i nepotpun. Čita se po
    ključu (`id > poslednji`, `order(id)`), ne po offsetu: brisanje reda
    između dve strane ne može da pomeri i preskoči neki drugi red. Petlja se
    prekida tek na PRAZNOJ strani, ne na „kratkoj" -- tako ni niži `max-rows`
    od `_STRANA` ne može tiho da odseče ostatak. Pad bilo koje strane je pad
    cele tabele (izvoz se odbija, `data_export_failed`).
    """
    try:
        out: list = []
        poslednji = None
        while True:
            q = supa.table(table).select("*").eq("user_id", uid)
            if poslednji is not None:
                q = q.gt("id", poslednji)
            strana = q.order("id").limit(_STRANA).execute().data or []
            if not strana:
                break
            # C1-N1: id mora strogo da raste unutar strane i preko strana
            # (uuid u Postgres-u se poredi bajt po bajt = leksikografski nad
            # kanonskim heks zapisom). Inace bi strana van redosleda dala
            # duplikate ili rupe, a izvoz bi izgledao uspesan.
            for red in strana:
                rid = red.get("id")
                if rid is None or (poslednji is not None and str(rid) <= str(poslednji)):
                    raise RuntimeError("stranicenje nije strogo rastuce po id")
                poslednji = rid
            out.extend(strana)
        out.sort(key=_kljuc_redosleda(order))
        return out
    except Exception as e:
        # Samo klasa izuzetka: tekst greške baze može da nosi vrednost iz reda.
        logger.error("[EXPORT] %s greška (%s) — export je NEPOTPUN", table, type(e).__name__)
        if errors is not None:
            errors.append(table)
        return []


@router.get("/complete")
async def export_complete(user=Depends(get_current_user)):
    """
    Exportuje korisnikove zapise iz 8 tabela navedenih u README-u kao ZIP sa
    JSON fajlovima. Originalni fajlovi dokumenata NISU ukljuceni (README to kaze).
    GDPR čl. 20 — pravo na prenosivost podataka.
    """
    from shared.audit_immutable import log_action as _imm_log

    uid  = user["user_id"]
    email = user.get("email", uid)
    now  = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")

    # NS001 — kolona za sortiranje mora postojati na TOJ tabeli, inače
    # PostgREST odbija ceo upit (42703), `_fetch` je upiše u `_failed`, i ZIP se
    # odbacuje. `klijenti` i `predmet_komentari` nemaju `created_at` nego
    # `kreirano` -- mereno sondom `select(<kolona>)&limit=0` nad produkcijskom
    # bazom i potvrdjeno stvarnim pozivom: `GET /api/export/complete` je vraćao
    # HTTP 503 "podaci iz sledećih tabela nisu mogli da se pročitaju: klijenti,
    # predmet_komentari". Dakle prenosivost podataka (ZZPL čl. 36 / GDPR čl. 20)
    # nije radila ni za jednog korisnika.
    # C1-F1: kolona se vise ne salje PostgREST-u (upit ide po `id`); koristi se
    # samo za redosled u izvozu (`_kljuc_redosleda`).
    tables = [
        ("predmeti",          "predmeti.json",     "created_at"),
        ("klijenti",          "klijenti.json",     "kreirano"),
        ("billing_entries",   "billing.json",      "created_at"),
        ("predmet_dokumenti", "dokumenti.json",    "created_at"),
        ("predmet_beleske",   "beleske.json",      "created_at"),
        ("rocista",           "rocista.json",      "datum"),
        ("predmet_hronologija","hronologija.json", "datum_iso"),
        ("predmet_komentari", "komentari.json",    "kreirano"),
    ]

    # C1 (Night Sprint II): faze izvoza se beleze istinito. Server moze da
    # dokaze najvise fazu 3 (arhiva napravljena i predata odgovoru); da je
    # klijent primio ceo odgovor server NE moze da dokaze, pa to nijedan zapis
    # ni poruka ne tvrde. Neuspeh u bilo kojoj fazi ostavlja
    # `data_export_failed` (nikad `data_export`) -- samo faza, imena tabela i
    # klasa izuzetka; nikad sadrzaj arhive, tekst izuzetka ni email.
    #
    # NS2b-D: upis se CEKA (isti obrazac kao V34-V40 rute, npr.
    # billing_entry_delete), ne zakazuje kroz `spawn`. Zakazan upis je posle
    # `return` jos neizvrsen dok klijent vec prima ZIP; gasenje procesa u tom
    # prozoru (shared/bg.py: spawn NIJE trajan) ostavlja isporucen izvoz bez
    # zapisa, suprotno security.html §14.2.
    #
    # NS3-C (odluka osnivaca): za USPESAN izvoz upis je USLOV isporuke, ne
    # best-effort. `log_action` vraca id upisanog reda samo kada je PostgREST
    # vratio upisan red (`_build_and_insert`: `result.data[0]["id"]`); None
    # znaci neuspeh, progutan izuzetak ili akciju van AUDITABLE_ACTIONS.
    # Dokaz = neprazan string id. Sve ostalo (None, izuzetak, istek roka =
    # ishod NEPOZNAT) -> ZIP se ne salje. Vraca razlog neuspeha ili None.
    async def _upisi(akcija: str, meta: dict) -> str | None:
        try:
            zapis = await asyncio.wait_for(
                _imm_log(akcija, user_id=uid, resource_type="all_user_data",
                         metadata=meta),
                timeout=_AUDIT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            razlog = "timeout"
        except Exception as e:
            razlog = type(e).__name__
        else:
            if isinstance(zapis, str) and zapis:
                return None
            razlog = "not_persisted"
        # Sink koji je pao ne moze sam da zabelezi svoj pad: samo operativni
        # log -- akcija i razlog, nikad e-posta, sadrzaj arhive ni tekst greske.
        logger.error("[EXPORT] audit %s NIJE dokazano upisan (%s)", akcija, razlog)
        return razlog

    async def _neuspeh(faza: str, **dodatno) -> None:
        meta = {"format": "zip", "stage": faza, "archive_sent": False}
        meta.update(dodatno)
        await _upisi("data_export_failed", meta)

    # Faza 1 -> 2: klijent baze. Pad ovde znaci da nijedna tabela nije procitana.
    try:
        supa = _get_supa()
    except Exception as e:
        logger.error("[EXPORT] baza nedostupna (%s) -- izvoz NIJE napravljen", type(e).__name__)
        await _neuspeh("pre_retrieval", error_class=type(e).__name__)
        raise HTTPException(
            status_code=503,
            detail="Izvoz nije napravljen i nije vam poslat. Pokušajte ponovo za koji minut.",
        )

    # Faze 2 i 3, tabela po tabela: u memoriji je istovremeno samo jedna
    # tabela (kao JSON) i ZIP -- ne svih 8. ZIP se salje tek ako je SVAKA
    # tabela procitana do kraja; inace se odbacuje.
    _failed: list[str] = []
    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            readme = _README.format(datum=now.replace("T", " "), email=email)
            zf.writestr("README.txt", readme)
            for table, fname, order in tables:
                data = await _fetch(supa, table, uid, order, errors=_failed)
                if _failed:
                    continue  # arhiva se ionako odbacuje; samo se imenuju sve pale tabele
                zf.writestr(fname, json.dumps(data, ensure_ascii=False, indent=2, default=str))
                del data
    except Exception as e:
        logger.error("[EXPORT] pravljenje arhive palo (%s) -- izvoz NIJE poslat", type(e).__name__)
        await _neuspeh("serialization", error_class=type(e).__name__)
        raise HTTPException(
            status_code=500,
            detail="Izvoz nije napravljen i nije vam poslat. Pokušajte ponovo.",
        )

    # S4-4: never hand the data subject a partial archive that calls itself
    # complete. The ZIP is discarded rather than shipped.
    if _failed:
        await _neuspeh("retrieval", failed_tables=list(_failed))
        raise HTTPException(
            status_code=503,
            detail=(
                "Export nije kompletan — podaci iz sledećih tabela nisu mogli da se "
                f"pročitaju: {', '.join(_failed)}. Nepotpun export vam nije poslat "
                "jer bi izgledao kao potpun. Pokušajte ponovo za koji minut."
            ),
        )

    # N04: audit se upisuje tek POSLE uspeha. Ranije je `data_export` pisan pre
    # citanja tabela, pa je i odbijen (503) izvoz ostajao u nepromenjivom logu
    # kao izvrsen izvoz -- suprotno static/security.html §14.2 („Svaki kompletan
    # izvoz upisuje se ..."). NS2b-D: upis se ceka (v. `_upisi`).
    # C1: zapis tvrdi samo fazu 3 -- isporuka klijentu nije serverski dokaziva.
    # NS3-C: bez e-poste -- red vec nosi user_id, a §14.2 obecava samo
    # (user_id, vreme, format). Nepromenjiv log ne sme da cuva vise PII nego sto
    # je potrebno (iz njega se nista ne moze obrisati).
    razlog = await _upisi("data_export", {
        "format": "zip",
        "stage": "archive_generated",
        "delivery": "not_verified_by_server",
    })
    if razlog is not None:
        # NS3-C: upis nije dokazan -> arhiva se odbacuje, nijedan bajt ne izlazi.
        buf.close()
        if razlog != "timeout":
            # Brz neuspeh: pokusaj istinitog zapisa o odbijenom izvozu. Posle
            # isteka roka se ne pokusava (sink ne odgovara; drugi rok bi samo
            # produzio cekanje korisnika).
            await _neuspeh("audit_unproven", reason=razlog)
        raise HTTPException(status_code=503, detail=_PORUKA_AUDIT_NEDOKAZAN)

    buf.seek(0)
    filename = f"vindex-export-{now}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
