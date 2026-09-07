# AI-POISONING / AUDIT-RESISTANCE FORENSIC AUDIT — GB DOCKET, AUGUST 24, 2026
*Scope: the Aug. 24 agenda (event_id=1438) + all 20 supporting documents as captured from Granicus MetaViewer, tested for adversarial engineering — deliberate or otherwise — that would degrade, mislead, or throw off an AI-assisted audit. Companion: `docket-2026-08-24-gb.md`, `redteam-2026-08-24-agenda.md`, `unicode-audit.py` (byte-level tool for local use on downloaded originals).*

---

## VERDICT (read this first)

**EFFECT: CONFIRMED.** The docket's machine-readable layers are hostile to automated audit in five specific, catalogable ways — a scrambled text layer on the DDA map (decrypted below), extract-hostile table structures that misattribute dollar amounts, a cluster of corrupted date/digit fields, systematic proper-noun garble in the transcript corpus, and fine-print structural burial of major items.

**INTENT: UNPROVEN — and the evidence mostly points away from deliberate poisoning.** Every textual anomaly examined is consistent with known platform artifacts (broken font encodings, xlsx→PDF export interleaving, recycled form templates, ASR phonetic failure on names). No prompt-injection payloads, no adversarial suffixes, no keyword-stuffing signatures, and — the decisive statistical tell — the garble is **phonetics-correlated, not topic-correlated** (details in §3). What IS deliberate is the **structural layer**: consent-designating 73% of the money, announcing major ordinance returns in announcement fine print, the calendar incidents. That isn't AI poisoning; it's audit resistance that works on humans and machines alike — and it needs no conspiracy to explain.

**The sharpest true sentence:** *you don't need to poison a well that was never drinkable — the city publishes pictures of text and tables that scramble on extraction, and its video platform transcribes names through a broken telephone.* The remedy ask writes itself: **publish documents as native text.**

---

## 1. EXHIBIT TABLE

| # | Exhibit (doc) | Anomaly | Effect on AI audit | Most likely cause | Intent read |
|---|---|---|---|---|---|
| T1 | DDA district map (149973) | **Entire map text layer is character-shifted −29 ASCII** (decoded: "created by the City of Cheyenne GIS," "Miles," "DDA Boundaries," "Existing DDA / Adopted Expansion"); plus a phantom street grid "W.3RD ST" through "W.123TH ST" extracted in sequence | Map boundaries **cannot be found by any search**; an LLM ingesting the layer records 120+ nonexistent streets | Broken CID/ToUnicode font table in the ArcGIS PDF export — the shift is *uniform and trivially reversible*, the opposite of stealth | Artifact (high confidence) |
| T2 | Voucher report (149983) + p-card xlsx (149987) | **Row interleaving on extraction**: amounts migrate to wrong vendor/department cells (e.g., NAPA $118,104.14 rendered against "Budget & Finance / July 2026 Payroll"; a floating $997.83 with no vendor; blank-amount rows mid-table) | An automated audit **misattributes expenditures** — the single most dangerous failure mode for fiscal analysis, because it produces confident false facts | xlsx→PDF/markdown cell-ordering in the export pipeline | Artifact (high confidence); effect is severe regardless |
| T3 | Liquor form (149989), Motorola pack (149979) | **Date/digit corruption cluster**: form says "Formerly Held by **1134** Partners LLC" where the agenda says **1734**; "Date filed 7/30/**2024**," ads "8/13 & 8/20/**2024**" on a 2026 hearing; dept-head approval box dated "8/19/**2024**" while requester signs 8/19/**2026**; Motorola "Quote Date: 08/04/**2021**" in a 2026 packet; expiration date split across a line break ("10/03/ 2026") | Cross-referencing by date or license number **fails silently** — the auditor concludes records don't exist or doesn't match what does | Recycled form templates (the 2024 dates are *internally consistent as a set* — vintage template, not selective tampering); OCR digit confusion (1↔7, 1↔4) | Artifact (medium-high confidence); the 1134/1734 swap is exactly what OCR does to digits |
| T4 | STC memo (149977) | **Name variance inside one document**: header "FROM: TJ **Barttelbort**, Purchasing Manager"; signature block "**TF Battista**" | Entity resolution fails — an audit cannot tell if purchasing has one manager or two | Signature stamp from a predecessor/different signatory left in the template | Artifact (high confidence) — but catalogued because name-variance is precisely what a poisoning attack would simulate |
| T5 | Ardurra/CSRE memos (149961/149963) | Title variance: "Erin Gates, PE, Staff Engineer" vs. "Erin Gates, PE, **Senior** Staff Engineer" (same month) | Minor entity noise | Template reuse | Artifact |
| T6 | Motorola quote (149979) | **Address block interleaving**: "CHEYENNE ANIMA / CONTROL / 800 SW DR / CHEYENNE, WY 820 / 01" — the word ANIMAL and ZIP 82001 are split across table cells | Address normalization fails | PDF table extraction | Artifact |
| T7 | DDA map + memos generally | OCR garble on image-based content ("Benthie Grove," "Mesaive," "Dollove" for street names; [Image: R12] placeholders for signatures/seals) | Non-machine-readable content silently **absent** from any automated review | Image-first publishing (documents as pictures of text) | **Policy choice, not accident** — this is the layer where "engineering" is fair to allege: the city could publish native text and doesn't |
| T8 | Transcript corpus (mega_file, historical) | Systematic ASR garble: Rinne→"Renie," Segrave→"Crave/Secret," Emmons→"Evans/Emmens/Ern," Aldrich→"Aldridge," Greeley→"Gley," Walterschied→"Waltershide," Topanga→"Tanga," W.S. 11-49-102→"1149102," agritourism→"agurism" | Exact-string search **fails on the movement's own key names and statutes** — canonized as "absence-of-hit ≠ absence-of-content"; every audit must run proxy-string methodology | ASR phonetic failure, consistent per speaker across sessions | Artifact (see §3 statistical test) — the platform default; note the city also **disabled comments on its videos** (~April, per record), which compounds it |
| T9 | Agenda structure (tonight + Aug. 9 incident) | **Structural burial**: three April-postponed ordinances return via announcement sub-item 12g; $351,790 comp plan under [CA]; Sept.-14 triple-header set via two announcement lines; (historical) Aug. 10 meeting missing from the city's own calendar 24h out with a "hidden agenda anchor link" (the Chokepoint incident) | Defeats triage — the important items are engineered to *look* unimportant at exactly the layer where any auditor (human or AI) allocates attention | Administrative practice | **Deliberate or customary, either way it works** — the strongest "engineering" finding in this audit lives here, not in the bytes |

---

## 2. THE DECODED EXHIBIT — T1, the map that cannot be searched

The DDA boundary map's text layer renders as gibberish ("0DSFUHDWHGE\WKH&LW\RI&KH\HQQH*,6"). It is not gibberish. It is a **uniform ASCII shift of −29** on the embedded font's character map. Proof by decryption of four strings:

- `([SDQVLRQ` → **Expansion**
- `0LOHV` → **Miles**
- `'$%RXQGDULHV` → **DDA Boundaries**
- `E\WKH&LW\RI&KH\HQQH` → **by the City of Che[y]enne** (with the backslashes decoded as *y*)

This matters in both directions. **Against the poisoning theory:** a deliberate adversary encodes *irreversibly and unevenly*; a uniform, reversible shift that decodes "Miles" and "Boundaries" alongside the sensitive strings is a font table with a broken ToUnicode map — an export artifact, and a gift to anyone who bothers to decode it. **For the audit-resistance thesis:** the practical result stands — no keyword search, scraper, or LLM ingest will ever surface the DDA boundaries from this document as published. The information is public and unreachable in the same breath. That is the docket's text layer in miniature.

## 3. THE STATISTICAL TELL — phonetics vs. topic

Deliberate AI poisoning targets **what the auditor needs** (keywords: annexation, referendum, names, statute numbers) while leaving irrelevant text clean. Platform failure (ASR/OCR) targets **what the machine mishears** (phonetically odd proper nouns, fast-spoken numerals) regardless of topic.

Test against the corpus: the garble clusters on **names and spoken-aloud numbers** — "Renie," "Crave," "Tanga," "1149102" (statute read as one number), "agurism" — while the movement's core vocabulary survives intact: "Food Freedom" ×8 clean, "annexation" throughout, "urban farm" ×17, "electric fence" ×4. If the transcript layer were topic-poisoned, the reverse distribution would appear. It doesn't. **The transcript garble is a microphone with a speech impediment, not a man in the middle.**

## 4. WHAT WAS *ABSENT* (negative findings, equally important)

No prompt-injection strings ("ignore previous instructions," role-play hijacks, fake system text) in any of the 20 documents. No adversarial-suffix patterns. No keyword stuffing or anomalous repetition. No homoglyph signatures visible at the rendered-text layer (byte-level test requires the originals — see §6). No metadata anomalies observable through this capture path.

## 5. THREAT MODEL — if someone *wanted* to poison this pipeline, what they'd do

For the page's own methodology (and because the city's p-card shows a **$20 ChatGPT subscription in Budget & Finance** — both sides run AI now), the attack menu against an AI auditor is: (a) zero-width/homoglyph swaps inside key names — defeats exact-match while looking clean to humans; (b) date/digit field corruption — defeats cross-referencing (already occurring by accident at T3); (c) table interleaving — defeats fiscal attribution (already occurring at T2); (d) structural burial — defeats triage (already occurring at T9); (e) image-only publishing — defeats everything (standing policy at T7). **The docket already exhibits four of five — all with benign proximate causes.** The correct posture is not "they're poisoning us"; it is *"the pipeline is poison-compatible, verify at byte level, and demand native text."*

## 6. BYTE-LEVEL PROTOCOL (what this capture could NOT test)

`fetch`-rendered markdown cannot carry invisible Unicode. To close the gap, `unicode-audit.py` (this workspace) runs on the **downloaded originals** (save the MetaViewer PDFs / view-source HTML) and reports: zero-width characters (U+200B–200D, FEFF), homoglyphs (Cyrillic/Greek lookalikes), non-ASCII inventory per document, control characters, digit-variance in date fields, and duplicate-text-with-different-bytes (the poisoning smoking gun). **Chain of custody, per house discipline:** log filename + SHA-256 + capture time for every original; the page's timestamps are its credibility.

## 7. THE REMEDY ASK (add to the podium list)

One sentence, zero cost, unanswerable without transparency: **"Will the city commit to publishing agenda supporting documents as native searchable text rather than image-based PDFs, and to correcting the broken text layer on posted maps?"** If the answer is yes — the audit gets easier. If no — the audit-resistance thesis graduates from inference to on-record admission.

## 8. DISCIPLINE BOX (for any post on this subject)

- Never use the word "poisoning" about the city without byte-level proof — the verified claim is **"audit-hostile by construction or neglect."**
- The decoded map shift (−29) is publishable as a curiosity WITH its benign explanation — it demonstrates the page's technical depth without overclaiming.
- The T2 table-interleaving is the one finding that can silently corrupt the page's OWN fiscal claims — always re-verify any dollar attribution against the PDF image before publishing a number from these tables. (The docket file's figures were checked against memo headers, not table rows, for exactly this reason.)
- The structural findings (T9) are the strong ones — they're already documented, on the record, and need no speculation.
