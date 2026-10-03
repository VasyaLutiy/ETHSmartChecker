import json, sys, sqlite3, time
sys.path.insert(0, "/home/john/Documents/Work2026/ETHSmartChecker")
from ethsc.fingerprint import fingerprint, score_fingerprints
from ethsc.evm import strip_metadata, disassemble
def shingles(code):
    body,_=strip_metadata(code); ops=[op for _,op,_ in disassemble(body)]
    return frozenset(tuple(ops[i:i+5]) for i in range(len(ops)-4))
def J(a,b): return 0.0 if not a or not b else len(a&b)/len(a|b)
T0=time.time()
lab=json.load(open("calibration_labels.json"))
codes={a:bytes.fromhex(h[2:]) for a,h in json.load(open("codes.json")).items()}
db=sqlite3.connect(sys.argv[1])
fps={}; raw={}
for cid,size,sk,sel,pk,pt,std,code in db.execute("select code_id,size,skeleton_hash,selectors,proxy_kind,proxy_target,std_proxy,code from codes"):
    fps[cid]={"code_id":cid,"size":size,"skeleton_hash":sk,"selectors":json.loads(sel) if sel else [],"proxy":({"kind":pk,"target":pt} if pk else None),"std_proxy":bool(std)}; raw[cid]=code
addrs=sorted({a for k in ("positives","negatives") for p in lab[k] for a in p})
cid={}
for a in addrs:
    f=fingerprint(codes[a]); cid[a]=f["code_id"]; fps.setdefault(f["code_id"],f); raw.setdefault(f["code_id"],codes[a])
labset=set(cid.values()); MAN={cid[a] for a in lab.get('strict',[])}; benign=[c for c in fps if c not in labset]
SH={}
def sh(c):
    if c not in SH: SH[c]=shingles(raw[c])
    return SH[c]
sel={}  # (labelled cid) -> {cid: score>=0.5}
for a in addrs:
    s=cid[a]
    if s in sel: continue
    sel[s]={c:v for c in fps if c!=s for v in [score_fingerprints(fps[s],fps[c])] if v>=0.5}
print("benign_total",len(benign),"labelled",len(addrs),"prep %.0fs"%(time.time()-T0))
print("t\trecall\tneg\tbenign\tiface_only\tstrict_seeds")
for t in (0.5,0.6,0.7,0.75,0.8,0.9,1.0):
    strict={}
    for s,m in sel.items():
        strict[s]=s in MAN
    def ok(s,c):
        v=score_fingerprints(fps[s],fps[c])
        return v>=t and (not strict[s] or J(sh(s),sh(c))>=0.6)
    d=lambda k:[ok(cid[a],cid[b]) for a,b in lab[k]]+[ok(cid[b],cid[a]) for a,b in lab[k]]
    p=d("positives"); n=d("negatives")
    bset=set(benign); bh=set(); bi=set()
    for s,m in sel.items():
        for c,v in m.items():
            if c in bset and v>=t and (not strict[s] or J(sh(s),sh(c))>=0.6):
                bh.add(c)
                if J(sh(s),sh(c))<0.6: bi.add(c)
    viol=[(a[:10],b[:10]) for a,b in lab["negatives"] if ok(cid[a],cid[b]) or ok(cid[b],cid[a])]
    print(t, round(sum(p)/len(p),4), sum(n), len(bh), len(bi), sum(strict.values()), viol, sep="\t")
print("done %.0fs"%(time.time()-T0))
