/** Render the source-reviewed workflow atlas with Mermaid and a local browser.
 * Usage: node docs/workflow/render.mjs [--modules /path/to/node_modules]
 *        [--browser /path/to/chrome] [--scale 3] [--only 01-overview]
 * Dependencies are isolated under renderer/; no application runtime is loaded.
 */
import fs from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';

const root = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const option = (name, fallback) => {
  const i = args.indexOf(name);
  return i < 0 ? fallback : args[i + 1];
};
const moduleRoot = option('--modules', path.join(root, 'renderer', 'node_modules'));
const resolver = createRequire(path.join(path.resolve(moduleRoot), '.workflow-resolve.cjs'));
const cliPath = resolver.resolve('@mermaid-js/mermaid-cli');
const { renderMermaid } = await import(pathToFileURL(cliPath).href);
const { default: puppeteer } = await import(pathToFileURL(resolver.resolve('puppeteer')).href);
const scale = Number(option('--scale', '3'));
if (!Number.isFinite(scale) || scale < 1 || scale > 4) throw new Error('Scale must be between 1 and 4.');
const browsers = [
  option('--browser', process.env.PUPPETEER_EXECUTABLE_PATH),
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean);
const executablePath = browsers.find(existsSync);
if (!executablePath) throw new Error('Supply an installed browser with --browser or PUPPETEER_EXECUTABLE_PATH.');
const index = JSON.parse(await fs.readFile(path.join(root, 'diagram-index.json'), 'utf8'));
const only = option('--only', null);
const diagrams = index.diagrams.filter(d => !only || d.id === only);
if (!diagrams.length) throw new Error('No diagram matches --only.');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const escape = value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const palettes = {
  light: {
    page: '#F5F7FB', panel: '#FFFFFF', text: '#162B43', muted: '#66778D', line: '#8396AD', border: '#DCE4EE', accent: '#167D8C',
    cluster: '#F7F9FC', clusterBorder: '#CFDBE8',
    classes: {
      input: ['#E7F5F1', '#348E82', '#174D49'], process: ['#EAF1FC', '#6589BB', '#203F68'],
      decision: ['#FFF2D9', '#CA963B', '#6B4918'], artifact: ['#EEEFFD', '#8388C3', '#414779'],
      authority: ['#F4EBF9', '#A181B9', '#643E7A'], stop: ['#FCECEA', '#C57B74', '#823F39'],
      external: ['#F0F3F7', '#92A0B2', '#536277'],
    },
  },
  dark: {
    page: '#0B1523', panel: '#101E30', text: '#EBF2FA', muted: '#A0B3C9', line: '#95A9C0', border: '#30455E', accent: '#6DCCCB',
    cluster: '#14263B', clusterBorder: '#3C536D',
    classes: {
      input: ['#163F40', '#63B6AC', '#D2F6ED'], process: ['#203955', '#779FD3', '#E0EDFF'],
      decision: ['#49391E', '#C9A259', '#FFECC6'], artifact: ['#303858', '#9EA5E8', '#E8E9FF'],
      authority: ['#423251', '#BC9CD1', '#F4E6FF'], stop: ['#4B2C31', '#D69291', '#FFE3DF'],
      external: ['#293647', '#7F95AE', '#D6E1EE'],
    },
  },
};
function classes(palette) {
  return '\n%% BEGIN SHARED ATLAS STYLE\n' + Object.entries(palette.classes).map(([name, [fill, stroke, color]]) =>
    `    classDef ${name} fill:${fill},stroke:${stroke},color:${color},stroke-width:1.5px${name === 'external' ? ',stroke-dasharray:5 4' : ''};`
  ).join('\n') + '\n%% END SHARED ATLAS STYLE\n';
}
function unstyled(source) {
  return source.replace(/\n%% BEGIN SHARED ATLAS STYLE[\s\S]*?%% END SHARED ATLAS STYLE\s*/g, '\n').trimEnd() + '\n';
}
const baseCss = `
  .node rect, .node polygon, .node path { stroke-linejoin: round; }
  .node rect { rx: 9px; ry: 9px; }
  .cluster rect { rx: 14px; ry: 14px; }
  .nodeLabel { line-height: 1.45; }
  .edgeLabel { font-size: 13px; }
  .flowchart-link { stroke-width: 1.65px; }
`;
await fs.mkdir(path.join(root, 'png'), { recursive: true });
await fs.mkdir(path.join(root, 'svg'), { recursive: true });
const browser = await puppeteer.launch({ executablePath, headless: true });
const rendered = [];
try {
  for (const diagram of diagrams) {
    const sourcePath = path.join(root, diagram.id + '.mmd');
    const source = unstyled(await fs.readFile(sourcePath, 'utf8'));
    const portable = source + classes(palettes.light);
    await fs.writeFile(sourcePath, portable);
    const mdPath = path.join(root, diagram.id + '.md');
    const md = await fs.readFile(mdPath, 'utf8');
    if (!/```mermaid\r?\n[\s\S]*?```/.test(md)) throw new Error(`${diagram.id}: missing Mermaid document block`);
    await fs.writeFile(mdPath, md.replace(/```mermaid\r?\n[\s\S]*?```/, '```mermaid\n' + portable.trimEnd() + '\n```'));
    for (const theme of ['light', 'dark']) {
      const p = palettes[theme];
      const { data } = await renderMermaid(browser, source + classes(p), 'svg', {
        viewport: { width: 2200, height: 1400, deviceScaleFactor: 1 },
        backgroundColor: p.panel,
        mermaidConfig: {
          startOnLoad: false, theme: 'base', securityLevel: 'strict',
          fontFamily: 'Segoe UI, Arial, sans-serif',
          themeVariables: {
            fontFamily: 'Segoe UI, Arial, sans-serif', fontSize: '16px',
            background: p.panel, primaryColor: p.classes.process[0], primaryTextColor: p.text,
            primaryBorderColor: p.classes.process[1], lineColor: p.line, textColor: p.text,
            clusterBkg: p.cluster, clusterBorder: p.clusterBorder, titleColor: p.text,
            edgeLabelBackground: p.panel,
          },
          flowchart: { curve: 'basis', padding: 18, nodeSpacing: 32, rankSpacing: 52, wrappingWidth: 320, htmlLabels: true, useMaxWidth: false },
        },
        myCSS: baseCss,
      });
      const svg = new TextDecoder().decode(data);
      const viewBox = svg.match(/viewBox="([^"]+)"/);
      if (!viewBox) throw new Error(`${diagram.id}: missing SVG viewBox`);
      const [, , diagramWidth, diagramHeight] = viewBox[1].split(/\s+/).map(Number);
      if (!(diagramWidth > 0 && diagramHeight > 0)) throw new Error('Invalid SVG dimensions');
      const logicalWidth = Math.max(1120, Math.min(1920, Math.ceil(diagramWidth + 144)));
      const suffix = theme === 'dark' ? '.dark' : '';
      const svgFile = `svg/${diagram.id}${suffix}.svg`;
      await fs.writeFile(path.join(root, svgFile), svg);
      const page = await browser.newPage();
      try {
        await page.setViewport({ width: logicalWidth, height: 1000, deviceScaleFactor: scale });
        const legend = [['input', 'Input'], ['process', 'Process'], ['decision', 'Decision'], ['artifact', 'Record'], ['authority', 'Authority'], ['stop', 'Hold / error'], ['external', 'External / optional']];
        await page.setContent(`<!doctype html><html lang="en"><head><meta charset="utf-8"><style>
          *{box-sizing:border-box}body{margin:0;background:${p.page};color:${p.text};font-family:'Segoe UI',Arial,sans-serif}
          article{width:${logicalWidth}px;padding:42px;background:${p.page}}
          .eyebrow{font-size:12px;letter-spacing:3.5px;font-weight:700;color:${p.accent};display:flex;justify-content:space-between}
          h1{font-size:34px;line-height:1.2;letter-spacing:-.8px;font-weight:650;margin:18px 0 9px}
          .subtitle{font-size:16px;line-height:1.5;color:${p.muted};margin:0 0 26px}
          .canvas{background:${p.panel};border:1px solid ${p.border};border-radius:18px;padding:30px;display:flex;justify-content:center;align-items:flex-start;overflow:visible}
          .canvas svg{width:100%;height:auto;max-width:${diagramWidth}px;display:block}
          .legend{display:flex;flex-wrap:wrap;gap:14px 23px;margin-top:23px;font-size:11px;color:${p.muted}}
          .legend span{display:flex;gap:7px;align-items:center}.swatch{width:12px;height:12px;border-radius:3px;display:inline-block}
          footer{border-top:1px solid ${p.border};padding-top:16px;margin-top:22px;display:flex;justify-content:space-between;color:${p.muted};font-size:11px;letter-spacing:.3px}
        </style></head><body><article>
          <div class="eyebrow"><span>JRAPHYTE / TRACE-GC</span><span>WORKFLOW ${diagram.id.slice(0,2)} / ${String(index.diagrams.length).padStart(2,'0')}</span></div>
          <h1>${escape(diagram.title)}</h1><p class="subtitle">${escape(diagram.subtitle)}</p>
          <div class="canvas">${svg}</div>
          <div class="legend">${legend.map(([key, label]) => `<span><i class="swatch" style="background:${p.classes[key][0]};border:1px ${key==='external'?'dashed':'solid'} ${p.classes[key][1]}"></i>${label}</span>`).join('')}</div>
          <footer><span>SOURCE-REVIEWED WORKFLOW · ${index.source_revision.slice(0,7)}</span><span>docs/workflow/${diagram.id}.mmd</span></footer>
          </article></body></html>`, { waitUntil: 'load' });
        await page.evaluate(() => document.fonts.ready);
        const article = await page.$('article');
        const bounds = await article.boundingBox();
        const clipCheck = await page.$eval('.canvas', canvas => {
          const frame = canvas.getBoundingClientRect();
          const content = canvas.querySelector('svg').getBoundingClientRect();
          return { right: content.right <= frame.right + .5, bottom: content.bottom <= frame.bottom + .5 };
        });
        if (!clipCheck.right || !clipCheck.bottom) throw new Error(`${diagram.id}: diagram is clipped`);
        const pngFile = `png/${diagram.id}${suffix}.png`;
        const bytes = await article.screenshot({ path: path.join(root, pngFile), type: 'png' });
        const png = Buffer.from(bytes);
        const width = png.readUInt32BE(16), height = png.readUInt32BE(20);
        rendered.push({ diagram: diagram.id, theme, png: pngFile, svg: svgFile, width, height,
          bytes: bytes.length, sha256: sha(bytes), source_sha256: sha(portable), clipping_check: 'PASS' });
        console.log(`${diagram.id} ${theme}: ${width} x ${height}`);
      } finally { await page.close(); }
    }
  }
} finally { await browser.close(); }

// Full runs replace the receipt; partial runs refresh only the rendered views.
let previous = [];
if (only && existsSync(path.join(root, 'render-manifest.json'))) {
  previous = JSON.parse(await fs.readFile(path.join(root, 'render-manifest.json'), 'utf8')).renders.filter(r => r.diagram !== only);
}
const packageVersion = async name => {
  const json = JSON.parse(await fs.readFile(path.join(moduleRoot, name, 'package.json'), 'utf8'));
  return json.version;
};
await fs.writeFile(path.join(root, 'render-manifest.json'), JSON.stringify({
  source_revision: index.source_revision, rendered_at: new Date().toISOString(),
  renderer: { node: process.version, mermaid_cli: await packageVersion('@mermaid-js/mermaid-cli'),
    mermaid: await packageVersion('mermaid'), puppeteer: await packageVersion('puppeteer'), scale },
  scope: 'Mermaid parsing, browser rendering, image dimensions and clipping checks; not runtime or deployment validation.',
  renders: [...previous, ...rendered].sort((a,b) => (a.diagram+a.theme).localeCompare(b.diagram+b.theme)),
}, null, 2) + '\n');
