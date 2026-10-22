"""ADK matching agent.

The model may call ERP and invoice tools, then ``reconcile_invoice_payload``.
The reconcile tool is the only place amounts are decided. When a Model Armor
template is configured, this process also attaches ``ModelArmorPlugin`` so tool
output is screened again inside the agent. That second pass chunks by character
count; it does not replace the paragraph screen inside ``invoice-mcp``.

``to_a2a`` builds its own runner unless one is passed. A runner is passed only
when the plugin can be constructed, so a missing template still lets the
process start (invoice screening stays fail-closed in ``invoice-mcp``).
"""

from __future__ import annotations

import os

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import LlmAgent
from google.adk.apps.app import App
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import (
    InMemoryCredentialService,
)
from google.adk.integrations.model_armor import ModelArmorConfig, ModelArmorPlugin
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from starlette.responses import JSONResponse

from gcp_auth import id_token_headers, origin_of
from matching_agent.a2a_endpoint import advertised_endpoint
from matching_agent.rules import reconcile_from_tool_payload

MODEL = os.environ.get("LEDGERGUARD_MODEL", "gemini-2.5-flash")
ERP_MCP_URL = os.environ.get("ERP_MCP_URL", "http://localhost:8090/mcp")
INVOICE_MCP_URL = os.environ.get("INVOICE_MCP_URL", "http://localhost:8091/mcp")

INSTRUCTION = """You reconcile Australian tax invoices against purchase orders and goods receipts.
GST is 10 percent and amounts are AUD. Use the MCP tools to read data.
If get_invoice returns status quarantined, stop. Report the quarantine.
Do not ask for the invoice body and do not guess bank details.
When an invoice is released, pass the tool JSON unchanged to reconcile_invoice_payload.
Report that tool's status, exception_codes, and details exactly.
Never calculate money yourself and never reveal a supplier bank account, BSB, or account number.
"""


def _mcp_headers(url: str):
    def provider(_ctx):
        if os.environ.get("MCP_AUTH_MODE", "none") != "id_token":
            return {}
        return id_token_headers(origin_of(url))

    return provider


def _toolset(url: str) -> McpToolset:
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=url, timeout=30.0),
        header_provider=_mcp_headers(url),
    )


def reconcile_invoice_payload(
    invoice_json: str,
    purchase_order_json: str,
    goods_receipt_json: str,
    supplier_json: str,
) -> dict:
    """Three-way match. Amounts in the result are computed by code, not by the model.

    Args:
        invoice_json: JSON from get_invoice.
        purchase_order_json: JSON from get_purchase_order.
        goods_receipt_json: JSON from get_goods_receipt.
        supplier_json: JSON from get_supplier.
    """
    return reconcile_from_tool_payload(
        invoice_json,
        purchase_order_json,
        goods_receipt_json,
        supplier_json,
    )


def build_plugin() -> ModelArmorPlugin | None:
    prompt = (
        os.environ.get("MODEL_ARMOR_PROMPT_TEMPLATE")
        or os.environ.get("MODEL_ARMOR_TEMPLATE")
        or ""
    )
    response = os.environ.get("MODEL_ARMOR_RESPONSE_TEMPLATE") or prompt
    if not prompt and not response:
        return None
    return ModelArmorPlugin(
        config=ModelArmorConfig(
            prompt_template_name=prompt or None,
            response_template_name=response or None,
            tool_output_template_name=prompt or None,
            block_on_screening_failure=True,
            deidentify_sensitive_data=True,
        )
    )


root_agent = LlmAgent(
    name="matching_agent",
    model=MODEL,
    description="Matches invoices to purchase orders and goods receipts with deterministic rules.",
    instruction=INSTRUCTION,
    tools=[_toolset(ERP_MCP_URL), _toolset(INVOICE_MCP_URL), reconcile_invoice_payload],
)


def build_runner() -> Runner | None:
    plugin = build_plugin()
    if plugin is None:
        return None
    app = App(name="matching_agent", root_agent=root_agent, plugins=[plugin])
    return Runner(
        app=app,
        session_service=InMemorySessionService(),
        artifact_service=InMemoryArtifactService(),
        memory_service=InMemoryMemoryService(),
        credential_service=InMemoryCredentialService(),
    )


def build_a2a_app():
    listen_port = int(os.environ.get("PORT", "8080"))
    protocol, host, port = advertised_endpoint(os.environ.get("AGENT_URL"), listen_port)
    app = to_a2a(
        root_agent,
        host=host,
        port=port,
        protocol=protocol,
        runner=build_runner(),
    )

    async def health(_request):
        return JSONResponse({"status": "healthy", "service": "matching-agent"})

    app.add_route("/health", health, methods=["GET"])
    return app


a2a_app = build_a2a_app()


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(a2a_app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
