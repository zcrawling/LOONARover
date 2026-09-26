'use strict';
let current=null, token='', busy=false, latestRequest=null, commandQueue=Promise.resolve(), linearSpeed=0.1, speedInitialized=false, angularSpeed=0.2, angularSpeedInitialized=false;
const el=id=>document.getElementById(id);
const set=(id,text)=>{el(id).textContent=text;};
const connectionLabels={CONNECTED:'정상 연결',CONNECTING:'연결 중',RECONNECTING:'재연결 중',DISCONNECTED:'연결 끊김',DEGRADED:'통신 불안정'};
function badge(id,text,kind=''){set(id,text);el(id).className='badge '+kind;}
function controls(){document.querySelectorAll('[data-command]').forEach(b=>{b.disabled=!current||current.connection!=='CONNECTED'||busy;});}
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
 const sources=s.status?.value_sources||{};
 const v=s.status?.values||{},voltage=v['배터리 전압 (V)'],percent=v['배터리 잔량 (%)'];
 const showVoltage=sources['배터리 전압 (V)']==='VEHICLE'||Number.isFinite(voltage);
 el('battery-summary').hidden=!showVoltage&&sources['배터리 잔량 (%)']==='ROS';
 set('battery-label',showVoltage?'배터리 전압':'배터리 잔량');set('battery',showVoltage?number(voltage,' V'):number(percent,'%'));
 el('battery-fill').parentElement.hidden=showVoltage||!Number.isFinite(percent);
 el('battery-fill').style.width=Number.isFinite(percent)?Math.max(0,Math.min(100,percent))+'%':'0%';
 set('temperature',number(v['Control MCU 온도 (°C)']??v['MCU 온도 (°C)'],' °C'));
 el('devices').replaceChildren();el('ros-values').replaceChildren();let rosCount=0;
 for(const key of Object.keys(v)){
  const ros=['ROS','VEHICLE'].includes(sources[key]);
  if(!ros&&['배터리 잔량 (%)','라즈베리파이 내부 온도 (°C)','Control MCU 온도 (°C)','MCU 온도 (°C)'].includes(key))continue;
  const row=document.createElement('div');row.className='device';const label=document.createElement('span');label.textContent=key;const value=document.createElement('span');value.className='value';value.textContent=v[key]??'—';if(v[key]==='ONLINE')value.classList.add('value-online');if(v[key]==='OFFLINE')value.classList.add('value-offline');row.append(label,value);el(ros?'ros-values':'devices').append(row);if(ros)rosCount++;
 }
 if(!rosCount){const message=document.createElement('p');message.className='muted';message.textContent='차량 측정값 수신 대기';el('ros-values').append(message);}
 badge('ros-stale',rosCount?(s.status_stale?'이전 상태':'수신 중'):'대기',rosCount?(s.status_stale?'warn':'good'):'');
 const p=s.status?.payload||{};badge('payload-state',p.state||'IDLE',p.state==='MEASURING'?'good':'');
 const sample=s.payload_sample;const same=sample&&sample.request_id===p.request_id;const keys=['비접촉 표면온도계','접촉식 표면온도계','자기상센서'];keys.forEach((key,i)=>{const reading=same?sample.values[key]:null;set('sensor-'+i,reading?number(reading.value,reading.unit==='TBD'?'':' '+reading.unit):'—');set('sensor-status-'+i,reading?.status||'수신 대기');});
 set('sample-time',same?`측정 시각 ${sample.time}`:'측정값 수신 대기');set('sample-number',same?`샘플 #${sample.sample}`:'샘플 —');set('payload-id',`요청 ${p.request_id||'—'}`);set('sample-freshness',same?(s.sample_stale?'이전 측정값':'실시간 갱신'):'—');
 if(latestRequest){const r=s.requests.find(r=>r.request_id===latestRequest);if(r&&r.state!=='Pending')set('command-message',`"${r.command}" ${r.state}`);}
 set('updated','갱신 '+clockTime());controls();drawEvents();
}
async function poll(){try{const response=await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(9000)});if(!response.ok)throw Error('backend unavailable');draw(await response.json());}catch(error){current=null;token='';badge('connection','백엔드 연결 끊김','bad');el('connection').title='BACKEND OFFLINE';set('health','OFFLINE');el('notice').hidden=false;el('notice').className='notice error';set('notice','백엔드에 연결할 수 없습니다. 마지막 표시값은 이전 데이터입니다. 자동으로 다시 확인합니다.');badge('stale','이전 상태','warn');badge('ros-stale','이전 상태','warn');set('sample-freshness','이전 측정값');controls();}finally{setTimeout(poll,700);}}
async function send(command,select=true){if(!current||current.connection!=='CONNECTED')return;if(select)selectCommand(command);busy=true;controls();set('command-message',`"${command}" 전송 중`);set('request-id','—');latestRequest=null;const body={command};if(command==='FORWARD'||command==='REVERSE')body.linear_speed_mps=linearSpeed;if(command==='LEFT'||command==='RIGHT')body.angular_speed_radps=angularSpeed;try{const response=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-GCS-Token':token},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)});const result=await response.json();if(!response.ok)throw Error(result.error||'전송 결과 확인 불가');latestRequest=result.request_id||null;set('command-message',result.text);set('request-id',latestRequest||'—');}catch(error){set('command-message',`${error.message} · 자동 재전송하지 않습니다.`);}finally{busy=false;controls();}}
function enqueue(command,select=true){commandQueue=commandQueue.then(()=>send(command,select));return commandQueue;}
document.querySelectorAll('[data-command]').forEach(button=>button.addEventListener('click',()=>{cancelDrive();enqueue(button.dataset.command);}));
const driveKeys={
 ArrowUp:'FORWARD',ArrowLeft:'LEFT',ArrowDown:'REVERSE',ArrowRight:'RIGHT',
 PageUp:'FORWARD',Home:'LEFT',PageDown:'REVERSE',End:'RIGHT'
};
const speedInput=el('linear-speed');
function updateSpeedDisplay(){linearSpeed=Math.max(0.01,Math.min(1,Math.round(linearSpeed*100)/100));speedInput.value=linearSpeed.toFixed(2);set('linear-speed-value',linearSpeed.toFixed(2)+' m/s');}
speedInput.addEventListener('input',()=>{linearSpeed=Number(speedInput.value);speedInitialized=true;updateSpeedDisplay();});
el('speed-control').addEventListener('wheel',event=>{event.preventDefault();linearSpeed+=event.deltaY<0?0.01:-0.01;speedInitialized=true;updateSpeedDisplay();},{passive:false});
updateSpeedDisplay();
const angularSpeedInput=el('angular-speed');
function updateAngularSpeedDisplay(){angularSpeed=Math.max(0.01,Math.min(1,Math.round(angularSpeed*100)/100));angularSpeedInput.value=angularSpeed.toFixed(2);set('angular-speed-value',angularSpeed.toFixed(2)+' rad/s');}
angularSpeedInput.addEventListener('input',()=>{angularSpeed=Number(angularSpeedInput.value);angularSpeedInitialized=true;updateAngularSpeedDisplay();});
el('angular-speed-control').addEventListener('wheel',event=>{event.preventDefault();angularSpeed+=event.deltaY<0?0.01:-0.01;angularSpeedInitialized=true;updateAngularSpeedDisplay();},{passive:false});
updateAngularSpeedDisplay();
let activeDriveKey=null,driveTimer=null,driveSending=false,driveEpoch=0;
function cancelDrive(){const held=activeDriveKey!==null;if(driveTimer!==null){clearInterval(driveTimer);driveTimer=null;}activeDriveKey=null;driveEpoch++;return held;}
async function drivePulse(){if(!activeDriveKey||driveSending)return;const key=activeDriveKey,epoch=driveEpoch;driveSending=true;try{commandQueue=commandQueue.then(()=>{if(activeDriveKey===key&&driveEpoch===epoch)return send(driveKeys[key],false);});await commandQueue;}finally{driveSending=false;}}
function stopDrive(){if(cancelDrive())enqueue('MANUAL',false);}
window.addEventListener('keydown',event=>{if(event.target?.closest?.('.speed-control'))return;const command=driveKeys[event.key];if(!command)return;event.preventDefault();if(event.repeat||activeDriveKey!==null||!current||current.connection!=='CONNECTED')return;activeDriveKey=event.key;drivePulse();const interval=current.manual_control?.repeat_interval_ms||100;driveTimer=setInterval(drivePulse,interval);});
window.addEventListener('keyup',event=>{if(!driveKeys[event.key])return;event.preventDefault();if(event.key!==activeDriveKey)return;stopDrive();});
window.addEventListener('blur',stopDrive);
el('event-filter').addEventListener('change',drawEvents);
setInterval(()=>set('clock',clockTime()),1000);
poll();
