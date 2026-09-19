import fs from 'node:fs/promises';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const out = new URL('./', import.meta.url).pathname;
const wb = Workbook.create();
const rows = [];
function group(letter, category, items) {
  items.forEach(([title, detail, classification='설계 제안', dependency='GCS'], i) => rows.push([
    `${letter}${i+1}`, category, title, detail, classification, dependency, '검토 전', '', ''
  ]));
}
group('A','개발 범위',[
 ['백엔드 우선','GUI보다 백엔드를 먼저 개발하고 터미널로 통신과 기능을 검증한다.','사용자 요청'],
 ['초기 GUI 제외','초기 버전은 웹 화면 없이 터미널에서 사용한다.','사용자 요청'],
 ['세 개의 창','GStreamer 영상 창, 명령 입력·응답 창, 지속적인 상태 출력 창을 사용한다.','사용자 요청'],
 ['백엔드 재사용','추후 GUI에서도 기존 백엔드와 로컬 API를 재사용하도록 구성한다.'],
 ['변경 범위','파일 생성·수정은 LOONARover/GCS/ 내부에서만 허용한다. 로버 측 변경은 별도 허용이 필요하다.','사용자 요청','작업 전반'],
 ['대화 후 파일 반영','먼저 대화로 검토하고 사용자가 파일 반영을 요청할 때만 생성·수정한다. 이번 엑셀 생성은 요청됨.','사용자 요청','작업 전반']
]);
group('B','네트워크',[
 ['Wi-Fi AP','라즈베리파이와 지상국 PC가 Wi-Fi AP를 통해 통신한다.','사용자 요청','AP·로버·GCS'],
 ['세 통신 경로','영상 UDP 5600, 메인 TCP 7443, ROS 2 DDS 관측 경로를 분리한다.','사용자 요청','로버·GCS'],
 ['공유 대역폭 검증','세 경로는 같은 무선 대역폭을 공유한다. 영상·지도 전송 중 제어 응답을 확인한다.','설계 제안','AP·로버·GCS'],
 ['주소 설정 관리','IP·포트는 소스에 고정하지 않고 설정에서 관리한다. DHCP 예약을 검토한다.','설계 제안','AP·GCS']
]);
group('C','백엔드',[
 ['TCP 연결 하나','백엔드 하나가 로버 cFS GroundLink와 TCP 연결 하나를 유지한다.','기존 문서 기준'],
 ['양방향 송수신','같은 TCP 연결로 명령 송신과 상태·결과 수신을 동시에 처리한다.'],
 ['터미널 연결 방식','두 터미널은 같은 PC의 백엔드에 연결한다. 각각 로버에 직접 접속하지 않는다.'],
 ['통신 처리','GroundLink 생성·해석, TCP 수신 버퍼, 요청·응답 연결, 상태 저장, 재접속과 로컬 API를 구현한다.'],
 ['재접속 시 동작','연결·재접속 시 자동으로 모드 변경 명령을 보내지 않고 로버 상태를 받아 표시한다.','기존 문서 기준']
]);
group('D','차량 명령',[
 ['다섯 명령','STOP, MANUAL, AUTO, PAYLOAD, REACTION을 입력할 수 있어야 한다.','사용자 요청','GCS·로버'],
 ['MANUAL 형식','현재 MANUAL은 선속도·각속도를 함께 전달하며 수동 모드 전환도 수행한다.','기존 문서 기준','GCS·로버'],
 ['실제 모드 표시','마지막으로 입력한 명령이 아니라 로버가 보고한 상태를 기준으로 현재 모드를 표시한다.','기존 문서 기준'],
 ['활동 명령 명세','PAYLOAD·REACTION의 opcode·매개변수는 하드웨어 명세에 따른다. 미구현 기능은 명확히 표시한다.','추가 결정 필요','로버·MCU 명세']
]);
group('E','명령 확인',[
 ['로버 결과 표시','입력한 명령의 로버 처리 결과를 받아 명령 입력 창에 표시한다.','사용자 요청','GCS·로버'],
 ['요청 번호','명령마다 번호를 붙여 요청과 응답을 대응시킨다.','기존 문서 기준'],
 ['처리 단계 구별','전송됨, 응답 대기, 로버 처리 결과, 실제 동작 확인, 응답 시간 초과를 구별한다.'],
 ['OK와 동작 완료','COMMAND_RESULT의 OK와 물리적 동작 완료를 구별한다. 필요하면 MCU·센서 데이터로 확인한다.','설계 제안','GCS·로버·MCU'],
 ['장시간 작업 완료','PAYLOAD처럼 시간이 걸리는 작업은 최종 완료를 확인할 결과 메시지가 필요하다.','추가 결정 필요','로버·MCU'],
 ['응답 시간 초과','응답이 없으면 실행 여부 확인 불가로 표시한다. 실패로 단정하거나 자동 재전송하지 않는다.','설계 제안','GCS']
]);
group('F','조이스틱',[
 ['MANUAL 조종','MANUAL 주행에서 조이스틱을 사용한다.','사용자 요청','입력 장치·GCS·로버'],
 ['속도 변환','조이스틱 입력을 선속도(m/s)와 각속도(rad/s)로 변환하여 메인 TCP로 전송한다.'],
 ['전송 값 표시','조이스틱 입력과 실제 전송 값을 확인할 수 있어야 한다.'],
 ['단계적 연결','터미널 속도 입력으로 통신을 먼저 검증한 뒤 조이스틱을 연결한다.'],
 ['세부 입력 정책','입력 장치 종류, 전송 주기, 중립·버튼 해제 동작, 연속 명령 응답 표시 방식을 정한다.','추가 결정 필요','입력 장치·GCS·로버']
]);
group('G','주요 상태',[
 ['상태 표시 항목','배터리 잔량·전압, 온도와 측정 대상, 센서·MCU·Wi-Fi 상태, 운용 모드, TCP 연결·수신 시각을 표시한다.','사용자 요청','GCS·로버·MCU'],
 ['값 유효성','미제공·유효하지 않은 값은 —로 표시하고 실제 0과 구별한다.','기존 문서 기준'],
 ['오래된 데이터','연결이 끊기면 이전 값을 최신 데이터처럼 표시하지 않는다.'],
 ['데이터 생산부','최종 MCU 온도·장치 상태 등의 실제 값을 만드는 로버 측 구현이 필요하다.','기존 문서 기준','로버·MCU']
]);
group('H','영상 파이프라인',[
 ['GStreamer 사용','송신과 수신 모두 GStreamer를 사용한다.','사용자 요청','로버·GCS'],
 ['송신 과정','카메라 → H.264 압축 → MPEG-TS 포장 → UDP 송신.','기존 문서 기준','로버 카메라·송신기'],
 ['수신·압축 해제','UDP 수신 → MPEG-TS 분리 → H.264 디코딩(압축 해제) → 영상 표시.','사용자 요청','GCS'],
 ['영상 데이터 분리','영상 데이터는 cFS와 GCS 백엔드를 통과하지 않는다.','기존 문서 기준','로버·GCS'],
 ['별도 영상 창','초기에는 GStreamer를 별도로 실행해 독립 영상 창으로 표시한다.','사용자 요청','GCS']
]);
group('I','영상 품질',[
 ['비트레이트 선택','지상국에서 1 / 3 / 5 Mbps 목표 비트레이트를 선택한다. 실제 전송에는 부가 데이터가 포함된다.','사용자 요청','GCS·로버 송신기'],
 ['송신 중 변경','링크 사용량이 크면 명령으로 송신 비트레이트를 낮출 수 있도록 한다. 가능 여부를 검증한다.','조건부 요청','GCS·로버 송신기'],
 ['변경 대안','실행 중 변경이 어렵다면 짧게 중단하고 새 설정으로 재시작하는 방식을 검토한다.','설계 제안','로버 송신기'],
 ['해상도·FPS 정책','비트레이트만 바꿀지 해상도·FPS도 함께 바꿀지 미정이다. 기존 프리셋은 해상도도 변경된다.','추가 결정 필요','로버 송신기'],
 ['적용 설정 확인','요청한 설정과 송신기에 실제 적용된 설정을 구별해서 표시한다.','설계 제안','GCS·로버'],
 ['수동 선택 우선','초기에는 사용자가 직접 선택한다. 자동 화질 조절은 후속 선택 기능으로 둔다.','설계 제안','GCS·로버']
]);
group('J','영상 제어',[
 ['송신 시작·중지','지상국 명령으로 영상 송신을 중지·시작해 링크 점유를 조절한다.','사용자 요청','GCS·로버'],
 ['명령 이름 제안','VIDEO_START, VIDEO_STOP, VIDEO_SET_BITRATE를 제안한다. 기존 GroundLink에 구현된 명령은 아니다.','설계 제안','GCS·cFS·영상 서비스'],
 ['TCP 제어 경로','영상 설정 명령·결과는 메인 TCP → cFS → 영상 제어 서비스 경로로 전달하도록 확장한다.','설계 제안','GCS·cFS·영상 서비스'],
 ['송신 측 중지','대역폭 절약은 라즈베리파이 송신 측에서 수행한다. 수신 창 종료·수신 UDP 차단만으로는 부족하다.','설계 제안','로버 송신기'],
 ['중지 방식','초기에는 영상 파이프라인 중지를 검토한다. UDP 출력만 일시 중지하는 방식은 선택 사항이다.','추가 결정 필요','로버 송신기'],
 ['다른 경로 유지','영상만 중지하고 차량 제어와 ROS 통신은 유지한다. 전체 UDP를 차단하지 않는다.','설계 제안','로버·GCS'],
 ['재시작 복구','재시작 후 키프레임·헤더 처리와 정상 디코딩을 확인하고 최신 영상을 표시한다.','설계 제안','로버·GCS'],
 ['STOP 구별','영상 송신 STOP과 차량 STOP은 별개의 명령으로 구별한다.'],
 ['송신·수신 상태 구별','로버의 송신 실행 상태와 지상국의 실제 영상 수신 상태를 따로 표시한다.','설계 제안','GCS·로버'],
 ['링크 단절 한계','Wi-Fi가 완전히 끊기면 영상 제어 명령도 전달되지 않는다. 무조건 즉시 중지된다고 가정하지 않는다.','설계 제안','로버·GCS']
]);
group('K','ROS 관측',[
 ['별도 경로','ROS 데이터는 메인 TCP와 별도로 관측한다.','사용자 요청','로버 ROS·지상국 도구'],
 ['관측 데이터','누적 이동경로, odom, TF, 2.5D 지도, 내부 파라미터·진단 데이터를 읽는다.','사용자 요청','로버 ROS·지상국 도구'],
 ['별도 프로그램','GCS 앱과 별도로 RViz2 등의 ROS 도구를 사용한다.','설계 제안','지상국 도구'],
 ['읽기 중심 운용','초기에는 읽기·관측용으로 사용하며 해당 도구에서 주행 명령·파라미터 변경을 보내지 않는다.','사용자 요청','로버 ROS·지상국 도구'],
 ['데이터 생성 의존성','누적 경로·2.5D 지도 생성 노드와 지도 형식에 맞는 표시 도구가 필요하다.','추가 결정 필요','로버 ROS·지상국 도구']
]);

const milestones = [
 ['L1','프로토콜','GroundLink 생성·해석 및 파서 테스트','분할·연속 수신과 잘못된 프레임 테스트 통과','C4','장비 없이 진행 가능'],
 ['L2','상태 수신','실제 TCP 연결과 상태 출력','현재 모드·상태가 들어오고 수신 시각 확인','B1~B4, C1~C4, G1','로버 cFS 실행 필요'],
 ['L3','명령·응답','명령 입력과 로버 처리 결과 표시','요청 번호에 맞는 응답·오류 확인','D1~D4, E1~E6','STOP·MANUAL(0,0)부터 검증'],
 ['L4','상태·재접속','상태 항목 확대와 단절·복구 처리','이전 값 구별 및 자동 모드 변경 없이 수신 복구','C5, G1~G4','미제공 상태값은 — 표시'],
 ['L5','조이스틱','수동 조이스틱 입력 연결','의도한 입력·전송 값·로버 반응 확인','F1~F5','물리 시험은 운영자가 정한 조건'],
 ['L6','GStreamer 영상','별도 UDP 영상 수신·디코딩','영상 표시와 TCP 제어 동시 동작','H1~H5','준비되면 백엔드와 별도 진행'],
 ['L7','영상 원격 제어','1/3/5 Mbps 변경·중지·재시작','적용 설정 확인 및 제어·ROS 유지','I1~I6, J1~J10','로버 cFS·송신기 확장 필요'],
 ['L8','ROS 관측','이동경로·odom·지도·파라미터 조회','필요 데이터를 읽기 도구로 관측','K1~K5','데이터 생성 노드·도구 필요'],
 ['L9','통합 검증','세 경로 동시 운용·혼잡·단절·복구','합의할 응답·영상 품질 기준 충족','B3, E, G, I, J, K','기준값은 검토 필요']
].map(r=>[...r,'미착수','','']);
const decisions = [
 ['Q1','F5','조이스틱 종류','물리 장치 / 화면 조이스틱 중 선택','','','미결정'],
 ['Q2','F5','입력 정책','전송 주기, 중립·버튼 해제 동작, 연속 응답 표시 방식','','','미결정'],
 ['Q3','I4','영상 해상도·FPS','고정 해상도에서 비트레이트만 변경 / 해상도·FPS도 변경','','','미결정'],
 ['Q4','I2~I3','송신 중 품질 변경','실행 중 변경 검증; 불가 시 재시작 허용 여부','','','미결정'],
 ['Q5','J5','영상 중지 방식','전체 파이프라인 중지 / 송신 출력만 일시 중지','','','미결정'],
 ['Q6','D4, E5','활동 명령·완료 명세','PAYLOAD·REACTION opcode·매개변수·완료 이벤트 정의','','','미결정'],
 ['Q7','E4~E6','명령 확인 기준','물리 동작 확인 데이터와 응답 대기 시간 기준','','','미결정'],
 ['Q8','K5','ROS 데이터 형식','누적 경로·2.5D 지도 생성 노드와 표시 방식','','','미결정'],
 ['Q9','L9','통합 품질 기준','명령 응답 시간·상태 갱신 간격·영상 지연의 허용 범위','','','미결정']
];

function makeSheet(name,title,note,headers,data,widths,tableName){
 const s=wb.worksheets.add(name); const end=String.fromCharCode(64+headers.length); const last=data.length+4;
 s.showGridLines=false;
 s.getRange(`A1:${end}${last}`).format.font.name='Noto Sans CJK KR';
 s.getRange(`A1:${end}${last}`).format.font.size=11;
 s.getRange(`A1:${end}1`).merge(); s.getRange('A1').values=[[title]];
 s.getRange(`A1:${end}1`).format={fill:'#17324D',font:{bold:true,color:'#FFFFFF',size:19},rowHeight:38};
 s.getRange(`A2:${end}2`).merge(); s.getRange('A2').values=[[note]];
 s.getRange(`A2:${end}2`).format={font:{color:'#526477',size:10},wrapText:true,rowHeight:32};
 s.getRange(`A4:${end}4`).values=[headers];
 s.getRange(`A5:${end}${last}`).values=data;
 const table=s.tables.add(`A4:${end}${last}`,true,tableName); table.showFilterButton=true;
 s.getRange(`A4:${end}4`).format={fill:'#176D79',font:{bold:true,color:'#FFFFFF'},rowHeight:30};
 s.getRange(`A5:${end}${last}`).format.wrapText=true;
 s.getRange(`A5:${end}${last}`).format.rowHeight=72;
 widths.forEach((width,i)=>s.getRange(`${String.fromCharCode(65+i)}1:${String.fromCharCode(65+i)}${last}`).format.columnWidth=width);
 s.freezePanes.freezeRows(4);
 return s;
}
const req=makeSheet('요구사항','LOONAR GCS | 요구사항 검토표','대화 내용을 정리한 초안입니다. 요구 구분은 승인·구현 완료를 뜻하지 않습니다. 각 셀을 직접 수정하거나 수정안·메모를 작성하세요.',
 ['ID','분류','항목','요구사항 / 설명','요구 구분','구현 범위 / 의존성','검토 상태','사용자 수정안','메모'],rows,[8,18,23,72,19,26,17,48,35],'Requirements');
req.getRange(`G5:G${rows.length+4}`).dataValidation={rule:{type:'list',values:['검토 전','유지','수정 필요','삭제','확정']}};
req.getRange(`E5:E${rows.length+4}`).dataValidation={rule:{type:'list',values:['사용자 요청','조건부 요청','기존 문서 기준','설계 제안','추가 결정 필요']}};
req.getRange(`G5:I${rows.length+4}`).format.fill='#FFF8DF';
req.getRange(`G5:G${rows.length+4}`).conditionalFormats.add('containsText',{text:'확정',format:{fill:'#DDF1E6',font:{color:'#176045'}}});
const ms=makeSheet('마일스톤','LOONAR GCS | 개발 마일스톤','일정과 담당자는 미정입니다. 진행 상태는 실제 구현을 확인한 뒤 수정하세요. 첫 장비 목표는 상태 수신과 명령 응답 확인입니다.',
 ['ID','단계','작업 내용','완료 기준','관련 요구사항','의존성 / 비고','진행 상태','담당자','메모'],milestones,[8,20,44,60,24,44,17,18,35],'Milestones');
ms.getRange('G5:G13').dataValidation={rule:{type:'list',values:['미착수','진행 중','검증 중','완료','보류']}};
ms.getRange('G5:I13').format.fill='#FFF8DF';
const dec=makeSheet('결정할 사항','LOONAR GCS | 함께 결정할 사항','아래 항목은 미정입니다. 선택 방향을 검토한 뒤 결정 내용과 메모를 직접 입력하세요.',
 ['ID','관련 요구사항','결정 항목','검토할 내용','결정 내용','메모','상태'],decisions,[8,19,26,65,48,35,17],'Decisions');
dec.getRange('G5:G13').dataValidation={rule:{type:'list',values:['미결정','검토 중','결정 완료','보류']}};
dec.getRange('E5:G13').format.fill='#FFF8DF';

console.log('Requirement rows:',rows.length,'Milestones:',milestones.length,'Decisions:',decisions.length);
console.log((await wb.inspect({kind:'table',range:'요구사항!A4:G7',include:'values',tableMaxRows:4,tableMaxCols:7,maxChars:1800})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A',options:{useRegex:true,maxResults:10},maxChars:500})).ndjson);
for(const [name,range,file] of [['요구사항','A1:I8','requirements-preview.png'],['마일스톤','A1:I8','milestones-preview.png'],['결정할 사항','A1:G8','decisions-preview.png']]){
 const preview=await wb.render({sheetName:name,range,scale:1,format:'png'});
 await fs.writeFile(out+file,new Uint8Array(await preview.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(wb)).save(out+'LOONAR_GCS_요구사항.xlsx');
