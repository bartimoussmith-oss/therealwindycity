# Packet audit — Finance Committee, Nov 3, 2026 (Items 22A, 22B, SWAT armor)

**What this does:** takes every factual claim made at the microphone on
Nov 3 — staff's and Miller's — and checks it against the three supporting-
document packets the committee actually had, page by page. It also audits the
packets themselves (do the fee tables foot? what's missing?) and pulls the
historical record for these contracts from the repo corpus and both GitHub
accounts (`bartimoussmith-oss`, `therealwindycity`).

**Method in one line:** pypdf text extraction of all 46 packet pages
(SHA-256 fingerprints and page map in `packets/README.md`); image renders to
read the scanned Form #3 and the CAD/fee-table pages the text layer drops;
every fee table re-footed by hand; history from `2026-09-14-council/
civicwatch/` briefs + extracted packet texts, `pipeline/notebooklm/`
minutes, and `uploads/` work-session transcripts. GitHub code-search API
queries across both accounts returned **no items** for `7782`, `8081`, or
`AARDVARK` — the archive repos' mega-files exceed the code-search index, so
the local corpus in this repo (which mirrors that material) is the search
surface used. `civicwatch.py search` itself won't run in this sandbox
(missing `requests`); its precomputed briefs and text extractions were used
instead. Verdicts: ✔ confirmed on the packet's face · ◐ confirmed with
correction/nuance · ✘ not supported as stated.

**Headline results**

1. **Miller's packet citations hold up.** Almost everything he read into the
   record checks out verbatim — including the two facts the outcomes now
   turn on: the word "Lottery" appears **nowhere** in any of the three
   packets, and **neither SOLE nor SINGLE is circled** on Form #3 (verified
   visually from the scan).
2. **Three corrections Miller should make before Nov 9** (details in §2/§3):
   the armor "specify" subtotal is **$94,510, not $94,290**; the armor is
   **IIIA-class (UL3A), not "IIA"** as transcribed; and the *legal notice*
   claims only "single source" — the sole/single contradiction is inside the
   Purchasing memo and Form #3, which is actually the stronger version.
3. **A new finding bigger than the one argued on Nov 3 (R-1):** the Exhibit 3
   fee table's printed subtotals foot to **$487,072**, but the sheet states
   an "Overall Add-Service Total" of **$620,427** — a **$133,355 difference
   that cannot be traced to any printed column** (structural, electrical,
   branding and railroad-advisor columns are entirely blank while their work
   is described in the scope text). The $250,427 city share (#2c) is, on the
   face of DHM's own letter, the arithmetic remainder
   ($620,427 − $370,000 RCE-available), not a bottom-up sum. The RCE detail
   sheet (#2d, pp. 28–29) by contrast foots to $370,000.00 **exactly**.
4. **22A's packet is the thinnest of the three:** the MOU references a Work
   Plan and Budget "Appendix A" that **is not attached**, so the claimed
   within-grant reallocation of $39,800 cannot be verified from anything the
   committee was given.
5. **History reframes Moody's lone "no":** he was also the **lone no on the
   underlying BNSF 22905 Agreement** at the May 11, 2026 Governing Body
   meeting. His Nov 3 dissent fits a standing position on the corridor deal,
   not necessarily a reaction to the Nov 3 testimony.

Governing Body dates from the packets themselves: armor legal notice says
**voted on at the November 9, 2026 City Council meeting** (packet p. 3);
Form #3 carries City Council dates "October 26 & November 9, 2026"
(referral + vote). The 22A/22B instruments have blank signature blocks
awaiting that approval.

---

## 1. Item 22A — National Forest Foundation MOU (Contract #8081), 8 pp.

What the committee was given is **only the restated MOU** — no staff memo, no
fiscal summary, no exhibits. Title block: "SEPTEMBER 2026 MODIFICATION."

| Claim (staff report) | Packet check | Verdict |
|---|---|---|
| Term extends Oct 31, 2026 → Oct 31, 2027 | p. 1 WHEREAS; §2 restates term Nov 1, 2024 – Oct 31, 2027 | ✔ |
| Amount $110,000 → $149,800 | p. 1 WHEREAS (§5a); §5a p. 3 | ✔ |
| "No additional financial commitment from the City" / reallocated within the $250k grant, Endowment approved | Grant #24-00799 / City Contract #8038 named (p. 3, §3); WHEREAS asserts Endowment approval. **No budget table anywhere in the 8 pp.; the "Work Plan and Budget (Appendix A)" invoked in §1 is not attached** | ◐ asserted, **unverifiable from packet** |
| City is merely grant holder; NFF does the work | §4: NFF is "project implementation lead"; §5: City disburses/administers | ✔ |
| (not stated on mic) what the $149,800 may be spent on | §5a restricts disbursement "for the Community Coordinator's staff time and travel costs" — narrower than the oral "management" framing | new |
| (not stated on mic) city match obligation | §5d: City "shall … Ensure that the grant match is met by City and Cheyenne Board of Public Utility staff" — so "no financial commitment" means no *cash*; staff-time match exists | new |

Drafting defects on the face of the instrument:

- **§3 vs §5a tension:** "Neither Party shall have any obligation to make any
  payment of any kind to the other Party under this MOU" (§3) sits against
  "Disburse grant funds … to NFF for $149,800" (§5a). The bridge is §3's
  second sentence (payments occur under grant Contract #8038), but the
  committee was not given #8038 either.
- **Indemnity boilerplate from a different template:** §6e covers liabilities
  arising from "the performance of the **Licensee's** duties" — there is no
  licensee in this MOU.
- **No §7:** numbering runs §6 (General Provisions a–n) straight to
  "8. Signatures."
- **Retroactivity:** a document titled "September 2026 Modification,"
  created Oct 7 / last modified Oct 15 (PDF metadata), acted on Nov 3 — three
  days *after* the original Oct 31, 2026 expiry. The restated §2 ("commence
  on November 1, 2024") papers over the gap; minutes should reflect that.

None of this makes 22A a bad deal — the watershed logic staff gave (Rob Roy /
Hog Park, beetle kill, $1,227,176 SRF loan at 75% forgiveness = $920,382
forgiven, NFF covering the $306,794 balance + fees) is coherent. But the
committee approved a $39,800 reallocation with **zero budget documentation in
hand**. One-line fix for Nov 9: attach Appendix A.

**History sweep for #8081:** the minutes corpus in this repo
(`pipeline/notebooklm/cheyenne_minutes_2024–2026.md`) contains no mention of
Contract #8081 or the National Forest Foundation — consistent with a
consent-agenda MOU approved in late 2024 (term commencement Nov 1, 2024 is
the only date anchor available locally). No prior modification found; this is
billed as Modification #1. Grant Contract #8038 is likewise not in the local
extracted corpus. *Open pull:* Granicus search for the fall-2024 8081/8038
approvals if the original budget categories matter.

---

## 2. Item 22B — Reed Avenue / DHM Design (Contract #7782), Mod #2, 29 pp.

### 2.1 The money, re-footed

Packet p. 3 (Cobb memo) and p. 6 (modification form) agree, and both foot:

| Component | Fund | Amount |
|---|---|---|
| Original contract | — | $1,281,279.20 |
| Previous modifications | — | $39,640.00 |
| Prior to Mod #2 | — | $1,320,919.20 |
| #2a Expanded street improvements (Bent→Snyder) | 5th penny 2023–26 | $466,620 |
| #2b Parking lot & pedestrian access (20th–21st) | 6th penny | $79,600 |
| #2c Railroad coordination / replenishment | 6th penny | $250,427 |
| #2d FRA design elements / NEPA | $277,500 FRA grant 69A365242140RCEWY + $92,500 city 25% match (6th penny) | $370,000 |
| **Mod #2 total** | $277,500 + $466,620 + $422,527 | **$1,166,647** ✔ |
| New contract total (NTE) | | $2,487,566.20 ✔ |

Miller's headline numbers — $1,166,647, **88.3% increase**, $2,487,566.20 new
total, completion to **April 30, 2028** (memo p. 3, form p. 6 §III) — all ✔.

One safety valve Miller didn't mention (form p. 6): *"If a fee stated in an
attached exhibit differs from the corresponding not-to-exceed fee in this
Contract Modification, the amount stated in this Contract Modification
controls."* Every exhibit discrepancy below is therefore capped at the
contract numbers — sloppiness, not open-ended exposure. It also means staff
*drafted around* known exhibit inconsistencies instead of reconciling them.
Note also p. 6 §V: the FRA grant GL account is still "[to be assigned by City
Treasurer prior to execution]" at approval time.

### 2.2 #2b parking lot — Miller's central claim, verified

- **"Lottery" appears 0 times in all three packets** (full-text grep). The
  memo (p. 1) describes only "design of a parking lot … at the southern end
  of the corridor"; the form (p. 5) "a parking area located between 20th and
  21st Streets"; Exhibit 2 (pp. 15–19) "redesign the parking lot between 20th
  and 21st Streets, adjacent to the Reed Avenue Rail Corridor" — owner never
  identified. ✔ Non-disclosure confirmed.
- Closest the packet comes: Exhibit 1's fee table budgets meetings with
  "Property Owners (**Tribune Eagle, State of Wyoming**, etc.)" — i.e., the
  design team knows a state owner is in play; the packet still never says the
  20th–21st lot itself is state (Wyoming Lottery) land under negotiation.
  That fact exists *only* in Cobb's oral testimony.
- Deliverables are 60% / 90% / **100% plan sets** with bid items, quantities
  and SWPPP (p. 15) — final construction documents, as Miller said, for land
  the city does not own, before any purchase approval. ✔
- **The three-totals problem is real, with one refinement:** Exhibit 2's
  letter (p. 16) lists $29,300 + $31,500 + $18,800 + $196 expenses and prints
  "Total: $79,800," but those components sum to **$79,796** — DHM's letter
  doesn't foot to its own printed total (off $4). Its fee table (pp. 17–18)
  foots cleanly: task subtotals $30,216 + $30,506 + $18,882 = $79,604 + $196
  = **$79,800**, but every phase figure differs from the letter's. Contract
  NTE is **$79,600** (controls, per §2.1). Miller's arithmetic ✔ on all three.
- **Severance drafting trap (new):** the parking lot's *drainage* design is
  not in #2b at all (#2b expressly excludes "storm sewer/drainage
  analyses," p. 16) — it sits in **#2a**, as "Site drainage design/report
  for parking lot," 12 hrs in each of Tasks 2 and 3 at the $155 stormwater
  rate = **$3,720** (Exhibit 1 fee table). A clean severance motion must
  carve that line out of #2a too, or the city still pays to design drainage
  for the un-bought lot.

### 2.3 #2c/#2d replenishment — the backfill is admitted, and the total doesn't foot

Miller's characterization is, if anything, *understated* against Exhibit 3
(pp. 20–21, DHM letter of Sept 4, 2026 transmitting the Jan 14, 2026 work
plan — "fee table dated January 14th, 2026, 9 months ago" ✔):

- *"Under our original agreement … the 30% design phase was anticipated to
  consist primarily of **hand-drawn conceptual graphics** … BNSF's review
  process, however, required **developed CAD drawings**"* (p. 20) — verbatim
  as Miller read it. ✔
- *"DHM Design **elected to continue responding** to these evolving project
  needs … rather than interrupting the design process"* and *"resources that
  had originally been allocated for later Design Development and Construction
  Document phases **were utilized** … The purpose of this additional services
  request is therefore to **replenish those design-phase resources**"* (p. 20).
  The memo repeats the mechanism (p. 2). Neither document identifies any
  prior council authorization for the out-of-scope work or the phase-budget
  draw; the first council action is this after-the-fact replenishment. ✔
- *"Updated hourly rates from 2023"* is listed as a scope-summary bullet
  (p. 21): the replenishment is priced at updated rates, and **no 2023-vs-2026
  rate schedule is anywhere in the packet** to test the increase. (History:
  DHM was hired June 2023 after Cobb terminated Wilson & Company in Aug 2022
  — Oct 10, 2025 work-session transcript, `uploads/`.)

**Finding R-1 — the $133,355 that won't foot.** Re-footing the Exhibit 3 work
plan (pp. 22–26) column by column (and visually confirming pp. 23/26):

| Column (p. 26 "Overall Project Design Sub-Total") | Printed |
|---|---|
| DHM Design (3 staff @ $225/$145/$125) | $60,300 + $53,650 + $36,500 |
| GLM Design, stormwater/grant @ $155 | $112,995 |
| Quandel, Class 1 rail (LS) | $170,145 * |
| BenchMark, civil (LS) | $33,882 |
| HydroSystems, irrigation (LS) | $4,600 |
| Ground Eng., geotech (LS) | $15,000 |
| JVA structural · JCAA electrical · Granite Peak environmental · Warehouse 21 branding · Mike Pannell railroad | **blank** |
| **Sum of printed subtotals** | **$487,072** |
| Stated "Overall Add-Service Total #2c, #2d" | **$620,427** |
| **Untraced difference** | **$133,355** |

\* The Quandel column total ($170,145) silently absorbs Granite Peak's
$26,112 environmental lump sum from Task 2 ($72,016+$57,613+$14,404 railway
track plans = $144,033; + $26,112 = $170,145) — Granite Peak's own column
total is blank.

Every task subtotal row foots into these column totals exactly, so the
$133,355 is not hiding in arithmetic — it corresponds to **no priced column**.
Meanwhile the scope text describes work for the blank columns (structural
foundations for plaza monuments/fencing/shade structure, full electrical/
lighting design incl. LED monument lighting, branding/website/signage —
pp. 22–24). Either that work is priced inside the untraced $133,355 without
a breakout, or it is unfunded scope. And DHM's letter (p. 21) builds the ask
top-down: "Available for RCE Grant Repayment … $370,000 / City Add-Service
Amount: $250,427 / Total: $620,427" — the city share is presented as a
remainder after available grant money, not as a bottom-up sum. **The
committee approved a $620,427 component whose own work plan foots to
$487,072.** Fair caveat: a tie-out may exist outside the packet (the RCE
sheet's $370k is built from overlapping Quandel/Granite/GLM pricing — see
below). What the packet does not contain is any reconciliation, and neither
the memo nor the oral testimony mentioned one. This is the single best
question for Nov 9: *produce the $133,355 tie-out on the record.*

For contrast, **#2d's RCE detail sheet foots perfectly**: Quandel+DJ Mitchell
$185,067.20 + Granite Peak $65,000 + GLM task subtotals
$28,480+$4,272+$34,888+$49,128 + expenses $3,164.80 = **$370,000.00 exactly**
(pp. 28–29). Cross-checking the two sheets raises the obvious overlap
question the packet never answers: Quandel is priced at $144,033 of railway
track plans in the main table *and* $185,067.20 in the RCE sheet; Granite
Peak at $26,112 *and* $65,000; GLM project management at $112,995 *and*
$116,768. Are the RCE-sheet amounts the same dollars re-presented for grant
repayment, or additive? If re-presented, the two tables double-describe
roughly a quarter-million dollars — and still leave the $133,355 unexplained.

**Finding R-2 — #2a exhibit total also differs:** Exhibit 1's letter and fee
table both foot to **$466,627** ($185,108 + $137,356 + $144,117 + $46
expenses), $7 over the $466,620 NTE (controls clause caps it). Exhibit 1's
task rows also slip a "19th Street" into the Task 1 street list that appears
nowhere else in the #2a scope.

**Finding R-3 — packet assembly:** the identical 30% schematic sheet (SP1.0)
is reproduced **twice** (pp. 14 and 19, text-identical), under legacy labels
"Add Service #2 / #3," while Exhibit 3's letter still calls #2c/#2d
"Add-Service #1." Three numbering schemes across one modification, stitched
from January and September documents. Minor, but it's why the packet is hard
for anyone — council included — to foot.

**Finding R-4 — what's inside "replenishment":** the Exhibit 3 work plan
includes Project Branding, Website & Signage/placemaking (QR codes, blog,
1-year hosting — "Partially Completed"), Public Open House #2, railroad
protective liability insurance + flagger ($7,500), geotechnical borings
($7,500), and items already marked "Completed" carrying fresh project-
management hours (pp. 22–23). Whether branding/website scope belongs in a
*sixth-penny design replenishment* or is FRA-eligible is a segmentation
question the packet never poses. (Its Warehouse 21 column is one of the
blank ones in R-1.)

### 2.4 Reed Ave history (repo corpus)

- **2017** 6th-penny ballot: $4M for Reed Ave (corridor study had said
  ~$5.5M). **2019** Wilson & Co. hired; **Aug 2022** Cobb terminated Wilson;
  **June 2023** DHM hired; BNSF preliminary engineering agreement same month.
  **Jan 2025** FRA Rail Crossing Elimination award **$2.5M + $853,500 match**
  (~$3.4M total). **Oct 10, 2025 work session:** north-component construction
  estimate $12.4M + 20% contingency ≈ **$14.9M**; Councilwoman Aldrich on
  record: *"out of $4 million we've expended 2.6 million on just plans and
  consultants over eight years."* (All: 2025-10-10 work-session transcript
  in `uploads/`.) Against that baseline, Mod #2 takes the DHM design contract
  alone to $2,487,566.20, and construction funding was, as of that work
  session, a *future* 6th-penny proposal — worth asking Nov 9 what pays to
  build the side-street reconstruction #2a is designing to 100% CDs.
- **BNSF 22905 Agreement timeline corroborates Cobb:** referred to Finance
  Committee as a consent item **Apr 27, 2026**, approved by Governing Body
  **May 11, 2026** (briefs `brief_2026-04-27_clip1093.md`,
  `brief_2026-05-11_clip1095.md`; minutes `cheyenne_minutes_2026.md`).
  Minutes record the May vote as *all yes except **Mr. Moody voting "no"***,
  with Miller commenting and Moody/White raising points of order that he was
  off subject. The 22905 packet document itself was scanned (no extractable
  text in the civicwatch corpus) — its ROW-compensation clause can't be
  verified locally; Cobb's $275k–$350k estimate stands as oral testimony only.
- **Nov 3 claim check on crossing scope:** the RCE sheet (p. 28) prices
  exactly the four closures Cobb described — 17th, 18th, 21st, Dillon (east
  of 24th) — with 19th/20th/22nd channelized with gates and 23rd/24th
  quiet-zone medians marked "(ADDED)." Note the RCE design reaches **24th
  Street**, one block beyond the 17th–23rd limits described orally.
- DHM is a repeat city vendor (voucher records in `civicwatch/data/text/`:
  Contract #7958 15th Street Master Plan, #8122 Parks & Rec, etc.) —
  context for the "continuity" justification; no Reed-specific payment
  ledger was reconstructed here.

---

## 3. SWAT armor — Aardvark Tactical Project 7, $142,800, 9 pp.

### 3.1 Claim-by-claim

| Miller claim (Nov 3) | Packet check | Verdict |
|---|---|---|
| Form #3 (signed Oct 16, 2026) says CIRCLE ONE; neither circled | **Visually confirmed** from the p. 2 scan: heading reads "STATE REASON FOR SOLE OR SINGLE SOURCE PURCHASE (CIRCLE ONE)"; no circle on either word. The only circles on the form are Purchasing's two "Yes" marks (letter attached / legal ad attached) | ✔ |
| Memo + legal notice claim both classifications | Memo p. 1, adjacent sentences: "This is a **single source** purchase, therefore no bids were requested. The PROJECT 7 … products are **sole source**, made exclusively by and sold exclusively through AARDVARK Tactical." Legal notice p. 3 says **only** "single source." Form #3's typed reason adopts the vendor's "sole source" sentence | ◐ contradiction is memo+form, not the notice — correct the citation, keep the point |
| Justification copied word-for-word from Aardvark's Jan 9, 2026 letter, incl. typo "ROM" | Side-by-side: memo p. 1 and Form #3 both reproduce the letter's two sentences (pp. 4) verbatim; memo drops the "f" ("or **rom** any other source"), Form #3 spells "from." Letter is generic ("To whom it may concern," signed Brittany Baeza, Account Management Supervisor). No independent CPD evaluation, test record, or market survey anywhere in the 9 pp. | ✔ |
| Vendor admits third-party components (Blue Force Gear UltraComp, FirstSpear Tubes) | p. 5, verbatim | ✔ (his add-on "standard SAPI-sized plates" is from the p. 6 marketing sheet, not the p. 5 list — immaterial) |
| 7 of 11 line items say Specify Color/Size, totaling $94,290 | 7 items confirmed (platforms, yoke, throat, upper arm, abdominal, groin, battle belt). They sum to **$94,510** | ◐ **correct the total: $94,510** (off by $220) |
| All 52 plates one size (SAPI Large), $31,980 | p. 8: "Rifle Plate/Level 3++/Ceramic Stand Alone/Lightweight/**SAPI Large**" ×52 @ $615 = $31,980. vs p. 5 "No Guess Sizing System … tailored fitting" and p. 6 "SAPI based hard armor coverage **sized to the individual operator**" | ✔ |
| 150-day delivery, non-returnable, 25% restocking | p. 9: "DELIVERY: 150 Days after receipt of order"; returns within 15 days w/ possible 25% restocking; "**Customized orders are non-returnable**" | ✔ (nuance: standard goods returnable ≤15 days; customized — which sized armor is — non-returnable) |
| $5,492.31 per set | $142,800 ÷ 26 | ✔ |
| "NIJ-level IIA" | Packet specifies **Ultralight 3A** soft armor throughout ("3A Ballistic," Form #3 description and quote) — IIIA class. "Level 3++" plates are a vendor designation; **"NIJ" appears nowhere in the packet** — no certification/compliance documentation at all | ◐ **correct to IIIA**; new point: zero NIJ paperwork in packet |

Rest of the quote foots exactly: 11 equipment lines $141,960 + $840 freight
(Old Dominion, palletized) = **$142,800**; every unit-price × quantity line
recomputes correctly (pp. 8–9). Quotation **S02435** (read on mic as
SO2435), salesperson Tiffany Hanke, quote date Oct 16, **expires Nov 27,
2026** — 18 days after the Nov 9 vote, so a two-week paperwork hold does not
kill the price; ordered promptly, 150 days ARO puts delivery ~April 2027.

Packet quality notes (new): the memo calls the product the "Ballistic Body
**Armory** System"; Form #3's division-head approval block carries a
signature and date (10/16/26) but **no printed name**; the pouch-set SKU
suffix is "-MC" while the platform sub-note specifies "OD/OD" — if MC denotes
MultiCam (see p. 6 color list), the quote mixes colorways across a
"fully integrated system." What's *absent*: any expiration date for the
current SWAT vests, any operator sizing roster justifying 26 identical
plate sizes, any SHSP grant terms/deadline, any warranty terms. Funding line
on p. 1: acct 025-21-2111-41-46528, Project #97910, SHSP ✔ as stated on mic.

Fairness note on the circle-one defect: the city's own Form #3 fuses the two
categories throughout ("Sole/Single Source Letter Attached"), so staff can
credibly say Cheyenne's form treats them as one request type. The durable
defect is narrower and stronger: **the form's explicit CIRCLE ONE instruction
was not complied with, the memo then uses both terms for one purchase, and
the entire substantive justification is the vendor's own marketing
sentences** — thin paper for a $142,800 non-competitive buy on a federal
pass-through grant, where 2 CFR 200 noncompetitive-procurement grounds must
be documented by the recipient, not the seller.

### 3.2 History

- No prior Aardvark armor purchase in the searched corpus. Aardvark appears
  only as a small-dollar Fire/TEMS medical-supply payee on 2025 voucher
  reports ($1,573; $625; $625 — `civicwatch/data/text/791.txt`, `894.txt`).
- Pattern precedent: **$161,826 Musco sole-source purchase, Finance Committee
  Apr 21, 2026, approved unanimously** over a competitive-bidding objection
  (verified in `ACCESS-TEST-2026-10-16.md`). Sole/single-source items reach
  this committee regularly and pass; the Nov 3 armor item is the norm, not an
  outlier — which is precisely why the paperwork standard matters.

---

## 4. What to file / say on Nov 9 (packet-verified version)

File the full text with the Clerk (both Nov 3 speeches lost their second
half to the clock; armor "defect 4" and 22B "defects 3–4" exist in no
record). Orally, three questions now carry packet page numbers staff must
answer on mic:

1. **22B / Exhibit 3:** "Exhibit 3's work plan foots to $487,072 on page 26,
   but the same page states $620,427. Before this body approves $250,427 of
   sixth-penny money as the remainder, have the City Engineer put the
   **$133,355 tie-out** on the record — which subconsultants, which tasks —
   and state whether the Quandel, Granite Peak and GLM amounts on pages
   28–29 are the same dollars already counted in the main table."
2. **22B / #2b severance, amended:** sever #2b ($79,600) *and* the parking-lot
   drainage line inside #2a ($3,720), conditioned on an executed Wyoming
   Lottery purchase — converting Councilman Wolf's Nov 3 "properly sequence"
   assurance into motion text. Cite: the word "Lottery" appears in none of
   the 46 packet pages; ownership was disclosed only orally.
3. **Armor:** hold to the corrected numbers — $94,510 in unspecified
   color/size lines; UL3A, not IIA; quote valid to Nov 27. Ask: circle one
   on Form #3, file the city's own justification (not pp. 4–5 of the
   vendor's letter), file the 26-operator sizing basis for 52 SAPI-Large
   non-returnable plates, and file NIJ compliance documentation (currently:
   none in packet).

Also worth one sentence each: 22A — attach Appendix A before signature;
22B — what fund pays the $275k–$350k BNSF right-of-way payment, and what
pays to *construct* the #2a street reconstruction now being designed to 100%
documents?

## 5. Sources & limits

- Packets: owner-supplied PDFs, SHA-256 + page map in `packets/README.md`;
  extracted texts alongside. Page cites are packet pagination.
- Rendered-image verifications: armor p. 2 (Form #3), 22B pp. 14/19
  (SP1.0 duplicate), 23, 26, 29 (fee-table footing).
- History: `2026-09-14-council/civicwatch/briefs/` (2026-04-27, 2026-05-11),
  `2026-09-14-council/civicwatch/data/text/` voucher extractions,
  `pipeline/notebooklm/cheyenne_minutes_2026.md`,
  `uploads/Work_Session_-_6th_Penny_Presentation_-_Reed_Avenue_Corridor_-_10-10-25.md`,
  `ACCESS-TEST-2026-10-16.md`.
- GitHub: repo inventories for `bartimoussmith-oss` (6 repos) and
  `therealwindycity` (9 repos incl. `cheyenne-archives-*`, `The-Real-Windy-City-`)
  enumerated 2026-11-03 via `gh`; code-search API returned no items for the
  three contract/vendor terms (mega-file index limits), so cross-repo claims
  rest on this repo's mirrored corpus — negative results ("no prior X found")
  mean *not in the mirrored/extracted corpus*, not *never happened*.
- The executed BNSF 22905 Agreement, grant Contract #8038, Appendix A to the
  NFF MOU, original PSA #7782 and Modification #1 ($39,640; utility locating
  per a Granicus agenda found in web search, not in the local corpus), and
  SHSP grant terms were **not available** and are flagged as open pulls
  wherever they bear on a finding.
