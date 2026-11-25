#!/usr/bin/env python3
"""Reduce first-use shader transformation allocations without changing generated words."""
from pathlib import Path
import argparse,os
CHANGES=[('    std::map<uint32_t, uint32_t> binding, set, type_of;  // id -> Binding, DescriptorSet, value type', '    // PATCH-SPIRV-FIRST-USE: only access-chain indices need a result-type lookup.\n    std::set<uint32_t> index_ids;\n    for (const Inst& n : insts)\n        if ((n.op == OpAccessChain || n.op == OpInBoundsAccessChain) && n.len >= 6)\n            index_ids.insert(in[n.at + 5]);\n    std::map<uint32_t, uint32_t> binding, set, type_of;  // id -> Binding, DescriptorSet, value type'), ('            type_of.emplace(w[2], w[1]);', '            if (index_ids.count(w[2])) type_of.emplace(w[2], w[1]); // PATCH-SPIRV-FIRST-USE'), ('    for (const Inst& n : insts) {\n        if (n.at == insert_at) out.insert(out.end(), types.begin(), types.end());\n        std::vector<uint32_t> w(in.begin() + n.at, in.begin() + n.at + n.len);', '    std::vector<uint32_t> instruction; // PATCH-SPIRV-FIRST-USE: retain scratch capacity across instructions\n    for (const Inst& n : insts) {\n        if (n.at == insert_at) out.insert(out.end(), types.begin(), types.end());\n        instruction.assign(in.begin() + n.at, in.begin() + n.at + n.len);\n        auto& w = instruction;'), ('    for (const Inst& n : insts) {\n        if (n.at == first_function) out.insert(out.end(), constants.begin(), constants.end());\n        std::vector<uint32_t> w(in.begin() + n.at, in.begin() + n.at + n.len);', '    std::vector<uint32_t> instruction; // PATCH-SPIRV-FIRST-USE: retain scratch capacity across instructions\n    for (const Inst& n : insts) {\n        if (n.at == first_function) out.insert(out.end(), constants.begin(), constants.end());\n        instruction.assign(in.begin() + n.at, in.begin() + n.at + n.len);\n        auto& w = instruction;'), ('    for (const Inst& n : insts) {\n        if (n.at == insert_at) out.insert(out.end(), globals.begin(), globals.end());\n        std::vector<uint32_t> w(in.begin() + n.at, in.begin() + n.at + n.len);', '    std::vector<uint32_t> instruction; // PATCH-SPIRV-FIRST-USE: retain scratch capacity across instructions\n    for (const Inst& n : insts) {\n        if (n.at == insert_at) out.insert(out.end(), globals.begin(), globals.end());\n        instruction.assign(in.begin() + n.at, in.begin() + n.at + n.len);\n        auto& w = instruction;')]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))));p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
 path=a.root/'runtime/src/nvn/nvn_spirv_patch.cpp';data=path.read_bytes();states=[]
 for old,new in CHANGES:
  matches=[]
  for nl in (b'\n',b'\r\n'):
   left=old.encode().replace(b'\n',nl);right=new.encode().replace(b'\n',nl)
   if data.count(right)==1:matches.append((right,left if a.restore else right,True))
  if not matches:
   for nl in (b'\n',b'\r\n'):
    left=old.encode().replace(b'\n',nl);right=new.encode().replace(b'\n',nl)
    if data.count(left)!=1:continue
    if b'\n' not in left:
     at=data.index(left)+len(left);local=b'\r\n' if data[at:at+2]==b'\r\n' else b'\n'
     if nl!=local:continue
    matches.append((left,left if a.restore else right,False))
  matches=list(dict.fromkeys(matches))
  if len(matches)!=1:raise SystemExit('Shader transform source mismatch; no files changed')
  before,after,state=matches[0];states.append(state);data=data.replace(before,after,1)
 if len(set(states))!=1:raise SystemExit('Partial shader transform patch; no files changed')
 if a.check:print('Preflight passed');return
 path.write_bytes(data);print('Restored' if a.restore else 'Applied; rebuild nvn_spirv_patch.cpp')
if __name__=='__main__':main()
