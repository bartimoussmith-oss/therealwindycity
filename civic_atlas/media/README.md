# Separate Media Drop Studio

Routes after publication: /therealwindycity/media/, /therealwindycity/media/builder.html, /therealwindycity/media/review.html. These routes are planned, not verified live.

Three standalone pages share local CSS, JavaScript and six editorial drafts sourced from three repository-held proceedings across 2008, 2012 and 2026. No existing page is overwritten. Serve the repository over HTTP to preview; opening file:// does not support the JSON fetch reliably.

Features: historical library/filter, editable deterministic copy generation, Facebook post, teaser, video SCRIPT, carousel COPY, reporter brief, source sheet, browser-only saved draft, JSON/text downloads, explicit review checklist. No AI service, full-corpus ingestion, MP4 render, image render, publishing API, factual certification, multi-user review, or automatic upload is implemented. Draft edits can invalidate source support; the editor must recheck. Downloads and browser storage may contain unverified text. Public seed drafts are clearly labeled historical and unreviewed.

Source coverage: extracted proceedings for May 27, 2008; June 25, 2012 (filename/header discrepancy flagged); August 10, 2026. Not an exhaustive historical sweep. The short excerpts are text fragments, not verified audio quotations. Original viewer URLs are discovery links and were not opened during source selection. File blob SHAs identify the inspected extracted text; main-branch source URLs may change.

Build validation: python tools/publish_media_studio.py --check-only
JavaScript syntax: node --check civic_atlas/media/studio.js
Publication integration still required: add the media paths to the existing ai-record-pages push filters, run the validation and JS syntax checks before the existing build, then run python tools/publish_media_studio.py --out _site AFTER the normal renderer and BEFORE upload-pages-artifact. Verify /media/, /media/builder.html, /media/review.html and /media/drops.json after deployment. Do not create a separate deploy-pages workflow that replaces the existing site artifact.

This branch commit does not trigger the current Pages path filter and does not publish. Merge and deployment integration require separate approval. Browser rendering and end-to-end downloads have not been tested in this environment.
