"""One offline report over the whole database.

Every number lives here and is computed by the standard library alone:
no matplotlib, no numpy, no network, no sqlite3. The store is read only
through its public methods (counts, ledger_days, fingerprints,
code_by_id, addresses_of, seeds); clusters come from
ethsc.cluster.build_clusters, alerts from
ethsc.cluster.recheck_watchlist, risk flags from ethsc.evm.risk_flags.
The drawing layer ethsc.charts is imported lazily inside build_report
and only there; an ImportError there becomes ChartsUnavailable, whose
message names matplotlib.

Two calls of collect() on the same store give equal structures.
"""

import html
import importlib
import json
import math
from typing import List, Tuple

from ethsc.cluster import build_clusters, recheck_watchlist
from ethsc.evm import disassemble, risk_flags

FEATURES = (
    "bytecode_size",
    "opcode_count",
    "selector_count",
    "address_count",
    "l1_family_size",
    "is_proxy",
)

RISK_FLAGS = ("selfdestruct", "mutable_delegatecall")

SIZE_EDGES = [0, 256, 1024, 4096, 8192, 16384, 24576]
SELECTOR_EDGES = [0, 1, 2, 4, 8, 16, 32, 64]
CLUSTER_EDGES = [2, 3, 4, 5, 9, 17, 33, 65]

CHART_KEYS = (
    "cluster_sizes",
    "top_clusters",
    "code_sizes",
    "selector_counts",
    "spearman",
)


class ChartsUnavailable(Exception):
    """Raised by build_report when the drawing layer cannot be imported."""


# -- small numeric helpers -------------------------------------------------


def _histogram(values, edges):
    """Counts of values in the buckets delimited by the fixed edges.

    A value falls into the last bucket whose edge does not exceed it;
    the last bucket is open on the right. len(counts) == len(edges).
    """
    counts = [0] * len(edges)
    for value in values:
        index = 0
        for i, edge in enumerate(edges):
            if value >= edge:
                index = i
        counts[index] += 1
    return counts


def _median(values) -> float:
    """The true median, always a float; 0.0 on no values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    middle = n // 2
    if n % 2 == 1:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _share(numerator: int, denominator: int) -> float:
    """numerator / denominator as a float; exactly 0.0 on a zero base."""
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def _distribution(values, edges) -> dict:
    """min / median / max / histogram of one numeric feature."""
    return {
        "min": min(values) if values else 0,
        "median": _median(values),
        "max": max(values) if values else 0,
        "histogram": {"edges": list(edges),
                      "counts": _histogram(values, edges)},
    }


# -- Spearman rank correlation ---------------------------------------------


def _ranks(values) -> List[float]:
    """Average ranks, 1-based: a group of equal values shares the mean
    of its positions. Ties are the point of this implementation; the
    tie-blind shortcut 1 - 6*sum(d^2)/(n(n^2-1)) is wrong on this data
    and is not used anywhere here.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    n = len(values)
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def _pearson(xs, ys):
    """Pearson's correlation of two equal-length series, or None when
    one of them has zero variance."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0.0 or var_y == 0.0:
        return None
    return cov / math.sqrt(var_x * var_y)


def spearman(rows) -> dict:
    """Rank correlation matrix of the columns of rows.

    rows is a list of equal-length tuples; one tuple per observation,
    one column per feature. Ties are ranked by their average rank and
    the coefficient is Pearson's on those ranks. A feature whose values
    are all equal gives None in its whole row and column, the diagonal
    included; fewer than two rows gives None everywhere. Returns a dict
    with the keys features, n and matrix; the matrix is square,
    symmetric, with 1.0 on a non-degenerate diagonal.
    """
    rows = list(rows)
    n = len(rows)
    ncols = len(rows[0]) if rows else 0
    if ncols == len(FEATURES):
        names = list(FEATURES)
    else:
        names = ["f%d" % i for i in range(ncols)]
    if n < 2 or ncols == 0:
        return {"features": names, "n": n,
                "matrix": [[None] * ncols for _ in range(ncols)]}

    columns = [[float(row[i]) for row in rows] for i in range(ncols)]
    rank_columns = [_ranks(column) for column in columns]
    degenerate = [all(v == columns[i][0] for v in columns[i])
                  for i in range(ncols)]

    matrix = [[None] * ncols for _ in range(ncols)]
    for i in range(ncols):
        for j in range(i, ncols):
            if degenerate[i] or degenerate[j]:
                continue
            value = _pearson(rank_columns[i], rank_columns[j])
            matrix[i][j] = value
            matrix[j][i] = value
    return {"features": names, "n": n, "matrix": matrix}


# -- Collect Report Data -----------------------------------------------------


def collect(store) -> dict:
    """Every number of the report, and not one chart.

    Returns a dict with exactly the nine keys summary, levels,
    skeletons, clusters, codes, ledger, alerts, spearman, risk, of
    ints, floats, strings, lists and dicts only. Reads the store
    through counts(), ledger_days(), fingerprints(), code_by_id(),
    addresses_of() and seeds() only, and calls build_clusters,
    recheck_watchlist and risk_flags for the cluster, alert and risk
    sections.
    """
    summary = store.counts()
    fps = store.fingerprints()

    addr_by_code = {}
    for fp in fps:
        addr_by_code[fp["code_id"]] = store.addresses_of(fp["code_id"])

    clusters = build_clusters(store)

    # levels: the proxy level counts eip1167 clones only; the eip7702
    # delegations are a level of their own.
    levels = {}
    for level in ("L0", "L1", "proxy", "eip7702"):
        members = set()
        count = 0
        for cluster in clusters:
            if cluster["level"] == level:
                count += 1
                members.update(cluster["members"])
        addresses = len(members)
        levels[level] = {
            "clusters": count,
            "addresses": addresses,
            "share": _share(addresses, summary["addresses_with_code"]),
        }
    proxy_codes = sum(1 for fp in fps
                      if fp["proxy"] is not None
                      and fp["proxy"]["kind"] == "eip1167")
    eip7702_codes = sum(1 for fp in fps
                        if fp["proxy"] is not None
                        and fp["proxy"]["kind"] == "eip7702")
    levels["proxy_codes"] = proxy_codes
    levels["proxy_code_share"] = _share(proxy_codes, summary["codes"])
    levels["eip7702_codes"] = eip7702_codes
    levels["eip7702_code_share"] = _share(eip7702_codes, summary["codes"])

    # skeletons, over non-proxy codes only
    non_proxy = [fp for fp in fps if fp["proxy"] is None]
    skeleton_counts = {}
    for fp in non_proxy:
        key = fp["skeleton_hash"]
        skeleton_counts[key] = skeleton_counts.get(key, 0) + 1
    unique_fps = [fp for fp in non_proxy
                  if skeleton_counts[fp["skeleton_hash"]] == 1]
    non_proxy_addresses = sum(
        len(addr_by_code[fp["code_id"]]) for fp in non_proxy)
    unique_addresses = sum(
        len(addr_by_code[fp["code_id"]]) for fp in unique_fps)
    skeletons = {
        "non_proxy_codes": len(non_proxy),
        "unique_codes": len(unique_fps),
        "unique_share": _share(len(unique_fps), len(non_proxy)),
        "non_proxy_addresses": non_proxy_addresses,
        "unique_addresses": unique_addresses,
        "unique_address_share": _share(unique_addresses,
                                       non_proxy_addresses),
    }

    # clusters: at most 20 top entries in build_clusters order, a
    # histogram over every cluster
    top = [{"level": cluster["level"], "key": cluster["key"],
            "size": len(cluster["members"])}
           for cluster in clusters[:20]]
    sizes = [len(cluster["members"]) for cluster in clusters]
    clusters_section = {
        "top": top,
        "histogram": {"edges": list(CLUSTER_EDGES),
                      "counts": _histogram(sizes, CLUSTER_EDGES)},
    }

    # code distributions, over every code
    code_sizes = [fp["size"] for fp in fps]
    selector_counts = [len(fp["selectors"]) for fp in fps]
    codes_section = {
        "size": _distribution(code_sizes, SIZE_EDGES),
        "selectors": _distribution(selector_counts, SELECTOR_EDGES),
    }

    # ledger
    days = store.ledger_days()
    ledger = {"days": days,
              "total": sum(day["credits"] for day in days)}

    # alerts, folded per seed
    alerts_list = recheck_watchlist(store)
    by_seed = {}
    for alert in alerts_list:
        entry = by_seed.get(alert["seed_address"])
        if entry is None:
            by_seed[alert["seed_address"]] = {
                "address": alert["seed_address"],
                "label": alert["label"],
                "count": 1,
            }
        else:
            entry["count"] += 1
    alerts_section = {
        "seeds": [by_seed[key] for key in sorted(by_seed)],
        "total": len(alerts_list),
    }

    # spearman, one row per code, features in the fixed order
    family = {}
    for fp in fps:
        key = fp["skeleton_hash"]
        family[key] = family.get(key, 0) + 1
    rows = []
    for fp in fps:
        code = store.code_by_id(fp["code_id"])
        rows.append((
            fp["size"],
            len(disassemble(code)) if code is not None else 0,
            len(fp["selectors"]),
            len(addr_by_code[fp["code_id"]]),
            family[fp["skeleton_hash"]],
            1 if fp["proxy"] is not None else 0,
        ))
    if len(rows) < 2:
        matrix = [[None] * len(FEATURES) for _ in range(len(FEATURES))]
        spearman_section = {"features": list(FEATURES), "n": len(rows),
                            "matrix": matrix}
    else:
        result = spearman(rows)
        spearman_section = {"features": list(FEATURES), "n": result["n"],
                            "matrix": result["matrix"]}

    # risk flags, over every code and every address with code
    codes_with_flag = dict((name, 0) for name in RISK_FLAGS)
    addrs_with_flag = dict((name, 0) for name in RISK_FLAGS)
    for fp in fps:
        code = store.code_by_id(fp["code_id"])
        flags = risk_flags(code) if code is not None else \
            {"selfdestruct": False, "mutable_delegatecall": False}
        addresses = len(addr_by_code[fp["code_id"]])
        for name in RISK_FLAGS:
            if flags[name]:
                codes_with_flag[name] += 1
                addrs_with_flag[name] += addresses
    risk = {}
    for name in RISK_FLAGS:
        risk[name] = {
            "codes": codes_with_flag[name],
            "code_share": _share(codes_with_flag[name],
                                 summary["codes"]),
            "addresses": addrs_with_flag[name],
            "address_share": _share(addrs_with_flag[name],
                                    summary["addresses_with_code"]),
        }

    return {
        "summary": summary,
        "levels": levels,
        "skeletons": skeletons,
        "clusters": clusters_section,
        "codes": codes_section,
        "ledger": ledger,
        "alerts": alerts_section,
        "spearman": spearman_section,
        "risk": risk,
    }


# -- Render Report -----------------------------------------------------------


def _fmt(value) -> str:
    """One cell of the page: floats at four places, None as n/a."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return "%.4f" % value
    return str(value)


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _strip_svg(text: str) -> str:
    """The SVG verbatim, minus its XML declaration and DOCTYPE."""
    kept = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("<?xml") or stripped.startswith("<!DOCTYPE"):
            continue
        kept.append(line)
    return "\n".join(kept)


def render_html(data, svgs) -> str:
    """One self-contained page: no script, no link, no img, no http.

    The five SVGs are inlined verbatim, each stripped of its XML
    declaration and its DOCTYPE, so nothing is ever fetched. Every
    float is printed "%.4f"; every None cell of the Spearman matrix is
    the literal n/a, never an empty cell. Two calls on the same data
    give equal strings.
    """
    parts = []
    parts.append("<!DOCTYPE html>\n<html>\n<head>")
    parts.append("<meta charset=\"utf-8\">")
    parts.append("<title>ETHSmartChecker report</title>")
    parts.append("</head>\n<body>\n")
    parts.append("<h1>ETHSmartChecker report</h1>\n")

    summary = data["summary"]
    parts.append("<h2>Summary</h2>\n<table>\n")
    for key in sorted(summary):
        parts.append("<tr><th>%s</th><td>%s</td></tr>\n"
                     % (_esc(key), _fmt(summary[key])))
    parts.append("</table>\n")

    levels = data["levels"]
    parts.append("<h2>Cluster levels</h2>\n<table>\n")
    parts.append("<tr><th>level</th><th>clusters</th><th>addresses</th>"
                 "<th>share</th></tr>\n")
    for level in ("L0", "L1", "proxy", "eip7702"):
        entry = levels[level]
        parts.append("<tr><th>%s</th><td>%s</td><td>%s</td><td>%s</td></tr>\n"
                     % (_esc(level), _fmt(entry["clusters"]),
                        _fmt(entry["addresses"]), _fmt(entry["share"])))
    parts.append("</table>\n")
    parts.append("<p>proxy codes: %s (share %s)</p>\n"
                 % (_fmt(levels["proxy_codes"]),
                    _fmt(levels["proxy_code_share"])))
    parts.append("<p>eip7702 codes: %s (share %s)</p>\n"
                 % (_fmt(levels["eip7702_codes"]),
                    _fmt(levels["eip7702_code_share"])))

    skeletons = data["skeletons"]
    parts.append("<h2>Unique skeletons</h2>\n<table>\n")
    for key in sorted(skeletons):
        parts.append("<tr><th>%s</th><td>%s</td></tr>\n"
                     % (_esc(key), _fmt(skeletons[key])))
    parts.append("</table>\n")

    clusters = data["clusters"]
    parts.append("<h2>Top clusters</h2>\n<table>\n")
    parts.append("<tr><th>level</th><th>key</th><th>size</th></tr>\n")
    for entry in clusters["top"]:
        parts.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>\n"
                     % (_esc(entry["level"]), _esc(entry["key"]),
                        _fmt(entry["size"])))
    parts.append("</table>\n")
    hist = clusters["histogram"]
    parts.append("<p>cluster size histogram over edges %s: %s</p>\n"
                 % (_esc(hist["edges"]), _esc(hist["counts"])))

    codes = data["codes"]
    parts.append("<h2>Code distributions</h2>\n")
    for name in ("size", "selectors"):
        entry = codes[name]
        hist = entry["histogram"]
        parts.append("<h3>%s</h3>\n<table>\n" % _esc(name))
        for key in ("min", "median", "max"):
            parts.append("<tr><th>%s</th><td>%s</td></tr>\n"
                         % (_esc(key), _fmt(entry[key])))
        parts.append("<tr><th>histogram</th><td>%s over %s</td></tr>\n"
                     % (_esc(hist["counts"]), _esc(hist["edges"])))
        parts.append("</table>\n")

    ledger = data["ledger"]
    parts.append("<h2>Credit ledger</h2>\n<table>\n")
    parts.append("<tr><th>day</th><th>credits</th></tr>\n")
    for day in ledger["days"]:
        parts.append("<tr><td>%s</td><td>%s</td></tr>\n"
                     % (_esc(day["day"]), _fmt(day["credits"])))
    parts.append("<tr><th>total</th><td>%s</td></tr>\n"
                 % _fmt(ledger["total"]))
    parts.append("</table>\n")

    alerts = data["alerts"]
    parts.append("<h2>Watchlist alerts</h2>\n<table>\n")
    parts.append("<tr><th>seed</th><th>label</th><th>alerts</th></tr>\n")
    for seed in alerts["seeds"]:
        parts.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>\n"
                     % (_esc(seed["address"]), _esc(seed["label"]),
                        _fmt(seed["count"])))
    parts.append("<tr><th>total</th><td></td><td>%s</td></tr>\n"
                 % _fmt(alerts["total"]))
    parts.append("</table>\n")

    sp = data["spearman"]
    parts.append("<h2>Spearman rank correlation</h2>\n")
    parts.append("<p>n = %s</p>\n" % _fmt(sp["n"]))
    parts.append("<table>\n<tr><th></th>")
    for name in sp["features"]:
        parts.append("<th>%s</th>" % _esc(name))
    parts.append("</tr>\n")
    for i, name in enumerate(sp["features"]):
        parts.append("<tr><th>%s</th>" % _esc(name))
        for j in range(len(sp["features"])):
            parts.append("<td>%s</td>" % _fmt(sp["matrix"][i][j]))
        parts.append("</tr>\n")
    parts.append("</table>\n")
    parts.append("<p>A cell n/a means the coefficient is undefined "
                 "(a feature with zero variance), not zero.</p>\n")

    risk = data["risk"]
    parts.append("<h2>Risk flags</h2>\n<table>\n")
    parts.append("<tr><th>flag</th><th>codes</th><th>code share</th>"
                 "<th>addresses</th><th>address share</th></tr>\n")
    for name in RISK_FLAGS:
        entry = risk[name]
        parts.append(
            "<tr><th>%s</th><td>%s</td><td>%s</td><td>%s</td>"
            "<td>%s</td></tr>\n"
            % (_esc(name), _fmt(entry["codes"]),
               _fmt(entry["code_share"]), _fmt(entry["addresses"]),
               _fmt(entry["address_share"])))
    parts.append("</table>\n")

    for key in CHART_KEYS:
        parts.append("<h2>%s</h2>\n" % _esc(key))
        parts.append(_strip_svg(svgs[key]))
        parts.append("\n")

    parts.append("</body></html>\n")
    return "".join(parts)


def build_report(store, prefix: str, charts=None) -> Tuple[str, str]:
    """Write prefix + ".html" and prefix + ".json", return their paths.

    The drawing layer is resolved first: with charts None, ethsc.charts
    is imported here, and an ImportError becomes ChartsUnavailable
    (its message names matplotlib) before anything is written, so a
    missing matplotlib never leaves a half-written report behind. A
    given charts mapping must have exactly the CHART_KEYS keys. The
    JSON is the collected data with sort_keys True, indent 2 and a
    trailing newline.
    """
    data = collect(store)
    if charts is None:
        try:
            charts_module = importlib.import_module("ethsc.charts")
        except ImportError as error:
            raise ChartsUnavailable(
                "matplotlib is required to render the report charts; "
                "install matplotlib to use the report subcommand"
            ) from error
        svgs = charts_module.render_charts(data)
    else:
        if set(charts.keys()) != set(CHART_KEYS):
            raise ValueError("charts must have exactly the keys %s"
                             % (", ".join(CHART_KEYS)))
        svgs = charts

    page = render_html(data, svgs)
    html_path = prefix + ".html"
    json_path = prefix + ".json"
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(page)
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, sort_keys=True, indent=2)
        handle.write("\n")
    return (html_path, json_path)
