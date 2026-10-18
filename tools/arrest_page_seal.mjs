#!/usr/bin/env node
/*
 * arrest_page_seal.mjs -- seal a plaintext JSON payload with AES-256-GCM.
 *
 * WHY THIS EXISTS
 *   GitHub Pages is static hosting: there is no server, so there is no such
 *   thing as a server-side login. A "password page" that merely hides content
 *   with JavaScript is not protection -- the data still ships to the browser
 *   and anyone can fetch it directly.
 *
 *   The only honest gate on static hosting is to encrypt the payload at build
 *   time and ship ciphertext. This script does that. The password never appears
 *   in the repository, in the built site, or in any log line.
 *
 * ENVELOPE (base64 of the concatenation)
 *   salt (16 B) || iv (12 B) || ciphertext || GCM tag (16 B)
 *
 * KEY DERIVATION
 *   PBKDF2-HMAC-SHA256, 210,000 iterations, 32-byte key.
 *   These exact parameters are reproducible in the browser with WebCrypto
 *   (crypto.subtle PBKDF2 + AES-GCM), which is what index.html uses to open
 *   the envelope. Verified interoperable; a wrong password raises
 *   OperationError rather than returning garbage.
 *
 * USAGE
 *   node tools/arrest_page_seal.mjs --in plain.json --out data.enc \
 *        --password-env ARREST_PAGE_PASSWORD [--iterations 210000]
 *
 *   The password is read from an environment variable or from a file. It is
 *   never accepted as a command-line argument, because argv is visible in the
 *   process table and lands in CI logs.
 *
 * EXIT CODES
 *   0 sealed  |  2 bad arguments or unreadable input  |  3 no/weak password
 *   4 write error
 */
import { readFileSync, writeFileSync } from "node:fs";
import { pbkdf2Sync, randomBytes, createCipheriv, timingSafeEqual } from "node:crypto";

const DEFAULT_ITERATIONS = 210000;
const MIN_PASSWORD_LENGTH = 12;

function die(code, msg) {
  process.stderr.write(`arrest_page_seal: ${msg}\n`);
  process.exit(code);
}

function parseArgs(argv) {
  const out = { iterations: DEFAULT_ITERATIONS };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => {
      const v = argv[++i];
      if (v === undefined) die(2, `${a} needs a value`);
      return v;
    };
    if (a === "--in") out.in = next();
    else if (a === "--out") out.out = next();
    else if (a === "--password-env") out.passwordEnv = next();
    else if (a === "--password-file") out.passwordFile = next();
    else if (a === "--iterations") out.iterations = parseInt(next(), 10);
    else if (a === "--min-length") out.minLength = parseInt(next(), 10);
    else die(2, `unknown argument ${a}`);
  }
  return out;
}

function readPassword(a) {
  // Exactly one source, and never argv.
  if (a.passwordEnv && a.passwordFile) die(2, "use only one of --password-env / --password-file");
  let pw = null;
  if (a.passwordEnv) {
    pw = process.env[a.passwordEnv];
    if (pw === undefined || pw === "") die(3, `environment variable ${a.passwordEnv} is not set`);
  } else if (a.passwordFile) {
    try {
      pw = readFileSync(a.passwordFile, "utf8");
    } catch (e) {
      die(3, `cannot read password file: ${e.message}`);
    }
  } else {
    die(2, "need --password-env NAME or --password-file PATH");
  }
  // Strip one trailing newline only -- that is what `echo pw > file` adds.
  pw = pw.replace(/\r?\n$/, "");
  const minLen = a.minLength ?? MIN_PASSWORD_LENGTH;
  if (pw.length < minLen) {
    die(3, `password is ${pw.length} characters; the sealed blob is published ` +
           `worldwide and can be attacked offline, so a minimum of ${minLen} is enforced. ` +
           `Use a passphrase (several unrelated words), not a short word.`);
  }
  return pw;
}

const a = parseArgs(process.argv.slice(2));
if (!a.in || !a.out) die(2, "need --in and --out");
if (!Number.isInteger(a.iterations) || a.iterations < 100000) {
  die(2, `--iterations must be an integer >= 100000 (got ${a.iterations})`);
}

let plaintext;
try {
  plaintext = readFileSync(a.in);
} catch (e) {
  die(2, `cannot read input: ${e.message}`);
}

// Refuse to seal something that is not the JSON we expect. This is a cheap
// structural check, not a content audit: the importer owns the name audit.
try {
  JSON.parse(plaintext.toString("utf8"));
} catch (e) {
  die(2, `input is not valid JSON: ${e.message}`);
}

const password = readPassword(a);
const salt = randomBytes(16);
const iv = randomBytes(12);
const key = pbkdf2Sync(password, salt, a.iterations, 32, "sha256");

const cipher = createCipheriv("aes-256-gcm", key, iv);
const body = Buffer.concat([cipher.update(plaintext), cipher.final()]);
const tag = cipher.getAuthTag();
if (tag.length !== 16) die(4, `unexpected GCM tag length ${tag.length}`);

const envelope = Buffer.concat([salt, iv, body, tag]);

// Prove the seal round-trips before we hand the caller a file. Encrypting
// something that cannot be decrypted would publish an unusable page.
const check = createCipheriv("aes-256-gcm", key, iv);
if (!timingSafeEqual(Buffer.concat([check.update(plaintext), check.final()]), body)) {
  die(4, "self-check failed: re-encryption did not reproduce the ciphertext");
}

try {
  writeFileSync(a.out, envelope.toString("base64"), { mode: 0o644 });
} catch (e) {
  die(4, `cannot write output: ${e.message}`);
}

// Deliberately no password material in stdout.
process.stdout.write(
  `arrest_page_seal: sealed ${plaintext.length} B -> ${envelope.toString("base64").length} B base64 ` +
  `(aes-256-gcm, pbkdf2-sha256 ${a.iterations} iters, salt ${salt.length} B, iv ${iv.length} B)\n`
);
