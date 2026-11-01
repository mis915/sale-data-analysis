"""Synthetic data with the SAME headers / formats as the real sheets - used for demo mode and tests."""
from __future__ import annotations

import numpy as np
import pandas as pd


def make_demo(seed: int = 7, n_clients: int = 60, n_pos: int = 700) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    states = {
        "Uttar Pradesh": ["VARANASI", "PRAYAGRAJ", "KANPUR", "GORAKHPUR", "LUCKNOW", "AGRA"],
        "Rajasthan": ["KOTA", "JAIPUR", "BIKANER", "JODHPUR"],
        "Bihar": ["PATNA", "GAYA", "HAZARIBAGH"],
        "Odisha": ["BHUBANESHWAR", "JHARSUGUDA", "BERHAMPUR"],
        "Madhya Pradesh": ["BHOPAL", "SATNA", "NAGPUR"],
    }
    zone_of = {"Uttar Pradesh": "EAST", "Rajasthan": "NORTH", "Bihar": "EAST", "Odisha": "SOUTH", "Madhya Pradesh": "CENTER"}
    partners = ["SAFEXPRESS", "HEERA TPT", "NBET", "GLOBE TPT", "VRL", "PAWAN CARRYING", "SATNA EXPRESS"]
    salesmen = ["Raju Bajpai", "Ramesh Maurya", "Sunil Sharma", "Anil Sahni"]
    employees = ["Hridesh Khaitan", "Amit Mishra", "Sonu Kumar"]
    words = ["SHREEYAM", "MAHESHWARI", "VIKASH", "GIRDHAR", "NEW PRAYAG", "MAHARANI", "UPKAR", "JANTA", "BHAGWATI", "KALYANI",
             "MAA TARINI", "RAJESH", "SATGURU", "HIND", "LAXMI", "OM", "DAKSH", "RAMDEV", "PARAS", "SEVA"]
    suffix = ["HARDWARE", "TRADING CO.", "PLYWOOD", "ENTERPRISES", "GLASS HOUSE", "AGENCIES", "& SONS", "TRADERS"]

    # ---------------- Client_Master
    rows = []
    names = []
    for i in range(n_clients):
        st = list(states)[i % len(states)]
        city = states[st][i % len(states[st])]
        nm = f"{words[i % len(words)]} {suffix[(i * 3) % len(suffix)]}{'' if i < len(words) else ' ' + str(i)}"
        names.append((nm, st, city))
        rows.append({
            "Sr no": i + 1, "PARTY NAME": f"BNRDLR{i + 1:04d}", "CLIENT CODE": f"BNRDLR{i + 1:04d}", "Dealer Name": nm,
            "GST NO": f"09AAAPY{i:04d}F1ZX", "Address": f"Main Road, {city}", "STATUS": "ACTIVE" if rng.random() > 0.1 else "INACTIVE",
            "TYPE": "CRR", "DISTRICT": city, "PINCODE": str(200000 + i), "CITY": city, "ZONE": zone_of[st],
            "SALES MANAGER": ["Ramesh Maurya", "Raju Bajpai", "Sunil Sharma"][i % 3], "STATE": st, "TOUR": "TOUR-" + str(i % 5),
        })
    client_master = pd.DataFrame(rows).astype(str)

    # ---------------- Finished_Goods
    cats = {"Hinges": ("FITICO", 50, 300), "Coat Hanger": ("NEMANI", 40, 500), "Glass Bracket": ("NEMANI", 35, 160),
            "Shelf Bracket": ("NEMANI", 150, 450), "Castors": ("NEMANI", 200, 1500), "L Bracket": ("NEMANI", 100, 800),
            "Corner Zinc": ("NEMANI", 60, 400)}
    fg_rows = []
    k = 2
    for cat, (brand, lo, hi) in cats.items():
        for j in range(12):
            price = float(rng.integers(lo, hi))
            daily = round(float(rng.uniform(0.05, 12)), 2)
            safety = float(rng.choice([1, 1.1, 1.25, 1.5, 2]))
            lead = 20
            msl = round(daily * lead * safety)
            stock = int(rng.integers(-5, int(max(msl * 3.5, 20))))
            pcs = int(rng.choice([2, 6, 10, 20, 30, 40]))
            fg_rows.append({
                "Code": f"F0{k}", "Catalogue_Code": f"{cat[:2].upper()}-{j:03d}", "Brand": brand, "Item_Category": cat,
                "Item_Name": f"{cat.upper()} {j + 1}", "Size/thickness": f"{(j + 1) * 5} MM", "Specification": "SS 202",
                "Price per Unit": f"₹{price:,.2f}", "Outer Box Price": f"₹{price * pcs:,.2f}", "Item_Image": "",
                "Finish": ["GLOSS", "MATT", "ZINC"][j % 3], "Variation": "REGULAR", "PCS/Outer_Box": str(pcs),
                "Total_Out": str(int(rng.integers(100, 6000))), "Current_Stock": str(stock), "MSL": str(msl),
                "1_Day_Consump": f"{daily:.2f}", "Safety_Factor": str(safety), "Lead_Time": str(lead),
            })
            k += 1
    finished_goods = pd.DataFrame(fg_rows).astype(str)
    fg_num = pd.DataFrame(fg_rows)

    # ---------------- Order_List / Sales_Data / FR1
    start = pd.Timestamp("2025-04-01")
    ol, sd, fr = [], [], []
    for n in range(n_pos):
        nm, st, city = names[int(rng.integers(0, n_clients))]
        pdt = start + pd.Timedelta(days=int(rng.integers(0, 190)), hours=int(rng.integers(9, 18)), minutes=int(rng.integers(0, 59)))
        prefix = rng.choice(["DO", "RB", "RM", "SS"])
        po_raw = f"{prefix}-{n + 1:04d}" if rng.random() > 0.05 else f"{prefix}-{n + 1}"
        po_sd = f"{prefix}-{n + 1:04d}"
        partner = str(rng.choice(partners))
        planned = pdt + pd.Timedelta(days=int(rng.integers(5, 12)))
        disc = float(rng.choice([58, 60, 62, 62, 62, 56.88]))
        status = rng.choice(["full", "partial", "none"], p=[0.7, 0.12, 0.18])
        brand_po = str(rng.choice(["NEMANI", "FITICO"], p=[0.8, 0.2]))
        pool = fg_num[fg_num["Brand"] == brand_po]
        n_items = int(rng.integers(1, 7))
        total_net = 0.0
        disp_net = 0.0
        last_ts = None
        for _, it in pool.sample(min(n_items, len(pool)), random_state=int(rng.integers(0, 10_000))).iterrows():
            price = float(str(it["Price per Unit"]).replace("₹", "").replace(",", ""))
            qty = int(rng.integers(1, 40)) * int(it["PCS/Outer_Box"]) // int(it["PCS/Outer_Box"]) * int(rng.integers(1, 4))
            cp = round(price * (1 - disc / 100) * float(rng.uniform(0.55, 1.08)), 2)
            if rng.random() < 0.03:
                cp = np.nan
            dq = {"full": qty, "partial": int(qty * rng.uniform(0.3, 0.8)), "none": 0}[status]
            dts = planned + pd.Timedelta(days=int(rng.integers(-3, 6)), hours=3) if dq > 0 else None
            last_ts = dts if dts is not None else last_ts
            net = qty * price * (1 - disc / 100)
            total_net += net
            disp_net += dq * price * (1 - disc / 100)
            ol.append({
                "Timestamp": pdt.strftime("%m/%d/%Y %H:%M:%S"), "PO_Date": pdt.strftime("%m/%d/%Y"), "PO_Number": po_raw,
                "PARTY NAME": nm, "Dispatch_Date": planned.strftime("%m/%d/%Y"), "Delivery_Partner": partner, "City": city, "State": st,
                "ITEM_CODE": it["Code"], "CAT.CODE": it["Catalogue_Code"], "BRAND": brand_po, "CATEGORY": it["Item_Category"],
                "ITEM": it["Item_Name"], "SIZE": it["Size/thickness"], "VARIATION": "NA", "FINISH": it["Finish"],
                "ITEM_PRICE": f"{price:.0f}", "ORDER_QTY": str(qty), "ITEM_AMOUNT": f"{qty * price:.0f}", "PO_AMOUNT": "0",
                "Disc.": f"{disc:g}", "CP": "" if pd.isna(cp) else f"{cp:.2f}", "Dispatch_Qty": str(dq),
                "Dispatch_Timestamp": "" if dts is None else dts.strftime("%m/%d/%Y %H:%M:%S"),
            })
        for r in ol[-n_items:]:
            r["PO_AMOUNT"] = f"{total_net:.0f}"
        packed = pdt + pd.Timedelta(days=float(rng.uniform(0.5, 5)))
        fr.append({
            "Timestamp": packed.strftime("%m/%d/%Y %H:%M:%S"), "PO No.": po_sd, "Party_Name": nm, "Delivery_Partner": partner,
            "City": city, "BRAND": brand_po, "Confirm that Packing has been done ?": "Yes", "Emp_id": "BRN04",
            "Emp_Name": str(rng.choice(employees)), "Image_1": "x" if rng.random() > 0.2 else "", "Image_2": "x" if rng.random() > 0.5 else "",
            "Does it Partial Dispatch?": "Yes" if status == "partial" else "No",
        })
        if status != "none" and rng.random() > 0.05:
            disp = last_ts if last_ts is not None else planned
            inv_date = disp + pd.Timedelta(days=int(rng.integers(0, 3)))
            gr = disp + pd.Timedelta(days=int(rng.integers(2, 9)))
            wt = float(rng.uniform(15, 400))
            row = {
                "Timestamp": (disp).strftime("%d/%m/%Y %H:%M:%S"), "PO_Date": pdt.strftime("%d/%m/%Y"), "PO No.": po_sd,
                "Party_Name": nm, "Planned_Dispatch": planned.strftime("%d/%m/%Y"), "Delivery_Partner": partner, "City": city,
                "BRAND": brand_po, "Item_Count": str(n_items), "PO AMT(MRP)": f"{total_net / (1 - disc / 100):.0f}",
                "Discount%": f"{disc:g}", "PO AMOUNT": f"{total_net * float(rng.choice([1, 1, 1, 1.04])):.0f}",
                "Packing_Date": packed.strftime("%d-%b-%y %H:%M"), "Dispatch_Qty": "", "Delivery Note No": str(800 + n),
                "Delivery Note Date": disp.strftime("%d/%m/%Y"), "Invoice No.": str(1000 + n), "Invoice Date": inv_date.strftime("%d/%m/%Y"),
                "Invoice Amount": f"{disp_net:.0f}", "No. of Cases dispatched": str(int(rng.integers(1, 40))),
                "Does it Partial Dispatch?": "Yes" if status == "partial" else "No", "GR No.": str(10000 + n),
                "GR Date": gr.strftime("%d/%m/%Y"), "Weight of the consignment": f"{wt:.0f}",
                "Loading unloading charge": str(int(rng.choice([35, 70, 105, 140]))), "Billy Amount": f"{wt * rng.uniform(4, 9):.0f}",
                "Emp_Id": "BRN06", "Emp_Name": "Brijesh", "Datetime": disp.strftime("%d/%m/%Y %H:%M"),
            }
            for i in range(8):
                row[f"filler_{i}"] = ""
            row["Dispatched_Date"] = disp.strftime("%d-%b-%y")
            row["Tour"] = "TOUR-" + str(n % 5)
            row["Salesman"] = str(rng.choice(salesmen))
            sd.append(row)
    return {
        "client_master": client_master,
        "finished_goods": finished_goods,
        "fr1": pd.DataFrame(fr).astype(str).replace("", np.nan).fillna(""),
        "sales_data": pd.DataFrame(sd).astype(str),
        "order_list": pd.DataFrame(ol).astype(str),
    }
