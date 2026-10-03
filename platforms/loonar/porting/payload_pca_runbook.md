# Payload PCA 수동 정차 지점 시험

Payload Teensy와 센서는 임무 내내 켜 둔다. 지상국 `PAYLOAD START`는 Pi에서
항상 연결된 USB CDC로 MCU에 `START` 명령을 보내 센서 재초기화와 새 지점
계측을 시작한다. `PAYLOAD STOP`은 MCU에 `STOP` 명령을 보내며, MCU는
시작 후 최소 5초가 지난 다음 그 지점의 PCA 한 행을 출력한다. Pi는 PCA와
완료 응답을 받은 뒤 로그 파일만 닫고 USB 상태 조회는 유지한다. 센서 전원은 끄지 않는다.

첫 번째 완료 구간은 `STATION01`이고, 다음 START/STOP 구간은 `STATION02`다.
MCU를 재부팅하면 지점 번호는 다시 1부터 시작한다. 각 구간의 원시 센서
행과 PCA 행은 Pi의 별도 `payload-pca-*.csv`에 저장된다. 지상국에는
지점별 자기장 중앙값, IR/RTD 온도, novelty, candidate 및 모델 상태가 표시된다.
현재 `model_params.h`는 **DEMO_ONLY**이며 과학적 이상 판정용 모델이 아니다.

## 명령 계약

[Payload USB v1 명세](payload_protocol.md)에 명령·health·CSV/PCA 필드와 재접속 동작을 정의한다.
Pi 서비스·MCU 펌웨어·cFS·GCS를 함께 갱신해야 한다. 구형 자동 PCA 출력 펌웨어는
STATUS 응답이 없어 OFFLINE으로 표시되며 새 서비스의 START를 받을 수 없다.

## 준비와 확인

1. `platforms/loonar/firmware/payload`를 PlatformIO로 빌드하여 Payload Teensy에 업로드한다.
2. Pi에서 `/dev/serial/by-id/`의 Payload Teensy 경로를 확인한다.
3. `/etc/loonar/payload-pca.env`에 `PAYLOAD_DEVICE`와 `PAYLOAD_LOG_DIR`를 설정한다.
4. Pi에 현재 `main`을 설치하고 다음 서비스를 시작한다.

```bash
sudo systemctl start loonar-payload-pca.service
sudo systemctl start vehicle_gatewayd.service loonar-cfs.service
journalctl -u loonar-payload-pca.service -f
```

지상국에서 START를 눌러 `RUNNING,station_01` 이벤트와 원시 센서 행을
확인한다. 센서 재초기화가 끝나고 5초가 지난 뒤 STOP을 눌러 PCA 값과
`IDLE,station_01_complete` 이벤트를 확인한다. 다음 지점에서 반복하면
`station_02`가 된다. 로그 경로는 `/var/lib/loonar/payload/payload-pca-*.csv`다.

## Checkout에서 함께 실행

systemd Payload 서비스 대신 bench에서 실행할 수 있다. 같은 USB를 두 프로세스가 열지 않는다.

```bash
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --payload-device /dev/serial/by-id/usb-Teensyduino_USB_Serial_20356570-if00
```

기존 `--video`, `--record` 등과 함께 사용 가능하다(`--video`는 맨 앞).
이 방식은 runtime/payload-pca.sock과 runtime/payload/ CSV를 사용한다.
서비스 실패는 보고하되 Control 프로세스는 유지한다. 종료 시 MCU 측정 자동 STOP은 없으므로
완료 결과가 필요하면 GCS에서 Payload STOP을 누르고 완료 응답 후 종료한다.

## 변경 적용

PC에서 firmware를 빌드하고 Pi에 복사한다. 아래 tag는 확인했던 Payload 보드다.

```bash
cd ~/LOONAR
~/.local/bin/pio run -d platforms/loonar/firmware/payload -e teensy41
scp platforms/loonar/firmware/payload/.pio/build/teensy41/firmware.hex loonar@10.254.254.3:~/payload-v1.hex
```

Pi에서 기존 지원 프로그램과 시리얼 모니터를 종료한 뒤 업로드한다.

```bash
~/.local/bin/tycmd upload --board 20356570-Teensy ~/payload-v1.hex
```

Pi checkout에도 현재 `cfs/`, `platforms/loonar/tools/` 소스를 반영하고
`bash ~/LOONAR/platforms/loonar/deploy/prepare-ground-control.sh`로 cFS를 재빌드한 뒤
위 `--payload-device` 명령으로 실행한다. 이 절차는 전체 `/opt` runtime 설치를 요구하지 않는다.
