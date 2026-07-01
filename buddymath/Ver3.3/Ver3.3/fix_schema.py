"""
fix_schema.py – Chạy MỘT LẦN để đồng bộ schema MSSQL thật với code db.py hiện tại.

Vì sao cần chạy:
  Log khởi động server không thấy dòng "Database 'mathbuddy' sẵn sàng." /
  "Tất cả bảng đã được khởi tạo." mà db.init_db() in ra → init_db() chưa
  từng chạy trên DB thật. Vì vậy:
    - cột 'status' trong bảng accounts CHƯA tồn tại → /monitor/accounts 500
    - bảng 'notifications' CHƯA tồn tại        → /monitor/notifications* 500

Script này chỉ gọi lại db.init_db() — hàm này AN TOÀN để chạy nhiều lần
(mọi CREATE TABLE / ALTER TABLE đều có kiểm tra IF NOT EXISTS), không xoá
hay ghi đè dữ liệu hiện có.

Cách dùng (trên server, đặt cùng thư mục với db.py, dùng đúng biến môi
trường DB_HOST/DB_USER/DB_PASSWORD/DB_NAME nếu bạn có set khác mặc định):

    python3 fix_schema.py
"""

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

import db

print("Đang kết nối & đồng bộ schema với DB thật...")
db.init_db()
print("✅ Hoàn tất. Cột 'status' và bảng 'notifications' đã sẵn sàng (đã tạo nếu trước đó còn thiếu).")
print("   Bây giờ hãy thử lại /monitor/accounts và /monitor/notifications/unread-count.")
