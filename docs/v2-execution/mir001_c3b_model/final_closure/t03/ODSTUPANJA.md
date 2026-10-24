# TASK-03 (FINAL CLOSURE) — odstupanja od prethodne registracije

1. **Harness i uputstva su napisani posle commita prethodne registracije** (`6f9b584b`), a pre ijednog merenja:
   `t03_fc.py`, `paketi_fc.py`, `zbir_fc.py`, `UPUTSTVO_B1.md`, `UPUTSTVO_B23.md`. Merila i pravilo odluke su iz
   prethodne registracije i nisu menjani.
2. **Posle merenja dela A** u harness je dodato `FC_IZLAZ`, kako bi provera harness-a mutacijama pisala u zaseban
   folder i ne bi pregazila merenje. Merenje se time ne menja.
3. **Pre primene odluka B1** harness beleži i zamene advokata koje nisu nađene u tekstu (`zamene_nisu_nadjene`).
   Rezultat je 0 u svih 10 predmeta.
4. **`paketi_fc.py b23` je razdvojen na `b2` i `b3`** (isto seme za oba), jer se paket B3 pravi tek posle primene
   odluka B1. Šifre i ključevi su nastali iz istog semena kao što je planirano.
5. **Paketi su predati agentima kao kopije u izolovanim folderima scratchpad-a.** Ključevi (`kljuc_*.json`) nisu bili
   u folderu iznad paketa, za razliku od GATE-03.
6. **Uputstvo B1, tačka 5** (nerazrešena mesta `[PROVERITI …]`) preformulisano je pre predaje agentu, jer je prva
   verzija bila nejasna. Nijedan agent nije video prvu verziju.
7. **Širi regresijski skup je pokrenut bez `-p no:logging`.** Time su nestale greške postavke `caplog` iz TASK-00.
   Skup fajlova je isti (`scratchpad/fc_siri.txt`, 87 fajlova), a na HEAD-u je dodat i `test_mir001_c3b_usvajanje.py`.
8. **Posle GATE-03 (recenzent, NAPOMENA 1)** harness dobija proveru **K1b**: odobren tekst je TAČNO spoj usvojenih
   stavki uz advokatove zamene. Stara provera K1 bi propustila delimično procurelu odbačenu stavku (mutacija Y1). Deo A
   (110) i primena B1 (10) su ponovljeni sa novim harness-om: rezultat je isti, 0 povreda, uz K1b True u 120/120. Y1
   sada daje 10 povreda (`scratchpad/fc_mut03b.py`). Recenzent je istu tačnu rekonstrukciju nezavisno uradio za svih
   120 slučajeva pre ove dopune.
