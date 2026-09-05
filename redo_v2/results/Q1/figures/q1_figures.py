from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "redo_v2" / "workspace" / "data_clean"
RESULTS = ROOT / "redo_v2" / "results" / "Q1" / "experiments" / "round2" / "tables"
OUT = ROOT / "final_figures"
SRC = ROOT / "figure_sources" / "source_data"
OUT.mkdir(exist_ok=True)
SRC.mkdir(exist_ok=True)

FONT = "SimSun"
plt.rcParams.update({
    "font.family": FONT,
    "axes.unicode_minus": False,
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.labelsize": 9.5,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "legend.fontsize": 8,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "savefig.facecolor": "white",
    "axes.facecolor": "#FBFCFE",
    "figure.facecolor": "white",
})
BLUE = "#2F6690"
TEAL = "#3D8B8B"
ORANGE = "#D8893B"
RED = "#B84A62"
GREEN = "#5A9367"
PURPLE = "#8064A2"
GRAY = "#4B5563"
TYPE_COLORS = {"粮食": BLUE, "粮食（豆类）": GREEN, "蔬菜": TEAL, "蔬菜（豆类）": ORANGE, "食用菌": PURPLE}
TYPE_HATCHES = {"粮食": "", "粮食（豆类）": "///", "蔬菜": "..", "蔬菜（豆类）": "xx", "食用菌": "\\\\"}
LAND_ORDER = ["平旱地", "梯田", "山坡地", "水浇地", "普通大棚", "智慧大棚"]

def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=400)
    fig.savefig(OUT / f"{name}.svg")
    fig.savefig(OUT / f"{name}.pdf")
    plt.close(fig)

def money(x, pos):
    return f"{x:.0f}"

def fig1_land():
    l = pd.read_csv(DATA / "land.csv")
    g = l.groupby("land_type", as_index=False).agg(地块数=("plot_id", "nunique"), 面积_mu=("area_mu", "sum"))
    g["land_type"] = pd.Categorical(g.land_type, LAND_ORDER, ordered=True)
    g = g.sort_values("land_type")
    g.to_csv(SRC / "fig1_land_inventory.csv", index=False, encoding="utf-8-sig")
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    y = np.arange(len(g))
    bars = ax.barh(y, g.面积_mu, color=[BLUE, TEAL, GREEN, ORANGE, PURPLE, RED], height=.62,
                   hatch=["", "//", "..", "xx", "\\\\", "++"], edgecolor="white", linewidth=.35)
    ax.set_yticks(y, g.land_type)
    ax.invert_yaxis()
    ax.set_xlabel("土地面积（亩）")
    ax.set_xlim(0, max(g.面积_mu) * 1.22)
    ax.grid(axis="x", color="#D9E1EA", linewidth=.7, alpha=.8)
    ax.set_axisbelow(True)
    total = g.面积_mu.sum()
    for b, (_, r) in zip(bars, g.iterrows()):
        ax.text(b.get_width() + 8, b.get_y() + b.get_height()/2,
                f"{r.面积_mu:.1f} 亩  ·  {int(r.地块数)} 块  ·  {r.面积_mu/total:.1%}",
                va="center", color=GRAY, fontsize=8.5)
    ax.text(0, 1.04, f"总面积 = {total:.1f} 亩；地块总数 = {int(g.地块数.sum())}", transform=ax.transAxes, color=GRAY)
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.subplots_adjust(left=.20, right=.98, bottom=.16, top=.90)
    save(fig, "Fig1_land_inventory")

def fig2_economic():
    e = pd.read_csv(DATA / "economics_2023.csv")
    ctype = pd.read_csv(DATA / "crops.csv")[["crop_id", "crop_type"]]
    e = e.merge(ctype, on="crop_id", how="left", validate="many_to_one")
    e["price_mid"] = (e.price_low_yuan_per_jin + e.price_high_yuan_per_jin) / 2
    e["gross_margin"] = e.yield_jin_per_mu * e.price_mid - e.cost_yuan_per_mu
    g = e.groupby(["crop_id", "crop_name", "crop_type"], as_index=False).agg(
        yield_jin_per_mu=("yield_jin_per_mu", "median"),
        cost_yuan_per_mu=("cost_yuan_per_mu", "median"),
        price_low=("price_low_yuan_per_jin", "median"),
        price_high=("price_high_yuan_per_jin", "median"),
        gross_margin=("gross_margin", "median"), records=("record_id", "count"))
    g["price_mid"] = (g.price_low + g.price_high) / 2
    g = g.sort_values("gross_margin", ascending=False)
    g.to_csv(SRC / "fig2_crop_economics.csv", index=False, encoding="utf-8-sig")
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.5), gridspec_kw={"width_ratios": [1.15, 1]})
    plot = g.sort_values("gross_margin").tail(18)
    colors = [TYPE_COLORS.get(x, GRAY) for x in plot.crop_type]
    ax.barh(plot.crop_name, plot.gross_margin / 1000, color=colors, height=.68)
    ax.set_xlabel("典型亩均毛利（千元/亩）")
    ax.grid(axis="x", color="#D9E1EA", linewidth=.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax2.scatter(g.yield_jin_per_mu, g.gross_margin / 1000, s=25 + 8*g.records,
                c=[TYPE_COLORS.get(x, GRAY) for x in g.crop_type], alpha=.82, edgecolor="white", linewidth=.5)
    for _, r in g.head(8).iterrows():
        ax2.annotate(r.crop_name, (r.yield_jin_per_mu, r.gross_margin/1000), xytext=(4, 3), textcoords="offset points", fontsize=7.5)
    ax2.set_xlabel("亩产（斤/亩）")
    ax2.set_ylabel("典型亩均毛利（千元/亩）")
    ax2.grid(color="#D9E1EA", linewidth=.7)
    ax2.set_axisbelow(True)
    ax2.spines[["top", "right"]].set_visible(False)
    handles = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=c, label=t, markersize=7) for t,c in TYPE_COLORS.items() if t in set(g.crop_type)]
    ax2.legend(handles=handles, frameon=False, loc="lower right", title="作物类型", title_fontsize=8)
    fig.subplots_adjust(left=.20, right=.98, bottom=.17, top=.93, wspace=.30)
    save(fig, "Fig2_crop_economic_profile")

def fig3_baseline():
    p = pd.read_csv(DATA / "planting_2023.csv")
    land = pd.read_csv(DATA / "land.csv")[["plot_id", "land_type"]]
    p = p.merge(land, on="plot_id", how="left", validate="many_to_one")
    g = p.groupby(["land_type", "crop_type"], as_index=False).area_mu.sum()
    piv = g.pivot(index="land_type", columns="crop_type", values="area_mu").fillna(0)
    piv = piv.reindex(LAND_ORDER).dropna(how="all").fillna(0)
    piv.to_csv(SRC / "fig3_baseline_2023_composition.csv", encoding="utf-8-sig")
    cols = [c for c in TYPE_COLORS if c in piv.columns]
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    bottom = np.zeros(len(piv))
    for c in cols:
        vals = piv[c].values
        ax.bar(piv.index, vals, bottom=bottom, color=TYPE_COLORS[c], label=c, width=.66,
               hatch=TYPE_HATCHES[c], edgecolor="white", linewidth=.35)
        bottom += vals
    totals = piv.sum(axis=1)
    for i, v in enumerate(totals):
        ax.text(i, v + max(totals)*.025, f"{v:.1f}", ha="center", fontsize=8, color=GRAY)
    ax.set_ylabel("2023 年种植面积（亩）")
    ax.set_xlabel("地块类型")
    ax.grid(axis="y", color="#D9E1EA", linewidth=.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.legend(ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(.5, 1.13))
    ax.text(0, -0.22, "注：2023 年基准记录按地块类型和作物类型汇总；此图不将未记录面积补为 0。", transform=ax.transAxes, fontsize=7.5, color=GRAY)
    fig.subplots_adjust(left=.12, right=.98, bottom=.25, top=.82)
    save(fig, "Fig3_baseline_2023_composition")

def fig4_tradeoff():
    m = pd.read_csv(RESULTS / "method_comparison.csv")
    names = {"m1_zero_price_profit":"主模型·零价处置", "m1_eta_01":"主模型·浪费约束1%", "m1_eta_03":"主模型·浪费约束3%", "m1_half_price":"主模型·半价销售", "b1_zero_price":"基准模型·零价处置", "b1_half_price":"基准模型·半价销售"}
    m["label"] = m.policy.map(names)
    m.to_csv(SRC / "fig4_q1_policy_tradeoff.csv", index=False, encoding="utf-8-sig")
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    marker = {"m1":"o", "b1":"s"}
    colors = [RED if "half" in p else (BLUE if p.startswith("m1") else TEAL) for p in m.policy]
    offsets = {"m1_zero_price_profit": (8, 8), "m1_eta_01": (8, -18), "m1_eta_03": (8, 10),
               "m1_half_price": (8, 8), "b1_zero_price": (-112, 10), "b1_half_price": (8, -18)}
    for (_, r), c in zip(m.iterrows(), colors):
        ax.scatter(r.waste_rate*100, r.profit_yuan/1e6, s=125, c=c, marker=marker["m1" if r.policy.startswith("m1") else "b1"], edgecolor="white", linewidth=1.0, zorder=3)
        if r.policy == "b1_zero_price":
            ax.annotate(r.label, (r.waste_rate*100, r.profit_yuan/1e6), xytext=offsets.get(r.policy, (8, 6)), textcoords="offset points", fontsize=7.5,
                        bbox=dict(boxstyle="round,pad=.18", fc="white", ec="none", alpha=.78))
    ax.set_xlabel("浪费率（%）")
    ax.set_ylabel("总利润（百万元）")
    ax.grid(color="#D9E1EA", linewidth=.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.text(.02, .03, "圆点=主模型，方点=基准模型。\n半价销售情景的超产不计入浪费，但会显著增加超产量。", transform=ax.transAxes, fontsize=7.5, color=GRAY, va="bottom")
    ax.set_xlim(-0.8, 22.5)
    from mpl_toolkits.axes_grid1.inset_locator import inset_axes, mark_inset
    ins = inset_axes(ax, width="38%", height="34%", loc="lower right", borderpad=1.1)
    for (_, r), c in zip(m.iterrows(), colors):
        ins.scatter(r.waste_rate*100, r.profit_yuan/1e6, s=35, c=c, marker=marker["m1" if r.policy.startswith("m1") else "b1"], edgecolor="white", linewidth=.5)
        if r.policy in {"m1_zero_price_profit", "m1_eta_01", "m1_eta_03"}:
            short = {"m1_zero_price_profit":"零价", "m1_eta_01":"η=1%", "m1_eta_03":"η=3%"}[r.policy]
            ins.annotate(short, (r.waste_rate*100, r.profit_yuan/1e6), xytext=(3, 2), textcoords="offset points", fontsize=6)
    ins.set_xlim(1.8, 4.2); ins.set_ylim(38.2, 40.4)
    ins.set_xticks([2, 3, 4]); ins.set_yticks([39, 40]); ins.tick_params(labelsize=6, pad=1)
    ins.grid(color="#E4EAF0", linewidth=.5); ins.set_axisbelow(True)
    mark_inset(ax, ins, loc1=2, loc2=4, fc="none", ec="#9AA5B1", lw=.7)
    from matplotlib.lines import Line2D
    handles = [Line2D([0], [0], marker="o", color="w", markerfacecolor=RED, markeredgecolor="white", markersize=8, label="主模型·半价销售"),
               Line2D([0], [0], marker="s", color="w", markerfacecolor=RED, markeredgecolor="white", markersize=8, label="基准模型·半价销售")]
    ax.legend(handles=handles, frameon=False, loc="upper left", bbox_to_anchor=(.02, 1.01), borderaxespad=0)
    fig.subplots_adjust(left=.13, right=.98, bottom=.18, top=.94)
    save(fig, "Fig4_q1_policy_tradeoff")

def fig5_dynamics():
    p = pd.read_csv(RESULTS / "m1_eta_01_plan.csv")
    land = p.groupby(["year", "land_type"], as_index=False).area.sum()
    crop = p.groupby(["year", "crop_type"], as_index=False).area.sum()
    landp = land.pivot(index="year", columns="land_type", values="area").fillna(0).reindex(columns=LAND_ORDER, fill_value=0)
    cropp = crop.pivot(index="year", columns="crop_type", values="area").fillna(0)
    landp.to_csv(SRC / "fig5_selected_policy_land_dynamics.csv", encoding="utf-8-sig")
    cropp.to_csv(SRC / "fig5_selected_policy_crop_dynamics.csv", encoding="utf-8-sig")
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(8.0, 6.1), sharex=True)
    styles = {"平旱地": "-", "梯田": "--", "山坡地": "-.", "水浇地": ":", "普通大棚": (0, (3, 1, 1, 1)), "智慧大棚": (0, (5, 1))}
    for c in LAND_ORDER:
        ax.plot(landp.index, landp[c], marker="o", linestyle=styles[c], linewidth=1.8, markersize=4, label=c, color={"平旱地":BLUE,"梯田":TEAL,"山坡地":GREEN,"水浇地":ORANGE,"普通大棚":PURPLE,"智慧大棚":RED}[c])
    ax.set_ylabel("种植面积（亩·季）")
    ax.grid(color="#D9E1EA", linewidth=.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(.5, 1.22))
    cols = [c for c in TYPE_COLORS if c in cropp.columns]
    bottom = np.zeros(len(cropp))
    for c in cols:
        ax2.bar(cropp.index, cropp[c], bottom=bottom, color=TYPE_COLORS[c], width=.62, label=c,
                hatch=TYPE_HATCHES[c], edgecolor="white", linewidth=.35)
        bottom += cropp[c].values
    ax2.set_xlabel("年份")
    ax2.set_ylabel("种植面积（亩·季）")
    ax2.grid(axis="y", color="#D9E1EA", linewidth=.7)
    ax2.spines[["top", "right", "left"]].set_visible(False)
    ax2.text(.01, -.28, "注：选定方案为 m1_eta_01；由于部分地块可种植两季，面积按“亩·季”统计，不等同于土地实物面积。", transform=ax2.transAxes, fontsize=7.5, color=GRAY)
    fig.subplots_adjust(left=.12, right=.98, bottom=.19, top=.83, hspace=.35)
    save(fig, "Fig5_selected_policy_dynamics")

if __name__ == "__main__":
    fig1_land(); fig2_economic(); fig3_baseline(); fig4_tradeoff(); fig5_dynamics()
    print(f"Generated figures in {OUT}")
