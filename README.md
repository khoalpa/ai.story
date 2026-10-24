# AI Audio & Video Studio

Bộ công cụ Python để kiểm tra gói truyện, dựng lời thoại và ghép video trong một
quy trình thống nhất. Dự án cung cấp ba ứng dụng có thể cài và chạy độc lập:

- **Audio** chuyển kịch bản văn bản hoặc JSON chuẩn thành giọng đọc, phụ đề, báo
  cáo chất lượng và manifest bàn giao cho Video.
- **Video** ghép audio, phụ đề và ảnh do người dùng cung cấp thành MP4 đã được
  kiểm tra đầu ra.
- **Studio** tập hợp các luồng Audio, Video và Story Studio trong một giao diện
  Streamlit duy nhất.

Dự án **không sinh nội dung truyện hoặc hình ảnh**. Bạn có thể tạo kịch bản và
tài nguyên hình ảnh bằng bất kỳ công cụ nào, sau đó đưa chúng vào quy trình này.

## Yêu cầu

- Python 3.10, 3.11 hoặc 3.12
- FFmpeg và FFprobe có trong `PATH`
- Windows, Linux hoặc môi trường tương thích với các phụ thuộc Python của dự án

Các mô hình Audio dung lượng lớn nên được lưu ngoài repository. Đặt biến môi
trường `AI_AUDIO_MODELS_ROOT` để chỉ đến thư mục mô hình; xem
[Tài nguyên bên ngoài](docs/EXTERNAL_ASSETS.md) để biết thêm chi tiết.

## Cài đặt

Tạo và kích hoạt môi trường ảo, sau đó cài các phụ thuộc và package chính:

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

Nếu phát triển hoặc chạy bộ kiểm tra, cài thêm công cụ dành cho lập trình viên:

```bash
python -m pip install -r requirements-dev.txt
```

Repository cũng định nghĩa ba wheel độc lập tại `packages/audio`,
`packages/video` và `packages/studio`.

## Khởi động

Trên Windows, cách nhanh nhất để mở Studio là:

```powershell
.\open_app.bat
```

Script này kiểm tra phiên bản Python và Streamlit trước khi khởi động. Sau khi
cài package, bạn cũng có thể dùng các entry point sau:

```bash
render-audio --help
render-audio-gui
render-video --help
render-video-gui
ai-studio-gui
ai-story-audit --help
```

Giao diện Studio gồm bốn không gian làm việc: **Overview**, **Audio**,
**Video** và **Story Studio**.

## Quy trình cơ bản

1. Chuẩn bị kịch bản ở dạng văn bản thuần hoặc JSON theo schema chuẩn.
2. Dùng Audio để kiểm tra kịch bản, dựng giọng đọc và phụ đề. Khi cần chuyển
   sang Video, xuất manifest `audio.video-handoff`.
3. Cung cấp audio hoặc manifest bàn giao cho Video, kèm ảnh bìa hay thư mục ảnh
   theo cảnh.
4. Dựng MP4, sau đó xem lại video, manifest kết quả và báo cáo chất lượng.

Video không tự tạo ảnh. Pillow được dùng để kiểm tra định dạng, kích thước và
mức độ sẵn sàng của ảnh trước khi dựng slideshow.

## Làm việc với kịch bản và gói truyện

Các tài liệu biên soạn chuẩn nằm trong `prompts/`, theo tên
`ChatGPT_prompt_vX.Y.Z.txt`; tên tệp có thể có thêm tiền tố số như `01-`. Runtime
luôn chọn phiên bản semantic mới nhất, đồng thời ghi nhận phiên bản và SHA-256.
Các prompt cũ chỉ dùng để đối chiếu và không còn là nguồn chuẩn khi đã có phiên
bản mới hơn.

Kiểm tra một thư mục đầu ra hoặc gói truyện v4.1.6 bằng lệnh:

```bash
ai-story-audit output
ai-story-audit output/story.zip
```

Audit kiểm tra JSON nghiêm ngặt, schema hiện hành, liên kết giữa artifact, danh
sách tệp trong archive, CRC, định dạng PNG và kích thước ảnh chuẩn. Những tiêu
chí cần OCR, nguồn gốc từ trình tạo, đánh giá ngữ nghĩa hoặc bộ lọc an toàn bên
ngoài sẽ được ghi là `NOT_VERIFIED`; kiểm tra xác định không tự nâng chúng thành
`PASS`.

Story Studio có thể chuyển `video_prompts.json` chuẩn thành dữ liệu dành cho
Veo, Flow hoặc Generic. Đầu ra hỗ trợ một tệp JSON đã liên kết, văn bản thuận
tiện để sao chép và ZIP xác định gồm từng clip, ánh xạ tài nguyên, thứ tự tạo,
cảnh báo khả năng và digest nguồn. Đây là các bản xuất dùng cho công cụ đích;
chúng không sửa hay thay thế dữ liệu chuẩn.

## Biên tập và rà soát sản xuất

- Trong tab **Canonical JSON** của Audio, mục **Chỉnh từng câu thoại** cho phép
  sửa người nói, nội dung, cảm xúc, tốc độ, khoảng nghỉ và âm thanh môi trường.
  Bản sửa chỉ tồn tại trong phiên và có thể tải xuống dưới tên
  `story.draft.json`; package nguồn cùng các báo cáo kiểm định không bị ghi đè.
- Video có thể tách một cue chứa nhiều câu thành các cue SRT dành riêng cho hiển
  thị. Timeline cảnh và hiệu ứng môi trường vẫn dùng SRT gốc, kể cả khi tắt phụ
  đề trên hình.
- Story Studio tổng hợp báo cáo truyện, kiểm định, chất lượng package và tính
  liên tục của series trong cùng một thư mục đầu ra.
- Lịch sử kiểm tra ảnh được lưu trong
  `.render_audio_gui/story_asset_history_*.json`, bên ngoài package chuẩn. Lịch
  sử này ghi nhận revision, kết quả, ghi chú và fingerprint nội dung; nó không
  thay thế bằng chứng nguồn gốc ảnh hoặc kiểm định ngữ nghĩa.

Các công cụ trên giữ nguyên định dạng package bốn giai đoạn, schema JSON nguồn
và hợp đồng bàn giao từ Audio sang Video.

## Nhịp đọc Audio

Mixer đo khoảng lặng đầu và cuối của từng đoạn tổng hợp rồi chỉ chèn phần còn
thiếu để đạt nhịp đã chọn. Preset `natural` mặc định đặt mục tiêu 550 ms giữa
hai câu, 650 ms khi đổi giọng hoặc ngôn ngữ, 800 ms khi đổi đoạn và 1200 ms khi
đổi vùng. Thẻ `[PAUSE]` và `[SILENCE]` luôn được ưu tiên. Các preset khác gồm
`compact`, `dramatic` và `off`.

## Phát triển và kiểm tra

Bốn archive tham chiếu chuẩn nằm trong `samples/Tiem_Sua_Nhung_Loi_Hua/`. Byte
của từng archive được ghim trong `SHA256SUMS` và được Git theo dõi. Fixture kiểm
thử xác minh checksum trước khi giải nén vào thư mục tạm, vì vậy một test không
thể sửa dữ liệu tham chiếu hoặc ảnh hưởng đến test khác.

Chạy toàn bộ cổng kiểm tra trước khi phát hành:

```bash
python scripts/check_reference_samples.py --require-tracked
ruff check .
mypy
pytest -q --cov=audio --cov=video --cov=studio --cov-report=term-missing:skip-covered --cov-report=xml
python scripts/run_audio_to_video_e2e.py --fixture --report e2e-report.json
python scripts/check_public_api.py
python scripts/check_dependency_direction.py
python scripts/check_standalone_architecture.py
python scripts/check_module_size_budget.py
python scripts/check_wheel_contents.py
python scripts/check_independent_wheels.py
python scripts/release_smoke.py
```

Lệnh coverage đầy đủ đo cả branch của ba package được phát hành và áp dụng
ngưỡng trong `pyproject.toml`. Các lần chạy test có mục tiêu hẹp không chịu
ngưỡng toàn cục, phù hợp cho vòng lặp phát triển nhanh.

Khi chủ động thay archive tham chiếu, hãy kiểm tra nội dung, cập nhật checksum
đã ghim rồi chạy lại các contract test. Loader không tự sửa checksum.

## Tài liệu liên quan

- [Tổng quan Story Studio](docs/OVERVIEW_STORY_STUDIO.md)
- [Xử lý sự cố](docs/TROUBLESHOOTING.md)
- [Di chuyển sang package độc lập](docs/MIGRATION_STANDALONE_PACKAGES.md)
- [Các API và hành vi đã ngừng dùng](docs/DEPRECATIONS.md)
- [Đồng bộ prompt với runtime](docs/PROMPT_SYNC.md)
- [Thay đổi theo nhóm](docs/CHANGE_GROUPS.md)
- [Lịch sử phát hành](CHANGELOG.md)

## Giấy phép

Dự án được phát hành theo giấy phép MIT. Xem [LICENSE](LICENSE).
