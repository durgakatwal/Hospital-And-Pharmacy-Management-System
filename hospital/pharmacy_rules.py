import frappe
from frappe import _
from frappe.utils import getdate, today


def block_expired_batches(doc, method=None):
    """Stop the sale of expired medicines and say clearly why."""
    if not (doc.get("update_stock") or doc.get("is_pos")):
        return

    for row in doc.items:
        batch = row.get("batch_no")

        # A batch was chosen: refuse it if it has expired.
        if batch:
            expiry = frappe.db.get_value("Batch", batch, "expiry_date")
            if expiry and getdate(expiry) < getdate(today()):
                frappe.throw(
                    _("Row {0}: batch {1} of {2} expired on {3} and cannot be sold.").format(
                        row.idx, batch, row.item_code, expiry
                    )
                )
            continue

        # No batch yet: if the item tracks batches and every batch with
        # stock has expired, say that, instead of the generic message.
        if row.get("serial_and_batch_bundle"):
            continue
        if not frappe.db.get_value("Item", row.item_code, "has_batch_no"):
            continue

        live = {"item": row.item_code, "disabled": 0, "batch_qty": [">", 0]}
        if frappe.db.exists("Batch", {**live, "expiry_date": [">=", today()]}):
            continue  # a valid batch exists, let ERPNext assign it

        expired = frappe.get_all(
            "Batch",
            filters={**live, "expiry_date": ["<", today()]},
            fields=["name", "expiry_date"],
            order_by="expiry_date desc",
            limit=1,
        )
        if expired:
            frappe.throw(
                _("{0}: all batches with stock have expired (batch {1} expired on {2}). "
                  "Remove this medicine from the bill.").format(
                    row.item_code, expired[0].name, expired[0].expiry_date
                ),
                title=_("Medicine Expired"),
            )
