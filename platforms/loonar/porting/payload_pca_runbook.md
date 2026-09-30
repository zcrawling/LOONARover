# Payload PCA 수동 임무 시험

이 경로는 Payload Teensy의 세 센서를 500 ms마다 읽고 5초 station 중앙값으로
PCA를 계산한다. 현재 `model_params.h`는 **DEMO_ONLY**이며 이상 판정용 모델이 아니다.

## 명령 계약

GroundLink `PAYLOAD_CMD` opcode는 다음 두 값만 사용한다.

- `1`: 센서 전원 ON, USB CDC 연결, 기록/PCA 수신 시작
- `2`: USB CDC 종료, 로그 닫기, 센서 전원 OFF

지상국의 `PAYLOAD START`와 `PAYLOAD STOP` 버튼이 각각 위 opcode를 전송한다.
PCA 행은 기존 EVENT 텔레메트리를 통해 전달되므로 wire type을 추가하지 않는다.

## 전원 하드웨어 필수 조건

USB 데이터 포트를 닫는 것은 전원 차단이 아니다. 포트별 전원 차단을 지원하는 USB
허브 또는 GPIO 제어 load switch/MOSFET이 필요하다. 실제 장치의 hub location/port를
확인하기 전에는 예시 명령을 사용하지 않는다. `PAYLOAD_POWER_ON_COMMAND`와
`PAYLOAD_POWER_OFF_COMMAND`가 없으면 서비스는 START/STOP을 실패 처리한다.

## 준비

1. `platforms/loonar/firmware/payload`를 PlatformIO로 빌드해 Payload Teensy에 업로드한다.
2. Pi에서 `/dev/serial/by-id/`의 Payload Teensy 경로를 확인한다.
3. `/etc/loonar/payload-pca.env`를 `payload-pca.env.example`에서 만들고 장치 경로와
   검증된 물리 전원 ON/OFF 명령을 설정한다.
4. 새 release를 빌드·설치한 뒤 다음 서비스만 수동으로 시작한다.

```bash
sudo systemctl start loonar-payload-pca.service
sudo systemctl start vehicle_gatewayd.service loonar-cfs.service
journalctl -u loonar-payload-pca.service -f
```

서비스 시작만으로 센서 전원은 켜지지 않는다. GCS에서 `PAYLOAD START`를 눌러야 한다.
종료할 때는 먼저 `PAYLOAD STOP`을 눌러 `IDLE,power_off` 이벤트를 확인한다.

로그는 `/var/lib/loonar/payload/payload-pca-*.csv`에 저장된다. 지상국에는 station별
자기장 중앙값, IR/RTD 온도, novelty, candidate 및 `DEMO_ONLY` 상태가 표시된다.
