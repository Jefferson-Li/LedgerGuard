"""FastMCP server for synthetic purchase orders, goods receipts, and suppliers.

Bank account fields exist in the seed files so tests can prove they are not
returned. Firestore is not read yet; set nothing and the server uses the JSON
under ``LEDGERGUARD_DATA_DIR``.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from starlette.responses import JSONResponse

from redact import redact_sensitive

SERVICE = "erp-mcp"
logger = logging.getLogger(SERVICE)
mcp = FastMCP(SERVICE)


def data_dir() -> Path:
    env = os.environ.get("LEDGERGUARD_DATA_DIR")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "seed").is_dir():
            return parent / "data"
    raise FileNotFoundError(
        "Set LEDGERGUARD_DATA_DIR to the directory that contains seed/ and invoices/."
    )


def _load(name: str) -> list[dict[str, Any]]:
    path = data_dir() / "seed" / name
    return json.loads(path.read_text(encoding="utf-8"))


def get_purchase_order(po_number: str) -> dict[str, Any]:
    """Return one synthetic purchase order, without payment details.

    Args:
        po_number: Purchase order number, for example PO-1001.
    """
    for record in _load("purchase_orders.json"):
        if record["po_number"] == po_number:
            return redact_sensitive(record)
    return {"error": "not_found", "po_number": po_number}


def get_goods_receipt(po_number: str) -> dict[str, Any]:
    """Return goods receipts for a purchase order. An empty list means nothing was received.

    Args:
        po_number: Purchase order number the receipt should reference.
    """
    receipts = [row for row in _load("goods_receipts.json") if row["po_number"] == po_number]
    return {"po_number": po_number, "goods_receipts": redact_sensitive(receipts)}


def get_supplier(supplier_id: str) -> dict[str, Any]:
    """Return a supplier master record. Bank account fields are never included.

    Args:
        supplier_id: Supplier id, for example SUP-ACME.
    """
    for record in _load("suppliers.json"):
        if record["supplier_id"] == supplier_id:
            return redact_sensitive(record)
    return {"error": "not_found", "supplier_id": supplier_id}


mcp.tool()(get_purchase_order)
mcp.tool()(get_goods_receipt)
mcp.tool()(get_supplier)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    return JSONResponse({"status": "healthy", "service": SERVICE})


app = mcp.http_app(stateless_http=True, json_response=True)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
