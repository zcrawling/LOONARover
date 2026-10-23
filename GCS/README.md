# 지상국

## 실제 LOONAR 연결

Pi의 [지원 프로그램](../platforms/loonar/porting/ground_control_runbook.md)을 먼저 실행한다.
PC에서:

```bash
cd ~/LOONAR
bash GCS/scripts/start_loonar_gcs.sh 192.168.0.14
```

웹 UI `http://127.0.0.1:8080`, 진단·영상 창과 감지된 Xbox 입력 창을 연다.
Pi 주소는 실제 주소로 바꾼다. 이미 실행 중인 GCS는 종료하고 다시 실행해야
코드·설정 변경이 반영된다. 설정은 [config/loonar.toml](config/loonar.toml)이다.

Python 3.11 이상, SSH, ffmpeg/ffplay, gnome-terminal, xdg-open이 필요하다.
영상 테두리 표시는 tkinter와 Pillow를 사용한다. Xbox 장치 접근은
[설정 안내](docs/xbox-controller.md)를 따른다.

| 연결 | 기본값 |
| --- | --- |
| PC 웹 UI | TCP 8080, localhost |
| Pi GroundLink | TCP 7443 |
| PC 영상 수신 | UDP 5600, H.264/MPEG-TS |
| PC backend | `GCS/.runtime/backend.sock` |

WASD로 주행한다(W 전진, S 후진, A/D 좌·우 회전). 여러 키를 누르면 마지막으로
누른 방향을 우선하고, 그 키를 놓으면 아직 누르고 있는 이전 방향으로 돌아간다.
모든 주행 키 해제·포커스 상실 시 속도 0을 요청한다. 방향키는 슬라이더 조절에 사용하며, 슬라이더에 포커스가
있어도 WASD로 주행할 수 있다. 숫자·텍스트 입력 중에는 주행 키가 동작하지 않는다.
STOP은 별도 모드 명령이다. Xbox LT는 A/B, RT는 STOP/MANUAL을 전환하며
Xbox 터미널에 포커스가 있을 때만 입력한다. [상세 조작](docs/xbox-controller.md).
종료 전 STOP을 누르고 PC와 Pi의 실행 터미널에서 Ctrl+C한다.

지상국 실행 터미널에서 `flip` 입력 후 Enter를 누르면 뒤집힘 보정을 전환한다.
ON에서는 영상이 180° 회전하고 웹 WASD·Xbox의 전후진·조향을 뒤집힌 차체에 맞춘다.
전송 변환은 `(v, w) → (-v, w)`다. 기존 `(-v, -w)`에서 발생한 실기 좌우 조향 문제를
보정한 값이며, 다시 `flip`을 입력하면 원상 복구된다.
상태는 웹·영상·Xbox 창에 표시되며 백엔드 재시작 시 OFF로 초기화된다.
이 설정은 지상국 수동주행에 적용되며 Pi AUTO 알고리즘이나 저장되는 원본 영상은 바꾸지 않는다.

같은 실행 터미널에서 `obj` + Enter로 PC 객체인식을 ON/OFF 전환한다. 기본은 ON이다.
OFF에서는 박스를 숨기고 진행 중인 추론이 끝나면 대기하며 영상 표시·녹화·조종은 유지한다.
다시 ON으로 전환하면 메모리에 유지한 모델로 최신 프레임부터 재개한다.
영상 창을 다시 열어도 실행 중인 백엔드의 설정을 따르며, 백엔드 재시작 시 ON으로 초기화된다.

선속도 상한은 0.4m/s, 회전 상한은 3.8rad/s다. 혼합 주행은 바퀴 속도가
0.4m/s를 넘지 않도록 정규화한다. 웹 HTTP 속도 입력도 같은 상한으로 제한하며,
범위를 넘는 유한한 숫자는 거부하지 않고 0부터 해당 상한 사이로 맞춘다.

Payload 버튼은 [별도 Pi 서비스](../platforms/loonar/porting/payload_pca_runbook.md)가 필요하다.
영상 탐지는 [Mission02 안내](docs/mission02-object-detection.md)를 참고한다.
기본 영상 창은 지상국 PC CPU에서 객체인식을 실행한다. 기존
`GCS/.venv-vision`과 `GCS/models/mission02/best.pt`를 사용하며,
Pi의 객체인식 및 인식 전용 영상 변환은 기본 비활성화된다.

## Payload 시퀀스 그래프

Payload 패널은 직전 완료 시퀀스의 세 센서 원시값을 시간축으로 표시한다.
큰 숫자는 해당 시퀀스의 중앙값이다. PCA 결과는 후보 / 후보 아님 / 판정 불가로
구분하며, 점수는 확률이 아니다. START/STOP 버튼은 패널 하단에 있다.

GCS는 PCA 완료 결과를 받으면 SSH로 해당 CSV를 읽어 메모리에 캐시한다.
MCU UID·부팅 ID·시퀀스 번호, 완료 기록과 모델을 확인한다. MCU 식별 정보가
없는 경우 요청 ID까지 일치해야 한다.
새 측정을 시작해도 직전 결과는 유지하며, 가져오기 실패는 10초 간격으로 재시도한다.
MCU 펌웨어나 Pi 프로그램을 배포할 필요는 없다.

기본 검색 위치는 Pi의 `/var/lib/loonar/payload`와
`~/loonar-motor-bench/runtime/payload`다. 사용자 지정 위치는 지상국 실행 전에
`LOONAR_PAYLOAD_CSV_DIR` 환경변수로 지정한다. SSH 사용자는 `loonar`이며
`LOONAR_SSH_USER`로 변경할 수 있다. 기존 SSH 키 또는 sshpass와
`LOONAR_SSH_PASSWORD`를 사용한다. 인증 기본값은 기존 지상국 SSH 설정을 따른다.

완료 메타데이터(`.events.jsonl`)가 없는 옛 CSV는 다른 시퀀스와 혼동할 수 있어
자동으로 선택하지 않는다. 파일 크기·표본 수·측정 시간은 패널 상단에 표시한다.
2 MB 초과 CSV는 자동으로 가져오지 않으며, 긴 기록은 표시 점 수를 줄여 전송한다.

## 개별 실행

```bash
cd ~/LOONAR/GCS
python3 -B -m webui.server --real-host 192.168.0.14
bash scripts/start_diagnostics.sh --host 192.168.0.14
bash scripts/start_video.sh --rotate-left --record --compass
```

각 명령은 별도 터미널에서 실행한다. 영상 수신기는 UDP 포트를 중복 사용하지 않도록
기존 창을 종료한다. PC 녹화는 `~/Videos/LOONAR/`에 저장되며 Pi 녹화와 별개다.
상대 방위는 자이로 적분 기준으로, 절대 북쪽을 보장하지 않는다.

## 장치 없는 Mock

각 터미널에서 `cd ~/LOONAR/GCS` 후 하나씩 실행한다.

```bash
python3 -m mock.rover
python3 -m backend.app
python3 -m cli.commands
python3 -m cli.monitor
```

Mock은 [GCP1 계약](docs/interface-draft.md)을 사용한다. 실제 로버의
[LNK1](../docs/ground_link_protocol.md)과 호환되지 않으며 Mock 결과는 실기 검증이 아니다.
cFS까지 포함하는 PC 시험은 [통합 시험 도구](../tools/gcs_test/README.md)를 사용한다.

## 실행 시 IP 선택

PC에서는 Pi 주소를 지정합니다. 주소를 생략하면 입력 창이 열립니다.

```bash
bash GCS/scripts/start_loonar_gcs.sh --rover-ip PI_IP
```

Pi에서는 영상과 제어를 담당하는 PC 주소를 지정합니다. 기존 위치 인자 `start_loonar_gcs.sh PI_IP`도 지원합니다.

```bash
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --gcs-ip PC_IP --video
# 별도 PC에는 상태 UDP만 추가 송신
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --gcs-ip PC_IP --status-ip OBSERVER_IP --video
```

Pi 실행기는 sudo로 `/etc/loonar/network.env`, 영상/ROS 설정, LOONAR 방화벽 테이블과 상태 송신 서비스를 갱신합니다.
주소 변경은 기존 주행 지원 프로세스를 종료한 뒤 실행합니다. SSH 및 다른 방화벽 테이블은 유지합니다.
선택한 PC만 제어 TCP 7443/7444/7445와 ROS 통신을 허용하며, 관찰 PC에는 상태 UDP 6101/6102만 송신합니다.
영상 UDP는 5600, 선택적 Pi 객체인식 결과는 5601입니다. Pi 상태 패킷의 송신 주소는 실제 라우팅 주소에서 구합니다.
`--record`, `--record-all`, `--record-video`는 각각 기존의 명시적 녹화 옵션입니다.

Pi 코드 배포 및 cFS 재빌드 (기존 Pi 저장소와 빌드 환경 필요):

```bash
bash platforms/loonar/tools/deploy-network.sh loonar@PI_IP
```

위 배포 명령은 파일 복사와 빌드만 합니다. 완료 후 Pi에서 위 `start-ground-support.sh` 명령을 실행합니다.
기존 cFS 바이너리에는 이전 IP 허용 조건이 남으므로 재빌드가 필요합니다.

개별 실행 시에도 주소를 지정할 수 있습니다.

```bash
# Pi: 설정/방화벽만 적용
sudo bash platforms/loonar/tools/setup-network.sh --gcs-ip PC_IP --status-ip OBSERVER_IP
# Pi: 기존 video.env의 영상 형식을 사용하되 송신 주소를 지정
bash platforms/loonar/deploy/run-video.sh --gcs-ip PC_IP
# Pi: 선택적 객체인식 결과 송신
bash platforms/loonar/deploy/run-vision.sh --gcs-ip PC_IP
# Pi: 상태 송신 단독 실행 (기존 서비스와 중복 실행하지 않음)
python3 platforms/loonar/tools/pi_status_broadcast.py --gcs-ip PC_IP --gcs-ip OBSERVER_IP
# Pi: ToF 단독 송신
bash platforms/loonar/tools/start-tof-stream.sh PC_IP
# PC: AUTO brain 단독 실행
bash platforms/loonar/ros2/terrain_navigation/fly_brain/run_pc.sh --rover-ip PI_IP
# PC: 상태 수신 단독 실행
bash GCS/scripts/start_hardware_monitor.sh --host PI_IP
```

개별 송신 인자를 바꿀 때에도 Pi 방화벽의 허용 PC를 `setup-network.sh`로 동일하게 지정해야 합니다.

## 주행 영상 노출 조절

지상국 실행 터미널에서 다음 명령을 입력합니다. 선택한 Pi의 SSH 계정으로
실행 중인 카메라 소유 프로세스에 전달하며, 적용 요청의 응답을 표시합니다.

| 명령 | 동작 |
|---|---|
| `exposure` | 현재 제어 설정 조회 |
| `exposure +` / `exposure -` | 0.5 EV씩 밝게 / 어둡게 |
| `exposure 1.5` | +1.5 EV로 지정 (범위 -3~+3) |
| `exposure backlight` | 자동 노출, 중앙 측광, 어두운 영역 우선, +1 EV |
| `exposure auto` | 자동 노출, 중앙 측광, 일반 모드, 0 EV 복귀 |

EV는 자동 노출의 목표 밝기 보정입니다. `exposure +1`은 +1 EV 지정이며,
현재 값에 더하려면 `exposure +`를 사용합니다. 역광에서는 `backlight` 후 영상을 보며 조절합니다.
지형을 밝게 하면 하늘이 하얗게 포화될 수 있습니다.

Pi의 `common/video/{loonar-video-stream,camera_ros.py,camera_stream.py,camera_control.py}`와
PC의 GCS 코드를 갱신한 뒤 기존 영상 송신 및 GCS 실행기를 한 번 재시작해야 합니다.
이후 노출 명령마다 영상 파이프라인을 재시작하지 않습니다. 노출 설정은 카메라 프로세스가 종료되면 초기화됩니다.
명령 응답은 GStreamer 속성 설정 결과이며, 센서의 실제 셔터 시간이나 프레임 밝기 측정값은 아닙니다.
SSH 인증은 기존 `LOONAR_SSH_USER` / `LOONAR_SSH_PASSWORD` 설정을 사용합니다.
