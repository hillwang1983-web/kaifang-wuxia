export const IMPACTS = {
  light: { stop: .038, shake: 2.3, duration: .12 },
  heavy: { stop: .072, shake: 4.6, duration: .18 },
  qi: { stop: .062, shake: 3.6, duration: .16 },
  hurt: { stop: .042, shake: 3.8, duration: .17 },
};

export function kickCamera(camera, event) {
  if (event?.name !== 'impact') return;
  const profile = IMPACTS[event.kind], strength = Math.min(5, profile.shake + (event.killed ? .4 : 0));
  const remaining = camera.strength ? camera.strength * Math.pow(Math.max(0, 1 - camera.age / camera.duration), 2) : 0;
  if (strength < remaining) return;
  Object.assign(camera, { strength, duration: profile.duration, face: event.face, age: 0 });
}

export function advanceCamera(camera, dt) {
  if (!camera.strength || camera.age >= camera.duration) return { x: 0, y: 0 };
  const fade = Math.pow(Math.max(0, 1 - camera.age / camera.duration), 2), recoil = Math.cos(camera.age * 85);
  const strength = camera.strength * fade;
  camera.age = Math.min(camera.duration, camera.age + Math.max(0, Math.min(.05, dt)));
  return { x: -Math.cos(camera.face) * strength * recoil,
    y: -Math.sin(camera.face) * strength * recoil * .7 + Math.sin(camera.age * 110) * strength * .22 };
}

// 一次创建噪声与总线；命中采用气声、金属短响和低频冲击三层合成。
export function createCombatAudio(audio) {
  const master = audio.createGain(), limiter = audio.createDynamicsCompressor(), voices = new Set();
  master.gain.value = .65; limiter.threshold.value = -12; limiter.knee.value = 12;
  limiter.ratio.value = 8; limiter.attack.value = .002; limiter.release.value = .08;
  master.connect(limiter); limiter.connect(audio.destination);
  const noise = audio.createBuffer(1, Math.ceil(audio.sampleRate * .3), audio.sampleRate), data = noise.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  const voice = (source, duration, volume, filter) => {
    if (voices.size >= 32) return;
    const gain = audio.createGain(), t = audio.currentTime;
    gain.gain.setValueAtTime(.0001, t); gain.gain.exponentialRampToValueAtTime(volume, t + .002);
    gain.gain.exponentialRampToValueAtTime(.0001, t + duration);
    if (filter) { source.connect(filter); filter.connect(gain); } else source.connect(gain);
    gain.connect(master); voices.add(source);
    source.onended = () => { voices.delete(source); source.disconnect(); filter?.disconnect(); gain.disconnect(); };
    source.start(t); source.stop(t + duration + .005);
  };
  const tone = (from, to, duration, volume, type = 'sine') => {
    const source = audio.createOscillator(), t = audio.currentTime; source.type = type;
    source.frequency.setValueAtTime(from, t); source.frequency.exponentialRampToValueAtTime(to, t + duration);
    voice(source, duration, volume);
  };
  const air = (from, to, duration, volume, type = 'bandpass') => {
    const source = audio.createBufferSource(), filter = audio.createBiquadFilter(), t = audio.currentTime;
    source.buffer = noise; filter.type = type; filter.Q.value = .7;
    filter.frequency.setValueAtTime(from, t); filter.frequency.exponentialRampToValueAtTime(to, t + duration);
    voice(source, duration, volume, filter);
  };
  function impact(event) {
    const heavy = event.kind === 'heavy', qi = event.kind === 'qi', hurt = event.kind === 'hurt';
    tone(heavy ? 125 : hurt ? 105 : 180, heavy ? 42 : 65, heavy ? .15 : .085, heavy ? .3 : .18, 'triangle');
    air(hurt ? 450 : qi ? 1700 : 2900, hurt ? 120 : 750, heavy ? .075 : .045, heavy ? .26 : .18);
    if (!hurt) tone(qi ? 1250 : 2050, qi ? 480 : 820, heavy ? .1 : .055, heavy ? .065 : .045);
    if (qi) air(2400, 350, .16, .15);
    if (event.killed) { tone(85, 38, .18, .13, 'triangle'); air(900, 180, .14, .08); }
  }
  const cues = { ui:[740,740,.03,.016], coin:[1568,2093,.1,.025], heal:[660,990,.16,.03], tele:[170,340,.18,.025], interrupt:[988,1319,.1,.035], down:[330,160,.14,.025], evade:[1175,1175,.06,.025], dodge: [480, 950, .07, .018], cast: [320, 1100, .18, .035],
    wave: [420, 630, .25, .025], won: [560, 1120, .45, .04], lost: [220, 90, .4, .03] };
  return {
    play(events) {
      const hits = events.filter(e => e?.name === 'impact');
      if (hits.length) {
        const strongest = hits.reduce((a, b) => IMPACTS[b.kind].shake > IMPACTS[a.kind].shake ? b : a);
        impact({ ...strongest, killed: hits.some(e => e.killed) });
      }
      for (const name of events) {
        if (name === 'swing' || name === 'heavy') air(name === 'heavy' ? 1600 : 2400, 280, name === 'heavy' ? .12 : .075, name === 'heavy' ? .12 : .075);
        else if (name === 'arrow') air(3100, 1200, .045, .045, 'highpass');
        else if (cues[name]) { tone(...cues[name]); if (name === 'cast') air(700, 2600, .18, .1); }
      }
    },
    stop() { for (const source of voices) source.stop(); voices.clear(); },
  };
}
