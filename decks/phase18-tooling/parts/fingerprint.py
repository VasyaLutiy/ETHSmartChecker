from tests.helpers import load_hex
from ethsc import fingerprint as F
H = load_hex
def e1():
    a, b = H("code_belle.hex"), H(COPY_HEX[0])
    chk("Code Similarity 1 (a, b)", F.code_similarity(a, b), 920 / 929)
    chk("Code Similarity 1 (b, a)", F.code_similarity(b, a), 920 / 929)
    chk("Code Similarity 1 shingle sizes", (len(F.opcode_shingles(a)), len(F.opcode_shingles(b))), (924, 925))
    chk("Code Similarity 1 opcode_shingles returns a frozenset", type(F.opcode_shingles(a)).__name__, "frozenset")
    g = sorted(F.opcode_shingles(a))[0]
    chk("Code Similarity 1 a shingle is a 5-tuple of ints", (type(g).__name__, len(g), all(isinstance(x, int) for x in g)), ("tuple", 5, True))
def e2():
    chk("Code Similarity 2 univ3 pools", F.code_similarity(H("code_univ3_usdc_weth_005.hex"), H("code_univ3_pool_e0554a47.hex")), 1.0)
    chk("Code Similarity 2 launchtoken pair", F.code_similarity(H("code_launchtoken_40676634.hex"), H("code_launchtoken_4e67db19.hex")), 1.0)
def e3():
    chk("Code Similarity 3 belle/weth9", F.code_similarity(H("code_belle.hex"), H("code_weth9.hex")), 209 / 1291)
    chk("Code Similarity 3 weth9/usdt", F.code_similarity(H("code_weth9.hex"), H("code_usdt.hex")), 430 / 1311)
    chk("Code Similarity 3 two standard proxies", F.code_similarity(H("code_proxy_seed_0c010533.hex"), H("code_proxy_046eee2c.hex")), 197 / 1221)
def e4():
    a, b = H("code_clone_270df012.hex"), H("code_clone_2ca7b61b.hex")
    chk("Code Similarity 4 clones code_similarity", F.code_similarity(a, b), 1.0)
    chk("Code Similarity 4 clones similarity unchanged", F.similarity(a, b), 0.0)
def e5():
    w = H("code_weth9.hex")
    chk("Code Similarity 5 empty", F.code_similarity(b"", w), 0.0)
    chk("Code Similarity 5 two opcodes", F.code_similarity(b"\x60\x00\x60\x00", b"\x60\x00\x60\x00"), 0.0)
    chk("Code Similarity 5 shingle sizes", [len(F.opcode_shingles(x)) for x in (b"", b"\x60\x00\x60\x00", b"\x60\x00" * 5, b"\xfe\xff\x7f")], [0, 0, 1, 0])
    chk("Code Similarity 5 garbage", F.code_similarity(b"\xfe\xff\x7f", b"\xfe\xff\x7f"), 0.0)
def e6():
    chk("Code Similarity 6 ALERT_MIN", F.ALERT_MIN, 0.75)
    chk("Code Similarity 6 CODE_MIN", F.CODE_MIN, 0.6)
def keep():
    a, b = H("code_belle.hex"), H(COPY_HEX[0])
    chk("unchanged: similarity of the BELLE pair", F.similarity(a, b), 13 / 15)
    chk("unchanged: score_fingerprints of the BELLE pair", F.score_fingerprints(F.fingerprint(a), F.fingerprint(b)), 13 / 15)
    chk("unchanged: fingerprint keys", sorted(F.fingerprint(a).keys()), ["code_id", "proxy", "selectors", "size", "skeleton_hash", "std_proxy"])
for n, f in [("Code Similarity 1", e1), ("Code Similarity 2", e2), ("Code Similarity 3", e3), ("Code Similarity 4", e4),
             ("Code Similarity 5", e5), ("Code Similarity 6", e6), ("unchanged", keep)]:
    run(n, f)
finish()
