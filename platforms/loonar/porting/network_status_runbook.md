# 조종 PC와 상태 전용 PC

Pi 주소는 `10.254.254.3`이다. 상태 전용 PC 주소는 `10.254.254.4`이다.

| 용도 | 허용 PC | 전송 |
| --- | --- | --- |
| 지상국 명령/텔레메트리, bag 프록시, 열화상 TCP | 10.254.254.2 | TCP 7443–7445 |
| Pi 영상/vision 데이터 | 10.254.254.2 | UDP 5600, 5601 |
| ROS 2 외부 통신 (domain 0) | 10.254.254.2 | DDS UDP 7400–7649 |
| 하드웨어 상태 (온도/전압/MCU 등) | 10.254.254.2 및 10.254.254.4 | Pi → PC UDP 6101 |
| 통신/프로세스 상태 | 10.254.254.2 및 10.254.254.4 | Pi → PC UDP 6102 |

## 상태 창 실행

두 PC에서 각각 다음 명령을 별도 터미널로 실행한다. 저장소가 없는 PC에는
`GCS/cli/status_udp.py` 파일 하나만 복사해도 된다. Python 3 표준 라이브러리만
사용하며 SSH 비밀번호나 ROS 설치가 필요 없다.

```bash
python3 GCS/cli/status_udp.py communication
python3 GCS/cli/status_udp.py hardware
```

Windows에서는 복사한 파일의 경로와 `python` 명령을 사용한다.
수신 PC의 방화벽은 Pi에서 들어오는 UDP 6101/6102를 허용해야 한다.
기존 `GCS/scripts/start_diagnostics.sh`와 `start_hardware_monitor.sh` 진입점도
이 UDP 수신기를 사용한다. 같은 PC에서 같은 종류의 창을 중복 실행하지 않는다.

기존 상태 조회는 SSH/ping을 사용해 전송 계층에서 양방향이었다. 새 상태 창은
UDP 수신만 수행하며 요청, ACK, SSH 로그인, ping, 제어 명령을 보내지 않는다.
Pi가 로컬 상태를 초당 한 번 수집하여 두 PC에 각각 전송한다. 통신 창은
Pi가 보고한 연결 상태를 표시하며 왕복 지연이나 PC에서의 접속 성공을 검사하지 않는다.
UDP 유실은 재전송하지 않으며 4초간 새 데이터가 없으면 이전 값을 숨기고
수신 중단을 표시한다. 발신 주소를 검사하지만 암호학적 인증은 제공하지 않는다.

## Pi 설치 및 재부팅

```bash
sudo bash platforms/loonar/tools/setup-network.sh
```

설치기는 전용 nftables 테이블 `inet loonar_link_policy`를 검사 후 적용하고,
`loonar-link-policy.service`와 `loonar-status-broadcast.service`를 부팅 시
자동 시작하도록 설정한다. 다른 방화벽 테이블은 지우지 않는다.
SSH(22), DNS 등 관리 통신은 이 정책의 제한 대상이 아니다.

`/etc/loonar/video.env`는 영상 목적지를 `.2`로 고정한다.
`/etc/loonar/ros.env`와 ROS 실행 환경은 domain 0, 로컬 discovery 및
외부 static peer `.2`를 사용한다. 변경된 실행 스크립트와 환경 변수는
다음 ground-support/ROS 실행 때 적용된다. 설치기는 실행 중인 조종 프로세스를
재시작하지 않는다. 방화벽 제한은 설치 시 즉시 적용된다.

```bash
systemctl status loonar-link-policy.service loonar-status-broadcast.service
journalctl -u loonar-status-broadcast.service -n 40 --no-pager
sudo nft list table inet loonar_link_policy
```

2026-10-16 Pi 설치 명령은 성공했다. 이후 사용자가 Pi 전원 또는 연결을
해제했으므로 실제 Pi → 두 PC 상태 수신 확인은 전원을 다시 켠 뒤 수행해야 한다.
로컬 UDP 양쪽 수신, 수신기 무송신, 오래된 데이터 처리, 발행기 재시작,
cFS 허용/비허용 피어 분리 검증은 통과했다. cFS 소스의 피어 검사 변경은
로컬 빌드로 검증했으며 Pi cFS 바이너리는 이번 설치에서 교체하지 않았다.
Pi의 피어 제한은 설치된 nftables 정책이 적용한다.
