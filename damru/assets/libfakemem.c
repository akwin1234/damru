/*
 * libfakemem.so — Intercept memory queries to report fake RAM.
 *
 * Key override: sysconf(_SC_PHYS_PAGES) — what Chrome calls for deviceMemory.
 * Also overrides sysinfo() for direct callers and get_phys_pages() variants.
 *
 * Auto-detects Android (Bionic) vs Linux (glibc) because sysconf
 * parameter values differ between the two.
 *
 * Bionic values sourced from AOSP bionic/libc/include/bits/sysconf.h
 *
 * Compile (x86_64 only):
 *   gcc -shared -fPIC -nostdlib -fno-stack-protector \
 *       -o libfakemem_x86_64.so libfakemem.c
 */

/* ── Kernel struct definitions ── */

struct sysinfo {
    long uptime;
    unsigned long loads[3];
    unsigned long totalram;
    unsigned long freeram;
    unsigned long sharedram;
    unsigned long bufferram;
    unsigned long totalswap;
    unsigned long freeswap;
    unsigned short procs;
    unsigned short pad;
    unsigned long totalhigh;
    unsigned long freehigh;
    unsigned int mem_unit;
};

struct rlimit {
    unsigned long rlim_cur;
    unsigned long rlim_max;
};

/* ── x86_64 syscall numbers ── */

#define SYS_read                0
#define SYS_close               3
#define SYS_getrlimit          97
#define SYS_sysinfo            99
#define SYS_sched_getaffinity 204
#define SYS_openat            257

/* ── Constants ── */

#define PAGE_SIZE      4096
#define RLIMIT_NOFILE  7
#define RLIMIT_NPROC   6
#define AT_FDCWD      -100

/* ── Raw x86_64 syscall wrappers ── */

static inline long _sc1(long nr, long a1) {
    long ret;
    __asm__ volatile("syscall"
        : "=a"(ret) : "0"(nr), "D"(a1)
        : "rcx", "r11", "memory");
    return ret;
}

static inline long _sc3(long nr, long a1, long a2, long a3) {
    long ret;
    __asm__ volatile("syscall"
        : "=a"(ret) : "0"(nr), "D"(a1), "S"(a2), "d"(a3)
        : "rcx", "r11", "memory");
    return ret;
}

static inline long _sc4(long nr, long a1, long a2, long a3, long a4) {
    long ret;
    register long r10 __asm__("r10") = a4;
    __asm__ volatile("syscall"
        : "=a"(ret) : "0"(nr), "D"(a1), "S"(a2), "d"(a3), "r"(r10)
        : "rcx", "r11", "memory");
    return ret;
}

static inline long _open_ro(const char *path) {
    return _sc4(SYS_openat, AT_FDCWD, (long)path, 0, 0);
}

/* ── Target file and cache ── */

static const char _path[] = "/data/local/tmp/damru_fakemem_gb";
static unsigned long _target_bytes = 0;
static int _done = 0;

static void _load(void) {
    long fd, n, i;
    char buf[8];
    unsigned long gb;

    if (_done) return;
    _done = 1;

    fd = _open_ro(_path);
    if (fd < 0) return;

    n = _sc3(SYS_read, fd, (long)buf, 7);
    _sc1(SYS_close, fd);
    if (n <= 0) return;

    gb = 0;
    for (i = 0; i < n; i++) {
        if (buf[i] >= '0' && buf[i] <= '9')
            gb = gb * 10 + (buf[i] - '0');
        else
            break;
    }

    if (gb > 0 && gb <= 64)
        _target_bytes = gb * 1024UL * 1024UL * 1024UL;
}

/* ── Platform detection ── */

static int _is_android = -1;

static int _check_android(void) {
    if (_is_android >= 0) return _is_android;
    long fd = _open_ro("/system/build.prop");
    if (fd >= 0) {
        _sc1(SYS_close, fd);
        _is_android = 1;
    } else {
        _is_android = 0;
    }
    return _is_android;
}

/* ── Helpers ── */

static int _get_nprocs(void) {
    unsigned long mask[16];
    int i, count;
    long ret;
    for (i = 0; i < 16; i++) mask[i] = 0;
    ret = _sc3(SYS_sched_getaffinity, 0, (long)sizeof(mask), (long)mask);
    if (ret <= 0) return 1;
    count = 0;
    for (i = 0; i < (int)(ret / (long)sizeof(unsigned long)); i++) {
        unsigned long m = mask[i];
        while (m) { count += (int)(m & 1); m >>= 1; }
    }
    return count > 0  count : 1;
}

static long _get_rlimit(int resource) {
    struct rlimit rl;
    long ret = _sc3(SYS_getrlimit, resource, (long)&rl, 0);
    if (ret == 0 && rl.rlim_cur > 0)
        return (long)rl.rlim_cur;
    return 1024;
}

static long _phys_pages(void) {
    _load();
    if (_target_bytes > 0)
        return (long)(_target_bytes / PAGE_SIZE);
    struct sysinfo si;
    long ret = _sc1(SYS_sysinfo, (long)&si);
    if (ret == 0)
        return (long)(((unsigned long long)si.totalram * si.mem_unit) / PAGE_SIZE);
    return -1;
}

static long _avphys_pages(void) {
    struct sysinfo si;
    long ret = _sc1(SYS_sysinfo, (long)&si);
    if (ret == 0)
        return (long)(((unsigned long long)si.freeram * si.mem_unit) / PAGE_SIZE);
    return -1;
}

/* ══════════════════════════════════════════════════════════════
 * sysconf() — Comprehensive override for BOTH Bionic and glibc.
 *
 * Bionic values from AOSP bionic/libc/include/bits/sysconf.h
 * (verified against Android 14 / API 34 source).
 * ══════════════════════════════════════════════════════════════ */

__attribute__((visibility("default")))
long sysconf(int name) {
    /* Critical Android/Bionic constants must work even before platform
       detection is reliable in app_process preload context. */
    switch (name) {
    case 0x27: return PAGE_SIZE;             /* _SC_PAGESIZE */
    case 0x28: return PAGE_SIZE;             /* _SC_PAGE_SIZE */
    case 0x60: return _get_nprocs();         /* _SC_NPROCESSORS_CONF */
    case 0x61: return _get_nprocs();         /* _SC_NPROCESSORS_ONLN */
    case 0x62: return _phys_pages();         /* _SC_PHYS_PAGES */
    case 0x63: return _avphys_pages();       /* _SC_AVPHYS_PAGES */
    }

    if (1) {
        /* ═══ Bionic (Android) — values from AOSP sysconf.h ═══ */
        switch (name) {
        /* 0x00-0x0c: Basic limits */
        case 0x00: return 131072;             /* _SC_ARG_MAX */
        case 0x01: return 99;                 /* _SC_BC_BASE_MAX */
        case 0x02: return 2048;               /* _SC_BC_DIM_MAX */
        case 0x03: return 99;                 /* _SC_BC_SCALE_MAX */
        case 0x04: return 1000;               /* _SC_BC_STRING_MAX */
        case 0x05: return _get_rlimit(RLIMIT_NPROC); /* _SC_CHILD_MAX */
        case 0x06: return 100;                /* _SC_CLK_TCK */
        case 0x07: return 2;                  /* _SC_COLL_WEIGHTS_MAX */
        case 0x08: return 32;                 /* _SC_EXPR_NEST_MAX */
        case 0x09: return 2048;               /* _SC_LINE_MAX */
        case 0x0a: return 65536;              /* _SC_NGROUPS_MAX */
        case 0x0b: return _get_rlimit(RLIMIT_NOFILE); /* _SC_OPEN_MAX */
        case 0x0c: return 128;               /* _SC_PASS_MAX */
        /* 0x0d-0x16: POSIX2 values */
        case 0x0d: return 200809L;            /* _SC_2_C_BIND */
        case 0x0e: return -1;                 /* _SC_2_C_DEV */
        case 0x0f: return -1;                 /* _SC_2_C_VERSION */
        case 0x10: return -1;                 /* _SC_2_CHAR_TERM */
        case 0x11: return -1;                 /* _SC_2_FORT_DEV */
        case 0x12: return -1;                 /* _SC_2_FORT_RUN */
        case 0x13: return -1;                 /* _SC_2_LOCALEDEF */
        case 0x14: return -1;                 /* _SC_2_SW_DEV */
        case 0x15: return -1;                 /* _SC_2_UPE */
        case 0x16: return 199209L;            /* _SC_2_VERSION */
        /* 0x17-0x1c: POSIX features */
        case 0x17: return 1;                  /* _SC_JOB_CONTROL */
        case 0x18: return 1;                  /* _SC_SAVED_IDS */
        case 0x19: return 200809L;            /* _SC_VERSION */
        case 0x1a: return 255;                /* _SC_RE_DUP_MAX */
        case 0x1b: return 20;                 /* _SC_STREAM_MAX */
        case 0x1c: return 50;                 /* _SC_TZNAME_MAX */
        /* 0x1d-0x24: XOPEN values */
        case 0x1d: return -1;                 /* _SC_XOPEN_CRYPT */
        case 0x1e: return 1;                  /* _SC_XOPEN_ENH_I18N */
        case 0x1f: return 1;                  /* _SC_XOPEN_SHM */
        case 0x20: return 700;                /* _SC_XOPEN_VERSION */
        case 0x21: return -1;                 /* _SC_XOPEN_XCU_VERSION */
        case 0x22: return 1;                  /* _SC_XOPEN_REALTIME */
        case 0x23: return 1;                  /* _SC_XOPEN_REALTIME_THREADS */
        case 0x24: return 1;                  /* _SC_XOPEN_LEGACY */
        /* 0x25-0x28: Misc */
        case 0x25: return 2147483647L;        /* _SC_ATEXIT_MAX (INT_MAX) */
        case 0x26: return 1024;               /* _SC_IOV_MAX */
        case 0x27: return PAGE_SIZE;          /* _SC_PAGESIZE */
        case 0x28: return PAGE_SIZE;          /* _SC_PAGE_SIZE */
        /* 0x29-0x2d: XBS5/XOPEN */
        case 0x29: return 1;                  /* _SC_XOPEN_UNIX */
        case 0x2a: return -1;                 /* _SC_XBS5_ILP32_OFF32 */
        case 0x2b: return -1;                 /* _SC_XBS5_ILP32_OFFBIG */
        case 0x2c: return 1;                  /* _SC_XBS5_LP64_OFF64 */
        case 0x2d: return 1;                  /* _SC_XBS5_LPBIG_OFFBIG */
        /* 0x2e-0x38: AIO/MQ/RT limits */
        case 0x2e: return 2;                  /* _SC_AIO_LISTIO_MAX */
        case 0x2f: return 1;                  /* _SC_AIO_MAX */
        case 0x30: return 0;                  /* _SC_AIO_PRIO_DELTA_MAX */
        case 0x31: return 2147483647L;        /* _SC_DELAYTIMER_MAX */
        case 0x32: return 8;                  /* _SC_MQ_OPEN_MAX */
        case 0x33: return 32;                 /* _SC_MQ_PRIO_MAX */
        case 0x34: return 32;                 /* _SC_RTSIG_MAX */
        case 0x35: return 256;                /* _SC_SEM_NSEMS_MAX */
        case 0x36: return 2147483647L;        /* _SC_SEM_VALUE_MAX */
        case 0x37: return 32;                 /* _SC_SIGQUEUE_MAX */
        case 0x38: return 32;                 /* _SC_TIMER_MAX */
        /* 0x39-0x46: POSIX options (all supported = 200809L or 1) */
        case 0x39: return 200809L;            /* _SC_ASYNCHRONOUS_IO */
        case 0x3a: return 200809L;            /* _SC_FSYNC */
        case 0x3b: return 200809L;            /* _SC_MAPPED_FILES */
        case 0x3c: return 200809L;            /* _SC_MEMLOCK */
        case 0x3d: return 200809L;            /* _SC_MEMLOCK_RANGE */
        case 0x3e: return 200809L;            /* _SC_MEMORY_PROTECTION */
        case 0x3f: return 200809L;            /* _SC_MESSAGE_PASSING */
        case 0x40: return 200809L;            /* _SC_PRIORITIZED_IO */
        case 0x41: return 200809L;            /* _SC_PRIORITY_SCHEDULING */
        case 0x42: return 200809L;            /* _SC_REALTIME_SIGNALS */
        case 0x43: return 200809L;            /* _SC_SEMAPHORES */
        case 0x44: return 200809L;            /* _SC_SHARED_MEMORY_OBJECTS */
        case 0x45: return 200809L;            /* _SC_SYNCHRONIZED_IO */
        case 0x46: return 200809L;            /* _SC_TIMERS */
        /* 0x47-0x55: Thread & user limits */
        case 0x47: return 1024;               /* _SC_GETGR_R_SIZE_MAX */
        case 0x48: return 1024;               /* _SC_GETPW_R_SIZE_MAX */
        case 0x49: return 256;                /* _SC_LOGIN_NAME_MAX */
        case 0x4a: return 4;                  /* _SC_THREAD_DESTRUCTOR_ITERATIONS */
        case 0x4b: return 128;                /* _SC_THREAD_KEYS_MAX */
        case 0x4c: return 16384;              /* _SC_THREAD_STACK_MIN (x86_64) */
        case 0x4d: return -1;                 /* _SC_THREAD_THREADS_MAX (unlimited) */
        case 0x4e: return 32;                 /* _SC_TTY_NAME_MAX */
        case 0x4f: return 200809L;            /* _SC_THREADS */
        case 0x50: return 200809L;            /* _SC_THREAD_ATTR_STACKADDR */
        case 0x51: return 200809L;            /* _SC_THREAD_ATTR_STACKSIZE */
        case 0x52: return 200809L;            /* _SC_THREAD_PRIORITY_SCHEDULING */
        case 0x53: return 200809L;            /* _SC_THREAD_PRIO_INHERIT */
        case 0x54: return 200809L;            /* _SC_THREAD_PRIO_PROTECT */
        case 0x55: return 200809L;            /* _SC_THREAD_SAFE_FUNCTIONS */
        /* 0x60-0x64: Hardware/system */
        case 0x60: return _get_nprocs();      /* _SC_NPROCESSORS_CONF */
        case 0x61: return _get_nprocs();      /* _SC_NPROCESSORS_ONLN */
        case 0x62: return _phys_pages();      /* _SC_PHYS_PAGES *** KEY *** */
        case 0x63: return _avphys_pages();    /* _SC_AVPHYS_PAGES */
        case 0x64: return 200809L;            /* _SC_MONOTONIC_CLOCK */
        /* 0x65-0x7f: Extended POSIX */
        case 0x65: return -1;                 /* _SC_2_PBS */
        case 0x66: return -1;                 /* _SC_2_PBS_ACCOUNTING */
        case 0x67: return -1;                 /* _SC_2_PBS_CHECKPOINT */
        case 0x68: return -1;                 /* _SC_2_PBS_LOCATE */
        case 0x69: return -1;                 /* _SC_2_PBS_MESSAGE */
        case 0x6a: return -1;                 /* _SC_2_PBS_TRACK */
        case 0x6b: return 200809L;            /* _SC_ADVISORY_INFO */
        case 0x6c: return 200809L;            /* _SC_BARRIERS */
        case 0x6d: return 200809L;            /* _SC_CLOCK_SELECTION */
        case 0x6e: return 200809L;            /* _SC_CPUTIME */
        case 0x6f: return 255;                /* _SC_HOST_NAME_MAX */
        case 0x70: return 200809L;            /* _SC_IPV6 */
        case 0x71: return 200809L;            /* _SC_RAW_SOCKETS */
        case 0x72: return 200809L;            /* _SC_READER_WRITER_LOCKS */
        case 0x73: return 200809L;            /* _SC_REGEXP */
        case 0x74: return 200809L;            /* _SC_SHELL */
        case 0x75: return 200809L;            /* _SC_SPAWN */
        case 0x76: return 200809L;            /* _SC_SPIN_LOCKS */
        case 0x77: return -1;                 /* _SC_SPORADIC_SERVER */
        case 0x78: return -1;                 /* _SC_SS_REPL_MAX */
        case 0x79: return -1;                 /* _SC_SYMLOOP_MAX (POSIX says 8 min) */
        case 0x7a: return 200809L;            /* _SC_THREAD_CPUTIME */
        case 0x7b: return 200809L;            /* _SC_THREAD_PROCESS_SHARED */
        case 0x7c: return -1;                 /* _SC_THREAD_ROBUST_PRIO_INHERIT */
        case 0x7d: return -1;                 /* _SC_THREAD_ROBUST_PRIO_PROTECT */
        case 0x7e: return -1;                 /* _SC_THREAD_SPORADIC_SERVER */
        case 0x7f: return 200809L;            /* _SC_TIMEOUTS */
        /* 0x80-0x9e: Trace, cache, misc */
        case 0x80: return -1;                 /* _SC_TRACE */
        case 0x81: return -1;                 /* _SC_TRACE_EVENT_FILTER */
        case 0x82: return -1;                 /* _SC_TRACE_EVENT_NAME_MAX */
        case 0x83: return -1;                 /* _SC_TRACE_INHERIT */
        case 0x84: return -1;                 /* _SC_TRACE_LOG */
        case 0x85: return -1;                 /* _SC_TRACE_NAME_MAX */
        case 0x86: return -1;                 /* _SC_TRACE_SYS_MAX */
        case 0x87: return -1;                 /* _SC_TRACE_USER_EVENT_MAX */
        case 0x88: return -1;                 /* _SC_TYPED_MEMORY_OBJECTS */
        case 0x89: return -1;                 /* _SC_V7_ILP32_OFF32 */
        case 0x8a: return -1;                 /* _SC_V7_ILP32_OFFBIG */
        case 0x8b: return 1;                  /* _SC_V7_LP64_OFF64 */
        case 0x8c: return 1;                  /* _SC_V7_LPBIG_OFFBIG */
        case 0x8d: return -1;                 /* _SC_XOPEN_STREAMS */
        case 0x8e: return -1;                 /* _SC_XOPEN_UUCP */
        /* 0x8f-0x9d: Cache info (return 0 = unknown) */
        case 0x8f: return 0;                  /* _SC_LEVEL1_ICACHE_SIZE */
        case 0x90: return 0;                  /* _SC_LEVEL1_ICACHE_ASSOC */
        case 0x91: return 0;                  /* _SC_LEVEL1_ICACHE_LINESIZE */
        case 0x92: return 0;                  /* _SC_LEVEL1_DCACHE_SIZE */
        case 0x93: return 0;                  /* _SC_LEVEL1_DCACHE_ASSOC */
        case 0x94: return 0;                  /* _SC_LEVEL1_DCACHE_LINESIZE */
        case 0x95: return 0;                  /* _SC_LEVEL2_CACHE_SIZE */
        case 0x96: return 0;                  /* _SC_LEVEL2_CACHE_ASSOC */
        case 0x97: return 0;                  /* _SC_LEVEL2_CACHE_LINESIZE */
        case 0x98: return 0;                  /* _SC_LEVEL3_CACHE_SIZE */
        case 0x99: return 0;                  /* _SC_LEVEL3_CACHE_ASSOC */
        case 0x9a: return 0;                  /* _SC_LEVEL3_CACHE_LINESIZE */
        case 0x9b: return 0;                  /* _SC_LEVEL4_CACHE_SIZE */
        case 0x9c: return 0;                  /* _SC_LEVEL4_CACHE_ASSOC */
        case 0x9d: return 0;                  /* _SC_LEVEL4_CACHE_LINESIZE */
        case 0x9e: return 64;                 /* _SC_NSIG (typically 64 + 1) */
        default:   return -1;
        }
    }

    /* ═══ glibc (Linux) — enum-based values ═══ */
    switch (name) {
    case 0:  return 131072;                   /* _SC_ARG_MAX */
    case 2:  return 100;                      /* _SC_CLK_TCK */
    case 4:  return _get_rlimit(RLIMIT_NOFILE); /* _SC_OPEN_MAX */
    case 30: return PAGE_SIZE;                /* _SC_PAGESIZE */
    case 83: return _get_nprocs();            /* _SC_NPROCESSORS_CONF */
    case 84: return _get_nprocs();            /* _SC_NPROCESSORS_ONLN */
    case 85: return _phys_pages();            /* _SC_PHYS_PAGES */
    case 86: return _avphys_pages();          /* _SC_AVPHYS_PAGES */
    default: return -1;
    }
}

/* glibc compatibility */
__attribute__((visibility("default")))
long __sysconf(int name) {
    return sysconf(name);
}

/* ── sysinfo() override ── */

__attribute__((visibility("default")))
int sysinfo(struct sysinfo *info) {
    long ret = _sc1(SYS_sysinfo, (long)info);
    if (ret == 0) {
        _load();
        if (_target_bytes > 0 && info->mem_unit > 0)
            info->totalram = _target_bytes / info->mem_unit;
    }
    return (int)ret;
}

/* ── get_phys_pages overrides ── */

__attribute__((visibility("default")))
long get_phys_pages(void) { return _phys_pages(); }

__attribute__((visibility("default")))
long __get_phys_pages(void) { return _phys_pages(); }

__attribute__((visibility("default")))
long get_avphys_pages(void) { return _avphys_pages(); }

__attribute__((visibility("default")))
long __get_avphys_pages(void) { return _avphys_pages(); }
