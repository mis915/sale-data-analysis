# Order-to-Cash Dashboard (Streamlit)

Reports from Client_Master, Finished_Goods, FR1 (packing), Sales_Data (invoices) and Order_List,
joined on PO number (`PO_Number` in Order_List = `PO No.` in Sales_Data = `PO No.` in FR1).

Tabs: Overview · Sales & Orders · Pending & Fulfilment · Lead time & On-time · Packing & Dispatch · Logistics ·
Products (ABC) · Inventory (MSL / reorder) · Gross Profit · Clients (dormant / scorecard) · Data quality · Column mapping & Excel export.

## Gross profit
`Net sales = qty x ITEM_PRICE x (1 - Disc%)`, `GP = Net sales - qty x CP` (Order_List column V).
"Dispatched" basis uses Dispatch_Qty, "Ordered" basis uses ORDER_QTY. Lines with no CP are excluded and counted.
If column V is the *total* cost of the line instead of per-unit cost, switch it in the sidebar.

## Run locally
    pip install -r requirements.txt
    streamlit run app.py          # starts in Demo-data mode (no secrets needed)

## Connect your Google Sheets (once)
1. Google Cloud console -> create project -> enable **Google Sheets API** and **Google Drive API**.
2. IAM -> Service accounts -> create -> Keys -> Add key -> JSON (download).
3. Open each of the 4 Google Sheet files -> Share -> add the service account e-mail as **Viewer**.
4. Put the values in `.streamlit/secrets.toml` locally (see `secrets.toml.example`).

## Deploy on share.streamlit.io
1. Create a GitHub repo, push this folder (`secrets.toml` is git-ignored).
2. share.streamlit.io -> New app -> pick repo / branch, main file `app.py`.
3. Advanced settings -> Secrets -> paste the contents of your filled `secrets.toml.example`.
4. Deploy. Data refreshes every 10 minutes, or press **Refresh data** in the sidebar.
5. Keep the repo private and restrict viewers (App settings -> Sharing) - this app shows customer and margin data.
