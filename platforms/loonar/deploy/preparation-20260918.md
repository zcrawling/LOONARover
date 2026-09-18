# 2026-09-18 Pi 사전 준비 기록

요청 범위: 하드웨어 제작 중, 카메라 검증 전에 가능한 설치·빌드·배포.
이번 작업에서는 자동 테스트, 실기 통신 시험, 카메라 열거/촬영, ROS 노드 실행,
펌웨어 업로드, 모터 명령을 실행하지 않았다. 아래 빌드/정적 점검은 기능 합격 판정이 아니다.

## 대상과 설치

- 접속 대상: `loonar@10.42.0.103`.
- Raspberry Pi 5, aarch64, 메모리 약 8 GiB.
- Ubuntu 24.04.5 LTS, 실행 중 kernel `6.8.0-1064-raspi`.
- `noble-updates` 누락을 복구한 뒤 [전체 APT 목록](apt-packages.txt) 설치 완료.
  `/etc/apt/sources.list.d/ubuntu.sources.loonar-backup`에 원본 보관.
- ROS Jazzy ros-base `0.11.0-1noble.20260903.024458`, robot_localization
  `3.8.3-1noble.20260902.170723` 설치. 최소 EKF의 rosdep 의존성 해결 완료.
- `/boot/firmware/config.txt`의 기존 `camera_auto_detect=1` 확인. 부팅 설정 변경·재부팅 없음.
- 원격 소스: `/home/loonar/LOONAR`, 기반 commit `9027237` 이후 이번 준비 변경 반영.

## 빌드 산출물

| 구성 | 준비 결과 | 남은 실기 확인 |
| --- | --- | --- |
| gateway/ctl | Pi ARM64 native build 완료, `BUILD_TESTING=OFF` | 실제 cFS/socket/backend 연동 |
| cFS v7.0.1 + GroundLink/VehicleAdapter | Pi native mission build 완료 | TCP 7443 지상국 왕복, runtime startup |
| 최소 Jazzy EKF | 선택한 1개 package colcon build 완료 | MCU 실측 입력, TF, odom 품질 |
| CubeEye helper | SDK 2.5.9로 ARM64 link 완료, `ldd` missing 없음 | 실제 I200DK XYZ/ROS 점군/재연결 |
| Control Teensy USB/UART | 두 PlatformIO 환경 compile 완료, hex 보관 | 업로드, USB CDC 통신, timeout/재연결 |
| 카메라 전용 스택 | libcamera 0.7.2 / libpisp 1.5.0 / rpicam 1.13.0 build·배포 완료 | CSI 열거, 촬영, 실제 GCS 표시 |

첫 clean Pi build에서 누락됐던 cFS `tools/tblCRCTool`, `tools/commandline-tools`
submodule을 runner에 추가했다. `--build-only --skip-tests`를 추가해 build 후 runtime
시작과 synthetic 상태 주입 경로로 들어가지 않도록 했다.

CubeEye archive SHA256:
`e7055c03d3d6638683f37c2d10236a8ba23d8cecb277f6858a608653a1061ea3`.
SDK의 library path는 helper 자식에만 설정한다.

Control firmware는 `teensy41_usb` 빌드를 추가했다. 기본 UART는 유지하며
USB 포트가 열리지 않아도 제어 task 부팅을 기다리지 않는다. USB DTR이 필요하다.
두 hex는 Pi의 `~/loonar-staging/firmware/control-{usb,uart}/firmware.hex`에 보관했다.
펌웨어는 보드에 쓰지 않았다. 실제 제어기는 여전히 항상 0 출력이다.

## 최종 배포 기록

`/opt/loonar/releases/20260918-pre-camera`에 배포하고 `/opt/loonar/current`를 연결했다.
`/home/loonar/loonar-staging/preparation-manifest.json`에 실제
source revision, package version, binary SHA256, systemd 상태를 기록했다.
`systemd-analyze verify`는 오류 없이 종료했다. 설치한 5개 service와 core target은
모두 `loaded / inactive / dead / disabled`다.
gateway, cFS core, CubeEye helper, rpicam-hello/still, GStreamer libcamera plugin의
설치 후 `ldd` 결과에 missing library가 없다. 이것은 장치 실행 검증이 아니다.

카메라 전용 library 경로와 IPA 경로는 camera wrapper에만 적용한다.
Noble FFmpeg 6.1과 rpicam 1.13 libav encoder의 API 불일치 때문에 후자는 빌드에서
비활성화했다. 실제 영상 송신은 GStreamer/libcamerasrc/x264enc를 사용한다.
`/usr`의 libcamera/FFmpeg는 source build로 덮어쓰지 않았다.
영상 설정은 GCS `10.42.0.1`, UDP 5600, low profile이며 서비스는 정지 상태다.

`loonar`에 `dialout,video,render,plugdev`를 추가하고 USB udev 규칙을 배치했다.
장치 trigger는 하지 않았다. 다음 하드웨어 단계 시작 전에 SSH를 새로 접속한다.
로그는 같은 staging 디렉터리의 `apt-install.log`, `cfs-build.log`, `ros-build.log`,
`tof-build.log`, `tof-linkage.txt`, `camera-build.log`, `runtime-install.log`,
`systemd-verify.log`, `runtime-linkage.txt`에 보관한다.
cFS 세부 build log는 `~/LOONAR/build/gcs-test/build.log`다.

## 후속 순서와 남은 구현

1. 카메라: CSI 열거 → 단독 이미지 → 별도 UDP 영상의 지상국 표시.
2. Teensy USB: 실제 serial ID 지정, 비구동 통신/재연결 확인.
3. 라이다/ToF: 현재 확보된 것은 I200DK SDK. 다른 라이다 모델은 별도 확정 필요.
4. 모터/주행: Control backend, encoder/BNO085 수집, 실제 제어기, command freshness,
   측정 TF, motion restrict 실행기와 상태 연결을 완성한 뒤 검증.

독립 Payload Transport/cFS payload app은 아직 없다. 기존 command MID 발행과
relay 코드만으로 payload 왕복이 구현됐다고 판단하지 않는다.
[실행 명령과 기록 방법](README.md)을 다음 하드웨어 단계에서 사용한다.
