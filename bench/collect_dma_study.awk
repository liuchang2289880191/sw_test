# Login-node validation and aggregation. No Python or compute-node shell needed.
# awk -v out=DIR -v capacity=65536 -v seed=20261005 -f collect_dma_study.awk DIR/plan.csv
function fail(s) { print "ERROR: " s > "/dev/stderr"; failed=1; exit 1 }
function abs(x) { return x < 0 ? -x : x }
function integer(x) { return x ~ /^[0-9]+$/ }
function hex(x,   i,n,d) {
    x=tolower(x); sub(/^0x/, "", x)
    if (x !~ /^[0-9a-f]+$/) fail("invalid address")
    n=0
    for (i=1;i<=length(x);i++) {
        d=index("0123456789abcdef", substr(x,i,1))-1
        n=n*16+d
    }
    return n
}
function read_case(path,mode,bytes,reps,active,offset,stride,map,   line,a,n,pe,pes,agg,mx,cy,bw,sbase,dbase,r) {
    delete pe_seen
    r=(getline line < path)
    sub(/\r$/, "", line)
    if (r!=1 || line!=raw_header) fail("missing file or invalid header: " path)
    pes=agg=mx=0
    while ((r=(getline line < path))>0) {
        sub(/\r$/, "", line)
        n=split(line,a,",")
        if (n!=17 || a[1]!="dma" || a[2]!=mode || a[3]!=bytes || a[4]!=reps ||
            a[5]!=active || a[6]!=offset || a[12]!=stride || a[13]!=map || a[14]!=seed ||
            !integer(a[8]) || a[8]+0<=0 || !integer(a[11]) || a[11]+0!=0 ||
            a[9]!~/^[0-9]+[.][0-9]+$/ || abs(a[9]-a[8]/reps)>0.000001)
            fail("invalid configuration, timing or errors: " path)
        if (a[7]=="aggregate") {
            agg++; cy=a[8]+0; bw=a[10]+0
            if (a[10]!~/^[0-9]+[.][0-9]+$/ || bw<=0 || a[15]!="" || a[16]!="" || a[17]!="")
                fail("invalid aggregate: " path)
        } else {
            pe=a[7]+0
            if (!integer(a[7]) || pe>=active || pe_seen[pe]++ || a[10]!="" ||
                !integer(a[15]) || a[15]!=slots[map,pe]) fail("invalid PE/slot: " path)
            sbase=hex(a[16])-a[15]*stride-offset
            dbase=hex(a[17])-a[15]*stride-offset
            if (!base_set) { src_base=sbase; dst_base=dbase; base_set=1 }
            if (sbase!=src_base || dbase!=dst_base || sbase%128 || dbase%128)
                fail("host buffer base changed or bad address: " path)
            if (a[8]>mx) mx=a[8]+0
            pes++
        }
    }
    close(path)
    if (r<0 || agg!=1 || pes!=active || cy!=mx || abs(bw-bytes*reps*active/cy)>0.000000001)
        fail("incomplete CSV or inconsistent aggregate: " path)
    result_cycles=cy; result_bw=bw
}
BEGIN {
    FS=OFS=","; capacity+=0; seed+=0
    if (capacity<512 || capacity>131072 || capacity%128 || seed<1 || seed>2147483647)
        fail("invalid capacity or seed")
    raw_header="benchmark,mode,bytes,reps,active_pes,offset,pe,cycles,cycles_per_op,aggregate_bytes_per_cycle,errors,slot_stride,mapping,mapping_seed,slot,src_address,dst_address"
    nm=split("get put iget iput", modes," ")
    na=split("1 2 4 8 16 32 64", actives," ")
    nmap=split("identity reverse transpose shuffle", maps," ")
    for(i=1;i<=nm;i++) mode_ok[modes[i]]=1
    for(i=1;i<=na;i++) active_ok[actives[i]]=1
    for(i=1;i<=nmap;i++) map_ok[maps[i]]=1
    split("64 96 124 128 132 192 252 256 260", tmp," ")
    for(i in tmp) { allowed["boundary",tmp[i]]=1; nb++ }
    delete tmp
    split("8 16 32 64 96 124 128 132 192 252 256 260 384 512 768 1024 1536 2048 3072 4096 6144 8192 12288 16384 24576 32768 49152 65536 98304 131072",tmp," ")
    for(i in tmp) if(tmp[i]<=capacity) { allowed["load",tmp[i]]=1; nl++ }
    delete tmp
    split("64 128 256 4096 32768 65536 98304 131072",tmp," ")
    for(i in tmp) if(tmp[i]<=capacity) { allowed["mapping",tmp[i]]=1; ns++ }
    strides[capacity+128]=1; strides[capacity+256]=1
    strides[capacity+4096]=1; strides[2*capacity]=1
    for(i in strides) nt++
    expected["boundary"]=4*7*4*nb
    expected["load"]=4*7*2*nl
    expected["mapping"]=4*7*2*ns*nt*4
    path=out "/slot_maps.csv"
    if ((getline line < path)!=1 || line!="mapping,mapping_seed,pe,slot") fail("invalid slot_maps.csv")
    while ((r=(getline line < path))>0) {
        sub(/\r$/, "", line); n=split(line,a,",")
        if(n!=4 || !(a[1] in map_ok) || a[2]!=seed || !integer(a[3]) || a[3]>=64 ||
            !integer(a[4]) || a[4]>=64 || seen_pe[a[1],a[3]]++ || seen_slot[a[1],a[4]]++)
            fail("invalid slot map or non-bijective permutation")
        if ((a[1]=="identity" && a[4]!=a[3]) ||
            (a[1]=="reverse" && a[4]!=63-a[3]) ||
            (a[1]=="transpose" && a[4]!=(a[3]%8)*8+int(a[3]/8))) fail("wrong slot map")
        slots[a[1],a[3]]=a[4]; map_count[a[1]]++
    }
    close(path)
    if(r<0) fail("cannot read slot maps")
    for(i=1;i<=nmap;i++) if(map_count[maps[i]]!=64) fail("incomplete slot map")
    for(i=1;i<=nm;i++) {
        read_case(out "/smoke/" modes[i] "_1pe.csv",modes[i],8,10,1,0,capacity+128,"identity")
        read_case(out "/smoke/" modes[i] "_64pe.csv",modes[i],8,10,64,0,capacity+128,"identity")
    }
    summary=out "/study_summary.csv"; scaling=out "/study_scaling.csv"
    print "case_id,phase,mode,bytes,reps,active_pes,offset,slot_stride,mapping,mapping_seed,cycles,cycles_per_op,aggregate_bytes_per_cycle,errors" > summary
    print "phase,mode,bytes,offset,slot_stride,mapping,mapping_seed,active_pes,single_bytes_per_cycle,aggregate_bytes_per_cycle,bandwidth_ratio_to1,parallel_efficiency" > scaling
}
NR==1 {
    sub(/\r$/, "")
    if($0!="case_id,phase,mode,bytes,reps,active_pes,offset,slot_stride,mapping,mapping_seed,filename") fail("invalid plan header")
    next
}
{
    sub(/\r$/, "")
    if(NF!=11 || $1!=NR-1 || !($3 in mode_ok) || !(($2 SUBSEP $4) in allowed) ||
        $5!=($4<1024?10000:1000) || !($6 in active_ok) || !($9 in map_ok) || $10!=seed ||
        $11!=sprintf("case_%06d.csv",$1) || !($8 in strides)) fail("invalid plan row " NR)
    if ($2=="boundary") {
        if(($7!=0 && $7!=4 && $7!=64 && $7!=124) || $8!=capacity+128 || $9!="identity") fail("bad boundary configuration")
    } else if ($2=="load" || $2=="mapping") {
        if($7!=0 && $7!=4) fail("bad offset")
        if($2=="load" && ($8!=capacity+128 || $9!="identity")) fail("bad load configuration")
    } else fail("unknown phase")
    key=$2 SUBSEP $3 SUBSEP $4 SUBSEP $6 SUBSEP $7 SUBSEP $8 SUBSEP $9
    if(config_seen[key]++) fail("duplicate configuration")
    read_case(out "/raw/" $11,$3,$4,$5,$6,$7,$8,$9)
    printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%.0f,%.6f,%.9f,0\n",$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,result_cycles,result_cycles/$5,result_bw > summary
    key=$2 SUBSEP $3 SUBSEP $4 SUBSEP $7 SUBSEP $8 SUBSEP $9 SUBSEP $10
    if(!(key in group_seen)) { group_seen[key]=1; group_order[++ng]=key }
    bandwidth[key,$6]=result_bw
    phase_count[$2]++; count++
}
END {
    if(failed) exit 1
    for(phase in expected) if(phase_count[phase]!=expected[phase]) fail("missing configurations in " phase)
    if((getline line < (out "/RUN_COMPLETE"))!=1 || line!="completed_cases=" count) fail("RUN_COMPLETE count mismatch")
    close(out "/RUN_COMPLETE")
    for(g=1;g<=ng;g++) {
        key=group_order[g]; split(key,a,SUBSEP)
        for(i=2;i<=na;i++) {
            one=bandwidth[key,1]; many=bandwidth[key,actives[i]]
            if(one<=0 || many<=0) fail("unmatched scaling configuration")
            printf "%s,%s,%s,%s,%s,%s,%s,%s,%.9f,%.9f,%.6f,%.6f\n",a[1],a[2],a[3],a[4],a[5],a[6],a[7],actives[i],one,many,many/one,many/one/actives[i] > scaling
        }
    }
    close(summary); close(scaling)
    printf "DMA study validated: %d cases (boundary=%d, load=%d, mapping=%d).\n",count,phase_count["boundary"],phase_count["load"],phase_count["mapping"]
    print "completed_cases=" count > (out "/COMPLETE")
}
