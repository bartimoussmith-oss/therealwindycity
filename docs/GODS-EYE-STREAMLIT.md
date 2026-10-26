# Full God's Eye application in Streamlit

## Scope and coordination

Owner-requested additive work, 2026-10-26: only new `pages/26_Gods_Eye_View.py` and this document. No existing page, entrypoint twin, dependency, dataset, workflow, credential or upstream repository is modified. This bounded scope does not overlap the existing page scopes inspected in READ-FIRST.md.

## Implemented behavior

The independent page embeds the full application at the owner-configured `GODS_EYE_APP_URL`. It does not reproduce a reduced globe or run Node in Streamlit Community Cloud. The URL is read from the server environment first, then Streamlit secrets. Empty or invalid configuration fails closed. The external frame loads only after the visitor opts in. The direct-open button is the fallback for framing restrictions and browser features.

## Required setup

1. Deploy the full upstream `bilawalsidhu/gods-eye-view` application on a separate suitable Node/Docker host. The upstream revision inspected during preparation was `301bc2e0b301600d1bd57c9ab89cdf1e181a304c`; no copy of that source is bundled here. Review its current security and provider terms before exposing it publicly.
2. Protect provider setup and secret-bearing endpoints. Configure allowed hosts for the actual deployment. Do not expose local provider-settings privileges through a public proxy. Supply API credentials only through the host's secret management.
3. In this Streamlit deployment's secrets, set `GODS_EYE_APP_URL` to the deployed application's public HTTPS root URL. No credentials, query string or fragment are accepted. The URL is public once the page is enabled; it must not contain a secret.
4. Open the God’s Eye View page from Streamlit's existing pages navigation. Enable loading and verify the actual globe and supported feeds. Use the separate-tab fallback if framing or browser permissions prevent an embedded feature.

## Acceptance gates

- The new page appears in the deployed Streamlit sidebar and produces no exceptions.
- Missing/invalid URL shows a setup message and no iframe.
- A real configured endpoint serves the full upstream app, not its source-code page or a placeholder.
- The host permits framing by the real Streamlit origin; test CSP and X-Frame-Options.
- Verify globe rendering, provider errors, input/resize behavior and separate-tab fallback in a browser.
- Verify no credentials appear in browser responses, logs, URLs or committed files.
- Verify provider settings cannot be changed by unauthenticated public visitors.

## Evidence boundary

Adding this page does not provision a host, set Streamlit secrets, verify an endpoint, import civic records into the globe, or prove deployment. The hosting URL was unavailable at preparation time. Full integration must not be described as live until the host and deployed Streamlit page pass the checks above. Third-party data and assets remain under their own terms; the upstream MIT source-code license does not license all data.
