# Encrypted static resource

Only `index.html` (the generic unlock screen) and `payload.json` (AES-GCM ciphertext) belong in the public GitHub Pages artifact. Never add the original HTML, source documents, passphrase, or a passphrase file to Git.

To update it, obtain the **redacted** HTML, then seal it locally:

```sh
node tools/seal_resource.mjs /secure/local/path/redacted.html
```

The tool prompts for a passphrase (minimum 16 bytes; use a unique, randomly generated passphrase). Or pass a protected local file with `--password-file /path/to/secret`. The output is `locked-resource/payload.json`. Commit that ciphertext only. Keep the passphrase out of the repository and deliver it separately to intended viewers. Replacing the payload requires the same passphrase to be used by viewers; changing the passphrase means resealing and replacing the payload.

## Security limits

The browser uses PBKDF2-HMAC-SHA-256 (600,000 iterations) to derive an AES-256-GCM key. Decryption happens in the visitor's browser; the passphrase is not submitted to a server. This protects the content at rest in a public repository **only while the passphrase remains secret and strong**. The URL, ciphertext size, repository source, and access times are public. A person with the passphrase can save, copy, or redistribute the content, and a visitor can inspect it after unlocking. This is not account-based access control and is not a substitute for a private repository or a secure case-management system. Do not publish the unredacted/private source or the passphrase.
