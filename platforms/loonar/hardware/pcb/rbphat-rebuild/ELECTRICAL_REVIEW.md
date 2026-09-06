# RBPHAT 2단계 — 전기적 타당성 검토

2026-09-05. 사용자 확정: **16mm 헤더로 진행**. 대상은 Pi 5, 3S 배터리, Control/Payload 전용 전이중 링크 2개다.

## 판정

**정상 전원에서 기본 기능은 구현 가능하지만, 기존 연결 그대로는 전원 OFF·전환 구간 보호를 승인할 수 없다.** 새 회로도에 반영할 수정안과 확인 항목을 아래에 정리했다. 이번 결과는 문서·DC 계산 검토이며 SPICE, ERC, 실측, EMC 인증 결과가 아니다.

| 항목 | 판정 | 다음 설계에 반영할 내용 |
|---|---|---|
| Pi 5 UART 두 채널 | 적합 | GPIO4/5, GPIO12/13 유지. Pi 5 전용 overlay 사용 |
| MAX3490E 정상 통신 | 조건부 적합 | 3.0–3.6V, Control 2Mbit/s. 케이블과 원격 수신 종단 필요 |
| SN74LVC2G34 | 정상 logic 연결 적합 | Ioff를 보드 전체 역급전 방지로 해석하지 않음 |
| 배터리 분압·ADC 범위 | 적합 | 47k+47k/18k, PGA ±4.096V 유지 |
| TMUX SEL1 전원 직결 | 수정 필요 | 전원 정상 신호로 enable 제어. 빠른 전원 하강도 별도 검증 |
| RX 바이어스 기본 DNP | 기능 조건 명시 필요 | 원격 OFF 시 UART idle HIGH를 보장하지 못함 |
| RX 바이어스 Pi 3.3V 직결 실장 | 보호 요구와 충돌 | 외부 A→저항→Pi rail 경로 때문에 그대로 실장 금지 |
| SM712 보호 협조 | 보장 근거 부족 | TVS 실장만으로 MAX3490E surge 보호 완료라 하지 않음 |
| 배터리 정확도 | 목표 미정 | 0.1% 저항만으로 0.1% 측정 정확도 불가. 교정 필요 |

전체 부품 공통 정상 공급 범위는 MAX3490E의 3.0–3.6V가 제한한다. 온도 범위는 우선 MAX3490EESA의 -40–85°C를 상한으로 보며 완성 보드 보증 범위는 아니다. 배터리 검토 범위는 정상 극성, 0–12.6V, 공통 GND다. 역극성·자동차 load-dump·낙뢰 수준 보호는 이 조건에 포함하지 않는다.

## 1. Pi 연결 및 정상 logic

| GPIO | 물리 핀 | RP1 기능 | 연결 |
|---|---:|---|---|
| 4 | 7 | a2 UART2_TX | Control buffer 입력 |
| 5 | 29 | a2 UART2_RX | Control buffer 출력 |
| 12 | 32 | a2 UART4_TX | Payload buffer 입력 |
| 13 | 33 | a2 UART4_RX | Payload buffer 출력 |
| 2 | 3 | a3 I2C1_SDA | ADS1115 SDA |
| 3 | 5 | a3 I2C1_SCL | ADS1115 SCL |
| — | 1, 17 | 3.3V | HAT logic 전원 |
| — | 6, 9, 14, 20, 25, 30, 34, 39 | GND | 공통 GND |

5V 핀 2/4는 이 HAT의 전원 경로에 연결하지 않는다. ID_SD/ID_SC는 HAT ID 결정 전 일반 I/O에 사용하지 않는다. [RP1 Table 4, §3.1](references/rp1-peripherals.pdf)

Pi 5용 OS 이미지의 `/boot/firmware/config.txt`에 적용할 설정 예시는 다음과 같다. 실제 파일 위치·overlay 지원은 최종 OS에서 확인한다. 이번에 실행 중인 호스트 설정을 변경하지 않았다.

```ini
dtoverlay=uart2-pi5
dtoverlay=uart4-pi5
dtparam=i2c_arm=on
```

`ctsrts`와 `rs485` 옵션은 사용하지 않는다. MAX3490E에는 DE/RE가 없으며 방향 전환 없는 전이중 UART다. BCM2711용 `uart2`/`uart4`와 혼용하지 않는다. `/dev/ttyAMA*` 번호를 회로 채널명에서 추정하지 말고 실제 DT 경로와 loopback으로 매핑한다. [Raspberry Pi Linux 공식 overlay 목록](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.12.y/arch/arm/boot/dts/overlays/README)

MAX RO→LVC 입력은 VCC=3.0V에서도 RO HIGH ≥2.6V, LOW ≤0.4V로 LVC VIH=2.0V/VIL=0.8V와 맞는다. LVC→MAX DI도 경부하 출력 사양에서 여유가 있다. RP1 핀은 동일 3.3V logic로 연결하되 이전 BCM 계열의 전기 특성 숫자를 Pi 5 보증치로 옮기지 않는다. Pi 측 경계의 최종 noise margin은 RP1 전기 사양 추가 확인과 파형 측정 대상으로 남긴다. [MAX 데이터시트 p.3](https://www.analog.com/media/en/technical-documentation/data-sheets/max3483e-max3491e.pdf), [LVC §6.3–6.6](references/sn74lvc2g34.pdf)

직렬저항은 우선 **47Ω**, buffer 출력 핀 가까이에 배치한다. 20pF 가정 시 저항만의 10–90% 상승시간은 약 2.1ns로 2Mbit/s의 500ns bit time보다 작다. 실제 driver·기생성분은 포함하지 않은 추정이다.

TX 47kΩ 풀업은 정상 UART 구동을 크게 방해하지 않지만 **부팅 전체의 HIGH 보장 수단은 아니다.** 내부 pulldown/초기 pinmux와 경쟁할 수 있고, 20pF 가정의 수동 상승시간은 약 2.07µs다. LVC2G34는 Schmitt 입력이 아니므로 reset 때 느린 입력도 검토한다. GPIO 내부 pull 설정 확인 후 강한 풀업 또는 Schmitt buffer 변경 여부를 결정한다.

GPIO2/3에는 고정 풀업이 있으므로 HAT의 추가 I2C 풀업은 기본 DNP로 설계한다. 실측 bus capacitance에 따라 결정하며 5V로 풀업하지 않는다. ADS ADDR=GND로 0x48, AIN0 single-ended, ALERT 미사용 시 NC 또는 테스트 패드, AIN1–3은 미사용 표시한다. [Raspberry Pi 공식 GPIO 설명](https://github.com/raspberrypi/documentation/blob/master/documentation/asciidoc/computers/raspberry-pi/gpio-on-raspberry-pi.adoc)

## 2. 전원 OFF와 역급전

### A. 버퍼를 통과하지 않는 경로

MAX VCC는 0Ω을 통해 Pi 3.3V와 연결돼 있다. **0Ω은 분리·측정용이며 역류 차단이나 퓨즈가 아니다.** MAX 입력에서 전원으로 전류가 들어오면 버퍼와 무관하게 Pi rail에 도달할 수 있다. LVC Ioff는 VCC=0V 조건에서 ±10µA 규격이며 그 조건 자체가 rail 상승으로 깨질 수 있다.

바이어스를 실장하면 더 명확한 경로가 생긴다.

```text
원격 TX+ → HAT RX A → 680Ω → Pi 3.3V
```

Pi rail이 0V로 유지되고 A=3.3V라는 예시에서 이 저항 전류만 약 4.85mA다. 실제 A 전압과 rail 부하에 따라 달라진다. 이 연결은 사용자의 역급전 방지 요구와 충돌한다.

**설계 방향:** 기본 DNP를 유지하되, 원격 OFF idle 보장은 별도 해결한다. MAX를 유지한다면 MAX 전원·바이어스를 Pi rail에서 실제 역류 차단하는 전원 분기와, 꺼진 분기의 방전·logic 주입까지 함께 설계해야 한다. 단순히 diode나 load switch 하나를 추가했다고 완료 처리하지 않는다. 대안은 powered-off 특성과 terminated-idle fail-safe가 명시된 transceiver로 변경하는 것이다. 이번 단계에서 MAX 부품은 임의 교체하지 않았다.

MAX 데이터시트의 line 입력 전류 표는 Pi rail로 유입되는 전류의 보증 상한이 아니다. MAX3491E에만 명시된 출력 leakage/enable 조건을 MAX3490E로 일반화하지 않는다. [MAX p.3–4](https://www.analog.com/media/en/technical-documentation/data-sheets/max3483e-max3491e.pdf)

### B. TMUX1511 전원 전환

VDD=0V에서 BAT_DIV=2.025V는 TMUX의 powered-off 허용 신호 범위 안에 있다. 그러나 OFF leakage는 무조건 0이 아니다. 데이터시트 지정 조건에서 25°C ±10nA, 전체 온도 표에서는 ±2µA이므로 무부하 rail 상승 가능성을 측정한다. [TMUX §5.3, §5.5, §7.3.4](references/tmux1511.pdf)

**SEL1=Pi 3.3V 직결은 삭제할 수정안이다.** 전원이 1.5V인 구간에서 TMUX는 동작 가능하고 SEL1은 HIGH다. 배터리 입력 약 2.025V를 연결하면 ADS 입력 한계 VDD+0.3V=1.8V를 넘을 수 있다. 완전히 꺼진 상태의 보호와 전원 상승/하강 중 ADC 보호는 구분해야 한다.

수정 후보는 **TLV803ED29DBZR** 같은 2.93V supervisor의 `/RESET`을 TMUX SEL1에 연결하는 것이다. open-drain 출력에 Pi rail 풀업, 저전압에서는 SEL LOW, 정상 전원에서 지연 후 HIGH로 만든다. 이 품번은 50ms 지연형이다. RESET은 Pi reset에 연결할 필요가 없다. [TI 제품](https://www.ti.com/product/TLV803E/part-details/TLV803ED29DBZR), [데이터시트](references/tlv803e.pdf)

이 후보도 아직 회로 승인 상태는 아니다. 검출 지연·glitch immunity·출력 pullup 부하·저전압 출력 보장을 확인하고, 빠른 rail 붕괴 시 ADC 입력이 한계를 넘기 전에 switch가 끊기는지 검증해야 한다. ADC 측 잔류 전하 방전/전류 제한까지 포함한다. MCU/OS GPIO enable만으로 brownout 보호를 대체하지 않는다.

### C. 시험해야 할 전원 상태

| 상태 | 확인 사항 |
|---|---|
| Pi ON / 배터리 ON / 원격 ON | 두 통신채널과 전압 측정 정상 |
| Pi reboot / 3.3V 유지 | boot pinmux, TX idle, framing 재동기화 |
| Pi OFF / 원격 ON | RX A/B와 선택 바이어스·MAX VCC의 Pi rail 유입 전류 |
| Pi OFF / 배터리 ON | TMUX leakage와 AIN0·Pi rail 상승 |
| Pi 상승/완만한 하강/급락 | SEL1, VDD_ADC, AIN0 동시 관측 |
| MAX 전원 0Ω 제거 / Pi ON | Pi TX→buffer→꺼진 MAX DI의 주입 가능성. 측정 절차에서 분리 |
| Pi ON / 원격 OFF 또는 케이블 분리 | 수신 idle/가짜 byte 발생 여부 |

USB/debug 케이블 등 다른 전원이 연결된 상태도 별도로 구분한다. BAT-와 통신 GND는 공통이지만 모터 전류가 sense/통신 GND 가는 선을 귀환로로 쓰지 않게 하네스를 구성한다.

## 3. 종단·바이어스·보호

HAT RX A/B에 120Ω, HAT TX Y/Z는 원격 receiver 쪽에 120Ω을 둔다. point-to-point 각 방향 한 쌍의 twisted pair를 전제로 한다. 여러 송신기를 병렬로 붙이지 않는다. 120Ω 케이블을 기준으로 하며 케이블 임피던스가 다르면 종단값도 재검토한다.

MAX의 open-input fail-safe는 **120Ω으로 묶인 입력의 idle 보장이 아니다.** 바이어스 DNP에서 원격 송신이 멈추고 고임피던스가 되면 A−B≈0V로 결정 불가능 영역에 들어간다. CRC로 가짜 명령을 걸러도 물리 idle이 보장되는 것은 아니다.

680Ω 양쪽 바이어스와 120Ω의 이상적 idle은 3.3V에서 268mV다. 3.0V, 저항 1%, 수신 입력 12kΩ 가정에서는 약 237mV로 200mV 임계 대비 37mV만 남는다. 원격 OFF leakage·TVS leakage·잡음은 제외했다. 560Ω이면 해당 모델에서 약 283mV지만 역급전 경로는 더 강해진다. **저항값 변경만으로 해결할 문제가 아니다.**

SM712는 1/2번을 각 differential line, 3번을 GND에 연결하는 구조다. 해당 12V/-7V 수치는 working voltage이며 펄스 때 그 전압으로 고정되는 의미가 아니다. MAX의 DC absolute maximum과 TVS 펄스 clamp를 단순 비교해 파손을 단정할 수도, 보호를 보증할 수도 없다. 요구 ESD/EFT/surge 파형·전압·발생기 임피던스에 대한 보호 협조 검토와 시험이 필요하다. **현재 SM712는 후보 footprint로 유지하되 surge 적합 판정은 보류한다.** [Semtech 작성 데이터시트 p.2–6](https://www.mouser.com/datasheet/2/761/SEMT_S_A0003609968_1-2576005.pdf)

TVS는 커넥터 가까이, 짧고 넓은 GND 귀환과 인접 via를 둔다. 보호되지 않은 배선이 보호된 배선 옆으로 길게 지나가지 않게 한다. 통신선의 지속적인 배터리 오접속 보호와 ESD 보호는 별개다.

## 4. 배터리 측정 계산

[계산 코드](electrical_calculations.py)와 [재현 결과](electrical_calculations.json)를 함께 저장했다. 저항 공차는 3개 부품의 극단 조합 8개를 계산했다.

| 항목 | 결과 | 의미 |
|---|---:|---|
| 분압비 / 환산계수 | 0.160714 / 6.222222 | 기존 식 유지 |
| 12.6V 입력 | 2.025V | 3.3V 정상 전원에서 적합 |
| 분압 전류 | 112.5µA | 배터리 연결 중 계속 소비 |
| 상단 47k 각각 소비 | 0.595mW | 정상 상태에서 저항 전력 부담 작음 |
| 하단 18k 소비 | 0.228mW | 같은 조건 |
| Thevenin 저항 | 15.107kΩ | ADC 부하/누설 오차 계산 기준 |
| 1µF RC 시정수 / 차단주파수 | 15.107ms / 10.535Hz | 공칭 C, ADC 부하 제외 |
| RC 0.1% 정착 | 104.36ms | ADC conversion 시간 별도 |
| 0.1% 저항의 분압비 극단오차 | -0.16774% ~ +0.16797% | ADC·온도·누설 제외 |
| ±4.096V PGA의 1LSB | ADC 125µV / 배터리 0.778mV | 분해능이며 정확도 아님 |

ADS1115 Fig.7-5의 전형적 모델을 적용하면 common-mode 6MΩ은 **0.7V 기준**, differential 15MΩ은 AINN=GND 기준이다. 둘을 모두 GND 저항으로 단순화하지 않았다. 모델상 12.6V에서 ADC≈2.01964V이며 기존 환산식으로 약 **33.3mV 낮게** 읽힌다. 9V에서는 약 20.7mV다. 두 impedance는 typical뿐이므로 이 값을 보증 오차나 고정 보정계수로 쓰지 않는다. [ADS p.5, p.14](references/ads1115.pdf)

TMUX 50nA ON leakage를 하나의 node 오차 전류로 놓으면 배터리 환산 약 4.7mV다. 이는 지정 시험조건 값을 이용한 민감도 계산으로 보드 전체 worst-case 합계가 아니다. ADC의 gain/offset 사양에도 PGA·온도 조건이 있으므로 ±2.048V 조건 값을 ±4.096V 전체온도 보증으로 전용하지 않는다.

**선택:** 현 분압값과 ±4.096V 유지, 실제 구성에서 최소 2점 교정 적용. 정확도 목표가 0.1%급이라면 low-bias buffer 또는 분압 저항 감소를 별도 설계해야 한다. 1µF는 sampling 노이즈를 완화하지만 DC loading을 없애지 않는다. ±2.048V는 12.6V에서 여유가 작아 채택하지 않는다. 첫 측정은 전원 정상·SEL ON·RC 정착·변환 완료 후 사용한다.

수동소자 설계 기준: 분압 저항은 0603 0.1%, TCR은 25ppm/°C 이하를 우선하고 서로의 tracking까지 오차에 반영한다. 분압 C는 1µF X7R, 최소 10V 후보로 실제 bias 용량을 확인한다. IC별 100nF를 각 VCC 바로 옆에 둔다. RX 120Ω은 정상 신호의 전력과 온도 derating을 계산해 0.25W급을 우선 검토한다. 제조사 품번·풋프린트는 회로도 부품표에서 확정하며 아직 발주 BOM은 아니다.

## 5. 전원 예산 및 회로도 이행 조건

외부 수신단 120Ω 두 개에 각각 최대 3.6V가 걸린다는 이상적 상한 모델의 선로 전류는 합계 60mA다. MAX 무부하 소비 약 4.4mA(max 표 적용 조건 확인), 기타 IC·풀업·스위칭 소비가 추가된다. 초기 배선 예산은 정상 100mA 수준의 여유로 잡되 Pi 3.3V 가용 예산·증설 용량은 별도 확인한다. 이는 단락 전류 한도가 아니다. 0Ω은 고장 차단을 제공하지 않는다.

3단계 회로도에 넘길 상태:

- **확정:** 16mm 헤더, 두 UART 핀, I2C 연결, 47Ω 출력 직렬저항 초깃값, 분압값, PGA ±4.096V, 4층 기본 구조.
- **수정 설계 필요:** TMUX power-good enable/하강 보호, RS 바이어스와 rail 역류 차단을 함께 해결하는 구조, boot TX idle 조건.
- **회로 승인 전 필요:** MAX rail leakage 근거 또는 bench 결과, 보호 시험 수준, 측정 정확도 목표, ADC 방전·누설 처리, 정확한 MAX SOIC-8 도면.
- **기구/제작 단계:** 16mm 실제 조립 간격·팬·케이블 간섭, footprint pad 대응, 보드 제조사 DRC/stackup.

보호 요구를 충족했다고 표시한 완성 회로도는 아직 만들 수 없다. 정상 동작이 가능한 블록과 변경이 필요한 보호 블록을 구분한 상태로 2단계 검토를 완료한다.
