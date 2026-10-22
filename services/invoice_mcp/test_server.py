import asyncio

from invoice_mcp.armor import AllowAllScreener
from invoice_mcp.server import fetch_invoice, list_invoices, mcp


def test_tool_names():
    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    assert names == {"get_invoice", "list_invoices"}


def test_ten_metadata_rows():
    assert len(list_invoices()) == 10


def test_unknown_invoice():
    assert fetch_invoice("INV-DOES-NOT-EXIST", screener=AllowAllScreener())["status"] == "not_found"
