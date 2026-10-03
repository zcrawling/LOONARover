# 지상국

## 실제 LOONAR 연결

Pi의 [지원 프로그램](../platforms/loonar/porting/ground_control_runbook.md)을 먼저 실행한다.
PC에서:

```bash
cd ~/LOONAR
bash GCS/scripts/start_loonar_gcs.sh 192.168.0.14
```

웹 UI `http://127.0.0.1:8080`, 진단·영상 창과 감지된 Xbox 입력 창을 연다.
Pi 주소는 실제 주소로 바꾼다. 이미 실행 중인 GCS는 종료하고 다시 실행해야
코드·설정 변경이 반영된다. 설정은 [config/loonar.toml](config/loonar.toml)이다.

Python 3.11 이상, SSH, ffmpeg/ffplay, gnome-terminal, xdg-open이 필요하다.
영상 테두리 표시는 tkinter와 Pillow를 사용한다. Xbox 장치 접근은
[설정 안내](docs/xbox-controller.md)를 따른다.

| 연결 | 기본값 |
| --- | --- |
| PC 웹 UI | TCP 8080, localhost |
| Pi GroundLink | TCP 7443 |
| PC 영상 수신 | UDP 5600, H.264/MPEG-TS |
| PC backend | `GCS/.runtime/backend.sock` |

방향키로 주행하며 키 해제·포커스 상실 시 속도 0을 요청한다.
STOP은 별도 모드 명령이다. Xbox LT는 A/B, RT는 STOP/MANUAL을 전환하며
Xbox 터미널에 포커스가 있을 때만 입력한다. [상세 조작](docs/xbox-controller.md).
종료 전 STOP을 누르고 PC와 Pi의 실행 터미널에서 Ctrl+C한다.

선속도 상한은 0.4m/s, 회전 상한은 3.8rad/s다. 혼합 주행은 바퀴 속도가
0.4m/s를 넘지 않도록 정규화한다. **남은 불일치:** 웹 HTTP 입력 검사는 아직
각속도 1.0rad/s 초과를 거부한다(`webui/server.py`). 이 문서 정리에서 코드는 수정하지 않았다.

Payload 버튼은 [별도 Pi 서비스](../platforms/loonar/porting/payload_pca_runbook.md)가 필요하다.
영상 탐지는 [Mission02 안내](docs/mission02-object-detection.md)를 참고한다.

## 개별 실행

```bash
cd ~/LOONAR/GCS
python3 -B -m webui.server --real-host 192.168.0.14
bash scripts/start_diagnostics.sh --host 192.168.0.14
bash scripts/start_video.sh --rotate-left --record --compass
```

각 명령은 별도 터미널에서 실행한다. 영상 수신기는 UDP 포트를 중복 사용하지 않도록
기존 창을 종료한다. PC 녹화는 `~/Videos/LOONAR/`에 저장되며 Pi 녹화와 별개다.
상대 방위는 자이로 적분 기준으로, 절대 북쪽을 보장하지 않는다.

## 장치 없는 Mock

각 터미널에서 `cd ~/LOONAR/GCS` 후 하나씩 실행한다.

```bash
python3 -m mock.rover
python3 -m backend.app
python3 -m cli.commands
python3 -m cli.monitor
```

Mock은 [GCP1 계약](docs/interface-draft.md)을 사용한다. 실제 로버의
[LNK1](../docs/ground_link_protocol.md)과 호환되지 않으며 Mock 결과는 실기 검증이 아니다.
cFS까지 포함하는 PC 시험은 [통합 시험 도구](../tools/gcs_test/README.md)를 사용한다.
