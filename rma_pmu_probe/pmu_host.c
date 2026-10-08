#define _POSIX_C_SOURCE 200112L
#include <athread.h>
#include <swperf.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <sys/utsname.h>
#include "pmu_common.h"
extern void SLAVE_FUN(pmu_kernel)();
typedef struct { const char *name; void (*init)(void); void (*count)(unsigned long *); } event;
#define EVENT(x) {#x, x##_init, x##_count}
static event events[] = {
    EVENT(penv_cg_tbox1_desc_rma_put),
    EVENT(penv_cg_tbox6_total_rma_put),
    EVENT(penv_cg_stn_lpcr1_l1_req_p1up_flit),
    EVENT(penv_cg_stn_spcr1_s1_req_p1up_flit),
    EVENT(penv_cg_stn_npcr1_n1_req_p1up_flit),
    EVENT(penv_cg_stn_wpcr1_w1_req_p1up_flit),
    EVENT(penv_cg_stn_epcr1_e1_req_p1up_flit),
    EVENT(penv_cg_stn_lpcr1_l1_req_p1down_flit),
    EVENT(penv_cg_stn_lpcr1_l1_res_p1up_flit),
    EVENT(penv_cg_stn_lpcr1_l1_res_p1down_flit),
    EVENT(penv_cg_stn_spcr1_s1_req_p1down_flit),
    EVENT(penv_cg_stn_spcr1_s1_res_p1up_flit),
    EVENT(penv_cg_stn_spcr1_s1_res_p1down_flit),
    EVENT(penv_cg_stn_npcr1_n1_req_p1down_flit),
    EVENT(penv_cg_stn_npcr1_n1_res_p1up_flit),
    EVENT(penv_cg_stn_npcr1_n1_res_p1down_flit),
    EVENT(penv_cg_stn_wpcr1_w1_req_p1down_flit),
    EVENT(penv_cg_stn_wpcr1_w1_res_p1up_flit),
    EVENT(penv_cg_stn_wpcr1_w1_res_p1down_flit),
    EVENT(penv_cg_stn_epcr1_e1_req_p1down_flit),
    EVENT(penv_cg_stn_epcr1_e1_res_p1up_flit),
    EVENT(penv_cg_stn_epcr1_e1_res_p1down_flit)
};
/* Manual specifies 16 cells. Extra canaries detect unexpected writes; cell order is uncalibrated. */
typedef struct { unsigned long pre[16], value[16], post[64]; } guarded;
static void prepare(guarded *g)
{
    int i;
    for (i=0;i<16;i++) g->pre[i] = g->value[i] = ~0UL;
    for (i=0;i<64;i++) g->post[i] = ~0UL;
}
static int intact(const guarded *g)
{
    int i;
    for(i=0;i<16;i++) if(g->pre[i]!=~0UL || g->value[i]==~0UL) return 0;
    for(i=0;i<64;i++) if(g->post[i]!=~0UL) return 0;
    return 1;
}
static void timeout_handler(int sig)
{
    static const char text[]="PMU_TIMEOUT: see last PMU_CASE / PMU_STAGE in job.log\n";
    (void)sig; write(2,text,sizeof(text)-1); _exit(124);
}
static FILE *open_output(const char *dir, const char *name)
{
    char path[4096]; FILE *f;
    if(snprintf(path,sizeof(path),"%s/%s",dir,name)>=(int)sizeof(path)) exit(2);
    f=fopen(path,"w"); if(!f) { perror(path); exit(2); } return f;
}
int main(int argc, char **argv)
{
    int pairs[][2]={{0,1},{1,2},{0,8},{8,16},{18,20},{18,34},{0,54},{54,0}};
    int sizes[]={64,4096}, ns_smoke[]={0,64,256}, ns_cal[]={0,256,1024,4096};
    int cal,e,p,s,k,r,m,i,rc,case_id=0,status=0;
    int ne,np,ns,nn,nr,*counts;
    pmu_result results[64] __attribute__((aligned(128)));
    pmu_args args; guarded before,after; struct utsname host;
    FILE *raw,*checks,*info;
    if(argc!=3 || (strcmp(argv[2],"smoke") && strcmp(argv[2],"calibrate"))) {
        fprintf(stderr,"Usage: pmu_probe NEW_OUTPUT_DIRECTORY smoke|calibrate\n"); return 2;
    }
    cal=!strcmp(argv[2],"calibrate");
    ne=cal?22:7; np=cal?8:2; ns=cal?2:1; nn=cal?4:3; nr=cal?3:2;
    counts=cal?ns_cal:ns_smoke;
    setvbuf(stdout,NULL,_IOLBF,0);
    signal(SIGALRM,timeout_handler); alarm(60);
    raw=open_output(argv[1],"counters.csv"); checks=open_output(argv[1],"checks.csv");
    info=open_output(argv[1],"runtime.txt");
    if(!uname(&host)) fprintf(info,"compute_host=%s\nmachine=%s\n",host.nodename,host.machine);
    fprintf(info,"profile=%s\nexpected_cases=%d\narray_order=uncalibrated\nsizeof_unsigned_long=%lu\n",
        argv[2],ne*np*ns*nn*nr*2,(unsigned long)sizeof(unsigned long));
    fclose(info);
    fprintf(raw,"case_id,event,repeat,mode,src,dst,bytes,n,cell,before,after,delta,decreased\n");
    fprintf(checks,"case_id,pe,errors,local_done,remote_done,cycles,source_addr,stack_addr\n");
    printf("PMU_STAGE athread_init\n");
    if(athread_init()) return 3;
    args.results=results;
    for(e=0;e<ne;e++) for(p=0;p<np;p++) for(s=0;s<ns;s++) for(r=0;r<nr;r++)
    for(k=0;k<nn;k++) for(m=0;m<2;m++) {
        int decreasing=0;
        args.src=pairs[p][0]; args.dst=pairs[p][1]; args.bytes=sizes[s];
        /* Reverse count and control order on alternating repetitions. */
        args.iterations=counts[r%2?nn-1-k:k]; args.local_only=(m+r)%2;
        memset(results,0xff,sizeof(results)); prepare(&before); prepare(&after);
        alarm(60);
        printf("PMU_CASE %d event=%s mode=%s src=%d dst=%d bytes=%d n=%d repeat=%d\n",
            ++case_id,events[e].name,args.local_only?"local":"put",args.src,args.dst,args.bytes,args.iterations,r+1);
        printf("PMU_STAGE init_count\n");
        events[e].init(); events[e].count(before.value);
        if(!intact(&before)) { fprintf(stderr,"PMU_ARRAY_ERROR before\n"); status=4; goto done; }
        rc=athread_spawn(pmu_kernel,&args); if(!rc) rc=athread_join();
        /* No printf between kernel return and the final counter read. */
        events[e].count(after.value); alarm(0);
        if(rc || !intact(&after)) { fprintf(stderr,"PMU_API_OR_ARRAY_ERROR rc=%d\n",rc); status=4; goto done; }
        for(i=0;i<16;i++) {
            int dec=after.value[i]<before.value[i]; decreasing+=dec;
            fprintf(raw,"%d,%s,%d,%s,%d,%d,%d,%d,%d,%lu,%lu,",case_id,events[e].name,r+1,
                args.local_only?"local":"put",args.src,args.dst,args.bytes,args.iterations,i,before.value[i],after.value[i]);
            if(!dec) fprintf(raw,"%lu",after.value[i]-before.value[i]);
            fprintf(raw,",%d\n",dec);
        }
        for(i=0;i<64;i++) {
            pmu_result *v=results+i;
            if(v->pe!=i) ++status;
            status+=v->errors!=0;
            if(!args.local_only && i==args.src && v->local_done!=(unsigned long)args.iterations) ++status;
            if(!args.local_only && i==args.dst && v->remote_done!=(unsigned long)args.iterations) ++status;
            fprintf(checks,"%d,%d,%d,%lu,%lu,%lu,%lu,%lu\n",case_id,i,v->errors,
                v->local_done,v->remote_done,v->cycles,v->source_addr,v->stack_addr);
        }
        fflush(raw); fflush(checks);
        printf("PMU_RETURN %d errors=%d decreased_cells=%d\n",case_id,status,decreasing);
        if(status || decreasing) { status=5; goto done; }
    }
done:
    alarm(60); athread_halt(); alarm(0);
    if(fclose(raw)) status=6;
    if(fclose(checks)) status=6;
    if(!status) { FILE *f=open_output(argv[1],"RUN_COMPLETE"); fprintf(f,"cases=%d\n",case_id); fclose(f); }
    return status?1:0;
}
