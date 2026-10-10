# Odoo OEM Connect

Odoo 18 module that links a company's own product references to international OEM numbers, compatible vehicles, images and alternative parts, using the TecDoc data from the RapidAPI "Auto Parts Catalog" API (pay per call, one subscription per client).

Roadmap and architecture: see [PLAN.md](PLAN.md).

## Install (development)

1. Copy or symlink this folder into your Odoo addons path **named `rapidapi_bdeel`** (the folder name must match the module name).
2. Restart Odoo, update the apps list, install **Odoo OEM Connect**.
3. Settings > RapidAPI Settings: enter your RapidAPI key and host (`auto-parts-catalog.p.rapidapi.com`).

Depends on `product`, `stock`, `delivery`, `sale`, `website_sale`.

## OEM price matching script

`OEM-Price-matching-tool.py` is the original standalone script. It fuzzy-matches part names between the company's product export (`Bdeel_List.xlsx`) and a competitor list (`Nour.xlsx`) with RapidFuzz and writes `Mapped_OEM_Parts.xlsx`. It is being replaced by a matcher inside the module (see PLAN.md, phases 3b and 4).

```bash
pip install pandas rapidfuzz openpyxl
python OEM-Price-matching-tool.py
```

The sample spreadsheets are shared with permission for educational and research use only.

## License

OPL-1 for the module (see `__manifest__.py`); the repository LICENSE file covers the original script.
