// GPU-lock protected. Only retired, destroyed images may return memory here.
#pragma once
#include <map>
#include <vector>

namespace nx::nvn {
class ImageMemoryCache {
    struct Entry { VkDeviceMemory memory; uint64_t bytes; uint32_t type; };
    std::vector<Entry> free_;
    std::map<VkDeviceMemory, Entry> active_;
    uint64_t bytes_ = 0, budget_;
    size_t limit_;
public:
    explicit ImageMemoryCache(uint64_t budget, size_t limit) : budget_(budget), limit_(limit) {}
    uint64_t cached_bytes() const { return bytes_; }
    size_t cached_count() const { return free_.size(); }
    void drain() {
        for (auto& e : free_) nx::vk::p_vkFreeMemory(vk_device(), e.memory, nullptr);
        free_.clear(); bytes_ = 0;
    }
    VkResult allocate(const VkMemoryAllocateInfo& ai, VkDeviceMemory* out) {
        // Specialized allocations (dedicated/export/device-address) have independent rules.
        if (!budget_ || !limit_ || ai.pNext) return nx::vk::p_vkAllocateMemory(vk_device(), &ai, nullptr, out);
        for (auto it = free_.begin(); it != free_.end(); ++it) {
            if (it->bytes != ai.allocationSize || it->type != ai.memoryTypeIndex) continue;
            Entry e = *it;
            free_.erase(it); bytes_ -= e.bytes;
            active_.emplace(e.memory, e); *out = e.memory;
            return VK_SUCCESS;
        }
        VkResult result = nx::vk::p_vkAllocateMemory(vk_device(), &ai, nullptr, out);
        if (result != VK_SUCCESS && result != VK_ERROR_DEVICE_LOST && !free_.empty()) {
            drain();
            result = nx::vk::p_vkAllocateMemory(vk_device(), &ai, nullptr, out);
        }
        if (result == VK_SUCCESS) active_.emplace(*out, Entry{*out, ai.allocationSize, ai.memoryTypeIndex});
        return result;
    }
    void retire(VkDeviceMemory memory) {
        auto it = active_.find(memory);
        if (it == active_.end()) { nx::vk::p_vkFreeMemory(vk_device(), memory, nullptr); return; }
        Entry e = it->second; active_.erase(it);
        if (!e.bytes || e.bytes > budget_ || !limit_) {
            nx::vk::p_vkFreeMemory(vk_device(), memory, nullptr); return;
        }
        // FIFO eviction and an exact size/type match keep memory bounded across changing resolutions.
        while (!free_.empty() && (free_.size() >= limit_ || bytes_ > budget_ - e.bytes)) {
            Entry old = free_.front(); free_.erase(free_.begin()); bytes_ -= old.bytes;
            nx::vk::p_vkFreeMemory(vk_device(), old.memory, nullptr);
        }
        free_.push_back(e); bytes_ += e.bytes;
    }
};
} // namespace nx::nvn
