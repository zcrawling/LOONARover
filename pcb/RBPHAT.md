## 1. 목적

Raspberry Pi 5용 40-pin 확장 PCB를 설계한다.

주요 기능:

1. Raspberry Pi 5 UART 2채널을 MAX3490E 2개를 이용해 Full-Duplex RS-422/RS-485 물리계층으로 변환
2. Control MCU PCB와 Payload MCU PCB 각각 연결
3. 3S 배터리 RAW 전압 측정
4. 외부 회로 이상 또는 Pi 전원 OFF 상태에서 Raspberry Pi GPIO/3.3V rail로 역급전되지 않도록 보호
5. PCB는 실제 제작 가능한 KiCad 회로도/PCB 설계를 목표로 함

---

# 2. Raspberry Pi 5 UART 핀

## UART Channel 1 — Control MCU

* GPIO4 = UART2_TX
* GPIO5 = UART2_RX

연결:

```text
Pi GPIO4 / UART2_TX
        |
        v
GPIO protection/buffer
        |
        v
MAX3490E #1 DI

MAX3490E #1 RO
        |
        v
GPIO protection/buffer
        |
        v
Pi GPIO5 / UART2_RX
```

외부 Control MCU PCB 쪽은 MAX3490E의 differential 신호를 커넥터로 출력한다.

```text
MAX3490E #1 Y  -> CTRL_TX+
MAX3490E #1 Z  -> CTRL_TX-

MAX3490E #1 A  <- CTRL_RX+
MAX3490E #1 B  <- CTRL_RX-

GND             -> CTRL_GND
```

---

## UART Channel 2 — Payload MCU

* GPIO12 = UART4_TX
* GPIO13 = UART4_RX

연결:

```text
Pi GPIO12 / UART4_TX
        |
        v
GPIO protection/buffer
        |
        v
MAX3490E #2 DI

MAX3490E #2 RO
        |
        v
GPIO protection/buffer
        |
        v
Pi GPIO13 / UART4_RX
```

외부 Payload MCU PCB 커넥터:

```text
MAX3490E #2 Y  -> PAYLOAD_TX+
MAX3490E #2 Z  -> PAYLOAD_TX-

MAX3490E #2 A  <- PAYLOAD_RX+
MAX3490E #2 B  <- PAYLOAD_RX-

GND             -> PAYLOAD_GND
```

---

# 3. MAX3490E 기본 연결

MAX3490E SO-8 기준:

```text
Pin 1 VCC -> Pi 3V3
Pin 2 RO  -> Pi UART RX 방향
Pin 3 DI  <- Pi UART TX 방향
Pin 4 GND -> Pi/HAT GND

Pin 5 Y   -> Differential TX+
Pin 6 Z   -> Differential TX-
Pin 7 B   <- Differential RX-
Pin 8 A   <- Differential RX+
```

MAX3490E #1과 #2 모두 Raspberry Pi의 3.3V rail에서 전원을 공급하되,
각 IC의 전원 경로를 독립적으로 분리한다.

```text
Pi 3V3 -> 0R -> MAX3490E #1 VCC
Pi 3V3 -> 0R -> MAX3490E #2 VCC
```

각 0R의 MAX3490E 쪽에는 test point를 둔다. Rev.A power-off 시험에서는
0R을 제거하고 전류계를 삽입하거나 해당 MAX3490E rail을 분리할 수 있어야 한다.

각 MAX3490E VCC 근처에:

```text
100nF ceramic decoupling capacitor
VCC -- 100nF -- GND
```

를 최대한 가까이 배치한다.

---

# 4. Pi GPIO 보호

Raspberry Pi GPIO가 MAX3490E에 직접 연결되지 않도록 중간에 3.3V logic buffer를 사용한다.

후보:

```text
SN74LVC2G34
```

UART 채널당 dual buffer 1개 사용 가능.

즉 총:

```text
SN74LVC2G34 x 2
```

개념:

```text
Pi TX -> buffer -> series resistor -> MAX3490 DI

MAX3490 RO -> buffer -> series resistor -> Pi RX
```

series resistor 후보:

```text
47 ~ 100 ohm
```

초기값은 47Ω 또는 100Ω 중 하나를 사용하고 필요시 실측 후 수정 가능하게 한다.

Buffer VCC는 Pi 3.3V.

SN74LVC2G34의 Ioff 특성을 이용해 Pi 3V3가 실제로 OFF인 상태에서 GPIO
측 back-drive를 차단한다.

Pi가 부팅 또는 reboot 중이라 GPIO TX가 input/Hi-Z가 되는 구간에도 UART
idle=HIGH가 유지되도록 다음 pull-up을 추가한다.

```text
GPIO4  / UART2_TX -> Pi 3V3 : 47k
GPIO12 / UART4_TX -> Pi 3V3 : 47k
```

47k pull-up은 정상 push-pull UART 신호에는 거의 영향을 주지 않는다.

---

# 5. RS-422 Differential Line 보호

각 외부 커넥터는:

```text
TX+
TX-
RX+
RX-
GND
```

최소 5핀으로 구성한다.

외부 케이블에서 들어오는 ESD/transient를 막기 위해 커넥터 바로 근처에 RS-422/RS-485용 TVS 보호소자를 배치한다.

구조:

```text
Connector
   |
  TVS
   |
MAX3490E
```

두 UART 채널 모두 적용한다.

TVS 정확한 부품은 아직 미확정이며 PCB 설계 전 선정한다.

---

# 6. Termination

각 MAX3490E의 RX differential pair A/B에 120Ω termination footprint를 둔다.

```text
A ----+
      |
     120R
      |
B ----+
```

즉 HAT에서 수신하는:

```text
CTRL_RX+ / CTRL_RX-
PAYLOAD_RX+ / PAYLOAD_RX-
```

각 pair에 120Ω.

반대로 HAT에서 송신하는 Y/Z pair의 termination은 반대편 MCU PCB의 receiver에서 수행한다.

120R termination은 기본 실장한다.

원격 송신기가 OFF일 때를 위한 fail-safe bias footprint도 각 receiver pair에
추가하되 Rev.A 기본 조립은 DNP로 한다.

```text
A -> Pi 3V3 : 680R DNP
B -> GND    : 680R DNP
```

실제 케이블 연결 상태의 idle differential voltage를 oscilloscope로 확인한 뒤
필요할 때만 실장한다.

---

# 7. 전원 상태 요구사항

MAX3490E와 GPIO buffer는 모두 Pi의 3.3V rail을 사용한다.

Pi ON 또는 reboot 중 Pi 3V3 ON:

```text
MAX3490E와 SN74LVC2G34는 정상 powered 상태
외부 Teensy의 UART/RS-422 연속 송신은 정상 입력 조건
중간 packet부터 수신되는 문제는 firmware/protocol framing에서 처리
```

실제 power-off fault 시험 조건:

```text
Teensy ON
RS-422 계속 송신
Pi 3V3 OFF
```

이때 MAX3490E와 buffer는 OFF이다. SN74LVC2G34는 Ioff로 GPIO 측
back-drive를 차단한다. MAX3490E의 A/B 입력을 통해 VCC rail로 유의미한
역급전이 생기는지는 Rev.A에서 0R과 test point를 이용해 전류로 측정한다.
Pi의 단순 reboot는 이 fault condition으로 취급하지 않는다.

---

# 8. 배터리 전압 측정

배터리:

```text
3S Li-ion / LiPo
Nominal approximately 11.1V
Maximum = 12.6V
```

실전 시스템에서는:

```text
BAT- = HAT GND = Raspberry Pi GND
```

를 전제로 한다.

Pi는 배터리에서 non-isolated DC/DC를 통해 5V가 공급될 예정.

테스트 시 battery sensing을 사용하지 않는 경우 BAT+ / BAT- sense connector 자체를 연결하지 않아도 된다.

---

# 9. Battery Voltage Divider

분압 저항:

```text
RAW_BAT+
   |
  47k 0.1%
   |
  47k 0.1%
   |
   +------ BAT_DIV
   |
  18k 0.1%
   |
RAW_BAT- / GND
```

총 저항:

```text
47k + 47k + 18k = 112k
```

분압비:

```text
18 / 112
= 0.160714...
```

따라서:

```text
VBAT = 12.6V
BAT_DIV approximately 2.025V
```

Firmware 환산:

```text
VBAT = VADC x (112 / 18)

VBAT = VADC x 6.222222...
```

예:

```text
VADC = 2.025V
VBAT approximately 12.60V
```

분압 저항은 가능하면 0.1% tolerance 사용.

---

# 10. Battery Sense RC Filter

BAT_DIV에 capacitor를 추가한다.

초기값:

```text
1uF ceramic, preferably X7R
```

구조:

```text
BAT_DIV
   |
  1uF
   |
  GND
```

목적:

* DC/DC switching noise 감소
* ESC/motor 계열 고주파 noise 감소
* ADC reading 안정화

필요하면 100nF footprint도 병렬 추가 가능.

---

# 11. Pi OFF 시 Battery Sense 역급전 방지

문제:

Battery는 ON인데 Raspberry Pi가 OFF이면 divider 출력 약 0~2V가 계속 존재한다.

이를 꺼진 ADC에 직접 연결하면 ADC 내부 보호경로를 통해 Pi 3.3V rail로 역급전될 가능성이 있다.

따라서 divider와 ADC 사이에 powered-off protection을 지원하는 analog switch를 넣는다.

선정 부품:

```text
TMUX1511PWR (TSSOP-14)
```

구조:

```text
BAT_DIV
   |
   v
TMUX1511 channel 1
   |
   v
ADS1115 AIN0
```

TMUX1511 전원:

```text
VDD -> Pi 3V3
GND -> Pi GND
```

채널 1 연결:

```text
BAT_DIV -> S1 (pin 2)
D1 (pin 3) -> ADS1115 AIN0
SEL1 (pin 1) -> Pi 3V3
```

Pi 3V3가 정상일 때 SEL1=HIGH로 switch가 ON되고, Pi 3V3가 OFF이면
powered-off protection에 의해 S1/D1이 high impedance가 된다. 사용하지 않는
SEL2/SEL3/SEL4는 GND에 고정하고 S2/D2, S3/D3, S4/D4는 NC로 둔다.

TMUX1072는 사용하지 않는다. 47k+47k/18k처럼 source impedance가 높은
divider에서 ON leakage가 오차를 키울 수 있기 때문이다.

---

# 12. Power-Off 동작

Pi ON:

```text
Pi 3V3 = 3.3V

TMUX1511 powered, SEL1 HIGH
BAT_DIV -> TMUX -> ADS1115

Battery voltage measurement enabled
```

Pi OFF:

```text
Pi 3V3 = 0V

TMUX1511 powered off
I/O becomes high impedance

BAT_DIV --X--> ADS1115

No battery-sense backfeed into ADC/Pi
```

이 동작은 필수 요구사항이다.

---

# 13. ADC

외부 ADC:

```text
ADS1115
```

전원:

```text
VDD -> Pi 3V3
GND -> Pi GND
```

I2C:

```text
Pi GPIO2 / SDA -> ADS1115 SDA
Pi GPIO3 / SCL -> ADS1115 SCL
```

Analog:

```text
AIN0 <- TMUX1511 <- BAT_DIV
```

초기 PGA 설정:

```text
FSR = +/-4.096V
```

Battery max 12.6V에서 ADC input은 약 2.025V이므로 충분한 margin 확보.

나머지 AIN1/AIN2/AIN3는 future expansion 용도로 남겨도 됨.

---

# 14. Battery Sense 전체 블록

```text
3S BATTERY
MAX 12.6V

BAT+
 |
47k 0.1%
 |
47k 0.1%
 |
 +--------- BAT_DIV -------- S1
 |             |               |
18k 0.1%      1uF        +-----v------+
 |             |         | TMUX1511   |
BAT- --------- GND       |             |
 |                       | D1 ---------+---- ADS1115 AIN0
 +--------- HAT GND      +-------------+
                              |
                        VDD = Pi 3V3
                        SEL1 = Pi 3V3


ADS1115
 |
 +-- VDD = Pi 3V3
 +-- GND = Pi GND
 +-- SDA = Pi GPIO2
 +-- SCL = Pi GPIO3
```

---

# 15. 전체 시스템 블록

```text
                         Raspberry Pi 5
                  +---------------------------+
                  |                           |
GPIO4 UART2_TX ---+-> Buffer -> MAX3490E #1 --+--> CTRL TX+/TX-
GPIO5 UART2_RX <--+<- Buffer <- MAX3490E #1 --+<-- CTRL RX+/RX-
                  |                           |
GPIO12 UART4_TX --+-> Buffer -> MAX3490E #2 --+--> PAYLOAD TX+/TX-
GPIO13 UART4_RX <-+<- Buffer <- MAX3490E #2 --+<-- PAYLOAD RX+/RX-
                  |                           |
GPIO2 SDA --------+-----------+               |
GPIO3 SCL --------+---------+ |               |
                  |         | |               |
                  |      ADS1115              |
                  |         ^                 |
                  |         |                 |
                  |      TMUX1511             |
                  |         ^                 |
                  +---------|-----------------+
                            |
                         BAT_DIV
                            |
                     47k + 47k / 18k
                            |
                        3S BATTERY
```

---

# 16. PCB 설계 주요 원칙

* Rev.A는 4층(F.Cu / GND plane / power+slow signal / B.Cu)을 기본으로 한다.
* MAX3490E 및 buffer의 100nF decoupling capacitor는 VCC 핀에 최대한 근접
* RS-422 TVS는 MAX3490E보다 외부 connector에 최대한 근접
* differential TX/RX pair는 pair 간 간격을 일정하게 유지
* RX 120Ω termination은 receiver/MAX3490E 근처
* Pi UART logic trace는 짧게
* Pi GND plane/return path를 최대한 연속적으로 유지
* BAT_DIV node는 noisy digital/MAX3490E line에서 떨어뜨림
* ADS1115/TMUX1511/BAT divider는 analog section으로 묶어서 배치
* BAT_DIV capacitor와 TMUX 입력 사이 trace를 짧게
* BAT+, BAT-, BAT_DIV, ADS_AIN0, Pi 3V3, GND에 test point를 둔다.
* 각 MAX3490E의 0R 뒤 VCC에 독립 test point를 둔다.

---

# 17. Rev.A CAD 기본 선정

1. RS-422: JST-GH 1.25mm horizontal 1x5, 채널당 1개
2. Battery sense: JST-GH 1.25mm horizontal 1x2
3. RS-422 TVS: SM712 footprint를 differential pair마다 1개
4. GPIO buffer: SN74LVC2G34DBVR, SOT-23-6
5. Transceiver: MAX3490EESA+, SOIC-8
6. Battery isolation: TMUX1511PWR, TSSOP-14
7. ADC: ADS1115IDGSR, VSSOP-10
8. Raspberry Pi 2x20 stacking header와 공식 HAT 외형/홀 위치 사용
9. 4-layer board

정식 HAT+ ID EEPROM의 실장 여부와 RAW_BAT 입력 surge protection은 Rev.A
조립 전 별도 결정 항목으로 남긴다.

---

# 18. 중요 설계 요구사항 요약

반드시 만족해야 한다.

```text
1. UART2:
GPIO4 TX / GPIO5 RX
-> MAX3490E #1
-> Control MCU full-duplex differential interface

2. UART4:
GPIO12 TX / GPIO13 RX
-> MAX3490E #2
-> Payload MCU full-duplex differential interface

3. Pi GPIO는 외부 differential line에 직접 노출되지 않음.

4. MAX3490E, buffer, ADC, TMUX1511은 Pi 3.3V 기반.

5. Pi reboot + Pi 3V3 ON은 정상 powered 동작으로 취급한다.

6. 실제 fault 시험은 Teensy ON + RS-422 송신 + Pi 3V3 OFF이며,
   MAX3490E rail backfeed를 0R/test point로 측정한다.

7. Battery ON + Pi OFF 상태에서 battery sensing 회로를 통한 3.3V rail back-power 금지.

8. 3S battery 최대 12.6V 측정.

9. Divider:
47k + 47k top,
18k bottom,
0.1%.

10. 12.6V -> 약 2.025V ADC input.

11. Battery conversion:
VBAT = VADC x 6.222222

12. BAT_DIV -> 1uF RC filter -> TMUX1511 -> ADS1115.

13. TMUX1511 powered-off protection으로 ADC/Pi 역급전 차단.

14. ADS1115는 Pi I2C GPIO2/3 사용.

15. 실전에서는 BAT-와 Pi/HAT GND가 공통.

16. 테스트에서 battery sense가 필요 없으면 BAT+/BAT-를 연결하지 않는다.

17. Pi UART TX GPIO4/GPIO12에는 47k pull-up을 적용한다.

18. RX A/B에는 120R을 기본 실장하고 680R fail-safe bias 두 개는 DNP로 둔다.

19. MAX3490E 핀맵은 반드시 다음으로 고정하고 datasheet / symbol / footprint를
    3중 검증한다: 1=VCC, 2=RO, 3=DI, 4=GND, 5=Y, 6=Z, 7=B, 8=A.
```
