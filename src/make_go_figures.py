"""Render publication figures from the frozen GO diagnostic outputs.

The plotting layer is intentionally separate from the model layer.  It reads
only the frozen run CSV files and the project graph, then writes high
resolution PNG files and editable PDF counterparts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle
from PIL import Image


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = PROJECT / "runs" / "corridor_2024" / "go_diagnostic_20260907"
DEFAULT_DATA = PROJECT / "data" / "corridor_2024"
DEFAULT_OUT = PROJECT / "outputs" / "ieeeaccess_corridor_redesign" / "go_version_20260907" / "figures"
DEFAULT_MAP = PROJECT / "data" / "geography" / "ne_110m_admin_0_countries.geojson"


# A restrained, colour-blind-safe palette.  The red accent is reserved for
# selected or adverse outcomes; it is not used for ordinary structure.
INK = "#243447"
NAVY = "#1D3F5E"
BLUE = "#3B6F91"
TEAL = "#2A8C82"
ORANGE = "#D58A2B"
RED = "#C43B3B"
MUTED = "#718096"
GREY = "#AAB7C4"
GRID = "#D9E2E8"
PALE = "#F3F6F8"
PALE_BLUE = "#E7EFF4"
PALE_RED = "#F8E8E8"
PANEL_TITLE_X = 0.12


def style() -> None:
    """Set one figure-wide style for the full manuscript."""

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.2,
            "axes.titlesize": 9.4,
            "axes.titleweight": "normal",
            "axes.labelsize": 8.2,
            "axes.labelcolor": INK,
            "axes.edgecolor": INK,
            "axes.linewidth": 0.7,
            "legend.fontsize": 7.2,
            "xtick.labelsize": 7.4,
            "ytick.labelsize": 7.4,
            "xtick.color": INK,
            "ytick.color": INK,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.unicode_minus": True,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def save(fig: plt.Figure, path: Path) -> None:
    """Save both the submission PNG and an editable vector PDF."""

    path.parent.mkdir(parents=True, exist_ok=True)
    png_path = path.with_suffix(".png")
    pdf_path = path.with_suffix(".pdf")
    fig.savefig(
        png_path,
        dpi=900,
        bbox_inches="tight",
        pad_inches=0.04,
        facecolor="white",
    )
    with Image.open(png_path) as image:
        # PNG stores pixels per metre as an integer.  This small calibration
        # offset keeps the recorded metadata at or above the 900 dpi gate.
        image.save(png_path, dpi=(900.02, 900.02), optimize=True)
    fig.savefig(
        pdf_path,
        bbox_inches="tight",
        pad_inches=0.04,
        facecolor="white",
    )
    plt.close(fig)


def prepare_axis(ax: plt.Axes, grid: bool = False) -> None:
    """Apply quiet axes and optional horizontal guide lines."""

    ax.spines["left"].set_color(INK)
    ax.spines["bottom"].set_color(INK)
    ax.spines["left"].set_linewidth(0.7)
    ax.spines["bottom"].set_linewidth(0.7)
    ax.tick_params(length=3, width=0.65, pad=2.5)
    if grid:
        ax.grid(axis="y", color=GRID, linewidth=0.55, alpha=0.85)
        ax.set_axisbelow(True)


def panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.105,
        1.045,
        f"({label})",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=9.5,
        fontweight="bold",
        color=INK,
    )


def _stage_box(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    accent: str,
    title: str,
    body: str,
) -> None:
    """Draw a compact, flat workflow stage."""

    ax.add_patch(
        Rectangle(
            (x, y),
            width,
            height,
            facecolor="white",
            edgecolor=GRID,
            linewidth=0.8,
            zorder=1,
        )
    )
    ax.add_patch(
        Rectangle(
            (x, y + height - 0.055),
            width,
            0.055,
            facecolor=accent,
            edgecolor="none",
            zorder=2,
        )
    )
    ax.text(
        x + 0.018,
        y + height - 0.105,
        title,
        ha="left",
        va="top",
        fontsize=7.8,
        fontweight="bold",
        color=INK,
    )
    ax.text(
        x + 0.018,
        y + height - 0.19,
        body,
        ha="left",
        va="top",
        fontsize=7.0,
        color=MUTED,
        linespacing=1.35,
    )


def lineage(out: Path) -> None:
    """Draw the data to decision workflow without decorative empty space."""

    fig = plt.figure(figsize=(7.15, 3.35), constrained_layout=True)
    grid = fig.add_gridspec(2, 1, height_ratios=[1.15, 1.0], hspace=0.02)

    ax = fig.add_subplot(grid[0])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(
        0.005,
        0.98,
        "DATA TO DECISION",
        ha="left",
        va="top",
        fontsize=8.2,
        fontweight="bold",
        color=INK,
    )

    stages = [
        (
            0.02,
            BLUE,
            "PUBLIC DATA",
            "TYNDP 2024 | EHO\nEHB and Eurostat\ncontext",
        ),
        (
            0.265,
            TEAL,
            "EVIDENCE FILTER",
            "endpoints | years\ncapacity | compatibility\nexclusions",
        ),
        (
            0.51,
            ORANGE,
            "PROJECT GRAPH",
            "terminal to H2 node\nedge to demand\nsink",
        ),
        (
            0.755,
            RED,
            "ROBUST MILP",
            "12 scenarios\nfixed interface\nbudget",
        ),
    ]
    for x, accent, title, body in stages:
        _stage_box(ax, x, 0.28, 0.205, 0.46, accent, title, body)

    for x in (0.229, 0.474, 0.719):
        ax.add_patch(
            FancyArrowPatch(
                (x, 0.66),
                (x + 0.032, 0.66),
                arrowstyle="-|>",
                mutation_scale=10,
                linewidth=0.85,
                color=MUTED,
                zorder=3,
            )
        )

    ax2 = fig.add_subplot(grid[1])
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.axis("off")
    ax2.text(
        0.005,
        0.90,
        "AUDIT OUTPUTS",
        ha="left",
        va="top",
        fontsize=8.2,
        fontweight="bold",
        color=INK,
    )
    outputs = [
        "flows and demand cut",
        "capacity utilisation",
        "selected interfaces",
        "single interface loss",
        "evidence gap regret",
        "external face check",
    ]
    for index, label in enumerate(outputs):
        col = index % 3
        row = index // 3
        x = 0.005 + col * 0.33
        y = 0.57 - row * 0.25
        ax2.add_patch(
            Rectangle(
                (x, y),
                0.285,
                0.14,
                facecolor=PALE,
                edgecolor="none",
            )
        )
        ax2.add_patch(
            Rectangle(
                (x, y),
                0.012,
                0.14,
                facecolor=(TEAL if index < 3 else ORANGE),
                edgecolor="none",
            )
        )
        ax2.text(
            x + 0.026,
            y + 0.07,
            label,
            ha="left",
            va="center",
            fontsize=7.2,
            color=INK,
        )
    ax2.text(
        0.005,
        0.02,
        "Gates: traceability | equal budget discrimination | monotone response | external face validity",
        ha="left",
        va="bottom",
        fontsize=6.8,
        color=MUTED,
    )
    save(fig, out / "figure1_data_lineage.png")


COUNTRY_ANCHORS = {
    "Albania": (20.1, 41.2),
    "Algeria": (2.5, 35.0),
    "Austria": (14.1, 47.6),
    "Belgium": (4.6, 50.8),
    "Bosnia Herzegovina": (17.8, 44.2),
    "Bulgaria": (25.3, 42.7),
    "Croatia": (15.4, 45.2),
    "Cyprus": (33.0, 35.1),
    "Czechia": (15.3, 49.8),
    "Denmark": (10.0, 56.0),
    "Estonia": (25.5, 58.6),
    "Finland": (26.0, 62.0),
    "France": (2.2, 46.5),
    "Germany": (10.5, 51.1),
    "Greece": (22.0, 39.0),
    "Hungary": (19.2, 47.2),
    "Ireland": (-8.0, 53.2),
    "Israel": (34.8, 31.5),
    "Italy": (12.5, 42.8),
    "Latvia": (24.6, 56.9),
    "Lithuania": (23.9, 55.2),
    "Luxembourg": (6.1, 49.8),
    "Luxemburg": (6.1, 49.8),
    "Moldavia": (28.5, 47.1),
    "Morocco": (-6.0, 33.5),
    "Netherlands": (5.5, 52.2),
    "North Macedonia": (21.7, 41.6),
    "Norway": (8.0, 60.5),
    "Poland": (19.1, 52.1),
    "Portugal": (-8.0, 39.5),
    "Romania": (25.0, 45.8),
    "Serbia": (20.8, 44.0),
    "Slovakia": (19.7, 48.7),
    "Slovenia": (14.9, 46.1),
    "Spain": (-3.5, 40.3),
    "Sweden": (16.0, 59.3),
    "Switzerland": (8.2, 46.8),
    "Turkey": (29.0, 40.5),
    "Ukraine": (31.0, 49.0),
    "United Kingdom": (-2.0, 54.5),
}


COUNTRY_CODES = {
    "Albania": "AL",
    "Algeria": "DZ",
    "Austria": "AT",
    "Belgium": "BE",
    "Bosnia Herzegovina": "BA",
    "Bulgaria": "BG",
    "Croatia": "HR",
    "Cyprus": "CY",
    "Czechia": "CZ",
    "Denmark": "DK",
    "Estonia": "EE",
    "Finland": "FI",
    "France": "FR",
    "Germany": "DE",
    "Greece": "GR",
    "Hungary": "HU",
    "Ireland": "IE",
    "Israel": "IL",
    "Italy": "IT",
    "Latvia": "LV",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Luxemburg": "LU",
    "Moldavia": "MD",
    "Morocco": "MA",
    "Netherlands": "NL",
    "North Macedonia": "MK",
    "Norway": "NO",
    "Poland": "PL",
    "Portugal": "PT",
    "Romania": "RO",
    "Serbia": "RS",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Turkey": "TR",
    "Ukraine": "UA",
    "United Kingdom": "UK",
}


def _draw_europe_outline(ax: plt.Axes, map_path: Path) -> None:
    """Draw a light geographic backdrop without using map geometry in the model."""

    if not map_path.exists():
        return
    payload = json.loads(map_path.read_text(encoding="utf-8"))
    for feature in payload.get("features", []):
        geometry = feature.get("geometry") or {}
        kind = geometry.get("type")
        coordinates = geometry.get("coordinates", [])
        polygons = coordinates if kind == "MultiPolygon" else [coordinates]
        for polygon in polygons:
            for ring in polygon[:1]:
                if len(ring) >= 3:
                    ax.add_patch(
                        Polygon(
                            ring,
                            closed=True,
                            facecolor="#F4F7F9",
                            edgecolor="#D3DEE5",
                            linewidth=0.35,
                            zorder=0,
                        )
                    )


def _project_positions(
    edges: pd.DataFrame,
    nodes: pd.DataFrame,
) -> tuple[dict[str, tuple[float, float]], list[str], list[str], dict[str, str], dict[str, str]]:
    """Create repeatable display anchors for the evidence graph."""

    node_records = nodes.set_index("node_id")["country"].to_dict()
    node_type = nodes.set_index("node_id")["node_type"].to_dict()
    for _, row in edges.iterrows():
        node_records.setdefault(row["from_node"], row["from_country"])
        node_records.setdefault(row["to_node"], row["to_country"])
        node_type.setdefault(
            row["from_node"],
            "terminal" if row["edge_type"] == "terminal_backbone" else "backbone",
        )
        node_type.setdefault(row["to_node"], "backbone")

    terminals = sorted(
        [
            node
            for node, kind in node_type.items()
            if kind == "terminal" or str(node).startswith("LH2_Tk_")
        ]
    )
    backbone = sorted([node for node in node_records if node not in terminals])
    countries = sorted({node_records[node] for node in backbone})
    pos: dict[str, tuple[float, float]] = {}

    terminal_index: dict[str, int] = {}
    for node in terminals:
        country = node_records.get(node, "")
        terminal_index[country] = terminal_index.get(country, 0) + 1
        base = COUNTRY_ANCHORS.get(country, (12.0, 48.0))
        offset = terminal_index[country] - 1
        pos[node] = (base[0] - 1.0, base[1] + 0.72 + 0.36 * offset)

    for country in countries:
        group = [node for node in backbone if node_records[node] == country]
        for i, node in enumerate(group):
            base = COUNTRY_ANCHORS.get(country, (12.0, 48.0))
            dx = (-0.35, 0.0, 0.35)[i % 3]
            dy = 0.45 * ((i // 3) % 3 - 1)
            pos[node] = (base[0] + dx, base[1] + dy)
    return pos, terminals, backbone, node_records, node_type


def _draw_graph_panel(
    ax: plt.Axes,
    frame: pd.DataFrame,
    pos: dict[str, tuple[float, float]],
    terminals: list[str],
    backbone: list[str],
    node_records: dict[str, str],
    selected: set[str],
    map_path: Path,
    zoom: bool,
) -> None:
    """Draw one map panel with explicit visual hierarchy."""

    _draw_europe_outline(ax, map_path)
    selected_terminals = {item.split("|")[0] for item in selected}
    selected_backbone = {item.split("|")[1] for item in selected}

    for _, row in frame.iterrows():
        u, v = row["from_node"], row["to_node"]
        if u not in pos or v not in pos:
            continue
        candidate = f"{u}|{v}" if row["edge_type"] == "terminal_backbone" else ""
        is_selected = candidate in selected
        if is_selected:
            color, width, alpha, zorder = RED, 2.15, 0.95, 3
        elif row["edge_type"] == "terminal_backbone":
            color, width, alpha, zorder = ORANGE, 1.1, 0.8, 2
        else:
            color, width, alpha, zorder = "#C7D2DA", 0.42, 0.62, 1
        ax.plot(
            [pos[u][0], pos[v][0]],
            [pos[u][1], pos[v][1]],
            color=color,
            linewidth=width,
            alpha=alpha,
            zorder=zorder,
            solid_capstyle="round",
        )

    candidate_terminal = [node for node in terminals if node in pos]
    candidate_backbone = [node for node in backbone if node in pos]
    ax.scatter(
        [pos[n][0] for n in candidate_backbone],
        [pos[n][1] for n in candidate_backbone],
        s=(16 if zoom else 10),
        color=BLUE,
        alpha=0.78,
        linewidth=0,
        zorder=4,
    )
    ax.scatter(
        [pos[n][0] for n in candidate_terminal],
        [pos[n][1] for n in candidate_terminal],
        s=(34 if zoom else 24),
        color=ORANGE,
        alpha=0.92,
        edgecolor="white",
        linewidth=0.45,
        zorder=5,
    )
    selected_terminal = [n for n in candidate_terminal if n in selected_terminals]
    selected_backbone_nodes = [n for n in candidate_backbone if n in selected_backbone]
    ax.scatter(
        [pos[n][0] for n in selected_backbone_nodes],
        [pos[n][1] for n in selected_backbone_nodes],
        s=(34 if zoom else 22),
        color=NAVY,
        edgecolor=RED,
        linewidth=0.8,
        zorder=6,
    )
    ax.scatter(
        [pos[n][0] for n in selected_terminal],
        [pos[n][1] for n in selected_terminal],
        s=(58 if zoom else 40),
        color=RED,
        edgecolor="white",
        linewidth=0.65,
        zorder=7,
    )

    context_labels = {"Belgium", "France", "Germany", "Italy", "Netherlands", "Poland"}
    for country in sorted({node_records[n] for n in backbone}):
        if (zoom and country in {"Belgium", "France", "Germany", "Netherlands", "Luxembourg", "Switzerland"}) or (
            not zoom and country in context_labels
        ):
            xcoord, ycoord = COUNTRY_ANCHORS.get(country, (12.0, 48.0))
            ax.text(
                xcoord,
                ycoord - (0.88 if not zoom else 0.55),
                COUNTRY_CODES.get(country, country[:2].upper()),
                fontsize=(6.8 if zoom else 6.0),
                color=MUTED,
                ha="center",
                va="top",
                zorder=8,
                clip_on=True,
            )

    if zoom:
        label_by_country = {
            "Belgium": "Belgium",
            "Germany": "Germany",
            "France": "Northern France",
            "Netherlands": "Netherlands",
        }
        offsets = {
            "Belgium": (-1.60, 1.50),
            "Germany": (1.05, 0.72),
            "France": (1.02, -0.58),
            "Netherlands": (1.25, 0.90),
        }
        for node in selected_terminal:
            country = node_records.get(node, "")
            if country not in label_by_country:
                continue
            dx, dy = offsets[country]
            ax.annotate(
                label_by_country[country],
                xy=pos[node],
                xytext=(pos[node][0] + dx, pos[node][1] + dy),
                fontsize=7.0,
                color=INK,
                ha="left",
                va="center",
                arrowprops={
                    "arrowstyle": "-",
                    "color": MUTED,
                    "linewidth": 0.55,
                    "shrinkA": 3,
                    "shrinkB": 3,
                },
                bbox={
                    "facecolor": "white",
                    "edgecolor": "none",
                    "alpha": 0.92,
                    "pad": 1.2,
                },
                zorder=9,
                annotation_clip=True,
            )

    if zoom:
        ax.set_xlim(-2.2, 14.3)
        ax.set_ylim(43.5, 55.5)
        ax.set_title("Selected corridor", loc="left", x=PANEL_TITLE_X, pad=4)
        ax.text(
            0.02,
            0.03,
            "Graph anchors, not pipe routes",
            transform=ax.transAxes,
            fontsize=6.5,
            color=MUTED,
        )
    else:
        ax.set_xlim(-12.5, 36.0)
        ax.set_ylim(30.0, 64.5)
        ax.set_title("European context", loc="left", x=PANEL_TITLE_X, pad=4)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude (degrees)", labelpad=2)
    if not zoom:
        ax.set_ylabel("Latitude (degrees)", labelpad=2)
    else:
        ax.set_yticklabels([])
    ax.tick_params(length=2.5, labelsize=6.8)


def project_graph(run: Path, data: Path, out: Path, map_path: Path = DEFAULT_MAP) -> None:
    edges = pd.read_csv(data / "network_edges.csv")
    nodes = pd.read_csv(data / "network_nodes.csv")
    selected = set(
        json.loads((run / "main_selections.json").read_text(encoding="utf-8"))["robust_n1"]
    )
    frame = edges[
        (edges["year"] == 2040) & (edges["capacity_advanced_gwh_per_day"] > 0)
    ].copy()
    pos, terminals, backbone, node_records, _ = _project_positions(frame, nodes)

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(7.15, 3.75),
        gridspec_kw={"width_ratios": [1.0, 1.17]},
        constrained_layout=True,
    )
    _draw_graph_panel(
        ax1,
        frame,
        pos,
        terminals,
        backbone,
        node_records,
        selected,
        map_path,
        zoom=False,
    )
    _draw_graph_panel(
        ax2,
        frame,
        pos,
        terminals,
        backbone,
        node_records,
        selected,
        map_path,
        zoom=True,
    )
    panel_label(ax1, "a")
    panel_label(ax2, "b")

    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=RED,
            markeredgecolor="white",
            markersize=5.7,
            label="selected terminal",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=ORANGE,
            markeredgecolor="white",
            markersize=5.0,
            label="candidate terminal",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=BLUE,
            markersize=4.2,
            label="H2 node",
        ),
        Line2D([0], [0], color=RED, linewidth=2.0, label="selected interface"),
        Line2D([0], [0], color="#C7D2DA", linewidth=1.0, label="documented backbone"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.025),
        ncol=3,
        frameon=False,
        handlelength=1.8,
        columnspacing=1.3,
    )
    save(fig, out / "figure2_project_graph.png")


def portfolio_vs_random(run: Path, out: Path) -> None:
    random = pd.read_csv(run / "random_baseline.csv")
    metrics = pd.read_csv(run / "main_selection_metrics.csv")
    base = float(metrics.loc[metrics["method"].eq("robust_base"), "demand_cut_rate_pct"].max())
    median = float(random["worst_dcr_pct"].median())
    q90 = float(random["worst_dcr_pct"].quantile(0.90))
    gains = [median - base, q90 - base]

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(7.15, 3.05),
        gridspec_kw={"width_ratios": [1.48, 0.92]},
        constrained_layout=True,
    )

    bins = np.arange(50, 105, 5)
    ax1.hist(
        random["worst_dcr_pct"],
        bins=bins,
        color=PALE_BLUE,
        edgecolor="white",
        linewidth=0.5,
        rwidth=0.95,
    )
    ax1.axvline(base, color=RED, linewidth=1.9)
    ax1.axvline(median, color=NAVY, linewidth=1.25, linestyle=(0, (3, 2)))
    ax1.axvline(q90, color=ORANGE, linewidth=1.1, linestyle=(0, (1.5, 2)))
    ax1.text(
        base + 0.7,
        ax1.get_ylim()[1] * 0.90,
        f"selected\n{base:.2f}%",
        color=RED,
        fontsize=7.1,
        ha="left",
        va="top",
    )
    ax1.text(
        median + 0.7,
        ax1.get_ylim()[1] * 0.66,
        f"median\n{median:.2f}%",
        color=NAVY,
        fontsize=7.1,
        ha="left",
        va="top",
    )
    ax1.text(
        q90 - 0.8,
        ax1.get_ylim()[1] * 0.49,
        f"90th percentile\n{q90:.2f}%",
        color=ORANGE,
        fontsize=7.1,
        ha="right",
        va="top",
    )
    ax1.set_xlim(50, 105)
    ax1.set_xlabel("Worst planning cut rate (%)")
    ax1.set_ylabel("Number of portfolios")
    ax1.set_title("Exact four interface census", loc="left", x=PANEL_TITLE_X, pad=4)
    prepare_axis(ax1, grid=True)
    panel_label(ax1, "a")

    gain_labels = ["Below median", "Below 90th percentile"]
    y = np.arange(len(gains))
    ax2.barh(
        y,
        gains,
        color=[TEAL, ORANGE],
        height=0.46,
        alpha=0.92,
    )
    ax2.set_yticks(y, gain_labels)
    ax2.invert_yaxis()
    ax2.set_xlim(0, max(gains) + 8)
    ax2.set_xlabel("Selection separation (percentage points)")
    ax2.set_title("Observed separation", loc="left", x=PANEL_TITLE_X, pad=4)
    for ypos, value in zip(y, gains):
        ax2.text(
            value + 0.8,
            ypos,
            f"{value:.2f}",
            va="center",
            ha="left",
            fontsize=7.6,
            color=INK,
        )
    prepare_axis(ax2, grid=True)
    panel_label(ax2, "b")
    save(fig, out / "figure3_portfolio_vs_random.png")


def data_gap(run: Path, out: Path) -> None:
    gap = pd.read_csv(run / "data_gap_diagnostics.csv")

    def value(key: str, column: str) -> float:
        return float(gap.loc[gap["ablation"].eq(key), column].iloc[0])

    full = value("full_evidence", "worst_dcr_full_evidence_pct")
    capacity_removed = value(
        "capacity_evidence_removed",
        "worst_dcr_full_evidence_pct",
    )
    keys = [
        "carrier_evidence_removed",
        "capacity_evidence_removed",
        "demand_uncertainty_omitted",
    ]
    regret = [value(key, "regret_vs_full_robust_pp") for key in keys]

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(7.15, 3.05),
        gridspec_kw={"width_ratios": [1.0, 1.22]},
        constrained_layout=True,
    )

    y1 = np.arange(2)
    ax1.barh(
        y1,
        [full, capacity_removed],
        color=[TEAL, RED],
        height=0.48,
        alpha=0.92,
    )
    ax1.set_yticks(y1, ["Full evidence", "Capacity removed"])
    ax1.invert_yaxis()
    ax1.set_xlim(70, 105)
    ax1.set_xlabel("Held out worst cut rate (%)")
    ax1.set_title("Stress consequence", loc="left", x=PANEL_TITLE_X, pad=4)
    for ypos, current in zip(y1, [full, capacity_removed]):
        ax1.text(
            current + 1.0,
            ypos,
            f"{current:.2f}%",
            va="center",
            ha="left",
            fontsize=7.5,
            color=INK,
        )
    ax1.annotate(
        "",
        xy=(capacity_removed, 0.5),
        xytext=(full, 0.5),
        arrowprops={
            "arrowstyle": "<->",
            "color": RED,
            "linewidth": 0.85,
            "shrinkA": 4,
            "shrinkB": 4,
        },
    )
    ax1.text(
        (full + capacity_removed) / 2,
        0.5,
        f"+{capacity_removed - full:.2f} pp",
        ha="center",
        va="center",
        fontsize=7.4,
        color=RED,
        bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5},
    )
    prepare_axis(ax1)
    panel_label(ax1, "a")

    labels = ["Carrier evidence", "Capacity evidence", "Demand layer"]
    y2 = np.arange(len(regret))
    colors = [GREY, RED, GREY]
    for ypos, current, color in zip(y2, regret, colors):
        ax2.hlines(ypos, 0, current, color=color, linewidth=2.0, alpha=0.85)
        ax2.scatter([current], [ypos], s=34, color=color, zorder=3)
        label_x = current + (1.35 if current == 0 else 1.0)
        ax2.text(
            label_x,
            ypos,
            f"{current:.2f}",
            va="center",
            ha="left",
            fontsize=7.5,
            color=INK,
        )
    ax2.axvline(
        1.0,
        color=ORANGE,
        linestyle=(0, (3, 2)),
        linewidth=1.0,
    )
    ax2.text(
        1.75,
        0.12,
        "predeclared 1 pp gate",
        transform=ax2.get_xaxis_transform(),
        color=ORANGE,
        fontsize=6.9,
        ha="left",
        va="bottom",
    )
    ax2.set_yticks(y2, labels)
    ax2.invert_yaxis()
    ax2.set_xlim(0, max(regret) + 4)
    ax2.set_xlabel("Planning stress increase (percentage points)")
    ax2.set_title("Evidence ablation", loc="left", x=PANEL_TITLE_X, pad=4)
    prepare_axis(ax2)
    panel_label(ax2, "b")
    save(fig, out / "figure4_data_gap_regret.png")


def structural_ablation(run: Path, out: Path) -> None:
    frame = pd.read_csv(run / "structural_ablation.csv")
    labels = [
        "Topology free LP",
        "Project graph LP",
        "Graph plus carrier",
        "Central scenario MILP",
        "Robust scenario MILP",
    ]
    values = frame["worst_dcr_pct"].to_numpy()
    colors = [GREY, MUTED, TEAL, BLUE, RED]
    y = np.arange(len(values))

    fig, ax = plt.subplots(figsize=(7.15, 3.0), constrained_layout=True)
    ax.barh(y, values, color=colors, height=0.54, alpha=0.92)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(50, max(values) + 1.9)
    ax.set_xlabel("Worst planning cut rate (%)")
    ax.set_title("Structural ablation", loc="left", pad=4)
    for ypos, current in zip(y, values):
        ax.text(
            current + 0.22,
            ypos,
            f"{current:.2f}%",
            va="center",
            ha="left",
            fontsize=7.3,
            color=INK,
        )
    prepare_axis(ax, grid=True)
    save(fig, out / "figure3_structural_ablation.png")


def resilience(run: Path, out: Path) -> None:
    criticality = pd.read_csv(run / "interface_criticality.csv")
    envelope = pd.read_csv(run / "nk_resilience.csv")
    criticality = criticality.sort_values("delta_worst_dcr_pp", ascending=True)
    name_map = {
        "LH2_Tk_NL|NLh2": "Netherlands",
        "LH2_Tk_BE|BEh2": "Belgium",
        "LH2_Tk_DE|DEh2": "Germany",
        "LH2_Tk_FRn|FRh2N": "Northern France",
    }
    labels = [name_map.get(key, key) for key in criticality["candidate_key"]]
    values = criticality["delta_worst_dcr_pp"].to_numpy()
    colors = [
        RED if label == "Netherlands" else ORANGE if label in {"Belgium", "Germany"} else GREY
        for label in labels
    ]

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(7.15, 3.0),
        gridspec_kw={"width_ratios": [1.23, 0.9]},
        constrained_layout=True,
    )
    y = np.arange(len(values))
    ax1.barh(y, values, color=colors, height=0.52, alpha=0.92)
    ax1.set_yticks(y, labels)
    ax1.set_xlim(0, max(values) + 5)
    ax1.set_xlabel("Increase in worst cut rate (pp)")
    ax1.set_title("Single interface loss", loc="left", x=PANEL_TITLE_X, pad=4)
    for ypos, current in zip(y, values):
        ax1.text(
            current + 0.45,
            ypos,
            f"+{current:.2f}",
            va="center",
            ha="left",
            fontsize=7.3,
            color=INK,
        )
    prepare_axis(ax1, grid=True)
    panel_label(ax1, "a")

    env = envelope[envelope["method"].eq("robust_n1")].sort_values("k")
    x = env["k"].to_numpy()
    values_env = env["worst_dcr_pct"].to_numpy()
    ax2.plot(
        x,
        values_env,
        color=RED,
        linewidth=1.8,
        marker="o",
        markersize=5.0,
        markeredgecolor="white",
        markeredgewidth=0.7,
    )
    for current_x, current_y in zip(x, values_env):
        if abs(current_x) < 1e-9:
            label_x = current_x + 0.50
            label_y = current_y + 5.0
            label_ha = "left"
            label_bbox = {"facecolor": "white", "edgecolor": "none", "alpha": 0.92, "pad": 0.7}
        else:
            label_x = current_x
            label_y = current_y + 2.5
            label_ha = "center"
            label_bbox = {"facecolor": "white", "edgecolor": "none", "alpha": 0.92, "pad": 0.7}
        ax2.text(
            label_x,
            label_y,
            f"{current_y:.2f}%",
            ha=label_ha,
            va="bottom",
            fontsize=7.1,
            color=INK,
            bbox=label_bbox,
        )
    ax2.set_xticks([0, 1, 2], ["0", "1", "2"])
    ax2.set_xlabel("Interfaces failed")
    ax2.set_ylabel("Worst cut rate (%)")
    ax2.set_ylim(50, 100)
    ax2.set_title("Portfolio envelope", loc="left", x=PANEL_TITLE_X, pad=4)
    prepare_axis(ax2, grid=True)
    panel_label(ax2, "b")
    save(fig, out / "figure5_nk_resilience.png")


def capacity(run: Path, out: Path) -> None:
    frame = pd.read_csv(run / "capacity_sensitivity.csv")
    x = frame["capacity_multiplier"].to_numpy()
    worst = frame["worst_dcr_pct"].to_numpy()
    mean = frame["mean_dcr_pct"].to_numpy()

    fig, ax = plt.subplots(figsize=(7.15, 3.15), constrained_layout=True)
    ax.axvspan(0.95, 1.05, color=PALE_BLUE, alpha=0.95, zorder=0)
    ax.text(
        1.0,
        81.5,
        "recorded\ncapacity",
        ha="center",
        va="top",
        fontsize=7.0,
        color=BLUE,
    )
    ax.plot(
        x,
        worst,
        color=RED,
        linewidth=1.9,
        marker="o",
        markersize=5.0,
        markeredgecolor="white",
        markeredgewidth=0.7,
        label="worst scenario",
    )
    ax.plot(
        x,
        mean,
        color=BLUE,
        linewidth=1.7,
        marker="s",
        markersize=4.6,
        markeredgecolor="white",
        markeredgewidth=0.7,
        label="mean scenario",
    )
    for current_x, current_worst, current_mean in zip(x, worst, mean):
        ax.text(
            current_x,
            current_worst + 2.2,
            f"{current_worst:.1f}%",
            ha="center",
            va="bottom",
            fontsize=7.1,
            color=RED,
        )
        mean_offset = 2.5 if current_mean < 10 else -3.3
        mean_va = "bottom" if current_mean < 10 else "top"
        ax.text(
            current_x,
            current_mean + mean_offset,
            f"{current_mean:.1f}%",
            ha="center",
            va=mean_va,
            fontsize=7.0,
            color=BLUE,
        )
    ax.set_xticks(x, ["0.5", "1.0", "1.5"])
    ax.set_xlabel("Capacity multiplier")
    ax.set_ylabel("Demand cut rate (%)")
    ax.set_ylim(0, 85)
    ax.set_title("Capacity sensitivity", loc="left", pad=4)
    ax.legend(frameon=False, loc="upper right", ncol=2, handlelength=1.6)
    prepare_axis(ax, grid=True)
    save(fig, out / "figure6_capacity_sensitivity.png")


def external(run: Path, out: Path) -> None:
    frame = pd.read_csv(run / "external_corridor_face_validity.csv")
    years = [str(int(year)) for year in frame["year"]]
    x = np.arange(len(frame))

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(7.15, 3.0),
        gridspec_kw={"width_ratios": [0.9, 1.1]},
        constrained_layout=True,
    )

    overlap = frame["top4_overlap"].to_numpy()
    ax1.bar(x, overlap, color=TEAL, width=0.48, alpha=0.92)
    ax1.axhline(2, color=ORANGE, linestyle=(0, (3, 2)), linewidth=1.0)
    for current_x, current_y in zip(x, overlap):
        ax1.text(
            current_x,
            current_y + 0.15,
            f"{current_y:.0f}",
            ha="center",
            va="bottom",
            fontsize=7.4,
            color=INK,
        )
    ax1.set_xticks(x, years)
    ax1.set_ylim(0, 4.4)
    ax1.set_ylabel("Countries in external top four")
    ax1.set_xlabel("Year")
    ax1.set_title("Top four overlap", loc="left", x=PANEL_TITLE_X, pad=4)
    prepare_axis(ax1)
    panel_label(ax1, "a")

    coverage = frame["weighted_target_coverage"].to_numpy() * 100.0
    ax2.plot(
        x,
        coverage,
        color=NAVY,
        linewidth=1.8,
        marker="o",
        markersize=5.0,
        markeredgecolor="white",
        markeredgewidth=0.7,
    )
    for current_x, current_y in zip(x, coverage):
        ax2.text(
            current_x + (0.04 if current_x == 0 else 0.0),
            current_y + 4.0,
            f"{current_y:.1f}%",
            ha="center",
            va="bottom",
            fontsize=7.4,
            color=INK,
        )
    ax2.set_xticks(x, years)
    ax2.set_ylim(0, 75)
    ax2.set_ylabel("Weighted target coverage (%)")
    ax2.set_xlabel("Year")
    ax2.set_title("Weighted target coverage", loc="left", x=PANEL_TITLE_X, pad=4)
    prepare_axis(ax2, grid=True)
    panel_label(ax2, "b")
    save(fig, out / "figure7_external_face_validity.png")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    args = parser.parse_args()

    style()
    lineage(args.output)
    project_graph(args.run, args.data, args.output, args.map)
    structural_ablation(args.run, args.output)
    portfolio_vs_random(args.run, args.output)
    data_gap(args.run, args.output)
    resilience(args.run, args.output)
    capacity(args.run, args.output)
    external(args.run, args.output)
    print(f"Wrote publication figures to {args.output}")


if __name__ == "__main__":
    main()
