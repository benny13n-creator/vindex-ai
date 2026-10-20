# -*- coding: utf-8 -*-
"""Night Sprint IV — Task 6: jedino pravilo važenja overenog (LAWYER_VERIFIED) vektora, tabelarno.

`services/law_brain.vazece_overe` odlučuje i za Law Brain i za RAG (`app/services/retrieve._vazece_overe_matcheva`)
da li se overen nacrt sme servirati. Opoziv i pozajmljen roditelj su već pokriveni (NS008 T20/T21); ovde i stanja
koja nisu ni prošla overu: nacrt na čekanju, odbijen, `approved` bez `is_lawyer_approved`, roditelj drugog predmeta,
nepostojeći roditelj, vektor bez roditelja.
"""
import pytest

import tests.ns005_harness as h5
from services.law_brain import vazece_overe

P1, P2 = "aaaaaaaa-6666-4000-8000-000000000001", "aaaaaaaa-6666-4000-8000-000000000002"


def _baza():
    return h5.Baza({"staging_memory": [
        # NS4-R2: overen vektor važi samo uz `pinecone_indexed=True` (potpun upis) — v. test_ns4r_nezavisni_pregled
        {"id": "s-ok", "predmet_id": P1, "status": "approved", "is_lawyer_approved": True, "pinecone_indexed": True},
        {"id": "s-nepotpun", "predmet_id": P1, "status": "approved", "is_lawyer_approved": True,
         "pinecone_indexed": False},
        {"id": "s-ceka", "predmet_id": P1, "status": "pending", "is_lawyer_approved": False},
        {"id": "s-odbijen", "predmet_id": P1, "status": "rejected", "is_lawyer_approved": False},
        {"id": "s-bez-overe", "predmet_id": P1, "status": "approved", "is_lawyer_approved": False},
        {"id": "s-pending-flag", "predmet_id": P1, "status": "pending", "is_lawyer_approved": True},
    ]})


@pytest.mark.parametrize("parent,predmet,vazi", [
    ("s-ok", P1, True),
    ("s-nepotpun", P1, False),      # odobren, upis u indeks nepotpun/pao
    ("s-ceka", P1, False),
    ("s-odbijen", P1, False),
    ("s-bez-overe", P1, False),
    ("s-pending-flag", P1, False),
    ("s-ok", P2, False),            # overa „pozajmljena" drugom predmetu
    ("s-nema", P1, False),          # roditelj ne postoji
    (None, P1, False),              # vektor bez roditelja
])
def test_pravilo_vazenja_overe(parent, predmet, vazi):
    assert (str(parent) in vazece_overe(_baza(), [(parent, predmet)])) is vazi


def test_greska_baze_se_propusta_ne_otvara():
    b = _baza()
    b.greske["staging_memory"] = Exception("db down")
    with pytest.raises(Exception):
        vazece_overe(b, [("s-ok", P1)])
