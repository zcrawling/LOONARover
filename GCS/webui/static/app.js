'use strict';
let current=null, token='', busy=false, latestRequest=null, commandQueue=Promise.resolve(), linearSpeed=0.1, speedInitialized=false;
const el=id=>document.getElementById(id);
const set=(id,text)=>{el(id).textContent=text;};
function badge(id,text,kind=''){set(id,text);el(id).className='badge '+kind;}
function controls(){document.querySelectorAll('[data-command]').forEach(b=>{b.disabled=!current||current.connection!=='CONNECTED'||busy;});}
function selectCommand(command){document.querySelectorAll('[data-command]').forEach(button=>{const selected=button.dataset.command===command;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));});}
function number(value,unit=''){return typeof value==='number'&&Number.isFinite(value)?`${value}${unit}`:'—';}
function drawEvents(){
 const filter=el('event-filter').value;
 const events=(current?.events||[]).filter(e=>filter==='all'||(filter==='commands'?!!e.request_id:!e.request_id)).slice().reverse();
 el('event-list').replaceChildren();
 for(const e of events){const row=document.createElement('div');row.className='event';const time=document.createElement('time');const d=new Date(e.time);time.textContent=Number.isNaN(d.getTime())?'—':d.toLocaleTimeString('ko-KR',{hour12:false});const msg=document.createElement('span');msg.textContent=e.text;msg.className=/Completed|Received|CONNECTED/.test(e.text)?'success':/Unknown|Failed|RECONNECTING|DEGRADED|Aborted/.test(e.text)?'warning':'';const id=document.createElement('code');id.textContent=e.request_id?e.request_id.slice(0,12):'—';id.title=e.request_id||'';row.append(time,msg,id);el('event-list').append(row);}
 if(!events.length){const p=document.createElement('p');p.className='muted';p.textContent='표시할 이벤트가 없습니다.';el('event-list').append(p);}
}
function draw(s){
 current=s;token=s.csrf_token;const good=s.connection==='CONNECTED';
 if(!speedInitialized&&typeof s.manual_control?.linear_speed_mps==='number'){linearSpeed=s.manual_control.linear_speed_mps;speedInitialized=true;updateSpeedDisplay();}
 set('environment',s.source||'데이터 출처 미확인');
 const liveAge=s.last_rx_age==null?'수신 없음':`${s.last_rx_age.toFixed(1)}초 전 수신`;
 badge('connection',good?`실시간 연결 · RX ${s.rx_messages} · ${liveAge}`:`연결 끊김 · ${s.connection}`,good?'good':s.connection==='DEGRADED'?'warn':'bad');
 set('health',s.connection);set('mode',s.status?.mode||'—');set('age',s.last_rx_age==null?'—':`${s.last_rx_age.toFixed(1)}초`);set('counts',`${s.rx_messages} / ${s.tx_messages}`);set('gaps',s.data_gaps);
 const notice=el('notice');notice.className='notice'+(good?'':' error');notice.textContent=good?(s.source||'TCP 연결')+' · 수신 상태와 명령 결과를 확인하세요.':`TCP ${s.connection} · 현재 상태를 확인할 수 없습니다. 명령 전송을 사용할 수 없습니다.`;
 badge('stale',s.status_stale?'이전 상태':'갱신 중',s.status_stale?'warn':'good');
 const sources=s.status?.value_sources||{};el('battery-summary').hidden=sources['배터리 잔량 (%)']==='ROS';
 const v=s.status?.values||{};set('battery',number(v['배터리 잔량 (%)'],'%'));set('temperature',number(v['라즈베리파이 내부 온도 (°C)'],' °C'));el('battery-fill').style.width=typeof v['배터리 잔량 (%)']==='number'?Math.max(0,Math.min(100,v['배터리 잔량 (%)']))+'%':'0%';
 el('devices').replaceChildren();el('ros-values').replaceChildren();let rosCount=0;
 for(const key of Object.keys(v)){
  const ros=sources[key]==='ROS';
  if(!ros&&(key==='배터리 잔량 (%)'||key==='라즈베리파이 내부 온도 (°C)'))continue;
  const row=document.createElement('div');row.className='device';const label=document.createElement('span');label.textContent=key;const value=document.createElement('span');value.className='value';value.textContent=v[key]??'—';row.append(label,value);el(ros?'ros-values':'devices').append(row);if(ros)rosCount++;
 }
 if(!rosCount){const message=document.createElement('p');message.className='muted';message.textContent='ROS 데이터 수신 대기';el('ros-values').append(message);}
 badge('ros-stale',rosCount?(s.status_stale?'이전 상태':'수신 중'):'대기',rosCount?(s.status_stale?'warn':'good'):'');
 const p=s.status?.payload||{};badge('payload-state',p.state||'IDLE',p.state==='MEASURING'?'good':'');
 const sample=s.payload_sample;const same=sample&&sample.request_id===p.request_id;const keys=['비접촉 표면온도계','접촉식 표면온도계','자기상센서'];keys.forEach((key,i)=>{const reading=same?sample.values[key]:null;set('sensor-'+i,reading?number(reading.value,reading.unit==='TBD'?'':' '+reading.unit):'—');set('sensor-status-'+i,reading?.status||'수신 대기');});
 set('sample-time',same?`측정 시각 ${sample.time}`:'측정값 수신 대기');set('sample-number',same?`샘플 #${sample.sample}`:'샘플 —');set('payload-id',`요청 ${p.request_id||'—'}`);set('sample-freshness',same?(s.sample_stale?'이전 측정값':'실시간 갱신'):'—');
 if(latestRequest){const r=s.requests.find(r=>r.request_id===latestRequest);if(r&&r.state!=='Pending')set('command-message',`"${r.command}" ${r.state}`);}
 set('updated','갱신 '+new Date().toLocaleTimeString('ko-KR',{hour12:false}));controls();drawEvents();
}
async function poll(){try{const response=await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(9000)});if(!response.ok)throw Error('backend unavailable');draw(await response.json());}catch(error){current=null;token='';badge('connection','연결 끊김 · BACKEND OFFLINE','bad');set('health','OFFLINE');el('notice').className='notice error';set('notice','백엔드에 연결할 수 없습니다. 마지막 표시값은 이전 데이터입니다. 자동으로 다시 확인합니다.');badge('stale','이전 상태','warn');badge('ros-stale','이전 상태','warn');set('sample-freshness','이전 측정값');controls();}finally{setTimeout(poll,700);}}
async function send(command,select=true){if(!current||current.connection!=='CONNECTED')return;if(select)selectCommand(command);busy=true;controls();set('command-message',`"${command}" 전송 중`);set('request-id','—');latestRequest=null;const body={command};if(command==='FORWARD'||command==='REVERSE')body.linear_speed_mps=linearSpeed;try{const response=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-GCS-Token':token},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)});const result=await response.json();if(!response.ok)throw Error(result.error||'전송 결과 확인 불가');latestRequest=result.request_id||null;set('command-message',result.text);set('request-id',latestRequest||'—');}catch(error){set('command-message',`${error.message} · 자동 재전송하지 않습니다.`);}finally{busy=false;controls();}}
function enqueue(command,select=true){commandQueue=commandQueue.then(()=>send(command,select));return commandQueue;}
document.querySelectorAll('[data-command]').forEach(button=>button.addEventListener('click',()=>enqueue(button.dataset.command)));
const driveKeys={
 ArrowUp:'FORWARD',ArrowLeft:'LEFT',ArrowDown:'REVERSE',ArrowRight:'RIGHT',
 PageUp:'FORWARD',Home:'LEFT',PageDown:'REVERSE',End:'RIGHT'
};
const speedInput=el('linear-speed');
function updateSpeedDisplay(){linearSpeed=Math.max(0.01,Math.min(1,Math.round(linearSpeed*100)/100));speedInput.value=linearSpeed.toFixed(2);set('linear-speed-value',linearSpeed.toFixed(2)+' m/s');}
speedInput.addEventListener('input',()=>{linearSpeed=Number(speedInput.value);speedInitialized=true;updateSpeedDisplay();});
el('speed-control').addEventListener('wheel',event=>{event.preventDefault();linearSpeed+=event.deltaY<0?0.01:-0.01;speedInitialized=true;updateSpeedDisplay();},{passive:false});
updateSpeedDisplay();
let activeDriveKey=null,driveTimer=null,driveSending=false;
async function drivePulse(){if(!activeDriveKey||driveSending)return;driveSending=true;try{await send(driveKeys[activeDriveKey],false);}finally{driveSending=false;}}
function stopDrive(){if(driveTimer!==null){clearInterval(driveTimer);driveTimer=null;}if(activeDriveKey!==null){activeDriveKey=null;send('MANUAL',false);}}
window.addEventListener('keydown',event=>{const command=driveKeys[event.key];if(!command)return;event.preventDefault();if(event.repeat||activeDriveKey!==null||!current||current.connection!=='CONNECTED')return;activeDriveKey=event.key;drivePulse();const interval=current.manual_control?.repeat_interval_ms||100;driveTimer=setInterval(drivePulse,interval);});
window.addEventListener('keyup',event=>{if(!driveKeys[event.key])return;event.preventDefault();if(event.key!==activeDriveKey)return;stopDrive();});
window.addEventListener('blur',stopDrive);
el('event-filter').addEventListener('change',drawEvents);
setInterval(()=>set('clock',new Date().toLocaleTimeString('ko-KR',{hour12:false})),1000);
poll();
