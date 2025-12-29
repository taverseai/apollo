# Hướng dẫn xử lý lỗi "unknown type: public.vector" với Supabase

Tài liệu này hướng dẫn cách khắc phục lỗi `ERROR: PostgreSQL, Failed to connect database ... Got:unknown type: public.vector` khi chạy ứng dụng LightRAG với cơ sở dữ liệu Supabase.

## Mô tả lỗi

Khi khởi động ứng dụng, bạn gặp thông báo lỗi sau:

```
ERROR: PostgreSQL, Failed to connect database at aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres, Got:unknown type: public.vector
```

hoặc

```
ValueError: unknown type: public.vector
```

## Nguyên nhân

Lỗi này xảy ra do sự kết hợp của hai vấn đề:

1.  **Cổng kết nối (Port)**: Bạn đang sử dụng cổng `6543` (Transaction Pooler) của Supabase. Trình điều khiển `asyncpg` (được LightRAG sử dụng) cần thực hiện "type introspection" (kiểm tra kiểu dữ liệu) để nhận diện kiểu `vector`, nhưng Transaction Pooler không hỗ trợ đầy đủ các prepared statements cần thiết cho việc này.
2.  **Schema của Extension**: Mặc định trên một số setup, extension `vector` có thể được cài đặt vào schema `extensions` hoặc schema khác, trong khi thư viện `pgvector` và `asyncpg` mặc định tìm kiếm kiểu `vector` trong schema `public`.

## Cách khắc phục

Thực hiện 2 bước sau để giải quyết triệt để vấn đề:

### Bước 1: Chuyển sang Session Pooler (Port 5432)

Supabase cung cấp hai chế độ kết nối gọi là Transaction Mode (6543) và Session Mode (5432). Để `asyncpg` hoạt động tốt với các kiểu dữ liệu tùy chỉnh, hãy sử dụng Session Mode.

Mở file `.env` và cập nhật:

```ini
# Thay đổi từ 6543 sang 5432
POSTGRES_PORT=5432
```

### Bước 2: Di chuyển extension `vector` về schema `public`

Nếu extension `vector` đang nằm ở schema khác (ví dụ: `extensions`), bạn cần di chuyển nó về `public` để ứng dụng có thể tìm thấy.

Chạy lệnh SQL sau trong SQL Editor của Supabase hoặc qua psql:

```sql
ALTER EXTENSION vector SET SCHEMA public;
```

Sau khi thực hiện hai bước trên, hãy khởi động lại ứng dụng LightRAG. Lỗi sẽ được giải quyết.
