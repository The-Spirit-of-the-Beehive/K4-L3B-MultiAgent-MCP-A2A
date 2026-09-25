import asyncio
import json
from pathlib import Path

from student_agent.config import Settings
from student_agent.contracts import Contracts
from student_agent.mcp_gateway import connect_gateway


async def inspect():
    s = Settings.load(Path("."))
    c = Contracts(Path("contracts/schemas"))

    async with connect_gateway(s.mcp_endpoint, s.team_api_key, c) as g:
        # 1. In Schema chính xác của 10 Tools
        tools_resp = await g._session.list_tools()
        print("=== 10 MCP TOOLS & THAM SỐ CHUẨN ===")
        for t in tools_resp.tools:
            schema = t.input_schema or {}
            props = list(schema.get("properties", {}).keys())
            req = schema.get("required", [])
            print(f"- {t.name}:")
            print(f"    params  : {props}")
            print(f"    required: {req}")

        # 2. Test gọi thử ngay với CASE_001
        case1 = json.loads(Path("inputs/L3B_CASE_001.json").read_text(encoding="utf-8"))
        case_id = case1["case_id"]
        hint = case1.get("customer_unique_id_hint")
        order_candidate = case1["candidate_order_ids"][0]
        policy_ver = case1.get("policy_version", "EC_POLICY_V2")

        print("\n=== TEST GỌI THỰC TẾ TRÊN CASE_001 ===")
        # Gọi thử get_customer_history
        try:
            res_cust = await g.call(
                "get_customer_history",
                case_id=case_id,
                customer_unique_id=hint,
            )
            print("[SUCCESS] get_customer_history:", res_cust.get("evidence_ref"))
            print("          data:", res_cust.get("data"))
        except Exception as e:
            print("[FAILED] get_customer_history:", e)

        # Gọi thử get_order
        try:
            res_ord = await g.call(
                "get_order",
                case_id=case_id,
                order_id=order_candidate,
            )
            print("[SUCCESS] get_order:", res_ord.get("evidence_ref"))
            print("          status:", res_ord.get("data", {}).get("order_status"))
        except Exception as e:
            print("[FAILED] get_order:", e)

        # Gọi thử get_shipment_summary
        try:
            res_ship = await g.call(
                "get_shipment_summary",
                case_id=case_id,
                order_id=order_candidate,
            )
            print("[SUCCESS] get_shipment_summary:", res_ship.get("evidence_ref"))
            print("          data:", res_ship.get("data"))
        except Exception as e:
            print("[FAILED] get_shipment_summary:", e)

        # Gọi thử get_policy
        try:
            res_pol = await g.call(
                "get_policy",
                case_id=case_id,
                policy_version=policy_ver,
                topic="late_delivery_logistics",
            )
            print("[SUCCESS] get_policy:", res_pol.get("evidence_ref"))
            print("          data:", res_pol.get("data"))
        except Exception as e:
            print("[FAILED] get_policy:", e)


if __name__ == "__main__":
    asyncio.run(inspect())