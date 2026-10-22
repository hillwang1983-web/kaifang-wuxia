const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const modulePath = path.join(__dirname, '../原型/V0.4/chapter.js');
const C = fs.existsSync(modulePath) ? require(modulePath) : {};
function state(branch = 'B') {
  return { chapter: C.create(), inv: { coin: 40, bandage: 2, wood: 0, iron: 0 }, f: { branch, delivered: true }, log: [], receipts: {}, p: { hp: 100, maxHp: 100 } };
}
test('章节规则可加载', () => assert.equal(typeof C.create, 'function'));
test('公开账目需要互相印证的证据，不能凭传言定罪', () => {
  const s = state('A');
  assert.equal(C.act(s, 'decide', 'public').ok, false);
  C.act(s, 'clue', 'cart');
  assert.equal(C.act(s, 'decide', 'public').ok, false);
  C.act(s, 'clue', 'witness');
  assert.equal(C.act(s, 'decide', 'public').ok, true);
  assert.equal(s.chapter.decision, 'public');
  assert.equal(C.act(s, 'decide', 'leave').ok, false);
});
test('线索唯一，未知线索和未交药决策不生效', () => {
  const s = state(); s.f.delivered = false;
  assert.equal(C.act(s, 'decide', 'leave').ok, false);
  assert.equal(C.act(s, 'clue', 'invented').ok, false);
  C.act(s, 'clue', 'cart'); C.act(s, 'clue', 'cart');
  assert.deepEqual(s.chapter.clues, ['cart']);
});
test('交换信任加两条证据允许当面对峙时议和', () => {
  const s = state(); C.act(s, 'clue', 'cart'); C.act(s, 'clue', 'ledger'); C.act(s, 'decide', 'mediate');
  assert.equal(C.encounter(s).peace, true);
  assert.equal(C.act(s, 'resolve', 'peace').ok, false);
  assert.equal(C.act(s, 'start').ok, true);
  assert.equal(C.act(s, 'resolve', 'peace').ok, true);
  assert.equal(s.chapter.ending, 'mediate');
});
test('武力线不能无条件议和，随时可选择离开', () => {
  const s = state('A'); C.act(s, 'decide', 'leave');
  assert.equal(C.encounter(s).peace, false);
  assert.equal(C.act(s, 'start').ok, true);
  assert.equal(C.act(s, 'resolve', 'peace').ok, false);
  assert.equal(C.act(s, 'resolve', 'victory').ok, true);
});
test('补给和结局奖励只入账一次', () => {
  const s = state(); C.act(s, 'decide', 'leave');
  const before = s.inv.bandage; C.act(s, 'supply'); C.act(s, 'supply');
  assert.equal(s.inv.bandage, before + 2);
  C.act(s, 'start'); C.act(s, 'resolve', 'victory');
  const after = s.inv.coin; C.act(s, 'resolve', 'victory');
  assert.equal(s.inv.coin, after);
});
test('公开断掉陆平补给，证人会实际成为队友', () => {
  const s = state('A'); C.act(s, 'clue', 'cart'); C.act(s, 'clue', 'witness'); C.act(s, 'decide', 'public');
  assert.equal(C.act(s, 'supply').ok, false);
  assert.equal(C.encounter(s).ally, 'xu');
  assert.equal(C.encounter(s).foes.length, 3);
});
test('两份书证公开也能争取船工支援，但不能伪造已经获得证词', () => {
  const s=state('A');C.act(s,'clue','cart');C.act(s,'clue','ledger');C.act(s,'decide','public');
  assert.equal(C.encounter(s).ally,'xu');
  assert.deepEqual(s.chapter.clues,['cart','ledger']);
  assert.equal(C.encounter(s).intro.includes('没有低下头'),false);
});
test('三招只能携带两招，战斗外更换不会重复或空槽', () => {
  const s = state();
  assert.deepEqual(s.chapter.skills, ['thrust', 'break']);
  assert.equal(C.act(s, 'equip', { slot: 1, skill: 'sweep' }).ok, true);
  assert.equal(C.act(s, 'equip', { slot: 0, skill: 'sweep' }).ok, false);
  assert.equal(C.act(s, 'equip', { slot: 2, skill: 'break' }).ok, false);
  assert.deepEqual(s.chapter.skills, ['thrust', 'sweep']);
});
test('写入失败时物品、剧情与回执均保持原样，可以重试', () => {
  const s = state(); const before = JSON.stringify(s);
  const r = C.transact(s, 'buy', d => { d.inv.coin -= 5; d.inv.wood += 2; return { ok: true }; }, () => { throw Error('quota'); });
  assert.equal(r.ok, false); assert.equal(JSON.stringify(s), before);
  const good = C.transact(s, 'buy', d => { d.inv.coin -= 5; d.inv.wood += 2; return { ok: true }; }, () => {});
  assert.equal(good.ok, true); assert.equal(s.inv.coin, 35);
  const duplicate = C.transact(s, 'buy', () => { throw Error('重复执行'); }, () => {});
  assert.equal(duplicate.dup, true); assert.equal(s.inv.wood, 2);
});
