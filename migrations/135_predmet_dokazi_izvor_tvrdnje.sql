-- 135 — predmet_dokazi.izvor_tvrdnje (NS006 Task 4)
--
-- Ko je AUTOR tvrdnje. `izvor_snage` (118) govori ko je odlucio o SNAZI, ne ko je
-- napisao tvrdnju: rucni unos bez procene snage i AI unos koji DC-005 nije nasao
-- u dokumentu oba daju `izvor_snage = podrazumevano`. Bez ove kolone ljudska
-- tvrdnja i tvrdnja modela se ne mogu razlikovati.
--
--   covek             = upisano kroz rucni unos advokata (routers/evidence.py::add_dokaz)
--   ai_klasifikacija  = upisao model pri klasifikaciji dokumenta
--                       (routers/evidence.py::klasifikuj_i_sacuvaj)
--   NULL              = autor nije zabelezen (redovi pre ove migracije, ili upis
--                       pre njenog pokretanja — pisac tada izostavlja kolonu)
--
-- Nullable i bez DEFAULT-a namerno: autor postojecih redova se ne moze
-- rekonstruisati, a podrazumevana vrednost bi ga izmislila. Citalac
-- (shared/genome_contract.py::poreklo_tvrdnje) NULL tretira kao "nije poznato".
--
-- Bez backfill-a, bez UPDATE, bez okidaca, bez CHECK-a: vokabular drzi
-- shared/evidence_write.py::IZVORI_TVRDNJE, jedini pisac ove kolone (isti obrazac
-- kao 118). Aplikacija radi i PRE pokretanja ove migracije: pisac izostavlja
-- kolonu kad je nema, a citalac je cita samo ako postoji.

ALTER TABLE predmet_dokazi
  ADD COLUMN IF NOT EXISTS izvor_tvrdnje TEXT;

COMMENT ON COLUMN predmet_dokazi.izvor_tvrdnje IS
  'Autor tvrdnje. covek = rucni unos advokata. ai_klasifikacija = model pri klasifikaciji dokumenta. NULL = autor nije zabelezen (stari red ili upis pre migracije 135); citalac ga tretira kao nepoznat, nikad kao ljudski.';
