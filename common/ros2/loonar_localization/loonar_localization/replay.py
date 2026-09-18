"""Replay existing V1-manifest bags without ROS or robot connections."""
import argparse
import json
from pathlib import Path
import numpy as np
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores, get_typestore
from .core import Config, Estimator, Sample, PrimitiveManager


def replay(manifest, output):
    output.mkdir(parents=True, exist_ok=True)
    summary = []
    for r in json.loads(manifest.read_text())['runs']:
        if r['status'] != 'processed':
            continue
        base = np.genfromtxt(manifest.parent/'series'/f"{r['run_id']}.csv", names=True, delimiter=',')
        raw = []
        path = Path(r['path'])
        with AnyReader([path], default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
            for c, _, d in bag.messages(connections=[c for c in bag.connections if c.topic == '/imu']):
                m = bag.deserialize(d, c.msgtype); g=m.angular_velocity; a=m.linear_acceleration
                raw.append([m.header.stamp.sec+m.header.stamp.nanosec*1e-9,g.x,g.y,g.z,a.x,a.y,a.z])
        raw = np.array(raw); R=np.array(r['imu_to_base_rotation'])
        raw[:,1:4] = raw[:,1:4]@R.T; raw[:,4:7] = raw[:,4:7]@R.T
        values = np.column_stack([np.interp(base['t_ros'],raw[:,0],raw[:,k]) for k in range(1,7)])
        eventfile=path.parent/'command-events.jsonl'
        events=[]
        if eventfile.exists():
            for line in eventfile.read_text().splitlines():
                e=json.loads(line);events.append([e['ros_stamp_ns']/1e9,e['linear_mps'],e['angular_radps']])
        if not events:
            # No command truth manufactured from observed velocity.
            commands=np.zeros((len(base),2)); prior_available=False
        else:
            events=np.array(events); ix=np.searchsorted(events[:,0],base['t_ros'],side='right')-1
            commands=events[np.maximum(ix,0),1:];prior_available=True
        config=Config(); estimator=Estimator(config,[0.,0.,r['bias_radps']])
        check=Estimator(Config(stationary_enabled=False),[0.,0.,r['bias_radps']])
        manager=PrimitiveManager();rows=[];diff=0.
        for i,b in enumerate(base):
            prior=manager.observe(*commands[i]) if prior_available else manager.state
            s=Sample(float(b['t_ros']),float(b['vx_encoder']),float(b['wz_encoder']),values[i,:3],values[i,3:])
            result=estimator.update(s,prior);original=check.update(s,prior)
            if int(b['segment']) == 0:
                diff=max(diff,float(np.max(np.abs(np.array(original['pose'])-[b['x_v1'],b['y_v1'],b['yaw_v1']]))))
            rows.append(result)
        with (output/f"{r['run_id']}.jsonl").open('w') as f:
            for row in rows:f.write(json.dumps(row,allow_nan=False)+'\n')
        states={s:sum(x['state']==s for x in rows) for s in set(x['state'] for x in rows)}
        summary.append(dict(run_id=r['run_id'],samples=len(rows),prior_available=prior_available,stationary_samples=sum(x['stationary'] for x in rows),
                            v1_max_absolute_difference_first_segment=diff,states=states,final_pose=rows[-1]['pose']))
    (output/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(dict(runs=len(summary),max_v1_difference=max(r['v1_max_absolute_difference_first_segment'] for r in summary),
                         stationary_samples=sum(r['stationary_samples'] for r in summary)),indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();replay(a.manifest,a.output)

if __name__=='__main__':main()
