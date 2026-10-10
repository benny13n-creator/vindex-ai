# -*- coding: utf-8 -*-
"""
Vindex AI — shared/memorija_vidljivost.py

JEDAN vlasnik granice poverljivosti za memoriju kancelarije (`memory_entries`, `memory_graph_edges`).

`memory_entries`/`memory_graph_edges` su izričit put deljenja u kancelariji (čovek upisuje u memoriju firme), ali
članstvo u istoj kancelariji NIJE osnov za pristup predmetu. Zato:
  • beleška ili veza vezana za PREDMET vidljiva je samo onome ko taj predmet sme da vidi — kanonska autorizacija
    `shared/rag_acl.dozvoljeni_predmeti` (vlasnik + aktivna delegacija, bez predmeta u brisanju);
  • vezana za KLIJENTA — samo vlasniku tog klijenta (`klijenti.user_id`);
  • opšti entiteti (sudija, firma, partner; u grafu i argument, strategija) su deljeni u kancelariji.
Nepoznat tip beleške se ne prikazuje (zatvoreno, ne otvoreno).

Koristi ga NS008 Law Brain (`services/law_brain.ucitaj_memoriju`) i legacy rute (`routers/firm_memory.py`,
`routers/memory_graph.py`) — RH001: legacy rute nad istim tabelama pre ovoga su vraćale tuđe predmetne beleške,
klijentske beleške i veze sa ishodom svakom članu kancelarije.

Greška baze pri čitanju ACL-a se PROPUŠTA (pozivalac vraća grešku) — nikad „prikaži sve".
"""
from __future__ import annotations

OPSTI_ENTITETI_BELESKI = ("sudija", "firma", "partner")
_TIPOVI_BELESKI = OPSTI_ENTITETI_BELESKI + ("predmet", "klijent")
_IN_DEO = 200


def predmeti_veze(red: dict) -> set:
    out = {str(red["predmet_id"])} if red.get("predmet_id") else set()
    for strana in ("from", "to"):
        if red.get(f"{strana}_type") == "predmet" and red.get(f"{strana}_id"):
            out.add(str(red[f"{strana}_id"]))
    return out


def klijenti_veze(red: dict) -> set:
    return {str(red[f"{s}_id"]) for s in ("from", "to") if red.get(f"{s}_type") == "klijent" and red.get(f"{s}_id")}


def klijenti_vlasnika(supa, user_id: str, ids) -> set:
    """Podskup `ids` koji su klijenti čiji je vlasnik `user_id`."""
    ids = sorted({str(i) for i in ids if i})
    out: set = set()
    for i in range(0, len(ids), _IN_DEO):
        r = supa.table("klijenti").select("id,user_id").in_("id", ids[i:i + _IN_DEO]).execute()
        out |= {str(x["id"]) for x in (r.data or []) if str(x.get("user_id") or "") == str(user_id)}
    return out


class Vidljivost:
    """ACL podaci za jedan zahtev, učitani SAMO ako ih redovi traže (opšte beleške ne čitaju ACL)."""

    def __init__(self, supa, user_id: str, beleske=(), veze=()):
        from shared.rag_acl import dozvoljeni_predmeti
        beleske, veze = list(beleske), list(veze)
        treba_acl = any(m.get("entity_type") == "predmet" for m in beleske) or any(predmeti_veze(g) for g in veze)
        self.predmeti = set(str(x) for x in dozvoljeni_predmeti(supa, user_id)) if treba_acl else set()
        self.klijenti = klijenti_vlasnika(
            supa, user_id, [m.get("entity_id") for m in beleske if m.get("entity_type") == "klijent"]
            + [k for g in veze for k in klijenti_veze(g)])

    def beleska(self, m: dict) -> bool:
        et = m.get("entity_type")
        if et not in _TIPOVI_BELESKI:
            return False
        if et == "predmet":
            return str(m.get("entity_id") or "") in self.predmeti
        if et == "klijent":
            return str(m.get("entity_id") or "") in self.klijenti
        return True

    def veza(self, g: dict) -> bool:
        return predmeti_veze(g) <= self.predmeti and klijenti_veze(g) <= self.klijenti


def vidljive_beleske(supa, user_id: str, redovi) -> list:
    redovi = list(redovi or [])
    v = Vidljivost(supa, user_id, beleske=redovi)
    return [m for m in redovi if v.beleska(m)]


def vidljive_veze(supa, user_id: str, redovi) -> list:
    redovi = list(redovi or [])
    v = Vidljivost(supa, user_id, veze=redovi)
    return [g for g in redovi if v.veza(g)]
