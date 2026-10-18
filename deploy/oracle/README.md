# Going live on Oracle Cloud (OCI) — us-phoenix-1

Runbook for putting **The Real Windy City** stack on an Oracle Cloud VM in the
**Phoenix (us-phoenix-1)** region. Everything in this folder is the deploy kit:
one bootstrap script, systemd units, and an nginx front door.

> Region: `us-phoenix-1` — <https://cloud.oracle.com/?region=us-phoenix-1>
> Always Free shapes are region-scoped; if an A1 capacity error appears, retry
> later or switch to the x86 micro (see *Shape* below).

## What "live" means here — the four things that ship

| # | Surface | Served as | Path on the box |
|---|---|---|---|
| 1 | **Console** (`Transparency_Index_App.py` / `streamlit_app.py` twins) | Streamlit on `127.0.0.1:8501`, proxied by nginx | `/opt/windycity` |
| 2 | **Pipeline studio** (`pipeline/webui.py`) | stdlib HTTP on `127.0.0.1:8717`, proxied at `/studio/` | `/opt/windycity/pipeline` |
| 3 | **Static ledger + RSS** (`public/index.html`, `public/feed.xml`) | nginx serves files directly — no Python in the path | `/opt/windycity/public` |
| 4 | **Civic cycle** (`engine/scheduler.py --once`) | systemd timer every 6 h at :17 | writes `data/`, `public/`, `Entity_Database/` |

The console and studio **never** listen on the public interface; only nginx
(80/443) is public. That is deliberate: the studio exposes job endpoints that
should not be anonymous on the open internet.

---

## Step 0 — what you need first

- An OCI tenancy with the **Phoenix** region selected in the console.
- A **compartment** to hold the instance (default: your root compartment).
- An **SSH key pair**. In the console you can let OCI generate one and download
  the private key; or paste your own public key.
- *(Optional but recommended)* a domain or subdomain you can point at the VM's
  public IP, so HTTPS works: e.g. `windycity.example.com` +
  `pipeline.windycity.example.com` → the instance IP (A records).

## Step 1 — create the instance (console clicks)

1. Hamburger menu → **Compute → Instances → Create instance**.
2. **Name:** `windycity-prod`. **Compartment:** your choice.
3. **Placement:** leave the default Availability Domain (Phoenix has AD-1/2/3).
4. **Image and shape:**
   - Image: **Canonical Ubuntu 24.04** (Oracle Linux 9 also supported by the
     bootstrap; Ubuntu is the best-tested path).
   - Shape: **`VM.Standard.A1.Flex`** (Ampere/ARM, Always Free up to 4 OCPU /
     24 GB). **2 OCPU / 12 GB** is comfortable for Streamlit + the pipeline
     studio and still free-tier eligible.
   - Fallback if A1 capacity is unavailable: **`VM.Standard.E2.1.Micro`**
     (x86, 1 OCPU / 1 GB, always free). The bootstrap then also enables a 2 GB
     swapfile — required, Streamlit will OOM on 1 GB without it.
5. **Networking:** create/choose a VCN with a **public subnet**; tick
   **Assign a public IPv4 address**.
6. **Add SSH keys:** upload your public key (or download the generated pair —
   you will not see it again).
7. **Boot volume:** 50 GB is plenty (default 47 GB is fine). Meeting video does
   not belong on this box; keep `pipeline/videos/` off unless you grow the disk.
8. **Create.** Then copy the **Public IP address** from the instance page.

### Then open the front door

**Networking → Virtual Cloud Networks → your VCN → Security Lists → Default
Security List → Add Ingress Rules** (twice, or one rule per port):

| Stateless | Source Type | Source CIDR | IP Protocol | Destination Port Range |
|---|---|---|---|---|
| No | CIDR | `0.0.0.0/0` | TCP | `80` |
| No | CIDR | `0.0.0.0/0` | TCP | `443` |

Leave `22` as-is (SSH). **Do not** open 8501 or 8717 — nginx is the only door.
*(If you used an NSG instead of a security list, add the same two rules to the NSG.)*

### Optional: skip the clicks with the OCI CLI

If you have `oci` configured locally (`oci setup config`), this creates the same
instance:

```bash
export COMPARTMENT_OCID=ocid1.compartment.oc1..xxxx
export SUBNET_OCID=ocid1.subnet.oc1.phx.xxxx
export SSH_PUBKEY_FILE=~/.ssh/id_ed25519.pub
bash deploy/oracle/oci-launch.sh
```

It prints the instance OCID and public IP when the instance reaches `RUNNING`.

## Step 2 — one command on the box

```bash
ssh ubuntu@<PUBLIC_IP>            # 'opc' instead of 'ubuntu' on Oracle Linux
sudo apt-get update -y && sudo apt-get install -y git
git clone https://github.com/bartimoussmith-oss/therealwindycity.git /tmp/windycity
sudo bash /tmp/windycity/deploy/oracle/bootstrap.sh \
  --domain windycity.example.com \
  --email  you@example.com
```

`--domain` and `--email` are optional. Without them you get plain HTTP on the
public IP, which is a perfectly good first light — add TLS later by re-running
the bootstrap with the flags (it is idempotent).

What the bootstrap does, in order:

1. installs `git`, `python3-venv`, `nginx`, `ffmpeg`, `certbot` (+ firewalld on
   Oracle Linux, iptables-persistent + swap on small x86 micros);
2. creates the `windycity` service account and clones the repo to
   `/opt/windycity`;
3. builds `/opt/windycity/.venv` and `pip install -r requirements.txt`
   (plus `yt-dlp`, `curl_cffi` for the pipeline's fallback paths);
4. runs `python3 run.py init` to create `data/engine.db` and sync sources;
5. installs and enables the three systemd units + the cycle timer;
6. writes the nginx config, opens the host firewall for 80/443, reloads nginx;
7. if `--domain` DNS already resolves here, runs certbot and enables HTTPS.

Then it prints the live URLs.

## Step 3 — verify (don't take "deployed" on faith)

```bash
sudo bash /opt/windycity/deploy/oracle/preflight.sh
```

It checks: service states, listening sockets, that 8501/8717 are **not** public,
HTTP status of each surface, the RSS feed parsing as XML, the engine DB having
tables, and the timer being scheduled. It exits non-zero on any failure.

By hand:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost/            # 200
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost/studio/     # 200
curl -sS http://localhost/feed.xml | head -c 200
sudo systemctl status windycity-console windycity-pipeline --no-pager
journalctl -u windycity-cycle -n 40 --no-pager
```

## Step 4 — the cycle runs itself

`windycity-cycle.timer` fires `engine/scheduler.py --once` every 6 h at :17 UTC
(same cadence as the GitHub Action). The Action can stay on or be disabled —
running both is harmless (worst case, the same document is fetched twice), but
if the VM becomes the source of truth, disable the Action so two writers stop
racing on the ledger repo:

```bash
# repo Settings → Actions → disable civic-cycle, or:
gh workflow disable civic-cycle
```

The VM cycle writes into `/opt/windycity/{data,public,Entity_Database}`. It does
**not** push to GitHub — if you want the pushed ledger too, keep the Action.
If you want the VM to commit, add a deploy key and uncomment the `git push`
block in `deploy/oracle/systemd/windycity-cycle.service` (left off by default:
an unattended push loop is exactly how the repo got flattened before).

## Day-2 operations

```bash
sudo bash /opt/windycity/deploy/oracle/update.sh      # git pull + deps + restart
sudo bash /opt/windycity/deploy/oracle/update.sh --no-pull   # restart only
sudo systemctl restart windycity-console
sudo journalctl -u windycity-console -f
sudo tail -f /var/log/nginx/error.log
```

Certificates renew via the `certbot.timer` that the certbot package installs;
`preflight.sh` prints days-to-expiry.

## Shape / sizing notes

| Shape | vCPU / RAM | Notes |
|---|---|---|
| `VM.Standard.A1.Flex` 2/12 | 2 ARM / 12 GB | Recommended. Free-tier eligible, plenty of headroom. |
| `VM.Standard.A1.Flex` 4/24 | 4 ARM / 24 GB | The free-tier maximum. Use 4 OCPU if you also render clips. |
| `VM.Standard.E2.1.Micro` | 1 x86 / 1 GB | Works, tight. Bootstrap adds 2 GB swap. Keep the studio idle-heavy work (no reel renders) on it. |

Disk: the console's corpus/DB is ~300 MB of the repo. Meeting video is the only
thing that eats disk — `pipeline/videos/` is intentionally gitignored, so it
only exists if you pull it. Put it on a block volume if you need it.

## Notes, gotchas, and what this kit deliberately does not do

- **Port 25 is blocked** by OCI for all tenancies, and outbound 25 is blocked by
  default policy. Nothing here sends mail, so it does not matter. Public records
  requests still go out from a human's mailbox — that is the repo's rule, not a
  hosting limitation.
- **ARM vs x86:** all wheels in `requirements.txt` (streamlit, pandas, pyarrow,
  pillow, pypdfium2) have aarch64 builds — the pip step on A1 is fine. `ffmpeg`
  comes from the distro on both arches.
- **Robots and politeness stay in force.** The engine's own `robots.txt` /
  crawl-delay layer travels with the code; nothing here bypasses it.
- **No credentials in this kit.** There is no token in any file here. The VM
  boots from a public clone; if you later enable VM→GitHub pushes, use a
  read-write deploy key stored outside the repo (`/etc/windycity/`), never in a
  committed file.
- **Not included on purpose:** an OCI Load Balancer, WAF, Autonomous DB, or
  Container Instances. A single small VM with nginx is the right size for this
  load and costs nothing; the upgrade path (Container Instances + LB + Object
  Storage static ledger) is a rewrite of this kit, not a config flag.
- **Static-ledger-only variant:** if all you want is surface #3, skip the VM —
  push `public/` to a **public Object Storage bucket** with the static-website
  toggle on, in Phoenix. Cheap, but it loses the console and the studio.
