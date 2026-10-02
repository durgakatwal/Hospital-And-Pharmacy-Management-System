import frappe
from frappe import _
from frappe.utils import today


def _qty_in_warehouse(batch, warehouse):
    """Stock of one batch inside one warehouse (ERPNext's own helper)."""
    from erpnext.stock.doctype.batch.batch import get_batch_qty

    qty = get_batch_qty(batch_no=batch, warehouse=warehouse)
    if isinstance(qty, (int, float)):
        return qty
    if isinstance(qty, list):
        return sum(r.get("qty", 0) for r in qty if r.get("warehouse", warehouse) == warehouse)
    return 0


def _pick_batches(item_code, qty, warehouse):
    """Earliest-expiry valid batches that together cover qty. Returns [(batch, qty)]."""
    batches = frappe.get_all(
        "Batch",
        filters={
            "item": item_code,
            "disabled": 0,
            "batch_qty": [">", 0],
            "expiry_date": [">=", today()],
        },
        fields=["name"],
        order_by="expiry_date asc",
    )
    picks, needed = [], qty
    for b in batches:
        available = _qty_in_warehouse(b.name, warehouse)
        if available <= 0:
            continue
        take = min(available, needed)
        picks.append((b.name, take))
        needed -= take
        if needed <= 0:
            break
    if needed > 0:
        frappe.throw(
            _("Not enough valid (non-expired) stock of {0} in {1}: {2} short.").format(
                item_code, warehouse, needed
            )
        )
    return picks


@frappe.whitelist(methods=["POST"])
def issue_to_ward(ward: str, items: str, source: str = "Stores - D") -> dict:
    """Send medicines from the pharmacy store to a ward (no payment).

    items is a JSON list like [{"item_code": "Amlodipine 5mg", "qty": 10}].
    Batches are chosen automatically, earliest expiry first.
    """
    frappe.has_permission("Stock Entry", "create", throw=True)

    wards_group = frappe.db.get_value("Warehouse", ward, "parent_warehouse")
    if not wards_group or not wards_group.startswith("Wards"):
        frappe.throw(_("{0} is not a ward warehouse.").format(ward))

    wanted = frappe.parse_json(items)
    if not wanted:
        frappe.throw(_("Add at least one medicine."))

    company = frappe.db.get_value("Warehouse", source, "company")
    rows, summary = [], []
    for line in wanted:
        item_code, qty = line.get("item_code"), float(line.get("qty") or 0)
        if not item_code or qty <= 0:
            frappe.throw(_("Each line needs an item and a quantity above zero."))
        uom = frappe.db.get_value("Item", item_code, "stock_uom")
        for batch, take in _pick_batches(item_code, qty, source):
            rows.append({
                "item_code": item_code,
                "qty": take,
                "uom": uom,
                "stock_uom": uom,
                "conversion_factor": 1,
                "s_warehouse": source,
                "t_warehouse": ward,
                "use_serial_batch_fields": 1,
                "batch_no": batch,
            })
            summary.append({"item": item_code, "batch": batch, "qty": take})

    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Transfer",
        "purpose": "Material Transfer",
        "company": company,
        "from_warehouse": source,
        "to_warehouse": ward,
        "remarks": f"Ward issue to {ward}",
        "items": rows,
    })
    se.insert()
    se.submit()
    return {"stock_entry": se.name, "issued": summary}
