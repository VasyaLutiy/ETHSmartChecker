"""Drawing layer for the ETHSmartChecker report.

The only module of the package allowed a third-party import: matplotlib,
nothing else (numpy arrives as its dependency but is never imported here).
This module computes nothing: every number it draws comes from the Report
Data structure that ethsc.report.collect built with the standard library.

Determinism is bought with exactly four settings (docs/TASK_PHASE7_2.md
2.2): matplotlib.use("Agg") before pyplot, a fixed svg.hashsalt,
svg.fonttype "none" (labels stay real <text> elements, no embedded font),
and savefig(format="svg", metadata={"Date": None}). Every figure is closed.
"""

import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import rcParams  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

rcParams["svg.hashsalt"] = "ethsc-charts-fixed-hashing-salt"
rcParams["svg.fonttype"] = "none"

CHART_KEYS = ("cluster_sizes", "top_clusters", "code_sizes",
              "selector_counts", "spearman")

_LEVEL_ORDER = {"L0": 0, "L1": 1, "proxy": 2}
_LEVEL_COLORS = {"L0": "#4477aa", "L1": "#ee7733", "proxy": "#228833"}
_HIST_COLOR = "#4477aa"
_EDGE_COLOR = "#1f1f1f"
_UNDEFINED_FILL = "#bfbfbf"  # flat grey, clearly not the near-white zero
_UNDEFINED_HATCH = "///"
_UNDEFINED_EDGE = "#404040"


def _svg(fig):
    try:
        buf = io.BytesIO()
        fig.savefig(buf, format="svg", metadata={"Date": None},
                    bbox_inches="tight")
        return buf.getvalue().decode("utf-8")
    finally:
        plt.close(fig)


def _strip_xml_decoration(text):
    """Remove the XML declaration and DOCTYPE so nothing external is referenced."""
    out = text
    if out.startswith("<?xml"):
        end = out.find("?>")
        if end != -1:
            out = out[end + 2:]
    idx = out.find("<!DOCTYPE")
    if idx != -1:
        end = out.find(">", idx)
        if end != -1:
            out = out[:idx] + out[end + 1:]
    return out.lstrip()


def _hist_axes(edges, counts, title, xlabel, log_y=False):
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    n = len(counts)
    centers = []
    lefts = []
    widths = []
    for i in range(n):
        lo = edges[i]
        hi = edges[i + 1] if i + 1 < len(edges) else edges[i] * 1.2 + 1
        lefts.append(lo)
        widths.append(max(hi - lo, 1.0))
        centers.append((lo + hi) / 2.0)
    # A log axis with no positive value makes matplotlib warn to stderr
    # ("Data has no positive values, and therefore cannot be log-scaled"),
    # and the report contract is an empty stderr on an empty base too.
    # The log axis is what the chart is for on real data; when nothing is
    # positive it is dropped for the drawing only, never by filtering the
    # warning.
    use_log = bool(log_y) and any(c > 0 for c in counts)
    ax.bar(lefts, counts, width=widths, align="edge", log=use_log,
           color=_HIST_COLOR, edgecolor=_EDGE_COLOR, linewidth=0.6)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    if use_log:
        ax.set_ylabel("count (log)")
    else:
        ax.set_ylabel("clusters" if log_y else "codes")
    ax.set_xticks(edges)
    return fig, ax


def _render_cluster_sizes(data):
    hist = data["clusters"]["histogram"]
    fig, ax = _hist_axes(hist["edges"], hist["counts"],
                         "Cluster sizes", "members", log_y=True)
    return _svg(fig)


def _render_top_clusters(data):
    top = data["clusters"]["top"]
    fig, ax = plt.subplots(figsize=(6.0, 0.4 + 0.35 * max(len(top), 1)))
    if top:
        entries = list(reversed(top))
        labels = []
        colors = []
        for c in entries:
            key = c["key"]
            if isinstance(key, str) and len(key) > 10:
                short = key[:10]
            else:
                short = str(key)
            labels.append("%s %s" % (c["level"], short))
            colors.append(_LEVEL_COLORS.get(c["level"], "#888888"))
        positions = list(range(len(entries)))
        sizes = [c["size"] for c in entries]
        ax.barh(positions, sizes, color=colors, edgecolor=_EDGE_COLOR,
                linewidth=0.5)
        ax.set_yticks(positions)
        ax.set_yticklabels(labels)
        ax.set_xlabel("addresses")
        ax.set_title("Largest clusters")
        ax.set_ylim(-0.6, len(entries) - 0.4)
    else:
        ax.text(0.5, 0.5, "no clusters", ha="center", va="center")
        ax.set_axis_off()
    return _svg(fig)


def _render_code_sizes(data):
    hist = data["codes"]["size"]["histogram"]
    fig, ax = _hist_axes(hist["edges"], hist["counts"],
                         "Bytecode size", "bytes")
    return _svg(fig)


def _render_selector_counts(data):
    hist = data["codes"]["selectors"]["histogram"]
    fig, ax = _hist_axes(hist["edges"], hist["counts"],
                         "Selector counts", "selectors")
    return _svg(fig)


def _render_spearman(data):
    sp = data["spearman"]
    feats = list(sp["features"])
    matrix = sp["matrix"]
    n = len(feats)
    fig, ax = plt.subplots(figsize=(5.6, 4.8))
    ax.set_xlim(-0.5, n - 0.5)
    ax.set_ylim(n - 0.5, -0.5)
    ax.set_xticks(list(range(n)))
    ax.set_yticks(list(range(n)))
    ax.set_xticklabels(feats, rotation=45, ha="right")
    ax.set_yticklabels(feats)
    ax.set_title("Spearman rank correlation")
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([i - 0.5 for i in range(1, n)], minor=True)
    ax.set_yticks([i - 0.5 for i in range(1, n)], minor=True)
    ax.grid(which="minor", color="#cccccc", linewidth=0.5)
    ax.tick_params(which="minor", length=0)

    for i in range(n):
        for j in range(n):
            value = matrix[i][j]
            if value is None:
                ax.add_patch(plt.Rectangle(
                    (j - 0.5, i - 0.5), 1.0, 1.0,
                    facecolor=_UNDEFINED_FILL,
                    edgecolor=_UNDEFINED_EDGE, linewidth=0.5,
                    hatch=_UNDEFINED_HATCH))
                ax.text(j, i, "n/a", ha="center", va="center",
                        fontsize=8, color="#202020")
            else:
                # diverging scale, fixed to [-1, 1]
                t = max(-1.0, min(1.0, float(value)))
                if t >= 0.0:
                    color = (1.0 - t, 1.0 - 0.6 * t, 1.0 - 0.6 * t)
                else:
                    color = (1.0 + 0.6 * t, 1.0 + 0.6 * t, 1.0 + t)
                ax.add_patch(plt.Rectangle(
                    (j - 0.5, i - 0.5), 1.0, 1.0,
                    facecolor=color, edgecolor="#ffffff", linewidth=0.5))
                ax.text(j, i, "%.4f" % float(value), ha="center",
                        va="center", fontsize=7,
                        color="#000000" if abs(t) < 0.6 else "#ffffff")
    if n > 0:
        legend_handles = [
            Patch(facecolor="#3b4cc0", label="-1"),
            Patch(facecolor="#ffffff", edgecolor="#888888", label="0"),
            Patch(facecolor="#b40426", label="1"),
            Patch(facecolor=_UNDEFINED_FILL, edgecolor=_UNDEFINED_EDGE,
                  hatch=_UNDEFINED_HATCH, label="n/a (undefined)"),
        ]
        ax.legend(handles=legend_handles, loc="center left",
                  bbox_to_anchor=(1.02, 0.5), frameon=False, fontsize=8)
    return _svg(fig)


def render_charts(data):
    """Draw the five report charts; every number comes from `data`."""
    charts = {
        "cluster_sizes": _strip_xml_decoration(_render_cluster_sizes(data)),
        "top_clusters": _strip_xml_decoration(_render_top_clusters(data)),
        "code_sizes": _strip_xml_decoration(_render_code_sizes(data)),
        "selector_counts": _strip_xml_decoration(
            _render_selector_counts(data)),
        "spearman": _strip_xml_decoration(_render_spearman(data)),
    }
    if set(charts) != set(CHART_KEYS):
        raise ValueError("chart keys mismatch")
    return charts

