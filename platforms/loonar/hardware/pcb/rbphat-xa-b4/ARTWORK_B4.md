# RBPHAT B4 — 수평형 JST XA 변경 완료

J2·J3은 수평형 JST XA 6핀, J4는 수평형 JST XA 2핀으로 변경했다. J1 Raspberry Pi 40핀 소켓은 유지한다. J2/J3의 6번은 CHASSIS 전용이며 SH1 M3 도금 체결점으로 연결되고 보드 GND와 분리되어 있다. R107/R207 120Ω은 기본 실장이다.

회로도 4장, 회로 항목 73개, 핀 연결 243개를 검증했다. ERC 오류/경고 0, PCB DRC 위반 0, 미연결 0, 회로도–PCB 불일치 0. 실제 실장 부품은 SMT 61개와 PTH 커넥터 4개이다. 7개 테스트포인트와 SH1은 PCB 형상이다.

제조 자료는 manufacturing 폴더에 있으며, 발주 전 FABRICATION_NOTES.md의 완성 홀 치수·XA 고정 슬롯·조립 방향을 업체와 확인해야 한다. 19mm 적층 및 공식 Active Cooler 조건을 유지한다. XA 플러그와 케이블은 보드 바깥 공간이 필요하다. SH1 링터미널 및 M3 하드웨어는 별도 조립한다.

CAD 검증은 완료했지만 실물 전원 차단·역급전·2Mbps 통신·냉각·기구 결합 시험은 아직 수행하지 않았다. XA 3D 형상은 공칭 외형 확인용 단순 모델이다.

- `rbphat.kicad_pcb`: 현재 PCB
- `rbphat.pdf`: 현재 4장 회로도
- `artwork/validation.json`: 핀·배선·제조 데이터 검증 결과
- `artwork/final-drc.json`: KiCad DRC 원본
- `manufacturing/assembly/fitted-bom.csv`: 실장 BOM
- `manufacturing/assembly/harness-bom.csv`: 케이블 및 섀시 체결 부품
- `manufacturing/RBPHAT-B4-fabrication.zip`: PCB 제조 파일
- `manufacturing/RBPHAT-B4-project.zip`: 편집 원본 및 조립 자료 포함

B3에서 복사된 과거 검토 자료는 history-b3 폴더에 보관하며 이번 발주 기준에 포함하지 않는다. 생성/배선 스크립트는 중간 작업 도구이며, 일괄 재실행하면 수동 마감 배선이 사라질 수 있다. 현재 PCB와 검증 결과가 납품 기준이다.
