// Renders the PWA icons from public/icons/icon.svg (run: npm run icons).
import { Resvg } from '@resvg/resvg-js';
import { readFileSync, writeFileSync } from 'node:fs';

const svg = readFileSync('public/icons/icon.svg', 'utf8');
// maskable: full-bleed background, artwork inside the 80% safe zone
const maskable = svg
  .replace('<rect width="512" height="512" rx="112" fill="url(#g)"/>', '<rect width="512" height="512" fill="url(#g)"/><g transform="translate(51.2 51.2) scale(0.8)">')
  .replace('</svg>', '</g></svg>');

function render(src, size, out) {
  const png = new Resvg(src, { fitTo: { mode: 'width', value: size } }).render().asPng();
  writeFileSync(out, png);
  console.log(out, png.length, 'bytes');
}
render(svg, 192, 'public/icons/icon-192.png');
render(svg, 512, 'public/icons/icon-512.png');
render(maskable, 512, 'public/icons/maskable-512.png');
render(maskable, 180, 'public/icons/apple-touch-icon.png');
