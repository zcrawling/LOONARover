"""Recompute pooled statistics from saved per-frame/resource evidence."""
import importlib.util,json,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('bench',HERE/'run_pi_bench.py');bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
OUT=bench.OUT
report=[]
for name in [p['name'] for p in bench.PROFILES]:
 paths=sorted(OUT.glob(name+'_r*/raw.json'))
 paths=[p for p in paths if json.loads(p.read_text()).get('instrument_version')==2]
 if not paths:continue
 values=[];all_values=[];cpus=[];mem=[];local_cpu=[];local_mem=[];temperatures=[];uncertainty=[];gaps=0;invalid=0;duplicates=0;unique_frames=0;seconds=0;names=[]
 for p in paths:
    raw=json.loads(p.read_text());summary=json.loads(p.with_name('summary.json').read_text());names.append(raw['config']['name'])
    begin=raw['start']+3;end=raw['end'];seconds+=summary['seconds']-3
    selected=[f for f in raw['frames'] if begin*1e6<=f['received_us']<=end*1e6]
    unique=len(set(f['sequence'] for f in selected));unique_frames+=unique;duplicates+=len(selected)-unique
    values += [f['latency_ms'] for f in selected]
    all_values += [f['latency_ms'] for f in raw['frames'] if f['received_us']<=end*1e6]
    offset=raw['clock_before']['best']['offset_us']/1e6
    rows=[r for r in raw['remote']['samples'] if begin<=r['wall']-offset<=end]
    cpus += [(b['ticks']-a['ticks'])/100/(b['mono']-a['mono'])*100 for a,b in zip(rows,rows[1:])]
    mem += [r['rss_kib']/1024 for r in rows];temperatures += [r['temp_c'] for r in rows]
    local=[r for r in raw['resources'] if begin<=r['wall']<=end]
    local_cpu += [sum((pb['ticks']-pa['ticks'])/100/(pb['mono']-pa['mono'])*100 for pa,pb in zip(a['processes'],b['processes'])) for a,b in zip(local,local[1:])]
    local_mem += [sum(x['rss_kib'] for x in r['processes'])/1024 for r in local]
    uncertainty.append(summary['clock_uncertainty_ms']);gaps+=summary['sequence_gaps'];invalid+=summary['invalid_frames']
 report.append(dict(profile=name,runs=names,steady_seconds=seconds,latency_ms=bench.stats(values),including_startup_ms=bench.stats(all_values),
   pi_cpu_percent=bench.stats(cpus),pi_rss_mib=bench.stats(mem),pi_temperature_c=bench.stats(temperatures),
   laptop_ffmpeg_cpu_percent=bench.stats(local_cpu),laptop_ffmpeg_rss_mib=bench.stats(local_mem),
   clock_uncertainty_ms=max(uncertainty),sequence_gaps=gaps,invalid=invalid,duplicates=duplicates,unique_fps=unique_frames/seconds,received_fps=len(values)/seconds))
(OUT/'pooled.json').write_text(json.dumps(report,indent=2)+'\n')
for d in report:
 print(f"{d['profile']:22s} {d['latency_ms']['n']:5d} mean {d['latency_ms']['mean']:6.1f} max {d['latency_ms']['maximum']:6.1f} ms  Pi CPU {d['pi_cpu_percent']['mean']:5.1f}/{d['pi_cpu_percent']['maximum']:5.1f}% RSS {d['pi_rss_mib']['mean']:5.1f}/{d['pi_rss_mib']['maximum']:5.1f} MiB PC CPU {d['laptop_ffmpeg_cpu_percent']['mean']:5.1f}% FPS {d['received_fps']:.2f} clock +/-{d['clock_uncertainty_ms']:.2f}ms")
