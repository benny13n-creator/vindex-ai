# -*- coding: utf-8 -*-
"""
Vindex AI — shared/pravni_autoritet.py

JEDAN vlasnik pravila: da li AI tekst TVRDI pravni autoritet ili pravno pravilo koje nije provereno.

Gde se koristi: svuda gde model piše tekst za advokata BEZ proverenih pravnih izvora u ulazu (NS007 Hearing Prep,
NS008 Law Brain sinteza). Formalni citati (član 12, Zakon o…, Rev 123/2023) imaju svoje provere kod pozivaoca; ovo
hvata IMPLICITNI autoritet bez broja propisa — tvrdnju šta je sudska praksa, šta sudovi „smatraju", šta zakon
„propisuje", na kome „je" teret dokazivanja, koliki „je" rok — koju bi advokat mogao da pročita kao utvrđeno pravo.

Dva nivoa:
  1. AUTORITET (praksa, sudovi, zakon, teret dokazivanja) — odbija se UVEK, i u upitnom obliku: „Proverite: sudska
     praksa nalaže…" i dalje tvrdi autoritet. „Proverite da li postoji praksa Vrhovnog suda o…" ne tvrdi ništa.
  2. PRAVILO (rok, zastarelost, dužnost dokazivanja, pravni zaključak „otkaz je nezakonit") — dozvoljeno SAMO kao
     jasno označeno pitanje za proveru („Proveriti: …", „Da li …?"), što ugovor Hearing Prep izričito dozvoljava.

Ovo je lista obrazaca, ne razumevanje jezika: nepoznata formulacija može da prođe (RH001, rezidualni rizik). Pravilo je
namerno konzervativno: lažno odbijanje košta jednu AI stavku (deo iz baze ostaje), lažno prihvatanje košta poverenje
advokata u pravnu tvrdnju bez izvora.
"""
from __future__ import annotations

import re


def _r(n: int) -> str:
    """Do n reči između (pridevi, nazivi sudova)."""
    return r"(?:\s+\S+){0,%d}" % n


_OBRASCI = [
    # sudska praksa kao autoritet
    r"\bustaljen\w*",
    r"\b(?:sudsk|dosadašnj|jedinstven|preovlađuj|preovladjuj|novij|stalne?)\w*\s+praks\w*",
    r"\b(?:prema|po|u\s+skladu\s+sa)" + _r(3) + r"\s+praks\w*",
    r"\b(?:iz|u)\s+(?:sudskoj\s+|sudske\s+)?praks\w*",
    r"\bshvatanj\w*" + _r(1) + r"\s+sud\w*",
    r"\b(?:vrhovn|ustavn|kasacion)\w*\s+sud\w*" + _r(4) + r"\s+(?:potvrdi\w*|odlu[čc]i\w*|presudi\w*|presu[đd]uj\w*"
    r"|utvrdi\w*|vi[šs]e\s+puta|u\s+vi[šs]e\s+navrata)",
    r"\bkako\s+je\s+(?:op[šs]te\s+)?poznato\b",
    r"\bpraks\w*" + _r(3) + r"\s+(?:je\s+da|nala[žz]\w*|zahteva\w*|smatra\w*|potvr[đd]uj\w*|ka[žz]e|ukazuj\w*"
    r"|predvi[đd]\w*|propisuj\w*|stoji|ide\s+u\s+korist)\b",
    r"\b(?:judikatur|preseda[nt]|sentenc)\w*",
    r"\bpravn\w*\s+(?:stav|shvatanj|pravil)\w*",
    r"\bstav\w*" + _r(1) + r"\s+(?:vrhovn|apelacion|ustavn|kasacion|upravn|privredn|sud)\w*",
    # sud kao autoritet (šta sudovi „smatraju", „prihvataju", „moraju")
    r"\bsud\w*" + _r(4) + r"\s+(?:smatra\w*|nala[žz]\w*|zauze\w*|zauzima\w*|tuma[čc]\w*|dosledno|redovno|po\s+pravilu"
    r"|(?:je|su)\s+stava|stoj\w*\s+na\s+stanovi[šs]tu|stao\s+na\s+stanovi[šs]te|priznaj\w*"
    r"|(?:ne\s+)?(?:prihvata|prihvataju|usvaja|usvajaju|odbacuj\w*|odbija|odbijaju))\b",
    r"\bsud\w*" + _r(2) + r"\s+(?:mora|je\s+du[žz]an|ne\s+mo[žz]e|ne[ćc]e)\b",
    # zakon kao autoritet bez citata
    r"\b(?:po|prema)\s+zakonu\b",
    r"\bzakon\w*" + _r(2) + r"\s+(?:propisuj\w*|nala[žz]\w*|predvi[đd]\w*|zahteva\w*|ka[žz]e|dozvoljava\w*|zabranjuj\w*"
    r"|odre[đd]uj\w*)",
    r"\b(?:propisano|predvi[đd]eno|zakonom\s+odre[đd]eno)\s+je\b",
    r"\b(?:zakonom\s+)?je\s+(?:propisano|predvi[đd]eno)\b",
    # pravilo o teretu dokazivanja kao činjenica
    r"\bteret\w*\s+dokazivanja\s+(?:je|le[žz]i|pada|prelazi|snosi)\b",
]

_BROJ_RECI = (r"(?:\d+|jedan|jedna|dva|dve|tri|[čc]etiri|pet|[šs]est|sedam|osam|petnaest|trideset|[šs]ezdeset"
              r"|devedeset)")
_PRAVILA = [
    r"\b(?:zastarelost|zastarevanj\w*|zastarn\w*\s+rok\w*)" + _r(2)
    + r"\s+(?:je|nastup\w*|isti[čc]\w*|po[čc]inj\w*|iznosi|traje)\b",
    r"\bprekluziv\w*",
    r"\brok\w*" + _r(3) + r"\s+(?:je|iznosi|traje)\s+" + _BROJ_RECI + r"\s+(?:dan|mesec|godin)\w*",
    r"\bop[šs]te\s+(?:je\s+)?pravilo\b",
    r"\bpravn\w*\s+dejstv\w*",
    r"\bmora\w*\s+(?:da\s+)?doka[žz]\w*",
    r"\b(?:je|su)\s+du[žz]a?n\w*\s+da\s+(?:doka[žz]\w*|isplat\w*|nadoknad\w*|vrat\w*|plat\w*|snos\w*)",
    # jedna reč dozvoljena između („je očigledno neosnovana"); NE „osnovan": „društvo je osnovano 2015." je činjenica
    r"\b(?:je|su|bi\s+bio|bi\s+bila|bi\s+bilo)(?:\s+\S+)?\s+(?:ni[šs]tav|nezakonit|protivzakonit|nedopu[šs]ten"
    r"|neblagovremen|neosnovan|zastarel)\w*",
]

_AUTORITET = re.compile("|".join(f"(?:{o})" for o in _OBRASCI), re.IGNORECASE)
_PRAVILO = re.compile("|".join(f"(?:{o})" for o in _PRAVILA), re.IGNORECASE)
_PROVERA = re.compile(r"^(?:provera|proveri\w*|razjasni\w*|ispita\w*|pravno\s+pitanje|pitanje\s+za\s+proveru|da\s+li)\b",
                      re.IGNORECASE)


def oznaceno_kao_provera(tekst: str) -> bool:
    """Pitanje za pravnu proveru: počinje sa „Proveriti/Proverite/Da li/Pravno pitanje…" ili je upitna rečenica."""
    t = " ".join(str(tekst or "").split())
    return bool(_PROVERA.search(t)) or t.endswith("?")


def tvrdi_pravni_autoritet(tekst) -> bool:
    """True ako tekst predstavlja pravni autoritet (nivo 1, uvek) ili pravno pravilo van pitanja za proveru (nivo 2)."""
    t = " ".join(str(tekst or "").split())
    if _AUTORITET.search(t):
        return True
    return bool(_PRAVILO.search(t)) and not oznaceno_kao_provera(t)
