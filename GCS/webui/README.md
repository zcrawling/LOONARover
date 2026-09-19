# LOONAR 웹 지상국

기존 backend/cli/mock/config 파일을 수정하지 않고 추가한 로컬 웹 UI입니다. OpenC3 COSMOS의 명령·상태·로그 중심 구성을 참고한 LOONAR 전용 화면이며 COSMOS 제품 자체가 아닙니다.

## 한 번에 실행

Ubuntu 터미널 하나에서 다음을 실행하세요.

```bash
cd $HOME/LOONAR/LOONARover/GCS
python3 -B -m webui.server
```

Firefox에서 **http://127.0.0.1:8080** 을 여세요. TCP CONNECTED가 되면 명령 버튼을 사용할 수 있습니다. PAYLOAD를 누르면 Received와 측정값을 확인하고, STOP을 누르면 Mock의 Aborted/Completed 응답을 볼 수 있습니다.

런처가 필요한 Mock Rover와 백엔드를 시작합니다. 이미 백엔드가 실행 중이면 재사용합니다. 종료는 터미널에서 Ctrl+C이며, 런처가 새로 시작한 프로세스만 종료합니다. 기존에 따로 실행한 프로그램은 그대로 둡니다. 기존 백엔드가 다른 설정으로 실행 중이면 그 백엔드 설정이 적용됩니다.

포트가 사용 중이면 `python3 -B -m webui.server --port 8081`로 시작하고 표시된 주소를 여세요. UI만 실행하려면 `--attach`를 사용합니다. 중앙 설정 파일은 기존 `config/gcs.toml`이며 별도 설정은 `--config`로 지정합니다. 서비스 로그는 `webui/runtime/services.log`에 저장됩니다.

## 기능과 범위

- 명령 버튼: STOP / MANUAL / AUTO / PAYLOAD / REACTION
- 백엔드가 보고한 모드, 연결 상태, 수신 경과, 메시지 수, 누락 구간
- 배터리, 라즈베리파이 내부 온도, 장치 상태와 PAYLOAD 세 센서값
- 명령 응답·통신 로그와 필터
- 연결 불가 시 명령 비활성화 및 오래된 데이터 표시

HTTP 서버는 127.0.0.1에만 열립니다. 명령 요청은 동일 출처와 세션 토큰을 검증합니다. 기존 Unix 소켓 API를 사용하며 로버에 두 번째 TCP 연결을 만들지 않습니다.

실제 로버 연동은 기존 프로토타입과 동일하게 아직 미지원입니다. 모든 값과 결과는 MOCK입니다. 영상은 별도 GStreamer 창을 사용하며, 현재 웹 화면에 가짜 영상을 표시하거나 원격 영상 제어를 지원한다고 표시하지 않습니다. 조이스틱, ROS 화면 통합, 그래프와 과거 데이터 복구는 후속 범위입니다.

기존 소스코드의 동작과 테스트를 변경하지 않습니다. 이 런처 실행 중 백엔드가 사용하는 `.runtime` 소켓·잠금 파일은 정상적으로 생성됩니다.
