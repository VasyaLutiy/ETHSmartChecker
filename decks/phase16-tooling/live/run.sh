#!/bin/bash
# Phase 16 §3.4 live check: night2 copy, dashboard + listen 10 min, headless Chrome over CDP.
set -m
R=/home/john/Documents/Work2026/ETHSmartChecker
L=/tmp/p16/live
cd $R
rm -f $L/ethsc.sqlite*
cp smoke/20261001-night2/ethsc.sqlite $L/ethsc.sqlite
HEAD=$(curl -s -X POST -H 'content-type: application/json' --data '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}' https://ethereum-rpc.publicnode.com | python3 -c 'import sys,json;print(int(json.load(sys.stdin)["result"],16))')
venv/bin/python -c "from ethsc.store import Store; s=Store('$L/ethsc.sqlite'); s.set_progress($HEAD-1); s.close()"
echo "head $HEAD, progress set to $((HEAD-1))"
venv/bin/python -m ethsc --db $L/ethsc.sqlite dashboard --static dashboard/dist --port 8090 2> $L/dash.err &
DASH=$!
venv/bin/python -m ethsc --db $L/ethsc.sqlite listen --source publicnode > $L/listen.out 2> $L/listen.err &
LISTEN=$!
sleep 3
google-chrome --headless=new --remote-debugging-port=9333 --user-data-dir=$L/chrome --no-first-run \
  --window-size=1400,1100 --enable-logging=stderr --v=0 http://127.0.0.1:8090/ 2> $L/chrome.err &
CHROME=$!
sleep 8
node $L/cdp.mjs sample
node $L/cdp.mjs shot $L/shot-start.png
node $L/cdp.mjs watch 600 > $L/watch.log
node $L/cdp.mjs shot $L/shot-10min.png
kill -INT $DASH; wait $DASH; echo "dashboard stopped rc=$?"
sleep 20
node $L/cdp.mjs sample > $L/down.log
node $L/cdp.mjs shot $L/shot-down.png
venv/bin/python -m ethsc --db $L/ethsc.sqlite dashboard --static dashboard/dist --port 8090 2>> $L/dash.err &
DASH=$!
sleep 65
node $L/cdp.mjs sample > $L/up.log
node $L/cdp.mjs shot $L/shot-up.png
kill -INT $LISTEN; wait $LISTEN; echo "listen rc=$?"
kill -INT $DASH; wait $DASH
kill $CHROME; wait $CHROME 2>/dev/null
echo done
