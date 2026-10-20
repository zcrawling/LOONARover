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
      attributes: {}, setAttribute(name,value) {this.attributes[name]=value;}, addEventListener(name, fn) {this[name] = fn;},
    });
    return nodes.get(id);
  }
  const buttons = ['STOP', 'AUTO', 'MANUAL', 'PAYLOAD_START', 'PAYLOAD_STOP','REACTION_LEFT','REACTION_RIGHT'].map(node);
  const context = vm.createContext({
    document: {getElementById: node, querySelectorAll: selector => selector === '[data-command]' ? buttons : [],
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
  return {requests, buttons, events, timers, node, evaluate: code=>vm.runInContext(code, context),
          draw(state) {context.state = state; vm.runInContext('draw(state)', context);}};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const key = {key: 'w', code:'KeyW', repeat: false, preventDefault() {}};

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
  const left = {...key, key:'a', code:'KeyA'};
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
  const right = {...key, key:'d', code:'KeyD'};
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
  b.events.get('keydown')({...key, key:'ArrowUp', code:'ArrowUp', target:{closest:()=>null},
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
  assert.equal(b.node('battery-reading').textContent, '16.70 V');
  state.status.values['배터리 전압 (V)'] = null;
  b.draw(state);
  assert.equal(b.node('battery-reading').textContent, '—');
});

test('linear slider and wheel stop at 0.40 m/s', async () => {
  const b = browser();
  b.node('linear-speed').value = '1.00';
  b.node('linear-speed').input();
  assert.equal(b.node('linear-speed').value, '0.40');
  b.node('speed-control').wheel({deltaY:-1, preventDefault(){}});
  assert.equal(b.node('linear-speed').value, '0.40');
  b.events.get('keydown')(key);
  await tick();
  assert.equal(b.requests[0].body.linear_speed_mps, .4);
});

test('angular slider and wheel stop at 3.80 rad/s', () => {
  const b = browser();
  b.node('angular-speed').value = '10.00';
  b.node('angular-speed').input();
  b.node('angular-speed-control').wheel({deltaY:-1, preventDefault(){}});
  assert.equal(b.node('angular-speed').value, '3.80');
});


test('Payload STOP remains available during initialization', () => {
  const b = browser();
  b.draw({connection: 'CONNECTED', status: {values: {}, payload: {state: 'STARTING'}}});
  assert.equal(b.node('PAYLOAD_STOP').disabled, false);
  assert.equal(b.node('PAYLOAD_START').disabled, true);
  b.draw({connection: 'CONNECTED', status: {values: {}, payload: {state: 'STOPPING'}}});
  assert.equal(b.node('PAYLOAD_STOP').disabled, true);
});

test('invalid payload measurement keeps rover controls available', () => {
  const b = browser();
  const values = Object.fromEntries(['비접촉 표면온도계', '접촉식 표면온도계', '자기상센서', 'PCA novelty']
    .map(name => [name, {value:null, unit:'', status:'측정 오류'}]));
  values['PCA candidate'] = {value:0, status:'INVALID_STATION'};
  values['PCA model'] = {value:'DEMO_ONLY'};
  b.draw({connection:'CONNECTED', status:{values:{}, payload:{state:'IDLE',request_id:'8'}},
          payload_sample:{request_id:'8',sample:1,time:1000,values}, events:[]});
  assert.equal(b.node('sensor-0').textContent, '—');
  assert.equal(b.node('sensor-status-0').textContent, '측정 오류');
  for (const command of ['STOP','MANUAL','AUTO','PAYLOAD_START']) {
    assert.equal(b.node(command).disabled, false, command);
  }
});

test('reaction defaults and tuned settings reach the command without executing while editing', async () => {
  const b=browser();
  assert.equal(b.node('reaction-esc_neutral').value,1488);
  assert.equal(b.node('reaction-left_first_ms').value,5);
  b.node('reaction-left_first_offset').value='30';
  b.node('reaction-left_first_offset').input();
  assert.equal(b.requests.length,0);
  assert.match(b.node('reaction-preview').textContent,/1518 µs × 5초/);
  b.node('REACTION_LEFT').click(); await tick();
  assert.equal(b.requests[0].body.reaction_settings.left_first_offset,30);
  assert.equal(b.requests[0].body.reaction_settings.left_first_ms,5000);
  const defaults=JSON.parse(fs.readFileSync(path.join(__dirname,'../../platforms/loonar/tools/mcu_v2/reaction-wheel.example.json'),'utf8'));
  assert.deepEqual(b.requests[0].body.reaction_settings,{...defaults,left_first_offset:30});
  b.requests[0].finish(); await tick();
  b.node('reaction-reset').click();
  assert.equal(b.node('reaction-left_first_offset').value,25);
  assert.equal(b.requests.length,1);
  b.draw({connection:'CONNECTED',status:{values:{},payload:{}},reaction:{state:'FIRST'}});
  assert.equal(b.node('REACTION_LEFT').disabled,true);
  assert.equal(b.node('STOP').disabled,false);
});


test('hardware telemetry supplies graphs and text without GroundLink', () => {
  const b = browser();
  b.draw({connection:'DISCONNECTED', status_stale:true,
    hardware:{age_s:0.5,data:{cpu_temperature_c:52.5,input_voltage_v:5.05,
      wireless:[{interface:'wlan0',signal_dbm:-63}],
      control:{online:true,battery_v:16.2},payload:{online:false}}}});
  assert.equal(b.node('temperature-reading').textContent, '52.5 °C');
  assert.equal(b.node('battery-reading').textContent, '16.20 V');
  assert.equal(b.node('wifi-reading').textContent, '-63 dBm');
  assert.equal(b.node('pi-input').textContent, '5.05 V');
  assert.equal(b.node('control-state').textContent, 'ONLINE');
  assert.equal(b.node('payload-mcu-state').textContent, 'OFFLINE');
  b.draw({connection:'DISCONNECTED',hardware:{age_s:5,data:{input_voltage_v:5.05}}});
  for (const id of ['temperature','battery','wifi']) assert.equal(b.node(id+'-reading').textContent,'—');
  assert.equal(b.node('pi-input').textContent, '— · 데이터 없음');
});

test('hidden drive panel and editing reaction inputs do not drive', async () => {
  const b = browser();
  b.node('commands').hidden = true;
  b.events.get('keydown')(key);
  b.node('commands').hidden = false;
  b.events.get('keydown')({...key,target:{closest:()=>b.node('reaction-esc_neutral')}});
  await tick();
  assert.equal(b.requests.length,0);
});


test('monitor history keeps only 60 seconds and breaks lines on missing samples', () => {
  const b = browser();
  b.evaluate(`{
    const now=Date.now();
    monitorHistory.battery.push({time:now-61000,value:15},
      {time:now-2000,value:16}, {time:now-1500,value:null}, {time:now-1000,value:16.1});
    renderMonitoring(now);
  }`);
  assert.equal(b.evaluate('monitorHistory.battery.length'),3);
  assert.equal((b.node('battery-line').attributes.d.match(/M/g)||[]).length,2);
  assert.equal(b.node('battery-line').attributes.d.includes('NaN'),false);
  b.evaluate('renderMonitoring(Date.now()+61000)');
  assert.equal(b.evaluate('monitorHistory.battery.length'),0);
  assert.equal(b.node('battery-line').attributes.d,'');
});

function payloadSample(candidate=1,status='DEMO_ONLY') {
 return {request_id:'8',sample:1,time:1000,values:{
  '비접촉 표면온도계':{value:27,unit:'°C',status:'정상'},
  '접촉식 표면온도계':{value:28,unit:'°C',status:'정상'},
  '자기상센서':{value:34,unit:'µT',status:'정상'},
  'PCA novelty':{value:10},'PCA candidate':{value:candidate,status},
  'PCA model':{value:'DEMO_ONLY'}}};
}

test('payload keeps last completed sequence while next one measures, uses matching CSV only', () => {
 const b=browser();
 const sample=payloadSample();
 const state={connection:'CONNECTED',status:{payload:{state:'MEASURING',request_id:'9'}},payload_sample:sample,
  payload_trace:{key:'["8",1,1000,null,null]',sample:1,duration_s:5,bytes:1500,sample_count:3,
   points:[{t:.5,values:[26,28,34]},{t:1,values:[null,28,34]},{t:1.5,values:[27,28,34]}]}};
 b.draw(state);
 assert.equal(b.node('sensor-0').textContent,'27.00 °C');
 assert.equal(b.node('sample-number').textContent,'SEQ 001');
 assert.match(b.node('sample-freshness').textContent,/직전 결과/);
 assert.equal((b.node('payload-0-line').attributes.d.match(/M/g)||[]).length,2);
 state.payload_trace.key='different';
 b.draw(state);
 assert.equal(b.node('payload-0-line').attributes.d,'');
});

test('PCA verdict distinguishes candidates, non-candidates and invalid results', () => {
 const b=browser();
 for (const [candidate,status,expected] of [[1,'DEMO_ONLY','추가 확인 후보'],[0,'DEMO_ONLY','후보 아님'],[0,'INVALID_STATION','판정 불가']]) {
  b.draw({connection:'CONNECTED',status:{},payload_sample:payloadSample(candidate,status)});
  assert.equal(b.node('pca-candidate').textContent,expected);
  assert.equal(b.node('pca-model').textContent,'DEMO_ONLY');
 }
});


test('arrows and old navigation keys retain native behavior without driving', async () => {
 const b=browser();
 for(const code of ['ArrowUp','ArrowLeft','ArrowDown','ArrowRight','PageUp','Home','PageDown','End']) {
  const event={code,key:code,preventDefault(){assert.fail('native key intercepted');}};
  b.events.get('keydown')(event);b.events.get('keyup')(event);
 }
 await tick();assert.equal(b.requests.length,0);
});

test('physical WASD works with uppercase and Korean layout; release still stops', async () => {
 const b=browser();
 b.events.get('keydown')({...key,key:'ㅈ'});
 await tick();assert.equal(b.requests[0].command,'FORWARD');
 b.events.get('keyup')({...key,key:'W'});
 b.requests[0].finish();await tick();
 assert.equal(b.requests[1].command,'MANUAL');b.requests[1].finish();await tick();
 b.events.get('keydown')({...key,code:'KeyS',key:'S'});
 await tick();assert.equal(b.requests[2].command,'REVERSE');
});

test('browser shortcuts do not start driving', async () => {
 const b=browser();
 for(const modifier of ['ctrlKey','altKey','metaKey','isComposing']) {
  b.events.get('keydown')({...key,[modifier]:true,preventDefault(){assert.fail('shortcut intercepted');}});
 }
 await tick();assert.equal(b.requests.length,0);
});
