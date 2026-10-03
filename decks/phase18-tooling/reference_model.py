"""Reference model of the phase-18 rule, for measuring Contour examples only."""
import sys, json
sys.path.insert(0, "/home/john/Documents/Work2026/ETHSmartChecker")
sys.path.insert(0, "/home/john/Documents/Work2026/ETHSmartChecker/tests")
from ethsc.fingerprint import fingerprint, score_fingerprints
from ethsc.evm import strip_metadata, disassemble
ALERT_MIN, CODE_MIN, GENERIC_HITS = 0.7, 0.6, 10
def opcode_shingles(code):
    body,_ = strip_metadata(code); ops=[op for _,op,_ in disassemble(body)]
    return frozenset(tuple(ops[i:i+5]) for i in range(len(ops)-4))
def code_similarity(a,b):
    x,y=opcode_shingles(a),opcode_shingles(b)
    if not x or not y: return 0.0
    return float(len(x&y))/float(len(x|y))
def interface_hits(store, code_id, min_score=ALERT_MIN, code_min=CODE_MIN):
    fps={f["code_id"]:f for f in store.fingerprints()}
    if code_id not in fps: return 0
    seed=fps[code_id]; sc=store.code_by_id(code_id); n=0
    for cid,f in fps.items():
        if cid==code_id: continue
        if score_fingerprints(seed,f)>=min_score and code_similarity(sc,store.code_by_id(cid))<code_min: n+=1
    return n
def passes(store, s_cid, c_cid, t, strict, fps):
    sel=score_fingerprints(fps[s_cid],fps[c_cid])
    if sel<t: return False, sel, None
    if not strict: return True, sel, None
    cs=code_similarity(store.code_by_id(s_cid),store.code_by_id(c_cid))
    return cs>=CODE_MIN, sel, cs
def evaluate(store, labels, thresholds=(0.5,0.6,0.7,0.8,0.9,1.0)):
    fps={f["code_id"]:f for f in store.fingerprints()}
    addrs=sorted({a.lower() for k in ("positives","negatives") for p in labels.get(k,[]) for a in p})
    cid={}; missing=[]
    for a in addrs:
        c=store.code_of(a)
        if c is None: missing.append(a)
        else: cid[a]=fingerprint(c)["code_id"]
    lab={cid[a] for a in cid}
    benign=[c for c in fps if c not in lab]
    rows=[]
    for t in thresholds:
        strict={a: interface_hits(store,cid[a],t)>=GENERIC_HITS for a in cid}
        def dirs(k):
            out=[]
            for a,b in labels.get(k,[]):
                a,b=a.lower(),b.lower()
                if a in cid and b in cid:
                    out.append(passes(store,cid[a],cid[b],t,strict[a],fps)[0]); out.append(passes(store,cid[b],cid[a],t,strict[b],fps)[0])
            return out
        p=dirs("positives"); n=dirs("negatives")
        bh=set(); bi=set()
        for c in benign:
            for a in cid:
                ok,sel,cs=passes(store,cid[a],c,t,strict[a],fps)
                if ok:
                    bh.add(c)
                    if not strict[a] and code_similarity(store.code_by_id(cid[a]),store.code_by_id(c))<CODE_MIN: bi.add(c)
        rows.append({"threshold":t,"recall":(sum(p)/len(p) if p else 0.0),"negatives":sum(n),"benign":len(bh),"interface_only":len(bi)})
    return {"rows":rows,"missing":missing,"benign_total":len(benign)}
