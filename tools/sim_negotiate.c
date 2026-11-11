/*
 * sim_negotiate.c —— 通过 libhidisplayclient.so 模拟一次 HDMI 能力协商
 *
 * 思路：DisplayClient 走 binder 找到已注册的 "display" 服务，
 *       调 GetDisplayCapability(Parcel*) 拿到 Sink 能力表；
 *       同时读 GetEncFmt/GetDisplayDeviceType/GetOptimalFormatEnable。
 *
 * 编译（设备上或交叉编译）：
 *   arm-linux-gnueabi-gcc -o sim_negotiate sim_negotiate.c \
 *       -L/system/lib -lhidisplayclient -lbinder -lutils -lcutils -lui
 *
 * 用法： push 到 /data/local/tmp 执行
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- DisplayClient 的 mangled 名字（从 so 的 dynsym 里拿到）---- */
/* _ZN7android13DisplayClient17getDisplayServiceEv */
/* _ZN7android13DisplayClient20GetDisplayCapabilityEPNS_6ParcelE */
/* _ZN7android13DisplayClient9GetEncFmtEv */
/* _ZN7android13DisplayClient20GetDisplayDeviceTypeEv */
/* _ZN7android13DisplayClient22GetOptimalFormatEnableEv */
/* _ZN7android13DisplayClient6ReloadEv */
/* _ZN7android13DisplayClient18GetHDMISuspendEnableEv */
/* _ZN7android13DisplayClient18GetHDMISuspendTimeEv */

extern void *DisplayClient_getDisplayService();
extern int   DisplayClient_GetDisplayCapability(void *self, void *parcel);
extern int   DisplayClient_GetEncFmt(void *self);
extern int   DisplayClient_GetDisplayDeviceType(void *self);
extern int   DisplayClient_GetOptimalFormatEnable(void *self);
extern int   DisplayClient_Reload(void *self);
extern int   DisplayClient_GetHDMISuspendEnable(void *self);
extern int   DisplayClient_GetHDMISuspendTime(void *self);

int main(void) {
    printf("=== HDMI 能力协商模拟 (via libhidisplayclient) ===\n");

    void *svc = DisplayClient_getDisplayService();
    printf("getDisplayService() = %p\n", svc);
    if (!svc) {
        printf("[FAIL] 无法获取 display service\n");
        return 1;
    }

    printf("GetEncFmt()              = %d\n", DisplayClient_GetEncFmt(svc));
    printf("GetDisplayDeviceType()   = %d\n", DisplayClient_GetDisplayDeviceType(svc));
    printf("GetOptimalFormatEnable() = %d\n", DisplayClient_GetOptimalFormatEnable(svc));
    printf("GetHDMISuspendEnable()   = %d\n", DisplayClient_GetHDMISuspendEnable(svc));
    printf("GetHDMISuspendTime()     = %d\n", DisplayClient_GetHDMISuspendTime(svc));

    printf("--- 触发 Reload() 重新协商 ---\n");
    DisplayClient_Reload(svc);

    printf("Reload 后 GetEncFmt()    = %d\n", DisplayClient_GetEncFmt(svc));
    printf("=== 完成 ===\n");
    return 0;
}
