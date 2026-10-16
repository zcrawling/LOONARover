# Payload PCA 수동 정차 지점 시험

Payload Teensy와 센서는 임무 내내 켜 둔다. 지상국 `PAYLOAD START`는 Pi에서
항상 연결된 USB CDC로 MCU에 `START` 명령을 보내 센서 재초기화와 새 지점
계측을 시작한다. `PAYLOAD STOP`은 MCU에 `STOP` 명령을 보내며, MCU는
시작 후 최소 5초가 지난 다음 그 지점의 PCA 한 행을 출력한다. Pi는 PCA와
완료 응답을 받은 뒤 로그 파일만 닫고 USB 상태 조회는 유지한다. 센서 전원은 끄지 않는다.

첫 번째 완료 구간은 `STATION01`이고, 다음 START/STOP 구간은 `STATION02`다.
MCU를 재부팅하면 지점 번호는 다시 1부터 시작한다. 각 구간의 원시 센서
행과 PCA 행은 Pi의 별도 `payload-pca-*.csv`에 저장된다. 지상국에는
지점별 자기장 중앙값, IR/RTD 온도, novelty, candidate 및 모델 상태가 표시된다.
현재 `model_params.h`는 **DEMO_ONLY**이며 과학적 이상 판정용 모델이 아니다.

## 회차별 파일과 ROS2 bag 이벤트

Checkout 실행의 저장 위치는 `~/loonar-motor-bench/runtime/payload/`다.
CSV 이름은 `payload-<MCU UID>-boot000001-seq000002-<Pi Unix ns>.csv` 형식이다.
`seq`는 MCU가 발급한 Station ID이며, 부팅 번호와 파일 생성 시각으로 재부팅·재접속 시 덮어쓰기를 방지한다.
같은 이름의 `.events.jsonl`에는 해당 회차의 시작·종료·오류 기록을 저장한다.

Pi 지원 스크립트의 ROS 샘플 브리지는 `/payload/sequence_events`에
`std_msgs/msg/String` JSON 이벤트를 발행한다. 전체 토픽 bag에도 저장되며,
기본 complete recorder는 이 토픽을 시작부터 구독하고 이벤트의 `stamp_ns`를 bag timestamp로 사용한다.
Reliable / transient-local QoS로 구독자가 늦게 연결되어도 최근 이벤트를 전달한다(최대 1000개).
브리지 입력 원본은 `runtime/payload/events-<실행 Unix ns>.jsonl`에도 남는다.

- `START`: MCU의 START 완료 응답을 수신한 실제 측정 시작 확인.
- `END`: MCU의 STOP 완료와 PCA 결과 확인. `INVALID_STATION` 결과도 종료로 기록한다.
- `ACTIVE_OBSERVED`: 이미 실행 중인 MCU에 재접속. 실제 시작 시각을 알았다고 표시하지 않는다.
- `RESULT_RECOVERED`: 이전 회차 결과 복구. 새로운 START/END로 표시하지 않는다.
- `ERROR` / `INTERRUPTED`: 명령 오류·통신 단절·MCU 재부팅·서비스 종료. 정상 END와 구분한다.

모든 이벤트에 `payload_seq_id`, `sequence_key`(UID/부팅/회차), `mcu_uid`,
`mcu_boot_id`, `stamp_ns`(Pi Unix ns), `monotonic_ns`, `pi_boot_id`, `request_id`,
`csv_path`가 들어간다. `END`에는 MCU 기준 `mcu_start_ms`, `mcu_end_ms`, 표본 수,
유효 표본 수와 결과 상태도 포함한다. Pi 이벤트 시각은 응답 처리 시각이므로 MCU의
정확한 측정 구간은 함께 기록된 MCU 시작·종료 시각으로 확인한다.

실시간 확인: `ros2 topic echo /payload/sequence_events`.
MCAP 왕복 검증은 `recording/tests/payload_roundtrip.py`를 사용하며 USB를 열거나 하드웨어를 구동하지 않는다.

## 명령 계약

[Payload USB v1 명세](payload_protocol.md)에 명령·health·CSV/PCA 필드와 재접속 동작을 정의한다.
Pi 서비스·MCU 펌웨어·cFS·GCS를 함께 갱신해야 한다. 구형 자동 PCA 출력 펌웨어는
STATUS 응답이 없어 OFFLINE으로 표시되며 새 서비스의 START를 받을 수 없다.

## 준비와 확인

1. `platforms/loonar/firmware/payload`를 PlatformIO로 빌드하여 Payload Teensy에 업로드한다.
2. Pi에서 `/dev/serial/by-id/`의 Payload Teensy 경로를 확인한다.
3. `/etc/loonar/payload-pca.env`에 `PAYLOAD_DEVICE`와 `PAYLOAD_LOG_DIR`를 설정한다.
4. Pi에 현재 `main`을 설치하고 다음 서비스를 시작한다.

```bash
sudo systemctl start loonar-payload-pca.service
sudo systemctl start vehicle_gatewayd.service loonar-cfs.service
journalctl -u loonar-payload-pca.service -f
```

지상국에서 START를 눌러 `RUNNING,station_01` 이벤트와 원시 센서 행을
확인한다. 센서 재초기화가 끝나고 5초가 지난 뒤 STOP을 눌러 PCA 값과
`IDLE,station_01_complete` 이벤트를 확인한다. 다음 지점에서 반복하면
`station_02`가 된다. 로그 경로는 `/var/lib/loonar/payload/payload-pca-*.csv`다.

## Checkout에서 함께 실행

systemd Payload 서비스 대신 bench에서 실행할 수 있다. 같은 USB를 두 프로세스가 열지 않는다.
기본 Payload 보드는 `21147480`이며 장치 인자 없이도 서비스를 시작한다.
미연결 시 OFFLINE으로 대기하고 1초마다 재접속을 시도하므로 주행·영상 실행을 막지 않는다.

```bash
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video
```

다른 보드는 `--payload-device /dev/serial/by-id/...` 또는 `PAYLOAD_DEVICE` 환경변수로 지정한다.
기존 `--record` 등과 함께 사용 가능하다(`--video`는 맨 앞).
이 방식은 runtime/payload-pca.sock과 runtime/payload/ CSV를 사용한다.
서비스 실패는 보고하되 Control 프로세스는 유지한다. 종료 시 MCU 측정 자동 STOP은 없으므로
완료 결과가 필요하면 GCS에서 Payload STOP을 누르고 완료 응답 후 종료한다.

## 변경 적용

PC에서 firmware를 빌드하고 Pi에 복사한다. 아래 tag는 확인했던 Payload 보드다.

```bash
cd ~/LOONAR
~/.local/bin/pio run -d platforms/loonar/firmware/payload -e teensy41
scp platforms/loonar/firmware/payload/.pio/build/teensy41/firmware.hex loonar@10.254.254.3:~/payload-v1.hex
```

Pi에서 기존 지원 프로그램과 시리얼 모니터를 종료한 뒤 업로드한다.

```bash
~/.local/bin/tycmd upload --board 21147480-Teensy ~/payload-v1.hex
```

Pi checkout에도 현재 `cfs/`, `platforms/loonar/tools/` 소스를 반영하고
`bash ~/LOONAR/platforms/loonar/deploy/prepare-ground-control.sh`로 cFS를 재빌드한 뒤
위 `--payload-device` 명령으로 실행한다. 이 절차는 전체 `/opt` runtime 설치를 요구하지 않는다.
