# main/master 병합과 로컬 작업물 반영 기록

기준일: 2026-09-18. 저장소: `zcrawling/LOONARover`.

## 이력과 충돌

- 기존 main: `1f9a156b9aad4f63cab93c9661ceacf2a59e3bbc`
- 기존 master: `5049941d250a8e21c63c555e8ab2fb4ac5affc24` (`payload code add`)
- 병합 commit: `2bea6db` (첫 부모 main, 두 번째 부모 master)

두 브랜치는 공통 조상이 없는 별도 root였다. 전체 파일 내용은 같았고 다음 파일의
실행 권한만 master에서 `100755 → 100644`로 바뀌어 add/add 충돌이 발생했다.

- `common/video/loonar-video-stream`
- `common/video/tests/test_video_stream.sh`
- `platforms/limo/scripts/live_gateway_test.sh`
- `platforms/limo/scripts/run_odom_motion_test.sh`
- `platforms/limo/scripts/start_dabai_tof.sh`

main의 실행 권한을 유지해 충돌을 해결했다. merge commit의 tree는 기존 main과 같으며,
이력은 rebase/squash/강제 덮어쓰기 없이 연결했다. 기존 로컬 변경은 별도 worktree에서
병합을 검증한 후 원래 main에 fast-forward하여 보존했다.
원격 반영은 main이 기존 두 tip을 모두 포함하는지 확인한 뒤 main 갱신과 master 삭제를
atomic push로 수행한다. master 삭제에는 검토한 tip의 lease를 지정해 동시 변경을 보호한다.
`sci_payload`는 이번 삭제 대상이 아니다.

## 함께 반영하는 로컬 작업물

- 실제 cFS/Gateway 실행·지상국/시험 영상 통합 테스트 도구
- 실험 localization, primitive, C_accel, ToF 및 odom 분석 코드
- AprilTag 추적/보고서/회귀 시험과 실행 스크립트
- RBPHAT B4 편집 원본, 제조 자료와 검증 결과, I200DK 시험 이미지
- odom 설계 문서와 수정된 [포팅 계획](../platforms/loonar/porting/limo_to_loonar_plan.md)

공급사 CubeEye archive(129.4 MiB)는 로컬에 남기고
[별도 배치 및 checksum 문서](../platforms/loonar/vendor-assets.md)를 추가한다.
중복 최상위 PCB zip, 편집기 `.history`/lock/local 설정, `odom.save`는 로컬에 보존한다.
공급사 PDF와 archive는 Git binary 속성을, CAD 교환 파일은 원본 형식 보존 속성을 사용한다.

## Payload 코드 확인 결과

원격 master의 commit 제목과 달리 신규 payload 소스 차이는 없다. 이 컴퓨터의 작업
트리에도 cFS 앱은 GroundLink/VehicleAdapter 두 개뿐이다. PAYLOAD 명령의 STOP/mode
선택과 EXEC MID 발행은 있지만 실제 UART transport/subscriber 및 MCU 완료 결과는 없다.
이 상태를 포팅 계획의 PL0~PL4와 TP1~TP4에 명시했다. 추후 별도 구현을 확보하면
해당 소스·mission 등록·실기 log를 근거로 완료 상태를 갱신해야 한다.

## 검증

| 항목 | 결과 |
| --- | --- |
| 깨끗한 병합 worktree CMake build/CTest | 15/15 PASS |
| 공통 localization unit tests | 20/20 PASS |
| odom V1/V2/C 분석 tests | 3 + 3 + 4 PASS |
| AprilTag tests | 18 PASS, 격리 ROS container 필요 1 SKIP |
| 실제 cFS/Gateway smoke | mode/sequence/synthetic 상태/UDP MPEG-TS/종료 정리 PASS |
| 변경 Python/shell | Python 87개 AST, shell 10개 문법 확인 |
| 포팅 문서 | 로컬 링크와 shell 예제 문법 확인 |

AprilTag 검증 중 `rosbags`, `matplotlib` 의존성이 누락되어 requirements에 추가했고,
0개 테스트를 탐색하던 README 명령을 실제 `tests/` 경로로 수정했다.
검증은 개발 PC에서 수행했다. Pi ARM64 실행, 실제 payload MCU, 카메라 및 주행은
이 결과에 포함되지 않는다.
