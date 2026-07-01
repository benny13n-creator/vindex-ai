# -*- coding: utf-8 -*-
"""
Vindex AI — services/confidence_calibrator.py

Confidence Calibrator: transformiše sirovi procenat AI-a u strukturirani,
dokazivi odgovor sa konkretnim razlozima.

Umesto: "65%"
Daje:
  VISOKO POVERENJE
  ✓ 194 slična predmeta u sudskoj praksi
  ✓ 17 presuda VKS
  ✓ 8 predmeta vaše kancelarije — win rate 73%

Ili:
  NISKO POVERENJE
  ✗ Nedovoljno sopstvenih predmeta za kalibraciju
  ✗ Različita sudska praksa po okruzima
"""
from __future__ import annotations

import logging
from typing import Optional

from services.learning_engine import learning

logger = logging.getLogger("vindex.confidence_calibrator")


class ConfidenceCalibrator:

    async def calibrate(
        self,
        user_id: str,
        tip_spora: str,
        raw_procenat: Optional[int],
        kontekst: dict,
        rag_hits: int = 0,
        vks_hits: int = 0,
    ) -> dict:
        """
        Strukturirani confidence sa konkretnim razlozima umesto suve cifre.

        Parametri:
          raw_procenat  — sirovi % iz GPT-a (može biti None)
          kontekst      — {"dokazi": [...], "rokovi": [...], "kriticni_rokovi": N}
          rag_hits      — broj sličnih odluka nađenih RAG pretragom
          vks_hits      — broj VKS odluka u RAG rezultatima
        """
        # Dohvati kancelarijske podatke
        kancelarija = await learning.get_confidence_data(user_id, tip_spora)
        uzoraka     = kancelarija.get("uzoraka_kancelarije", 0)
        win_rate    = kancelarija.get("win_rate_kancelarije")

        # ── Odredi nivo ────────────────────────────────────────────────────────
        nivo = self._odredi_nivo(rag_hits, vks_hits, uzoraka, win_rate, kontekst)

        # ── Sagradi faktore ────────────────────────────────────────────────────
        faktori_plus  = self._faktori_plus(rag_hits, vks_hits, uzoraka, win_rate,
                                           kancelarija, kontekst)
        faktori_minus = self._faktori_minus(rag_hits, uzoraka, win_rate, kontekst)

        # ── Kancelarija data za UI ─────────────────────────────────────────────
        kancelarija_data = None
        if uzoraka > 0:
            top_faktori = kancelarija.get("top_faktori_uspeha", [])
            kancelarija_data = {
                "win_rate":   win_rate,
                "uzoraka":    uzoraka,
                "top_faktor": top_faktori[0] if top_faktori else None,
            }

        # ── Objašnjenje ────────────────────────────────────────────────────────
        objasnjenje = self._objasnjenje(nivo, rag_hits, vks_hits, uzoraka, win_rate)

        boja = {"VISOKO": "zelena", "SREDNJE": "žuta", "NISKO": "crvena"}[nivo]

        return {
            "nivo":                   nivo,
            "boja":                   boja,
            "procenat":               raw_procenat,
            "faktori_plus":           faktori_plus,
            "faktori_minus":          faktori_minus,
            "kancelarija_data":       kancelarija_data,
            "pouzdanost_objasnjenje": objasnjenje,
        }

    # ─── Interni helperi ──────────────────────────────────────────────────────

    def _odredi_nivo(
        self,
        rag_hits: int,
        vks_hits: int,
        uzoraka: int,
        win_rate: Optional[float],
        kontekst: dict,
    ) -> str:
        kriticni_rokovi = kontekst.get("kriticni_rokovi", 0)

        # NISKO: mali RAG, ili kancelarija ima loš track record, ili kritični rokovi
        if rag_hits < 3:
            return "NISKO"
        if uzoraka >= 3 and win_rate is not None and win_rate < 40:
            return "NISKO"
        if kriticni_rokovi >= 2:
            return "NISKO"

        # VISOKO: dobar RAG + VKS + solidna kancelarija
        if rag_hits >= 10 and vks_hits >= 5:
            if uzoraka == 0 or (win_rate is not None and win_rate > 60):
                return "VISOKO"

        return "SREDNJE"

    def _faktori_plus(
        self,
        rag_hits: int,
        vks_hits: int,
        uzoraka: int,
        win_rate: Optional[float],
        kancelarija: dict,
        kontekst: dict,
    ) -> list[str]:
        faktori = []

        if rag_hits >= 10:
            faktori.append(f"{rag_hits} sličnih predmeta pronađeno u sudskoj praksi")
        elif rag_hits >= 3:
            faktori.append(f"{rag_hits} relevantnih sudskih odluka")

        if vks_hits >= 5:
            faktori.append(f"{vks_hits} presuda Vrhovnog kasacionog suda")
        elif vks_hits >= 1:
            faktori.append(f"{vks_hits} presuda VKS")

        if uzoraka >= 5 and win_rate is not None and win_rate >= 60:
            faktori.append(
                f"{uzoraka} predmeta vaše kancelarije — win rate {win_rate}%"
            )
        elif uzoraka >= 3 and win_rate is not None and win_rate >= 50:
            faktori.append(
                f"Kancelarija: {uzoraka} sličnih predmeta, win rate {win_rate}%"
            )

        top_uspeha = kancelarija.get("top_faktori_uspeha", [])
        if top_uspeha:
            faktori.append(
                f"Ključni faktor uspeha u kancelariji: {top_uspeha[0]}"
            )

        dokazi = kontekst.get("dokazi", [])
        if len(dokazi) >= 3:
            faktori.append(f"{len(dokazi)} dokaza priloženo u spisu")

        return faktori[:4]

    def _faktori_minus(
        self,
        rag_hits: int,
        uzoraka: int,
        win_rate: Optional[float],
        kontekst: dict,
    ) -> list[str]:
        faktori = []

        if rag_hits < 3:
            faktori.append("Nedovoljno sličnih predmeta u sudskoj praksi za pouzdanu procenu")
        elif rag_hits < 7:
            faktori.append("Ograničen uzorak sudske prakse — procena je indikativna")

        if uzoraka == 0:
            faktori.append("Kancelarija još nema zatvorenih predmeta ovog tipa za kalibraciju")
        elif uzoraka >= 3 and win_rate is not None and win_rate < 50:
            faktori.append(
                f"Kancelarija: win rate {win_rate}% na {uzoraka} predmeta ovog tipa"
            )

        kriticni = kontekst.get("kriticni_rokovi", 0)
        if kriticni >= 1:
            faktori.append(
                f"{kriticni} kritičan rok ističe — vremenski pritisak utiče na procenu"
            )

        nedostajuci = kontekst.get("nedostajuci_dokazi", [])
        if len(nedostajuci) >= 2:
            faktori.append(
                f"{len(nedostajuci)} dokumenata nedostaje u spisu"
            )

        return faktori[:3]

    def _objasnjenje(
        self,
        nivo: str,
        rag_hits: int,
        vks_hits: int,
        uzoraka: int,
        win_rate: Optional[float],
    ) -> str:
        if nivo == "VISOKO":
            delovi = [f"Visoko poverenje zasnovano na {rag_hits} sličnih predmeta u sudskoj praksi"]
            if vks_hits >= 5:
                delovi.append(f"{vks_hits} presuda VKS")
            if uzoraka >= 5 and win_rate:
                delovi.append(f"{uzoraka} predmeta kancelarije sa win rate {win_rate}%")
            return " i ".join(delovi) + "."
        elif nivo == "SREDNJE":
            if rag_hits >= 3:
                osnov = f"Srednje poverenje — {rag_hits} sličnih odluka u praksi"
            else:
                osnov = "Srednje poverenje na osnovu dostupnih podataka"
            if uzoraka > 0 and win_rate:
                osnov += f", kancelarija: {uzoraka} predmeta, win rate {win_rate}%"
            return osnov + "."
        else:
            if rag_hits < 3:
                return "Nisko poverenje — nedovoljno sudske prakse za pouzdanu procenu ovog tipa predmeta."
            return "Nisko poverenje — faktori rizika prevazilaze raspoložive pozitivne pokazatelje."


# ─── Singleton ────────────────────────────────────────────────────────────────
confidence_calibrator = ConfidenceCalibrator()
