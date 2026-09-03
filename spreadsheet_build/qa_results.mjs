import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";


const projectRoot = path.resolve(".");
const outputDir = path.join(projectRoot, "outputs", "24c_modeling");
const qaDir = path.join(projectRoot, "spreadsheet_build", "qa");
await fs.mkdir(qaDir, { recursive: true });

const workbooks = [
  { file: "result1_1.xlsx", sheets: ["说明", "种植方案", "年度指标", "基线方案", "方法对比"] },
  { file: "result1_2.xlsx", sheets: ["说明", "种植方案", "年度指标", "基线方案", "方法对比"] },
  { file: "result2.xlsx", sheets: ["说明", "种植方案", "情景年度指标", "均值基线方案", "方法对比"] },
  { file: "result3.xlsx", sheets: ["说明", "种植方案", "Q2基线方案", "Q2与Q3比较", "关系强度敏感性", "相关情景年度指标"] },
];

const report = [];
for (const config of workbooks) {
  const input = await FileBlob.load(path.join(outputDir, config.file));
  const workbook = await SpreadsheetFile.importXlsx(input);
  const sheetInspect = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 5000 });
  const formulaErrors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
    summary: `${config.file} formula error scan`,
  });
  await fs.writeFile(path.join(qaDir, `${config.file}.inspect.txt`), `${sheetInspect.ndjson}\n${formulaErrors.ndjson}`, "utf8");
  for (const sheetName of config.sheets) {
    const range = sheetName === "说明" ? "A1:F18" : "A1:I25";
    const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
    const safeName = sheetName.replaceAll(/[\\/:*?"<>|]/g, "_");
    await fs.writeFile(path.join(qaDir, `${config.file}_${safeName}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
  report.push({ file: config.file, sheets: config.sheets.length, rendered: config.sheets.length, formulaScan: formulaErrors.ndjson });
}

await fs.writeFile(path.join(qaDir, "qa_report.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify(report.map(item => ({ file: item.file, renderedSheets: item.rendered })), null, 2));
