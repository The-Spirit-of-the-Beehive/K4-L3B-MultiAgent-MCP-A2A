import asyncio
import json
from pathlib import Path
import httpx

from student_agent.config import Settings
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def probe():
    s = Settings.load(Path("."))
    headers = {"Authorization": f"Bearer {s.team_api_key}"}

    # 1. KIỂM TRA FILE NỘI BỘ TRONG CONTRACTS
    print("=== 1. KIỂM TRA CÁC FILE TRONG CONTRACTS / REPO ===")
    contracts_dir = Path("contracts")
    if contracts_dir.exists():
        for p in contracts_dir.rglob("*"):
            if p.is_file():
                print(f"  Found file: {p}")
                if "policy" in p.name.lower():
                    print(f"    -> Preview {p.name}: {p.read_text(encoding='utf-8')[:200]}")

    # 2. PROBE BACKEND SERVER DIRECTLY
    print("\n=== 2. PROBE ENDPOINTS TRÊN SERVER BACKEND ===")
    base_url = s.mcp_endpoint.replace("/mcp", "")
    endpoints = [
        "/openapi.json",
        "/docs",
        "/health",
        "/api/me",
        "/me",
        "/teams/me",
        "/api/cases",
    ]
    async with httpx.AsyncClient(headers=headers, timeout=5.0) as client:
        for ep in endpoints:
            try:
                r = await client.get(f"{base_url}{ep}")
                print(f"  GET {base_url}{ep} -> status: {r.status_code}")
                if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                    data = r.json()
                    print(f"    Data: {str(data)[:250]}")
            except Exception as e:
                print(f"  GET {ep} failed: {e}")

    # 3. TEST MATRIX POLICY_VERSION & CASE_ID TRÊN MCP
    print("\n=== 3. TEST MA TRẬN GIÁ TRỊ policy_version & case_id TRÊN MCP ===")
    policy_versions = [
        "EC_POLICY_V2",
        "ec_policy_v2",
        "v2",
        "V2",
        "scoring-policy-v2",
        "EC_POLICY_V1",
        "v1",
        "2.0",
    ]
    case_ids = [
        "L3B_CASE_001",
        "l3b_case_001",
        "CASE_001",
        "001",
    ]

    async with (
        httpx.AsyncClient(headers=headers, timeout=20.0) as http_client,
        streamable_http_client(s.mcp_endpoint, http_client=http_client) as (r, w),
        ClientSession(r, w) as session,
    ):
        await session.initialize()

        found = False
        for cid in case_ids:
            for pv in policy_versions:
                res = await session.call_tool(
                    "get_policy",
                    arguments={"case_id": cid, "policy_version": pv}
                )
                is_err = getattr(res, "is_error", getattr(res, "isError", False))
                txt = " ".join(b.text for b in res.content if getattr(b, "text", None))
                if not is_err:
                    print(f"  ===> [SUCCESS!] case_id='{cid}', policy_version='{pv}'")
                    print(f"       Result: {txt[:200]}")
                    found = True
                    break
            if found:
                break

        if not found:
            print("  -> Tất cả các tổ hợp get_policy đều báo lỗi. Thử test 1 lệnh get_customer_history:")
            # Thử get_customer_history
            res_c = await session.call_tool(
                "get_customer_history",
                arguments={"case_id": "L3B_CASE_001", "customer_unique_id": "customer-597dc70ef07b"}
            )
            print("  get_customer_history result:", res_c)


if __name__ == "__main__":
    asyncio.run(probe())