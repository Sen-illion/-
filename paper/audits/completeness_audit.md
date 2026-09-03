# 提交档案完整性审计

**配置：** submission  
**结论：** PASSED  
**机器证据：** `paper/audits/final_audit_evidence.json`

## 分问题证据

Q1、Q2、Q3 均具备且保持当前有效：最终方法说明、Python 审查 JSON、最终结果分析、稳健性报告、写作方案包、冻结数值、对应论文节和已渲染论文图。三个代码审查的总判定均为 `PASSED`，其中 syntax、input_contract、method_alignment、reproducibility 和 output_contract 五项命名检查全部通过。

每问均存在四项 human 决策：方法选择、结果判定、稳定性判定和方案包签署。冻结数值分别包含 17、25、25 项主张，所有来源文件均存在。

## 全局证据

- 全局符号表、模型假设、参考文献库和参考文献核验记录存在。
- 跨媒介一致性审计、本文完整性审计和最终 `paper/qa_report.md` 均存在。
- 三张论文图、四个结果工作簿、最终 DOCX 和 PDF 均存在。
- 正文含 5 条完整参考文献，正文引用编号 [1]—[5] 均可解析，未检出 TODO、TBD、PLACEHOLDER、待补或待定文本。
- PDF 每页均可提取非空文本，7 页全部通过视觉检查；DOCX 表格宽度、网格列宽、单元格宽度和 120 DXA 缩进一致。

## 缺口

未发现提交档案的语义证据缺口。

