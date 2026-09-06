> **B1 회로 설계 이력**: 현재 기구·풋프린트·BOM·PCB 준비 상태는 [B2 인계 문서](PRE_LAYOUT_READY.md)가 우선한다. 16mm는 헤더 몸체이며 보드 간격은 19mm다. 아래의 미완료 풋프린트/품번/PCB 항목은 B2에서 갱신했다.

# RBPHAT Rev B1 — 3단계 회로도

2026-09-05. **16mm 헤더, 기존 약 33mV의 ADC 로딩 편차 허용**을 반영한 새 회로도다. 이전 `rbphat/` 회로의 연결 데이터를 가져오지 않고 제조사 핀 표를 기준으로 작성했다. 원래 요구 문서와 2단계 검토는 변경 이력으로 보존한다. 회로 변경의 현재 기준은 이 문서와 같은 폴더의 KiCad 파일이다.

현재 결과는 **회로도 검토본**이다. KiCad ERC·넷리스트 검증을 마쳤으며 PCB 배치·배선, DRC, 실물 과도응답/통신 시험은 다음 단계다. 빠른 전원 차단과 서지 내성은 계산만으로 실물 합격을 선언하지 않는다.

## 파일

- `rbphat.kicad_pro`, `rbphat.kicad_sch`: 열어 편집할 프로젝트와 최상위 회로도.
- `control.kicad_sch`, `payload.kicad_sch`, `battery.kicad_sch`: 하위 세 장.
- `RBPHAT.kicad_sym`, `sym-lib-table`: 프로젝트 전용 심볼과 라이브러리 등록.
- `fp-lib-table`: KiCad 10 표준 풋프린트 라이브러리 등록.
- `rbphat.pdf`: 네 장의 회로도 PDF.
- `bom.csv`, `components.json`: 실장/DNP, 품번, 풋프린트, 핀 연결.
- `validation/erc.rpt`, `validation/validation.json`, `validation/netlist.xml`: 실제 KiCad 출력과 검증 기록.
- `rev_b_calculations.py/.json`: 변경된 분압·ADC 로딩·전원 유지 계산.

## 변경 사항과 근거

| 문제 | 반영한 회로 | 근거/한계 |
|---|---|---|
| 종단된 RX에서 MAX3490E의 open-input fail-safe만으로 idle HIGH 보장 불가 | U101/U201 **THVD1451DR**로 변경, 외부 bias 저항 삭제 | [TI 데이터시트](references/thvd1451.pdf), full-duplex pin table p.5, fail-safe 설명. 기존 MAX와 8-pin SOIC 핀 기능 호환. 최대 속도 50Mbps인 소자이며 실제 링크 목표는 2Mbps 유지 |
| remote → transceiver VCC → Pi rail 역류 경로 | U1 LM66100, **CE를 VOUT에 연결** | [LM66100](references/lm66100.pdf) pin table 및 reverse-blocking 회로. 정상 공급은 Pi 3.3V에서만 받음. 절연 전원은 아님 |
| 통신 전원 분리 시험 필요 | R108/R208 0Ω, TP100/TP200 유지 | 0Ω은 전류 측정·분리용. 보호 소자로 계산하지 않음. 링크 제거 시 해당 송신 GPIO 구동도 중지해야 함 |
| TX reset 시 느린 입력/약한 pull-up | U100/U200 **SN74LVC2G17DBVR**, TX pull-up 10kΩ | [LVC2G17](references/sn74lvc2g17.pdf): Schmitt 입력, Ioff. 출력 47Ω 유지. Pi boot pinmux/내부 pull과의 경쟁은 bring-up에서 확인 |
| TMUX enable 전원 직결 | U3 **TLV803ED29DBZR**, POWER_GOOD → TMUX SEL1 | [TLV803E](references/tlv803e.pdf): nominal threshold 2.93V, delay 50ms. SEL2/3/4는 GND, 미사용 signal pin은 NC |
| 전원 급락 시 ADC가 먼저 꺼지는 문제 | U2 LM66100 + R1 22Ω pulse + C3 **EEEFK1C101P 100µF/16V** | ADC/TMUX/TCA B측 전원을 잠시 유지. [Panasonic FK](references/panasonic-fk.pdf): 100µF ±20%, 6.3×5.8mm. LM66100 turn-off 시간은 typical이므로 파형 검증 필요 |
| 잔류 입력 전하·TMUX OFF leakage | R303 **47kΩ 0.1%**, C301 1nF C0G | OFF leakage 2µA 단독 가정에서 AIN0 ≈94mV. 켜진 상태에서는 의도적으로 분압을 부하하므로 새 환산계수 사용 |
| 유지된 ADC 전원 → Pi I2C 역급전 경로 | U302 **TCA9517ADGKR** | [TCA9517A](references/tca9517a.pdf): A측 Pi 전원, B측 ADC 전원, EN=POWER_GOOD. B측 pull-up 4.7kΩ. Pi 측 추가 pull-up 없음. galvanic isolation 아님 |
| TVS 하나만으로 보호 협조 주장 | 커넥터측 CDSOT23-SM712 + 각 선로 **CRCW0603010RJNEAHP 10Ω** | THVD 데이터시트 p.27 Figure 38/Table 7의 조합 반영. 해당 예제는 5V 기준으로, 이 3.3V 보드의 1kV 내성을 보증하지 않음 |

U1/U2의 미사용 ST는 각각 10kΩ으로 GND에 묶었다. U1 출력에 10kΩ, U2 출력에 10kΩ, Pi 3.3V에 1kΩ 방전 부하를 둔다. 이들은 leakage에 의한 전압 상승을 줄이는 수단이며 외부 과전압을 흡수하는 정격 보호 회로는 아니다. Ioff·ideal-diode leakage는 0이 아니므로 “전원 OFF에서 전류가 완전히 0”이라고 표현하지 않는다.

## 배터리 측정 설정

R300/R301=47kΩ, R302=18kΩ, R303=47kΩ, 모두 0.1%다. 스위치가 켜지면 R303도 하단 저항으로 작용한다.

```text
VBAT / VADC = 1 + 94000/18000 + 94000/47000 = 8.222222222
VADC(12.6V) = 1.532432V     [Ron와 ADC 내부 부하 제외]
VBAT = signed_ADC_code × (4.096 / 32768) × 8.222222222
```

ADS1115: ADDR=GND(0x48), MUX=AIN0–GND, PGA=±4.096V, comparator disabled. AIN1–3=GND, ALERT/RDY=NC. single-shot 128SPS 설정 예시는 config `0xC383`; conversion-ready를 확인하고 conversion register의 **signed 16-bit** 값을 읽는다. 이 값은 펌웨어에 적용한 변경이 아니라 구현용 설정이다. POWER_GOOD 활성화 후 150ms 이상 기다려 분압 RC를 안정시킨 뒤 읽는다. Pi 재부팅으로 이전 전원 상태를 모르면 동일하게 대기한다.

ADC의 **typical** 6MΩ common-mode(0.7V 기준), 15MΩ differential 입력 모델을 쓰면 12.6V에서 −22.6mV, Ron=4.5Ω까지 넣은 예시는 −23.5mV다. 사용자 허용 범위 내인 것으로 판단해 별도 정밀 buffer는 추가하지 않았다. 이것은 전체 정확도 보증값이 아니다. 저항 공차만 약 ±0.176%, ADC gain/offset·온도·TMUX leakage는 별도다. 기존 **6.222222** 환산계수를 사용하면 큰 오차가 나므로 반드시 바꾼다.

전원 OFF 시 입력 방전 계산은 TMUX OFF leakage와 R303만의 정적 모델이다. ADC 내부, 실제 기생용량, 미규정 저전압 구간까지 모든 조건을 보증하는 모델은 아니다.

## 전원 시퀀스 검토

정상 Pi 공급 검토 범위는 우선 3.15–3.45V, 공통 GND, 정상 극성 배터리 0–12.6V다. 이는 Pi 제조사의 전원 허용 범위를 새로 규정하는 것이 아니라 이번 HAT의 설계/시험 조건이다. 외부 line fault는 THVD absolute maximum을 넘지 않는 범위로 제한되며 임의 고전압 fault를 보증하지 않는다.

- 전원 상승: C3는 R1을 통해 충전된다. nominal RC=2.2ms이며 supervisor release 지연보다 짧다. POWER_GOOD가 켜진 뒤 TMUX/I2C가 활성화된다.
- 전원 하강: supervisor가 SEL을 내리고, LM66100이 역류를 막으며 C3가 analog 전원을 유지한다. C3=80µF, analog 부하 10mA 가정에서 200µs 동안 하강량은 25mV다. 입력 1nF의 2.025V→0.3V 방전 추정은 약 99µs다.
- R1 초기 순간 전력 약 0.495W, 충전 에너지 약 0.545mJ다. 일반 0603의 DC 정격만으로 대체하지 말고 지정 pulse-proof 계열과 펄스/반복 조건을 확인한다.
- TLV803E 검출 지연의 조건부 최대값과 LM66100의 **typical** turn-off 시간을 섞어 최악조건 보증값으로 만들지 않았다. C3의 저온·수명·ESR도 실측 검토 대상이다.
- brownout 중 TCA9517A B측이 권장 최소 2.7V 아래로 내려갈 수 있으므로 통신 성공을 기대하지 않는다. 진행 중 I2C transaction의 abort/NACK는 허용하고 전원 복귀 후 재시도한다. ADC 입력 절대정격 보호와 통신 가용성을 구분한다.

실물에서 TP1(ANA), TP301(AIN0), TP302(POWER_GOOD), Pi 3.3V를 동시에 관측한다. 배터리/remote를 켠 채 Pi 공급의 상승, 완만한 하강, 급격한 차단을 시험하고 **AIN0 ≤ VDD_ADC+0.3V**, Pi OFF rail 상승/유입 전류, UART RX 파형을 기록한다. USB/debug 등 우회 전원 경로를 구분한다.

## 인터페이스·실장

- J1: physical pin 7/29 = GPIO4/5 Control TX/RX, 32/33 = GPIO12/13 Payload TX/RX, 3/5 = SDA/SCL. 5V와 ID pins 27/28은 NC.
- J2/J3: **1 TX+, 2 TX−, 3 RX+, 4 RX−, 5 GND**. 원격 TX↔로컬 RX 교차. 각 방향 twisted pair를 사용한다.
- R107/R207 120Ω은 기본 DNP. 로컬 receiver가 120Ω 케이블의 끝이고 중복 종단이 없을 때 실장한다. TX 종단은 원격 receiver에 둔다. 각 종단은 10Ω 직렬저항의 커넥터측에 연결했다.
- J4: 1 BAT+, 2 common GND. 배터리 전압 감지 전용이며 HAT 전원 입력이 아니다. 역극성·모터 load-dump 보호를 추가한 회로로 보지 않는다.
- J1은 **16mm socket** 선택을 유지한다. PCB 단계에서 부품을 HAT 하단에 배치할 때 B.Cu 미러/1번 핀과 실제 mating height를 확인한다. 일반 2×20 풋프린트의 3D 모델 높이가 선택한 헤더를 대표하지 않는다.
- ADC 풋프린트는 DGS 3×3mm/0.5mm에 대응하는 KiCad `MSOP-10_3x3mm_P0.5mm`; TI의 VSSOP 명칭과 KiCad 이름 차이를 정리했다.
- 이번 검증은 **패드 번호 존재/커버리지**까지다. 각 pad 치수, solder mask/paste, 부품 courtyard, 높이, 제조사 land pattern 대조와 3D 간섭 검증은 PCB 단계에서 수행한다.
- `bom.csv`에서 MPN 공란인 수동소자는 값/패키지 기준의 parametric BOM이다. 제조사 품번·온도계수·유전체·DC bias를 확정하기 전 발주용 BOM으로 사용하지 않는다. IC/TVS/커넥터/C3/line pulse 저항은 품번을 기재했다. R1 품번은 Vishay ordering 규칙으로 구성한 후보이며 주문 가능성 확인이 남는다.
- HAT ID EEPROM은 추가하지 않았다. 제품을 HAT+ 인증/준수 완료라고 표시하지 않는다.

## 검증 재현

```bash
python3 generate_schematic.py
python3 validate_schematic.py
python3 rev_b_calculations.py
```

`generate_schematic.py`는 같은 폴더의 생성 파일을 덮어쓴다. GUI에서 편집한 회로도를 보존하려면 재생성 전에 복사하거나 변경을 생성기에 반영한다.

2026-09-05 KiCad 10.0.4 결과: **4 sheets, 72 components, 240 pin connections, ERC errors 0 / warnings 0**. 핀 연결 검사는 생성기 manifest와 실제 export의 일치뿐 아니라 Pi physical pins, 양방향 UART chain, THVD differential polarity, LM66100 CE=VOUT, ADC/TMUX/I2C 전원 분리를 별도 assertion으로 확인한다. footprint pad 번호도 확인했다. 명시적 ERC 제외 항목은 0개다. KiCad 기본 비활성 검사 네 항목은 `erc.rpt`에 그대로 보존했다.

PDF 네 장을 렌더링하여 핀/값/라벨/도면 경계를 확인했다. SPICE, PCB DRC, 시제품 통신/전원/EMC 시험은 실행하지 않았다.
