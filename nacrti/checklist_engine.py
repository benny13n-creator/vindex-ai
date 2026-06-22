# -*- coding: utf-8 -*-
"""
Faza 1 — Checklist Engine

Prima tip podneska + slobodan tekst činjenica.
Analizira koje obavezne elemente korisnik nije naveo.
Koristi GPT-4o-mini za razumevanje teksta (brzo i jeftino).

Vraća:
  {
    "tip": str,
    "naziv_tipa": str,
    "elementi": [
      {
        "naziv": str,
        "pokriven": bool,
        "kriticnost": str,     # "visoka" | "srednja" | "niska"
        "razlog": str | null,  # samo ako nije pokriven
      }
    ],
    "nedostajuci_kriticni": [str],   # nazivi VISOKA + SREDNJA koji nedostaju
    "nedostajuci_svi": [str],
    "procenat_pokrivenosti": int,    # 0-100
    "blokira_nastavak": bool,        # True ako ima nedostajucih VISOKIH elemenata
  }
"""

import os
import json
import logging
from openai import OpenAI
from nacrti.checklist_config import get_config, ChecklistElement

logger = logging.getLogger(__name__)
_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

_SYSTEM = (
    "Ti si pravni asistent koji analizira da li su određeni elementi navedeni u tekstu. "
    "Vraćaj ISKLJUČIVO validni JSON. "
    "Odgovori na srpskom jeziku."
)


def _build_user_prompt(cinjenice: str, elementi: list[ChecklistElement]) -> str:
    elementi_json = json.dumps(
        [{"id": i, "naziv": e["naziv"], "pitanje": e["pitanje"]} for i, e in enumerate(elementi)],
        ensure_ascii=False,
    )
    return (
        f"Analiziraj sledeće činjenice i odgovori da li je svaki element pokriven (true/false).\n\n"
        f"ELEMENTI ZA PROVERU:\n{elementi_json}\n\n"
        f"UNETE ČINJENICE:\n{cinjenice}\n\n"
        "Odgovori u JSON formatu:\n"
        '{"rezultati": [{"id": 0, "pokriven": true/false}, ...]}\n\n'
        "Budi liberalan — ako je element implicitno prisutan u tekstu, označi kao pokriven. "
        "Element je NIJE pokriven (false) samo ako nije ni eksplicitno ni implicitno naveden u tekstu."
    )


def analiziraj_checklist(tip: str, cinjenice: str) -> dict:
    """
    Faza 1 — Checklist analiza.

    Args:
        tip: Ključ iz CHECKLIST dict (npr. 'tuzba_naknada_stete')
        cinjenice: Slobodan tekst koji je korisnik uneo

    Returns:
        dict sa rezultatima analize (v. docstring modula)

    Raises:
        KeyError: ako tip nije poznat
        RuntimeError: ako GPT poziv ne vrati validan JSON
    """
    config = get_config(tip)
    elementi = config["elementi"]

    prompt = _build_user_prompt(cinjenice.strip(), elementi)

    try:
        resp = _client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=512,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        gpt_result = json.loads(raw)
    except Exception as exc:
        logger.error("checklist_engine GPT error: %s", exc)
        raise RuntimeError(f"GPT poziv nije uspeo: {exc}") from exc

    rezultati_map: dict[int, bool] = {}
    for item in gpt_result.get("rezultati", []):
        rezultati_map[int(item["id"])] = bool(item.get("pokriven", False))

    # fallback keyword provera za elemente koje GPT nije vratio
    def _keyword_check(e: ChecklistElement, tekst: str) -> bool:
        tekst_lower = tekst.lower()
        return any(kw in tekst_lower for kw in e["kljucne_reci"])

    elementi_out = []
    nedostajuci_svi: list[str] = []
    nedostajuci_kriticni: list[str] = []
    pokriven_count = 0

    for i, elem in enumerate(elementi):
        gpt_pokriven = rezultati_map.get(i)
        if gpt_pokriven is None:
            # GPT nije odgovorio za ovaj element — koristimo keyword fallback
            gpt_pokriven = _keyword_check(elem, cinjenice)
            logger.debug("checklist fallback keyword za '%s': %s", elem["naziv"], gpt_pokriven)

        if gpt_pokriven:
            pokriven_count += 1
        else:
            nedostajuci_svi.append(elem["naziv"])
            if elem["kriticnost"] in ("visoka", "srednja"):
                nedostajuci_kriticni.append(elem["naziv"])

        elementi_out.append({
            "naziv": elem["naziv"],
            "pokriven": gpt_pokriven,
            "kriticnost": elem["kriticnost"],
            "razlog": None if gpt_pokriven else elem["razlog"],
        })

    procenat = round(pokriven_count / len(elementi) * 100) if elementi else 100
    blokira = any(
        not e["pokriven"] and e["kriticnost"] == "visoka"
        for e in elementi_out
    )

    return {
        "tip": tip,
        "naziv_tipa": config["naziv"],
        "elementi": elementi_out,
        "nedostajuci_kriticni": nedostajuci_kriticni,
        "nedostajuci_svi": nedostajuci_svi,
        "procenat_pokrivenosti": procenat,
        "blokira_nastavak": blokira,
    }
