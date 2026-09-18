from pathlib import Path
import json,csv,base64,html
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'data/apriltag_gt/analysis_20260910'
D=json.loads((OUT/'correlations.json').read_text());A=json.loads((OUT/'audit.json').read_text())
S=json.loads((OUT/'strict_windows.json').read_text());E=json.loads((OUT/'screened_windows.json').read_text())
ids=sorted({r['run'] for r in E});colors={i:plt.get_cmap('tab10')(n) for n,i in enumerate(ids)}
def label(i):return i[13:15]+':'+i[15:17]+':'+i[17:19]
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(figsize=(9,4))
for k,i in enumerate(ids):
 e=[r['C'] for r in E if r['run']==i];s=[r['C'] for r in S if r['run']==i]
 ax.scatter([k+.1]*len(e),e,s=65,facecolors='none',edgecolors=[colors[i]],label='Screened (not independent of strict)' if k==0 else None)
 ax.scatter([k-.1]*len(s),s,s=35,color=colors[i],label='Strict' if k==0 else None)
ax.axhline(1,color='gray',ls='--');ax.set_xticks(range(len(ids)),[label(i) for i in ids]);ax.set_ylabel('C = camera speed / wheel speed');ax.set_title('Non-overlapping 3 s windows, commanded speed 0.1 m/s');ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2);fig.tight_layout();fig.savefig(OUT/'c_windows.png',dpi=160);plt.close(fig)
names=['vx_std','ay_power_10_25','az_power_10_25'];fig,axs=plt.subplots(2,3,figsize=(12,7))
for row,(tier,rows) in enumerate([('strict',S),('screened',E)]):
 for col,n in enumerate(names):
  ax=axs[row,col];stats=next(x for x in D[tier+'_0.1']['ranking'] if x['feature']==n)
  for i in sorted({r['run'] for r in rows}):
   subset=[r for r in rows if r['run']==i];x=[r['features'][n] for r in subset];y=[r['C'] for r in subset]
   ax.scatter(x,y,color=colors[i],s=22,alpha=.45)
   ax.scatter(np.mean(x),np.mean(y),color=colors[i],marker='D',s=65,edgecolors='black',linewidth=.5,label=label(i))
  ax.set_xlabel(n);ax.set_ylabel('C');ax.set_title(f"{tier}: bag rho={stats['bag_spearman']:.2f}, window rho={stats['pooled_spearman']:.2f}",fontsize=9);ax.ticklabel_format(axis='x',style='sci',scilimits=(-2,2));ax.grid(alpha=.2)
axs[1,2].legend(fontsize=7);fig.suptitle('Diamonds = bag means; small dots = individual windows. Ranking is exploratory.');fig.tight_layout();fig.savefig(OUT/'correlations.png',dpi=150);plt.close(fig)
for tier,rows in [('strict',S),('screened',E)]:
 flat=[{**{k:v for k,v in r.items() if k not in ['features','rejections']},**r['features']} for r in rows]
 if flat:
  with (OUT/(tier+'_samples.csv')).open('w') as f:w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
 with (OUT/(tier+'_correlations.csv')).open('w') as f:
  rankings=D[tier+'_0.1']['ranking'];w=csv.DictWriter(f,fieldnames=list(rankings[0]));w.writeheader();w.writerows(rankings)
def image(name):return '<img alt="'+name+'" src="data:image/png;base64,'+base64.b64encode((OUT/name).read_bytes()).decode()+'">'
def table(rows):return '<table>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</table>'
comp=[['Feature','strict bag ρ','strict window ρ','screened bag ρ','strict FDR q']]
for n in names:
 a=next(r for r in D['strict_0.1']['ranking'] if r['feature']==n);b=next(r for r in D['screened_0.1']['ranking'] if r['feature']==n)
 comp.append([n,f"{a['bag_spearman']:.3f}",f"{a['pooled_spearman']:.3f}",f"{b['bag_spearman']:.3f}",f"{a['fdr_q']:.3f}"])
audit=[['시작','명령 m/s','strict 구간','screened 구간','설명']]
for n in A['runs']:
 i=n['run'];cs=[r for r in A['candidates'] if r['run']==i];ss=sum(r['run']==i for r in S);es=sum(r['run']==i for r in E)
 reasons=Counter(v for r in cs for v in r.get('rejections',{}).get('strict',[]))
 desc=n['status'] if n['status']!='reviewed' else ('3초 정상 구간 없음' if not cs else ', '.join(f'{k}:{v}' for k,v in reasons.items()) or '통과')
 audit.append([label(i),n.get('speed','—'),ss,es,desc])
best=D['screened_0.1']['ranking'][:5]
extra=[['보조 기준 상위 특징','bag ρ','구간 ρ','FDR q']]+[[r['feature'],round(r['bag_spearman'],3),round(r['pooled_spearman'],3),round(r['fdr_q'],3)] for r in best]
body=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>9월 10일 C 상관 분석</title><style>body{{max-width:1120px;margin:40px auto;padding:0 24px;font:17px/1.7 sans-serif;color:#21313d}}h1,h2{{line-height:1.3}}h2{{margin-top:40px}}img{{width:100%;height:auto}}table{{width:100%;border-collapse:collapse;font-size:14px}}td{{border-bottom:1px solid #cdd4d9;padding:9px;text-align:left}}tr:first-child{{font-weight:bold;background:#edf2f6}}.lead{{padding:22px;background:#eef5f8;border-left:5px solid #3d7187}}code{{overflow-wrap:anywhere}}@media(max-width:700px){{body{{padding:0 12px}}table{{font-size:11px}}}}</style>
<h1>오늘 C 상관 분석: 표본은 늘었지만, bag 평균의 강한 관계가 구간별 관계로 이어지지 않는다</h1>
<p>2026-09-10 · 원본 bag·명령 이벤트·카메라 GT · 노면 분류가 아닌 IMU/Encoder → C 탐색</p>
<div class="lead"><b>결론:</b> 엄격한 품질 기준으로 5개 bag / 7개 비중첩 3초 구간, 보조 기준으로 7개 bag / 12개 구간을 확보했다. 이전 2개 구간보다 관계를 검토할 근거가 늘었다. 그러나 엄격한 표본에서 encoder vx 표준편차와 C의 bag 평균 순위상관 1.0이 보조 표본에서는 0.18로 낮아졌다. IMU 10–25 Hz 후보도 개별 구간에서는 거의 상관이 없다. 현재 결과만으로 특징 기반 C 스위칭·회귀를 적용할 근거는 부족하다.</div>
<h2>C와 독립 표본을 먼저 구분했다</h2>
<p>C = 같은 시각에서 적합한 카메라 이동 속도 / 누적 wheel 거리의 속도. C &gt; 1은 이 카메라 기준에서 엔코더가 거리를 작게 잡는다는 뜻이며, 곧바로 슬립 크기라는 뜻은 아니다. 카메라 배율·원근·초점에 의한 오차도 C에 들어간다. bag마다 여러 창을 만들어 표본 수를 부풀리지 않도록 비중첩 창만 사용했고, 순위상관 검정은 bag 평균을 단위로 했다. 구간 상관은 별도 기술통계로 제시했다.</p>
<h2>같은 속도에서 분석 가능한 자료가 늘었다</h2>
<p>오늘 날짜 폴더 17개(root/old/fail 포함)를 조사했고 16개에서 bag과 카메라 기록이 있었다. 0.1/0.3/0.5 m/s를 섞지 않았다. 0.3·0.5 m/s 시험은 시작 후 2초와 정지 전 0.5초를 제외하면 3초 창이 없어 이번 비교에 들어가지 않았다. 실패 종료한 시험도 앞부분이 통과하면 포함했다.</p>
{image('c_windows.png')}
<p>엄격 기준의 bag 평균 C는 약 1.014–1.083이다. 17:08:09 같은 bag 안에서도 C=1.009와 1.073 두 구간이 남았다. 작은 직선 적합 잔차가 거리 배율의 정확성을 보증하지 않으므로 이 차이를 곧바로 실제 노면 변화로 해석하지 않았다.</p>
<h2>높은 bag 상관을 바로 제어 규칙으로 쓰면 안 된다</h2>
{table(comp)}
{image('correlations.png')}
<p>vx_std는 엄격 표본 5개 bag에서 순위가 완전히 일치했다. 하지만 개별 7개 창의 ρ는 0.464이고, 보조 기준 7개 bag에서는 0.179다. ay/az의 10–25 Hz power는 엄격 bag ρ=0.9이지만 구간 ρ는 각각 약 0.07, −0.11이다. 특정 구간에서 진동이 커지면 즉시 C를 올리는 규칙으로 옮길 수 있는 결과가 아니다.</p>
<p>bag 내 평균을 뺀 관계도 계산했지만 엄격 표본에서 반복 창이 있는 bag은 2개뿐이다. 그 안의 강한 음의 상관 또한 안정적인 역관계의 증거로 삼지 않았다. 서로 반대인 bag 간/내 관계는 지형 차이, 구간 시간 변화, 카메라 배율 편향 등이 섞였을 가능성을 점검해야 한다는 뜻이다.</p>
<h2>보조 기준에서는 다른 후보가 상위로 올라왔다</h2>
{table(extra)}
<p>ax의 연속 샘플 차이 RMS와 25–45 Hz power 등이 후보지만 구간 관계와 일치하지 않는다. 총 66개 특징을 탐색했으며 다중검정 보정 후 q&lt;0.05인 특징은 없다. 높은 상관을 선택한 뒤 같은 자료로 성능을 주장하는 회귀 시험은 하지 않았다. 상관 부재가 접근법 전체의 불가능성을 증명하는 것도 아니다.</p>
<h2>선별·시간·주파수 계산 방법</h2>
<ul><li>시작/재개 후 2초, 정지 전 0.5초 제외. 3초 후보를 0.5초 간격으로 검사하고 품질을 통과한 가장 이른 비중첩 창 선택. C나 특징값에 따른 선택 없음.</li><li>엄격: tag 유효율 ≥95%, 최대 gap ≤0.25초, 직선 RMS ≤3 mm, 최대 재투영오차 ≤1 px, 창 안 자세 변화 범위 ≤3°. 보조: 90%, 0.4초, 5 mm, 1.5 px, 5°. 두 세트를 합치지 않는다.</li><li>전후 SSH 시계 측정값을 선형 보간해 camera→ROS 시각 변환. 전후 offset 변화 &gt;0.1초는 두 세트 모두 제외. 연속적인 시계 변화라는 가정이며 하드웨어 동기 검증은 아니다.</li><li>잔여 ±0.1초 시간 이동에서 C 범위 ≤0.04 확인. IMU 최소 270개, wheel 최소 120개 / 3초, 각각 최대 gap 0.04/0.08초. 보간으로 큰 누락을 채우지 않는다.</li><li>IMU 6축을 100 Hz 공통 격자로 보간하고 평균 제거 후 Hann periodogram 적분: 2–10 / 10–25 / 25–45 Hz. std·MAD·차분 RMS·범위·첨도, 가속도/각속도 norm 특징 포함. 자세·중력 성분은 완전히 제거한 신호가 아니므로 기구 진동만의 수치로 해석하지 않는다.</li><li>/wheel/odometer의 좌우 누적 position(m)을 시간 차분해 원시 좌우 속도 및 차이의 평균·표준편차 추가. position 양자화가 차분 분산에 반영될 수 있다. /wheel/odom vx/wz 특징도 사용. 전류 데이터는 없음.</li><li>bag 평균 Spearman, bag 하나씩 제외한 안정성, 구간 단위 Spearman, bag 평균 제거 관계. 5/7 bag의 모든 순열(120/5040)을 사용한 양측 검정 및 66개 특징 BH-FDR.</li></ul>
<h2>파일별 포함·제외 근거</h2>
<p>제외 사유 숫자는 겹치는 후보 창 수다. 채택 표본 수와 구분해야 하며, 한 후보가 여러 사유에 해당할 수 있다.</p>
{table(audit)}
<h2>다음 판단을 바꾸려면</h2>
<p>가장 먼저 동일 bag 안에서 C가 달라지는 이유를 실제 속도 변화와 카메라 배율 변화로 구분해야 한다. 초점 고정만으로 이미 촬영한 calibration과 현재 초점이 일치하는 것은 아니다. 동일 조건 반복과 실제 거리 검증을 확보하고, 새 bag에서 후보 특징의 방향이 유지되는지 확인해야 한다. 시간 정렬은 전후 보간으로 보완했지만 완전히 동기화됐다고 보지 않는다.</p>
<p>오늘 촬영의 노면 라벨은 추측하지 않았으며 달 모사토 일반화도 주장하지 않았다. 이번 결과로 실행 중 C 보정이나 EKF 설정을 변경하지 않았다.</p>
<h2>재현 파일</h2><p>strict_samples.csv / screened_samples.csv, 각 correlations.csv, audit.json, correlations.json, analysis.ipynb를 같은 폴더에 저장했다. 코드: tools/analysis/20260910/correlate.py 및 report.py. 원본 bag과 카메라 파일은 수정하지 않았다.</p></html>'''
(OUT/'report.html').write_text(body)
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'cells':[{'cell_type':'markdown','metadata':{},'source':['# 2026-09-10 IMU / Encoder → C\n','Run with /home/sb/LOONAR/.venv-icp. Unit of inference: bag. Strict/screened samples overlap and must not be pooled.']},{'cell_type':'code','execution_count':None,'metadata':{},'source':['import runpy\n',f"runpy.run_path('{ROOT}/tools/analysis/20260910/correlate.py', run_name='__main__')\n",f"runpy.run_path('{ROOT}/tools/analysis/20260910/report.py', run_name='__main__')"],'outputs':[]}]}
(OUT/'analysis.ipynb').write_text(json.dumps(nb,indent=2))
print('Report and charts saved',OUT)
