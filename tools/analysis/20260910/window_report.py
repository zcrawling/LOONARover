from pathlib import Path
import json,base64,html
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, FormatStrFormatter
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'data/apriltag_gt/analysis_20260910'
d=json.loads((OUT/'window_correlations.json').read_text());rows={k:json.loads((OUT/(k+'_windows.json')).read_text()) for k in ['screened','strict']}
names=['wheel_right_mean','ax_power_10_25','ay_kurt','vx_diff_rms']
labels=['Right encoder mean speed (m/s)','X accel. power 10–25 Hz\n[(m/s²)²]','IMU Y acceleration kurtosis (dimensionless)','Encoder vx difference RMS\n[m/s]']
fig,axs=plt.subplots(2,4,figsize=(15,7),layout='constrained')
for i,k in enumerate(['screened','strict']):
 for j,n in enumerate(names):
  rr=rows[k];x=np.array([r['features'][n] for r in rr]);y=np.array([r['C'] for r in rr]);ax=axs[i,j]
  ax.scatter(x,y,color='#276c95',s=38);ax.set_xlabel(labels[j],fontsize=9);ax.set_ylabel('Local C');ax.grid(alpha=.2)
  r=next(t for t in d[k]['ranking'] if t['feature']==n)
  ax.set_title(f"{k}, n={len(rr)} | Spearman {r['spearman']:+.2f}\nPearson {r['pearson']:+.2f}",fontsize=10)
  ax.xaxis.set_major_locator(MaxNLocator(4));ax.xaxis.set_major_formatter(FormatStrFormatter('%.4g'));ax.xaxis.label.set_fontsize(8);ax.spines[['top','right']].set_visible(False)
fig.suptitle('One dot = one paired 3-second feature/C window. No bag means, no time predictors.',fontsize=13)
fig.savefig(OUT/'window_scatter.png',dpi=150);plt.close(fig)
def tr(cells):return '<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in cells)+'</tr>'
def stats(n,k):return next(r for r in d[k]['ranking'] if r['feature']==n)
summary=tr(['구간 특징','12구간 Spearman','12구간 Pearson','7구간 Spearman'])+''.join(tr([n,f"{stats(n,'screened')['spearman']:+.3f}",f"{stats(n,'screened')['pearson']:+.3f}",f"{stats(n,'strict')['spearman']:+.3f}"]) for n in names)
full=tr(['특징','Spearman','Pearson','한 구간 제외 ρ 범위','가장 유사한 특징 구간의 평균 |ΔC|'])+''.join(tr([r['feature'],f"{r['spearman']:+.3f}",f"{r['pearson']:+.3f}",f"{r['leave_one_window_min']:+.3f} … {r['leave_one_window_max']:+.3f}",f"{r['nearest_feature_C_difference']:.4f}"]) for r in d['screened']['ranking'])
uri='data:image/png;base64,'+base64.b64encode((OUT/'window_scatter.png').read_bytes()).decode()
report=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>구간별 IMU·Encoder → C 상관</title><style>body{{font:17px/1.7 sans-serif;max-width:1250px;margin:40px auto;padding:0 22px;color:#23323c}}h1,h2{{line-height:1.3}}h2{{margin-top:38px}}.lead{{padding:22px;background:#edf5fa;border-left:5px solid #287094}}img{{width:100%}}table{{border-collapse:collapse;width:100%;font-size:14px}}td{{padding:9px;border-bottom:1px solid #d0dbe2}}tr:first-child{{background:#edf2f5;font-weight:bold}}code{{overflow-wrap:anywhere}}@media(max-width:700px){{table{{font-size:11px}}}}</style>
<h1>각 구간의 진동·엔코더 특징과 그 구간 C를 직접 비교</h1>
<p>2026-09-10 기록 · 0.1 m/s · 시간·bag ID를 입력하지 않음 · bag 평균과 bag 내 평균 제거를 사용하지 않음</p>
<div class="lead"><b>직접 비교 결과:</b> 오른쪽 엔코더 평균속도, IMU X축 10–25 Hz 에너지, Y축 가속도 첨도, 엔코더 속도 차분 RMS가 후속 조사 후보다. 이 네 후보는 12구간과 엄격한 7구간에서 상관 방향이 같다. 이전의 bag 평균 ρ=1.0/0.9 주장을 대신하는 결과다. 66개 특징 전체에서 고른 탐색 결과이며 검증된 C 회귀 성능은 아니다.</div>
<h2>비교 단위는 오직 구간별 (특징, C)</h2>
<p>1개 표본 = 겹치지 않는 3초 주행 구간의 66개 IMU·엔코더 특징 + 같은 구간의 C. C는 카메라 이동량 기울기 / 엔코더 이동량 기울기다. 12개 품질 선별 구간을 주 분석에 사용하고, 별도 엄격 기준의 7개 구간은 민감도 확인에만 사용했다. 두 세트는 중복되므로 합치지 않았다. 시각은 센서·카메라를 짝짓고 중복 구간을 제거하는 데만 사용한다. 시간 순서·bag·노면 라벨에 따라 평균내거나 특징을 조정하지 않는다.</p>
<h2>높은 특징과 C의 방향</h2><table>{summary}</table>
<p>오른쪽 바퀴 평균속도가 작거나 X축 10–25 Hz 진동 에너지가 작을수록 C가 큰 순서가 관측된다. Y축 첨도는 가속도 분포의 꼬리·충격성을 나타내며 마찬가지로 음의 관계다. vx 차분 RMS는 반대로 클수록 C가 큰 방향이다. 이것은 관측 관계이며 원인이나 제어 규칙을 확정한 것이 아니다.</p>
<img src="{uri}" alt="Local feature versus local C scatter plots">
<p>모든 점이 개별 구간이다. bag 평균점·시간 추세선은 없다. X축 에너지의 12구간 Spearman은 −0.524지만 Pearson은 −0.066이다. 값의 순서에는 관계가 있어도 단순 직선 회귀에는 잘 맞지 않을 수 있음을 뜻한다.</p>
<h2>비슷한 특징일 때 비슷한 C가 다시 나타나는가</h2>
<p>각 구간에서 해당 특징값이 가장 가까운 다른 구간을 찾고 C 차이를 계산했다. 자기 자신은 제외하고 거리가 같은 이웃은 모두 평균했다. 시간과 bag에 따른 이웃 제한은 두지 않았다. 12구간 전체에서 임의의 다른 구간과의 평균 |ΔC|는 0.0362였다.</p>
<ul><li>오른쪽 엔코더 평균속도 기준 이웃: |ΔC|=0.0266. 무작위 다른 구간보다 약 27% 작았다.</li><li>X축 10–25 Hz 에너지 기준 이웃: 0.0311. 약 14% 작았다.</li><li>Y축 첨도 기준 이웃: 0.0321. 약 11% 작았다.</li><li>vx 차분 RMS 기준 이웃: 0.0395. 12구간에서는 반복 유사성이 개선되지 않았다. 엄격 7구간의 높은 상관만 보고 채택하면 안 된다.</li></ul>
<p>이 수치는 동일 자료 안에서 특징별로 확인한 유사성이다. 66개를 탐색한 뒤 선택했으므로 새 자료의 예측 오차 개선율로 표현하지 않는다. 변수에서 시간을 뺐다고 실제 표본의 통계적 의존성이 없어지는 것도 아니므로 독립 표본 가정의 p값은 제시하지 않는다.</p>
<h2>해석할 때 구분해야 할 두 가지</h2>
<p><b>엔코더 특징의 상관:</b> C의 분모 자체가 엔코더 이동량이다. 따라서 엔코더 속도와 C의 음의 상관 일부는 수식 구조에서도 생길 수 있다. 유용한 입력 후보이지만 지형을 감지했다는 증거는 아니다.</p>
<p><b>IMU 특징의 상관:</b> X축 10–25 Hz 에너지와 Y축 첨도는 C 계산에 직접 사용되지 않은 후보다. 두 품질 기준에서 부호가 유지돼 후속 조사 가치가 있다. 이번 결과는 이 둘을 무관하다고 버리는 근거가 아니다. 다만 카메라 배율 오차가 남아 있어 C를 오차 없는 정답으로 취급하지 않는다.</p>
<h2>66개 전체 순위 — 12개 구간을 직접 비교</h2><table>{full}</table>
<h2>재현과 데이터 품질</h2>
<p>기존 품질 선별과 시간 보정은 유지했다. 시작 후 2초·정지 전 0.5초를 제외하고, GT 유효율·누락·재투영·직선 잔차를 검사했다. 엄격/보조 기준과 원본 출처는 audit.json에 남아 있다. 다른 속도 시험은 같은 품질의 3초 구간이 없어 포함되지 않았다. 구간의 C나 특징값을 보고 품질을 선별하지 않았다.</p>
<p>window_correlations.py / window_report.py가 새 분석 코드다. window_correlations.json, window_screened_ranking.csv, window_strict_ranking.csv에 모든 수치를 저장했다. 원래 분석은 report_bag_means_superseded.html에 보존했다. 실행 중 C 보정 로직은 변경하지 않았다.</p></html>'''
previous=OUT/'report_bag_means_superseded.html'
if not previous.exists():previous.write_bytes((OUT/'report.html').read_bytes())
(OUT/'report.html').write_text(report)
print('Updated',OUT/'report.html')
