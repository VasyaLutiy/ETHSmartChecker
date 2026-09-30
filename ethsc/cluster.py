"""Clusters and similarity search over the store.

L0 identical code, L1 identical skeleton, proxy by target (EIP-1167
clones only), eip7702 per delegation target, L2 similarity over stored
fingerprints, and the security watchlist check for a new code. Pure
orchestration: the module does no I/O of its own -- it reads the Store
only through its public methods (fingerprints, code_of, addresses_of,
seeds) and never imports sqlite3, urllib, http or socket. Since phase 11
the three similarity searches score stored Fingerprint dicts with
score_fingerprints: no stored code is loaded and similarity() over raw
bytes is not called here.

Every list returned is fully ordered; the result does not depend on the
order in which codes or addresses were inserted into the store.
"""

from typing import List, Tuple

from ethsc.fingerprint import fingerprint, score_fingerprints

# Sort rank of the cluster levels: L0 first, then L1, then proxy, then
# eip7702 last -- the 7702 delegating EOAs must not drown out the
# contract clusters.
_LEVEL_RANK = {"L0": 0, "L1": 1, "proxy": 2, "eip7702": 3}


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

    A proxy code (fingerprint proxy not None) enters only its proxy or
    eip7702 cluster, never L0 or L1.

    Each cluster is a dict with exactly the keys level, key and members
    (sorted lowercase addresses); key is the code_id, the skeleton_hash
    or "<kind>:<target>". The list is sorted by member count descending,
    then level (L0, L1, proxy, eip7702), then key ascending. An empty
    store gives [].
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


def find_similar(
    store, address: str, min_score: float = 0.8
) -> List[Tuple[str, float]]:
    """Every other stored address with code similar to address's code.

    Full scan over stored fingerprints: the query code is fingerprinted
    once and every element of store.fingerprints() is scored with
    score_fingerprints -- no stored code is loaded. The score is fanned
    out to that code's addresses. The queried address itself is
    excluded; the other addresses of the same code come back with 1.0.
    Returns (address, score) tuples sorted by score descending, then
    address ascending. An unknown address, or one without code, gives
    []. Scores are the floats from score_fingerprints, not rounded.
    """
    query = address.lower()
    code = store.code_of(query)
    if code is None:
        return []
    query_fp = fingerprint(code)

    result = []
    for fp in store.fingerprints():
        score = score_fingerprints(query_fp, fp)
        if score < min_score:
            continue
        for addr in store.addresses_of(fp["code_id"]):
            if addr != query:
                result.append((addr, score))
    result.sort(key=lambda item: (-item[1], item[0]))
    return result


def match_watchlist(store, code: bytes, min_score: float = 0.8) -> List[dict]:
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
    """
    code_fp = fingerprint(code)
    fps = {}  # code_id -> stored Fingerprint dict
    for fp in store.fingerprints():
        fps[fp["code_id"]] = fp

    result = []
    for seed in store.seeds():
        seed_fp = fps.get(seed["code_id"])
        if seed_fp is None:
            continue
        score = score_fingerprints(code_fp, seed_fp)
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
    store, min_score: float = 0.8, seed_addresses=None
) -> List[dict]:
    """Every stored address whose code matches a watchlist seed.

    The whole database is rechecked against the seeds, without the
    network, so a copy of a scam already in the store becomes visible:
    match_watchlist only sees a code arriving after the seed was added.

    Each Alert has exactly the keys address (the matching stored
    address, lowercase), seed_address, label and score (the float from
    score_fingerprints, unrounded). Every (code_id, seed) pair is
    scored by score_fingerprints over two elements of
    store.fingerprints() -- no code is loaded -- and fanned out to that
    code's addresses. A seed never alerts on itself -- the single pair
    address == seed_address is dropped -- while every other address of
    the seed's own code alerts with 1.0. A seed whose code_id has no
    fingerprint is skipped. Addresses stored without code are never
    checked. seed_addresses restricts the check to those seeds (any
    case accepted, unknown ones simply match nothing); None means every
    seed of store.seeds().

    Returns [] with no seeds, on an empty store or when seed_addresses
    names nothing known. The list is sorted by address ascending, then
    score descending, then seed_address ascending; it does not depend
    on insertion order, and two calls on the same store give equal
    lists. Reads the store through seeds(), fingerprints() and
    addresses_of() only.
    """
    seeds = store.seeds()
    if seed_addresses is not None:
        wanted = set(address.lower() for address in seed_addresses)
        seeds = [seed for seed in seeds if seed["address"] in wanted]

    fps = {}  # code_id -> stored Fingerprint dict
    for fp in store.fingerprints():
        fps[fp["code_id"]] = fp

    alerts = []
    for seed in seeds:
        seed_fp = fps.get(seed["code_id"])
        if seed_fp is None:
            continue
        for code_id, fp in fps.items():
            score = score_fingerprints(seed_fp, fp)
            if score < min_score:
                continue
            for addr in store.addresses_of(code_id):
                if addr == seed["address"]:
                    continue
                alerts.append(
                    {
                        "address": addr,
                        "seed_address": seed["address"],
                        "label": seed["label"],
                        "score": score,
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
