SWCC ?= swgcc
CFLAGS ?= -O2

all: dma_bench rma_bench rma_bcast_bench rma_cluster_bench

dma_host.o: dma_host.c bench_common.h
	$(SWCC) -mhost $(CFLAGS) -c $< -o $@
dma_slave.o: dma_slave.c bench_common.h
	$(SWCC) -mslave $(CFLAGS) -c $< -o $@
rma_host.o: rma_host.c bench_common.h
	$(SWCC) -mhost $(CFLAGS) -c $< -o $@
rma_slave.o: rma_slave.c bench_common.h
	$(SWCC) -mslave $(CFLAGS) -c $< -o $@
bcast_host.o: bcast_host.c bench_common.h
	$(SWCC) -mhost $(CFLAGS) -c $< -o $@
bcast_slave.o: bcast_slave.c bench_common.h
	$(SWCC) -mslave $(CFLAGS) -c $< -o $@
cluster_host.o: rma_cluster_host.c bench_common.h
	$(SWCC) -mhost $(CFLAGS) -c $< -o $@
cluster_slave.o: rma_cluster_slave.c bench_common.h
	$(SWCC) -mslave $(CFLAGS) -c $< -o $@

dma_bench: dma_host.o dma_slave.o
	$(SWCC) -mhybrid $^ -o $@
rma_bench: rma_host.o rma_slave.o
	$(SWCC) -mhybrid $^ -o $@
rma_bcast_bench: bcast_host.o bcast_slave.o
	$(SWCC) -mhybrid $^ -o $@
rma_cluster_bench: cluster_host.o cluster_slave.o
	$(SWCC) -mhybrid $^ -o $@

clean:
	rm -f *.o dma_bench rma_bench rma_bcast_bench rma_cluster_bench

.PHONY: all clean
