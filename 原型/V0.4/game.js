import { createChapterCombatRenderer, skillHead } from './combat-render.mjs';
import { IMPACTS, createCombatAudio } from './songfeng-feedback.mjs';
import { createMusic } from './songfeng-music.mjs';
import { createWorldArt, WORLD_STYLE } from './world-art.mjs';
(() => {
'use strict';
const Chapter = window.QingShiChapter;
const Playtest=window.QingShiPlaytest, DEBUG=location.search.includes('debug');
const PAGE_SESSION=Date.now().toString(36)+Math.random().toString(36).slice(2,7);
const $ = (id) => document.getElementById(id);
const app = $('app'), cv = $('cv'), ctx = cv.getContext('2d');
const worldArt=createWorldArt();
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const angDiff = (a, b) => { let d = a - b; while (d > Math.PI) d -= Math.PI * 2; while (d < -Math.PI) d += Math.PI * 2; return Math.abs(d); };
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

// ================================================================ 像素美术
const cnv = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; };
const RNG = (seed) => { let s = seed % 2147483647; if (s <= 0) s += 2147483646; return () => (s = (s * 16807) % 2147483647) / 2147483647; };
const hash = (str) => { let h = 7; for (const ch of str) h = (h * 31 + ch.charCodeAt(0)) % 1000003; return h + 1; };
const R = (g, x, y, w, h, c) => { g.fillStyle = c; g.fillRect(x, y, w, h); };
const P = (g, x, y, c) => { g.fillStyle = c; g.fillRect(x, y, 1, 1); };
function fc(g, cx, cy, r, c) { g.fillStyle = c; for (let y = -r; y <= r; y++) for (let x = -r; x <= r; x++) if (x * x + y * y <= r * r + r * 0.6) g.fillRect(cx + x, cy + y, 1, 1); }
function fe(g, cx, cy, rx, ry, c) { g.fillStyle = c; for (let y = -ry; y <= ry; y++) for (let x = -rx; x <= rx; x++) if ((x * x) / (rx * rx) + (y * y) / (ry * ry) <= 1.05) g.fillRect(cx + x, cy + y, 1, 1); }
function line(g, x0, y0, x1, y1, c) { x0 = Math.round(x0); y0 = Math.round(y0); x1 = Math.round(x1); y1 = Math.round(y1); const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1; let e = dx + dy; for (;;) { P(g, x0, y0, c); if (x0 === x1 && y0 === y1) break; const e2 = 2 * e; if (e2 >= dy) { e += dy; x0 += sx; } if (e2 <= dx) { e += dx; y0 += sy; } } }
const INK = '#1C1612';
function outline(c, col) {
  const g = c.getContext('2d'), w = c.width, h = c.height, d = g.getImageData(0, 0, w, h).data;
  const solid = (x, y) => x >= 0 && y >= 0 && x < w && y < h && d[(y * w + x) * 4 + 3] > 40;
  g.fillStyle = col || INK;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (!solid(x, y) && (solid(x - 1, y) || solid(x + 1, y) || solid(x, y - 1) || solid(x, y + 1))) g.fillRect(x, y, 1, 1);
  return c;
}

// ---- 人物 16×20（匪首 18×20）
const PAL = { k: INK, K: '#3B2F28', s: '#F0C8A0', S: '#D29E78', h: '#2B2320', H: '#4D3D34', w: '#F0E8D6', W: '#BDB2A0', e: INK, p: '#3A3644', f: '#221B19', r: '#777777', R: '#555555', b: '#C9A45C', a: '#C8402C', A: '#8A3A2A', c: '#3A2A22', g: '#D8B66A', G: '#A8864A', m: '#5A4436', M: '#43332A' };
const BODY_DOWN = [
  '................', '.....kkkkkk.....', '....khhhhhhk....', '...khhhhhhhhk...', '...khHhhhhHhk...',
  '...khsssssshk...', '...ksessssesk...', '...kssssssssk...', '....kSssssSk....', '....krrwwrrk....',
  '...krrrwwrrrk...', '..krrrrrrrrrrk..', '..krRrrrrrrRrk..', '..ksbbbbbbbbsk..', '...krrrrrrrrk...',
  '...krRrrrrRrk...', '...kRrrrrrrRk...'];
const BODY_UP = BODY_DOWN.slice(0, 5).concat([
  '...khhhhhhhhk...', '...khhHhhHhhk...', '...khhhhhhhhk...', '....khhhhhhk....', '....krrrrrrk....',
  '...krrrrrrrrk...']).concat(BODY_DOWN.slice(11));
const LEGS_FB = {
  idle: ['...kpppkkpppk...', '...kppk..kppk...', '...kffk..kffk...'],
  w1: ['...kpppkkpppk...', '...kffk..kppk...', '.........kffk...'],
  w2: ['...kpppkkpppk...', '...kppk..kffk...', '...kffk.........'],
};
const BODY_SIDE = [
  '................', '.....kkkkkk.....', '....khhhhhhk....', '...khhhhhhhhk...', '...khhhhhHhhk...',
  '...khhhsssssk...', '...khhhsssesk...', '...khhssssssk...', '....khSssssk....', '.....krrwrk.....',
  '....krrrrrrk....', '....krrrrrrk....', '....krRrrrsk....', '....kbbbbbbk....', '....krrrrrrk....',
  '....krrrrrrk....', '....kRrrrrRk....'];
const LEGS_SIDE = {
  idle: ['.....kppppk.....', '.....kpkkpk.....', '.....kfk.kfk....'],
  w1: ['....kppppppk....', '...kpk....kpk...', '..kfk......kfk..'],
  w2: ['.....kppppk.....', '......kppk......', '......kffk......'],
};
function baseGrid(dir, frame) {
  const body = dir === 'down' ? BODY_DOWN : dir === 'up' ? BODY_UP : BODY_SIDE;
  const legs = (dir === 'right' ? LEGS_SIDE : LEGS_FB)[frame];
  return body.concat(legs).map((r) => r.split(''));
}
const set = (g, x, y, c) => { if (g[y] && x >= 0 && x < g[y].length) g[y][x] = c; };
const row = (g, y, x, s) => { for (let i = 0; i < s.length; i++) if (s[i] !== '.') set(g, x + i, y, s[i]); };
const full = (g, y, s) => { g[y] = s.split(''); };
const widen = (g, from) => g.map((r, y) => (y >= from ? r.slice(0, 8).concat([r[7], r[8]], r.slice(8)) : ['.'].concat(r, ['.'])));
const CHARS = [
  { id: 'xia', pal: { r: '#3D5A80', R: '#2B405E', b: '#C9A45C' },
    mod(g, d) {
      row(g, 0, 6, 'khhk'); set(g, 7, 1, 'h'); set(g, 8, 1, 'h');
      if (d === 'down') { set(g, 10, 1, 'a'); set(g, 13, 7, 'W'); set(g, 13, 8, 'K'); set(g, 12, 9, 'K'); }
      if (d === 'up') { set(g, 10, 1, 'a'); for (let i = 0; i < 6; i++) set(g, 11 - i, 10 + i, 'W'); set(g, 12, 9, 'K'); set(g, 13, 8, 'K'); }
      if (d === 'right') { set(g, 5, 1, 'a'); set(g, 3, 7, 'W'); set(g, 4, 8, 'K'); }
    } },
  { id: 'shen', pal: { r: '#86AB8E', R: '#62876C', b: '#EFE6D2' },
    mod(g, d) {
      if (d === 'down') {
        for (let y = 7; y <= 10; y++) { set(g, 3, y, 'h'); set(g, 12, y, 'h'); set(g, 2, y, 'k'); set(g, 13, y, 'k'); }
        row(g, 0, 9, 'kkk'); set(g, 9, 1, 'h'); set(g, 10, 1, 'h'); set(g, 11, 1, 'k'); set(g, 12, 0, 'a');
        row(g, 14, 12, 'GG'); row(g, 15, 12, 'GG'); set(g, 14, 14, 'k'); set(g, 14, 15, 'k');
      }
      if (d === 'up') { row(g, 0, 6, 'khhk'); set(g, 7, 1, 'h'); set(g, 8, 1, 'h'); set(g, 10, 0, 'a'); row(g, 9, 5, 'hhhhhh'); row(g, 10, 5, 'hhhhhh'); row(g, 11, 6, 'hhhh'); row(g, 12, 7, 'hh'); }
      if (d === 'right') { for (let y = 8; y <= 10; y++) { set(g, 4, y, 'h'); set(g, 3, y, 'k'); } row(g, 1, 3, 'kh'); row(g, 2, 2, 'khh'); set(g, 2, 1, 'a'); set(g, 11, 14, 'G'); set(g, 11, 15, 'G'); }
    } },
  { id: 'xu', pal: { r: '#8C6C4A', R: '#6B5236', b: '#3A3644', p: '#4B4A55' },
    mod(g) { ['......kkkk......', '....kkggggkk....', '..kkggggggggkk..', '.kGGGGGGGGGGGGk.'].forEach((s, i) => full(g, i, s)); } },
  { id: 'lu', pal: { r: '#5D677A', R: '#454D5C', b: '#2B2320' },
    mod(g, d) {
      ['....kkkkkkkk....', '...kKKKKKKKKk...', '.kkkKKKKKKKKkkk.'].forEach((s, i) => full(g, i, s));
      if (d === 'down') row(g, 7, 6, 'hhhh');
      if (d === 'right') row(g, 7, 9, 'hh');
    } },
  { id: 'zhou', pal: { r: '#9A6440', R: '#73472B', b: '#3A2A20' },
    mod(g, d) {
      row(g, 4, 4, 'WWWWWWWW');
      if (d === 'up') { set(g, 8, 5, 'W'); set(g, 9, 6, 'W'); }
      if (d === 'down') { for (let y = 11; y <= 16; y++) row(g, y, 6, 'mmmm'); row(g, 10, 7, 'mm'); set(g, 3, 11, 's'); set(g, 12, 11, 's'); set(g, 3, 12, 'S'); set(g, 12, 12, 'S'); }
      if (d === 'right') { for (let y = 11; y <= 16; y++) row(g, y, 8, 'mmm'); row(g, 10, 11, 'kWWk'); set(g, 12, 11, 'K'); set(g, 12, 12, 'K'); }
    } },
  { id: 'bandit', pal: { r: '#5E4130', R: '#44301F', b: '#2B2320', a: '#B8452F' },
    mod(g, d) {
      row(g, 4, 4, 'aaaaaaaa');
      if (d === 'down') { row(g, 7, 4, 'cccccccc'); row(g, 8, 5, 'cccccc'); }
      if (d === 'right') { row(g, 7, 7, 'ccccc'); row(g, 8, 6, 'ccccc'); set(g, 3, 4, 'a'); set(g, 2, 5, 'a'); }
      if (d === 'up') { set(g, 7, 5, 'a'); set(g, 8, 5, 'a'); set(g, 8, 6, 'a'); }
    } },
  { id: 'boss', pal: { r: '#6E3A28', R: '#4F281B', b: '#C9A45C' },
    mod(g, d) {
      const last = d === 'up' ? 8 : 5;
      for (let y = 1; y <= last; y++) g[y] = g[y].map((c) => (c === 'h' ? 's' : c === 'H' ? 'S' : c));
      row(g, 0, 7, 'kk'); set(g, 7, 1, 'h'); set(g, 8, 1, 'h');
      if (d === 'down') { row(g, 5, 5, 'hh'); row(g, 5, 9, 'hh'); row(g, 7, 5, 'hhhhhh'); row(g, 8, 5, 'hhhhhh'); row(g, 9, 6, 'hhhh'); }
      if (d === 'right') { row(g, 5, 9, 'hh'); row(g, 7, 8, 'hhhh'); row(g, 8, 7, 'hhhh'); }
    },
    post(g) { return widen(g, 9); } },
];
CHARS.push({ id:'archer',pal:{r:'#6A7553',R:'#46543B',b:'#B9A778',a:'#334A30'},mod:CHARS.find(c=>c.id==='bandit').mod });
CHARS.push({ id:'guard',pal:{r:'#5D7190',R:'#3A4965',b:'#BDAB78',a:'#8798A8'},mod:CHARS.find(c=>c.id==='bandit').mod });
CHARS.push({ id:'captain',pal:{r:'#394A60',R:'#253449',b:'#D8B66A'},mod:CHARS.find(c=>c.id==='boss').mod,post:CHARS.find(c=>c.id==='boss').post });
const SPR = {};
function gridToCanvas(g, pal) {
  const h = g.length, w = g[0].length, c = cnv(w, h), x = c.getContext('2d');
  for (let y = 0; y < h; y++) for (let i = 0; i < w; i++) { const k = g[y][i]; if (k !== '.') P(x, i, y, pal[k] || PAL[k] || '#FF00FF'); }
  return c;
}
function silhouette(s, col) { const c = cnv(s.width, s.height), g = c.getContext('2d'); g.drawImage(s, 0, 0); g.globalCompositeOperation = 'source-in'; R(g, 0, 0, s.width, s.height, col); return c; }
for (const ch of CHARS) {
  SPR[ch.id] = {};
  for (const d of ['down', 'up', 'right']) {
    SPR[ch.id][d] = {};
    for (const f of ['idle', 'w1', 'w2']) {
      let g = baseGrid(d, f); ch.mod(g, d); if (ch.post) g = ch.post(g, d);
      const s = gridToCanvas(g, ch.pal);
      SPR[ch.id][d][f] = { n: s, white: silhouette(s, '#FFFFFF'), red: silhouette(s, '#FF7A60') };
    }
  }
}
// 兵器：手里的刀剑单独画，跟着出招角度转
const WEAPON = { xia: { len: 15, col: '#E8E2D2', hilt: '#C9A45C' }, bandit: { len: 8, col: '#C9C2B2', hilt: '#3B2F28' }, boss: { len: 15, col: '#D8D2C2', hilt: '#3B2F28', wide: true } };
const WALK = ['w1', 'idle', 'w2', 'idle'];
const dirOf = (a) => { const c = Math.cos(a), s = Math.sin(a); return c > 0.7 ? 'right' : c < -0.7 ? 'left' : s > 0 ? 'down' : 'up'; };
// 素材精灵表：16×16 一帧，列是朝向（下、上、左、右），行 0–3 走路、行 4 出招；脚踩在帧底
const SHEET_COL = { down: 0, up: 1, left: 2, right: 3 }, SHEET_ROW = { idle: 0, w1: 1, w2: 3, atk: 4 };
function footShadow(g, x, y, w) {
  if (IMG.shadow && w <= 8) { g.drawImage(IMG.shadow, x - 6, y - 4); return; }
  g.fillStyle = 'rgba(0,0,0,0.3)'; g.fillRect(x - w + 1, y - 2, w * 2 - 2, 3); g.fillRect(x - w + 3, y + 1, w * 2 - 6, 1);
}
function drawChar(g,id,dir,frame,x,y,o){
  g.save();if(o?.alpha!==undefined)g.globalAlpha=o.alpha;
  worldArt.npc(g,id,dir,x+(o?.dx||0),y+(o?.dy||0),G?.time||0,frame);g.restore();
}
function drawWeapon(g, id, x, y, ang, behind) {
  const w = WEAPON[id]; if (!w || (id === 'boss' && BOSS.idle)) return;
  const hx = Math.round(x + Math.cos(ang) * 4), hy = Math.round(y - (SHEET[id] ? 7 : 9) + Math.sin(ang) * 3);
  const tx = hx + Math.cos(ang) * w.len, ty = hy + Math.sin(ang) * w.len * 0.85;
  g.save(); if (behind) g.globalAlpha = 0.85;
  line(g, hx + 1, hy + 1, tx + 1, ty + 1, INK);
  if (w.wide) line(g, hx, hy + 1, tx, ty + 1, '#9A9286');
  line(g, hx, hy, tx, ty, w.col);
  P(g, hx, hy, w.hilt); P(g, Math.round(hx - Math.cos(ang) * 2), Math.round(hy - Math.sin(ang) * 2), w.hilt);
  g.restore();
}
function portrait(canvas,id){worldArt.portrait(canvas,id);}

// ---- 地块 16×16
const TILE = {};
function tile(kind, v, f) {
  const key = kind + v + '_' + f; if (TILE[key]) return TILE[key];
  const c = cnv(16, 16), g = c.getContext('2d'), rnd = RNG(hash(kind) * 13 + v * 97 + 3);
  const speck = (n, col) => { for (let i = 0; i < n; i++) P(g, (rnd() * 16) | 0, (rnd() * 16) | 0, col); };
  const water = (h) => {
    R(g, 0, 0, 16, h, '#2C5768');
    for (let i = 0; i < 26; i++) P(g, (rnd() * 16) | 0, (rnd() * h) | 0, '#264C5B');
    const wr = RNG(hash('wave') + v * 7);
    for (let i = 0; i < 3; i++) { const wy = (wr() * (h - 2)) | 0, wx = ((wr() * 16) | 0) + f * 2; for (let k = 0; k < 4; k++) P(g, (wx + k) % 16, wy, k === 1 ? '#8FC0C8' : '#5D93A2'); }
  };
  switch (kind) {
    case 'grass':
      R(g, 0, 0, 16, 16, '#4E6A3C'); speck(40, '#5B7A45'); speck(18, '#42593A');
      for (let i = 0; i < 4; i++) { const x = (rnd() * 15) | 0, y = 2 + ((rnd() * 13) | 0); P(g, x, y, '#6F8F50'); P(g, x, y - 1, '#6F8F50'); }
      if (v === 1) { P(g, 5, 6, '#EFE6D2'); P(g, 4, 6, '#EFE6D2'); P(g, 6, 6, '#EFE6D2'); P(g, 5, 5, '#EFE6D2'); P(g, 5, 7, '#EFE6D2'); P(g, 5, 6, '#D8B66A'); P(g, 11, 11, '#D9553A'); P(g, 12, 11, '#D9553A'); }
      if (v === 2) { P(g, 10, 4, '#8A8A80'); P(g, 11, 4, '#A19D95'); P(g, 3, 12, '#8A8A80'); }
      break;
    case 'dark':
      R(g, 0, 0, 16, 16, '#23301E'); speck(30, '#2C3C25'); speck(24, '#1B2617'); fc(g, (v * 5) % 12 + 2, 6, 3, '#2A3A24'); break;
    case 'dirt':
      R(g, 0, 0, 16, 16, '#8A7152'); speck(32, '#7A6346'); speck(20, '#9B8263'); speck(3, '#B3A58C');
      if (v === 1) { for (let x = 0; x < 16; x++) { if (x % 5) { P(g, x, 5, '#73603F'); P(g, x, 11, '#73603F'); } } }
      break;
    case 'camp':
      R(g, 0, 0, 16, 16, '#6C5843'); speck(32, '#5D4B39'); speck(20, '#7B6650'); speck(2, '#9A8A72');
      if (v === 1) { P(g, 4, 9, '#3B2F28'); P(g, 5, 9, '#3B2F28'); P(g, 5, 10, '#3B2F28'); }
      break;
    case 'stone': {
      R(g, 0, 0, 16, 16, '#6F797D'); speck(16, '#646E72'); speck(8, '#7D878B');
      R(g, 0, 0, 16, 1, '#4C5457'); R(g, 0, 8, 16, 1, '#4C5457');
      const vx = v % 2 ? [3, 11] : [6, 14];
      R(g, vx[0], 1, 1, 7, '#4C5457'); R(g, (vx[0] + 5) % 16, 9, 1, 7, '#4C5457'); R(g, vx[1], 9, 1, 7, '#4C5457');
      R(g, 0, 1, 16, 1, '#869094'); R(g, 0, 9, 16, 1, '#869094');
      if (v === 1) { P(g, 9, 4, '#5A6366'); P(g, 10, 5, '#5A6366'); P(g, 11, 5, '#5A6366'); }
      break;
    }
    case 'water': water(16); break;
    case 'shore':
      water(9); R(g, 0, 9, 16, 7, '#C4B087');
      for (let i = 0; i < 14; i++) P(g, (rnd() * 16) | 0, 10 + ((rnd() * 6) | 0), '#AE9A70');
      for (let x = 0; x < 16; x++) if ((x + f) % 3 !== 0) P(g, x, 8 + ((x + f) % 2), '#DCE8E4');
      break;
    case 'plank':
      R(g, 0, 0, 16, 16, '#7C5A3C');
      for (const y of [0, 4, 8, 12]) { R(g, 0, y, 16, 1, '#5A3F29'); R(g, 0, y + 1, 16, 1, '#93704E'); }
      P(g, 2, 2, '#3A2A1D'); P(g, 13, 6, '#3A2A1D'); P(g, 2, 10, '#3A2A1D'); P(g, 13, 14, '#3A2A1D');
      R(g, 0, 0, 1, 16, '#5A3F29'); R(g, 15, 0, 1, 16, '#5A3F29');
      break;
  }
  TILE[key] = c; return c;
}
const CODE = { '~': ['water', 0], '_': ['shore', 0], ',': ['grass', 0], "'": ['grass', 1], ';': ['grass', 2], '=': ['stone', 0], ':': ['dirt', 0], '#': ['plank', 0], c: ['camp', 0], X: ['dark', 0] };

// ---- 物件（描边）
function mkHouse(roof, roofD, sign, chimney) {
  const c = cnv(50, 50), g = c.getContext('2d'), o = 1, oy = 4;
  if (chimney) { R(g, 34, 0, 6, 10, '#5A524A'); R(g, 34, 0, 6, 1, '#3B2F28'); }
  for (let y = 0; y < 15; y++) {
    const inset = y < 3 ? 10 - y * 2 : Math.max(0, 6 - Math.floor((y - 3) / 2));
    R(g, o + inset, oy + y, 48 - inset * 2, 1, y === 0 ? roofD : y >= 13 ? '#6A737B' : roof);
    if (y >= 2 && y <= 12) for (let x = inset + 2; x < 48 - inset; x += 4) P(g, o + x, oy + y, roofD);
  }
  P(g, o, oy + 10, roof); P(g, o + 47, oy + 10, roof); P(g, o + 1, oy + 11, roof); P(g, o + 46, oy + 11, roof);
  R(g, o + 4, oy + 15, 40, 24, '#DCD2BD'); R(g, o + 40, oy + 15, 4, 24, '#C4B9A3'); R(g, o + 4, oy + 15, 40, 2, '#A99E8A');
  R(g, o + 4, oy + 15, 3, 24, '#6B4630'); R(g, o + 41, oy + 15, 3, 24, '#6B4630');
  R(g, o + 18, oy + 23, 12, 16, '#6B4630'); R(g, o + 19, oy + 24, 10, 15, '#4A3424'); R(g, o + 24, oy + 25, 1, 14, '#3A2A1D'); P(g, o + 22, oy + 31, '#C9A45C'); P(g, o + 26, oy + 31, '#C9A45C');
  for (const wx of [9, 33]) { R(g, o + wx - 1, oy + 20, 9, 9, '#6B4630'); R(g, o + wx, oy + 21, 7, 7, '#3A2F28'); R(g, o + wx, oy + 24, 7, 1, '#8A6444'); R(g, o + wx + 3, oy + 21, 1, 7, '#8A6444'); }
  R(g, o + 20, oy + 17, 8, 5, sign); P(g, o + 23, oy + 19, '#D8B66A'); P(g, o + 24, oy + 19, '#D8B66A');
  R(g, o + 2, oy + 39, 44, 5, '#8B8780'); R(g, o + 2, oy + 39, 44, 1, '#A19D95');
  return outline(c);
}
function mkTree(v) { const c = cnv(30, 38), g = c.getContext('2d'); R(g, 13, 24, 4, 13, '#5A4030'); R(g, 13, 24, 1, 13, '#6E5039'); const dk = v ? '#3A4A2A' : '#2F4A2E', md = v ? '#53643A' : '#3D5E37', lt = v ? '#6E7E46' : '#4F7645'; fc(g, 15, 14, 12, dk); fc(g, 13, 12, 9, md); fc(g, 11, 9, 5, lt); fc(g, 10, 7, 2, v ? '#8C9A58' : '#6A9256'); for (let i = 0; i < 9; i++) P(g, 8 + ((i * 7) % 15), 18 + ((i * 3) % 6), '#26402A'); return outline(c); }
function mkRock() { const c = cnv(24, 16), g = c.getContext('2d'); fe(g, 12, 9, 10, 5, '#5F5F5A'); fe(g, 11, 7, 8, 4, '#77776F'); fe(g, 8, 6, 3, 2, '#93938A'); P(g, 15, 9, '#4F4F4A'); P(g, 16, 10, '#4F4F4A'); return outline(c); }
function mkTent() { const c = cnv(36, 30), g = c.getContext('2d'); for (let y = 2; y < 28; y++) { const half = Math.floor((y - 2) * 0.62); R(g, 18 - half, y, half, 1, '#A08A66'); R(g, 18, y, half + 1, 1, '#7E6C4E'); } for (let y = 15; y < 28; y++) { const half = Math.floor((y - 15) * 0.42); R(g, 18 - half, y, half * 2 + 1, 1, '#2B2320'); } R(g, 17, 0, 2, 3, '#3B2F28'); P(g, 19, 0, '#C8402C'); P(g, 20, 0, '#C8402C'); P(g, 20, 1, '#C8402C'); line(g, 7, 20, 10, 18, '#8A7656'); return outline(c); }
function mkWood() { const c = cnv(20, 15), g = c.getContext('2d'); for (const [x, y] of [[5, 10], [12, 10], [8, 5], [15, 5]]) { fc(g, x, y, 3, '#8A6040'); P(g, x, y, '#C8A070'); P(g, x - 1, y, '#A87850'); } return outline(c); }
function mkHerb() { const c = cnv(16, 14), g = c.getContext('2d'); for (const x of [4, 8, 12]) { line(g, x, 12, x, 6, '#3F7A3A'); fe(g, x - 2, 9, 2, 1, '#64A659'); fe(g, x + 2, 8, 2, 1, '#64A659'); P(g, x, 4, '#EFE6D2'); P(g, x - 1, 5, '#EFE6D2'); P(g, x + 1, 5, '#EFE6D2'); P(g, x, 5, '#D8B66A'); } return outline(c); }
function mkBoat() { const c = cnv(48, 16), g = c.getContext('2d'); for (let y = 5; y < 14; y++) { const inset = Math.round(((y - 5) * (y - 5)) / 4) + (y === 5 ? 0 : 1); R(g, 1 + inset, y, 46 - inset * 2, 1, y === 5 ? '#8A6444' : y < 8 ? '#4E3422' : '#6B4A30'); } R(g, 20, 1, 9, 4, '#8A7A5A'); R(g, 20, 1, 9, 1, '#A8986E'); return outline(c); }
function mkLantern() { const c = cnv(9, 18), g = c.getContext('2d'); R(g, 4, 7, 1, 10, '#3B2F28'); R(g, 2, 1, 5, 1, '#3B2F28'); fe(g, 4, 4, 3, 3, '#C0452E'); P(g, 3, 3, '#E8845A'); P(g, 3, 4, '#E8845A'); R(g, 3, 8, 3, 1, '#3B2F28'); return outline(c); }
function mkFence() { const c = cnv(18, 12), g = c.getContext('2d'); R(g, 2, 1, 2, 10, '#7A5A3C'); R(g, 14, 1, 2, 10, '#7A5A3C'); R(g, 1, 3, 16, 2, '#8A6848'); R(g, 1, 7, 16, 2, '#8A6848'); return outline(c); }
function mkReed() { const c = cnv(10, 14), g = c.getContext('2d'); for (const [x, h] of [[2, 9], [4, 12], [6, 10], [8, 7]]) { line(g, x, 13, x, 13 - h, '#7A8A4A'); P(g, x, 13 - h, '#A8864A'); P(g, x, 12 - h, '#A8864A'); } return outline(c); }
function mkBarrel() { const c = cnv(12, 14), g = c.getContext('2d'); R(g, 1, 2, 10, 11, '#7A5A3C'); R(g, 1, 2, 10, 2, '#93704E'); R(g, 1, 6, 10, 1, '#3B2F28'); R(g, 1, 10, 10, 1, '#3B2F28'); R(g, 8, 3, 2, 9, '#5A3F29'); return outline(c); }
function mkBoard() { const c = cnv(22, 24), g = c.getContext('2d'); R(g, 3, 8, 2, 15, '#5A3F29'); R(g, 17, 8, 2, 15, '#5A3F29'); R(g, 1, 2, 20, 12, '#7A5A3C'); R(g, 3, 4, 7, 8, '#EADFC4'); R(g, 12, 4, 7, 7, '#E0D2B0'); for (const y of [6, 8, 10]) { R(g, 4, y, 5, 1, '#8A7A6A'); } R(g, 13, 6, 5, 1, '#8A7A6A'); R(g, 13, 8, 3, 1, '#C8402C'); R(g, 0, 1, 22, 2, '#4E3422'); return outline(c); }
function mkCart() { const c = cnv(34, 20), g = c.getContext('2d'); for (let i = 0; i < 4; i++) R(g, 3, 6 + i * 3, 22, 2, i % 2 ? '#7A5A3C' : '#8A6848'); R(g, 3, 6, 2, 12, '#5A3F29'); fc(g, 27, 12, 5, '#5A3F29'); fc(g, 27, 12, 3, '#8A6848'); P(g, 27, 12, '#3B2F28'); line(g, 22, 12, 32, 12, '#3B2F28'); line(g, 27, 7, 27, 17, '#3B2F28'); R(g, 8, 2, 8, 4, '#9A7A50'); R(g, 9, 1, 6, 1, '#B8986A'); P(g, 12, 3, '#EADFC4'); P(g, 13, 4, '#EADFC4'); return outline(c); }
function mkSign() { const c = cnv(18, 22), g = c.getContext('2d'); R(g, 8, 6, 2, 15, '#5A3F29'); R(g, 2, 3, 14, 6, '#8A6848'); R(g, 2, 3, 14, 1, '#A8864A'); R(g, 4, 5, 3, 2, '#3B2F28'); R(g, 9, 5, 4, 2, '#3B2F28'); line(g, 14, 6, 16, 6, '#8A6848'); P(g, 16, 5, '#8A6848'); P(g, 16, 7, '#8A6848'); return outline(c); }
function mkDummy(hit) { const c = cnv(18, 24), g = c.getContext('2d'); R(g, 8, 3, 3, 20, hit ? '#A87850' : '#8A6040'); R(g, 8, 3, 1, 20, '#A87850'); R(g, 3, 9, 13, 2, '#7A5A3C'); fe(g, 9, 4, 3, 3, '#C8A86A'); P(g, 8, 3, '#8A6A3A'); P(g, 10, 4, '#8A6A3A'); R(g, 6, 12, 7, 6, '#B89A5A'); line(g, 6, 14, 12, 14, '#8A6A3A'); R(g, 5, 22, 9, 2, '#5A4030'); return outline(c); }
const FIRE = [0, 1, 2].map((f) => {
  const c = cnv(16, 18), g = c.getContext('2d');
  line(g, 2, 16, 13, 13, '#5A4030'); line(g, 2, 13, 13, 16, '#4A3424');
  const rnd = RNG(17 + f * 31);
  for (let i = 0; i < 3; i++) { const cx = 6 + i * 2 + ((rnd() * 2) | 0) - 1; fe(g, cx, 10 - i, 2, 4 + ((rnd() * 2) | 0), '#E0603F'); }
  fe(g, 8, 11, 2, 3, '#F2A03C'); fe(g, 8, 12, 1, 2, '#F8D878'); P(g, 6 + f, 3, '#F2A03C');
  return outline(c);
});
const OBJ = {
  house: mkHouse('#4A5159', '#363C43', '#2F6B5A'), home: mkHouse('#5B5650', '#45403B', '#8A6A3A'), forge: mkHouse('#5A4A3E', '#3E322A', '#A8402C', true),
  tree: mkTree(0), tree2: mkTree(1), rock: mkRock(), tent: mkTent(), wood: mkWood(), herb: mkHerb(), boat: mkBoat(), lantern: mkLantern(), fence: mkFence(),
  reed: mkReed(), barrel: mkBarrel(), board: mkBoard(), cart: mkCart(), sign: mkSign(), dummy: mkDummy(false), dummyHit: mkDummy(true),
};
Object.assign(OBJ, { home2: OBJ.home, bigtree: OBJ.tree, rock2: OBJ.rock, boulder: OBJ.rock, boulder2: OBJ.rock, tent2: OBJ.tent, stump: OBJ.wood, bush: OBJ.tree2, firepit: cnv(1, 1) });

// ---- 素材图（Ninja Adventure 素材包，CC0，来源见 assets/na/README.md）。某张没读到就退回上面的程序绘制
const NA = 'assets/na/';
const IMG = {}, SHEET = {}, BOSS = {}, FACE = {};
const CHAR_FILE = { xia: 'player', shen: 'shen', xu: 'xu', lu: 'lu', zhou: 'zhou', bandit: 'bandit', archer: 'archer', guard: 'guard', captain: 'captain' };
// 首领每个动作一条图：站立 / 走 / 受击是 96×48 一帧，蓄力 / 出招是 96×96 一帧，分左右两版
const BOSS_FILE = { idle: 48, walk: 48, hit: 48, chargeL: 96, chargeR: 96, attackL: 96, attackR: 96 };
function loadImg(src) { return new Promise((ok) => { const im = new Image(); im.onload = () => ok(im); im.onerror = () => ok(null); im.src = NA + src; }); }
const crop = (im, x, y, w, h) => { const c = cnv(w, h); c.getContext('2d').drawImage(im, x, y, w, h, 0, 0, w, h); return c; };
async function loadAssets() {
  const jobs = [];
  const add = (src, fn) => jobs.push(loadImg(src).then((im) => { if (im) fn(im); }));
  for (const k of ['floor', 'water', 'nature', 'house', 'camp']) add('tiles/' + k + '.png', (im) => { IMG[k] = im; });
  add('shadow.png', (im) => { IMG.shadow = im; });
  for (const [id, f] of Object.entries(CHAR_FILE)) {
    add('chars/' + f + '.png', (im) => { SHEET[id] = { n: im, white: silhouette(im, '#FFFFFF'), red: silhouette(im, '#FF7A60') }; });
    add('faces/' + f + '.png', (im) => { FACE[id] = im; });
  }
  add('faces/boss.png', (im) => { FACE.boss = im; });
  const boss = {};
  for (const [k, fh] of Object.entries(BOSS_FILE)) add('boss/' + k + '.png', (im) => { boss[k] = { n: im, white: silhouette(im, '#FFFFFF'), fh, count: Math.round(im.width / 96) }; });
  await Promise.all(jobs);
  if (Object.keys(boss).length === Object.keys(BOSS_FILE).length) Object.assign(BOSS, boss);
  if (IMG.house && IMG.nature && IMG.camp && IMG.water) Object.assign(OBJ, {
    house: crop(IMG.house, 0, 0, 64, 48), home: crop(IMG.house, 192, 0, 64, 48), home2: crop(IMG.house, 64, 0, 64, 48), forge: crop(IMG.house, 256, 0, 48, 48),
    tree: crop(IMG.nature, 0, 0, 32, 32), tree2: crop(IMG.nature, 32, 0, 32, 32), bigtree: crop(IMG.nature, 48, 288, 48, 48),
    rock: crop(IMG.nature, 240, 144, 16, 16), rock2: crop(IMG.nature, 288, 144, 16, 16), boulder: crop(IMG.nature, 208, 128, 32, 32), boulder2: crop(IMG.nature, 256, 128, 32, 32),
    tent: crop(IMG.camp, 64, 0, 48, 48), tent2: crop(IMG.camp, 112, 0, 48, 48), firepit: crop(IMG.camp, 192, 80, 32, 32), stump: crop(IMG.camp, 16, 80, 32, 32),
    wood: crop(IMG.camp, 0, 0, 32, 16), herb: crop(IMG.nature, 96, 176, 16, 16), boat: crop(IMG.water, 416, 0, 32, 16), lantern: crop(IMG.camp, 96, 80, 16, 32),
    fence: crop(IMG.house, 160, 80, 48, 16), reed: crop(IMG.nature, 144, 176, 16, 16), barrel: crop(IMG.camp, 64, 80, 16, 16), bush: crop(IMG.nature, 96, 160, 16, 16),
  });
}

// ---- 界面素材
function frameImg(hi, mid, lo, fill) {
  const c = cnv(12, 12), g = c.getContext('2d');
  R(g, 1, 0, 10, 1, INK); R(g, 1, 11, 10, 1, INK); R(g, 0, 1, 1, 10, INK); R(g, 11, 1, 1, 10, INK);
  R(g, 1, 1, 10, 10, mid); R(g, 1, 1, 10, 1, hi); R(g, 1, 1, 1, 10, hi); R(g, 1, 10, 10, 1, lo); R(g, 10, 1, 1, 10, lo);
  g.clearRect(3, 3, 6, 6); R(g, 3, 3, 6, 6, fill);
  return 'url(' + c.toDataURL() + ')';
}
function roundBtn(d, ring, ringLo, inner) {
  const c = cnv(d, d), g = c.getContext('2d'), r = d / 2;
  for (let y = 0; y < d; y++) for (let x = 0; x < d; x++) {
    const dx = x + 0.5 - r, dy = y + 0.5 - r, dist = Math.hypot(dx, dy);
    if (dist > r - 0.3) continue;
    P(g, x, y, dist > r - 1.3 ? INK : dist > r - 3.3 ? (dy < -dx * 0.2 ? ring : ringLo) : inner || (dx + dy < -r * 0.7 ? '#2E2620' : '#1F1A16'));
  }
  return 'url(' + c.toDataURL() + ')';
}
function stickBase() {
  const d = 42, c = cnv(d, d), g = c.getContext('2d'), r = d / 2;
  for (let y = 0; y < d; y++) for (let x = 0; x < d; x++) { const dist = Math.hypot(x + 0.5 - r, y + 0.5 - r); if (dist > r - 0.3) continue; P(g, x, y, dist > r - 1.3 ? INK : dist > r - 2.3 ? 'rgba(240,232,214,0.45)' : 'rgba(240,232,214,0.07)'); }
  return 'url(' + c.toDataURL() + ')';
}
const rs = document.documentElement.style;
// 面板统一用深紫灰（借鉴 Sephiria 的菜单底色），选中项金框，地名和说话人用米色牌子
rs.setProperty('--fDark', frameImg('#6B5E8A', '#4A3F63', '#2A2340', 'rgba(28,23,42,0.9)'));
rs.setProperty('--fPaper', frameImg('#6B5E8A', '#4A3F63', '#2A2340', 'rgba(33,27,49,0.97)'));
rs.setProperty('--fGold', frameImg('#F0D78F', '#D8B66A', '#9A7A3A', 'rgba(33,27,49,0.95)'));
rs.setProperty('--fOpt', frameImg('#5A4F78', '#3B3352', '#231D33', '#2C2542'));
rs.setProperty('--fOptSel', frameImg('#F0D78F', '#D8B66A', '#9A7A3A', '#3A3150'));
rs.setProperty('--bRed', roundBtn(32, '#E0603F', '#A8402C'));
rs.setProperty('--bJade', roundBtn(26, '#5FB3A1', '#3F8576'));
rs.setProperty('--bGray', roundBtn(24, '#BDB2A0', '#7E7466'));
rs.setProperty('--bHot', roundBtn(26, '#F2A03C', '#E0603F', '#3A2218'));
rs.setProperty('--iStick', stickBase());
rs.setProperty('--iKnob', roundBtn(18, '#F0E8D6', '#BDB2A0', '#D8CFBC'));
const ICONS = {
  coin: (g) => { fc(g, 8, 8, 6, '#A8823A'); fc(g, 7, 7, 5, '#D8B66A'); P(g, 5, 5, '#F0D78F'); P(g, 4, 6, '#F0D78F'); g.clearRect(6, 6, 4, 4); },
  bandage: (g) => { R(g, 2, 5, 11, 7, '#EFE6D2'); R(g, 2, 10, 11, 2, '#CFC4AE'); fc(g, 12, 8, 3, '#E0D6C0'); P(g, 12, 8, '#BDB2A0'); R(g, 6, 6, 1, 4, '#D9553A'); R(g, 5, 7, 3, 1, '#D9553A'); },
  pack: (g) => { R(g, 3, 5, 10, 9, '#9A7A50'); R(g, 3, 5, 10, 2, '#B8986A'); R(g, 6, 2, 4, 3, '#7A5A38'); R(g, 7, 8, 2, 3, '#D8B66A'); },
  book: (g) => { R(g, 3, 2, 10, 12, '#7A5236'); R(g, 5, 3, 7, 10, '#EFE6D2'); R(g, 3, 2, 2, 12, '#5A3B26'); R(g, 6, 5, 5, 1, '#8A7A6A'); R(g, 6, 7, 5, 1, '#8A7A6A'); R(g, 6, 9, 3, 1, '#8A7A6A'); },
  talk: (g) => { R(g, 2, 3, 12, 8, '#EFE6D2'); R(g, 3, 2, 10, 1, '#EFE6D2'); R(g, 3, 11, 10, 1, '#EFE6D2'); R(g, 4, 12, 2, 2, '#EFE6D2'); for (const x of [5, 8, 11]) P(g, x, 7, '#3B2F28'); },
  atk: (g) => { line(g, 3, 13, 12, 4, '#EFE6D2'); line(g, 4, 13, 13, 4, '#BDB2A0'); R(g, 3, 10, 4, 1, '#C9A45C'); R(g, 5, 8, 1, 4, '#C9A45C'); line(g, 2, 14, 3, 13, '#5A3B26'); },
  skill: (g) => { line(g, 3, 13, 11, 5, '#EFE6D2'); line(g, 4, 13, 12, 5, '#BDB2A0'); R(g, 10, 2, 4, 1, '#5FB3A1'); R(g, 13, 2, 1, 4, '#5FB3A1'); line(g, 7, 3, 13, 9, '#5FB3A1'); },
  dodge: (g) => { line(g, 2, 12, 6, 7, '#EFE6D2'); line(g, 6, 7, 12, 5, '#EFE6D2'); line(g, 3, 13, 7, 8, '#BDB2A0'); R(g, 11, 3, 1, 5, '#EFE6D2'); R(g, 9, 3, 3, 1, '#EFE6D2'); },
  save: (g) => { R(g, 2, 2, 12, 12, '#5FB3A1'); R(g, 4, 2, 8, 5, '#EFE6D2'); R(g, 9, 3, 2, 3, '#3B2F28'); R(g, 4, 9, 8, 5, '#2B4A44'); },
  close: (g) => { line(g, 4, 4, 11, 11, '#5A3B26'); line(g, 11, 4, 4, 11, '#5A3B26'); line(g, 5, 4, 12, 11, '#5A3B26'); line(g, 12, 4, 5, 11, '#5A3B26'); },
};
const ICON_URL = {};
for (const [k, fn] of Object.entries(ICONS)) { const c = cnv(16, 16); fn(c.getContext('2d')); if (k !== 'close') outline(c); ICON_URL[k] = c.toDataURL(); }
document.querySelectorAll('img[data-ic]').forEach((im) => { im.src = ICON_URL[im.dataset.ic]; });
portrait($('myFace'), 'xia');

// ================================================================ 声音（开始后才能出声）
// 声音默认关闭；玩家主动开启后记住偏好。按钮显示以 AudioContext 实际是否在运行为准（#7）。
const SOUND_KEY = 'qingshi-sound';
let AC = null, combatAudio = null, music = null, soundEnabled = (() => { try { return localStorage.getItem(SOUND_KEY) === 'on'; } catch { return false; } })(), audioWarned = false;
const combatArt = createChapterCombatRenderer(), combatEvents = [];
const cue = name => combatEvents.push(name);
const SFX = { swing:()=>cue('swing'), swing3:()=>cue('heavy'), skill:()=>cue('cast'),
  hit:()=>{}, hitBig:()=>{}, hurt:()=>{}, tele:()=>cue('tele'), teleS:()=>cue('tele'),
  interrupt:()=>cue('interrupt'), dodge:()=>cue('dodge'), evade:()=>cue('evade'),
  heal:()=>cue('heal'), coin:()=>cue('coin'), ui:()=>cue('ui'), down:()=>cue('down'),
  pickup:()=>cue('pickup'), buy:()=>cue('buy'), craft:()=>cue('craft'), note:()=>cue('note'), done:()=>cue('done') };
function impact(kind, face, killed=false) {
  const event={name:'impact',kind,face,killed};combatEvents.push(event);
  G.hitstop=Math.max(G.hitstop,IMPACTS[kind].stop+(killed ? .008 : 0));
}

// ================================================================ 世界（1 个像素 = 3 个世界单位，1 格地块 = 16 像素 = 48 单位）
const U = 3;
const MAP_W = 70, MAP_H = 25;
const WORLD = { w: MAP_W * 16 * U, h: MAP_H * 16 * U };
// 物件：[种类, 左上角 x, y]（像素）。SIZE 是素材图的尺寸，程序绘制的替身按底边居中对齐到同一个框里
const PROPS = [
  ['house', 8, 54], ['home', 197, 50], ['forge', 130, 188], ['home2', 16, 198],
  ['boat', 186, 14], ['lantern', 32, 114], ['lantern', 100, 114], ['lantern', 210, 114], ['fence', 72, 58],
  ['reed', 15, 36], ['reed', 52, 38], ['reed', 113, 37], ['reed', 236, 36], ['reed', 270, 40],
  ['barrel', 122, 58], ['barrel', 128, 68], ['board', 178, 50], ['sign', 244, 132], ['cart', 296, 160],
  ['tree', -7, 246], ['tree2', 57, 268], ['bigtree', 227, 244], ['tree', 289, 274], ['tree2', 359, 276], ['bigtree', 321, -6], ['tree', 539, 12], ['tree2', 559, 268], ['tree', 789, 36], ['bigtree', 767, 240], ['tree', 599, 278], ['tree2', 469, 274], ['tree', 679, 276], ['tree2', 262, 64],
  ['boulder', 286, 10], ['rock', 312, 34], ['rock2', 294, 46], ['boulder2', 306, 40], ['rock', 386, 178], ['rock2', 406, 180], ['rock', 426, 178], ['rock2', 446, 180], ['boulder', 318, 226], ['rock', 344, 248],
  ['tent', 622, 20], ['tent2', 714, 198], ['boulder', 756, 104], ['boulder2', 596, 194], ['barrel', 668, 50], ['barrel', 680, 58], ['stump', 700, 80],
  ['bush', 252, 100], ['bush', 270, 214], ['bush', 520, 60], ['bush', 560, 230], ['bush', 744, 150], ['bush', 600, 60],
];
// 青石渡扩图：匪营整体东移 220 像素，南面添了绕路、旧行囊和渡口对峙场地
for (const prop of PROPS) if (prop[1] >= 590) prop[1] += 220;
PROPS.push(['tree', 479, 311], ['tree2', 589, 326], ['rock', 434, 310], ['rock2', 712, 180], ['tree', 849, 356], ['tent', 939, 197], ['barrel', 943, 98], ['board', 117, 290], ['barrel', 170, 305], ['barrel', 184, 305], ['home2', 1, 300]);
// 扩图后空出来的山坡和南路两侧补些树石，不挡路、不压对峙场地（x 150–300 的渡口南面）
PROPS.push(['tree', 610, 20], ['tree2', 650, 6], ['bigtree', 700, -6], ['tree', 764, 14], ['bush', 822, 44], ['tree2', 862, 4],
  ['tree', 600, 214], ['bush', 640, 252], ['tree2', 772, 236], ['boulder', 792, 290], ['rock', 650, 266],
  ['tree', 336, 350], ['bush', 392, 372], ['tree2', 432, 356], ['tree', 612, 352], ['bush', 700, 372], ['tree', 764, 350], ['tree2', 824, 362], ['bush', 884, 334], ['tree', 958, 346], ['tree2', 1036, 352], ['boulder', 1078, 300],
  ['tree', 1084, 120], ['tree2', 1088, 200], ['bush', 1060, 60]);
const SIZE = { house: [64, 48], home: [64, 48], home2: [64, 48], forge: [48, 48], tree: [32, 32], tree2: [32, 32], bigtree: [48, 48], rock: [16, 16], rock2: [16, 16], boulder: [32, 32], boulder2: [32, 32], tent: [48, 48], tent2: [48, 48], boat: [32, 16], lantern: [16, 32], fence: [48, 16], reed: [16, 16], barrel: [16, 16], board: [22, 24], cart: [34, 20], sign: [18, 22], stump: [32, 32], bush: [16, 16] };
const FOOT = { house: [3, 16, 58, 30], home: [3, 16, 58, 30], home2: [3, 16, 58, 30], forge: [2, 16, 44, 30], tree: [11, 25, 10, 6], tree2: [11, 25, 10, 6], bigtree: [17, 38, 14, 8], rock: [2, 7, 12, 8], rock2: [2, 7, 12, 8], boulder: [3, 12, 26, 18], boulder2: [3, 12, 26, 18], tent: [4, 18, 40, 28], tent2: [4, 18, 40, 28], fence: [1, 8, 46, 7], barrel: [2, 7, 12, 8], board: [2, 18, 18, 5], cart: [2, 10, 30, 9], sign: [7, 17, 4, 4], stump: [3, 10, 26, 18], lantern: [2, 27, 6, 4] };
// 北缘密林：山道和匪营背后的树墙，人走不进去（地块坐标：列、行、宽、高）
const PLATS = [[22, 0, 8, 2], [58, 0, 7, 2]];
const CLIFF = 10;
for (const [c, r, w, h] of PLATS) {
  const rnd = RNG(c * 31 + r * 7 + 5);
  for (let y = r * 16 - 18; y < (r + h) * 16 - 10; y += 13) for (let x = c * 16 - 8; x < (c + w) * 16 - 16; x += 17) PROPS.push([rnd() < 0.5 ? 'tree' : 'tree2', x + ((rnd() * 6) | 0), y + ((rnd() * 4) | 0)]);
}
const FIREPOS = [866, 100];
const DUMMY_POS = { x: 96 * U, y: 250 * U };
const OBST = [
  { x: 0, y: 0, w: 144 * U, h: 40 * U }, { x: 176 * U, y: 0, w: 112 * U, h: 40 * U },
  { x: (FIREPOS[0] - 5) * U, y: (FIREPOS[1] + 8) * U, w: 26 * U, h: 20 * U },
  { x: DUMMY_POS.x - 9, y: DUMMY_POS.y - 9, w: 18, h: 9 },
];
for (const [k, x, y] of PROPS) { const f = FOOT[k]; if (f) OBST.push({ x: (x + f[0]) * U, y: (y + f[1]) * U, w: f[2] * U, h: f[3] * U }); }
for (const [c, r, w, h] of PLATS) OBST.push({ x: c * 16 * U, y: r * 16 * U, w: w * 16 * U, h: (h * 16 + (r + h < MAP_H ? CLIFF : 0)) * U });
const spriteW=im=>im.logicalWidth||im.width,spriteH=im=>im.logicalHeight||im.height;
const drawArt=(g,im,x,y)=>g.drawImage(im,x,y,spriteW(im),spriteH(im));
function propXY(k,x,y){const im=OBJ[k],s=SIZE[k]||[spriteW(im),spriteH(im)];return [x+((s[0]-spriteW(im))>>1),y+s[1]-spriteH(im)];}
const MAP = (() => {
  const rnd = RNG(4242), m = [];
  const dist = (px, py, pts) => { let best = 1e9; for (let i = 0; i + 1 < pts.length; i++) { const [ax, ay] = pts[i], [bx, by] = pts[i + 1]; const vx = bx - ax, vy = by - ay, t = clamp(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy), 0, 1); best = Math.min(best, Math.hypot(px - ax - vx * t, py - ay - vy * t)); } return best; };
  const MAIN = [[256,153],[350,120],[420,113],[500,140],[620,180],[750,140],[840,150],[930,152]];
  const BYPASS = [[333, 140], [370, 230], [433, 247], [500, 203], [540, 153]];
  const FORGE = [[153, 176], [153, 238]], YARD = [[60, 176], [100, 248]];
  for (let r = 0; r < MAP_H; r++) {
    const ln = [];
    for (let c = 0; c < MAP_W; c++) {
      const q = rnd();
      let k = q < 0.07 ? "'" : q < 0.11 ? ';' : ',';
      const px = c * 16 + 8, py = r * 16 + 8;
      if (c >= 51 && r >= 2 && r <= 21) k = 'c';
      if (dist(px, py, MAIN) < 15 || dist(px, py, BYPASS) < 13 || dist(px, py, FORGE) < 10 || dist(px, py, YARD) < 9) k = ':';
      if (c <= 16 && (r === 9 || r === 10)) k = '=';
      if (c<=16 && r>=18 && r<=22) k='=';
      if (dist(px,py,[[120,170],[120,300],[160,330]])<12) k='=';
      if (dist(px,py,[[490,220],[535,335],[680,320],[740,170]])<11) k=':';
      if ((c === 9 || c === 10) && r >= 3 && r <= 8) k = '=';
      if (c <= 17 && r <= 1) k = '~';
      if (c <= 17 && r === 2) k = '_';
      if ((c === 9 || c === 10) && r <= 2) k = '#';
      ln.push(k);
    }
    m.push(ln);
  }
  return m;
})();
const kindAt = (c, r) => (r < 0 || r >= MAP_H || c < 0 || c >= MAP_W ? (r < 3 && c >= -6 && c <= 17 ? (r === 2 ? 'shore' : 'water') : 'dark') : CODE[MAP[r][c]][0]);
// 素材地块：草地铺底；泥路、青石、河水按四邻自动拼边（3×3 拼块 + 横条 + 竖条 + 孤点，在图集里排成 4×4）
const GROUND = { dirt: 'path', camp: 'path', stone: 'stone', water: 'water', shore: 'water', plank: 'water' };
const autoCell = (n, s, w, e) => [w && e ? 1 : !w && !e ? 3 : !w ? 0 : 2, n && s ? 1 : !n && !s ? 3 : !n ? 0 : 2];
let STONE = null;
// 青石板：把泥路那几块的泥色换成青灰，再刻出错缝的石缝（file:// 下读不了像素，就退回原色泥路）
function stoneAtlas() {
  const c = cnv(64, 80), g = c.getContext('2d'); g.drawImage(IMG.floor, 0, 112, 64, 80, 0, 0, 64, 80);
  try {
    const d = g.getImageData(0, 0, 64, 80), px = d.data;
    for (let i = 0; i < px.length; i += 4) {
      const r = px[i], gr = px[i + 1], b = px[i + 2]; if (r < gr + 10) continue;
      const x = (i >> 2) % 64, y = (i >> 2) >> 6, L = 0.3 * r + 0.59 * gr + 0.11 * b;
      const k = y % 8 === 0 || (x + ((y >> 3) % 2) * 8) % 16 === 0 ? 0.74 : 1;
      px[i] = L * 0.8 * k + 14; px[i + 1] = L * 0.86 * k + 18; px[i + 2] = L * 0.92 * k + 26;
    }
    g.putImageData(d, 0, 0);
  } catch (e) { return null; }
  return c;
}
function naTileAt(c, r, wf) {
  const inMap = r >= 0 && r < MAP_H && c >= 0 && c < MAP_W, code = inMap ? MAP[r][c] : 'X';
  const k = kindAt(c, r), cls = GROUND[k] || k;
  const same = (dc, dr) => {
    const nc = c + dc, nr = r + dr, out = nr < 0 || nr >= MAP_H || nc < 0 || nc >= MAP_W, nk = kindAt(nc, nr), ncls = GROUND[nk] || nk;
    if (cls === 'water') return ncls === 'water';
    if (out) return true;
    return cls === 'path' || cls === 'stone' ? ncls === 'path' || ncls === 'stone' : ncls === cls;
  };
  const n = same(0, -1), s = same(0, 1), w = same(-1, 0), e = same(1, 0);
  const h = (Math.imul(c + 101, 374761393) ^ Math.imul(r + 57, 668265263)) >>> 0;
  const key = 'na' + cls + code + +n + +s + +w + +e + (h % 60) + '_' + (cls === 'water' ? wf : 0);
  if (TILE[key]) return TILE[key];
  const t = cnv(16, 16), g = t.getContext('2d'), F = IMG.floor, Wt = IMG.water;
  const at = (im, col, row) => g.drawImage(im, col * 16, row * 16, 16, 16, 0, 0, 16, 16);
  const [ac, ar] = autoCell(n, s, w, e);
  if (cls === 'water') {
    at(Wt, ac, 6 + ar);
    if (n && s && w && e) { const sr = RNG(h % 9973 + 11); for (let i = 0; i < 2; i++) { const y = 2 + ((sr() * 12) | 0), x = (((sr() * 12) | 0) + wf * 3) % 13; R(g, x, y, 3, 1, 'rgba(255,255,255,0.5)'); } }
    if (code === '#') at(Wt, 1, 13);
  } else if (cls === 'path' || (cls === 'stone' && !STONE)) {
    if (ac === 1 && ar === 1 && h % 11 === 0) at(F, h % 2, 11); else at(F, ac, 7 + ar);
  } else if (cls === 'stone') {
    g.drawImage(STONE, ac * 16, ar * 16, 16, 16, 0, 0, 16, 16);
  } else {
    at(F, h % 10 < 6 ? 0 : 1 + (h % 4), 12);
    if (code === "'") for (const [fx, fy, col] of [[3 + h % 7, 4, '#FFF3D6'], [10, 9 + h % 4, '#F07858']]) { P(g, fx, fy, col); P(g, fx - 1, fy, col); P(g, fx + 1, fy, col); P(g, fx, fy - 1, col); P(g, fx, fy + 1, col); P(g, fx, fy, '#F2C440'); }
    if (code === ';') { P(g, 4 + h % 6, 11, '#8C8C84'); P(g, 5 + h % 6, 11, '#B4B2A8'); P(g, 11, 5 + h % 5, '#8C8C84'); }
    if (cls === 'dark') R(g, 0, 0, 16, 16, 'rgba(14,20,10,0.72)');
  }
  TILE[key] = t; return t;
}
function tileAt(c,r,wf){return worldArt.tile(c,r,wf,kindAt);}
// 整张地图预先画好三帧（水面流动），路和草地交界处补一圈草边
let MAPBG = null, MAPART = null;
function buildMap() {
  if (IMG.floor && !STONE) STONE = stoneAtlas();
  MAPBG = [0, 1, 2].map((f) => {
  const c = cnv(MAP_W * 16, MAP_H * 16), g = c.getContext('2d');
  for (let r = 0; r < MAP_H; r++) for (let col = 0; col < MAP_W; col++) g.drawImage(tileAt(col, r, f), col * 16, r * 16);
  const rnd = RNG(99);
  if (!IMG.floor) for (let r = 0; r < MAP_H; r++) for (let col = 0; col < MAP_W; col++) {
    const k = kindAt(col, r); if (k !== 'dirt' && k !== 'camp' && k !== 'stone') continue;
    const x0 = col * 16, y0 = r * 16;
    for (const [dc, dr] of [[0, -1], [0, 1], [-1, 0], [1, 0]]) {
      const nk = kindAt(col + dc, r + dr);
      if (nk === 'grass') {
        for (let i = 0; i < 16; i++) {
          const depth = 1 + (rnd() < 0.45 ? 1 : 0) + (rnd() < 0.15 ? 1 : 0);
          for (let d = 0; d < depth; d++) {
            const x = dc === 0 ? x0 + i : dc < 0 ? x0 + d : x0 + 15 - d, y = dr === 0 ? y0 + i : dr < 0 ? y0 + d : y0 + 15 - d;
            P(g, x, y, d === depth - 1 ? '#42593A' : (i + d) % 3 ? '#4E6A3C' : '#5B7A45');
          }
        }
      } else if (k === 'dirt' && nk === 'camp') {
        for (let i = 0; i < 16; i += 2) { const x = dc === 0 ? x0 + i + (r % 2) : dc < 0 ? x0 : x0 + 15, y = dr === 0 ? y0 + i : dr < 0 ? y0 : y0 + 15; P(g, x, y, '#6C5843'); }
      }
    }
  }
  // 物件的落地阴影（静态，画进底图）
  for (const [k, x, y] of PROPS) {
    const sz = SIZE[k]; if (!sz || k === 'reed' || k === 'boat' || k === 'lantern') continue;
    const w = sz[0]; fe(g, x + (w >> 1), y + sz[1] - 2, Math.round(w * 0.34), w >= 32 ? 3 : 2, 'rgba(10,8,20,0.2)');
  }
  return c;
});
  MAPART=cnv(MAP_W*16,MAP_H*16);const overview=MAPART.getContext('2d');overview.drawImage(MAPBG[0],0,0);
  for(const [k,x,y]of PROPS){const [dx,dy]=propXY(k,x,y);drawArt(overview,OBJ[k],dx,dy);}
}
const W3 = (x, y) => ({ x: x * U, y: y * U });
const NPCS = [
  { id: 'shen', name: '沈青', ...W3(62, 152) },
  { id: 'xu', name: '许舟', ...W3(160, 30) },
  { id: 'lu', name: '陆平', ...W3(120, 134) },
  { id: 'zhou', name: '周砚', ...W3(196, 226) },
];
const INSPECT = [
  { id: 'board', name: '渡口告示', obj: 'board', ...W3(189, 74) },
  { id: 'cart', name: '翻倒的货车', obj: 'cart', ...W3(313, 180) },
  { id: 'sign', name: '路标', obj: 'sign', ...W3(253, 154) },
];
const CRATE = W3(216, 212);
const FINAL_POS=W3(152,337), LEDGER_POS=W3(959,120), CACHE_POS=W3(538,329);
const HERBS = [W3(490, 53), W3(513, 257)];
const ZONE = W3(420, 117);
const RESPAWN = W3(84, 160);
const KIND = {
  bandit: { name: '匪徒', hp: 45, r: 17, speed: 95, aggro: 210, leash: 330, flinch: true,
    atks: [{ id: 'slash', shape: 'cone', range: 74, half: 0.9, tele: 0.7, dmg: 9, rec: 0.55, inter: true, reach: 58 }] },
  boss: { name: '匪首', hp: 240, r: 30, speed: 86, aggro: 9999, leash: 560, flinch: false,
    atks: {
      heavy: { id: 'heavy', shape: 'cone', range: 150, half: 0.65, tele: 1.5, dmg: 28, rec: 0.6, inter: true, reach: 118 },
      sweep: { id: 'sweep', shape: 'circle', range: 78, tele: 0.6, dmg: 12, rec: 0.5, inter: false, reach: 64 },
      quick: { id: 'quick', shape: 'circle', range: 78, tele: 0.45, dmg: 10, rec: 0.6, inter: false, reach: 999 },
      charge: { id: 'charge', shape: 'line', range: 240, width: 22, tele: 1.0, dmg: 20, rec: 0.8, inter: false, reach: 260, minD: 150 },
    } },
};
KIND.archer={name:'弓手',hp:60,r:17,speed:90,aggro:340,leash:460,flinch:true};
KIND.guard={...KIND.bandit,name:'护院',hp:90,aggro:360,leash:700,atks:[{id:'slash',shape:'cone',range:90,half:.8,tele:.85,dmg:14,rec:.7,inter:true,reach:70}]};
KIND.captain={...KIND.guard,name:'护院头领',hp:180,flinch:false,atks:[{id:'heavy',shape:'cone',range:140,half:1,tele:1.3,dmg:24,rec:.85,inter:true,reach:105}]};
WEAPON.guard=WEAPON.bandit; WEAPON.captain=WEAPON.boss;
const P_ = { speed: 210, atkCd: 0.27, skCd: 0.9, skCost: 30, dgCd: 0.5, mpRegen: 6, combo: [{ dmg: 20, range: 112, half: 1.15 }, { dmg: 24, range: 112, half: 1.15 }, { dmg: 34, range: 136, half: 1.6, big: true }], skDmg: 26, qiBack: 18, bandageHeal: 0.4 };

function mkEnemy(kind, x, y) {
  const K = KIND[kind];
  return { id:uid(), kind, x, y, hx: x, hy: y, hp: K.hp, maxHp: K.hp, face: Math.PI, state: 'idle', t: 0, atk: null, plan: null, cnt: 0, hostile: kind !== 'boss', alive: true, flash: 0, defeated: false, an: 0, moving: false, dieT: 0, spar: false, strafeDir: 1, dashHit: false };
}
function newGame() {
  const state = {
    v: 4, chapter: Chapter.create(), arrows: [], swings: [], qi: [], combatSerial: 0, manualPaused: false, ally: null, started: false, time: 0, deadT: 0, respawned: true, done: false, logOpen: false, dlg: null, echo: '', hitstop: 0, shake: 0,
    p: { x: RESPAWN.x + 30, y: RESPAWN.y + 12, face: 0, hp: 100, maxHp: 100, mp: 100, maxMp: 100, sp: 100, atkCd: 0, skCd: 0, dgCd: 0, dodge: 0, inv: 0, dvx: 0, dvy: 0, swing: 0, swingDur: 0.15, swingKind: '', hurt: 0, trail: [], an: 0, moving: false, combo: 0, comboT: 0 },
    inv: { coin: 30, bandage: 2, wood: 0, iron: 0, herb: 0, med: false },
    orn: null,
    f: { accepted: false, matPicked: false, asked: false, branch: null, bought: false, delivered: false, told: null, fought: false, lostBoss: false, heardDebt: false, bossClaim: false, askedLu: false, zhouBuys: 0, herbs: [false, false], defeats: 0, bandagesUsed: 0, sparWins: 0, inspected: {} },
    mem: { shen: { k: [], att: 0 }, xu: { k: [], att: 0 }, lu: { k: [], att: 0 }, zhou: { k: [], att: 0 }, boss: { k: [], att: 0 } },
    stats: { interrupts: 0, practice: 0, evades: 0, qiBack: 0, hitsTaken: 0, crafts: [], branchAt: null, deliveredAt: null, chat: {} },
    dummy: { state: 'idle', t: 0, face: 0, hit: 0, atk: { shape: 'cone', range: 96, half: 0.7, tele: 1.5, inter: true } },
    tips: {}, receipts: {}, ui: { perf: false },
    enemies: [mkEnemy('bandit', 1230, 300), mkEnemy('bandit', 1310, 420), mkEnemy('boss', 2769, 450), mkEnemy('archer',1515,312),mkEnemy('bandit',1965,555),mkEnemy('archer',2115,570)],
    log: [], toasts: [], fx: [],
  };
  Playtest.ensure(state,{fresh:true,debug:DEBUG});return state;
}
let G = newGame();

// ================================================================ 存档：每个改动物品 / 剧情的动作都是一次提交，带操作号，重复提交只回原回执
const SAVE_KEY = 'qingshi-chapter-v04';
let SAVED_FLASH = 0;
function snapshotState(source=G) { const s=JSON.parse(JSON.stringify(source)); settlePendingSkills(s); s.fx=[]; s.swings=[]; s.qi=[]; s.manualPaused=false; s.toasts=[]; s.arrows=[]; s.dlg=null; s.logOpen=false; s.hitstop=0; s.shake=0; s.done=false; return s; }
function persist(state) { localStorage.setItem(SAVE_KEY,JSON.stringify({v:4,at:Date.now(),G:snapshotState(state)})); }
function saveNow(flash) {
  try { persist(G); if(flash) SAVED_FLASH=1.4; return true; }
  catch(e) { showSaveError('存档失败。进度尚未写入；请保留页面并检查浏览器存储。'); return false; }
}
function showSaveError(msg) { $('saveError').hidden=false; $('saveError').textContent=msg; }
function loadSave() { try { const s=JSON.parse(localStorage.getItem(SAVE_KEY)||'null'); if(s && s.v===4 && s.G?.v===4 && Array.isArray(s.G.chapter?.skills) && s.G.enemies?.length>=3 && s.G.inv && s.G.receipts) return s; } catch(e) { showSaveError('无法读取本章存档；原存档保留。可以尝试刷新页面。'); } return null; }
function clearSave() { try { localStorage.removeItem(SAVE_KEY); return true; } catch(e) {showSaveError('无法清除存档，请检查浏览器存储');return false;} }
const lg=(d,text)=>{if(!d.log.includes(text))d.log.push(text);};
const know=(d,who,fact)=>{const m=d.mem[who];if(!m.k.includes(fact))m.k.push(fact);};
function commit(opId,label,fn) {
  const result=Chapter.transact(G,opId,d=>{const before={...d.inv};const r=fn(d)||{ok:true};if(r.ok){d.receipts[opId]={what:label};Playtest.transaction(d,label,before,d.inv);}return r;},persist);
  if(!result.ok){if(result.msg){toast(result.msg);if(result.msg.includes('存档'))showSaveError(result.msg);}return result;}
  if(!result.dup){SAVED_FLASH=1.4;$('saveError').hidden=true;}return result;
}

// ---------------------------------------------------------------- 小工具
function toast(text) { G.toasts.push({ text, t: 2.6 }); if (G.toasts.length > 2) G.toasts.shift(); }
function tip(id, text) { if (G.tips[id]) return; G.tips[id] = true; toast(text); }
function fxText(x, y, text, color, pix) { G.fx.push({ type: 'text', x, y, text, color, pix: !!pix, t: 0, dur: 0.9 }); }
function burst(x, y, n, cols, spd, up) {
  for (let i = 0; i < n; i++) { const a = Math.random() * Math.PI * 2, s = spd * (0.4 + Math.random() * 0.8); G.fx.push({ type: 'pt', x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - (up || 0), col: cols[i % cols.length], t: 0, dur: 0.3 + Math.random() * 0.25 }); }
}
function collide(o, r) {
  o.x = clamp(o.x, r, WORLD.w - r); o.y = clamp(o.y, r + 24, WORLD.h - r);
  for (const b of OBST) {
    const nx = clamp(o.x, b.x, b.x + b.w), ny = clamp(o.y, b.y, b.y + b.h);
    const dx = o.x - nx, dy = o.y - ny, d2 = dx * dx + dy * dy;
    if (d2 >= r * r) continue;
    if (d2 > 0.0001) { const d = Math.sqrt(d2); o.x = nx + (dx / d) * r; o.y = ny + (dy / d) * r; }
    else {
      const l = o.x - b.x, rr = b.x + b.w - o.x, t = o.y - b.y, bt = b.y + b.h - o.y, m = Math.min(l, rr, t, bt);
      if (m === l) o.x = b.x - r; else if (m === rr) o.x = b.x + b.w + r; else if (m === t) o.y = b.y - r; else o.y = b.y + b.h + r;
    }
  }
}
function move(o, dx, dy, r) { o.x += dx; o.y += dy; collide(o, r); }
function activeFoe(e) { return e.alive && e.hostile && e.state !== 'down' && e.state !== 'dying'; }
function inCombat() {
  const p = G.p;
  return G.enemies.some((e) => activeFoe(e) && ['chase', 'windup', 'recover', 'stagger', 'strafe', 'dash', 'flinch'].includes(e.state) && Math.hypot(e.x - p.x, e.y - p.y) < 460);
}
const paused = () => !!(G.manualPaused || G.dlg || G.done || G.logOpen || !$('atlas').hidden || document.hidden);

// ---------------------------------------------------------------- 玩家动作
function aim(maxAng) {
  const p = G.p; let best = null, bd = 170;
  const cands = G.enemies.filter(activeFoe).map((e) => [e.x, e.y]);
  if (Math.hypot(DUMMY_POS.x - p.x, DUMMY_POS.y - p.y) < 170) cands.push([DUMMY_POS.x, DUMMY_POS.y]);
  for (const [x, y] of cands) { const d = Math.hypot(x - p.x, y - p.y), a = Math.atan2(y - p.y, x - p.x); if (d < bd && angDiff(a, p.face) <= maxAng) { bd = d; best = a; } }
  if (best !== null) p.face = best;
}
function canAct() { return G.started && !paused() && G.deadT <= 0; }
function inArc(x, y, r, range, half, p = G.p) { const d = Math.hypot(x - p.x, y - p.y); if (d > range + r) return false; return d <= r || angDiff(Math.atan2(y - p.y, x - p.x), p.face) <= half; }
function damageFoe(e, dmg, isSkill, big, face, skillId) {
  const K=KIND[e.kind], p=G.p;
  const bonus=!isSkill&&G.orn==='破势'&&e.state==='stagger'&&e.opening?8:0;
  if(bonus){e.opening=false;trackCombat('counters');fxText(e.x,e.y-100,'破势追击 +8','#F2D27A');}
  e.hp-=dmg+bonus;e.flash=.12;e.sfHeavy=!!(big||isSkill);
  fxText(e.x,e.y-66,'-'+(dmg+bonus),big||isSkill?'#F2D27A':'#EFE6D2',true);
  G.fx.push({type:'songfengSpark',x:e.x,y:e.y-15,face,heavy:!!(big||isSkill),t:0,dur:.22});
  const d=Math.hypot(e.x-p.x,e.y-p.y)||1,kb=big?26:isSkill?16:8;
  if(K.flinch||e.state==='idle')move(e,(e.x-p.x)/d*kb,(e.y-p.y)/d*kb,K.r);
  if(e.state==='idle')e.state='chase';
  if(isSkill&&(G.orn==='破势'||skillId==='break')&&e.state==='windup'&&e.atk.inter){
    e.state='stagger';e.opening=G.orn==='破势';e.t=G.orn==='破势'?-.8:0;G.stats.interrupts++;trackCombat('interrupts');
    fxText(e.x,e.y-98,'打断！','#F08A6A');toast((G.orn==='破势'?'破势打断！接普攻可追击 +8：':'截流剑打断：')+K.name);
    SFX.interrupt();
  }else if(K.flinch&&e.state!=='windup'&&e.state!=='dash'){e.state='flinch';e.t=0;}
  if(e.hp<=0)kill(e);
  const current=G.enemies.find(x=>x.id===e.id);
  impact(skillId==='qi'?'qi':big||isSkill?'heavy':'light',face,current?.hp<=0);
}
function countSkillHit(action){
  if(!action.skill||action.counted||[...G.swings,...G.qi].some(s=>s.id===action.id&&s.counted))return;action.counted=true;trackCombat('hits',1,G,action.orn);
  for(const s of [...G.swings,...G.qi])if(s.id===action.id)s.counted=true;
}
function settlePendingSkills(state){
  const actions=[...state.swings,...state.qi],seen=new Set();
  for(const action of actions){
    if(!action.skill||seen.has(action.id))continue;seen.add(action.id);
    if(!actions.some(s=>s.id===action.id&&s.counted))trackCombat('misses',1,state,action.orn);
  }
}
function cancelSwings(){
  for(const s of G.swings)if(s.skill&&!s.counted&&!(s.skill==='qi'&&s.launched))trackCombat('misses',1,G,s.orn);
  G.swings=[];G.p.swing=0;
}
function returnQi(attack) {
  if(!attack.skill||attack.qiReturned||(attack.orn||G.orn)!=='回气'||[...G.swings,...G.qi].some(s=>s.id===attack.id&&s.qiReturned))return;
  attack.qiReturned=true;
  for(const current of [...G.swings,...G.qi])if(current.id===attack.id)current.qiReturned=true;
  const gain=Math.min(P_.qiBack,G.p.maxMp-G.p.mp);G.p.mp+=gain;G.stats.qiBack+=Math.round(gain);trackCombat('qiReturned',gain,G,attack.orn);
  if(gain>0)fxText(G.p.x,G.p.y-76,'回气 +'+Math.round(gain),'#7FD0BE');
}
function strikeEnemies(strike) {
  const origin={x:strike.x,y:strike.y,face:strike.face+(strike.skill==='sweep'?skillHead(strike.age/strike.duration)*Math.PI*2-.7:0)};let n=0;
  const hits=()=>G.swings.find(s=>s.id===strike.id)?.hitIDs||strike.hitIDs;
  for(const old of G.enemies.slice()){
    const e=G.enemies.find(x=>x.id===old.id);if(!activeFoe(e)||hits().includes(e.id))continue;
    if(!inArc(e.x,e.y,KIND[e.kind].r,strike.range,strike.skill==='sweep'?.72:strike.half,origin))continue;
    hits().push(e.id);n++;countSkillHit(strike);damageFoe(e,strike.damage,!!strike.skill,strike.combo===3,origin.face,strike.skill);
  }
  const dd=G.dummy,dm=DUMMY_POS;
  if(!hits().includes('dummy')&&inArc(dm.x,dm.y,14,strike.range,strike.skill==='sweep'?.72:strike.half,origin)){
    hits().push('dummy');n++;dd.hit=.15;
    G.fx.push({type:'songfengSpark',x:dm.x,y:dm.y-15,face:strike.face,heavy:!!strike.skill||strike.combo===3,t:0,dur:.22});
    if(strike.skill&&(G.orn==='破势'||strike.skill==='break')&&dd.state==='windup'){
      dd.state='stagger';dd.opening=G.orn==='破势';dd.t=G.orn==='破势'?-.8:0;G.stats.practice++;trackCombat('interrupts');
      fxText(dm.x,dm.y-90,'打断！','#F08A6A');SFX.interrupt();toast('打断了木人桩（练习）');
    }else if(!strike.skill&&G.orn==='破势'&&dd.state==='stagger'&&dd.opening){dd.opening=false;trackCombat('counters');fxText(dm.x,dm.y-90,'破势追击 +8（练习）','#F2D27A');}
    impact(strike.combo===3||strike.skill?'heavy':'light',strike.face);
  }
  if(n>0){returnQi(strike);countSkillHit(strike);}
  return n;
}
function attack() {
  const p=G.p;if(!canAct()||p.atkCd>0||p.dodge>.06)return;
  p.combo=p.comboT>0?(p.combo+1)%3:0;const c=P_.combo[p.combo];
  p.atkCd=c.big?.39:P_.atkCd;p.comboT=.8;aim(Math.PI);
  p.swing=p.swingDur=c.big?.35:.24;p.swingKind=c.big?'atk3':'atk';
  G.combatSerial++;G.swings.push({id:uid(),x:p.x,y:p.y,face:p.face,combo:p.combo+1,age:0,life:p.swingDur,duration:p.swingDur,damage:c.dmg,range:c.range,half:c.half,hitIDs:[]});
  startActionBattle(c.range);(c.big?SFX.swing3:SFX.swing)();
}
function skill(slot=0) {
  const p=G.p,c=G.chapter,id=c.skills[slot],s=Chapter.SKILLS[id];
  if(!canAct()||c.cooldowns[slot]>0||p.dodge>.06)return;
  if(p.mp<s.cost){trackCombat('noMp');toast('内力不足，先用普攻周旋；战斗中自然回气较慢');return;}
  startActionBattle(s.range+s.dash);trackCombat('casts');p.mp-=s.cost;c.cooldowns[slot]=s.cd;p.skCd=s.cd;p.activeSkill=id;
  aim(id==='sweep'?Math.PI:1.7);
  for(let n=0;n<Math.ceil(s.dash/8);n++)move(p,Math.cos(p.face)*Math.min(8,s.dash-n*8),Math.sin(p.face)*Math.min(8,s.dash-n*8),16);
  p.swing=p.swingDur=(id==='sweep'||id==='break')?.35:.24;p.swingKind='sk';p.comboT=0;G.combatSerial++;SFX.skill();
  G.swings.push({id:uid(),x:p.x,y:p.y,face:p.face,combo:(id==='sweep'||id==='break')?3:id==='thrust'?1:2,visualCombo:(id==='sweep'||id==='break')?3:id==='thrust'?1:2,age:0,life:p.swingDur,duration:p.swingDur,
    damage:s.dmg,range:s.range,half:s.half,skill:id,orn:G.orn||'基础剑',hitIDs:[],launched:false});
}
function updateStrikes(dt) {
  for(const before of G.swings.slice()){
    const swing=G.swings.find(s=>s.id===before.id);if(!swing)continue;
    const previousAge=swing.age;swing.age+=dt;swing.life-=dt;
    if(swing.skill==='qi'){
      if(!swing.launched&&swing.age>=.055){swing.launched=true;G.qi.push({id:swing.id,x:swing.x+Math.cos(swing.face)*20,y:swing.y+Math.sin(swing.face)*20,
        vx:Math.cos(swing.face)*590,vy:Math.sin(swing.face)*590,face:swing.face,life:.8,damage:swing.damage,skill:'qi',orn:swing.orn,hitIDs:[]});}
    }else if(swing.skill==='sweep'){
      const from=Math.max(previousAge,.055),to=Math.min(swing.age,swing.duration*.95);
      if(from<=to){const steps=Math.max(1,Math.ceil((to-from)/.008));for(let i=0;i<=steps;i++)strikeEnemies({...swing,age:from+(to-from)*i/steps});}
    }else if(swing.age>=(swing.skill==='break'?.095:.055)&&swing.age<=.19)strikeEnemies(swing);
  }
  G.swings=G.swings.filter(s=>{if(s.life>0)return true;if(s.skill&&s.skill!=='qi'&&!s.counted)trackCombat('misses',1,G,s.orn);return false;});
  for(const old of G.qi.slice()){
    let shot=G.qi.find(s=>s.id===old.id);if(!shot)continue;shot.life-=dt;
    const x=shot.x,y=shot.y;shot.x+=shot.vx*dt;shot.y+=shot.vy*dt;
    if(!clearShot(x,y,shot.x,shot.y)||covered(shot.x,shot.y)){shot.life=0;continue;}
    for(const before of G.enemies.slice()){
      const e=G.enemies.find(s=>s.id===before.id);shot=G.qi.find(s=>s.id===old.id)||shot;
      if(!activeFoe(e)||shot.hitIDs.includes(e.id)||Math.hypot(e.x-shot.x,e.y-shot.y)>42)continue;
      shot.hitIDs.push(e.id);countSkillHit(shot);damageFoe(e,shot.damage,true,true,shot.face,'qi');returnQi(G.qi.find(s=>s.id===old.id)||shot);
    }
    shot=G.qi.find(s=>s.id===old.id)||shot;
    if(!shot.hitIDs.includes('dummy')&&Math.hypot(shot.x-DUMMY_POS.x,shot.y-DUMMY_POS.y)<42){
      shot.hitIDs.push('dummy');countSkillHit(shot);G.dummy.hit=.15;G.fx.push({type:'songfengSpark',x:DUMMY_POS.x,y:DUMMY_POS.y-15,face:shot.face,heavy:true,t:0,dur:.22});impact('qi',shot.face);returnQi(shot);
    }
  }
  G.qi=G.qi.filter(s=>{if(s.life>0&&s.x>0&&s.x<WORLD.w&&s.y>0&&s.y<WORLD.h)return true;if(!s.counted)trackCombat('misses',1,G,s.orn);return false;});
}
function dodge() {
  const p = G.p; if (!canAct() || p.dgCd > 0 || p.dodge > 0 || p.sp < 30) return;
  let dx = p.ix || 0, dy = p.iy || 0; const l = Math.hypot(dx, dy);
  if (l < 0.2) { dx = Math.cos(p.face); dy = Math.sin(p.face); } else { dx /= l; dy /= l; }
  cancelSwings();p.sp -= 30; p.dodge = 0.23; p.inv = 0.3; p.dgCd = P_.dgCd; p.dvx = dx * 650; p.dvy = dy * 650; p.trail = [];
  burst(p.x, p.y, 5, ['#9B8263', '#B3A58C'], 60, 10); SFX.dodge();
}
function useBandage() {
  const p = G.p; if (!canAct()) return;
  if (inCombat()) { toast('打斗中腾不出手包扎，先脱身'); SFX.ui(); return; }
  if (p.hp >= p.maxHp) { toast('没有受伤，不用包扎'); return; }
  if (G.inv.bandage <= 0) { toast('没有绷带了，回青石渡找沈青'); return; }
  const r = commit('bandage:' + uid(), '用绷带', (d) => {
    if (d.inv.bandage <= 0) return { ok: false, msg: '没有绷带了' };
    d.inv.bandage--; d.f.bandagesUsed++; d.p.hp = Math.min(d.p.maxHp, d.p.hp + Math.round(d.p.maxHp * P_.bandageHeal));
  });
  if (r.ok) { fxText(p.x, p.y - 76, '+' + Math.round(G.p.maxHp * P_.bandageHeal), '#F08A6A', true); toast('用了一条绷带'); SFX.heal(); }
}
function hurtPlayer(dmg, fx, fy) {
  const p = G.p;
  p.hp -= dmg; p.hurt = 0.25; G.stats.hitsTaken++;
  fxText(p.x, p.y - 76, '-' + dmg, '#F08A6A', true);
  burst(p.x, p.y - 30, 6, ['#F08A6A', '#FFFFFF'], 120, 40);
  const d = Math.hypot(p.x - fx, p.y - fy) || 1;
  move(p, ((p.x - fx) / d) * 26, ((p.y - fy) / d) * 26, 16);
  impact('hurt',Math.atan2(p.y-fy,p.x-fx));
  if (p.hp <= 0) {
    const sp = G.enemies.find((e) => e.spar && e.hostile);
    if (sp) { p.hp = 1; endSpar(sp, false); return; }
    p.hp = 0; die();
  }
}
function die() { G.deadT = 1.6; G.respawned = false; G.f.defeats++; toast('你败退了……'); SFX.down(); }
function respawn() {
  settlePendingSkills(G);G.swings=[];G.qi=[];combatArt.reset();
  const p = G.p;
  Object.assign(p, { x: RESPAWN.x, y: RESPAWN.y, hp: p.maxHp, mp: p.maxMp, sp: 100, dodge: 0, inv: 0, swing: 0, hurt: 0, trail: [], combo: 0, comboT: 0 });
  for (const e of G.enemies) {
    if(e.kind!=='boss' && e.hp<=0){e.alive=false;continue;}
    if (!e.alive) continue;
    const K = KIND[e.kind];
    if (e.kind === 'boss') {
      if (e.defeated && !e.spar) continue;
      if (e.hostile && !e.spar) { G.f.lostBoss = true; if (!G.mem.boss.k.includes('beat_player')) G.mem.boss.k.push('beat_player'); if (!G.log.includes('你在匪营败给了匪首，退回青石渡')) G.log.push('你在匪营败给了匪首，退回青石渡'); }
      e.hostile = false; e.spar = false;
    }
    Object.assign(e, { x: e.hx, y: e.hy, hp: K.hp, maxHp: K.hp, state: 'idle', t: 0, atk: null, plan: null, flash: 0 });
  }
  toast('你回到青石渡，伤已经养好；用掉的绷带回不来');
  saveNow(false);
}
function kill(e) {
  if(e.kind==='boss' && e.spar){endSpar(e,true);return;}
  if(e.kind!=='boss'){
    const r=commit('defeat:'+e.id,'击退'+KIND[e.kind].name,d=>{const foe=d.enemies.find(x=>x.id===e.id);foe.hp=0;foe.state='dying';foe.dieT=.6;foe.hostile=false;if(foe.final)d.chapter.kills++;});
    if(!r.ok){e.hp=1;return;}
    fxText(e.x,e.y-50,KIND[e.kind].name+'退走','#C9BFAE');SFX.down();return;
  }
  const r=commit('bossA','武力夺回药包',d=>{
    if(d.f.branch)return {ok:false,msg:'药包已经取回'};
    Object.assign(d.enemies[2],{hp:0,state:'down',hostile:false,defeated:true});
    d.inv.med=true;d.f.branch='A';d.stats.branchAt=Math.round(G.time);know(d,'boss','route_A');d.mem.boss.att-=1;lg(d,'你击退匪首，夺回药包；他承认你剑快，却不再信任你');
  });
  if(!r.ok){e.hp=1;return;}
  G.hitstop=Math.max(G.hitstop,.08);toast('药包到手。匪首退开，指着旧账箱：有胆也看看那本账');SFX.down();
}
function endSpar(e,win) {
  const n=G.f.sparWins+1;
  const r=commit(win?'spar:'+n:'spar-loss:'+uid(),win?'切磋胜利':'切磋点到为止',d=>{
    const boss=d.enemies[2];Object.assign(boss,{hostile:false,spar:false,state:'idle',hp:KIND.boss.hp,x:boss.hx,y:boss.hy,plan:null});
    if(win){d.f.sparWins=n;if(n<=2){d.inv.wood+=2;d.inv.iron+=1;lg(d,'第 '+n+' 次切磋赢了匪首，得一份修械料');}else lg(d,'又赢了匪首一场切磋');d.mem.boss.att++;}
    else d.p.hp=Math.max(1,d.p.hp);
  });
  if(!r.ok){e.hp=Math.max(1,e.hp);return;}
  toast(win?(n<=2?'切磋赢了！匪首给了一份修械料':'切磋赢了！（之后没有物质奖励）'):'点到为止。匪首收了刀：「再来？」');if(win)(n<=2?SFX.pickup:SFX.coin)();
}

// ---------------------------------------------------------------- 敌人
function pickAtk(e, d) {
  const K = KIND[e.kind];
  if (e.kind !== 'boss') return K.atks[0];
  e.cnt++;
  if (d > 150 && e.cnt % 3 !== 1) return K.atks.charge;
  return e.cnt % 2 ? K.atks.heavy : K.atks.sweep;
}
function bossLow(e) { return e.kind === 'boss' && e.hp < KIND.boss.hp * 0.5; }
function updEnemy(e, dt) {
  if(e.kind==='archer'){updArcher(e,dt);return;}
  e.moving = false;
  if (!e.alive || e.state === 'down') return;
  if (e.state === 'dying') { e.dieT -= dt; if (e.dieT <= 0) e.alive = false; return; }
  const K = KIND[e.kind], p = G.p;
  e.flash = Math.max(0, e.flash - dt);
  const dx = p.x - e.x, dy = p.y - e.y, d = Math.hypot(dx, dy) || 1;
  const homeD = Math.hypot(p.x - e.hx, p.y - e.hy);
  const busyMate = e.kind === 'bandit' && G.enemies.some((o) => o !== e && o.kind === 'bandit' && activeFoe(o) && (o.state === 'windup' || o.state === 'recover'));
  switch (e.state) {
    case 'idle':
      if (e.hostile && d < K.aggro && homeD < K.leash) e.state = 'chase';
      else if (!e.hostile && d < 220) e.face = Math.atan2(dy, dx);
      break;
    case 'chase': {
      if (!e.hostile || (!e.spar && homeD > K.leash + 40)) { e.state = 'return'; break; }
      e.face = Math.atan2(dy, dx);
      if (!e.plan) e.plan = pickAtk(e, d);
      const a = e.plan;
      if (a.minD && d < a.minD * 0.7) { e.plan = pickAtk(e, d); if (e.plan.minD) e.plan = K.atks.heavy; break; }
      if (busyMate && d < 120) { e.state = 'strafe'; e.t = 0; e.strafeDir = Math.random() < 0.5 ? 1 : -1; break; }
      if (d <= a.reach && (!a.minD || d >= a.minD * 0.7)) {
        e.state = 'windup'; e.t = 0; e.atk = a; e.plan = null; e.dashHit = false;
        if (a.tele >= 1) SFX.tele(); else SFX.teleS();
        if (Math.hypot(e.x - p.x, e.y - p.y) < 320) tip('tele', '红色范围就是要挨打的地方，看到就闪避（空格 / 闪避键）');
      } else { move(e, (dx / d) * K.speed * dt, (dy / d) * K.speed * dt, K.r); e.moving = true; }
      break;
    }
    case 'strafe': {
      e.t += dt; e.face = Math.atan2(dy, dx);
      const tx = -dy / d * e.strafeDir, ty = dx / d * e.strafeDir, back = d < 90 ? -0.6 : d > 130 ? 0.6 : 0;
      move(e, (tx + (dx / d) * back) * K.speed * 0.8 * dt, (ty + (dy / d) * back) * K.speed * 0.8 * dt, K.r); e.moving = true;
      if (e.t > (e.kind === 'boss' ? 0.7 : 0.9) && !(busyMate && d < 120)) { e.state = 'chase'; }
      break;
    }
    case 'windup':
      e.t += dt;
      if (e.t >= e.atk.tele) {
        if (e.atk.shape === 'line') { e.state = 'dash'; e.t = 0; G.fx.push({ type: 'zone', x: e.x, y: e.y, face: e.face, shape: 'line', range: e.atk.range, width: e.atk.width, t: 0, dur: 0.25 }); }
        else { enemyStrike(e); e.state = 'recover'; e.t = 0; }
      }
      break;
    case 'dash': {
      e.t += dt; const sp = e.atk.range / 0.25;
      move(e, Math.cos(e.face) * sp * dt, Math.sin(e.face) * sp * dt, K.r); burst(e.x, e.y, 1, ['#9B8263'], 40, 5);
      if (!e.dashHit && Math.hypot(p.x - e.x, p.y - e.y) < K.r + 22) { e.dashHit = true; if (p.inv > 0) { fxText(p.x, p.y - 76, '闪过', '#7FD0BE'); G.stats.evades++; SFX.evade(); } else hurtPlayer(e.atk.dmg, e.x - Math.cos(e.face) * 10, e.y - Math.sin(e.face) * 10); }
      if (e.t >= 0.25) { e.state = 'recover'; e.t = 0; G.shake = Math.max(G.shake, 2); }
      break;
    }
    case 'recover':
      e.t += dt;
      if (e.t >= e.atk.rec) {
        if (bossLow(e) && e.atk.id === 'heavy' && Math.random() < 0.6) { e.state = 'windup'; e.t = 0; e.atk = K.atks.quick; SFX.teleS(); break; }
        if (e.kind === 'boss' && Math.random() < 0.35) { e.state = 'strafe'; e.t = 0; e.strafeDir = Math.random() < 0.5 ? 1 : -1; break; }
        e.state = 'chase';
      }
      break;
    case 'stagger':
      e.t += dt;
      if (e.t >= 0.9) e.state = 'chase';
      break;
    case 'flinch':
      e.t += dt;
      if (e.t >= 0.18) e.state = 'chase';
      break;
    case 'return': {
      const hx = e.hx - e.x, hy = e.hy - e.y, hd = Math.hypot(hx, hy);
      if (hd < 6) { e.state = 'idle'; e.hp = K.hp; e.x = e.hx; e.y = e.hy; }
      else { move(e, (hx / hd) * K.speed * 1.4 * dt, (hy / hd) * K.speed * 1.4 * dt, K.r); e.face = Math.atan2(hy, hx); e.moving = true; }
      if (e.hostile && d < K.aggro && homeD < K.leash - 60) e.state = 'chase';
      break;
    }
  }
  if (e.moving) e.an += dt;
}
function inZone(a, ex, ey, face, px, py, pr) {
  const dx = px - ex, dy = py - ey, d = Math.hypot(dx, dy);
  if (a.shape === 'circle') return d <= a.range + pr;
  if (a.shape === 'cone') return d <= a.range + pr && (d <= pr || angDiff(Math.atan2(dy, dx), face) <= a.half);
  const along = dx * Math.cos(face) + dy * Math.sin(face), across = Math.abs(-dx * Math.sin(face) + dy * Math.cos(face));
  return along >= -pr && along <= a.range + pr && across <= a.width + pr;
}
function enemyStrike(e) {
  const a = e.atk, p = G.p;
  G.fx.push({ type: 'zone', x: e.x, y: e.y, face: e.face, shape: a.shape, range: a.range, half: a.half || 0, t: 0, dur: 0.2 });
  G.shake = Math.max(G.shake, a.id === 'heavy' ? 3 : 1);
  if (!inZone(a, e.x, e.y, e.face, p.x, p.y, 14)) return;
  if (p.inv > 0) { fxText(p.x, p.y - 76, '闪过', '#7FD0BE'); G.stats.evades++; SFX.evade(); return; }
  hurtPlayer(a.dmg, e.x, e.y);
}
function separate() {
  const es = G.enemies.filter((e) => e.alive && e.state !== 'dying');
  for (let i = 0; i < es.length; i++) {
    for (let j = i + 1; j < es.length; j++) {
      const a = es[i], b = es[j], rr = KIND[a.kind].r + KIND[b.kind].r;
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy);
      if (d > 0.01 && d < rr) { const k = (rr - d) / 2 / d; a.x -= dx * k; a.y -= dy * k; b.x += dx * k; b.y += dy * k; }
    }
    const e = es[i], p = G.p, rr = KIND[e.kind].r + 16;
    const dx = e.x - p.x, dy = e.y - p.y, d = Math.hypot(dx, dy);
    if (d > 0.01 && d < rr) { e.x += (dx / d) * (rr - d); e.y += (dy / d) * (rr - d); collide(e, KIND[e.kind].r); }
  }
}
// 木人桩：慢慢蓄力，打不疼人，专门练闪避和破势
function updDummy(dt) {
  const dd = G.dummy, p = G.p, d = Math.hypot(p.x - DUMMY_POS.x, p.y - DUMMY_POS.y);
  dd.hit = Math.max(0, dd.hit - dt);
  if (d > 190) { dd.state = 'idle'; dd.t = 0; return; }
  dd.t += dt;
  if (dd.state === 'idle') { dd.face = Math.atan2(p.y - DUMMY_POS.y, p.x - DUMMY_POS.x); if (dd.t > 1.4) { dd.state = 'windup'; dd.t = 0; SFX.tele(); } }
  else if (dd.state === 'windup') {
    if (dd.t >= dd.atk.tele) {
      G.fx.push({ type: 'zone', x: DUMMY_POS.x, y: DUMMY_POS.y, face: dd.face, shape: 'cone', range: dd.atk.range, half: dd.atk.half, t: 0, dur: 0.2 });
      if (inZone(dd.atk, DUMMY_POS.x, DUMMY_POS.y, dd.face, p.x, p.y, 14)) {
        if (p.inv > 0) { fxText(p.x, p.y - 76, '闪过', '#7FD0BE'); SFX.evade(); G.stats.evades++; tip('dummyOk', '漂亮！实战里也一样：看到红色范围，闪出去'); }
        else { fxText(p.x, p.y - 76, '被打中（练习）', '#F08A6A'); SFX.hit(); G.shake = 1; }
      }
      dd.state = 'recover'; dd.t = 0;
    }
  } else if (dd.state === 'recover' && dd.t > 0.8) { dd.state = 'idle'; dd.t = 0; }
  else if (dd.state === 'stagger' && dd.t > 1.0) { dd.state = 'idle'; dd.t = 0; }
}

// ---------------------------------------------------------------- 交互对象
function interactables() {
  const out = [], f = G.f, inv = G.inv;
  for (const n of NPCS) {const pos=G.ally?.id===n.id&&!G.chapter.finalResolved?G.ally:n;out.push({ kind: 'npc', id: n.id, x: pos.x, y: pos.y, label: '交谈 · ' + n.name });}
  for (const it of INSPECT) out.push({ kind: 'look', id: it.id, x: it.x, y: it.y, label: '查看 · ' + it.name });
  if (!f.matPicked) out.push({ kind: 'crate', x: CRATE.x, y: CRATE.y, label: '拾取 · 木料堆' });
  if (f.asked && !inv.med && f.branch === null) HERBS.forEach((h, i) => { if (!f.herbs[i] && inv.herb < 2) out.push({ kind: 'herb', i, x: h.x, y: h.y, label: '采集 · 止血草' }); });
  const boss = G.enemies[2];
  if(G.f.accepted && !G.chapter.clues.includes('ledger') && G.f.branch)out.push({kind:'chapter',id:'ledger',x:LEDGER_POS.x,y:LEDGER_POS.y,label:'翻阅 · 工钱账册'});
  if(!G.chapter.cache)out.push({kind:'chapter',id:'cache',x:CACHE_POS.x,y:CACHE_POS.y,label:'搜寻 · 山中行囊'});
  if(G.f.delivered && G.chapter.decision && !G.chapter.finalStarted)out.push({kind:'chapter',id:'final',x:FINAL_POS.x,y:FINAL_POS.y,label:'赴约 · 渡口对峙'});
  if (!boss.hostile && !(G.ally?.id==='boss'&&!G.chapter.finalResolved)) out.push({ kind: 'boss', id: 'boss', x: boss.x, y: boss.y, label: '交谈 · 匪首' });
  return out;
}
let curTarget = null;
function findTarget() {
  if (!canAct() || inCombat()) return null;
  const p = G.p; let best = null, bd = 80;
  for (const t of interactables()) { const d = Math.hypot(t.x - p.x, t.y - p.y); if (d < bd) { bd = d; best = t; } }
  return best;
}
function interact() {
  const t = findTarget(); if (!t) return;
  SFX.ui();
  if(t.kind==='chapter'){setDlg(chapterObject(t.id));return;}
  if (t.kind === 'npc' || t.kind === 'boss') { openDlg(t.id); return; }
  if (t.kind === 'look') { openDlg('look:' + t.id); return; }
  if (t.kind === 'crate') {
    const r = commit('crate', '拾取木料堆', (d) => { if (d.f.matPicked) return { ok: false }; d.f.matPicked = true; d.inv.wood += 2; d.inv.iron += 1; lg(d, '在铁匠铺门口的木料堆拿到一份修械料（木料 2、废铁 1）'); });
    if (r.ok && !r.dup) { toast('拿到木料 2、废铁 1。去找周砚做剑饰'); SFX.pickup(); }
    return;
  }
  if (t.kind === 'herb') {
    const r = commit('herb' + t.i, '采止血草', (d) => { if (d.f.herbs[t.i] || d.inv.herb >= 2) return { ok: false }; d.f.herbs[t.i] = true; d.inv.herb++; });
    if (r.ok && !r.dup) { toast('采到止血草（' + G.inv.herb + '/2）'); SFX.pickup(); }
  }
}

// ---------------------------------------------------------------- 对话
const CHAT = {
  shen: ['病人是渡口的船工，烧了三天了，嘴唇都裂了。', '匪营那伙人以前也来抓过药，那时候还客客气气的。', '周砚铺子旁边有个木人桩，你可以先去那儿试试身手。'],
  shenAfter: ['船工今早退烧了，能喝下半碗粥。', '药钱的事，我心里有数，你不用操心。'],
  xu: ['船停了好几天，渡口的人心里都不踏实。', '那伙人原先也在码头扛活，后来不知怎么就上了山。', '水急的时候别往码头边上站，木板滑。'],
  zhou: ['破势讲究一个「准」字：等他刀举起来，再出剑招。', '回气讲究一个「连」字：剑招打中就回内力，可以多出几下。', '木人桩就在我铺子旁边，打不坏，放心敲。'],
  lu: ['渡口三条船，两条在修，一条在等药。', '沈大夫心软，什么人都给治。'],
};
function chatLine(who, pool) { const s = G.stats.chat; s[who] = (s[who] || 0) + 1; const arr = CHAT[pool || who]; return arr[(s[who] - 1) % arr.length]; }
function dialogFor(id) {
  const cd=chapterDialog(id);if(cd)return cd;
  const f = G.f, inv = G.inv, m = G.mem;
  const op = uid();
  const D = (o) => Object.assign({ op, opts: [] }, o);
  if (id.startsWith('look:')) {
    const k = id.slice(5), it = INSPECT.find((x) => x.id === k);
    const text = { board: '药材船误了三日。凡见渡口药包下落者，告知药师沈青。——青石渡', cart: '车辙在这里乱了。药箱被撬开过，箱底压着半张撕碎的工钱单，字迹已经看不清。', sign: '往东：山道，再往东是匪营。往西：青石渡。' }[k];
    return D({ who: it.name, id, face: it.obj, look: k, text, opts: [{ label: '记下', key: 'look_ok', primary: true }] });
  }
  if (id === 'shen') {
    if (f.delivered) {
      const t = f.told ? (f.branch === 'A' ? '你和匪首动了手……下回受了伤，早些回来。' : '原来他们也是讨工钱的人。') : '药送到了。其余的，你不说我也不多问。';
      return D({ who: '沈青', sub: '青石渡药师', id, text: t + ' 累了就在这儿歇歇。', opts: [{ label: '请她包扎', sub: '生命补满，不花绷带', key: 'heal' }, { label: '闲聊', key: 'chat_shen2' }, { label: '告辞', key: 'close' }] });
    }
    if (inv.med) return D({ who: '沈青', sub: '青石渡药师', id, text: '药包……真的拿回来了。山道上，还顺利吗？', note: '两个选择的奖励相同：铜钱 +20 · 绷带 +1',
      opts: [{ label: '交出药包，并讲述经过', sub: f.branch === 'A' ? '告诉她：你击退了匪首，夺回药包' : '告诉她：你用药草 2 与匪首换回了药包', key: 'give_tell', primary: true },
        { label: '只交出药包，不提山道细节', sub: '沈青只会确认收到了药', key: 'give_quiet' }] });
    if (!f.accepted) return D({ who: '沈青', sub: '青石渡药师', id, text: '你是外乡来的吧？渡口的药包被山道上的匪首扣下了。病人等不起，你能帮我取回来吗？', opts: [{ label: '接下这件事', key: 'accept', primary: true }, { label: '再想想', key: 'close' }] });
    return D({ who: '沈青', sub: '青石渡药师', id, text: f.lostBoss ? '伤成这样……匪首下手不轻吧？先歇歇，别逞强。' : '药包在山道尽头的匪营里。受了伤就回来，我给你包扎。', opts: [{ label: '请她包扎', sub: '生命补满，不花绷带', key: 'heal' }, { label: '闲聊', key: 'chat_shen' }, { label: '这就去', key: 'close' }] });
  }
  if (id === 'xu') {
    const opts = [];
    if (f.bossClaim && !m.xu.k.includes('claim')) opts.push({ label: '匪首说渡口欠着工钱账目', sub: '把匪首的说法告诉他', key: 'xu_claim' });
    if (!f.heardDebt) return D({ who: '许舟', sub: '渡口船工', id, text: '我听扣货的那伙人说，是渡口先拖欠了他们的工钱。我也只是听说，做不得准。', opts: [{ label: '记下了', key: 'xu_ok', primary: true }] });
    opts.push({ label: '闲聊', key: 'chat_xu' }, { label: '告辞', key: 'close' });
    return D({ who: '许舟', sub: '渡口船工', id, text: f.delivered ? '药送到了？那船工能好起来，渡口的船也能开了。' : m.xu.k.includes('claim') ? '那件事……你心里有数就行，别往外传。' : '船停着，人也闲着。你要过河，还得等等。', opts });
  }
  if (id === 'lu') {
    if (f.delivered) return D({ who: '陆平', sub: '渡口管事', id, text: m.lu.att < 0 ? '药送到了就好。账的事，不劳你操心。' : '药送到了就好。渡口欠你一份人情。', opts: [{ label: '闲聊', key: 'chat_lu' }, { label: '告辞', key: 'close' }] });
    if (f.bossClaim && !f.askedLu) return D({ who: '陆平', sub: '渡口管事', id, text: '药还没送到，你倒先打听起账目来了？', opts: [{ label: '问欠薪的事', sub: '匪首说渡口欠着他们的工钱账目', key: 'lu_debt' }, { label: '没什么', key: 'close' }] });
    return D({ who: '陆平', sub: '渡口管事', id, text: f.askedLu ? '你问的那件事，别再提了。药呢？' : f.accepted ? '药呢？快些，沈大夫那边等着呢。' : '你是新来的？沈大夫正为药包的事发愁，去帮帮她。', opts: [{ label: '闲聊', key: 'chat_lu' }, { label: '知道了', key: 'close' }] });
  }
  if (id === 'zhou') {
    let text = '山里那位出手前总要停一下，破势就是冲那个停顿去的；要是怕内力跟不上，选回气。一份料加 5 铜钱，必定做成；剑饰槽只放一件，换新的，旧的就毁了。';
    if (G.orn === '破势' && G.stats.interrupts > 0) text = '看来破势派上用场了，刀口没卷吧？想换回气，料和钱备齐了就来。';
    else if (G.orn === '回气' && G.stats.qiBack > 0) text = '回气用得顺手？内力续上了，剑招就能多出几下。想换破势，料和钱备齐了就来。';
    const opts = [
      { label: '做一件「破势」', sub: '剑招命中对手的蓄力时，打断这一次攻击', key: 'craft_ps' },
      { label: '做一件「回气」', sub: '剑招命中后返还部分内力，每次出招只返还一次', key: 'craft_hq' },
    ];
    if (f.zhouBuys < 2) opts.push({ label: '买一份料（10 铜钱）', sub: '木料 2 + 废铁 1，还能买 ' + (2 - f.zhouBuys) + ' 份', key: 'buy_zhou' });
    opts.push({ label: '闲聊', key: 'chat_zhou' }, { label: '离开', key: 'close' });
    return D({ who: '周砚', sub: '铁匠', id, text, note: '持有：木料 ' + inv.wood + ' · 废铁 ' + inv.iron + ' · 铜钱 ' + inv.coin + '　当前剑饰：' + (G.orn || '无'), opts });
  }
  if (id === 'boss') {
    if (f.branch === 'A') {
      const opts = [];
      if (f.delivered) opts.push({ label: '切磋一场', sub: f.sparWins < 2 ? '赢了给一份修械料（还剩 ' + (2 - f.sparWins) + ' 次）' : '已经没有物质奖励', key: 'spar', primary: true });
      opts.push({ label: '离开', key: 'close' });
      return D({ who: '匪首', sub: '匪营', id, text: f.delivered ? '药被你夺回了，还想再比一场？' : '药被你夺回了。……服气。别在我营里多待。', opts });
    }
    if (f.branch === 'B') {
      const opts = [];
      if (!f.bought) opts.push({ label: '买修械料（5 铜钱）', sub: '木料 2 + 废铁 1，限购一份', key: 'buy_boss', primary: true });
      if (f.delivered) opts.push({ label: '切磋一场', sub: '点到为止，没有物质奖励', key: 'spar' });
      opts.push({ label: '离开', key: 'close' });
      const t = f.delivered ? '药已按约给你，想切磋随时奉陪。' : f.bought ? '按约办事的人，我记着。' : '你肯按约办事。我这有一份修械料，五文给你。';
      return D({ who: '匪首', sub: '匪营', id, text: t + (f.bossClaim && f.delivered ? ' 那本账，你要是有门路，帮我们问问。' : ''), opts });
    }
    const opts = [];
    let text;
    if (f.asked) {
      text = inv.herb >= 2 ? '药草带来了？' : '止血草长在山道两侧，采两株来。（现在 ' + inv.herb + '/2）';
      if (inv.herb >= 2) opts.push({ label: '交出药草 2，换回药包', sub: '本次不再走武力取回', key: 'trade', primary: true });
    } else {
      text = f.lostBoss ? '又是你。刚才那一架还没打够？' : '药包在我这儿。想要？';
      opts.push({ label: '问交换条件', key: 'ask' });
    }
    opts.push({ label: '动手抢回药包', sub: '击退匪首就能拿回药包', key: 'fight' });
    opts.push({ label: '离开', key: 'close' });
    return D({ who: '匪首', sub: '匪营', id, text, opts });
  }
  return null;
}
function openDlg(id) { const d = dialogFor(id); if (!d) return; resetInput();G.dlg={op:uid(),...d};Playtest.event(G,'dialogue',{who:id});renderDlg(); }
function setDlg(d) { resetInput(); G.dlg = Object.assign({ op: uid() }, d); renderDlg(); }
function closeDlg() { G.dlg = null; renderDlg(); }
const FACE_ID = { 沈青: 'shen', 许舟: 'xu', 陆平: 'lu', 周砚: 'zhou', 匪首: 'boss' };
function renderDlg() {
  const d = G.dlg, el = $('dlg');
  app.classList.toggle('talking', !!d);
  if (!d) { el.hidden = true; return; }
  el.hidden = false;
  portrait($('dFaceC'), d.face || FACE_ID[d.who] || 'xia');
  const who = $('dWho'); who.textContent = d.who; if (d.sub) { const s = document.createElement('small'); s.textContent = d.sub; who.appendChild(s); }
  $('dText').textContent = d.text; $('dNote').textContent = d.note || '';
  const box = $('dOpts'); box.textContent = '';
  d.opts.forEach((o) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'opt ' + (o.primary ? 'px-optsel' : 'px-opt');
    const s = document.createElement('span'); s.textContent = o.label; b.appendChild(s);
    if (o.sub) { const m = document.createElement('small'); m.textContent = o.sub; b.appendChild(m); }
    b.addEventListener('click', () => doAct(o.key));
    box.appendChild(b);
  });
  const first = box.querySelector('button'); if (first && matchMedia('(pointer: fine)').matches) first.focus({ preventScroll: true });
}
function craft(name, op) {
  const old = G.orn;
  const r = commit(op, '制作剑饰「' + name + '」', (d) => {
    if (d.orn === name) return { ok: false, msg: '已经装着「' + name + '」了' };
    if (d.inv.wood < 2 || d.inv.iron < 1) return { ok: false, msg: '料不够：要木料 2、废铁 1' };
    if (d.inv.coin < 5) return { ok: false, msg: '铜钱不够，制作费要 5' };
    d.inv.wood -= 2; d.inv.iron -= 1; d.inv.coin -= 5; d.orn = name; d.stats.crafts.push(name);
    lg(d, '请周砚做了剑饰「' + name + '」' + (old ? '（替换了「' + old + '」）' : ''));
    know(d, 'zhou', 'made_' + name);
  });
  if (r.ok && !r.dup) { toast('周砚做好了「' + name + '」' + (old ? '，旧的「' + old + '」已毁' : '')); SFX.craft(); tip('dummy', '去铺子旁边的木人桩试试新剑饰'); }
  setDlg(dialogFor('zhou'));
}
function doAct(key) {
  const d0 = G.dlg; if (!d0 || !d0.opts.some(o=>o.key===key)) return;
  const op = d0.op + ':' + key, f = G.f, p = G.p, boss = G.enemies[2];
  if(chapterAction(key,d0,op))return;
  SFX.ui();
  switch (key) {
    case 'close': closeDlg(); break;
    case 'accept': {
      const r = commit(op, '接下请求', (d) => { d.f.accepted = true; lg(d, '接下沈青的请求：从匪首手里取回药包'); know(d, 'shen', 'accepted'); });
      if (r.ok && !r.dup) { toast('接下请求：药包在山道尽头的匪营'); tip('dummy', '铁匠铺旁的木人桩可以先练练闪避'); }
      closeDlg(); break;
    }
    case 'heal': { const r=commit(op,'沈青包扎',d=>{d.p.hp=d.p.maxHp;});if(r.ok){toast('沈青帮你包扎好了');SFX.heal();closeDlg();}break;}
    case 'xu_ok': commit('xu_ok', '听许舟转述', (d) => { d.f.heardDebt = true; lg(d, '许舟转述：扣货的人说渡口拖欠他们工钱（未核实）'); know(d, 'xu', 'told_rumor'); }); closeDlg(); break;
    case 'xu_claim':
      commit('xu_claim', '把匪首的说法告诉许舟', (d) => { know(d, 'xu', 'claim'); d.mem.xu.att += 1; lg(d, '把匪首的说法告诉了许舟，他叫你别往外传'); });
      setDlg({ who: '许舟', sub: '渡口船工', id: 'xu', text: '……我就知道。可这话从我嘴里说出去，饭碗就没了。你心里有数就行。', opts: [{ label: '明白', key: 'close' }] }); break;
    case 'chat_shen': setDlg({ who: '沈青', sub: '青石渡药师', id: 'shen', text: chatLine('shen'), opts: [{ label: '再聊聊', key: 'chat_shen' }, { label: '告辞', key: 'close' }] }); break;
    case 'chat_shen2': setDlg({ who: '沈青', sub: '青石渡药师', id: 'shen', text: chatLine('shen2', 'shenAfter'), opts: [{ label: '再聊聊', key: 'chat_shen2' }, { label: '告辞', key: 'close' }] }); break;
    case 'chat_xu': setDlg({ who: '许舟', sub: '渡口船工', id: 'xu', text: chatLine('xu'), opts: [{ label: '再聊聊', key: 'chat_xu' }, { label: '告辞', key: 'close' }] }); break;
    case 'chat_zhou': setDlg({ who: '周砚', sub: '铁匠', id: 'zhou', text: chatLine('zhou'), opts: [{ label: '回到剑饰', key: 'back_zhou' }, { label: '告辞', key: 'close' }] }); break;
    case 'back_zhou': setDlg(dialogFor('zhou')); break;
    case 'chat_lu': setDlg({ who: '陆平', sub: '渡口管事', id: 'lu', text: chatLine('lu'), opts: [{ label: '告辞', key: 'close' }] }); break;
    case 'lu_debt':
      commit('lu_debt', '向陆平问欠薪', (d) => { d.f.askedLu = true; d.mem.lu.att -= 1; know(d, 'lu', 'asked_debt'); lg(d, '向陆平问起欠薪账目，他没有正面回答'); });
      setDlg({ who: '陆平', sub: '渡口管事', id: 'lu', text: '……那本账，不是你该管的。先把药送到沈大夫手上。', opts: [{ label: '好吧', key: 'close' }] }); break;
    case 'look_ok': {
      const k = d0.look;
      const lines = { board: '看过渡口告示：药材船误了三日', cart: '山道上的货车翻了，箱底有半张撕碎的工钱单（看不清写了什么）', sign: '' };
      if (lines[k]) commit('look:' + k, '查看' + k, (d) => { d.f.inspected[k] = true; lg(d, lines[k]); });
      closeDlg(); break;
    }
    case 'craft_ps': craft('破势', op); break;
    case 'craft_hq': craft('回气', op); break;
    case 'buy_zhou': {
      const r = commit(op, '向周砚买料', (d) => { if (d.f.zhouBuys >= 2) return { ok: false, msg: '周砚的料卖完了' }; if (d.inv.coin < 10) return { ok: false, msg: '铜钱不够，一份料要 10' }; d.inv.coin -= 10; d.inv.wood += 2; d.inv.iron += 1; d.f.zhouBuys++; });
      if (r.ok && !r.dup) { toast('向周砚买了一份料'); SFX.buy(); }
      setDlg(dialogFor('zhou')); break;
    }
    case 'ask': {
      const r=commit('ask', '问交换条件', (d) => { d.f.asked = true; d.f.bossClaim = true; know(d, 'boss', 'asked'); lg(d, '匪首声称渡口欠着他们的工钱账目（未核实）'); lg(d, '匪首开出条件：采止血草 2 换药包'); });
      if(!r.ok)break;
      setDlg({ who: '匪首', sub: '匪营', id: 'boss', text: '渡口欠我们兄弟的工钱，账上记得清清楚楚。药包可以给你：山道两侧有止血草，采两株来换。', note: '山道上下两侧出现了止血草的记号', opts: [{ label: '我去采', key: 'close', primary: true }, { label: '还是动手吧', sub: '击退匪首就能拿回药包', key: 'fight' }] });
      break;
    }
    case 'trade': {
      const lost = f.lostBoss;
      const r = commit('trade', '药草换药包', (d) => {
        if (d.f.branch) return { ok: false, msg: '药包已经拿回来了' };
        if (d.inv.herb < 2) return { ok: false, msg: '止血草还不够两株' };
        d.inv.herb -= 2; d.inv.med = true; d.f.branch = 'B'; d.stats.branchAt = Math.round(G.time);
        know(d, 'boss', 'route_B'); d.mem.boss.att += 2;
        lg(d, lost ? '败过一阵后，仍用止血草 2 与匪首换回了药包' : '用止血草 2 与匪首换回了药包');
      });
      if(!r.ok)break;
      if (!r.dup) { toast('药包到手。回青石渡交给沈青'); SFX.pickup(); }
      setDlg({ who: '匪首', sub: '匪营', id: 'boss', text: (lost ? '打过一架还肯按约办事……行。' : '') + '你肯按约办事。我这有一份修械料，五文给你。', opts: [{ label: '买修械料（5 铜钱）', sub: '木料 2 + 废铁 1，限购一份；以后再来买也行', key: 'buy_boss', primary: true }, { label: '先不买', key: 'close' }] });
      break;
    }
    case 'buy_boss': {
      const r = commit('buy_boss', '向匪首买料', (d) => { if (d.f.branch !== 'B') return { ok: false }; if (d.f.bought) return { ok: false, msg: '这份料已经买过了' }; if (d.inv.coin < 5) return { ok: false, msg: '铜钱不够' }; d.inv.coin -= 5; d.inv.wood += 2; d.inv.iron += 1; d.f.bought = true; know(d, 'boss', 'bought'); lg(d, '向匪首买下一份修械料（5 铜钱）'); });
      if (r.ok && !r.dup) { toast('买到修械料：木料 2、废铁 1'); SFX.buy(); }
      setDlg(dialogFor('boss')); break;
    }
    case 'fight': {
      const r=commit(op,'与匪首交手',d=>{const b=d.enemies[2];Object.assign(b,{hostile:true,spar:false,state:'chase',plan:null});d.f.fought=true;lg(d,'你向匪首动了手');});
      if(r.ok){toast('匪首拔刀了！看准他的蓄力');closeDlg();}break;}
    case 'spar': {
      const r=commit(op,'开始切磋',d=>{Object.assign(d.enemies[2],{hostile:true,spar:true,state:'chase',plan:null,hp:KIND.boss.hp});});
      if(r.ok){toast('切磋开始：点到为止');closeDlg();}break;}
    case 'give_tell': deliver(true, op); break;
    case 'give_quiet': deliver(false, op); break;
    case 'finish': closeDlg();toast('第二幕 · 查账。找许舟、货车与匪营账箱；也可向沈青决定离开。'); break;
  }
}
function deliver(tell, op) {
  const br = G.f.branch, hadHerb = G.inv.herb > 0, bought = G.f.bought;
  const echo = (tell ? '你向沈青讲述了' + (br === 'A' ? '击退匪首' : '用药草交换') + '的经过' : '沈青只知道药送回来了') + (br === 'B' && !bought ? '；匪首仍愿意向你出让那份修械料' : '') + '。';
  const r = commit('deliver', '交药', (d) => {
    if (d.f.delivered) return { ok: false, msg: '药已经交过了' };
    if (!d.inv.med) return { ok: false, msg: '身上没有药包' };
    d.inv.med = false; d.inv.coin += 20; d.inv.bandage += 1; d.f.delivered = true; d.f.told = tell; d.inv.herb = 0;
    d.stats.deliveredAt = Math.round(G.time);
    if (tell) { know(d, 'shen', 'route_' + br); d.mem.shen.att += 1; } else know(d, 'shen', 'got_med');
    lg(d, tell ? '向沈青讲述了' + (br === 'A' ? '击退匪首、夺回药包' : '用药草与匪首交换药包') + '的经过' : '只把药包交给沈青，没提山道上的事');
    d.echo = echo; lg(d, '江湖回响：' + echo);
  });
  if (r.dup) return;
  if (!r.ok) { closeDlg(); return; }
  SFX.done();
  const text = tell ? (br === 'A' ? '你和匪首动了手？……人没事就好。这些你收着。' : '拿药草换回来的？他们倒还讲道理。这些你收着。') : '药收到了，多谢。这些你收着。';
  setDlg({ who: '沈青', sub: '青石渡药师', id: 'shen', text, note: '获得：铜钱 +20 · 绷带 +1' + (hadHerb ? '；顺手把采到的止血草也交给了她' : ''), opts: [{ label: '收下', key: 'finish', primary: true }] });
}

// ---------------------------------------------------------------- 第二、三幕：证据、抉择与实际遭遇
function chapterObject(id) {
  if(id==='ledger') return {who:'工钱账册',face:'board',id:'ledger',text:Chapter.CLUES.ledger.text,note:G.f.branch==='B'?'匪首把账箱交给了你：你守过约，他也肯让你看。':'匪首把旧账箱踢到你面前：赢了刀，也看看欠的到底是谁。',opts:[{label:'抄下姓名和数额',key:'clue_ledger',primary:true},{label:'暂时放下',key:'close'}]};
  if(id==='cache') return {who:'山中行囊',face:'wood',id:'cache',text:'松针下压着一只旧行囊。布包里还有一条干净绷带、五文钱和两块修械木料。没有人的踪迹。',opts:[{label:'收好能用的东西',sub:'绷带 +1、铜钱 +5、木料 +2；只可搜寻一次',key:'cache',primary:true},{label:'放回原处',key:'close'}]};
  const e=Chapter.encounter(G);
  const opts=[{label:'准备好了，赴约',sub:'开始后仍可败退、包扎，再回来继续；已击退的人不会重复出现',key:'final_start',primary:true}];
  if(e.peace) opts.unshift({label:'带证据当面对账',sub:'交换建立的信任与两条证据，让双方有议和的条件',key:'final_peace',primary:true});
  opts.push({label:'再准备一下',key:'close'});
  return {who:'渡口之约',face:'lu',id:'final',text:e.intro,note:'这一局的抉择：'+Chapter.DECISIONS[G.chapter.decision].name+(e.ally==='boss'?'。匪首会与你并肩出剑。':e.ally==='xu'?'。许舟会用投石支援你。':'。这一回只能靠自己。'),opts};
}
function choiceDialog() {
  const c=G.chapter;
  if(c.decision)return {who:'沈青',id:'shen',text:'药已经救下人。你做过的决定，也已经传到该听见的人耳里。去渡口南面的告示前赴约吧。',opts:[{label:'请她包扎',key:'heal'},{label:'查看江湖图',key:'atlas_map'},{label:'告辞',key:'close'}]};
  return {who:'沈青',id:'shen',text:'船工醒了，先说了一声“工钱”。你可以到这里为止，也可以继续追问。账的事，至少找两处相互印证，别拿一句传言去伤人。',note:'已掌握 '+c.clues.length+'/3 条线索。正式决定前会再说明代价；现在可以继续调查。',opts:[{label:'公开账目',sub:c.clues.length>=2?'证据够了，请许舟到渡口对质':'需要至少两条线索',key:'decide_public'},{label:'促成调停',sub:'保留合作，在渡口让双方把账说清',key:'decide_mediate'},{label:'不再追问，准备离开',sub:'陆平给补给；欠薪暂不处理',key:'decide_leave'},{label:'先去寻找线索',sub:'许舟、翻倒的货车、匪营旧账箱',key:'close'}]};
}
function chapterDialog(id) {
  const c=G.chapter, f=G.f;
  if(id==='look:cart')return {who:'货车残单',face:'cart',id,text:Chapter.CLUES.cart.text,note:c.clues.includes('cart')?'你已经抄下了这张运单。':'箱底的半张残单，还能读清落款和日期。',opts:[{label:c.clues.includes('cart')?'收起残单':'抄下残单',key:c.clues.includes('cart')?'close':'clue_cart',primary:true}]};
  if(id==='xu' && f.accepted){
    if(c.finalResolved)return {who:'许舟',id,text:c.decision==='public'?'护院退了，账也摊开了。我不知道明天还能不能上船，但今天这话总算说出来了。':c.decision==='mediate'?'他们肯坐下来对账了。要真能结清，兄弟们还是愿意回渡口扛活。':'船又要开了。欠的那些钱……以后再说吧。',opts:[{label:'告辞',key:'close'}]};
    return {who:'许舟',id,text:c.clues.includes('witness')?'我答应过你的话还作数。要对质，我会到渡口。可别只凭我这一张嘴，货车残单和旧账册也去看看。':'我亲眼看见陆管事收下药商结款。我们六个人，两个月一文工钱也没拿到。先前我只敢说听说；你若真想查，我愿意用自己的名字作证。',note:'证词有来源，也有风险；仍需书面记录印证。',opts:[{label:c.clues.includes('witness')?'看看已有线索':'记下他的亲历证词',key:c.clues.includes('witness')?'atlas_clues':'clue_witness',primary:true},{label:'告辞',key:'close'}]};
  }
  if(id==='shen' && f.delivered){
    if(c.finalResolved)return {who:'沈青',id,text:endingText(),opts:[{label:'请她包扎',key:'heal'},{label:'回看本章结果',key:'ending'},{label:'告辞',key:'close'}]};
    const d=choiceDialog();d.opts.unshift({label:'请她包扎',sub:'免费恢复生命，不消耗绷带',key:'heal'});
    if(c.decision==='mediate'&&!c.supplied)d.opts.unshift({label:'带一条绷带赴约',sub:'沈青的帮助，只领取一次',key:'supply'});
    return d;
  }
  if(id==='lu' && f.delivered){
    if(c.decision==='public')return {who:'陆平',id,text:'你把账翻到明面上，就别再指望我给你什么方便。渡口南面有人等你，护好你的证人。',opts:[{label:'告辞',key:'close'}]};
    if(c.decision==='leave')return {who:'陆平',id,text:'救命药送到，事情就算办完了。拿两条绷带，乘船走吧。至于山道上的人……你自己多留意。',opts:[{label:c.supplied?'补给已领取':'收下两条绷带',key:c.supplied?'close':'supply',primary:true},{label:'告辞',key:'close'}]};
    return {who:'陆平',id,text:c.clues.length>=2?'你手里的两份东西，倒是对得上。真要对账，就到渡口，当着人的面谈。':'运费、工钱、修船钱，哪有你想得这么清楚。真想打听，就拿出凭据。',opts:[{label:'决定怎样处理',key:'choices'},{label:'告辞',key:'close'}]};
  }
  if(id==='zhou'){
    return {who:'周砚',id,text:'剑有三路：追风刺追人，截流剑断招，回澜斩解围。带哪两路由你。剑饰另算：破势延长打断并让下一次普攻追击 +8；回气每次剑招命中返 18 内力，空挥不返。',note:'木人桩在铺旁：破势打断后接普攻，追击 +8；回气剑招命中返 18 内力（空挥不返）。练习和战斗每秒回 1.5，离开后回 6。',opts:[{label:'挑选携带的两招',key:'atlas_skills',primary:true},{label:'做一件「破势」',sub:'木料 2、废铁 1、铜钱 5；替换旧剑饰',key:'craft_ps'},{label:'做一件「回气」',sub:'木料 2、废铁 1、铜钱 5；替换旧剑饰',key:'craft_hq'},...(f.zhouBuys<2?[{label:'买一份料（10 铜钱）',key:'buy_zhou'}]:[]),{label:'告辞',key:'close'}]};
  }
  if(id==='boss' && f.branch){
    const opts=[];
    if(f.branch==='B'&&!f.bought)opts.push({label:'买修械料（5 铜钱）',sub:'限购一份，木料 2、废铁 1',key:'buy_boss'});
    if(!c.clues.includes('ledger'))opts.push({label:'想看看你说的工钱账',sub:'旧账箱在营地东侧，有一卷纸的标记',key:'ledger_hint',primary:true});
    if(f.delivered&&(!c.finalStarted||c.finalResolved))opts.push({label:'切磋一场',sub:f.sparWins<2?'前两次胜利各得一份修械料':'只切磋，不再发材料',key:'spar'});
    opts.push({label:'告辞',key:'close'});
    return {who:'匪首',id,text:f.branch==='A'?'药你拿走，刀我认输。可我们为什么扣货，你还没问明白。账箱就在那儿，自己看。':c.decision==='mediate'?'你守过约，我信你这一次。渡口会面，我会去。':'你肯守约，我也不藏着掖着。那本账你拿去核；渡口的人要肯对账，我们就肯回去做工。',opts};
  }
  return null;
}
function chapterAction(key,d0,op) {
  if(key.startsWith('atlas_')){closeDlg();toggleAtlas(true,key.slice(6));return true;}
  if(key==='choices'){setDlg(choiceDialog());return true;}
  if(key.startsWith('clue_')){
    const id=key.slice(5),r=commit('clue:'+id,'取得线索',d=>Chapter.act(d,'clue',id));
    if(r.ok){toast('记下线索：'+Chapter.CLUES[id].name);SFX.note();closeDlg();}return true;
  }
  if(key==='ledger_hint'){setDlg({who:'匪首',id:'boss',text:'东边木桶旁的旧箱子。六个人，两个月，谁欠谁的，你自己看。',opts:[{label:'去翻阅账册',key:'close'}]});return true;}
  if(key==='cache'){
    const r=commit('cache','搜寻山中行囊',d=>{if(d.chapter.cache)return {ok:false};d.chapter.cache=true;d.inv.bandage++;d.inv.coin+=5;d.inv.wood+=2;lg(d,'在山中旧行囊找到绷带 1、铜钱 5 和木料 2');});
    if(r.ok){toast('行囊里的补给已经收好');SFX.pickup();closeDlg();}return true;
  }
  if(key.startsWith('decide_')){
    const id=key.slice(7),probe=JSON.parse(JSON.stringify(G)),r=Chapter.act(probe,'decide',id);
    if(!r.ok){toast(r.msg);return true;}
    setDlg({who:'你的抉择',face:'xia',id:'decision',decision:id,text:Chapter.DECISIONS[id].text,note:'确认后保留本次决定。你仍能探索、换招与包扎。',opts:[{label:'就这样做：'+Chapter.DECISIONS[id].name,key:'confirm_decision',primary:true},{label:'再想一想',key:'choices'}]});return true;
  }
  if(key==='confirm_decision'){
    const r=commit('decision','渡口抉择',d=>Chapter.act(d,'decide',d0.decision));
    if(r.ok){closeDlg();toast('第三幕 · '+Chapter.DECISIONS[G.chapter.decision].name+'。前往渡口南面告示赴约');SFX.done();}return true;
  }
  if(key==='supply'){
    const r=commit('chapter:supply','领取赴约补给',d=>Chapter.act(d,'supply'));
    if(r.ok){toast('绷带已经放进行囊');SFX.pickup();closeDlg();}return true;
  }
  if(key==='final_start'||key==='final_peace'){startFinal(key==='final_peace');return true;}
  if(key==='ending'){closeDlg();G.done=true;renderDone();return true;}
  return false;
}
function startFinal(peace) {
  if(peace&&!Chapter.encounter(G).peace){toast('议和条件不足');return;}
  const r=commit('chapter:final','赴渡口之约',d=>{
    const r=Chapter.act(d,'start');if(!r.ok)return r;
    if(peace)return Chapter.act(d,'resolve','peace');
    const plan=Chapter.encounter(d);
    plan.foes.forEach((role,i)=>{const e=mkEnemy(role==='archer'?'archer':role==='captain'?'captain':role==='raider'?'bandit':'guard',FINAL_POS.x+75+i*64,FINAL_POS.y+(i%2?65:-25));e.final=true;d.enemies.push(e);});
    d.p.x=FINAL_POS.x-120;d.p.y=FINAL_POS.y+25;d.p.mp=d.p.maxMp;
    d.ally=plan.ally?{id:plan.ally,x:d.p.x-28,y:d.p.y+35,cd:.6,face:0}:null;
    lg(d,'渡口对峙开始：'+plan.title+(plan.ally?'；'+(plan.ally==='xu'?'许舟投石支援':'匪首并肩出剑'):'；独自应对'));
    return {ok:true};
  });
  if(!r.ok)return;
  closeDlg();resetInput();
  if(peace){G.done=true;SFX.done();renderDone();}
  else toast('对峙开始。先处理弓手，木桶和房屋可以挡箭');
}
function endingText() {
  const c=G.chapter;
  if(c.decision==='public')return c.clues.map(id=>Chapter.CLUES[id].name).join('、')+'在渡口摊开。护院退去，陆平失去了把事情压回去的机会。'+(c.clues.includes('witness')?'许舟愿意出面，付出的可能是明天的饭碗。':'许舟在冲突中赶来帮忙；你凭书面记录争取到了当面对账的机会。')+'船工尚未收到全部工钱，但从此有了能当面追索的凭据。';
  if(c.decision==='mediate')return c.peaceful?'你把账和人都带到了桌前。匪首放下刀，陆平承认有一笔工钱尚未付清，约定分批偿还。协议尚需兑现；至少今天，这船药和这本账，没有再靠一场流血了结。':'你护住了会面，双方终于坐下核账。匪首记得你先前守过的约；陆平答应再谈，尚未承认所有数额。你争取到了开口的机会，后面的偿还还要人盯着。';
  return '你击退追来的余匪，乘船离开了青石渡。沈青救下了船工。'+(c.supplied?'你收下了陆平提供的两条绷带。':'你没有收下陆平提供的补给。')+'那本账还留在渡口——你救了人，也选择把另一个难题留给他们。';
}
function chapterQuest() {
  const c=G.chapter;
  if(c.finalResolved)return ['第一章完成 · '+Chapter.DECISIONS[c.decision].name,'M 回看线索与人物；可换招、回匪营切磋'];
  if(c.finalStarted)return ['渡口对峙 · '+Chapter.encounter(G).title,'击退剩余 '+G.enemies.filter(e=>e.final&&activeFoe(e)).length+' 人；败退后可包扎再回来'];
  if(c.decision)return ['到渡口南面赴约','选择：'+Chapter.DECISIONS[c.decision].name+'；可先向'+(c.decision==='leave'?'陆平领补给':c.decision==='mediate'?'沈青领绷带':'周砚换剑饰')];
  return ['第二幕 · 谁的账','找许舟、货车残单、匪营账箱（'+c.clues.length+'/3）；找沈青决定下一步'];
}

// ---------------------------------------------------------------- 江湖图、武学与人物手记
let atlasTab='map';
function toggleAtlas(on,tab) {
  if(!G.started)return;
  const open=on===undefined?$('atlas').hidden:on;
  if(open&&G.dlg)return;
  if(tab)atlasTab=tab;
  if(open&&inCombat()){toast('战斗中无法查看手记或换招，先脱身');return;}
  $('atlas').hidden=!open;resetInput();if(open)renderAtlas();
}
function atlasButton(text,fn) {const b=document.createElement('button');b.className='mini px-opt';b.textContent=text;b.onclick=fn;return b;}
function renderAtlas() {
  const body=$('atlasBody');body.textContent='';
  for(const [name,id]of [['map','tabMap'],['skills','tabSkills'],['clues','tabClues']]){$(id).className='mini '+(name===atlasTab?'px-optsel':'px-opt');$(id).setAttribute('aria-selected',String(name===atlasTab));}
  if(atlasTab==='map'){
    const map=document.createElement('canvas');map.width=840;map.height=300;map.className='mapfull';map.setAttribute('aria-label','青石渡在西，松风山道居中，匪营在东；白点是你，金点是人物，青点是线索');body.append(map);paintMap(map,true);
    const legend=document.createElement('div');legend.className='maplegend';legend.textContent='白：你的位置　金：人物　青：线索 / 药草　红：敌人　菱形：当前目标';body.append(legend);
    const p=document.createElement('p');p.className='atlas-note';p.textContent=questText().join('。')+'。绕行山道南侧可以避开正面交战；林中可能有旧行囊。地图只指路，不会替你移动。';body.append(p);
  }else if(atlasTab==='skills'){
    const head=document.createElement('p');head.className='atlas-note';head.textContent='携带两招 · K：'+Chapter.SKILLS[G.chapter.skills[0]].name+' / I：'+Chapter.SKILLS[G.chapter.skills[1]].name+'。当前剑饰：'+(G.orn||'基础剑，无修饰')+'。战斗外换招，不会重置冷却。';body.append(head);
    for(const [id,sk]of Object.entries(Chapter.SKILLS)){
      const row=document.createElement('div');row.className='skill-row';
      const title=document.createElement('div');const h=document.createElement('h3');h.textContent=sk.name;const t=document.createElement('small');t.textContent=sk.tag;title.append(h,t);
      const p=document.createElement('p');p.textContent=sk.text+' 耗内力 '+sk.cost+'，冷却 '+sk.cd+' 秒。';const buttons=document.createElement('div');buttons.className='skill-actions';
      [0,1].forEach(slot=>{const equipped=G.chapter.skills[slot]===id,b=atlasButton(equipped?'已在 '+(slot?'I':'K')+' 槽':'装入 '+(slot?'I':'K')+' 槽',()=>{
        if(inCombat()){toast('战斗中不能换招');return;}
        const r=commit('equip:'+uid(),'更换携带招式',d=>Chapter.act(d,'equip',{slot,skill:id}));if(r.ok)renderAtlas();
      });b.disabled=G.chapter.skills.includes(id);buttons.append(b);});row.append(title,p,buttons);body.append(row);
    }
  }else{
    const p=document.createElement('p');p.className='atlas-note';p.textContent='已有 '+G.chapter.clues.length+'/3 条线索。'+(G.chapter.decision?'已决定：'+Chapter.DECISIONS[G.chapter.decision].name:'先救人，后追问；线索不足也可以选择离开。');body.append(p);
    for(const [id,clue]of Object.entries(Chapter.CLUES)){const row=document.createElement('div');row.className='clue-row';const h=document.createElement('h3');h.textContent=G.chapter.clues.includes(id)?'已得 · '+clue.name:'未得 · '+clue.name;const text=document.createElement('div');text.textContent=G.chapter.clues.includes(id)?clue.text:'去向：'+clue.source+(id==='ledger'?'；先解决药包的事，再到匪营东侧翻阅':'');row.append(h,text);body.append(row);}
    const relations=document.createElement('p');relations.className='atlas-note';relations.textContent='沈青：'+(G.f.delivered?(G.f.told?'知道你讲述的取药方式':'只知道药已送回'):'等药救人')+'。匪首：'+(G.f.branch==='B'?'记得你守约，愿意合作':G.f.branch==='A'?'被你击退，对你戒备':'尚未与你打交道')+'。陆平：'+(G.chapter.decision==='public'?'拒绝补给':G.chapter.decision==='leave'?'愿用补给送你离开':'担心账目公开')+'。许舟：'+(G.chapter.clues.includes('witness')?'已答应当面作证':'还没有对你说出亲历之事')+'。';body.append(relations);
  }
}
function mapGoals() {
  if(G.chapter.finalResolved)return [];
  if(G.chapter.decision)return [{...FINAL_POS,label:'渡口之约'}];
  if(G.inv.med)return [{...NPCS[0],label:'交药 · 沈青'}];
  if(G.f.delivered)return [{...NPCS[0],label:'决定下一步'},...(!G.chapter.clues.includes('witness')?[{...NPCS[1],label:'证词'}]:[]),...(!G.chapter.clues.includes('cart')?[{...INSPECT[1],label:'残单'}]:[]),...(!G.chapter.clues.includes('ledger')?[{...LEDGER_POS,label:'账册'}]:[])];
  if(!G.f.accepted)return [{...NPCS[0],label:'沈青'}];
  if(G.f.asked&&G.inv.herb<2)return HERBS.filter((_,i)=>!G.f.herbs[i]).map(h=>({...h,label:'止血草'}));
  return [{x:G.enemies[2].hx,y:G.enemies[2].hy,label:'匪营'}];
}
function paintMap(canvas,full) {
  const g=canvas.getContext('2d'),w=canvas.width,h=canvas.height,sx=w/WORLD.w,sy=h/WORLD.h;
  g.imageSmoothingEnabled=false;g.fillStyle='#476c50';g.fillRect(0,0,w,h);g.drawImage(MAPART,0,0,w,h);
  const dot=(x,y,col,r=2)=>{g.fillStyle='#183d2c';g.beginPath();g.arc(x*sx,y*sy,r+1,0,Math.PI*2);g.fill();g.fillStyle=col;g.beginPath();g.arc(x*sx,y*sy,r,0,Math.PI*2);g.fill();};
  for(const n of NPCS)dot(n.x,n.y,'#E2BB69',full?4:2);
  for(const e of G.enemies)if(activeFoe(e))dot(e.x,e.y,'#DF755A',full?3:1);
  if(G.f.branch&&!G.chapter.clues.includes('ledger'))dot(LEDGER_POS.x,LEDGER_POS.y,'#8CD4BC',full?4:2);
  if(G.f.asked&&!G.f.branch)HERBS.forEach((p,i)=>{if(!G.f.herbs[i])dot(p.x,p.y,'#8CD4BC',full?4:2);});
  if(full){g.font='bold 15px serif';g.fillStyle='#EFE6D2';g.fillText('青石渡',35,22);g.fillText('松风山道',w*.4,22);g.fillText('匪营',w*.8,22);}
  for(const p of mapGoals()){dot(p.x,p.y,'#E7D181',full?6:3);if(full){g.fillStyle='#10211D';g.fillRect(p.x*sx-25,p.y*sy+7,70,17);g.fillStyle='#E7D181';g.font='12px sans-serif';g.fillText(p.label,p.x*sx-21,p.y*sy+20);}}
  dot(G.p.x,G.p.y,'#12191a',full?6:3);dot(G.p.x,G.p.y,'#ffffff',full?4:2);
}
function drawMiniMap(){paintMap($('minimap'),false);const name=G.p.x<900?'青石渡':G.p.x<2400?'松风山道':'匪营';setText('regionName',name);setText('regionHint',G.chapter.finalStarted&&!G.chapter.finalResolved?'渡口风急':G.f.delivered?'药已救人，账待说清':'药船迟归');}
$('bMap').onclick=()=>toggleAtlas();$('atlasClose').onclick=()=>toggleAtlas(false);
for(const [id,name]of [['tabMap','map'],['tabSkills','skills'],['tabClues','clues']])$(id).onclick=()=>{atlasTab=name;renderAtlas();};

// ---------------------------------------------------------------- 弓手、掩体、同伴：都参与真实的伤害与胜负
function covered(x,y) {return OBST.some(b=>x>=b.x&&x<=b.x+b.w&&y>=b.y&&y<=b.y+b.h);}
function clearShot(ax,ay,bx,by){const n=Math.ceil(Math.hypot(bx-ax,by-ay)/8);for(let i=1;i<n;i++)if(covered(ax+(bx-ax)*i/n,ay+(by-ay)*i/n))return false;return true;}
function updArcher(e,dt){
  e.moving=false;if(!e.alive)return;
  if(e.state==='dying'){e.dieT-=dt;if(e.dieT<=0)e.alive=false;return;}
  e.flash=Math.max(0,e.flash-dt);if(!e.hostile)return;
  const dx=G.p.x-e.x,dy=G.p.y-e.y,d=Math.hypot(dx,dy)||1;
  if(e.state==='windup'){
    e.t+=dt;if(e.t>=e.atk.tele){G.arrows.push({x:e.x+Math.cos(e.face)*22,y:e.y+Math.sin(e.face)*22,vx:Math.cos(e.face)*310,vy:Math.sin(e.face)*310,t:2.5});e.state='recover';e.t=0;SFX.swing();}return;
  }
  if(['recover','stagger','flinch'].includes(e.state)){e.t+=dt;if(e.t>(e.state==='recover'?1.2:e.state==='stagger'?.9:.3))e.state='chase';return;}
  if(d>KIND.archer.aggro && !e.final){e.state='idle';return;}
  e.face=Math.atan2(dy,dx);e.state='chase';
  if(d<130){move(e,-dx/d*80*dt,-dy/d*80*dt,17);e.moving=true;}
  else if(d>280||!clearShot(e.x,e.y,G.p.x,G.p.y)){move(e,dx/d*90*dt,dy/d*90*dt,17);e.moving=true;}
  else{e.atk={id:'arrow',shape:'line',range:330,width:7,tele:.95,inter:true};e.state='windup';e.t=0;}
  if(e.moving)e.an+=dt;
}
function updateChapter(dt){
  const arrows=[];
  for(const a of G.arrows){
    a.t-=dt;let gone=a.t<=0;const n=Math.ceil(310*dt/6);
    for(let i=0;i<n&&!gone;i++){
      a.x+=a.vx*dt/n;a.y+=a.vy*dt/n;
      if(covered(a.x,a.y)){gone=true;G.chapter.arrowsBlocked++;burst(a.x,a.y-15,3,['#D8B66A'],50,10);}
      else if(Math.hypot(a.x-G.p.x,a.y-G.p.y)<20){gone=true;if(G.p.inv>0){G.stats.evades++;fxText(G.p.x,G.p.y-70,'闪过','#8CD4BC');}else hurtPlayer(12,a.x-a.vx,a.y-a.vy);}
    }if(!gone)arrows.push(a);
  }G.arrows=arrows;
  const ally=G.ally;
  if(ally&&!G.chapter.finalResolved){
    ally.cd=Math.max(0,ally.cd-dt);
    const foes=G.enemies.filter(e=>e.final&&activeFoe(e)).sort((a,b)=>Math.hypot(a.x-ally.x,a.y-ally.y)-Math.hypot(b.x-ally.x,b.y-ally.y));
    const target=foes[0],range=ally.id==='xu'?300:95;
    let tx=G.p.x-35,ty=G.p.y+35;
    if(target){ally.face=Math.atan2(target.y-ally.y,target.x-ally.x);if(Math.hypot(target.x-ally.x,target.y-ally.y)>range){tx=target.x;ty=target.y;}
      else if(ally.cd<=0&&clearShot(ally.x,ally.y,target.x,target.y)){ally.cd=ally.id==='xu'?1.5:1.1;target.hp-=ally.id==='xu'?8:16;target.flash=.15;G.chapter.allyHits++;G.fx.push({type:'text',x:target.x,y:target.y-80,text:ally.id==='xu'?'许舟 · 投石':'匪首 · 援剑',color:'#8CD4BC',pix:false,t:0,dur:.7});if(target.hp<=0)kill(target);}}
    const dx=tx-ally.x,dy=ty-ally.y,d=Math.hypot(dx,dy);if(d>42)move(ally,dx/d*160*dt,dy/d*160*dt,14);
  }
  if(G.chapter.finalStarted&&!G.chapter.finalResolved&&!G.enemies.some(e=>e.final&&activeFoe(e))){
    const r=commit('chapter:result','结算渡口风波',d=>Chapter.act(d,'resolve','victory'));
    if(r.ok){G.arrows=[];G.done=true;SFX.done();renderDone();}
  }
}
function drawChapterWorld(g,items,t){
  if(G.f.branch&&!G.chapter.clues.includes('ledger'))items.push({y:LEDGER_POS.y/U,d:()=>{drawArt(g,OBJ.wood,Math.round(LEDGER_POS.x/U)-(spriteW(OBJ.wood)>>1),Math.round(LEDGER_POS.y/U)-spriteH(OBJ.wood)+3);R(g,LEDGER_POS.x/U-4,LEDGER_POS.y/U-20,8,9,'#E4D5B0');line(g,LEDGER_POS.x/U-2,LEDGER_POS.y/U-17,LEDGER_POS.x/U+2,LEDGER_POS.y/U-17,'#5A4436');diamond(g,LEDGER_POS.x/U,LEDGER_POS.y/U-27,'#8CD4BC');}});
  if(!G.chapter.cache)items.push({y:CACHE_POS.y/U,d:()=>{drawArt(g,OBJ.wood,Math.round(CACHE_POS.x/U)-(spriteW(OBJ.wood)>>1),Math.round(CACHE_POS.y/U)-spriteH(OBJ.wood)+3);P(g,CACHE_POS.x/U,CACHE_POS.y/U-18,'#C1D3AC');}});
  if(G.f.delivered&&G.chapter.decision&&!G.chapter.finalStarted)items.push({y:FINAL_POS.y/U,d:()=>{drawChar(g,'lu','down','idle',FINAL_POS.x/U,FINAL_POS.y/U);diamond(g,FINAL_POS.x/U,FINAL_POS.y/U-31,'#E7D181');}});
  if(G.ally&&!G.chapter.finalResolved)items.push({y:G.ally.y/U,d:()=>{drawChar(g,G.ally.id,dirOf(G.ally.face),'idle',G.ally.x/U,G.ally.y/U);LABELS.push([G.ally.id==='xu'?'许舟 · 支援':'匪首 · 同行',G.ally.x/U,G.ally.y/U-(G.ally.id==='boss'&&BOSS.idle?46:22),'dim']);}});
  for(const a of G.arrows)items.push({y:a.y/U,d:()=>{const len=Math.hypot(a.vx,a.vy);line(g,a.x/U,a.y/U-8,(a.x-a.vx/len*20)/U,(a.y-a.vy/len*20)/U-8,'#E4CF8E');}});
}

// ---------------------------------------------------------------- 试玩记录与帧时间采样
let PERF=Playtest.createSampler(),perfCache=null,perfCacheAt=0;
function perfRec(ms){if(G.started)PERF.add(ms,frameMode());}
function perfStats(mode){return PERF.stats(mode);}
function frameMode(){if(!G.started)return 'startup';if(document.hidden)return 'background';if(G.dlg)return 'dialogue';if(G.logOpen||!$('atlas').hidden||G.done)return 'menu';if(inCombat())return 'combat';if(nearDummy())return 'practice';return G.p.moving?'move':'idle';}
function nearDummy(){return Math.hypot(G.p.x-DUMMY_POS.x,G.p.y-DUMMY_POS.y)<190;}
function trackCombat(key,n=1,state=G,orn=state.orn||'基础剑'){
  const r=Playtest.ensure(state);r.combat[key]=(r.combat[key]||0)+n;
  if(!r.byOrn)r.byOrn={};const id=orn;if(!r.byOrn[id])r.byOrn[id]={casts:0,hits:0,misses:0,noMp:0,interrupts:0,counters:0,qiReturned:0};r.byOrn[id][key]+=n;
}
let battle=null;
function finishBattle(reason='离开战斗范围'){
  if(!battle)return;
  const r=Playtest.ensure(G),delta={};for(const k of Object.keys(r.combat))delta[k]=r.combat[k]-(battle.before[k]||0);
  r.battles.push({mode:battle.mode,orn:battle.orn,skills:battle.skills,start:battle.start,end:G.time,mpBefore:battle.mp,mpAfter:G.p.mp,reason,...delta});battle=null;
}
function beginBattle(mode){battle={mode,orn:G.orn||'基础剑',skills:[...G.chapter.skills],start:G.time,mp:G.p.mp,before:{...Playtest.ensure(G).combat}};}
function startActionBattle(range){
  const mode=inCombat()?'combat':Math.hypot(G.p.x-DUMMY_POS.x,G.p.y-DUMMY_POS.y)<=Math.max(190,range+14)?'practice':G.enemies.some(e=>activeFoe(e)&&Math.hypot(e.x-G.p.x,e.y-G.p.y)<=range+KIND[e.kind].r)?'combat':null;
  if(battle&&battle.orn!==(G.orn||'基础剑'))finishBattle('更换剑饰');if(mode&&!battle)beginBattle(mode);
}
function syncBattle(){
  const mode=frameMode(),active=mode==='combat'||mode==='practice',orn=G.orn||'基础剑';
  if(battle&&(!active||battle.mode!==mode||battle.orn!==orn))finishBattle();
  if(active&&!battle)beginBattle(mode);
}
function perfText(){const s=perfStats(),combat=perfStats('combat');return s?'性能（本页前台）：'+s.frames+' 帧 / '+(s.durationMs/1000).toFixed(1)+' 秒 · p95≤'+s.p95+'ms（1ms分辨率）· 最大 '+s.max.toFixed(1)+'ms · >100ms '+s.over100+' / >200ms '+s.over200+'；战斗段 '+(combat?(combat.durationMs/1000).toFixed(1)+' 秒':'尚无样本')+(combat?.durationMs>=300000?'（样本累计≥5分钟，不代表连续实机达标）':'（不足5分钟，不能据此判定达标）'):'性能：本页尚无采样';}
function recordPayload(){
  syncBattle();const r=Playtest.ensure(G,{debug:DEBUG});
  return {build:'V0.4-songfeng-clear1-20261023',session:PAGE_SESSION,exportedAt:new Date().toISOString(),evidence:r.debugUsed?'调试记录':r.profile.operator==='真人试玩'?'真人自报、正常输入记录':r.profile.operator==='自动化输入检查'?'自动化正常输入检查':'正常入口、操作者未声明',coverage:r.coverage,record:JSON.parse(JSON.stringify(r)),progress:{branch:G.f.branch,decision:G.chapter.decision,finished:G.chapter.finalResolved,inventory:{...G.inv},ornament:G.orn,skills:[...G.chapter.skills]},performance:{scope:'本页会话；p95向上取整至1ms，计入全部前台长帧；后台及恢复跨界帧排除',all:perfStats(),combat:perfStats('combat'),practice:perfStats('practice'),move:perfStats('move'),dialogue:perfStats('dialogue'),menu:perfStats('menu'),idle:perfStats('idle')},environment:{userAgent:navigator.userAgent,viewport:[innerWidth,innerHeight],pixelRatio:devicePixelRatio,standalone:matchMedia('(display-mode: standalone)').matches},limitations:['旧存档升级前的事件不补造','正常入口不证明操作者为真人','调试记录不能作为自然试玩样本','未进行五人真实实机验收']};
}
function fmtTime(s) { const m = Math.floor(s / 60), r = Math.floor(s % 60); return m + ' 分 ' + (r < 10 ? '0' : '') + r + ' 秒'; }
function recordText() {
  const f = G.f, s = G.stats, ps = perfStats(), now = new Date(),r=Playtest.ensure(G,{debug:DEBUG});
  const pad = (n) => (n < 10 ? '0' : '') + n;
  const route = f.branch === 'A' ? 'A（武力夺回）' : f.branch === 'B' ? 'B（交涉交换）' + (f.bought ? '，买了匪首的料' : '，没买匪首的料') : '还没取回药包';
  return [
    '青石渡风波 V0.4 松风版试玩记录',
    '会话：'+PAGE_SESSION,
    '来源：'+(r.debugUsed?'调试记录，不计自然试玩':'正常输入；操作者 '+r.profile.operator)+' · 覆盖：'+(r.coverage==='legacy'?'历史存档续玩，早期事件缺失':'新局起记录'),
    '招式：施放 '+r.combat.casts+' / 有效命中 '+r.combat.hits+' / 空挥 '+r.combat.misses+' / 内力不足 '+r.combat.noMp+'；破势追击 '+r.combat.counters+' 次，返内力 '+r.combat.qiReturned.toFixed(1),
    '人工提示 '+r.prompts.length+' 次 · 卡点：'+(r.profile.difficulty||'未填写')+' · 玩家原话：'+(r.profile.observation||'未填写'),
    perfText(),
    '时间：' + now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate()) + ' ' + pad(now.getHours()) + ':' + pad(now.getMinutes()),
    '设备：屏幕 ' + innerWidth + '×' + innerHeight + ' · 像素比 ' + (window.devicePixelRatio || 1) + ' · 触屏 ' + (matchMedia('(pointer: coarse)').matches ? '是' : '否'),
    '取药方式：' + route + (s.branchAt != null ? '，第 ' + fmtTime(s.branchAt) + ' 拿到' : ''),
    '交药：' + (f.delivered ? (f.told ? '讲述了经过' : '没提细节') + '，第 ' + fmtTime(s.deliveredAt) + ' 交付' : '还没交'),
    '章节：'+(G.chapter.finalResolved?'已完成':G.chapter.decision?'渡口冲突':G.f.delivered?'查账':'取药')+' · 决定：'+(Chapter.DECISIONS[G.chapter.decision]?.name||'未决定')+' · 线索：'+G.chapter.clues.join('、'),
    '支援命中 '+G.chapter.allyHits+' 次 · 掩体挡箭 '+G.chapter.arrowsBlocked+' 次',
    '剑饰：' + (s.crafts.length ? s.crafts.join(' → ') : '没做'),
    '总用时：' + fmtTime(G.time),
    '败退 ' + f.defeats + ' 次 · 挨打 ' + s.hitsTaken + ' 次 · 闪过 ' + s.evades + ' 次 · 用掉绷带 ' + f.bandagesUsed + ' 条',
    '破势打断 ' + s.interrupts + ' 次（木人桩练习 ' + s.practice + ' 次） · 回气返还 ' + s.qiBack + ' 点 · 切磋胜 ' + f.sparWins + ' 次',
    '按剑饰汇总：'+JSON.stringify(r.byOrn||{}),
    '事务差额（历史档升级前不补造）：\n'+r.events.filter(e=>e.type==='transaction').map(e=>'#'+e.seq+' @'+e.activeSeconds+'s '+e.data.label+' '+JSON.stringify(e.data.delta)).join('\n'),
  ].join('\n');
}

// ---------------------------------------------------------------- 结算、日志
function renderDone() {
  const el = $('done'); el.hidden = !G.done; if (!G.done) return;
  const f = G.f, inv = G.inv, ps = perfStats();
  $('echo').textContent = endingText();
  $('endingTitle').textContent=G.chapter.decision==='public'?'账目见天日':G.chapter.decision==='mediate'?'渡口和约':'一船风雨';
  const rows = [
    ['渡口抉择',Chapter.DECISIONS[G.chapter.decision]?.name||'尚未决定'],
    ['最后对峙',G.chapter.peaceful?'凭证据议和':'战斗击退'],
    ['实际帮助',G.chapter.peaceful?'用证据议和，未发生战斗':(G.ally?(G.ally.id==='xu'?'许舟投石支援':'匪首并肩出剑'):'独自应对')+'；支援命中 '+G.chapter.allyHits+' 次'],
    ['取药方式', f.branch === 'A' ? 'A · 武力夺回' : 'B · 交涉交换' + (f.bought ? '，买了匪首的料' : '，没买匪首的料')],
    ['交药时', f.told ? '讲述了经过' : '没提细节'],
    ['剑饰', G.stats.crafts.length ? G.stats.crafts.join(' → ') : '没做'],
    ['铜钱 / 绷带', inv.coin + ' / ' + inv.bandage],
    ['败退 / 闪过', f.defeats + ' 次 / ' + G.stats.evades + ' 次'],
    ['破势打断', G.stats.interrupts + ' 次'],
    ['用时', fmtTime(G.time)],
    ['帧率', ps ? ps.fps.toFixed(0) + ' fps，p95 ' + ps.p95.toFixed(1) + ' ms' : '—'],
  ];
  const sum = $('sum'); sum.textContent = '';
  for (const [k, v] of rows) { const dt = document.createElement('dt'); dt.textContent = k; const dd = document.createElement('dd'); dd.textContent = v; sum.append(dt, dd); }
}
function renderLog() {
  const el = $('logp'); el.hidden = !G.logOpen; if (!G.logOpen) return;
  const ol = $('logl'); ol.textContent = '';
  for (const t of G.log) { const li = document.createElement('li'); li.textContent = t; ol.appendChild(li); }
  $('logEmpty').hidden = G.log.length > 0;
  $('rec').textContent = recordText();
  const r=Playtest.ensure(G);for(const el of document.querySelectorAll('[data-profile]'))if(document.activeElement!==el)el.value=r.profile[el.dataset.profile]||'';
  $('promptCount').textContent='已记录人工提示 '+r.prompts.length+' 次；没有人工提示就不添加。';
  $('bPerf').textContent = G.ui.perf ? '隐藏帧率' : '显示帧率';
  $('recTa').hidden = true;
}

// ---------------------------------------------------------------- 输入
const keys = new Set();
const MOVE = { KeyW: [0, -1], KeyS: [0, 1], KeyA: [-1, 0], KeyD: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] };
addEventListener('keydown', (e) => {
  if(e.target.matches?.('input,textarea,select'))return;
  if (e.code === 'Space' || e.code.startsWith('Arrow')) e.preventDefault();
  if (G.dlg) {
    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= G.dlg.opts.length) doAct(G.dlg.opts[n - 1].key);
    else if (e.code === 'Escape') { const c = G.dlg.opts.find((o) => o.key === 'close'); if (c) doAct('close'); }
    return;
  }
  if(!$('atlas').hidden){if(e.code==='Escape'||e.code==='KeyM')toggleAtlas(false);return;}
  if(e.code==='Escape'&&G.started&&!G.dlg&&!G.logOpen&&$('atlas').hidden){pauseGame(!G.manualPaused);return;}
  if (G.logOpen && e.code === 'Escape') { toggleLog(false); return; }
  if (MOVE[e.code]) { keys.add(e.code); return; }
  if (e.repeat) return;
  if(e.code==='KeyM'){toggleAtlas();return;}
  if (['KeyJ','KeyK','KeyI','Space','KeyL'].includes(e.code)){keys.add(e.code);pending[({KeyJ:'attack',KeyK:'skill',KeyI:'skill2',Space:'dodge',KeyL:'dodge'})[e.code]]=.14;startAudio();}
  else if (e.code === 'KeyE' || e.code === 'Enter') interact();
  else if (e.code === 'KeyH') useBandage();
});
addEventListener('keyup', (e) => keys.delete(e.code));
function resetInput(){keys.clear();heldActions.clear();for(const key of Object.keys(pending))pending[key]=0;combatEvents.length=0;combatAudio?.stop();stick.id=null;stick.dx=stick.dy=0;stickHome();document.querySelectorAll('.press').forEach(e=>e.classList.remove('press'));}
addEventListener('blur',resetInput);
document.addEventListener('visibilitychange',()=>{if(document.hidden)finishBattle('切到后台');PERF.visibility(document.hidden);resetInput();if(G.started){Playtest.event(G,document.hidden?'background':'foreground');saveNow(false);}});
addEventListener('pagehide',()=>{if(G.started){finishBattle('页面离开');saveNow(false);}});

const heldActions=new Map(), pending={attack:0,skill:0,skill2:0,dodge:0};
const actionCodes={attack:['KeyJ'],skill:['KeyK'],skill2:['KeyI'],dodge:['Space','KeyL']};
const heldCombat=name=>[...heldActions.values()].includes(name)||actionCodes[name].some(code=>keys.has(code));
function pauseGame(on=true){G.manualPaused=on;if(on)music?.stop();$('pauseMenu').hidden=!on;resetInput();}
$('bPause').onclick=()=>pauseGame();$('bResume').onclick=()=>{pauseGame(false);startAudio();};
$('bPauseMap').onclick=()=>{if(inCombat()){let note=$('pauseMenu').querySelector('.battle-help');if(!note){note=document.createElement('p');note.className='battle-help';$('bPauseMap').after(note);}note.textContent='战斗中无法查看手记或换招，先脱身。';return;}pauseGame(false);toggleAtlas(true);};
$('bPauseFull').onclick=()=>{
  let note=$('pauseMenu').querySelector('.full-help');
  if(!note){note=document.createElement('p');note.className='full-help';$('bPauseFull').after(note);}
  note.textContent=standaloneMode()?'已在主屏幕模式中。':fullscreenRequest()?'已向浏览器请求全屏；若未进入，可继续横屏试玩。':'这个浏览器不提供网页全屏；iPhone 可分享→添加到主屏幕后横屏打开。';
  if(!standaloneMode())$('bFull').click();
};
$('bSound').onclick=()=>{if(soundEnabled&&AC&&AC.state!=='running')startAudio();else setSound(!soundEnabled);};
$('bStartSound').onclick=()=>setSound(!soundEnabled);
addEventListener('blur',()=>{if(G.started&&!paused())pauseGame();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)return;combatAudio?.stop();music?.stop();combatEvents.length=0;AC?.suspend().catch(()=>{});if(G.started)pauseGame();});
addEventListener('orientationchange',()=>{if(G.started&&innerHeight>innerWidth)pauseGame();});
const stick = { id: null, ox: 0, oy: 0, dx: 0, dy: 0 };
const zone = $('stickzone'), stickEl = $('stick'), knob = $('knob');
function stickHome() {
  const r = app.getBoundingClientRect();
  stickEl.style.left = '90px'; stickEl.style.top = (r.height - 86) + 'px'; knob.style.transform = '';
  stickEl.style.opacity = '0.8';
}
zone.addEventListener('pointerdown', (e) => {
  if (stick.id !== null || !canAct()) return;
  e.preventDefault();
  stick.id = e.pointerId; try { zone.setPointerCapture(e.pointerId); } catch (err) { /* 老浏览器 */ }
  const r = app.getBoundingClientRect();
  stick.ox = e.clientX; stick.oy = e.clientY;
  stickEl.style.left = (e.clientX - r.left) + 'px'; stickEl.style.top = (e.clientY - r.top) + 'px'; stickEl.style.opacity = '1';
  stick.dx = stick.dy = 0;
});
zone.addEventListener('pointermove', (e) => {
  if (e.pointerId !== stick.id) return;
  let dx = e.clientX - stick.ox, dy = e.clientY - stick.oy; const l = Math.hypot(dx, dy), max = 45;
  if (l > max) { dx = (dx / l) * max; dy = (dy / l) * max; }
  stick.dx = dx / max; stick.dy = dy / max;
  knob.style.transform = 'translate(' + (Math.round(dx / 3) * 3) + 'px,' + (Math.round(dy / 3) * 3) + 'px)';
});
function stickEnd(e) { if (e.pointerId !== stick.id) return; stick.id = null; stick.dx = stick.dy = 0; stickHome(); }
zone.addEventListener('pointerup', stickEnd);
zone.addEventListener('pointercancel', stickEnd);
function bindBtn(el, fn) {
  el.addEventListener('pointerdown', (e) => { e.preventDefault(); e.stopPropagation(); el.classList.add('press'); fn(); });
  const up = () => el.classList.remove('press');
  el.addEventListener('pointerup', up); el.addEventListener('pointerleave', up); el.addEventListener('pointercancel', up);
  el.addEventListener('click', (e) => { if (e.detail === 0) fn(); });
}
for(const [id,action] of [['bAtk','attack'],['bSk','skill'],['bSk2','skill2'],['bDg','dodge']]){
  const el=$(id);el.addEventListener('pointerdown',e=>{if(!canAct())return;e.preventDefault();e.stopPropagation();el.setPointerCapture(e.pointerId);heldActions.set(e.pointerId,action);pending[action]=.14;el.classList.add('press');startAudio();});
  const release=e=>{heldActions.delete(e.pointerId);el.classList.remove('press');if(e.type==='pointercancel')pending[action]=0;};
  for(const event of ['pointerup','pointercancel','lostpointercapture'])el.addEventListener(event,release);
  el.addEventListener('click',e=>{if(e.detail===0)pending[action]=.14;});
}
bindBtn($('interact'), interact);
bindBtn($('nearTalk'),interact);
// iOS 的双击缩放不能只依赖 CSS；这些控件已经在 pointerdown 执行动作。
for(const type of ['touchstart','touchend','dblclick'])app.addEventListener(type,e=>{
  if(e.cancelable&&e.target.closest('#pad,#stickzone,#cv,#interact,#nearTalk'))e.preventDefault();
},{passive:false});
// 其余区域（小地图下的信息栏、HUD 空白间隙等）不拦单击和滚动，只拦快速的第二下，防双击缩放（#9）。
// 按钮和输入框不拦，否则会吞掉它们的 click；按钮靠 CSS 的 touch-action 防缩放。
let lastTapEnd=-1e9;
app.addEventListener('touchend',e=>{
  const quick=e.timeStamp-lastTapEnd<350;lastTapEnd=e.timeStamp;
  if(quick&&e.cancelable&&!e.touches?.length&&!e.target.closest('button,a,input,select,textarea,[contenteditable]'))e.preventDefault();
},{passive:false});
app.addEventListener('dblclick',e=>{if(e.cancelable)e.preventDefault();});
$('bBand').addEventListener('click', useBandage);
function toggleLog(on) { G.logOpen = on === undefined ? !G.logOpen : on;resetInput();renderLog(); }
$('bLog').addEventListener('click', () => { SFX.ui(); toggleLog(); });
$('logx').addEventListener('click', () => toggleLog(false));
$('bPerf').addEventListener('click', () => { G.ui.perf = !G.ui.perf; renderLog(); });
$('bCopy').addEventListener('click', () => {
  const text = recordText();
  const fallback = () => { const ta = $('recTa'); ta.hidden = false; ta.value = text; ta.focus(); ta.select(); toast('复制不了，已经全选，手动复制即可'); };
  try { navigator.clipboard.writeText(text).then(() => toast('试玩记录已复制'), fallback); } catch (e) { fallback(); }
});
function startAudio() {
  if(!soundEnabled)return;
  try {
    if(!AC){AC=new (window.AudioContext||window.webkitAudioContext)();AC.onstatechange=renderSound;}
    combatAudio ||= createCombatAudio(AC);music ||= createMusic(AC);
    if(AC.state!=='running')AC.resume().then(renderSound,()=>{renderSound();if(!audioWarned){audioWarned=true;toast('浏览器没有放行声音，点右上角「音」再试');}});
  } catch { soundEnabled=false;toast('当前浏览器无法开启声音'); }
  renderSound();
}
function setSound(on) {
  soundEnabled=on;try{localStorage.setItem(SOUND_KEY,on?'on':'off');}catch{}
  if(on){audioWarned=false;startAudio();}else{combatAudio?.stop();music?.stop();combatEvents.length=0;}
  renderSound();
}
// 想开但浏览器还没放行（挂起、切后台回来）时显示「停」，点一下恢复，不假装已经在响。
function renderSound() {
  const state=!soundEnabled?'off':AC&&AC.state!=='running'?'blocked':'on';
  $('bSound').innerHTML='音<span>'+{off:'关',blocked:'停',on:'开'}[state]+'</span>';
  $('bSound').dataset.sound=state;
  $('bSound').setAttribute('aria-label',{off:'开启声音',blocked:'声音被浏览器暂停，点此恢复',on:'关闭声音'}[state]);
  $('bStartSound').textContent=soundEnabled?'声音：开':'声音：关（点此开启）';
  $('bStartSound').setAttribute('aria-pressed',String(soundEnabled));
  $('soundHint').textContent=soundEnabled?'进入后播放出剑、预警与命中音效；右上角「音」可随时静音。':'当前静音。想听出剑、预警与命中音效，先点「声音」开启。';
}
function begin() {
  G.manualPaused=false;$('pauseMenu').hidden=true;resetInput();combatArt.reset();
  Playtest.ensure(G,{debug:DEBUG});Playtest.event(G,'session_start',{session:PAGE_SESSION});
  startAudio(); G.started = true; $('start').hidden = true;saveNow(false);
  if (!G.f.accepted) tip('move', '左半边按住拖动来走（键盘 WASD）。先去找渡口的沈青，她头顶有金色记号');
  else toast('继续上次的进度');
}
$('bStart').addEventListener('click', begin);
renderSound();
let newArmed = false;
$('bNew').addEventListener('click', () => {
  if (!newArmed) { newArmed = true; $('bNew').textContent = '确定清空进度？'; return; }
  if(!clearSave())return; G = newGame();PERF=Playtest.createSampler();battle=null;perfCache=null;perfCacheAt=0; newArmed = false; $('bNew').hidden = true; $('bNew').textContent = '重新开始'; $('bStart').textContent = '踏入青石渡'; $('saveHint').textContent = ''; begin(); renderAll();
});
function standaloneMode(){return navigator.standalone===true||matchMedia('(display-mode: standalone)').matches;}
function fullscreenElement(){return document.fullscreenElement||document.webkitFullscreenElement;}
function fullscreenRequest(){const el=document.documentElement;return el.requestFullscreen||el.webkitRequestFullscreen||el.webkitRequestFullScreen;}
function fullscreenHelp(message){
  const hint=$('fullHint');hint.hidden=false;
  hint.textContent=message+' iPhone / Chrome：点地址栏的「分享」→「添加到主屏幕」，如有「作为 Web App 打开」请保持开启；再从桌面图标打开并横屏使用，可隐藏浏览器地址栏。桌面模式可能需要重新登录，存档不保证与浏览器互通。';
}
function syncFullscreen(){
  const standalone=standaloneMode();
  $('bFull').disabled=standalone;
  $('bFull').textContent=standalone?'已在桌面模式':fullscreenElement()?'退出全屏':fullscreenRequest()?'全屏':'全屏说明';
}
$('bFull').addEventListener('click',async()=>{
  if(standaloneMode())return;
  const el=document.documentElement,request=fullscreenRequest();
  if(!request){fullscreenHelp('这个浏览器未提供网页全屏。');return;}
  try{
    if(fullscreenElement())await (document.exitFullscreen||document.webkitExitFullscreen).call(document);
    else await request.call(el);
    $('fullHint').hidden=true;syncFullscreen();
  }catch(e){fullscreenHelp('未能进入全屏，请在浏览器中打开游戏后重试。');}
});
document.addEventListener('fullscreenchange',syncFullscreen);
document.addEventListener('webkitfullscreenchange',syncFullscreen);
syncFullscreen();
$('bMore').addEventListener('click', () => { G.done = false; renderDone(); });
$('bAgain').addEventListener('click', () => { if(!clearSave())return; G = newGame();PERF=Playtest.createSampler();battle=null;perfCache=null;perfCacheAt=0; G.started = true; renderAll(); saveNow(false); });

// ---------------------------------------------------------------- 更新
function update(dt) {
  G.time += dt;
  if(heldCombat('attack')||pending.attack>0)attack();
  for(const [name,slot] of [['skill',0],['skill2',1]])if((heldCombat(name)||pending[name]>0)&&G.chapter.cooldowns[slot]<=0){
    if(G.p.mp>=Chapter.SKILLS[G.chapter.skills[slot]].cost){skill(slot);pending[name]=0;}
    else if(pending[name]>0){skill(slot);pending[name]=0;}
  }
  if(heldCombat('dodge')||pending.dodge>0)dodge();
  for(const key of Object.keys(pending))pending[key]=Math.max(0,pending[key]-dt);
  const p = G.p;
  for (const k of ['atkCd', 'skCd', 'dgCd', 'inv', 'swing', 'hurt', 'comboT']) p[k] = Math.max(0, p[k] - dt);
  G.shake = Math.max(0, G.shake - dt * 14);
  if (G.deadT > 0) {
    G.deadT -= dt;
    if (G.deadT <= 0.8 && !G.respawned) { respawn(); G.respawned = true; }
    if (G.deadT < 0) G.deadT = 0;
    updFx(dt); return;
  }
  let ix = stick.dx, iy = stick.dy;
  for (const k of keys) { const m = MOVE[k]; if (m) { ix += m[0]; iy += m[1]; } }
  const il = Math.hypot(ix, iy); if (il > 1) { ix /= il; iy /= il; }
  p.ix = ix; p.iy = iy; p.moving = false;
  p.sp=Math.min(100,p.sp+21*dt);
  p.mp = Math.min(p.maxMp, p.mp + (inCombat()||nearDummy()?1.5:P_.mpRegen) * dt);
  G.chapter.cooldowns=G.chapter.cooldowns.map(n=>Math.max(0,n-dt));
  if (p.dodge > 0) {
    p.dodge -= dt; move(p, p.dvx * dt, p.dvy * dt, 16);
  } else if (Math.hypot(ix, iy) > 0.08) {
    const slow = p.swing > 0 ? 0.35 : 1;
    move(p, ix * P_.speed * slow * dt, iy * P_.speed * slow * dt, 16);
    if (p.swing <= 0) p.face = Math.atan2(iy, ix);
    p.moving = true; p.an += dt * Math.min(1, Math.hypot(ix, iy) * 1.3);
  }
  p.trail=[];
  updateStrikes(dt);
  for (const e of G.enemies) updEnemy(e, dt);
  updateChapter(dt);
  updDummy(dt);
  separate();
  updFx(dt);
  if (p.hp < 50 && !inCombat() && G.inv.bandage > 0) tip('bandage', '右上角的绷带可以包扎（H）；回青石渡找沈青能免费包扎');
  if (G.started && Math.floor(G.time / 15) !== Math.floor((G.time - dt) / 15)) saveNow(false);
}
function updFx(dt) {
  G.fx = G.fx.filter((f) => {
    f.t += dt;
    if (f.type === 'pt') { f.x += f.vx * dt; f.y += f.vy * dt; f.vy += 300 * dt; f.vx *= 0.92; }
    return f.t < f.dur;
  });
}

// ---------------------------------------------------------------- 绘制：场景缓冲与屏幕像素一致，逻辑地图尺寸不变
let DPR = 1, VW = 0, VH = 0, Z = 3;
const BUF = cnv(1, 1), bg = BUF.getContext('2d');
const LBUF = cnv(1, 1), lgc = LBUF.getContext('2d');
const AMB = [];
// 光照：越往山里越暗（青石渡傍晚、山道薄暮、匪营入夜），灯笼、营火、铁匠铺和人物身边各有一圈暖光
function ambientAt(px) { return px < 240 ? .035 : px < 300 ? .035 + ((px - 240) / 60) * .025 : px < 760 ? .06 : px < 840 ? .06 + ((px - 760) / 80) * .06 : .12; }
function lightPass(g, ox, oy, BW, BH, t) {
  const lights = [];
  for (const [k, x, y] of PROPS) if (k === 'lantern') lights.push({ x: x + (OBJ.lantern.width > 9 ? 11 : 7), y: y + (OBJ.lantern.width > 9 ? 14 : 18), r: 30, cut: 0.95, col: [255, 170, 90], a: 0.2 + 0.03 * Math.sin(t * 7 + x) });
  lights.push({ x: FIREPOS[0] + 8, y: FIREPOS[1] + 10, r: 58 + Math.sin(t * 11) * 2, cut: 1, col: [255, 150, 70], a: 0.32 });
  lights.push({ x: 153, y: 222, r: 22, cut: 0.7, col: [255, 140, 80], a: 0.16 });
  lights.push({ x: Math.round(G.p.x / U), y: Math.round(G.p.y / U) - 8, r: 36, cut: 0.6 });
  for (const e of G.enemies) if (e.alive && e.state === 'windup') lights.push({ x: e.x / U, y: e.y / U - 6, r: 26, cut: 0.5, col: [255, 80, 50], a: 0.28 * clamp(e.t / e.atk.tele, 0.3, 1) });
  if (G.f.asked && !G.inv.med && G.f.branch === null) HERBS.forEach((h, i) => { if (!G.f.herbs[i]) lights.push({ x: h.x / U, y: h.y / U - 5, r: 14, cut: 0.5, col: [127, 208, 190], a: 0.22 }); });
  lgc.globalCompositeOperation = 'source-over'; lgc.clearRect(0, 0, BW, BH);
  const grad = lgc.createLinearGradient(0, 0, BW, 0);
  for (let i = 0; i <= 8; i++) grad.addColorStop(i / 8, 'rgba(14,10,30,' + ambientAt(ox + (i / 8) * BW).toFixed(3) + ')');
  lgc.fillStyle = grad; lgc.fillRect(0, 0, BW, BH);
  lgc.globalCompositeOperation = 'destination-out';
  for (const L of lights) {
    const x = L.x - ox, y = L.y - oy; if (x < -L.r || y < -L.r || x > BW + L.r || y > BH + L.r) continue;
    const rg = lgc.createRadialGradient(x, y, 0, x, y, L.r); rg.addColorStop(0, 'rgba(0,0,0,' + L.cut + ')'); rg.addColorStop(1, 'rgba(0,0,0,0)');
    lgc.fillStyle = rg; lgc.fillRect(x - L.r, y - L.r, L.r * 2, L.r * 2);
  }
  g.drawImage(LBUF, 0, 0);
  g.globalCompositeOperation = 'lighter';
  for (const L of lights) {
    if (!L.col) continue;
    const x = L.x - ox, y = L.y - oy; if (x < -L.r || y < -L.r || x > BW + L.r || y > BH + L.r) continue;
    const rg = g.createRadialGradient(x, y, 0, x, y, L.r * 0.8); rg.addColorStop(0, 'rgba(' + L.col.join(',') + ',' + L.a.toFixed(3) + ')'); rg.addColorStop(1, 'rgba(' + L.col.join(',') + ',0)');
    g.fillStyle = rg; g.fillRect(x - L.r, y - L.r, L.r * 2, L.r * 2);
  }
  g.globalCompositeOperation = 'source-over';
}
let ambT = 0;
function resize() {
  const viewport=window.visualViewport;
  app.style.setProperty('--app-width',Math.round(viewport?viewport.width:innerWidth)+'px');
  app.style.setProperty('--app-height',Math.round(viewport?viewport.height:innerHeight)+'px');
  DPR = window.devicePixelRatio || 1;
  VW = app.clientWidth; VH = app.clientHeight;
  cv.width = Math.max(1, Math.round(VW * DPR)); cv.height = Math.max(1, Math.round(VH * DPR));
  Z = clamp(Math.round(VH / 170), 2, 5);
  BUF.width=cv.width;BUF.height=cv.height;
  LBUF.width=Math.ceil(VW/Z)+1;LBUF.height=Math.ceil(VH/Z)+1;
  if (stick.id === null) stickHome();
}
addEventListener('resize', resize);
window.visualViewport?.addEventListener('resize',resize);
addEventListener('orientationchange',()=>requestAnimationFrame(resize));
addEventListener('pageshow',resize);
function pxCircle(g, cx, cy, r, col, step) { g.fillStyle = col; const n = Math.max(12, Math.round(r * 6)); for (let i = 0; i < n; i += step || 1) { const a = (i / n) * Math.PI * 2; g.fillRect(Math.round(cx + Math.cos(a) * r), Math.round(cy + Math.sin(a) * r), 1, 1); } }
function drawZonePx(g, ex, ey, a, face, prog, solid) {
  const range = Math.round(a.range / U), half = a.half || Math.PI, wid = a.width ? a.width / U : 0;
  const lim = range + 2;
  const c = Math.cos(face), s = Math.sin(face);
  for (let yy = -lim; yy <= lim; yy++) for (let xx = -lim; xx <= lim; xx++) {
    let inside, edge, depth;
    if (a.shape === 'line') {
      const along = xx * c + yy * s, across = Math.abs(-xx * s + yy * c);
      inside = along >= 0 && along <= range && across <= wid; if (!inside) continue;
      edge = across > wid - 1 || along > range - 1 || along < 1; depth = along / range;
    } else {
      const d = Math.hypot(xx, yy); if (d > range || d < 1.5) continue;
      const ad = a.shape === 'cone' ? angDiff(Math.atan2(yy, xx), face) : 0; if (ad > half) continue;
      edge = d > range - 1.2 || (a.shape === 'cone' && ad > half - 1.2 / Math.max(d, 1)); depth = d / range;
    }
    const x = ex + xx, y = ey + yy;
    if (solid) { if ((xx + yy) % 2 === 0) { g.fillStyle = 'rgba(242,120,90,0.8)'; g.fillRect(x, y, 1, 1); } continue; }
    if (edge) { g.fillStyle = '#E0603F'; g.fillRect(x, y, 1, 1); continue; }
    if (depth <= prog) { g.fillStyle = (xx + yy) % 2 === 0 ? 'rgba(224,96,63,0.85)' : 'rgba(224,96,63,0.35)'; g.fillRect(x, y, 1, 1); }
    else if ((xx + yy) % 2 === 0 && yy % 2 === 0) { g.fillStyle = 'rgba(224,96,63,0.75)'; g.fillRect(x, y, 1, 1); }
  }
}
function drawBang(g, x, y, col) { fc(g, x, y, 4, col || '#E0603F'); R(g, x, y - 2, 1, 3, '#14110E'); P(g, x, y + 2, '#14110E'); pxCircle(g, x, y, 5, INK); }
function diamond(g, x, y, col) { R(g, x - 1, y - 3, 3, 1, col); R(g, x - 2, y - 2, 5, 1, col); R(g, x - 3, y - 1, 7, 1, col); R(g, x - 2, y, 5, 1, col); R(g, x - 1, y + 1, 3, 1, col); P(g, x, y - 4, INK); P(g, x, y + 2, INK); P(g, x - 4, y - 1, INK); P(g, x + 4, y - 1, INK); }
const LABELS = [];
let hudRects = [];
function draw(realT) {
  const shake=combatArt.prepare(G,paused(),realT),p = G.p, g = bg, BW = VW/Z, BH = VH/Z, scale=Z*DPR, t = G.started ? G.time : realT;
  let ox=p.x/U-BW/2,oy=p.y/U-BH/2;
  // 镜头不出地图：地图比画面宽（高）时夹在边内，比画面小就居中
  const MW = MAP_W * 16, MH = MAP_H * 16;
  ox = BW < MW ? clamp(ox, 0, MW - BW) : (MW-BW)/2; oy=BH<MH?clamp(oy,0,MH-BH):(MH-BH)/2;
  const motionScale=matchMedia('(prefers-reduced-motion: reduce)').matches?.25:1;ox+=shake.x/U*motionScale;oy+=shake.y/U*motionScale;
  ox=Math.round(ox*scale)/scale;oy=Math.round(oy*scale)/scale;
  g.setTransform(1,0,0,1,0,0);g.globalAlpha=1;g.globalCompositeOperation='source-over';
  g.fillStyle='#0E0B09';g.fillRect(0,0,BUF.width,BUF.height);
  g.setTransform(scale,0,0,scale,0,0);g.imageSmoothingEnabled=false;
  const wf = Math.floor(t * 2) % 3, c0 = Math.floor(ox / 16), r0 = Math.floor(oy / 16);
  for (let r = r0; r <= r0 + Math.ceil(BH / 16) + 1; r++) for (let c = c0; c <= c0 + Math.ceil(BW / 16) + 1; c++) if (r < 0 || c < 0 || r >= MAP_H || c >= MAP_W) g.drawImage(tileAt(c, r, wf), c * 16 - ox, r * 16 - oy);
  g.drawImage(MAPBG[wf], -ox, -oy);
  g.translate(-ox, -oy);
  const f = G.f, inv = G.inv;
  g.fillStyle = 'rgba(224,96,63,0.5)';
  for (let i = 0; i < 90; i += 2) { const a = (i / 90) * Math.PI * 2; g.fillRect(Math.round(ZONE.x / U + Math.cos(a) * 58), Math.round(ZONE.y / U + Math.sin(a) * 45), 1, 1); }
  if (f.asked && !inv.med && f.branch === null) HERBS.forEach((h, i) => { if (!f.herbs[i]) pxCircle(g, h.x / U, h.y / U - 4, 9 + Math.floor((t * 4 + i) % 3), 'rgba(127,208,190,0.85)', 2); });
  for (const e of G.enemies) if (e.alive && e.state === 'windup') drawZonePx(g, Math.round(e.x / U), Math.round(e.y / U), e.atk, e.face, clamp(e.t / e.atk.tele, 0, 1), false);
  if (G.dummy.state === 'windup') drawZonePx(g, Math.round(DUMMY_POS.x / U), Math.round(DUMMY_POS.y / U), G.dummy.atk, G.dummy.face, clamp(G.dummy.t / G.dummy.atk.tele, 0, 1), false);
  for (const fx of G.fx) if (fx.type === 'zone' && Math.floor(fx.t * 30) % 2 === 0) drawZonePx(g, Math.round(fx.x / U), Math.round(fx.y / U), fx, fx.face, 1, true);
  const items = [];
  drawChapterWorld(g, items, t);
  for (const [k, x, y] of PROPS) { const im = k==='tree2'&&x%3===0?OBJ.bamboo:OBJ[k], [baseX,baseY] = propXY(k,x,y),dx=baseX+(spriteW(OBJ[k])-spriteW(im))/2,dy=baseY+spriteH(OBJ[k])-spriteH(im); items.push({ y: SIZE[k] ? y + SIZE[k][1] : dy + spriteH(im), d: () => drawArt(g,im,dx,dy) }); }
  items.push({y:FIREPOS[1]+22,d:()=>{g.globalAlpha=.9+Math.sin(t*8)*.1;drawArt(g,OBJ.firepit,FIREPOS[0]-4,FIREPOS[1]-6);g.globalAlpha=1;}});
  { const dd = G.dummy, dx = Math.round(DUMMY_POS.x / U), dy = Math.round(DUMMY_POS.y / U); items.push({ y: dy, d: () => { const wob = dd.state === 'stagger' ? Math.round(Math.sin(t * 30)) : dd.state === 'windup' ? -1 : 0; drawArt(g,dd.hit > 0 ? OBJ.dummyHit : OBJ.dummy, dx - 9 + wob, dy - 23); if (dd.state === 'windup') { drawBang(g, dx, dy - 31); if (G.orn === '破势') LABELS.push(['可打断', dx, dy - 40, 'red']); } LABELS.push(['木人桩', dx, dy - 27, 'dim']); } }); }
  if (!f.matPicked) items.push({ y: CRATE.y / U + 2, d: () => { drawArt(g,OBJ.wood, Math.round(CRATE.x / U) - (spriteW(OBJ.wood) >> 1), Math.round(CRATE.y / U) - spriteH(OBJ.wood) + 2); diamond(g, Math.round(CRATE.x / U), Math.round(CRATE.y / U) - 20 - (Math.floor(t * 2) % 2), '#D8B66A'); } });
  if (f.asked && !inv.med && f.branch === null) HERBS.forEach((h, i) => { if (!f.herbs[i]) items.push({ y: h.y / U, d: () => drawArt(g,OBJ.herb, Math.round(h.x / U) - (spriteW(OBJ.herb) >> 1), Math.round(h.y / U) - spriteH(OBJ.herb) + 1) }); });
  LABELS.length = 0;
  for (const it of INSPECT) if (!f.inspected[it.id] && it.id !== 'sign') items.push({ y: it.y / U + 1, d: () => { P(g, Math.round(it.x / U), Math.round(it.y / U) - 26 - (Math.floor(t * 2) % 2), '#F2D27A'); P(g, Math.round(it.x / U), Math.round(it.y / U) - 28 - (Math.floor(t * 2) % 2), '#F2D27A'); P(g, Math.round(it.x / U), Math.round(it.y / U) - 29 - (Math.floor(t * 2) % 2), '#F2D27A'); } });
  for (const n of NPCS.filter(n=>!(G.ally?.id===n.id&&!G.chapter.finalResolved))) items.push({ y: n.y / U, d: () => {
    const near = Math.hypot(p.x - n.x, p.y - n.y) < 220;
    drawChar(g, n.id, near ? dirOf(Math.atan2(p.y - n.y, p.x - n.x)) : 'down', 'idle', n.x / U, n.y / U);
    LABELS.push([n.name, n.x / U, n.y / U - 22]);
    const mark = (n.id === 'shen' && (!f.accepted || inv.med)) || (n.id === 'zhou' && !G.orn && inv.wood >= 2 && inv.iron >= 1);
    if (mark) diamond(g, Math.round(n.x / U), Math.round(n.y / U) - 36 - (Math.floor(t * 2) % 2), '#D8B66A');
  } });
  for (const e of G.enemies) {
    if (!e.alive || (e.kind==='boss'&&G.ally?.id==='boss'&&!G.chapter.finalResolved)) continue;
    items.push({ y: e.y / U, d: () => {
      const K = KIND[e.kind], ex = e.x / U, ey = e.y / U;
      combatArt.enemy(g,e,U);
      if(e.state==='dying')return;
      if(e.state==='down'){LABELS.push(['匪首',ex,ey-24]);return;}
      const bossArt=e.kind==='boss';
      const top = Math.round(ey) - (bossArt ? 32 : 19);
      if (e.kind === 'boss' && !e.hostile) LABELS.push(['匪首', ex, ey - (bossArt ? 34 : 25)]);
      else if (e.hostile && e.kind !== 'boss' && e.hp < K.hp) {
        const w = 14, x0 = Math.round(ex - w / 2);
        R(g, x0 - 1, top - 1, w + 2, 4, INK); R(g, x0, top, w, 2, '#3B2F28'); R(g, x0, top, Math.max(0, Math.round(w * e.hp / K.hp)), 2, '#D9553A'); R(g, x0, top, Math.max(0, Math.round(w * e.hp / K.hp)), 1, '#F08A6A');
      }
      if (e.kind === 'boss' && !e.hostile && f.accepted && !inv.med && f.branch === null) diamond(g, Math.round(ex), top - 15 - (Math.floor(t * 2) % 2), '#E0603F');
      if(e.kind!=='boss')LABELS.push([K.name,ex,ey-28,e.kind==='archer'?'red':'dim']);
      if (e.state === 'windup') {
        drawBang(g, Math.round(ex), top - 8, e.atk.inter ? '#E0603F' : '#F2A03C');
        if (e.atk.inter && G.orn === '破势') LABELS.push(['可打断', ex, ey - (bossArt ? 44 : 30), 'red']);
      }
      if (e.state === 'stagger') for (let k = 0; k < 3; k++) { const a = t * 6 + k * 2.1; P(g, Math.round(ex + Math.cos(a) * 7), Math.round(top - 2 + Math.sin(a) * 2), '#F2D27A'); }
    } });
  }
  items.push({y:p.y/U,d:()=>combatArt.hero(g,G,U)});
  items.sort((a, b) => a.y - b.y).forEach((it) => it.d());
  combatArt.effects(g,G,U);
  for (const fx of G.fx) if (fx.type === 'pt') { g.globalAlpha = Math.max(0, 1 - fx.t / fx.dur); g.fillStyle = fx.col; g.fillRect(Math.round(fx.x / U), Math.round(fx.y / U), 1, 1); }
  g.globalAlpha = 1;
  // 命中闪光：两道交叉的黄白光条
  for (const fx of G.fx) if (fx.type === 'streak') {
    const k = fx.t / fx.dur, cx = Math.round(fx.x / U), cy = Math.round(fx.y / U), L = fx.len * (0.6 + 0.4 * k);
    for (const [da, col] of [[0, '#FFF59A'], [1.9, '#F2A03C']]) {
      const a = fx.a + da, dx = Math.cos(a) * L / 2, dy = Math.sin(a) * L / 2;
      g.globalAlpha = 1 - k; line(g, cx - dx, cy - dy, cx + dx, cy + dy, col); if (da === 0) line(g, cx - dx, cy - dy + 1, cx + dx, cy + dy + 1, '#FFFFFF');
    }
    g.globalAlpha = 1;
  }
  ambT += 1 / 60;
  if (ambT > 0.4) { ambT = 0; AMB.push({ x: 164 + Math.random() * 2, y: 189, t: 0, dur: 2.2, vx: 2 + Math.random() * 3 }); }
  for (let i = AMB.length - 1; i >= 0; i--) { const a = AMB[i]; a.t += 1 / 60; if (a.t > a.dur) { AMB.splice(i, 1); continue; } const k = a.t / a.dur; g.fillStyle = 'rgba(190,184,172,' + (0.45 * (1 - k)) + ')'; const s = 1 + Math.floor(k * 3); g.fillRect(Math.round(a.x + a.vx * a.t * 3), Math.round(a.y - a.t * 9), s, s); }
  g.setTransform(scale,0,0,scale,0,0);
  lightPass(g, ox, oy, BW, BH, t);

  ctx.setTransform(1,0,0,1,0,0);ctx.globalAlpha=1;ctx.globalCompositeOperation='copy';
  ctx.drawImage(BUF,0,0);ctx.globalCompositeOperation='source-over';
  ctx.setTransform(DPR,0,0,DPR,0,0);
  const sx = (x) => (x - ox) * Z, sy = (y) => (y - oy) * Z;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  const blocked = (X, Y, w, h) => hudRects.some((r) => X < r.right && X + w > r.left && Y < r.bottom && Y + h > r.top);
  for (const [text, x, y, kind] of LABELS) {
    ctx.font = '700 13px ' + SERIF; const w = Math.ceil(ctx.measureText(text).width) + 14, X = Math.round(sx(x) - w / 2), Y = Math.round(sy(y) - 22);
    if (blocked(X,Y,w,22)) continue;
    ctx.fillStyle='rgba(16,42,34,.82)';ctx.fillRect(X-2,Y-1,w+4,24);ctx.fillStyle=kind==='red'?'#cf9870':'#b8b68b';ctx.fillRect(X,Y+22,w,1);
    ctx.fillStyle = kind === 'red' ? '#E0603F' : kind === 'dim' ? 'rgba(34,67,49,.75)' : 'rgba(26,57,43,.9)'; ctx.fillRect(X, Y, w, 22);
    ctx.fillStyle = kind === 'red' ? '#14110E' : kind === 'dim' ? '#c5cfb3' : '#f1e8ce'; ctx.fillText(text, X + w / 2, Y + 12);
  }
  for (const fx of G.fx) {
    if (fx.type !== 'text') continue;
    const k = fx.t / fx.dur, X = sx(fx.x / U), Y = sy(fx.y / U) - Math.round(k * 10) * 3;
    ctx.globalAlpha = 1 - k * k;
    ctx.font = fx.pix ? '700 20px ' + PIX : '700 17px ' + SANS;
    ctx.fillStyle = '#0E0B09'; for (const [dx, dy] of [[-3, 0], [3, 0], [0, -3], [0, 3]]) ctx.fillText(fx.text, X + dx, Y + dy);
    ctx.fillStyle = fx.color; ctx.fillText(fx.text, X, Y); ctx.globalAlpha = 1;
  }
  if (G.deadT > 0) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    const a = G.deadT > 0.8 ? (1.6 - G.deadT) / 0.8 : G.deadT / 0.8;
    ctx.fillStyle = 'rgba(8,6,5,' + clamp(a, 0, 1) + ')'; ctx.fillRect(0, 0, cv.width, cv.height);
  }
}

// ---------------------------------------------------------------- HUD
const cache = {};
function setText(id, v) { v = String(v); if (cache[id] !== v) { cache[id] = v; $(id).textContent = v; } }
function setStyle(el, prop, v) { const k = el.id + prop; if (cache[k] !== v) { cache[k] = v; el.style.setProperty(prop, v); } }
function questText() {
  if(G.f.delivered)return chapterQuest();
  const f = G.f, inv = G.inv;
  if (!f.accepted) return ['去找沈青', '她在渡口青石板路上，头顶有金色记号'];
  if (f.delivered) return chapterQuest();
  if (inv.med) return ['把药包交给沈青', '回青石渡'];
  if (f.asked) return ['取回药包，交给沈青', '采止血草 ' + inv.herb + '/2 交给匪首；或直接动手'];
  return ['取回药包，交给沈青', '药包在山道尽头的匪营'];
}
let toastKey = '', bannerRegion = null, bannerT = 0;
function hud(dt) {
  const p = G.p, inv = G.inv;
  setStyle($('hpf'), 'width', (p.hp / p.maxHp * 100).toFixed(1) + '%');
  setStyle($('mpf'), 'width', (p.mp / p.maxMp * 100).toFixed(1) + '%');
  setStyle($('spBar'),'width',p.sp+'%');setText('spVal',Math.floor(p.sp));
  setText('hpn', Math.ceil(p.hp)); setText('mpn', Math.floor(p.mp));
  setText('coin', inv.coin); setText('band', inv.bandage);
  const mats = [];
  if (inv.wood) mats.push('木料 ' + inv.wood);
  if (inv.iron) mats.push('废铁 ' + inv.iron);
  if (inv.herb) mats.push('止血草 ' + inv.herb);
  if (inv.med) mats.push('药包');
  $('mats').hidden = mats.length === 0; setText('matsT', mats.join(' · '));
  const q = questText(); setText('qt', q[0]); setText('qs', q[1]); $('qs').classList.toggle('echo', G.f.delivered);
  setText('qo', G.f.delivered ? ('线索 '+G.chapter.clues.length+'/3 · M 查看江湖图与人物') : (G.orn ? '剑饰：' + G.orn : '可选：找周砚做一件剑饰'));
  const orn = $('orn'); setText('orn', G.orn || '无剑饰'); orn.classList.toggle('none', !G.orn);
  for(let i=0;i<2;i++){const sk=Chapter.SKILLS[G.chapter.skills[i]],button=$(i?'bSk2':'bSk');setStyle(button,'--p',(G.chapter.cooldowns[i]/sk.cd*100).toFixed(0)+'%');setText('skName'+i,sk.name);setText('skCost'+i,sk.cost+' 内力 '+(i?'I':'K'));button.setAttribute('aria-label',sk.name+(i?'（I）':'（K）'));button.classList.toggle('low',p.mp<sk.cost);}
  setStyle($('bAtk'), '--p', (p.atkCd / 0.45 * 100).toFixed(0) + '%');
  setStyle($('bDg'), '--p', (p.dgCd / P_.dgCd * 100).toFixed(0) + '%');
  $('quest').querySelector('.eyebrow').textContent=G.chapter.finalResolved?'第一章 · 风波之后':G.chapter.decision?'第三幕 · 渡口冲突':G.f.delivered?'第二幕 · 谁的账':'第一幕 · 渡口失药';
  drawMiniMap();
  for(let i=0;i<2;i++){const id=G.chapter.skills[i],sk=Chapter.SKILLS[id],canBreak=(G.orn==='破势'||id==='break')&&p.mp>=sk.cost&&G.chapter.cooldowns[i]<=0&&(G.enemies.some(e=>activeFoe(e)&&e.state==='windup'&&e.atk.inter&&Math.hypot(e.x-p.x,e.y-p.y)<sk.range+sk.dash+KIND[e.kind].r)||(G.dummy.state==='windup'&&nearDummy()));$(i?'bSk2':'bSk').classList.toggle('hot',canBreak);}
  const hint=$('combatHint');hint.hidden=!G.started||paused()||!(inCombat()||nearDummy());if(!hint.hidden)hint.textContent=G.orn==='破势'?'破势：打断后接普攻，追击 +8':G.orn==='回气'?'回气：剑招命中返18，空挥不返；自然回气1.5/秒':'战斗 / 练习回气1.5/秒；截流剑可打断蓄力';
  setText('combo', p.comboT > 0 && p.combo > 0 ? (p.combo + 1) + ' 段' : '');
  curTarget = findTarget();
  const ib = $('interact');
  if (curTarget) { ib.hidden = false; setText('interactT', curTarget.label+' · E / 点击'); if (curTarget.kind === 'npc') tip('talk', '点人物上方「点击交谈」标记，或按 E；底部交谈按钮也能用'); } else ib.hidden = true;
  updateTalkMarker();
  const boss = G.enemies[2], bb = $('bossbar');
  if (boss.hostile && activeFoe(boss) && Math.hypot(boss.x - p.x, boss.y - p.y) < 520) {
    bb.hidden = false; setText('bbName', boss.spar ? '匪首 · 切磋' : '匪首');
    setStyle($('bbHp'), 'width', (boss.hp / KIND.boss.hp * 100).toFixed(1) + '%');
    const w = boss.state === 'windup' ? boss.t / boss.atk.tele : 0;
    setStyle($('bbT'), 'width', (w * 100).toFixed(1) + '%');
    const tagOn = boss.state === 'windup';
    $('bbTag').hidden = !tagOn;
    if (tagOn) setText('bbTag', boss.atk.id === 'heavy' ? (G.orn === '破势' ? '重劈 · 可打断' : '重劈') : boss.atk.id === 'charge' ? '冲撞 · 侧闪' : '横扫 · 后退');
  } else bb.hidden = true;
  SAVED_FLASH = Math.max(0, SAVED_FLASH - dt);
  $('saved').hidden = SAVED_FLASH <= 0;
  const tk = G.toasts.map((t) => t.text).join('|');
  if (tk !== toastKey) {
    toastKey = tk; const box = $('toasts'); box.textContent = '';
    for (const t of G.toasts) { const d = document.createElement('div'); d.className = 'toast px-dark'; d.textContent = t.text; box.appendChild(d); }
  }
  // 进入新区域时，顶部弹出米色地名牌，停 2.6 秒后淡出
  const region = p.x < 768 ? '青石渡' : p.x < 2400 ? '山道' : '匪营';
  if (G.started && !paused() && region !== bannerRegion) { bannerRegion = region; bannerT = 2.6; const b = $('banner'); b.textContent = region; b.hidden = false; b.classList.remove('out'); }
  if (bannerT > 0) { bannerT -= dt; if (bannerT <= 0) $('banner').classList.add('out'); }
  const pf = $('perf');
  if (G.ui.perf) { if(performance.now()-perfCacheAt>1000||!perfCache){perfCache=perfStats();perfCacheAt=performance.now();}const ps=perfCache; pf.hidden = false; setText('perf', ps ? Math.round(ps.fps) + ' FPS · P95≤' + ps.p95 + 'MS · MAX '+Math.round(ps.max)+'MS' : '...'); } else pf.hidden = true;
}
function updHudRects() {
  hudRects = ['status', 'quest', 'res', 'pad', 'bossbar', 'interact'].map((id) => $(id)).filter((el) => !el.hidden).map((el) => el.getBoundingClientRect()).map((r) => { const a = app.getBoundingClientRect(); return { left: r.left - a.left, right: r.right - a.left, top: r.top - a.top, bottom: r.bottom - a.top }; });
}
function renderAll() { $('start').hidden = G.started; renderDlg(); renderDone(); renderLog(); toastKey = '#'; }

function updateTalkMarker(){
  const el=$('nearTalk'),t=curTarget;el.hidden=!t||!['npc','boss'].includes(t.kind)||!canAct();if(el.hidden)return;
  const name=t.label.replace('交谈 · ','');el.querySelector('span').textContent=name+' · 点击交谈';el.setAttribute('aria-label','点击与'+name+'交谈');
  el.style.left=(VW/2+(t.x-G.p.x)/U*Z)+'px';el.style.top=(VH/2+(t.y-G.p.y)/U*Z+4)+'px';el.style.width=Math.max(92,24*Z)+'px';el.style.height=(23*Z+30)+'px';
}
function installPlaytestForm(){
  for(const el of document.querySelectorAll('[data-profile]'))el.addEventListener('change',()=>{
    const r=Playtest.ensure(G);r.profile[el.dataset.profile]=el.value;saveNow(false);$('rec').textContent=recordText();
  });
  $('bPrompt').onclick=()=>{const r=Playtest.ensure(G),entry={at:new Date().toISOString(),activeSeconds:G.time,level:Number($('promptLevel').value),text:$('promptNote').value.trim()};if(!entry.text){toast('请写下实际给出的人工提示');return;}r.prompts.push(entry);Playtest.event(G,'human_prompt',entry);$('promptNote').value='';saveNow(false);renderLog();};
  $('bExport').onclick=()=>{const data=JSON.stringify(recordPayload(),null,2),url=URL.createObjectURL(new Blob([data],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='青石渡试玩-'+PAGE_SESSION+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
}

// ---------------------------------------------------------------- 开场的人物排成一排
const castC = $('cast'), castG = castC.getContext('2d');
function drawCast(t) {
  if ($('start').hidden) return;
  castG.clearRect(0, 0, castC.width, castC.height);
  const fr = WALK[Math.floor(t * 6) % 4];
  ['xia', 'shen', 'xu', 'lu', 'zhou', 'bandit'].forEach((id, i) => drawChar(castG, id, 'down', i === 0 ? fr : 'idle', 12 + i * 22, 45));
  drawChar(castG,'boss','down','idle',166,45);
}

// ---------------------------------------------------------------- 主循环
let last = performance.now(), rectT = 0;
let SERIF = 'serif', SANS = 'sans-serif', PIX = 'monospace';
function frame(now) {
  syncBattle();
  const raw = now - last; last = now; perfRec(raw);
  const dt = Math.min(0.05, raw / 1000);
  if (G.started && !paused()) { if (G.hitstop > 0) G.hitstop=Math.max(0,G.hitstop-dt); else update(dt); }
  G.toasts = G.toasts.filter((t) => (t.t -= dt) > 0);
  rectT -= dt; if (rectT <= 0) { updHudRects(); rectT = 0.25; }
  for(const event of combatEvents)combatArt.impact(event);
  // 背景音乐：手动暂停、切后台、静音时停；战斗中切到战斗段；预警、命中与交互提示音时让路
  music?.update(soundEnabled&&AC?.state==='running'&&G.started&&!G.manualPaused&&!document.hidden,inCombat()?'combat':'explore');
  if(combatEvents.some(e=>['tele','pickup','buy','craft','note','done'].includes(e)||e?.name==='impact'))music?.duck();
  if(soundEnabled&&AC?.state==='running')combatAudio.play(combatEvents);combatEvents.length=0;
  draw(now / 1000); hud(dt); drawCast(now / 1000);
  requestAnimationFrame(frame);
}
function sanitizeLoaded() {
  for (const e of G.enemies) {
    if (!e.alive) continue;
    const K = KIND[e.kind];
    if (e.state === 'dying') { e.alive = false; continue; }
    if (e.kind === 'boss') { e.spar = false; e.hostile = false; }
    Object.assign(e, { x: e.hx, y: e.hy, hp: K.hp, maxHp: K.hp, state: 'idle', t: 0, atk: null, plan: null });
    if (e.defeated && G.f.sparWins === 0) e.state = 'down';
  }
  G.swings=[];G.qi=[];G.manualPaused=false;G.p.sp??=100;G.combatSerial??=0;combatArt.reset();
  G.dummy.state = 'idle'; G.dummy.t = 0; G.deadT = 0; G.p.hp = G.p.hp<=0?G.p.maxHp:G.p.hp;G.arrows=[];G.chapter.cooldowns=[0,0];G.p.dodge=G.p.inv=G.p.swing=0;
}
function boot(data) {
  $('bStart').disabled=true;$('bNew').disabled=true;
  if (data && data.G && data.G.v === 4) G = data.G;
  else {
    const s = loadSave();
    if (s) {
      G = s.G; G.started = false; sanitizeLoaded();
      const when = new Date(s.at);
      $('bStart').textContent = '继续'; $('bNew').hidden = false;
      $('saveHint').textContent = '上次存档：' + (when.getMonth() + 1) + ' 月 ' + when.getDate() + ' 日 ' + when.getHours() + ':' + String(when.getMinutes()).padStart(2, '0') + ' · ' + (G.f.delivered ? '已交药' : G.inv.med ? '药包在身上' : G.f.accepted ? '正在取药' : '刚到渡口');
    }
  }
  Playtest.ensure(G,{debug:DEBUG});
  const cs = getComputedStyle(document.documentElement);
  SERIF = cs.getPropertyValue('--serif') || 'serif'; SANS = cs.getPropertyValue('--sans') || 'sans-serif'; PIX = cs.getPropertyValue('--pix') || 'monospace';
  loadAssets().then(async () => { Object.assign(OBJ,await worldArt.props(new URL('./assets/songfeng/world-atlas.png',import.meta.url).href,SIZE));buildMap(); portrait($('myFace'), 'xia'); resize(); renderAll();$('bStart').disabled=false;$('bNew').disabled=false; last = performance.now(); requestAnimationFrame(frame); }).catch(error=>{showSaveError('场景载入失败，请刷新重试：'+error.message);$('bStart').disabled=true;});
}
try { window.claude?.hot?.snapshot?.(() => ({ G: JSON.parse(JSON.stringify(G)) })); } catch (e) { /* 没有热更新也能玩 */ }
if (location.search.includes('debug')) window.__duko = { get G() { return G; }, get music() { return music?.state; }, get BUF() { return BUF; }, get LBUF() { return LBUF; }, draw, OBST, NPCS, INSPECT, CRATE, HERBS, DUMMY_POS, RESPAWN, WORLD, interact, doAct, attack, skill, dodge, useBandage, commit, loadSave, clearSave, recordText, recordPayload, perfRec, perfStats, newGame, get locations(){return {NPCS,CRATE,HERBS,LEDGER_POS,CACHE_POS,FINAL_POS};}, openDlg, toggleAtlas, kill, hurtPlayer, respawn, updArcher, updateChapter, get worldStyle(){return WORLD_STYLE;},get saveKey(){return SAVE_KEY;}, get target() { return curTarget; }, step(dt, n) { for (let i = 0; i < (n || 1); i++) { if (G.started && !paused()) { if (G.hitstop > 0) G.hitstop=Math.max(0,G.hitstop-dt); else update(dt); } } hud(dt); } };
installPlaytestForm();
const hot = window.claude?.hot;
if (hot?.ready) hot.ready(boot); else boot(hot?.data ?? {});
})();
