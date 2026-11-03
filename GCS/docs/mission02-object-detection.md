# 지상국 PC 객체인식

## 실행

Pi에서 영상 지원 프로그램을 실행한다:

```bash
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video
```

PC에서는 기존 영상 창을 닫고 실행한다:

```bash
bash ~/LOONAR/GCS/scripts/start_video.sh
```

기본 실행은 방위 표시·왼쪽 90도 회전·PC 객체인식을 켠다. 옵션을 명시할 때는
`--compass --rotate-left`를 넣는다. `--compass` 없는 ffplay 경로는 영상만 표시한다.
PC 영상 녹화는 `--record`를 명시해야 켜지며, Pi의 `--record`/`--record-all`과 별개다.

지상국 `start_gcs.sh` 실행 터미널에서 `obj` + Enter를 누르면 객체인식을
ON/OFF 전환한다(백엔드 시작 시 기본 ON). OFF에서도 영상 표시와 녹화는 계속되며,
진행 중인 초기 로딩 또는 추론을 마친 뒤 인식 작업은 대기한다. 모델은 메모리에
유지하므로 다시 ON으로 바꾸면 최신 영상으로 재개한다. 영상 하단에 ON/OFF가 표시된다.

## 처리 경로

```text
Pi 카메라 → H.264/MPEG-TS → UDP 5600 → PC FFmpeg 디코딩·회전
                                           ├─ 영상 표시
                                           └─ 최신 프레임 1개 → PC NCNN YOLO → rover/obstacle 박스 표시
```

별도 작업 스레드가 NCNN CPU 2개 연산 스레드로 최대 10 Hz 추론한다. 추론 중 들어온 프레임은
최신 1개만 유지하고, 영상 표시는 추론 완료를 기다리지 않는다. 디코딩 이후 대기·추론·표시
경과 시간이 500 ms를 넘은 결과는 박스를 숨긴다. 이 시간은 카메라 촬영부터 표시까지의
전체 지연 측정값이 아니다. 인식 결과는 표시용이며 주행 명령을 보내지 않는다.

Pi의 일반 지원 실행에서는 인식 노드와 BGR 공유 메모리 변환을 시작하지 않는다.
UDP 5601은 PC 인식에 필요하지 않으며 `/vision/detections`, `/vision/target_cue`를
Pi ROS에 발행하지 않는다. ToF 지형 기반 AUTO 경로는 이 객체인식과 별개다.

## 모델과 Python

기본 Python은 `GCS/.venv-vision/bin/python`, 모델은
`GCS/models/mission02/best_ncnn_model/`이다. `LOONAR_VIDEO_PYTHON`으로 Python을 지정할 수 있다.
Tk, Pillow, PyTorch, Ultralytics 8.4.145, NCNN 1.0.20260526이 필요하다.
PyTorch는 Ultralytics 의존성으로 남지만 모델 연산은 NCNN CPU에서 수행한다.
모델이나 추론 의존성이 없으면
영상은 계속 표시하고 영상 터미널에 인식 오류를 출력한다.
새 PC에 환경을 만들 때:

```bash
sudo apt install python3-venv python3-tk ffmpeg
python3 -m venv ~/LOONAR/GCS/.venv-vision
~/LOONAR/GCS/.venv-vision/bin/python -m pip install --only-binary=:all: --index-url https://download.pytorch.org/whl/cpu torch torchvision
~/LOONAR/GCS/.venv-vision/bin/python -m pip install --only-binary=:all: -r ~/LOONAR/GCS/requirements-vision.txt
```

현재 기본 모델은 보유 로버와 스티커를 목표로 학습한 2클래스 NCNN FP32 모델이다.
내부 출력은 `0: target_rover`, `1: obstacle`이며 화면에서만 `rover`, `obstacle`로 표시한다.
미검출 물체까지 자동으로 장애물이 되는 것은 아니다. 현장 정확도는 별도 검증이 필요하다.
기존 `best.pt`는 보관만 하며 기본 실행에서 사용하거나 자동 대체하지 않는다.
모델 교체 시 `.param`, `.bin`, `metadata.yaml`, `deployment.json`을 함께 교체한다.
시작 시 배포 파일의 개별 SHA-256, 클래스, 입력 크기, 백엔드를 검사하고 준비 추론한다.
터미널의 `GCS vision: NCNN / CPU / ... / threads=2` 로그로 실행 경로를 확인한다.
입력 640×384, 신뢰도 0.35, 최대 12박스, 500ms 유효 시간, obj ON/OFF는 유지한다.
100ms 추가 휴식은 이번 변경에 포함하지 않았다. Pi·노트북에 자동 설치/배포하지 않는다.

기존 Pi NCNN 진단 경로는 `LOONAR_FLY_VISION=1`을 명시한 경우에만 실행한다.
Pi 전용 런타임 설치는 [Pi 인식 패키지](../../common/ros2/loonar_target_vision/README.md)를
참고한다. PC 영상 창은 이 경우에도 자체 추론한다.
