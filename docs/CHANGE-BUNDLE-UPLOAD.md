# Change Bundle Upload

Open **Change Bundle Upload** in the live Streamlit sidebar or home page.
This feature must first be deployed; editing this working branch does not itself
update the production site.

## One-time setup

In Streamlit Cloud → app settings → Secrets, add this section (do not commit
actual secrets or paste tokens into chat):

```toml
[change_upload]
password = "use a long unique randomly generated upload password"
github_token = "set privately in Streamlit Secrets"
branch = "arena/7063c52c-therealwindycity"
```

Use a fine-grained GitHub token restricted to this repository with **Contents:
read and write**. The branch must already exist and permit direct commits.
The branch above is the current working branch; after it is merged/retired,
explicitly configure the intended intake branch. Never use a token with broader
access than needed. The password protects this uploader, not the public files.
Do not reuse the arrest database password. Anyone with the upload password can
publish a bundle; rotate it if shared unintentionally.

## Upload and hand off

1. Package instructions (preferably `README.md`) and reference material as ZIP.
2. Open the upload page and enter the upload password.
3. Select a ZIP (15 MiB compressed maximum), review the filename inventory, and
   confirm that **all** contents may be public.
4. Click **Save bundle to GitHub** and wait for the durable receipt.
5. Paste the displayed handoff path and commit into this Arena conversation.

Uploads are stored as `uploads/change-bundles/<sha256>.zip`. A single GitHub
Contents API commit stores the archive, without overwriting site code. A receipt
is shown only after GitHub confirms the commit. Site-local disk is not used for
persistence. Re-uploading identical content may report that the file exists;
use the existing GitHub file. Network timeouts can occur after GitHub saves the
file, so check the intake directory before retrying.

The agent does not share the live Streamlit filesystem and is not automatically
notified. It can retrieve the ZIP from the receipt's commit using GitHub tools
and review it as untrusted input. Uploads do not automatically apply changes,
run scripts, install dependencies, or deploy the site. ZIPs are inspected but
not extracted on the site. They are not malware-scanned. Encrypted archives,
unsafe paths, duplicate names, links, corrupt ZIPs, over 2,000 entries, and more
than 100 MiB expanded data are rejected. Do not include credentials or private
records: this repository is public and deleting a file does not erase history.
