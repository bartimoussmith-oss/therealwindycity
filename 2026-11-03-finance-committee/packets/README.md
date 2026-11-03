# Packets — provenance (Finance Committee, 2026-11-03)

Owner-supplied via chat upload 2026-11-03. Raw PDFs are **not** committed
(repo convention: public packets are re-fetchable; extracted text is the
archival form). SHA-256 fingerprints below let anyone verify a re-fetched
file is the same document audited in `../PACKET-AUDIT_2026-11-03.md`.

| Audit name | Original upload | SHA-256 | Size | Pages | PDF metadata |
|---|---|---|---|---|---|
| `packet-22A-nff-contract-8081.txt` | `Supporting_Document (54).pdf` | `25e5cb216e03d4ed0d794d76bb8b056cd2c64ec41c04ffcd9ad05128436a61de` | 976 KB | 8 | Author "Lara White", Word 365, created 2026-10-07, modified 2026-10-15 |
| `packet-22B-reed-dhm-contract-7782.txt` | `Supporting_Document (55).pdf` | `fbb72bdc4ccc49eca13fa3e05c08b2572c6114d108156ca2905d0ae98b935bc1` | 3.5 MB | 29 | Author "nathan", Word 365, created 2026-10-14, modified 2026-10-15 |
| `packet-SWAT-armor-aardvark.txt` | `Supporting_Document (56).pdf` | `47b6e834e0f90a20a79f695c0d7e1396ca8154757b66536cb9d7d159a4c74357` | 1.4 MB | 9 | Author "carol", Adobe Acrobat, created/modified 2026-10-21 |

Extraction method: pypdf text layer, page-marked (`===== PACKET PAGE n =====`).
Exceptions, all verified by rendering the page to an image and reading it:

- **22B packet pp. 14 and 19** defeated pypdf (CAD vector sheet). Recovered
  with pdfplumber and spliced in. The two pages are the *identical* sheet
  (30% schematic SP1.0) — byte-identical extracted text, confirmed by direct
  comparison.
- **Armor packet p. 2 (Form #3)** is a scanned image; the text layer holds
  only a date stamp. Rendered at 150 dpi and read visually for the audit
  (circled/not-circled, signatures, dates).
- **22B packet pp. 23, 26, 29** rendered to confirm fee-table column
  subtotals and blank subconsultant columns behind Finding R-1.

Content map:

- **22A (8 pp.)** — the restated MOU itself. *No staff memo, no Appendix A,
  no Endowment approval letter in the packet.*
- **22B (29 pp.)** — pp. 1–4 Cobb memo (2026-10-14); pp. 5–7 Contract
  Modification #2 form; pp. 8–14 Exhibit 1 (Add-Service #2a, DHM letter +
  fee table + SP1.0 sheet); pp. 15–19 Exhibit 2 (#2b parking lot, letter +
  fee table + same SP1.0 sheet again); pp. 20–29 Exhibit 3 (#2c/#2d, DHM
  letter 2026-09-04 + 2026-01-14 work plan pp. 22–27 + GLM/Quandel RCE
  sheet pp. 28–29).
- **Armor (9 pp.)** — p. 1 Purchasing memo (Barttelbort, 2026-10-21); p. 2
  Form #3 (scan, signed 2026-10-16); p. 3 legal notice (WTE, Oct 23 & 30);
  pp. 4–5 Aardvark sole-source letter (Baeza, 2026-01-09); pp. 6–7 Project 7
  marketing sheets; pp. 8–9 quotation S02435 (2026-10-16, expires 2026-11-27).
