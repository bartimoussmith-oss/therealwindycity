# Verifier repair: release gates

Candidate implementation: 3e99ad8ae05cd34f31cf40aa151110c7dfefe628. Production remains at the PR #28 merge until a separately reviewed release.

Sixteen offline regression tests passed locally against source whose Git blob matched e2a41524137121b8401773508f9f2c9a0f5f9050. Network and generator boundaries were mocked. Run `python3 tools/test_wyoming_verify.py` in CI as well; this is not live or full integration verification.

## Do not declare statewide activation complete
- Existing instantiation tests reject enabled sources and nonempty timelines. Separate pristine-render tests from operational-state tests before applying reviewed sources.
- Full generator --write still replaces facts.json and env.sh; define durable local overrides before real onboarding. The candidate only prevents verifier-driven overwrite.
- Correct odd-year municipal-election guidance in generator and generated text. W.S. 22-2-104 establishes even-year general elections; 22-23-201 normally aligns municipal elections, with exceptions under 22-23-202. Source: https://sos.wyo.gov/Forms/Publications/ElectionCode.pdf
- Generated engine contacts and root config still contain placeholders. The new verifier uses the public repository issues URL rather than an inferred personal email.
- Approval and denial fields need provenance, schema validation, and direct generator enforcement. Current denial takes effect when the verifier updates verification state.
- Add transactional write/rollback tests and stricter robots.txt content validation.
- No live sweep or deployment verification was completed in this test pass.

## Functional tradeoff
The conservative candidate does not follow redirects, infer site platforms, or auto-enable discovered agenda paths. Exact registry-approved URLs are required. Do not describe it as feature-equivalent to the original discovery implementation.

## Onboarding evidence
All 23 county clerks have source-listed sites and mailing contacts in the Secretary of State 2026 Voter Guide, pages 6-7: https://sos.wyo.gov/Elections/Docs/2026/2026_Voter_Guide.pdf. These are elections-office directory entries, not confirmation of the proper PRA custodian for every record category.

WAM identifies 99 municipalities: https://wyomuni.org/about/membership-directory/. This supports the count, not an exact roster or legal-classification reconciliation.
