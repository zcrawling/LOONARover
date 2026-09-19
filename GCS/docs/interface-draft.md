# GCS 프로토타입 통신 인터페이스 (Mock 전용)

이 문서는 실제 라즈베리파이 5/cFS와 합의된 규격이 아니다. 초기 GCS를 로컬에서 검증하는 임시 계약이다. 현재 구현은 loopback Mock 연결만 허용한다. 기존 GroundLink `LNK1`과 호환되지 않는다. 임시 구현에 기존 Type ID를 재사용해 실제 로버에 잘못된 명령을 보내지 않도록 magic도 `GCP1`로 구별한다.

## 메시지 경계

각 메시지는 8바이트 헤더와 UTF-8 JSON 본문으로 구성한다. 헤더는 `GCP1` 4바이트와 unsigned 32-bit big-endian 본문 길이다. 본문 최대 길이는 16,384바이트다. TCP는 메시지를 나누거나 합쳐 전달할 수 있으므로 헤더와 본문을 누적해서 읽는다. 잘못된 magic, 길이, JSON, 필수 필드는 연결 오류로 처리하고 재접속한다.

## 메시지 종류

- `command`: `command`, `request_id`. STOP/MANUAL/AUTO/PAYLOAD/REACTION만 지원. MANUAL은 모드 전환만 요청한다.
- `result`: `command`, `request_id`, `result`, 선택적 `error`. 결과는 Received/Completed/Ended/Failed/Aborted/Rejected.
- `status`: `mode`, `values`, `payload` 객체. payload는 `state`, `request_id`를 담는다. 최초 연결 및 주기적으로 전달한다.
- `payload`: `request_id`, `sample`, `time`, `values`. 센서값 및 센서 상태는 로버가 제공하는 의미 그대로 표시한다.
- `ping`, `pong`: 동일한 양의 정수 `sequence`로 대응시킨다.

request_id는 GCS가 생성하는 UUID 문자열이다. 지상국 프로세스 재시작 후 요청 번호가 충돌하는 것을 피한다. 실제 로버 명세의 숫자 sequence 등으로 전환할 때 이 매핑도 함께 변경한다.

PAYLOAD는 Received를 20초 동안 기다린다. 측정 종료 시간 제한이 아니다. 제한 시간이 지나면 Command Result Unknown을 표시하며 자동 재전송하지 않는다. 늦게 도착한 정상 결과는 같은 요청에 반영한다. 측정 패킷이 도착했다고 Received를 받은 것으로 바꾸지는 않는다.

## 통신과 제어 책임

GCS는 명령 송신, 응답 표시, 상태 수신, Heartbeat, 단절·재접속을 담당한다. 센서 진단, 정지 판정, 모드 전환 허용 여부, PAYLOAD 측정 및 리액션휠 제어는 로버 책임이다. Mock의 BUSY, STOP 후 Aborted, REACTION의 즉시 Completed 등은 GCS 검증 시나리오이며 실제 차량 정책이 아니다.

2초마다 PING을 보내고 대응 PONG만 양방향 생존 확인으로 인정한다. 6초 지연은 DEGRADED, 20초 지연은 재접속한다. 일반 상태 수신은 PONG 타이머를 초기화하지 않는다. 새 연결에서 PONG과 현재 상태를 모두 받아야 CONNECTED가 된다. 최초 상태가 20초 안에 없으면 다시 연결한다.

연결 시도는 3초 제한, 실패 후 1/2/4/8/10초 간격이다. 데이터가 계속 송신되는 중에도 PING과 STOP 수신이 가능한지를 테스트한다. 전송 중 오류는 Result Unknown, 연결 확인 불가 상태에서 새 요청은 Not Sent로 표시한다. 애플리케이션 명령은 재전송하지 않는다. OS TCP 재전송과 RTO는 기본 동작을 이용한다.

Keepalive는 GCS 소켓에 적용한다. 로버 소켓의 설정은 로버 담당자와 별도로 협의한다. TCP_USER_TIMEOUT은 기본적으로 0(OS 기본값)이며 중앙 설정으로 변경할 수 있다.

## 현재 없는 기능 / 실제 연동 전 합의할 항목

- 실제 LNK1 바이너리 adapter와 수정된 MANUAL 규격
- 실제 상태/센서 패킷 필드, 단위, 유효 비트, 명령 응답 형식
- 실제 로버의 PING/PONG 지원과 현재 상태 전달 방식
- 영상 START/STOP/비트레이트 명령과 수동 방향 command
- REACTION 등의 장시간 동작 결과 정책 (PAYLOAD 이외에 20초 완료 제한을 임의 적용하지 않음)
- 이전 명령 결과 복원 및 과거 PAYLOAD 데이터 재전송 (후속)

재연결 시 Mock은 현재 상태를 먼저 보낸다. 누락 샘플은 재전송하지 않고 GCS는 연결 단절 구간을 표시한다. Mock 프로세스가 유지되는 동안 측정은 연결 단절과 무관하게 계속되지만, Mock 자체를 종료하면 상태도 사라진다. 로버 로컬 저장 구현을 이 프로젝트가 제공하는 것은 아니다.

GUI, 조이스틱, 자동 협상, 설정 hot reload, 그래프/DB/로그 재생은 이번 범위에서 제외한다.
