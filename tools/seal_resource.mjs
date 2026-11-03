#!/usr/bin/env node
// Seal a single HTML document for the public, client-side encrypted resource page.
// The plaintext source and password are never written to the output directory.
import { createCipheriv, pbkdf2Sync, randomBytes } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { createInterface } from 'node:readline/promises';
import { stdin, stdout } from 'node:process';

const args = process.argv.slice(2);
const source = args.find(arg => !arg.startsWith('--'));
const passwordFileArg = args.indexOf('--password-file');
const passwordFile = passwordFileArg >= 0 ? args[passwordFileArg + 1] : null;
const output = args.includes('--output') ? args[args.indexOf('--output') + 1] : 'locked-resource/payload.json';
if (!source || (passwordFileArg >= 0 && !passwordFile)) {
  console.error('Usage: node tools/seal_resource.mjs <redacted.html> [--password-file /path/to/secret] [--output locked-resource/payload.json]');
  process.exit(2);
}

let password;
if (passwordFile) {
  password = (await readFile(passwordFile, 'utf8')).trim();
} else if (stdin.isTTY) {
  const rl = createInterface({ input: stdin, output: stdout });
  try { password = (await rl.question('Encryption passphrase (minimum 16 characters): ')).trim(); }
  finally { rl.close(); }
} else {
  console.error('Provide a passphrase interactively or with --password-file.');
  process.exit(2);
}
if (Buffer.byteLength(password, 'utf8') < 16) {
  console.error('Use a passphrase of at least 16 bytes; a randomly generated 20+ character value is recommended.');
  process.exit(2);
}

const iterations = 600_000;
const salt = randomBytes(16);
const iv = randomBytes(12);
const key = pbkdf2Sync(password, salt, iterations, 32, 'sha256');
const cipher = createCipheriv('aes-256-gcm', key, iv);
const plaintext = await readFile(source);
const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final(), cipher.getAuthTag()]);
const payload = {
  version: 1,
  kdf: 'PBKDF2-SHA-256',
  iterations,
  cipher: 'AES-256-GCM',
  salt: salt.toString('base64'),
  iv: iv.toString('base64'),
  ciphertext: ciphertext.toString('base64')
};
await writeFile(output, JSON.stringify(payload) + '\n', { mode: 0o644 });
console.log(`Wrote encrypted payload (${ciphertext.length} bytes). No plaintext was copied.`);
