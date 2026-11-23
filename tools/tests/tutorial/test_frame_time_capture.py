"""Check actual bounded frame capture: disabled zero work, real intervals, final CSV only."""
import argparse,os,subprocess,tempfile,csv
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();s=a.source.read_text();start=s.index('const char* frame_csv_path()');end=s.index('\nbool g_ready',start);body=s[start:end]
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
 sample_present(1000000000);nx::g_frame=2;sample_present(1016666667);
 if (!frame_csv_path()) { assert(g_present_samples.empty());assert(g_last_present_ns==0);flush_present_samples();assert(plat::opens==0);return 0; }
 assert(g_present_samples.size()==1);assert(g_present_samples[0].ns==16666667);
 count=4;ns=200000000;g_present_interval=2;nx::g_frame=3;sample_present(1050000000);assert(g_present_samples[1].ns==33333333);assert(g_present_samples[1].interval==2);assert(plat::opens==0);
 flush_present_samples();assert(plat::opens==1);
 for (uint64_t k=0;k<120010;k++)sample_present(1060000000+16666667*k);
 assert(g_present_samples.size()==120000);assert(plat::opens==1);
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-frame-times-') as td:
 d=Path(td);cpp=d/'t.cpp';exe=d/'t';cpp.write_text(prefix+body+tests)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
 env=os.environ.copy();env.pop('NX_FRAME_CSV',None);subprocess.run([str(exe)],env=env,check=True)
 env['NX_FRAME_CSV']='';subprocess.run([str(exe)],env=env,check=True)
 out=d/'frames.csv';env['NX_FRAME_CSV']=str(out);subprocess.run([str(exe)],env=env,check=True)
 rows=list(csv.DictReader(out.open()));assert len(rows)==2;assert rows[0]['frame']=='2' and abs(float(rows[0]['interval_ms'])-16.666667)<.000001;assert rows[1]['requested_interval']=='2';assert rows[1]['pipeline_count']=='4';assert float(rows[1]['pipeline_ms'])==200
print('PASS disabled capture, measured frame intervals, requested rate, bounded storage and final CSV-only I/O')
