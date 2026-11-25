#!/usr/bin/env python3
"""Reuse completed Windows image allocations with exact memory requirements."""
import argparse,os
from pathlib import Path
HELPER='// PATCH-IMAGE-MEMORY-CACHE: empty memory only, never image contents.\nstatic ImageMemoryCache& image_memory_cache() {\n#ifdef _WIN32\n    static ImageMemoryCache cache(std::getenv("NX_IMAGE_MEMORY_CACHE") &&\n        std::getenv("NX_IMAGE_MEMORY_CACHE")[0] == \'0\' ? 0 : (128ull << 20), 128);\n#else\n    static ImageMemoryCache cache(0, 0);\n#endif\n    return cache;\n}\nvoid release_image_memory(VkDeviceMemory memory) { image_memory_cache().retire(memory); }\n\n'
CHANGES={
'runtime/src/nvn/nvn_image.cpp':[
 ('#include "nvn_vk.h"', '#include "nvn_vk.h"\n#include "image_memory_cache.h"'),
 ('// PATCH-IMGSTATS: live image bytes', HELPER+'// PATCH-IMGSTATS: live image bytes'),
 ('p_vkAllocateMemory(vk_device(), &ai, nullptr, &img->memory)', 'image_memory_cache().allocate(ai, &img->memory)'),
],
'runtime/src/nvn/nvn_vk.h':[
 ('void retire_image(std::shared_ptr<GpuImage> image);', 'void release_image_memory(VkDeviceMemory memory); // PATCH-IMAGE-MEMORY-CACHE\nvoid retire_image(std::shared_ptr<GpuImage> image);'),
],
'runtime/src/nvn/nvn_frames.cpp':[
 ('if (img->memory) p_vkFreeMemory(vk_device(), img->memory, nullptr);', 'if (img->memory) release_image_memory(img->memory); // PATCH-IMAGE-MEMORY-CACHE'),
]}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))));p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
 pending=[];states=[]
 for name,changes in CHANGES.items():
  path=a.root/name;data=path.read_bytes()
  for old,new in changes:
   old,new=old.encode(),new.encode()
   # Private source can contain CRLF and LF regions; match each full block locally.
   matches=[]
   expected=2 if old.startswith(b'p_vkAllocateMemory') else 1
   for nl in (b'\n',b'\r\n'):
    left=old.replace(b'\n',nl);right=new.replace(b'\n',nl)
    if data.count(right)==expected:matches.append((right,left if a.restore else right,True))
   if not matches:
    for nl in (b'\n',b'\r\n'):
     left=old.replace(b'\n',nl);right=new.replace(b'\n',nl)
     if data.count(left)!=expected:continue
     end=data.index(left)+len(left)
     if b'\n' not in left:
      local=b'\r\n' if data[end:end+2]==b'\r\n' else b'\n'
      if nl!=local:continue
     matches.append((left,left if a.restore else right,False))
   # Single-line replacement variants are byte-identical.
   matches=list(dict.fromkeys(matches))
   if len(matches)!=1:raise SystemExit('Image memory source mismatch: '+name+'; no files changed')
   left,right,state=matches[0];states.append(state);data=data.replace(left,right)
  pending.append((path,data))
 if len(set(states))!=1:raise SystemExit('Partial image memory patch; no files changed')
 header=a.root/'runtime/src/nvn/image_memory_cache.h'
 payload=(Path(__file__).resolve().parents[1]/'runtime/image_memory_cache.h').read_bytes()
 if header.exists() and header.read_bytes()!=payload:raise SystemExit('Image memory header differs; no files changed')
 if a.check:print('Preflight passed');return
 for path,data in pending:path.write_bytes(data)
 if not a.restore:header.write_bytes(payload)
 elif header.exists() and header.read_bytes()==payload:header.unlink()
 print('Restored' if a.restore else 'Applied; rebuild nvn_image.cpp and nvn_frames.cpp')
if __name__=='__main__':main()
