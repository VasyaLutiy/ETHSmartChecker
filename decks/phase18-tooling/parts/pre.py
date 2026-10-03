import socket, sys
_orig_connect = socket.socket.connect
def _b(*a, **k):
    raise OSError("network blocked")
def _c(self, addr, *a, **k):
    if isinstance(addr, tuple) and addr and addr[0] == "127.0.0.1":
        return _orig_connect(self, addr, *a, **k)
    raise OSError("network blocked")
socket.getaddrinfo = _b; socket.create_connection = _b; socket.socket.connect = _c
import contextlib, inspect, io, json, os, sqlite3, tempfile
from unittest import mock
bad = []
def chk(name, got, want):
    if got != want:
        r = repr(got)
        w = repr(want)
        bad.append("%s: got %s, want %s" % (name, r if len(r) < 300 else r[:300] + "...", w if len(w) < 300 else w[:300] + "..."))
def run(name, fn):
    try:
        fn()
    except Exception as e:
        bad.append("%s: raised %r" % (name, e))
def finish():
    print("\n".join(bad) if bad else "probe OK")
    sys.exit(1 if bad else 0)
BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
COPIES = ["0x1807090dd15a6f58e00fd769e32ebf20ee610385", "0x2141be5f2afa674c94167ab167a478a56cb539f5",
          "0x46cadea509dc3d3c96a11fb61ab8b222f5238f0a", "0x6411bed82614b91ef655d82486e0bd3a13d2eb8c"]
COPY_HEX = ["code_belle_copy_1807090d.hex", "code_belle_copy_2141be5f.hex", "code_belle_copy_46cadea5.hex", "code_belle_copy_6411bed8.hex"]
SHIB = "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce"
LINK = "0x514910771af9ca656af840dff83e8264ecf986ca"
UNI = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
U2205 = "0x22052a1a0f5a3d2839d71c458f177e68b0e73963"
X9999 = "0x9999999999999999999999999999999999999999"
B53C = "0xb53c071bdb35d21aa1216b084f79c372d71053d5"
C02A = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
FF74 = "0xff74317e948695297acb79cb2de06111f5cc16b3"
SEED1 = "0x1111111111111111111111111111111111111111"
B_ID = "8571d00b598627ac40e1ae7bc4d0cb3fd5a77a0d663763fdfc1cd9127b63cb4d"
D_ID = "ee3b081294ee0f2f1804d8aa0204848d1d0f58efe81fae42998e81f1170c9ef9"
LAB = {"positives": [[BELLE, COPIES[0]], [UNI, U2205], [BELLE, X9999]], "negatives": [[BELLE, SHIB]], "strict": [BELLE]}
