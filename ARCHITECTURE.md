# L3B Architecture Record

Team phải cập nhật tài liệu này cùng source. Mục tiêu là mô tả quyết định có thể kiểm chứng, không ghi prompt bí mật hoặc chain-of-thought.

## 1. System overview

Quy trình xử lý một case trải qua 6 chặng tuần tự kết hợp song song:

```text
Input Case
    │
    ▼
[Coordinator] ──(handoff)──► [Entity/Customer Resolver]
    │                                │ (MCP: get_customer_history, get_order)
    │◄────── (resolved_orders) ──────┘
    │
    ▼ (Fan-out Specialist Investigation)
    ├──► [Order/Product Agent]    ──► (MCP: get_order, get_order_items, get_product_context, get_sellers)
    ├──► [Shipment Agent]         ──► (MCP: get_shipment_summary)
    └──► [Payment/Refund Agent]   ──► (MCP: get_order_payments, get_payment_timeline, get_refund_timeline)
    │
    ▼
[Conflict Resolver]               ──► Đối soát cross-source, áp dụng bảng ưu tiên nguồn dữ liệu
    │
    ▼
[Policy Specialist]               ──► (MCP: get_policy) Đối chiếu điều khoản & tính toán bồi hoàn
    │
    ▼
[Verifier]                        ──► Kiểm định 10 invariants cứng & schema validation
    │
    ▼
Case Output (l3b-output-v2) & Observable Trace (trace-event-v1)
```

## 2. Agent ownership

Áp dụng nguyên tắc Least Privilege: Mỗi agent chỉ được cấp quyền gọi đúng các tool cần thiết cho phạm vi trách nhiệm của mình.

| Actor | Input | Trách nhiệm | Tool permission | Output/handoff |
| --- | --- | --- | --- | --- |
| **Entity/customer** | `case_id`, text complaint, customer hints | Bóc tách danh tính khách hàng, liên kết đơn hàng lịch sử, xếp hạng candidate và loại trừ đơn không khớp | `get_customer_history`, `get_order` | `entity_resolution`, `customer_context` |
| **Coordinator** | Case input thô từ runner | Điều phối luồng làm việc A2A, khởi tạo trace, quản lý timeout, chuyển giao tác vụ giữa các agent | *None* (Chỉ điều phối, không gọi MCP data tools) | Handoff payloads tới các Specialist |
| **Order/product** | `resolved_order_ids` | Trích xuất thông tin trạng thái đơn hàng, danh sách SKU/items, thông tin nhà bán lẻ (sellers) | `get_order`, `get_order_items`, `get_product_context`, `get_sellers` | Danh sách seller, items, phân tích trạng thái đơn |
| **Shipment** | `resolved_order_ids`, shipment IDs | Phân tích mốc thời gian giao hàng, SLA vận chuyển, phát hiện trễ do seller hay đơn vị vận chuyển | `get_shipment_summary` | `shipment_analysis` (verdict, late_seller_ids, timeline_complete) |
| **Payment/refund** | `resolved_order_ids`, payment references | Đối soát dòng tiền: tiền đã trừ (captured), tiền đã hoàn (refunded), phát hiện duplicate/mismatch | `get_order_payments`, `get_payment_timeline`, `get_refund_timeline` | `payment_analysis` (verdict, captured, refunded, refundable totals) |
| **Policy** | Phân tích vi phạm, mã vấn đề sơ bộ | Tra cứu chính sách nền tảng tương ứng với vi phạm, xác định trách nhiệm và định mức bồi hoàn | `get_policy` | Điều khoản áp dụng, căn cứ tính phạt |
| **Conflict resolver** | Dữ liệu đối chiếu từ nhiều nguồn | Phát hiện xung đột thông tin giữa các tool MCP, chọn nguồn theo thứ tự ưu tiên pháp lý | *None* (Pure logic deduction) | `data_conflicts`, `root_cause_analysis` |
| **Verifier** | Draft payload của case | Kiểm tra toàn bộ 10 bất biến (Verification Invariants), tính toàn vẹn của evidence, khóa JSON schema | *None* (Deterministic validation) | Finalized L3B JSON hoặc Reject/Flag error |

## 3. Entity resolution và A2A protocol

- **Tiêu chí xếp hạng & Loại trừ Candidate:**
  - Điểm khớp danh tính (`match_score`) tính trên 3 tiêu chí: Trùng khớp `customer_id`/`customer_unique_id` (0.5), Khoảng cách thời gian mua hàng với ngày khiếu nại (0.3), và Khớp SKU/tên sản phẩm (0.2).
  - Ngưỡng tin cậy (`confidence_threshold`):
    - $\ge 0.85$: Ghi nhận trạng thái `resolved`, đưa vào `resolved_order_ids`.
    - $0.50 \le \text{score} < 0.85$: Ghi nhận `ambiguous`.
    - $< 0.50$: Đưa vào `rejected_candidates`. Tuyệt đối không phỏng đoán nếu không có bằng chứng liên kết.
- **A2A Message Envelope:**
  Mọi giao tiếp giữa các agent đều đi qua cấu trúc envelope thống nhất:
  ```json
  {
    "case_id": "CASE_123",
    "sender": "coordinator",
    "target": "shipment_specialist",
    "correlation_id": "corr_abc123",
    "payload": { "order_ids": ["ORD_001"] },
    "evidence_refs": ["ev_12345678901234567890"]
  }
  ```
- **Chống lặp & Handoff Timeout:**
  - Mỗi case giới hạn tối đa **8 lượt handoff**. Nếu vượt quá, coordinator ép buộc kết thúc với `case_status: "needs_investigation"`.
  - Timeout tối đa cho toàn case: **25 giây**. Timeout cho mỗi specialist: **5 giây**.
  - Không ghi nội dung suy luận nội bộ (chain-of-thought) vào trace log; chỉ ghi nhận các trường định danh và mã quyết định.

## 4. Evidence và conflict lifecycle

- **Kiểm thực MCP Response:**
  Mọi phản hồi từ `EvidenceGateway` bắt buộc phải khớp với schema `mcp-evidence-response-v1.schema.json`. Hệ thống từ chối nạp bằng chứng nếu thiếu `result_hash` hoặc định dạng `evidence_ref` không khớp regex `^ev_[A-Za-z0-9_-]{20,96}$`.
- **Trace Consumption:**
  Khi bất kỳ specialist nào sử dụng kết quả từ tool để đưa ra kết luận, bắt buộc phải emit sự kiện trace `tool_result_consumed` với `actor`, `tool_name` và mảng `evidence_refs`.
- **Thứ tự ưu tiên nguồn dữ liệu (Source Precedence):**
  1. *Hệ thống vật lý / Sự kiện thực tế*: Carrier checkpoint scan (`get_shipment_summary`), Gateway webhook logs (`get_payment_timeline`).
  2. *Dữ liệu đơn hàng hệ thống*: Platform core order tables (`get_order`, `get_order_items`).
  3. *Tuyên bố chủ quan*: Seller notes, Customer complaint statements.
- **Biểu diễn xung đột (Unresolved Conflict):**
  Nếu có sự sai lệch giữa 2 nguồn cùng cấp mà không có bằng chứng thứ ba phân xử, ghi nhận vào `data_conflicts` với `selected_source: null` và `resolution_code: "UNRESOLVED_DISCREPANCY"`.
- **Cô lập phạm vi bằng chứng (Evidence Scope):**
  `evidence_ref` được sinh ra theo phiên làm việc của từng case. Không tái sử dụng `evidence_ref` giữa các `case_id` khác nhau.

## 5. Failure and efficiency policy

| Failure | Retry budget | Fallback | Trace event/code |
| --- | ---: | --- | --- |
| **MCP timeout / 5xx** | 2 lần (exponential backoff: 200ms, 600ms) | Đánh dấu domain là `insufficient_evidence`, tiếp tục các nhánh còn lại | `tool_result_consumed` (`decision_code: "TOOL_TIMEOUT"`) |
| **Entity not found/ambiguous** | 0 lần (Không retry khi thiếu dữ liệu) | Ghi nhận `status: "not_found"` hoặc `"ambiguous"`, chuyển `case_status` sang `"needs_investigation"` | `handoff` (`decision_code: "ENTITY_NOT_FOUND"`) |
| **Source conflict** | 0 lần | Áp dụng bảng ưu tiên nguồn (Source Precedence) hoặc gắn cờ `data_conflicts` | `policy_decided` (`decision_code: "CONFLICT_RESOLVED"`) |
| **Invalid specialist result** | 1 lần (Parse lại với fallback parser) | Sử dụng fallback safe-stub mặc định, hạ `confidence` xuống dưới 0.5 | `verification_completed` (`decision_code: "PARSE_FALLBACK"`) |

- **Chiến lược Query Budget & Cache:**
  - Áp dụng bộ nhớ đệm (In-memory memoization cache) theo cặp `(tool_name, tool_args)` trong cùng một `case_id`.
  - Không thực hiện quét hàng loạt (fan-out unconstrained queries). Chỉ truy vấn thông tin dựa trên các ID đã được giải quyết từ bước Entity Resolution.

## 6. Verification invariants

Trước khi xuất kết quả cuối cùng, Verifier Agent thực hiện kiểm tra 10 bất biến bắt buộc:

1. **Schema Invariant:** Dữ liệu hoàn toàn khớp với `l3b-output-v2.schema.json` (`additionalProperties: false`, không thừa trường).
2. **Entity Boundary:** Tất cả ID trong `affected_entities` phải thuộc tập hợp ID đã được xác thực qua MCP evidence.
3. **Candidate Isolation:** Không có bất kỳ ID nào thuộc `entity_resolution.rejected_candidates` xuất hiện trong `resolved_order_ids` hoặc `affected_entities.order_ids`.
4. **Evidence Linkage:** Mọi `evidence_ref` trong `evidence_refs` và `claim_assessments[].evidence_refs` phải tồn tại trong sự kiện trace `tool_result_consumed`.
5. **Timeline Consistency:** Thứ tự thời gian vận chuyển phải hợp lệ: `order_purchase_timestamp` $\le$ `order_delivered_carrier_date` $\le$ `order_delivered_customer_date`.
6. **Financial Match:** `recommended_refund_brl` phải bằng chính xác tổng các dòng bồi hoàn: $\sum \text{refund\_lines}[].\text{amount\_brl}$.
7. **Refund Ceiling:** Số tiền bồi hoàn `recommended_refund_brl` không được vượt quá `refundable_total_brl` (hoặc `captured_total_brl`).
8. **Responsibility Alignment:** Nếu `primary_issue` là `late_delivery_seller`, thì danh sách `responsible_parties` phải chứa ít nhất một bên có `party_type: "seller"`.
9. **Confidence Limits:** Tất cả các chỉ số `confidence` phải là số thực nằm trong đoạn $[0.0, 1.0]$.
10. **Trace Completeness:** Mọi case phải có chuỗi trace hợp lệ: Bắt đầu bằng `case_received`, có ít nhất 1 `task_assigned`, có `verification_completed` và kết thúc bằng `case_finalized`.

## 7. Reproducibility

- **Runtime & Môi trường:** Python 3.11+, quản lý gói qua Virtual Environment (`.venv`).
- **Thư viện chuẩn:** `pydantic` (nếu dùng parsing), `jsonschema` (validation), `asyncio` chuẩn.
- **Tính tiền định (Deterministic Settings):** Random seed cố định `seed=42`, model temperature = `0.0`.
- **Giới hạn tài nguyên:** Tối đa 4 coroutine specialist chạy đồng thời (`asyncio.Semaphore(4)`).
- **Quy trình thực thi chuẩn (Day09 CLI):**
  1. Kiểm tra bộ dữ liệu đầu vào:
     ```bash
     day09 validate-inputs
     ```
  2. Kiểm tra xác thực và danh sách tool MCP:
     ```bash
     day09 mcp-tools
     ```
  3. Thực thi xử lý toàn bộ 100 cases:
     ```bash
     day09 run
     ```
  4. Kiểm tra tính hợp lệ của output và trace:
     ```bash
     day09 validate
     ```
  5. Đóng gói file nộp bài:
     ```bash
     day09 package
     ```