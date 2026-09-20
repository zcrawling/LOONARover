'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function browser() {
  const nodes = new Map(), events = new Map(), timers = new Map(), requests = [];
  let timerId = 0;
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {
      dataset: {command: id}, classList: {toggle() {}}, style: {},
      setAttribute() {}, addEventListener(name, fn) {this[name] = fn;},
    });
    return nodes.get(id);
  }
  const buttons = ['STOP', 'AUTO', 'MANUAL'].map(node);
  const context = vm.createContext({
    document: {getElementById: node, querySelectorAll: () => buttons},
    window: {addEventListener: (name, fn) => events.set(name, fn)},
    setInterval(fn) {timers.set(++timerId, fn); return timerId;},
    clearInterval(id) {timers.delete(id);}, setTimeout() {},
    AbortSignal: {timeout: () => undefined},
    fetch(url, options) {
      if (url === '/api/state') return new Promise(() => {});
      return new Promise(resolve => requests.push({
        command: JSON.parse(options.body).command,
        finish: () => resolve({ok: true, json: async () => ({ok: true, text: 'Sent'})}),
      }));
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'static/app.js'), 'utf8'), context);
  vm.runInContext("current={connection:'CONNECTED',manual_control:{repeat_interval_ms:50}};token='test';", context);
  return {requests, buttons, events, timers};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const key = {key: 'ArrowUp', repeat: false, preventDefault() {}};

test('key release queues zero after an in-flight motion request', async () => {
  const b = browser();
  b.events.get('keydown')(key);
  await tick();
  b.events.get('keyup')(key);
  assert.deepEqual(b.requests.map(r => r.command), ['FORWARD']);
  b.requests[0].finish();
  await tick();
  assert.deepEqual(b.requests.map(r => r.command), ['FORWARD', 'MANUAL']);
  b.requests[1].finish();
  await tick();
});

test('STOP cancels held-key repeats and follows the in-flight motion', async () => {
  const b = browser();
  b.events.get('keydown')(key);
  await tick();
  b.buttons[0].click();
  b.requests[0].finish();
  await tick();
  assert.deepEqual(b.requests.map(r => r.command), ['FORWARD', 'STOP']);
  b.requests[1].finish();
  await tick();
  b.events.get('keyup')(key);
  await tick();
  assert.equal(b.requests.length, 2);
  assert.equal(b.timers.size, 1); // Only the unrelated clock timer remains.
});
