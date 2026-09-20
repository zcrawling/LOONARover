# LOONAR ToF 수신 및 시험주행 기록

Pi: `loonar@192.168.0.99`, Ubuntu 24.04 / ROS 2 Jazzy.
CubeEye I200D의 XYZ를 `/tof/depth/points` (`sensor_msgs/msg/PointCloud2`)로 기록한다.
2D `/scan`이나 카메라 동영상은 이 bag에 들어가지 않는다.

## 시험주행 시 실행 — Pi 터미널

```bash
# ToF도 함께 시작한다. 재빌드 불필요. SSH 연결이 끊겨도 기록은 계속된다.
sudo systemctl start loonar-tof-record.service

# active 상태와 실제 구독 로그/저장 경로 확인
systemctl status loonar-tof-record.service --no-pager
journalctl -u loonar-tof-record.service -n 15 --no-pager

# 별도 터미널에서 기존 지상국 support를 실행하고, PC 지상국으로 조종한다.
# 주행 종료 후 bag을 정상 마무리한다.
sudo systemctl stop loonar-tof-record.service

source /opt/ros/jazzy/setup.bash
ls -dt ~/loonar-bags/tof_*
# 위 목록에서 이번 기록 폴더를 지정
ros2 bag info ~/loonar-bags/tof_YYYYMMDD_HHMMSS
```

기록 종료 후에도 ToF 수신은 계속된다. 모두 종료하려면
`sudo systemctl stop loonar-tof.service`를 실행한다.
두 서비스 모두 부팅 자동 시작은 설정하지 않았다.
동일한 기록 서비스를 다시 start하면 중복 실행되지 않는다.
새 bag은 stop 후 다시 start할 때 만들어진다.

터미널에서 직접 기록하고 Ctrl+C로 끝내려면 다음을 사용한다.
서비스 방식과 동시에 실행하지 않는다. 이 방식은 SSH 종료 시 지속을 보장하지 않는다.

```bash
sudo systemctl start loonar-tof.service
bash ~/LOONAR/platforms/loonar/tools/record-tof.sh
```

## 실제 프레임 확인

```bash
source /opt/ros/jazzy/setup.bash
set -a
source /etc/loonar/ros.env
set +a
python3 ~/LOONAR/platforms/loonar/tools/check-tof.py
```

10초간 관찰하여 프레임 수, 수신 Hz, 점 개수, SDK callback 이후 지연을 출력한다.
`ok: true`는 새 타임스탬프, 유한한 XYZ, 비어 있지 않은 데이터 수신을 확인한다.
거리 정확도나 실제 주행 중 성능까지 검증하는 것은 아니다.

## 데이터 설정과 제한

- `/etc/loonar/tof.env`: 현재 목표 5 Hz, `TOF_STRIDE=1`.
  640×480에서 공간 샘플링을 줄이지 않고 유효 XYZ를 저장한다.
  SDK의 모든 시간 프레임을 기록하는 설정은 아니다. 최신 프레임을 목표 주기에 맞춰 발행한다.
- 기존 유효점 필터: 유한한 XYZ, 전방 Z > 0.1 m, 3D 거리 < 5 m.
  XYZ만 포함하며 intensity, raw depth/amplitude 이미지는 포함하지 않는다.
- 좌표 단위 m, `cubeeye_optical`: X 오른쪽 / Y 아래 / Z 전방.
  장착 위치 미실측으로 `TOF_PUBLISH_BASE_TF=false`; 임의의 base_link TF를 넣지 않는다.
  실측 후 여섯 위치/회전 값을 입력하고 true로 변경하여 서비스를 재시작한다.
- 타임스탬프는 Pi의 SDK callback 시각이며 센서 노출 시각은 아니다.
  장치 원시 timestamp는 `/tof/status`에 함께 기록한다.
- Pi 브리지와 recorder 모두 reliable QoS를 사용한다. 최초 best-effort 저장에서
  고해상도 메시지 누락이 발견되어 기록 경로를 변경했다.
- MCAP으로 Pi 로컬 `~/loonar-bags/tof_날짜_시간/`에 저장하고 약 1 GiB마다 분할한다.
  전체 사용량 제한은 아니므로 장시간 기록 시 남은 용량을 확인한다.
- `/tof/status`, `/tf`, `/tf_static`도 기록 대상으로 지정한다.
  실제 publisher가 없는 TF는 bag에 생성되지 않는다.
  현재 ToF만으로 로봇 궤적/지도나 주행 odometry가 기록되는 것은 아니다.
- IMU/odom ROS publisher를 별도로 구성한 뒤에는 foreground 스크립트의
  첫 인자로 출력 폴더, 이후 인자로 실제 토픽을 추가할 수 있다.
  예: `bash ~/LOONAR/platforms/loonar/tools/record-tof.sh ~/loonar-bags/trial01 /imu/data /wheel/odom`

## PC로 복사

PC에서 실제 기록 폴더명을 넣는다.

```bash
mkdir -p ~/loonar-bags
scp -r loonar@192.168.0.99:/home/loonar/loonar-bags/tof_YYYYMMDD_HHMMSS ~/loonar-bags/
```

## 배치 위치

`/opt/loonar/current/lib/cubeeye/bridge.py`, `/opt/loonar/current/lib/run-tof.sh`,
`/etc/loonar/tof.env`, `/etc/systemd/system/loonar-tof-record.service`.
기록 스크립트와 QoS 파일은 Pi의 `~/LOONAR/platforms/loonar/` 소스를 사용한다.
이전 실행 파일 백업: `~/loonar-staging/tof-before-20260920/`.
검증 로그: `~/loonar-staging/tof-20260920/`.

## 실기 확인 — 2026-09-20

- 센서 `I200D`, serial `I200DU2608000212`, USB 3.0 5000M.
- bag: `/home/loonar/loonar-bags/tof_20260920_040123`.
- 기록 시간 58.82초, PointCloud2 295개 + status 295개, 873.8 MiB.
- bag 내부 timestamp 기준 4.996 Hz, 프레임당 유효점 258,152~259,323개.
- 저장 데이터를 전부 역직렬화해 확인: 비정상 XYZ 0개, timestamp 역전 0개,
  첫/마지막 cloud 사이 status와 대조한 cloud 누락 0개.
- 마지막 프레임의 전방 깊이 중앙값 약 1.632 m. 실측 거리와 비교한 정확도 검증은 아니다.
- 이번 장면에서 저장량은 약 0.87 GiB/분(약 52 GiB/시간).
  유효점 수에 따라 달라진다. 공간 샘플링을 줄이려면 `TOF_STRIDE=2`로 변경 후
  기록을 종료하고 ToF 서비스를 재시작한다. 이는 이미지 가로·세로를 각각 2픽셀 간격으로
  취해 점 개수를 약 1/4로 줄이는 선택이다.
- 검증 종료 상태: ToF 수신 active / recorder inactive. 부팅 자동 시작 미설정.
- 정지 상태에서 ToF와 로컬 저장만 검증했다. 실제 주행·카메라 스트림·지상국 동시 부하
  시험은 아직 하지 않았다. 이 결과가 이후 모든 조건의 무손실을 보장하지는 않는다.
