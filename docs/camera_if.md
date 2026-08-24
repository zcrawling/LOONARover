# Camera Interface

## 1. 책임과 소유권

`camera.service`만 Camera 장치를 열고 capture format, frame lifetime, encoder, health를 소유한다. Vision과 GCS는 Camera device를 직접 열지 않는다.

## 2. 초기 구조

초기 구현은 libcamera와 GStreamer pipeline 하나로 구성한다.

```text
Camera capture
  -> tee
      -> leaky queue(depth 1) -> ROS Vision input
      -> leaky encoder queue -> hardware encoder -> GCS video
```

느린 consumer 때문에 capture가 block되지 않도록 모든 branch는 bounded/leaky로 설정하고 오래된 frame을 버린다. 주행 제어 경로와 공유하는 lock이나 queue를 두지 않는다.

## 3. Vision branch

- 항상 최신 frame 하나만 유지한다.
- metadata는 `frame_sequence`, `capture_time_ns`, width, height, format, validity다.
- Vision 결과에는 사용한 `frame_sequence`와 age를 포함한다.
- inference 완료 시 이미 허용 age를 넘은 결과는 폐기한다.
- 초기에는 ROS `image_transport` 또는 GStreamer ROS source를 사용한다.

Raspberry Pi 5 profiling에서 복사 비용이 CPU/latency 요구를 넘는다는 측정이 있을 때만 FD 기반 zero-copy를 추가한다.

## 4. Video branch

- hardware H.264/H.265 encoder를 우선 사용한다.
- bitrate, resolution, FPS는 bounded config로 제한한다.
- network 정체 시 오래된 encoded frame을 버리고 실시간성을 유지한다.
- `GCS_IF`가 인증한 session에 대해 짧은 수명의 stream token을 발급하고 video branch는 token만 검증한다.
- video 연결 실패나 encoder 재시작은 Vision과 drive에 영향을 주지 않는다.

## 5. 제어 endpoint

local control 메시지는 다음으로 제한한다.

| Message | 필드 | 목적 |
| --- | --- | --- |
| `CAMERA_CONFIG` | `request_id`, profile enum | 사전 정의 profile 선택 |
| `VIDEO_SESSION` | `request_id`, token, expiry | 인증된 video 시작/종료 |
| `CAMERA_STATUS` | sequence, validity, counters | cFS/GCS 요약 상태 |

임의 GStreamer pipeline 문자열, device path, output file path를 외부 입력으로 받지 않는다.

## 6. 상태와 counter

`CAMERA_STATUS`는 다음을 포함한다.

- state: `OFF`, `STARTING`, `RUNNING`, `DEGRADED`, `FAULT`
- capture FPS와 encoded FPS
- latest frame age
- Vision drop, encoder drop, network drop
- capture/encoder restart count
- last fault reason

상태전이와 fault만 cFS/GCS event로 보낸다. frame 단위 event는 만들지 않는다.

## 7. 장애 동작

| 장애 | 동작 |
| --- | --- |
| Vision 지연/종료 | Vision frame drop, capture/video 유지 |
| GCS network 정체 | encoded frame drop, capture/Vision 유지 |
| encoder fault | encoder branch만 재초기화 |
| Camera disconnect | bounded backoff 재연결, Camera fault 통보 |
| `camera.service` 종료 | systemd 재시작, drive 영향 없음 |

## 8. 검증

- Vision consumer 정지 중 capture FPS와 memory 상한
- video network 0/저대역폭에서 drop 정책
- encoder restart가 Vision sequence를 중단하지 않는지 확인
- 30분 thermal/CPU/전력 측정
- frame capture time부터 Vision result/video 표시까지 latency
- profiling Gate 전에는 zero-copy 전용 코드를 추가하지 않음
