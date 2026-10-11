# BETA-DEF-003 — odbijeno prikačivanje (404) zaključava intake posao na 120 s

**Status:** otvoren, NIJE ispravljen (nije kritičan za izdanje). Otkriven u OSB002 Task 1.
**Ozbiljnost:** niska (UX, sam se oslobađa; nema curenja, nema pogrešnog upisa).

## Šta se dešava
`routers/smart_intake.py::_finalize_intake_job_core` prvo zauzme finalizaciju (`claim_intake_finalize`, upis
`finalizing_at`), pa tek onda proveri da li predmet za prikačivanje pripada pozivaocu. Ako ne pripada (ili je
obrisan), diže se 404 **bez oslobađanja zauzeća**. Susedne grane greške (konflikt brojeva predmeta, više kandidata)
oslobađaju ga (`finalizing_at = None`).

## Posledica
Sledeći pokušaj prikačivanja ISTOG posla, i u ispravan predmet, dobija 409 „Finalizacija je već u toku“ dok ne
istekne prozor zastarevanja (120 s, `shared/intake_queue.claim_finalize`). Posle toga radi normalno.

## Dostižnost u solo beti
V2 nudi samo sopstvene predmete korisnika. 404 nastaje samo ako je predmet obrisan između učitavanja liste i klika.

## Dokaz
`tests/test_osb002_solo_tok.py::test_dokument_ne_moze_u_tudj_predmet_ni_tudj_posao` opisuje sadašnje ponašanje
(409 odmah posle odbijanja, 200 posle isteka prozora, jedan dokument, nijedan upis u tuđi predmet).

## Predložena ispravka (čeka odobrenje)
Pre `raise HTTPException(404, "Predmet za prikačivanje nije pronađen.")` osloboditi zauzeće istim obrascem kao
susedne grane. Jedna linija; test bi tada očekivao 200 odmah.
