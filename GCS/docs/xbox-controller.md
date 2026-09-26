# Xbox Series USB 컨트롤러

지원 장치: Microsoft Xbox Series S|X Controller, USB **045e:0b12**.
Linux `xpad`/evdev를 사용하며 추가 pip 패키지는 필요 없다.
USB 이벤트 번호는 바뀔 수 있어 매번 VID/PID로 자동 탐색한다.
기존 웹 키보드 주행(Page Up/Home/Page Down/End/Space)은 그대로 사용한다.

## 실행

지상국 PC에서 컨트롤러를 연결하고:

```bash
cd /home/sb/LOONAR
./GCS/scripts/start_loonar_gcs.sh 192.168.0.14
```

GCS 실행 시 지원 장치를 읽을 수 있으면 별도 Xbox 터미널도 열린다.
이미 GCS가 실행 중이면 **백엔드 변경 적용을 위해 한 번 종료 후 재시작**한다.
나중에 연결했거나 직접 창을 열려면:

```bash
gnome-terminal -- /home/sb/LOONAR/GCS/scripts/start_controller.sh
```

컨트롤러 터미널에서 다른 창으로 전환했다가 돌아온 뒤, RT를 눌러 MANUAL을 선택한다.
터미널의 포커스 ON 표시를 확인한다. 최초 상태는 A/STOP이며 자동으로 주행하지 않는다.
포커스 이벤트를 보고하는 GNOME Terminal 등에서 사용한다. tmux/screen 내부는 지원하지 않는다.
포커스 보고를 지원하지 않는 터미널에서는 포커스 OFF 상태로 남아 조종할 수 없다.

로버 없이 이 PC의 실제 컨트롤러 입력과 표시만 확인:

```bash
gnome-terminal -- /home/sb/LOONAR/GCS/scripts/start_controller.sh --dry-run
```

이 모드는 네트워크/로버 명령을 전혀 보내지 않는다.
장치 정보만 확인하려면 `./GCS/scripts/start_controller.sh --inspect`.
여러 장치 연결 시 `--device /dev/input/eventN`으로 선택한다.
자동 창 열기는 `GCS_XBOX=0 ./GCS/scripts/start_loonar_gcs.sh 192.168.0.14`로 끌 수 있다.

## 조작

| 입력 | 동작 |
| --- | --- |
| LT | A ↔ B 전환, 누를 때마다 한 번 |
| RT | STOP ↔ MANUAL 전환, 누를 때마다 한 번 |
| A: 왼쪽 스틱 전후 | 직선 전진/후진, 좌우 축 무시 |
| A: 오른쪽 스틱 좌우 | 제자리 좌/우 회전, 전후 축 무시 |
| B: 왼쪽 스틱 | 전후 속도와 좌우 회전 속도를 동시에 전달 |
| B: 오른쪽 스틱 | 사용하지 않음 |
| 기타 컨트롤러 버튼 | 사용하지 않음 |
| Q / Ctrl+C | 조종 중이면 STOP 전송 후 종료 |

A에서 두 스틱을 동시에 기울이면 **오른쪽 제자리 회전 우선**으로 선속도를 0으로 한다.
B에서 전후 스틱이 중앙이면 조향도 0으로 하여 제자리 회전을 하지 않는다.
B의 좌우 입력은 전진/후진 모두 같은 각속도 부호를 사용한다(왼쪽 = 양의 yaw).
개별 바퀴 속도 변환은 기존 로버 backend/MCU가 수행한다.

중앙 ±8%는 0이며, 그 밖은 기울기에 따라 크기 0.01~1.00으로 선형 변환한다.
선속도 단위는 m/s, 각속도 단위는 rad/s이다. 전후·좌우 방향에 따라 부호가 바뀐다.
`--deadzone 0.10`처럼 중앙 무입력 범위를 조정할 수 있다.
LT/RT는 65% 이상에서 눌림, 25% 이하에서 해제로 판정하여 누르고 있는 동안 반복 전환하지 않는다.
MANUAL 상태에서는 약 10Hz로 현재 속도를 전송하고 스틱을 놓으면 MANUAL(0,0)을 전송한다.

## 화면과 포커스

화면 상단에 **A/B, 조종기의 STOP/MANUAL 선택, 포커스, 로버가 보고한 상태**를 계속 표시한다.
A/B는 조이스틱 매핑이며 로버 AUTO 모드와는 관계없다.
전송 성공은 로컬 backend가 명령을 보냈다는 뜻이며 실제 로버 상태는 별도로 표시한다.

조종 중 포커스를 잃으면 STOP을 한 번 보내고 조종기를 STOP 상태로 전환한다.
그 이후 포커스가 없는 동안에는 명령을 보내지 않아 기존 웹 키보드 주행을 사용할 수 있다.
돌아와도 자동으로 재주행하지 않으며 RT를 다시 눌러야 한다.
컨트롤러 분리/이벤트 유실/프로그램 종료 시에도 활성 상태라면 STOP을 시도한다.
통신 자체가 끊어지면 STOP 전달은 보장되지 않으며 실패 메시지를 출력한다.

컨트롤러는 GCS의 로컬 Unix API를 사용한다. 웹 키보드와 동일한 backend TCP 연결 및
시퀀스 번호를 공유하며, 컨트롤러가 로버 7443 포트에 두 번째 연결을 만들지 않는다.
별도 구형 `cli.keyboard_control` 직접 TCP 조종기는 동시에 실행하지 않는다.
로버나 MCU 배포 변경은 필요 없다.

## 검증

```bash
cd /home/sb/LOONAR/GCS
python3 -B -m unittest tests.test_xbox_control tests.test_xbox_terminal tests.test_xbox_backend tests.test_keyboard_control tests.test_real_backend -v
```

축/트리거 매핑, 포커스 상실·복귀, 장치 분리 시 STOP, 드라이런, 기존 키보드 회귀,
로컬 Unix API → 하나의 GroundLink TCP 연결로 복합 속도 전송을 검증한다.
실제 로버의 바퀴 주행은 자동 테스트에 포함하지 않는다.

구현 근거: [Linux 입력 이벤트](https://docs.kernel.org/input/event-codes.html),
[xterm 포커스 보고](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html).
