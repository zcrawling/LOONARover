# ROS 없는 PC 지상국 통합 테스트

이 PC를 로버 역할로 사용한다. **실제 NASA cFS v7.0.1 + LOONAR 앱 두 개 +
vehicle_gatewayd**를 실행한다. 실제 모터/ROS backend는 실행하지 않는다.

```bash
cd /home/sb/LOONAR
# 명령/텔레메트리만
./tools/run_gcs_test.sh

# 지상국 IP를 인자로 지정, 테스트 영상까지 전송
./tools/run_gcs_test.sh --gcs-ip 192.168.0.100 --video test

# 연결된 V4L2 카메라 영상 (MJPEG 640x480@30 지원 필요)
./tools/run_gcs_test.sh --gcs-ip 192.168.0.100 --video camera --video-device /dev/video0
```

첫 실행은 GitHub에서 cFS를 다운로드하고 빌드한다. 모든 산출물은
`build/gcs-test/`에 저장한다. 시스템 설치/sudo가 필요하지 않다.
필요 도구: `git`, `cmake`, `make`, C/C++ 컴파일러, `python3`, `stdbuf`.
영상 사용 시 GStreamer의 `x264enc`, `h264parse`, `mpegtsmux`, `udpsink`와
선택한 소스 플러그인이 필요하다.

`READY`가 출력되면 연결한다. 실행 터미널에서 **Ctrl+C**로 전체 종료한다.
이미 빌드했다면 `--skip-build`로 빠르게 실행할 수 있다.
`--build-only`는 다운로드/빌드/호스트 테스트만 수행한다.
하드웨어 준비 중 테스트와 런타임 실행을 모두 생략하고 ARM64에서 컴파일만 하려면:

```bash
./tools/run_gcs_test.sh --build-only --skip-tests --jobs 2
```

`--skip-tests`는 `--build-only`와 함께만 허용한다. 이 경로는 cFS/gateway 실행,
포트 바인딩, synthetic telemetry 주입 및 영상 실행 전에 종료한다.

## 포트 / 설정

| 경로 | 주소 |
| --- | --- |
| 지상국 → 이 PC 명령 및 텔레메트리 | **이 PC IP:7443/TCP** (0.0.0.0에서 수신) |
| 이 PC → 지상국 영상 | **--gcs-ip:5600/UDP**, `--video-port`로 변경 가능 |
| cFS ↔ gateway | `/tmp/loonar-gcs-test-<UID>/cfs.sock` |
| 테스트 배터리 주입 → gateway | 같은 디렉터리의 `backend.sock` |

`ros.sock`도 gateway가 생성하지만 ROS 프로세스는 실행하지 않는다.
Unix socket에는 TCP/UDP 포트 번호가 없다. 7443은 TLS/HTTP가 아닌
[GroundLink 바이너리 프로토콜](../../docs/ground_link_protocol.md)이다.
외부 지상국은 실행 시 출력하는 이 PC의 LAN IP를 `ROVER_HOST`로 사용한다.
`--gcs-ip`는 영상 수신 PC이며 제어 서버 주소를 바꾸지 않는다.

지상국 PC에서 영상 수신:

```bash
ffplay -fflags nobuffer -flags low_delay -framedrop 'udp://@:5600'
```

## 확인과 한계

- 배터리는 기본 **11.7 V 테스트 값**을 1초마다 전송한다.
  `--battery-voltage 12.0`으로 변경할 수 있다. 다른 VehicleStatus 필드는 미측정이다.
- STOP/MANUAL/AUTO 모드 선택과 명령 전달을 확인한다. ROS 없이 AUTO의
  실제 주행 명령은 발생하지 않는다. 물리 모터는 연결하지 않는다.
- PAYLOAD/REACTION 경로는 기존 구현 그대로이며 실제 MCU 동작은 구현되지 않았다.
  REACTION은 `NOT_IMPLEMENTED`를 반환한다.
- 지상국 연결은 한 개만 허용한다. 실제 GCS와 아래 mock을 동시에 실행하지 않는다.

다른 터미널에서 테스트 명령(3초 후 timeout 종료 코드 124는 정상):

```bash
timeout 3 ./build/gcs-test/host/common/ground_link/ground_link_mock 127.0.0.1 7443 manual 0 0
timeout 3 ./build/gcs-test/host/common/ground_link/ground_link_mock 127.0.0.1 7443 stop
```

수신 명령 / cFS 로그:

```bash
tail -f build/gcs-test/gateway.log build/gcs-test/cfs.log
```

빌드 오류는 `build/gcs-test/build.log`, 영상 오류는 `build/gcs-test/video.log`에서 확인한다.

로컬 자동 통합 검증(다른 GCS 테스트 실행을 종료한 뒤):

```bash
python3 tools/gcs_test/smoke.py
```

실제 cFS에 다섯 명령을 보내고 응답, 배터리 텔레메트리, UDP MPEG-TS 패킷,
중복 실행 거부 및 종료 후 포트 정리를 검증한다. 실제 카메라/외부 네트워크는
이 자동 검증에 포함되지 않는다.
