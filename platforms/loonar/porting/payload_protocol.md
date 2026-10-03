# Payload USB 프로토콜 v1

구현: [MCU](../firmware/payload/src/main.cpp), [Pi](../tools/payload_pca_service.py).
USB CDC 115200, ASCII, LF 종료(CRLF 수신 허용). Control LNR2와 별개다.
MCU 명령은 최대 79자, Pi 수신 행은 최대 512바이트다. 초과 명령은 행 전체를 버린다.

## 명령과 응답

| Pi → MCU | MCU → Pi |
| --- | --- |
| `HELLO` | `HELLO,1,PAYLOAD,board_id,payload-1,boot_id` |
| `STATUS,request` | `HEALTH,1,request,board_id,boot_id,state,station_id,uptime_ms,sensor_mask,sample_age_ms,sample_sequence,payload-1` |
| `CMD,request,START` | `ACK,request,START` → 초기화 후 `DONE,request,START,station_id` |
| `CMD,request,STOP` | `ACK,request,STOP` → PCA 행 → `DONE,request,STOP,station_id` |
| `CMD,request,RESULT` | 마지막 PCA 행 → `DONE,request,RESULT,station_id`; 없으면 `ERROR,request,no_result` |

오류: `ERROR,request,reason`. request는 최대 20자리 unsigned 64bit 십진 문자열이다.
Pi는 MCU 명령마다 새 번호를 생성한다. MCU는 최근 8개 START/STOP 요청의
ACK 또는 최종 응답을 기억하며 중복 수신으로 작업을 다시 실행하지 않는다.
같은 번호에 다른 명령은 `request_conflict`다. RESULT는 조회라 반복 가능하다.

기존 직접 터미널용 `START`/`STOP` 및 `CTRL,START/STOP/ERROR`도 유지한다.
새 Pi 서비스는 STATUS v1 응답이 확인된 장치에만 측정 명령을 보낸다.
구형 자동 출력 펌웨어는 센서 데이터가 와도 ONLINE으로 처리하지 않는다.

## 상태와 시각

상태는 IDLE, INITIALIZING, STARTING, MEASURING, STOPPING이다.
ACK는 수락, DONE은 완료다. START는 5회/150ms 재시도 초기화를 거쳐 측정한다.
부팅 안정화 5000ms와 버스 안정화 500ms(기존 250+250ms)는 유지하되 루프에서
시간을 확인한다. 센서 begin은 한 번씩 호출하며 그 사이 USB 명령을 처리한다.
개별 센서 라이브러리 호출 자체의 실행 시간은 실기 확인 대상이다.

STOP은 측정 시작 후 최소 5초에 PCA와 함께 완료한다. STARTING에서 STOP하면
초기화를 취소하고 START에 `ERROR,...,cancelled`, STOP에 station_id=0을 반환한다.
IDLE STOP도 station_id=0이며 PCA를 만들지 않는다. 측정 중 센서 재초기화도 STOP 가능하다.

sensor_mask: bit0 LIS3MDL, bit1 MLX90614, bit2 MAX31865. 첫 표본 전에는 초기화
성공 여부, 이후에는 최근 표본 유효성이다. 센서 오류는 MCU OFFLINE과 구분한다.
시각은 MCU millis 기반이며 약 49.7일에 wrap한다. sample_age_ms=4294967295는 미수신이다.
표본 번호는 부팅 후 증가한다. boot_id는 EEPROM 마지막 8바이트에 magic과 counter를
저장하여 부팅마다 증가한다. board_id는 MCU silicon ID다.

## 데이터와 결과

기존 원시 CSV 필드는 유지한다:

```text
time_ms,mag_x_uT,mag_y_uT,mag_z_uT,mag_norm_uT,ir_ambient_C,ir_object_C,rtd_raw,rtd_ohm,rtd_C,mag_valid,ir_valid,rtd_valid,rtd_fault
```

각 표본 뒤 `SAMPLE_META,sample_sequence,time_ms`를 보낸다.
PCA 행은 다음 16필드다:

```text
PCA,model_id,station_id,start_ms,end_ms,sample_count,valid_count,usable,mag_norm_uT,ir_object_C,rtd_C,q_residual,t2_distance,novelty,candidate,status
```

센서 CSV와 전체 PCA 행은 Pi CSV에 원문 저장한다. 지상국 요약은 EVENT 크기 제한에
맞춰 숫자를 유효숫자 3자리로 표시한다. 원본 정밀도는 Pi 기록에서 확인한다.
무효 지점은 usable=0, 수치 nan이 가능하다. 모델 상태는 firmware의 model_params.h를 따른다.
마지막 완료 PCA 하나를 MCU RAM에 보관한다. RESULT로 재조회 가능하지만 MCU 재부팅 시 소실된다.

## Health와 재접속

Pi는 USB를 계속 열고 STATUS를 1초마다 요청한다. 최근 요청 번호에 맞는 응답이
3초 이내에 도착해야 ONLINE이다. IDLE/측정/초기화 상태 모두 동일하다.
USB 분리나 응답 만료 시 OFFLINE, 1초 간격으로 재연결한다. 진행 중 명령은
result_unknown으로 보고하며 자동 재전송하지 않는다. MCU의 측정은 통신 단절만으로 중단하지 않는다.
재연결 시 STATUS로 상태를 복원하고 RESULT로 마지막 완료 결과를 조회한다.
명령 응답 제한은 20초, RESULT 조회는 3초다. 센서 데이터 age는 health와 별도로 표시한다.
파일 쓰기 실패는 RECORD 오류이며 MCU 연결을 끊거나 자동 STOP하지 않는다.

## Pi ↔ cFS ↔ GCS

명령 소켓은 Unix SOCK_SEQPACKET, 기본 `/run/loonar/payload-pca.sock`.
패킷 `<QHH` little endian: request_id, opcode(1 START/2 STOP), parameter_length(0).
GCS는 별도 64bit 요청 번호를 만들며 TCP 프레임 sequence와 구분한다.
Pi는 최근 64개 GCS 요청을 기억하여 중복 실행을 방지한다.

응답 STATE/ERROR/PCA는 기존 `payload-pca` EVENT로 전달한다.
고정 필드 health 레코드는 **별도 source `payload-health`**의 EVENT로 전달한다:

```text
HEALTH,1,online,boot_id,state,station_id,sensor_mask,health_age_ms,sample_age_ms,sample_sequence,board_id
```

각 레코드는 127바이트 이내이며 초과 레코드는 절단하지 않고 오류로 보고한다.
cFS는 서비스 미연결 시 state=UNAVAILABLE/online=0을 1초마다 보고한다.
GCS는 health가 3초 이상 끊겨도 OFFLINE으로 바꾸며, 기존 Payload MCU2 텔레메트리가
새 연결 상태를 덮어쓰지 않는다. 새로운 GroundLink type이나 MCU2 가짜 health는 만들지 않는다.

## 검증

```bash
python3 -B -m unittest discover -s platforms/loonar/tools/tests -p test_payload_pca_service.py -v
python3 tools/gcs_test/run.py --build-only --skip-tests --jobs 2
python3 platforms/loonar/tools/tests/payload_pipeline_smoke.py
```

마지막 시험은 실제 cFS와 Pi 서비스를 가상 USB MCU에 연결한다. TCP 7443이 비어 있어야 한다.
실제 센서/I2C 고장 시 지연, USB 재연결, EEPROM 부팅 번호는 별도의 보드 시험이 필요하다.
