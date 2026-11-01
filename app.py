"""
Order-to-Cash dashboard  (Streamlit)
Tables: Client_Master, Finished_Goods, FR1, Sales_Data, Order_List
Run locally :  streamlit run app.py
"""
from __future__ import annotations

from io import BytesIO

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import demo_data
import etl

st.set_page_config(page_title="Order-to-Cash Dashboard", page_icon="📊", layout="wide")

BLUE, TEAL, AMBER, RED, PURPLE, GREY = "#2563eb", "#0d9488", "#f59e0b", "#dc2626", "#7c3aed", "#64748b"
PALETTE = [BLUE, TEAL, AMBER, PURPLE, RED, "#0891b2", "#65a30d", GREY]
STATUS_COLORS = {"Fully dispatched": TEAL, "Partially dispatched": AMBER, "Not dispatched": RED}

st.markdown(
    """<style>
    .block-container{padding-top:1.4rem}
    div[data-testid="stMetric"]{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 14px}
    @media (prefers-color-scheme: dark){div[data-testid="stMetric"]{background:#1e293b;border-color:#334155}}
    </style>""",
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ formatting helpers
def inr(v) -> str:
    if v is None or pd.isna(v):
        return "–"
    a, s = abs(v), "-" if v < 0 else ""
    if a >= 1e7:
        return f"{s}₹{a / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"{s}₹{a / 1e5:.2f} L"
    return f"{s}₹{a:,.0f}"


def pct(v, d=1) -> str:
    return "–" if v is None or pd.isna(v) else f"{v:.{d}f}%"


def num(v, d=0) -> str:
    return "–" if v is None or pd.isna(v) else f"{v:,.{d}f}"


def safe_div(a, b):
    return np.nan if b is None or pd.isna(b) or b == 0 else a / b


def style(fig, h=360):
    fig.update_layout(
        template="plotly_white", height=h, margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", y=-0.15), font=dict(size=12),
    )
    return fig


def show(fig, h=360):
    st.plotly_chart(style(fig, h), width="stretch")


def table(df, height=380, **kw):
    df = df.copy()
    num_cols = df.select_dtypes("number").columns
    df[num_cols] = df[num_cols].round(2)
    st.dataframe(df, width="stretch", height=height, hide_index=True, **kw)


def barh(df, x, y, title, top=15, color=BLUE, h=None):
    d = df.sort_values(x, ascending=False).head(top).sort_values(x)
    fig = px.bar(d, x=x, y=y, orientation="h", title=title, color_discrete_sequence=[color])
    fig.update_yaxes(title=None)
    show(fig, h or max(300, 26 * len(d) + 90))


def download(df, name, key):
    st.download_button("⬇ CSV", df.to_csv(index=False).encode("utf-8-sig"), f"{name}.csv", "text/csv", key=key)


# ------------------------------------------------------------------ data loading
DEFAULT_TABS = {
    "client_master": "Client_Master", "order_list": "Order_List", "finished_goods": "Finished_Goods",
    "fr1": "FR1", "sales_data": "Sales_Data",
}


@st.cache_data(ttl=600, show_spinner="Reading Google Sheets ...")
def load_gsheets(sa_info: dict, sheets: dict, tabs: dict) -> dict:
    import gspread

    gc = gspread.service_account_from_dict(sa_info)
    which = {  # logical table -> which spreadsheet holds it
        "client_master": "order_punching", "order_list": "order_punching", "finished_goods": "finished_goods",
        "fr1": "order_to_dispatch", "sales_data": "sales_invoice",
    }
    books, raw = {}, {}
    for table_key, book_key in which.items():
        ref = sheets[book_key]
        if book_key not in books:
            books[book_key] = gc.open_by_url(ref) if str(ref).startswith("http") else gc.open_by_key(ref)
        ws = books[book_key].worksheet(tabs.get(table_key, DEFAULT_TABS[table_key]))
        raw[table_key] = etl.frame_from_values(ws.get_all_values())
    return raw


def from_uploads(files) -> dict:
    raw = {}
    for f in files:
        name = f.name.lower()
        if name.endswith(".csv"):
            frames = {name.rsplit(".", 1)[0]: pd.read_csv(f, dtype=str)}
        else:
            frames = pd.read_excel(f, sheet_name=None, dtype=str)
        for sheet, df in frames.items():
            for key, label in etl.RAW_NAMES.items():
                if etl._norm(sheet) == etl._norm(label) or etl._norm(label) in etl._norm(sheet):
                    df.columns = etl.dedupe_columns(df.columns)
                    raw[key] = df
    return raw


@st.cache_data(show_spinner="Preparing demo data ...")
def load_demo() -> dict:
    return demo_data.make_demo()


@st.cache_data(show_spinner="Building reports ...")
def build_cached(raw: dict, cp_per_unit: bool) -> dict:
    return etl.build(raw, cp_per_unit)


# ------------------------------------------------------------------ sidebar: source
st.sidebar.title("📊 Order-to-Cash")
try:
    has_secrets = "gcp_service_account" in st.secrets and "sheets" in st.secrets
except Exception:  # no secrets.toml at all (local run / first deploy)
    has_secrets = False
modes = (["Google Sheets"] if has_secrets else []) + ["Demo data", "Upload files"]
source = st.sidebar.radio("Data source", modes, index=0)
if st.sidebar.button("🔄 Refresh data"):
    st.cache_data.clear()
    st.rerun()

raw = None
if source == "Google Sheets":
    try:
        raw = load_gsheets(dict(st.secrets["gcp_service_account"]), dict(st.secrets["sheets"]), dict(st.secrets.get("tabs", {})))
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not read Google Sheets: {e}")
        st.stop()
elif source == "Upload files":
    files = st.sidebar.file_uploader("Excel / CSV (sheet or file names: Client_Master, Finished_Goods, FR1, Sales_Data, Order_List)",
                                     type=["xlsx", "xls", "csv"], accept_multiple_files=True)
    if files:
        raw = from_uploads(files)
    missing = [v for k, v in etl.RAW_NAMES.items() if not raw or k not in raw]
    if not raw or missing:
        st.info("Upload the files to start. Still missing: " + (", ".join(missing) if raw else ", ".join(etl.RAW_NAMES.values())))
        st.stop()
else:
    raw = load_demo()
    raw = {k: v.replace("", np.nan) for k, v in raw.items()}
    st.sidebar.warning("Showing synthetic demo data")

st.sidebar.markdown("---")
cp_basis = st.sidebar.radio("Order_List column V (CP / CV) is", ["Cost per unit", "Total cost of the line"], index=0,
                            help="Gross profit = net sales value - cost. Choose how column V should be read.")
asof = pd.Timestamp(st.sidebar.date_input("As-of date", value=pd.Timestamp.today().normalize()))

D = build_cached(raw, cp_basis == "Cost per unit")
L_all, PO_all = D["lines"], D["po"]

# ------------------------------------------------------------------ sidebar: filters
st.sidebar.markdown("### Filters")
dmin, dmax = PO_all["po_date"].min(), PO_all["po_date"].max()
if pd.isna(dmin):
    st.error("No valid PO dates found in Order_List - check the Column mapping tab.")
    st.stop()
dr = st.sidebar.date_input("PO date range", value=(dmin.date(), dmax.date()), min_value=dmin.date(), max_value=dmax.date())
if isinstance(dr, tuple) and len(dr) == 2:
    d0, d1 = pd.Timestamp(dr[0]), pd.Timestamp(dr[1]) + pd.Timedelta(days=1)
else:
    d0, d1 = dmin, dmax + pd.Timedelta(days=1)


def ms(label, col):
    opts = sorted(PO_all[col].dropna().astype(str).unique())
    return st.sidebar.multiselect(label, opts)


f_brand, f_state, f_zone = ms("Brand", "brand"), ms("State", "state"), ms("Zone", "zone")
f_sales, f_partner, f_status = ms("Salesman", "salesman"), ms("Delivery partner", "delivery_partner"), ms("PO status", "status")
f_party = ms("Party", "party")

PO = PO_all[(PO_all["po_date"] >= d0) & (PO_all["po_date"] < d1)]
for col, sel in [("brand", f_brand), ("state", f_state), ("zone", f_zone), ("salesman", f_sales),
                 ("delivery_partner", f_partner), ("status", f_status), ("party", f_party)]:
    if sel:
        PO = PO[PO[col].isin(sel)]
L = L_all[L_all["po_no"].isin(PO["po_no"])]
if PO.empty:
    st.warning("No orders match the filters.")
    st.stop()

st.title("Order-to-Cash Dashboard")
st.caption(f"{len(PO):,} POs · {len(L):,} item lines · PO dates {PO['po_date'].min():%d %b %Y} – {PO['po_date'].max():%d %b %Y} · as of {asof:%d %b %Y}")

tabs = st.tabs(["Overview", "Sales & Orders", "Pending & Fulfilment", "Lead time & On-time", "Packing & Dispatch",
                "Logistics", "Products", "Inventory", "Gross Profit", "Clients", "Data quality", "Column mapping & Export"])

# ====================================================================== 1 OVERVIEW
with tabs[0]:
    ov, dv, pv = PO["order_value"].sum(), PO["dispatch_value"].sum(), PO["pending_value"].sum()
    gp, rev = PO["gp_dispatched"].sum(), PO["rev_cp_dispatched"].sum()
    c = st.columns(4)
    c[0].metric("Orders (POs)", num(len(PO)))
    c[1].metric("Order value (net)", inr(ov))
    c[2].metric("Dispatched value", inr(dv), pct(safe_div(dv, ov) * 100) + " of ordered")
    c[3].metric("Pending value", inr(pv))
    c = st.columns(4)
    c[0].metric("Invoiced value", inr(PO["invoice_amount"].sum()))
    c[1].metric("Gross profit (dispatched)", inr(gp), pct(safe_div(gp, rev) * 100) + " GP")
    c[2].metric("Avg PO → dispatch", f"{PO['d_po_to_dispatch'].mean():.1f} days" if PO["d_po_to_dispatch"].notna().any() else "–")
    ot = PO["on_time"].dropna()
    c[3].metric("On-time dispatch", pct(ot.mean() * 100) if len(ot) else "–")

    m = PO.groupby("po_month").agg(order=("order_value", "sum"), dispatched=("dispatch_value", "sum"),
                                   gp=("gp_dispatched", "sum"), rev=("rev_cp_dispatched", "sum"), pos=("po_no", "count")).reset_index()
    m["gp_pct"] = m["gp"] / m["rev"].replace(0, np.nan) * 100
    fig = go.Figure()
    fig.add_bar(x=m["po_month"], y=m["order"], name="Ordered", marker_color=BLUE)
    fig.add_bar(x=m["po_month"], y=m["dispatched"], name="Dispatched", marker_color=TEAL)
    fig.add_scatter(x=m["po_month"], y=m["gp_pct"], name="GP %", yaxis="y2", mode="lines+markers", line=dict(color=AMBER, width=3))
    fig.update_layout(title="Monthly order vs dispatched value, and GP %", barmode="group",
                      yaxis2=dict(overlaying="y", side="right", title="GP %", showgrid=False))
    show(fig, 400)

    a, b = st.columns(2)
    with a:
        barh(PO.groupby("party", as_index=False)["order_value"].sum(), "order_value", "party", "Top 10 parties by order value", 10)
    with b:
        st_ = PO.groupby("status", as_index=False).agg(pos=("po_no", "count"), value=("order_value", "sum"))
        fig = px.bar(st_, x="status", y="value", color="status", color_discrete_map=STATUS_COLORS, text="pos", title="Order value by status (label = POs)")
        fig.update_layout(showlegend=False)
        show(fig)
    a, b = st.columns(2)
    with a:
        barh(PO.groupby("state", as_index=False)["order_value"].sum(), "order_value", "state", "Order value by state", 10, TEAL)
    with b:
        stages = [("PO placed", len(PO)), ("Packed", int(PO["pack_date"].notna().sum())),
                  ("Dispatched", int(PO["dispatch_date"].notna().sum())), ("Invoiced", int(PO["invoiced"].sum())),
                  ("GR received", int(PO["gr_date"].notna().sum()))]
        fig = go.Figure(go.Funnel(y=[s[0] for s in stages], x=[s[1] for s in stages], marker=dict(color=PALETTE[:5])))
        fig.update_layout(title="Order-to-cash funnel (POs)")
        show(fig)

# ====================================================================== 2 SALES & ORDERS
with tabs[1]:
    dims = {"Party": ("po", "party"), "Brand": ("po", "brand"), "State": ("po", "state"), "City": ("po", "city"), "Zone": ("po", "zone"),
            "Salesman": ("po", "salesman"), "Sales manager": ("po", "sales_manager"), "Tour": ("po", "tour"),
            "Delivery partner": ("po", "delivery_partner"), "Category": ("line", "category"), "Item": ("line", "item")}
    dim = st.selectbox("Analyse sales by", list(dims), key="s_dim")
    src, col = dims[dim]
    base = PO if src == "po" else L
    g = base.groupby(col).agg(order_value=("order_value", "sum"), dispatched_value=("dispatch_value", "sum"),
                              order_qty=("order_qty", "sum") if src == "line" else ("order_qty", "sum"),
                              pos=("po_no", "nunique")).reset_index()
    g["share_%"] = g["order_value"] / g["order_value"].sum() * 100
    g["avg_order_value"] = g["order_value"] / g["pos"]
    g = g.sort_values("order_value", ascending=False)
    a, b = st.columns([3, 2])
    with a:
        barh(g, "order_value", col, f"Order value by {dim.lower()}", 15)
    with b:
        table(g, 420)
        download(g, f"sales_by_{col}", "dl_sales_dim")

    a, b = st.columns(2)
    with a:  # pareto of parties
        p = PO.groupby("party")["order_value"].sum().sort_values(ascending=False).reset_index()
        p["cum_%"] = p["order_value"].cumsum() / p["order_value"].sum() * 100
        p["rank"] = np.arange(1, len(p) + 1)
        fig = go.Figure()
        fig.add_bar(x=p["rank"], y=p["order_value"], name="Order value", marker_color=BLUE)
        fig.add_scatter(x=p["rank"], y=p["cum_%"], name="Cumulative %", yaxis="y2", line=dict(color=AMBER, width=3))
        fig.update_layout(title="Party Pareto (80/20)", yaxis2=dict(overlaying="y", side="right", range=[0, 105], showgrid=False),
                          xaxis_title="Party rank")
        show(fig)
    with b:
        first = PO_all.groupby("party")["po_date"].min()
        t = PO.copy()
        t["kind"] = np.where(t["party"].map(first) >= d0, "New client", "Repeat client")
        nr = t.groupby(["po_month", "kind"], as_index=False)["order_value"].sum()
        fig = px.bar(nr, x="po_month", y="order_value", color="kind", title="New vs repeat clients (by first PO in data)",
                     color_discrete_sequence=[AMBER, BLUE])
        show(fig)
    a, b = st.columns(2)
    with a:
        hm = PO.pivot_table(index="state", columns="po_month", values="order_value", aggfunc="sum", fill_value=0)
        hm.columns = [c.strftime("%b %y") for c in hm.columns]
        fig = px.imshow(hm / 1e5, aspect="auto", color_continuous_scale="Blues", title="State × month order value (₹ lakh)")
        show(fig, 380)
    with b:
        fig = px.histogram(PO, x="order_value", nbins=40, title="Distribution of PO value", color_discrete_sequence=[TEAL])
        show(fig, 380)
    a, b = st.columns(2)
    with a:
        dow = PO.assign(day=PO["po_date"].dt.day_name()).groupby("day").agg(pos=("po_no", "count")).reindex(
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]).reset_index()
        show(px.bar(dow, x="day", y="pos", title="POs by weekday", color_discrete_sequence=[BLUE]))
    with b:
        dd = PO.groupby("brand").agg(avg_disc=("avg_disc", "mean"), value=("order_value", "sum")).reset_index()
        show(px.bar(dd, x="brand", y="avg_disc", title="Average discount % by brand", color_discrete_sequence=[PURPLE]))

# ====================================================================== 3 PENDING
with tabs[2]:
    pend = PO[PO["pending_value"] > 0].copy()
    pend["age_days"] = (asof - pend["po_date"]).dt.days
    c = st.columns(4)
    c[0].metric("POs with pending qty", num(len(pend)))
    c[1].metric("Pending value", inr(pend["pending_value"].sum()))
    c[2].metric("Avg age of pending POs", f"{pend['age_days'].mean():.0f} days" if len(pend) else "–")
    c[3].metric("Pending > 30 days", inr(pend.loc[pend["age_days"] > 30, "pending_value"].sum()))
    a, b = st.columns(2)
    with a:
        pend["bucket"] = pd.cut(pend["age_days"], [-1, 7, 15, 30, 60, 10_000], labels=["0-7", "8-15", "16-30", "31-60", "60+"])
        bk = pend.groupby("bucket", observed=False).agg(value=("pending_value", "sum"), pos=("po_no", "count")).reset_index()
        show(px.bar(bk, x="bucket", y="value", text="pos", title="Pending value by age in days (label = POs)", color_discrete_sequence=[RED]))
    with b:
        barh(pend.groupby("party", as_index=False)["pending_value"].sum(), "pending_value", "party", "Top parties by pending value", 10, RED)
    a, b = st.columns(2)
    with a:
        pl = L[L["pending_qty"] > 0].groupby(["item_code", "item"], as_index=False).agg(
            pending_qty=("pending_qty", "sum"), pending_value=("pending_value", "sum")).sort_values("pending_value", ascending=False)
        st.markdown("**Pending by item**")
        table(pl, 360)
        download(pl, "pending_by_item", "dl_pend_item")
    with b:
        sm = PO.groupby(["po_month", "status"], as_index=False)["po_no"].count()
        show(px.bar(sm, x="po_month", y="po_no", color="status", color_discrete_map=STATUS_COLORS, title="PO status by month (count)"), 360)
    st.markdown("#### Action lists")
    cols = ["po_no", "po_date", "party", "delivery_partner", "order_value", "dispatch_value", "pending_value"]
    t1 = PO[PO["pack_date"].notna() & PO["dispatch_date"].isna()]
    t2 = PO[PO["dispatch_date"].notna() & ~PO["invoiced"]]
    t3 = PO[PO["invoiced"] & PO["gr_date"].isna()]
    t4 = pend.sort_values("age_days", ascending=False)
    for lbl, d_, extra in [("Packed but not dispatched", t1, []), ("Dispatched but not invoiced", t2, ["dispatch_date"]),
                           ("Invoiced but GR not received", t3, ["invoice_no", "invoice_date"]),
                           ("Oldest pending POs", t4, ["age_days", "status"])]:
        with st.expander(f"{lbl}  ({len(d_)})"):
            table(d_[cols + extra], 300)
            download(d_[cols + extra], lbl.replace(" ", "_"), "dl_" + lbl[:8])

# ====================================================================== 4 LEAD TIME
with tabs[3]:
    P = PO
    c = st.columns(5)
    for i, (lbl, k) in enumerate([("PO → Packing", "d_po_to_pack"), ("Packing → Dispatch", "d_pack_to_dispatch"),
                                  ("PO → Dispatch", "d_po_to_dispatch"), ("Dispatch → Invoice", "d_dispatch_to_invoice"),
                                  ("Dispatch → GR", "d_dispatch_to_gr")]):
        c[i].metric(lbl, f"{P[k].mean():.1f} d" if P[k].notna().any() else "–", f"median {P[k].median():.1f}" if P[k].notna().any() else None, delta_color="off")
    ot = P[P["on_time"].notna()].copy()
    ot["on_time"] = ot["on_time"].astype(float)
    a, b = st.columns(2)
    with a:
        mt = ot.groupby("po_month").agg(on_time=("on_time", "mean"), pos=("po_no", "count")).reset_index()
        mt["on_time"] *= 100
        show(px.line(mt, x="po_month", y="on_time", markers=True, title="On-time dispatch % (dispatch ≤ planned date)", color_discrete_sequence=[TEAL]))
    with b:
        show(px.histogram(ot, x="delay_days", nbins=30, title="Dispatch delay vs plan (days, + = late)", color_discrete_sequence=[RED]))
    dim = st.selectbox("Compare by", ["delivery_partner", "city", "state", "salesman", "brand", "party"], key="lt_dim")
    g = P.groupby(dim).agg(pos=("po_no", "count"), po_to_pack=("d_po_to_pack", "mean"), pack_to_dispatch=("d_pack_to_dispatch", "mean"),
                           po_to_dispatch=("d_po_to_dispatch", "mean"), on_time=("on_time", lambda x: x.dropna().astype(float).mean() * 100),
                           avg_delay=("delay_days", "mean")).reset_index()
    g = g[g["pos"] >= 3].sort_values("po_to_dispatch", ascending=False)
    a, b = st.columns([3, 2])
    with a:
        fig = go.Figure()
        d_ = g.head(15).iloc[::-1]
        fig.add_bar(y=d_[dim], x=d_["po_to_pack"], name="PO → Pack", orientation="h", marker_color=BLUE)
        fig.add_bar(y=d_[dim], x=d_["pack_to_dispatch"], name="Pack → Dispatch", orientation="h", marker_color=AMBER)
        fig.update_layout(barmode="stack", title=f"Average days by {dim} (min 3 POs)")
        show(fig, max(320, 26 * len(d_) + 100))
    with b:
        table(g, 420)
        download(g, "lead_time", "dl_lt")
    with st.expander("Late POs (dispatched after planned date)"):
        late = P[P["delay_days"] > 0].sort_values("delay_days", ascending=False)[["po_no", "party", "delivery_partner", "planned_dispatch", "dispatch_date", "delay_days", "order_value"]]
        table(late, 300)

# ====================================================================== 5 PACKING
with tabs[4]:
    F = PO[PO["in_fr1"]]
    c = st.columns(4)
    c[0].metric("POs with packing confirmation", num(len(F)), f"{len(F) / len(PO) * 100:.0f}% of POs", delta_color="off")
    c[1].metric("Avg PO → packing", f"{F['d_po_to_pack'].mean():.1f} days" if F["d_po_to_pack"].notna().any() else "–")
    c[2].metric("Partial dispatches", pct((F["partial_fr1"] == "Yes").mean() * 100) if len(F) else "–")
    c[3].metric("Photos per PO", f"{F['n_images'].mean():.1f}" if len(F) else "–")
    a, b = st.columns(2)
    with a:
        e = F.groupby("emp_name").agg(pos=("po_no", "count"), value=("order_value", "sum"), po_to_pack=("d_po_to_pack", "mean"), photos=("n_images", "mean")).reset_index()
        show(px.bar(e.sort_values("pos"), x="pos", y="emp_name", orientation="h", title="POs packed by employee", color_discrete_sequence=[BLUE]))
        table(e, 200)
    with b:
        dly = F.assign(day=F["pack_ts"].dt.date).groupby("day").size().reset_index(name="POs packed")
        show(px.line(dly, x="day", y="POs packed", title="Packing confirmations per day", color_discrete_sequence=[TEAL]))
    d_ = PO[PO["dispatch_date"].notna()].assign(day=lambda x: x["dispatch_date"].dt.date).groupby("day").agg(
        POs=("po_no", "count"), cases=("cases", "sum"), weight_kg=("weight", "sum")).reset_index()
    fig = go.Figure()
    fig.add_bar(x=d_["day"], y=d_["POs"], name="POs dispatched", marker_color=BLUE)
    fig.add_scatter(x=d_["day"], y=d_["cases"], name="Cases", yaxis="y2", line=dict(color=AMBER))
    fig.update_layout(title="Dispatches per day (POs and cases)", yaxis2=dict(overlaying="y", side="right", showgrid=False))
    show(fig)

# ====================================================================== 6 LOGISTICS
with tabs[5]:
    S = PO[PO["in_sales"] & PO["dispatch_date"].notna()]
    c = st.columns(5)
    c[0].metric("Cases dispatched", num(S["cases"].sum()))
    c[1].metric("Weight (kg)", num(S["weight"].sum()))
    c[2].metric("Bilty / freight", inr(S["bilty_amount"].sum()))
    c[3].metric("Loading-unloading", inr(S["loading_charge"].sum()))
    c[4].metric("Freight % of invoice", pct(safe_div(S["bilty_amount"].sum() + S["loading_charge"].sum(), S["invoice_amount"].sum()) * 100, 2))
    dim = st.selectbox("Group by", ["delivery_partner", "city", "state", "salesman", "tour"], key="lg_dim")
    g = S.groupby(dim).agg(pos=("po_no", "count"), cases=("cases", "sum"), weight=("weight", "sum"), bilty=("bilty_amount", "sum"),
                           loading=("loading_charge", "sum"), invoice=("invoice_amount", "sum"), transit_days=("d_dispatch_to_gr", "mean")).reset_index()
    g["freight_per_kg"] = (g["bilty"] + g["loading"]) / g["weight"].replace(0, np.nan)
    g["freight_per_case"] = (g["bilty"] + g["loading"]) / g["cases"].replace(0, np.nan)
    g["freight_%_invoice"] = (g["bilty"] + g["loading"]) / g["invoice"].replace(0, np.nan) * 100
    g = g.sort_values("invoice", ascending=False)
    a, b = st.columns(2)
    with a:
        barh(g, "pos", dim, f"POs shipped by {dim}", 12)
    with b:
        barh(g[g["weight"] > 0], "freight_per_kg", dim, "Freight cost per kg (₹)", 12, AMBER)
    table(g, 340)
    download(g, "logistics", "dl_log")

# ====================================================================== 7 PRODUCTS
with tabs[6]:
    pd_dim = st.selectbox("Group by", ["category", "item", "brand", "size", "finish", "variation", "cat_code"], key="pr_dim")
    g = L.groupby(pd_dim).agg(order_qty=("order_qty", "sum"), dispatch_qty=("dispatch_qty", "sum"), order_value=("order_value", "sum"),
                              dispatch_value=("dispatch_value", "sum"), pending_value=("pending_value", "sum"),
                              gp=("gp_dispatched", "sum"), rev_cp=("rev_cp_dispatched", "sum"), pos=("po_no", "nunique")).reset_index()
    g["gp_%"] = g["gp"] / g["rev_cp"].replace(0, np.nan) * 100
    g["fill_%"] = g["dispatch_qty"] / g["order_qty"].replace(0, np.nan) * 100
    g = g.sort_values("order_value", ascending=False)
    g["cum_%"] = g["order_value"].cumsum() / g["order_value"].sum() * 100
    g["ABC"] = np.select([g["cum_%"] <= 80, g["cum_%"] <= 95], ["A", "B"], default="C")
    a, b = st.columns(2)
    with a:
        barh(g, "order_value", pd_dim, "Top by order value", 15)
    with b:
        barh(g, "order_qty", pd_dim, "Top by order quantity", 15, TEAL)
    abc = g.groupby("ABC").agg(count=(pd_dim, "count"), value=("order_value", "sum")).reset_index()
    a, b = st.columns([1, 3])
    with a:
        show(px.bar(abc, x="ABC", y="value", text="count", title="ABC classes (label = count)", color_discrete_sequence=[PURPLE]), 320)
    with b:
        table(g.drop(columns=["rev_cp"]), 320)
        download(g, "product_report", "dl_prod")

# ====================================================================== 8 INVENTORY
with tabs[7]:
    c1, c2 = st.columns(2)
    mult = c1.slider("Reorder target = MSL ×", 1.0, 5.0, 2.0, 0.5, help="Target free stock (stock − pending orders) for the reorder suggestion")
    win = c2.slider("Velocity window (days)", 30, 365, 90, 30)
    inv = etl.inventory_view(D["fg"], L_all, asof, mult, win)
    c = st.columns(5)
    c[0].metric("SKUs", num(len(inv)))
    c[1].metric("Out / negative", num((inv["status"] == "Out / negative").sum()))
    c[2].metric("Below MSL", num((inv["status"] == "Below MSL").sum()))
    c[3].metric("Overstock", num((inv["status"] == "Overstock (>3x MSL)").sum()))
    c[4].metric("Stock value (MRP)", inr(inv["stock_value_mrp"].sum()))
    a, b = st.columns(2)
    with a:
        sc = inv["status"].value_counts().reset_index()
        sc.columns = ["status", "SKUs"]
        show(px.bar(sc, x="status", y="SKUs", color="status", title="SKU stock status", color_discrete_map={
            "Out / negative": RED, "Below MSL": AMBER, "OK": TEAL, "Overstock (>3x MSL)": PURPLE}).update_layout(showlegend=False))
    with b:
        cc = inv.groupby("category").agg(stock_value=("stock_value_mrp", "sum")).reset_index()
        barh(cc, "stock_value", "category", "Stock value at MRP by category", 10, TEAL)
    a, b = st.columns(2)
    with a:
        sh = inv[inv["shortage_vs_pending"] > 0].sort_values("shortage_vs_pending", ascending=False)
        st.markdown("**Cannot fulfil pending orders (pending qty > stock)**")
        table(sh[["code", "item", "category", "stock", "pending_qty", "shortage_vs_pending"]], 300)
    with b:
        v = inv[(inv["daily"] > 0) | (inv["actual_daily"] > 0)]
        fig = px.scatter(v, x="daily", y="actual_daily", hover_name="item", color="status", title=f"Sheet 1-day consumption vs actual last {win} days",
                         labels={"daily": "1_Day_Consump (sheet)", "actual_daily": "Actual dispatched / day"})
        mx = max(v["daily"].max(), v["actual_daily"].max()) if len(v) else 1
        fig.add_shape(type="line", x0=0, y0=0, x1=mx, y1=mx, line=dict(dash="dot", color=GREY))
        show(fig)
    st.markdown("**Reorder suggestions** (rounded up to outer-box multiples)")
    flt = st.multiselect("Status", sorted(inv["status"].unique()), default=["Out / negative", "Below MSL"], key="inv_status")
    ro = inv[inv["status"].isin(flt) | (inv["reorder_qty"] > 0)] if not flt else inv[inv["status"].isin(flt)]
    cols = ["code", "brand", "category", "item", "size", "finish", "stock", "pending_qty", "free_stock", "msl", "daily", "actual_daily",
            "days_cover", "target_stock", "reorder_qty", "status"]
    table(ro[cols].sort_values("reorder_qty", ascending=False), 360)
    download(ro[cols], "reorder_suggestions", "dl_reorder")
    st.caption("MSL in the sheet = 1_Day_Consump × Lead_Time × Safety_Factor. Free stock = Current_Stock − pending order qty.")

# ====================================================================== 9 GROSS PROFIT
with tabs[8]:
    basis = st.radio("Basis", ["Dispatched", "Ordered"], horizontal=True, key="gp_basis")
    rv, cs, gcol = ("rev_cp_dispatched", "cost_dispatched", "gp_dispatched") if basis == "Dispatched" else ("rev_cp_ordered", "cost_ordered", "gp_ordered")
    R, C, G = L[rv].sum(), L[cs].sum(), L[gcol].sum()
    c = st.columns(5)
    c[0].metric("Net sales value", inr(R))
    c[1].metric("Cost (CP × qty)", inr(C))
    c[2].metric("Gross profit", inr(G))
    c[3].metric("GP %", pct(safe_div(G, R) * 100))
    c[4].metric("Lines without CP", num((~L["has_cp"]).sum()), "excluded", delta_color="off")
    st.caption("Net sales value = qty × item price × (1 − Disc%). Gross profit = net sales value − qty × cost price (Order_List col V). Lines without cost are excluded from both sides.")

    mm = L.groupby("po_month").agg(rev=(rv, "sum"), gp=(gcol, "sum")).reset_index()
    mm["gp_pct"] = mm["gp"] / mm["rev"].replace(0, np.nan) * 100
    fig = go.Figure()
    fig.add_bar(x=mm["po_month"], y=mm["gp"], name="Gross profit", marker_color=TEAL)
    fig.add_scatter(x=mm["po_month"], y=mm["gp_pct"], name="GP %", yaxis="y2", line=dict(color=AMBER, width=3), mode="lines+markers")
    fig.update_layout(title="Monthly gross profit and GP %", yaxis2=dict(overlaying="y", side="right", showgrid=False))
    show(fig)

    gdims = {"Brand": "brand", "Category": "category", "Item": "item", "Party": "party", "State": "state", "City": "city", "Zone": "zone",
             "Salesman": "salesman", "Size": "size", "Finish": "finish", "PO": "po_no"}
    gd = st.selectbox("Gross profit by", list(gdims), index=1, key="gp_dim")
    col = gdims[gd]
    g = L.groupby(col).agg(net_sales=(rv, "sum"), cost=(cs, "sum"), gp=(gcol, "sum"), qty=("dispatch_qty" if basis == "Dispatched" else "order_qty", "sum"),
                           avg_disc=("disc", "mean")).reset_index()
    g["gp_%"] = g["gp"] / g["net_sales"].replace(0, np.nan) * 100
    g = g[g["net_sales"] > 0].sort_values("gp", ascending=False)
    a, b = st.columns(2)
    with a:
        barh(g, "gp", col, f"Gross profit by {gd.lower()}", 15, TEAL)
    with b:
        gg = g[g["net_sales"] > g["net_sales"].sum() * 0.002]
        fig = px.bar(gg.sort_values("gp_%").tail(15), x="gp_%", y=col, orientation="h", title=f"GP % by {gd.lower()} (top 15)", color_discrete_sequence=[AMBER])
        show(fig, 460)
    a, b = st.columns(2)
    with a:
        fig = px.scatter(g, x="avg_disc", y="gp_%", size="net_sales", hover_name=col, title="Discount % vs GP % (bubble = sales)",
                         color_discrete_sequence=[PURPLE])
        show(fig)
    with b:
        fig = px.histogram(L[L["has_cp"] & (L["net_rate"] > 0)].assign(line_gp_pct=lambda x: (x["net_rate"] - x["cp_unit"]) / x["net_rate"] * 100),
                           x="line_gp_pct", nbins=50, title="Distribution of line-level margin %", color_discrete_sequence=[BLUE])
        fig.update_xaxes(range=[-100, 100])
        show(fig)
    table(g, 320)
    download(g, f"gross_profit_by_{col}", "dl_gp")
    with st.expander("Lines selling below cost (negative margin)"):
        neg = L[L["has_cp"] & (L["net_rate"] < L["cp_unit"])][["po_no", "party", "item_code", "item", "item_price", "disc", "net_rate", "cp_unit", "order_qty", "dispatch_qty"]]
        neg = neg.assign(loss_per_unit=neg["cp_unit"] - neg["net_rate"])
        table(neg, 300)
        download(neg, "below_cost_lines", "dl_neg")
    with st.expander("PO-wise gross profit"):
        pg = PO[["po_no", "po_date", "party", "brand", "order_value", "dispatch_value", "rev_cp_dispatched", "gp_dispatched", "invoice_amount"]].copy()
        pg["gp_%"] = pg["gp_dispatched"] / pg["rev_cp_dispatched"].replace(0, np.nan) * 100
        table(pg, 320)
        download(pg, "po_wise_gp", "dl_pogp")

# ====================================================================== 10 CLIENTS
with tabs[9]:
    thr = st.slider("Dormant after (days without a PO)", 30, 365, 90, 15, key="dorm")
    last = PO_all.groupby("party").agg(last_order=("po_date", "max"), first_order=("po_date", "min"), pos=("po_no", "count"),
                                      value=("order_value", "sum"), gp=("gp_dispatched", "sum"), rev=("rev_cp_dispatched", "sum"),
                                      disc=("avg_disc", "mean"), zone=("zone", "first"), salesman=("salesman", "first")).reset_index()
    last["recency_days"] = (asof - last["last_order"]).dt.days
    last["gp_%"] = last["gp"] / last["rev"].replace(0, np.nan) * 100
    last["segment"] = np.select([last["recency_days"] <= thr, last["recency_days"] <= 2 * thr], ["Active", "Cooling"], default="Dormant")
    cm = D["clients"].copy()
    never = cm[~cm["party_key"].isin(etl.party_key(PO_all["party"]))]
    c = st.columns(5)
    c[0].metric("Clients in master", num(len(cm)))
    c[1].metric("Ordering (in data)", num(len(last)))
    c[2].metric("Active", num((last["segment"] == "Active").sum()))
    c[3].metric("Dormant", num((last["segment"] == "Dormant").sum()))
    c[4].metric("Never ordered", num(len(never)))
    top10 = last.nlargest(10, "value")["value"].sum() / last["value"].sum() * 100
    st.caption(f"Top 10 clients contribute {top10:.0f}% of order value.")
    a, b = st.columns(2)
    with a:
        sg = last.groupby("segment").agg(clients=("party", "count"), value=("value", "sum")).reset_index()
        show(px.bar(sg, x="segment", y="value", text="clients", color="segment", title="Value by client segment (label = clients)",
                    color_discrete_map={"Active": TEAL, "Cooling": AMBER, "Dormant": RED}).update_layout(showlegend=False))
    with b:
        zz = cm.groupby("zone").size().reset_index(name="clients")
        show(px.bar(zz, x="zone", y="clients", title="Clients by zone (master)", color_discrete_sequence=[BLUE]))
    st.markdown("**Client scorecard**")
    table(last.drop(columns=["rev"]).sort_values("value", ascending=False), 380)
    download(last, "client_scorecard", "dl_cl")
    with st.expander(f"Dormant clients - last order more than {thr} days ago"):
        table(last[last["segment"] != "Active"].sort_values("value", ascending=False)[["party", "last_order", "recency_days", "pos", "value", "salesman"]], 300)
    with st.expander("Clients in master that never ordered"):
        table(never[["client_code", "party", "city", "state", "zone", "status", "sales_manager"]], 300)

# ====================================================================== 11 DATA QUALITY
with tabs[10]:
    st.caption("Reconciliation checks across the five tables. Fix the source sheets, then press Refresh data.")
    summary = pd.DataFrame([{"Check": k, "Rows": len(v)} for k, v in D["dq"].items()])
    table(summary, 480)
    for k, v in D["dq"].items():
        if len(v):
            with st.expander(f"{k}  ({len(v)})"):
                table(v, 280)
                download(v, "dq_" + k[:25].replace(" ", "_"), "dq_" + k[:20])

# ====================================================================== 12 MAPPING & EXPORT
with tabs[11]:
    st.markdown("**Which sheet column feeds each field** — anything marked *position* or *missing* needs a look.")
    mp = D["mapping"]
    bad = mp[mp["Matched by"].isin(["missing"]) | mp["Matched by"].str.startswith("position")]
    if len(bad):
        st.warning(f"{len(bad)} fields were found by column position or not found at all.")
        table(bad, 260)
    with st.expander("Full mapping"):
        table(mp, 420)

    def to_excel() -> bytes:
        bio = BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as xw:
            PO.drop(columns=["party_key"], errors="ignore").to_excel(xw, "PO_level", index=False)
            L.to_excel(xw, "Order_lines", index=False)
            etl.inventory_view(D["fg"], L_all, asof).to_excel(xw, "Inventory", index=False)
            for k, v in D["dq"].items():
                if len(v):
                    v.to_excel(xw, k[:28].replace("/", "-").replace(">", "gt"), index=False)
        return bio.getvalue()

    st.download_button("⬇ Download all reports (Excel)", to_excel(), "order_to_cash_reports.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    pick = st.selectbox("Preview table", ["PO level (joined)", "Order lines", "Sales_Data (clean)", "FR1 (clean)", "Client_Master (clean)", "Finished_Goods (clean)"])
    frame = {"PO level (joined)": PO, "Order lines": L, "Sales_Data (clean)": D["sales"], "FR1 (clean)": D["fr1"],
             "Client_Master (clean)": D["clients"], "Finished_Goods (clean)": D["fg"]}[pick]
    table(frame.head(500), 420)
