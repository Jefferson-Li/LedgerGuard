"""FastMCP server that returns an invoice only after paragraph screening.

The document body is withheld when any paragraph matches or when screening
cannot run. ``list_invoices`` returns metadata only, so a caller can discover
ids without receiving the untrusted text.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from starlette.responses import JSONResponse

from invoice_mcp.armor import (
    Screener,
    invoice_untrusted_text,
    screen_paragraphs,
    screener_from_env,
)

SERVICE = "invoice-mcp"
logger = logging.getLogger(SERVICE)
mcp = FastMCP(SERVICE)

_PUBLIC_INVOICE_KEYS = (
    "invoice_id",
    "supplier_name",
    "supplier_abn",
    "po_number",
    "invoice_date",
    "currency",
    "lines",
    "subtotal_ex_gst",
    "gst",
    "total_inc_gst",
    "text",
)


def data_dir() -> Path:
    env = os.environ.get("LEDGERGUARD_DATA_DIR")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "invoices").is_dir():
            return parent / "data"
    raise FileNotFoundError(
        "Set LEDGERGUARD_DATA_DIR to the directory that contains seed/ and invoices/."
    )


def _invoice_path(invoice_id: str) -> Path:
    return data_dir() / "invoices" / f"{invoice_id}.json"


def load_invoice(invoice_id: str) -> dict[str, Any] | None:
    path = _invoice_path(invoice_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def public_invoice(invoice: dict[str, Any]) -> dict[str, Any]:
    return {key: invoice[key] for key in _PUBLIC_INVOICE_KEYS if key in invoice}


def list_invoices() -> list[dict[str, str]]:
    """List invoice metadata. Document text is not included.

    Returns:
        One row per synthetic invoice, with id, supplier, date, currency, total, and PO number.
    """
    rows = []
    for path in sorted((data_dir() / "invoices").glob("INV-*.json")):
        invoice = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            {
                "invoice_id": invoice["invoice_id"],
                "supplier_name": invoice["supplier_name"],
                "invoice_date": invoice["invoice_date"],
                "currency": invoice["currency"],
                "total_inc_gst": invoice["total_inc_gst"],
                "po_number": invoice["po_number"],
            }
        )
    return rows


def fetch_invoice(invoice_id: str, screener: Screener | None = None) -> dict[str, Any]:
    """Screen and maybe return one invoice. ``screener`` is for tests and is not a tool argument."""
    invoice = load_invoice(invoice_id)
    if invoice is None:
        return {"invoice_id": invoice_id, "status": "not_found", "blocked": False}

    active = screener if screener is not None else screener_from_env()
    result = screen_paragraphs(invoice_untrusted_text(invoice), active)
    logger.info(
        json.dumps(
            {
                "event": "invoice_screened",
                "service": SERVICE,
                "invoice_id": invoice_id,
                "blocked": result.blocked,
                "reason": result.reason,
                "paragraph_count": result.paragraph_count,
                "filters": sorted(
                    {name for finding in result.findings for name in finding.filters}
                ),
            }
        )
    )
    if result.blocked:
        return {
            "invoice_id": invoice_id,
            "status": "quarantined",
            "blocked": True,
            "screening": result.public_dict(),
        }
    return {
        "invoice_id": invoice_id,
        "status": "released",
        "blocked": False,
        "screening": result.public_dict(),
        "invoice": public_invoice(invoice),
    }


def get_invoice(invoice_id: str) -> dict[str, Any]:
    """Return one invoice after screening each paragraph.

    On a match or a screening failure the body is omitted and the invoice is quarantined.

    Args:
        invoice_id: Invoice id, for example INV-1001.
    """
    return fetch_invoice(invoice_id)


mcp.tool()(list_invoices)
mcp.tool()(get_invoice)


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
