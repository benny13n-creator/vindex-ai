# MIR001 C3 — slepe oznake nacrta (nezavisni označivač, posle GATE-C3 1. prolaza)

Označivač (zaseban agent, uloga: iskusan parnični advokat) je pročitao svaki nacrt u celini **bez uvida** u proveru
(`routers/multi_agent.py`), njen rečnik, testove, ledger i ranije oznake. Definicije:

- **A** — nacrt traži da sud odbije dopunu veštačenja ili se protivi predlogu za nju kao da je otvoreno pitanje (samo
  skupovi u kojima je DOK-07 u spisu).
- **B** — A, ili nacrt bilo kojim rečima tvrdi da je naložena dopuna / dodatno veštačenje / dodatni dokazi / uvid u
  građevinski dnevnik nepotreban, ili implicitno traži odluku na osnovu postojećeg nalaza bez naložene dopune.
  „g“ = granično (npr. „dodatni uvid neće promeniti utvrđene činjenice“ — predviđanje ishoda); **B strogo** = bez graničnih.

Po nacrtu (N0..N4), B strogo (1 = protivrečno), i provera (`c3_provera_konacno.json`, broj označenih rečenica > 0):

| skup | A | B strogo (N0..N4) | granično | provera označila (N0..N4) | slaganje (strogo) |
|---|---|---|---|---|---|
| uzorci_t06 (TASK-06, pre C3) | 4 | 1 1 1 0 1 | N3 | 1 1 1 0 1 | 5/5 |
| uzorci_t06b (TASK-06, pre C3) | 3 | 0 0 1 1 1 | — | 0 0 1 1 1 | 5/5 |
| c3_osnova (pre C3, `3c8e1de8`) | 3 | 1 1 1 1 0 | — | 1 1 1 1 0 | 5/5 |
| c3_posle (blok, pravilo v1) | 0 | 1 0 1 0 1 | N3 | 1 0 1 0 0 | 4/5 — **promašen N4** |
| c3_posle2 (pravilo v2) | 0 | 1 1 1 0 1 | — | 1 1 1 0 1 | 5/5 |
| c3_posle2b | 0 | 1 1 0 0 1 | N3 | 1 0 0 0 1 | 4/5 — **promašen N1** |
| c3_posle2c | 0 | 1 0 0 0 0 | N1, N3 | 1 0 0 0 0 | 5/5 |
| c3_val1 | 0 | 1 0 0 0 0 | N3 | 1 0 0 0 0 | 5/5 |
| c3_val2 | 0 | 0 0 0 1 0 | N0, N1, N2 | 0 0 0 1 0 | 5/5 |
| c3_val3 | 0 | 1 1 0 1 1 | — | 1 1 0 1 1 | 5/5 |
| c3_val4 | 0 | 0 1 0 1 1 | N0 | 0 1 0 1 1 | 5/5 |
| c3_neg (bez DOK-07; protivljenje legitimno) | n/a | — | — | (provera se ne pokreće — nema odluka) | — |

Ukupno 55 nacrta sa DOK-07: B strogo = **31**; provera označila **29/31**, **0 lažno pozitivnih nacrta**; granični
slučajevi (10) — provera ne označava nijedan. Promašaji (neoznačeni, ručno potvrđeni):
- `c3_posle` N4: „Tužilac smatra da je nalaz veštaka već dovoljno jasan i da dodatna veštačenja nisu potrebna.“
  (zajednička je samo osnova „vešta“; „dodatna veštačenja“ nije „dopuna“).
- `c3_posle2b` N1: „Smatramo da je nalaz veštaka potpun i da ne zahteva dodatne dokaze u tom pogledu.“

Druge procesne nedoslednosti (označivač; provera ih ne vidi):
- **(G1) rok od 15 dana** (od 15.07.2026, istekao ≈ 30.07.2026): nijedan nacrt sa DOK-07 ne pita da li je tuženi
  dostavio dnevnik; mnogi ga tretiraju kao tekući („očekuje da će tuženi u predviđenom roku dostaviti“ — posle2b N3,
  „očekujemo da će se dostaviti“ — val4 N2).
- **(G2) nalaz veštaka kao utvrđen** („utvrđeno“, „već utvrđene činjenice“) u većini nacrta (DEBT-MIR-06-2).
- **ponovljena radnja**: „i povlači zahtev … od 600.000 dinara“ (val1 N0, val4 N2; granično posle2c N3, val4 N0,
  t06b N3) — povlačenje je izvršeno 15.07.
- **datum ročišta 18.11.2026** izostaje u većini nacrta (merilo TASK-06: 14/35).
- **negativni skup**: neg N0 pripisuje nalaz veštaka tuženom i spori ga protiv sopstvenog interesa; neg N2 „U
  Beogradu“ (izmišljeno mesto); neg N1–N3 prihvataju 3.150.000 uz neusklađenu vrednost spora.
