# AI Themes 1.0.0

Bộ giao diện dùng chung cho các dự án trong `D:/project`. Nguồn chuẩn nằm tại
`ai.atelier/themes`; thư mục `themes` trong mỗi dự án là một bản sao đã ghim
phiên bản. Ứng dụng chỉ dùng tài nguyên cục bộ và không cần đọc dữ liệu từ dự án
khác khi chạy.

## Cấu hình

Tệp `project.json` chọn bốn thuộc tính độc lập:

| Thuộc tính | Giá trị hỗ trợ |
|---|---|
| `theme` | `neutral`, `story`, `paper` |
| `mode` | `system`, `light`, `dark` |
| `style` | `minimal`, `soft`, `editorial` |
| `density` | `comfortable`, `compact` |

Token màu nguồn nằm trong `tokens.json`. Component chỉ nên dùng biến semantic
`--ui-*`; không đưa màu của nội dung ảnh, video, phụ đề hoặc màu nhận diện nghiệp
vụ vào theme.

Trên web, nút tròn **Giao diện** nằm ở góc phải dưới và lưu lựa chọn riêng cho
từng ứng dụng trong trình duyệt. Chế độ `system` tự cập nhật theo hệ điều hành.
Streamlit đặt nhóm **Giao diện** trong sidebar và lưu thiết lập theo phiên.

Ứng dụng Windows hoặc Gradio đọc cấu hình mặc định, đồng thời chấp nhận các biến
môi trường `AI_THEME`, `AI_THEME_MODE`, `AI_THEME_STYLE` và
`AI_THEME_DENSITY` khi khởi động. Android dùng bảng màu Neutral sáng/tối theo hệ
thống; Telegram giữ bộ chọn chế độ hiện có.

## Tích hợp vào ứng dụng web

Sao chép `dist/theme.css` và `dist/theme.js` vào thư mục tài nguyên tĩnh của ứng
dụng. Nạp JavaScript trong `head` trước nội dung để khôi phục lựa chọn trước lần
vẽ đầu tiên, sau đó nạp stylesheet của theme sau CSS riêng của ứng dụng.

```html
<html data-theme="neutral" data-mode="system" data-style="minimal"
      data-density="comfortable" data-theme-app="my-project">
  <head>
    <script src="/ai-theme.js"></script>
    <link rel="stylesheet" href="/ai-theme.css">
  </head>
  <body class="ui-scope">
    <button class="ui-button ui-primary">Lưu</button>
  </body>
</html>
```

Các lớp component dùng chung gồm `.ui-input`, `.ui-select`, `.ui-textarea`,
`.ui-card`, `.ui-table`, `.ui-feedback`, `.ui-tabs` và `.ui-actions`. Ứng dụng
vẫn chịu trách nhiệm xử lý bàn phím và trạng thái ARIA cho tab. Bộ chọn giao diện
dùng dialog gốc của trình duyệt.

Font mặc định là font hệ thống có hỗ trợ tiếng Việt. Style `editorial` dùng serif
cho tiêu đề; mật độ, khoảng cách và bán kính bo góc thay đổi độc lập với palette
màu.

## Phát triển và triển khai

Chạy các lệnh sau tại repository AI Atelier:

```powershell
.venv-ai/Scripts/python.exe themes/tools/build.py
.venv-ai/Scripts/python.exe themes/tools/deploy.py
.venv-ai/Scripts/python.exe themes/tools/verify.py
node themes/tools/theme.test.js
```

- `build.py` sinh CSS từ token nguồn.
- `deploy.py` đồng bộ bản ghim và tài nguyên runtime, đồng thời cập nhật các điểm
  nạp đã biết.
- `verify.py` kiểm tra kết quả triển khai.

Trước khi thay đổi tệp nguồn, công cụ tạo bản sao trong `.theme-backups/` của
từng dự án. Manifest tại `themes/deployment/` ghi đường dẫn và checksum; chạy lại
không sửa những tệp đã có cùng nội dung.

Hoàn tác một lần triển khai bằng manifest tương ứng:

```powershell
.venv-ai/Scripts/python.exe themes/tools/deploy.py --rollback themes/deployment/TIMESTAMP.json
```

Rollback sẽ dừng nếu tệp đã được chỉnh sau lần triển khai, nhờ đó không ghi đè
thay đổi mới của người dùng. Các package đã build và tiến trình đang chạy cần
được tạo lại hoặc khởi động lại để nhận theme mới.

Lần triển khai đầu tiên có manifest tổng hợp tại
`deployment/initial-rollout.json`. Kết quả xác minh và các giới hạn đã biết nằm
trong `verification/results.json`; ảnh mẫu nằm tại
`verification/preview.png`.

## Bộ chuyển đổi theo nền tảng

| Dự án | Điểm tích hợp |
|---|---|
| `ai.atelier` | Web, ánh xạ token và palette cũ |
| `ai.studio` | Web, ánh xạ biến và danh sách tài nguyên máy chủ |
| `watermarks-remover` | Web, ánh xạ biến và tuyến tài nguyên |
| `ai.slide`, `ai.story` | Studio và cửa sổ Audio/Video Streamlit |
| `ai.player` | QSS, giữ bố cục và thay bảng màu của cửa sổ chính |
| `ai.meeting`, `ai.player.android` | Resource màu giữ ID cũ và `values-night` |
| `ai.telegram.android` | Material 3 `ColorScheme`, giữ bộ chọn sáng/tối |
| `VieNeu-TTS` | Gradio CPU/CUDA, XPU và giao diện streaming FastAPI |
| `sd.webui` | Extension `ai-shared-themes`; không sửa mã upstream |

CSS component đầy đủ dành cho web. Adapter native chỉ ánh xạ những khả năng mà
nền tảng hỗ trợ; Android hiện chưa có bộ chọn ba style và hai mức density. QSS
tiếp tục giữ các quy tắc bố cục riêng. Khi thêm màn hình mới, hãy dùng semantic
token để không phải mở rộng lớp tương thích màu cũ.
