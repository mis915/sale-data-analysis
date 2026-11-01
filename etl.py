"""
etl.py - cleaning, joining and metric calculation for the order-to-dispatch dashboard.

Input  : 5 raw tables (DataFrames of strings, exactly as they come out of Google Sheets)
           client_master, finished_goods, fr1, sales_data, order_list
Output : dict with clean line-level and PO-level tables + data-quality checks.

Columns are found by NAME first (several aliases), then by sheet column LETTER as a fallback.
The "Column mapping" table in the app shows exactly which source column was used for every field.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------------------
# generic helpers
# --------------------------------------------------------------------------------------


def _norm(x) -> str:
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def letter_to_idx(letter: str) -> int:
    n = 0
    for ch in letter.upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def dedupe_columns(cols) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for i, c in enumerate(cols):
        c = str(c).strip() or f"col_{i}"
        if c in seen:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out


def frame_from_values(values: list[list]) -> pd.DataFrame:
    """Google Sheets get_all_values() -> DataFrame (row 1 = header)."""
    if not values:
        return pd.DataFrame()
    header = dedupe_columns(values[0])
    w = len(header)
    rows = [(list(r) + [""] * (w - len(r)))[:w] for r in values[1:]]
    df = pd.DataFrame(rows, columns=header, dtype="object")
    df = df.apply(lambda c: c.astype(str).str.strip())
    df = df.replace("", np.nan)
    return df.dropna(how="all").reset_index(drop=True)


def to_num(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    t = s.astype(str).str.replace(r"[₹,%\s]|Rs\.?", "", regex=True)
    t = t.replace({"": np.nan, "nan": np.nan, "None": np.nan, "<NA>": np.nan, "-": np.nan})
    return pd.to_numeric(t, errors="coerce")


_NUMDATE = re.compile(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})")


def to_date(s: pd.Series, dayfirst_default: bool = False) -> pd.Series:
    """Parse dates; auto-detects d/m vs m/d per column (looks for a part > 12)."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    t = s.astype(object).where(s.notna(), None)
    t = t.map(lambda v: None if v is None or str(v).strip() in ("", "nan", "None", "NaT", "<NA>") else str(v).strip())
    ex = pd.Series([m.groups()[:2] if (m := _NUMDATE.match(v)) else None for v in t.dropna()], dtype=object).dropna()
    dayfirst = dayfirst_default
    if len(ex):
        a = pd.Series([float(x[0]) for x in ex])
        b = pd.Series([float(x[1]) for x in ex])
        if (a > 12).any() and not (b > 12).any():
            dayfirst = True
        elif (b > 12).any() and not (a > 12).any():
            dayfirst = False
    return pd.to_datetime(t, dayfirst=dayfirst, errors="coerce", format="mixed")


def norm_po(s: pd.Series) -> pd.Series:
    """DO-571 / DO-0571 / do 0571  ->  DO-0571"""
    t = s.astype(object).where(s.notna(), "").astype(str).str.strip().str.upper()
    ex = t.str.extract(r"^([A-Z]+)[\s\-_/]*0*(\d+)$")
    key = ex[0] + "-" + ex[1].str.zfill(4)
    key = key.where(ex[0].notna(), t)
    return key.replace({"": np.nan, "NAN": np.nan})


def party_key(s: pd.Series) -> pd.Series:
    return s.astype(object).where(s.notna(), "").astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)


# --------------------------------------------------------------------------------------
# column specs: field -> (aliases, sheet letter fallback or None, kind)
# --------------------------------------------------------------------------------------

ORDER_SPEC = {
    "po_no": (["PO_Number", "PO Number", "PO No.", "PO No"], "C", "po"),
    "po_date": (["PO_Date", "PO Date"], "B", "date"),
    "party": (["PARTY NAME", "Party_Name", "Party Name"], "D", "dim"),
    "planned_dispatch": (["Dispatch_Date", "Dispatch Date", "Planned_Dispatch"], "E", "date"),
    "delivery_partner": (["Delivery_Partner", "Delivery Partner"], "F", "dim"),
    "city": (["City"], "G", "dim"),
    "state": (["State"], "H", "dim"),
    "item_code": (["ITEM_CODE", "Item Code"], "I", "text"),
    "cat_code": (["CAT.CODE", "CAT CODE", "Catalogue_Code"], "J", "text"),
    "brand": (["BRAND"], "K", "dim"),
    "category": (["CATEGORY", "Item_Category"], "L", "dim"),
    "item": (["ITEM", "Item_Name"], "M", "dim"),
    "size": (["SIZE"], "N", "text"),
    "variation": (["VARIATION"], "O", "text"),
    "finish": (["FINISH"], "P", "dim"),
    "item_price": (["ITEM_PRICE", "Item Price"], "Q", "num"),
    "order_qty": (["ORDER_QTY", "Order Qty"], "R", "num"),
    "item_amount": (["ITEM_AMOUNT"], "S", "num"),
    "po_amount": (["PO_AMOUNT"], "T", "num"),
    "disc": (["Disc.", "Disc", "Discount"], "U", "num"),
    "cp": (["CP", "CV", "Cost Price", "Cost Value"], "V", "num"),
    "dispatch_qty": (["Dispatch_Qty", "Dispatch Qty"], "W", "num"),
    "dispatch_ts": (["Dispatch_Timestamp", "Dispatched_Timestamp"], "X", "date"),
}

SALES_SPEC = {
    "po_date": (["PO_Date"], "B", "date"),
    "po_no": (["PO No.", "PO No", "PO_Number"], "C", "po"),
    "party": (["Party_Name", "Party Name"], "D", "dim"),
    "planned_dispatch": (["Planned_Dispatch", "Planned Dispatch"], "E", "date"),
    "delivery_partner": (["Delivery_Partner"], "F", "dim"),
    "city": (["City"], "G", "dim"),
    "brand": (["BRAND"], "H", "dim"),
    "item_count": (["Item_Count"], "I", "num"),
    "po_amt_mrp": (["PO AMT(MRP)", "PO AMT (MRP)", "PO_AMT_MRP"], "J", "num"),
    "discount": (["Discount%", "Discount %", "Discount"], "K", "num"),
    "po_amount": (["PO AMOUNT", "PO_AMOUNT"], "L", "num"),
    "packing_date": (["Packing_Date", "Packing Date"], "M", "date"),
    "delivery_note_no": (["Delivery Note No", "Delivery Note No."], None, "text"),
    "delivery_note_date": (["Delivery Note Date"], None, "date"),
    "invoice_no": (["Invoice No.", "Invoice No", "Invoice_No"], None, "text"),
    "invoice_date": (["Invoice Date", "Invoice_Date"], None, "date"),
    "invoice_amount": (["Invoice Amount", "Invoice_Amount"], None, "num"),
    "cases": (["No. of Cases dispatched", "No of Cases dispatched", "Cases"], None, "num"),
    "partial": (["Does it Partial Dispatch?", "Does it Partial Dispatch", "Partial Dispatch"], None, "text"),
    "gr_no": (["GR No.", "GR No"], None, "text"),
    "gr_date": (["GR Date"], None, "date"),
    "weight": (["Weight of the consignment", "Weight"], None, "num"),
    "loading_charge": (["Loading unloading charge", "Loading Unloading Charge"], None, "num"),
    "bilty_amount": (["Billy Amount", "Bilty Amount", "Builty Amount"], None, "num"),
    "dispatched_date": (["Dispatched_Date", "Dispatched Date"], "AL", "date"),
    "tour": (["Tour"], "AM", "dim"),
    "salesman": (["Salesman"], "AN", "dim"),
}

FR1_SPEC = {
    "ts": (["Timestamp"], "A", "date"),
    "po_no": (["PO No.", "PO No", "PO_Number"], "B", "po"),
    "party": (["Party_Name", "Party Name"], "C", "dim"),
    "delivery_partner": (["Delivery_Partner"], "D", "dim"),
    "city": (["City"], "E", "dim"),
    "brand": (["BRAND"], "F", "dim"),
    "packed": (["Confirm that Packing has been done ?", "Confirm that Packing has been done?"], "G", "text"),
    "emp_id": (["Emp_id", "Emp_Id"], "H", "text"),
    "emp_name": (["Emp_Name"], "I", "dim"),
    "partial": (["Does it Partial Dispatch?", "Does it Partial Dispatch"], None, "text"),
}

CLIENT_SPEC = {
    "client_code": (["CLIENT CODE", "Client Code"], None, "text"),
    "party": (["Dealer Name", "DEALER NAME"], "D", "dim"),
    "gst": (["GST NO", "GST No."], None, "text"),
    "status": (["STATUS"], None, "dim"),
    "type": (["TYPE"], None, "dim"),
    "district": (["DISTRICT"], None, "dim"),
    "pincode": (["PINCODE", "Pin Code"], None, "text"),
    "city": (["CITY"], None, "dim"),
    "zone": (["ZONE"], None, "dim"),
    "sales_manager": (["SALES MANAGER", "Sales Manager"], None, "dim"),
    "state": (["STATE"], None, "dim"),
    "tour": (["TOUR"], None, "dim"),
}

FG_SPEC = {
    "code": (["Code"], "A", "text"),
    "cat_code": (["Catalogue_Code"], "B", "text"),
    "brand": (["Brand"], "C", "dim"),
    "category": (["Item_Category"], "D", "dim"),
    "item": (["Item_Name"], "E", "dim"),
    "size": (["Size/thickness", "Size"], "F", "text"),
    "spec": (["Specification"], "G", "text"),
    "mrp": (["Price per Unit"], "H", "num"),
    "box_price": (["Outer Box Price"], "I", "num"),
    "image": (["Item_Image"], "J", "text"),
    "finish": (["Finish"], "K", "dim"),
    "variation": (["Variation"], "L", "dim"),
    "pcs_box": (["PCS/Outer_Box", "PCS/Outer Box"], "M", "num"),
    "total_out": (["Total_Out"], "N", "num"),
    "stock": (["Current_Stock"], "O", "num"),
    "msl": (["MSL"], None, "num"),
    "daily": (["1_Day_Consump", "1_Day_Consumption"], None, "num"),
    "safety": (["Safety_Factor"], None, "num"),
    "lead_time": (["Lead_Time"], None, "num"),
}

RAW_NAMES = {
    "client_master": "Client_Master",
    "finished_goods": "Finished_Goods",
    "fr1": "FR1",
    "sales_data": "Sales_Data",
    "order_list": "Order_List",
}


def standardize(raw: pd.DataFrame, spec: dict, table: str, dayfirst: bool = False):
    """Return (clean DataFrame with logical column names, mapping report rows)."""
    cols = list(raw.columns)
    nmap: dict[str, str] = {}
    for c in cols:
        nmap.setdefault(_norm(c), c)
    used: set[str] = set()
    out: dict[str, pd.Series] = {}
    report = []
    for key, (aliases, letter, kind) in spec.items():
        col, how = None, "missing"
        for a in aliases:
            c = nmap.get(_norm(a))
            if c is not None and c not in used:
                col, how = c, "name"
                break
        if col is None:
            for a in aliases:
                na = _norm(a)
                if len(na) >= 6:
                    hit = [c for nc, c in nmap.items() if nc.startswith(na) and c not in used]
                    if hit:
                        col, how = hit[0], "name (partial)"
                        break
        if col is None and letter:
            i = letter_to_idx(letter)
            if i < len(cols) and cols[i] not in used:
                col, how = cols[i], f"position {letter}"
        if col is None:
            if kind == "num":
                out[key] = pd.Series(np.nan, index=raw.index, dtype=float)
            elif kind == "date":
                out[key] = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")
            else:
                out[key] = pd.Series("Unknown" if kind == "dim" else np.nan, index=raw.index, dtype=object)
        else:
            used.add(col)
            s = raw[col]
            if kind == "num":
                out[key] = to_num(s)
            elif kind == "date":
                out[key] = to_date(s, dayfirst)
            elif kind == "po":
                out[key] = norm_po(s)
            elif kind == "dim":
                v = s.astype(object).where(s.notna(), "").astype(str).str.strip()
                out[key] = v.replace({"": "Unknown", "nan": "Unknown"})
            else:
                v = s.astype(object).where(s.notna(), "").astype(str).str.strip()
                out[key] = v.replace({"": np.nan, "nan": np.nan})
        report.append({"Table": table, "Field": key, "Source column": col or "-", "Matched by": how})
    return pd.DataFrame(out), report


# --------------------------------------------------------------------------------------
# main build
# --------------------------------------------------------------------------------------


def _first(s):
    s = s.dropna()
    return s.iloc[0] if len(s) else np.nan


def _unknown_to_nan(s: pd.Series) -> pd.Series:
    return s.replace({"Unknown": np.nan})


def build(raw: dict[str, pd.DataFrame], cp_per_unit: bool = True) -> dict:
    report: list[dict] = []

    # ---------------- Order_List (line level) ----------------
    o, r = standardize(raw["order_list"], ORDER_SPEC, "Order_List", dayfirst=False)
    report += r
    o = o[o["po_no"].notna()].copy().reset_index(drop=True)
    o["disc"] = o["disc"].fillna(0.0)
    if o["disc"].max() <= 1.0 and o["disc"].max() > 0:
        o["disc"] = o["disc"] * 100
    o["order_qty"] = o["order_qty"].fillna(0.0)
    o["dispatch_qty"] = o["dispatch_qty"].fillna(0.0)
    o["gross_value"] = o["order_qty"] * o["item_price"]
    o["gross_value"] = o["gross_value"].fillna(o["item_amount"])
    o["order_value"] = o["gross_value"] * (1 - o["disc"] / 100)
    o["net_rate"] = o["item_price"] * (1 - o["disc"] / 100)
    o["dispatch_value"] = o["dispatch_qty"] * o["net_rate"]
    if cp_per_unit:
        o["cp_unit"] = o["cp"]
    else:  # column V holds the total cost of the line
        o["cp_unit"] = o["cp"] / o["order_qty"].replace(0, np.nan)
    o["has_cp"] = o["cp_unit"].notna()
    o["rev_cp_ordered"] = np.where(o["has_cp"], o["order_value"], 0.0)
    o["rev_cp_dispatched"] = np.where(o["has_cp"], o["dispatch_value"], 0.0)
    o["cost_ordered"] = np.where(o["has_cp"], o["order_qty"] * o["cp_unit"], 0.0)
    o["cost_dispatched"] = np.where(o["has_cp"], o["dispatch_qty"] * o["cp_unit"], 0.0)
    o["gp_ordered"] = o["rev_cp_ordered"] - o["cost_ordered"]
    o["gp_dispatched"] = o["rev_cp_dispatched"] - o["cost_dispatched"]
    o["pending_qty"] = (o["order_qty"] - o["dispatch_qty"]).clip(lower=0)
    o["pending_value"] = o["pending_qty"] * o["net_rate"]
    o["po_month"] = o["po_date"].dt.to_period("M").dt.to_timestamp()

    # ---------------- Sales_Data (invoice level) ----------------
    s, r = standardize(raw["sales_data"], SALES_SPEC, "Sales_Data", dayfirst=True)
    report += r
    s = s[s["po_no"].notna()].copy().reset_index(drop=True)

    # ---------------- FR1 (packing confirmation) ----------------
    f, r = standardize(raw["fr1"], FR1_SPEC, "FR1", dayfirst=False)
    report += r
    img_cols = [c for c in raw["fr1"].columns if _norm(c).startswith("image")]
    f["n_images"] = raw["fr1"][img_cols].notna().sum(axis=1) if img_cols else 0
    f = f[f["po_no"].notna()].copy().reset_index(drop=True)

    # ---------------- Client_Master ----------------
    c, r = standardize(raw["client_master"], CLIENT_SPEC, "Client_Master")
    report += r
    c["party_key"] = party_key(c["party"])
    c = c[c["party_key"] != ""].drop_duplicates("party_key").reset_index(drop=True)

    # ---------------- Finished_Goods ----------------
    fg, r = standardize(raw["finished_goods"], FG_SPEC, "Finished_Goods")
    report += r
    fg = fg[fg["code"].notna() & (fg["code"].str.upper() != "NA")].copy().reset_index(drop=True)

    # ---------------- PO level ----------------
    po = (
        o.groupby("po_no")
        .agg(
            po_date=("po_date", "min"),
            party=("party", "first"),
            brand=("brand", "first"),
            city=("city", "first"),
            state=("state", "first"),
            lines=("item_code", "count"),
            order_qty=("order_qty", "sum"),
            dispatch_qty=("dispatch_qty", "sum"),
            gross_value=("gross_value", "sum"),
            order_value=("order_value", "sum"),
            dispatch_value=("dispatch_value", "sum"),
            pending_value=("pending_value", "sum"),
            rev_cp_dispatched=("rev_cp_dispatched", "sum"),
            rev_cp_ordered=("rev_cp_ordered", "sum"),
            gp_dispatched=("gp_dispatched", "sum"),
            gp_ordered=("gp_ordered", "sum"),
            avg_disc=("disc", "mean"),
            planned_dispatch_ol=("planned_dispatch", "min"),
            delivery_partner_ol=("delivery_partner", "first"),
            last_dispatch_ts=("dispatch_ts", "max"),
            sheet_po_amount=("po_amount", "first"),
        )
        .reset_index()
    )

    sg = (
        s.groupby("po_no")
        .agg(
            planned_dispatch_sd=("planned_dispatch", "min"),
            packing_date=("packing_date", "min"),
            dispatched_date=("dispatched_date", "max"),
            invoice_date=("invoice_date", "max"),
            gr_date=("gr_date", "max"),
            invoice_no=("invoice_no", _first),
            invoices=("invoice_no", "nunique"),
            invoice_amount=("invoice_amount", "sum"),
            cases=("cases", "sum"),
            weight=("weight", "sum"),
            loading_charge=("loading_charge", "sum"),
            bilty_amount=("bilty_amount", "sum"),
            delivery_partner_sd=("delivery_partner", "first"),
            salesman=("salesman", "first"),
            tour=("tour", "first"),
            partial_sd=("partial", lambda x: "Yes" if x.astype(str).str.lower().str.startswith("y").any() else "No"),
            po_amount_sd=("po_amount", "first"),
            po_amt_mrp=("po_amt_mrp", "first"),
            brand_sd=("brand", "first"),
        )
        .reset_index()
    )
    sg["in_sales"] = True

    fg1 = (
        f.groupby("po_no")
        .agg(
            pack_ts=("ts", "max"),
            packed=("packed", lambda x: "Yes" if x.astype(str).str.lower().str.startswith("y").any() else "No"),
            emp_name=("emp_name", "first"),
            n_images=("n_images", "sum"),
            partial_fr1=("partial", lambda x: "Yes" if x.astype(str).str.lower().str.startswith("y").any() else "No"),
            delivery_partner_fr1=("delivery_partner", "first"),
        )
        .reset_index()
    )
    fg1["in_fr1"] = True

    po = po.merge(sg, on="po_no", how="left").merge(fg1, on="po_no", how="left")
    po["in_sales"] = po["in_sales"].fillna(False).astype(bool)
    po["in_fr1"] = po["in_fr1"].fillna(False).astype(bool)

    po["delivery_partner"] = (
        _unknown_to_nan(po["delivery_partner_sd"].astype(object))
        .fillna(_unknown_to_nan(po["delivery_partner_fr1"].astype(object)))
        .fillna(_unknown_to_nan(po["delivery_partner_ol"].astype(object)))
        .fillna("Unknown")
    )
    po["brand"] = _unknown_to_nan(po["brand"]).fillna(_unknown_to_nan(po["brand_sd"].astype(object))).fillna("Unknown")
    po["salesman"] = po["salesman"].astype(object).fillna("Unknown")
    po["tour"] = po["tour"].astype(object).fillna("Unknown")
    po["emp_name"] = po["emp_name"].astype(object).fillna("Unknown")
    po["planned_dispatch"] = po["planned_dispatch_sd"].fillna(po["planned_dispatch_ol"])
    po["pack_date"] = po["packing_date"].fillna(po["pack_ts"])
    po["dispatch_date"] = po["dispatched_date"].fillna(po["last_dispatch_ts"])

    def days(a, b):
        return (po[b] - po[a]).dt.total_seconds() / 86400

    po["d_po_to_pack"] = days("po_date", "pack_date")
    po["d_pack_to_dispatch"] = days("pack_date", "dispatch_date")
    po["d_po_to_dispatch"] = days("po_date", "dispatch_date")
    po["d_dispatch_to_invoice"] = days("dispatch_date", "invoice_date")
    po["d_dispatch_to_gr"] = days("dispatch_date", "gr_date")
    for k in ["d_po_to_pack", "d_pack_to_dispatch", "d_po_to_dispatch", "d_dispatch_to_invoice", "d_dispatch_to_gr"]:
        po.loc[po[k] < 0, k] = np.nan  # impossible order of events -> ignore, shown in data quality
    po["delay_days"] = (po["dispatch_date"].dt.normalize() - po["planned_dispatch"].dt.normalize()).dt.days
    po["on_time"] = np.where(po["delay_days"].notna(), po["delay_days"] <= 0, np.nan)

    has_qty = o["dispatch_qty"].sum() > 0
    if has_qty:
        po["status"] = np.select(
            [po["dispatch_qty"] <= 0, po["dispatch_qty"] >= po["order_qty"] - 1e-9],
            ["Not dispatched", "Fully dispatched"],
            default="Partially dispatched",
        )
    else:
        po["status"] = np.where(po["dispatch_date"].notna(), "Fully dispatched", "Not dispatched")
    po["fill_rate"] = np.where(po["order_qty"] > 0, po["dispatch_qty"] / po["order_qty"], np.nan)
    po["invoiced"] = po["invoice_no"].notna() | (po["invoice_amount"].fillna(0) > 0)
    po["po_month"] = po["po_date"].dt.to_period("M").dt.to_timestamp()

    # client master
    po["party_key"] = party_key(po["party"])
    cm = c[["party_key", "client_code", "status", "type", "zone", "sales_manager", "state", "district"]].rename(
        columns={"status": "client_status", "type": "client_type", "state": "client_state", "district": "client_district"}
    )
    po = po.merge(cm, on="party_key", how="left")
    po["zone"] = po["zone"].fillna("Unmapped")
    po["state"] = _unknown_to_nan(po["state"].astype(object)).fillna(po["client_state"]).fillna("Unknown")
    po["sales_manager"] = po["sales_manager"].fillna("Unmapped")
    po["in_client_master"] = po["client_code"].notna()

    # propagate PO level attributes down to lines
    attrs = po[["po_no", "zone", "salesman", "tour", "sales_manager", "delivery_partner", "status"]].rename(
        columns={"delivery_partner": "delivery_partner_po", "status": "po_status"}
    )
    o = o.merge(attrs, on="po_no", how="left")

    # ---------------- data quality ----------------
    fgcodes = set(fg["code"].dropna())
    dq: dict[str, pd.DataFrame] = {}
    dq["POs in Order_List but not in Sales_Data"] = po.loc[~po["in_sales"], ["po_no", "po_date", "party", "order_value", "status"]]
    dq["POs in Sales_Data but not in Order_List"] = (
        s.loc[~s["po_no"].isin(set(o["po_no"])), ["po_no", "po_date", "party", "po_amount", "invoice_no", "invoice_amount"]]
        .drop_duplicates("po_no")
    )
    dq["POs in FR1 (packing) but not in Order_List"] = f.loc[
        ~f["po_no"].isin(set(o["po_no"])), ["po_no", "ts", "party", "emp_name"]
    ].drop_duplicates("po_no")
    t = po[po["in_sales"] & (po["po_amount_sd"] > 0) & (po["order_value"] > 0)].copy()
    t["diff_pct"] = (t["po_amount_sd"] - t["order_value"]) / t["order_value"] * 100
    dq["PO amount differs by >2% (Sales_Data vs Order_List)"] = t.loc[
        t["diff_pct"].abs() > 2, ["po_no", "party", "order_value", "po_amount_sd", "diff_pct"]
    ]
    t = po[po["invoiced"] & (po["dispatch_value"] > 0)].copy()
    t["diff_pct"] = (t["invoice_amount"] - t["dispatch_value"]) / t["dispatch_value"] * 100
    dq["Invoice amount differs by >5% from dispatched value"] = t.loc[
        t["diff_pct"].abs() > 5, ["po_no", "party", "dispatch_value", "invoice_amount", "diff_pct"]
    ]
    dq["Dispatch qty more than order qty"] = o.loc[
        o["dispatch_qty"] > o["order_qty"], ["po_no", "party", "item_code", "item", "order_qty", "dispatch_qty"]
    ]
    dq["Lines without CP (cost) - excluded from GP"] = o.loc[~o["has_cp"], ["po_no", "party", "item_code", "item", "order_qty", "item_price"]]
    dq["Lines selling below cost"] = o.loc[
        o["has_cp"] & (o["net_rate"] < o["cp_unit"]), ["po_no", "party", "item_code", "item", "net_rate", "cp_unit", "disc"]
    ]
    dq["Item codes not found in Finished_Goods"] = (
        o.loc[~o["item_code"].isin(fgcodes), ["item_code", "item", "category"]].drop_duplicates()
    )
    dq["Parties not found in Client_Master"] = po.loc[~po["in_client_master"], ["party"]].drop_duplicates()
    dq["Dates out of order (dispatch before PO / invoice before dispatch)"] = po.loc[
        ((po["dispatch_date"] < po["po_date"]) | (po["invoice_date"] < po["dispatch_date"])),
        ["po_no", "party", "po_date", "pack_date", "dispatch_date", "invoice_date"],
    ]
    dq["Duplicate item lines inside a PO"] = o.loc[
        o.duplicated(["po_no", "item_code"], keep=False) & o["item_code"].notna(), ["po_no", "item_code", "item", "order_qty"]
    ]
    dq["Finished goods with negative stock"] = fg.loc[fg["stock"] < 0, ["code", "item", "category", "stock"]]

    return {
        "lines": o,
        "po": po,
        "sales": s,
        "fr1": f,
        "clients": c,
        "fg": fg,
        "mapping": pd.DataFrame(report),
        "dq": dq,
    }


# --------------------------------------------------------------------------------------
# inventory view
# --------------------------------------------------------------------------------------


def inventory_view(fg: pd.DataFrame, lines: pd.DataFrame, asof: pd.Timestamp, target_mult: float = 2.0, window: int = 90) -> pd.DataFrame:
    f = fg.copy()
    pend = lines.groupby("item_code").agg(pending_qty=("pending_qty", "sum"), ordered_qty=("order_qty", "sum"))
    cutoff = asof - pd.Timedelta(days=window)
    recent = lines[(lines["po_date"] >= cutoff) & (lines["po_date"] <= asof)].groupby("item_code")["dispatch_qty"].sum().rename("dispatched_recent")
    f = f.merge(pend, left_on="code", right_index=True, how="left").merge(recent, left_on="code", right_index=True, how="left")
    for k in ["pending_qty", "ordered_qty", "dispatched_recent"]:
        f[k] = f[k].fillna(0.0)
    f["stock"] = f["stock"].fillna(0.0)
    f["actual_daily"] = f["dispatched_recent"] / window
    f["days_cover"] = np.where(f["daily"] > 0, f["stock"] / f["daily"], np.nan)
    f["free_stock"] = f["stock"] - f["pending_qty"]
    f["shortage_vs_pending"] = (f["pending_qty"] - f["stock"]).clip(lower=0)
    f["status"] = np.select(
        [f["stock"] <= 0, f["stock"] < f["msl"], f["stock"] > f["msl"] * 3],
        ["Out / negative", "Below MSL", "Overstock (>3x MSL)"],
        default="OK",
    )
    f["target_stock"] = f["msl"].fillna(0) * target_mult
    need = (f["target_stock"] - f["free_stock"]).clip(lower=0)
    box = f["pcs_box"].where(f["pcs_box"] > 0)
    f["reorder_qty"] = np.where(box.notna(), np.ceil(need / box) * box, np.ceil(need))
    f["stock_value_mrp"] = f["stock"].clip(lower=0) * f["mrp"]
    return f
