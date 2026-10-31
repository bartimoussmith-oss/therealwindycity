#!/usr/bin/env bash
SHARD_ID=$(date +%Y-%m-%d-%H%M)
ORG_NAME="therealwindycity"
REPO_NAME="Promethean-Archive-${SHARD_ID}"
STAGING_DIR="shard_staging_${SHARD_ID}"

echo "[*] Auditing payload size for Shard Provisioning..."
if [ -d "artifacts/" ] && [ $(du -sm artifacts/ | cut -f1) -gt 90 ]; then
    echo "[*] Provisioning Linked Shard: $ORG_NAME/$REPO_NAME"
    gh repo create "$ORG_NAME/$REPO_NAME" --public -d "Promethean Storage Node" -y || true
    
    mkdir -p "$STAGING_DIR"
    cp -r artifacts/* "$STAGING_DIR/" 2>/dev/null || true
    cp database/promethean_evidence.db "$STAGING_DIR/promethean_evidence_backup.db" 2>/dev/null || true
    
    cd "$STAGING_DIR"
    git init
    git branch -M main
    
    find . -type f -size +90M | while read HEAVY_FILE; do
        split -b 90M "$HEAVY_FILE" "${HEAVY_FILE}.part_"
        rm "$HEAVY_FILE"
    done
    
    cat << 'INNER_EOF' > rejoin_payloads.sh
#!/usr/bin/env bash
find . -type f -name "*.part_aa" | while read FIRST_PART; do
    BASE_FILE="${FIRST_PART%.part_aa}"
    cat "${BASE_FILE}.part_"* > "$BASE_FILE"
done
INNER_EOF
    chmod +x rejoin_payloads.sh
    
    git add -A
    git commit -m "Promethean Storage Node: Authorized Data Ingestion"
    git remote add origin "https://github.com/$ORG_NAME/$REPO_NAME.git"
    git push -u origin main
    
    cd ..
    rm -rf "$STAGING_DIR"
    
    echo "- [Data Shard $SHARD_ID](https://github.com/$ORG_NAME/$REPO_NAME)" >> STORAGE_MANIFEST.md
    echo "[+] Shard provisioning complete."
else
    echo "[*] Payload within safe limits. No shard required."
fi
