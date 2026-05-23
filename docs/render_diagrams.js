// Render every Mermaid file in docs/mermaid_src/*.mmd into docs/diagrams/*.png
// using mermaid-cli (mmdc). Calls the JS entry directly to avoid Windows
// .cmd shim issues with spaces in the path.
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const SRC = path.join(__dirname, 'mermaid_src');
const OUT = path.join(__dirname, 'diagrams');
const MMDC_JS = path.join(__dirname, 'node_modules', '@mermaid-js', 'mermaid-cli', 'src', 'cli.js');

if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });

const files = fs.readdirSync(SRC).filter(f => f.endsWith('.mmd')).sort();
let ok = 0, fail = 0;
for (const f of files) {
  const input = path.join(SRC, f);
  const output = path.join(OUT, f.replace(/\.mmd$/, '.png'));
  process.stdout.write(`[mmdc] ${f} -> ${path.basename(output)} ... `);
  // Theme is set inside each .mmd file via %%{init: {'theme':'base',...}}%%
  const res = spawnSync(process.execPath, [
    MMDC_JS,
    '-i', input,
    '-o', output,
    '-b', 'white',
    '-w', '1600',
    '--scale', '2',
  ], { stdio: ['ignore', 'pipe', 'pipe'], encoding: 'utf-8' });
  if (res.status === 0) {
    console.log('OK');
    ok++;
  } else {
    console.log('FAIL (' + res.status + ')');
    if (res.stderr) console.log(res.stderr.slice(0, 500));
    fail++;
  }
}
console.log(`\nDone: ${ok} ok, ${fail} failed.`);
process.exit(fail === 0 ? 0 : 1);
