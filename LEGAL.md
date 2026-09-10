# Legal & Ethics Contract

This engine is an accountability tool, not an intrusion tool. If a run you're
configuring would break one of these rules, the configuration is wrong.

## Hard rules baked into the code

1. **Public documents only.** The harvester fetches public pages and files from
   confirmed .gov / news endpoints. No logins, no paywall circumvention, no
   session spoofing, no endpoint probing.
2. **`robots.txt` compliance.** Uses `urllib.robotparser`; honors `Disallow:` and
   `crawl-delay` when present. If a site's Terms of Service prohibit automated
   collection, disable that source — do not work around it.
3. **Rate discipline.** Default ≥3 seconds between requests per host, one page of
   links per crawl, hard cap of 40 documents per source per run. This never runs
   hot enough to matter to a municipal server.
4. **Human-in-the-loop on outbound communication.** The engine *drafts* Wyoming
   PRA requests and public comments. A person reads, edits, signs, and sends them.
   There is deliberately **no** email/Twilio/auto-submission integration.
5. **Public-official scope.** Records and minutes concern officials acting in
   their official capacity. Do not add personal addresses, personal phone numbers,
   family members, or non-public personal data to any watchlist or output.
6. **Accuracy over narrative.** Every emitted claim must carry a verbatim quote,
   source URL, and fetch timestamp. AI-generated summaries are labeled with their
   method. Unverifiable items go in a notes/unverified bin — never the ledger.

## Not legal advice

The Wyoming Public Records Act templates cite Wyo. Stat. §§ 16-4-201 through
16-4-205 as commonly used by Wyoming requesters. Custodians may charge reasonable
fees; the template asks for a cost estimate first. If a request is denied or the
stakes are high (litigation, election timing), consult a Wyoming attorney — the
Wyoming Press Association and the regional Reporters Committee for Freedom of the
Press hotlines both cover open-records questions.
