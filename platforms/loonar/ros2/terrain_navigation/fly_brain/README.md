# LOONAR 실제 초파리 연결망 인터페이스

**실제 공개 전체 뇌 모델을 ROS 센서와 연결했다. `--drive`를 사용하면 지상국 없이
실제 바퀴를 구동한다. 최대 전진 0.2m/s, 가속 0.4m/s², 회전 0.4rad/s로 제한한다.
ToF·TF·IMU로 바닥을 추정해 지름 30% 이상 높이의 장애물을 먼저 피하고,
통과 가능한 방향 중 평탄한 surface를 따라간다. 사용자가 관찰하고 Ctrl+C로 종료한다.
`--drive`가 없으면 기존 관찰 모드다. 이 모델의 지형 주행 성능은 아직 검증되지 않았다.**

가짜 소형 신경망이나 규칙 기반 회피기를 초파리 뇌라고 부르지 않는다.
Eon 공개 저장소의 원본 Shiu Brian2 모델과 FlyWire 783 데이터를 실제로 읽는다.
138,639개 뉴런, 15,091,983개 뉴런 간 연결 행의 부호와 가중치를 유지한다.
이는 생물학적 초파리 전체를 그대로 재현한다는 뜻은 아니다. 단순화한 LIF 모델이며,
감각 변환과 로버 운동 해독은 아래에 명시한 별도 실험 어댑터다.

## 지상국 AUTO / STOP 실행

한 번 배포·빌드한 다음, Pi와 PC에서 각각 한 명령을 실행한다.

```bash
# PC: 변경 파일 복사 + Pi ROS 빌드 (처음/업데이트 때)
bash /home/sb/LOONAR/platforms/loonar/ros2/terrain_navigation/fly_brain/deploy_pi.sh 10.254.254.3

# Pi: 센서·MCU·cFS + AUTO 대기 (녹화 없음)
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh

# PC: 기존 지상국
bash /home/sb/LOONAR/GCS/scripts/start_loonar_gcs.sh 10.254.254.3
```

**AUTO**를 누르면 새 GNOME 터미널에서 `run_pc.sh --drive`가 실행된다.
Pi는 cFS의 AUTO 선택을 받아 ToF SDK/ROS 어댑터, TF, 지형 처리,
안전·정지 상태 감시를 시작한다. 유효한 heading을 받으면 주행 노드를 시작하고, 유효한 신경망 결과가
도착하면 주행한다. 로딩/컴파일 중에는 전진하지 않는다. 중복 AUTO는
터미널을 더 열거나 목표 heading을 초기화하지 않는다.

**STOP**은 먼저 로버에 STOP을 보내고 PC 신경망 컨테이너와 Pi 주행 노드를
종료한다. 수동주행 전환도 PC 신경망을 종료한다. 신경망 터미널 Ctrl+C/닫기는
GCS STOP으로 이어진다. STOP·수동·Payload 등 AUTO 이외 모드에서는
Pi의 ToF·TF·지형 처리·안전/정지 감시·주행 노드와 그 하위 프로세스를 종료한다.
모드 정보가 1초 넘게 끊겨도 종료한다. MCU 통신과 ROS base 상태·IMU 전달,
AUTO supervisor, 기존 영상 송출은 계속 실행한다. 객체인식은 지상국 PC의
영상 수신 창에서 실행하며, Pi 인식과 전용 BGR 변환은 기본으로 꺼진다.
종료 중 새 AUTO가 들어오면 이전 프로세스 종료 후 시작하며, 같은 AUTO 명령으로 중복 실행하지 않는다.
Pi 명령의 Ctrl+C로 이 지원 스택을 종료한다.
`start-ground-support.sh --video`도 인자 없는 실행과 동일한 AUTO 지원 스택을 시작한다.
기본 실행과 `--video`는 bag/원시 journal 녹화를 시작하지 않는다.
`--record`는 기존 bench의 발행 중인 ROS 토픽 기록,
`--record-all`은 기존 bench의 ToF·카메라 수집 및 전체 기록으로 유지한다.
`--encoder-verify`, `--record`, `--record-all` 등 별도 bench 옵션이나 `LOONAR_FLY_LEGACY_SUPPORT=1`은
기존 bench 경로를 사용하므로 AUTO 주행을 지원하지 않는다.
기존 별도 `recording/run_pi.sh --mode fly` 또는 수동 `fly_brain/run_pc.sh`는
이 모드와 동시에 실행하지 않는다. GCS 실행 전 Docker 모델 준비가 필요하다.

AUTO 시점의 `/imu/orientation_raw` yaw를 세션 목표로 저장한다. 아직 IMU가
도착하지 않았다면 첫 유효한 heading을 받았을 때 시작한다. 장애물 회피는
우선하고, 회피 종료 후 초기 방향으로 조향한다. 목표는 회피·중복 AUTO로
바뀌지 않고 STOP 후 새 AUTO에서만 다시 잡는다. 큰 방향 오차(60° 초과)는
제자리 회전으로 먼저 복구한다. 최대 전진 0.2 m/s, 회전 0.4 rad/s는 유지한다.
이 기준은 절대 방위/경로 계획이 아닌 시작 방향 유지이며 IMU drift는 누적된다.

AUTO와 전체 녹화를 함께 사용할 때는 Pi에서
`bash ~/LOONAR/platforms/loonar/ros2/terrain_navigation/recording/run_pi.sh --mode gcs`를 명시적으로 실행한다.
이 별도 녹화 실행기의 bag은 Pi `~/loonar-bags/capture_*`에 생성한다. 기존 입력·출력 외에도
`/loonar/fly/status`의 `heading`과 `/loonar/fly/lifecycle`의 시작 목표·실행 상태를
저장한다. 지상국은 기존 TCP **7443**을 사용한다.

검증: `bash fly_brain/test.sh unit`, `bash fly_brain/test.sh gcs`.
후자는 별도 ROS domain의 합성 센서로 실제 supervisor/driver 프로세스를
실행하며 물리 모터에 연결하지 않는다.

## 독립 실행 (지상국 없이)

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
유실돼도 주행 모드에서는 원래 센서 시각 기준 1.5초가 지난 뇌 출력은 차단하며, base_io에는 별도의 0.15초
명령 watchdog이 있다. 물리적 정지까지의 시간은 통신·제어·기계 응답에 영향을 받는다.

기존 지형 모니터의 경고는 계속 참고 정보다. 새 회피기는 장애물 앞에서 전진을 끊고 회전한다.
관측된 양쪽 회전 영역이 모두 막히면 대기하고, 열린 방향이 관측되면 다시 진행한다.
일시적 데이터 만료나 모터 fault가 해소되면 자동 재개한다. 짧은 입력 공백에는
0 속도를 보내되 AUTO를 반복 해제하지 않는다. 정상 응답을 보내는 새 PC worker도
수용한다. 명시적인 PC halt/Ctrl+C는 정지가 유지되므로 Pi 명령을 다시 실행한다.

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
Pi: ToF 전처리 + 바닥/장애물 분리 + 평탄도 + 카메라 → /loonar/fly/input
                                               ↓
PC: 독립 Poisson 자극 → 원본 전체 뇌 연결망 → 실제 DN 발화율
                                               ↓
Pi: /loonar/fly/result → 시간·드라이버 확인 → /loonar/fly/candidate_cmd_vel
                       └ --drive: 최신 지형 회피·제한·가속 → /cmd_vel → base_io → gateway → MCU
```

| 부분 | 구현 / 제한 |
|---|---|
| 원본 뇌 | upstream `create_model()` 직접 호출. 뉴런 방정식·연결·가중치·지연 보존 |
| ToF | 정지 3~5프레임 중앙값 → TF/IMU → 관측 바닥 추정 → 바닥을 제외한 장애물 근접도 LC4 0–100Hz. 평탄 방향 편향 최대 40Hz, 회피 방향 최소 120Hz |
| 카메라 | 96×64 영상 두 장의 방사 방향 optical flow를 LPLC2 좌우 집단의 0–100Hz 자극으로 변환 |
| 입력 자극 | upstream `poi()`와 같은 자극 크기와 자극 대상의 refractory 설정. 가변 Poisson 입력은 로버 어댑터 |
| 신체 피드백 | IMU 중력으로 수평 보정. 자이로·바퀴 피드백으로 정지 누적 가능 여부를 판단하며, 없으면 최신 프레임을 사용 |
| 운동 해독 | DNp09 평균과 DNa02 좌우 차이를 속도 후보로 표시. 신경이 조용하면 후보도 0 |
| 실험 이득 | 후보 최대 전진 0.2m/s, 회전 0.4rad/s. 주행 모드에서 가속 제한 후 모터에 전달. 신경-바퀴 이득은 실험 설정 |
| 회피/정지 | 가까운 실측 장애물은 회전. 바닥 미관측만으로 전진을 억제하지 않음. 양쪽 실제 회전 영역 막힘은 대기. Ctrl+C·데이터 만료·fault 경로 유지 |

시야 좌우와 뉴런 집단의 연결은 실험 가정이다. 원본 망막의 retinotopy나
초파리 다리 운동계의 이식이 아니다. ToF 근접도를 시각 자극으로 바꾸는 것도 인공적인 연결이다.
원본 모델은 스스로 먹이 탐색 목표를 세우거나 로버의 바퀴와 지형을 학습한 모델이 아니다.

기본 `--motivation-hz 0`은 DNp09 직접 자극을 하지 않는다.
`run_pc.sh --drive`는 `--motivation-hz 150`을 적용하여 전진 성향을 준다.
이는 원본 P9 자극 실험처럼 **외부에서 활성화한 상태**이지 자발적 동기 생성이 아니다.
전진 자극은 유효 지형이 있는 동안 유지한다. 장애물 제동은 Pi 모터 출력에서만 적용하며,
느린 뇌 계산으로 인해 전진 자극이 다시 살아날 때까지 기다리는 이중 억제를 제거했다.
이것으로 전진 후보가 나왔다고 자발적 주행이나 장애물 회피가 검증된 것은 아니다.

## 지연과 상태

뇌 시간은 실제 시간과 구분해서 출력한다. 기본 관찰 주기는 뇌 시간 10ms이며,
이 PC는 원본 모델을 생물학적 실시간 속도로 계산하지 못한다.
연속 Brian 실행 중 정확한 10ms 경계에서 감각률을 갱신해, 1,509만 연결의 실행 준비를
매 창마다 반복하지 않는다. 기존 한 번 실행과 모든 뉴런의 발화 수가 같은지 시험한다.
입력이 없으면 외부 자극을 0으로 내리고 신경 상태는 계속 진화한다. 새 입력 없이
이전 요청의 응답을 재발행하지 않는다. 새 PC 실행은 뇌를 초기 상태로 다시 시작한다.

요청은 Pi의 세션 ID와 순번을 사용한다. 응답 만료는 Pi에서 원래 센서 시각을 기준으로
주행 모드 1.5초(관찰 모드 0.75초) 안에 확인하므로 PC/Pi 시계 동기화에 의존하지 않는다.
주행 모드의 지형 관측 유효시간은 센서 시각 기준 1초다. 10월 9일 bag에서 측정한
지형 처리 지연 중앙값 0.36초, p90 0.50초를 반영했다. `/loonar/fly/status`의 수신·거부 횟수와 이유로 확인할 수 있다.
카메라가 없거나 오래되면 그 입력은 명시적으로 빠진다. 유효한 전처리 지형이 없으면 요청을 보내지 않는다. 주행 모드에서는 같은 센서에서
만든 유효 지형을 받은 뒤 원시 깊이 희소율·별도 깊이 콜백으로 다시 거부하지 않는다. 주행 입력은 `vision.source=surface_v1`이며,
원시 깊이의 좌우 근접값을 함께 자극하지 않는다. `encode_depth` 경로는 과거 데이터 재현용이다.

`candidate_cmd_vel`은 `TwistStamped` 관찰 토픽이다. `/cmd_vel`로 remap하지 않는다.
`--drive`에서만 전용 `drive_node`가 `/cmd_vel`을 발행하고 base_io의 `enable_motion`을 켠다.
기존 navigator와 motion primitive 노드는 꺼져 있어 명령 소유자가 겹치지 않는다.
Pi의 드라이버 연결/피드백·현재 fault·전처리 지형·원래 신경 요청의 TTL을 확인한다.
새 지형 노드는 깊이 시각 ±60ms 이내 중력 샘플과 실제 TF를 사용한다.
IMU/TF가 없어 지형을 갱신할 수 없으면 주행 출력도 갱신하지 않는다.
`/loonar/safety/emergency_stop`은 이 모드에서 지형 모니터의 참고 출력이다.
그 토픽의 근거리 판정이나 미수신으로 주행을 막지 않는다. Ctrl+C와 드라이버 fault 정지는 별도 경로다.
신경 출력의 방향·이득 보정, 실제 단차 통과 한계 및 여러 지형의 장거리 폐루프 검증은 남아 있다.
지금의 연결을 검증된 지형 자율주행으로 간주하지 않는다.

## 2026-10-09 주행 정지 수정

`capture_20261009_140206_482217`에서 모터 피드백 6,638건의 오류는 모두 0이었고,
비영 모터 목표는 없었다. 유효 지형 180개 중 139개가 기존 0.3초 제한을 넘었다.
같은 기록을 실제 콜백에 재입력했을 때 수용 프레임은 41/180에서 180/180으로 늘었다.
이는 입력 수용 검증이며 실제 이동거리나 새 신경망 추론 결과를 뜻하지 않는다.

약 46초 뒤 SDK `fatal error 3`도 발생했다. 번들 SDK enum에서 3은 `NoSuchDevice`다.
드라이버는 helper 종료/EOF, 3초 프레임 중단(최초 시작은 30초) 후 기존 프로세스를
정리하고 재시작한다. USB 장치가 실제로 사라져 있으면 재등장 전까지 회복할 수 없다.
연결 해제의 물리적 원인은 bag만으로 확정할 수 없다.

분석은 `analysis/20261009/`, ROS 명령 시험은 `log/drive-ros.json`에 있다.
Pi에 새 코드를 배포하려면 PC에서 아래 명령을 실행한 뒤 기존 PC/Pi 실행 명령을 사용한다.

```bash
bash /home/sb/LOONAR/platforms/loonar/ros2/terrain_navigation/fly_brain/deploy_pi.sh 10.254.254.3
```

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

## 회피 현재 동작 (2026-10-07 운동성 수정)

원본 뉴런·시냅스는 그대로다. 아래는 로버용 인공 감각/운동 어댑터다.
보상 학습은 없다. 전진은 신경 후보를 사용하며, 가까운 실측 장애물 앞의
회전 방향과 최소 회전 속도는 Pi에서 선택한다.

이전판은 바닥 미관측 시 탐색 회전, 부분 시야 0.04m/s, 낮은 단차 및
회전 동반 전진 0.05m/s 제한을 추가했다. 접근 시 DNp09 자극도 함께 줄여
이중으로 전진을 억제했다. 이 조건들은 제거했다.

- 평상시 최대 전진 0.2m/s. 낮은 단차·바닥 일부 미관측·신경 회전 출력만으로
  별도 저속 상한을 걸지 않는다. 신경 후보 자체가 작으면 실제 명령도 작다.
- 실측 벽/큰 단차는 차체 앞 여유 0.40m부터 모터 상한만 0.2→0.1m/s로 줄이고,
  약 0.22m(접근속도 반영 시 최대 0.24m)에서 전진을 끊고 회전한다.
  실측 낙차는 기존 0.45m 기준을 유지한다.
- 회전은 기본 0.3rad/s, 최종 상한 0.4rad/s. 평상시 신경 회전 이득은
  좌우 DNa02 차이 100Hz당 0.3rad/s다. 회전 때문에 전진을 0.05m/s로 제한하지 않는다.
- 최소 회전 유지 0.3초. 가까운 실측 장애물이 없어지거나 벽/단차 여유가
  0.30m 이상인 상태가 0.15초 유지되면 전진으로 돌아간다. 연속 바닥 관측을
  재전진의 필수조건으로 사용하지 않는다.
- 전진 가속 제한은 0.4m/s²: 후보가 0.2m/s이면 정지 상태에서 약 0.5초에 도달한다.
  제동·Ctrl+C는 가속 제한과 무관하게 즉시 0 명령을 보낸다.
- 7방향, TF/IMU 수평 보정, 5cm 격자, 최소 3점은 유지한다. 위쪽 장애물은 아래 비전 개편의
  지름 30% 기준으로 변경했다. 낙차의 기존 35mm+5mm 기준은 별도로 유지한다.
  빈 지면은 `unknown_ground`로 표시한다. 이것만으로 멈추지는 않으므로,
  **바닥이 전혀 관측되지 않는 구덩이의 회피를 보장하지 않는다.**
- 실제 점이 양쪽 회전 영역 모두에 들어오는 `no_turn_room`, 깊이·지형·뇌 결과
  만료, 모터 fault, Ctrl+C 정지는 유지한다. 이 조건의 실측 오판 여부는
  새로운 실차 로그가 있어야 판단할 수 있다. 기존 aggregate guard는 참고 정보다.

`/loonar/fly/status`의 `candidate`는 신경 속도 후보, `commanded`는 최종 명령,
`avoidance`는 회피 판단, `blocked_reason`은 데이터/fault 정지 사유다.
`candidate_cmd_vel`은 관찰 토픽이며 모터 명령으로 remap하지 않는다.

관련 소스는 `loonar_fly/avoidance.py`, `terrain_node.py`, `interface.py`,
`body_node.py`, `brain_node.py`, `drive_node.py`다. 공통 ROS Runtime에는
음수인 차체 자체 마스크 높이 좌표를 허용하는 수정만 추가했다.
펌웨어·지상국·cFS 변경은 없다. 재현 결과와 실기 범위는 `AVOIDANCE_VALIDATION.json`,
원시 데이터는 `log/terrain-ros.json`, `log/drive-ros.json`, `log/avoidance-hardware-latest.json`에 기록한다.


2026-10-06 이전판 실기 기록(현재판 성능 검증이 아님):

- 단위 시험 29개와 합성 지형 ROS·실제 주행 노드 ROS 시험 통과.
- Pi 실측 40초 동안 실제 뇌 응답 121개, 요청 137개(카메라 포함 135개) 수신.
- 최종 회피 자극 DNp09 좌우 0Hz, 회전 편향 LC4 120Hz 확인.
- 전진 명령 0, 좌회전 최대 0.5rad/s 및 양 바퀴 엔코더의 반대 방향 변화를 확인.
- 시험의 2초 구동 제한 후 양 바퀴 속도 0. 드라이버 fault `0x00000000`.
- 실제 회전 출력은 지형/신선도 조건에 따라 간헐적이었다. 연속 2초 회전이나
  벽을 완전히 우회하는 성능, 실제 구덩이 회피까지 검증한 것은 아니다.
- 시험 프로세스는 PC/Pi 모두 종료했다. 위의 각 한 명령으로 다시 시작하며,
  기본 최대 전진은 여전히 0.2m/s다.


2026-10-07 수정판: 단위 시험과 합성 ROS 주행/지형 시험 결과는
`MOBILITY_VALIDATION.json`에 기록한다. 이후 비전 수정판과 함께 Pi 배포를 완료했다.
이번 수정판의 실차 주행 시험은 아직 하지 않았다. `AVOIDANCE_VALIDATION.json`의
실기 수치는 이전판 기록이며 이번 수정판 검증으로 해석하지 않는다.


## 비전 전처리와 두 목표 (2026-10-07)

우선순위는 **큰 장애물 회피 → 통과 가능한 방향 중 평탄한 surface 선택**이다.
원본 전체 뇌 모델·펌웨어·GCS는 변경하지 않았다. 구현은 이 폴더의
`loonar_fly/vision.py`, `terrain_node.py`, `avoidance.py`, `body_node.py`, `interface.py`에 모았다.

### 깊이 정리와 바닥 기준

- 깊이와 같은 시각의 amplitude로 유효 픽셀을 선택한다.
- 깊이 시각과 ±60ms 안의 자이로·바퀴 피드백이 정지를 나타내면 최근 최대 0.4초의
  3~5프레임을 중앙값/MAD로 정리한다. 중력 방향·캘리브레이션 변경, 2mm 초과
  바퀴 위치 변화, 시간 역전/간격 초과는 누적을 초기화한다.
- 이동 중, 피드백 없음, 초기 1~2프레임은 최신 프레임을 바로 사용한다.
  누적을 위해 로버를 정지시키거나 5장을 기다리는 상태는 없다.
- 현재 없는 픽셀을 옛 프레임으로 채우지 않는다. 갑자기 가까워진 연속 픽셀 패치는
  새 장애물이 지연되지 않도록 현재 측정을 우선한다.
- TF·IMU로 수평 보정하고 자기 차체를 제거한 뒤, 공간별 점 밀도를 균등화해
  가까운 지면에 맞는 robust plane `z=ax+by+c`를 추정한다. 중력·예상 차축 높이로
  후보를 제한하며, 단차의 수직 면이 바닥을 위로 끌어올리지 않도록 좁은 잔차로 재추정한다.
- 충분한 바닥을 찾지 못하면 `floor.measured=false`, confidence 0을 출력하고
  보정 높이를 명시적 대체 기준으로 사용한다. 이런 영역을 평탄한 길로 점수화하지 않는다.
  단일 평면 기반 로컬 추정이므로 복잡한 굴곡·언덕 전체를 재구성하는 지도는 아니다.

### 첫 목표: 바퀴 지름 30% 이상 장애물

높이는 **추정한 주변 바닥에서 수직으로 솟은 높이**다.
`obstacle_threshold_m = 2 × wheel_radius × obstacle_diameter_fraction`이며,
새 Pi 비전 노드의 `obstacle_diameter_fraction` 기본값은 0.30이다.
현재 보정 반지름 98mm에서는 **58.8mm**, 반지름 100mm에서는 **60mm**다.
기존 공통 `max_step_up=35mm`는 이 fly 비전 경로의 위쪽 장애물 기준에 사용하지 않는다.
위쪽 판정에 별도 5mm 여유를 더하지 않으며, 경계값 이상인 점 3개가 격자를 지지하면 장애물이다.
실측 노이즈·가려짐 때문에 실제 높이의 정확한 경계 판정까지 보장하는 것은 아니다.

그보다 낮은 물체는 높이만으로 강제 회피하지 않는다. 표면이 거칠면 두 번째 목표의
방향 선호에 영향을 줄 수 있다. 낮게 관측된 지면은 별도 낙차로, 미관측은 unknown으로 구분한다.

### 두 번째 목표: 평탄한 방향

7방향의 차체 통과 폭에서 종방향 경사, 횡경사, 평면 잔차(거칠기), 양 바퀴 지면 연속성을 계산한다.
관측 범위 안에 장애물이 있는 방향을 먼저 제외하고, 충분히 관측된 나머지 방향의 평탄도를 비교한다.
비슷하면 직진을 유지한다. 차이가 확실하면 `follow_surface`로 부드럽게 조향한다.
선호 방향에는 0.35초 유지 조건이 있으나, 그 방향에 장애물이 나타나면 즉시 재선택한다.
가까운 전방 장애물의 회피 회전이 평탄도 선호보다 우선한다.

평탄도 때문에 별도의 전진 저속 상한을 추가하지 않는다. 최대 전진 **0.2m/s**,
최대 회전 0.4rad/s는 그대로다. `follow_surface`의 방향 보정은 최대 ±0.2rad/s에
신경 회전 후보의 20%를 합한다. 장애물 접근 제동과 가까운 장애물 회전은 유지한다.

### 뇌에 보내는 입력과 확인

`/loonar/fly/input`의 `vision`에는 지면을 제외한 좌우 장애물 근접도, 선호 방향,
바닥 추정 신뢰도가 들어간다. 진단용 7방향 수치와 카메라 확장 특징도 함께 기록한다.
원시 깊이 프레임이나 가까운 바닥의 거리값은 이 경로에서 LC4 자극으로 전달하지 않는다.
바닥 제거와 방향 선호를 초파리 뇌가 스스로 학습했다는 의미는 아니다.

`/loonar/fly/terrain`의 `floor`, `temporal`, `obstacle_threshold_m`, `preferred_heading_rad`,
`directions[*].{slope_rad,cross_slope_rad,roughness_m,surface_confidence}`로 판단 근거를 확인한다.
검증은 `VISION_VALIDATION.json`과 `log/`에 기록한다. Pi 10.254.254.3에 최신 코드를
복사했고 PC/Pi 소스·실행 스크립트 20개 해시 일치, 의존성 및 지형 노드 초기화를 확인했다.
Pi에서도 합성 ROS 지형 9개 장면 시험을 통과했다. 기존 두 실행 명령을 사용한다.
새 비전 코드의 실제 바닥 주행 검증은 아직 하지 않았다.


비전 개편 검증 완료:

- 단위 시험 55개 통과. 지름 200mm에서 59mm/60mm/61mm 경계와 경사 바닥 대비 높이 판정을 확인했다.
- 합성 ROS 깊이·amplitude·TF·IMU·바퀴 입력으로 정지 누적, 이동 중 최신 프레임,
  평면/벽/단차/낙차/미관측 분류를 확인했다.
- 실제 주행 노드 시험에서 평탄 방향 조향 중 0.2m/s 후보 유지와 장애물 우선 회피를 확인했다.
- 실제 전체 뇌의 응답 82개를 수신했고, 가까운 바닥 영상이 장애물 LC4 자극에 섞이지 않는 것을 확인했다.
- 위 결과는 PC 합성 시험이다. 배포 후 Pi에서도 합성 지형 시험을 통과했다
  (`log/pi-deployment-terrain-ros.json`, 각 장면 마지막 처리 약 15~35ms).
  실제 바닥 주행은 시작하지 않았으며, 실차 회피 성능은 아직 검증하지 않았다.
