# Login-node validation and collection; scheduler/stderr text is never CSV input.
function fail(message) { print "ERROR: " message > "/dev/stderr"; exit 1 }
function abs(x) { return x < 0 ? -x : x }
function member(c, local_id) { return (int(c/4)*2+int(local_id/2))*8+(c%4)*2+local_id%2 }
function edge(src,dst) { active[src]=1; active[dst]=1; flows++ }
function setup(    i,j,near,side,far) {
    for(i in active) delete active[i]
    flows=0
    if(type=="bandwidth") { edge($6+0,$7+0); return }
    near=int(cluster/4)==3 ? cluster-4 : cluster+4
    side=cluster%4==3 ? cluster-1 : cluster+1
    far=((int(cluster/4)+2)%4)*4+cluster%4
    if(name=="single") edge(member(cluster,0),member(cluster,1))
    else if(name=="intra2") {edge(member(cluster,0),member(cluster,1));edge(member(cluster,2),member(cluster,3))}
    else if(name ~ /^split_/) {
        edge(member(cluster,0),member(cluster,1))
        i=name=="split_near2" ? near : (name=="split_side2" ? side : far)
        edge(member(i,0),member(i,1))
    } else if(name=="incast3") {for(i=1;i<4;i++) edge(member(cluster,i),member(cluster,0))}
    else if(name=="ring4") {
        edge(member(cluster,0),member(cluster,1));edge(member(cluster,1),member(cluster,3))
        edge(member(cluster,3),member(cluster,2));edge(member(cluster,2),member(cluster,0))
    } else if(name=="alltoall4") {for(i=0;i<4;i++) for(j=0;j<4;j++) if(i!=j) edge(member(cluster,i),member(cluster,j))}
    else fail("unknown flow case " name)
}
BEGIN {
    FS=","
    summary=out "/summary.csv"; latency=out "/latency.csv"
    print "case_id,phase,type,case,src,dst,bytes,reps,window,cluster_index,flows,max_cycles,aggregate_bytes_per_cycle,errors" > summary
    print "case_id,phase,bytes,reps,initiator,peer,same_cluster,row_distance,col_distance,rtt_cycles,latency_cycles,errors" > latency
}
NR==1 {
    sub(/\r$/, "")
    if($0!="order,phase,case_id,type,case,src,dst,bytes,reps,window,cluster_index") fail("invalid plan header")
    next
}
{
    sub(/\r$/, "")
    if(NF!=11) fail("invalid plan row")
    phase=$2; id=$3; type=$4; name=$5; bytes=$8+0; reps=$9+0; window=$10+0; cluster=$11+0
    if(id !~ /^[a-zA-Z0-9_]+$/ || (phase!="raw" && phase!="smoke") || planned[phase SUBSEP id]++) fail("invalid/duplicate case ID")
    file=out "/" phase "/" id ".csv"
    if((getline line < file)!=1) fail("missing CSV " file)
    sub(/\r$/, "", line)
    if(type=="latency") header="benchmark,bytes,reps,initiator,peer,same_cluster,row_distance,col_distance,rtt_cycles,latency_cycles,errors"
    else header="benchmark,case,cluster_index,bytes,reps,window,flows,pe,cycles,aggregate_bytes_per_cycle,errors"
    if(line!=header) fail("invalid CSV header " file)
    for(i in seen) delete seen[i]
    rows=0; aggregates=0; max_cycles=0
    if(type!="latency") setup()
    while((read_status=(getline line < file))>0) {
        sub(/\r$/, "", line)
        if(split(line,v,",")!=11 || v[11]!~/^[0-9]+$/ || v[11]+0!=0 || v[9]!~/^[0-9]+$/ || v[9]+0<=0) fail("invalid timing/errors " file)
        if(type=="latency") {
            a=v[4]+0; b=v[5]+0
            if(v[1]!="rma_pingpong" || v[2]+0!=bytes || v[3]+0!=reps || v[4]!~/^[0-9]+$/ || v[5]!~/^[0-9]+$/ || a>63 || b>63 || a==b || seen[a SUBSEP b]++) fail("invalid pair " file)
            same=(int(int(a/8)/2)*4+int((a%8)/2)==int(int(b/8)/2)*4+int((b%8)/2))
            if(v[6]+0!=same || v[7]+0!=abs(int(a/8)-int(b/8)) || v[8]+0!=abs(a%8-b%8) || v[10]+0<=0 || abs(v[10]-v[9]/(2*reps))>0.000001) fail("invalid latency metric " file)
            print id "," phase "," v[2] "," v[3] "," v[4] "," v[5] "," v[6] "," v[7] "," v[8] "," v[9] "," v[10] "," v[11] > latency
        } else {
            if(v[1]!="rma_flow" || v[2]!=name || v[3]+0!=cluster || v[4]+0!=bytes || v[5]+0!=reps || v[6]+0!=window || v[7]+0!=flows) fail("flow metadata mismatch " file)
            if(v[8]=="aggregate") {
                aggregates++; agg_cycles=v[9]+0; bw=v[10]+0
                if(bw<=0 || abs(bw-bytes*reps*flows/agg_cycles)>0.00000001) fail("invalid bandwidth metric " file)
            } else {
                if(v[8]!~/^[0-9]+$/ || !(v[8]+0 in active) || seen[v[8]+0]++ || v[10]!="") fail("invalid PE row " file)
                if(v[9]+0>max_cycles) max_cycles=v[9]+0
            }
        }
        rows++
    }
    close(file)
    if(read_status<0) fail("CSV read failed " file)
    if(type=="latency") { if(rows!=4032) fail("incomplete latency matrix " file) }
    else {
        active_count=0; for(i in active) active_count++
        if(rows!=active_count+1 || aggregates!=1 || max_cycles!=agg_cycles) fail("incomplete flow CSV " file)
        print id "," phase "," type "," name "," $6 "," $7 "," bytes "," reps "," window "," cluster "," flows "," agg_cycles "," sprintf("%.9f",bw) ",0" > summary
    }
}
