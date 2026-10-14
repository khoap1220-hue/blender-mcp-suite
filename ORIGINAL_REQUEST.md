# Original User Request

## 2026-09-16T08:44:22Z

# Teamwork Project Prompt

Xây dựng và hoàn thiện bộ công cụ Blender MCP (Model Context Protocol suite) toàn diện, ổn định chuẩn Production cho Antigravity / AI Agents, tích hợp sâu vào Blender 4.1+ với khả năng quản lý vòng đời daemon tự động, kết nối socket 2 chiều tự phục hồi, mở rộng bộ công cụ 3D (dựng hình, rigging, vật liệu PBR, animation, render) và bộ kiểm thử tự động end-to-end.

Working directory: y:\MCP Blender Agent
Integrity mode: development

## Requirements

### R1. Blender Daemon Lifecycle & Socket Auto-Recovery
Xây dựng cơ chế quản lý vòng đời daemon của Blender và kết nối socket 2 chiều bền bỉ:
- Tự động phát hiện phiên bản Blender trên máy (`C:\Program Files\Blender Foundation\Blender 4.1\blender.exe`) và tự khởi động Blender ngầm (headless daemon) hoặc kết nối vào phiên Blender GUI đang mở.
- Thiết lập cơ chế tự phục hồi kết nối (auto-reconnect với exponential backoff) khi socket bị ngắt đột ngột, đảm bảo AI client không bị ngắt quãng hoặc treo kết nối.
- Hỗ trợ cơ chế graceful shutdown và giải phóng cổng TCP port 9876 khi tắt tiến trình.

### R2. Full-Spectrum 3D MCP Tools Suite
Mở rộng và chuẩn hóa bộ công cụ MCP đáp ứng đầy đủ chu trình làm việc 3D chuyên nghiệp:
- **Scene & Object Manipulation**: Tạo, chỉnh sửa, biến đổi (transform), nhóm và quản lý phân cấp hierarchy đối tượng.
- **PBR Shading & Materials**: Khởi tạo và liên kết các node shader Principled BSDF, gán texture màu, độ nhám (roughness), kim loại (metallic), pháp tuyến (normal) và vật liệu phát sáng (emission).
- **Auto-Rigging & Hierarchy**: Hỗ trợ khởi tạo khung xương (Armature), gán trọng số da tự động (automatic skin weights) và thiết lập ràng buộc động học nghịch lưu (IK constraints) cơ bản.
- **Cinematic Lighting & Camera Control**: Thiết lập đèn (Sun, Point, Spot, Area), môi trường HDRI/World, tự động căn góc máy quay (Track-To Target) và điều chỉnh tiêu cự (focal length).
- **Render Engine & Viewport Capture**: Điều khiển render hình ảnh/video chất lượng cao (Cycles & Eevee Next) và chụp ảnh tức thời viewport 3D hỗ trợ phân tích thị giác AI.

### R3. Structured Error Handling & Zero-Crash Boundary
Thiết lập ranh giới an toàn tuyệt đối trong giao tiếp giữa MCP Server và Blender:
- Mọi thao tác thực thi script Python trong Blender (`bpy`) phải được bọc trong bộ xử lý ngoại lệ có cấu trúc.
- Trả về mã lỗi và thông điệp chẩn đoán chi tiết theo đúng đặc tả MCP JSON-RPC khi gặp lỗi dữ liệu (như object không tồn tại, sai kiểu tham số) thay vì làm sập socket server hay tiến trình Blender.

### R4. Automated Testing & Verification Suite
Xây dựng bộ kịch bản kiểm thử độc lập tự động:
- Bộ test suite `tests/test_blender_mcp_e2e.py` kiểm tra toàn bộ luồng từ client gửi lệnh MCP, server điều phối, Blender thực thi, đến nhận kết quả phản hồi.
- Kiểm thử chịu tải và mô phỏng sự cố ngắt socket đột ngột để kiểm chứng cơ chế tự phục hồi.

## Acceptance Criteria

### Connection & Lifecycle Stability
- [ ] Server tự động phát hiện phiên Blender 4.1 đang chạy hoặc tự kích hoạt phiên daemon ngầm khi có yêu cầu kết nối từ AI client.
- [ ] Cơ chế tự kết nối lại (auto-reconnect) khôi phục phiên làm việc thành công trong vòng < 3 giây khi ngắt kết nối giả lập.
- [ ] Không rò rỉ tiến trình zombie của Blender khi đóng MCP server.

### Tool Coverage & Robustness
- [ ] 100% các công cụ 3D cốt lõi (mesh, material, camera, light, armature, render) phản hồi đúng schema MCP và trả về `isError: false` với các tham số chuẩn.
- [ ] Khi truyền tham số sai hoặc gọi đối tượng không tồn tại, server phản hồi thông báo lỗi rõ ràng và giữ nguyên trạng thái kết nối socket ổn định.

### Verification & Delivery
- [ ] Toàn bộ kịch bản trong `tests/test_blender_mcp_e2e.py` chạy thành công với exit code 0.
- [ ] Cung cấp tài liệu hướng dẫn khởi chạy 1-click và tích hợp cấu hình mẫu cho Antigravity / Cursor / Claude Desktop.
