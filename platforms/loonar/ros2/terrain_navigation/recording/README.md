# LOONAR 전체 데이터 녹화

Pi에서 센서를 시작하고 수동 주행하며 한 세션 폴더에 저장한다. 기본 모드는 자율주행 명령을 만들지 않는다. 초파리 신경망 PC 실행은 수동 녹화에 필요 없다.

## 실행

기존 Pi 주행과 PC 지상국을 Ctrl+C로 종료한 뒤 Pi에서:

```bash
bash ~/LOONAR/platforms/loonar/ros2/terrain_navigation/recording/run_pi.sh
```

PC에서:

```bash
bash /home/sb/LOONAR/platforms/loonar/ros2/terrain_navigation/recording/run_pc.sh
```

브라우저에서 http://127.0.0.1:8080 을 연다. 수동 조작은 기존 지상국 UI를 사용한다. 이 실행기는 녹화 프록시 `10.254.254.3:7444`를 통해 기존 cFS `7443`으로 원문 바이트를 전달한다. 기존 7443 직접 연결은 프록시 이전 수동 입력 기록을 우회하므로 사용하지 않는다. 수동 속도 설정은 전진 0.2m/s, 회전 0.3rad/s이다. 기존 GCS 소스는 변경하지 않는다.

Pi의 `RECORD missing=none stale=none`을 확인하고 움직인다. 다른 상태라면 해당 스트림이 누락되거나 중단된 것이다. 이 표시는 실시간 기록 상태이며 마지막 저장 검증과 구분한다.

Pi에서 **Ctrl+C**를 누르면 MCU 정지 및 센서 종료 → 남은 데이터 저장 → MCAP 전체 읽기 검증 순으로 끝난다. `COPY THIS WHOLE DIRECTORY:`가 나올 때까지 기다린다. PC도 Ctrl+C로 종료한다.

```bash
scp -r loonar@10.254.254.3:/home/loonar/loonar-bags/capture_날짜_시간 ./
```

MCAP 하나만 고르지 말고 출력된 **세션 폴더 전체**를 복사한다. 1GiB마다 분할된 파일, 원본 백업, 설정, 로그와 검증 보고서가 모두 필요하다. 실제 폴더명은 Pi가 출력한 것을 쓴다.

자율주행이 안 되는 현상을 추가로 기록할 때만 PC에서 기존 `fly_brain/run_pc.sh --drive`, Pi에서 `recording/run_pi.sh --mode fly`를 사용한다. 이 모드는 기존 자율주행을 켜므로 기본 수동 녹화와 다르다. 전진 한도 0.2m/s는 유지된다.

모터를 구동하지 않고 센서·기록 부하만 확인하려면 `--mode observe --seconds 30`을
사용한다. 이 모드는 cFS/GCS 프록시와 drive node를 시작하지 않는다.
CPU 배치를 설치한 Pi에서는 모든 녹화·ROS 프로세스가 CPU 1–3, MCU backend와
vehicle gateway가 OS와 함께 CPU 0에 자동 배치된다. [CPU 구성](../runtime/README.md)을 참고한다.

## 저장 범위

- ToF: SDK가 전달한 모든 깊이/진폭 원본 `16UC1`, 원본 intrinsics/distortion, SDK callback 시각과 프레임 순번. `/loonar/tof/raw_depth`, `raw_amplitude`, `raw_camera_info`, `/recording/tof/frame`. 전처리된 깊이/진폭/CameraInfo도 별도 저장한다.
- 카메라: JPEG 이미지 전체와 GStreamer PTS, Pi 환산 시각, 수신 시각, 누적 프레임 수. ROS/JPEG 요청 속도는 평소 주행과 같은 5fps이며, 실제 저장 수와 간격은 보고서로 확인한다. 광학 노출 시각 동기화나 보유하지 않은 카메라 보정을 만들어내지 않는다.
- IMU: 기존 ROS gyro/accel/gravity/quaternion 및 MCU가 내보낸 모든 IMU 종류의 원본과 해석값(`/recording/imu/sample`). MCU 시각, Pi offset, sync RTT도 보존한다.
- 모터: 양쪽 encoder/count/speed/목표 qpps/current/PWM/전압/온도/valid mask/fault/query age/ack 등의 원본 64바이트와 해석값(`/recording/motor/feedback`). `/wheel_states`, odometry, base state도 기록한다.
- 명령: 지상국이 보낸 GroundLink 원문/프레임/수동 속도와 회신, gateway→backend 명령, 실제 serial write가 완료된 MCU 명령과 STOP. '명령 전송'과 '하드웨어 적용 성공'은 구별한다.
- TF, robot description, diagnostics, parameter events, 초파리 입력·출력·후보·회피 판단 등 발견되는 나머지 ROS 토픽도 저장한다.

수동 정보는 **Pi가 수신한 조작 명령**이다. PC에서 키를 눌렀지만 네트워크로 보내지지 않은 OS 입력 이벤트까지 의미하지 않는다.

## 세션 구성과 검증

- `bag/`: 단일 rosbag2 MCAP 세션. 1GiB 분할, Zstd fast 압축, `/tf_static` transient-local metadata 보존.
- `raw/*.journal`: ROS/DDS를 경유하기 전 원본 획득 기록. ToF와 JPEG는 이 파일에서 MCAP으로 가져오므로 ROS 구독 시작 지연에 의존하지 않는다. 기록 도중 bag writer가 중단되어도 이 원본이 분석·복구 근거다.
- MCU/gateway 원본은 4096개 제한의 메모리 큐 → 전송 스레드 → 별도 저장 프로세스
  순서로 기록한다. 제어 루프는 SD 쓰기나 큐 공간을 기다리지 않는다. 과부하 시
  누락을 `raw/*.transport.json`에 기록하며, 최종 송수신 수가 다르거나 생산자의
  종료 상태가 없으면 저장 검증을 실패 처리한다. 저장 프로세스는 MCU STOP 후,
  최종 MCAP flush 전에 종료한다.
- `live_status.json`: 기록 수, 필수 스트림 누락·지연, DDS 보고 손실, 디스크 공간, 원본 journal 처리 지연.
- `verification.json`: 전체 메시지 읽기·역직렬화, JPEG 디코딩, 이미지 크기, ToF 짝, 원본 journal/MCAP 레코드 수 비교, MCU sample sequence 간격, 수동 명령 수. 누락을 정상으로 위장하지 않는다.
- `configuration/`, `source/`, `source_sha256.json`: 차체/TF/실행 설정과 해당 기록을 생성한 코드 스냅샷.
- `logs/`, `session.json`: SDK·카메라·backend·gateway·cFS·ROS 로그, 종료 결과.

`ready_for_analysis=true`는 필수 스트림이 있고 저장 무결성 검사를 통과했다는 뜻이다. `recording_complete=false`와 `stream_ended_before_capture_end_s`는 센서 중단 등을 별도로 표시한다. 분석 가능과 전체 구간 정상 획득을 혼동하지 않는다. `manual_command_count=0`이면 수동 명령이 담긴 주행 예제는 아니다. ROS만으로 전달되는 스트림은 DDS 보고 손실과 시간 간격을 검사하지만, 송신 전 유실까지 '절대 0'이라고 보장하지 않는다. 원본 프레임과 처리 후 프레임 수는 의도적으로 분리해 전처리 탈락도 드러낸다.

## 다시 검사 / 재생

Pi의 ROS 환경 또는 같은 메시지 패키지가 설치된 PC에서:

```bash
source ~/LOONAR/platforms/loonar/ros2/terrain_navigation/env.sh
export PYTHONPATH="$HOME/LOONAR/platforms/loonar/ros2/terrain_navigation/recording:$HOME/LOONAR/platforms/loonar/tools:$PYTHONPATH"
python3 -m loonar_recording.verify ~/loonar-bags/capture_날짜_시간
ROS_DOMAIN_ID=219 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ros2 bag play ~/loonar-bags/capture_날짜_시간/bag --clock
```

재생은 실제 로버와 다른 ROS domain에서 한다. 기록 도구가 구동 명령을 재전송하는 기능은 없다.

## 지상국 통합 모드

Pi에서 `bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh`를 인자 없이
실행하면 `--mode gcs` 기록 세션이 시작된다. 센서와 기록은 계속 유지되고,
지상국 AUTO에서만 Pi 주행 노드와 PC 신경망이 시작된다. STOP은 주행/신경망을
종료하며 기록은 유지한다. 이 모드는 원래 지상국 TCP 7443을 사용하므로
recording/run_pc.sh(7444 프록시용)를 함께 실행하지 않는다.
