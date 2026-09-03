from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECTION_DIR = ROOT / "paper" / "sections"
TARGET = ROOT / "paper" / "main.md"

parts = []
for path in sorted(SECTION_DIR.glob("*.md")):
    parts.append(path.read_text(encoding="utf-8").strip())
TARGET.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
print(TARGET)
