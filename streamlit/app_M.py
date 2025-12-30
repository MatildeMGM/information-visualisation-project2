# -----------------------------
# Safety checks
# -----------------------------
required = ["df_merged", "state_year", "dir_year_merged"]
missing = [name for name in required if name not in globals()]

if missing:
    raise NameError(
        "Missing required dataframe(s): "
        + ", ".join(missing)
        + "\n\nYou must have these defined before running this cell:\n"
        + "- df_merged (award-level merged dataset)\n"
        + "- state_year (state-year aggregated for Q1)\n"
        + "- dir_year_merged (directorate-year aggregated for Q2/Q3)\n"
    )

# -----------------------------
# Global colors
# -----------------------------
COL_TOTAL = "#4C78A8"   # total / active
COL_TERM  = "#E45756"   # terminated / cancelled
COL_BG    = "#F3F4F6"   # neutral background

# -----------------------------
# Ensure year exists
# -----------------------------
if "year" not in df_merged.columns:
    if "awd_eff_date" not in df_merged.columns:
        raise KeyError(
            "df_merged must contain either 'year' or 'awd_eff_date' to derive year."
        )
    tmp_dates = pd.to_datetime(df_merged["awd_eff_date"], errors="coerce")
    df_merged["year"] = tmp_dates.dt.year

# -----------------------------
# Shared interactive parameters
# -----------------------------
years = sorted(pd.Series(df_merged["year"]).dropna().astype(int).unique().tolist())
if len(years) == 0:
    raise ValueError("No valid years found in df_merged['year'].")

year_param = alt.param(
    name="Year",
    value=years[-1],
    bind=alt.binding_select(options=years, name="Year: ")
)

# State selector (Q5)
if "state_x" not in df_merged.columns:
    raise KeyError("df_merged must contain 'state_x' for Q5.")
states = sorted(pd.Series(df_merged["state_x"]).dropna().unique().tolist())

state_param = alt.param(
    name="SelectedState",
    value="All",
    bind=alt.binding_select(options=["All"] + states, name="State: ")
)

# Directorate selector (Q6)
if "dir_abbr" not in df_merged.columns:
    raise KeyError("df_merged must contain 'dir_abbr' for Q6.")
dirs = sorted(pd.Series(df_merged["dir_abbr"]).dropna().unique().tolist())
if len(dirs) == 0:
    raise ValueError("No valid directorates found in df_merged['dir_abbr'].")

dir_param = alt.param(
    name="Directorate",
    value=dirs[0],
    bind=alt.binding_select(options=dirs, name="Directorate: ")
)

# Toggles (Q2/Q3 + Q5)
show_total = alt.param(
    name="ShowTotal",
    value=True,
    bind=alt.binding_checkbox(name="Show total (blue)")
)

show_term = alt.param(
    name="ShowTerminated",
    value=True,
    bind=alt.binding_checkbox(name="Show terminated (red)")
)

# -----------------------------
# Global legend
# -----------------------------
legend_df = pd.DataFrame({
    "label": ["Total / Active", "Terminated / Cancelled"],
    "color": [COL_TOTAL, COL_TERM]
})

global_legend_points = (
    alt.Chart(legend_df)
    .mark_point(filled=True, size=130)
    .encode(
        x=alt.value(12),
        y=alt.Y(
            "label:N",
            sort=["Total / Active", "Terminated / Cancelled"],
            axis=None
        ),
        color=alt.Color("color:N", scale=None, legend=None),
        tooltip=[alt.Tooltip("label:N", title="Meaning")]
    )
    .properties(width=420, height=55, title="Legend (global)")
)

global_legend_text = (
    alt.Chart(legend_df)
    .mark_text(align="left", dx=10, fontSize=11)
    .encode(
        x=alt.value(22),
        y=alt.Y(
            "label:N",
            sort=["Total / Active", "Terminated / Cancelled"],
            axis=None
        ),
        text="label:N"
    )
    .properties(width=420, height=55)
)

legend_panel = global_legend_points + global_legend_text

# -----------------------------
# Base US map
# -----------------------------
states_topo = alt.topo_feature(data.us_10m.url, "states")
usChart = (
    alt.Chart(states_topo)
    .mark_geoshape(fill=COL_BG, stroke="white")
    .project(type="albersUsa")
    .properties(width=420, height=260)
)

# -----------------------------
# Q1 — State bubbles with custom legend
# -----------------------------
capitals = data.us_state_capitals.url
Q1_COLOR_RANGE = ["#F1F4F7", "#B5D5DB", "#78B8C4", "#2F7F94"]
SIZE_RANGE = [50, 1000]

LEGEND_X = -70
LEGEND_Y = 10
legend_ticks = [0, 250, 400, 800, 1000]

q1_base = (
    alt.Chart(state_year, title="NSF Grants per State and Year")
    .transform_filter(alt.datum.year == year_param)
    .transform_lookup(
        lookup="state_name",
        from_=alt.LookupData(capitals, key="state", fields=["lat", "lon"])
    )
    .transform_filter(alt.datum.lat != None)
)

q1_points = (
    q1_base
    .mark_circle(opacity=0.8, stroke="black", strokeWidth=0.5)
    .encode(
        longitude="lon:Q",
        latitude="lat:Q",
        size=alt.Size("n_grants:Q", scale=alt.Scale(range=SIZE_RANGE), legend=None),
        color=alt.Color("n_grants:Q", scale=alt.Scale(range=Q1_COLOR_RANGE), legend=None),
        tooltip=[
            alt.Tooltip("state_name:N", title="State"),
            alt.Tooltip("state_x:N", title="State (abbr)"),
            alt.Tooltip("year:O", title="Year"),
            alt.Tooltip("n_grants:Q", title="# Grants"),
            alt.Tooltip("total_amount:Q", title="Total amount", format=",.0f"),
        ],
    )
)

q1_map = (usChart + q1_points).properties(width=420, height=260)

# Custom graded bubble legend
legend_df = pd.DataFrame({"n_grants": legend_ticks})
STEP = 40
Y0 = LEGEND_Y + 35

legend_title = (
    alt.Chart(pd.DataFrame({"t": ["Number of grants"]}))
    .mark_text(align="left", fontSize=11, fontWeight="bold")
    .encode(
        x=alt.value(LEGEND_X - 50),
        y=alt.value(LEGEND_Y + 10),
        text="t:N"
    )
)

legend_bubbles = (
    alt.Chart(legend_df)
    .transform_window(idx="row_number()")
    .transform_calculate(y_pos=f"{Y0} + (datum.idx-1)*{STEP}")
    .mark_circle(opacity=0.95)
    .encode(
        x=alt.value(LEGEND_X - 20),
        y=alt.Y("y_pos:Q", axis=None, scale=None),
        size=alt.Size("n_grants:Q", scale=alt.Scale(range=SIZE_RANGE), legend=None),
        color=alt.Color("n_grants:Q", scale=alt.Scale(range=Q1_COLOR_RANGE), legend=None),
    )
)

legend_labels = (
    alt.Chart(legend_df)
    .transform_window(idx="row_number()")
    .transform_calculate(y_pos=f"{Y0} + (datum.idx-1)*{STEP}")
    .mark_text(align="left", dx=18, fontSize=10)
    .encode(
        x=alt.value(LEGEND_X + 20),
        y=alt.Y("y_pos:Q", axis=None, scale=None),
        text=alt.Text("n_grants:Q", format=",")
    )
)

q1_chart = alt.layer(q1_map, legend_title, legend_bubbles, legend_labels).properties(width=420, height=260)

# -----------------------------
# Q2/Q3 — Directorates (selected year) with toggles
# -----------------------------
chart_height = 260
bubble_y = chart_height / 2

q23_bubbles = (
    alt.Chart(dir_year_merged, title="Grants per directorate incl. terminations")
    .transform_filter(alt.datum.year == year_param)
    .mark_circle()
    .encode(
        x=alt.X("dir_abbr:N", title="Directorate"),
        y=alt.value(bubble_y),
        size=alt.Size(
            "n_grants:Q",
            scale=alt.Scale(type="sqrt", domain=[0, 2200], range=[5200, 9000]),
            legend=None
        ),
        color=alt.value(COL_TOTAL),
        opacity=alt.condition(show_total, alt.value(1.0), alt.value(0.0)),
        tooltip=[
            alt.Tooltip("org_dir_long_name:N", title="Directorate"),
            alt.Tooltip("dir_abbr:N", title="Abbr"),
            alt.Tooltip("year:O", title="Year"),
            alt.Tooltip("n_grants:Q", title="Grants"),
            alt.Tooltip("total_amount:Q", title="Total amount", format=",.0f"),
        ]
    )
    .properties(width=420, height=chart_height)
)

q23_term_bars = (
    alt.Chart(dir_year_merged)
    .transform_filter(alt.datum.year == year_param)
    .transform_filter("datum.n_term > 0")
    .mark_bar()
    .encode(
        x=alt.X("dir_abbr:N", title="Directorate"),
        y=alt.Y("n_term:Q", title="Terminated grants"),
        color=alt.value(COL_TERM),
        opacity=alt.condition(show_term, alt.value(0.75), alt.value(0.0)),
        tooltip=[
            alt.Tooltip("org_dir_long_name:N", title="Directorate"),
            alt.Tooltip("dir_abbr:N", title="Abbr"),
            alt.Tooltip("year:O", title="Year"),
            alt.Tooltip("n_term:Q", title="Terminated grants"),
            alt.Tooltip("term_amount:Q", title="Terminated amount", format=",.0f"),
        ],
    )
)

q23_text = (
    alt.Chart(dir_year_merged)
    .transform_filter(alt.datum.year == year_param)
    .mark_text(dy=3, fontSize=10, color="white")
    .encode(
        x="dir_abbr:N",
        y=alt.value(bubble_y),
        text="n_grants:Q",
        opacity=alt.condition(show_total, alt.value(1.0), alt.value(0.0)),
    )
)

q23_chart = alt.layer(q23_term_bars, q23_bubbles, q23_text).properties(width=420, height=chart_height)

# -----------------------------
# Q4 — Total amount per month (2021–2025) with zoom + year highlight + year labels
# -----------------------------
if "awd_eff_date" not in df_merged.columns or "awd_amount" not in df_merged.columns:
    raise KeyError("df_merged must contain 'awd_eff_date' and 'awd_amount' for Q4.")

df_q4 = df_merged.copy()
df_q4["awd_eff_date"] = pd.to_datetime(df_q4["awd_eff_date"], errors="coerce")
df_q4["month_date"] = df_q4["awd_eff_date"].dt.to_period("M").dt.to_timestamp()
df_q4["year_m"] = df_q4["month_date"].dt.year.astype("Int64")
df_q4 = df_q4[(df_q4["year_m"] >= 2021) & (df_q4["year_m"] <= 2025)]

df_q4m = (
    df_q4.dropna(subset=["month_date", "awd_amount", "year_m"])
    .groupby(["year_m", "month_date"], as_index=False)
    .agg(total_amount=("awd_amount", "sum"))
)

all_years = sorted(df_q4m["year_m"].dropna().unique().tolist())
full_grid = []
for y in all_years:
    months_y = pd.date_range(f"{int(y)}-01-01", f"{int(y)}-12-01", freq="MS")
    full_grid.append(pd.DataFrame({"year_m": int(y), "month_date": months_y}))
full_grid = pd.concat(full_grid, ignore_index=True)

df_q4m_full = full_grid.merge(df_q4m, on=["year_m", "month_date"], how="left").fillna({"total_amount": 0})
df_q4m_full["total_amount_musd"] = df_q4m_full["total_amount"] / 1_000_000

zoom_q4 = alt.selection_interval(bind="scales", encodings=["x"], name="ZoomQ4")
base_q4 = alt.Chart(df_q4m_full)

q4_highlight = (
    base_q4.transform_filter(alt.datum.year_m == year_param)
    .mark_area(opacity=0.12, color=COL_TOTAL)
    .encode(x="month_date:T", y="total_amount_musd:Q")
)

q4_line = (
    base_q4.mark_line(point=True, color=COL_TOTAL)
    .encode(
        x=alt.X(
            "month_date:T",
            title="",
            scale=alt.Scale(domain=[pd.Timestamp("2021-01-01"), pd.Timestamp("2025-12-01")]),
            axis=alt.Axis(format="%b", labelAngle=0, grid=False),
        ),
        y=alt.Y(
            "total_amount_musd:Q",
            title="Total amount (M USD)",
            axis=alt.Axis(format=",.0f"),
        ),
        tooltip=[
            alt.Tooltip("month_date:T", title="Month", format="%Y-%m"),
            alt.Tooltip("total_amount_musd:Q", title="Amount (M USD)", format=",.0f"),
        ],
    )
    .add_selection(zoom_q4)
)

q4_year_lines = (
    base_q4.transform_filter("month(datum.month_date) == 0")
    .mark_rule(color="lightgray")
    .encode(x="month_date:T")
)

q4_main = (q4_highlight + q4_line + q4_year_lines).properties(width=420, height=200)

timeline_q4 = pd.DataFrame({"month_date": pd.date_range("2021-01-01", "2025-12-01", freq="MS")})
timeline_q4["year_str"] = timeline_q4["month_date"].dt.year.astype(int).astype(str)

q4_year_labels = (
    alt.Chart(timeline_q4)
    .transform_filter("month(datum.month_date) == 0")
    .mark_text(dy=-5)
    .encode(x=alt.X("month_date:T", axis=None), text="year_str:N")
    .properties(width=420, height=22)
)

q4_chart = (
    alt.vconcat(q4_year_labels, q4_main, spacing=0)
    .resolve_scale(x="shared")
    .properties(title="Drag to zoom: Total monthly budget")
)

# -----------------------------
# Q5 — Grants over time (state / All) + terminated bars, zoom
# -----------------------------
if "awd_id" not in df_merged.columns or "status" not in df_merged.columns:
    raise KeyError("df_merged must contain 'awd_id' and 'status' for Q5.")

df5 = df_merged.copy()
df5["awd_eff_date"] = pd.to_datetime(df5["awd_eff_date"], errors="coerce")
df5 = df5.dropna(subset=["awd_eff_date", "state_x", "awd_id"])
df5["month_date"] = df5["awd_eff_date"].dt.to_period("M").dt.to_timestamp()
df5["year_m"] = df5["month_date"].dt.year.astype(int)
df5 = df5[(df5["year_m"] >= 2021) & (df5["year_m"] <= 2025)]

s = df5["status"]
df5["is_term"] = (
    (s == True) |
    (s == 1) |
    (s.astype(str).str.strip().str.lower().isin(
        ["true", "t", "1", "yes", "y", "terminated", "cancelled", "canceled"]
    ))
)

df_term_states = (
    df5[df5["is_term"]]
    .groupby("month_date")["state_x"]
    .apply(lambda x: ", ".join(sorted(x.dropna().unique())))
    .reset_index(name="term_states")
)
df_term_states["n_term_states"] = df_term_states["term_states"].apply(
    lambda txt: 0 if (pd.isna(txt) or txt == "") else len(txt.split(", "))
)

tot = df5.groupby(["state_x", "month_date"], as_index=False).agg(n_grants=("awd_id", "count"))
term = df5[df5["is_term"]].groupby(["state_x", "month_date"], as_index=False).agg(n_term=("awd_id", "count"))
df_q5m = tot.merge(term, on=["state_x", "month_date"], how="left").fillna({"n_term": 0})

states_q5 = sorted(df_q5m["state_x"].dropna().unique().tolist())
months = pd.date_range("2021-01-01", "2025-12-01", freq="MS")
full_grid = pd.MultiIndex.from_product([states_q5, months], names=["state_x", "month_date"]).to_frame(index=False)

df_q5m_full = full_grid.merge(df_q5m, on=["state_x", "month_date"], how="left").fillna({"n_grants": 0, "n_term": 0})
df_q5m_full = df_q5m_full.merge(df_term_states, on="month_date", how="left")
df_q5m_full["term_states"] = df_q5m_full["term_states"].fillna("")
df_q5m_full["n_term_states"] = df_q5m_full["n_term_states"].fillna(0).astype(int)

zoom_q5 = alt.selection_interval(bind="scales", encodings=["x"], name="ZoomQ5")

base_q5 = alt.Chart(df_q5m_full).transform_filter(
    "SelectedState == 'All' || datum.state_x == SelectedState"
)

agg_q5 = (
    base_q5.transform_aggregate(
        n_grants="sum(n_grants)",
        n_term="sum(n_term)",
        n_term_states="max(n_term_states)",
        term_states="max(term_states)",
        groupby=["month_date"]
    )
    .transform_calculate(
        term_states_show="SelectedState == 'All' ? datum.term_states : ''",
        n_term_states_show="SelectedState == 'All' ? datum.n_term_states : null"
    )
)

month_ticks = months.tolist()

q5_line = (
    agg_q5.mark_line(color=COL_TOTAL)
    .encode(
        x=alt.X("month_date:T", title="", axis=alt.Axis(values=month_ticks, format="%b", labelAngle=0, grid=False)),
        y=alt.Y("n_grants:Q", title="# grants", axis=alt.Axis(format=",.0f")),
        tooltip=[
            alt.Tooltip("month_date:T", title="Month", format="%Y-%m"),
            alt.Tooltip("n_grants:Q", title="# grants", format=",.0f"),
            alt.Tooltip("n_term:Q", title="# terminated", format=",.0f"),
            alt.Tooltip("n_term_states_show:Q", title="# states w/ terminations", format=",.0f"),
            alt.Tooltip("term_states_show:N", title="States w/ terminations"),
        ],
    )
    .add_selection(zoom_q5)
)

q5_points = agg_q5.mark_point(size=35, color=COL_TOTAL).encode(
    x="month_date:T",
    y=alt.Y("n_grants:Q", axis=None)
)

q5_term_bars = (
    agg_q5.transform_filter("datum.n_term > 0")
    .mark_bar(color=COL_TERM)
    .encode(
        x="month_date:T",
        y=alt.Y(
            "n_term:Q",
            title="# terminated",
            axis=alt.Axis(orient="right", format=",.0f", tickMinStep=1)
        ),
        opacity=alt.condition(show_term, alt.value(0.75), alt.value(0.0)),
    )
)

timeline_q5 = pd.DataFrame({"month_date": months})
timeline_q5["year_str"] = timeline_q5["month_date"].dt.year.astype(int).astype(str)

q5_year_labels = (
    alt.Chart(timeline_q5)
    .transform_filter("month(datum.month_date) == 0")
    .mark_text(dy=-5)
    .encode(x=alt.X("month_date:T", axis=None), text="year_str:N")
    .properties(width=420, height=22)
)

q5_main = (q5_term_bars + q5_line + q5_points).resolve_scale(y="independent").properties(width=420, height=220)

q5_chart = (
    alt.vconcat(q5_year_labels, q5_main, spacing=0)
    .resolve_scale(x="shared")
    .properties(title="Drag to zoom: Grants evolution incl. terminated grants (bars)")
)

# -----------------------------
# Q6 — Award amount vs collaboration
# -----------------------------
required_q6 = ["n_pi", "awd_amount", "status", "awd_id", "inst_name", "inst_state_code"]
missing_q6 = [c for c in required_q6 if c not in df_merged.columns]
if missing_q6:
    raise KeyError("df_merged missing columns for Q6: " + ", ".join(missing_q6))

df6 = df_merged.copy()
df6["status_label"] = df6["status"].map({True: "Cancelled", False: "Active"}).fillna("Unknown")

scatter_base = (
    alt.Chart(df6)
    .transform_filter(
        (alt.datum.year == year_param) &
        (alt.datum.dir_abbr == dir_param) &
        (alt.datum.awd_amount > 0)
    )
    .transform_calculate(
        x_jitter="datum.n_pi + (random() - 0.5) * 0.35"
    )
)

q6_scatter = (
    scatter_base
    .mark_circle(opacity=0.6, size=55)
    .encode(
        x=alt.X(
            "x_jitter:Q",
            title="Number of PIs",
            axis=alt.Axis(values=list(range(1, 11)), labelAngle=0)
        ),
        y=alt.Y(
            "awd_amount:Q",
            title="Award amount (USD, log)",
            scale=alt.Scale(type="log", nice=False),
            axis=alt.Axis(format="~s", tickCount=6)
        ),
        color=alt.Color(
            "status_label:N",
            scale=alt.Scale(domain=["Active", "Cancelled"], range=[COL_TOTAL, COL_TERM]),
            legend=None
        ),
        tooltip=[
            alt.Tooltip("awd_id:N", title="Award ID"),
            alt.Tooltip("inst_name:N", title="Institution"),
            alt.Tooltip("inst_state_code:N", title="State"),
            alt.Tooltip("n_pi:Q", title="Number of PIs"),
            alt.Tooltip("awd_amount:Q", title="Award amount", format=",.0f"),
            alt.Tooltip("status_label:N", title="Status"),
        ],
    )
    .properties(
        width=420,
        height=300,
        title="Award amount vs number of scientific collaborators (PIs)"
    )
)

# -----------------------------
# Final layout
# -----------------------------
left_col = alt.vconcat(q1_chart, q4_chart, q5_chart, spacing=14)
right_col = alt.vconcat(legend_panel, q23_chart, q6_scatter, spacing=14)

dashboard = (
    alt.hconcat(left_col, right_col, spacing=18)
    .add_params(year_param, state_param, dir_param, show_total, show_term)
    .properties(title="Project 2 — Final visualization (Q1–Q6)")
    .configure_title(fontSize=16, anchor="start")
    .configure_axis(labelFontSize=10, titleFontSize=11)
    .configure_legend(titleFontSize=11, labelFontSize=10)
    .configure_view(stroke=None)
)

dashboard
