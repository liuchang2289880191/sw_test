SWCC ?= swgcc
CFLAGS ?= -O2
HOST_FLAGS ?= -mhost
# swgcc/1473 crts2ath.h requires SIMD interfaces for athread DMA calls.
SLAVE_FLAGS ?= -mslave -msimd
LINK_FLAGS ?= -mhybrid

OBJECTS = dma_host.o dma_slave.o rma_host.o rma_slave.o \
          bcast_host.o bcast_slave.o cluster_host.o cluster_slave.o
PROGRAMS = dma_bench rma_bench rma_bcast_bench rma_cluster_bench

all: $(PROGRAMS)

$(OBJECTS) $(PROGRAMS): | check-toolchain

check-toolchain:
	@command -v "$(SWCC)" >/dev/null 2>&1 || { \
	  printf '%s\n' 'Compiler not found: $(SWCC)' \
	    'Run: bash bench/check_toolchain.sh (from the project root)' \
	    'Then set SWCC and the HOST_FLAGS/SLAVE_FLAGS/LINK_FLAGS for your installed toolchain.' >&2; \
	  exit 1; \
	}
	@if [ "$(notdir $(SWCC))" = gcc ]; then \
	  target=$$("$(SWCC)" -dumpmachine 2>/dev/null) || exit 1; \
	  case "$$target" in \
	    x86_64*|i?86*|aarch64*|arm*) \
	      printf '%s\n' "gcc targets $$target; this build needs the Sunway MPE/CPE toolchain." \
	        'Locate/load the site toolchain before building.' >&2; exit 1 ;; \
	  esac; \
	fi

dma_host.o: dma_host.c bench_common.h
	$(SWCC) $(HOST_FLAGS) $(CPPFLAGS) $(CFLAGS) -c $< -o $@
dma_slave.o: dma_slave.c bench_common.h
	$(SWCC) $(SLAVE_FLAGS) $(CPPFLAGS) $(CFLAGS) -c $< -o $@
rma_host.o: rma_host.c bench_common.h
	$(SWCC) $(HOST_FLAGS) $(CPPFLAGS) $(CFLAGS) -c $< -o $@
rma_slave.o: rma_slave.c bench_common.h
	$(SWCC) $(SLAVE_FLAGS) $(CPPFLAGS) $(CFLAGS) -c $< -o $@
bcast_host.o: bcast_host.c bench_common.h
	$(SWCC) $(HOST_FLAGS) $(CPPFLAGS) $(CFLAGS) -c $< -o $@
bcast_slave.o: bcast_slave.c bench_common.h
	$(SWCC) $(SLAVE_FLAGS) $(CPPFLAGS) $(CFLAGS) -c $< -o $@
cluster_host.o: rma_cluster_host.c bench_common.h rma_cluster_suite.h
	$(SWCC) $(HOST_FLAGS) $(CPPFLAGS) $(CFLAGS) -c $< -o $@
cluster_slave.o: rma_cluster_slave.c bench_common.h
	$(SWCC) $(SLAVE_FLAGS) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

dma_bench: dma_host.o dma_slave.o
	$(SWCC) $(LINK_FLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
rma_bench: rma_host.o rma_slave.o
	$(SWCC) $(LINK_FLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
rma_bcast_bench: bcast_host.o bcast_slave.o
	$(SWCC) $(LINK_FLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
rma_cluster_bench: cluster_host.o cluster_slave.o
	$(SWCC) $(LINK_FLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@

clean:
	rm -f *.o dma_bench rma_bench rma_bcast_bench rma_cluster_bench

.PHONY: all clean check-toolchain
