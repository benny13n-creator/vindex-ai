# -*- coding: utf-8 -*-
"""NS4 nezavisni pregled — Zadatak 5: granice preračuna `case_patterns` (G1/G2).

Do NS4 završnog zatvaranja ovde su bila dva STROGA xfail-a nad `routers.learning._preracunaj_obrasce` (Python
čitanje → računanje → upis u zasebnim PostgREST pozivima):
  G1  zastareo preračun prepisuje tačan zbir (poslednji pisac pobeđuje);
  G2  postojeći faktori bez straničenja — iznad max-rows preračun puca usred petlje.

Ispravka (migracija 139): ishod i zbir upisuje JEDNA transakcija u bazi (`zabelezi_ishod_predmeta`) — brava po
korisniku, zbir skupovno iz `outcome_log`, bez ograničenja broja redova. Svojstva G1/G2 sada se dokazuju kao
PROLAZNI testovi nad STVARNIM PostgreSQL-om u `tests/test_ns4f_pg_ishod.py`:
  G1  test_g1_drugi_pisac_ceka_i_vidi_prvi_upis, test_mnogo_istovremenih_pisaca_ispravki_i_promena_vrste,
      test_izuzetak_usred_preracuna_vraca_i_ishod, test_prekid_procesa_pre_commit_ne_ostavlja_nista
  G2  test_g2_tacno_i_vise_od_hiljadu_faktora_bez_skracivanja[100-1000 / 130-1300]
Ovaj fajl čuva da se ranjiv put ne vrati: ruta ne sme ponovo da računa ili piše zbir mimo transakcije.
"""
import inspect

import routers.learning as L


def test_g1_g2_nema_vise_preracuna_mimo_transakcije():
    assert not hasattr(L, "_preracunaj_obrasce"), "vraćen ne-atomski Python preračun"
    izvor = inspect.getsource(L.zabeleži_ishod)
    assert 'table("case_patterns")' not in izvor and "table('case_patterns')" not in izvor
    assert 'table("outcome_log").upsert' not in izvor, "ishod se opet upisuje van transakcije sa zbirom"
    assert L._RPC_ISHOD in ("zabelezi_ishod_predmeta",) and "supa.rpc(_RPC_ISHOD" in izvor
