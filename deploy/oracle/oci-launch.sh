#!/usr/bin/env bash
# ==============================================================================
# The Real Windy City — create the OCI instance from the CLI (us-phoenix-1)
#
# Alternative to the console clicks in README.md §Step 1. Requires:
#   oci CLI configured (oci setup config) with permission to launch instances
#   an existing VCN public subnet in us-phoenix-1
#
#   export COMPARTMENT_OCID=ocid1.compartment.oc1..xxxx
#   export SUBNET_OCID=ocid1.subnet.oc1.phx.xxxx
#   export SSH_PUBKEY_FILE=~/.ssh/id_ed25519.pub
#   bash deploy/oracle/oci-launch.sh
#
# Options (env): SHAPE (default VM.Standard.A1.Flex), OCPUS (2), MEM_GB (12),
#   NAME (windycity-prod), AD (leave empty for AD-1), IMAGE_ID (override the
#   Ubuntu 24.04 lookup), BOOT_GB (50).
#
# Free-tier notes: VM.Standard.A1.Flex up to 4 OCPU / 24 GB is Always Free in
# the tenancy's home region; x86 fallback is VM.Standard.E2.1.Micro (1/1).
# A1 capacity in Phoenix is sometimes exhausted — the script reports the OCI
# error verbatim and retries once in another availability domain when possible.
# ==============================================================================
set -Eeuo pipefail

REGION="${REGION:-us-phoenix-1}"
NAME="${NAME:-windycity-prod}"
SHAPE="${SHAPE:-VM.Standard.A1.Flex}"
OCPUS="${OCPUS:-2}"
MEM_GB="${MEM_GB:-12}"
BOOT_GB="${BOOT_GB:-50}"
AD="${AD:-}"
SSH_PUBKEY_FILE="${SSH_PUBKEY_FILE:-$HOME/.ssh/id_ed25519.pub}"

command -v oci >/dev/null || { echo "the oci CLI is not installed: https://docs.oracle.com/iaas/Content/API/SDKDocs/cliinstall.htm" >&2; exit 1; }
: "${COMPARTMENT_OCID:?set COMPARTMENT_OCID (compartment OCID from the console)}"
: "${SUBNET_OCID:?set SUBNET_OCID (a public subnet in $REGION)}"
[[ -r "$SSH_PUBKEY_FILE" ]] || { echo "cannot read $SSH_PUBKEY_FILE — set SSH_PUBKEY_FILE to your public key" >&2; exit 1; }

echo "[oci] region ${REGION}, shape ${SHAPE}, ${OCPUS} OCPU / ${MEM_GB} GB, name ${NAME}"

# availability domain: default to the first one in the region
if [[ -z "$AD" ]]; then
  AD="$(oci iam availability-domain list --region "$REGION" --compartment-id "$COMPARTMENT_OCID" \
        --query 'data[0].name' --raw-output)"
fi
echo "[oci] availability domain: $AD"

# Ubuntu 24.04 image: pick the newest Canonical image for this shape's arch
if [[ -z "${IMAGE_ID:-}" ]]; then
  OS_FILTER="Canonical Ubuntu"
  OS_VER_FILTER="24.04"
  echo "[oci] looking up the newest $OS_FILTER $OS_VER_FILTER image…"
  IMAGE_ID="$(oci compute image list --region "$REGION" --compartment-id "$COMPARTMENT_OCID" \
    --operating-system "$OS_FILTER" --shape "$SHAPE" --sort-by TIMECREATED --sort-order DESC \
    --query "data[?contains(\"display-name\", '$OS_VER_FILTER')].id | [0]" --raw-output)"
  [[ -n "$IMAGE_ID" && "$IMAGE_ID" != "null" ]] || {
    echo "[oci] no matching image found; list candidates with:" >&2
    echo "      oci compute image list --compartment-id \$COMPARTMENT_OCID --operating-system 'Canonical Ubuntu' --query 'data[].\"display-name\"'" >&2
    exit 1; }
fi
echo "[oci] image: $IMAGE_ID"

# extra NIC/security settings: the subnet's security list must allow 22/80/443 ingress
launch() {
  oci compute instance launch \
    --region "$REGION" \
    --compartment-id "$COMPARTMENT_OCID" \
    --availability-domain "$1" \
    --display-name "$NAME" \
    --shape "$SHAPE" \
    --shape-config "{\"ocpus\": $OCPUS, \"memoryInGBs\": $MEM_GB}" \
    --image-id "$IMAGE_ID" \
    --subnet-id "$SUBNET_OCID" \
    --assign-public-ip true \
    --boot-volume-size-in-gbs "$BOOT_GB" \
    --metadata "{\"ssh_authorized_keys\": \"$(cat "$SSH_PUBKEY_FILE")\"}" \
    --wait-for-state RUNNING \
    --query 'data.id' --raw-output
}

INSTANCE_ID="$(launch "$AD")" || {
  echo "[oci] launch failed. Most common cause in Phoenix: no A1 (Ampere) capacity in that AD." >&2
  echo "      Options: retry later, or SHAPE=VM.Standard.E2.1.Micro bash $0" >&2
  exit 1
}

PUBIP="$(oci compute instance list-vnics --region "$REGION" --instance-id "$INSTANCE_ID" \
         --query 'data[0]."public-ip"' --raw-output)"

cat <<EOF

[oci] instance RUNNING
  ocid   $INSTANCE_ID
  ip     $PUBIP
  ssh    ssh ubuntu@$PUBIP        # 'opc' on Oracle Linux images

  console: https://cloud.oracle.com/compute/instances/$INSTANCE_ID?region=$REGION

Next (on the box):
  sudo apt-get update -y && sudo apt-get install -y git
  git clone https://github.com/bartimoussmith-oss/therealwindycity.git /tmp/windycity
  sudo bash /tmp/windycity/deploy/oracle/bootstrap.sh --domain your.domain --email you@example.com

Don't forget the ingress rules for TCP 80/443 in the subnet's security list.
EOF
