#!/bin/bash
# Push workspace to GitHub. Token lives in ~/.gh_token (never committed).
cd ~/twc
T=$(cat ~/.gh_token)
git add -A
git -c user.name=civicwatch-bot -c user.email=civicwatch@users.noreply.github.com commit -qm "${1:-sync $(date -u +%Y-%m-%dT%H:%MZ)}" || true
git push -q "https://x-access-token:${T}@github.com/bartimoussmith-oss/therealwindycity.git" HEAD:main 2>&1 | grep -v x-access-token
echo "pushed $(git rev-parse --short HEAD)"
