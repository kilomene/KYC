'use strict';
/*
 * Node harness for the flow.html document detector (live-scanner
 * tests). Extracts the KYC-DETECTOR block from public/flow.html
 * VERBATIM and runs evaluateDocument against synthetic frames whose
 * derived maps (Sobel magnitude, Laplacian variance, glare ratio,
 * frame diff) are computed exactly the way analyseFrame computes
 * them in the browser — so a pass here means the shipped detector
 * code, not a reimplementation, detects the scene.
 *
 * Fixture mode (no args): prints a JSON array of scenario results.
 * Grey mode:  node detector_harness.js --grey <raw-uint8-file> <w> <h> <geo-json>
 *             runs one real frame (fed 3x, like a settled scanner)
 *             and prints {"state": ...}.
 */
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'public', 'flow.html'), 'utf8');
const begin = html.indexOf('// == KYC-DETECTOR-BEGIN ==');
const end = html.indexOf('// == KYC-DETECTOR-END ==');
if (begin < 0 || end < 0) { console.error('detector markers not found in flow.html'); process.exit(2); }
const src = html.slice(begin, end);

function makeDetector() {
  // A fresh instance per scenario: the app resets bandHist when a
  // scanner starts; a fresh closure mirrors that.
  return new Function(src + '\nreturn {evaluateDocument, detectDocument, detectPaperDocument, entryGeometry};')();
}

// Derived maps, mirroring analyseFrame() in flow.html exactly.
// vw/vh are the source stream dimensions (aspect correction input);
// fixtures draw directly in canvas space, so they pass w/h.
function derived(grey, w, h, prev, vw, vh) {
  const n = w * h;
  let sum = 0, glare = 0;
  for (let i = 0; i < n; i++) { sum += grey[i]; if (grey[i] >= 245) glare++; }
  const mean = sum / n, glareRatio = glare / n;
  const mag = new Float32Array(n);
  let lapSum = 0, lapSq = 0, cnt = 0, edge = 0;
  for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
    const i = y * w + x;
    const gx = -grey[i - w - 1] - 2 * grey[i - 1] - grey[i + w - 1] + grey[i - w + 1] + 2 * grey[i + 1] + grey[i + w + 1];
    const gy = -grey[i - w - 1] - 2 * grey[i - w] - grey[i - w + 1] + grey[i + w - 1] + 2 * grey[i + w] + grey[i + w + 1];
    mag[i] = Math.abs(gx) + Math.abs(gy);
    const lap = 4 * grey[i] - grey[i - 1] - grey[i + 1] - grey[i - w] - grey[i + w];
    lapSum += lap; lapSq += lap * lap; cnt++; if (Math.abs(lap) > 28) edge++;
  }
  const lapMean = lapSum / cnt;
  const lapVar = lapSq / cnt - lapMean * lapMean;
  let diff = 999;
  if (prev && prev.length === n) {
    let ds = 0; for (let i = 0; i < n; i += 3) ds += Math.abs(grey[i] - prev[i]);
    diff = ds / (n / 3);
  }
  return { mean, glareRatio, lapVar, edgeRatio: edge / cnt, diff, grey, mag, w, h, rgba: null, vw: vw || w, vh: vh || h };
}

// ---------------- synthetic scenes (grey, W x H) ----------------
const W = 320, H = 420;
let seed = 42;
function rnd() { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }
function canvas(base) {
  const g = new Float32Array(W * H);
  for (let i = 0; i < g.length; i++) g[i] = base + (rnd() - 0.5) * 10;
  return g;
}
function rect(g, x0, y0, x1, y1, v, jitter = 10) {
  for (let y = Math.max(0, y0); y <= Math.min(H - 1, y1); y++)
    for (let x = Math.max(0, x0); x <= Math.min(W - 1, x1); x++)
      g[y * W + x] = v + (rnd() - 0.5) * jitter;
}
function printLines(g, x0, y0, x1, y1, rows) {
  // rows of short dark "text" dashes inside a region
  for (let r = 0; r < rows; r++) {
    const y = y0 + Math.round((y1 - y0) * (r + 0.5) / rows);
    let x = x0;
    while (x < x1 - 12) {
      const len = 8 + Math.floor(rnd() * 22);
      rect(g, x, y, Math.min(x + len, x1), y + 1, 92, 14);
      x += len + 5 + Math.floor(rnd() * 6);
    }
  }
}
// A wide paper slip with BOWED top/bottom edges (hand-held curve),
// print texture, a portrait box at the right, a pale watermark arc,
// on a dark background.
function paperSlipScene(opts = {}) {
  // Drawn in ANALYSIS-CANVAS space at the slip's real proportions:
  // 288 px wide, ~131 px tall -> aspect ~2.2, like the owner's.
  // Background is a dim room (50), not near-black: the whole-frame
  // mean must stay in the scanner's working light range.
  const g = canvas(opts.bg === undefined ? 50 : opts.bg);
  const x0 = 16, x1 = 304, yTop = 140, yBot = 271;
  const bowT = opts.bow === undefined ? 7 : opts.bow, bowB = opts.bow === undefined ? 6 : opts.bow;
  const topAt = x => yTop + bowT * Math.sin(Math.PI * (x - x0) / (x1 - x0));
  const botAt = x => yBot - bowB * Math.sin(Math.PI * (x - x0) / (x1 - x0));
  for (let x = x0; x <= x1; x++)
    for (let y = Math.round(topAt(x)); y <= Math.round(botAt(x)); y++)
      g[y * W + x] = 208 + (rnd() - 0.5) * 12;
  // header rule + field rows (print)
  for (let x = x0 + 8; x <= x1 - 8; x++) g[Math.round(topAt(x)) + 14 < H ? (Math.round(topAt(x)) + 14) * W + x : 0] = 120;
  printLines(g, x0 + 12, yTop + 30, 218, yBot - 14, 4);
  // portrait box right with a face-ish oval
  rect(g, 246, yTop + 24, 296, yBot - 20, 168, 8);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const dx = (x - 271) / 13, dy = (y - (yTop + 58)) / 20;
    if (dx * dx + dy * dy < 1) g[y * W + x] = 96 + (rnd() - 0.5) * 10;
  }
  // pale watermark swirl across the middle (the NIMC-style overlay)
  for (let x = x0 + 30; x < 210; x++) {
    const y = Math.round(yTop + 62 + 12 * Math.sin((x - x0) / 34));
    rect(g, x, y, x + 3, y + 9, 176, 8);
  }
  if (opts.glare) { // glare spot overlapping the top-right corner
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const d = Math.hypot(x - 268, y - 122);
      if (d < 30) g[y * W + x] = Math.min(255, g[y * W + x] + (30 - d) * 6);
    }
  }
  if (opts.hand) { // hand-like occlusion over the bottom-left corner
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const dx = (x - 24) / 54, dy = (y - 282) / 27;
      if (dx * dx + dy * dy < 1) g[y * W + x] = 118 + (rnd() - 0.5) * 12;
    }
  }
  return g;
}
function cardScene(cx, cy, cw, base = 38) {
  const g = canvas(base);
  const ch = Math.round(cw / 1.586);
  const x0 = Math.round(cx - cw / 2), x1 = x0 + cw, y0 = Math.round(cy - ch / 2), y1 = y0 + ch;
  rect(g, x0, y0, x1, y1, 196, 10);
  printLines(g, x0 + 70, y0 + 16, x1 - 12, y1 - 14, 4);
  rect(g, x0 + 10, y0 + 14, x0 + 56, y1 - 14, 160, 8); // portrait box
  return g;
}
function roomScene() {
  const g = new Float32Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++)
    g[y * W + x] = 62 + y * 0.14 + (rnd() - 0.5) * 8;
  rect(g, 196, 52, 302, 196, 186, 8);          // bright window
  rect(g, 244, 52, 250, 196, 90, 6);           // window bars
  rect(g, 196, 118, 302, 124, 90, 6);
  rect(g, 18, 84, 108, 168, 120, 8);           // picture frame
  rect(g, 30, 96, 96, 156, 150, 8);
  rect(g, 0, 300, 319, 419, 74, 8);            // sofa band
  rect(g, 40, 268, 130, 300, 96, 8);           // cushion
  return g;
}
function banded(g, frameIdx) {
  const out = new Float32Array(g);
  for (let y = 0; y < H; y++) {
    const f = 1 + 0.17 * Math.sin(2 * Math.PI * y / 9 + frameIdx * 1.7);
    for (let x = 0; x < W; x++) out[y * W + x] = Math.max(0, Math.min(255, g[y * W + x] * f));
  }
  return out;
}

function runScenario(name, frames, geo, noneState) {
  const det = makeDetector();
  let prev = null, state = null;
  for (const g of frames) {
    const fr = derived(g, W, H, prev);
    prev = g;
    state = det.evaluateDocument(fr, geo, noneState).state;
  }
  return { name, state };
}

function fixtures() {
  const slipGeo = { physical: 'paper', aspectMin: 1.2, aspectMax: 2.8 };
  const cardGeo = { physical: 'card', aspect: 1.586 };
  const poaGeo = { physical: 'paper', aspectMin: 0.60, aspectMax: 0.90 };
  const settle = g => [g, g, g];
  const out = [];
  // The deliverable fixture: curved wide paper slip, glare spot,
  // hand occlusion — must DETECT.
  out.push({ expect: 'doc_hold', ...runScenario('paper_curved_glare_hand', settle(paperSlipScene({ glare: true, hand: true })), slipGeo, 'doc_none') });
  out.push({ expect: 'doc_hold', ...runScenario('paper_flat', settle(paperSlipScene({ bow: 0 })), slipGeo, 'doc_none') });
  // Negatives.
  out.push({ expect: 'doc_none', ...runScenario('room_paper_geo', settle(roomScene()), slipGeo, 'doc_none') });
  out.push({ expect: 'doc_none', ...runScenario('room_card_geo', settle(roomScene()), cardGeo, 'doc_none') });
  const blank = canvas(206);
  out.push({ expect: 'doc_none', ...runScenario('blank_paper_geo', settle(blank), slipGeo, 'doc_none') });
  out.push({ expect: 'doc_none', ...runScenario('blank_card_geo', settle(blank), cardGeo, 'doc_none') });
  out.push({ expect: 'doc_none', ...runScenario('small_far_card', settle(cardScene(160, 210, 110)), cardGeo, 'doc_none') });
  // Paper aspect outside the registry range must not lock.
  const wide = paperSlipScene({ bow: 0 });
  out.push({ expect: 'doc_none', ...runScenario('paper_aspect_out_of_range', settle(wide), { physical: 'paper', aspectMin: 1.2, aspectMax: 1.9 }, 'doc_none') });
  // Card regression: a proper card at the guide still locks, strictly.
  out.push({ expect: 'doc_hold', ...runScenario('card_good', settle(cardScene(160, 210, 282)), cardGeo, 'doc_none') });
  // A card (1.586) is excluded by a paper range that does not cover it.
  out.push({ expect: 'doc_none', ...runScenario('card_outside_paper_range', settle(cardScene(160, 210, 282)), { physical: 'paper', aspectMin: 1.9, aspectMax: 2.8 }, 'doc_none') });
  // Screen refusal keeps precedence: banded slip frames -> doc_screen.
  const scr = paperSlipScene({});
  out.push({ expect: 'doc_screen', ...runScenario('screen_slip', [banded(scr, 0), banded(scr, 1), banded(scr, 2), banded(scr, 3), banded(scr, 4)], slipGeo, 'doc_none') });
  // POA: a portrait paper page locks under the POA paper geometry.
  const page = canvas(40);
  rect(page, 58, 56, 262, 346, 210, 10);
  printLines(page, 74, 84, 246, 320, 9);
  out.push({ expect: 'doc_hold', ...runScenario('poa_portrait_page', settle(page), poaGeo, 'poa_none') });
  return out;
}

if (process.argv[2] === '--grey') {
  // --grey <raw-uint8> <canvasW> <canvasH> <geo-json> <srcW> <srcH>
  // The raw file is the frame ALREADY drawn into the capped analysis
  // canvas (like analyseFrame's drawImage); srcW/srcH are the source
  // stream dimensions for the aspect correction.
  const [, , , file, wS, hS, geoJson, srcWS, srcHS] = process.argv;
  const w = parseInt(wS, 10), h = parseInt(hS, 10);
  const raw = fs.readFileSync(file);
  const grey = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) grey[i] = raw[i];
  const det = makeDetector();
  let prev = null, state = null;
  for (let k = 0; k < 3; k++) {
    const fr = derived(grey, w, h, prev, parseInt(srcWS || wS, 10), parseInt(srcHS || hS, 10));
    prev = grey;
    state = det.evaluateDocument(fr, JSON.parse(geoJson), 'doc_none').state;
  }
  console.log(JSON.stringify({ state }));
} else {
  console.log(JSON.stringify(fixtures(), null, 1));
}
