import asyncio
import json
from pathlib import Path
import httpx

from student_agent.config import Settings
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def run_diagnose():
    s = Settings.load(Path("."))

    print("=== THÔNG TIN HIỆN TẠI ===")
    print(f"MCP Endpoint: {s.mcp_endpoint}")
    print(f"Team Key    : {s.team_api_key[:15]}...{s.team_api_key[-5:]} (len: {len(s.team_api_key)})")

    # 1. KẾT NỐI VÀ IN TOÀN BỘ DESCRIPTION CỦA 10 TOOLS
    print("\n=== 1. TOÀN BỘ MÔ TẢ TOOL TỪ SERVER (TÌM HƯỚNG DẪN ẨN) ===")
    headers_standard = {"Authorization": f"Bearer {s.team_api_key}"}

    async with (
        httpx.AsyncClient(headers=headers_standard, timeout=30.0) as http_client,
        streamable_http_client(s.mcp_endpoint, http_client=http_client) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools_resp = await session.list_tools()
        for t in tools_resp.tools:
            print(f"\n[Tool: {t.name}]")
            print(f"  Description: {t.description}")
            print(f"  Input Schema: {json.dumps(t.input_schema, indent=2)}")

        # 2. KIỂM TRA ĐỐI CHIẾU: THỬ THAY ĐỔI CÁC YẾU TỐ
        print("\n=== 2. THỬ NGHIỆM CÁC TRƯỜNG HỢP GỌI TOOL ===")

        # Trường hợp A: Gọi đúng chuẩn CASE_001
        res_a = await session.call_tool(
            "get_policy",
            arguments={"case_id": "L3B_CASE_001", "policy_version": "EC_POLICY_V2"}
        )
        print("A. get_policy (Key thật, case_id chuẩn):", res_a)

        # Trường hợp B: Bỏ case_id (xem server phản ứng thế nào)
        try:
            res_b = await session.call_tool(
                "get_policy",
                arguments={"policy_version": "EC_POLICY_V2"}
            )
            print("B. get_policy (Không có case_id):", res_b)
        except Exception as e:
            print("B. get_policy (Không có case_id) Exception:", e)

        # Trường hợp C: case_id dạng lowercase
        res_c = await session.call_tool(
            "get_policy",
            arguments={"case_id": "l3b_case_001", "policy_version": "EC_POLICY_V2"}
        )
        print("C. get_policy (case_id lowercase):", res_c)

    # 3. THỬ NGHIỆM VỚI KEY GIẢ (Để xem server có check Authorization không)
    print("\n=== 3. THỬ NGHIỆM VỚI FAKE TEAM KEY ===")
    fake_headers = {"Authorization": "Bearer sk-team-fakekey12345678901234567890"}
    try:
        async with (
            httpx.AsyncClient(headers=fake_headers, timeout=30.0) as fake_client,
            streamable_http_client(s.mcp_endpoint, http_client=fake_client) as (r, w),
            ClientSession(r, w) as fake_session,
        ):
            await fake_session.initialize()
            res_fake = await fake_session.call_tool(
                "get_policy",
                arguments={"case_id": "L3B_CASE_001", "policy_version": "EC_POLICY_V2"}
            )
            print("Gọi bằng Fake Key -> Kết quả:", res_fake)
    except Exception as e:
        print("Gọi bằng Fake Key -> Exception:", e)


if __name__ == "__main__":
    asyncio.run(run_diagnose())