"""Command line interface of ETHSmartChecker.

python -m ethsc with subcommands over one SQLite db: listen, backfill,
clusters top, cluster, similar, seed add, seed list, seed strict, seed
audit, recheck, risk, calibrate, report, dashboard. Output is plain
text, one record per line, tab-separated, fully ordered; every float is
printed "%.4f". ALERT lines are printed from the on_alerts sink of
follow_chain as each block ends and flushed at once, so an alert
reaches the log before the next block is fetched and survives a pass
that never returns. The summary alerts are not printed a second time:
each alert appears exactly once. recheck prints the alerts of
recheck_watchlist over the whole database -- including the copies
already stored when the seed was added, which no listen or backfill
will ever report -- and seed add, after a successful add_seed, prints
the alerts for the new seed alone. Neither makes an rpc call: both
print through the same _print_alerts sink.

The <flags> field is the risk_flags of an address's code, the True names
joined by "," in the fixed order selfdestruct then mutable_delegatecall,
or "-" when neither is set (never an empty field). cluster and similar
always carry the field, "-" included, so the record keeps a fixed column
count. risk is a filter, not an annotation: it prints one
"<address>\t<flags>" record only for a stored address whose code has at
least one flag; a flagless address and an address without code never
appear, so risk has no "-" placeholder at all.

report writes build_report(store, --out) and prints exactly two lines:
the html path, then the json path; without matplotlib it writes no file
and exits 2 with one stderr line naming matplotlib.

Exit codes: 0 success, 1 a failed RPC call, 2 usage error (or a report
without matplotlib), 3 a budget or cap stop that left work undone --
then one line goes to stderr:
"stopped: <budget|cap>, spent <N> credits, progress <P>", where <N> is
the ledger of summary["day"], the day the pass last charged, and <P> is
"none" when no block has ever completed. The day is left to follow_chain
(day=None): it resolves the ledger day per block.
KeyboardInterrupt anywhere in listen or backfill -- in the sleep, in an
rpc call, in a retry backoff, inside ingest, in a store write, while the
ALERT lines are being written, while the stop line is being written, and
in the gap between a pass and the pause -- is a clean stop: exit 0, no
traceback, no stderr, the store still closed. main() never raises
SystemExit: argparse failures are caught and returned as the int code
2, so tests calling main() directly see the same code sys.exit(main())
produces in __main__.

Data source (phase 10): listen and backfill take --source
{infura,publicnode} (default infura) and --workers K. Infura keeps
prices=PRICES, code_tag None and workers --workers or 1; publicnode
builds RpcClient(PUBLICNODE_URL, prices={}, max_retries=5) without ever
calling infura_url(), and follow_chain gets prices={}, code_tag
"latest" and workers --workers or 8, so the credit ledger stays as it
was. A --daily-budget with publicnode, and --workers below 1, are usage
errors: exit 2, one stderr line, no rpc call.

The rpc client is built only on the paths that talk to the chain --
listen and backfill -- and only when the caller passed rpc=None; every
other subcommand runs without INFURA_API_KEY and infura_url() is never
called on their path. No network in this module: urllib, http and socket
stay in ethsc.rpc. The rpc object is injected (tests) or built here from
ethsc.rpc only; the store is used through its public methods, never its
private attributes.

seed add --fetch (phase 12) fetches the code of an address no listen or
backfill ever stored: keyless, over the public node, and only when the
address is not already in the store -- a known address, EOA included,
takes the old path and never builds a client or calls the chain. seed
remove <address> deletes one seed (exit 2, "not a seed: <address>",
when it was not one) and leaves the code and address rows untouched, so
the address can be seeded again without a new fetch.

Origin of an alert (phase 13): the ALERT record carries a sixth field,
the alerted address's origin (created, seen, fetched, unknown); --fetch
stores with origin "fetched". --alert-on on listen/backfill and
--origin on recheck filter the printed lines only -- they never touch
what follow_chain hands to on_alerts, the store writes, the progress or
the exit code.

Standard proxies (phase 14). listen and backfill print one
"UPGRADE\t<proxy>\t<old>\t<new>\t<block>" record per upgrade of a
block, after that block's ALERT lines; --alert-on never touches them.
The ALERT origin field gains "impl"; recheck --origin accepts it too.
cluster, clusters top, similar and recheck see through a resolved
proxy's implementation exactly as build_clusters, find_similar and
recheck_watchlist do -- this module decides none of that itself. seed
add --fetch also resolves a standard proxy's implementation at
"latest", fetching it the first time an address is seeded (fresh or
already held); it does not touch a held proxy that already has one,
and it does not call the beacon of a beacon proxy.

Dashboard (phase 15). dashboard --db PATH [--host H] [--port P]
[--static DIR] serves the store of that file read-only on localhost
through ethsc.dashboard: it never opens a writable Store, so the
database is neither migrated nor switched to WAL by it.

Calibration (phase 18). listen and backfill take --min M (a float,
default ALERT_MIN = 0.75) and pass it to follow_chain as watch; an M
that is not a float or lies outside [0, 1] is a usage error: exit 2,
one stderr line, empty stdout, no rpc call -- the value is validated
before any client is built. similar keeps --min 0.8: it is a search,
not an alert. recheck --min defaults to ALERT_MIN, and the seed add
preview runs recheck_watchlist at its own default. seed strict <addr>
{on,off} sets the seed's strict flag through
store.set_seed_strict(address, mode == "on"): exit 0 with empty stdout
and stderr when it returns True; "not a seed: <address lowercase>" on
stderr and exit 2 when it returns False; a bad address or mode is exit
2. seed audit prints, for every seed of store.seeds() in address order,
"<address>\t<label>\t<interface_hits>\t<strict|loose>" and writes
nothing. calibrate reads --labels with load_labels and --grid with
parse_grid (a ValueError is exit 2 with its str as the one stderr line,
before any store read) and prints evaluate(store, labels, thresholds),
one record per row in grid order:
"<threshold>\t<recall>\t<negatives>\t<benign>\t<interface_only>\t<benign_total>",
threshold and recall "%.4f", the counts plain integers; when missing is
not empty, one stderr line "missing: <addresses comma-joined>" follows;
exit 0. calibrate makes no rpc call and writes no row.
"""

import argparse
import os
import re
import sys
import time

from ethsc import dashboard
from ethsc.calibrate import evaluate, load_labels, parse_grid
from ethsc.cluster import (
    build_clusters,
    find_similar,
    interface_hits,
    recheck_watchlist,
)
from ethsc.config import PRICES, PUBLICNODE_URL
from ethsc.evm import is_std_proxy, risk_flags
from ethsc.fingerprint import ALERT_MIN
from ethsc.ingest import fetch_implementation, follow_chain
from ethsc.report import ChartsUnavailable, build_report
from ethsc.rpc import RpcClient, RpcError, infura_url
from ethsc.store import Store

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

# The fixed order of the flags field and of the --flag choices.
_FLAG_NAMES = ("selfdestruct", "mutable_delegatecall")

_HEX_DIGITS = "0123456789abcdefABCDEF"


class _UsageError(Exception):
    """An argparse-level usage error; main turns it into exit code 2."""


class _Parser(argparse.ArgumentParser):
    """ArgumentParser whose error() raises instead of exiting."""

    def error(self, message):
        raise _UsageError(message)


def _check_address(address):
    """Validate one positional address argument; exit code 2 otherwise."""
    if not _ADDRESS_RE.match(address):
        raise _UsageError("invalid address: %s" % address)
    return address


def _chain_rpc():
    """The rpc client for the subcommands that talk to the chain."""
    return RpcClient(infura_url())


def _is_hex_code(text):
    """True iff text is "0x" + a (possibly empty) run of hex digits.

    Copied from ethsc.ingest._is_hex_code, which is private: seed add
    --fetch needs the same eth_getCode validation without reaching into
    another module's private helper.
    """
    if not isinstance(text, str) or not text.startswith("0x"):
        return False
    body = text[2:]
    if len(body) % 2 != 0:
        return False
    for char in body:
        if char not in _HEX_DIGITS:
            return False
    return True


def _flags_field(code):
    """The <flags> text of one code: the True names joined, or "-"."""
    if code is None:
        return "-"
    flags = risk_flags(code)
    names = [name for name in _FLAG_NAMES if flags[name]]
    if not names:
        return "-"
    return ",".join(names)


def _print_alerts(alerts):
    """Write the block's ALERT lines to stdout and flush at once.

    Six fields since phase 13: the sixth is the alert's origin key.
    """
    for alert in alerts:
        sys.stdout.write(
            "ALERT\t%s\t%s\t%s\t%.4f\t%s\n"
            % (
                alert["address"],
                alert["seed_address"],
                alert["label"],
                alert["score"],
                alert["origin"],
            )
        )
    sys.stdout.flush()


def _alert_on_sink(alert_on):
    """The on_alerts sink of listen/backfill, filtered by --alert-on.

    A wrapper around _print_alerts, not a change in ingest: "all"
    prints every alert; "created" or "seen" prints only the lines whose
    origin matches, in the same order -- "impl" included under "all",
    hidden like any other origin under "created" or "seen" (phase 14).
    follow_chain always hands the full, unfiltered list to this sink --
    the filter touches stdout only, never the store writes, the
    progress or the stats.
    """
    if alert_on == "all":
        return _print_alerts

    def sink(alerts):
        _print_alerts([a for a in alerts if a["origin"] == alert_on])

    return sink


def _print_upgrades(upgrades):
    """Write the block's UPGRADE lines to stdout and flush at once.

    Printed after that block's ALERT lines (follow_chain calls
    on_alerts, then on_upgrades); never filtered by --alert-on, which
    touches ALERT lines only (phase 14).
    """
    for upgrade in upgrades:
        sys.stdout.write(
            "UPGRADE\t%s\t%s\t%s\t%d\n"
            % (upgrade["address"], upgrade["old"], upgrade["new"],
               upgrade["block"])
        )
    sys.stdout.flush()


def _follow(rpc, store, start=None, stop=None, daily_budget=None,
            max_calls=None, prices=PRICES, code_tag=None, workers=None,
            alert_on="all", watch=None):
    """One follow_chain call with the CLI's error and exit-code policy.

    Returns the exit code, or None when the pass was interrupted by
    KeyboardInterrupt (a clean stop: no output, no traceback). The ALERT
    lines of every block -- a complete one included -- are printed by
    the on_alerts sink as the block ends, filtered by --alert-on
    (phase 13). The stop line reports the ledger of summary["day"], the
    day the pass last charged, not the day it started on. prices,
    code_tag and workers come from the --source resolution in main;
    watch is the --min of listen/backfill (phase 18), handed to every
    ingest_block call of the pass.
    """
    try:
        summary = follow_chain(
            rpc,
            store,
            start=start,
            stop=stop,
            max_calls_per_block=max_calls,
            daily_budget=daily_budget,
            prices=prices,
            code_tag=code_tag,
            workers=workers,
            on_alerts=_alert_on_sink(alert_on),
            on_upgrades=_print_upgrades,
            watch=watch,
        )
    except KeyboardInterrupt:
        return None
    except RpcError as err:
        sys.stderr.write(str(err) + "\n")
        return 1
    if summary["stopped"] is None:
        return 0
    progress = summary["progress"]
    try:
        sys.stderr.write(
            "stopped: %s, spent %d credits, progress %s\n"
            % (
                summary["stopped"],
                store.spent(summary["day"]),
                "none" if progress is None else progress,
            )
        )
    except KeyboardInterrupt:
        return None
    return 3


def _run_backfill(args, rpc, store, prices, code_tag, workers):
    try:
        code = _follow(
            rpc,
            store,
            start=args.from_block,
            stop=args.to_block,
            daily_budget=args.daily_budget,
            max_calls=args.max_calls_per_block,
            prices=prices,
            code_tag=code_tag,
            workers=workers,
            alert_on=args.alert_on,
            watch=args.min,
        )
    except KeyboardInterrupt:
        # Ctrl-C in the gap between the pass and the return.
        return 0
    return 0 if code is None else code


def _run_listen(args, rpc, store, sleep, prices, code_tag, workers):
    try:
        while True:
            code = _follow(
                rpc,
                store,
                daily_budget=args.daily_budget,
                max_calls=args.max_calls_per_block,
                prices=prices,
                code_tag=code_tag,
                workers=workers,
                alert_on=args.alert_on,
                watch=args.min,
            )
            if code is None:
                # Ctrl-C inside the pass: a clean stop, no pause, no loop.
                return 0
            if code != 0:
                return code
            try:
                sleep(args.interval)
            except KeyboardInterrupt:
                return 0
    except KeyboardInterrupt:
        # Ctrl-C in the gap between a pass and the pause.
        return 0


def _run_clusters_top(args, store):
    for cluster in build_clusters(store)[: args.n]:
        sys.stdout.write(
            "%s\t%s\t%d\n"
            % (cluster["level"], cluster["key"], len(cluster["members"]))
        )
    return 0


def _run_cluster(args, store):
    _check_address(args.address)
    query = args.address.lower()
    flags = _flags_field(store.code_of(query))
    for cluster in build_clusters(store):
        if query in cluster["members"]:
            sys.stdout.write(
                "%s\t%s\t%s\t%s\n"
                % (cluster["level"], cluster["key"], ",".join(
                    cluster["members"]), flags)
            )
    return 0


def _run_similar(args, store):
    _check_address(args.address)
    for address, score in find_similar(
        store, args.address, min_score=args.min
    ):
        sys.stdout.write(
            "%s\t%.4f\t%s\n"
            % (address, score, _flags_field(store.code_of(address)))
        )
    return 0


def _stored_addresses_with_code(store):
    """Every stored address that has code, sorted ascending."""
    seen = set()
    for fp in store.fingerprints():
        seen.update(store.addresses_of(fp["code_id"]))
    return sorted(seen)


def _run_risk(args, store):
    """One "<address>\t<flags>" line per address with at least one flag.

    A filter, not an annotation: a flagless address and an address
    stored without code never appear. --flag restricts the listing to
    that one flag and prints only its name.
    """
    for address in _stored_addresses_with_code(store):
        flags = risk_flags(store.code_of(address))
        if args.flag is not None:
            if flags[args.flag]:
                sys.stdout.write("%s\t%s\n" % (address, args.flag))
        else:
            names = [name for name in _FLAG_NAMES if flags[name]]
            if names:
                sys.stdout.write("%s\t%s\n" % (address, ",".join(names)))
    sys.stdout.flush()
    return 0


def _run_seed_add(args, rpc, store):
    """seed add, with --fetch pulling or resolving an address's code.

    --fetch on an address the store does not hold makes exactly two
    calls, in order -- eth_blockNumber then eth_getCode -- on rpc (or a
    fresh keyless publicnode client when rpc is None); a code answer is
    stored and seeded, an "0x" answer is stored as an EOA and refused,
    any other answer or an RpcError leaves nothing stored.

    Standard proxies (phase 14). When the stored (or freshly fetched)
    code is a standard proxy, fetch_implementation follows at "latest"
    -- get_storage = rpc.call("eth_getStorageAt", [address, slot,
    "latest"]), get_code = rpc.call("eth_getCode", [address,
    "latest"]) -- storing the implementation with origin "impl". On a
    held address whose code is a standard proxy with no resolved
    implementation, --fetch is no longer a no-op: it makes
    eth_blockNumber and the same fetch_implementation calls, with no
    eth_getCode of the proxy itself (it is already stored). A held
    non-proxy, a held EOA, or a held proxy whose implementation is
    already resolved: --fetch stays a no-op, no client built, no rpc
    call at all. A slot read that fails or reads zero leaves the seed
    on the proxy's own code (phase 9), exit 0, nothing on stderr --
    fetch_implementation never raises.
    """
    _check_address(args.address)
    address = args.address.lower()
    known = store.has_address(address)
    stored_code = store.code_of(address) if known else None
    needs_resolve = (
        known and stored_code is not None and is_std_proxy(stored_code)
        and store.implementation(address) is None
    )
    if args.fetch and (not known or needs_resolve):
        if rpc is None:
            rpc = RpcClient(PUBLICNODE_URL, prices={}, max_retries=5)
        try:
            head = rpc.call("eth_blockNumber", [])
            text = None if known else rpc.call(
                "eth_getCode", [address, "latest"])
        except RpcError as err:
            sys.stderr.write(str(err) + "\n")
            return 1
        block = int(head, 16)
        code = stored_code
        if not known:
            if text == "0x":
                store.put_address(args.address, None, block,
                                  origin="fetched")
                sys.stderr.write(
                    "unknown address or no code: %s\n" % args.address)
                return 2
            if not _is_hex_code(text):
                sys.stderr.write(
                    "eth_getCode returned no code: %s\n" % args.address)
                return 1
            code = bytes.fromhex(text[2:])
            code_id = store.put_code(code)
            store.put_address(args.address, code_id, block,
                              origin="fetched")
        if is_std_proxy(code):
            def get_storage(addr, slot, blk):
                return rpc.call("eth_getStorageAt", [addr, slot, "latest"])

            def get_code(addr, blk):
                return rpc.call("eth_getCode", [addr, "latest"])

            fetch_implementation(store, address, block, get_storage, get_code)
    try:
        store.add_seed(args.address, args.label)
    except KeyError:
        sys.stderr.write("unknown address or no code: %s\n" % args.address)
        return 2
    _print_alerts(recheck_watchlist(store, seed_addresses=[args.address]))
    return 0


def _run_seed_remove(args, store):
    """seed remove: delete one seed, keeping its code and address rows."""
    _check_address(args.address)
    if store.remove_seed(args.address):
        return 0
    sys.stderr.write("not a seed: %s\n" % args.address)
    return 2


def _run_seed_list(args, store):
    for seed in store.seeds():
        sys.stdout.write("%s\t%s\n" % (seed["address"], seed["label"]))
    return 0


def _run_seed_strict(args, store):
    """seed strict <addr> {on,off}: set or clear the seed's strict flag.

    Phase 18: strictness is the operator's decision, never computed.
    A mode other than on/off is a usage error; an address that is not
    a seed gives "not a seed: <address lowercase>" on stderr, exit 2.
    """
    _check_address(args.address)
    if args.mode not in ("on", "off"):
        raise _UsageError("mode must be on or off")
    if store.set_seed_strict(args.address, args.mode == "on"):
        return 0
    sys.stderr.write("not a seed: %s\n" % args.address.lower())
    return 2


def _run_seed_audit(args, store):
    """seed audit: one "<address>\t<label>\t<hits>\t<strict|loose>" per seed.

    Phase 18: the evidence for the operator's strict decision --
    interface_hits at its defaults, and the current strict flag. It
    writes nothing and exits 0 (empty stdout with no seeds).
    """
    strict = set(store.strict_seeds())
    for seed in store.seeds():
        hits = interface_hits(store, seed["code_id"])
        sys.stdout.write(
            "%s\t%s\t%d\t%s\n"
            % (seed["address"], seed["label"], hits,
               "strict" if seed["address"] in strict else "loose")
        )
    sys.stdout.flush()
    return 0


def _run_recheck(args, store):
    """recheck, filtered by --origin (phase 13): without it, every alert."""
    alerts = recheck_watchlist(store, min_score=args.min)
    if args.origin is not None:
        alerts = [a for a in alerts if a["origin"] == args.origin]
    _print_alerts(alerts)
    return 0


def _run_report(args, store):
    """Write the report and print its two file paths, html then json.

    Without matplotlib the write is refused by build_report through
    ChartsUnavailable before any file is created: one stderr line
    naming matplotlib, empty stdout, exit 2, no traceback.
    """
    try:
        html_path, json_path = build_report(store, args.out)
    except ChartsUnavailable as err:
        sys.stderr.write("%s\n" % err)
        return 2
    sys.stdout.write("%s\n%s\n" % (html_path, json_path))
    sys.stdout.flush()
    return 0


def _run_calibrate(args, store):
    """calibrate: evaluate the alert rule over the labelled pairs.

    Phase 18. --labels is read with load_labels and --grid with
    parse_grid before the store is opened (a ValueError there is exit
    2 in main); evaluate runs over the store and one record is printed
    per row in grid order, threshold and recall "%.4f", the counts
    plain integers, benign_total last. A non-empty missing list adds
    one stderr line "missing: <addresses comma-joined>". No rpc call,
    no row written.
    """
    try:
        labels = load_labels(args.labels)
        thresholds = parse_grid(args.grid)
    except ValueError as err:
        sys.stderr.write("%s\n" % err)
        return 2
    result = evaluate(store, labels, thresholds)
    for row in result["rows"]:
        sys.stdout.write(
            "%.4f\t%.4f\t%d\t%d\t%d\t%d\n"
            % (row["threshold"], row["recall"], row["negatives"],
               row["benign"], row["interface_only"],
               result["benign_total"])
        )
    if result["missing"]:
        sys.stderr.write(
            "missing: %s\n" % ",".join(result["missing"]))
    sys.stdout.flush()
    return 0


def _run_dashboard(args):
    """Serve the dashboard of args.db; blocks until Ctrl-C (phase 15).

    It never opens a writable Store: main branches here before the
    Store(args.db) every other subcommand opens, so an old database is
    neither migrated nor switched to WAL by it. A --db path that is not
    an existing file is exit 2 with one stderr line naming the path and
    no file created; an OSError from make_server (a busy port, a host
    it cannot bind) is exit 2 with one stderr line. On success exactly
    one stderr line announces the address, then serve_forever blocks;
    KeyboardInterrupt (Ctrl-C) closes the server and exits 0. stdout
    stays empty.
    """
    if not os.path.isfile(args.db):
        sys.stderr.write("no such database file: %s\n" % args.db)
        return 2
    try:
        # Through the module attribute, so a test that patches
        # ethsc.dashboard.make_server takes effect.
        server = dashboard.make_server(args.db, args.host, args.port,
                                       args.static)
    except OSError as err:
        sys.stderr.write("%s\n" % err)
        return 2
    try:
        sys.stderr.write("serving http://%s:%d/\n" % server.server_address)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    return 0


def _build_parser():
    parser = _Parser(prog="ethsc", description="ETHSmartChecker CLI")
    parser.add_argument("--db", default="ethsc.sqlite")
    sub = parser.add_subparsers(dest="command")

    backfill = sub.add_parser("backfill")
    backfill.add_argument("--from", dest="from_block", type=int, required=True)
    backfill.add_argument("--to", dest="to_block", type=int, required=True)
    backfill.add_argument("--daily-budget", type=int, default=None)
    backfill.add_argument("--max-calls-per-block", type=int, default=None)
    backfill.add_argument("--source", choices=["infura", "publicnode"],
                          default="infura")
    backfill.add_argument("--workers", type=int, default=None)
    backfill.add_argument("--alert-on", choices=["created", "seen", "all"],
                          default="all")
    backfill.add_argument("--min", type=float, default=ALERT_MIN)

    listen = sub.add_parser("listen")
    listen.add_argument("--daily-budget", type=int, default=None)
    listen.add_argument("--max-calls-per-block", type=int, default=None)
    listen.add_argument("--interval", type=float, default=12)
    listen.add_argument("--source", choices=["infura", "publicnode"],
                        default="infura")
    listen.add_argument("--workers", type=int, default=None)
    listen.add_argument("--alert-on", choices=["created", "seen", "all"],
                        default="all")
    listen.add_argument("--min", type=float, default=ALERT_MIN)

    clusters = sub.add_parser("clusters")
    clusters_sub = clusters.add_subparsers(dest="subcommand")
    clusters_top = clusters_sub.add_parser("top")
    clusters_top.add_argument("--n", type=int, default=20)

    cluster = sub.add_parser("cluster")
    cluster.add_argument("address")

    similar = sub.add_parser("similar")
    similar.add_argument("address")
    similar.add_argument("--min", type=float, default=0.8)

    risk = sub.add_parser("risk")
    risk.add_argument(
        "--flag",
        choices=["selfdestruct", "mutable_delegatecall"],
        default=None,
    )

    seed = sub.add_parser("seed")
    seed_sub = seed.add_subparsers(dest="subcommand")
    seed_add = seed_sub.add_parser("add")
    seed_add.add_argument("address")
    seed_add.add_argument("--label", required=True)
    seed_add.add_argument("--fetch", action="store_true")
    seed_remove = seed_sub.add_parser("remove")
    seed_remove.add_argument("address")
    seed_sub.add_parser("list")
    seed_strict = seed_sub.add_parser("strict")
    seed_strict.add_argument("address")
    seed_strict.add_argument("mode")
    seed_sub.add_parser("audit")

    recheck = sub.add_parser("recheck")
    recheck.add_argument("--min", type=float, default=ALERT_MIN)
    recheck.add_argument(
        "--origin",
        choices=["created", "seen", "fetched", "impl", "unknown"],
        default=None,
    )

    calibrate = sub.add_parser("calibrate")
    calibrate.add_argument("--labels", required=True)
    calibrate.add_argument("--grid", default=",".join(
        str(value) for value in
        __import__("ethsc.calibrate", fromlist=["DEFAULT_GRID"]
                   ).DEFAULT_GRID))

    report = sub.add_parser("report")
    report.add_argument("--out", default="ethsc-report")

    dash = sub.add_parser("dashboard")
    dash.add_argument("--host", default="127.0.0.1")
    dash.add_argument("--port", type=int, default=8080)
    dash.add_argument("--static", default="dashboard/dist")

    return parser


def _resolve_source(args):
    """The (prices, code_tag, workers) of --source/--workers, or None.

    Validates first: --workers below 1, and --daily-budget together
    with --source publicnode, are usage errors (None). Returns
    (PRICES, None, workers or 1) for infura and ({}, "latest",
    workers or 8) for publicnode. Only called for listen and backfill.
    """
    workers = args.workers
    if workers is not None and workers < 1:
        raise _UsageError("--workers must be at least 1")
    if args.source == "publicnode" and args.daily_budget is not None:
        raise _UsageError(
            "--daily-budget applies to infura only, not to publicnode"
        )
    if args.source == "publicnode":
        return {}, "latest", (workers or 8)
    return PRICES, None, (workers or 1)


def _check_min(value):
    """Validate a --min alert threshold: a float inside [0, 1]."""
    if not isinstance(value, float) or value < 0.0 or value > 1.0:
        raise _UsageError("--min must be a float in [0, 1]")
    return value


def main(argv=None, rpc=None, sleep=None) -> int:
    """Run one CLI invocation; returns the exit code, never raises."""
    if argv is None:
        argv = sys.argv[1:]
    if sleep is None:
        sleep = time.sleep

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _UsageError as err:
        sys.stderr.write("%s\n" % err)
        return 2
    except SystemExit:
        # --help and --version print and exit(0); keep that exit code.
        return 0

    # The dashboard branches before any Store is opened: it never
    # migrates or re-journals the database.
    if args.command == "dashboard":
        return _run_dashboard(args)

    # The --min threshold is validated before any rpc client is built:
    # a bad value is a usage error with no rpc call at all.
    if args.command in ("listen", "backfill"):
        try:
            _check_min(args.min)
            prices, code_tag, workers = _resolve_source(args)
        except _UsageError as err:
            sys.stderr.write("%s\n" % err)
            return 2
        if rpc is None:
            if args.source == "publicnode":
                rpc = RpcClient(PUBLICNODE_URL, prices={}, max_retries=5)
            else:
                rpc = _chain_rpc()

    store = Store(args.db)
    try:
        if args.command == "backfill":
            return _run_backfill(args, rpc, store, prices, code_tag, workers)
        if args.command == "listen":
            return _run_listen(args, rpc, store, sleep,
                               prices, code_tag, workers)
        if args.command == "clusters":
            if args.subcommand == "top":
                return _run_clusters_top(args, store)
            raise _UsageError("missing clusters subcommand")
        if args.command == "cluster":
            return _run_cluster(args, store)
        if args.command == "similar":
            return _run_similar(args, store)
        if args.command == "risk":
            return _run_risk(args, store)
        if args.command == "seed":
            if args.subcommand == "add":
                return _run_seed_add(args, rpc, store)
            if args.subcommand == "remove":
                return _run_seed_remove(args, store)
            if args.subcommand == "list":
                return _run_seed_list(args, store)
            if args.subcommand == "strict":
                return _run_seed_strict(args, store)
            if args.subcommand == "audit":
                return _run_seed_audit(args, store)
            raise _UsageError("missing seed subcommand")
        if args.command == "recheck":
            return _run_recheck(args, store)
        if args.command == "calibrate":
            return _run_calibrate(args, store)
        if args.command == "report":
            return _run_report(args, store)
        raise _UsageError("missing command")
    except _UsageError as err:
        sys.stderr.write("%s\n" % err)
        return 2
    finally:
        store.close()
