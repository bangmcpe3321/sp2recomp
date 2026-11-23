"""Summarize present times and synchronous pipeline costs, separated by requested rate."""
import argparse,csv,json,math,statistics
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('capture',type=Path);p.add_argument('--from-frame',type=int,default=0)
p.add_argument('--to-frame',type=int);p.add_argument('--json',action='store_true')
p.add_argument('--worst',type=int,default=0,help='Show N longest frames with their compilation costs')
a=p.parse_args();groups={};selected=[]
for row in csv.DictReader(a.capture.open(newline='',encoding='utf-8')):
 frame=int(row['frame']);ms=float(row['interval_ms']);interval=int(row['requested_interval'])
 if not math.isfinite(ms) or ms<=0:raise SystemExit(f'Invalid frame time at frame {frame}')
 if frame<a.from_frame or (a.to_frame is not None and frame>a.to_frame):continue
 sample={'frame':frame,'interval_ms':ms,'requested_interval':interval,'pipeline_count':int(row.get('pipeline_count',0)),'pipeline_ms':float(row.get('pipeline_ms',0))}
 groups.setdefault(interval,[]).append(sample);selected.append(sample)
if not groups:raise SystemExit('No frame samples in the selected range')
result=[]
for interval,samples in sorted(groups.items()):
 values=sorted(s['interval_ms'] for s in samples);n=len(values)
 def q(f):return values[min(n-1,int((n-1)*f))]
 result.append({'requested_interval':interval,'target_fps':60/interval if interval>0 else None,'samples':n,'average_fps':1000/statistics.mean(values),'p50_ms':q(.5),'p95_ms':q(.95),'p99_ms':q(.99),'max_ms':values[-1],'over_50ms':sum(v>50 for v in values),'over_100ms':sum(v>100 for v in values),'pipeline_count':sum(s['pipeline_count'] for s in samples),'pipeline_ms':sum(s['pipeline_ms'] for s in samples)})
worst=sorted(selected,key=lambda s:s['interval_ms'],reverse=True)[:max(0,a.worst)]
if a.json:print(json.dumps({'groups':result,'worst':worst} if a.worst else result,indent=2))
else:
 for r in result:print('interval {requested_interval}: {samples} frames, {average_fps:.2f} FPS; p50 {p50_ms:.2f}, p95 {p95_ms:.2f}, p99 {p99_ms:.2f}, max {max_ms:.2f} ms; >50 ms {over_50ms}, >100 ms {over_100ms}; {pipeline_count} pipelines / {pipeline_ms:.2f} ms'.format(**r))
 for s in worst:print('frame {frame}: {interval_ms:.2f} ms, interval {requested_interval}, pipelines {pipeline_count} / {pipeline_ms:.2f} ms'.format(**s))
