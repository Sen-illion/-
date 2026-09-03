import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const projectRoot = path.resolve(".");
const outputDir = path.join(projectRoot, "outputs", "24c_modeling");
const previewDir = path.join(projectRoot, "spreadsheet_build", "previews");

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        cell += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        cell += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(cell);
      cell = "";
    } else if (ch === "\n") {
      row.push(cell.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += ch;
    }
  }
  if (cell.length || row.length) {
    row.push(cell.replace(/\r$/, ""));
    rows.push(row);
  }
  if (!rows.length) return [];
  const numericHeaders = new Set([
    "year", "plot_area_mu", "crop_id", "planted_area_mu", "scenario",
    "revenue_yuan", "cost_yuan", "profit_yuan", "excess_jin",
    "production_jin", "excess_rate", "main_mean_profit_yuan",
    "baseline_mean_profit_yuan", "profit_improvement_yuan",
    "main_excess_rate", "baseline_excess_rate", "main_top5_area_mass",
    "baseline_top5_area_mass", "main_lower_10pct_mean_profit_yuan",
    "baseline_lower_10pct_mean_profit_yuan", "main_p05_profit_yuan",
    "baseline_p05_profit_yuan", "plan_area_overlap", "mean_profit_change_yuan",
    "lower_tail_change_yuan", "q3_main_mean_profit_yuan",
    "q2_plan_mean_profit_under_q3_scenarios_yuan",
    "q3_main_lower_10pct_mean_profit_yuan", "q2_plan_lower_10pct_mean_profit_yuan",
    "q3_main_mean_excess_rate", "q2_plan_mean_excess_rate",
    "mean_profit_yuan", "std_profit_yuan", "p05_profit_yuan",
    "median_profit_yuan", "p95_profit_yuan", "lower_10pct_mean_profit_yuan",
    "mean_excess_jin", "mean_excess_rate"
  ]);
  return rows.map((values, rowIndex) => values.map((value, columnIndex) => {
    if (rowIndex === 0) return value.replace(/^\uFEFF/, "");
    const header = rows[0][columnIndex]?.replace(/^\uFEFF/, "");
    if (numericHeaders.has(header) && value !== "" && Number.isFinite(Number(value))) return Number(value);
    if (value === "true") return true;
    if (value === "false") return false;
    return value;
  }));
}

function columnName(index) {
  let value = index + 1;
  let name = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name;
}

function styleDataSheet(sheet, rows, tableName) {
  if (!rows.length) return;
  const rowCount = rows.length;
  const colCount = rows[0].length;
  const lastCol = columnName(colCount - 1);
  const used = sheet.getRange(`A1:${lastCol}${rowCount}`);
  const headers = rows[0];
  const displayRows = [headers.map((header) => String(header).replaceAll("_", " ")), ...rows.slice(1)];
  used.values = displayRows;
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  sheet.getRange(`A1:${lastCol}1`).format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    rowHeight: 60,
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange(`A2:${lastCol}${rowCount}`).format.borders = {
    preset: "inside",
    style: "thin",
    color: "#E5E7EB",
  };
  headers.forEach((header, index) => {
    const range = sheet.getRange(`${columnName(index)}2:${columnName(index)}${rowCount}`);
    if (header.includes("yuan")) range.format.numberFormat = "#,##0.00";
    if (header.includes("rate") || header.includes("mass") || header.includes("overlap")) range.format.numberFormat = "0.00%";
    if (header.includes("area_mu")) range.format.numberFormat = "0.00";
    if (header.includes("jin")) range.format.numberFormat = "#,##0.00";
  });
  used.format.autofitColumns();
  used.format.autofitRows();
  sheet.getRange(`A1:${lastCol}1`).format.rowHeight = 60;
  headers.forEach((header, index) => {
    const col = sheet.getRange(`${columnName(index)}:${columnName(index)}`);
    if (["plot_id", "season", "land_type", "crop_name", "crop_type"].includes(header)) col.format.columnWidth = 14;
    else if (String(header).length > 18) col.format.columnWidth = 28;
    else if (header.includes("profit") || header.includes("revenue") || header.includes("cost")) col.format.columnWidth = 20;
    else col.format.columnWidth = Math.min(18, Math.max(10, String(header).length + 2));
  });
  const table = sheet.tables.add(`A1:${lastCol}${rowCount}`, true, tableName);
  table.style = "TableStyleMedium2";
  table.showBandedColumns = false;
  table.showFilterButton = true;
}

async function addCsvSheet(workbook, name, relativePath, tableName) {
  const text = await fs.readFile(path.join(projectRoot, relativePath), "utf8");
  const rows = parseCsv(text);
  const sheet = workbook.worksheets.add(name);
  styleDataSheet(sheet, rows, tableName);
  return { sheet, rows };
}

function populateInfoSheet(sheet, config, planRows, warningRows) {
  sheet.showGridLines = false;
  sheet.getRange("A1:F1").merge();
  sheet.getRange("A1").values = [[config.title]];
  sheet.getRange("A1:F1").format = {
    fill: "#17365D",
    font: { bold: true, color: "#FFFFFF", size: 18 },
    rowHeight: 34,
    horizontalAlignment: "left",
    verticalAlignment: "center",
  };
  const info = [
    ["题目", config.question],
    ["方案", config.method],
    ["求解状态", config.status],
    ["随机种子", 20240902],
    ["方案记录数", null],
    ["累计种植面积/亩", null],
    ["输出说明", config.outputNote],
  ];
  sheet.getRange("A3:B9").values = info;
  for (let row = 3; row <= 9; row += 1) sheet.getRange(`B${row}:F${row}`).merge();
  sheet.getRange("A3:A9").format = { fill: "#D9EAF7", font: { bold: true, color: "#17365D" } };
  sheet.getRange("B3:B9").format = { fill: "#F7FAFC", wrapText: true };
  sheet.getRange("B3:F9").format = { fill: "#F7FAFC", wrapText: true, verticalAlignment: "center" };
  sheet.getRange("A3:F9").format.rowHeight = 28;
  sheet.getRange("A4:F4").format.rowHeight = 44;
  sheet.getRange("A9:F9").format.rowHeight = 40;
  const planLastRow = planRows.length;
  sheet.getRange("B7").formulas = [[`=COUNTA('种植方案'!$A$2:$A$${planLastRow})`]];
  const plantedAreaColumn = columnName(planRows[0].indexOf("planted_area_mu"));
  sheet.getRange("B8").formulas = [[`=SUM('种植方案'!$${plantedAreaColumn}$2:$${plantedAreaColumn}$${planLastRow})`]];
  sheet.getRange("B8").format.numberFormat = "#,##0.00";
  sheet.getRange("A11:F11").merge();
  sheet.getRange("A11").values = [["重要限制与警告"]];
  sheet.getRange("A11:F11").format = { fill: "#F4B183", font: { bold: true, color: "#7F2704" } };
  const warnings = warningRows.map((value, index) => [`${index + 1}. ${value}`]);
  if (warnings.length) {
    sheet.getRange(`A12:F${11 + warnings.length}`).merge(true);
    sheet.getRange(`A12:A${11 + warnings.length}`).values = warnings;
    sheet.getRange(`A12:F${11 + warnings.length}`).format = { fill: "#FFF2CC", wrapText: true, rowHeight: 32, font: { color: "#7F6000" } };
  }
  sheet.getRange("A3:A20").format.columnWidth = 20;
  sheet.getRange("B3:F20").format.columnWidth = 18;
  sheet.freezePanes.freezeRows(1);
}

async function buildWorkbook(config) {
  const workbook = Workbook.create();
  const planText = await fs.readFile(path.join(projectRoot, config.plan), "utf8");
  const planRows = parseCsv(planText);
  const infoSheet = workbook.worksheets.add("说明");
  const planSheet = workbook.worksheets.add("种植方案");
  styleDataSheet(planSheet, planRows, `${config.id}PlanTable`);
  populateInfoSheet(infoSheet, config, planRows, config.warnings);
  for (const sheetConfig of config.extraSheets) {
    await addCsvSheet(workbook, sheetConfig.name, sheetConfig.path, `${config.id}${sheetConfig.table}`);
  }
  const infoInspect = await workbook.inspect({ kind: "table", sheetId: "说明", range: "A1:F20", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 6 });
  const planInspect = await workbook.inspect({ kind: "table", sheetId: "种植方案", range: `A1:I${Math.min(planRows.length, 12)}`, include: "values,formulas", tableMaxRows: 12, tableMaxCols: 9 });
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: `${config.id} formula error scan` });
  await fs.writeFile(path.join(previewDir, `${config.id}_inspect.txt`), `${infoInspect.ndjson}\n${planInspect.ndjson}\n${errors.ndjson}`, "utf8");
  const preview = await workbook.render({ sheetName: "说明", autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, `${config.id}_summary.png`), new Uint8Array(await preview.arrayBuffer()));
  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(path.join(outputDir, config.filename));
}


await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const q1Warnings = [
  "本结果为满足全部硬约束的滚动窗口可行近似解，不应表述为已证明的全局最优。",
  "Q1 最大窗口 MIP gap 为 48.86%，备用方法触发条件已成立。",
  "智慧大棚第一季缺少独立经济参数，暂复用附件中智慧大棚第二季参数。",
  "未使用附件3模板；本工作簿采用自设计的长表结构。",
];
const q2Warnings = [
  "使用30个轻量情景和固定随机种子20240902；超产部分按正常售价的50%销售。",
  "全部滚动窗口 MIP gap 低于5%，但情景分布仍是题面范围内的模拟假设。",
  "智慧大棚第一季暂复用第二季经济参数。",
];
const q3Warnings = [
  "替代、互补和相关结构均为模拟设定，不是从单年附件数据估计得到。",
  "Q3主方案在测试相关情景中低于Q2基线方案，备用触发条件已成立；请同时查看Q2基线方案和比较表。",
  "关系强度0.5×、1.0×、1.5×仅用于敏感性分析，不能解释为真实相关系数。",
];

const configs = [
  {
    id: "Result11", filename: "result1_1.xlsx", title: "问题1（1）：超产滞销浪费种植方案",
    question: "Q1 情形（1）", method: "三年展望、两年提交的滚动MILP；显式提高浪费规避优先级",
    status: "硬约束通过；可行近似解；备用触发", outputNote: "2024—2030逐地块、逐季、逐作物种植面积",
    plan: "results/Q1/experiments/round1/tables/result1_1_main.csv", warnings: q1Warnings,
    extraSheets: [
      { name: "年度指标", path: "results/Q1/experiments/round1/tables/result1_1_main_annual_metrics.csv", table: "Annual" },
      { name: "基线方案", path: "results/Q1/experiments/round1/tables/result1_baseline.csv", table: "Baseline" },
      { name: "方法对比", path: "results/Q1/experiments/round1/tables/comparison.csv", table: "Compare" },
    ],
  },
  {
    id: "Result12", filename: "result1_2.xlsx", title: "问题1（2）：超产部分半价销售种植方案",
    question: "Q1 情形（2）", method: "三年展望、两年提交的滚动MILP；超产按50%价格销售",
    status: "硬约束通过；可行近似解；备用触发", outputNote: "2024—2030逐地块、逐季、逐作物种植面积",
    plan: "results/Q1/experiments/round1/tables/result1_2_main.csv", warnings: q1Warnings,
    extraSheets: [
      { name: "年度指标", path: "results/Q1/experiments/round1/tables/result1_2_main_annual_metrics.csv", table: "Annual" },
      { name: "基线方案", path: "results/Q1/experiments/round1/tables/result1_baseline.csv", table: "Baseline" },
      { name: "方法对比", path: "results/Q1/experiments/round1/tables/comparison.csv", table: "Compare" },
    ],
  },
  {
    id: "Result2", filename: "result2.xlsx", title: "问题2：不确定性与风险下的种植方案",
    question: "Q2", method: "独立情景随机滚动MILP + 下行风险项；30个情景",
    status: "硬约束通过；全部窗口gap低于5%", outputNote: "2024—2030风险平衡种植面积；超产按50%价格销售",
    plan: "results/Q2/experiments/round1/tables/result2_main.csv", warnings: q2Warnings,
    extraSheets: [
      { name: "情景年度指标", path: "results/Q2/experiments/round1/tables/main_scenario_annual_metrics.csv", table: "Scenario" },
      { name: "均值基线方案", path: "results/Q2/experiments/round1/tables/result2_baseline.csv", table: "Baseline" },
      { name: "方法对比", path: "results/Q2/experiments/round1/tables/comparison.csv", table: "Compare" },
    ],
  },
  {
    id: "Result3", filename: "result3.xlsx", title: "问题3：相关性、替代性与互补性模拟方案",
    question: "Q3", method: "类别中等相关情景随机滚动MILP；关系强度±50%敏感性",
    status: "硬约束通过；主方案低于Q2基线；备用触发", outputNote: "Q3相关情景方案、Q2基线方案及比较分析",
    plan: "results/Q3/experiments/round1/tables/result3_main.csv", warnings: q3Warnings,
    extraSheets: [
      { name: "Q2基线方案", path: "results/Q3/experiments/round1/tables/result3_baseline_q2_plan.csv", table: "Baseline" },
      { name: "Q2与Q3比较", path: "results/Q3/experiments/round1/tables/comparison_q2_q3.csv", table: "Compare" },
      { name: "关系强度敏感性", path: "results/Q3/experiments/round1/tables/relationship_sensitivity_summary.csv", table: "Sensitivity" },
      { name: "相关情景年度指标", path: "results/Q3/experiments/round1/tables/main_correlated_scenario_annual_metrics.csv", table: "Scenario" },
    ],
  },
];

for (const config of configs) {
  await buildWorkbook(config);
}

console.log(JSON.stringify(configs.map(config => path.join(outputDir, config.filename)), null, 2));
