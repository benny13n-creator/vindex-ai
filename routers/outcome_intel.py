# -*- coding: utf-8 -*-
"""
Outcome Intelligence — statistička analiza ishoda predmeta kancelarije.

GET /api/outcome-intel/predmeti/{predmet_id}
Analizira sve zatvorene predmete istog tipa i vraća statističke uvide.
"U 82% uspešnih radnih sporova postojala je pisana komunikacija poslodavca."
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.outcome_intel")
router = APIRouter(prefix="/api/outcome-intel", tags=["outcome_intel"])

_OUTCOME_SYSTEM = """Ti si pravni analitičar koji analizira obrasce iz zatvorenih predmeta advokatske kancelarije.

Na osnovu datih podataka o predmetima, izvuci konkretne statističke uvide.
Format odgovora (tačno ovako):

📊 STATISTIKA KANCELARIJE
[2-3 konkretne cifre o tipičnom toku predmeta]

🏆 FAKTORI USPEHA
[2-3 faktora koji su bili prisutni u uspešnim predmetima]

⚠️ FAKTORI RIZIKA
[1-2 faktora koja su bila prisutna u neuspešnim predmetima]

💡 PREPORUKA ZA OVAJ PREDMET
[1 konkretna preporuka na osnovu istorije kancelarije]

Budi konkretan sa brojevima. Srpski jezik. Bez generalizacija."""


@router.get("/predmeti/{predmet_id}")
async def get_outcome_intel(predmet_id: str, user=Depends(get_current_user)):
    supa = _get_supa()
    uid  = user["user_id"]

    # Ownership + tekući predmet
    pr = supa.table("predmeti").select(
        "id,naziv,tip,status,opis"
    ).eq("id", predmet_id).eq("user_id", uid).execute()
    if not pr.data:
        raise HTTPException(status_code=404)
    predmet = pr.data[0]
    tip = predmet.get("tip") or "ostalo"

    # Svi predmeti istog tipa
    svi_r = supa.table("predmeti").select(
        "id,naziv,tip,status,created_at,opis"
    ).eq("user_id", uid).eq("tip", tip).execute()
    svi = svi_r.data or []

    if len(svi) <= 1:
        # Nema dovoljno istorije
        return {
            "analiza": (
                "Nema dovoljno istorijskih predmeta za statističku analizu. "
                f"Ovo je jedan od prvih predmeta tipa '{tip}' u kancelariji. "
                "Outcome Intelligence će postati moćniji sa svakim novim zatvorenim predmetom."
            ),
            "ukupno_predmeta": len(svi),
            "isti_tip": 0,
            "tip": tip,
        }

    # Analiza po statusu
    zatvoreni = [p for p in svi if p.get("status") in ("zatvoren","arhiviran","uspesno","neuspesno")]
    aktivni   = [p for p in svi if p.get("status") not in ("zatvoren","arhiviran","uspesno","neuspesno")]

    # Dohvati dokaze za zatvorene predmete (da vidimo koji dokazi koreliisu sa uspehom)
    dok_pattern: dict = {}
    for zp in zatvoreni[:15]:
        try:
            dk = supa.table("predmet_dokumenti").select("tip_dokaza").eq(
                "predmet_id", zp["id"]).is_("deleted_at","null").execute()
            tipovi = [d.get("tip_dokaza") for d in (dk.data or []) if d.get("tip_dokaza")]
            for t in tipovi:
                dok_pattern[t] = dok_pattern.get(t, 0) + 1
        except Exception:
            pass

    # Dohvati billing za zatvorene (prosečno vreme i vrednost)
    billing_avg = []
    for zp in zatvoreni[:10]:
        try:
            be = supa.table("billing_entries").select("iznos").eq(
                "predmet_id", zp["id"]).is_("deleted_at","null").execute()
            total = sum(float(e.get("iznos",0)) for e in (be.data or []))
            if total > 0:
                billing_avg.append(total)
        except Exception:
            pass

    avg_vrednost = int(sum(billing_avg) / len(billing_avg)) if billing_avg else 0

    # Pripremi kontekst za GPT
    ctx = f"""Tip predmeta: {tip}
Ukupno predmeta ovog tipa: {len(svi)}
Zatvoreni/završeni: {len(zatvoreni)}
Trenutno aktivnih: {len(aktivni)}
Prosečna fakturisana vrednost: {avg_vrednost:,} RSD

Dokumenti koji se najčešće pojavljuju (top 5):
"""
    sorted_docs = sorted(dok_pattern.items(), key=lambda x: x[1], reverse=True)[:5]
    for dt, cnt in sorted_docs:
        ctx += f"  - {dt}: {cnt}x (u {int(cnt/max(1,len(zatvoreni))*100)}% predmeta)\n"

    if zatvoreni:
        ctx += f"\nPrimer zatvorenih predmeta:\n"
        for zp in zatvoreni[:5]:
            ctx += f"  - {zp.get('naziv','?')} [{zp.get('status','?')}]\n"

    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=600,
            messages=[
                {"role": "system", "content": _OUTCOME_SYSTEM},
                {"role": "user",   "content": ctx},
            ],
        )
        analiza = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("[OUTCOME] GPT greška: %s", exc)
        # Fallback: manuelna analiza
        linija = []
        linija.append(f"📊 STATISTIKA KANCELARIJE")
        linija.append(f"Ukupno predmeta tipa '{tip}': {len(svi)}")
        linija.append(f"Zatvorenih: {len(zatvoreni)} | Aktivnih: {len(aktivni)}")
        if avg_vrednost:
            linija.append(f"Prosečna vrednost predmeta: {avg_vrednost:,} RSD")
        if sorted_docs:
            linija.append(f"\n🏆 FAKTORI USPEHA")
            linija.append(f"Dokumenti prisutni u većini predmeta: {', '.join(d[0] for d in sorted_docs[:3])}")
        linija.append(f"\n💡 PREPORUKA")
        linija.append("Prikupite što više dokumentacije tipa koji se pojavljuje u uspešnim predmetima.")
        analiza = "\n".join(linija)

    return {
        "analiza":          analiza,
        "ukupno_predmeta":  len(svi),
        "zatvoreni":        len(zatvoreni),
        "aktivni":          len(aktivni),
        "isti_tip":         len(svi) - 1,
        "tip":              tip,
        "avg_vrednost":     avg_vrednost,
        "top_dokumenti":    sorted_docs,
    }
