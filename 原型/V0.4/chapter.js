/* 青石渡风波：章节规则与一次提交。浏览器和 Node 测试共用。 */
(function (root) {
  'use strict';
  const CLUES = {
    cart: { name: '货车残单', source: '翻倒的货车', text: '半张运单记着三批药材的运费。落款是陆平，工钱一栏被划去；它能证明有这笔支出，不能独自证明钱被谁拿走。' },
    witness: { name: '船工证词', source: '许舟亲述', text: '许舟亲眼见陆平收下药商的结款，而同船六名工人两个月没领到工钱。他愿意当面对质，代价是可能丢掉饭碗。' },
    ledger: { name: '工钱账册', source: '匪营旧账箱', text: '账册列着六名船工的姓名与欠付月份，金额能和货车残单对上。这是船工自记的账，需要证词或运单印证。' },
  };
  const SKILLS = {
    qi: { name: '松风剑气', tag: '剑气 · 贯穿来敌', cost: 25, cd: 3.8, dmg: 44, range: 470, half: .35, dash: 0, text: '向面前放出一道剑气，可贯穿多名来敌，遇到掩体消散。命中配回气仍只返还一次内力。' },
    thrust: { name: '追风刺', tag: '突进 · 追弓手', cost: 24, cd: 2.0, dmg: 24, range: 105, half: 0.55, dash: 100, text: '沿面向突进后刺击，适合逼近弓手；突进没有无敌，不能顶着重劈硬闯。' },
    break: { name: '截流剑', tag: '破招 · 压蓄力', cost: 30, cd: 2.6, dmg: 30, range: 112, half: 0.9, dash: 12, text: '命中可打断预兆时令敌人短暂失衡；装备破势会延长失衡，给反击留下窗口。' },
    sweep: { name: '回澜斩', tag: '横扫 · 解围', cost: 36, cd: 3.5, dmg: 22, range: 120, half: Math.PI, dash: 0, text: '环身横扫所有近敌，拉开被围攻的空间；配回气每次施放只返还一次内力。' },
  };
  const DECISIONS = {
    public: { name: '公开账目', text: '请许舟当面对质。陆平停止补给，护院会阻拦；船工愿意帮你。需要两条能相互印证的证据。' },
    mediate: { name: '促成调停', text: '让双方在渡口对账。保留匪首的合作；若交换取药且有两条证据，可在对峙中议和，否则要护住会面。' },
    leave: { name: '送药后离开', text: '不公开欠薪。陆平提供两条绷带，但山道余匪会来截路；船工的账暂时没有结果。' },
  };
  const fail = msg => ({ ok: false, msg });
  function create() {
    return { clues: [], decision: null, supplied: false, finalStarted: false, finalResolved: false, ending: null, peaceful: false, skills: ['qi', 'break'], cooldowns: [0, 0], kills: 0, visited: [], allyHits: 0, arrowsBlocked: 0 };
  }
  function encounter(s) {
    const c = s.chapter, trusted = s.f.branch === 'B';
    if (c.decision === 'public') return { peace: false, ally: 'xu', foes: ['captain', 'guard', 'archer'], title: '护住证人', intro: c.clues.includes('witness')?'陆平的护院拦住了渡口。许舟握着运单，第一次没有低下头。':'陆平的护院拦住了渡口。许舟听到你公开账目的消息，走来帮忙；你没有预先取得他的证词，只能凭两份书面记录对账。' };
    if (c.decision === 'mediate') return { peace: trusted && c.clues.length >= 2, ally: trusted ? 'boss' : null, foes: ['guard', 'archer'], title: '守住会面', intro: '匪首按约来到渡口。护院要收走账册，先证明你们有资格把话说完。' };
    return { peace: false, ally: null, foes: ['raider', 'raider', 'archer'], title: '余波未平', intro: '你准备乘船离开，失去药包的余匪追到了渡口。陆平关上门，船工各自散开。' };
  }
  function act(s, action, value) {
    const c = s.chapter;
    if (action === 'clue') {
      if (!CLUES[value]) return fail('没有这条线索');
      if (c.clues.includes(value)) return fail('这条线索已经记下');
      c.clues.push(value); s.log.push('线索 · ' + CLUES[value].name + '：' + CLUES[value].text); return { ok: true };
    }
    if (action === 'equip') {
      if (!value || ![0, 1].includes(value.slot) || !SKILLS[value.skill]) return fail('请选择一个招式槽');
      if (c.skills.includes(value.skill)) return fail('这个招式已经携带了');
      c.skills[value.slot] = value.skill; return { ok: true };
    }
    if (action === 'decide') {
      if (!s.f.delivered) return fail('先把救命药送给沈青');
      if (c.decision) return fail('渡口已经记住你的决定');
      if (!DECISIONS[value]) return fail('没有这种决定');
      if (value === 'public' && c.clues.length < 2) return fail('只有一面之词。至少找两条线索相互印证');
      if (value === 'mediate' && s.f.branch !== 'B' && !c.clues.length) return fail('先找一条证据，或与匪首建立交换的信任');
      c.decision = value; s.log.push('你的决定 · ' + DECISIONS[value].name + '：' + DECISIONS[value].text); return { ok: true };
    }
    if (action === 'supply') {
      if (!c.decision || c.decision === 'public') return fail('陆平拒绝再提供补给');
      if (c.supplied) return fail('这份补给已经领过');
      c.supplied = true;
      const n = c.decision === 'leave' ? 2 : 1; s.inv.bandage += n;
      s.log.push((c.decision === 'leave' ? '陆平' : '沈青') + '提供绷带 ' + n + '；这份帮助已经放进行囊'); return { ok: true };
    }
    if (action === 'start') {
      if (!c.decision) return fail('先决定怎样处理这件事');
      if (c.finalStarted || c.finalResolved) return fail('这场对峙已经开始');
      c.finalStarted = true; return { ok: true };
    }
    if (action === 'resolve') {
      if (!c.finalStarted || c.finalResolved) return fail('这场对峙尚未开始，或已经结束');
      if (!['peace', 'victory'].includes(value)) return fail('对峙还没有结果');
      if (value === 'peace' && !encounter(s).peace) return fail('双方还没有议和的条件');
      c.finalResolved = true; c.ending = c.decision; c.peaceful = value === 'peace'; s.inv.coin += 25;
      s.log.push('渡口终局 · ' + DECISIONS[c.decision].name + (c.peaceful ? '，双方当面对账，护院放行' : '，你击退了拦路的人') + '；获得酬谢 25 铜钱'); return { ok: true };
    }
    return fail('这一步无法完成');
  }
  function transact(state, op, change, write) {
    if (Object.hasOwn(state.receipts, op)) return { ok: true, dup: true, ...state.receipts[op] };
    const draft = JSON.parse(JSON.stringify(state));
    let result;
    try { result = change(draft) || { ok: true }; } catch (_) { return fail('这一步没有生效，请重试'); }
    if (!result.ok) return result;
    const receipt = { ...draft.receipts[op], op, at: Math.round(state.time || 0) }; draft.receipts[op] = receipt;
    try { if (write(draft) === false) return fail('存档失败，这一步没有生效，请检查浏览器存储后重试'); }
    catch (_) { return fail('存档失败，这一步没有生效，请检查浏览器存储后重试'); }
    Object.assign(state, draft); return { ok: true, ...receipt };
  }
  const api = { create, act, encounter, transact, CLUES, SKILLS, DECISIONS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.QingShiChapter = api;
})(globalThis);
