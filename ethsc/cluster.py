"""Clusters and similarity search over the store.

L0 identical code, L1 identical skeleton, proxy by target (EIP-1167
clones only), eip7702 per delegation target, L2 similarity over stored
fingerprints, and the security watchlist check for a new code. Pure
orchestration: the module does no I/O of its own -- it reads the Store
only through its public methods (fingerprints, code_of, addresses_of,
seeds) and never imports sqlite3, urllib, http or socket. Since phase 11
the three similarity searches score stored Fingerprint dicts with
score_fingerprints: no stored code is loaded and similarity() over raw
bytes is not called here -- with one exception since phase 18, the
strict-seed gate of the watchlist: for a seed marked strict (and only
for one), code_similarity is read over the two codes via code_by_id
after a pair has already passed the Similarity Score threshold.

Every list returned is fully ordered; the result does not depend on the
order in which codes or addresses were inserted into the store. Origin
(phase 13): recheck_watchlist reads store.origins() to label its
alerts; it never computes an origin itself, and match_watchlist is
unchanged -- its alerts carry no address and no origin. Implementation
(phase 14): a standard proxy whose implementation is resolved and
whose implementation's code is stored is scored by that code's
fingerprint, in build_clusters, find_similar and recheck_watchlist
alike; match_watchlist itself does not change -- a seed added on a
proxy already carries the implementation's code_id (Store.add_seed),
and ingest hands match_watchlist the implementation's bytes on a
proxy's behalf, so this module never has to decide which bytes a proxy
means. Phase 18: match_watchlist and recheck_watchlist alert at
ALERT_MIN (0.75) by default, and a strict seed (store.strict_seeds(),
read once per call) demands, on top of a passing score, code_similarity
of the two codes >= CODE_MIN -- a store with no strict seed is read
exactly as before, code_by_id never called. find_similar is a search,
not an alert: it keeps 0.8 and no strict gate.
"""

from typing import List, Optional, Tuple

from ethsc.fingerprint import (
    ALERT_MIN,
    CODE_MIN,
    code_similarity,
    fingerprint,
    score_fingerprints,
)

# Sort rank of the cluster levels: L0 first, then L1, then proxy, then
# eip7702, then impl last -- the implementation clusters are an
# addition on top of the others, never ahead of them.
_LEVEL_RANK = {"L0": 0, "L1": 1, "proxy": 2, "eip7702": 3, "impl": 4}


def build_clusters(store) -> List[dict]:
    """Build every Cluster visible in the store.

    L0: one cluster per non-proxy code_id with >= 2 addresses.
    L1: one cluster per skeleton_hash shared by >= 2 distinct non-proxy
    code_id; its members are all addresses of all those codes.
    proxy: one cluster per (kind, target) pair of EIP-1167 clones with
    >= 2 addresses over all codes carrying that pair.
    eip7702: one cluster per (kind, target) pair of EIP-7702 delegations
    with >= 2 addresses; a 7702 designator is a delegating EOA, a
    wallet, not a deployed contract, so it is kept apart from the
    contract proxy clusters.
    impl (phase 14): one cluster per implementation address of
    store.implementations() with >= 2 standard-proxy addresses pointing
    at it; the members are those proxy addresses, the implementation
    address itself is never a member (it is an ordinary address, in its
    own L0/L1 cluster if any). A beacon proxy counts under its beacon
    address the same way -- the column holds whichever ingest found. A
    standard proxy still enters its own L0/L1 cluster as before, so it
    may be a member of both an L0 (or L1) and an impl cluster.

    A proxy code (fingerprint proxy not None) enters only its proxy or
    eip7702 cluster, never L0 or L1.

    Each cluster is a dict with exactly the keys level, key and members
    (sorted lowercase addresses); key is the code_id, the skeleton_hash,
    "<kind>:<target>" or the implementation address. The list is sorted
    by member count descending, then level (L0, L1, proxy, eip7702,
    impl), then key ascending. An empty store gives [].
    """
    fps = store.fingerprints()

    l0_members = {}       # code_id -> set of addresses
    l1_groups = {}        # skeleton_hash -> list of code_id
    l1_members = {}       # skeleton_hash -> set of addresses
    proxy_members = {}    # (kind, target) -> set of addresses, eip1167 only
    eip7702_members = {}  # (kind, target) -> set of addresses

    for fp in fps:
        code_id = fp["code_id"]
        addresses = store.addresses_of(code_id)
        if not addresses:
            continue
        if fp["proxy"] is not None:
            pair = (fp["proxy"]["kind"], fp["proxy"]["target"])
            if pair[0] == "eip7702":
                eip7702_members.setdefault(pair, set()).update(addresses)
            else:
                proxy_members.setdefault(pair, set()).update(addresses)
        else:
            l0_members[code_id] = set(addresses)
            key = fp["skeleton_hash"]
            l1_groups.setdefault(key, []).append(code_id)
            l1_members.setdefault(key, set()).update(addresses)

    clusters = []

    for code_id, members in sorted(l0_members.items()):
        if len(members) >= 2:
            clusters.append(
                {"level": "L0", "key": code_id, "members": sorted(members)}
            )

    for skeleton_hash, code_ids in sorted(l1_groups.items()):
        if len(code_ids) >= 2:
            clusters.append(
                {
                    "level": "L1",
                    "key": skeleton_hash,
                    "members": sorted(l1_members[skeleton_hash]),
                }
            )

    for pair, members in sorted(proxy_members.items()):
        if len(members) >= 2:
            clusters.append(
                {
                    "level": "proxy",
                    "key": "%s:%s" % (pair[0], pair[1]),
                    "members": sorted(members),
                }
            )

    for pair, members in sorted(eip7702_members.items()):
        if len(members) >= 2:
            clusters.append(
                {
                    "level": "eip7702",
                    "key": "%s:%s" % (pair[0], pair[1]),
                    "members": sorted(members),
                }
            )

    impl_members = {}  # implementation address -> set of proxy addresses
    for address, info in store.implementations().items():
        implementation = info["implementation"]
        if implementation is not None:
            impl_members.setdefault(implementation, set()).add(address)

    for implementation, members in sorted(impl_members.items()):
        if len(members) >= 2:
            clusters.append(
                {
                    "level": "impl",
                    "key": implementation,
                    "members": sorted(members),
                }
            )

    clusters.sort(
        key=lambda c: (
            -len(c["members"]),
            _LEVEL_RANK[c["level"]],
            c["key"],
        )
    )
    return clusters


def _code_addresses(store) -> dict:
    """code_id -> sorted list of addresses, from the store's public API."""
    mapping = {}
    for fp in store.fingerprints():
        mapping[fp["code_id"]] = store.addresses_of(fp["code_id"])
    return mapping


def _proxy_code_ids(store, fps_by_id) -> dict:
    """address -> its own code_id, for every stored standard-proxy address.

    Built once from fps_by_id and store.addresses_of, so an address's
    own code_id is known even when store.implementations() carries no
    resolved implementation for it (phase 9 fallback).
    """
    from_fp = {}
    for fp in fps_by_id.values():
        if fp["std_proxy"]:
            for addr in store.addresses_of(fp["code_id"]):
                from_fp[addr] = fp["code_id"]
    return from_fp


def _effective_code_id(address, impls, own_code_id) -> Optional[str]:
    """The code_id to score address by (phase 14).

    A standard proxy whose implementations() entry carries a code_id
    (its implementation is resolved and its code is stored) is scored
    by that code_id instead of its own, on both sides of a comparison.
    Anything else -- a non-proxy, an unresolved proxy, one whose
    implementation's code is not stored -- keeps own_code_id, so an
    unresolved standard proxy still scores 0.0 against everything
    (similarity rule 2, phase 9).
    """
    info = impls.get(address)
    if info is not None and info["code_id"] is not None:
        return info["code_id"]
    return own_code_id


def find_similar(
    store, address: str, min_score: float = 0.8
) -> List[Tuple[str, float]]:
    """Every other stored address with code similar to address's code.

    Full scan over stored fingerprints: the query code is fingerprinted
    once and every non-proxy element of store.fingerprints() is scored
    with score_fingerprints -- no stored code is loaded. The score is
    fanned out to that code's addresses. The queried address itself is
    excluded; the other addresses of the same code come back with 1.0.
    Returns (address, score) tuples sorted by score descending, then
    address ascending. An unknown address, or one without code, gives
    []. Scores are the floats from score_fingerprints, not rounded.

    find_similar is a search, not an alert: its default min_score stays
    0.8 and no strict gate applies to it (phase 18).

    Through the implementation (phase 14): a standard proxy -- as the
    query or as a stored address -- is scored by the fingerprint of
    its implementations() code_id instead of its own, when one is
    there; an unresolved standard proxy keeps its own (std_proxy)
    fingerprint and so still scores 0.0 against everything, on both
    sides. Reads the store through code_of(), fingerprints(),
    addresses_of() and implementations() only.
    """
    query = address.lower()
    code = store.code_of(query)
    if code is None:
        return []
    own_fp = fingerprint(code)

    fps_by_id = {fp["code_id"]: fp for fp in store.fingerprints()}
    impls = store.implementations()
    proxy_code_id = _proxy_code_ids(store, fps_by_id)

    query_code_id = _effective_code_id(
        query, impls, proxy_code_id.get(query, own_fp["code_id"]))
    query_fp = fps_by_id.get(query_code_id, own_fp)

    result = []
    for fp in fps_by_id.values():
        if fp["std_proxy"]:
            continue  # scored per proxy address below, not by code_id
        score = score_fingerprints(query_fp, fp)
        if score >= min_score:
            for addr in store.addresses_of(fp["code_id"]):
                if addr != query:
                    result.append((addr, score))

    for proxy_address, own_code_id in proxy_code_id.items():
        if proxy_address == query:
            continue
        fp = fps_by_id.get(
            _effective_code_id(proxy_address, impls, own_code_id))
        if fp is None:
            continue
        score = score_fingerprints(query_fp, fp)
        if score >= min_score:
            result.append((proxy_address, score))

    result.sort(key=lambda item: (-item[1], item[0]))
    return result


def interface_hits(
    store, code_id: str, min_score: float = ALERT_MIN,
    code_min: float = CODE_MIN,
) -> int:
    """How many stored codes share an interface without sharing the code.

    The number of code_ids of store.fingerprints(), other than code_id
    itself, whose score_fingerprints against code_id's fingerprint is
    >= min_score and whose code_similarity with code_id's code is
    < code_min. It is the evidence seed audit prints for the
    operator's strict decision; nothing applies it automatically.

    0 when code_id has no element in store.fingerprints() (an unknown
    code_id). code_by_id is called for code_id itself and for the
    code_ids that reach min_score, never for the others. Stored
    fingerprints as they are: no implementation fan-out. Never raises.
    """
    fps = {fp["code_id"]: fp for fp in store.fingerprints()}
    own_fp = fps.get(code_id)
    if own_fp is None:
        return 0
    own_code = store.code_by_id(code_id)
    if own_code is None:
        return 0
    hits = 0
    for other_id, fp in fps.items():
        if other_id == code_id:
            continue
        score = score_fingerprints(own_fp, fp)
        if score < min_score:
            continue
        other_code = store.code_by_id(other_id)
        if other_code is None:
            continue
        if code_similarity(own_code, other_code) < code_min:
            hits += 1
    return hits


def match_watchlist(store, code: bytes, min_score: float = ALERT_MIN) -> List[dict]:
    """Every seed whose code is similar enough to the new code.

    Returns Alert dicts with exactly the keys seed_address, label and
    score, one per seed with score_fingerprints(code fingerprint, seed
    fingerprint) >= min_score, sorted by score descending, then
    seed_address ascending. The incoming code is fingerprinted once (a
    None fingerprint for empty code still scores, 0.0 against every
    seed, so min_score=0.0 keeps giving one 0.0 alert per seed); each
    seed is scored against its element of store.fingerprints(), and a
    seed whose code_id has no fingerprint is skipped. No stored code is
    loaded. No seeds or garbage bytes give [] (or the matching list);
    the function never raises.

    Phase 14 changes nothing here: it scores exactly the bytes it is
    given. A seed added on a standard proxy already carries its
    implementation's code_id (Store.add_seed), and ingest hands this
    function the implementation's bytes on a proxy's behalf -- a
    proxy's own bytes still score 0.0 against everything.

    Phase 18: the default min_score is ALERT_MIN (0.75). A strict seed
    (its address in store.strict_seeds(), read once per call) alerts
    only when, besides score >= min_score, code_similarity of the given
    code and the seed's code (store.code_by_id of the seed's code_id)
    is >= CODE_MIN; the alert still carries the Similarity Score, not
    the code similarity. code_by_id is called only for a strict seed
    that reached min_score -- a store with no strict seed is read
    exactly as before (no code_by_id). A strict seed whose code_by_id
    is None alerts on nothing.
    """
    code_fp = fingerprint(code)
    fps = {}  # code_id -> stored Fingerprint dict
    for fp in store.fingerprints():
        fps[fp["code_id"]] = fp

    strict = set(store.strict_seeds())
    strict_code_cache = {}  # code_id -> code bytes or None

    result = []
    for seed in store.seeds():
        seed_fp = fps.get(seed["code_id"])
        if seed_fp is None:
            continue
        score = score_fingerprints(code_fp, seed_fp)
        if score >= min_score and seed["address"] in strict:
            if seed["code_id"] not in strict_code_cache:
                strict_code_cache[seed["code_id"]] = \
                    store.code_by_id(seed["code_id"])
            seed_code = strict_code_cache[seed["code_id"]]
            if seed_code is None:
                continue
            if code_similarity(code, seed_code) < CODE_MIN:
                continue
        if score >= min_score:
            result.append(
                {
                    "seed_address": seed["address"],
                    "label": seed["label"],
                    "score": score,
                }
            )
    result.sort(key=lambda alert: (-alert["score"], alert["seed_address"]))
    return result


def recheck_watchlist(
    store, min_score: float = ALERT_MIN, seed_addresses=None
) -> List[dict]:
    """Every stored address whose code matches a watchlist seed.

    The whole database is rechecked against the seeds, without the
    network, so a copy of a scam already in the store becomes visible:
    match_watchlist only sees a code arriving after the seed was added.

    Each Alert has exactly the keys address (the matching stored
    address, lowercase), seed_address, label, score (the float from
    score_fingerprints, unrounded) and origin (phase 13: that address's
    origin, from store.origins(), read once per call -- never once per
    alert -- "unknown" for a row stored before phase 13). Every
    (code_id, seed) pair is
    scored by score_fingerprints over two elements of
    store.fingerprints() -- no code is loaded -- and fanned out to that
    code's addresses. A seed never alerts on itself -- the single pair
    address == seed_address is dropped -- while every other address of
    the seed's own code alerts with 1.0. A seed whose code_id has no
    fingerprint is skipped. Addresses stored without code are never
    checked. seed_addresses restricts the check to those seeds (any
    case accepted, unknown ones simply match nothing); None means every
    seed of store.seeds().

    Through the implementation (phase 14): a stored standard proxy
    whose implementations() entry carries a code_id is grouped and
    scored by that code_id instead of its own -- so the proxies of one
    implementation are scored once per seed, exactly like a shared
    code_id -- while an unresolved standard proxy stays grouped under
    its own (std_proxy) code_id and so still alerts on nothing and
    draws no alert through its bytes (similarity rule 2, phase 9). A
    seed on a proxy already carries the implementation's code_id
    (Store.add_seed), so it is scored like any other seed of that
    code_id: against the implementation address and every other proxy
    resolved to it.

    Returns [] with no seeds, on an empty store or when seed_addresses
    names nothing known. The list is sorted by address ascending, then
    score descending, then seed_address ascending; it does not depend
    on insertion order, and two calls on the same store give equal
    lists. Reads the store through seeds(), fingerprints(),
    addresses_of(), origins() and implementations() only.

    Phase 18: the default min_score is ALERT_MIN (0.75), and a strict
    seed (store.strict_seeds(), read once per call) keeps a (code_id,
    seed) pair only when code_similarity of the two codes
    (store.code_by_id of the effective code_id and of the seed's
    code_id) is >= CODE_MIN, as in match_watchlist; the alerts carry
    the Similarity Score. code_by_id is read only for pairs of a strict
    seed that reached min_score, so with no strict seed the reads stay
    exactly as before; a None code on either side lets the pair alert
    on nothing.
    """
    seeds = store.seeds()
    if seed_addresses is not None:
        wanted = set(address.lower() for address in seed_addresses)
        seeds = [seed for seed in seeds if seed["address"] in wanted]

    fps = {}  # code_id -> stored Fingerprint dict
    for fp in store.fingerprints():
        fps[fp["code_id"]] = fp
    origins = store.origins()  # read once per call, not once per alert
    impls = store.implementations()
    proxy_code_id = _proxy_code_ids(store, fps)

    # Group every address by the code_id it is effectively scored
    # with: non-proxy addresses by their own code_id (fanned via
    # addresses_of, as before); standard-proxy addresses by their
    # implementation's code_id when resolved, else their own -- so the
    # proxies sharing one implementation are scored once per seed.
    groups = {}  # effective code_id -> list of addresses
    for code_id, fp in fps.items():
        if not fp["std_proxy"]:
            groups.setdefault(code_id, []).extend(
                store.addresses_of(code_id))
    for proxy_address, own_code_id in proxy_code_id.items():
        effective = _effective_code_id(proxy_address, impls, own_code_id)
        groups.setdefault(effective, []).append(proxy_address)

    strict = set(store.strict_seeds())
    strict_code_cache = {}  # code_id -> code bytes or None

    alerts = []
    for seed in seeds:
        seed_fp = fps.get(seed["code_id"])
        if seed_fp is None:
            continue
        seed_is_strict = seed["address"] in strict
        seed_code = None
        if seed_is_strict:
            if seed["code_id"] not in strict_code_cache:
                strict_code_cache[seed["code_id"]] = \
                    store.code_by_id(seed["code_id"])
            seed_code = strict_code_cache[seed["code_id"]]
        for code_id, addresses in groups.items():
            fp = fps.get(code_id)
            if fp is None:
                continue
            score = score_fingerprints(seed_fp, fp)
            if score < min_score:
                continue
            if seed_is_strict:
                if seed_code is None:
                    continue
                if code_id not in strict_code_cache:
                    strict_code_cache[code_id] = store.code_by_id(code_id)
                cand_code = strict_code_cache[code_id]
                if cand_code is None:
                    continue
                if code_similarity(seed_code, cand_code) < CODE_MIN:
                    continue
            for addr in addresses:
                if addr == seed["address"]:
                    continue
                alerts.append(
                    {
                        "address": addr,
                        "seed_address": seed["address"],
                        "label": seed["label"],
                        "score": score,
                        "origin": origins.get(addr, "unknown"),
                    }
                )
    alerts.sort(
        key=lambda alert: (
            alert["address"],
            -alert["score"],
            alert["seed_address"],
        )
    )
    return alerts
