#!/usr/bin/env python3
"""Add opt-in Vulkan 1.3 pipeline-cache feedback and account for compute creation time."""
from pathlib import Path
import argparse, os

HELPER = b'''// PATCH-PIPELINE-CREATION-FEEDBACK: diagnostic only; pipeline flags are unchanged.
static bool pipeline_feedback_on() {
    static const bool requested = [] {
        const char* value = std::getenv("NX_PIPELINE_FEEDBACK");
        return value && value[0] == '1' && value[1] == 0;
    }();
    if (!requested) return false;
    static const bool supported = [] {
        VkPhysicalDeviceProperties properties{};
        p_vkGetPhysicalDeviceProperties(vk_physical(), &properties);
        const bool available = properties.apiVersion >= VK_API_VERSION_1_3;
        log("nvn/vk: pipeline feedback %s (NX_PIPELINE_FEEDBACK, device API %u.%u)",
            available ? "enabled" : "unsupported: Vulkan 1.3 required",
            VK_API_VERSION_MAJOR(properties.apiVersion), VK_API_VERSION_MINOR(properties.apiVersion));
        return available;
    }();
    return supported;
}

struct PipelineFeedbackProbe {
    bool enabled;
    VkPipelineCreationFeedback pipeline{};
    VkPipelineCreationFeedback stages[2]{};
    VkPipelineCreationFeedbackCreateInfo info{VK_STRUCTURE_TYPE_PIPELINE_CREATION_FEEDBACK_CREATE_INFO};
    PipelineFeedbackProbe(bool active, uint32_t count) : enabled(active) {
        info.pPipelineCreationFeedback = &pipeline;
        info.pipelineStageCreationFeedbackCount = std::min(count, 2u);
        info.pPipelineStageCreationFeedbacks = stages;
    }
    template<class CreateInfo> void attach(CreateInfo& create) {
        if (!enabled) return;
        info.pNext = create.pNext;
        create.pNext = &info;
    }
    static bool valid(const VkPipelineCreationFeedback& value, VkResult result) {
        return result == VK_SUCCESS && (value.flags & VK_PIPELINE_CREATION_FEEDBACK_VALID_BIT);
    }
    static int cache_hit(const VkPipelineCreationFeedback& value, VkResult result) {
        return valid(value, result)
            ? int(bool(value.flags & VK_PIPELINE_CREATION_FEEDBACK_APPLICATION_PIPELINE_CACHE_HIT_BIT)) : -1;
    }
    static uint64_t duration(const VkPipelineCreationFeedback& value, VkResult result) {
        return valid(value, result) ? value.duration : 0;
    }
};

// Only populated with feedback enabled. Hash the actual module after integer,
// unwritten-input, clip and output transforms, rather than just its asset hash.
static std::map<VkShaderModule, uint64_t> g_feedback_module_code;
static uint64_t feedback_code_hash(VkShaderModule module) {
    auto found = g_feedback_module_code.find(module);
    return found == g_feedback_module_code.end() ? 0 : found->second;
}
static void report_pipeline_feedback(const char* type, const PipelineFeedbackProbe& feedback,
        VkResult result, uint64_t elapsed, uint64_t recipe, uint64_t code0, uint64_t code1) {
    if (!feedback.enabled) return;
    static uint64_t records = 0;
    if (++records > 8192) return;
    log("PIPE_FEEDBACK frame=%llu type=%s recipe=%016llx code0=%016llx code1=%016llx result=%d "
        "host_ms=%.3f valid=%u cache_hit=%d driver_ns=%llu stages=%u stage0_hit=%d stage0_ns=%llu stage1_hit=%d stage1_ns=%llu",
        (unsigned long long)nx::g_frame.load(), type, (unsigned long long)recipe,
        (unsigned long long)code0, (unsigned long long)code1, int(result), double(elapsed)/1e6,
        unsigned(PipelineFeedbackProbe::valid(feedback.pipeline, result)),
        PipelineFeedbackProbe::cache_hit(feedback.pipeline, result),
        (unsigned long long)PipelineFeedbackProbe::duration(feedback.pipeline, result),
        feedback.info.pipelineStageCreationFeedbackCount,
        PipelineFeedbackProbe::cache_hit(feedback.stages[0], result),
        (unsigned long long)PipelineFeedbackProbe::duration(feedback.stages[0], result),
        feedback.info.pipelineStageCreationFeedbackCount > 1 ? PipelineFeedbackProbe::cache_hit(feedback.stages[1], result) : -1,
        (unsigned long long)(feedback.info.pipelineStageCreationFeedbackCount > 1 ? PipelineFeedbackProbe::duration(feedback.stages[1], result) : 0));
}
// END-PATCH-PIPELINE-CREATION-FEEDBACK

'''

CHANGES = [
    (b'VkShaderStageFlags stage_bit(ShaderStage s) {', HELPER+b'VkShaderStageFlags stage_bit(ShaderStage s) {'),
    (b'        if (p_vkCreateShaderModule(vk_device(), &ci, nullptr, &m) != VK_SUCCESS) log("nvn/vk: shader %s rejected", s->hash.c_str());',
     b'''        if (p_vkCreateShaderModule(vk_device(), &ci, nullptr, &m) != VK_SUCCESS) log("nvn/vk: shader %s rejected", s->hash.c_str());
        if (m && pipeline_feedback_on()) // PATCH-PIPELINE-CREATION-FEEDBACK
            g_feedback_module_code[m] = hash_bytes(reinterpret_cast<const unsigned char*>(code.data()), code.size()*sizeof(uint32_t));'''),
    (b'''    VkPipeline p = VK_NULL_HANDLE;
    const uint64_t t0 = plat::monotonic_ns();
    VkResult made = p_vkCreateGraphicsPipelines(vk_device(), pipeline_cache(), 1, &ci, nullptr, &p);
    note_pipeline_created(plat::monotonic_ns() - t0);''',
     b'''    PipelineFeedbackProbe feedback(pipeline_feedback_on(), nstages); // PATCH-PIPELINE-CREATION-FEEDBACK
    feedback.attach(ci); // keeps the dynamic-rendering or existing extension chain
    VkPipeline p = VK_NULL_HANDLE;
    const uint64_t t0 = plat::monotonic_ns();
    VkResult made = p_vkCreateGraphicsPipelines(vk_device(), pipeline_cache(), 1, &ci, nullptr, &p);
    const uint64_t elapsed = plat::monotonic_ns() - t0;
    note_pipeline_created(elapsed);
    if (feedback.enabled) {
        Key recipe = k;
        std::memset(recipe.b + offsetof(PipelineKey, vs), 0, sizeof(key.vs));
        std::memset(recipe.b + offsetof(PipelineKey, fs), 0, sizeof(key.fs));
        uint64_t codes[2] = {};
        for (uint32_t stage = 0; stage < nstages && stage < 2; ++stage)
            codes[stage] = feedback_code_hash(stages[stage].module);
        uint64_t signature = hash_bytes(recipe.b, sizeof recipe.b) ^ codes[0] ^ (codes[1] << 1) ^ layout.dynamic;
        report_pipeline_feedback("graphics", feedback, made, elapsed, signature, codes[0], codes[1]);
    }'''),
    (b'''        if (p_vkCreateComputePipelines(vk_device(), pipeline_cache(), 1, &ci, nullptr, &p) != VK_SUCCESS) {''',
     b'''        PipelineFeedbackProbe feedback(pipeline_feedback_on(), 1); // PATCH-PIPELINE-CREATION-FEEDBACK
        feedback.attach(ci);
        const uint64_t t0 = plat::monotonic_ns();
        VkResult made = p_vkCreateComputePipelines(vk_device(), pipeline_cache(), 1, &ci, nullptr, &p);
        const uint64_t elapsed = plat::monotonic_ns() - t0;
        note_pipeline_created(elapsed); // compute creation was previously missing from the frame CSV
        if (feedback.enabled) {
            uint64_t code = feedback_code_hash(ci.stage.module);
            report_pipeline_feedback("compute", feedback, made, elapsed, code ^ layout.dynamic, code, 0);
        }
        if (made != VK_SUCCESS) {'''),
]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))))
    parser.add_argument('--check',action='store_true');parser.add_argument('--restore',action='store_true')
    args=parser.parse_args();path=args.root/'runtime/src/nvn/nvn_pipeline.cpp';data=path.read_bytes()
    for old,new in CHANGES:
        if data.count(new)==1:data=data.replace(new,old if args.restore else new,1)
        elif data.count(old)==1:data=data.replace(old,old if args.restore else new,1)
        else:raise SystemExit('Pipeline feedback anchor mismatch; no files changed')
    if args.check:print('Preflight passed');return
    path.write_bytes(data);print('Restored' if args.restore else 'Applied; rebuild nvn_pipeline.cpp')
if __name__=='__main__':main()
