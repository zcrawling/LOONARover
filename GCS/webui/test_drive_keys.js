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
      dataset: {command: id}, classList: {toggle() {}, add() {}}, style: {},
      parentElement: {}, replaceChildren() {}, append() {},
      setAttribute() {}, addEventListener(name, fn) {this[name] = fn;},
    });
    return nodes.get(id);
  }
  const buttons = ['STOP', 'AUTO', 'MANUAL'].map(node);
  const context = vm.createContext({
    document: {getElementById: node, querySelectorAll: () => buttons,
               createElement: () => node(Symbol())},
    window: {addEventListener: (name, fn) => events.set(name, fn)},
    setInterval(fn) {timers.set(++timerId, fn); return timerId;},
    clearInterval(id) {timers.delete(id);}, setTimeout() {},
    AbortSignal: {timeout: () => undefined},
    fetch(url, options) {
      if (url === '/api/state') return new Promise(() => {});
      return new Promise(resolve => requests.push({
        command: JSON.parse(options.body).command,
        body: JSON.parse(options.body),
        finish: () => resolve({ok: true, json: async () => ({ok: true, text: 'Sent'})}),
      }));
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'static/app.js'), 'utf8'), context);
  vm.runInContext("current={connection:'CONNECTED',manual_control:{repeat_interval_ms:50}};token='test';", context);
  return {requests, buttons, events, timers, node,
          draw(state) {context.state = state; vm.runInContext('draw(state)', context);}};
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

test('angular slider uses config initially and updates held turn commands without starting motion', async () => {
  const b = browser();
  const state = {connection:'CONNECTED', manual_control:{angular_speed_radps:0.2},
    status:{}, events:[], requests:[]};
  b.draw(state);
  assert.equal(b.node('angular-speed').value, '0.20');
  b.node('angular-speed').value = '0.37';
  b.node('angular-speed').input();
  b.draw(state); // Polling must not overwrite the user's selection.
  assert.equal(b.node('angular-speed-value').textContent, '0.37 rad/s');
  assert.equal(b.requests.length, 0);
  const left = {...key, key:'ArrowLeft'};
  b.events.get('keydown')(left);
  await tick();
  assert.deepEqual(b.requests[0].body, {command:'LEFT', angular_speed_radps:0.37});
  b.requests[0].finish();
  await tick();
  b.node('angular-speed-control').wheel({deltaY:-1, preventDefault(){}});
  for (const timer of b.timers.values()) timer();
  await tick();
  assert.deepEqual(b.requests[1].body, {command:'LEFT', angular_speed_radps:0.38});
  b.events.get('keyup')(left);
  b.requests[1].finish();
  await tick();
  assert.deepEqual(b.requests[2].body, {command:'MANUAL'});
  b.requests[2].finish();
  await tick();
  const right = {...key, key:'ArrowRight'};
  b.events.get('keydown')(right);
  await tick();
  assert.deepEqual(b.requests[3].body, {command:'RIGHT', angular_speed_radps:0.38});
  b.events.get('keyup')(right);
  b.requests[3].finish();
  await tick();
  b.requests[4].finish();
  await tick();
});

test('arrow keys editing a speed slider do not issue driving commands', async () => {
  const b = browser();
  b.events.get('keydown')({...key, target:{closest:()=>b.node('angular-speed-control')},
    preventDefault(){assert.fail('slider keyboard input must keep its native behavior');}});
  await tick();
  assert.equal(b.requests.length, 0);
});

test('real rover battery summary shows voltage without an invented percentage', () => {
  const b = browser();
  const state = {connection:'CONNECTED',rx_messages:1,tx_messages:0,data_gaps:0,
    status:{values:{'배터리 전압 (V)':16.7,'배터리 잔량 (%)':null},
            value_sources:{'배터리 전압 (V)':'VEHICLE'}},events:[],requests:[]};
  b.draw(state);
  assert.equal(b.node('battery-label').textContent, '배터리 전압');
  assert.equal(b.node('battery').textContent, '16.7 V');
  assert.equal(b.node('battery-fill').parentElement.hidden, true);
  state.status.values['배터리 전압 (V)'] = null;
  b.draw(state);
  assert.equal(b.node('battery-label').textContent, '배터리 전압');
  assert.equal(b.node('battery').textContent, '—');
});
