# LOONAR 배선과 차체 값

현재 소스의 기준이다. PCB 도면·과거 센서 단독 시험의 배선과 구분한다.

| 구성 | 장치 / 역할 |
| --- | --- |
| 메인 | Raspberry Pi 5, Ubuntu 24.04 arm64 / ROS 2 Jazzy |
| Control | Teensy 4.1, FreeRTOS, RoboClaw와 BNO055 |
| Payload | 별도 Teensy 4.1, Arduino 센서 앱 |
| 카메라 | Raspberry Pi Camera Module 3 Wide |
| 깊이 센서 | CubeEye I200DK |

## Control Teensy

| 신호 | 핀 / 인터페이스 |
| --- | --- |
| RoboClaw TX → Teensy RX | 7, Serial2 |
| Teensy TX → RoboClaw RX | 8, Serial2 |
| BNO055 TX → Teensy RX | 25, Serial6 |
| Teensy TX → BNO055 RX | 24, Serial6 |
| Pi 링크 기본값 | USB CDC |
| Pi 링크 UART 옵션 | Serial3 RX15 / TX14, 2Mbaud; HAT 배선 확인 필요 |

BNO055 UART는 115200 8N1, PS1 HIGH / PS0 LOW다. GND를 공통으로 연결한다.
이전 BNO085 RESET8은 현재 모터 TX8과 충돌하므로 연결하지 않는다.
RoboClaw packet serial은 115200baud다. 엔코더는 RoboClaw가 읽으며 Teensy A/B 입력은 없다.
핀 정의: [board_pins.h](../firmware/control/include/loonar/control/board_pins.h).

| 차체 설정 | 값 |
| --- | --- |
| 모터 채널 | M1 오른쪽 / M2 왼쪽 |
| 바퀴 반지름 | 0.098m |
| 윤거 | 0.210m |
| 출력축 1회전 count | 485681 |
| 전진 count 부호 | 좌우 +1 |
| 바퀴 속도 상한 | 0.4m/s |

Pi registry geometry와 실제 드라이버 설정을 맞춘다.

## Payload

[Payload 펌웨어](../firmware/payload/README.md)의 핀 표를 따른다.
Control과 독립된 USB 장치를 사용하며 현재 START/STOP은 ASCII 프로토콜이다.
UART transceiver를 통한 Payload binary 전송은 현재 운용 경로가 아니다.
