# Pi 지원 프로그램 실행

Pi는 `~/LOONAR`에 현재 소스, gateway/cFS 빌드 결과와 장치 registry가 있어야 한다.
최초 설치는 [배포 안내](../deploy/README.md), 펌웨어는
[Control 빌드·업로드](../firmware/control/README.md)를 따른다.

## 빌드와 장치 등록

Pi에서 gateway와 cFS를 빌드한다. MCU를 업로드하거나 주행시키지 않는다.

```bash
cd ~/LOONAR
bash platforms/loonar/deploy/prepare-ground-control.sh
```

`~/loonar-motor-bench/control.json`에는 연결된 MCU UID, bound UID,
USB by-id 경로와 차체 설정이 맞아야 한다.
[registry 예제](../config/mcu-registry.example.json)와
[장치 조회 도구](../tools/mcu_v2/inspect.py)를 참고한다.
`MCU UID/binding does not match role registry`는 실제 보드·펌웨어 binding·registry
불일치다. 식별 검사를 우회하지 말고 대상 보드와 빌드 UID를 확인한다.

## 실행

지상국 PC에서 접속한 SSH 터미널에서:

```bash
ssh loonar@192.168.0.14
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video
```

`--video`는 첫 번째 인자로 주며 SSH 접속 PC로 송신한다.
영상 목적지를 직접 지정할 수도 있다.

```bash
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video-ip 192.168.0.20
```

| 인자 | 효과 / 저장 위치 |
| --- | --- |
| 없음 | gateway, cFS, Control backend, ROS 표본 발행 |
| `--encoder-verify` | 명령/엔코더 비교, `~/loonar-motor-bench/runtime/encoder-*.csv` |
| `--record` | ROS bag, `~/loonar-bags/` |
| `--record-video` | Pi 로컬 카메라 H.264/MPEG-TS, `~/loonar-videos/` |
| `--video-record-dir /경로` | Pi 영상 저장 디렉터리 변경 |

```bash
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video --encoder-verify --record --record-video
```

ROS 기록에는 Jazzy와 MCAP 의존성이 필요하다. 영상 녹화만 필요하면
`--record-video`만 추가한다. Pi 영상 기본 프로필은 low(640×360, 30fps, 1Mbps)다.
영상은 UDP 송신·파일 저장에 같은 인코더를 사용한다. 부하로 인한 프레임 누락을
완전히 막는 무손실 녹화는 아니다.

시작만으로 주행 명령은 전송하지 않는다. `health online: true`와 최신 motor/imu
표본을 확인한 뒤 [PC 지상국](../../../GCS/README.md)을 실행한다.
`--encoder-verify`는 피드백 기록 옵션이며 IMU 제외 진단 펌웨어를 강제하지 않는다.

## 확인과 종료

- 로그: `~/loonar-motor-bench/runtime/{backend,gateway,cfs,sensors,video,record}.log`
- Pi: GroundLink TCP 7443. PC: 영상 UDP 5600, 웹 localhost TCP 8080.
- `imu`: gyro/accel/quaternion 수신 값. health의 `imu_progress`와 `gyro_age_ms`도 확인한다.
- ROS 표본: `/imu/*`, `/wheel/odom`, `/battery_state`. 기록 여부는 bag 메시지 수로 확인한다.
- 영상·기록 실패는 해당 로그를 확인한다. core 프로세스 종료는 전체 bench 종료로 이어진다.

GCS STOP 후 Pi 터미널에서 Ctrl+C한다. backend는 STOP을 요청하고 기록 프로세스를
정리한다. 파일 마무리를 위해 종료를 기다린다. 실행 중인 backend와 시리얼 모니터가
같은 USB 장치를 동시에 열면 안 된다.

## Payload와 systemd

`--payload-device /dev/serial/by-id/...`를 주면 Payload 서비스를 함께 시작한다.
이 인자가 없으면 별도 Payload 서비스가 필요하다. 전체 localization은 별도 실행한다.
Payload는 [별도 안내](payload_pca_runbook.md)에 따라 `loonar-payload-pca.service`를
준비한다. checkout bench를 사용할 때 systemd gateway/cFS/Control을 중복 실행하지 않는다.
`loonar-mcu@control.service`가 없으면 systemd runtime이 설치되지 않은 것이다.
checkout 실행에는 그 unit이 필요하지 않다.
