# 현재 산출물: Rev B3 / 배치·배선 완료

[아트웍 완료 보고](ARTWORK_B3.md), [KiCad 프로젝트](rbphat.kicad_pro), [상면 미리보기](artwork/top-3d.png), [최종 검증](artwork/validation.json)을 사용한다. ERC 0/0, DRC 위반 0, 미연결 0, 회로도 불일치 0.

> 아래 B2 및 1단계 내용은 과거 이력이다. 현재 상태는 B3 보고서가 우선한다.

# 현재 산출물: Rev B2 / 아트웍 착수 준비

[최종 인계 문서](PRE_LAYOUT_READY.md), [KiCad 프로젝트](rbphat.kicad_pro), [회로도 PDF](rbphat.pdf), [기구 도면](mechanical-review.pdf), [풋프린트 검토표](footprint-review.pdf), [구매 BOM](procurement_bom.csv)을 사용한다.

공식 Active Cooler, 16mm 몸체 헤더와 19mm 스페이서 기준. 회로도 ERC 0/0, PCB 일치 문제 0, 시작 형상 DRC 위반 0. 미연결 161개이며 배치·배선은 아직 시작하지 않았다.

---

> 아래는 **폐기된 선정안을 포함한 1단계 조사 이력**이다. 현재 부품·미해결 상태로 해석하지 말고 B2 인계 문서와 BOM을 따른다.

# RBPHAT 새 설계 — 부품 및 공식 자료 조사

조사일: 2026-09-05. 1단계 부품 조사 기록. 후속 [2단계 전기 검토](ELECTRICAL_REVIEW.md)를 함께 따른다.

사용자 결정(2026-09-05): **헤더 높이 16mm 확정**. PRT-16763을 해당 높이의 우선 품번으로 유지하며 조립 공차·간섭은 기구 단계에서 확인한다.

요구사항은 [기존 사양](../RBPHAT.md)을 따른다. 기존 회로도·심볼·검증 보고서는 새 설계의 검증 근거로 사용하지 않았다. 이 디렉터리에는 아직 새 회로도나 PCB가 없다.

## 조사 결과

주요 IC 4종과 JST 커넥터 계열의 품번을 확인했다. TVS는 제조사를 Semtech로 명시하고 SM712.TCT를 조건부 선정했다. Pi 헤더 높이는 후속 사용자 지시로 16mm 확정했다. 최종 조립 적합성 검토는 남아 있다. **주문 품번 확인은 회로 적합성 승인 또는 발주 승인을 뜻하지 않는다.**

로컬 PDF 10개를 저장하고 파일 형식, 페이지 수, SHA256을 확인했다. [자료 목록](references/manifest.json)은 다운로드 URL·최종 URL·해시·실패한 시도를 기록한다. MAX3490E와 SM712 데이터시트는 웹으로 열람했으나 로컬 PDF 저장에는 실패했다. MAX3490E의 정확한 SOIC-8 패키지 도면 대조와 SM712 최신 원문 확보는 남아 있다.

## 주요 부품 선정표

수량은 요구사항 기준이며 새 회로도에서 RefDes와 최종 수량을 부여한다. 재고·단가·납기는 이번에 확인하지 않았다.

| 용도 | 제조사 / 주문 품번 | 수량 | 패키지 | 현재 상태 |
|---|---|---:|---|---|
| 전이중 트랜시버 | Analog Devices / MAX3490EESA+ | 2 | 8-pin narrow SOIC | 사양 지정 유지. 공식 제품 페이지·데이터시트 확인, 패키지 도면 대조 미완료 |
| UART 버퍼 | Texas Instruments / SN74LVC2G34DBVR | 2 | DBV, SOT-23-6 | 주문 품번·패키지 도면 확보 |
| 배터리 측정 스위치 | Texas Instruments / TMUX1511PWR | 1 | PW, TSSOP-14 | 주문 품번·패키지 도면 확보 |
| ADC | Texas Instruments / ADS1115IDGSR | 1 | DGS, VSSOP-10 | 주문 품번·패키지 도면 확보 |
| 통신선 TVS | Semtech / SM712.TCT | 4 | SOT-23-3 | 조건부 선정. 송수신 pair 각각 1개, 보호 협조 검토 전 |
| 통신 커넥터 | JST / SM05B-GHS-TB(LF)(SN) | 2 | GH 1.25mm, SMT side-entry, 5극 | 카탈로그 품번·치수 확보 |
| 배터리 sense 커넥터 | JST / SM02B-GHS-TB(LF)(SN) | 1 | GH 1.25mm, SMT side-entry, 2극 | 카탈로그 품번·치수 확보. 배터리 전력 공급용이 아님 |
| Pi 40핀 stacking header | SparkFun / PRT-16763 | 1 | 2×20, 2.54mm, PTH, H=16mm / tail=7.30mm | 16mm 높이 확정, 우선 품번. 제조 도면 4UCON 07005 확보, 조립 적합성은 기구 단계 확인 |

JST 공식 기본 품번은 SM05B-GHS-TB / SM02B-GHS-TB이며 카탈로그에 (LF)(SN) 라벨 표시가 명시되어 있다. 공급사 발주 표기와 BOM의 기본 품번을 함께 유지한다. MAX3490EESA+와 MAX3490ESA+는 서로 다른 제품명이므로 혼용하지 않는다. MAX3490EESA+T 등 포장형태 변경도 별도 확인한다.

### 케이블 측 부품

| 용도 | JST 품번 | HAT 쪽 케이블 단부 1세트 기준 |
|---|---|---:|
| 통신 하우징 | GHR-05V-S | 2개 |
| 배터리 sense 하우징 | GHR-02V-S | 1개 |
| 압착 단자 | SSHL-002T-P0.2 | 12개 + 작업 여유분 |

단자는 AWG 30–26, 피복 외경 0.76–1.0mm 조건이다. 위 수량은 원격 MCU 쪽 단부를 포함하지 않는다. 케이블 길이·선재·원격 커넥터가 정해지면 하네스 BOM을 별도로 만든다. 핀 번호는 커넥터 정면과 PCB 장착면을 구분해 새 회로도에서 정의한다. [JST 공식 GH 자료](https://www.jst-mfg.com/product/index.php?lang=2&series=105)

## 데이터시트 및 도면 근거

아래 페이지 번호는 PDF 파일의 1부터 세는 페이지다. TI 본문 개정일과 부록 패키지/발주표 갱신일은 다를 수 있으므로 파일 해시도 보존했다.

| 부품 | 문서와 확인 위치 | 확보 상태 |
|---|---|---|
| MAX3490E | [공식 제품 페이지](https://www.analog.com/en/products/max3490e.html), [MAX3483E–MAX3491E Rev.1, 2019-05](https://www.analog.com/media/en/technical-documentation/data-sheets/max3483e-max3491e.pdf), p.18 주문표 | 웹 열람. 로컬 다운로드 timeout/HTTP2 오류 |
| SN74LVC2G34 | [로컬 PDF](references/sn74lvc2g34.pdf), SCES359J, 2015-10. p.21 DBV0006A 외형, p.22 land pattern, p.23 stencil | 공식 TI PDF 저장. 외형 도면 시각 확인 |
| TMUX1511 | [로컬 PDF](references/tmux1511.pdf), SCDS390B, 2025-03. p.38 PW0014A 외형, p.39 land pattern, p.40 stencil | 공식 TI PDF 저장. 외형 도면 시각 확인 |
| ADS1115 | [로컬 PDF](references/ads1115.pdf), SBAS444E, 2024-12. p.51 DGS0010A 외형, p.52 land pattern, p.53 stencil | 공식 TI PDF 저장. 외형 도면 시각 확인 |
| SM712 | [공식 제품 페이지](https://www.semtech.com/products/circuit-protection/esd-protection/sm712), [Semtech 작성 데이터시트의 Mouser 사본](https://www.mouser.com/datasheet/2/761/SEMT_S_A0003609968_1-2576005.pdf), Rev.6.0, 2017-10-17. p.6 외형/land pattern, p.7 발주표 | 제조사 작성 사본 웹 열람. 공식 페이지 자료일은 2019-02-07이므로 최신 원문과 동일 개정인지 미확정 |
| JST GH | [로컬 카탈로그](references/jst-gh.pdf), p.2 PCB land/단자, p.3 기본 GH 하우징·side-entry 외형 | 공식 PDF 저장. p.3 시각 확인. p.2 패턴은 제조사 참고치임 |
| Pi 헤더 후보 | [PRT-16763 도면](references/sparkfun-prt-16763.pdf), 4UCON drawing 07005 Rev.A0, 2014-05-03 | SparkFun 공식 배포 PDF 저장·시각 확인. H=16 / A=7.30 행 사용 |
| 헤더 비교 자료 | [Samtec SSQ 외형](references/samtec-ssq-drawing.pdf), [PTH 패턴](references/samtec-ssq-footprint.pdf), [SSQ-120-03-G-D-LL](https://www.samtec.com/products/ssq-120-03-g-d-ll) | 공식 PDF 저장. 몸체 8.51mm이므로 16mm 후보의 대체품으로 확정하지 않음 |
| Pi 기구 | [Pi 5 mechanical drawing](references/pi5-mechanical.pdf), RP-008347-DS-1 | 공식 PDF 저장·시각 확인. 제조사에서 근사 참고치로 명시 |
| HAT 요구사항 | [HAT+ specification](references/hat-plus-specification.pdf), [공식 URL](https://datasheets.raspberrypi.com/hat/hat-plus-specification.pdf) | 공식 PDF 저장. Chapter 6 전기, Chapter 7 기구 |
| Pi 핀 기능 | [RP1 peripherals](references/rp1-peripherals.pdf), [공식 URL](https://datasheets.raspberrypi.com/rp1/rp1-peripherals.pdf) | 공식 PDF 저장. GPIO alternate function 대조는 2단계 |

TI 원본: [SN74LVC2G34](https://www.ti.com/lit/ds/symlink/sn74lvc2g34.pdf), [TMUX1511](https://www.ti.com/lit/ds/symlink/tmux1511.pdf), [ADS1115](https://www.ti.com/lit/ds/symlink/ads1115.pdf).

## 풋프린트 제작에 사용할 치수 기준

| 부품 | 확인한 도면 기준 | CAD 작업 시 주의 |
|---|---|---|
| SN74LVC2G34DBVR | DBV0006A, 0.95mm pitch, 최대 높이 1.45mm | 6핀 SOT-23. SM712의 3핀 SOT-23과 구분 |
| TMUX1511PWR | PW0014A, 몸체 4.3–4.5 × 4.9–5.1mm, 0.65mm pitch, 최대 높이 1.2mm | PW 14핀 선택. 다른 패키지 도면 제외 |
| ADS1115IDGSR | DGS0010A, 몸체 양변 2.9–3.1mm, 0.5mm pitch, 최대 높이 1.1mm | 기존 코드의 TSSOP/VSSOP 이름만으로 호환 판정하지 않음 |
| JST 5극 / 2극 | side-entry, 1.25mm pitch. 외형 폭 B=9.50 / 5.75mm | 장착면 기준 핀 1과 금속 고정 패드 포함. top-entry 패턴과 혼용 금지 |
| PRT-16763 | 2.54mm grid, 도면 권장 구멍 Ø1.02mm, 16mm 몸체/7.30mm tail | PCB 하부 장착 시 번호 반전 확인. 도금 후 홀, 삽입 깊이, 스페이서 공차 확인 필요 |

3D STEP 모델은 아직 내려받거나 제작하지 않았다. JST 제품별 2D/STEP은 이메일 정보 제출 방식이며, 공개 카탈로그로 이번 치수 수집을 진행했다. 이후 3D 모델을 만들 때는 단순 기구 확인용 모델임을 표시하고 제조 풋프린트 검증과 구분한다.

## 확정하지 않은 항목과 후속 작업

1. **MAX3490E SOIC-8 도면:** 데이터시트 p.2 패키지 표에는 14핀 항목이 있어 선택한 8핀 품번에 그대로 적용하면 안 된다. 정확한 8핀 외형/land drawing 확보와 품번 대응 확인 전 풋프린트를 승인하지 않는다. 21-0041/90-0096 도면 URL도 다운로드 실패했으며 검증된 도면으로 취급하지 않는다.
2. **SM712:** 정확한 제조사 품번은 정했으나 최신 공식 원문 개정 확인이 남았다. 12V/-7V working voltage와 실제 클램핑 전압은 다르므로 MAX3490E 보호 적합성은 2단계에서 판정한다.
3. **헤더와 냉각장치:** 사용자 지시로 16mm 높이를 확정했다. 공식 HAT+는 최소 15mm, 이상적 16mm 보드 간 스페이서를 권장한다. 헤더 표기 높이를 실제 보드 간격과 동일하다고 단정하지 않고 Pi 헤더 삽입 깊이, HAT 하부 부품, 냉각장치와 함께 조립 검토한다.
4. **HAT+ ID EEPROM:** 기존 사양의 미정 상태를 유지한다. EEPROM 없는 확장보드를 정식 HAT+ 준수 설계로 표시하지 않는다.
5. **RAW_BAT surge 보호:** 사양상 미정. 현재 TVS 선정은 통신선용이며 배터리 입력 보호 선정은 별도다.
6. **수동소자:** 47k+47k/18k 0.1%, 1µF, 100nF, RX 120Ω, 680Ω DNP, TX 47k, 전원 0Ω 요구사항은 유지한다. 47–100Ω 직렬저항 선택, 저항 정격·TCR·허용오차, MLCC 정격전압·DC bias·유전체를 2단계에서 계산한 뒤 제조사 품번을 부여한다. 완성 BOM으로 표시하지 않는다.

이번 자료로 TI·JST·Pi 연결부의 상세 검토는 진행할 수 있다. 전체 부품과 풋프린트의 최종 확정에는 위 미해결 항목을 닫아야 한다.
