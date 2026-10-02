"""From a block to stored codes: candidate discovery, per-block ingest,
chain following with resume and budgets.

No network here: rpc, get_code and store are injected by the caller. The
module imports ethsc.rpc only for the RpcError class (no transport of its
own) and neither ethsc.rpc's client construction nor ethsc.config -- prices
come in as a parameter, the rpc object duck-types a .call(method, params).
Every list the module returns is fully ordered; results do not depend on
insertion order. Origin (phase 13): candidate_origins tells "created"
from "seen" by the receipts alone, never by a trace or a later fetch --
an address made by a factory inside a transaction is "seen", not
"created".

Standard proxies (phase 14): a standard proxy's own bytecode never
matches a watchlist seed (similarity rule 2, unchanged) -- the module
reads the implementation address out of a storage slot instead, via an
injected get_storage, and checks the implementation's bytes. get_storage
is optional (None keeps exactly the phase-9/13 behaviour, no slot ever
read); when it is given, ingest_block runs two more steps after its
candidate loop: resolving implementations (and noting an upgrade when a
known proxy's implementation changes) and the implementation-aware
alerts. Neither step reads a block tag or a transport: the caller's
get_storage(address, slot, block) does that, the same way get_code
already does.
"""

import concurrent.futures
import datetime
import threading

from ethsc.cluster import match_watchlist
from ethsc.evm import is_std_proxy
from ethsc.rpc import RpcError

_HEX_DIGITS = "0123456789abcdefABCDEF"

# Phase 14: the EIP-1967 implementation and beacon storage slots.
IMPL_SLOT = (
    "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
)
BEACON_SLOT = (
    "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"
)


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


def candidate_origins(receipts):
    """{address: "created" | "seen"} for every candidate of discover_candidates.

    The keys are exactly the elements discover_candidates(receipts)
    gives for the same list, under the same tolerance (non-dict
    elements, None, missing keys and missing logs skipped). An address
    is "created" when it is the contractAddress of a receipt of the
    block (contractAddress wins over a log of the same address in the
    same block); every other candidate -- a to or a logs[].address only
    -- is "seen". An empty list gives {}.
    """
    origins = {}
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        to_value = receipt.get("to")
        if isinstance(to_value, str):
            address = to_value.lower()
            if origins.get(address) != "created":
                origins[address] = "seen"
        logs = receipt.get("logs")
        if isinstance(logs, list):
            for log in logs:
                if isinstance(log, dict):
                    value = log.get("address")
                    if isinstance(value, str):
                        address = value.lower()
                        if origins.get(address) != "created":
                            origins[address] = "seen"
        contract_address = receipt.get("contractAddress")
        if isinstance(contract_address, str):
            origins[contract_address.lower()] = "created"
    return origins


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


def slot_address(word):
    """The address a storage slot word carries, or None.

    Pure: a str of "0x" plus 64 hex digits whose first 24 digits are
    zero and whose last 40 are not all zero gives "0x" plus those 40
    digits lowercased. Anything else -- None, a non-string, the zero
    word, a short or malformed string, a non-zero prefix -- gives None;
    never raises (Tolerant Parser).
    """
    if not isinstance(word, str) or len(word) != 66:
        return None
    if word[:2].lower() != "0x":
        return None
    body = word[2:]
    for char in body:
        if char not in _HEX_DIGITS:
            return None
    if body[:24] != "0" * 24:
        return None
    tail = body[24:]
    if tail == "0" * 40:
        return None
    return "0x" + tail.lower()


def _store_implementation_code(store, address, text, block):
    """Store a resolved implementation's code like a fetched candidate.

    Exactly the _store_text shapes -- "0x" as an address without code,
    hex through put_code/put_address -- with origin "impl" and no
    watchlist check (step 3 of ingest_block does that, once, with the
    stored bytes). Not 0x-hex: nothing stored (Tolerant Parser). Returns
    True iff contract code was stored, so the caller can tell a newly
    known implementation apart from one merely marked without code.
    """
    if not _is_hex_code(text):
        return False
    if text == "0x":
        store.put_address(address, None, block, origin="impl")
        return False
    code = bytes.fromhex(text[2:])
    code_id = store.put_code(code)
    store.put_address(address, code_id, block, origin="impl")
    return True


def _fetch_implementation(store, address, block, get_storage, get_code):
    """fetch_implementation's body, also reporting a fresh code fetch.

    Returns (implementation or None, True iff this call stored the
    implementation's code) -- the second value lets ingest_block tell a
    newly known implementation from one already held without a second
    store query. fetch_implementation (the public name) discards it.
    """
    if get_storage is None:
        return None, False
    try:
        word = get_storage(address, IMPL_SLOT, block)
    except Exception:
        return None, False
    implementation = slot_address(word)
    from_impl_slot = implementation is not None
    if implementation is None:
        try:
            word = get_storage(address, BEACON_SLOT, block)
        except Exception:
            return None, False
        implementation = slot_address(word)
    if implementation is None:
        return None, False
    # The resolution is written whether or not the code fetch below
    # succeeds: a later failure must not clear what was just found.
    store.set_implementation(address, implementation)
    if from_impl_slot and not store.has_address(implementation):
        try:
            text = get_code(implementation, block)
        except Exception:
            return implementation, False
        return implementation, _store_implementation_code(
            store, implementation, text, block)
    return implementation, False


def _read_slot(get_storage, address, slot, block):
    """One get_storage call as (word, raised) -- never raises Exception."""
    try:
        return get_storage(address, slot, block), False
    except Exception:
        return None, True


def _resolve_in_pool(store, targets, block, get_storage, get_code, workers):
    """Step 2's _fetch_implementation calls, with the network in a pool.

    targets are the addresses step 2 resolves, in candidate order. The
    reads run in at most ``workers`` threads, in three waves -- every
    IMPL_SLOT read, then the BEACON_SLOT reads of the targets whose
    IMPL_SLOT word was not an address and did not raise, then one
    get_code per distinct implementation the store does not hold yet --
    and every store write happens afterwards in the calling thread, in
    targets order, exactly as the sequential _fetch_implementation does
    it: set_implementation for each found address, the implementation's
    code stored once (the first target that needs it stores it; a later
    one finds it held). Returns address -> (implementation or None,
    fetched_new), the pair _fetch_implementation returns. The only
    difference from the sequential run is under failure: a get_code of
    an implementation that raised is not retried for a second proxy of
    the same implementation in the same block.
    """
    results = {}
    if not targets:
        return results
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        impl_reads = [executor.submit(_read_slot, get_storage, address,
                                      IMPL_SLOT, block)
                      for address in targets]
        impl_words = [future.result() for future in impl_reads]
        beacon_needed = [address for address, (word, raised)
                         in zip(targets, impl_words)
                         if not raised and slot_address(word) is None]
        beacon_reads = [executor.submit(_read_slot, get_storage, address,
                                        BEACON_SLOT, block)
                        for address in beacon_needed]
        beacon_words = dict(zip(beacon_needed,
                                [future.result() for future in beacon_reads]))

        found = []  # (address, implementation or None, from_impl_slot)
        for address, (word, raised) in zip(targets, impl_words):
            if raised:
                found.append((address, None, False))
                continue
            implementation = slot_address(word)
            if implementation is not None:
                found.append((address, implementation, True))
                continue
            word, raised = beacon_words[address]
            found.append((address, None if raised else slot_address(word),
                          False))

        to_fetch = []
        for _, implementation, from_impl_slot in found:
            if (from_impl_slot and implementation not in to_fetch
                    and not store.has_address(implementation)):
                to_fetch.append(implementation)

        def fetch(implementation):
            try:
                return get_code(implementation, block), False
            except Exception:
                return None, True

        code_reads = [executor.submit(fetch, implementation)
                      for implementation in to_fetch]
        texts = dict(zip(to_fetch, [future.result() for future in code_reads]))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    for address, implementation, from_impl_slot in found:
        if implementation is None:
            results[address] = (None, False)
            continue
        store.set_implementation(address, implementation)
        if from_impl_slot and not store.has_address(implementation):
            text, raised = texts.get(implementation, (None, True))
            if raised:
                results[address] = (implementation, False)
                continue
            results[address] = (implementation, _store_implementation_code(
                store, implementation, text, block))
            continue
        results[address] = (implementation, False)
    return results


def fetch_implementation(store, address, block, get_storage, get_code):
    """The implementation address a standard proxy delegates through.

    Reads get_storage(address, IMPL_SLOT, block); when the answer is
    not a usable address and the call did not raise, reads
    get_storage(address, BEACON_SLOT, block) instead. The first address
    found is written with store.set_implementation and returned. When
    it came from IMPL_SLOT and the store does not already hold it, its
    code is fetched with get_code(implementation, block) and stored
    with origin "impl"; a beacon address is only ever stored in the
    column, never fetched (calling the beacon is out of scope). A
    get_storage or get_code call that raises, or an answer
    slot_address rejects, ends the attempt there: nothing already
    stored is cleared, nothing else is stored, and None comes back only
    when no address was found at all -- no exception ever leaves
    (Tolerant Parser). get_storage=None means no read at all.
    """
    return _fetch_implementation(store, address, block, get_storage,
                                 get_code)[0]


def _deliver_alerts(on_alerts, alerts):
    """Hand a copy of the alerts, sorted by address, to the sink once."""
    if on_alerts is not None:
        on_alerts(
            sorted(alerts, key=lambda alert: alert["address"])
        )


def _deliver_upgrades(on_upgrades, upgrades):
    """Hand a copy of the block's upgrade records to the sink once.

    Called after _deliver_alerts, on the normal return and on the
    KeyboardInterrupt path alike, with whatever step 2 had found so far
    (an empty list when the interrupt happened before step 2 ran, since
    it comes after the whole candidate loop).
    """
    if on_upgrades is not None:
        on_upgrades(list(upgrades))


def _store_text(address, text, block, store, watch, stats, origin):
    """Apply one fetched code answer exactly as the sequential loop does.

    Not 0x-hex is failed; "0x" stores the address with code_id None
    (eoas); other code goes through put_code/put_address (contracts) and
    every stored code is checked with match_watchlist, each alert gaining
    the keys address and origin (phase 13: origin is the address's own
    origin, "created" or "seen", from candidate_origins). Runs in the
    calling thread only. Returns the stored code bytes (contracts) or
    None (an eoa or a failed fetch), so the caller can tell a standard
    proxy apart without a second store read (phase 14).
    """
    if not _is_hex_code(text):
        stats["failed"] += 1
        return None
    if text == "0x":
        store.put_address(address, None, block, origin=origin)
        stats["eoas"] += 1
        return None
    code = bytes.fromhex(text[2:])
    code_id = store.put_code(code)
    store.put_address(address, code_id, block, origin=origin)
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
                "origin": origin,
            }
        )
    return code


def ingest_block(block, receipts, get_code, store, max_calls=None,
                 watch=None, on_alerts=None, workers=None, get_storage=None,
                 on_upgrades=None):
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
    Alert gains the keys address and origin (dict with exactly address,
    seed_address, label, score, origin). Alerts are returned, not
    printed, sorted by address, and inside one address in
    match_watchlist order.

    Origin (phase 13): candidate_origins(receipts) is computed once per
    call, and every address this call stores -- contracts and eoas
    alike, in both the sequential and the workers path -- is stored
    with put_address(address, code_id or None, block,
    origin=<its origin>), "created" or "seen".

    on_alerts, when given, is called exactly once per ingest_block call
    with that alert list, as its single positional argument, on both
    exits: on the normal return and when get_code raised
    KeyboardInterrupt -- there the alerts found so far are handed over
    and the exception then propagates unchanged (it is a BaseException
    and passes through the except Exception around get_code). The list
    may be empty; the call happens anyway.

    workers (None or 1) keeps the sequential loop, one get_code at a
    time. With workers K > 1 the decision -- known, fetched (the first
    max_calls unknown candidates), deferred -- is taken in candidate
    order in the calling thread; the get_code calls of the fetched ones
    run in at most K threads at once
    (concurrent.futures.ThreadPoolExecutor); the results are taken in
    candidate order in the calling thread and get exactly the per-address
    handling of the sequential run. Only get_code runs in a worker: the
    store is a sqlite3 connection and is touched only from the calling
    thread, so for the same get_code answers the stats, the alerts and
    their order are those of the sequential run. A KeyboardInterrupt
    leaves through the same path as in the sequential loop -- the pool is
    shut down with cancel_futures=True and wait=False, the alerts found
    so far reach on_alerts once, then the exception propagates.

    Standard proxies (phase 14). get_storage(address, slot, block) is
    optional; None keeps every step below out of the run, exactly the
    phase-9/13 behaviour. When it is given, two steps run after the
    candidate loop above, in candidate order, neither one counted in
    the stats or capped by max_calls:
      step 2 resolves implementations with fetch_implementation (with
      workers K > 1 its slot reads and implementation code fetches run in
      the same kind of K-thread pool as get_code, store writes stay in
      the calling thread in candidate order -- phase 14.1), for
      every candidate this call stored with a standard-proxy code and
      for every already-known candidate that store.implementations()
      held before this call (that snapshot is read once, before the
      candidate loop, so a proxy first seen in this call is never
      double-resolved as both "new" and "known"); a known proxy whose
      stored implementation changes appends {"address", "old", "new",
      "block"} to stats["upgrades"] (a NULL that resolves is silent --
      not an upgrade, a first sighting);
      step 3 adds alerts match_watchlist does not reach by itself: a
      proxy stored in this call whose implementation's code is stored
      (fetched just now or already held) is checked with the
      implementation's bytes, the alert gaining address = the proxy and
      origin = the proxy's own origin; an implementation whose code
      this call fetched is checked with its own bytes, gaining address
      = the implementation and origin "impl". A known proxy (skipped in
      the candidate loop) never gains an alert here, even when step 2
      resolves or re-resolves it -- only a proxy this call actually
      stored gets checked. These alerts join the candidate-loop ones
      before the final sort, so on_alerts and the returned list carry
      both. on_upgrades, when given, is called exactly once per call
      with stats["upgrades"] (possibly []), after on_alerts, on the
      normal return and on the KeyboardInterrupt path alike (there it
      is always [], since step 2 runs only after the candidate loop
      returns without interruption).

    Returns a dict with exactly the keys candidates, known, fetched,
    contracts, eoas, failed, deferred, complete, alerts, upgrades.
    """
    candidates = discover_candidates(receipts)
    origins = candidate_origins(receipts)
    # Read before the candidate loop so a proxy first stored in this
    # call never also counts as "known" in step 2 below.
    known_before = store.implementations() if get_storage is not None else {}
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
        "upgrades": [],
    }

    deferred = 0
    new_std_proxies = set()
    try:
        if workers is not None and workers > 1:
            fetched = []
            for address in candidates:
                if store.has_address(address):
                    stats["known"] += 1
                elif max_calls is not None and len(fetched) >= max_calls:
                    deferred += 1
                else:
                    fetched.append(address)
            stats["fetched"] = len(fetched)
            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=workers)
            try:
                futures = [executor.submit(get_code, address, block)
                           for address in fetched]
                for address, future in zip(fetched, futures):
                    try:
                        text = future.result()
                    except Exception:
                        stats["failed"] += 1
                        continue
                    code = _store_text(address, text, block, store, watch,
                                       stats, origins[address])
                    if code is not None and is_std_proxy(code):
                        new_std_proxies.add(address)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        else:
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
                code = _store_text(address, text, block, store, watch,
                                   stats, origins[address])
                if code is not None and is_std_proxy(code):
                    new_std_proxies.add(address)
    except KeyboardInterrupt:
        # Steps 2 and 3 live after this loop, so an interruption here
        # always leaves stats["upgrades"] at [].
        _deliver_alerts(on_alerts, stats["alerts"])
        _deliver_upgrades(on_upgrades, stats["upgrades"])
        raise

    if get_storage is not None:
        resolved_new = {}       # new-this-call proxy address -> implementation
        new_implementations = set()
        if workers is not None and workers > 1:
            pooled = _resolve_in_pool(
                store,
                [a for a in candidates
                 if a in new_std_proxies or a in known_before],
                block, get_storage, get_code, workers)

            def resolve(address):
                return pooled[address]
        else:
            def resolve(address):
                return _fetch_implementation(
                    store, address, block, get_storage, get_code)
        for address in candidates:
            if address in new_std_proxies:
                implementation, fetched_new = resolve(address)
                if implementation is not None:
                    resolved_new[address] = implementation
                if fetched_new:
                    new_implementations.add(implementation)
            elif address in known_before:
                old = known_before[address]["implementation"]
                implementation, fetched_new = resolve(address)
                if fetched_new:
                    new_implementations.add(implementation)
                if (old is not None and implementation is not None
                        and implementation != old):
                    stats["upgrades"].append(
                        {"address": address, "old": old,
                         "new": implementation, "block": block}
                    )

        for address in sorted(resolved_new):
            implementation = resolved_new[address]
            code = store.code_of(implementation)
            if code is None:
                continue
            for alert in match_watchlist(store, code):
                stats["alerts"].append(
                    {
                        "address": address,
                        "seed_address": alert["seed_address"],
                        "label": alert["label"],
                        "score": alert["score"],
                        "origin": origins[address],
                    }
                )

        for implementation in sorted(new_implementations):
            code = store.code_of(implementation)
            if code is None:
                continue
            for alert in match_watchlist(store, code):
                stats["alerts"].append(
                    {
                        "address": implementation,
                        "seed_address": alert["seed_address"],
                        "label": alert["label"],
                        "score": alert["score"],
                        "origin": "impl",
                    }
                )

    _deliver_alerts(on_alerts, stats["alerts"])
    _deliver_upgrades(on_upgrades, stats["upgrades"])

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
                 prices=None, on_alerts=None, workers=None, code_tag=None,
                 on_upgrades=None):
    """One pass from progress (or start) up to the head (or stop).

    Polls eth_blockNumber once, then for each block calls
    eth_getBlockReceipts and ingest_block whose get_code is
    rpc.call("eth_getCode", [address, tag]) with tag hex(block) when
    code_tag is None, else code_tag verbatim (e.g. "latest": the public
    node refuses eth_getCode on an old block).

    A receipts answer that is not a list (null included) is not an empty
    block: RpcError(None, "eth_getBlockReceipts returned null") is
    raised before that call is charged, before ingest_block and before
    set_progress, so progress stays at the last complete block and a
    rerun asks for the same block again.

    The ledger day comes from the day parameter: a "YYYY-MM-DD" string
    pins every block of the pass, a callable of no arguments is called
    again at every resolution point, and None means today's UTC date.
    The day is resolved once before the eth_blockNumber charge and again
    before each block; every charge of a block -- the budget check
    spent(day) + price <= daily_budget, the max_calls arithmetic and the
    spends -- goes to that block's day. summary["day"] is the last day
    resolved. On_alerts is handed to every ingest_block call unchanged;
    follow_chain itself never calls it.

    workers is handed to every ingest_block call unchanged. With workers
    K > 1 the get_code handed down does the rpc call only -- it must not
    touch the store, it runs in a worker -- and its successful calls are
    counted under a lock and charged to the ledger from the calling
    thread once ingest_block returns or raises (try/finally), one spend
    per successful call, so the ledger totals equal the sequential run.
    With workers None or 1 each successful call is charged inside
    get_code as before.

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

    Standard proxies (phase 14). Every ingest_block call gets
    get_storage(address, slot, blk) = rpc.call("eth_getStorageAt",
    [address, slot, tag]), tag following the eth_getCode rule above,
    and on_upgrades unchanged. summary["upgrades"] is the concatenation
    of the blocks' upgrades in block order, the incomplete block
    included. Before each read the check is spent(day) +
    price(eth_getStorageAt) + price(eth_getCode) <= daily_budget -- one
    read and the code fetch it may trigger -- and when it fails
    get_storage returns None without a call: the implementation stays
    unresolved, and slot reads never set stopped or cap a block. Each
    successful read is charged price(eth_getStorageAt); the
    implementation's eth_getCode goes through this block's get_code
    (above) and is charged exactly like a candidate's, workers included
    -- the step 2/3 reads run in the calling thread regardless of
    workers (allowed to run in the pool, not required), so the existing
    get_code charging already covers them.

    Returns a dict with exactly the keys blocks, stopped, progress,
    alerts, day, upgrades.
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
        "upgrades": [],
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
        block_day = day_value
        receipts_price = prices.get("eth_getBlockReceipts", 0)
        if not budget_ok(receipts_price, block_day):
            summary["stopped"] = "budget"
            break
        receipts = rpc.call("eth_getBlockReceipts", [hex(block)])
        if not isinstance(receipts, list):
            raise RpcError(None, "eth_getBlockReceipts returned null")
        store.spend(block_day, "eth_getBlockReceipts", receipts_price)

        code_price = prices.get("eth_getCode", 0)
        max_calls = max_calls_per_block
        budget_capped = False
        if daily_budget is not None and code_price > 0:
            allowed = (daily_budget - store.spent(block_day)) // code_price
            if allowed < 0:
                allowed = 0
            budget_capped = max_calls is None or allowed < max_calls
            if max_calls is None or allowed < max_calls:
                max_calls = allowed

        if workers is not None and workers > 1:
            counter = [0]
            counter_lock = threading.Lock()

            def get_code(address, blk):
                result = rpc.call(
                    "eth_getCode",
                    [address,
                     hex(blk) if code_tag is None else code_tag])
                with counter_lock:
                    counter[0] += 1
                return result

            charge_after = True
        else:
            def get_code(address, blk, _day=block_day):
                result = rpc.call(
                    "eth_getCode",
                    [address,
                     hex(blk) if code_tag is None else code_tag])
                store.spend(_day, "eth_getCode", code_price)
                return result

            charge_after = False

        storage_price = prices.get("eth_getStorageAt", 0)

        if workers is not None and workers > 1:
            # Pool path (phase 14.1): the reads run in worker threads, and
            # the sqlite store must not be touched there. The budget is
            # checked against the day's spend read once here plus what
            # this block has called so far; the reads are charged after
            # ingest_block, like the pooled eth_getCode calls.
            storage_counter = [0]
            spent_before = store.spent(block_day)

            def get_storage(address, slot, blk):
                if daily_budget is not None:
                    with counter_lock:
                        projected = (spent_before
                                     + counter[0] * code_price
                                     + storage_counter[0] * storage_price)
                    if projected + storage_price + code_price > daily_budget:
                        return None
                result = rpc.call(
                    "eth_getStorageAt",
                    [address, slot,
                     hex(blk) if code_tag is None else code_tag])
                with counter_lock:
                    storage_counter[0] += 1
                return result
        else:
            storage_counter = None

            def get_storage(address, slot, blk, _day=block_day):
                # One read plus the code fetch it may trigger -- a soft
                # reservation, not a second check before that fetch.
                if (daily_budget is not None
                        and store.spent(_day) + storage_price + code_price
                        > daily_budget):
                    return None
                result = rpc.call(
                    "eth_getStorageAt",
                    [address, slot,
                     hex(blk) if code_tag is None else code_tag])
                store.spend(_day, "eth_getStorageAt", storage_price)
                return result

        try:
            stats = ingest_block(block, receipts, get_code, store,
                                 max_calls=max_calls, on_alerts=on_alerts,
                                 workers=workers, get_storage=get_storage,
                                 on_upgrades=on_upgrades)
        finally:
            if charge_after:
                for _ in range(counter[0]):
                    store.spend(block_day, "eth_getCode", code_price)
                for _ in range(storage_counter[0]):
                    store.spend(block_day, "eth_getStorageAt", storage_price)
        summary["alerts"].extend(stats["alerts"])
        summary["upgrades"].extend(stats["upgrades"])
        if stats["complete"]:
            store.set_progress(block)
            summary["blocks"] += 1
        else:
            summary["stopped"] = "budget" if budget_capped else "cap"
            break

    summary["progress"] = store.get_progress()
    return summary
