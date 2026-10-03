# LOONAR

로버: Raspberry Pi 5 · Control/Payload Teensy 4.1 · RoboClaw.
지상국 명령은 cFS와 vehicle_gatewayd를 거쳐 Control MCU로 전달한다.

## 실행

준비된 Pi에서:

```bash
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video
```

`--video`는 SSH 접속 PC로 영상을 보낸다. SSH 밖에서는 `--video-ip 지상국IP`를 사용한다.
지상국 PC에서:

```bash
cd ~/LOONAR
bash GCS/scripts/start_loonar_gcs.sh 192.168.0.14
```

주소는 실제 Pi IP로 바꾼다. 웹 화면은 `http://127.0.0.1:8080`이다.

- [Pi 준비·실행·기록](platforms/loonar/porting/ground_control_runbook.md)
- [지상국 사용법](GCS/README.md)
- [Control 펌웨어 빌드·업로드와 배선](platforms/loonar/firmware/control/README.md)
- [Payload 측정](platforms/loonar/porting/payload_pca_runbook.md)
- [구조와 명령 경로](docs/architecture.md) · [문서 목록](docs/README.md)

## 저장소

| 경로 | 내용 |
| --- | --- |
| `GCS/` | 웹 UI, 키보드·Xbox 입력, 영상 수신 |
| `cfs/` | GroundLink, 차량·MCU·Payload 앱 |
| `common/` | Gateway, 통신 codec, 공통 ROS·영상 도구 |
| `platforms/loonar/` | Pi 배포, MCU 펌웨어, 하드웨어·PCB |
| `platforms/limo/` | LIMO 시험 플랫폼과 검증 기록 |
| `tools/` | 통합 시험, 영상·센서·주행 분석 도구 |
| `data/`, `output/` | 실험 원본과 결과 |

문서는 저장소 소스 기준이다. Pi 설치본과 MCU에 업로드된 이미지가 같다는 뜻은 아니다.
날짜가 붙은 측정·제작 기록은 당시 결과로 읽는다.
