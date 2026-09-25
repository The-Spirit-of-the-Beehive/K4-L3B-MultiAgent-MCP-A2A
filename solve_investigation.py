import asyncio
import json
import re
from pathlib import Path
import httpx

from student_agent.config import Settings
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def investigate():
    s = Settings.load(Path("."))
    headers = {"Authorization": f"Bearer {s.team_api_key}"}

    print("=== 1. SOI FRONTEND n7-competition.pages.dev ĐỂ TÌM BACKEND CHÍNH THỨC ===")
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(s.competition_api_url)
            print(f"Status: {resp.status_code}")
            # Tìm các file script .js
            scripts = re.findall(r'src="([^"]+\.js)"', resp.text)
            print("Found JS files:", scripts)
            for sc in scripts[:3]:
                js_url = sc if sc.startswith("http") else f"{s.competition_api_url.rstrip('/')}/{sc.lstrip('/')}"
                js_resp = await client.get(js_url)
                # Tìm các endpoint / url / domain trong code frontend
                api_matches = set(re.findall(r'https?://[a-zA-Z0-9\.-]+(?::\d+)?(?:/[a-zA-Z0-9_\.-]+)*', js_resp.text))
                # Lọc ra các URL khả nghi
                filtered = [u for u in api_matches if "pages.dev" not in u and "google" not in u and "github" not in u]
                if filtered:
                    print(f"  -> Các API URL phát hiện trong {sc}:")
                    for u in filtered:
                        print("     *", u)
    except Exception as e:
        print("Lỗi đọc frontend:", e)

    print("\n=== 2. THỬ GỌI MCP VỚI CÁC CASE L3A VS L3B & POLICY DAY09-SCORING-V2 ===")
    test_cases = [
        # 1. Thử policy_version day09-scoring-v2
        ("get_policy", {"case_id": "L3B_CASE_001", "policy_version": "day09-scoring-v2"}),
        ("get_policy", {"case_id": "L3A_CASE_001", "policy_version": "day09-scoring-v2"}),
        ("get_policy", {"case_id": "L3A_CASE_001", "policy_version": "EC_POLICY_V2"}),
        # 2. Thử get_order với L3A
        ("get_order", {"case_id": "L3A_CASE_001", "order_id": "af0bbb47f125381ce9f3597dc70ef07b"}),
        # 3. Thử get_customer_history với L3A
        ("get_customer_history", {"case_id": "L3A_CASE_001", "customer_unique_id": "customer-597dc70ef07b"}),
    ]

    async with (
        httpx.AsyncClient(headers=headers, timeout=20.0) as http_client,
        streamable_http_client(s.mcp_endpoint, http_client=http_client) as (r, w),
        ClientSession(r, w) as session,
    ):
        await session.initialize()
        for tool_name, args in test_cases:
            res = await session.call_tool(tool_name, arguments=args)
            is_err = getattr(res, "is_error", getattr(res, "isError", False))
            txt = " ".join(b.text for b in res.content if getattr(b, "text", None))
            print(f"  {tool_name}({args}) -> is_error={is_err} | Text: {txt[:160]}")

    print("\n=== 3. THỬ CÁC DẠNG HEADER KHÁC NHAU VỚI MCP ===")
    header_variants = [
        {"Authorization": f"Bearer {s.team_api_key}"},
        {"Authorization": s.team_api_key},
        {"X-Team-Key": s.team_api_key},
        {"X-Team-API-Key": s.team_api_key},
        {"X-API-Key": s.team_api_key},
    ]

    for h in header_variants:
        try:
            async with (
                httpx.AsyncClient(headers=h, timeout=10.0) as hc,
                streamable_http_client(s.mcp_endpoint, http_client=hc) as (r, w),
                ClientSession(r, w) as sess,
            ):
                await sess.initialize()
                r_test = await sess.call_tool("get_policy", arguments={"case_id": "L3B_CASE_001", "policy_version": "EC_POLICY_V2"})
                is_err_t = getattr(r_test, "is_error", getattr(r_test, "isError", False))
                txt_t = " ".join(b.text for b in r_test.content if getattr(b, "text", None))
                h_name = list(h.keys())[0]
                print(f"  Header {h_name} -> is_error={is_err_t} | {txt_t[:100]}")
        except Exception as e:
            print(f"  Header {list(h.keys())[0]} failed connect:", e)


if __name__ == "__main__":
    asyncio.run(investigate())