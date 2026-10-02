import frappe


@frappe.whitelist()
def get_batches(item_code: str):
    """Batches of a medicine, earliest expiry first, only with stock."""
    return frappe.get_all(
        "Batch",
        filters={"item": item_code, "disabled": 0, "batch_qty": (">", 0)},
        fields=["name", "expiry_date", "batch_qty"],
        order_by="expiry_date asc",
    )