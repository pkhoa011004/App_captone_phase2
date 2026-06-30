# Tài liệu thiết kế Kịch bản lỗi Hạ tầng & Tài nguyên (Scenario 2 & Scenario 6)

Tài liệu này chi tiết hóa việc thiết kế kịch bản lỗi, bộ dữ liệu giả lập (fake-data) và phương pháp kiểm thử cho hai kịch bản thuộc trách nhiệm của **Thành viên 2: Nhóm kịch bản Hạ tầng & Tài nguyên (Infrastructure & Resources)**.

---

## 1. Tổng quan kịch bản

### Scenario 2: Container OOMKilled
*   **Mô tả**: Pod chạy dịch vụ `book-service` gặp hiện tượng rò rỉ bộ nhớ hoặc bị quá tải RAM (do số lượng thread xử lý tăng đột biến vượt ngưỡng giới hạn vật lý của container) dẫn tới việc Kubernetes Engine chủ động gửi tín hiệu `SIGKILL` để tiêu diệt khẩn cấp (OOMKilled).
*   **Mục tiêu giả lập**:
    *   Thiết kế chỉ số RAM leo thang chạm ngưỡng giới hạn 1024MB.
    *   Tạo các sự kiện Kubernetes đặc trưng (`OOMKilled`, `BackOff`, `CrashLoopBackOff`).
    *   Log báo lỗi cạn kiệt luồng và lỗi bộ nhớ luồng (`java.lang.OutOfMemoryError: unable to create new native thread`).

### Scenario 6: CPU Throttling
*   **Mô tả**: Dịch vụ `book-service` phải xử lý một khối lượng tính toán nặng dẫn đến việc chiếm dụng hết tài nguyên CPU được cấp phát. Do bị kìm hãm CPU bởi cơ chế cgroups của nhân Linux (CPU Throttling), thời gian xử lý các request bị kéo dài quá mức, gây tắc nghẽn luồng xử lý và timeout.
*   **Mục tiêu giả lập**:
    *   Thiết kế chỉ số CPU đạt ngưỡng 100% và tỷ lệ CPU Throttling leo thang tới 75%.
    *   Log cảnh báo nghẽn hàng đợi thread pool, lỗi từ chối tác vụ (`RejectedExecutionException`) và lỗi timeout từ client.
    *   Sự kiện Kubernetes ghi nhận probe kiểm tra sức khỏe liveness/readiness thất bại do container không kịp phản hồi.

---

## 2. Thiết kế chi tiết dữ liệu giả lập (Fake Data Design)

Dữ liệu giả lập được lưu trữ nhất quán dưới thư mục `Xbrain_fake_data/fake-data/` và được đồng bộ sang `dat/data/fake-data/` để phục vụ chạy kiểm thử.

### 2.1. Scenario 2: Container OOMKilled

#### A. Chuỗi cảnh báo đầu vào (Correlator Input)
*   **Đường dẫn**: `correlator-input/13_container_oomkilled.json`
*   **Nội dung**: Gom nhóm 3 alert xảy ra liên tiếp trong khung thời gian 10 phút (từ `11:00:00Z` tới `11:04:00Z` ngày `2026-06-29`):
    1.  `alert-book-service-memory-high` (started_at: `11:00:00Z`): Cảnh báo RAM vượt ngưỡng 90%.
    2.  `alert-book-service-oomkilled` (started_at: `11:02:00Z`): Cảnh báo container bị tiêu diệt do hết bộ nhớ.
    3.  `alert-book-service-crashloop` (started_at: `11:04:00Z`): Cảnh báo Pod rơi vào trạng thái lặp lại lỗi.

#### B. Chỉ số tài nguyên (Metrics Evidence)
*   **Đường dẫn**: `evidence/metrics/scenario_02_oomkilled_metrics.json`
*   **Dữ liệu RAM (`memory_usage_mb`)**:
    *   Từ `10:45:00Z` tới `10:58:00Z`: Tăng từ 410MB lên 980MB.
    *   Lúc `11:00:00Z` - `11:01:00Z`: Đạt đỉnh `1024.0` (giới hạn cứng của container).
    *   Lúc `11:02:00Z`: Tụt về `200.0` (thời điểm container bị kill và bắt đầu tái khởi động).

#### C. Sự kiện hệ thống (Kubernetes Events Evidence)
*   **Đường dẫn**: `evidence/k8s-events/scenario_02_oomkilled_events.json`
*   Ghi nhận 3 sự kiện chính trong vòng đời Pod:
    *   `OOMKilled` (11:01:45Z): Cảnh báo `Warning` báo hiệu container bị tắt khẩn cấp với exit code 137.
    *   `BackOff` (11:03:15Z): Kubernetes tạm hoãn việc tái khởi động container.
    *   `CrashLoopBackOff` (11:04:10Z): Trạng thái Pod lỗi liên tục.

#### D. Nhật ký hệ thống (Logs Evidence)
*   **Đường dẫn**: `evidence/logs/scenario_02_oomkilled_logs.json`
*   Mô tả quá trình thread tăng đột biến và lỗi cấp phát bộ nhớ native thread:
    *   `10:55:00Z` - Cảnh báo Warning: `"High thread count detected: 1800/2000 limits"`.
    *   `10:58:00Z` - Lỗi Error: `"Thread pool exhausted. Failed to create new native thread. Active threads: 2000"`.
    *   `11:00:00Z` - Lỗi Error: `"java.lang.OutOfMemoryError: unable to create new native thread"`.
    *   `11:01:30Z` - Ghi nhận tín hiệu tắt: `"Container received SIGKILL signal from Kubernetes"`.

---

### 2.2. Scenario 6: CPU Throttling

#### A. Chuỗi cảnh báo đầu vào (Correlator Input)
*   **Đường dẫn**: `correlator-input/14_cpu_throttling.json`
*   **Nội dung**: Gom nhóm 2 alert xảy ra liên tiếp trong khung thời gian 10 phút (từ `12:00:00Z` tới `12:02:00Z` ngày `2026-06-29`):
    1.  `alert-book-service-cpu-high` (started_at: `12:00:00Z`): Cảnh báo CPU sử dụng vượt ngưỡng 95%.
    2.  `alert-book-service-cpu-throttled` (started_at: `12:02:00Z`): Cảnh báo CPU bị bóp băng thông xử lý > 50%.

#### B. Chỉ số tài nguyên (Metrics Evidence)
*   **Đường dẫn**: `evidence/metrics/scenario_06_cpu_throttling_metrics.json`
*   **Dữ liệu CPU (`cpu_usage_percent`)**: Đạt ngưỡng `100.0` liên tiếp từ `12:00:00Z` đến `12:02:00Z`.
*   **Dữ liệu CPU Throttling (`cpu_throttling_percent`)**: Tăng vọt từ `0.0` lên `65.0` (`12:00:00Z`), đạt đỉnh `75.0` (`12:02:00Z`) trước khi giảm dần khi tải hạ nhiệt.

#### C. Sự kiện hệ thống (Kubernetes Events Evidence)
*   **Đường dẫn**: `evidence/k8s-events/scenario_06_cpu_throttling_events.json`
*   Do CPU bị throttle nặng khiến tiến trình không kịp xử lý phản hồi kiểm tra sức khỏe của kubelet:
    *   `Unhealthy` (11:59:30Z): Liveness probe thất bại (kéo dài quá 5000ms).
    *   `Unhealthy` (12:00:45Z): Readiness probe thất bại (kéo dài quá 5000ms).

#### D. Nhật ký hệ thống (Logs Evidence)
*   **Đường dẫn**: `evidence/logs/scenario_06_cpu_throttling_logs.json`
*   Mô tả hiện tượng nghẽn luồng do CPU bị kiềm chế:
    *   `11:55:00Z` - `"Garbage Collection duration exceeds threshold: GC paused for 2100ms"` (quá trình GC bị throttle gây dừng lâu).
    *   `11:58:00Z` - `"Task execution rejected: java.util.concurrent.RejectedExecutionException: Task rejected... Queue capacity (500) exceeded."`.
    *   `12:00:00Z` - `"Thread pool starved. 50 tasks waiting... CPU throttle time: 1450ms"`.
    *   `12:01:00Z` - `"HTTP Request timeout on POST /v1/books: client aborted request after 15000ms"`.

---

## 3. Cập nhật mã nguồn CDO Pipeline

Để hỗ trợ kiểm thử thành công hai kịch bản mới này, tôi đã thực hiện một số cập nhật kỹ thuật trong mã nguồn CDO:

1.  **Cập nhật trích xuất tín hiệu (CDO Correlator)**:
    Tại [correlate.py](file:///d:/GitHub/App_captone_phase2/dat/src/cdo_correlator/correlate.py#L309-L325), tôi đã cập nhật thêm các quy tắc phân tích từ khóa trong hàm `_extract_signals` để tự động nhận dạng các tín hiệu mới:
    *   `oom` -> gán tín hiệu `oom_killed`.
    *   `memory_usage_high` / `high memory` / `memory_usage_mb` -> gán tín hiệu `memory_usage_high`.
    *   `throttle` -> gán tín hiệu `cpu_throttled`.
    *   `cpu` (không chứa từ khóa throttle) -> gán tín hiệu `cpu_usage_high`.
    *   `blackbox` / `ping` -> gán tín hiệu `healthcheck_failed`.
2.  **Khắc phục tương thích môi trường**:
    Tạo file [conftest.py](file:///d:/GitHub/App_captone_phase2/dat/tests/conftest.py) để tự động shim trường `datetime.UTC` (vốn chỉ hỗ trợ từ Python 3.11+) về `datetime.timezone.utc` để chạy tương thích ngược hoàn hảo với môi trường Python 3.10 trên máy phát triển.

---

## 4. Tự động hóa kiểm thử (Testing & Verification)

Tôi đã tạo mới một file test tự động [test_fake_data_pack.py](file:///d:/GitHub/App_captone_phase2/dat/tests/test_fake_data_pack.py) nhằm kiểm duyệt tính chính xác của toàn bộ dữ liệu giả lập trong Monorepo:

*   **Logic kiểm thử**:
    *   Tự động phát hiện toàn bộ 14 kịch bản cảnh báo dưới thư mục `correlator-input`.
    *   Đưa từng kịch bản qua CDO Correlator để sinh incident và kiểm chứng so khớp 100% các thông tin: ID, severity, signals, alert_ids, related_entities.
    *   Đối với các kịch bản hợp lệ, đưa incident qua CDO Evidence Builder để gom dữ liệu từ thư mục `evidence/`. Kiểm tra chất lượng context (`COMPLETE`), đảm bảo các metrics, logs, và events khớp chính xác và được lọc gọn theo khung thời gian xảy ra lỗi.
*   **Kết quả chạy thực tế**:
    Chạy lệnh `python -m pytest` thành công hoàn toàn **38/38 test cases** (bao gồm 24 test có sẵn của hệ thống và 14 test kịch bản tự động mới):
    ```text
    tests\test_correlator.py ......                                          [ 15%]
    tests\test_evidence_builder.py ......                                    [ 31%]
    tests\test_fake_data_pack.py ..............                              [ 68%]
    tests\test_ingest.py ............                                        [100%]

    ============================= 38 passed in 0.30s ==============================
    ```
