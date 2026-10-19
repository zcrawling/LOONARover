'use strict';
let current=null, token='', busy=false, latestRequest=null, commandQueue=Promise.resolve(), linearSpeed=0.1, speedInitialized=false, angularSpeed=0.2, angularSpeedInitialized=false;
const el=id=>document.getElementById(id);
const set=(id,text)=>{el(id).textContent=text;};
const connectionLabels={CONNECTED:'정상 연결',CONNECTING:'연결 중',RECONNECTING:'재연결 중',DISCONNECTED:'연결 끊김',DEGRADED:'통신 불안정'};
function badge(id,text,kind=''){set(id,text);el(id).className='badge '+kind;}
 function controls(){document.querySelectorAll('[data-command]').forEach(b=>{const state=current?.status?.payload?.state||'IDLE';b.disabled=!current||current.connection!=='CONNECTED'||busy||(b.dataset.command.startsWith('REACTION_')&&(current?.reaction?.active||['CONFIGURING','ACCEPTED','FIRST','SECOND','NEUTRAL_WAIT','SERVO_HOLD'].includes(current?.reaction?.state)))||(b.dataset.command==='PAYLOAD_START'&&['STARTING','MEASURING','STOPPING'].includes(state))||(b.dataset.command==='PAYLOAD_STOP'&&!['STARTING','MEASURING'].includes(state));});}
function selectCommand(command){document.querySelectorAll('[data-command]').forEach(button=>{const selected=button.dataset.command===command;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));});}
function number(value,unit=''){return typeof value==='number'&&Number.isFinite(value)?`${value}${unit}`:'—';}
function clockTime(date=new Date()){return date.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});}
function drawEvents(){
 const filter=el('event-filter').value;
 const events=(current?.events||[]).filter(e=>filter==='all'||(filter==='commands'?!!e.request_id:!e.request_id)).slice().reverse();
 el('event-list').replaceChildren();
 for(const e of events){const row=document.createElement('div');row.className='event';const time=document.createElement('time');const d=new Date(e.time);time.textContent=Number.isNaN(d.getTime())?'—':clockTime(d);const msg=document.createElement('span');msg.textContent=e.text;msg.className=/Completed|Forwarded|Received|CONNECTED/.test(e.text)?'success':/Unknown|Failed|RECONNECTING|DEGRADED|Aborted/.test(e.text)?'warning':'';const id=document.createElement('code');id.textContent=e.request_id?e.request_id.slice(0,12):'—';id.title=e.request_id||'';row.append(time,msg,id);el('event-list').append(row);}
 if(!events.length){const p=document.createElement('p');p.className='muted';p.textContent='표시할 이벤트가 없습니다.';el('event-list').append(p);}
}
function draw(s){
 const reactionLabels={UNKNOWN:'대기',CONFIGURING:'설정 전송 중',ACCEPTED:'실행 수락',FIRST:'1단계',SECOND:'2단계',NEUTRAL_WAIT:'ESC 중립 대기',SERVO_HOLD:'서보 유지',READY:'중립 준비됨',END:'완료',INTERRUPTED:'중단',CANCELLED:'취소됨',ERROR:'오류'};badge('reaction-state',reactionLabels[s.reaction?.state]||'대기');const rd=(s.reaction?.detail||'').split(',');set('reaction-detail',rd.length===4?`${rd[1]==='1'?'왼쪽':'오른쪽'} · ESC ${rd[2]} µs / 서보 ${rd[3]} µs`:(rd[0]==='ERROR'?`실행 오류: ${rd[1]==='busy'?'실행 중에는 다시 시작할 수 없습니다':rd[1]==='mcu_rejected'?'MCU가 설정 또는 실행을 거부했습니다':rd[1]==='response_timeout'?'MCU 응답 시간 초과 · 중립 요청':rd[1]==='backend_offline'?'Control MCU 연결 프로세스가 준비되지 않았습니다':rd[1]==='mcu_health_timeout'?'MCU 상태 수신이 끊겨 중립을 요청했습니다':rd[1]==='bad_settings'?'설정 범위를 확인하세요':rd[1]}`:reactionLabels[rd[0]]||'설정 대기 · 아직 실행하지 않음'));
 current=s;token=s.csrf_token;const good=s.connection==='CONNECTED';
 if(!speedInitialized&&typeof s.manual_control?.linear_speed_mps==='number'){linearSpeed=s.manual_control.linear_speed_mps;speedInitialized=true;updateSpeedDisplay();}
 if(!angularSpeedInitialized&&Number.isFinite(s.manual_control?.angular_speed_radps)){angularSpeed=s.manual_control.angular_speed_radps;angularSpeedInitialized=true;updateAngularSpeedDisplay();}
 set('environment',s.source||'데이터 출처 미확인');
 const liveAge=s.last_rx_age==null?'수신 없음':`${s.last_rx_age.toFixed(1)}초 전 수신`;
 badge('connection',good?'로버 연결됨':(connectionLabels[s.connection]||s.connection),good?'good':s.connection==='DEGRADED'?'warn':'bad');
 el('connection').title=`${s.connection} · RX ${s.rx_messages} · ${liveAge}`;
 set('health',connectionLabels[s.connection]||s.connection);set('mode',s.status?.mode||'—');set('age',s.last_rx_age==null?'—':`${s.last_rx_age.toFixed(1)}초`);set('counts',`${s.rx_messages} / ${s.tx_messages}`);set('gaps',s.data_gaps);
 const notice=el('notice');notice.hidden=good;notice.className='notice'+(good?'':' error');notice.textContent=good?'로버가 연결되었습니다.':`TCP ${s.connection} · 현재 상태를 확인할 수 없습니다. 명령 전송을 사용할 수 없습니다.`;
 badge('stale',s.status_stale?'이전 상태':'갱신 중',s.status_stale?'warn':'good');
 updateMonitoring(s);
 const p=s.status?.payload||{};badge('payload-state',p.state||'IDLE',p.state==='MEASURING'?'good':'');
 drawPayload(s);
 if(latestRequest){const r=s.requests.find(r=>r.request_id===latestRequest);if(r&&r.state!=='Pending')set('command-message',`"${r.command}" ${r.state}`);}
 set('updated','갱신 '+clockTime());controls();drawEvents();
}
async function poll(){try{const response=await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(9000)});if(!response.ok)throw Error('backend unavailable');draw(await response.json());}catch(error){current=null;token='';badge('connection','백엔드 연결 끊김','bad');el('connection').title='BACKEND OFFLINE';set('health','OFFLINE');el('notice').hidden=false;el('notice').className='notice error';set('notice','백엔드에 연결할 수 없습니다. 마지막 표시값은 이전 데이터입니다. 자동으로 다시 확인합니다.');badge('stale','이전 상태','warn');updateMonitoring(null);set('sample-freshness','이전 측정값');controls();}finally{setTimeout(poll,700);}}
async function send(command,select=true){if(!current||current.connection!=='CONNECTED')return;if(select)selectCommand(command);busy=true;controls();set('command-message',`"${command}" 전송 중`);set('request-id','—');latestRequest=null;const body={command};if(command==='FORWARD'||command==='REVERSE')body.linear_speed_mps=linearSpeed;if(command==='LEFT'||command==='RIGHT')body.angular_speed_radps=angularSpeed;try{if(command.startsWith('REACTION_'))body.reaction_settings=readReactionSettings();const response=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-GCS-Token':token},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)});const result=await response.json();if(!response.ok)throw Error(result.error||'전송 결과 확인 불가');latestRequest=result.request_id||null;set('command-message',result.text);set('request-id',latestRequest||'—');}catch(error){set('command-message',`${error.message} · 자동 재전송하지 않습니다.`);}finally{busy=false;controls();}}
function enqueue(command,select=true){commandQueue=commandQueue.then(()=>send(command,select));return commandQueue;}
document.querySelectorAll('[data-command]').forEach(button=>button.addEventListener('click',()=>{cancelDrive();enqueue(button.dataset.command);}));
const driveKeys={
 ArrowUp:'FORWARD',ArrowLeft:'LEFT',ArrowDown:'REVERSE',ArrowRight:'RIGHT',
 PageUp:'FORWARD',Home:'LEFT',PageDown:'REVERSE',End:'RIGHT'
};
const speedInput=el('linear-speed');
function updateSpeedDisplay(){linearSpeed=Math.max(0.01,Math.min(0.4,Math.round(linearSpeed*100)/100));speedInput.value=linearSpeed.toFixed(2);set('linear-speed-value',linearSpeed.toFixed(2)+' m/s');}
speedInput.addEventListener('input',()=>{linearSpeed=Number(speedInput.value);speedInitialized=true;updateSpeedDisplay();});
el('speed-control').addEventListener('wheel',event=>{event.preventDefault();linearSpeed+=event.deltaY<0?0.01:-0.01;speedInitialized=true;updateSpeedDisplay();},{passive:false});
updateSpeedDisplay();
const angularSpeedInput=el('angular-speed');
function updateAngularSpeedDisplay(){angularSpeed=Math.max(0.01,Math.min(3.8,Math.round(angularSpeed*100)/100));angularSpeedInput.value=angularSpeed.toFixed(2);set('angular-speed-value',angularSpeed.toFixed(2)+' rad/s');}
angularSpeedInput.addEventListener('input',()=>{angularSpeed=Number(angularSpeedInput.value);angularSpeedInitialized=true;updateAngularSpeedDisplay();});
el('angular-speed-control').addEventListener('wheel',event=>{event.preventDefault();angularSpeed+=event.deltaY<0?0.01:-0.01;angularSpeedInitialized=true;updateAngularSpeedDisplay();},{passive:false});
updateAngularSpeedDisplay();
let activeDriveKey=null,driveTimer=null,driveSending=false,driveEpoch=0;
function cancelDrive(){const held=activeDriveKey!==null;if(driveTimer!==null){clearInterval(driveTimer);driveTimer=null;}activeDriveKey=null;driveEpoch++;return held;}
async function drivePulse(){if(!activeDriveKey||driveSending)return;const key=activeDriveKey,epoch=driveEpoch;driveSending=true;try{commandQueue=commandQueue.then(()=>{if(activeDriveKey===key&&driveEpoch===epoch)return send(driveKeys[key],false);});await commandQueue;}finally{driveSending=false;}}
function stopDrive(){if(cancelDrive())enqueue('MANUAL',false);}
window.addEventListener('keydown',event=>{if(el('commands').hidden||event.target?.closest?.('input, select, textarea, [contenteditable], .speed-control'))return;const command=driveKeys[event.key];if(!command)return;event.preventDefault();if(event.repeat||activeDriveKey!==null||!current||current.connection!=='CONNECTED')return;activeDriveKey=event.key;drivePulse();const interval=current.manual_control?.repeat_interval_ms||100;driveTimer=setInterval(drivePulse,interval);});
window.addEventListener('keyup',event=>{if(!driveKeys[event.key])return;event.preventDefault();if(event.key!==activeDriveKey)return;stopDrive();});
window.addEventListener('blur',stopDrive);
el('event-filter').addEventListener('change',drawEvents);
setInterval(()=>{set('clock',clockTime());renderMonitoring();},1000);

const reactionDefaults={esc_neutral:1488,servo_neutral:1500,left_first_offset:25,left_second_offset:50,right_first_offset:25,right_second_offset:50,servo_left:800,servo_right:2200,left_first_ms:5000,right_first_ms:10000,second_ms:10000,servo_delay_ms:10,servo_hold_ms:3000,prepare_ms:5000};
function reactionScale(key){return key.endsWith('_ms')&&key!=='servo_delay_ms'?1000:1;}
function readReactionSettings(){const values={};for(const key of Object.keys(reactionDefaults)){const input=el('reaction-'+key),value=Number(input.value)*reactionScale(key);if(input.value===''||!Number.isFinite(value)||Math.abs(value-Math.round(value))>1e-6)throw Error('리액션휠 설정 숫자를 확인하세요');values[key]=Math.round(value);}return values;}
function reactionPreview(){try{const v=readReactionSettings();set('reaction-preview',`왼쪽: ESC ${v.esc_neutral+v.left_first_offset} µs × ${v.left_first_ms/1000}초 → ${v.esc_neutral+v.left_second_offset} µs × ${v.second_ms/1000}초 → ${v.esc_neutral} µs → ${v.servo_delay_ms}ms 후 서보 ${v.servo_left} µs × ${v.servo_hold_ms/1000}초\n오른쪽: ESC ${v.esc_neutral-v.right_first_offset} µs × ${v.right_first_ms/1000}초 → ${v.esc_neutral-v.right_second_offset} µs × ${v.second_ms/1000}초 → ${v.esc_neutral} µs → ${v.servo_delay_ms}ms 후 서보 ${v.servo_right} µs × ${v.servo_hold_ms/1000}초\n종료: ESC ${v.esc_neutral} µs / 서보 ${v.servo_neutral} µs`);}catch(error){set('reaction-preview',error.message);}}
function resetReaction(){for(const [key,value] of Object.entries(reactionDefaults))el('reaction-'+key).value=value/reactionScale(key);reactionPreview();}
for(const key of Object.keys(reactionDefaults))el('reaction-'+key).addEventListener('input',reactionPreview);
el('reaction-reset').addEventListener('click',resetReaction);
resetReaction();
// UI history is bounded to one minute and is never filled with invented samples.
const chartSpecs = {
 temperature: {unit:'°C', digits:1, range:[30, 90]},
 battery: {unit:'V', digits:2, range:[10, 18]},
 wifi: {unit:'dBm', digits:0, range:[-100, -30]},
};
const monitorHistory = Object.fromEntries(Object.keys(chartSpecs).map(key=>[key, []]));
let lastMonitorState = null, lastMonitorAt = 0;
function initPanels() {
 let saved = {};
 try { saved = JSON.parse(localStorage.getItem('loonar.visiblePanels') || '{}') || {}; } catch (_) {}
 for (const button of document.querySelectorAll('[data-panel]')) {
  const id = button.dataset.panel;
  const apply = visible => {
   el(id).hidden = !visible;
   button.setAttribute('aria-pressed', String(visible));
   button.title = visible ? '표시 중 · 클릭하여 숨김' : '숨김 · 클릭하여 표시';
  };
  apply(saved[id] !== false);
  button.addEventListener('click', () => {
   const visible = el(id).hidden;
   if (id === 'commands' && !visible) stopDrive();
   apply(visible);
   saved[id] = visible;
   try { localStorage.setItem('loonar.visiblePanels', JSON.stringify(saved)); } catch (_) {}
  });
 }
}
function monitorValues(s) {
 const v = s?.status?.values || {};
 const live = s?.connection === 'CONNECTED' && !s.status_stale;
 const hardware = s?.hardware?.age_s != null && s.hardware.age_s <= 4 ? s.hardware.data : null;
 const wifi = (Array.isArray(hardware?.wireless) ? hardware.wireless : []).find(item=>Number.isFinite(item?.signal_dbm));
 return {
  temperature: hardware ? hardware.cpu_temperature_c : s?.pi_temperature ? (s.pi_temperature.age_s != null && s.pi_temperature.age_s < 3 ? s.pi_temperature.celsius : null) : (live ? v['라즈베리파이 내부 온도 (°C)'] : null),
  battery: hardware ? (hardware.control?.online && !hardware.control.stale ? hardware.control.battery_v : null) : live ? v['배터리 전압 (V)'] : null,
  wifi: wifi?.signal_dbm ?? null,
 };
}
function updateMonitoring(s) {
 const now = Date.now();
 lastMonitorState = s;
 lastMonitorAt = now;
 const values = monitorValues(s);
 for (const key of Object.keys(chartSpecs)) {
  const history = monitorHistory[key];
  history.push({time:now, value:Number.isFinite(values[key]) ? values[key] : null});
 }
 renderMonitoring(now);
}
function renderMonitoring(now = Date.now()) {
 const s = now - lastMonitorAt < 3000 ? lastMonitorState : null;
 const values = monitorValues(s);
 for (const [key, spec] of Object.entries(chartSpecs)) {
  const history = monitorHistory[key];
  while (history.length && history[0].time < now - 60000) history.shift();
  const valid = history.filter(point=>Number.isFinite(point.value));
  const low = Math.min(spec.range[0], ...valid.map(point=>point.value));
  const high = Math.max(spec.range[1], ...valid.map(point=>point.value));
  const value = values[key];
  set(key+'-reading', Number.isFinite(value) ? `${value.toFixed(spec.digits)} ${spec.unit}` : '—');
  set(key+'-quality', Number.isFinite(value) ? '최근 60초' : (valid.length ? '수신 끊김 · 이전 기록' : '데이터 없음'));
  set(key+'-max', high.toFixed(spec.digits === 2 ? 1 : 0));
  set(key+'-min', low.toFixed(spec.digits === 2 ? 1 : 0));
  let path = '', previous = null;
  for (const point of history) {
   if (!Number.isFinite(point.value)) {previous = null; continue;}
   const x = 38 + (point.time - now + 60000) / 60000 * 270;
   const y = 108 - (point.value - low) / (high - low) * 96;
   const connected = previous && point.time - previous.time < 3000;
   path += `${connected ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)} `;
   // A single sample is visible too; gaps remain unconnected.
   if (!connected) path += `l0.1,0 `;
   previous = point;
  }
  el(key+'-line').setAttribute('d', path);
 }
 const live = s?.connection === 'CONNECTED' && !s.status_stale;
 const v = s?.status?.values || {};
 const hardware = s?.hardware?.age_s != null && s.hardware.age_s <= 4 ? s.hardware.data : null;
 set('pi-input', Number.isFinite(hardware?.input_voltage_v) ? `${hardware.input_voltage_v.toFixed(2)} V` : '— · 데이터 없음');
 el('wifi-reading').title = (Array.isArray(hardware?.wireless) ? hardware.wireless : []).find(item=>Number.isFinite(item?.signal_dbm))?.interface || '';
 for (const [role, id, label] of [['control','control-state','Control'],['payload','payload-mcu-state','Payload']]) {
  const mcu = s?.mcu?.[role];
  const status = hardware?.[role];
  const state = status ? (status.stale ? '수신 끊김' : status.online ? 'ONLINE' : 'OFFLINE') : !live ? '수신 끊김' : mcu ? (mcu.online && mcu.health_age_ms < 3000 ? 'ONLINE' : 'OFFLINE') : (v[label+' MCU 연결'] || '수신 대기');
  set(id, state);
  el(id).className = state === 'ONLINE' ? 'value-online' : state === 'OFFLINE' ? 'value-offline' : 'muted';
 }
}

function payloadKey(sample) {
 return JSON.stringify(['request_id','sample','time','mcu_uid','mcu_boot'].map(key=>sample[key] ?? null));
}
function drawPayload(s) {
 const sample = s.payload_sample;
 const readings = sample?.values || {};
 const trace = sample && s.payload_trace?.key === payloadKey(sample) ? s.payload_trace : null;
 const transfer = sample && s.payload_trace_status?.key === payloadKey(sample) ? s.payload_trace_status : null;
 const state = s.status?.payload?.state;
 set('sample-number', sample ? `SEQ ${String(sample.sample).padStart(3,'0')}` : 'SEQ —');
 set('sample-freshness', !sample ? '완료된 측정 대기' : ['STARTING','MEASURING','STOPPING'].includes(state) ? '직전 결과 보관 · 새 측정 진행 중' : '최근 완료 시퀀스');
 set('payload-csv-state', trace ? `${trace.sample_count}표본 · ${trace.duration_s.toFixed(1)}초 · ${(trace.bytes/1024).toFixed(1)} KiB` : transfer?.state === 'error' ? transfer.message+' · 재시도 중' : sample ? '시계열 CSV 가져오는 중' : '시계열 수신 대기');
 const keys = ['비접촉 표면온도계','접촉식 표면온도계','자기상센서'];
 keys.forEach((key, i) => {
  const reading = readings[key];
  set('sensor-'+i, Number.isFinite(reading?.value) ? `${reading.value.toFixed(2)} ${reading.unit === 'TBD' ? '' : reading.unit || ''}` : '—');
  set('sensor-status-'+i, reading?.status || '수신 대기');
  const points = trace?.points || [];
  const values = points.map(point=>point.values[i]).filter(Number.isFinite);
  const minimum = values.length ? Math.min(...values) : 0;
  const maximum = values.length ? Math.max(...values) : 1;
  const pad = Math.max((maximum-minimum)*.15, i===2 ? .5 : .2);
  const low = minimum-pad, high = maximum+pad;
  set(`payload-${i}-max`, values.length ? high.toFixed(1) : '—');
  set(`payload-${i}-min`, values.length ? low.toFixed(1) : '—');
  set(`payload-${i}-end`, trace ? trace.duration_s.toFixed(1)+'초' : '—');
  let path = '', connected = false;
  for (const point of points) {
   const value = point.values[i];
   if (!Number.isFinite(value)) {connected=false; continue;}
   const x = 38 + point.t / Math.max(trace.duration_s, .001) * 270;
   const y = 108 - (value-low)/(high-low)*96;
   if (point.gap_before) connected = false;
   path += `${connected ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)} `;
   if (!connected) path += 'l0.1,0 ';
   connected = true;
  }
  el(`payload-${i}-line`).setAttribute('d', path);
 });
 const candidate = readings['PCA candidate'];
 const score = readings['PCA novelty']?.value;
 const model = readings['PCA model']?.value;
 const status = candidate?.status;
 const valid = Number.isFinite(score) && [0,1].includes(candidate?.value) && ['TRAINED_MODEL','DEMO_ONLY'].includes(status);
 const result = !sample ? 'waiting' : valid ? (candidate.value === 1 ? 'candidate' : 'within') : 'invalid';
 el('pca-result').setAttribute('data-result', result);
 set('pca-candidate', {waiting:'판정 대기',candidate:'추가 확인 후보',within:'후보 아님',invalid:'판정 불가'}[result]);
 set('pca-status', {waiting:'측정 종료 후 표시됩니다.',candidate:'모델 기준을 초과한 측정입니다.',within:'모델 기준 이내의 측정입니다.',invalid:'측정 품질 또는 결과 상태를 확인하세요.'}[result]);
 set('pca-novelty', Number.isFinite(score) ? score.toFixed(3) : '—');
 set('pca-model', model || '—');
 set('sample-time', trace ? '시퀀스 시작부터 종료까지 · 원시 측정값' : sample ? '센서 중앙값 수신 · 시계열 미수신' : '측정값 수신 대기');
 set('payload-id', sample ? `요청 ${sample.request_id ?? '—'}` : '요청 —');
}

initPanels();
poll();
