/*
 * pmoc_probe3 - brute-force the pmoc ioctl numbers on /dev/hi_pm.
 *
 * The SDK reference (drv_pmoc_ioctl.h) says
 *   HI_PMOC_GET_WAKEUP_CMD = _IOR(HI_ID_PM, 0x0C, C51_PMOC_VAL_S)
 * but _IOR(0x62, 0x0C, *) returns ENOTTY, so either HI_ID_PM differs on this
 * kernel build or the device node belongs to another module id.
 *
 * We therefore sweep module ids 0x50..0x70 and commands 0x00..0x10 using only
 * _IOR (read direction).  nr 0x01 is skipped because with _IOW it is
 * HI_PMOC_STANDBY_CMD, and we never want to trigger standby.
 */
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>

#define IOC(dir, type, nr, size) \
	(((uint32_t)(dir) << 30) | (((uint32_t)(type) & 0xff) << 8) | \
	 ((uint32_t)(nr) & 0xff) | (((uint32_t)(size) & 0x3fff) << 16))

static const int sizes[] = { 16, 32, 64, 128, 256, 512, 1024 };

int main(void)
{
	static unsigned char buf[2048];
	int fd, type, nr, i, hits = 0;

	fd = open("/dev/hi_pm", O_RDWR);
	if (fd < 0) {
		printf("open failed: %s\n", strerror(errno));
		return 1;
	}

	for (type = 0x50; type <= 0x70; type++) {
		for (nr = 0; nr <= 0x10; nr++) {
			if (nr == 0x01)
				continue;	/* standby, never poke */
			for (i = 0; i < (int)(sizeof(sizes) / sizeof(sizes[0])); i++) {
				uint32_t cmd = IOC(2, type, nr, sizes[i]);
				int r;

				memset(buf, 0xAA, sizeof(buf));
				errno = 0;
				r = ioctl(fd, cmd, buf);
				if (r == -1 && errno == ENOTTY)
					continue;	/* not this one */
				printf("HIT type=0x%02x nr=0x%02x size=%-4d -> ret=%d errno=%d (%s)\n",
				       type, nr, sizes[i], r, errno,
				       errno ? strerror(errno) : "ok");
				if (r == 0) {
					/* show anything that looks like a key value */
					int k;
					for (k = 0; k + 4 <= 128; k += 4) {
						uint32_t v;
						memcpy(&v, buf + k, 4);
						if (v == 0x639cff00u || v == 0x23dc4db2u)
							printf("     key @ +0x%02x = 0x%08x\n", k, v);
					}
				}
				hits++;
				break;		/* size found for this (type,nr) */
			}
		}
	}
	printf("total hits: %d\n", hits);
	close(fd);
	return 0;
}
