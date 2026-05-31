/**
 * Damru Vulkan Implicit Layer for redroid (x86_64)
 *
 * Intercepts vkGetPhysicalDeviceProperties2 to clear the driverInfo
 * field from SwiftShader ("LLVM 10.0.0") which ANGLE embeds into
 * GL_RENDERER and is a detectable emulator tell.
 *
 * Build (WSL gcc targeting x86_64 ELF):
 *   gcc -shared -fPIC -nostdlib -ffreestanding -O2 \
 *       -fcf-protection=none -fno-stack-protector \
 *       -Wl,--build-id=none -Wl,-z,norelro \
 *       -o libVkLayer_damru.so vulkan_layer.c
 */

/* ── Minimal type definitions (no libc headers) ─────────────── */

typedef unsigned int     uint32_t;
typedef unsigned long    uintptr_t;
typedef unsigned long    size_t;
typedef int              VkResult;

#define VK_SUCCESS       0
#define VK_INCOMPLETE    5
#define VK_ERROR_INITIALIZATION_FAILED  ((VkResult)-3)
#define NULL             ((void*)0)

typedef struct VkInstance_T*        VkInstance;
typedef struct VkPhysicalDevice_T*  VkPhysicalDevice;
typedef struct VkDevice_T*          VkDevice;

#define VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES  1000196000
#define VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO        47
#define VK_LAYER_LINK_INFO                                   0

#define VK_MAX_DRIVER_NAME_SIZE  256
#define VK_MAX_DRIVER_INFO_SIZE  256

/* ── Vulkan structures ──────────────────────────────────────── */

typedef struct VkBaseOutStructure {
    uint32_t sType;
    struct VkBaseOutStructure* pNext;
} VkBaseOutStructure;

typedef struct {
    uint32_t sType;
    void*    pNext;
    uint32_t driverID;
    char     driverName[VK_MAX_DRIVER_NAME_SIZE];
    char     driverInfo[VK_MAX_DRIVER_INFO_SIZE];
    /* conformanceVersion follows but we don't care */
} VkPhysicalDeviceDriverProperties;

/* Layer dispatch chain types */
typedef void  (*PFN_vkVoidFunction)(void);
typedef PFN_vkVoidFunction (*PFN_vkGetInstanceProcAddr)(VkInstance, const char*);
typedef PFN_vkVoidFunction (*PFN_vkGetDeviceProcAddr)(VkDevice, const char*);

typedef void (*PFN_vkGetPhysicalDeviceProperties2)(
    VkPhysicalDevice, void* /* VkPhysicalDeviceProperties2* */);

typedef VkResult (*PFN_vkCreateInstance)(
    const void* /* VkInstanceCreateInfo* */,
    const void* /* VkAllocationCallbacks* */,
    VkInstance*);

typedef struct VkLayerInstanceLink {
    struct VkLayerInstanceLink* pNext;
    PFN_vkGetInstanceProcAddr   pfnNextGetInstanceProcAddr;
    PFN_vkGetInstanceProcAddr   pfnNextGetPhysicalDeviceProcAddr;
} VkLayerInstanceLink;

typedef struct {
    uint32_t             sType;
    const void*          pNext;
    uint32_t             function;
    VkLayerInstanceLink* pLayerInfo;
} VkLayerInstanceCreateInfo;

typedef struct {
    uint32_t                  sType;
    void*                     pNext;
    uint32_t                  loaderLayerInterfaceVersion;
    PFN_vkGetInstanceProcAddr pfnGetInstanceProcAddr;
    PFN_vkGetDeviceProcAddr   pfnGetDeviceProcAddr;
    PFN_vkGetInstanceProcAddr pfnGetPhysicalDeviceProcAddr;
} VkNegotiateLayerInterface;

typedef struct {
    char     layerName[256];
    uint32_t specVersion;
    uint32_t implementationVersion;
    char     description[256];
} VkLayerProperties;


/* ── Inline helpers (no libc) ───────────────────────────────── */

static int str_eq(const char* a, const char* b) {
    if (!a || !b) return 0;
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

static void str_copy(char* dst, const char* src, int max) {
    int i = 0;
    while (i < max - 1 && src[i]) { dst[i] = src[i]; i++; }
    while (i < max) { dst[i] = 0; i++; }
}

static void mem_zero(void* dst, size_t n) {
    char* p = (char*)dst;
    while (n--) *p++ = 0;
}


/* ── Layer state ────────────────────────────────────────────── */

static PFN_vkGetInstanceProcAddr           g_nextGIPA     = 0;
static PFN_vkGetPhysicalDeviceProperties2  g_nextProps2    = 0;
static PFN_vkGetPhysicalDeviceProperties2  g_nextProps2KHR = 0;


/* ── pNext chain walker — clear driverInfo ──────────────────── */

static void fixup_driver_props(void* props_void) {
    /* props_void is VkPhysicalDeviceProperties2*.
     * First: modify deviceName (at offset 16+16 = 32 within base props) as a
     * marker to prove the layer interception is working.
     * deviceName is at: props_void + 16 (sType+pNext of Props2) + 16 (apiVersion+driverVersion+vendorID+deviceID+deviceType)
     * Actually: sType(4)+pad(4)+pNext(8) = 16, then properties starts:
     *   apiVersion(4)+driverVersion(4)+vendorID(4)+deviceID(4)+deviceType(4) = 20
     *   deviceName starts at props_void + 16 + 20 = 36 */
    char* deviceName = (char*)props_void + 16 + 20;
    /* Prepend "L>" to deviceName to prove layer is active */
    if (deviceName[0] != 'L' || deviceName[1] != '>') {
        /* Shift existing name right by 2 chars and prepend marker */
        int len = 0;
        while (len < 250 && deviceName[len]) len++;
        int i;
        for (i = len; i >= 0; i--) deviceName[i+2] = deviceName[i];
        deviceName[0] = 'L';
        deviceName[1] = '>';
    }

    /* Walk pNext chain to clear driverInfo */
    VkBaseOutStructure** ppNext = (VkBaseOutStructure**)((char*)props_void + 8);
    VkBaseOutStructure* s = *ppNext;
    while (s) {
        if (s->sType == VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES) {
            VkPhysicalDeviceDriverProperties* drv =
                (VkPhysicalDeviceDriverProperties*)s;
            mem_zero(drv->driverInfo, VK_MAX_DRIVER_INFO_SIZE);
            return;
        }
        s = s->pNext;
    }
}


/* ── Intercepted Vulkan functions ───────────────────────────── */

static void damru_GetPhysicalDeviceProperties2(
    VkPhysicalDevice physDev, void* props)
{
    if (g_nextProps2)
        g_nextProps2(physDev, props);
    fixup_driver_props(props);
}

static void damru_GetPhysicalDeviceProperties2KHR(
    VkPhysicalDevice physDev, void* props)
{
    if (g_nextProps2KHR)
        g_nextProps2KHR(physDev, props);
    fixup_driver_props(props);
}

static VkResult damru_CreateInstance(
    const void* pCreateInfo, const void* pAllocator, VkInstance* pInstance)
{
    if (!pCreateInfo)
        return VK_ERROR_INITIALIZATION_FAILED;

    /* Walk pNext chain to find VkLayerInstanceCreateInfo with LINK_INFO */
    const VkBaseOutStructure* ci = (const VkBaseOutStructure*)pCreateInfo;
    VkBaseOutStructure* chain = (VkBaseOutStructure*)ci->pNext;

    VkLayerInstanceCreateInfo* layerInfo = 0;
    while (chain) {
        if (chain->sType == VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO) {
            VkLayerInstanceCreateInfo* info = (VkLayerInstanceCreateInfo*)chain;
            if (info->function == VK_LAYER_LINK_INFO) {
                layerInfo = info;
                break;
            }
        }
        chain = chain->pNext;
    }

    if (!layerInfo || !layerInfo->pLayerInfo)
        return VK_ERROR_INITIALIZATION_FAILED;

    /* Save next layer's GetInstanceProcAddr */
    PFN_vkGetInstanceProcAddr nextGIPA =
        layerInfo->pLayerInfo->pfnNextGetInstanceProcAddr;
    if (!nextGIPA)
        return VK_ERROR_INITIALIZATION_FAILED;

    g_nextGIPA = nextGIPA;

    /* Advance the chain */
    layerInfo->pLayerInfo = layerInfo->pLayerInfo->pNext;

    /* Get real vkCreateInstance from next layer/ICD */
    PFN_vkCreateInstance nextCreate = (PFN_vkCreateInstance)
        nextGIPA((VkInstance)0, "vkCreateInstance");
    if (!nextCreate)
        return VK_ERROR_INITIALIZATION_FAILED;

    /* Call through */
    VkResult result = nextCreate(pCreateInfo, pAllocator, pInstance);
    if (result != VK_SUCCESS)
        return result;

    /* Now resolve Properties2 functions for later interception */
    if (*pInstance) {
        g_nextProps2 = (PFN_vkGetPhysicalDeviceProperties2)
            nextGIPA(*pInstance, "vkGetPhysicalDeviceProperties2");
        g_nextProps2KHR = (PFN_vkGetPhysicalDeviceProperties2)
            nextGIPA(*pInstance, "vkGetPhysicalDeviceProperties2KHR");
    }

    return VK_SUCCESS;
}


/* ── Layer dispatch ─────────────────────────────────────────── */

static PFN_vkVoidFunction damru_GetInstanceProcAddr(
    VkInstance instance, const char* funcName)
{
    if (!funcName)
        return 0;

    if (str_eq(funcName, "vkCreateInstance"))
        return (PFN_vkVoidFunction)damru_CreateInstance;

    if (str_eq(funcName, "vkGetInstanceProcAddr"))
        return (PFN_vkVoidFunction)damru_GetInstanceProcAddr;

    if (str_eq(funcName, "vkGetPhysicalDeviceProperties2"))
        return (PFN_vkVoidFunction)damru_GetPhysicalDeviceProperties2;

    if (str_eq(funcName, "vkGetPhysicalDeviceProperties2KHR"))
        return (PFN_vkVoidFunction)damru_GetPhysicalDeviceProperties2KHR;

    /* Chain everything else */
    if (g_nextGIPA)
        return g_nextGIPA(instance, funcName);
    return 0;
}

static PFN_vkVoidFunction damru_GetDeviceProcAddr(
    VkDevice device, const char* funcName)
{
    (void)device; (void)funcName;
    return 0;
}


/* ── Exported entry points ──────────────────────────────────── */

__attribute__((visibility("default")))
VkResult vkNegotiateLoaderLayerInterfaceVersion(
    VkNegotiateLayerInterface* iface)
{
    if (!iface) return VK_ERROR_INITIALIZATION_FAILED;

    iface->pfnGetInstanceProcAddr        = damru_GetInstanceProcAddr;
    iface->pfnGetDeviceProcAddr          = damru_GetDeviceProcAddr;
    iface->pfnGetPhysicalDeviceProcAddr  = damru_GetInstanceProcAddr;

    if (iface->loaderLayerInterfaceVersion > 2)
        iface->loaderLayerInterfaceVersion = 2;

    return VK_SUCCESS;
}

__attribute__((visibility("default")))
PFN_vkVoidFunction vkGetInstanceProcAddr(
    VkInstance instance, const char* funcName)
{
    return damru_GetInstanceProcAddr(instance, funcName);
}

__attribute__((visibility("default")))
VkResult vkEnumerateInstanceLayerProperties(
    uint32_t* pCount, VkLayerProperties* pProps)
{
    if (!pCount) return VK_ERROR_INITIALIZATION_FAILED;
    if (!pProps) { *pCount = 1; return VK_SUCCESS; }
    if (*pCount == 0) return VK_INCOMPLETE;

    str_copy(pProps[0].layerName, "VK_LAYER_DAMRU_driverinfo", 256);
    str_copy(pProps[0].description, "Clear SwiftShader driverInfo tell", 256);
    pProps[0].specVersion = (1u << 22) | (3u << 12);
    pProps[0].implementationVersion = 1;
    *pCount = 1;
    return VK_SUCCESS;
}

__attribute__((visibility("default")))
VkResult vkEnumerateInstanceExtensionProperties(
    const char* layerName, uint32_t* pCount, void* pProps)
{
    (void)layerName; (void)pProps;
    if (pCount) *pCount = 0;
    return VK_SUCCESS;
}
