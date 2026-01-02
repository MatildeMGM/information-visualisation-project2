import re
import pandas as pd
import altair as alt
import streamlit as st
from pathlib import Path
from vega_datasets import data

st.set_page_config(page_title="Project 2 — Final visualization (Q1–Q6)", layout="wide")

COL_TOTAL = "#4C78A8"
COL_TERM = "#E45756"
COL_BG = "#F3F4F6"

VALID_STATES = set([
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS",
    "KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY",
    "NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV",
    "WI","WY","DC"
])

STATE_ABBR_TO_NAME = {
    "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California","CO":"Colorado",
    "CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia","HI":"Hawaii","ID":"Idaho",
    "IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky","LA":"Louisiana",
    "ME":"Maine","MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota",
    "MS":"Mississippi","MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada",
    "NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico","NY":"New York",
    "NC":"North Carolina","ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon",
    "PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota",
    "TN":"Tennessee","TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington",
    "WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia"
}


def coerce_terminated_flag(s: pd.Series) -> pd.Series:
    return (
        (s == True)
        | (s == 1)
        | (s.astype(str).str.strip().str.lower().isin(
            ["true", "t", "1", "yes", "y", "terminated", "cancelled", "canceled"]
        ))
    )


@st.cache_data
def load_data(repo_root: Path) -> pd.DataFrame:
    data_dir = repo_root / "data"

    yearly_files = sorted(data_dir.glob("nsf_grants_*.csv"))
    yearly_files = [p for p in yearly_files if "all_merged" not in p.name]

    if len(yearly_files) == 0:
        raise FileNotFoundError("No yearly files found matching data/nsf_grants_*.csv")

    frames = []
    for p in yearly_files:
        df_y = pd.read_csv(p)

        # FIX: robust year extraction even for filenames like "nsf_grants_2022 (2).csv"
        m = re.search(r"(20\d{2})", p.stem)
        year = int(m.group(1)) if m else None
        if year is None:
            continue

        df_y["year"] = year
        frames.append(df_y)

    df = pd.concat(frames, ignore_index=True)

    if "inst_state_code" not in df.columns:
        raise KeyError("Expected column 'inst_state_code' in the nsf_grants_*.csv files")
    if "awd_id" not in df.columns:
        raise KeyError("Expected column 'awd_id' in the nsf_grants_*.csv files")

    df = df.dropna(subset=["awd_id", "inst_state_code"]).copy()
    df = df[df["inst_state_code"].isin(VALID_STATES)].copy()
    df["state_x"] = df["inst_state_code"].astype(str).str.upper()
    df["awd_id"] = df["awd_id"].astype(str)

    output_path = data_dir / "output.csv"
    df_output = pd.read_csv(output_path)
    df_output = df_output.rename(columns={"grant_id": "awd_id", "org_state": "state"})
    df_output["awd_id"] = df_output["awd_id"].astype(str)

    if "status" not in df_output.columns:
        raise KeyError("Expected column 'status' in output.csv")

    df_merged = df.merge(df_output[["awd_id", "status", "state"]], on="awd_id", how="left")
    df_merged["status"] = df_merged["status"].fillna(False)

    # FIX: make status Arrow-safe (pure boolean) to avoid pyarrow conversion errors
    df_merged["status"] = coerce_terminated_flag(df_merged["status"]).astype(bool)

    return df_merged


@st.cache_data
def load_capitals() -> pd.DataFrame:
    cap = pd.read_json(data.us_state_capitals.url)

    rename_map = {}
    if "latitude" in cap.columns and "lat" not in cap.columns:
        rename_map["latitude"] = "lat"
    if "longitude" in cap.columns and "lon" not in cap.columns:
        rename_map["longitude"] = "lon"
    if rename_map:
        cap = cap.rename(columns=rename_map)

    needed = ["state", "lat", "lon"]
    missing = [c for c in needed if c not in cap.columns]
    if missing:
        raise KeyError(f"us_state_capitals is missing required columns: {missing}")

    return cap


@st.cache_data
def build_state_year(df_merged: pd.DataFrame) -> pd.DataFrame:
    df = df_merged.copy()
    df["state_x"] = df["state_x"].astype(str).str.upper()
    df["state_name"] = df["state_x"].map(STATE_ABBR_TO_NAME)

    out = (
        df.dropna(subset=["year", "state_name"])
        .groupby(["year", "state_name", "state_x"], as_index=False)
        .agg(
            n_grants=("awd_id", "count"),
            total_amount=("awd_amount", "sum")
        )
    )

    return out


@st.cache_data
def build_dir_year_merged(df_merged: pd.DataFrame) -> pd.DataFrame:
    needed = ["year", "dir_abbr", "awd_amount", "status"]
    missing = [c for c in needed if c not in df_merged.columns]
    if missing:
        raise KeyError("df_merged missing columns for Q2/Q3: " + ", ".join(missing))

    df = df_merged.copy()
    df["is_term"] = coerce_terminated_flag(df["status"])

    if "org_dir_long_name" not in df.columns:
        df["org_dir_long_name"] = df["dir_abbr"]

    total = (
        df.groupby(["year", "dir_abbr", "org_dir_long_name"], as_index=False)
        .agg(n_grants=("awd_id", "count"), total_amount=("awd_amount", "sum"))
    )

    term = (
        df[df["is_term"]]
        .groupby(["year", "dir_abbr", "org_dir_long_name"], as_index=False)
        .agg(n_term=("awd_id", "count"), term_amount=("awd_amount", "sum"))
    )

    out = total.merge(term, on=["year", "dir_abbr", "org_dir_long_name"], how="left")
    out["n_term"] = out["n_term"].fillna(0)
    out["term_amount"] = out["term_amount"].fillna(0)

    return out


def render_global_legend():
    st.markdown(
        f"""
        <div style="padding: 6px 0 10px 0;">
          <div style="display: flex; align-items: center; gap: 10px; margin: 6px 0;">
            <span style="width: 14px; height: 14px; border-radius: 50%; background: {COL_TOTAL}; display: inline-block;"></span>
            <span style="font-size: 14px;">Total / Active</span>
          </div>

          <div style="display: flex; align-items: center; gap: 10px; margin: 6px 0;">
            <span style="width: 14px; height: 14px; border-radius: 50%; background: {COL_TERM}; display: inline-block;"></span>
            <span style="font-size: 14px;">Terminated / Cancelled</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def chart_q1(state_year: pd.DataFrame, year: int, selected_state: str) -> alt.Chart:
    states_topo = alt.topo_feature(data.us_10m.url, "states")

    # --- base map (set width+height so overlay coords behave) ---
    base_map = (
        alt.Chart(states_topo)
        .mark_geoshape(fill=COL_BG, stroke="white")
        .project(type="albersUsa")
        .properties(width=420, height=260)
    )

    # --- bubble map data (NOW reacts to state filter) ---
    q1_base = alt.Chart(state_year).transform_filter(alt.datum.year == year)

    if selected_state != "All":
        q1_base = q1_base.transform_filter(f"datum.state_x == '{selected_state}'")

    q1_base = (
        q1_base
        .transform_lookup(
            lookup="state_name",
            from_=alt.LookupData(data.us_state_capitals.url, key="state", fields=["lat", "lon"])
        )
        .transform_filter(alt.datum.lat != None)
    )

    points = (
        q1_base
        .mark_circle(opacity=0.85, stroke="black", strokeWidth=0.4)
        .encode(
            longitude="lon:Q",
            latitude="lat:Q",
            size=alt.Size("n_grants:Q", scale=alt.Scale(range=[40, 1000]), legend=None),
            color=alt.Color("n_grants:Q", scale=alt.Scale(range=[COL_BG, "#AFC6D9", COL_TOTAL]), legend=None),
            tooltip=[
                alt.Tooltip("state_name:N", title="State"),
                alt.Tooltip("state_x:N", title="Abbr"),
                alt.Tooltip("year:O", title="Year"),
                alt.Tooltip("n_grants:Q", title="# Grants"),
                alt.Tooltip("total_amount:Q", title="Total amount", format=",.0f"),
            ]
        )
    )

    q1_map = (base_map + points)

    # --- bubble legend (visible inside chart; no negative x so it won't clip) ---
    legend_ticks = [0, 250, 400, 800, 1000]
    legend_df = pd.DataFrame({"n_grants": legend_ticks})
# Legend positioning (recommended)
    LEG_X   = -55     # flyt hele boblelegenden tydeligt til venstre
    TITLE_X = -75     # titel lidt længere til venstre end boblerne
    LABEL_DX = 22     # god afstand mellem boble og tekst

    LEG_Y0 = 45       # lidt længere nede for luft under titlen
    STEP  = 35        # mere luft mellem boblerne


    legend_title = (
        alt.Chart(pd.DataFrame({"t": ["Number of grants"]}))
        .mark_text(align="left", fontSize=11, fontWeight="bold")
        .encode(x=alt.value(LEG_X), y=alt.value(22), text="t:N")
    )

    legend_bubbles = (
        alt.Chart(legend_df)
        .transform_window(idx="row_number()")
        .transform_calculate(y_pos=f"{LEG_Y0} + (datum.idx-1)*{STEP}")
        .mark_circle(opacity=0.95)
        .encode(
            x=alt.value(LEG_X),
            y=alt.Y("y_pos:Q", axis=None, scale=None),
            size=alt.Size("n_grants:Q", scale=alt.Scale(range=[40, 1000]), legend=None),
            color=alt.Color("n_grants:Q", scale=alt.Scale(range=[COL_BG, "#AFC6D9", COL_TOTAL]), legend=None),
        )
    )

    legend_labels = (
        alt.Chart(legend_df)
        .transform_window(idx="row_number()")
        .transform_calculate(y_pos=f"{LEG_Y0} + (datum.idx-1)*{STEP}")
        .mark_text(align="left", dx=32, fontSize=10)
        .encode(
            x=alt.value(LEG_X),
            y=alt.Y("y_pos:Q", axis=None, scale=None),
            text=alt.Text("n_grants:Q", format=",")
        )
    )

    return alt.layer(q1_map, legend_title, legend_bubbles, legend_labels).properties(width=420, height=260)



def chart_q23(dir_year_merged: pd.DataFrame, year: int, selected_dir: str, show_total: bool, show_term: bool) -> alt.Chart:

    chart_height = 260
    bubble_y = chart_height * 0.3

    bubbles = (
        alt.Chart(dir_year_merged)
        .transform_filter(alt.datum.year == year).transform_filter("'%s' == 'All' || datum.dir_abbr == '%s'" % (selected_dir, selected_dir))

        .mark_circle()
        .encode(
            x=alt.X("dir_abbr:N", title="Directorate"),
            y=alt.value(bubble_y),
            size=alt.Size("n_grants:Q", scale=alt.Scale(type="sqrt", range=[250, 1500]), legend=None),
            color=alt.value(COL_TOTAL),
            opacity=alt.value(1.0 if show_total else 0.0),
            tooltip=[
                alt.Tooltip("org_dir_long_name:N", title="Directorate"),
                alt.Tooltip("dir_abbr:N", title="Abbr"),
                alt.Tooltip("year:O", title="Year"),
                alt.Tooltip("n_grants:Q", title="Grants"),
                alt.Tooltip("total_amount:Q", title="Total amount", format=",.0f"),
            ]
        )
        .properties(height=chart_height)
    )

    term_bars = (
        alt.Chart(dir_year_merged)
        .transform_filter(alt.datum.year == year)
        .transform_filter("datum.n_term > 0")
        .mark_bar()
        .encode(
            x=alt.X("dir_abbr:N", title="Directorate"),
            y=alt.Y("n_term:Q", title="Terminated grants"),
            color=alt.value(COL_TERM),
            opacity=alt.value(0.75 if show_term else 0.0),
            tooltip=[
                alt.Tooltip("org_dir_long_name:N", title="Directorate"),
                alt.Tooltip("dir_abbr:N", title="Abbr"),
                alt.Tooltip("year:O", title="Year"),
                alt.Tooltip("n_term:Q", title="Terminated grants"),
                alt.Tooltip("term_amount:Q", title="Terminated amount", format=",.0f"),
            ],
        )
        .properties(height=chart_height)
    )

    text = (
        alt.Chart(dir_year_merged)
        .transform_filter(alt.datum.year == year)
        .mark_text(dy=3, fontSize=10, color="white")
        .encode(
            x="dir_abbr:N",
            y=alt.value(bubble_y),
            text="n_grants:Q",
            opacity=alt.value(1.0 if show_total else 0.0),
        )
        .properties(height=chart_height)
    )

    return alt.layer(term_bars, bubbles, text)


def chart_q4(df_merged: pd.DataFrame, year_selected: int) -> alt.Chart:
    df = df_merged.copy()

    if "awd_eff_date" not in df.columns:
        raise KeyError("df_merged must contain 'awd_eff_date' for Q4.")
    df["awd_eff_date"] = pd.to_datetime(df["awd_eff_date"], errors="coerce")

    df["month_date"] = df["awd_eff_date"].dt.to_period("M").dt.to_timestamp()
    df["year_m"] = df["month_date"].dt.year.astype("Int64")
    df = df[(df["year_m"] >= 2021) & (df["year_m"] <= 2025)]

    df_q4m = (
        df.dropna(subset=["month_date", "awd_amount", "year_m"])
        .groupby(["year_m", "month_date"], as_index=False)
        .agg(total_amount=("awd_amount", "sum"))
    )

    all_years = sorted(df_q4m["year_m"].dropna().unique().tolist())
    full_grid = []
    for y in all_years:
        months_y = pd.date_range(f"{int(y)}-01-01", f"{int(y)}-12-01", freq="MS")
        full_grid.append(pd.DataFrame({"year_m": int(y), "month_date": months_y}))
    full_grid = pd.concat(full_grid, ignore_index=True)

    df_full = full_grid.merge(df_q4m, on=["year_m", "month_date"], how="left").fillna({"total_amount": 0})
    df_full["total_amount_musd"] = df_full["total_amount"] / 1_000_000

    zoom = alt.selection_interval(bind="scales", encodings=["x"], name="ZoomQ4")

    base = alt.Chart(df_full)

    highlight = (
        base.transform_filter(alt.datum.year_m == year_selected)
        .mark_area(opacity=0.12, color=COL_TOTAL)
        .encode(x="month_date:T", y="total_amount_musd:Q")
    )

    line = (
        base.mark_line(point=True, color=COL_TOTAL)
        .encode(
            x=alt.X("month_date:T", title="", axis=alt.Axis(format="%b", labelAngle=0, grid=False)),
            y=alt.Y("total_amount_musd:Q", title="Total amount (M USD)", axis=alt.Axis(format=",.0f")),
            tooltip=[
                alt.Tooltip("month_date:T", title="Month", format="%Y-%m"),
                alt.Tooltip("total_amount_musd:Q", title="Amount (M USD)", format=",.0f"),
            ],
        )
        .add_params(zoom)   # FIX: Altair v5
    )

    year_lines = (
        base.transform_filter("month(datum.month_date) == 0")
        .mark_rule(color="lightgray")
        .encode(x="month_date:T")
    )

    return (highlight + line + year_lines).properties(height=200)


def chart_q5(df_merged: pd.DataFrame, selected_state: str, show_term: bool) -> alt.Chart:
    df = df_merged.copy()

    df["awd_eff_date"] = pd.to_datetime(df["awd_eff_date"], errors="coerce")
    df = df.dropna(subset=["awd_eff_date", "state_x", "awd_id"])

    df["month_date"] = df["awd_eff_date"].dt.to_period("M").dt.to_timestamp()
    df["year_m"] = df["month_date"].dt.year.astype(int)
    df = df[(df["year_m"] >= 2021) & (df["year_m"] <= 2025)]

    df["is_term"] = coerce_terminated_flag(df["status"])

    tot = df.groupby(["state_x", "month_date"], as_index=False).agg(n_grants=("awd_id", "count"))
    term = df[df["is_term"]].groupby(["state_x", "month_date"], as_index=False).agg(n_term=("awd_id", "count"))

    df_q5m = tot.merge(term, on=["state_x", "month_date"], how="left").fillna({"n_term": 0})

    states = sorted(df_q5m["state_x"].dropna().unique().tolist())
    months = pd.date_range("2021-01-01", "2025-12-01", freq="MS")
    full_grid = pd.MultiIndex.from_product([states, months], names=["state_x", "month_date"]).to_frame(index=False)

    df_full = full_grid.merge(df_q5m, on=["state_x", "month_date"], how="left").fillna({"n_grants": 0, "n_term": 0})

    if selected_state != "All":
        df_full = df_full[df_full["state_x"] == selected_state]

    agg = (
        df_full.groupby("month_date", as_index=False)
        .agg(n_grants=("n_grants", "sum"), n_term=("n_term", "sum"))
    )

    zoom = alt.selection_interval(bind="scales", encodings=["x"], name="ZoomQ5")
    month_ticks = months.tolist()

    line = (
        alt.Chart(agg)
        .mark_line(color=COL_TOTAL)
        .encode(
            x=alt.X("month_date:T", title="", axis=alt.Axis(values=month_ticks, format="%b", labelAngle=0, grid=False)),
            y=alt.Y("n_grants:Q", title="# grants", axis=alt.Axis(format=",.0f")),
            tooltip=[
                alt.Tooltip("month_date:T", title="Month", format="%Y-%m"),
                alt.Tooltip("n_grants:Q", title="# grants", format=",.0f"),
                alt.Tooltip("n_term:Q", title="# terminated", format=",.0f"),
            ],
        )
        .add_params(zoom)  # FIX: Altair v5
    )

    points = (
        alt.Chart(agg)
        .mark_point(size=35, color=COL_TOTAL)
        .encode(x="month_date:T", y=alt.Y("n_grants:Q", axis=None))
    )

    bars = (
        alt.Chart(agg[agg["n_term"] > 0])
        .mark_bar(color=COL_TERM)
        .encode(
            x="month_date:T",
            y=alt.Y("n_term:Q", title="# terminated", axis=alt.Axis(orient="right", format=",.0f")),
            opacity=alt.value(0.75 if show_term else 0.0),
        )
    )

    return (bars + line + points).resolve_scale(y="independent").properties(
        height=220,
    )


def chart_q6(df_merged: pd.DataFrame, year: int, directorate: str, selected_state: str) -> alt.Chart:
    required = ["n_pi", "awd_amount", "status", "awd_id", "inst_name",
                "inst_state_code", "dir_abbr", "year"]
    missing = [c for c in required if c not in df_merged.columns]
    if missing:
        raise KeyError("df_merged missing columns for Q6: " + ", ".join(missing))

    df = df_merged.copy()
    df["awd_amount"] = pd.to_numeric(df["awd_amount"], errors="coerce")
    df["n_pi"] = pd.to_numeric(df["n_pi"], errors="coerce")
    df["inst_state_code"] = df["inst_state_code"].astype(str).str.upper()

    df["status_label"] = df["status"].map({True: "Cancelled", False: "Active"}).fillna("Unknown")

    base = (
        alt.Chart(df)
        .transform_filter(alt.datum.year == year)
        .transform_filter(alt.datum.awd_amount != None)
        .transform_filter(alt.datum.n_pi != None)
        .transform_filter(alt.datum.awd_amount > 0)
        .transform_filter(alt.datum.n_pi >= 1)
        .transform_filter(alt.datum.n_pi <= 15)
    )

  
    if directorate != "All":
        base = base.transform_filter(f"datum.dir_abbr == '{directorate}'")

    if selected_state != "All":
        base = base.transform_filter(f"datum.inst_state_code == '{selected_state}'")

    base = base.transform_calculate(x_jitter="datum.n_pi + (random() - 0.5) * 0.25")

    return (
        base.mark_circle(opacity=0.25, size=18)
        .encode(
            x=alt.X("x_jitter:Q", title="Number of PIs"),
            y=alt.Y(
                "awd_amount:Q",
                title="Award amount (USD, log)",
                scale=alt.Scale(type="log", nice=False),
                axis=alt.Axis(format="~s", tickCount=6),
            ),
            color=alt.Color(
                "status_label:N",
                scale=alt.Scale(
                    domain=["Active", "Cancelled", "Unknown"],
                    range=[COL_TOTAL, COL_TERM, "#9CA3AF"],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("awd_id:N", title="Award ID"),
                alt.Tooltip("inst_name:N", title="Institution"),
                alt.Tooltip("inst_state_code:N", title="State"),
                alt.Tooltip("dir_abbr:N", title="Directorate"),
                alt.Tooltip("year:O", title="Year"),
                alt.Tooltip("n_pi:Q", title="Number of PIs"),
                alt.Tooltip("awd_amount:Q", title="Award amount", format=",.0f"),
                alt.Tooltip("status_label:N", title="Status"),
            ],
        )
        .properties(height=300)
    )


st.title("Project 2 — Final visualization (Q1–Q6)")

REPO_ROOT = Path(__file__).resolve().parents[1]



df_merged = load_data(REPO_ROOT)
_ = load_capitals()

state_year = build_state_year(df_merged)
dir_year_merged = build_dir_year_merged(df_merged)

years = sorted(pd.Series(df_merged["year"]).dropna().astype(int).unique().tolist())
dirs = sorted(pd.Series(df_merged["dir_abbr"]).dropna().astype(str).unique().tolist())
states = ["All"] + sorted(pd.Series(df_merged["state_x"]).dropna().astype(str).unique().tolist())

st.sidebar.header("Filters")

selected_year = st.sidebar.selectbox("Year", options=years, index=len(years) - 1)

# Defaults to "All"
selected_state = st.sidebar.selectbox("State", options=states, index=0)

# Defaults to "All"
dirs_ui = ["All"] + dirs
selected_dir = st.sidebar.selectbox("Directorate", options=dirs_ui, index=0)

show_total = st.sidebar.checkbox("Show total (blue)", value=True)
show_term = st.sidebar.checkbox("Show terminated (red)", value=True)

left, right = st.columns(2, gap="large")

with left:
    st.subheader("Q1 — Grants per state")
    st.altair_chart(chart_q1(state_year, selected_year, selected_state), width="stretch")


    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    st.subheader("Q4 — Total amount per month (2021–2025) (drag to zoom)")
    st.altair_chart(chart_q4(df_merged, selected_year), width="stretch")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    st.subheader("Q5 — Grants over time (state / All) + terminated bars (drag to zoom)")
    st.altair_chart(chart_q5(df_merged, selected_state, show_term), width="stretch")


with right:
    st.subheader("Legend (global)")
    render_global_legend()

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    st.subheader("Q2/Q3 — Grants & terminated per directorate")
    st.altair_chart(
        chart_q23(dir_year_merged, selected_year, selected_dir, show_total, show_term),
        width="stretch"
    )

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    st.subheader("Q6 — Award amount vs collaboration (Year + Directorate)")
    st.altair_chart(chart_q6(df_merged, selected_year, selected_dir, selected_state), width="stretch")



st.caption("This visualization was created by Matilde and Steffen as part of the Information Visualization course at UPC (2025). Data source: NSF Grants dataset.")
