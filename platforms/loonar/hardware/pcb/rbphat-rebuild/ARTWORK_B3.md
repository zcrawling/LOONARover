# RBPHAT B3 아트웍 완료 보고

2026-09-06. B2 회로와 확정 기구 조건을 유지하여 부품 배치, 배선, 접지면, 실크 및 제조 파일을 완성했다. 현재 편집 원본은 [rbphat.kicad_pro](rbphat.kicad_pro) / [rbphat.kicad_pcb](rbphat.kicad_pcb)다. B2의 미연결 161개와 아트웍 미착수 표기는 과거 상태다.

## 최종 검사

| 항목 | 결과 |
|---|---:|
| 회로도 ERC 오류 / 경고 | 0 / 0 |
| PCB DRC 위반 | 0 |
| 미연결 | 0 |
| 회로도와 PCB 불일치 | 0 |
| 별도 확인한 회로 핀 연결 | 240개 |
| 실장 부품 | 상면 SMD 62개 + 하면 PTH 소켓 1개 |
| 선택 실장 / 테스트 포인트 | DNP 2개 / 7개 |
| 배선 세그먼트 / 관통 비아 | 518개 / 67개 |
| 내부 접지면 | In1·In2 각각 연결된 구리 영역 1개 |

[검증 요약](artwork/validation.json), [DRC 원문](artwork/final-drc.json), [ERC 원문](validation/erc.rpt). DRC 예외 목록과 KiCad 기본 비활성 검사도 원문에 보존했다. 미연결을 제외 처리하거나 간격 규칙을 완화해서 통과시키지 않았다.

## 배치와 전기 경로

오른쪽에 CTRL/PAYLOAD 통신 커넥터와 각 트랜시버를 두고, TVS와 10Ω 직렬저항을 가까이 배치했다. 통신선은 상면에서 연결했다. TVS 접지 스텁은 0.5mm로 보강하고 가까운 비아로 내부 GND에 연결했다. RX 120Ω R107/R207은 기존 회로대로 기본 DNP다.

왼쪽에 배터리 분압·TMUX·ADC를 모아 통신 커넥터 경로와 분리했다. 각 SMD GND에는 가까운 접지 연결을 만들었고 디커플링 연결을 먼저 배선했다. 전원 격리 전후의 네트를 분리한 상태로 LM66100 CE=VOUT, TCA9517 A/B 전원, TMUX 전후 입력, Pi 미사용 5V/ID 핀을 별도 확인했다.

F.Cu/B.Cu에 신호와 전원을 배선하고 **In1.Cu/In2.Cu 모두 연속 GND**로 사용했다. 이는 B2의 In2 전원층 초안에서 변경한 사항이다. 상·하면 신호에 각각 가까운 접지 기준면을 제공하며 절연 전원을 의미하지 않는다. 일반 배선은 0.25mm, 전원 주 경로는 0.5mm, 일부 미세 피치 탈출 및 전원 연결은 0.2mm다. 최소 구리 간격은 0.2mm를 유지했다.

통신 목표는 기존 2Mbps다. 이 보드는 120Ω 제어 임피던스 배선을 인증한 설계가 아니며, THVD1451의 소자 정격인 50Mbps를 보드 검증 속도로 표기하지 않는다. 링크 종단과 케이블은 실제 원격 장치 조건에 맞춰 시험한다.

## 기구·실장 기준

65×56mm, R3 모서리, 두께 공칭 1.6mm, 4층 구리 각 35µm. 홀은 NPTH 2.75mm 4개이며 나사 주변 지름 6.2mm 구리 금지 영역을 유지했다. J1은 하면 PRT-16763, 몸체 16mm, 보드 간격 공칭 19mm / M2.5 19mm 스페이서 기준이다. 공식 Raspberry Pi Active Cooler를 사용하고 하면에 추가 회로 부품은 없다.

J2/J3: 1 TX+, 2 TX−, 3 RX+, 4 RX−, 5 GND. J4: 1 BAT+, 2 GND, 0–12.6V 감지 전용. 하면 실크에도 핀맵과 적층 높이를 표기했다. 소켓의 3D 모델은 외형 검토용이며 접점 제조 형상을 재현하지 않는다.

## 전달 파일

- [상면 3D](artwork/top-3d.png), [하면 3D](artwork/bottom-3d.png)
- [4개 구리층 PDF](artwork/copper-layers.pdf), [상면 조립 도면](manufacturing/assembly/top-assembly.pdf)
- [제조 ZIP](manufacturing/RBPHAT-B3-fabrication.zip): 4개 구리층, 앞뒤 마스크·실크, 외곽, PTH/NPTH 드릴, 제조 조건
- [실장 BOM](manufacturing/assembly/fitted-bom.csv), [상면 실장 좌표](manufacturing/assembly/top-placement.csv), [기본 실장용 페이스트](manufacturing/assembly/rbphat-F_Paste.gtp)
- [프로젝트 인계 ZIP](manufacturing/RBPHAT-B3-project.zip): KiCad 원본, 로컬 심볼/풋프린트/모델, 검증 기록, BOM과 인계 문서

페이스트 파일은 R107/R207의 개구를 제외한 기본 DNP 조립용이다. 실장 좌표는 상면 62개만 포함하며 테스트 포인트·장착홀·하면 수작업 소켓·DNP를 제외한다. 좌표 기준은 보드 좌상단 (100,100)mm의 출력 원점이며 X는 오른쪽, Y는 위쪽이라 보드 안 Y는 음수다. 조립업체 품번별 회전 기준은 조립 도면과 대조한다.

## 검증 범위

현재 CAD에서 단락·미연결·설정된 간격/폭 위반은 검출되지 않았다. **실물까지 전기적 결함이 전혀 없다고 보증하는 결과는 아니다.** 제조업체 적층·도금·완성 홀 공차 확인, 첫 조립의 소켓 삽입/냉각 간섭, 전원 차단 시 ADC 입력 과도응답·역급전, 배터리 측정 교정, 실제 케이블에서의 통신/EMC 시험은 시제품 검증 단계다. 기존 정상 극성·공통 GND·0–12.6V 조건을 벗어나는 역극성이나 load dump 보호를 추가한 것은 아니다.

최종 검사는 `validate_schematic.py`, KiCad `pcb drc --schematic-parity`, `validate_artwork.py` 순서로 재실행한다. `create_board_start.py`, `layout_board.py`, `seed_routing.py`, `finish_connections.py`는 제작 이력 재현용이며 현재 완성 보드에 다시 실행하면 배치·배선을 초기화하거나 중복시킬 수 있다. 최종 인계 ZIP을 먼저 보존한다.
