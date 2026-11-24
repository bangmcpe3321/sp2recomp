#!/usr/bin/env python3
"""Reuse the resolved image from readiness checks in the same texture gather."""
from pathlib import Path
import argparse
import os

CHANGES = {
 'runtime/src/nvn/nvn_pipeline.cpp': [
  ('bool sampled_ready(uint64_t texture) {',
   'bool sampled_ready_image(uint64_t texture, GpuImage*& image) { // PATCH-SAMPLED-IMAGE-REUSE'),
  ('    GpuImage* image = t ? image_of(texture) : nullptr;\n    if (!image)',
   '    image = t ? image_of(texture) : nullptr;\n    if (!image)'),
  ('\nvoid sampled_ready_log() {',
   '\nbool sampled_ready(uint64_t texture) {\n    GpuImage* image = nullptr;\n    return sampled_ready_image(texture, image);\n}\n\nvoid sampled_ready_log() {'),
 ],
 'runtime/src/nvn/nvn_pipeline.h': [
  ('bool sampled_ready(uint64_t texture);',
   'bool sampled_ready(uint64_t texture);\n// Same check; returns its resolved image even when an upload/layout change is needed.\nbool sampled_ready_image(uint64_t texture, GpuImage*& image); // PATCH-SAMPLED-IMAGE-REUSE'),
 ],
 'runtime/src/nvn/nvn_sets.cpp': [
  ('''        if (texture ? !sampled_ready(texture) : !dummy_ready(b->image)) out |= kNeedBreak;
        if (!texture) continue;
        GpuImage* img = image_of(texture);''',
   '''        GpuImage* img = nullptr; // PATCH-SAMPLED-IMAGE-REUSE: use the image checked just above.
        if (texture ? !sampled_ready_image(texture, img) : !dummy_ready(b->image)) out |= kNeedBreak;
        if (!texture) continue;'''),
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
   old,new=old.encode(),new.encode()
   if data.count(new)==1:
    states.append(True)
    if a.restore:data=data.replace(new,old,1)
   elif data.count(old)==1:
    states.append(False)
    if not a.restore:data=data.replace(old,new,1)
   else:raise SystemExit('Sampled image source mismatch: '+name+'; no files changed')
  pending.append((path,data))
 if len(set(states))!=1:raise SystemExit('Partial sampled-image patch; no files changed')
 if a.check:print('Preflight passed');return
 for path,data in pending:path.write_bytes(data)
 print('Restored' if a.restore else 'Applied; rebuild nvn_pipeline.cpp and nvn_sets.cpp')


if __name__=='__main__':main()
