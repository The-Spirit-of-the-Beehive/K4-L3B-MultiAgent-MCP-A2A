import asyncio
import json
from pathlib import Path

from student_agent.config import Settings
from student_agent.contracts import Contracts
from student_agent.mcp_gateway import connect_gateway


async def debug_mcp():
    s = Settings.load(Path("."))
    c = Contracts(Path("contracts/schemas"))

    print(f"Connecting to MCP Endpoint: {s.mcp_endpoint}")
    async with connect_gateway(s.mcp_endpoint, s.team_api_key, c) as g:

        # 1. Test get_policy CHUẨN (chỉ truyền case_id và policy_version)
        print("\n--- TEST 1: get_policy chuẩn ---")
        try:
            res_raw = await g._session.call_tool(
                "get_policy",
                arguments={"case_id": "L3B_CASE_001", "policy_version": "EC_POLICY_V2"},
            )
            print("Raw get_policy response:")
            print(f"  is_error: {getattr(res_raw, 'is_error', getattr(res_raw, 'isError', None))}")
            for b in res_raw.content:
                print(f"  content block: {getattr(b, 'text', b)}")
        except Exception as e:
            print("  Exception:", e)

        # 2. Test get_order với raw call trên CASE_001
        print("\n--- TEST 2: get_order trên CASE_001 ---")
        try:
            res_raw = await g._session.call_tool(
                "get_order",
                arguments={
                    "case_id": "L3B_CASE_001",
                    "order_id": "af0bbb47f125381ce9f3597dc70ef07b",
                },
            )
            print("Raw get_order response:")
            print(f"  is_error: {getattr(res_raw, 'is_error', getattr(res_raw, 'isError', None))}")
            for b in res_raw.content:
                print(f"  content block: {getattr(b, 'text', b)}")
        except Exception as e:
            print("  Exception:", e)

        # 3. Quét thử qua 5 Cases đầu tiên (CASE_001 -> CASE_005)
        print("\n--- TEST 3: Thử 5 cases đầu tiên ---")
        for i in range(1, 6):
            cid = f"L3B_CASE_{i:03d}"
            cpath = Path(f"inputs/{cid}.json")
            if not cpath.exists():
                continue
            cdata = json.loads(cpath.read_text(encoding="utf-8"))
            cands = cdata.get("candidate_order_ids") or []
            print(f"\nChecking {cid} (candidates: {cands}):")
            for oid in cands:
                try:
                    res = await g._session.call_tool(
                        "get_order",
                        arguments={"case_id": cid, "order_id": oid},
                    )
                    is_err = getattr(res, "is_error", getattr(res, "isError", False))
                    txt = "".join(b.text for b in res.content if getattr(b, "text", None))[:80]
                    print(f"  -> order {oid}: is_error={is_err} | {txt}")
                except Exception as e:
                    print(f"  -> order {oid}: crashed with {e}")


if __name__ == "__main__":
    asyncio.run(debug_mcp())