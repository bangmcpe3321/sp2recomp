"""Check actual bounded frame capture: disabled zero work, real intervals, final CSV only."""
import argparse,os,subprocess,tempfile,csv
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();s=a.source.read_text();start=s.index('const char* frame_csv_path()');end=s.index('\nbool g_ready',start);body=s[start:end]
assert 'note_submit_cost(g_timing.replay_ns - stats_replay_before,' in s
assert 'f2.encode_ns - f_in.encode_ns, f2.fence_ns - f_in.fence_ns,' in s
assert 'stats_end_ns - t_in, replay::g_stats.total - stats_draws_before)' in s
prefix='''#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
namespace nx { std::atomic<uint64_t> g_frame{1}; }
uint64_t count=0,ns=0;
void pipeline_compile_totals(uint64_t& c,uint64_t& n) {c=count;n=ns;}
namespace plat { unsigned opens=0; FILE* fopen_utf8(const char* p,const char* m) { ++opens;return std::fopen(p,m); } }
'''
tests='''
int main(int argc,char**) {
 note_submit_cost(1000000,2000000,3000000,7000000,10);
 sample_present(1000000000);nx::g_frame=2;
 note_submit_cost(2000000,1000000,3000000,7000000,20);
 note_submit_cost(3000000,2000000,4000000,10000000,30);
 sample_present(1016666667);
 if (!frame_csv_path()) { assert(g_present_samples.empty());assert(g_last_present_ns==0);assert(g_submit_cost.total_ns==0);flush_present_samples();assert(plat::opens==0);return 0; }
 assert(g_present_samples.size()==1);assert(g_present_samples[0].ns==16666667);
 assert(g_present_samples[0].cost.replay_ns==5000000 && g_present_samples[0].cost.encode_ns==3000000);
 assert(g_present_samples[0].cost.fence_ns==7000000 && g_present_samples[0].cost.total_ns==17000000 && g_present_samples[0].cost.draws==50);
 assert(g_submit_cost.total_ns==0);
 count=4;ns=200000000;g_present_interval=2;nx::g_frame=3;sample_present(1050000000);assert(g_present_samples[1].ns==33333333);assert(g_present_samples[1].interval==2);assert(plat::opens==0);
 assert(g_present_samples[1].cost.total_ns==0);
 flush_present_samples();assert(plat::opens==1);
 // Cross two wraps with distinct frame and cost values. No gameplay file I/O.
 for (uint64_t k=0;k<240010;k++){
  nx::g_frame=4+k;count+=k%3;ns+=k;
  note_submit_cost(k,2*k,3*k,7*k,k%1000);
  sample_present(1060000000+16666667*k);
 }
 assert(g_present_samples.size()==120000);assert(plat::opens==1);
 auto& oldest=g_present_samples[g_present_next];assert(oldest.frame==120014);
 auto& newest=g_present_samples[(g_present_next+119999)%120000];assert(newest.frame==240013);
 assert(oldest.cost.replay_ns==120010 && newest.cost.replay_ns==240009);
 flush_present_samples();assert(plat::opens==2);
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-frame-times-') as td:
 d=Path(td);cpp=d/'t.cpp';exe=d/'t';cpp.write_text(prefix+body+tests)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
 env=os.environ.copy();env.pop('NX_FRAME_CSV',None);subprocess.run([str(exe)],env=env,check=True)
 env['NX_FRAME_CSV']='';subprocess.run([str(exe)],env=env,check=True)
 out=d/'frames.csv';env['NX_FRAME_CSV']=str(out);subprocess.run([str(exe)],env=env,check=True)
 rows=list(csv.DictReader(out.open()));assert len(rows)==120000;assert rows[0]['frame']=='120014' and rows[-1]['frame']=='240013';assert all(int(rows[i]['frame'])+1==int(rows[i+1]['frame']) for i in range(len(rows)-1));assert all(r['requested_interval']=='2' for r in rows);assert float(rows[0]['replay_ms'])==.120010;assert float(rows[-1]['fence_ms'])==.720027;assert rows[-1]['draws']=='9'
print('PASS disabled capture, submit cost accumulation/reset, two ring wraps, bounded chronological recent CSV and no gameplay file I/O')

# Reproducible patch preflight/idempotence/rollback, preserving local line endings.
import importlib.util
installer=Path(__file__).resolve().parents[2]/'patches/patch-recent-frame-costs.py'
spec=importlib.util.spec_from_file_location('recent_capture_patch',installer);patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)
with tempfile.TemporaryDirectory() as tmp:
 fixture=Path(tmp);target=fixture/'runtime/src/nvn/nvn_vk.cpp';target.parent.mkdir(parents=True)
 original='\n'.join(old.replace('\r\n','\n') for old,_ in patch.CHANGES)
 command=[os.sys.executable,str(installer),'--root',str(fixture)]
 for mode in ['lf','crlf']:
  raw=original.encode();raw=raw.replace(b'\n',b'\r\n') if mode=='crlf' else raw;target.write_bytes(raw)
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL);installed=target.read_bytes()
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL);assert target.read_bytes()==installed
  subprocess.run(command+['--restore'],check=True,stdout=subprocess.DEVNULL);assert target.read_bytes()==raw
 target.write_bytes(original.encode());subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
 installed=target.read_bytes();old,new=patch.CHANGES[1];target.write_bytes(installed.replace(new.encode(),old.encode()))
 partial=target.read_bytes();result=subprocess.run(command,capture_output=True);assert result.returncode!=0 and target.read_bytes()==partial
print('PASS: recent capture installer LF/CRLF restore, idempotence and partial preflight')
