from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
PAPER = (ROOT / "paper" / "main.md").read_text(encoding="utf-8")
AUDIT_DIR = ROOT / "paper" / "audits"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def exists(rel):
    return (ROOT / rel).exists()


def read_json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def read_jsonl(rel):
    return [json.loads(line) for line in (ROOT / rel).read_text(encoding="utf-8").splitlines() if line.strip()]


evidence = {
    "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    "profile": read_json("planning/session_config.json")["rigor_profile"],
    "questions": {},
    "global": {},
}

required_per_q = {
    "final_method": "methods/{q}/{ql}_final_method_explanation.md",
    "code_review": "code/{q}/reviews/{ql}_python_review.json",
    "final_result": "results/{q}/reports/{ql}_final_result_analysis.md",
    "robustness_report": "robustness/{q}/{ql}_robustness_report.md",
    "solution_package": "results/{q}/reports/{ql}_solution_package_for_writer.md",
    "frozen_numbers": "results/{q}/reports/frozen_numbers.json",
    "paper_section": "paper/sections/{section}",
    "figure": "paper/figures/{figure}",
}

section_map = {"Q1": "03_q1.md", "Q2": "04_q2.md", "Q3": "05_q3.md"}
figure_map = {"Q1": "q1_demand_robustness.png", "Q2": "q2_seed_robustness.png", "Q3": "q3_relationship_robustness.png"}

major_claims = {
    "Q1": ["3372.86", "6.83%", "6141.21", "48.86%", "10.12%"],
    "Q2": ["6820.61", "6801.43", "6642.93", "6614.38", "58.03%", "4.40%"],
    "Q3": ["6756.33", "6819.68", "63.35", "6568.42", "42.65%", "3.63%", "0.356%"],
}

for q in ("Q1", "Q2", "Q3"):
    ql = q.lower()
    paths = {name: template.format(q=q, ql=ql, section=section_map[q], figure=figure_map[q])
             for name, template in required_per_q.items()}
    review = read_json(paths["code_review"])
    decisions = read_jsonl(f"methods/{q}/{ql}_decisions.jsonl")
    frozen = read_json(paths["frozen_numbers"])
    decision_ids = {d["decision_id"] for d in decisions if d.get("status") == "DECIDED" and d.get("decided_by") == "human"}
    source_files_exist = all(exists(c["source_file"]) for c in frozen["claims"])
    evidence["questions"][q] = {
        "required_files": {name: exists(path) for name, path in paths.items()},
        "review_verdict": review.get("verdict"),
        "named_checks_all_pass": all(v.get("status") == "PASS" for v in review.get("checks", {}).values()),
        "human_decisions": sorted(decision_ids),
        "required_decisions_present": all(x in decision_ids for x in [
            f"{ql}_method_choice", f"{ql}_result_verdict_round1",
            f"{ql}_stability_verdict_round1", f"{ql}_package_signoff"]),
        "frozen_claim_count": len(frozen["claims"]),
        "frozen_sources_exist": source_files_exist,
        "paper_major_claims_present": {claim: claim in PAPER for claim in major_claims[q]},
    }

global_required = [
    "planning/symbol_table.md", "planning/model_assumptions.md",
    "paper/refs.bib", "paper/reference_audit.md", "paper/polish_report.md",
    "paper/audits/cross_media_consistency_audit.md",
    "paper/audits/completeness_audit.md", "paper/qa_report.md",
    "paper/final/24C_农作物种植策略论文.docx",
    "paper/final/24C_农作物种植策略论文.pdf",
    "outputs/24c_modeling/result1_1.xlsx", "outputs/24c_modeling/result1_2.xlsx",
    "outputs/24c_modeling/result2.xlsx", "outputs/24c_modeling/result3.xlsx",
]
evidence["global"]["required_files"] = {path: exists(path) for path in global_required}
evidence["global"]["figures"] = {
    name: exists(f"paper/figures/{name}")
    for name in figure_map.values()
}
evidence["global"]["reference_entries"] = len(re.findall(r"^\[\d+\]", PAPER, flags=re.M))
evidence["global"]["citations_present"] = {str(i): f"[{i}]" in PAPER for i in range(1, 6)}
evidence["global"]["placeholder_hits"] = re.findall(r"\b(?:TODO|TBD|PLACEHOLDER)\b|待补|待定", PAPER, flags=re.I)

docx = ROOT / "paper" / "final" / "24C_农作物种植策略论文.docx"
with zipfile.ZipFile(docx) as archive:
    xml = ET.fromstring(archive.read("word/document.xml"))
ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
tables = xml.findall(".//w:tbl", ns)
geometry_ok = True
for table in tables:
    tbl_w = table.find("./w:tblPr/w:tblW", ns)
    tbl_ind = table.find("./w:tblPr/w:tblInd", ns)
    grid = table.findall("./w:tblGrid/w:gridCol", ns)
    if tbl_w is None or tbl_ind is None or not grid:
        geometry_ok = False
        break
    w = int(tbl_w.attrib[f"{{{ns['w']}}}w"])
    ind = int(tbl_ind.attrib[f"{{{ns['w']}}}w"])
    grid_sum = sum(int(c.attrib[f"{{{ns['w']}}}w"]) for c in grid)
    if w != 9411 or ind != 120 or grid_sum != w:
        geometry_ok = False
        break
evidence["global"]["docx_table_count"] = len(tables)
evidence["global"]["docx_table_geometry_ok"] = geometry_ok

pdf = ROOT / "paper" / "final" / "24C_农作物种植策略论文.pdf"
with pdfplumber.open(pdf) as opened:
    evidence["global"]["pdf_page_count"] = len(opened.pages)
    evidence["global"]["pdf_all_pages_nonempty"] = all((page.extract_text() or "").strip() for page in opened.pages)

all_q_ok = all(
    all(qe["required_files"].values())
    and qe["review_verdict"] == "PASSED"
    and qe["named_checks_all_pass"]
    and qe["required_decisions_present"]
    and qe["frozen_sources_exist"]
    and all(qe["paper_major_claims_present"].values())
    for qe in evidence["questions"].values()
)
global_ok = (
    all(evidence["global"]["required_files"].values())
    and all(evidence["global"]["figures"].values())
    and evidence["global"]["reference_entries"] == 5
    and all(evidence["global"]["citations_present"].values())
    and not evidence["global"]["placeholder_hits"]
    and evidence["global"]["docx_table_geometry_ok"]
    and evidence["global"]["pdf_page_count"] == 7
    and evidence["global"]["pdf_all_pages_nonempty"]
)
evidence["verdict"] = "PASSED" if all_q_ok and global_ok else "FAILED"

out = AUDIT_DIR / "final_audit_evidence.json"
out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"verdict": evidence["verdict"], "path": str(out)}, ensure_ascii=False))
