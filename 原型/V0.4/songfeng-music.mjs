// 背景音乐：全部用 Web Audio 现场合成，没有外部音频素材（#7 路线 A）。
// 探索：D 羽调五声音阶的拨弦旋律 + 低持续音；战斗：鼓点 + 低音反复 + 笛声短句。
// 两段各走一条增益母线，切换时交叉淡入淡出；预警、命中时短暂压低音量，不遮盖战斗提示。

// D 羽调五声：D F G A C，按半音距离 D3 的偏移列出两个八度
const SCALE = [0, 3, 5, 7, 10, 12, 15, 17, 19, 22, 24];
const hz = (step, base = 146.83) => base * 2 ** (SCALE[step] / 12);

// 旋律以八分音符为一格，null 是休止；四句一循环（A A B A）
const EXPLORE_A = [7, null, 6, 5, 4, null, 5, null, 3, null, 4, 5, 4, null, null, null];
const EXPLORE_B = [8, null, 7, null, 6, 5, 6, null, 5, null, 3, 4, 2, null, null, null];
const EXPLORE = [...EXPLORE_A, ...EXPLORE_A, ...EXPLORE_B, ...EXPLORE_A];
const COMBAT_BASS = [0, null, 0, 2, null, 0, 3, null, 0, null, 0, 2, null, 4, 3, 2];
const COMBAT_DRUM = [1, 0, 0, .5, 1, 0, .6, 0, 1, 0, 0, .5, 1, .4, .7, .4];
const COMBAT_FLUTE = [null, null, null, null, null, null, null, null, 9, null, 8, 7, 8, null, null, null,
  null, null, null, null, null, null, null, null, 7, null, 8, null, 6, null, null, null];

export function createMusic(audio) {
  const out = audio.createGain(), buses = { explore: audio.createGain(), combat: audio.createGain() };
  out.gain.value = .0001; out.connect(audio.destination);
  for (const bus of Object.values(buses)) { bus.gain.value = .0001; bus.connect(out); }
  const noise = audio.createBuffer(1, Math.ceil(audio.sampleRate * .25), audio.sampleRate), data = noise.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  const live = new Set();
  let timer = null, mode = 'explore', step = 0, nextAt = 0, pad = null, duckUntil = 0;
  const LEVEL = .35, TEMPO = { explore: 72, combat: 116 };

  const track = (source, end) => {
    if (live.size >= 24) return false;
    live.add(source); source.onended = () => live.delete(source);
    source.stop(end); return true;
  };
  // 拨弦：三角波起音带一点下滑，指数衰减；再叠一个低八度的正弦做琴身
  function pluck(bus, f, t, volume, length) {
    for (const [type, mul, v] of [['triangle', 1, volume], ['sine', .5, volume * .5]]) {
      const osc = audio.createOscillator(), gain = audio.createGain();
      osc.type = type; osc.frequency.setValueAtTime(f * mul * 1.012, t); osc.frequency.exponentialRampToValueAtTime(f * mul, t + .06);
      gain.gain.setValueAtTime(.0001, t); gain.gain.exponentialRampToValueAtTime(v, t + .008); gain.gain.exponentialRampToValueAtTime(.0001, t + length);
      osc.connect(gain); gain.connect(bus); osc.start(t);
      if (!track(osc, t + length + .02)) { osc.disconnect(); gain.disconnect(); }
    }
  }
  function flute(f, t, length) {
    const osc = audio.createOscillator(), vib = audio.createOscillator(), depth = audio.createGain(), gain = audio.createGain();
    osc.frequency.value = f; vib.frequency.value = 5.2; depth.gain.value = f * .006;
    vib.connect(depth); depth.connect(osc.frequency);
    gain.gain.setValueAtTime(.0001, t); gain.gain.exponentialRampToValueAtTime(.08, t + .08); gain.gain.exponentialRampToValueAtTime(.0001, t + length);
    osc.connect(gain); gain.connect(buses.combat); osc.start(t); vib.start(t);
    track(osc, t + length + .02); track(vib, t + length + .02);
  }
  function drum(t, volume) {
    const osc = audio.createOscillator(), gain = audio.createGain();
    osc.frequency.setValueAtTime(95, t); osc.frequency.exponentialRampToValueAtTime(42, t + .18);
    gain.gain.setValueAtTime(.0001, t); gain.gain.exponentialRampToValueAtTime(.55 * volume, t + .004); gain.gain.exponentialRampToValueAtTime(.0001, t + .26);
    osc.connect(gain); gain.connect(buses.combat); osc.start(t); track(osc, t + .28);
    const hit = audio.createBufferSource(), filter = audio.createBiquadFilter(), hg = audio.createGain();
    hit.buffer = noise; filter.type = 'lowpass'; filter.frequency.value = 900;
    hg.gain.setValueAtTime(.0001, t); hg.gain.exponentialRampToValueAtTime(.14 * volume, t + .003); hg.gain.exponentialRampToValueAtTime(.0001, t + .09);
    hit.connect(filter); filter.connect(hg); hg.connect(buses.combat); hit.start(t); track(hit, t + .1);
  }
  // 探索段的低持续音：D2 + A2 两个略微走音的正弦，过低通
  function startPad(t) {
    const filter = audio.createBiquadFilter(), gain = audio.createGain();
    filter.type = 'lowpass'; filter.frequency.value = 420; gain.gain.value = .05;
    filter.connect(gain); gain.connect(buses.explore);
    pad = [73.42, 110.3].map((f) => { const o = audio.createOscillator(); o.frequency.value = f; o.detune.value = (Math.random() - .5) * 8; o.connect(filter); o.start(t); live.add(o); return o; });
  }

  function schedule() {
    const beat = 60 / TEMPO[mode] / 2;
    while (nextAt < audio.currentTime + .25) {
      const t = Math.max(nextAt, audio.currentTime);
      if (mode === 'explore') {
        const note = EXPLORE[step % EXPLORE.length];
        if (note !== null) pluck(buses.explore, hz(note), t, .16, 1.6);
        if (step % 16 === 0) pluck(buses.explore, hz(0, 73.42), t, .12, 3);
      } else {
        const i = step % 16, bass = COMBAT_BASS[i], tone = COMBAT_FLUTE[step % COMBAT_FLUTE.length];
        if (COMBAT_DRUM[i]) drum(t, COMBAT_DRUM[i]);
        if (bass !== null) pluck(buses.combat, hz(bass, 73.42), t, .22, .32);
        if (tone !== null) flute(hz(tone), t, .45);
      }
      step++; nextAt = t + beat;
    }
  }
  const fade = (param, value, t, tau = .5) => { param.cancelScheduledValues(t); param.setTargetAtTime(value, t, tau); };

  function start() {
    const t = audio.currentTime;
    step = 0; nextAt = t + .05;
    fade(out.gain, LEVEL, t, .8); fade(buses[mode].gain, 1, t, .3);
    startPad(t); schedule(); timer = setInterval(schedule, 60);
  }
  function stop() {
    clearInterval(timer); timer = null;
    for (const source of live) { try { source.stop(); } catch { /* 已经停了 */ } }
    live.clear(); pad = null;
    out.gain.cancelScheduledValues(audio.currentTime); out.gain.value = .0001;
    for (const bus of Object.values(buses)) { bus.gain.cancelScheduledValues(audio.currentTime); bus.gain.value = .0001; }
  }
  return {
    // 每帧调用：on 为假时全部停掉；mode 变化时交叉淡入淡出，新段从头开始
    update(on, next) {
      if (!on) { if (timer) stop(); return; }
      if (!timer) { mode = next; start(); return; }
      if (next !== mode) {
        const t = audio.currentTime;
        fade(buses[mode].gain, .0001, t, .6); fade(buses[next].gain, 1, t, .4);
        mode = next; step = 0; nextAt = Math.max(nextAt, t + .05);
      }
      if (duckUntil && audio.currentTime >= duckUntil) { duckUntil = 0; fade(out.gain, LEVEL, audio.currentTime, .25); }
    },
    // 预警、命中、交互提示音时压低约 14 dB，0.4 秒后回升
    duck() {
      if (!timer) return;
      const t = audio.currentTime;
      if (!duckUntil) fade(out.gain, LEVEL * .2, t, .04);
      duckUntil = t + .4;
    },
    stop() { if (timer) stop(); },
    get state() { return { playing: !!timer, mode }; },
  };
}
