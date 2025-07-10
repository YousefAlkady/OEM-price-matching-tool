# 🔧 Car Part OEM Matcher

This tool was developed upon request by Bdeel Auto to automate the process of comparing and mapping car part prices and OEM numbers between the internal Bdeel inventory and a competitor's price list (e.g., Nour). It uses fuzzy string matching to find equivalent parts, making pricing analysis and product alignment faster and more reliable.
---

## 🚀 Features

- ✅ Fuzzy matching using `RapidFuzz` for Arabic/English part names
- ✅ Matches parts with a similarity score ≥ 75%
- ✅ Skips irrelevant rows (e.g. ones containing "وش")
- ✅ Outputs a clean Excel sheet showing:
  - Matched product names
  - Bdeel and Rival OEM numbers
  - Price comparison
  - Match score for transparency

---

## 📁 Included Data

This repository contains:

- `data/Bdeel_list.xlsx` – Sample product list from Bdeel Company  
- `data/Nour.xlsx` – Sample product list from Nour Company  
- `Mapped_OEM_Parts.xlsx` – Auto-generated match report from the script

📌 **Permission Notice**:  
Both Bdeel and Nour have granted permission for their product list samples to be shared publicly for educational and research purposes only. OEMs and prices shown here are sample data reflecting real-world formatting.

---

## 📂 Input Format

### `Bdeel_list.xlsx`
| Name Arabic      | Internal Reference | Price |
|------------------|--------------------|-------|
| فلتر هواء هوندا | BDE123              | 120   |

### `Nour.xlsx`
| Name            | Code1   | Code2   | Price |
|----------------|---------|---------|-------|
| فلتر هواء هوندا | N123    | X456    | 135   |

---

## 📤 Output

`Mapped_OEM_Parts.xlsx` includes:

| Bdeel Part Name   | Nour           | OEM Number | Rival Code1 | Rival Code2 | Bdeel Price | Rival Price | Match Score |
|------------------|----------------|------------|-------------|-------------|--------------|-------------|-------------|

Skipped parts (e.g. those containing "وش") are included at the bottom with a `"Skipped"` label.

---

## ⚙️ How It Works

- Loads the Excel files using `pandas`
- Filters out noisy or unwanted rows
- Compares each Bdeel part name to all rival names using fuzzy matching
- Accepts only matches above a similarity threshold (default: 75)
- Outputs a result file with all matches and skipped items

---

## 🧪 How to Run

1. Clone the repo:
   ```bash
   git clone https://github.com/yourusername/car-part-oem-matcher.git
   cd car-part-oem-matcher
