import os

import frappe
from frappe.modules.import_file import import_file_by_path


def reload_pharmacy():
    """Re-import the Pharmacy number cards, dashboard, workspace and sidebar from files."""
    base = frappe.get_app_path("hospital", "durga_hospital")
    for kind in ("number_card", "dashboard_chart", "dashboard", "workspace", "sidebar"):
        for root, _dirs, files in os.walk(os.path.join(base, kind)):
            for name in files:
                if name.endswith(".json"):
                    path = os.path.join(root, name)
                    print(kind, name, import_file_by_path(path, force=True, ignore_version=True))
    frappe.db.commit()
    frappe.clear_cache()


def add_charts():
    """Put the four Pharmacy charts on the workspace and the Dashboard page."""
    import json
    import uuid

    charts = ["Sales Trend", "Purchase Trend", "Items by Item Group",
              "Purchase Receipts by Supplier"]

    def bid():
        return uuid.uuid4().hex[:10]

    ws = frappe.get_doc("Workspace", "Pharmacy")
    blocks = [
        b for b in json.loads(ws.content)
        if b["type"] != "chart"
        and not (b["type"] == "header" and "Trends" in b["data"]["text"])
    ]
    at = next(
        (i for i, b in enumerate(blocks)
         if b["type"] == "header" and "Quick Actions" in b["data"]["text"]),
        len(blocks),
    )
    new = [{"id": bid(), "type": "header",
            "data": {"text": '<span class="h4"><b>Trends</b></span>', "col": 12}}]
    new += [{"id": bid(), "type": "chart", "data": {"chart_name": c, "col": 6}}
            for c in charts]
    blocks[at:at] = new
    ws.content = json.dumps(blocks)
    ws.set("charts", [{"chart_name": c, "label": c} for c in charts])
    ws.save()

    dash = frappe.get_doc("Dashboard", "Pharmacy")
    dash.set("charts", [{"chart": c, "width": "Half"} for c in charts])
    dash.save()

    frappe.db.commit()
    frappe.clear_cache()
    print("charts added")


def rebuild_layout():
    """Home = daily actions + key numbers. Dashboard = all cards + charts."""
    import json
    import uuid

    def bid():
        return uuid.uuid4().hex[:10]

    def header(text):
        return {"id": bid(), "type": "header",
                "data": {"text": f'<span class="h4"><b>{text}</b></span>', "col": 12}}

    def block(kind, key, name, col):
        return {"id": bid(), "type": kind, "data": {key: name, "col": col}}

    all_cards = ["Active Medicines", "Stock Value", "Low Stock Items",
                 "Batches Expiring in 30 Days", "Expired Batches with Stock",
                 "Purchase Receipts This Month", "Sales This Month",
                 "Purchase Orders to Receive"]
    key_cards = ["Sales This Month", "Batches Expiring in 30 Days",
                 "Expired Batches with Stock", "Low Stock Items"]
    charts = ["Sales Trend", "Purchase Trend", "Items by Item Group",
              "Purchase Receipts by Supplier"]

    # use the shortcut type this Frappe version offers for opening a page
    options = (frappe.get_meta("Workspace Shortcut").get_field("type").options or "").split("\n")
    print("shortcut types:", options)
    if "Page" in options:
        pos = {"label": "Open POS", "type": "Page", "link_to": "point-of-sale"}
    else:
        pos = {"label": "Open POS", "type": "URL", "url": "/desk/point-of-sale"}

    lists = [("Items", "Item"), ("Batches", "Batch"),
             ("Purchase Receipts", "Purchase Receipt"),
             ("Sales Invoices", "Sales Invoice"), ("Stock Entries", "Stock Entry")]
    shortcuts = [pos] + [
        {"label": label, "type": "DocType", "link_to": doctype,
         "doc_view": "List", "stats_filter": "[]"}
        for label, doctype in lists
    ]

    blocks = [header("Quick Actions")]
    blocks += [block("shortcut", "shortcut_name", s["label"], 4) for s in shortcuts]
    blocks.append(header("Needs Attention"))
    blocks += [block("number_card", "number_card_name", c, 3) for c in key_cards]

    ws = frappe.get_doc("Workspace", "Pharmacy")
    ws.content = json.dumps(blocks)
    ws.set("shortcuts", shortcuts)
    ws.set("number_cards", [{"label": c, "number_card_name": c} for c in key_cards])
    ws.set("charts", [])
    ws.save()

    dash = frappe.get_doc("Dashboard", "Pharmacy")
    dash.set("cards", [{"card": c} for c in all_cards])
    dash.set("charts", [{"chart": c, "width": "Half"} for c in charts])
    dash.save()

    frappe.db.commit()
    frappe.clear_cache()
    print("layout rebuilt")


def prepare_medicines():
    """Turn on expiry tracking and give a TEST price to the imported Drug items."""
    done = 0
    for name in frappe.get_all("Item", filters={"item_group": "Drug", "disabled": 0}, pluck="name"):
        item = frappe.get_doc("Item", name)
        changed = False

        # expiry can only be switched on while the item has no stock history
        if not item.has_expiry_date and not frappe.db.exists("Stock Ledger Entry", {"item_code": name}):
            item.has_expiry_date = 1
            item.shelf_life_in_days = 730
            changed = True

        if not item.standard_rate:
            item.standard_rate = 5  # test price, replace with real prices later
            changed = True

        if changed:
            item.save()
            done += 1

    frappe.db.commit()
    print("items updated:", done)


def add_test_stock(limit: int = 3):
    """Receive two batches (different expiry dates) for Drug items that have no batches yet."""
    from frappe.utils import add_days, today

    company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
    warehouse = "Stores - D"
    supplier = "Test Pharma Supplier"
    lots = [("A", 180), ("B", 700)]  # batch suffix, days until expiry
    made = 0

    items = frappe.get_all(
        "Item",
        filters={"item_group": "Drug", "disabled": 0, "has_batch_no": 1},
        fields=["name", "stock_uom"],
        order_by="name",
    )
    for n, it in enumerate(items, start=1):
        if made >= int(limit):
            break
        if frappe.db.exists("Batch", {"item": it.name}):
            continue  # already has batches (for example Paracetamol 500mg)
        try:
            rows = []
            for suffix, days in lots:
                batch_id = f"M{n:02d}-{suffix}"
                frappe.get_doc({
                    "doctype": "Batch", "batch_id": batch_id, "item": it.name,
                    "manufacturing_date": add_days(today(), -30),
                    "expiry_date": add_days(today(), days),
                }).insert()
                rows.append({
                    "item_code": it.name, "qty": 50, "rate": 3,
                    "uom": it.stock_uom, "stock_uom": it.stock_uom, "conversion_factor": 1,
                    "warehouse": warehouse, "use_serial_batch_fields": 1, "batch_no": batch_id,
                })
            pr = frappe.get_doc({
                "doctype": "Purchase Receipt", "supplier": supplier, "company": company,
                "posting_date": today(), "items": rows,
            })
            pr.set_missing_values()
            pr.insert()
            pr.submit()
            frappe.db.commit()
            made += 1
            print("stock added:", it.name)
        except Exception as e:
            frappe.db.rollback()
            print("FAILED:", it.name, "->", e)
    print("receipts made:", made)


def create_prices():
    """Give every Drug item a selling price (Item Price) on the POS price list."""
    profile = frappe.get_all("POS Profile", pluck="name")[0]
    price_list = frappe.db.get_value("POS Profile", profile, "selling_price_list")
    print("POS profile:", profile, "| price list:", price_list)
    if not price_list:
        print("The POS Profile has no price list set. Set one first.")
        return

    created = 0
    for item in frappe.get_all(
        "Item", filters={"item_group": "Drug", "disabled": 0}, fields=["name", "standard_rate"]
    ):
        if frappe.db.exists("Item Price", {"item_code": item.name, "price_list": price_list}):
            continue
        frappe.get_doc({
            "doctype": "Item Price",
            "item_code": item.name,
            "price_list": price_list,
            "price_list_rate": item.standard_rate or 5,
            "selling": 1,
        }).insert()
        created += 1

    frappe.db.commit()
    print("prices created:", created)


def create_wards():
    """Create a 'Wards' warehouse group with a few ward warehouses under it."""
    company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
    abbr = frappe.get_cached_value("Company", company, "abbr")
    group = f"Wards - {abbr}"

    if not frappe.db.exists("Warehouse", group):
        frappe.get_doc({
            "doctype": "Warehouse", "warehouse_name": "Wards", "is_group": 1,
            "parent_warehouse": f"All Warehouses - {abbr}", "company": company,
        }).insert()
        print("created", group)

    for ward in ["General Ward", "ICU", "Emergency"]:
        name = f"{ward} - {abbr}"
        if not frappe.db.exists("Warehouse", name):
            frappe.get_doc({
                "doctype": "Warehouse", "warehouse_name": ward,
                "parent_warehouse": group, "company": company,
            }).insert()
            print("created", name)

    frappe.db.commit()
