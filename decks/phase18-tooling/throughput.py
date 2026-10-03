import sys, time, sqlite3
sys.path.insert(0, sys.argv[1])
from ethsc.store import Store
from ethsc.cluster import match_watchlist
db = "/tmp/p18/live/night2.sqlite"
c = sqlite3.connect(db); codes = [r[0] for r in c.execute("SELECT code FROM codes ORDER BY code_id LIMIT 1000 OFFSET 5000")]; c.close()
s = Store(db, readonly=True) if len(sys.argv) > 2 else Store(db)
t = time.time(); n = 0
for code in codes:
    n += len(match_watchlist(s, code, min_score=0.75))
dt = time.time() - t
print("%s: %.1f ms per code, %d alerts" % (sys.argv[1], dt / len(codes) * 1000, n))
