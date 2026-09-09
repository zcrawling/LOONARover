from pathlib import Path
import json
import sqlite3

p = Path(__file__).resolve().parents[3]/'data/apriltag_gt/analysis_20260909/classification'
r = json.loads((p/'results.json').read_text())
labels = {'imu_vibration':'IMU 진동', 'wheel_only':'Wheel odom', 'combined':'IMU + Wheel odom'}
terrain = {'rough_paving':'거친 포장', 'stone_asphalt':'돌·아스팔트', 'grass_soil':'잔디·흙'}
sections = ['# Terrain Feature Separability\n\n현재 주행 기록에는 노면 구간을 구분하는 정보가 있다. 다만 같은 토양의 다른 장소·날짜까지 일반화되거나, 보정계수 C를 정확히 예측한다는 검증은 아니다.']
table = '| 입력 | 맞힌 bag | 클래스 균형 bag 정확도 | 1초 구간 균형 정확도 |\n|---|---:|---:|---:|\n'
for k,label in labels.items():
    s=r[k]
    table += f"| {label} | {round(s['bag_accuracy']*10)}/10 | {s['balanced_bag_accuracy']:.1%} | {s['balanced_window_accuracy']:.1%} |\n"
sections.append('## 특징으로 구간을 구분할 수 있는가?\n\n'+table+'\n10개 bag, 3개 시각적 노면 그룹, 총 '+str(sum(x['windows'] for x in r['included_runs']))+'개 중첩 구간이다. 균형 정확도는 클래스별 재현율의 평균이다. 구간 지표는 각 bag 안의 구간 정확도를 먼저 평균한 뒤 클래스별 평균을 동일 가중한다. 독립 표본 수는 구간 수가 아니라 bag 수에 가깝다. 표는 세 입력 조합의 정확한 수치 비교를 위해 사용했다.')
rows='| 실제 그룹 | 잔디·흙으로 예측 | 거친 포장으로 예측 | 돌·아스팔트로 예측 |\n|---|---:|---:|---:|\n'
for label,counts in zip(r['combined']['classes'],r['combined']['confusion']):
    rows+='| '+terrain[label]+' | '+' | '.join(map(str,counts))+' |\n'
sections.append('## 잔디·흙과 거친 포장은 구분되지만 돌·아스팔트가 겹친다\n\n'+rows+'\n결합 입력의 bag 판정이다. 17:30:07은 거친 포장, 17:33:15는 잔디·흙으로 오분류했다. 잔디·흙 두 bag에서는 각각 구간의 96.3%, 90.0%를 맞혔다. 돌·아스팔트는 bag 다수결로 맞히더라도 구간 판정이 흔들린다. 따라서 매초 안정적인 노면 판별이 완성됐다고 해석하면 안 된다.')
sections.append('## 검증 방식과 입력\n\nbag 하나 전체를 시험용으로 빼고 나머지로 학습하는 검증을 10회 수행했다. 같은 bag의 인접 구간은 학습과 시험에 섞이지 않는다. 표준화와 클래스 중심 모두 학습 bag만 사용하고 긴 bag이 학습을 지배하지 않도록 bag별 동일 가중했다. 분류기는 고정된 표준화 최근접 클래스 중심이며 파라미터 탐색은 하지 않았다.\n\nIMU 6축에서 표준편차, 차분 RMS, MAD, 범위, 첨도, 2–10 / 10–25 / 25–45 Hz 대역 에너지 등 48개 특징을 추출했다. Wheel은 /wheel/odom의 vx와 wz 평균·표준편차·범위·차분 RMS 8개다. 원시 좌우 모터 tick 분류 실험은 아니다. IMU 원시 평균, 영상, 태그 이동량, C, 파일 이름, 시간은 분류 입력으로 사용하지 않았다.\n\n1초 창, 0.5초 간격으로 추출했다. IMU 80개 이상, wheel 35개 이상, 내부 표본 간격 50ms 이하, wheel vx > 0.02m/s인 비율 80% 이상인 창을 사용했다. IMU를 100Hz로 보간했다. 정지와 주행 사이 과도 구간을 완전히 제거했다고 보장할 수 없다.')
sens='| 입력 | 짧은 bag 제외 후 맞힌 bag | 균형 bag 정확도 | 구간 균형 정확도 |\n|---|---:|---:|---:|\n'
for k,label in labels.items():
    s=r['at_least_five_windows']['scores'][k]
    sens+=f"| {label} | {round(s['bag_accuracy']*8)}/8 | {s['balanced_bag_accuracy']:.1%} | {s['balanced_window_accuracy']:.1%} |\n"
sections.append('## 짧은 실패 기록과 우연 일치 점검\n\n'+sens+'\n유효 창 5개 미만인 두 bag을 제외한 민감도 분석이다. 짧은 bag을 넣어야만 나오는 결과는 아니다. 다만 표본이 더 줄고 학습 중심도 바뀌므로 높은 수치를 최종 성능으로 선택하지 않는다.\n\nbag 단위 라벨을 199회 섞어 재학습한 순열검정에서 균형 bag 정확도 기준 p는 IMU 0.025, wheel 0.030, 결합 0.005였다. 세 입력 비교에 대한 보수적 Bonferroni 보정은 각각 0.075, 0.090, 0.015다. 같은 장소·시간에 연속 수집한 bag의 교환가능성 한계 때문에 이 값은 탐색적 근거다. 독립 노면 실험의 통계적 확증으로 사용하지 않는다.')
sections.append('## 데이터 범위와 해석의 한계\n\n노면 라벨은 이전 분석에서 영상 장면을 보고 묶은 시각적 그룹이다. 사용자가 확인한 토양 재질 정답이 아니다. 같은 그룹은 장소·수집시간·배터리·주행 상태도 비슷하므로 이 요인과 토양 효과를 분리하지 못했다. 특히 잔디·흙은 두 bag뿐이다. 실내, 블록포장, 아스팔트, 입구 타일은 각 한 bag이라 새 bag 일반화 검증에서 제외했다.\n\n사용자가 제외한 tag_20260909_173746_028090 오르막은 추출부터 제외했다. 실패 종료된 시험도 유효한 IMU/wheel 주행 창은 살렸다. 카메라 실패 자체로 센서 창을 버리지 않았다. 센서가 없는 기록이나 충분한 주행 창이 없는 기록은 이 분석에 기여할 수 없다.\n\n현재 결과는 구간 특징의 구분 가능성을 지지한다. LIMO에서 얻은 특징이 최종 로버의 BNO085와 다른 기구에서도 그대로 유지된다는 근거는 없다.')
sections.append('## C 추정으로 이어갈 판단\n\n특징 추출을 계속 시험할 근거는 있다. 그러나 노면 분류 성공과 C 예측 성공은 별도다. 서로 다른 노면이 같은 C를 가질 수도 있고, 같은 노면에서도 슬립과 하중에 따라 C가 달라질 수 있다. 필요한 것은 C가 달라지는 조건에서 특징도 재현성 있게 달라지는 관계다.\n\n다음 검증은 동일 속도에서 3개 노면의 순서를 섞어 각 여러 독립 주행을 수집하고, 다른 위치·날짜의 주행 전체를 시험용으로 남기는 것이다. 카메라 GT가 유효한 구간에 대해서만 C를 만들고, 학습 평균 상수 C 대비 시험 bag의 거리 오차가 줄어드는지 비교해야 한다. 이번 결과로 런타임 보정이나 EKF 값을 변경하지 않았다.')
source={'id':'analysis','title':'Whole-bag terrain separability analysis','path':'data/apriltag_gt/analysis_20260909/classification/results.json','query':{'language':'python','engine':'Python / NumPy / rosbags','sql':"from pathlib import Path\nimport runpy\nrunpy.run_path('tools/analysis/20260909/classify.py', run_name='__main__')",'description':'Extract raw IMU and wheel odom features; whole-bag held-out nearest-centroid classification.','tables_used':['data/apriltag_gt/analysis_20260909/runs.json','data/apriltag_gt/tag_*/remote/**/bag'],'filters':['Exclude tag_20260909_173746_028090','Moving, adequately sampled windows only','At least two eligible bags per class']}}
artifact={'surface':'report','manifest':{'version':1,'title':'Terrain Feature Separability','blocks':[dict(id=f's{i}',type='markdown',body=s,sourceId='analysis') for i,s in enumerate(sections)],'sources':[source]},'snapshot':{'status':'ready','datasets':{}},'sources':[source]}
(p/'artifact.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2))
source['query']['tables_used'][-1]='data/apriltag_gt/tag_*/rover/bag'
chart={'id':'window_accuracy','title':'결합 입력의 bag별 구간 정확도','subtitle':'2026-09-09 · 전체 bag을 제외해 예측한 1초 창의 정답 비율 · 10개 bag','type':'bar','dataset':'bag_details','sourceId':'analysis','valueFormat':'percent','encodings':{'x':{'field':'time','type':'nominal','label':'시험 시작 시각'},'y':{'field':'accuracy','type':'quantitative','label':'구간 정확도'},'tooltip':[{'field':'terrain','type':'nominal','label':'영상 기준 그룹'},{'field':'windows','type':'quantitative','label':'창 수'}]}}
artifact['manifest']['charts']=[chart]
artifact['snapshot']['version']=1
artifact['manifest']['blocks'].insert(3,{'id':'accuracy_chart','type':'chart','chartId':'window_accuracy'})
artifact['snapshot']['datasets']['bag_details']=[{'time':d['run_id'].split('_')[2],'terrain':terrain[d['actual']],'accuracy':d['window_accuracy'],'windows':d['windows'],'predicted':terrain[d['predicted']]} for d in r['combined']['details']]
sql="SELECT json_extract(value, '$.run_id') AS run_id, json_extract(value, '$.actual') AS terrain, json_extract(value, '$.window_accuracy') AS accuracy, json_extract(value, '$.windows') AS windows FROM json_each(?, '$.combined.details')"
db=sqlite3.connect(':memory:')
queried=db.execute(sql,[(p/'results.json').read_text()]).fetchall()
assert [x[2] for x in queried]==[x['accuracy'] for x in artifact['snapshot']['datasets']['bag_details']]
chart_source={'id':'chart_query','label':'Per-bag predictions from Python classification results','path':'data/apriltag_gt/analysis_20260909/classification/results.json','query':{'engine':'SQLite JSON1','language':'sql','sql':sql,'description':'Bind results.json as the first parameter. This query selects reviewed outputs of classify.py; it does not replace the raw-bag extraction and whole-bag validation provenance in the analysis source.','tables_used':['data/apriltag_gt/analysis_20260909/classification/results.json']}}
chart['sourceId']='chart_query'
artifact['manifest']['sources'].append(chart_source)
artifact['sources'].append(chart_source)
(p/'artifact.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2))
(p/'chart_contract.md').write_text('Question: Does whole-bag voting hide unstable local predictions?\nTen held-out bag accuracy bars, one row per bag, chronological order. Canonical bar in portable HTML; single default blue root, no color grouping, labels identify bags. Rates use fractional units and a zero baseline. Source: results.json combined.details. Final QA: packaged delivery verifier.\n')
(p/'README.md').write_text('\n\n'.join(sections))
notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'cells':[{'cell_type':'markdown','metadata':{},'source':['# Whole-bag terrain classification audit\n','Run from this directory using a Python environment with numpy and rosbags. Re-extraction reads local bags. See classify.py for all feature and split definitions.']} ,{'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':['from pathlib import Path\n','import json, runpy\n',"runpy.run_path('classify.py', run_name='__main__')\n","r = json.loads(Path('results.json').read_text())\n","assert len(r['included_runs']) == 10\n","assert all('173746_028090' not in x['run_id'] for x in r['included_runs'])\n","for key in ['imu_vibration', 'wheel_only', 'combined']:\n","    print(key, r[key]['bag_accuracy'], r[key]['balanced_window_accuracy'])\n"]}]}
(Path(__file__).resolve().parent/'audit.ipynb').write_text(json.dumps(notebook,ensure_ascii=False,indent=2))
