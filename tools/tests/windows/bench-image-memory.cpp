#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <windows.h>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <vector>
VkDevice device;
PFN_vkGetInstanceProcAddr gip;
PFN_vkGetDeviceProcAddr gdp;
PFN_vkAllocateMemory allocateMemory;
PFN_vkFreeMemory freeMemory;
uint64_t calls=0;
namespace nx::nvn {VkDevice vk_device(){return device;}}
namespace nx::vk {
VkResult p_vkAllocateMemory(VkDevice d,const VkMemoryAllocateInfo* ai,const VkAllocationCallbacks* cb,VkDeviceMemory* m){++calls;return allocateMemory(d,ai,cb,m);}
void p_vkFreeMemory(VkDevice d,VkDeviceMemory m,const VkAllocationCallbacks* cb){freeMemory(d,m,cb);}
}
#include "image_memory_cache.h"
void check(VkResult r){if(r!=VK_SUCCESS){std::printf("FAIL VkResult %d\n",int(r));std::exit(1);}}
int main(){
 auto dll=LoadLibraryA("vulkan-1.dll");if(!dll)return 1;
 gip=(PFN_vkGetInstanceProcAddr)GetProcAddress(dll,"vkGetInstanceProcAddr");
 auto createInstance=(PFN_vkCreateInstance)gip(nullptr,"vkCreateInstance");
 VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};app.pApplicationName="sp2 allocation benchmark";app.apiVersion=VK_API_VERSION_1_0;
 VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};ici.pApplicationInfo=&app;
 VkInstance instance;check(createInstance(&ici,nullptr,&instance));
 auto enumerate=(PFN_vkEnumeratePhysicalDevices)gip(instance,"vkEnumeratePhysicalDevices");
 auto properties=(PFN_vkGetPhysicalDeviceProperties)gip(instance,"vkGetPhysicalDeviceProperties");
 auto memoryProperties=(PFN_vkGetPhysicalDeviceMemoryProperties)gip(instance,"vkGetPhysicalDeviceMemoryProperties");
 auto queues=(PFN_vkGetPhysicalDeviceQueueFamilyProperties)gip(instance,"vkGetPhysicalDeviceQueueFamilyProperties");
 auto createDevice=(PFN_vkCreateDevice)gip(instance,"vkCreateDevice");
 uint32_t count=0;check(enumerate(instance,&count,nullptr));std::vector<VkPhysicalDevice> all(count);check(enumerate(instance,&count,all.data()));
 VkPhysicalDevice physical=all.at(0);VkPhysicalDeviceProperties props{};
 for(auto p:all){properties(p,&props);if(props.deviceType==VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU){physical=p;break;}}
 properties(physical,&props);std::printf("GPU: %s\n",props.deviceName);
 queues(physical,&count,nullptr);std::vector<VkQueueFamilyProperties> families(count);queues(physical,&count,families.data());
 uint32_t family=0;while(family<count && !(families[family].queueFlags & VK_QUEUE_GRAPHICS_BIT))++family;if(family==count)return 2;
 float priority=1;VkDeviceQueueCreateInfo qi{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};qi.queueFamilyIndex=family;qi.queueCount=1;qi.pQueuePriorities=&priority;
 VkDeviceCreateInfo dci{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};dci.queueCreateInfoCount=1;dci.pQueueCreateInfos=&qi;check(createDevice(physical,&dci,nullptr,&device));
 gdp=(PFN_vkGetDeviceProcAddr)gip(instance,"vkGetDeviceProcAddr");
 allocateMemory=(PFN_vkAllocateMemory)gdp(device,"vkAllocateMemory");freeMemory=(PFN_vkFreeMemory)gdp(device,"vkFreeMemory");
 auto createImage=(PFN_vkCreateImage)gdp(device,"vkCreateImage");auto destroyImage=(PFN_vkDestroyImage)gdp(device,"vkDestroyImage");
 auto requirements=(PFN_vkGetImageMemoryRequirements)gdp(device,"vkGetImageMemoryRequirements");auto bind=(PFN_vkBindImageMemory)gdp(device,"vkBindImageMemory");
 VkPhysicalDeviceMemoryProperties mp;memoryProperties(physical,&mp);
 for(int round=-1;round<8;round++){
  bool enabled=round>=0 && round%2==1;nx::nvn::ImageMemoryCache cache(enabled?128ull<<20:0,128);
  calls=0;auto start=std::chrono::steady_clock::now();
  const int iterations=round<0?24:1200;
  for(int i=0;i<iterations;i++){
   VkImageCreateInfo ci{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};ci.imageType=VK_IMAGE_TYPE_2D;ci.format=VK_FORMAT_R8G8B8A8_UNORM;
   ci.extent={uint32_t(960+(i%24)*4),uint32_t(540+(i%24)*2),1};ci.mipLevels=ci.arrayLayers=1;ci.samples=VK_SAMPLE_COUNT_1_BIT;ci.tiling=VK_IMAGE_TILING_OPTIMAL;
   ci.usage=VK_IMAGE_USAGE_TRANSFER_DST_BIT|VK_IMAGE_USAGE_TRANSFER_SRC_BIT|VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT|VK_IMAGE_USAGE_SAMPLED_BIT;
   VkImage image;check(createImage(device,&ci,nullptr,&image));VkMemoryRequirements req;requirements(device,image,&req);
   uint32_t type=0;while(type<mp.memoryTypeCount && (!(req.memoryTypeBits&(1u<<type)) || !(mp.memoryTypes[type].propertyFlags&VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)))++type;
   if(type==mp.memoryTypeCount)return 3;
   VkMemoryAllocateInfo ai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};ai.allocationSize=req.size;ai.memoryTypeIndex=type;
   VkDeviceMemory memory;check(cache.allocate(ai,&memory));check(bind(device,image,memory,0));
   destroyImage(device,image,nullptr);cache.retire(memory);
  }
  // Include releasing the bounded pool in the timing.
  auto retained=cache.cached_bytes();cache.drain();
  double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
  std::printf("round=%d cached=%d images=%d allocations=%llu retained_bytes=%llu ms=%.3f\n",round,int(enabled),iterations,(unsigned long long)calls,(unsigned long long)retained,ms);std::fflush(stdout);
 }
 ((PFN_vkDestroyDevice)gdp(device,"vkDestroyDevice"))(device,nullptr);
 ((PFN_vkDestroyInstance)gip(instance,"vkDestroyInstance"))(instance,nullptr);
}
