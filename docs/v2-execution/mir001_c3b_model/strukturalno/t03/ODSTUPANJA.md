# TASK-03 — odstupanja od prethodne registracije i tok izvršenja

1. **Prvo pokretanje (14 izlaza A_00–C1_03) bez ijednog stvarnog poziva modela.** `tests/conftest.py` blokira naplative
   hostove (`NetworkAccessBlocked`, BaseException), a `tests/ns005_harness.py` zabranjuje svaki ne-loopback
   `socket.connect`. Ruta je vratila 500, odnosno 503. Pokretanje je zaustavljeno, a izlazi su obrisani (nisu
   ocenjivani). Ništa nije poslato API-ju i ništa nije naplaćeno.
2. **Ispravka harness-a (samo merni alat, kod proizvoda nepromenjen):**
   - stvarno pokretanje ide uz `VINDEX_TEST_ALLOW_NETWORK=1`;
   - za trajanje jednog stvarnog `_pozovi_nacrt_api` vraća se pravi `socket.connect`, a posle poziva ponovo brana;
   - zapis dobija `greske_modela` (samo vrsta izuzetka) i `sirov_izlaz_modela` i `poruka_modelu`, koji služe samo
     dijagnozi izvršioca i ne idu označivačima.
3. **Jedna provera stvarnog toka (A, 1 izlaz)**: 200, 1 poziv, 1 naplata, DOCX 409 (čuvar mesta), posle ispravke
   advokata 200. Izlaz je obrisan i ne ulazi u uzorak, a pun uzorak od 100 je generisan iz početka.
4. **Pun uzorak (100 izlaza)**: 100/100 je vratilo 200 (1 poziv i 1 naplata po nacrtu). 94 izlaza imaju čuvar mesta
   (DOCX 409), a 6 nema (DOCX 200). Mehaničke provere: `mehanicke_provere_rezultat.json`.
   - **P5, simulirana ispravka:** u 2/100 izlaza (H1_09, N1_00) izvoz i posle ispravke vraća 409. Uzrok je oznaka
     `[PROVERITI: adresa]` koju je model upisao u zaglavlje (red bez čuvara mesta). Simulacija iz prethodne registracije
     uklanja samo redove sa „[IZOSTAVLJENO“. Server je blokirao nerazrešeno `[PROVERITI …]`, kako ugovor izvoza i
     propisuje. Ovo se prijavljuje kao nalaz P5 i ostavlja recenzentu GATE-03; izvršilac ga ne prekvalifikuje.
   - **Simulacija uklanja cele redove sa čuvarom mesta**, pa nestaje i tekst podneska u istom redu (npr. „Tužilac
     osporava tvrdnje tuženog …“ ispred čuvara mesta). Tako se ponaša simulirani advokat, ne proizvod.
5. **Označivači:** svaki deo od 25 ocenjuje zaseban, svež agent (A1–A4, B1–B4). Pun paket od 100 nacrta (oko 180 hiljada
   tokena) ne staje u jedan kontekst. Svi delovi istog označivača imaju isto uputstvo, a paketi A i B su u odvojenim
   kopijama foldera.
6. **Dodatak paketu:** pored izvezenog DOCX-a (4a), označivač vidi i DOCX posle simulirane ispravke (4b). Bez toga se M8
   ne bi moglo oceniti u 94 izlaza sa blokiranim izvozom.
