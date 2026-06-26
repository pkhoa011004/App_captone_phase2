# Thiết kế Hạ tầng - Task Force 1 · CDO 5

## 1. Sơ đồ kiến trúc

```text
User / Load Generator (Người dùng / Bộ tạo tải)
        │
        ▼
Application Load Balancer (Bộ cân bằng tải ứng dụng)
        │
        ▼
Demo App Workloads on EKS (Workload ứng dụng Demo trên EKS)
        │
        ├── metrics (thông số)
        │      ▼
        │   Prometheus
        │      ▼
        │   PrometheusRule
        │
        ├── logs (nhật ký)
        │      ▼
        │   Loki
        │
        └── dashboards (bảng điều khiển)
               ▼
            Grafana
```

## 1.1 Luồng xử lý sự cố chính (Main incident flow)

```text
PrometheusRule
        │
        ▼
Alertmanager
Gom nhóm / Ngăn chặn / Tắt tiếng / Khoảng thời gian lặp lại
        │
        ▼
Ingest Lambda (Lambda tiếp nhận)
Xác thực + Chuẩn hóa webhook cảnh báo
        │
        ▼
SQS FIFO Raw Alert Queue (Hàng đợi SQS FIFO cảnh báo thô)
Bộ đệm cảnh báo bền vững (Durable alert buffer)
        │
        ▼
CDO Incident Correlator Worker on EKS (Worker tương quan sự cố CDO trên EKS)
Loại bỏ trùng lặp + Tương quan các sự kiện cảnh báo
        │
        ▼
AI Engine / RCA
Truy vấn Prometheus/Loki + thực hiện RCA
        │
        ▼
Integration Lambda / CDO Integration Layer (Lambda/Lớp tích hợp CDO)
Tạo / cập nhật Slack và Jira
        │
        ▼
Slack / Jira
Thông báo và theo dõi sự cố hướng tới người vận hành (Human-facing)
```

## 1.2 Trạng thái chia sẻ và kho lưu trữ artifact (Shared state and artifact stores)

DynamoDB và S3 không phải là các thành phần tuyến tính trong luồng dữ liệu chính. Chúng là các kho lưu trữ chia sẻ được sử dụng bởi nhiều thành phần trong pipeline xử lý sự cố.

```text
                         ┌──────────────────────────────────────────┐
                         │ DynamoDB incident_state                  │
                         │ Trạng thái / Idempotency / Tình trạng    │
                         │ Tiến trình workflow / Các con trỏ        │
                         └──────────────────────────────────────────┘
                                              ▲
                                              │ read/write (đọc/ghi)
        ┌─────────────────────────────────────┼─────────────────────────────────────┐
        │                                     │                                     │
Ingest Lambda                      CDO Correlator Worker                 Integration Lambda
ghi trạng thái tiếp nhận           đọc/ghi trạng thái workflow           đọc/ghi trạng thái Jira/Slack
ghi trạng thái hàng đợi            ghi trạng thái AI                     ghi trạng thái tích hợp
tùy chọn con trỏ S3 URI            ghi các con trỏ S3 URI                ghi các con trỏ S3 URI
```

```text
                         ┌──────────────────────────────────────────┐
                         │ S3 Incident Artifact Store               │
                         │ Payloads / Minh chứng / Báo cáo          │
                         │ Tài liệu Replay / Kiểm toán (Audit)      │
                         └──────────────────────────────────────────┘
                                              ▲
                                              │ put/read object (đẩy/đọc đối tượng)
        ┌─────────────────────────────────────┼─────────────────────────────────────┐
        │                                     │                                     │
Ingest Lambda                      CDO Correlator Worker                 AI Engine
tùy chọn snapshot                  các cảnh báo đã gom nhóm              ngữ cảnh đã sử dụng
payload cảnh báo thô               ngữ cảnh sự cố                        minh chứng đã sử dụng
                                   yêu cầu/phản hồi AI                   kết quả RCA
                                              
                                              │
                                              ▼
                                      Integration Lambda
                                      yêu cầu Jira/Slack
                                      phản hồi Jira/Slack
```

Quy tắc cốt lõi:

```text
DynamoDB theo dõi trạng thái workflow và tính idempotency (tránh xử lý trùng lặp).
S3 lưu trữ các artifact và minh chứng sự cố.
DynamoDB lưu trữ các con trỏ (pointers) tới đối tượng S3, không lưu trực tiếp báo cáo đầy đủ hoặc các payload lớn.
```

Khi một thành phần tạo ra một artifact:

```text
1. Thành phần tạo ra artifact.
2. Thành phần ghi artifact đó vào S3.
3. Thành phần cập nhật DynamoDB với URI S3 và tình trạng của artifact.
```

Ví dụ:

```text
CDO Correlator Worker tạo ra rca_report.json
→ PutObject lên S3
→ Cập nhật DynamoDB:
   report.status = STORED
   report_s3_uri = s3://incident-artifacts/{tenant_id}/{service}/{incident_id}/rca_report.json
```

## 1.3 Chú giải (Caption)

Kiến trúc này sử dụng Amazon EKS làm nền tảng runtime chính cho ứng dụng demo, CDO Incident Correlator Worker và stack observability native với Kubernetes. Traffic từ người dùng truy cập thông qua Application Load Balancer (ALB) và đi tới các workload demo chạy bên trong EKS.

Ứng dụng phát sinh các metric (thông số) và log (nhật ký). Metric được lưu trữ trong Prometheus, log được lưu trữ trong Loki, và Grafana được dùng làm giao diện dashboard để điều tra sự cố. PrometheusRule đánh giá các metric và kích hoạt cảnh báo (alert) khi phát hiện các điều kiện bất thường.

Alertmanager đóng vai trò là lớp kiểm soát nhiễu cảnh báo đầu tiên. Nó thực hiện gom nhóm (grouping) các cảnh báo liên quan, ngăn chặn (inhibit) các cảnh báo phụ thuộc, hỗ trợ các quy tắc tắt tiếng (silence) và kiểm soát khoảng thời gian lặp lại (repeat intervals) trước khi cảnh báo đi vào pipeline xử lý sự cố.

Ingest Lambda nhận webhook từ Alertmanager, xác thực các siêu dữ liệu (metadata) bắt buộc, chuẩn hóa payload cảnh báo, tùy chọn lưu trữ minh chứng cảnh báo thô vào S3, ghi trạng thái tiếp nhận/hàng đợi ban đầu vào DynamoDB nếu cần, và gửi sự kiện cảnh báo tới SQS FIFO.

SQS FIFO chỉ được sử dụng cho các sự kiện cảnh báo. Nó cung cấp bộ đệm bền vững (durable buffering), cơ chế thử lại (retry), thời gian ẩn tin nhắn (visibility timeout), hàng đợi lỗi FIFO DLQ và khả năng giám sát hàng đợi tích lũy (backlog). Các metric và log thô không đi qua SQS FIFO.

CDO Incident Correlator Worker thực hiện poll tin nhắn từ SQS FIFO, kiểm tra trạng thái trong DynamoDB để đảm bảo tính idempotency, loại bỏ các cảnh báo trùng lặp, gom các cảnh báo liên quan thành các trigger cấp sự cố (incident-level), ghi các artifact tương quan vào S3, cập nhật trạng thái workflow trong DynamoDB và chỉ gọi AI Engine khi có sự cố mới hoặc có cập nhật quan trọng.

AI Engine thuộc quyền sở hữu của đội ngũ AIOps/AI. Nó nhận trigger cấp sự cố, truy vấn Prometheus và Loki thông qua quyền truy cập đọc có giới hạn (bounded read access), xây dựng ngữ cảnh metric/log, thực hiện phân tích nguyên nhân gốc rễ (RCA) và trả về kết quả cấu trúc như nguyên nhân gốc rễ, độ tin cậy, minh chứng, ngữ cảnh bị thiếu và các hành động gợi ý. Nếu được cấp quyền truy cập S3 trong phạm vi giới hạn, AI Engine cũng có thể ghi trực tiếp ngữ cảnh và minh chứng mà nó đã sử dụng cho phân tích vào S3.

Integration Lambda hoặc Lớp Tích hợp CDO (CDO Integration Layer) chịu trách nhiệm tạo hoặc cập nhật Slack và Jira. Nó đọc trạng thái sự cố từ DynamoDB, đọc báo cáo hoặc payload từ S3 nếu cần, gửi cập nhật đến Slack/Jira, lưu trữ lịch sử yêu cầu/phản hồi tích hợp vào S3 và cập nhật trạng thái Slack/Jira vào DynamoDB.

CloudWatch giám sát các thành phần pipeline phía AWS như Lambda, SQS FIFO, FIFO DLQ, DynamoDB, S3 và các log tích hợp.

---

## 1.4 Ranh giới quyền sở hữu dữ liệu (Data ownership boundary)

Hệ thống có hai luồng dữ liệu khác nhau.

### Luồng giám sát thông thường (Normal observability flow)

```text
App trên EKS
→ Prometheus metrics
→ Loki logs
→ Grafana dashboards
→ SRE / AI Engine truy vấn theo tenant/service/env/time window
```

Luồng này được sử dụng cho việc giám sát thông thường, SRE điều tra sự cố, hiển thị dashboard và lấy ngữ cảnh RCA.

Ranh giới quan trọng:

```text
Metrics/logs không đi qua SQS FIFO.
Metrics nằm lại tại Prometheus.
Log của ứng dụng Kubernetes nằm lại tại Loki.
Log/metrics của các dịch vụ phía AWS nằm lại tại CloudWatch.
```

AI Engine có thể truy cập dữ liệu giám sát thông qua quyền truy cập giới hạn (bounded access).

Các chiều truy vấn được đề xuất:

```text
tenant_id
service
env
namespace
time_window
alertname
severity
```

### Luồng cảnh báo sự cố (Alert incident flow)

```text
PrometheusRule
→ Alertmanager
→ Ingest Lambda
→ SQS FIFO
→ CDO Incident Correlator Worker
→ AI Engine / RCA
→ Integration Lambda / CDO Integration Layer
→ Slack / Jira
```

Luồng này chỉ được kích hoạt khi có sự kiện cảnh báo xảy ra và quy trình xử lý sự cố cần được bắt đầu.

Phân biệt cốt lõi:

```text
Metric/log thô = dữ liệu phân tích.
Sự kiện cảnh báo = trigger kích hoạt workflow sự cố.
```

Metric và log không được đẩy qua pipeline cảnh báo. Pipeline cảnh báo chỉ truyền tải các sự kiện trigger sự cố và các chuyển đổi trạng thái của workflow.

---

## 1.5 Ranh giới trách nhiệm: CDO vs AIOps / AI Engine

CDO không sở hữu logic RCA và không xây dựng logic lập luận AI cuối cùng.

CDO sở hữu:

```text
- Nền tảng runtime trên EKS
- Môi trường chạy ứng dụng demo
- Prometheus, Grafana, Alertmanager, Loki
- Tính nhất quán của metadata giám sát
- Quyền truy cập đọc có giới hạn vào Prometheus/Loki/CloudWatch
- Network policy, IAM, RBAC và ranh giới truy cập secret
- Tiếp nhận cảnh báo từ Alertmanager
- Bộ đệm cảnh báo SQS FIFO và FIFO DLQ
- Loại bỏ trùng lặp và tương quan cảnh báo
- Trạng thái workflow sự cố trong DynamoDB
- Lưu trữ artifact/minh chứng sự cố trong S3
- Độ tin cậy của tích hợp Jira/Slack (nếu được phân công cho CDO)
- Giám sát CloudWatch cho các dịch vụ pipeline phía AWS
```

AIOps / AI Engine sở hữu:

```text
- Nhận trigger cấp sự cố từ CDO
- Truy vấn Prometheus metrics theo tenant/service/env/window
- Truy vấn Loki logs theo tenant/service/env/window
- Chuẩn hóa và tổng hợp metrics/logs
- Xây dựng ngữ cảnh theo khung thời gian (time-window)
- Tính toán baseline/xu hướng/bất thường
- Thực hiện RCA
- Trả về nguyên nhân gốc rễ, độ tin cậy, minh chứng, ngữ cảnh bị thiếu và hành động gợi ý
- Tùy chọn ghi các artifact AI/minh chứng/RCA vào prefix S3 được giới hạn phạm vi
```

Ranh giới cuối cùng:

```text
CDO sở hữu nền tảng, độ tin cậy cảnh báo, trạng thái workflow và lưu trữ kiểm toán.
AI sở hữu việc diễn giải dữ liệu giám sát và RCA.
```

AI Engine không nên sở hữu cơ chế thử lại của SQS FIFO, tính idempotency của sự cố hoặc kiểm soát tác động ngoài (side-effect) của Jira/Slack.

---

# 2. Bảng thành phần (Component table)

|Thành phần|Dịch vụ AWS / Công cụ|Lý do lựa chọn|Lưu ý về chi phí|
|---|---|---|---|
|Compute (Tính toán)|Amazon EKS|Môi trường chạy chính cho app demo, CDO Correlator Worker và stack giám sát. Lựa chọn vì Kubernetes cung cấp metadata workload nhất quán, namespace, nhãn (labels), phát hiện dịch vụ (service discovery), NetworkPolicy và ngữ cảnh triển khai thân thiện với GitOps.|Chi phí cố định cao hơn ECS/Lambda do phí EKS control plane và các worker node. Được chấp nhận vì phục vụ thiết kế Kubernetes-native.|
|API entry (Cổng vào API)|ALB + AWS Load Balancer Controller|Cổng vào công cộng cho traffic từ người dùng/bộ tạo tải vào app demo trên EKS. Được quản lý thông qua Kubernetes Ingress.|ALB tính phí theo giờ và dung lượng traffic. Duy trì một ALB dùng chung cho MVP.|
|Metrics|Prometheus|Lưu trữ metric của ứng dụng và Kubernetes, đánh giá PrometheusRule và cung cấp nguồn truy vấn cho SRE/AIOps.|Chạy trong EKS, tiêu thụ CPU/RAM/dung lượng lưu trữ của node. Thời gian lưu trữ (retention) nên được giới hạn cho bản MVP.|
|Logs|Loki|Lưu trữ log workload của Kubernetes và hỗ trợ truy vấn theo nhãn (label) như namespace, pod, service, tenant_id, env và time window.|Chạy trong EKS. Chi phí phụ thuộc vào lượng log phát sinh và thời gian lưu trữ.|
|Dashboard|Grafana|Giao diện dashboard và điều tra cho metrics, logs và trạng thái cảnh báo.|Chạy trong EKS. Tiêu tốn tài nguyên rất ít trong bản MVP.|
|Kiểm soát nhiễu cảnh báo|Alertmanager|Lớp kiểm soát nhiễu cảnh báo đầu tiên: gom nhóm (grouping), ngăn chặn (inhibition), tắt tiếng (silence), group_wait, repeat_interval.|Chạy như một phần của stack giám sát.|
|Tiếp nhận cảnh báo|Ingest Lambda|Nhận webhook của Alertmanager, xác thực các trường bắt buộc, chuẩn hóa payload cảnh báo, tùy chọn ghi minh chứng thô và gửi tin nhắn vào SQS FIFO.|Chi phí thấp cho MVP vì lượng cảnh báo nhỏ.|
|Hàng đợi sự kiện|SQS FIFO Raw Alert Queue + FIFO DLQ|Đóng vai trò bộ đệm cảnh báo bền vững, xử lý thử lại, ẩn tin nhắn, giám sát hàng đợi tích lũy, hàng đợi lỗi FIFO DLQ cho các tin nhắn lỗi. Giúp phân tách lớp giám sát với xử lý hạ nguồn.|Thấp đối với traffic của dự án capstone. Cần giám sát backlog và FIFO DLQ.|
|Worker xử lý sự cố|CDO Incident Correlator Worker trên EKS|Poll tin nhắn từ SQS FIFO, loại bỏ cảnh báo trùng lặp, tương quan các cảnh báo liên quan, cập nhật DynamoDB, ghi artifact vào S3 và gọi AI Engine khi cần.|Chạy trên EKS worker node. Có thể scale dựa trên lượng hàng đợi tích lũy.|
|Trạng thái sự cố|DynamoDB|Lưu trữ incident_state, alert_fingerprint, correlation_key, tiến trình workflow, số lần thử lại, Jira ticket ID, Slack thread ID, lỗi cuối cùng và các con trỏ S3 URI. Đảm bảo tính idempotency.|Thấp cho MVP. Chế độ On-demand (theo yêu cầu) phù hợp hơn với traffic demo không ổn định.|
|Lưu trữ artifact|S3|Lưu trữ payload cảnh báo gốc, cảnh báo đã gom nhóm, yêu cầu/phản hồi AI, ngữ cảnh/minh chứng của AI, báo cáo RCA, payload Jira/Slack và tài liệu replay/debug.|Chi phí thấp. Có thể sử dụng lifecycle policy để chuyển dữ liệu cũ sang các tầng lưu trữ rẻ hơn.|
|RCA engine|AI Engine|Thực hiện phân tích RCA bằng cách truy vấn Prometheus/Loki và phân tích ngữ cảnh sự cố.|Do đội AIOps sở hữu. Chi phí phụ thuộc vào model/runtime.|
|Tích hợp bên ngoài|Integration Lambda / CDO Integration Layer + Jira + Slack|Tạo/cập nhật Jira và Slack. Một sự cố tương ứng với một Jira ticket và một Slack thread.|Chi phí dịch vụ bên ngoài phụ thuộc vào tài khoản/license, không tính vào hạ tầng AWS cốt lõi.|
|Giám sát phía AWS|CloudWatch|Giám sát log Lambda, SQS FIFO backlog, số lượng FIFO DLQ, lỗi/nghẽn của DynamoDB, lỗi S3 và log tích hợp AWS.|Chi phí phụ thuộc vào lượng log lưu trữ. Cần thiết lập retention policy để tối ưu.|
|Quản lý secret|Secrets Manager / SSM|Lưu trữ token Jira, token/webhook Slack, API key của AI Engine và các secret dùng trong runtime.|Thấp nếu số lượng secret nhỏ.|
|Quyền truy cập AWS của Pod|IAM + IRSA / EKS Pod Identity|Cho phép các pod trên EKS truy cập SQS FIFO, DynamoDB, S3 và Secrets Manager với nguyên tắc đặc quyền tối thiểu.|Không tốn thêm chi phí trực tiếp, nhưng rất quan trọng cho bảo mật.|

---

## 2.1 Trách nhiệm của thành phần (Component responsibility)

|Thành phần|Nhiệm vụ thực hiện|Không thực hiện|
|---|---|---|
|ALB|Định tuyến traffic công cộng tới app demo/dịch vụ API trên EKS.|Không gọi trực tiếp AI Engine.|
|EKS|Chạy các workload ứng dụng, Worker và stack giám sát.|Không tự lưu trữ trạng thái sự cố bền vững.|
|Demo App|Tạo traffic, metrics, logs và các kịch bản lỗi.|Không thực hiện RCA hoặc tạo Jira/Slack.|
|Prometheus|Thu thập metrics, lưu trữ time-series, đánh giá các luật cảnh báo.|Không lưu trữ nhật ký (logs) của ứng dụng.|
|Loki|Lưu trữ logs của ứng dụng/workload trên Kubernetes.|Không giám sát các dịch vụ AWS được quản lý.|
|Grafana|Cung cấp giao diện dashboard và điều tra sự cố.|Không sở hữu trạng thái workflow sự cố.|
|Alertmanager|Gom nhóm, ngăn chặn, tắt tiếng và kiểm soát cảnh báo lặp lại trước khi tiếp nhận.|Không thực hiện tương quan sự cố sâu giữa nhiều dịch vụ hoặc quản lý idempotency phía Jira/Slack.|
|Ingest Lambda|Xác thực và chuẩn hóa webhook cảnh báo, tùy chọn lưu artifact cảnh báo thô, ghi trạng thái tiếp nhận/hàng đợi ban đầu, đẩy cảnh báo vào SQS FIFO.|Không thực hiện RCA, không truy vấn sâu metrics/logs, không gọi AI Engine để phân tích RCA, không tạo Jira/Slack.|
|SQS FIFO|Lưu trữ sự kiện cảnh báo một cách bền vững và hỗ trợ thử lại/FIFO DLQ.|Không lưu trữ dữ liệu thô metric/log và không tự ghi vào DynamoDB/S3.|
|SQS FIFO DLQ|Lưu trữ các tin nhắn bị lỗi quá số lần quy định.|Không tự động sửa các tin nhắn bị lỗi.|
|CDO Correlator Worker|Poll tin nhắn từ SQS FIFO, loại bỏ cảnh báo trùng lặp, tương quan các cảnh báo liên quan, cập nhật DynamoDB, ghi artifact vào S3, quyết định có gọi AI Engine hay không.|Không sở hữu logic lập luận RCA, tính toán baseline, diễn giải bất thường hoặc phân tích sâu nhật ký.|
|DynamoDB|Lưu trữ trạng thái sự cố, key idempotency, tiến trình workflow, ID của Jira/Slack và các con trỏ trỏ tới artifact trên S3.|Không lưu trữ logs thô, dữ liệu metric lớn hoặc minh chứng lớn của AI.|
|S3 Artifact Store|Lưu trữ minh chứng kiểm toán, yêu cầu/phản hồi AI, snapshot payload, báo cáo RCA và tài liệu replay/debug.|Không theo dõi trạng thái workflow trực tiếp và không hoạt động như một state machine.|
|AI Engine|Truy vấn dữ liệu giám sát, xây dựng ngữ cảnh RCA, thực hiện lập luận phân tích, tùy chọn viết artifact AI lên S3, trả về kết quả RCA/độ tin cậy/hành động gợi ý.|Không sở hữu độ bền vững cảnh báo, cơ chế thử lại của SQS FIFO, trạng thái pipeline hoặc kiểm soát tác động ngoài của Jira/Slack.|
|Integration Lambda / CDO Integration Layer|Tạo/cập nhật Jira và Slack, ghi nhật ký yêu cầu/phản hồi tích hợp, cập nhật DynamoDB.|Không thực hiện RCA.|
|Jira/Slack|Giao diện thông báo và theo dõi sự cố dành cho con người.|Không làm nguồn dữ liệu gốc (source of truth) cho trạng thái workflow.|
|CloudWatch|Giám sát các thành phần pipeline phía AWS.|Không thay thế Loki để lưu trữ log ứng dụng Kubernetes.|

---

# 3. Phân tích sâu về góc độ tạo sự khác biệt (Differentiation angle deep-dive)

## 3.1 Tại sao chọn góc độ này?

Góc độ lựa chọn:

```text
Pipeline xử lý sự cố tin cậy với khả năng kiểm soát cơn bão cảnh báo (Alert Storm) và cổng gọi AI hạn chế
```

Điểm khác biệt chính của thiết kế này không chỉ nằm ở việc chọn EKS. EKS là runtime foundation. Giá trị thật của kiến trúc nằm ở cách CDO biến các alert nhiễu, lặp và phân mảnh thành incident-level trigger đáng tin cậy trước khi gọi AI Engine.

TF1 Triage Hub không chỉ là bài toán host container. Đây là bài toán xây một nền tảng AIOps incident triage, nơi CDO cần kết nối workload runtime, observability, alerting, deployment metadata, incident state và human integration thành một flow nhất quán.

Trong incident thật, một root cause có thể tạo ra nhiều alert ở nhiều service khác nhau:

```text
redis RedisTimeout
payment-api HighLatency
payment-api High5xx
checkout-api Timeout
frontend ErrorRateHigh
```

Nếu thiết kế đơn giản theo kiểu gửi từng alert trực tiếp sang AI Engine:

```text
Alert
→ AI Engine
→ Jira/Slack
```

thì hệ thống có nhiều rủi ro:

```text
- AI Engine bị gọi quá nhiều lần cho cùng một incident (tốn chi phí và tài nguyên)
- Jira ticket có thể bị tạo trùng lặp
- Slack channel có thể bị spam gây loãng thông tin
- RCA bị phân mảnh theo từng alert riêng lẻ
- Người vận hành có thể hiểu nhầm symptom (triệu chứng) là các sự cố riêng biệt
- Cost và latency tăng không cần thiết
```

Thiết kế CDO đề xuất thêm một reliable incident pipeline trước AI processing:

```text
Luồng sự cố chính:
PrometheusRule
→ Alertmanager
→ Ingest Lambda
→ SQS FIFO Raw Alert Queue
→ CDO Incident Correlator Worker
→ AI Engine (chỉ gọi khi cần thiết)
→ Integration Lambda / CDO Integration Layer
→ Jira/Slack
```

DynamoDB và S3 không nằm tuyến tính trong main flow. Chúng là shared stores được nhiều component đọc/ghi:

```text
Các kho lưu trữ phụ trợ:
- DynamoDB incident_state:
  lưu trạng thái workflow, idempotency, trạng thái retry, bước hiện tại, các ID của Jira/Slack, con trỏ S3 URI

- Kho lưu trữ minh chứng/kiểm toán S3:
  lưu payload cảnh báo thô, cảnh báo đã gom nhóm, yêu cầu/phản hồi AI, minh chứng RCA, payload của Jira/Slack, tài liệu phục vụ replay
```

Thiết kế này có ba lớp bảo vệ chính:

```text
1. Alertmanager giảm nhiễu cơ bản trước khi tiếp nhận (ingestion).
2. SQS FIFO bảo vệ việc chuyển cảnh báo (alert delivery) bằng cơ chế đệm bền vững, thử lại và FIFO DLQ.
3. CDO Correlator + DynamoDB loại trùng cảnh báo, gom các cảnh báo liên quan thành một sự cố (incident) và tránh tạo trùng lặp Jira/Slack.
```

Tuyên bố cốt lõi:

```text
SQS FIFO bảo vệ việc truyền tải cảnh báo.
DynamoDB bảo vệ trạng thái workflow và tính idempotency.
S3 lưu giữ minh chứng kiểm toán và tài liệu phục vụ replay.
CDO Correlator bảo vệ AI Engine khỏi các cơn bão cảnh báo (alert storms).
EKS cung cấp hệ sinh thái nơi các thành phần nền tảng này có thể chạy gần với workload.
```

---

## 3.2 Tại sao không dùng Lambda hay ECS làm nền tảng chính?

### Tại sao không dùng Lambda làm nền tảng compute chính?

Lambda phù hợp cho short-lived event handling, nhưng TF1 Triage Hub không chỉ là một API hoặc một simple event processor.

Nền tảng này cần chạy nhiều thành phần có tính platform và long-running:

```text
- Các workload ứng dụng demo
- CDO Incident Correlator Worker
- Prometheus
- Loki
- Grafana
- Alertmanager
- Ngữ cảnh triển khai được quản lý bằng GitOps
- Siêu dữ liệu Kubernetes bao quanh workload
```

Nếu dùng Lambda làm compute chính, team vẫn cần một runtime khác để chạy observability stack và các thành phần dạng worker. Điều đó làm hệ thống bị chia thành nhiều execution model khác nhau:

```text
- Lambda cho alert/API
- Một runtime khác cho app
- Một runtime khác cho observability
- Một cách khác để quản lý deployment metadata
```

Kết quả là RCA context khó nhất quán hơn. AI Engine cần biết alert liên quan tới service nào, pod/task nào, deployment version nào, namespace nào, tenant nào và logs/metrics nào trong cùng time window. Lambda không cung cấp một workload metadata ecosystem đủ tự nhiên cho bài toán này.

Vì vậy, Lambda vẫn được dùng, nhưng chỉ là thin adapter (bộ chuyển đổi mỏng):

```text
Alertmanager
→ Ingest Lambda
→ SQS FIFO
```

Lambda chỉ làm:

```text
- Nhận webhook
- Xác thực alert payload
- Chuẩn hóa sự kiện cảnh báo
- Gửi tin nhắn tới SQS FIFO
- Tùy chọn ghi trạng thái tiếp nhận ban đầu hoặc minh chứng payload thô
```

Lambda không làm:

```text
- Runtime chính của toàn hệ thống
- Nền tảng observability
- Worker chạy ngầm (long-running worker)
- Tương quan sự cố sâu
- Phân tích RCA
```

Quyết định (Decision):

```text
Chỉ sử dụng Lambda cho việc tiếp nhận cảnh báo nhẹ nhàng (lightweight alert ingestion).
Không sử dụng Lambda làm nền tảng tính toán chính.
```

---

### Tại sao không dùng ECS Fargate?

ECS Fargate chạy container tốt, đơn giản hơn EKS và thường rẻ hơn cho bài toán host service thông thường.

Lý do không chọn ECS không phải vì ECS không làm được. ECS vẫn có thể chạy demo app, worker và expose service qua ALB.

Nhưng TF1 cần nhiều hơn container hosting. TF1 cần một ecosystem thống nhất cho:

```text
- Workload runtime
- Observability
- Alerting
- Triển khai minh chứng (deployment evidence)
- Ranh giới bảo mật (security boundary)
- Siêu dữ liệu sự cố (incident metadata)
- Quyền truy cập truy vấn RCA có giới hạn (bounded access)
```

Với ECS, các ngữ cảnh cần cho RCA thường nằm rải ở nhiều nơi:

```text
- Metadata của ECS service/task
- CloudWatch metrics/logs
- Các sự kiện triển khai của EventBridge
- ALB target group
- Lịch sử pipeline CI/CD
- Các AWS resource tags
- Quy ước đặt tên tùy chỉnh (custom naming convention)
```

Ví dụ khi alert `High5xx` xảy ra ở `checkout-api`, AIOps cần biết:

```text
- Tenant nào bị ảnh hưởng
- Env nào bị ảnh hưởng
- Service nào lỗi
- Task/pod nào không khỏe (unhealthy)
- Version nào đang chạy
- Có đợt rollout nào vừa diễn ra không
- Metrics/logs nào thuộc cùng khung thời gian (time window)
- Cảnh báo này liên quan tới nhóm dịch vụ (service group) nào
```

Với ECS, các thông tin này có thể lấy được, nhưng CDO phải viết thêm glue logic (logic gắn kết) để nối ECS metadata, CloudWatch, EventBridge, ALB, CI/CD records và tags thành một ngữ cảnh sự cố thống nhất.

Với EKS, nhiều thông tin này nằm tự nhiên trong mô hình workload của Kubernetes:

```text
- Namespace
- Pod
- Deployment
- Service
- Labels
- Annotations
- Trạng thái rollout
- NetworkPolicy
- RBAC
- ServiceAccount
```

Cùng một mô hình nhãn (label model) có thể đi xuyên suốt:

```text
Kubernetes workload
→ Prometheus metrics
→ Loki logs
→ Alertmanager alert labels
→ Lịch sử triển khai của Argo CD
→ CDO Correlator incident_state
→ Hợp đồng truy vấn giới hạn của AI Engine
```

Vì vậy, ECS là lựa chọn tốt nếu mục tiêu là chạy container đơn giản, chi phí thấp. Nhưng với TF1, mục tiêu là xây một AIOps-ready incident platform có metadata nhất quán quanh workload.

Quyết định (Decision):

```text
Không chọn ECS làm nền tảng chính cho TF1 MVP.
Chọn EKS vì dự án được hưởng lợi nhiều hơn từ tính năng Kubernetes-native observability,
alerting, GitOps evidence, ranh giới bảo mật và tính nhất quán của siêu dữ liệu workload.
```

---

## 3.3 Tại sao EKS vẫn đóng vai trò quan trọng trong góc độ này

EKS phù hợp hơn không phải vì ECS không chạy được container. ECS hoàn toàn có thể chạy service ổn, rẻ hơn và đơn giản hơn trong nhiều trường hợp.

Điểm khác biệt là TF1 Triage Hub không chỉ cần một nơi để host container. TF1 Triage Hub cần một hệ sinh thái vận hành đủ mạnh để gom runtime state, observability data, alerting, deployment evidence, security boundary và tenant metadata về cùng một mô hình nhất quán cho incident triage.

EKS phù hợp hơn vì Kubernetes cung cấp một hệ sinh thái (ecosystem) thống nhất quanh workload:

```text
1. Hệ sinh thái runtime của workload (Workload runtime ecosystem)
   - Pod
   - Deployment
   - Service
   - Namespace
   - Labels (Nhãn)
   - Annotations
   - ReplicaSet / Trạng thái rollout

2. Hệ sinh thái giám sát (Observability ecosystem)
   - Prometheus
   - ServiceMonitor / PodMonitor
   - Loki
   - Grafana
   - Alertmanager
   - Các sự kiện Kubernetes (Kubernetes events)
   - Các nhãn ứng dụng/workload đi kèm với metrics và logs

3. Hệ sinh thái cảnh báo (Alerting ecosystem)
   - PrometheusRule
   - Alertmanager grouping
   - Inhibition (Ngăn chặn)
   - Silence (Tắt tiếng)
   - Repeat interval (Khoảng thời gian lặp lại)
   - Các nhãn cảnh báo như tenant_id, service, env, severity

4. Hệ sinh thái GitOps và minh chứng triển khai
   - Argo CD
   - Helm / Kustomize
   - Khác biệt triển khai (deployment diff)
   - Lịch sử rollout
   - Minh chứng rollback
   - Bản đồ Git commit / image version

5. Hệ sinh thái bảo mật và cô lập (Security and isolation)
   - Namespace
   - RBAC
   - ServiceAccount
   - IRSA / EKS Pod Identity
   - NetworkPolicy
   - Tích hợp Secret
   - Ranh giới truy cập cấp workload

6. Hệ sinh thái siêu dữ liệu nền tảng (Platform metadata ecosystem)
   - tenant_id
   - service
   - env
   - namespace
   - pod
   - deployment
   - version
   - owner (chủ sở hữu)
   - service_group
```

Các phần này không đứng rời rạc. Chúng xoay quanh cùng một Kubernetes workload model.

Ví dụ một service `checkout-api` có thể có siêu dữ liệu (metadata):

```text
tenant_id = tenant-a
service = checkout-api
env = prod
namespace = tenant-a-prod
deployment = checkout-api
pod = checkout-api-7c8d9f
version = v1.4.2
owner = checkout-team
service_group = checkout-stack
```

Metadata này có thể xuất hiện xuyên suốt trong:

```text
- Các nhãn Kubernetes Deployment
- Các nhãn Pod
- Các nhãn Prometheus metrics
- Các nhãn Loki log
- Các nhãn Alertmanager alert
- Lịch sử triển khai Argo CD
- Ranh giới NetworkPolicy/RBAC
- Trạng thái sự cố (incident_state) của CDO Correlator
- Hợp đồng truy vấn giới hạn của AI Engine
```

Khi alert `High5xx` xảy ra ở `checkout-api`, hệ thống không chỉ biết “service này lỗi”. Hệ thống có thể nối alert đó với:

```text
alert
→ tenant
→ environment
→ service
→ namespace
→ pod
→ deployment version
→ recent rollout
→ metrics window
→ logs window
→ related alerts (các cảnh báo liên quan)
→ incident trigger (kích hoạt sự cố)
```

Đây là điểm quan trọng cho AIOps/RCA. AI Engine cần query đúng metric/log theo tenant, service, env và time window. CDO cần đảm bảo dữ liệu đó có metadata nhất quán từ lúc workload chạy, sinh metric/log, tạo alert, đi qua correlator, rồi thành incident trigger.

Nếu dùng ECS, hệ thống vẫn làm được, nhưng context thường nằm rải ở nhiều nơi:

```text
- ECS task/service metadata
- CloudWatch metrics/logs
- Các sự kiện triển khai của EventBridge
- ALB target group
- Lịch sử pipeline CI/CD
- Các AWS resource tags
- Quy ước đặt tên tùy chỉnh
```

CDO sẽ phải viết thêm glue logic để nối các nguồn này thành một ngữ cảnh sự cố thống nhất. Với EKS, nhiều phần context đã nằm tự nhiên trong Kubernetes ecosystem thông qua namespace, labels, annotations, service discovery, rollout state và observability labels.

Vì vậy, lý do chọn EKS không phải là “EKS chạy container tốt hơn ECS”. Lý do là:

```text
EKS giúp CDO xây dựng một nền tảng vận hành sẵn sàng cho AIOps (AIOps-ready operational platform),
nơi runtime, observability, alerting, minh chứng GitOps, ranh giới bảo mật
và siêu dữ liệu sự cố dùng chung một mô hình workload.
```

---

## 3.4 Lợi thế về kiến trúc (Architectural advantages)

Không đưa ra các con số benchmark trong phần này. Bảng so sánh dưới đây dựa trên khả năng kiến trúc.

|Trục so sánh|Thiết kế đề xuất|Thiết kế cảnh báo trực tiếp đơn giản|
|---|---|---|
|Độ bền bỉ của cảnh báo (Alert durability)|Sự kiện cảnh báo được lưu trong SQS FIFO, có cơ chế retry và FIFO DLQ.|Cảnh báo có thể bị mất nếu dịch vụ hạ nguồn không khả dụng.|
|Xử lý bão cảnh báo (Alert storm handling)|Alertmanager + Correlator giảm nhiễu trước khi gọi AI.|Mỗi cảnh báo có thể kích hoạt cuộc gọi AI riêng lẻ.|
|Ngăn ngừa trùng lặp (Duplicate prevention)|DynamoDB lưu trữ fingerprint/state và ngăn chặn các tác động ngoài (side effects) bị trùng lặp.|Cơ chế thử lại (retry) có thể tạo ra các ticket Jira hoặc tin nhắn Slack trùng lặp.|
|Tương quan sự cố (Incident correlation)|Nhiều cảnh báo liên quan có thể được gom thành một sự cố duy nhất.|Mỗi cảnh báo có thể bị coi là một sự cố riêng lẻ.|
|Bảo vệ AI Engine (AI protection)|AI chỉ nhận trigger cấp sự cố khi thực sự cần thiết.|AI nhận toàn bộ lượng cảnh báo thô (spam).|
|Khả năng phục hồi (Recovery)|Worker thực hiện thử lại từ SQS FIFO và tái sử dụng trạng thái trong DynamoDB.|Cơ chế thử lại stateless có thể lặp lại các bước đã hoàn tất trước đó.|
|Debug/replay|SQS FIFO DLQ + S3 audit cung cấp minh chứng và tài liệu phục vụ replay.|Khó kiểm tra và replay các cảnh báo bị lỗi.|
|Giám sát vận hành (Ops visibility)|Có thể quan sát SQS FIFO backlog, FIFO DLQ, lỗi Lambda, lỗi DynamoDB và CloudWatch logs.|Khó xác định điểm lỗi trong luồng hơn.|
|Tính nhất quán của siêu dữ liệu|EKS cung cấp metadata nhất quán quanh namespace, pod, service, deployment, version, tenant_id, env.|ECS vẫn làm được nhưng cần nhiều custom glue giữa task metadata, CloudWatch, EventBridge, ALB, CI/CD và tags.|

---

## 3.5 Các điểm yếu được chấp nhận (Weakness accepted)

Thiết kế này phức tạp hơn thiết kế gửi webhook trực tiếp sang AI.

Nó bổ sung thêm:

```text
- Quản lý vận hành EKS cluster
- Cấu hình Alertmanager phức tạp hơn
- Ingest Lambda
- SQS FIFO + FIFO DLQ
- CDO Correlator Worker
- DynamoDB incident_state
- Kho lưu trữ audit trên S3
- Quyền hạn IAM/IRSA
- Giám sát CloudWatch cho các thành phần pipeline
```

Team chấp nhận trade-off này vì mục tiêu không chỉ là demo happy path. Mục tiêu là xây dựng một pipeline xử lý sự cố tin cậy có thể sống sót qua các lỗi, giảm thiểu bão cảnh báo, tránh trùng lặp Jira/Slack và cung cấp minh chứng kiểm toán rõ ràng.

Hạn chế của bản MVP (MVP limitation):

```text
Cơ chế tương quan dựa trên quy tắc cấu hình (rule-based).
Chưa hỗ trợ topology-aware (nhận biết sơ đồ kiến trúc), trace-aware hoặc có sự hỗ trợ của AI.
```

Cải tiến trong tương lai có thể thêm:

```text
- Đồ thị phụ thuộc dịch vụ (service dependency graph)
- Tương quan nhận biết topology (topology-aware correlation)
- Distributed tracing bằng OpenTelemetry
- Khung thời gian động (adaptive time windows)
- Tương quan có AI hỗ trợ (AI-assisted correlation)
- Vòng phản hồi từ con người (human feedback loop)
```

Kết luận cuối cùng (Final takeaway):

```text
Nếu mục tiêu chỉ là chạy container rẻ và đơn giản, ECS là lựa chọn tốt hơn.

Nếu mục tiêu là xây một nền tảng triage sự cố cần metadata nhất quán,
hệ thống giám sát đặt gần workload, minh chứng GitOps, tương quan cảnh báo,
truy cập truy vấn RCA có giới hạn và quy trình sự cố đáng tin cậy,
EKS + SQS FIFO + DynamoDB + Correlator là hướng đi phù hợp hơn.
```

---

# 4. Hướng tiếp cận Multi-tenant (Đa người thuê)

## 4.1 Mô hình Tenant

Trong bản MVP, multi-tenancy chủ yếu được xử lý thông qua siêu dữ liệu (metadata), không triển khai một vòng đời tenant SaaS đầy đủ.

Các metadata bắt buộc:

```text
tenant_id
service
env
namespace
workload
timestamp
alertname
severity
```

Ví dụ các Tenant ID cho bản demo:

```text
tenant-a
tenant-b
```

Môi trường production có thể sử dụng UUID v4, nhưng bản MVP không bao gồm quy trình đăng ký tenant (tenant onboarding) đầy đủ như thực tế.

---

## 4.2 Mô hình cô lập (Isolation pattern)

Cô lập dữ liệu sử dụng mô hình dùng chung tài nguyên (pooled model) phân tách bằng metadata.

```text
Prometheus labels bao gồm tenant_id, service, env.
Loki labels bao gồm tenant_id, service, env, namespace, pod.
Các key của DynamoDB bao gồm tenant_id, service, incident_id, và correlation_key.
S3 audit prefix bao gồm tenant_id/service/incident_id.
```

Cô lập tài nguyên tính toán (compute isolation) sử dụng chung một EKS cluster.

```text
Workload của các ứng dụng demo có thể được phân tách theo namespace.
Các thành phần pipeline CDO chạy trong namespace platform/ops.
AIOps/AI Engine có thể chạy trong namespace riêng hoặc một runtime bên ngoài.
```

Mô hình này phù hợp với phạm vi capstone vì mục tiêu chính là chứng minh khả năng xử lý cảnh báo tin cậy và tương quan sự cố, không phải triển khai cô lập tenant SaaS hoàn toàn với các tài khoản hoặc cluster riêng biệt cho mỗi tenant.

---

## 4.3 Truy cập có giới hạn cho AI Engine (Bounded access)

CDO không được cấp quyền truy cập không hạn chế cho AI Engine vào toàn bộ stack giám sát.

Quyền truy cập cần được giới hạn bởi:

```text
tenant_id
env
service hoặc service_group
Khung thời gian (time window)
Quyền chỉ đọc (read-only)
Đường truyền mạng nội bộ (internal network path)
```

Các cơ chế thực thi khả thi:

```text
- Cổng truy vấn/API nội bộ (internal query gateway/API)
- Service account hoặc token chỉ đọc
- Ranh giới namespace và NetworkPolicy
- Ranh giới IAM/RBAC nếu cần truy cập phía AWS
- Quy ước truy vấn bắt buộc có tenant_id/service/env/window
- Lưu log kiểm toán (audit logging) cho các truy vấn của AI
- Định rõ prefix S3 giới hạn nếu AI ghi các artifact RCA
```

Lưu ý quan trọng:

```text
Chỉ các nhãn của Prometheus/Loki thì chưa đủ để tạo sự cô lập tenant mạnh mẽ.
Đối với bản MVP, chúng được chấp nhận dưới dạng phân vùng dựa trên metadata.
Đối với môi trường production, cần bổ sung một cổng truy vấn hoặc một lớp kiểm soát truy cập mạnh mẽ hơn.
```

---

## 4.4 Luồng đăng ký tenant mới (Tenant onboarding flow)

Quy trình đăng ký trên bản MVP:

```text
1. Tạo tenant_id hoặc nhãn dịch vụ (service label) trong cấu hình.
2. Gắn tenant_id/service/env vào các nhãn metric, log và alert.
3. Tạo namespace nếu cần phân tách workload.
4. Cấu hình Alertmanager gom nhóm theo tenant/env/service/severity.
5. Xác minh payload cảnh báo có đầy đủ metadata bắt buộc.
6. Xác minh AI Engine có thể truy vấn dữ liệu giới hạn theo tenant/service/env/window.
7. Xác minh các key DynamoDB và prefix S3 đã chứa định danh tenant/service/incident.
```

Quy trình đăng ký trên môi trường production tương lai:

```text
POST /platform/v1/tenants
→ Terraform/Step Function khởi tạo namespace/config/IAM
→ Tạo các nhãn giám sát giới hạn theo tenant (tenant-scoped)
→ Tạo prefix S3 và access policy giới hạn theo tenant
→ Tạo secret và access policy
→ Chạy smoke test (kiểm tra nhanh)
→ Gọi lại (callback) thông báo tenant đã sẵn sàng
```

Không tuyên bố quy trình vòng đời đầy đủ này đã được triển khai trong MVP trừ khi nó thực sự được xây dựng.

---

## 4.5 Giảm thiểu ảnh hưởng từ các tenant khác (Noisy neighbor mitigation)

Các biện pháp kiểm soát trên MVP:

```text
- Cấu hình ResourceQuota và LimitRange cho mỗi namespace nếu mô phỏng nhiều tenant
- Cơ chế gom nhóm của Alertmanager để giảm thiểu spam cảnh báo trước khi tới Lambda/SQS FIFO
- Giám sát độ dài hàng đợi SQS FIFO để phát hiện lượng cảnh báo tăng đột biến
- Gating tại Correlator để tránh các cuộc gọi AI lặp lại liên tục
- Giới hạn các câu truy vấn giám sát theo tenant/service/env/time window
- Sử dụng key idempotency trên DynamoDB để ngăn các tác động ngoài bị trùng lặp
- Tổ chức các prefix trên S3 theo tenant/service/incident để quản lý các artifact
```

Tránh đưa ra các ngưỡng số lượng cụ thể trừ khi đã được đo đạc thực tế.

---

# 5. Các quyết định thiết kế chính / Các giải pháp thay thế được cân nhắc

## 5.1 Tại sao chọn Amazon EKS?

Các giải pháp thay thế:

```text
Lựa chọn A: Lambda + API Gateway
Lựa chọn B: ECS Fargate + ALB
Lựa chọn C: Amazon EKS
```

Lambda rất tốt cho việc xử lý các sự kiện ngắn hạn, nhưng TF1 không chỉ là một API hoặc một bộ xử lý sự kiện đơn giản. Nền tảng cần chạy các workload demo, các quy trình worker chạy ngầm, stack giám sát, Alertmanager, Grafana, Loki, Prometheus và siêu dữ liệu kiểu Kubernetes bao quanh các workload.

Lambda vẫn được sử dụng, nhưng chỉ đóng vai trò tiếp nhận cảnh báo nhẹ nhàng và các thành phần tích hợp.

ECS có thể chạy tốt các container, thường đơn giản và rẻ hơn EKS. Tuy nhiên, dự án này được hưởng lợi rất nhiều từ các khái niệm native của Kubernetes:

```text
- namespace
- labels
- annotations
- service discovery
- NetworkPolicy
- GitOps
- metadata của đợt rollout
- định danh pod/deployment
- giám sát đặt gần workload
```

EKS cung cấp một mô hình metadata nhất quán xoay quanh:

```text
tenant_id
service
env
namespace
pod
deployment
version
```

Metadata này có thể được sử dụng xuyên suốt trên runtime, metrics, logs, cảnh báo, lịch sử triển khai và quyền truy cập truy vấn giới hạn cho AIOps.

Quyết định (Decision):

```text
Chọn EKS vì TF1 là một nền tảng triage sự cố sẵn sàng cho AIOps,
không đơn thuần chỉ là bài toán chạy container giá rẻ.
```

---

## 5.2 Tại sao chọn AWS Load Balancer Controller + ALB?

Các giải pháp thay thế:

```text
Lựa chọn A: NodePort
Lựa chọn B: Chỉ dùng NGINX Ingress
Lựa chọn C: API Gateway
Lựa chọn D: AWS Load Balancer Controller + ALB
```

Ứng dụng demo và các cổng vào API khả thi chạy bên trong EKS. AWS Load Balancer Controller cho phép Kubernetes Ingress tự động quản lý ALB.

Lợi ích:

```text
- Quản lý ingress theo phong cách Kubernetes-native
- Không cần cấu hình thủ công ALB/target group
- Hoạt động tự nhiên với cơ chế phát hiện dịch vụ của EKS
- Hỗ trợ định tuyến dựa trên đường dẫn (path-based) và host (host-based)
- Phù hợp với luồng GitOps vì cấu hình ingress nằm trong các manifest Kubernetes
```

API Gateway rất hữu ích cho việc quản lý xác thực/giới hạn tốc độ của API, nhưng bản MVP này chủ yếu đóng vai trò mở ra các workload dạng container bên trong EKS. ALB đơn giản và tự nhiên hơn cho HTTP ingress vào workload Kubernetes.

Quyết định (Decision):

```text
Sử dụng ALB + AWS Load Balancer Controller cho các kết nối công cộng vào EKS.
```

---

## 5.3 Tại sao dùng Ingest Lambda trước SQS FIFO?

Các giải pháp thay thế:

```text
Lựa chọn A: Alertmanager gửi trực tiếp tới SQS FIFO
Lựa chọn B: Alertmanager gửi trực tiếp tới Worker/API
Lựa chọn C: Alertmanager gửi tới Ingest Lambda, sau đó Lambda gửi tới SQS FIFO
```

Payload webhook của Alertmanager có thể cần được xác thực và chuẩn hóa trước khi trở thành một sự kiện cảnh báo nội bộ.

Ingest Lambda thực hiện:

```text
- Nhận webhook
- Xác thực các trường bắt buộc
- Chuẩn hóa payload
- Gắn thêm siêu dữ liệu tenant/service/env/window
- Tạo key idempotency hoặc các trường tương quan nếu cần
- Tùy chọn lưu trữ payload cảnh báo thô/chuẩn hóa vào S3
- Tùy chọn ghi trạng thái tiếp nhận và hàng đợi vào DynamoDB
- Gửi tin nhắn tới SQS FIFO
```

Nhiệm vụ của nó được thiết kế cố ý rất nhẹ nhàng.

Nó không thực hiện:

```text
- Phân tích RCA
- Truy vấn sâu vào metrics/logs
- Tương quan sự cố
- Gọi AI Engine để phân tích RCA
- Tạo Jira/Slack
```

Quyết định (Decision):

```text
Sử dụng Ingest Lambda như một bộ chuyển đổi mỏng giữa webhook Alertmanager và SQS FIFO.
```

---

## 5.4 Tại sao chọn SQS FIFO + FIFO DLQ?

Các giải pháp thay thế:

```text
Lựa chọn A: Gửi webhook trực tiếp đến AI Engine
Lựa chọn B: Chỉ sử dụng cơ chế thử lại của Lambda
Lựa chọn C: Sử dụng SQS FIFO + FIFO DLQ
```

Sự kiện cảnh báo là trigger kích hoạt sự cố cực kỳ quan trọng. Nếu cảnh báo bị mất, quy trình xử lý sự cố có thể không bao giờ được bắt đầu.

SQS FIFO cung cấp:

```text
- Bộ đệm cảnh báo bền vững
- Thử lại thông qua thời gian ẩn tin nhắn (visibility timeout)
- FIFO DLQ cho các tin nhắn độc (poison messages)
- Giám sát lượng tin nhắn tích lũy (backlog visibility)
- Phân tách giữa hệ thống giám sát và xử lý hạ nguồn
- Khả năng replay/debug khi cần
```

Lambda retry chỉ bảo vệ việc thực thi hàm trong một số trường hợp. SQS FIFO bảo vệ toàn bộ vòng đời của sự kiện sự cố một cách rõ ràng hơn.

SQS FIFO là phân phát ít nhất một lần (at-least-once delivery), do đó việc xử lý trùng lặp vẫn có thể xảy ra. Do đó DynamoDB là cần thiết để đảm bảo tính idempotency và lưu trữ trạng thái workflow.

Quyết định (Decision):

```text
Sử dụng SQS FIFO cho các sự kiện cảnh báo.
Không sử dụng SQS FIFO cho dữ liệu thô metric/log.
```

---

## 5.5 Tại sao chọn DynamoDB cho incident_state?

Các giải pháp thay thế:

```text
Lựa chọn A: Không sử dụng database
Lựa chọn B: Sử dụng RDS/Aurora
Lựa chọn C: Sử dụng DynamoDB
```

Việc lưu trữ trạng thái là cần thiết vì quy trình xử lý có cơ chế thử lại và các tác động ngoài lên hệ thống bên thứ ba.

Ví dụ:

```text
Worker nhận cảnh báo
→ Hoàn thành AI RCA
→ Integration Lambda tạo thành công ticket Jira
→ Integration Lambda bị sập trước khi gửi tin Slack
→ Cơ chế thử lại kích hoạt
```

Nếu không lưu trạng thái, hệ thống có thể tạo trùng lặp ticket Jira hoặc tin nhắn Slack.

DynamoDB lưu trữ trạng thái workflow nhỏ gọn:

```text
- incident_id
- correlation_key
- alert_fingerprint
- status
- current_step
- retry_count
- last_error
- jira_ticket_id
- slack_thread_id
- Các con trỏ S3 URI
- created_at
- updated_at
```

Quyết định (Decision):

```text
Sử dụng DynamoDB làm kho lưu trạng thái sự cố, kho lưu idempotency, kho lưu tiến trình workflow và lưu trữ chỉ mục con trỏ tới các artifact trên S3.
```

---

## 5.6 Tại sao chọn S3 Audit Store?

Các giải pháp thay thế:

```text
Lựa chọn A: Lưu trữ tất cả trong DynamoDB
Lựa chọn B: Lưu trữ các minh chứng kiểm toán trong S3
```

DynamoDB nên được sử dụng để lưu trữ trạng thái hiện tại, không nên lưu các đối tượng minh chứng có kích thước lớn.

S3 có thể lưu trữ:

```text
- Payload cảnh báo gốc
- Payload cảnh báo đã chuẩn hóa
- Payload cảnh báo đã gom nhóm
- Trigger sự cố gửi tới AI
- Yêu cầu gửi tới AI (AI request)
- Phản hồi từ AI (AI response)
- Ngữ cảnh AI đã sử dụng
- Minh chứng AI đã sử dụng
- Báo cáo RCA
- Yêu cầu/phản hồi Jira
- Yêu cầu/phản hồi Slack
- Tài liệu phục vụ replay/debug
```

Điều này giúp trả lời các câu hỏi:

```text
Hệ thống đã nhận được những gì?
AI đã nhận được thông tin gì?
AI đã sử dụng ngữ cảnh và minh chứng nào?
Chúng ta có thể replay/debug sự cố này không?
Thông tin chính xác nào đã được gửi tới Jira/Slack?
```

Quyết định (Decision):

```text
Sử dụng DynamoDB cho trạng thái hiện tại và các con trỏ S3.
Sử dụng S3 để lưu trữ chi tiết minh chứng kiểm toán và tài liệu phục vụ replay.
```

---

## 5.7 Tại sao chia tách Prometheus/Loki + CloudWatch?

CloudWatch rất mạnh đối với các dịch vụ được quản lý của AWS, nhưng các metric/log của workload Kubernetes sẽ dễ xử lý hơn nhiều thông qua các nhãn native của Kubernetes.

Prometheus/Loki phù hợp với các workload trên EKS vì chúng có thể sử dụng các nhãn như:

```text
namespace
pod
container
service
tenant_id
env
```

CloudWatch vẫn cần thiết cho các dịch vụ phía AWS:

```text
- Log/lỗi/thời gian chạy của Lambda
- Metric hàng đợi tích lũy và FIFO DLQ của SQS
- Các lỗi/nghẽn của DynamoDB
- Các metric yêu cầu/lỗi của S3 nếu được bật
- Log tích hợp phía AWS
```

Quyết định (Decision):

```text
Prometheus = metrics ứng dụng/EKS.
Loki = logs ứng dụng/EKS.
Grafana = giao diện dashboard/điều tra sự cố.
CloudWatch = giám sát các thành phần pipeline phía AWS.
S3 = kho lưu trữ audit/minh chứng.
```

---

## 5.8 Tại sao dùng Alertmanager + CDO Correlator thay vì chỉ dùng Alertmanager?

Alertmanager tốt cho việc kiểm soát nhiễu cơ bản:

```text
- gom nhóm (grouping)
- ngăn chặn (inhibition)
- tắt tiếng (silence)
- khoảng thời gian lặp lại (repeat interval)
```

Nhưng Alertmanager không hiểu đầy đủ về:

```text
- trạng thái workflow sự cố
- các tác động ngoài của Jira/Slack
- cổng hạn chế gọi AI (AI call gating)
- tương quan sự cố chéo dịch vụ
- các con trỏ artifact trên S3
- trạng thái replay
```

CDO Correlator xử lý:

```text
- alert_fingerprint
- correlation_key
- incident_state
- quyết định gọi AI
- ngăn ngừa trùng lặp
- khôi phục/tiếp tục workflow
- theo dõi artifact trên S3
```

Quyết định (Decision):

```text
Sử dụng Alertmanager làm lớp kiểm soát nhiễu Layer 1.
Sử dụng CDO Correlator + DynamoDB làm lớp tương quan sự cố và kiểm soát tính idempotency Layer 2.
```

---

# 6. Chiến lược mở rộng (Scaling strategy)

## 6.1 Mở rộng theo chiều dọc (Vertical scaling)

Tăng cấu hình instance type của EKS nodes, Prometheus hoặc CPU/memory của Loki khi gặp nghẽn cổ chai.

Sử dụng phương pháp này khi một thành phần bị giới hạn tài nguyên nhưng không gặp phải nghẽn cổ chai khi mở rộng theo chiều ngang.

---

## 6.2 Mở rộng theo chiều ngang (Horizontal scaling)

Tăng số lượng instance:

```text
Demo App:
- theo mức sử dụng CPU/RAM hoặc traffic yêu cầu

CDO Correlator Worker:
- theo số lượng tin nhắn hiển thị trong SQS FIFO
- theo thời gian tồn tại của tin nhắn lâu nhất (age of oldest message)
- theo tỷ lệ lỗi của worker

Integration Lambda:
- tự động mở rộng theo khối lượng cuộc gọi (invocation volume)
- vẫn cần bảo vệ Jira/Slack bằng cơ chế retry và logic giới hạn tốc độ (rate-limit)

Observability stack:
- bắt đầu với cấu hình kích thước của bản MVP
- tăng số lượng bản sao (replicas)/dung lượng lưu trữ nếu thực sự cần thiết

AI Engine:
- thuộc sở hữu của đội AIOps
- CDO bảo vệ nó bằng cách giảm các cuộc gọi lặp lại
```

Đối với bản MVP, cấu hình số lượng bản sao cố định là chấp nhận được. HPA/KEDA có thể được bổ sung nếu có đủ thời gian triển khai.

---

## 6.3 Các trigger kích hoạt mở rộng (Scaling triggers)

Các trigger được đề xuất:

```text
- Mức sử dụng CPU
- Mức sử dụng bộ nhớ (memory)
- Chỉ số SQS FIFO ApproximateNumberOfMessagesVisible
- Chỉ số SQS FIFO ApproximateAgeOfOldestMessage
- Tỷ lệ lỗi của worker
- Tỷ lệ lỗi của Lambda
- Tỷ lệ lỗi/nghẽn của DynamoDB
- Tỷ lệ lỗi đẩy/đọc (put/read) của S3
- Độ trễ/tỷ lệ lỗi của AI Engine
- Tỷ lệ lỗi tích hợp Jira/Slack
```

Tránh đưa ra các ngưỡng cụ thể trừ khi đã được đo lường thực tế.

---

## 6.4 Kiểm soát cuộc gọi AI (AI call control)

Correlator không được gọi AI đối với mọi cảnh báo.

Chỉ gọi AI khi:

```text
- Một sự cố mới được tạo
- Độ nghiêm trọng (severity) tăng lên
- Xuất hiện loại cảnh báo quan trọng mới
- Sự cố kéo dài quá một khoảng thời gian ngưỡng nhất định
- Độ tin cậy RCA trước đó thấp
- Con người yêu cầu phân tích lại (re-analysis)
```

Bỏ qua cuộc gọi AI khi:

```text
- Cảnh báo bị trùng lặp
- Cảnh báo thuộc về một sự cố đang tồn tại
- Chỉ có chỉ số alert_count hoặc last_seen_at thay đổi
- Tin nhắn chỉ là một lượt thử lại (retry) từ SQS FIFO
```

Cơ chế này bảo vệ chi phí sử dụng AI và tránh lặp lại phân tích RCA vô ích.

---

## 7. Các kịch bản lỗi + Phục hồi (Failure modes + recovery)

| Kịch bản lỗi | Phát hiện | Phục hồi | RTO/RPO |
|---|---|---|---|
|Demo app pod bị sập|Sự kiện Kubernetes, Prometheus báo target down|Kubernetes tự động khởi động lại hoặc lên lịch chạy lại pod|RTO: <1 phút / RPO: 0 (ứng dụng stateless)|
|Prometheus không khả dụng|Kiểm tra sức khỏe Grafana/Prometheus, lỗi thu thập (scrape)|Khởi động lại pod, khôi phục cấu hình/lưu trữ nếu cần|RTO: <5 phút / RPO: Mất dữ liệu metric trong thời gian gặp lỗi|
|Loki không khả dụng|Lỗi Grafana Explore, kiểm tra sức khỏe Loki pod|Khởi động lại Loki/agent, kiểm tra dung lượng lưu trữ|RTO: <5 phút / RPO: Mất dữ liệu log trong thời gian gặp lỗi|
|Cơn bão cảnh báo (Alert storm)|Lượng cảnh báo tăng đột biến, Dashboard Alertmanager, SQS FIFO backlog|Cơ chế gom nhóm/ngăn chặn của Alertmanager + Gating của Correlator|RTO: N/A (bị hạn chế tốc độ) / RPO: 0 (các sự kiện được đệm an toàn trong SQS FIFO)|
|Ingest Lambda gặp lỗi|Lỗi Lambda/thời gian chạy trên CloudWatch|Sửa schema/cấu hình và replay lại nếu nguồn phát hỗ trợ thử lại|RTO: <5 phút (tự động) / RPO: Có thể mất cảnh báo nếu nguồn phát không thử lại|
|SQS FIFO tích lũy cao|Chỉ số tin nhắn hiển thị/tuổi tin nhắn trên CloudWatch|Mở rộng quy mô worker, điều tra độ trễ/lỗi ở hạ nguồn|RTO: <10 phút (mở rộng) / RPO: 0 (tin nhắn được giữ lại trong hàng đợi)|
|Worker bị sập|Pod khởi động lại, worker logs, tin nhắn hiển thị lại trên SQS|SQS thử lại tin nhắn; worker tiếp tục xử lý sử dụng trạng thái trong DynamoDB|RTO: <2 phút / RPO: 0 (trạng thái lưu trong DynamoDB)|
|Cảnh báo trùng lặp|Trùng alert_fingerprint|Cập nhật chỉ số count/last_seen_at, bỏ qua việc tạo sự cố mới|RTO: 0 / RPO: 0|
|Cảnh báo liên quan|Trùng correlation_key|Gắn thêm vào sự cố đang tồn tại và cập nhật trạng thái|RTO: 0 / RPO: 0|
|AI Engine trả về mã lỗi 400 (Yêu cầu lỗi / Sai lệch Tenant)|Mã phản hồi HTTP 400 từ endpoint `/v1/triage`|CDO Worker ghi nhận lỗi vào log, đánh dấu trạng thái FAILED_INVALID trong DynamoDB, dừng thử lại để ngăn lặp lỗi, cảnh báo cho người vận hành|RTO: N/A / RPO: 0|
|AI Engine trả về mã lỗi 401 (Lỗi xác thực)|Mã phản hồi HTTP 401 từ endpoint `/v1/triage`|CDO Worker lấy lại thông tin xác thực/token mới từ Secrets Manager, thử lại một lần. Nếu vẫn lỗi, đánh dấu trạng thái AUTH_FAILED|RTO: <2 phút / RPO: 0|
|AI Engine trả về mã lỗi 429 (Giới hạn tốc độ)|Mã phản hồi HTTP 429 từ endpoint `/v1/triage`|CDO Worker gửi lại tin nhắn về SQS FIFO, thực hiện thử lại với exponential backoff|RTO: <10 phút / RPO: 0|
|AI Engine trả về mã lỗi 500 (Lỗi hệ thống không xác định)|Mã phản hồi HTTP 500 từ endpoint `/v1/triage`|CDO Worker sử dụng cơ chế fallback dựa trên luật local, tạo ticket fallback với ngữ cảnh cảnh báo thô, đánh dấu sự cố DIAGNOSED_FALLBACK|RTO: <5 phút / RPO: 0|
|AI Engine trả về mã lỗi 503 / Timeout (AI không khả dụng)|Mã phản hồi HTTP 503 hoặc timeout kết nối|Thử lại qua SQS FIFO. Nếu thời gian sập vượt quá giới hạn timeout, chuyển hướng fallback sang cơ chế triage dựa trên luật để tránh tắc nghẽn pipeline|RTO: <10 phút / RPO: 0|
|AI Engine ghi lỗi lên S3|Lỗi từ AI, thiếu URI artifact|AI tự thử lại hoặc trả artifact về cho Worker để lưu trữ hộ|RTO: <5 phút / RPO: Minh chứng kiểm toán không đầy đủ|
|Jira được tạo thành công nhưng Integration Lambda bị sập trước khi gửi tin Slack|DynamoDB đã ghi nhận jira_ticket_id và current_step|Khi thử lại, bỏ qua bước tạo Jira và tiếp tục thực hiện bước gửi tin Slack|RTO: <5 phút / RPO: 0|
|Lỗi gửi Slack|Lỗi Integration Lambda và ghi last_error trong DynamoDB|Thử lại cập nhật Slack bằng trạng thái sự cố hiện tại|RTO: <5 phút / RPO: 0|
|DynamoDB bị nghẽn/lỗi|Các metric của DynamoDB trên CloudWatch|Thử lại với cơ chế backoff; điều chỉnh lại capacity/on-demand|RTO: <5 phút (backoff) / RPO: 0|
|Ghi file lên S3 thất bại|Log của Worker/Lambda, lỗi trên CloudWatch|Thử lại việc ghi log kiểm toán; duy trì trạng thái tối giản trong DynamoDB|RTO: <5 phút / RPO: Minh chứng kiểm toán không đầy đủ|
|Hàng đợi FIFO DLQ xuất hiện tin nhắn|Số lượng tin nhắn trên DLQ ở CloudWatch|Điều tra lỗi, sửa bug và thực hiện replay thủ công các tin nhắn bị lỗi|RTO: Thủ công / RPO: 0 (thời gian giữ tin nhắn 14 ngày)|
|Lỗi ghi log CloudWatch|Mất log/dữ liệu metric không được đẩy lên|Kiểm tra log group/retention/quyền hạn IAM|RTO: <15 phút / RPO: Mất dữ liệu log|
|Lỗi node/Availability Zone (AZ)|Các sự kiện node của EKS, pod được lên lịch lại|Sử dụng nhóm node Multi-AZ nếu được cấu hình|RTO: <5 phút / RPO: 0 (Nhờ các dịch vụ được AWS quản lý)|
|Sập toàn bộ Region AWS|Giám sát bên ngoài/phát hiện thủ công|Nằm ngoài phạm vi của MVP; kế hoạch DR trong tương lai|RTO: TBD / RPO: TBD (Nằm ngoài phạm vi MVP)|

---

# 8. Ghi chú bảo mật và quyền truy cập

- **Bảo mật mạng**: Các worker node EKS chạy trong subnet riêng tư; các kết nối công cộng được giới hạn thông qua ALB. Các NetworkPolicies trong namespace ngăn chặn các luồng traffic trái phép giữa các pod.
- **Kiểm soát truy cập**: IRSA cấp cho các pod quyền truy cập tối thiểu IAM để giao tiếp với SQS FIFO, DynamoDB, S3 và Secrets Manager.
- **Bảo vệ dữ liệu**: Các S3 audit buckets sử dụng mã hóa KMS và bucket policies. Các truy vấn giám sát của AI Engine chỉ có quyền đọc (read-only) và được giới hạn phạm vi nghiêm ngặt theo tenant, service và khung thời gian.

# 9. Phạm vi bản MVP (MVP scope)

- **Bao gồm**: Nền tảng runtime EKS, ALB ingress, stack Prometheus/Loki/Grafana, Ingest Lambda, hàng đợi cảnh báo SQS FIFO, CDO Correlator, trạng thái sự cố trên DynamoDB, kho lưu trữ audit S3 và tích hợp Jira/Slack.
- **Không bao gồm**: Quy trình tự động quản lý vòng đời đăng ký tenant SaaS, tương quan nhận biết topology dựa trên trace và khả năng tự động khắc phục sự cố (auto-remediation).

# 10. Các cải tiến trong tương lai (Future improvements)

- **Đồ thị phụ thuộc (Dependency Graph)**: Lưu trữ cấu trúc sơ đồ dịch vụ (service topology) để nâng cao chất lượng tương quan cảnh báo cascading.
- **OTel Tracing**: Bổ sung distributed tracing thông qua OpenTelemetry Collector và Tempo hoặc AWS X-Ray.
- **Tương quan có AI hỗ trợ**: Cho phép AI đề xuất mối liên hệ giữa các cảnh báo dưới các hàng rào bảo vệ (guardrails) dựa trên quy tắc tĩnh.

# 11. Kết luận cuối cùng (Final takeaway)

CDO xây dựng môi trường chạy ứng dụng EKS, pipeline cảnh báo và hệ thống lưu trữ trạng thái. AI Engine truy vấn dữ liệu telemetry trong phạm vi giới hạn để chạy RCA. Sự phân chia trách nhiệm rõ ràng này bảo vệ AI Engine khỏi các gánh nặng xử lý trong cơn bão cảnh báo trong khi vẫn cung cấp đầy đủ ngữ cảnh để tiến hành phân loại sự cố.

# Các tài liệu liên quan (Related documents)

- `01_requirements_analysis.md` — giải thích vấn đề, các yêu cầu phi chức năng (NFRs) và lý do CDO chọn hướng đi tập trung vào EKS/K8s.
    
- `03_security_design.md` — mở rộng chi tiết về IAM, RBAC, NetworkPolicy, Secrets Manager, mã hóa và bảo mật kiểm toán.
    
- `04_deployment_design.md` — mô tả Terraform, GitOps, CI/CD, chiến lược rollout, rollback và môi trường.
    
- `05_cost_analysis.md` — ước tính chi phí cho EKS, ALB, SQS FIFO, DynamoDB, S3, CloudWatch và thời gian giữ lại dữ liệu giám sát.
    
- `07_test_eval_report.md` — ghi lại kết quả kiểm thử tải, kiểm thử lỗi, kiểm thử bão cảnh báo, kiểm thử FIFO DLQ và minh chứng phục hồi.
    
- `08_adrs.md` — lưu trữ các quyết định thiết kế cốt lõi như chọn EKS thay vì ECS, SQS FIFO cho sự kiện cảnh báo, DynamoDB cho idempotency và S3 cho kiểm toán.
