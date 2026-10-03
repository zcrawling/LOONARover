# 임시 직진 엔코더 검증

`teensy41_encoder_verify`는 기존 USB 제어기 펌웨어에서 BNO055 작업만 시작하지 않는 별도 빌드다.
모터 명령, M1=오른쪽/M2=왼쪽 매핑, RoboClaw 속도제어, 명령 만료 정지 및 UID 검증은 유지한다.
IMU 기반 직진 보정은 추가하지 않는다. 자동 주행 명령을 보내지 않는다.
USB는 기존 이진 프로토콜이므로 `cat /dev/ttyACM0`으로 보지 않고 Pi bench 출력을 본다.

모터드라이버 UART는 **Serial2, RX7 / TX8**이다. Teensy TX8은 드라이버 RX,
Teensy RX7은 드라이버 TX에 연결하고 GND를 공통으로 연결한다.
기존 BNO RESET8 배선은 분리한다. 일반 Control 빌드는 BNO055를 별도 Serial6 TX24/RX25로 읽는다.

## 빌드·복사 (노트북)

현재 FreeRTOS 환경의 ARM Linux 빌드는 board_config.py에서 차단되어 있다.
아래는 노트북에서 빌드하고 Pi에서 업로드하는 경로다.
UID/tag는 현재 등록된 제어기 기준이다. 보드를 바꿀 때는 레지스트리와 함께 재확인한다.

```bash
cd /home/sb/LOONAR
LOONAR_BOARD_UID=000004e9e51e7948 ~/.local/bin/pio run -d platforms/loonar/firmware/control -e teensy41_encoder_verify
scp platforms/loonar/firmware/control/.pio/build/teensy41_encoder_verify/firmware.hex loonar@192.168.0.14:~/encoder-verify.hex
scp platforms/loonar/tools/mcu_v2/{motor_bench,encoder_verify}.py loonar@192.168.0.14:~/LOONAR/platforms/loonar/tools/mcu_v2/
```

## 업로드·실행 (Pi SSH)

실행 중인 start-ground-support.sh를 그 터미널에서 Ctrl+C로 종료하고, GCS를 STOP으로 놓는다.
초기 확인은 바퀴를 안전하게 들어 올린 상태에서 낮은 속도로 한다.

```bash
ssh loonar@192.168.0.14
~/.local/bin/tycmd upload --board 19971280-Teensy ~/encoder-verify.hex
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --encoder-verify
```

비밀번호는 기존 loonar 계정 비밀번호. 영상도 필요하면 `--video --encoder-verify` 순서로 실행한다.
GCS에서 직접 정지 → 낮은 속도 직진 유지 → 정지 → 후진 유지 순서로 시험한다.

## 판독

- `cmd L/R`: RoboClaw가 ACK한 좌우 속도 명령. GCS 입력 그 자체와 구별한다.
- `actual`: 엔코더 속도(qpps, 초당 카운트). `count`: 누적 카운트이며 시작점이 달라 절대값이 같을 필요는 없다.
- `track_error`: 실측 - 명령. 좌우가 같아도 둘 다 명령에 못 미치거나 반대로 회전하면 확인 가능하다.
- `STRAIGHT`: 같은 0이 아닌 좌우 명령이 1초 이상 유지되고 ACK/카운트/속도가 신선하며 드라이버 오류가 없는 구간.
- `diff`: `100*abs(left_speed-right_speed)/abs(command)`.
- `mean/max`: 해당 실행의 유효 직진 구간 속도 응답들에 대한 diff 평균/최대. 주행 속도별 분석은 CSV에서 분리한다.
- `STOP/TURN`, `SETTLING`, `STALE/FAULT`는 집계에서 제외한다. 유효 표본이 0이면 통계값은 의미 없다.
- CSV: `~/loonar-motor-bench/runtime/encoder-*.csv`. 모든 수신 모터 표본을 기록하며 상태 열로 분석 대상을 고른다.

속도 피드백은 주기적으로 조회한 값이므로 연속 시간 전체의 최악값을 보장하지 않는다.
엔코더 속도가 같다는 것만으로 지면에서 직진한다고 확정할 수 없다. 바퀴 지름, 미끄러짐,
좌우 엔코더 스케일을 별도로 확인한다. Pi 저전압/재부팅이 발생한 시험은 다시 진행한다.

## 기존 빌드 복구

노트북에서 같은 UID로 `-e teensy41_usb`를 빌드한 뒤
`.pio/build/teensy41_usb/firmware.hex`를 Pi에 복사하여 같은 tycmd 명령으로 업로드한다.
기본 PlatformIO 환경은 그대로 teensy41_usb다.

## Pi 카메라 로컬 녹화

```bash
# 로컬 녹화 + 엔코더 기록 (영상 전송 없음)
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --record-video --encoder-verify
# 지상국 영상 전송 + Pi 로컬 녹화 + 엔코더 기록
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video --record-video --encoder-verify
```

`--record-video`는 기본 `~/loonar-videos/camera-*.ts`에 H.264 MPEG-TS를 저장한다.
`--video-record-dir /경로`로 저장 폴더를 변경할 수 있다. 현재 bench 영상 설정은
640×360, 30fps, 1Mbps다. `--record`는 별도 ROS 데이터 기록이며 카메라 파일 옵션과 다르다.
전송과 녹화는 카메라·인코더 하나를 공유한다. 디스크 정체 시 제한된 녹화 큐는 프레임을
버릴 수 있어 무손실 기록을 보장하지 않는다. Ctrl+C로 종료하며 카메라 인식 실패는
`~/loonar-motor-bench/runtime/video.log`에 표시된다.
