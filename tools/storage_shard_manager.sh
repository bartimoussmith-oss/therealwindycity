#!/usr/bin/env bash
set -euo pipefail

# Keep payloads in the existing repository (a release per run); never provision repositories.
# Works with the workflow's own GITHUB_TOKEN (contents: write) -- no cross-account secret needed.
REPOSITORY="${GITHUB_REPOSITORY:-therealwindycity/TheReelWindyCity}"
INCLUDE_DB="${INCLUDE_DB:-1}"   # 0 when the database is already committed to the repository
if [ ! -d artifacts ] || ! find artifacts -type f -print -quit | grep -q .; then
    echo "[*] No harvested payload files to publish."
    exit 0
fi
export GH_TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
if [ -z "$GH_TOKEN" ]; then
    echo "::error::Storage publication requires GH_TOKEN or GITHUB_TOKEN; payloads were not published."
    exit 1
fi
: "${GITHUB_RUN_ID:?A workflow run ID is required}"
: "${GITHUB_SHA:?A source revision is required}"
ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"
[[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ && "$ATTEMPT" =~ ^[0-9]+$ ]] || exit 1
TAG="harvest-payloads-${GITHUB_RUN_ID}-${ATTEMPT}"
if gh release view "$TAG" --repo "$REPOSITORY" >/dev/null 2>&1; then
    echo "::error::Release already exists; refusing to overwrite archived evidence."
    exit 1
fi
TEMP_DIR=$(mktemp -d)
CREATED=0
cleanup() {
    status=$?
    # A run that fails after creating its draft release must not leave an orphaned draft behind
    # (21 such drafts, 4.8 GB, had piled up); the payload is re-harvested by the next run.
    if [ "$status" -ne 0 ] && [ "$CREATED" = 1 ]; then
        echo "[!] Publication failed; deleting unfinished draft $TAG."
        gh release delete "$TAG" --repo "$REPOSITORY" --yes --cleanup-tag >/dev/null 2>&1 || true
    fi
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT
PAYLOAD=(artifacts)
if [ "$INCLUDE_DB" = 1 ] && [ -f database/promethean_evidence.db ]; then
    sqlite3 database/promethean_evidence.db 'PRAGMA wal_checkpoint(TRUNCATE);'
    PAYLOAD+=(database/promethean_evidence.db)
fi
tar -czf "$TEMP_DIR/payload.tar.gz" -- "${PAYLOAD[@]}"
split -b 90M -d -a 6 "$TEMP_DIR/payload.tar.gz" "$TEMP_DIR/payload.part."
rm "$TEMP_DIR/payload.tar.gz"
(cd "$TEMP_DIR" && sha256sum payload.part.* > SHA256SUMS)
gh release create "$TAG" --repo "$REPOSITORY" --target "$GITHUB_SHA" --draft --prerelease \
    --title "Harvest payloads: run ${GITHUB_RUN_ID}, attempt ${ATTEMPT}" \
    --notes 'Raw public-source payloads and a database snapshot. This is not certification of complete records coverage or of website indexing. Verify SHA256SUMS, then reconstruct with: cat payload.part.* | tar -xz'
CREATED=1
gh release upload "$TAG" "$TEMP_DIR"/payload.part.* "$TEMP_DIR/SHA256SUMS" --repo "$REPOSITORY"
# Draft releases are not served by /releases/tags/{tag} (always 404); find the draft in the release list instead.
gh api "repos/$REPOSITORY/releases?per_page=100" > "$TEMP_DIR/releases.json"
python3 - "$TEMP_DIR" "$TAG" <<'PY'
import json, sys
from pathlib import Path
root, tag = Path(sys.argv[1]), sys.argv[2]
matches = [r for r in json.loads((root / "releases.json").read_text()) if r.get("tag_name") == tag]
if not matches:
    raise SystemExit("Draft release for " + tag + " was not found; nothing was published")
(root / "remote.json").write_text(json.dumps(matches[0]))
PY
python3 - "$TEMP_DIR" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
remote = json.loads((root / "remote.json").read_text())
assets = {asset["name"]: asset for asset in remote["assets"]}
for path in [*sorted(root.glob("payload.part.*")), root / "SHA256SUMS"]:
    asset = assets.get(path.name, {})
    expected = "sha256:" + hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
    if asset.get("size") != path.stat().st_size or asset.get("digest") != expected:
        raise SystemExit("Uploaded asset verification failed: " + path.name)
PY
gh release edit "$TAG" --repo "$REPOSITORY" --draft=false --prerelease
CREATED=0   # published: never delete it from here on
gh api "repos/$REPOSITORY/releases/tags/$TAG" > "$TEMP_DIR/published.json"
python3 - "$TEMP_DIR/published.json" <<'PY'
import json, sys
release = json.load(open(sys.argv[1]))
if release.get("draft") is not False:
    raise SystemExit("Release is not publicly published; manifest was not updated")
PY
LINK="https://github.com/$REPOSITORY/releases/tag/$TAG"
LINE="- [Harvest payload $TAG]($LINK) — SHA-256-verified archive parts; partial collection, not coverage certification."
if ! grep -Fqx -- "$LINE" STORAGE_MANIFEST.md 2>/dev/null; then
    printf '%s\n' "$LINE" >> STORAGE_MANIFEST.md
fi
echo "[+] Payload publication verified: $LINK"
