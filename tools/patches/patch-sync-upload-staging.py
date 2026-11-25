#!/usr/bin/env python3
"""Use the actual synchronous upload buffer for ordinary texture staging."""
import argparse,os
from pathlib import Path

CHANGES={
 'runtime/src/nvn/nvn_vk.cpp':[
  ('Upload upload_alloc(uint64_t size, uint64_t align) {',
   '// PATCH-SYNC-UPLOAD-STAGING: capacity/usage of the allocator upload_alloc uses.\nuint64_t upload_capacity() { return async_gpu() ? frame_ring_size() : g_upload_size; }\nuint64_t upload_bytes_used() { return async_gpu() ? frame_upload_used() : g_upload_used; }\n\nUpload upload_alloc(uint64_t size, uint64_t align) {'),
 ],
 'runtime/src/nvn/nvn_vk.h':[
  ('Upload upload_alloc(uint64_t size, uint64_t align);',
   'Upload upload_alloc(uint64_t size, uint64_t align);\nuint64_t upload_capacity(); // PATCH-SYNC-UPLOAD-STAGING: actual sync buffer or async ring\nuint64_t upload_bytes_used();'),
 ],
 'runtime/src/nvn/nvn_upload.cpp':[
  ('    uint64_t ring = frame_ring_size();\n    return always || !ring || frame_upload_used() + size > ring / 4 || size > ring / 8;',
   '    // PATCH-SYNC-UPLOAD-STAGING: the synchronous path has an upload buffer too.\n    // Keep the same conservative quarter/eighth policy without unsigned wrap.\n    const uint64_t ring = upload_capacity(), used = upload_bytes_used();\n    if (always || !ring) return true;\n    return size > ring / 8 || used > ring / 4 || size > ring / 4 - used;'),
 ],
}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))))
 p.add_argument('--check',action='store_true');p.add_argument('--restore',action='store_true')
 a=p.parse_args();pending=[];states=[]
 for name,changes in CHANGES.items():
  path=a.root/name;data=path.read_bytes()
  for old,new in changes:
   variants=[(newline,old.encode().replace(b'\n',newline),new.encode().replace(b'\n',newline))
             for newline in (b'\n',b'\r\n')]
   # Match the patched block first: its single-line anchor is also inside it.
   matches=[(right,left if a.restore else right,True)
            for _,left,right in variants if data.count(right)==1]
   if not matches:
    for newline,left,right in variants:
     if data.count(left)!=1:continue
     if b'\n' not in left:
      end=data.index(left)+len(left)
      local=b'\r\n' if data[end:end+2]==b'\r\n' else b'\n'
      if newline!=local:continue
     matches.append((left,left if a.restore else right,False))
   if len(matches)!=1:raise SystemExit('Upload staging source mismatch: '+name+'; no files changed')
   left,right,state=matches[0]
   rest=data.replace(left,b'',1)
   if b'PATCH-SYNC-UPLOAD-STAGING' in rest or any(before in rest for _,before,_ in variants):
    raise SystemExit('Duplicate or partial upload staging patch: '+name+'; no files changed')
   states.append(state);data=data.replace(left,right,1)
  pending.append((path,data))
 if len(set(states))!=1:raise SystemExit('Partial upload staging patch; no files changed')
 if a.check:print('Preflight passed');return
 for path,data in pending:path.write_bytes(data)
 print('Restored' if a.restore else 'Applied; rebuild nvn_vk.cpp and nvn_upload.cpp')

if __name__=='__main__':main()
