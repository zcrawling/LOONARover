from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

p=Path(__file__).resolve().parents[3]/'data/apriltag_gt/analysis_20260909'
r=json.loads((p/'runs.json').read_text())
r=[x for x in r if x.get('common',{}).get('wheel_m',0)>=.3]
x=np.arange(len(r));labels=[a['short']+'\n'+a['terrain'].replace('_','\n') for a in r]
fig,axes=plt.subplots(3,1,figsize=(12,10),sharex=True)
axes[0].scatter(x,[a['common']['ratio'] for a in r],color='#2079a8',s=45)
axes[0].axhline(1,color='gray',ls='--');axes[0].set_ylim(.94,1.09)
axes[0].set_ylabel('Camera / encoder\ncommon endpoint displacement')
axes[0].set_title('11 runs with >=0.3 m common encoder travel | uphill run excluded\nZero-offset camera estimates: diagnostic, not verified slip labels')
axes[1].bar(x,[a['accel_difference_rms'] for a in r],color='#5c9c80')
axes[1].set_ylabel('Moving IMU acceleration\nfirst-difference RMS (m/s²)')
axes[2].bar(x-.17,[a['wheel_yaw_deg'] for a in r],width=.34,label='wheel yaw',color='#be6d3c')
axes[2].bar(x+.17,[a['imu_yaw_deg'] for a in r],width=.34,label='integrated gyro z',color='#456db1')
axes[2].set_ylabel('Whole-run yaw change (deg)');axes[2].legend()
axes[2].set_xticks(x,labels,fontsize=8)
for ax in axes:ax.grid(axis='y',alpha=.2)
fig.tight_layout();fig.savefig(p/'overview.png',dpi=150);fig.savefig(p/'overview.svg');plt.close(fig)
