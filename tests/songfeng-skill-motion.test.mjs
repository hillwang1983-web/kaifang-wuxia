import test from 'node:test';
import assert from 'node:assert/strict';
import { skillHead, skillBladePoint, sampleSkillPose } from '../原型/V0.4/combat-render.mjs';
test('四门主动剑招的剑锋与各自剑光同源，固定剑身长度', () => {
  for (const skill of ['thrust', 'break', 'sweep', 'qi']) for (const face of [0, 1, Math.PI, -Math.PI / 2]) for (const p of [.23, .48, .7, .9]) {
    const point = skillBladePoint(skill, skillHead(p)), pose = sampleSkillPose(face, skill, p);
    const x = Math.cos(face) * point[0] - Math.sin(face) * point[1] * .84;
    const y = -18 + Math.sin(face) * point[0] + Math.cos(face) * point[1] * .84;
    assert.ok(Math.hypot(pose.tip.x - x, pose.tip.y - y) < .001);
    assert.ok(Math.abs(Math.hypot(pose.tip.x - pose.hand.x, pose.tip.y - pose.hand.y) - 55) < .001);
  }
});
test('追风沿直线刺出、截流由上劈下、回澜覆盖完整一周，剑气有独立斜向释放', () => {
  const samples = skill => Array.from({ length: 41 }, (_, i) => skillBladePoint(skill, i / 40));
  assert.ok(samples('thrust').every(p => p[1] === 0));
  assert.ok(skillBladePoint('break', 0)[1] < -70 && skillBladePoint('break', 1)[1] > 70);
  const sweep = samples('sweep'); assert.ok(Math.min(...sweep.map(p => p[0])) < -100); assert.ok(Math.max(...sweep.map(p => p[0])) > 100);
  assert.ok(Math.min(...sweep.map(p => p[1])) < -100 && Math.max(...sweep.map(p => p[1])) > 100);
  assert.notDeepEqual(samples('qi'), samples('thrust')); assert.notDeepEqual(samples('qi'), samples('break'));
});
