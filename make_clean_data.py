import json
from pathlib import Path
import pandas as pd

#URL for data: https://www.nsf.gov/awardsearch/download-awards/
# ---------------------------------------------------------
# 1. Set base paths and detect all year folders
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent   # folder where this script is located
DATA_DIR = BASE_DIR / "data"

# Automatically detect all subfolders (e.g., "2021 (1)", "2022 (2)", etc.)
YEARS = [p.name for p in DATA_DIR.iterdir() if p.is_dir()]


# ---------------------------------------------------------
# 2. Function to extract relevant fields from a single JSON file
# ---------------------------------------------------------
def parse_grant_json(json_path: Path) -> dict:
    """Read a single NSF grant JSON file and return a flattened dict with selected fields."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    row = {}

    # --- simple top-level fields ---
    row["awd_id"] = data.get("awd_id")
    row["agcy_id"] = data.get("agcy_id")
    row["awd_titl_txt"] = data.get("awd_titl_txt")

    row["awd_eff_date"] = data.get("awd_eff_date")
    row["awd_exp_date"] = data.get("awd_exp_date")

    # extract year from effective date (for time-series plots)
    eff_date = data.get("awd_eff_date")
    if isinstance(eff_date, str) and len(eff_date) >= 4:
        row["year"] = int(eff_date[:4])
    else:
        row["year"] = None

    # amounts
    row["awd_amount"] = data.get("awd_amount")
    row["tot_intn_awd_amt"] = data.get("tot_intn_awd_amt")

    # NSF directorate / division
    row["dir_abbr"] = data.get("dir_abbr")
    row["org_dir_long_name"] = data.get("org_dir_long_name")
    row["div_abbr"] = data.get("div_abbr")
    row["org_div_long_name"] = data.get("org_div_long_name")

    # additional attribute (for Q6)
    row["cfda_num"] = data.get("cfda_num")

    # --- institution info ---
    inst = data.get("inst") or {}
    row["inst_name"] = inst.get("inst_name")
    row["inst_city_name"] = inst.get("inst_city_name")
    row["inst_state_code"] = inst.get("inst_state_code")
    row["inst_country_name"] = inst.get("inst_country_name")

    # --- performing institution ---
    perf = data.get("perf_inst") or {}
    row["perf_inst_name"] = perf.get("perf_inst_name")
    row["perf_city_name"] = perf.get("perf_city_name")
    row["perf_st_code"] = perf.get("perf_st_code")
    row["perf_ctry_name"] = perf.get("perf_ctry_name")

    # --- PI information ---
    pi_list = data.get("pi") or []
    row["n_pi"] = len(pi_list)
    if pi_list:
        first_pi = pi_list[0]
        row["pi_full_name"] = first_pi.get("pi_full_name")
        row["pi_email_addr"] = first_pi.get("pi_email_addr")
    else:
        row["pi_full_name"] = None
        row["pi_email_addr"] = None

    # --- program elements ---
    pgm_ele = data.get("pgm_ele") or []
    row["pgm_ele_codes"] = ";".join(str(e.get("pgm_ele_code", "")) for e in pgm_ele if e) or None
    row["pgm_ele_names"] = ";".join(str(e.get("pgm_ele_name", "")) for e in pgm_ele if e) or None

    # --- obligated funding info ---
    oblg_list = data.get("oblg_fy") or []
    if oblg_list:
        first_oblg = oblg_list[0]
        row["oblg_fy_year"] = first_oblg.get("fund_oblg_fiscal_yr")
        row["oblg_fy_amount"] = first_oblg.get("fund_oblg_amt")
    else:
        row["oblg_fy_year"] = None
        row["oblg_fy_amount"] = None

    return row


# ---------------------------------------------------------
# 3. Loop through all years, parse JSON files, and save one CSV per year
# ---------------------------------------------------------
def build_yearly_csvs():
    for year in YEARS:
        year_dir = DATA_DIR / year
        if not year_dir.exists():
            print(f"[WARNING] Folder {year_dir} does not exist, skipping.")
            continue

        print(f"Processing year folder: {year} in {year_dir} ...")

        rows = []

        # Loop over all JSON files in the year folder
        for json_path in sorted(year_dir.glob("*.json")):
            try:
                row = parse_grant_json(json_path)
                rows.append(row)
            except Exception as e:
                print(f"  Error in file {json_path.name}: {e}")

        if not rows:
            print(f"  No rows found for {year}, skipping CSV writing.")
            continue

        df = pd.DataFrame(rows)

        # Save as CSV in the data folder
        out_path = DATA_DIR / f"nsf_grants_{year}.csv"
        df.to_csv(out_path, index=False)
        print(f"  Wrote {len(df)} rows to {out_path}")


if __name__ == "__main__":
    build_yearly_csvs()
