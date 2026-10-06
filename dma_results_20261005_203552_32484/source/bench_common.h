#ifndef SW_BENCH_COMMON_H
#define SW_BENCH_COMMON_H

#define BENCH_PES 64
#ifndef BENCH_MAX_BYTES
#define BENCH_MAX_BYTES (64 * 1024)
#endif
/* Keep host slots aligned and the ping-pong sizes available in every build. */
#if BENCH_MAX_BYTES < 256 || BENCH_MAX_BYTES > 65536 || BENCH_MAX_BYTES % 128
#error "BENCH_MAX_BYTES must be 256..65536 and a multiple of 128"
#endif
#define BENCH_SLOT_BYTES (BENCH_MAX_BYTES + 128)
/* DMA can use one larger buffer without enlarging the two-buffer RMA kernels. */
#ifndef DMA_MAX_BYTES
#define DMA_MAX_BYTES BENCH_MAX_BYTES
#endif
#if DMA_MAX_BYTES < 256 || DMA_MAX_BYTES > 131072 || DMA_MAX_BYTES % 128
#error "DMA_MAX_BYTES must be 256..131072 and a multiple of 128"
#endif
#define DMA_SLOT_BYTES (DMA_MAX_BYTES + 128)
#define BENCH_MAX_FLOWS 12

typedef struct {
    void *src;
    void *dst;
    unsigned long *cycles;
    int *errors;
    int bytes;
    int reps;
    int active;
    int mode;
    int offset;
    int slot_stride; /* bytes between host slots; always a multiple of 128 */
    int slot_of_pe[BENCH_PES]; /* permutation of all 64 slots */
} dma_args_t;

typedef struct {
    unsigned long *cycles; /* row-major [initiator][peer] */
    int *errors;
    int *receiver_errors;  /* row-major [receiver][initiator] */
    int bytes;
    int reps;
    int op;              /* 0: put, 1: get */
} rma_args_t;

typedef struct {
    unsigned long *cycles;
    int *errors;
    int bytes;
    int reps;
    int scope; /* 0: row, 1: column, 2: array */
    int root;
} bcast_args_t;

typedef struct {
    int src;
    int dst;
    int lane; /* destination-local incoming-flow index */
} flow_t;

typedef struct {
    unsigned long *cycles; /* 64x64 matrix or first 64 PE slots */
    int *errors;
    int *peer_errors; /* ping-pong: receiver row x initiator column */
    int mode;   /* 0: ping-pong matrix, 1: flow bandwidth */
    int bytes;
    int reps;
    int window;
    int nflows;
    int cluster_index; /* geometric 2x2 block, 0..15 */
    flow_t flows[BENCH_MAX_FLOWS];
} cluster_args_t;

#endif
