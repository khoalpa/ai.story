# Báo cáo phát hành Prompt v5.2.2 — Revision r2

**Quyết định:** `PRODUCTION_READY_SPEC` theo tiêu chuẩn PHÁT HÀNH ĐẶC TẢ RÚT GỌN.

**Không tương đương:** `STRICT_DEPLOYMENT_VERIFIED`, Stage 1/2/3 `COMPLETE` hay chứng nhận chất lượng truyện/ảnh/video/audio sản xuất.

## Điều chỉnh
- Bỏ yêu cầu **kiểm thử sản xuất thật** với tokenizer, audio và ảnh **để phát hành tài liệu prompt**.
- Không yêu cầu pipeline E2E thực hoặc hoàn tất 79 formal acceptance cho profile này.
- Giữ nguyên schema `4.1.3 / 5.0.0 / image 1.1 / CIP 1.0 / catalog 1.0`.
- Không hạ chuẩn gate **runtime** `IMAGE_PROMPT_T5_TOKENS`: thiếu tokenizer thì Stage 1 `PARTIAL`.
- Chứng cứ và chính sách lưu riêng, không đóng validator vào `story.zip`.

## Kiểm tra thực tế
| Kiểm | Kết quả |
|---|---|
| revision_consistency | PASS |
| schema_versions_preserved | PASS |
| seven_regression_suites_pass | PASS |
| control_fixture_mechanical_clean | PASS |
| critical_stage_gates_unchanged | PASS |
| no_production_test_claim | PASS |

### Chạy lại 7 bộ test

| Bộ test | Exit code |
|---|---:|
| `test_story_v522.py` | 0 |
| `test_story_v522_phase2.py` | 0 |
| `test_story_v522_phase3.py` | 0 |
| `test_story_v522_phase4.py` | 0 |
| `test_story_v522_phase5.py` | 0 |
| `test_story_v522_phase6.py` | 0 |
| `test_story_v522_phase7.py` | 0 |

**Fixture đối chứng:** 0 lỗi trong phạm vi validator hiện có.

**Chưa xác minh:** native tokenizer, alignment audio liên tục, ảnh AI/parity thực, Stage 1→3 thực, 79 ca nghiệm thu formal. Các hạng mục này được miễn ở **cấp phát hành đặc tả**, không cấp PASS giả cho artifact.
