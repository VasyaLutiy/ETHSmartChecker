"""Command line interface of ETHSmartChecker.

python -m ethsc with subcommands over one SQLite db: listen, backfill,
clusters top, cluster, similar, seed add, seed list. Output is plain
text, one record per line, tab-separated, fully ordered; alerts from
ingest print as lines starting "ALERT". Exit codes: 0 success, 1 a
failed RPC call, 2 usage error, 3 a budget or cap stop that left work
undone. main() never raises SystemExit: argparse failures are caught
and returned as the int code 2, so tests calling main() directly see
the same code sys.exit(main()) produces in __main__.

No network in this module: urllib, http and socket stay in ethsc.rpc.
The rpc object is injected (tests) or built here from ethsc.rpc only;
the store is used through its public methods, never its private
attributes.
"""

import argparse
import re
import sys
import time

from ethsc.cluster import build_clusters, find_similar
from ethsc.config import PRICES
from ethsc.ingest import follow_chain
from ethsc.rpc import RpcClient, RpcError, infura_url
from ethsc.store import Store

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


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


def _print_alerts(alerts):
    for alert in alerts:
        sys.stdout.write(
            "ALERT\t%s\t%s\t%s\t%.4f\n"
            % (
                alert["address"],
                alert["seed_address"],
                alert["label"],
                alert["score"],
            )
        )


def _follow(rpc, store, start=None, stop=None, daily_budget=None,
            max_calls=None):
    """One follow_chain call with the CLI's error and exit-code policy."""
    try:
        summary = follow_chain(
            rpc,
            store,
            start=start,
            stop=stop,
            max_calls_per_block=max_calls,
            daily_budget=daily_budget,
            prices=PRICES,
        )
    except RpcError as err:
        sys.stderr.write(str(err) + "\n")
        return 1
    _print_alerts(summary["alerts"])
    return 0 if summary["stopped"] is None else 3


def _run_backfill(args, rpc, store):
    return _follow(
        rpc,
        store,
        start=args.from_block,
        stop=args.to_block,
        daily_budget=args.daily_budget,
        max_calls=args.max_calls_per_block,
    )


def _run_listen(args, rpc, store, sleep):
    while True:
        code = _follow(
            rpc,
            store,
            daily_budget=args.daily_budget,
            max_calls=args.max_calls_per_block,
        )
        if code != 0:
            return code
        try:
            sleep(args.interval)
        except KeyboardInterrupt:
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
    for cluster in build_clusters(store):
        if query in cluster["members"]:
            sys.stdout.write(
                "%s\t%s\t%s\n"
                % (cluster["level"], cluster["key"], ",".join(
                    cluster["members"]))
            )
    return 0


def _run_similar(args, store):
    _check_address(args.address)
    for address, score in find_similar(
        store, args.address, min_score=args.min
    ):
        sys.stdout.write("%s\t%.4f\n" % (address, score))
    return 0


def _run_seed_add(args, store):
    _check_address(args.address)
    try:
        store.add_seed(args.address, args.label)
    except KeyError:
        sys.stderr.write("unknown address or no code: %s\n" % args.address)
        return 2
    return 0


def _run_seed_list(args, store):
    for seed in store.seeds():
        sys.stdout.write("%s\t%s\n" % (seed["address"], seed["label"]))
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

    listen = sub.add_parser("listen")
    listen.add_argument("--daily-budget", type=int, default=None)
    listen.add_argument("--max-calls-per-block", type=int, default=None)
    listen.add_argument("--interval", type=float, default=12)

    clusters = sub.add_parser("clusters")
    clusters_sub = clusters.add_subparsers(dest="subcommand")
    clusters_top = clusters_sub.add_parser("top")
    clusters_top.add_argument("--n", type=int, default=20)

    cluster = sub.add_parser("cluster")
    cluster.add_argument("address")

    similar = sub.add_parser("similar")
    similar.add_argument("address")
    similar.add_argument("--min", type=float, default=0.8)

    seed = sub.add_parser("seed")
    seed_sub = seed.add_subparsers(dest="subcommand")
    seed_add = seed_sub.add_parser("add")
    seed_add.add_argument("address")
    seed_add.add_argument("--label", required=True)
    seed_sub.add_parser("list")

    return parser


def main(argv=None, rpc=None, sleep=None) -> int:
    """Run one CLI invocation; returns the exit code, never raises."""
    if argv is None:
        argv = sys.argv[1:]
    if rpc is None:
        rpc = RpcClient(infura_url())
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

    store = Store(args.db)
    try:
        if args.command == "backfill":
            return _run_backfill(args, rpc, store)
        if args.command == "listen":
            return _run_listen(args, rpc, store, sleep)
        if args.command == "clusters":
            if args.subcommand == "top":
                return _run_clusters_top(args, store)
            raise _UsageError("missing clusters subcommand")
        if args.command == "cluster":
            return _run_cluster(args, store)
        if args.command == "similar":
            return _run_similar(args, store)
        if args.command == "seed":
            if args.subcommand == "add":
                return _run_seed_add(args, store)
            if args.subcommand == "list":
                return _run_seed_list(args, store)
            raise _UsageError("missing seed subcommand")
        raise _UsageError("missing command")
    except _UsageError as err:
        sys.stderr.write("%s\n" % err)
        return 2
    finally:
        store.close()
