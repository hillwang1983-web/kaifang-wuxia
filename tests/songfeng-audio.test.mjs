import test from 'node:test';
import assert from 'node:assert/strict';
import { createCombatAudio } from '../原型/V0.4/songfeng-feedback.mjs';

// 最小假 AudioContext：只记发声源的启动时刻，时间由测试手动推进
function fakeAudio() {
  const param = () => ({ value: 0, setValueAtTime() {}, exponentialRampToValueAtTime() {} });
  const node = extra => ({ connect() {}, disconnect() {}, ...extra });
  const audio = { currentTime: 0, sampleRate: 8000, destination: node(), starts: [] };
  const source = () => node({ frequency: param(), type: '', start(t) { audio.starts.push(t); }, stop() {}, onended: null });
  Object.assign(audio, {
    createGain: () => node({ gain: param() }),
    createDynamicsCompressor: () => node({ threshold: param(), knee: param(), ratio: param(), attack: param(), release: param() }),
    createBuffer: (c, n) => ({ getChannelData: () => new Float32Array(n) }),
    createOscillator: source, createBufferSource: source,
    createBiquadFilter: () => node({ frequency: param(), Q: param(), type: '' }),
  });
  return audio;
}

test('交互提示音各自出声，多音短句按延迟依次拨出（#7）', () => {
  const audio = fakeAudio(), sfx = createCombatAudio(audio), count = {};
  for (const name of ['pickup', 'buy', 'craft', 'note', 'done']) {
    audio.starts.length = 0; audio.currentTime += 1; sfx.play([name]);
    count[name] = audio.starts.length;
    assert.ok(audio.starts.some(t => t > audio.currentTime), name + ' 有延后拨出的音');
  }
  assert.deepEqual(count, { pickup: 2, buy: 2, craft: 5, note: 2, done: 4 });
});

test('同一帧重复的提示音只播一次，60ms 内不重播，过后恢复（#7）', () => {
  const audio = fakeAudio(), sfx = createCombatAudio(audio);
  sfx.play(['tele']); const one = audio.starts.length;
  audio.currentTime += 1; audio.starts.length = 0; sfx.play(['tele', 'tele', 'tele']);
  assert.equal(audio.starts.length, one, '同帧三次预警只出一次声');
  audio.currentTime += .03; audio.starts.length = 0; sfx.play(['tele']);
  assert.equal(audio.starts.length, 0, '30ms 后的同一预警被合并');
  audio.currentTime += .05; sfx.play(['tele']);
  assert.equal(audio.starts.length, one, '间隔够了照常出声');
  audio.currentTime += 1; audio.starts.length = 0; sfx.play(['swing', 'tele']);
  assert.ok(audio.starts.length > one, '不同提示音互不合并');
});

test('同一帧多个命中只取最重的一下发声（#7）', () => {
  const audio = fakeAudio(), sfx = createCombatAudio(audio);
  sfx.play([{ name: 'impact', kind: 'heavy', face: 0 }]); const single = audio.starts.length;
  audio.currentTime += 1; audio.starts.length = 0;
  sfx.play([{ name: 'impact', kind: 'light', face: 0 }, { name: 'impact', kind: 'heavy', face: 0 }, { name: 'impact', kind: 'light', face: 1 }]);
  assert.equal(audio.starts.length, single);
});
