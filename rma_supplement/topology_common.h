#ifndef RMA_TOPOLOGY_COMMON_H
#define RMA_TOPOLOGY_COMMON_H
#define TOPO_PES 64
#define TOPO_MAX_FLOWS 8
#define TOPO_BUFFER_BYTES 32768
#define TOPO_MAX_REPS 16384
#define TOPO_SAMPLE_BATCH 64
#define TOPO_MAX_SAMPLES (TOPO_MAX_REPS / TOPO_SAMPLE_BATCH)
typedef struct { int src, dst, lane; } topo_flow_t;
typedef struct {
    unsigned long cycles, send_cycles, recv_cycles;
    unsigned long sent, received;
    int errors, background_limit_hit;
} topo_result_t;
typedef struct {
    int mode; /* 0: finite bulk; 1: sequential data + reply, optional background */
    int bytes, probe_bytes, reply_bytes, reps, window, nflows, background_limit;
    topo_flow_t flows[TOPO_MAX_FLOWS]; /* probe is flow 0 in mode 1 */
    topo_result_t *results;
    unsigned long *samples; /* probe initiator's 64-RTT batch durations */
} topo_args_t;
#endif
