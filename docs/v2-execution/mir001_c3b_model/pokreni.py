# -*- coding: utf-8 -*-
"""Stvarni gpt-4o, parametri proizvoda (`_pozovi_agent_api`: temperature 0.35, max_tokens 2000), N nacrta po snimku.
Snimak već nosi system sa granicom (`_sa_granicom`). Ključ se čita iz .env i ne ispisuje.
Upotreba: python -I -X utf8 pokreni.py <N> <snimak.json> <izlaz.json> [<snimak> <izlaz> ...]"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

for red in open(os.environ.get("VINDEX_ENV_FILE", ".env"), encoding="utf-8"):
    if red.startswith("OPENAI_API_KEY="):
        os.environ["OPENAI_API_KEY"] = red.split("=", 1)[1].strip().strip('"').strip("'")
from openai import OpenAI  # noqa: E402

k = OpenAI()
N = int(sys.argv[1])
parovi = list(zip(sys.argv[2::2], sys.argv[3::2]))


def jedan(p):
    r = k.chat.completions.create(model="gpt-4o", temperature=0.35, max_tokens=2000,
                                  messages=[{"role": "system", "content": p["system"]}, {"role": "user", "content": p["user"]}])
    return {"odgovor": r.choices[0].message.content, "finish_reason": r.choices[0].finish_reason,
            "tokeni": {"ulaz": r.usage.prompt_tokens, "izlaz": r.usage.completion_tokens}}


for ulaz, izlaz in parovi:
    p = json.load(open(ulaz, encoding="utf-8"))["N"]["poruka"]
    with ThreadPoolExecutor(5) as ex:
        out = list(ex.map(lambda _: jedan(p), range(N)))
    json.dump({"N": out}, open(izlaz, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(os.path.basename(izlaz), [o["finish_reason"] for o in out], sum(o["tokeni"]["ulaz"] + o["tokeni"]["izlaz"] for o in out))
