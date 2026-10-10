# -*- coding: utf-8 -*-
"""
Vindex AI — services/law_brain_sinteza.py

NS008 Task 12 — JEDINI poziv modela u Law Brain-u, odvojen od `services/law_brain.py` da bi osnovno čitanje
ostalo dokazivo bez modela (test ugovora proverava da `law_brain.py` ne uvozi OpenAI).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from services.law_brain import (
    AUTHORITY_NOTICE, AI_CANDIDATE_LESSON, EXPLICIT_GRAPH_RELATION, HUMAN_CONFIRMED_OUTCOME, HUMAN_CORRECTION,
    HUMAN_MEMORY_NOTE, LAWYER_VERIFIED_ARTIFACT, OK, OUTCOME_RECORDED, SOURCE_CASE_FACT, UNKNOWN_LEGACY,
    kontekst_predmeta, safe_excerpt,
)

# ─── Task 12: izričita, utemeljena sinteza (jedini poziv modela u Law Brain-u) ──────────────────────
# Model dobija SAMO autorizovan, već pročitan kontekst (Task 11) kao numerisane reference R1..Rn. Svaka
# tvrdnja mora citirati reference iz tog skupa, a vrsta tvrdnje mora odgovarati klasi poverenja reference.
# Tvrdnja sa izmišljenom referencom, procentom/verovatnoćom, pozivom na propis, uopštavanjem („uvek") ili
# brojem kog nema u citiranim referencama se ODBACUJE — ne „popravlja".
import json as _json
import re as _re

SYNTH_VERSION = "lb-syn-1"
SYNTH_MODEL = "gpt-4o-mini"
SYNTH_NOTICE = ("AI sinteza iskustva kancelarije, zasnovana isključivo na navedenim izvorima. "
                "Nije pravni savet ni procena ishoda. " + AUTHORITY_NOTICE)
_VRSTE = {
    "iskustvo": None,                                                         # bilo koja referenca
    "ishod": {HUMAN_CONFIRMED_OUTCOME},
    "overen_rad": {LAWYER_VERIFIED_ARTIFACT},
    "neproverena_beleska": {HUMAN_MEMORY_NOTE, HUMAN_CORRECTION, EXPLICIT_GRAPH_RELATION,
                            AI_CANDIDATE_LESSON, UNKNOWN_LEGACY},
}
_ZABRANJENO = _re.compile(
    r"%|procen(at|ta|ata)|šans|sansa|verovatn|izgled[ei] (za )?uspeh|očekuje se|predviđ|"
    r"\bčl(an|\.)\s*\d|\bzakon[a-z]*\b|\bustav|\bsudsk[a-z]* praks|\buvek\b|\bnikad\b|\bsvaki put\b",
    _re.IGNORECASE)
_BROJ = _re.compile(r"\d+")
_SINTEZA_SISTEM = """Ti sažimaš ISKUSTVO ADVOKATSKE KANCELARIJE za jedan predmet, isključivo iz datih referenci.
PRAVILA (kršenje = tvrdnja se odbacuje):
- Svaka tvrdnja citira bar jednu referencu iz liste (npr. "R2"). Ne izmišljaj reference.
- vrsta: "ishod" samo uz reference klase HUMAN_CONFIRMED_OUTCOME; "overen_rad" samo uz LAWYER_VERIFIED_ARTIFACT;
  "neproverena_beleska" za beleške i nepotvrđeno; "iskustvo" za opšte poređenje sa ranijim predmetima.
- Iskustvo kancelarije NIJE zakon ni sudska praksa. Ne navodi propise, članove ni sudsku praksu.
- Bez procenata, verovatnoće, šansi i predviđanja ishoda. Ne uopštavaj ("uvek", "nikad").
- Ne izmišljaj predmete, ishode, ponašanje sudija ni želje klijenata. Brojeve navodi samo ako su u referenci.
- Najviše 8 tvrdnji, svaka do 2 rečenice. Srpski jezik, ekavica.
Vrati SAMO JSON: {"tvrdnje": [{"tekst": "...", "vrsta": "iskustvo|ishod|overen_rad|neproverena_beleska", "refs": ["R1"]}]}"""


def reference_za_sintezu(kontekst: dict) -> list:
    """Numerisane reference iz VEĆ autorizovanog konteksta. Deterministički redosled."""
    refs: list = []

    def _dodaj(trust, tekst, source_ref, vrsta):
        refs.append({"ref": f"R{len(refs) + 1}", "trust_class": trust, "vrsta_izvora": vrsta,
                     "tekst": safe_excerpt(tekst), "source_ref": source_ref})

    for i, s in enumerate((kontekst.get("similar_cases") or {}).get("stavke") or [], 1):
        _dodaj(SOURCE_CASE_FACT, f"Raniji predmet {i}: {s.get('zasto', '')}",
               {"table": "predmeti", "id": s["predmet_id"]}, "slican_predmet")
        it = (s.get("ishod") or {}).get("item")
        if it and (s.get("ishod") or {}).get("status") == OUTCOME_RECORDED:
            _dodaj(HUMAN_CONFIRMED_OUTCOME, f"Ishod ranijeg predmeta {i} (zabeležio advokat): {s['ishod']['ishod']}",
                   it["source_ref"], "ishod")
    for a in (kontekst.get("verified_artifacts") or {}).get("stavke") or []:
        _dodaj(a["trust_class"], f"Overen rad ({a.get('title', '')}): {a.get('excerpt', '')}", a["source_ref"], "artefakt")
    for x in (kontekst.get("confirmed_lessons") or {}).get("stavke") or []:
        _dodaj(x["trust_class"], f"Potvrđena lekcija: {x.get('excerpt', '')}", x["source_ref"], "lekcija")
    for b in (kontekst.get("relevant_human_memory") or {}).get("stavke") or []:
        _dodaj(b["trust_class"], f"Beleška kolege ({b.get('title', '')}): {b.get('excerpt', '')}", b["source_ref"], "beleska")
    d = kontekst.get("descriptive_outcomes") or {}
    if d.get("state") == OK and d.get("recenice"):
        _dodaj(SOURCE_CASE_FACT, "Izračunato u kodu: " + " ".join(d["recenice"]),
               {"table": "outcome_log", "id": "agregat"}, "statistika")
    return refs


def proveri_sintezu(sirovo, refs: list) -> tuple:
    """(prihvaćene tvrdnje, broj odbačenih, razlozi). Čista funkcija."""
    po_ref = {r["ref"]: r for r in refs}
    prihvacene, razlozi = [], []
    tvrdnje = sirovo.get("tvrdnje") if isinstance(sirovo, dict) else None
    for t in (tvrdnje if isinstance(tvrdnje, list) else [])[:20]:
        if not isinstance(t, dict):
            razlozi.append("NEISPRAVAN_OBLIK")
            continue
        tekst = " ".join(str(t.get("tekst") or "").split())
        vrsta = t.get("vrsta")
        citirane = [str(x) for x in (t.get("refs") or []) if isinstance(x, str)]
        if not tekst or len(tekst) > 600:
            razlozi.append("PRAZNO_ILI_PREDUGO")
        elif vrsta not in _VRSTE:
            razlozi.append("NEPOZNATA_VRSTA")
        elif not citirane or any(c not in po_ref for c in citirane):
            razlozi.append("IZMISLJENA_ILI_NEDOSTAJUCA_REFERENCA")
        elif _VRSTE[vrsta] is not None and any(po_ref[c]["trust_class"] not in _VRSTE[vrsta] for c in citirane):
            razlozi.append("VRSTA_NE_ODGOVARA_IZVORU")
        elif _ZABRANJENO.search(tekst):
            razlozi.append("ZABRANJEN_SADRZAJ")
        elif any(n not in " ".join(po_ref[c]["tekst"] for c in citirane) for n in _BROJ.findall(tekst)):
            razlozi.append("BROJ_BEZ_IZVORA")
        else:
            prihvacene.append({"tekst": tekst, "vrsta": vrsta, "refs": sorted(set(citirane)),
                               "source_refs": [po_ref[c]["source_ref"] for c in sorted(set(citirane))]})
            continue
        if len(prihvacene) >= 8:
            break
    return prihvacene[:8], len(razlozi), sorted(set(razlozi))


async def _pozovi_model_sinteze(prompt: str, predmet_id: str) -> str:
    from openai import AsyncOpenAI
    from shared.ai_provenance import case_context
    klijent = AsyncOpenAI(max_retries=0)
    with case_context(predmet_id=predmet_id, module_name="law_brain.sinteza", operation_name="LAW_BRAIN_SYNTHESIS"):
        r = await klijent.chat.completions.create(
            model=SYNTH_MODEL, temperature=0, max_tokens=900, timeout=60.0, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _SINTEZA_SISTEM}, {"role": "user", "content": prompt}])
    return (r.choices[0].message.content or "{}").strip()


class ModelNedostupan(Exception):
    pass


async def sinteza(supa, user_id: str, predmet_id: str, *, today: date) -> Optional[dict]:
    """None = predmet nije autorizovan/ne postoji. Bez referenci → bez poziva modela. Pad modela →
    ModelNedostupan (ruta: 503, bez kredita). Vraća i `model_pozvan` da ruta naplati tačno jednom."""
    import asyncio as _a
    kontekst = await _a.to_thread(kontekst_predmeta, supa, user_id, predmet_id, today=today)
    if kontekst is None:
        return None
    refs = reference_za_sintezu(kontekst)
    osnova = {"verzija": SYNTH_VERSION, "napomena": SYNTH_NOTICE,
              "reference": [{k: r[k] for k in ("ref", "trust_class", "vrsta_izvora", "source_ref")} for r in refs],
              "nedostupni_izvori": kontekst["data_quality"]["nedostupni_izvori"]}
    # Beleške kolega same po sebi nisu provereno iskustvo: bez bar jednog ranijeg autorizovanog predmeta,
    # ljudskog ishoda, overenog rada ili potvrđene lekcije model se ne poziva.
    if not any(r["vrsta_izvora"] in ("slican_predmet", "ishod", "artefakt", "lekcija") for r in refs):
        return {**osnova, "stanje": "NEMA_OSNOVA", "tvrdnje": [], "odbaceno": 0, "razlozi_odbacivanja": [],
                "model_pozvan": False,
                "poruka": "Kancelarija još nema proverenog iskustva za ovaj predmet — sinteza nije pokrenuta."}
    prompt = "REFERENCE:\n" + "\n".join(f"{r['ref']} [{r['trust_class']}] {r['tekst']}" for r in refs)
    try:
        sirovo = _json.loads(await _pozovi_model_sinteze(prompt, predmet_id))
    except Exception as e:
        raise ModelNedostupan(type(e).__name__)
    tvrdnje, odbaceno, razlozi = proveri_sintezu(sirovo, refs)
    return {**osnova, "stanje": "OK" if tvrdnje else "NIJEDNA_TVRDNJA_NIJE_PROVERENA", "tvrdnje": tvrdnje,
            "odbaceno": odbaceno, "razlozi_odbacivanja": razlozi, "model_pozvan": True, "model": SYNTH_MODEL}
