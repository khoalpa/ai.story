# Overview và Story Studio — workflow 3.13.0

## Cách sử dụng

- Overview hiển thị stage từ `workflow_manifest.json`, purpose, profile, prompt version,
  số file kỳ vọng và hành động cần xử lý. Trạng thái sản xuất audio/video nằm riêng.
- Story Studio → **Gói & quy trình**: kiểm tra thư mục hiện tại, `story.zip` trong thư mục,
  hoặc ZIP upload. Có thể cung cấp ZIP cha trực tiếp để đối chiếu digest và bytes kế thừa.
  Upload ZIP ở đây là bản kiểm tra riêng, không đổi nguồn của các workspace khác.
- **Visual Bible** đọc `visual_bible.json` của Stage 2. File này không bắt buộc ở Stage 3/4.
- **Kế hoạch video** đọc `video_prompts.json`: timeline, source span, reference inputs,
  continuity, prompt/audio prompt, capability và source binding. Khi canonical structure
  không FAIL, viewer cho xem trước và tải projection Veo, Flow hoặc Generic dưới dạng
  JSON tổng, prompt text và ZIP gồm job từng clip; đây không phải công cụ render video.
- **Tài nguyên** hiển thị metadata/provenance nguồn; đủ số ảnh không tự chứng minh đủ commit.

Ứng dụng không ghi đè artifact, giải nén lên thư mục người dùng, chuyển stage tự động,
gọi generator hoặc tự migrate legacy. Package builder API có thể rebuild archive mới và
atomic-publish khi caller yêu cầu; UI hiện vẫn chỉ đọc. Các nút export chỉ tạo bytes
download dẫn xuất ngoài `story.zip`; `video_prompts.json` vẫn là source of truth duy nhất.

## Phạm vi kiểm tra đã triển khai

`studio/workflow_package.py` kiểm tra root/member schema manifest, field order, enum,
stage-specific file allowlist/count/order, SHA-256/size từng member, story binding,
canonical package digest, ownership/mutation và parent trực tiếp khi có bytes nguồn.
JSON được đọc strict UTF-8, không BOM, duplicate key (kể cả trùng sau NFC), NaN/Infinity.
ZIP được reopen trong bộ nhớ và kiểm CRC; từ chối duplicate/case-collision, traversal,
backslash, symlink, directory entry, encryption và member vượt giới hạn.

Giới hạn viewer: tối đa 1.024 ZIP entries, 64 MiB/member, 512 MiB/archive hoặc tổng
bytes giải nén, 5 MiB/JSON. Đây là giới hạn tài nguyên của ứng dụng, không phải threshold prompt.

Thư mục làm việc chỉ kiểm tra projection của gói: root artifacts cùng các thư mục ảnh.
Audio, video, log và file ngoài projection không bị đóng gói hoặc dùng để kết luận archive
đúng allowlist. Muốn kiểm tra toàn bộ thành viên thực tế, chọn nguồn ZIP.

`integrity_status` mô tả các phép kiểm tra bytes/manifest/parent; `stage_gate_status`
mô tả detector nội dung; `publish_status` chỉ PASS khi cả hai PASS. `stage_gate_status`
hiện giữ `NOT_VERIFIED`: chưa có bộ detector độc lập
đầy đủ cho safety, provenance, nội dung, mỹ thuật và VIDEO_PROMPT_GATES.
Manifest/report tự khai PASS không được nâng thành xác minh đầy đủ, và không cấp quyền publish.
Parent binding chỉ chứng minh liên kết trực tiếp, không chứng nhận toàn bộ chuỗi tổ tiên.

Kế hoạch video kiểm tra deterministic exact field/order ở root và các object chính, enum lấy
từ prompt contract, số clip/scene, thứ tự ID, duration/usable span, source interval,
FULL_STORY gap/tail, tổng duration, output digest, ba source file hash và sự tồn tại của ảnh
tham chiếu. Chưa recompute đầy đủ script timeline, các set digest hoặc semantic continuity.
FULL_STORY trên 120 clip hiển thị cảnh báo xác nhận; mở viewer không được tính là xác nhận generation.

## Tương thích và việc chưa triển khai

- `story.zip` CURRENT có manifest luôn đi qua cùng validator workflow. Thiếu manifest:
  `MIGRATION_REQUIRED`, không suy stage từ filename hoặc ảnh hiện có; các tên
  `stage1_checkpoint.zip`/`stage2_checkpoint.zip` chỉ còn là legacy diagnostics.
  Chưa có adapter exact-version legacy được xác minh, vì vậy không tự chuyển đổi checkpoint cũ.
- `workflow_builder.py` cung cấp lõi CREATE/REPAIR deterministic: exact allowlist/order,
  parent/ownership binding, build trong bộ nhớ, reopen integrity và atomic publish tùy chọn;
  chưa có UI điều khiển hoặc detector đầy đủ để tự nâng `publish_status` thành PASS.
- Projection Veo/Flow/Generic là export disposable có binding source/adapter/digest,
  giữ nguyên canonical semantic envelope và không phải package authoritative. UI chỉ
  khóa export khi canonical structure FAIL; gate/capability `NOT_VERIFIED` được ghi rõ
  thành cảnh báo trong giao diện và manifest ZIP.
- ZIP export chứa canonical source, target payload, prompt JSON từng clip, bản text,
  reference map và generation order. Flow graph tạo dependency
  `last_frame_to_first_frame` cho clip yêu cầu `CHAINED_LAST_FRAME`.
- Legacy router chỉ activate exact basename/version allowlist. Thiếu fixture/gate của
  phiên bản gốc thì dừng ở `MIGRATION_REQUIRED`, không materialize package CURRENT.
- Tệp thay thế nội dung/báo cáo là bản xem thử, không ghi đè dữ liệu và không giữ xác minh
  của gói trên đĩa. Output audio/video không thay đổi trạng thái gói truyện.

## Kiểm thử

```powershell
.venv\Scripts\python.exe -m pytest tests/contracts -q
.venv\Scripts\python.exe -m pytest tests/smoke/test_streamlit_launchers.py -q
```

Các ca mới nằm trong `tests/contracts/test_workflow_package.py`, gồm tampering,
parent thiếu/sai, REPAIR, path/ZIP security, strict JSON, stage-aware inventory,
media độc lập, Stage 4 không sửa Stage 3 và Streamlit AppTest cho các mục mới.
