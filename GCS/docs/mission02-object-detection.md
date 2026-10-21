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

## 처리 경로

```text
Pi 카메라 → H.264/MPEG-TS → UDP 5600 → PC FFmpeg 디코딩·회전
                                           ├─ 영상 표시
                                           └─ 최신 프레임 1개 → PC YOLO → 박스 표시
```

별도 작업 스레드가 CPU 2개 스레드로 최대 10 Hz 추론한다. 추론 중 들어온 프레임은
최신 1개만 유지하고, 영상 표시는 추론 완료를 기다리지 않는다. 디코딩 이후 대기·추론·표시
경과 시간이 500 ms를 넘은 결과는 박스를 숨긴다. 이 시간은 카메라 촬영부터 표시까지의
전체 지연 측정값이 아니다. 인식 결과는 표시용이며 주행 명령을 보내지 않는다.

Pi의 일반 지원 실행에서는 인식 노드와 BGR 공유 메모리 변환을 시작하지 않는다.
UDP 5601은 PC 인식에 필요하지 않으며 `/vision/detections`, `/vision/target_cue`를
Pi ROS에 발행하지 않는다. ToF 지형 기반 AUTO 경로는 이 객체인식과 별개다.

## 모델과 Python

기본 Python은 `GCS/.venv-vision/bin/python`, 모델은
`GCS/models/mission02/best.pt`다. `LOONAR_VIDEO_PYTHON`으로 Python을 지정할 수 있다.
Tk, Pillow, PyTorch, Ultralytics가 필요하다. 모델이나 추론 의존성이 없으면
영상은 계속 표시하고 영상 터미널에 인식 오류를 출력한다.
새 PC에 환경을 만들 때:

```bash
sudo apt install python3-venv python3-tk ffmpeg
python3 -m venv ~/LOONAR/GCS/.venv-vision
~/LOONAR/GCS/.venv-vision/bin/python -m pip install ultralytics pillow
```

현재 모델은 COCO YOLO26n 범용 모델이다. 일반 객체를 `obstacle`로 표시하며,
임무 로버를 식별하도록 학습된 모델은 아니다. 검증된 `target_rover`, `obstacle`
두 클래스 모델로 `best.pt`를 교체하고 영상 창을 다시 실행하면 목표 모델로 표시한다.

기존 Pi NCNN 진단 경로는 `LOONAR_FLY_VISION=1`을 명시한 경우에만 실행한다.
Pi 전용 런타임 설치는 [Pi 인식 패키지](../../common/ros2/loonar_target_vision/README.md)를
참고한다. PC 영상 창은 이 경우에도 자체 추론한다.
