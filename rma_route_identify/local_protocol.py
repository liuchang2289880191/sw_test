"""Windows local verification of plan/host/CPE protocol; NO Sunway timing.

The actual topology_slave.c runs on 64 local threads with TLS-address-translated
memory copies and reply counters. This checks protocol/data logic, not hardware.
"""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent

ATHREAD = r'''
#ifndef LOCAL_ATHREAD_H
#define LOCAL_ATHREAD_H
#include <stddef.h>
#define SLAVE_FUN(x) x
int mock_posix_memalign(void **, size_t, size_t);
void mock_free(void *);
#define posix_memalign mock_posix_memalign
#define free mock_free
int athread_init(void);
void athread_halt(void);
int athread_spawn(void (*)(), void *);
int athread_join(void);
#endif
'''
SLAVE = r'''
#ifndef LOCAL_SLAVE_H
#define LOCAL_SLAVE_H
#include <stddef.h>
#define __thread_local __thread
typedef volatile long athread_rply_t;
extern __thread int _PEN;
void athread_dma_get(void *, const void *, size_t);
void athread_dma_put(void *, const void *, size_t);
void athread_ssync_array(void);
unsigned long athread_stime_cycle(void);
int athread_rma_iput(void *, athread_rply_t *, int, int, void *, athread_rply_t *);
void athread_rma_wait_value(athread_rply_t *, unsigned long);
void athread_memory_barrier(void);
#endif
'''
RUNTIME = r'''
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#include "slave.h"
#include "topology_common.h"
__thread int _PEN;
static uintptr_t anchors[64];
static HANDLE threads[64];
static CRITICAL_SECTION barrier_lock;
static CONDITION_VARIABLE barrier_cond;
static int arrived, generation, initialized, cases;
static int dropped_ready, dropped_stop;
static void (*kernel_function)();
static topo_args_t *argument;
int mock_posix_memalign(void **p, size_t a, size_t n) { *p=_aligned_malloc(n,a); return !*p; }
void mock_free(void *p) { _aligned_free(p); }
int athread_init(void) {
    if(initialized++) abort();
    InitializeCriticalSection(&barrier_lock); InitializeConditionVariable(&barrier_cond);
    return 0;
}
void athread_halt(void) { if(initialized!=1) abort(); DeleteCriticalSection(&barrier_lock); initialized=0; }
static DWORD WINAPI worker(LPVOID i) { _PEN=(int)(intptr_t)i; kernel_function(argument); return 0; }
int athread_spawn(void (*f)(),void *p) {
    int i; if(initialized!=1 || (uintptr_t)p%128) abort();
    argument=p; kernel_function=f; arrived=generation=0; dropped_ready=dropped_stop=0; ++cases;
    for(i=0;i<64;i++) { threads[i]=CreateThread(NULL,0,worker,(LPVOID)(intptr_t)i,0,NULL); if(!threads[i]) abort(); }
    return 0;
}
int athread_join(void) {
    int i; char *fail=getenv("TOPO_MOCK_ERROR_AT"), *cap=getenv("TOPO_MOCK_CAP_AT");
    if(WaitForMultipleObjects(64,threads,TRUE,120000)!=WAIT_OBJECT_0) abort();
    for(i=0;i<64;i++) CloseHandle(threads[i]);
    if(fail && atoi(fail)==cases) argument->results[argument->flows[0].src].errors=1;
    if(cap && atoi(cap)==cases) argument->results[argument->flows[0].src].background_limit_hit=1;
    return 0;
}
void athread_dma_get(void *d,const void *s,size_t n) { memcpy(d,s,n); anchors[_PEN]=(uintptr_t)d; }
void athread_dma_put(void *d,const void *s,size_t n) { memcpy(d,s,n); }
void athread_ssync_array(void) {
    int g; EnterCriticalSection(&barrier_lock); g=generation;
    if(++arrived==64) { arrived=0; generation++; WakeAllConditionVariable(&barrier_cond); }
    else while(g==generation) if(!SleepConditionVariableCS(&barrier_cond,&barrier_lock,120000)) abort();
    LeaveCriticalSection(&barrier_lock);
}
unsigned long athread_stime_cycle(void) { LARGE_INTEGER n; QueryPerformanceCounter(&n); return (unsigned long)n.QuadPart; }
int athread_rma_iput(void *s,athread_rply_t *lr,int n,int pe,void *d,athread_rply_t *rr) {
    uintptr_t remote_d,remote_r; int drop=0;
    char *ready=getenv("TOPO_MOCK_DROP_READY_PE"), *stop=getenv("TOPO_MOCK_DROP_STOP_PE");
    if(pe<0 || pe>63 || n<4 || n%4 || !anchors[pe]) abort();
    remote_d=anchors[pe]+(uintptr_t)d-anchors[_PEN];
    remote_r=anchors[pe]+(uintptr_t)rr-anchors[_PEN];
    memcpy((void *)remote_d,s,(size_t)n);
    if(argument->mode && argument->nflows>1 && n==8) {
        if(ready && _PEN==atoi(ready) && pe==argument->flows[0].src && !dropped_ready++) drop=1;
        if(stop && _PEN==argument->flows[0].src && pe==atoi(stop) && !dropped_stop++) drop=1;
    }
    if(!drop) InterlockedIncrement((LONG *)remote_r);
    InterlockedIncrement((LONG *)lr);
    return 0;
}
void athread_memory_barrier(void) { MemoryBarrier(); }
void athread_rma_wait_value(athread_rply_t *p,unsigned long value) {
    while((unsigned long)InterlockedCompareExchange((LONG *)p,0,0)<value) SwitchToThread();
}
'''

