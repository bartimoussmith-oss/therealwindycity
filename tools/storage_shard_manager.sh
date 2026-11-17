#!/usr/bin/env bash
set -euo pipefail

SHARD_ID=$(date -u +%Y-%m-%d-%H%M%S)
ORG_NAME="therealwindycity"
REPO_NAME="Promethean-Archive-${SHARD_ID}"
ROOT_DIR=$(pwd -P)

echo "[*] Auditing payload size for Shard Provisioning..."
if [ ! -d artifacts ] || [ "$(du -sm artifacts | cut -f1)" -le 90 ]; then
    echo "[*] Payload within safe limits. No shard required."
    exit 0
fi

for command in gh git python3 split; do
    command -v "$command" >/dev/null || { echo "::error::Missing dependency: $command" >&2; exit 1; }
done
if [ -z "${GH_TOKEN:-}" ]; then
    echo "::error::GH_TOKEN is missing. Configure PROMETHEAN_ARCHIVE_TOKEN in repository secrets; no shard created." >&2
    exit 1
fi
gh api user --jq .login >/dev/null
gh auth setup-git
if [ ! -f database/promethean_evidence.db ]; then
    echo "::error::Evidence database is missing; refusing incomplete archive." >&2
    exit 1
fi

STAGING_DIR=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/promethean-shard.XXXXXXXX")
trap 'rm -rf -- "$STAGING_DIR"' EXIT
cp -a artifacts/. "$STAGING_DIR/"
python3 - "$STAGING_DIR/promethean_evidence_backup.db" <<'PY'
import sqlite3, sys
with sqlite3.connect('file:database/promethean_evidence.db?mode=ro', uri=True) as source:
    with sqlite3.connect(sys.argv[1]) as target:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit('Evidence database backup failed integrity check')
PY

cd "$STAGING_DIR"
git init -b main
git config user.name "bartimoussmith-oss"
git config user.email "236240326+bartimoussmith-oss@users.noreply.github.com"
find . -type f -size +90M -print0 | while IFS= read -r -d '' heavy_file; do
    split -b 90M -- "$heavy_file" "${heavy_file}.part_"
    rm -- "$heavy_file"
done
cat > rejoin_payloads.sh <<'REJOIN'
#!/usr/bin/env bash
set -euo pipefail
find . -type f -name '*.part_aa' -print0 | while IFS= read -r -d '' first_part; do
    base_file="${first_part%.part_aa}"
    cat -- "${base_file}.part_"* > "$base_file"
done
REJOIN
chmod +x rejoin_payloads.sh
python3 - <<'PY'
import hashlib, json
from pathlib import Path
rows = []
for path in sorted(Path('.').rglob('*')):
    if path.is_file() and '.git' not in path.parts and path.name != 'SHARD_CHECKSUMS.json':
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        rows.append({'path': path.as_posix(), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()})
Path('SHARD_CHECKSUMS.json').write_text(json.dumps({'schema_version': 1, 'files': rows}, indent=2) + '\n')
PY
git add -A
git commit -m "Promethean Storage Node: checksummed public evidence backup"
# A failure is an error, never evidence that the repository already exists.
gh repo create "$ORG_NAME/$REPO_NAME" --public --description "Promethean public-record storage node"
git remote add origin "https://github.com/$ORG_NAME/$REPO_NAME.git"
git push -u origin main
LOCAL_SHA=$(git rev-parse HEAD)
REMOTE_SHA=$(git ls-remote origin refs/heads/main | cut -f1)
if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
    echo "::error::Remote shard revision did not verify; manifest unchanged." >&2
    exit 1
fi
cd "$ROOT_DIR"
printf -- '- [Data Shard %s](https://github.com/%s/%s) — commit `%s`\n' "$SHARD_ID" "$ORG_NAME" "$REPO_NAME" "$REMOTE_SHA" >> STORAGE_MANIFEST.md
echo "[+] Shard push revision verified and logged. Source artifacts preserved."
