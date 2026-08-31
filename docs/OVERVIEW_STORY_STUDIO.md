# Overview và Story Studio

## Diễn giải báo cáo

- Overview và Tổng quan Story Studio dùng chung `review_package`.
- Cổng NOT_APPLICABLE không bị coi là FAIL khi đó là continuity, hồ sơ ADULT_STANDARD/YOUTH_SAFE và có lý do standalone rõ ràng. Cổng không xác minh, danh sách trống/sai kiểu và cổng khác không được tự miễn.
- Điểm 0–10 giữ nguyên; bản xuất có điểm trên 10 đến 100 được quy đổi để hiển thị /10. Đây là tương thích dữ liệu xuất, không phải chấm lại chất lượng hoặc xác nhận schema đúng hoàn toàn. Giá trị thiếu/không hữu hạn/ngoài miền hiển thị dấu gạch.
- Tiêu chí đọc từ quality.dimension_scores khi có, giữ tương thích cấu trúc cũ. Thiếu điểm không thay bằng 0.
- Gói nội dung đạt khác với sẵn sàng xuất bản. Xuất bản yêu cầu gói đạt, kiểm tra binding và ảnh tại máy, audio/handoff đạt và tất cả phiên bản video được phát hiện đạt kiểm định.
- Thời lượng, số từ và số cảnh là số liệu khai báo trong báo cáo, không phải số liệu vừa tính lại. Bản đồ vùng/cảnh và bộ ảnh sản xuất có số lượng riêng.

## Nguồn dữ liệu

Tệp tải lên được giữ bằng bytes trong session, theo thư mục dự án. Các mục Story Studio và Overview của cùng thư mục dùng chung nguồn này. Tệp không được ghi vào output. Nút **Bỏ tất cả tệp thay thế** khôi phục nguồn từ thư mục. Đổi thư mục Story Studio xóa các tệp thay thế của dự án cũ; reload toàn bộ session cũng không bảo đảm giữ các tệp tải lên.

Tệp đĩa được đọc lại; không lưu snapshot báo cáo đĩa trong session. SHA-256 của báo cáo kiểm định/chất lượng được đối chiếu với đúng bytes kịch bản đang dùng, kể cả kịch bản tải lên. Hash thiếu là chưa xác minh, không phải khớp. Khi đổi dự án, kết quả render trước đó không được dùng làm đầu ra của dự án mới.

## Tài nguyên và bằng chứng

Mục Tài nguyên liệt kê ảnh nhân vật, landscape và portrait, lọc ảnh cần xem lại, xem kích thước/dung lượng/hash và so sánh hai tỷ lệ. Các đường dẫn từ báo cáo chỉ được đọc trong thư mục dự án. Ảnh được kiểm tra khả năng đọc và đối chiếu kích thước/hash; việc này không đánh giá mỹ thuật, nhận diện nhân vật hay xác thực mọi digest ngữ nghĩa.

Hồ sơ nhân vật hiển thị ảnh tham chiếu. Cổng kiểm định có thể mở bằng chứng dạng script:start-end trong Nội dung, kèm chỉ số JSON và số mục hiển thị. Bằng chứng ngoài phạm vi được cảnh báo.

## Kiểm tra

Chạy các kiểm thử ở `tests/contracts/test_project_review.py` cùng các bộ kiểm thử Story Studio, Overview, Story Validation, Story Report, Story Images và Project Context. Bộ mới gồm kiểm tra trạng thái cổng, thang điểm, thay đổi ảnh, báo cáo cũ, nguồn thay thế, đổi dự án và luồng giao diện mở bằng chứng.

Nếu ứng dụng đang chạy vẫn dùng module Python đã nạp trước khi cập nhật, khởi động lại ứng dụng bằng open_app.bat để nạp mã mới.
