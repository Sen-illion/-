from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "paper" / "figures"
PRIMARY = "#1A6FC4"
BASELINE = "#767676"
NEGATIVE = "#E53935"
ACCENT = "#E28E2C"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "svg.fonttype": "none",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 9,
})


def claims(question):
    data = json.loads((ROOT / "results" / question / "reports" / "frozen_numbers.json").read_text(encoding="utf-8"))
    return {item["claim_id"]: item["value"] for item in data["claims"]}


def clean_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#D8D8D8", linewidth=0.7, alpha=0.65)
    ax.set_axisbelow(True)


def save(fig, name):
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", dpi=320, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def q1_figure():
    c = claims("Q1")
    scales = [0.95, 1.00, 1.05]
    main = [100*c[f"Q1-robust-case1_main-{s}"] for s in scales]
    base = [100*c[f"Q1-robust-baseline-{s}"] for s in scales]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.1), gridspec_kw={"width_ratios": [1.05, 1]})
    ax = axes[0]
    ax.plot(scales, main, color=PRIMARY, marker="o", linewidth=2.2, label="主方案")
    ax.plot(scales, base, color=BASELINE, marker="s", linestyle="--", linewidth=1.8, label="贪心基线")
    ax.set_ylim(0, 100)
    ax.set_xlabel("预期销量倍率")
    ax.set_ylabel("超产率（%）")
    ax.set_title("(a) 主方案与基线的完整尺度比较")
    ax.legend(frameon=False)
    clean_axes(ax)
    ax = axes[1]
    ax.plot(scales, main, color=PRIMARY, marker="o", linewidth=2.2)
    ax.axhline(10, color=NEGATIVE, linestyle="--", linewidth=1.4, label="预设10%阈值")
    for x, y in zip(scales, main):
        ax.annotate(f"{y:.2f}%", (x, y), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=9)
    ax.set_ylim(0, 13)
    ax.set_xlabel("预期销量倍率")
    ax.set_ylabel("主方案超产率（%）")
    ax.set_title("(b) 主方案在阈值附近的变化")
    ax.legend(frameon=False)
    clean_axes(ax)
    fig.suptitle("Q1(1) 预期销量扰动下的超产控制", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93), pad=1.3)
    save(fig, "q1_demand_robustness")


def q2_figure():
    c = claims("Q2")
    seeds = [20240903, 20240904, 20240905, 20240906, 20240907]
    mean = [c[f"Q2-seed-{seed}-mean-diff"] / 10000 for seed in seeds]
    tail = [c[f"Q2-seed-{seed}-tail-diff"] / 10000 for seed in seeds]
    x = np.arange(len(seeds))
    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    ax.axhline(0, color="#4D4D4D", linewidth=1)
    ax.plot(x, mean, color=PRIMARY, marker="o", linewidth=2.2, label="平均利润增量")
    ax.plot(x, tail, color=ACCENT, marker="s", linestyle="--", linewidth=2.0, label="最差10%平均利润增量")
    ax.fill_between(x, mean, tail, color="#B4D4F0", alpha=0.22)
    ax.set_xticks(x)
    ax.set_xticklabels([str(seed)[-2:] for seed in seeds])
    ax.set_xlabel("新随机种子（末两位）")
    ax.set_ylabel("主方案相对基线的利润增量（万元/年）")
    ax.set_ylim(0, max(tail) * 1.22)
    ax.set_title("Q2 在五个新随机种子下的基线改进方向")
    ax.legend(frameon=False, loc="upper left")
    clean_axes(ax)
    fig.tight_layout(pad=1.2)
    save(fig, "q2_seed_robustness")


def q3_figure():
    c = claims("Q3")
    strengths = [0.5, 1.0, 1.5]
    seeds = [20240903, 20240904, 20240905]
    colors = [PRIMARY, ACCENT, "#7B5FD6"]
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.axhline(0, color="#4D4D4D", linewidth=1.2, label="Q3与Q2持平")
    for seed, color in zip(seeds, colors):
        vals = [c[f"Q3-strength-{s}-seed-{seed}-mean-diff"] / 10000 for s in strengths]
        ax.plot(strengths, vals, color=color, marker="o", linewidth=2, label=f"种子{str(seed)[-2:]}")
    ax.fill_between([0.45, 1.55], [-70, -70], [0, 0], color="#FDE8E7", alpha=0.45, zorder=-2)
    ax.set_xlim(0.45, 1.55)
    ax.set_ylim(-70, 5)
    ax.set_xticks(strengths)
    ax.set_xlabel("相关关系强度")
    ax.set_ylabel("Q3−Q2 平均利润差（万元/年）")
    ax.set_title("Q3 相关强度与随机种子敏感性")
    ax.legend(frameon=False, ncol=2, loc="upper right")
    clean_axes(ax)
    fig.tight_layout(pad=1.2)
    save(fig, "q3_relationship_robustness")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    q1_figure()
    q2_figure()
    q3_figure()
    print("generated q1_demand_robustness, q2_seed_robustness, q3_relationship_robustness")
