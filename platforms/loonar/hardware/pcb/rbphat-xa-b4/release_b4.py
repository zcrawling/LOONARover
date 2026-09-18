"""Refresh B4 purchasing and release documentation from current components."""
import csv,json,collections
from pathlib import Path
P=Path(__file__).resolve().parent
cs=json.loads((P/'components.json').read_text())
def csvout(path,fields,rows):
 with (P/path).open('w',newline='') as f:
  w=csv.writer(f);w.writerow(fields);w.writerows(rows)
fitted=[c for c in cs if not c['reference'].startswith(('TP','SH')) and not c['dnp']]
assert len(fitted)==65
rows=[[c['reference'],c['value'],c['mpn'],c['footprint'],'PTH bottom' if c['reference']=='J1' else 'PTH top' if c['reference'].startswith('J') else 'SMT top','FIT'] for c in fitted]
csvout('manufacturing/assembly/fitted-bom.csv',['Reference','Value','MPN','Footprint','Assembly','Status'],rows)
csvout('procurement_bom.csv',['Reference','Value','MPN','Footprint','Assembly','Status'],rows)
csvout('manufacturing/assembly/harness-bom.csv',['Item','MPN','Quantity','Notes'],[['J2/J3 mating housing','XAP-06V-1',2,'6 positions'],['J4 mating housing','XAP-02V-1',1,'2 positions'],['Crimp contact','SXA-001T-P0.6',14,'AWG28-22; insulation OD 0.8-1.9 mm; order spares'],['SH1 chassis bond','M3 ring terminal and hardware',1,'Choose terminal for chassis wire gauge; washer OD <=8 mm; see fabrication notes']])
(P/'resolved_bom.json').write_text(json.dumps(cs,indent=2)+'\n')
(P/'footprint_audit.json').write_text(json.dumps(json.loads((P/'validation/validation.json').read_text())['footprint_pad_number_checks'],indent=2)+'\n')
notes='''# RBPHAT B4 — fabrication and assembly instructions

Current design: rbphat-xa-b4/rbphat.kicad_pcb. Do not mix B3 or earlier manufacturing files with this release.

- 65 x 56 mm, corner radius 3 mm; 4-layer FR4, nominal finished thickness 1.6 mm. Follow supplied stackup; In1.Cu and In2.Cu are GND planes. Confirm actual dielectric/copper stack with fabricator. No controlled impedance specification.
- Minimum trace/clearance 0.20 mm; via diameter/drill 0.60/0.30 mm; board edge copper clearance 0.30 mm. Do not shrink clearances or alter drill geometry.
- J1: 40 plated holes, finished diameter 1.02 mm. Confirm finished-hole tolerance fits PRT-16763 pins before manufacture.
- J2/J3/J4: 14 plated holes, finished diameter 0.95 +/-0.05 mm (manufacturer reference 0.9 +0.1/-0 mm). THREE unplated hook slots, 2.8 x 2.0 mm. Slots MUST be routed, not replaced with round holes. Four separate mounting holes are NPTH diameter 2.75 mm.
- SH1: one plated 3.2 mm hole, 6.4 mm copper pad, dedicated CHASSIS net. Both inner GND planes have a local exclusion. Do not connect CHASSIS to board GND, mounting holes, or Pi rails.
- Total drills: 126 plated (71 vias, 40 J1, 14 XA, 1 SH1); 7 unplated features (4 mounting holes, 3 slots).
- 61 top SMT parts. R107 and R207: 120 ohm, FITTED; both appear in paste and placement. No DNP parts in this release.
- Four PTH connectors: J1 on bottom; J2/J3/J4 on top. PTH connectors are intentionally absent from top-placement.csv. Match pin 1 in the native board and assembly drawing; verify assembly-house rotation conventions.
- J2/J3: S06B-XASK-1(LF)(SN), horizontal JST XA with hook, facing right/outward. J4: S02B-XASS-1(LF)(SN), horizontal JST XA with hook, facing left/outward. Do not substitute vertical or hookless versions.
- J2/J3 physical pin order: 1 TX+, 2 TX-, 3 RX+, 4 RX-, 5 GND, 6 SHIELD/CHASSIS. J4: 1 BAT_RAW, 2 GND. Wire by molded pin number, not by an assumed viewing direction.
- Housings: XAP-06V-1 x2 and XAP-02V-1 x1. SXA-001T-P0.6 contacts x14 plus spares. Apply JST crimp instructions and verify retention.
- SH1 requires a ring-terminal wire to the external chassis. Use M3 hardware, maximum washer OD 8 mm; keep all underside terminal/hardware protrusion <=3.5 mm. Prevent loose hardware and unintended contact to surrounding conductors. Actual chassis bonding and fit require first-article inspection.
- Keep the 16 mm socket body (PRT-16763) and nominal 19 mm PCB spacing. Pi 5 official Active Cooler; no underside components except J1. Nominal cooler envelope leaves 5.3 mm under HAT, before hardware/tolerances. Confirm actual insertion, spacers, screw/terminal clearance and cooling airflow on first assembly.
- Connector molded envelope height 7.6 mm. Mating housings project approximately 5.9 mm beyond board edge, plus wire bend/strain-relief space. Enclosure must provide this clearance.
- 3D XA files are simplified nominal envelope models, not manufacturer detailed solids. Fabrication geometry comes from the footprint and manufacturer drawing.
- Battery conversion ratio 8.222222; intended normal input 0–12.6 V. Firmware must use this ratio. 2 Mbps communication, power-off/backfeed behavior, thermal/EMC performance and mechanical fit need prototype measurements.

CAD validation: ERC 0 errors/0 warnings, PCB DRC 0, unrouted 0, schematic parity 0. This is a prototype fabrication release, not physical qualification. Obtain fabrication/assembly DFM acknowledgement, particularly finished holes, slots and connector orientation.

Manufacturer drawing: https://www.jst-mfg.com/product/pdf/eng/eXA-WB.pdf (local references/jst-xa.pdf).
'''
(P/'manufacturing/FABRICATION_NOTES.md').write_text(notes)
report='''# RBPHAT B4 — 수평형 JST XA 변경 완료

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
'''
(P/'ARTWORK_B4.md').write_text(report)
(P/'README.md').write_text(report)
old=['ARTWORK_B3.md','DESIGN_REV_B.md','ELECTRICAL_REVIEW.md','PRE_LAYOUT_READY.md','footprint-review.pdf','mechanical-review.pdf','electrical_calculations.json','rev_b_calculations.json']
(P/'history-b3').mkdir(exist_ok=True)
for fn in old:
 f=P/fn
 if f.exists():f.rename(P/'history-b3'/fn)
print('B4 BOM and documents updated')
