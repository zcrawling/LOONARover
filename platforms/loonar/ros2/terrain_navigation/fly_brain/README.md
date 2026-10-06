# LOONAR 실제 초파리 연결망 인터페이스

**실제 공개 전체 뇌 모델을 ROS 센서와 연결했다. `--drive`를 사용하면 지상국 없이
실제 바퀴를 구동한다. 최대 전진 0.2m/s, 가속 0.1m/s², 회전 0.6rad/s로 제한한다.
ToF·TF·IMU로 감속→회전→재전진하며, 사용자가 관찰하고 Ctrl+C로 종료한다.
`--drive`가 없으면 기존 관찰 모드다. 이 모델의 지형 주행 성능은 아직 검증되지 않았다.**

가짜 소형 신경망이나 규칙 기반 회피기를 초파리 뇌라고 부르지 않는다.
Eon 공개 저장소의 원본 Shiu Brian2 모델과 FlyWire 783 데이터를 실제로 읽는다.
138,639개 뉴런, 15,091,983개 뉴런 간 연결 행의 부호와 가중치를 유지한다.
이는 생물학적 초파리 전체를 그대로 재현한다는 뜻은 아니다. 단순화한 LIF 모델이며,
감각 변환과 로버 운동 해독은 아래에 명시한 별도 실험 어댑터다.

## 실행

이 PC에는 모델 다운로드와 Docker 이미지 생성이 완료되어 있다.
Pi에는 작은 ROS 인터페이스만 복사하며 뇌 계산은 PC에서 한다.
기존 `run_auto.sh`와 동시에 실행하지 않는다.

PC 한 명령:

```bash
bash /home/sb/LOONAR/platforms/loonar/ros2/terrain_navigation/fly_brain/run_pc.sh --drive
```

Pi 한 명령:

```bash
bash ~/LOONAR/platforms/loonar/ros2/terrain_navigation/fly_brain/run_pi.sh --drive
```

Pi 주행 명령은 기존 gateway/backend, ToF, IMU, TF, 안전 노드와 카메라를 시작한다.
cFS와 지상국은 띄우지 않는다. 주행 노드가 로컬 mode socket을 소유하여 AUTO를 선택한다.
보정된 지형·센서와 신경 출력이 수신되면 회전 또는 전진한다. 기존 0.5초 대기 조건은 제거했다.
전방 여유 34mm 같은 지형 모니터 판정은 `terrain_advisory` 정보로만 표시한다.
카메라의 기존 스트리밍 파이프라인에서 JPEG 5fps를 함께 받는다.
지상국 영상도 필요하면 `--video-ip 10.254.254.2`를 추가한다. 기본은 ROS 영상만 받으며,
카메라가 없으면 `--no-camera`를 사용한다.
Pi의 ROS_DOMAIN_ID와 PC의 값이 같아야 한다. 현재 양쪽 모두 `0`이다.

PC 터미널에 `READY: 138639 neurons, 15091983 connections`가 뜨면 준비됐다.
이후 약 2초마다 DNa02/DNp09의 좌우 발화율, 계산 시간, 카메라 수신 여부를 표시한다.
첫 실행은 데이터 로딩과 Cython 컴파일 때문에 시간이 걸린다.
**정지는 Pi 터미널에서 Ctrl+C.** 백엔드가 MCU STOP을 보내고 종료한다.
주행 노드 자체에 들어오는 SIGINT/SIGTERM/SIGHUP도 gateway STOP과 0 속도를 전송한다.
PC Ctrl+C는 별도 halt 메시지를 보내 Pi를 정지시킨다. PC 강제 종료나 통신 단절로 이 메시지가
유실돼도 원래 센서 시각 기준 0.75초가 지난 뇌 출력은 차단하며, base_io에는 별도의 0.15초
명령 watchdog이 있다. 물리적 정지까지의 시간은 통신·제어·기계 응답에 영향을 받는다.

기존 지형 모니터의 경고는 계속 참고 정보다. 새 회피기는 장애물 앞에서 전진을 끊고 회전한다.
관측된 양쪽 회전 영역이 모두 막히면 대기하고, 열린 방향이 관측되면 다시 진행한다.
일시적 데이터 만료가 해소되면 재개한다. 주행 중 모터 fault,
PC halt, PC 뇌 프로세스 교체는 정지가 유지되므로 원인 해결 후 Pi 명령을 다시 실행한다.

더 낮은 속도로 시험하려면 Pi에 `--max-speed 0.03`을 추가한다.
`--drive-seconds 2`는 처음 비영(非零) 신경 주행 요청부터 2초 후 정지를 유지한다.
최대 속도 인자는 0 초과 0.2m/s 이하만 허용한다. `--drive` 없는 관찰 모드는 모터를 구동하지 않는다.

새 PC의 최초 준비와 Pi 복사는 다음을 한 번 실행한다. Docker와 git이 필요하다.
Pi 배포는 기존 ROS/CAD 빌드를 재사용하며 기존 SSH 인증 방법을 사용한다.

```bash
bash platforms/loonar/ros2/terrain_navigation/fly_brain/setup_pc.sh
bash platforms/loonar/ros2/terrain_navigation/fly_brain/deploy_pi.sh 10.254.254.3
```

`deploy_pi.sh`의 기존 배포기는 실행 중인 terrain launch를 덮어쓰지 않는다.
먼저 Pi의 현재 실행을 종료한다. 모델 데이터·PC 가상환경·캐시는 Pi에 복사하지 않는다.
배포기는 기존 LOONAR 카메라 런타임(`/opt/loonar/current/lib/loonar-camera-env.sh`)과
`common/video/camera_ros.py`가 설치된 Pi를 전제로 한다.

## 입력과 출력의 정확한 의미

```text
Pi: ToF + TF + IMU + 연속 카메라 → 지형·시각 특징 → /loonar/fly/input
                                               ↓
PC: 독립 Poisson 자극 → 원본 전체 뇌 연결망 → 실제 DN 발화율
                                               ↓
Pi: /loonar/fly/result → 시간·드라이버 확인 → /loonar/fly/candidate_cmd_vel
                       └ --drive: 최신 지형 회피·제한·가속 → /cmd_vel → base_io → gateway → MCU
```

| 부분 | 구현 / 제한 |
|---|---|
| 원본 뇌 | upstream `create_model()` 직접 호출. 뉴런 방정식·연결·가중치·지연 보존 |
| ToF | 좌우 근접도 LC4 0–100Hz + TF/IMU 보정 후 7방향 차체 폭 통로. 회피 방향 LC4 최소 120Hz 편향 |
| 카메라 | 96×64 영상 두 장의 방사 방향 optical flow를 LPLC2 좌우 집단의 0–100Hz 자극으로 변환 |
| 입력 자극 | upstream `poi()`와 같은 자극 크기와 자극 대상의 refractory 설정. 가변 Poisson 입력은 로버 어댑터 |
| 신체 피드백 | IMU 중력으로 ToF 점군 수평 보정. 자이로·바퀴 속도는 상태 문맥으로 전송 |
| 운동 해독 | DNp09 평균과 DNa02 좌우 차이를 속도 후보로 표시. 신경이 조용하면 후보도 0 |
| 실험 이득 | 후보 최대 전진 0.2m/s, 회전 0.6rad/s. 주행 모드에서 가속 제한 후 모터에 전달. 신경-바퀴 이득은 실험 설정 |
| 회피/정지 | 가까운 장애물은 회전, 바닥 미관측은 탐색 회전. 양쪽 실제 회전 영역 막힘은 대기. Ctrl+C·데이터 만료·fault 경로 유지 |

시야 좌우와 뉴런 집단의 연결은 실험 가정이다. 원본 망막의 retinotopy나
초파리 다리 운동계의 이식이 아니다. ToF 근접도를 시각 자극으로 바꾸는 것도 인공적인 연결이다.
원본 모델은 스스로 먹이 탐색 목표를 세우거나 로버의 바퀴와 지형을 학습한 모델이 아니다.

기본 `--motivation-hz 0`은 DNp09 직접 자극을 하지 않는다.
`run_pc.sh --drive`는 `--motivation-hz 150`을 적용하여 전진 성향을 준다.
이는 원본 P9 자극 실험처럼 **외부에서 활성화한 상태**이지 자발적 동기 생성이 아니다.
새 회피기는 접근 위험에 따라 이 자극을 줄이며 회전 중에는 0Hz로 내린다.
이것으로 전진 후보가 나왔다고 자발적 주행이나 장애물 회피가 검증된 것은 아니다.

## 지연과 상태

뇌 시간은 실제 시간과 구분해서 출력한다. 기본 관찰 주기는 뇌 시간 10ms이며,
이 PC는 원본 모델을 생물학적 실시간 속도로 계산하지 못한다.
연속 Brian 실행 중 정확한 10ms 경계에서 감각률을 갱신해, 1,509만 연결의 실행 준비를
매 창마다 반복하지 않는다. 기존 한 번 실행과 모든 뉴런의 발화 수가 같은지 시험한다.
입력이 없으면 외부 자극을 0으로 내리고 신경 상태는 계속 진화한다. 새 입력 없이
이전 요청의 응답을 재발행하지 않는다. 새 PC 실행은 뇌를 초기 상태로 다시 시작한다.

요청은 Pi의 세션 ID와 순번을 사용한다. 응답 만료는 Pi에서 원래 센서 시각을 기준으로
0.75초 안에 확인하므로 PC/Pi 시계 동기화에 의존하지 않는다. 오래된 응답을 살리기 위해
이 제한을 늘리지 않는다. `/loonar/fly/status`의 수신·거부 횟수와 이유로 확인할 수 있다.
카메라가 없거나 오래되면 그 입력은 명시적으로 빠진다. 깊이가 불량하면 요청을 보내지 않는다.

`candidate_cmd_vel`은 `TwistStamped` 관찰 토픽이다. `/cmd_vel`로 remap하지 않는다.
`--drive`에서만 전용 `drive_node`가 `/cmd_vel`을 발행하고 base_io의 `enable_motion`을 켠다.
기존 navigator와 motion primitive 노드는 꺼져 있어 명령 소유자가 겹치지 않는다.
Pi의 드라이버 연결/피드백·fault·깊이 데이터·원래 신경 요청의 TTL을 확인한다.
새 지형 노드는 깊이 시각 ±60ms 이내 중력 샘플과 실제 TF를 사용한다.
IMU/TF가 없어 지형을 갱신할 수 없으면 주행 출력도 갱신하지 않는다.
`/loonar/safety/emergency_stop`은 이 모드에서 지형 모니터의 참고 출력이다.
그 토픽의 근거리 판정이나 미수신으로 주행을 막지 않는다. Ctrl+C와 드라이버 fault 정지는 별도 경로다.
신경 출력의 방향·이득 보정, 실제 단차 통과 한계 및 여러 지형의 장거리 폐루프 검증은 남아 있다.
지금의 연결을 검증된 지형 자율주행으로 간주하지 않는다.

## 확인 / 시험

실행 중인 PC 컨테이너에서 읽기 전용 30초 관찰:

```bash
docker exec loonar-fly-brain bash -c 'source /opt/ros/jazzy/setup.bash; /opt/fly-env/bin/python -m loonar_fly.observe --seconds 30 --output /fly/log/observation.json'
```

현재 폴더에서:

```bash
bash test.sh unit
bash test.sh parity
bash test.sh ros
bash test.sh drive
bash test.sh terrain
```

`parity`는 실제 전체 연결망을 로드하며, `ros`는 빌드된 상위 ROS workspace가 필요하다.
자원을 많이 쓰므로 PC의 `run_pc.sh`를 종료한 뒤 실행한다. ROS 시험은 별도 domain 219의
합성 센서와 실제 전체 뇌를 사용하며 실차 센서·모터와 통신하지 않는다.
전체 자극/연결 차단 비교는 컨테이너에서 `python -m loonar_fly.benchmark`로 재현한다.
검증 요약은 `VALIDATION.json`, 원시 기록은 이 폴더의 `log/`에 있다.

2026-10-06 관찰 모드 검증 결과(주행 모드 추가 전):

- 입력·영상·만료 보호 단위 시험 10개 통과.
- 연속 실행과 200ms 단일 실행 사이 모든 138,639개 뉴런의 발화 수가 동일.
- 같은 왼쪽 시각 입력에서 DNa02 오른쪽은 20Hz, 연결 전달을 차단한 대조군은 0Hz.
- 합성 ROS + 실제 뇌 시험에서 fault·비상정지·오래된 깊이의 후보 출력 0 확인.
- Pi 실센서 30초: 뇌 출력 135개, 계산 중앙값 198.9ms/뇌 시간 10ms,
  최대 283.4ms. 카메라가 포함된 입력 238개. `/cmd_vel` 발행자 0개.
- 최종 MCU 읽기에서 모터 명령/속도는 양쪽 0, 드라이버 상태는 `0x00000000`.
  안전 노드는 전방 여유 약 33–35mm, 요구 여유 70mm로 정지 상태였다.
- 시험용 PC/Pi 프로세스는 검증 후 종료했다. 위의 각각 한 명령으로 재시작한다.

## 원본과 파일 보존

- [Eon 원본](https://github.com/eonsystemspbc/fly-brain), commit `a3db62f9436074e485c0278290c2164ed6150808`
- [Shiu 원본 모델](https://github.com/philshiu/Drosophila_brain_model)
- [FlyWire annotations](https://github.com/flyconnectome/flywire_annotations), commit `a83b2776d60d5764cef36b927f5f9679c16c47a2`

정확한 SHA256은 `provenance.json`에 있고 시작 시 원본 코드와 데이터를 검증한다.
업스트림 checkout은 수정하지 않는다. 원본 저장소는 기본 GPL-2.0-or-later,
사용하는 `code/paper-phil-drosophila/`의 별도 원본 모델은 MIT 표기를 유지한다.
라이선스·저작권·데이터 출처는 `vendor/fly-brain`의 원본 파일에 보존되어 있다.
`vendor/`, `cache/`, `log/`, PC 전용 `.venv/`는 생성물이며 Git에서 제외한다.
펌웨어·GCS·cFS는 이 작업으로 변경하지 않았다.

주행 모드 추가 검증은 `DRIVE_VALIDATION.json`과 `log/drive-ros.json`에 기록한다.
`test.sh drive`는 합성 센서와 실제 주행 프로세스·로컬 모드 프로토콜을 사용하여
0.2m/s 상한, 가속, 근거리 판정 및 모니터 미수신 시 계속 주행, 통신 만료 정지,
Ctrl+C STOP, fault와 PC halt 정지 유지를 검사한다.

지형 강제 정지를 제거하기 전 실기 확인에서는 45초 동안 실제 뇌 출력 317개와 `/cmd_vel` 발행자 1개를 확인했다.
당시 시험은 별도로 0.03m/s·2초로 제한했으며, 당시 전방 여유 약 34mm 안전 판정 때문에
모터 명령은 0이었다. 실제 이동은 확인하지 못했다. PC 종료가 Pi의 정지 유지로
전달되는 것도 확인했다. 시험 프로세스는 종료했고 재실행 시 기본 상한은 0.2m/s다.
이후 사용자의 지시에 따라 지형 강제 정지를 제거했다. 변경 후에는 합성 ROS 시험으로
근거리 경고 자체가 0.2m/s 명령을 막지 않는 것을 합성 시험으로 확인했다.
아래 회피 추가 검증은 이 과거 기록과 구분한다.

## 회피 1–3 구현 (2026-10-06)

원본 뉴런·시냅스는 그대로다. 아래는 **로버용 인공 감각/운동 어댑터**이며,
초파리 뇌가 새 행동을 학습했다는 의미가 아니다. 전진 후보는 실제 신경 발화에서 나오지만,
대칭인 벽 앞에서 확실히 방향을 선택하는 회전은 Pi의 명시적인 반사 동작이다.

1. **접근 감속·강한 회전**: 차체 앞면 기준 장애물 여유 0.55m부터 전진 자극과
   속도 상한을 줄인다. 기본 0.22m 또는 접근 속도로 계산한 1.2초 거리 안이면
   전진 0, 회전 0.5rad/s를 요청한다. 신경 회전 출력이 더 크면 최대 0.6rad/s까지 쓴다.
   운동 발화율 평활화는 느린 뇌 시간이 아닌 실제 시간 0.12초 기준이다.
2. **7방향·방향 유지**: -45°~+45°를 15° 간격으로 보고 차체 폭과 양쪽 바퀴의
   지면 지지를 확인한다. 열린 쪽으로 회전하고, 동률이면 오른쪽을 선택한다.
   최소 0.6초 유지하며 정면이 0.3초 연속 열리면 전진을 재개한다.
   돌아가는 쪽의 실제 회전 영역이 막히고 반대가 열리면 방향을 바꾼다.
3. **벽·단차·구덩이 분리**: CameraInfo와 CAD TF로 깊이를 3D 변환하고 중력으로
   수평 보정한다. 바닥 기준은 보정된 바퀴 반지름(현재 98mm)이다.
   5cm 격자의 최소 3개 점으로 지형을 판단하고 단일 높은 이상치는 무시한다.
   설정 `max_step_up/down=35mm`에 측정 여유 5mm를 더한 높이 차를 회피 대상으로 삼는다.
   15mm 초과 낮은 단차 후보는 최대 0.05m/s로 통과를 시도한다.
   낮게 **실측된 표면**은 낙차 후보이며 0.45m 이내에서 회피한다.
   단순 픽셀 누락은 구덩이로 확정하지 않는다. 바닥 지지 관측이 0.25m 미만이면
   0.35rad/s로 회전해 다시 보고, 부분 관측은 최대 0.04m/s로 접근한다.

회전 충돌 검사는 관측된 점으로 다음 0.2rad 범위를 갱신하며, 센서에 보이지 않는
후방까지 확인하는 기능은 없다. 수평 ToF의 바로 아래 사각지대, 구덩이 바닥이 전혀
보이지 않는 경우, 경사면과 높은 평면의 구별에는 한계가 있다. 바퀴 지름만으로 실제
단차 통과 한계를 확정하지 않는다. 모터 정지를 반복시키던 기존 aggregate guard는 복원하지 않았다.

실측에서 발견한 부분 시야 문제도 수정했다. 한쪽 깊이 유효 비율이 25%보다 낮아도,
새 보정 지형이 유효하면 보이는 장애물에서 벗어나는 회전 입력을 계속 보낸다.
두 시야 모두 사실상 비어 있거나 깊이/지형이 오래되면 출력하지 않는다.

`/loonar/fly/terrain`은 7방향 지형, `/loonar/fly/status`의 `avoidance`는 행동 이유,
`candidate`는 신경 속도 후보, `commanded`는 최종 `/cmd_vel`이다.
`candidate_cmd_vel`에는 회피 후 모터 명령이 담기지 않는다.

관련 소스는 `loonar_fly/avoidance.py`, `terrain_node.py`, `interface.py`,
`body_node.py`, `brain_node.py`, `drive_node.py`다. 공통 ROS Runtime에는
음수인 차체 자체 마스크 높이 좌표를 허용하는 수정만 추가했다.
펌웨어·지상국·cFS 변경은 없다. 재현 결과와 실기 범위는 `AVOIDANCE_VALIDATION.json`,
원시 데이터는 `log/terrain-ros.json`, `log/drive-ros.json`, `log/avoidance-hardware-latest.json`에 기록한다.


회피 추가 후 확인 결과:

- 단위 시험 29개와 합성 지형 ROS·실제 주행 노드 ROS 시험 통과.
- Pi 실측 40초 동안 실제 뇌 응답 121개, 요청 137개(카메라 포함 135개) 수신.
- 최종 회피 자극 DNp09 좌우 0Hz, 회전 편향 LC4 120Hz 확인.
- 전진 명령 0, 좌회전 최대 0.5rad/s 및 양 바퀴 엔코더의 반대 방향 변화를 확인.
- 시험의 2초 구동 제한 후 양 바퀴 속도 0. 드라이버 fault `0x00000000`.
- 실제 회전 출력은 지형/신선도 조건에 따라 간헐적이었다. 연속 2초 회전이나
  벽을 완전히 우회하는 성능, 실제 구덩이 회피까지 검증한 것은 아니다.
- 시험 프로세스는 PC/Pi 모두 종료했다. 위의 각 한 명령으로 다시 시작하며,
  기본 최대 전진은 여전히 0.2m/s다.
