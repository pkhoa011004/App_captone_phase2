# Tài liệu Luồng Xử lý Sự cố Triage Hub (End-to-End Pipeline Flow)

Tài liệu này đặc tả toàn bộ quy trình xử lý dữ liệu cảnh báo từ khi sự cố xảy ra ở hạ tầng cho đến khi AI chẩn đoán, tạo ticket Jira và gửi thông báo qua Slack.

---

## 1. Sơ đồ luồng (Workflow Diagram)

Dưới đây là sơ đồ luồng dữ liệu end-to-end được thiết kế theo mô hình K8s-native / event-driven worker:

```mermaid
graph TD
    %% Khai báo các bên liên quan
    subgraph K8s_Workload [Hạ tầng Kubernetes]
        workload[Microservices: book-service, ...]
        prom[Prometheus / Metrics]
        loki[Loki / Logs]
    end

    subgraph Phase_1 [CDO Phase 1: Ingestion Layer]
        am[Alertmanager Webhook]
        lambda[Ingest Lambda]
        catalog[Service Catalog YAML]
    end

    subgraph Phase_2_3 [CDO Phase 2 & 3: Correlation & Evidence Layer]
        sqs[SQS Incident Queue]
        correlator[cdo-correlator]
        state_store[(DynamoDB / State Store)]
        builder[cdo-evidence-builder]
        s3[(S3 Evidence Storage)]
    end

    subgraph AIOps_Layer [AIOps: AI Diagnose Layer]
        ai_engine[AI Engine / RCA Worker]
        llm[AI Model / Bedrock, OpenAI]
    end

    subgraph Dispatch_Layer [Notification & Action Layer]
        jira[Jira API]
        slack[Slack API]
    end

    %% Luồng đi của dữ liệu
    workload -->|Bắn alert| am
    am -->|Webhook payload| lambda
    catalog -->|Làm giàu metadata| lambda
    lambda -->|Ghi log & Normalization| sqs
    
    sqs -->|Đọc alert wrappers| correlator
    correlator <-->|Lưu/Đọc trạng thái gom nhóm| state_store
    correlator -->|Incident JSON| builder
    
    builder -->|Query Logs trong khung thời gian| loki
    builder -->|Query Metrics trong khung thời gian| prom
    builder -->|Đọc Lịch sử Deploy & Ownership| s3
    builder -->|Evidence Bundle JSON| s3
    
    s3 -->|Tải Evidence Bundle| ai_engine
    ai_engine -->|Gửi prompt + context| llm
    llm -->|Kết quả RCA & Gợi ý xử lý| ai_engine
    
    ai_engine -->|Tạo ticket| jira
    ai_engine -->|Gửi alert kèm nút Ack 1-click| slack
```

---

## 2. Chi tiết các bước trong luồng xử lý

### Bước 1: Cảnh báo kích hoạt (Alert Trigger)
Khi có sự cố xảy ra trên workload (ví dụ: RAM chạm hạn mức ở Scenario 2, hoặc code mới bị lỗi HTTP 500 ở Scenario 3):
1.  **Prometheus/Alertmanager** phát hiện chỉ số bất thường và bắn webhook alert thô (Raw alert) sang **Ingest Lambda**.

### Bước 2: Ingest & Normalize (CDO Phase 1)
1.  **Ingest Lambda** nhận raw alert.
2.  Kiểm tra tính hợp lệ (bắt buộc phải có các nhãn định danh: `tenant_id`, `environment`, `cluster`, `namespace`).
3.  Truy vấn **Service Catalog** để tự động điền các nhãn thông tin sở hữu còn thiếu (`owner_team`, `slack_channel`, `jira_project`).
4.  Lưu alert đã chuẩn hóa (Alert Wrapper) vào hàng đợi **SQS**.

### Bước 3: Gom nhóm & Correlate (CDO Phase 2)
1.  **cdo-correlator** kéo các alert từ queue.
2.  Gom các alert có cùng phạm vi (`tenant_id` + `service` + `environment` + `cluster` + `namespace`) xảy ra trong cùng một khung thời gian **10 phút** thành một **Incident** duy nhất.
3.  Cập nhật trạng thái vào State Store (tránh sinh lặp incident và hỗ trợ cơ chế giảm thiểu bão cảnh báo).

### Bước 4: Thu thập bằng chứng (CDO Phase 3 - Evidence Builder)
1.  Từ Incident được tạo, **cdo-evidence-builder** tự động mở rộng thời gian trước sự cố 15 phút và sau sự cố 5 phút (ví dụ: Alert bắt đầu lúc 10:00, Evidence window sẽ là 09:45 đến 10:10).
2.  Tiến hành truy vấn và lọc dữ liệu từ các kho lưu trữ:
    *   **Metrics**: Tải biểu đồ CPU/RAM, request rates.
    *   **Logs**: Tải log của container lỗi (nhận dạng các lỗi Thread, Exception).
    *   **K8s Events**: Gom các sự kiện Pod (`OOMKilled`, `Killing`, `CrashLoopBackOff`).
    *   **Deploys**: Truy xuất lịch sử triển khai gần nhất để kiểm tra có đợt cập nhật code nào trước sự cố hay không.
3.  Đóng gói toàn bộ thành một file **Evidence Bundle JSON** lưu trữ bất biến trên S3.

### Bước 5: Chẩn đoán AI (AI RCA Engine)
1.  **AI Engine** nhận thông báo về Evidence Bundle mới trên S3.
2.  Đọc file bundle, trích xuất dữ liệu thô và dựng prompt gửi đến LLM (như AWS Bedrock hoặc OpenAI).
3.  AI thực hiện phân tích:
    *   *Nguyên nhân*: Do đâu (ví dụ: OOMKilled do rò rỉ bộ nhớ, hoặc HTTP 500 do NullPointerException ở dòng 42 của deploy v1.4.3).
    *   *Mức độ tin cậy (Confidence)*.
    *   *Đề xuất hành động xử lý*.

### Bước 6: Tạo Ticket & Gửi thông báo (Notification & Human-in-the-loop)
1.  Hệ thống gọi API tạo ticket lỗi trên **Jira** (gắn tag team sở hữu, mức độ nghiêm trọng).
2.  Gửi thông điệp Slack đến kênh của đội on-call (`slack_channel`) chứa:
    *   Tóm tắt nguyên nhân lỗi từ AI.
    *   Đường link tới bằng chứng (Evidence Bundle) và ticket Jira.
    *   Nút bấm **1-Click Acknowledge** để kỹ sư on-call xác nhận xử lý, đảm bảo con người kiểm soát quy trình quyết định cuối cùng (*Human-in-the-loop*).
