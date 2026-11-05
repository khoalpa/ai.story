# Báo cáo phát hành Prompt v5.2.2 — Revision r3

**Quyết định:** `PRODUCTION_READY_SPEC` theo tiêu chuẩn phát hành đặc tả rút gọn.

**Không tương đương:** `STRICT_DEPLOYMENT_VERIFIED`, Stage 1/2/3 `COMPLETE` hay chứng nhận chất lượng truyện, ảnh, video hoặc audio sản xuất.

## Điều chỉnh

- Bỏ gate `IMAGE_PROMPT_T5_TOKENS` và giới hạn T5-512 khỏi Stage 1.
- Record tương thích cũ được phép dùng `required=false`, `status=NOT_APPLICABLE`; không ghi `PASS` nếu chưa đo.
- Giữ nguyên schema `4.1.3 / 5.0.0 / image 1.1 / CIP 1.0 / catalog 1.0`.
- Giữ nguyên mọi gate runtime khác và quy tắc không tạo bằng chứng giả.
- Chứng cứ và chính sách lưu riêng, không đóng validator vào `story.zip`.

## Kiểm tra thực tế

| Kiểm | Kết quả |
|---|---|
| revision_consistency | PASS |
| schema_versions_preserved | PASS |
| regression_suite | PASS |
| tokenizer_gate_removed_consistently | PASS |
| no_production_test_claim | PASS |

**Chưa xác minh:** tokenizer production, alignment audio liên tục, ảnh AI/parity thực, Stage 1→3 thực và 79 ca nghiệm thu formal. Các hạng mục này không được cấp PASS trong bằng chứng phát hành.
