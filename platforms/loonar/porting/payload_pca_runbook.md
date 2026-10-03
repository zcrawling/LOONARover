# Payload PCA 수동 정차 지점 시험

Payload Teensy와 센서는 임무 내내 켜 둔다. 지상국 `PAYLOAD START`는 Pi에서
USB CDC 포트를 열고 MCU에 `START` 명령을 보내 센서 재초기화와 새 지점
계측을 시작한다. `PAYLOAD STOP`은 MCU에 `STOP` 명령을 보내며, MCU는
시작 후 최소 5초가 지난 다음 그 지점의 PCA 한 행을 출력한다. Pi는 PCA와
완료 응답을 받은 뒤 로그 파일과 USB 포트를 닫는다. 센서 전원은 끄지 않는다.

첫 번째 완료 구간은 `STATION01`이고, 다음 START/STOP 구간은 `STATION02`다.
MCU를 재부팅하면 지점 번호는 다시 1부터 시작한다. 각 구간의 원시 센서
행과 PCA 행은 Pi의 별도 `payload-pca-*.csv`에 저장된다. 지상국에는
지점별 자기장 중앙값, IR/RTD 온도, novelty, candidate 및 모델 상태가 표시된다.
현재 `model_params.h`는 **DEMO_ONLY**이며 과학적 이상 판정용 모델이 아니다.

## 명령 계약

GroundLink `PAYLOAD_CMD` opcode는 `1=START`, `2=STOP`이다. Pi와 MCU
사이의 USB CDC 명령은 ASCII `START\n`과 `STOP\n`이다. MCU는
`CTRL,START,<station_id>`로 시작을 확인하고, PCA 행 뒤에
`CTRL,STOP,<station_id>`로 완료를 확인한다. STOP을 5초 전에 눌러도 MCU는
5초가 채워질 때까지 측정하며, Pi는 PCA 완료 응답을 기다린다. PCA 요약은
기존 EVENT 텔레메트리로 지상국에 전달된다.

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
