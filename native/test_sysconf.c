/* Test: Does sysconf(_SC_PHYS_PAGES) see our fake sysinfo? */
#include <stdio.h>
#include <unistd.h>
#include <sys/sysinfo.h>

int main() {
    /* Direct sysinfo() call — should be intercepted by LD_PRELOAD */
    struct sysinfo si;
    sysinfo(&si);
    printf("sysinfo: totalram=%lu mem_unit=%u total_gb=%.1f\n",
           si.totalram, si.mem_unit,
           (double)si.totalram * si.mem_unit / (1024.0*1024*1024));

    /* sysconf() call — what Chrome actually uses */
    long pages = sysconf(_SC_PHYS_PAGES);
    long pgsz = sysconf(_SC_PAGESIZE);
    printf("sysconf: pages=%ld page_sz=%ld total_gb=%.1f\n",
           pages, pgsz, (double)pages * pgsz / (1024.0*1024*1024));

    return 0;
}
