# MCU wire v2 구현 명세

모든 정수/IEEE-754 float는 little endian이다. 기존 wire v1과 호환되지 않는다.
`firmware/control/include/loonar/control/wire_v2.hpp`와 `tools/mcu_v2/wire.py`가 구현이다.

## 프레임

| Offset | 크기 | 필드 |
|---|---:|---|
| 0 | 4 | ASCII LNR2 |
| 4 | 1 | protocol=2 |
| 5 | 1 | role: control=1, payload=2 |
| 6 | 1 | type |
| 7 | 1 | flags=0 |
| 8 | 4 | boot counter |
| 12 | 4 | Pi가 생성한 nonzero session nonce |
| 16 | 4 | request sequence 또는 telemetry sample sequence |
| 20 | 8 | MCU monotonic timestamp, µs |
| 28 | 2 | payload size, 최대 192 |
| 30 | 2 | reserved=0 |
| 32 | 가변 | payload |
| 마지막 | 4 | CRC-32C(header+payload), init/final xor FFFFFFFF, reflected 82F63B78 |

CRC golden input `123456789` → `E3069283`. 최대 프레임 228바이트.
역할은 모든 패킷에서 검사한다. HELLO 외에는 boot가 같아야 하며 SESSION 이후에는
session과 증가하는 request sequence도 검사한다. MCU→Pi sample sequence는 ACK/replay용
별도 counter다. sequence wrap 전에 연결/보드 재시작이 필요하다.
CRC/nonce는 오접속·지연 패킷 구분용이며 암호학적 링크 인증은 아니다.

## 타입과 payload

| Type | 이름 | payload |
|---:|---|---|
| 1 | HELLO_REQUEST | 없음; 미등록 이미지에도 허용 |
| 2 | HELLO | `QQIII` (28바이트): UID, bound UID, oldest, latest, flags |
| 3 | SESSION | `Q`: UID; frame session에 새 nonce 지정 |
| 4 | HEALTH_REQUEST | 없음; 100 ms 간격 |
| 5 | HEALTH | 아래 88바이트 |
| 6 | MOTION | `IiiI`: command ID, left qpps, right qpps, lease ms |
| 7 | STOP | 없음 |
| 8 | CONFIGURE | `IB3x`: RoboClaw baud u32, address u8, reserved 3바이트=0 |
| 9 | ACK | `I`: Pi RAM에 수신한 연속 sample sequence |
| 10 | RESULT | `BBHI`: 요청 type, code(0=성공/1=거부), reserved, request sequence |
| 11 | TIME_REQUEST | `Q`: Pi wall-clock ns token |
| 12 | TIME | `QQ`: token echo, MCU µs |
| 32 | IMU | 아래 36바이트 |
| 33 | MOTOR | 아래 64바이트 |

HELLO flags bit0=UID binding 정상, bit4=control 기능.
COMMAND RESULT는 도착/수락 확인이며 실제 모터 회전 완료를 의미하지 않는다.
SESSION 성공 후 CONFIGURE는 정지 상태에서만 허용한다. 허용되지 않는 role/type 조합은 거부한다.
ACK는 실제 TX한 sample의 상한을 넘지 못한다. 누락된 record는 ACK하지 않고 재전송을 기다린다.
MCU가 이미 보유하지 않은 구간은 Pi missing counter와 로그에 남긴 뒤 진행한다.
Type 13은 사용하지 않으며 업로드 요청은 제공하지 않는다.

## Health (88 bytes)

| Offset | 내용 |
|---:|---|
| 0 / 8 / 16 | UID u64 / uptime ms u64 / CPU temperature float |
| 20 / 24 | inhibit u32 / last command u32 |
| 28 / 32 / 36 | link / driver / IMU progress u32 |
| 40 / 44 / 48 / 52 | RX errors / sample drops / priority drops / buffer depth u32 |
| 56 / 60 / 64 / 68 | gyro age ms / driver ACK age ms / IMU resets / rejected packets u32 |
| 72 | latest sample sequence u32 |
| 76 / 77 / 78 | transport u8(USB1/UART2), identity_bound u8, reserved u16 |
| 80 / 84 | driver failures / oldest retained sequence u32 |

age FFFFFFFF는 미수신이다. inhibit bit: identity1, session2, motion8, driver32, overtemperature128.
온도 조건은 MCU CPU 90°C 이상이다. IMU 및 health age는 주행 허가 조건이 아니다.

## IMU (36 bytes)

`BBBBQ5fI`: SH-2 sensor ID, accuracy status, sensor sequence, gap count,
SH-2 timestamp µs, values[5], reset count.

ID1 accel(m/s²), ID2 calibrated gyro(rad/s), ID3 mag(µT), ID4 linear acceleration(m/s²),
ID5 rotation vector(x,y,z,w,accuracy rad), ID6 gravity(m/s²).
프레임 timestamp는 MCU가 report를 수신한 시간이다. SH-2 내부 timestamp도 원본으로 보관한다.
Pi는 RTT 20 ms 이하의 TIME 교환으로 MCU 시간을 host 시간으로 변환하고,
200 ms보다 오래된 재전송 데이터는 ROS 제어용 topic에 재발행하지 않는다.
표본은 RAM으로만 처리하며 별도 archive를 만들지 않는다.

## Motor (64 bytes)

| Offset | 내용 |
|---:|---|
| 0 | valid mask u32 |
| 4 / 12 / 20 | L/R count i32×2 / speed qpps i32×2 / ACK된 commanded qpps i32×2 |
| 28 / 32 | current i16×2 (0.01 A) / PWM i16×2 (signed native scale) |
| 36 / 38 / 40 | main V u16 (0.1 V) / logic V u16 (0.1 V) / temperature u16 (0.1 °C) |
| 42 / 43 / 44 | ACK seen u8 / reserved / error u32 |
| 48 / 52 / 56 / 60 | ACK age / failures / count age / speed age (u32) |

valid mask bits0..7 = count, speed, current, main V, logic V, temperature, error, PWM.
모든 L/R 쌍은 왼쪽·오른쪽 순서이며 물리 채널은 M2/M1이다. RoboClaw 드라이버에서 변환한다.
각 측정이 500 ms 이내일 때 valid이다. 제어 허용 ACK는 이보다 엄격하게 100 ms 이내다.
RoboClaw packet serial 명령37/78/79/49/24/25/82/90/48을 사용한다.
명령90의 32bit error 응답을 지원하는 펌웨어가 필요하다.

## cFS → 지상국

새 SB MID `0x09A6`, GroundLink type `0x8007`, payload 128바이트다.
기존 `0x8004` 단일 MCU payload는 변경하지 않았다.

처음 40바이트는 `<4sBBHIIQQII>`:
`MCU2`, role, online, version=2, boot, session, host timestamp ms, UID,
health age ms, host parser errors. 뒤 88바이트가 MCU health 원문이다.
`mcu_bridge` 앱은 각 role의 마지막 수신 시각을 독립 관리하며 500 ms 후 online=0으로 보낸다.
GCS는 전송이 완전히 끊기는 경우에도 자체 수신 timeout으로 offline 판정해야 한다.
`common/ground_link` C++ decoder 및 `mcu_v2.inspect.decode_health` Python decoder가 제공된다.
