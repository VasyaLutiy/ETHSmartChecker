"""From a block to stored codes: candidate discovery, per-block ingest,
chain following with resume and budgets.

No network here: rpc, get_code and store are injected by the caller. The
module imports neither ethsc.rpc nor ethsc.config -- prices come in as a
parameter, the rpc object duck-types a .call(method, params). Every list
the module returns is fully ordered; results do not depend on insertion
order.
"""

import datetime

from ethsc.cluster import match_watchlist

_HEX_DIGITS = "0123456789abcdefABCDEF"


def discover_candidates(receipts):
    """Sorted distinct lowercase candidate addresses of one block.

    Every contractAddress, every to and every logs[].address of the
    block's receipts is a candidate. None, missing keys, missing logs
    and elements that are not dicts are skipped; from is never a
    candidate. An empty list gives [].
    """
    candidates = set()
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        for key in ("contractAddress", "to"):
            value = receipt.get(key)
            if isinstance(value, str):
                candidates.add(value.lower())
        logs = receipt.get("logs")
        if isinstance(logs, list):
            for log in logs:
                if isinstance(log, dict):
                    value = log.get("address")
                    if isinstance(value, str):
                        candidates.add(value.lower())
    return sorted(candidates)


def _is_hex_code(text):
    """True iff text is a string '0x' + an even number of hex digits."""
    if not isinstance(text, str) or not text.startswith("0x"):
        return False
    body = text[2:]
    if len(body) % 2 != 0:
        return False
    for char in body:
        if char not in _HEX_DIGITS:
            return False
    return True


def _deliver_alerts(on_alerts, alerts):
    """Hand a copy of the alerts, sorted by address, to the sink once."""
    if on_alerts is not None:
        on_alerts(
            sorted(alerts, key=lambda alert: alert["address"])
        )


def ingest_block(block, receipts, get_code, store, max_calls=None,
                 watch=None, on_alerts=None):
    """Fetch and store the codes of one block's candidates.

    Candidates already in the store are skipped (known). Each other one
    costs one get_code(address, block) call until max_calls is reached
    (None: no limit); the rest are deferred and complete is False.
    "0x" stores the address with code_id None (eoas); other 0x-hex text
    goes through put_code/put_address (contracts). A get_code that
    raises, returns a non-string or a string that is not 0x-hex counts
    as failed and does not stop the block (Tolerant Parser).

    Every address stored with code in this call is checked with
    match_watchlist (min_score=watch when watch is not None); each
    Alert gains the key address (dict with exactly address,
    seed_address, label, score). Alerts are returned, not printed,
    sorted by address, and inside one address in match_watchlist order.

    on_alerts, when given, is called exactly once per ingest_block call
    with that alert list, as its single positional argument, on both
    exits: on the normal return and when get_code raised
    KeyboardInterrupt -- there the alerts found so far are handed over
    and the exception then propagates unchanged (it is a BaseException
    and passes through the except Exception around get_code). The list
    may be empty; the call happens anyway.

    Returns a dict with exactly the keys candidates, known, fetched,
    contracts, eoas, failed, deferred, complete, alerts.
    """
    candidates = discover_candidates(receipts)
    stats = {
        "candidates": len(candidates),
        "known": 0,
        "fetched": 0,
        "contracts": 0,
        "eoas": 0,
        "failed": 0,
        "deferred": 0,
        "complete": True,
        "alerts": [],
    }

    deferred = 0
    try:
        for address in candidates:
            if store.has_address(address):
                stats["known"] += 1
                continue
            if max_calls is not None and stats["fetched"] >= max_calls:
                deferred += 1
                continue
            stats["fetched"] += 1
            try:
                text = get_code(address, block)
            except Exception:
                stats["failed"] += 1
                continue
            if not _is_hex_code(text):
                stats["failed"] += 1
                continue
            if text == "0x":
                store.put_address(address, None, block)
                stats["eoas"] += 1
                continue
            code = bytes.fromhex(text[2:])
            code_id = store.put_code(code)
            store.put_address(address, code_id, block)
            stats["contracts"] += 1
            if watch is not None:
                alerts = match_watchlist(store, code, min_score=watch)
            else:
                alerts = match_watchlist(store, code)
            for alert in alerts:
                stats["alerts"].append(
                    {
                        "address": address,
                        "seed_address": alert["seed_address"],
                        "label": alert["label"],
                        "score": alert["score"],
                    }
                )
    except KeyboardInterrupt:
        # The alerts found before the interruption leave the block; the
        # exception continues on its way unchanged.
        _deliver_alerts(on_alerts, stats["alerts"])
        raise
    _deliver_alerts(on_alerts, stats["alerts"])

    stats["deferred"] = deferred
    stats["complete"] = deferred == 0
    stats["alerts"].sort(key=lambda alert: alert["address"])
    return stats


def _resolve_day(day):
    """The ledger day: a string as is, a callable called, None = UTC now."""
    if day is None:
        return datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d"
        )
    if callable(day):
        return day()
    return day


def follow_chain(rpc, store, start=None, stop=None,
                 max_calls_per_block=None, daily_budget=None, day=None,
                 prices=None, on_alerts=None):
    """One pass from progress (or start) up to the head (or stop).

    Polls eth_blockNumber once, then for each block calls
    eth_getBlockReceipts and ingest_block whose get_code is
    rpc.call("eth_getCode", [address, hex(block)]).

    The ledger day comes from the day parameter: a "YYYY-MM-DD" string
    pins every block of the pass, a callable of no arguments is called
    again at every resolution point, and None means today's UTC date.
    The day is resolved once before the eth_blockNumber charge and again
    before each block; every charge of a block -- the budget check
    spent(day) + price <= daily_budget, the max_calls arithmetic and the
    spends -- goes to that block's day. summary["day"] is the last day
    resolved. On_alerts is handed to every ingest_block call unchanged;
    follow_chain itself never calls it.

    Before every RPC call the budget is checked; otherwise the run stops
    cleanly with stopped "budget" and progress at the last complete
    block. Within a block the eth_getCode calls are capped at
    min(max_calls_per_block, (daily_budget - spent) // price), so the
    check happens before the call. Each successful call is charged to
    the ledger with its price (prices None gives {}).

    set_progress runs only after a complete block; an unfinished block
    stops the pass with "budget" (its cap came from the budget) or
    "cap" (from max_calls_per_block); a rerun resumes the same block,
    skipping known addresses. The alerts of every block -- an
    incomplete one included -- are collected in summary["alerts"]. An
    exception from eth_blockNumber or eth_getBlockReceipts propagates
    as is, progress unchanged.

    Returns a dict with exactly the keys blocks, stopped, progress,
    alerts, day.
    """
    if prices is None:
        prices = {}

    def budget_ok(price, current_day):
        return (daily_budget is None
                or store.spent(current_day) + price <= daily_budget)

    day_value = _resolve_day(day)
    summary = {
        "blocks": 0,
        "stopped": None,
        "progress": store.get_progress(),
        "alerts": [],
        "day": day_value,
    }

    if not budget_ok(prices.get("eth_blockNumber", 0), day_value):
        summary["stopped"] = "budget"
        return summary

    head = int(rpc.call("eth_blockNumber", []), 16)
    store.spend(day_value, "eth_blockNumber", prices.get("eth_blockNumber", 0))

    progress = store.get_progress()
    if start is not None:
        first = start
    elif progress is not None:
        first = progress + 1
    else:
        first = head
    last = min(stop, head) if stop is not None else head

    for block in range(first, last + 1):
        day_value = _resolve_day(day)
        summary["day"] = day_value
        receipts_price = prices.get("eth_getBlockReceipts", 0)
        if not budget_ok(receipts_price, day_value):
            summary["stopped"] = "budget"
            break
        receipts = rpc.call("eth_getBlockReceipts", [hex(block)])
        store.spend(day_value, "eth_getBlockReceipts", receipts_price)

        code_price = prices.get("eth_getCode", 0)
        max_calls = max_calls_per_block
        budget_capped = False
        if daily_budget is not None and code_price > 0:
            allowed = (daily_budget - store.spent(day_value)) // code_price
            if allowed < 0:
                allowed = 0
            budget_capped = max_calls is None or allowed < max_calls
            if max_calls is None or allowed < max_calls:
                max_calls = allowed

        def get_code(address, blk, _day=day_value):
            result = rpc.call("eth_getCode", [address, hex(blk)])
            store.spend(_day, "eth_getCode", code_price)
            return result

        stats = ingest_block(block, receipts, get_code, store,
                             max_calls=max_calls, on_alerts=on_alerts)
        summary["alerts"].extend(stats["alerts"])
        if stats["complete"]:
            store.set_progress(block)
            summary["blocks"] += 1
        else:
            summary["stopped"] = "budget" if budget_capped else "cap"
            break

    summary["progress"] = store.get_progress()
    return summary
