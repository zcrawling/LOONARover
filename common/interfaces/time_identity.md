# 시각과 식별자

현재 패킷의 형식과 단위는 각 wire 명세를 따른다.


| 경로 | 식별·시각 |
| --- | --- |
| [GroundLink](../../docs/ground_link_protocol.md) | 프레임 sequence, discrete request_id |
| [Control LNR2](../../platforms/loonar/porting/mcu_wire_v2.md) | UID, boot counter, session nonce, request/sample sequence, MCU µs |
| [Payload ASCII](../../platforms/loonar/porting/payload_pca_runbook.md) | station_id; MCU 재부팅 시 1부터 다시 시작 |

Control은 TIME 요청/응답으로 MCU 시각과 Pi 시각을 연결한다. 프로세스 내부의
만료 판정은 monotonic clock을 사용하며 ROS 표본은 ROS header 시각으로 전달한다.
BNO055 표본 시각은 UART 수신 완료 시각이다. 센서 내부 측정 시각과 같다고 가정하지 않는다.
ACK는 Pi RAM 수신 확인이며 디스크 영구 저장 확인이 아니다.

Gateway의 control_epoch, 카메라 stream token, 모든 프로세스에 공통인 128bit boot_id는
현재 구현 계약이 아니다. 데이터 재생·분석에서 시간축을 맞출 때는 각 기록의
시계 원점과 재시작 구간을 확인한다.
