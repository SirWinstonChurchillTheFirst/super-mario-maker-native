#!/usr/bin/env python3
"""patch_guest_dmabuf.py RUNTIME_SRC_DIR (…/runtime/src) : MEM2 in GPU memory instead of an imported host pointer.

Linux / amdgpu: the runtime imported guest memory (MEM2: 1 GiB) with VK_EXT_external_memory_host, i.e. as a
userptr buffer object. RADV puts every buffer object in every submission (buffer device addresses), and amdgpu
re-reads the page list of each userptr object on every submission: on the console ~2.5 ms per submit; Super Mario
Maker submits 4 times a frame and its command processor thread spent 76% of its time in that ioctl.

TTT2_GUEST_DMABUF=1: right after the guest address space is reserved (before anything is loaded into it), a small
Vulkan device allocates MEM2 as exportable host-visible GPU memory (dma-buf), which is mapped over the guest range;
the renderer later imports that dma-buf (VK_EXT_external_memory_dma_buf) instead of the host pointer. Falls back to
the old import when anything is missing. The early device stays alive (it owns the allocation)."""
import sys

src = sys.argv[1]


def patch(rel, pairs):
    p = src + "/" + rel
    s = open(p, encoding="utf-8").read()
    if "patch_guest_dmabuf" in s:
        print(rel + ": already applied")
        return
    for old, new in pairs:
        assert s.count(old) == 1, rel + ": pattern not found or not unique: " + old[:80]
        s = s.replace(old, new)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched", p)


patch("gpu/vulkan/context.h", [(
    "    PFN_vkGetMemoryHostPointerPropertiesEXT get_memory_host_pointer_properties = nullptr;\n",
    "    PFN_vkGetMemoryHostPointerPropertiesEXT get_memory_host_pointer_properties = nullptr;\n"
    "    PFN_vkGetMemoryFdPropertiesKHR get_memory_fd_properties = nullptr; // port/patch_guest_dmabuf.py\n"
    "    bool dma_buf_import = false;\n")])

EARLY = r'''
// port/patch_guest_dmabuf.py: MEM2 as exportable GPU memory, mapped at the guest address before anything is loaded.
#ifdef __linux__
} // namespace cafe::gpu::vk
#include <sys/mman.h>
#include <unistd.h>
namespace cafe::gpu::vk {
namespace {
int g_guest_fd = -1;           // the dma-buf of MEM2 (kept open)
uint64_t g_guest_fd_size = 0;
VkInstance g_early_instance = VK_NULL_HANDLE;
VkDevice g_early_device = VK_NULL_HANDLE;
} // namespace

void early_guest_memory() {
    const char* v = std::getenv("TTT2_GUEST_DMABUF");
    if (v == nullptr || *v == '0') return;
    const auto fail = [](const char* what) { std::fprintf(stderr, "ttt2: GPU: MEM2 dma-buf not used: %s\n", what); };
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    app.apiVersion = VK_API_VERSION_1_3;
    VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    ici.pApplicationInfo = &app;
    if (vkCreateInstance(&ici, nullptr, &g_early_instance) != VK_SUCCESS) return fail("no Vulkan instance");
    uint32_t count = 0;
    vkEnumeratePhysicalDevices(g_early_instance, &count, nullptr);
    std::vector<VkPhysicalDevice> devices(count);
    vkEnumeratePhysicalDevices(g_early_instance, &count, devices.data());
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    for (VkPhysicalDevice d : devices) {
        uint32_t n = 0;
        vkEnumerateDeviceExtensionProperties(d, nullptr, &n, nullptr);
        std::vector<VkExtensionProperties> ext(n);
        vkEnumerateDeviceExtensionProperties(d, nullptr, &n, ext.data());
        bool fd = false, dma = false;
        for (const auto& e : ext) {
            fd |= std::strcmp(e.extensionName, VK_KHR_EXTERNAL_MEMORY_FD_EXTENSION_NAME) == 0;
            dma |= std::strcmp(e.extensionName, VK_EXT_EXTERNAL_MEMORY_DMA_BUF_EXTENSION_NAME) == 0;
        }
        if (fd && dma) {
            physical = d;
            break;
        }
    }
    if (physical == VK_NULL_HANDLE) return fail("no GPU with dma-buf export");
    const float priority = 1.0f;
    VkDeviceQueueCreateInfo qci{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    qci.queueFamilyIndex = 0;
    qci.queueCount = 1;
    qci.pQueuePriorities = &priority;
    const char* exts[] = {VK_KHR_EXTERNAL_MEMORY_FD_EXTENSION_NAME, VK_EXT_EXTERNAL_MEMORY_DMA_BUF_EXTENSION_NAME};
    VkDeviceCreateInfo dci{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
    dci.queueCreateInfoCount = 1;
    dci.pQueueCreateInfos = &qci;
    dci.enabledExtensionCount = 2;
    dci.ppEnabledExtensionNames = exts;
    if (vkCreateDevice(physical, &dci, nullptr, &g_early_device) != VK_SUCCESS) return fail("no device");
    VkPhysicalDeviceMemoryProperties mp;
    vkGetPhysicalDeviceMemoryProperties(physical, &mp);
    const VkMemoryPropertyFlags want[] = {
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT};
    uint32_t type = UINT32_MAX;
    for (VkMemoryPropertyFlags w : want) {
        for (uint32_t i = 0; i < mp.memoryTypeCount && type == UINT32_MAX; ++i) {
            if ((mp.memoryTypes[i].propertyFlags & w) == w &&
                !(mp.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)) {
                type = i;
            }
        }
        if (type != UINT32_MAX) break;
    }
    if (type == UINT32_MAX) return fail("no host-visible system memory type");
    const uint64_t size = uint64_t{layout::kMem2End} - layout::kMem2Base;
    VkExportMemoryAllocateInfo export_info{VK_STRUCTURE_TYPE_EXPORT_MEMORY_ALLOCATE_INFO};
    export_info.handleTypes = VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT;
    VkMemoryAllocateInfo mai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    mai.pNext = &export_info;
    mai.allocationSize = size;
    mai.memoryTypeIndex = type;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    if (vkAllocateMemory(g_early_device, &mai, nullptr, &memory) != VK_SUCCESS) return fail("allocation failed");
    const auto get_fd = reinterpret_cast<PFN_vkGetMemoryFdKHR>(vkGetDeviceProcAddr(g_early_device, "vkGetMemoryFdKHR"));
    VkMemoryGetFdInfoKHR gfi{VK_STRUCTURE_TYPE_MEMORY_GET_FD_INFO_KHR};
    gfi.memory = memory;
    gfi.handleType = VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT;
    int fd = -1;
    if (get_fd == nullptr || get_fd(g_early_device, &gfi, &fd) != VK_SUCCESS || fd < 0) return fail("no fd");
    void* at = guest_pointer(layout::kMem2Base);
    void* mapped = mmap(at, size, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_FIXED, fd, 0);
    if (mapped != at) {
        // The reservation there is intact (MAP_FIXED failed before replacing it).
        close(fd);
        return fail("mmap of the dma-buf failed");
    }
    g_guest_fd = fd;
    g_guest_fd_size = size;
    std::fprintf(stderr, "ttt2: GPU: MEM2 0x%08X-0x%08X in GPU memory (dma-buf, memory type %u)\n", layout::kMem2Base,
                 layout::kMem2End - 1, type);
}
#else
void early_guest_memory() {}
#endif
'''

patch("gpu/vulkan/context.cpp", [
    # function pointer + extensions on the renderer's device
    ("    custom_border_color = has_extension(available, VK_EXT_CUSTOM_BORDER_COLOR_EXTENSION_NAME);\n",
     "    custom_border_color = has_extension(available, VK_EXT_CUSTOM_BORDER_COLOR_EXTENSION_NAME);\n"
     "    // port/patch_guest_dmabuf.py: importing MEM2's dma-buf\n"
     "    dma_buf_import = has_extension(available, VK_KHR_EXTERNAL_MEMORY_FD_EXTENSION_NAME) &&\n"
     "                     has_extension(available, VK_EXT_EXTERNAL_MEMORY_DMA_BUF_EXTENSION_NAME);\n"
     "    if (dma_buf_import) {\n"
     "        device_extensions.push_back(VK_KHR_EXTERNAL_MEMORY_FD_EXTENSION_NAME);\n"
     "        device_extensions.push_back(VK_EXT_EXTERNAL_MEMORY_DMA_BUF_EXTENSION_NAME);\n"
     "    }\n"),
    ("    get_memory_host_pointer_properties = reinterpret_cast<PFN_vkGetMemoryHostPointerPropertiesEXT>(\n"
     "        vkGetDeviceProcAddr(device, \"vkGetMemoryHostPointerPropertiesEXT\"));\n",
     "    get_memory_host_pointer_properties = reinterpret_cast<PFN_vkGetMemoryHostPointerPropertiesEXT>(\n"
     "        vkGetDeviceProcAddr(device, \"vkGetMemoryHostPointerPropertiesEXT\"));\n"
     "    if (dma_buf_import) { // port/patch_guest_dmabuf.py\n"
     "        get_memory_fd_properties = reinterpret_cast<PFN_vkGetMemoryFdPropertiesKHR>(\n"
     "            vkGetDeviceProcAddr(device, \"vkGetMemoryFdPropertiesKHR\"));\n"
     "    }\n"),
    # early allocation, before GuestMemory::init
    ("void GuestMemory::init(Context& c) {\n",
     EARLY.lstrip("\n") + "\nvoid GuestMemory::init(Context& c) {\n"),
    # import of the dma-buf in place of the host pointer
    ("        void* host = guest_pointer(r.base);\n",
     "#ifdef __linux__\n"
     "        if (r.base == layout::kMem2Base && g_guest_fd >= 0 && c.dma_buf_import && c.get_memory_fd_properties) {\n"
     "            // port/patch_guest_dmabuf.py: MEM2 is a dma-buf already: imported as such (no userptr object).\n"
     "            Region region{r.base, size, {}};\n"
     "            VkExternalMemoryBufferCreateInfo ext{VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_BUFFER_CREATE_INFO};\n"
     "            ext.handleTypes = VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT;\n"
     "            VkBufferCreateInfo bci{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};\n"
     "            bci.pNext = &ext;\n"
     "            bci.size = size;\n"
     "            bci.usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT |\n"
     "                        VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT |\n"
     "                        VK_BUFFER_USAGE_INDEX_BUFFER_BIT | VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT;\n"
     "            VK_CHECK(vkCreateBuffer(c.device, &bci, nullptr, &region.buffer.buffer));\n"
     "            VkMemoryRequirements req;\n"
     "            vkGetBufferMemoryRequirements(c.device, region.buffer.buffer, &req);\n"
     "            VkMemoryFdPropertiesKHR fdp{VK_STRUCTURE_TYPE_MEMORY_FD_PROPERTIES_KHR};\n"
     "            const int fd = dup(g_guest_fd);\n"
     "            if (fd >= 0 && c.get_memory_fd_properties(c.device, VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT, fd, &fdp) ==\n"
     "                               VK_SUCCESS &&\n"
     "                (fdp.memoryTypeBits & req.memoryTypeBits) != 0) {\n"
     "                VkImportMemoryFdInfoKHR import{VK_STRUCTURE_TYPE_IMPORT_MEMORY_FD_INFO_KHR};\n"
     "                import.handleType = VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT;\n"
     "                import.fd = fd; // owned by the driver on success\n"
     "                VkMemoryAllocateFlagsInfo flags{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_FLAGS_INFO};\n"
     "                flags.flags = VK_MEMORY_ALLOCATE_DEVICE_ADDRESS_BIT;\n"
     "                flags.pNext = &import;\n"
     "                VkMemoryAllocateInfo mai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};\n"
     "                mai.pNext = &flags;\n"
     "                mai.allocationSize = g_guest_fd_size;\n"
     "                mai.memoryTypeIndex = c.memory_type(fdp.memoryTypeBits & req.memoryTypeBits, 0);\n"
     "                if (vkAllocateMemory(c.device, &mai, nullptr, &region.buffer.memory) == VK_SUCCESS) {\n"
     "                    VK_CHECK(vkBindBufferMemory(c.device, region.buffer.buffer, region.buffer.memory, 0));\n"
     "                    VkBufferDeviceAddressInfo bai{VK_STRUCTURE_TYPE_BUFFER_DEVICE_ADDRESS_INFO};\n"
     "                    bai.buffer = region.buffer.buffer;\n"
     "                    region.buffer.address = vkGetBufferDeviceAddress(c.device, &bai);\n"
     "                    region.buffer.size = size;\n"
     "                    std::fprintf(stderr, \"ttt2: GPU: guest memory 0x%08X-0x%08X imported as dma-buf\\n\", r.base,\n"
     "                                 r.base + size - 1);\n"
     "                    regions_.push_back(region);\n"
     "                    continue;\n"
     "                }\n"
     "                close(fd);\n"
     "            } else if (fd >= 0) {\n"
     "                close(fd);\n"
     "            }\n"
     "            std::fprintf(stderr, \"ttt2: GPU: dma-buf import of MEM2 failed, host pointer import\\n\");\n"
     "            vkDestroyBuffer(c.device, region.buffer.buffer, nullptr);\n"
     "        }\n"
     "#endif\n"
     "        void* host = guest_pointer(r.base);\n"),
])
