# Pi 설치

대상은 Raspberry Pi 5 / Ubuntu 24.04 arm64 / ROS 2 Jazzy다.
일상 실행은 [ground-support 안내](../porting/ground_control_runbook.md)를 따른다.
아래는 신규 설치 또는 전체 runtime 배포용이며 MCU 빌드·업로드는
[Control 안내](../firmware/control/README.md)와 별개다.

## 설치/빌드 재현

APT 패키지 전체 목록은 [apt-packages.txt](apt-packages.txt)다.
이미 `~/LOONAR` 소스가 있는 Pi에서 다음 명령으로 설치한다.

```bash
cd ~/LOONAR
sudo bash platforms/loonar/deploy/install-deps.sh
```

Ubuntu sources에는 `noble`, `noble-updates`, `noble-security` 및 `universe`가
필요하다. 업데이트된 runtime과 오래된 `-dev` 패키지가 충돌하면 강제 downgrade하지
말고 저장소 설정을 복구한다.

```bash
cd ~/LOONAR
bash tools/run_gcs_test.sh --build-only --skip-tests --jobs 2
bash platforms/loonar/deploy/build-camera-stack.sh
```

카메라는 RPi libcamera `v0.7.2+rpt20260817` 및 rpicam-apps `v1.13.0`의 정확한
commit을 스크립트에 고정했다. `/usr`의 Ubuntu libcamera를 교체하지 않고
`/opt/loonar/camera-stack/`에 설치한다. 이 빌드 성공만으로 Noble kernel/CSI 호환성이
검증되지는 않는다. 실제 장치 단계에서 확인한다.

rpicam 1.13의 libav encoder는 Noble의 FFmpeg 6.1보다 새 API를 요구하므로 빌드에서
비활성화한다. `rpicam-still`의 사진 취득을 준비하고, 지상국 동영상은 별도의
GStreamer `libcamerasrc → x264enc` 경로를 사용한다. Pi 5에서 `rpicam-vid`의
기본 H.264 인코딩이 된다고 가정하지 않는다.

CubeEye SDK는 [vendor-assets.md](../vendor-assets.md)의 별도 archive를
`~/loonar-staging/cubeeye/`에 풀고 다음을 실행한다.

```bash
bash ~/LOONAR/platforms/loonar/deploy/build-tof-helper.sh
```

SDK의 구형 OpenCV/FFmpeg library path는 helper 자식 프로세스에만 적용한다.
ROS/카메라 서비스의 전역 library path로 등록하지 않는다.

ROS는 중복 이름의 실험 패키지를 포함하지 않고 Pi 최소 EKF 패키지만 빌드한다.

```bash
# rosdep 초기화는 /etc/ros/rosdep/sources.list.d/20-default.list가 없을 때만 실행
test -f /etc/ros/rosdep/sources.list.d/20-default.list || sudo rosdep init
rosdep update --rosdistro jazzy
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths ~/LOONAR/platforms/loonar/ros2/loonar_localization \
  --ignore-src --rosdistro jazzy -y
mkdir -p ~/loonar_jazzy_ws
cd ~/loonar_jazzy_ws
colcon build --base-paths ~/LOONAR/platforms/loonar/ros2/loonar_localization \
  --merge-install --cmake-args -DBUILD_TESTING=OFF
```

## 전체 systemd runtime 설치

위 gateway/cFS, 카메라, CubeEye helper, ROS 빌드 산출물이 모두 필요하다.
관련 서비스가 실행 중이면 설치 스크립트가 거부한다. 새 release 이름으로 실행한다.

```bash
sudo bash ~/LOONAR/platforms/loonar/deploy/install-runtime.sh 20261003-local
```

이미 존재하는 release 이름은 재사용하지 않는다. 설치는 서비스를 enable/start하지 않는다.
`/opt/loonar/current` symlink를 새 release로 바꾸며 `/var/lib/loonar/cfs/cf/`의
네 앱과 startup 파일도 갱신한다. 설정 예제는 `/etc/loonar/`에 복사한다.
기존 설정의 장치 경로·IP는 별도로 확인한다.

| 경로 | 내용 |
| --- | --- |
| `/opt/loonar/current` | 선택한 runtime |
| `/opt/loonar/camera-stack/current` | libcamera/rpicam 별도 설치 |
| `/opt/loonar/vendor/cubeeye/2.5.9/release` | ARM64 SDK |
| `/etc/loonar` | registry·센서·영상·Payload 설정 |
| `/var/lib/loonar/cfs` | cFS 실행 디렉터리 |

`vehicle_gatewayd`, `loonar-cfs`, `loonar-mcu@`, `loonar-mcu-sensors`,
`loonar-payload-pca`, `loonar-video`, `loonar-tof`, `loonar-localization` unit이 설치된다.
checkout bench와 같은 장치·포트를 사용하는 서비스를 중복 실행하지 않는다.
그룹 권한을 새로 추가했다면 SSH에 재접속한다.

- [Payload 설정](../porting/payload_pca_runbook.md)
- [ToF 실행과 기록](../porting/tof_recording_runbook.md)
- [2026-09-18 설치 기록](preparation-20260918.md): 당시 설치 증거이며 현재 상태표가 아니다.
