"""Exercise actual pipeline feedback gating, pNext chaining and validity handling."""
from pathlib import Path
import argparse, subprocess, tempfile, sys

parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);args=parser.parse_args()
source=args.source.read_text()
def block(text,signature):
    start=text.index(signature);cursor=text.index('{',start);depth=1;end=cursor+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

gate=block(source,'static bool pipeline_feedback_on()')
probe=block(source,'struct PipelineFeedbackProbe {')+';'
graphics=block(source,'VkPipeline graphics_pipeline(')
compute=block(source,'VkPipeline compute_pipeline(')
module=block(source,'VkShaderModule module_of(')
assert 'PipelineFeedbackProbe feedback(pipeline_feedback_on(), nstages)' in graphics
assert 'PipelineFeedbackProbe feedback(pipeline_feedback_on(), 1)' in compute
for body in [graphics,compute]:
    assert body.index('feedback.attach(ci);')<body.index('VkResult made = p_vkCreate')
    assert 'note_pipeline_created(elapsed);' in body
    assert 'if (feedback.enabled)' in body
    assert 'PIPELINE_CREATE_FAIL_ON' not in body and 'PIPELINE_CREATE_DISABLE_OPTIMIZATION' not in body
assert module.index('clip_z_module(s, code)')<module.index('g_feedback_module_code[m] = hash_bytes')
assert 'sizeof(key.vs)' in graphics and 'sizeof(key.fs)' in graphics

code=r'''
#include <vulkan/vulkan.h>
#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <cstdio>
uint32_t version=VK_API_VERSION_1_3;unsigned property_queries=0,diagnostic_logs=0;
VkPhysicalDevice vk_physical(){return VK_NULL_HANDLE;}
void p_vkGetPhysicalDeviceProperties(VkPhysicalDevice,VkPhysicalDeviceProperties* props){++property_queries;props->apiVersion=version;}
void log(const char*,...){++diagnostic_logs;}
'''+gate+'\n'+probe+r'''
int main(int argc,char** argv){
 assert(argc==2);const bool off=std::strcmp(argv[1],"off")==0;
 const bool malformed=std::strcmp(argv[1],"malformed")==0;
 const bool unsupported=std::strcmp(argv[1],"unsupported")==0;
 if(off)unsetenv("NX_PIPELINE_FEEDBACK");else setenv("NX_PIPELINE_FEEDBACK",malformed?"1x":"1",1);
 if(unsupported)version=VK_API_VERSION_1_2;
 const bool expected=!off && !malformed && !unsupported;
 for(int repeat=0;repeat<10;++repeat)assert(pipeline_feedback_on()==expected);
 assert(property_queries==unsigned(!off && !malformed));
 assert(diagnostic_logs==property_queries);
 VkPipelineRenderingCreateInfo rendering{VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO};
 VkGraphicsPipelineCreateInfo graphics{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
 graphics.pNext=&rendering;graphics.flags=VK_PIPELINE_CREATE_ALLOW_DERIVATIVES_BIT;
 PipelineFeedbackProbe sample(expected,2);sample.attach(graphics);
 assert(graphics.flags==VK_PIPELINE_CREATE_ALLOW_DERIVATIVES_BIT);
 assert(graphics.pNext==(expected?static_cast<void*>(&sample.info):static_cast<void*>(&rendering)));
 if(expected){assert(sample.info.pNext==&rendering);assert(sample.info.pipelineStageCreationFeedbackCount==2);}
 assert(sample.pipeline.flags==0 && sample.pipeline.duration==0);
 for(const auto& stage:sample.stages)assert(stage.flags==0 && stage.duration==0);
 // Unknown feedback never masquerades as a cache miss, including poisoned durations.
 sample.pipeline.flags=VK_PIPELINE_CREATION_FEEDBACK_APPLICATION_PIPELINE_CACHE_HIT_BIT;
 sample.pipeline.duration=999999;
 assert(!sample.valid(sample.pipeline,VK_SUCCESS));
 assert(sample.cache_hit(sample.pipeline,VK_SUCCESS)==-1);
 assert(sample.duration(sample.pipeline,VK_SUCCESS)==0);
 sample.pipeline.flags|=VK_PIPELINE_CREATION_FEEDBACK_VALID_BIT;
 assert(sample.cache_hit(sample.pipeline,VK_SUCCESS)==1);
 assert(sample.duration(sample.pipeline,VK_SUCCESS)==999999);
 sample.pipeline.flags=VK_PIPELINE_CREATION_FEEDBACK_VALID_BIT;
 assert(sample.cache_hit(sample.pipeline,VK_SUCCESS)==0);
 assert(sample.cache_hit(sample.pipeline,VK_ERROR_OUT_OF_HOST_MEMORY)==-1);
 assert(sample.duration(sample.pipeline,VK_ERROR_OUT_OF_HOST_MEMORY)==0);
 // Compute requests exactly one stage and preserves an existing extension chain.
 VkBaseInStructure prior{VK_STRUCTURE_TYPE_APPLICATION_INFO,nullptr};
 VkComputePipelineCreateInfo compute{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
 compute.pNext=&prior;compute.flags=VK_PIPELINE_CREATE_ALLOW_DERIVATIVES_BIT;
 PipelineFeedbackProbe compute_sample(expected,1);compute_sample.attach(compute);
 assert(compute.flags==VK_PIPELINE_CREATE_ALLOW_DERIVATIVES_BIT);
 assert(compute.pNext==(expected?static_cast<void*>(&compute_sample.info):static_cast<const void*>(&prior)));
 if(expected){assert(compute_sample.info.pNext==&prior);assert(compute_sample.info.pipelineStageCreationFeedbackCount==1);}
 std::printf("PASS feedback %s: device gate, unchanged flags, preserved graphics/compute chains, invalid/failure outputs\n",argv[1]);
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-feedback-') as td:
    folder=Path(td);cpp=folder/'test.cpp';exe=folder/'test';cpp.write_text(code)
    headers=Path.home()/'vkheaders/include'
    subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(headers),str(cpp),'-o',str(exe)],check=True)
    for mode in ['off','malformed','unsupported','on']:
        subprocess.run([str(exe),mode],check=True)

patch=Path(__file__).resolve().parents[2]/'patches/patch-pipeline-creation-feedback.py'
with tempfile.TemporaryDirectory(prefix='sp2-feedback-install-') as td:
    root=Path(td);target=root/'runtime/src/nvn/nvn_pipeline.cpp';target.parent.mkdir(parents=True)
    original=args.source.read_bytes();target.write_bytes(original)
    def run(*flags,ok=True):
        result=subprocess.run([sys.executable,str(patch),'--root',str(root),*flags],capture_output=True,text=True)
        assert (result.returncode==0)==ok,result.stdout+result.stderr
    run('--check');assert target.read_bytes()==original
    run();assert target.read_bytes()==original
    run('--restore');assert b'PATCH-PIPELINE-CREATION-FEEDBACK' not in target.read_bytes()
    run();assert target.read_bytes()==original
    run();assert target.read_bytes()==original
    broken=original.replace(b'    feedback.attach(ci); // keeps the dynamic-rendering or existing extension chain',b'    // changed anchor',1)
    target.write_bytes(broken);run(ok=False);assert target.read_bytes()==broken
    print('PASS feedback installer preflight, idempotence, byte-exact restore/reapply and failed-anchor safety')
