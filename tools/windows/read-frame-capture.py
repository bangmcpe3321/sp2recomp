"""Read the existing frame recorder without modifying or suspending the game."""
import argparse,csv,ctypes,json,mmap,struct
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--base',type=lambda s:int(s,0),required=True);p.add_argument('--exe',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
with a.exe.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as pe:
 off=struct.unpack_from('<I',pe,0x3c)[0];assert pe[off:off+4]==b'PE\0\0'
 nsections=struct.unpack_from('<H',pe,off+6)[0];symbols,count=struct.unpack_from('<II',pe,off+12)
 optsize=struct.unpack_from('<H',pe,off+20)[0];sections=off+24+optsize;strings=symbols+18*count
 assert 0<symbols<strings<len(pe)
 found=[];index=0
 while index<count:
  entry=symbols+18*index;name=pe[entry:entry+8]
  if name[:4]==b'\0\0\0\0':
   pos=strings+struct.unpack_from('<I',name,4)[0];end=pe.find(b'\0',pos);name=pe[pos:end]
  if name in (b'_ZN2nx3nvn12_GLOBAL__N_117g_present_samplesE', b'_ZN2nx3nvn12_GLOBAL__N_114g_present_nextE'):
   value,section=struct.unpack_from('<Ih',pe,entry+8)
   if 1<=section<=nsections:
    rva=struct.unpack_from('<I',pe,sections+(section-1)*40+12)[0]+value;found.append((name.decode(),rva))
  index+=1+pe[entry+17]
 found=dict(found)
 rva=found['_ZN2nx3nvn12_GLOBAL__N_117g_present_samplesE']
 cursor_rva=found.get('_ZN2nx3nvn12_GLOBAL__N_114g_present_nextE')
 stride=80 if cursor_rva is not None else 40
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32];k.OpenProcess.restype=ctypes.c_void_p
k.ReadProcessMemory.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)];k.ReadProcessMemory.restype=ctypes.c_int
k.CloseHandle.argtypes=[ctypes.c_void_p]
h=k.OpenProcess(0x1010,False,a.pid)
if not h:raise ctypes.WinError(ctypes.get_last_error())
def read(address,size):
 buf=ctypes.create_string_buffer(size);n=ctypes.c_size_t()
 if not k.ReadProcessMemory(h,ctypes.c_void_p(address),buf,size,ctypes.byref(n)) or n.value!=size:raise ctypes.WinError(ctypes.get_last_error())
 return buf.raw
rows=None
try:
 for attempt in range(10):
  first,end,cap=struct.unpack('<QQQ',read(a.base+rva,24))
  cursor=struct.unpack('<Q',read(a.base+cursor_rva,8))[0] if cursor_rva is not None else 0
  assert 0<first<=end<=cap and (end-first)%stride==0 and (cap-first)//stride<=262144
  raw=read(first,end-first)
  again,new_end,_=struct.unpack('<QQQ',read(a.base+rva,24))
  new_cursor=struct.unpack('<Q',read(a.base+cursor_rva,8))[0] if cursor_rva is not None else 0
  if again!=first or new_end<end or new_cursor!=cursor:continue
  data=list(struct.iter_unpack('<QQI4xQQQQQQQ' if stride==80 else '<QQI4xQQ',raw))
  assert cursor<len(data)
  if cursor:data=data[cursor:]+data[:cursor]
  assert 0<len(data)<=120000
  assert all(0<=r[2]<=8 and r[1]<600_000_000_000 for r in data)
  assert all(data[i][0]<data[i+1][0] for i in range(len(data)-1))
  rows=data;break
 assert rows is not None,'Recorder reallocated during every read; no snapshot written'
finally:k.CloseHandle(h)
with a.out.open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['frame','interval_ms','requested_interval','pipeline_count','pipeline_ms']+(['replay_ms','encode_ms','fence_ms','submit_ms','draws'] if stride==80 else []))
 for row in rows:
  frame,ns,interval,pcount,pns=row[:5]
  extra=([n/1e6 for n in row[5:9]]+[row[9]]) if stride==80 else []
  w.writerow([frame,ns/1e6,interval,pcount,pns/1e6]+extra)
print(json.dumps({'pid':a.pid,'frames':len(rows),'last_frame':rows[-1][0],'snapshot':str(a.out),'method':'read-only buffered recorder; no process write or suspension'}))
