# MIR002 — Release A recovery

Parent d95c11f77ee23f662b9d4739458edbb2863ddf5f. Release base da50b0203a90e9d9dbc9226e7492e4c303c61500. This branch excludes migration 148 and F4.

The agent context already filtered document metadata and text by matter and user. Extracts and source evidence derive from those filtered rows. Matter, its stored Genome summary, claims, issue roots and document classification audit rows are owner-scoped. Child links in the issue graph use the IDs of the owned roots; claims are read with both owner and matter filters. RAG in this workflow calls the legal library with the task query. This change adds explicit owner filters to the hearing summary, deadline hearings and billing entries. All use the privileged backend client.

An explicit missing or foreign matter produces the same 404 before the model, including automatic agent selection. The pipeline checks ownership before cache replay and still authorizes each step. A general question without a matter is unchanged. The model and successful billing path are unchanged. The isolated SQL test seeds foreign child rows under the same matter while running reads under service_role, checks actual outbound prompts and response source evidence, and uses synthetic FastAPI auth and provider stubs.

Intake now cites ZPP article 367 for the general first-instance judgment appeal deadline from service of the judgment copy, subject to other statutory periods, with the eight-day bill-of-exchange/check exception. The only locked prompt fingerprint changed is intake. Article 371 ZOO, procedural state and S02 corrections are retained. Official sources: https://pravno-informacioni-sistem.rs/SlGlasnikPortal/eli/rep/sgrs/skupstina/zakon/2011/72/2/reg and https://va.os.sud.rs/files/zakon_o_parnicnom_postupku.pdf.

Production execution, model quality, CI and real-user acceptance require separate evidence. See the final handoff for the exact tested commit and test outcomes.
