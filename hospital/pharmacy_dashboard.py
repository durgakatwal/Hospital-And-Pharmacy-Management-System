import frappe
from frappe.utils import add_days, today


@frappe.whitelist()
def stock_value() -> float:
    """Total value of all stock, from the Bin table ERPNext keeps per item and warehouse."""
    total = frappe.db.sql("select coalesce(sum(stock_value), 0) from `tabBin`")[0][0]
    return total


@frappe.whitelist()
def low_stock_items() -> int:
    """Items whose total quantity is at or below their reorder level."""
    rows = frappe.db.sql(
        """
        select i.name, coalesce(q.qty, 0) as qty, r.level
        from `tabItem` i
        join (select parent, max(warehouse_reorder_level) as level
              from `tabItem Reorder` group by parent) r on r.parent = i.name
        left join (select item_code, sum(actual_qty) as qty
                   from `tabBin` group by item_code) q on q.item_code = i.name
        where i.disabled = 0 and coalesce(q.qty, 0) <= r.level
        """,
        as_dict=True,
    )
    return len(rows)


@frappe.whitelist()
def expiry_buckets() -> dict:
    """How many batches with stock fall into each expiry group."""
    t = today()
    base = {"disabled": 0, "batch_qty": [">", 0]}

    def count(expiry_filter):
        return frappe.db.count("Batch", {**base, "expiry_date": expiry_filter})

    return {
        "Expired": count(["<", t]),
        "0-30 days": count(["between", [t, add_days(t, 30)]]),
        "31-90 days": count(["between", [add_days(t, 31), add_days(t, 90)]]),
        "Over 90 days": count([">", add_days(t, 90)]),
    }


@frappe.whitelist()
def expiring_batches(days: int = 30) -> list:
    """Batches that expire within `days` days, soonest first. Also usable from React."""
    return frappe.get_all(
        "Batch",
        filters={
            "disabled": 0,
            "batch_qty": [">", 0],
            "expiry_date": ["<=", add_days(today(), days)],
        },
        fields=["name", "item", "expiry_date", "batch_qty"],
        order_by="expiry_date asc",
    )
