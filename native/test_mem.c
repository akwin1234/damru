/* Test: Does LD_PRELOAD sysinfo override work */
#include <stdio.h>
#include <sys/sysinfo.h>
#include <unistd.h>

int main() {
    /* Test 1: Direct sysinfo() call */
    struct sysinfo si;
    if (sysinfo(&si) == 0) {
        long long total_bytes = (long long)si.totalram * si.mem_unit;
        printf("sysinfo: totalram=%lu mem_unit=%u total_gb=%.1f\n",
               si.totalram, si.mem_unit, total_bytes / (1024.0*1024*1024));
    } else {
        printf("sysinfo: FAILED\n");
    }

    /* Test 2: sysconf(_SC_PHYS_PAGES) — what Chrome actually calls */
    long pages = sysconf(_SC_PHYS_PAGES);
    long page_size = sysconf(_SC_PAGESIZE);
    printf("sysconf: pages=%ld page_size=%ld total_gb=%.1f\n",
           pages, page_size, (double)pages * page_size / (1024.0*1024*1024));

    return 0;
}
