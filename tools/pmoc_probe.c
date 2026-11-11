/*
 * pmoc_probe - figure out the HI_UNF_PMOC_WAKEUP_ATTR_S layout at runtime.
 *
 * We do not have hi_unf_pmoc.h (SDK sparse checkout), so instead of guessing
 * struct offsets we call HI_UNF_PMOC_GetWakeUpAttr() into a zeroed buffer and
 * dump it.  The current wake-up IR key is known from /proc/hisi/msp/pm
 * (0x639cff00, count = 1), so its offset and the count field show up in the
 * hexdump and the layout can be reconstructed exactly.
 */
#include <stdio.h>
#include <string.h>
#include <dlfcn.h>

#define PROBE 1024

int main(void)
{
	void *h;
	void *sym_init, *sym_get;
	unsigned char buf[PROBE];
	int i, j, r;

	h = dlopen("/usr/lib/libhi_msp.so", RTLD_NOW);
	if (!h) {
		printf("dlopen FAILED: %s\n", dlerror());
		return 1;
	}
	printf("dlopen OK\n");

	sym_init = dlsym(h, "HI_UNF_PMOC_Init");
	sym_get  = dlsym(h, "HI_UNF_PMOC_GetWakeUpAttr");
	printf("Init  sym = %p\n", sym_init);
	printf("GetAttr sym = %p\n", sym_get);

	if (sym_init) {
		r = ((int (*)(void))sym_init)();
		printf("Init() = %d\n", r);
	}

	if (!sym_get) {
		printf("GetAttr missing\n");
		return 1;
	}

	memset(buf, 0, sizeof(buf));
	r = ((int (*)(void *))sym_get)(buf);
	printf("GetWakeUpAttr() = %d\n", r);

	for (i = 0; i < 128; i += 16) {
		printf("%04x:", i);
		for (j = 0; j < 16; j++)
			printf(" %02x", buf[i + j]);
		printf("   |");
		for (j = 0; j < 16; j++) {
			unsigned char c = buf[i + j];
			putchar(c >= 32 && c < 127 ? c : '.');
		}
		printf("|\n");
	}
	return 0;
}
