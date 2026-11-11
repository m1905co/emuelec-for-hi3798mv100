/*
 * pmoc_probe2 - talk to /dev/hi_pm directly, no libhi_msp.so needed.
 *
 * Target is glibc 2.24 with /lib/ld-linux.so.3, so any dynamically linked
 * binary built with the Ubuntu armhf toolchain fails to start ("not found"
 * or GLIBC_2.3x version errors).  This program is statically linked and uses
 * raw ioctl(), so it only depends on the kernel interface.
 *
 * From the SDK (source/msp/drv/include/drv_pmoc_ioctl.h):
 *   HI_PMOC_GET_WAKEUP_CMD = _IOR(HI_ID_PM, 0x0C, C51_PMOC_VAL_S)
 *   HI_PMOC_SET_WAKEUP_CMD = _IOW(HI_ID_PM, 0x02, C51_PMOC_VAL_S)
 * and from source/common/include/hi_module.h: HI_ID_PM = 0x62.
 *
 * sizeof(C51_PMOC_VAL_S) is unknown (hi_unf_pmoc.h missing from the SDK), and
 * it is encoded into the ioctl number, so we probe several sizes.  A driver
 * that ignores _IOC_SIZE accepts any of them; one that validates accepts
 * exactly one, and that is the real struct size.
 */
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>

#define HI_ID_PM 0x62

#define IOC(dir, type, nr, size) \
	(((uint32_t)(dir) << 30) | (((uint32_t)(type) & 0xff) << 8) | \
	 ((uint32_t)(nr) & 0xff) | (((uint32_t)(size) & 0x3fff) << 16))

#define GET_WAKEUP(sz) IOC(2, HI_ID_PM, 0x0C, sz)
#define SET_WAKEUP(sz) IOC(1, HI_ID_PM, 0x02, sz)
#define STANDBY(sz)    IOC(1, HI_ID_PM, 0x01, sz)

static void dump(const unsigned char *b, int n)
{
	int i, j;
	for (i = 0; i < n; i += 16) {
		printf("%04x:", i);
		for (j = 0; j < 16; j++)
			printf(" %02x", b[i + j]);
		printf("\n");
	}
}

int main(void)
{
	static unsigned char buf[2048];
	int fd, sz, r;

	fd = open("/dev/hi_pm", O_RDWR);
	if (fd < 0) {
		printf("open /dev/hi_pm failed: %s\n", strerror(errno));
		return 1;
	}
	printf("open /dev/hi_pm OK (fd=%d)\n", fd);

	for (sz = 32; sz <= 1024; sz *= 2) {
		memset(buf, 0xAA, sizeof(buf));
		errno = 0;
		r = ioctl(fd, GET_WAKEUP(sz), buf);
		printf("GET size=%-4d -> ret=%-3d errno=%d (%s)\n",
		       sz, r, errno, errno ? strerror(errno) : "ok");
		if (r == 0) {
			int k, hits = 0;
			/* look for the known wake key / small counts */
			for (k = 0; k + 4 <= 256; k += 4) {
				uint32_t v;
				memcpy(&v, buf + k, 4);
				if (v == 0x639cff00u || v == 0x23dc4db2u ||
				    (v == 1 && k < 64)) {
					printf("   hit @ +0x%02x = 0x%08x\n", k, v);
					hits++;
				}
			}
			if (!hits)
				printf("   (no known value in first 256 bytes)\n");
			dump(buf, 96);
			break;
		}
	}
	close(fd);
	return 0;
}
