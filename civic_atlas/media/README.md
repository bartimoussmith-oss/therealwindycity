# Separate Media Drop Studio

Publication routes after an approved merge and successful deployment: /therealwindycity/media/, /therealwindycity/media/builder.html, /therealwindycity/media/review.html. These are not verified live merely because a branch commit exists.

Three separate pages share local CSS, JavaScript and six editorial drafts from three extracted proceedings across 2008, 2012 and 2026. No existing page is overwritten. Serve over HTTP; file:// JSON fetching is not supported.

Implemented: historical library/filter, editable template-based Facebook posts, teasers, video scripts, carousel copy, reporter briefs, source sheets, browser-local draft storage, text/JSON downloads and a personal editorial checklist. No LLM integration, full-corpus ingestion, video/image rendering, publishing API, independent certification or multi-user workflow. Changing a claim requires fresh evidence review.

Source coverage: May 27, 2008; June 25, 2012 (filename/header discrepancy flagged); August 10, 2026. Not an exhaustive historical sweep. Excerpts are text fragments, not verified audio quotations. Original viewer links and later developments require review. Blob hashes identify the inspected extracts; main-branch URLs may change.

Checks:
- python tools/publish_media_studio.py --check-only
- python -m unittest discover -s tools -p 'test_media_studio.py' -v
- node --check civic_atlas/media/studio.js

The existing ai-record-pages workflow validates feature/media-drop-studio without building or deploying the full archive. On main, it preserves the normal renderer, GIS workspace copying, sealed arrest-page build and deployment safeguards, and copies the Media Studio into _site/media before uploading the same Pages artifact. A deployment step compares all six public asset files against the checkout.

Tests check source blob hashes, supporting text fragments, unique drop IDs, asset references and preservation of existing pages during copying. They do not establish factual completeness, legal conclusions, original recording accuracy, browser rendering or end-to-end download behavior. No test success or deployment success is claimed until its actual run is inspected.
