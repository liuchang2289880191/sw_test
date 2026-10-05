#ifndef SW_BENCH_COMMON_H
#define SW_BENCH_COMMON_H

#define BENCH_PES 64
#define BENCH_MAX_BYTES (64 * 1024)
#define BENCH_SLOT_BYTES (BENCH_MAX_BYTES + 128)
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
