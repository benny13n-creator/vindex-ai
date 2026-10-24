# -*- coding: utf-8 -*-
"""MIR001 C3b STRUCTURAL — test pomoćnik: nacrt iz spisa poziva model kroz `_pozovi_nacrt_api` (JSON: tekst za sud +
napomene). Postojeći zamenik modela (`(client, system, user_msg) → odgovor`) se ovde pakuje u isti JSON ugovor, pa
testovi koji su merili sadržaj poruke i nacrta i dalje mere isti tok.

`bez_pravila=True` za zamenike koji savetnika prepoznaju po TAČNOJ sistemskoj poruci (`c["system"] == system`):
pravila nacrta iz spisa (`shared.nacrt_za_sud.PRAVILA_ZA_MODEL`) se tada skidaju pre poziva zamenika. Inače zamenik
dobija punu poruku (snimak za stvaran model mora biti veran)."""
import json
import types


def kao_json(zamenik, napomene=(), bez_pravila=False):
    from shared.nacrt_za_sud import PRAVILA_ZA_MODEL

    def _nacrt(client, system, user_msg):
        s = system.replace("\n\n" + PRAVILA_ZA_MODEL, "") if bez_pravila else system
        r = zamenik(client, s, user_msg)
        sadrzaj = r.choices[0].message.content or ""
        telo = json.dumps({"tekst_za_sud": sadrzaj, "napomene_za_advokata": list(napomene)}, ensure_ascii=False)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=telo),
                                                                    finish_reason="stop")])
    return _nacrt
