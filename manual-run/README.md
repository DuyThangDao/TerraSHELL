# Manual Run Steps

Thư mục này chứa các file để chạy từng bước của quá trình xử lý một cách tuần tự, giúp debug và xác định bước nào gây timeout.

## Cấu trúc

Mỗi step được đánh số thứ tự và có thể chạy độc lập. Các step sử dụng `shared_state.py` để chia sẻ dữ liệu giữa các bước.

## Thứ tự chạy

1. **step_01_initialize.py** - Khởi tạo và load configuration files
2. **step_02_cleanup_db.py** - Clean up database (xóa tất cả nodes và relationships)
3. **step_03_load_graph.py** - Load graph từ Terraform folder
4. **step_04_implicit_resolution.py** - Chạy implicit dependency resolution (optional)
5. **step_05_tag_nodes.py** - Tag nodes từ annotation configuration
6. **step_06_remove_nontagged.py** - Xóa các nodes không được tag
7. **step_07_cleanup.py** - Cleanup graph (remove self-loops)
8. **step_08_compress.py** - Compress nodes
9. **step_09_link_tagged.py** - Link các tagged nodes
10. **step_10_remove_nontagged_again.py** - Xóa non-tagged nodes lần nữa
11. **step_11_semgrep_public.py** - Chạy Semgrep và tag public resources
12. **step_12_remove_public_boundaries.py** - Xóa public boundaries
13. **step_13_cleanup_again.py** - Cleanup graph lần nữa
14. **step_14_build_diagram.py** - Build diagram structure
15. **step_15_auto_detect_public.py** - Auto-detect public resources
16. **step_16_outermost_boundaries.py** - Query outermost boundaries
17. **step_17_connections.py** - Query và add connections
18. **step_18_export.py** - Export kết quả

## Cách sử dụng

### Chạy từng step một

```bash
# Step 1: Initialize
python3 manual-run/step_01_initialize.py \
    <terraform_project_path> \
    --anno_path=./input/aws_annotation.yaml \
    --rule_path=./input/aws_rule.yaml \
    --out_path=./output

# Step 2: Cleanup database
python3 manual-run/step_02_cleanup_db.py

# Step 3: Load graph
python3 manual-run/step_03_load_graph.py --reinit=True

# Step 4: Implicit resolution (optional)
python3 manual-run/step_04_implicit_resolution.py

# Step 5: Tag nodes
python3 manual-run/step_05_tag_nodes.py

# Step 6: Remove non-tagged
python3 manual-run/step_06_remove_nontagged.py

# Step 7: Cleanup
python3 manual-run/step_07_cleanup.py

# Step 8: Compress
python3 manual-run/step_08_compress.py

# Step 9: Link tagged
python3 manual-run/step_09_link_tagged.py

# Step 10: Remove non-tagged again
python3 manual-run/step_10_remove_nontagged_again.py

# Step 11: Semgrep public
python3 manual-run/step_11_semgrep_public.py --sem_rule=./input/semgrep_rule.yaml

# Step 12: Remove public boundaries
python3 manual-run/step_12_remove_public_boundaries.py

# Step 13: Cleanup again
python3 manual-run/step_13_cleanup_again.py

# Step 14: Build diagram
python3 manual-run/step_14_build_diagram.py

# Step 15: Auto-detect public
python3 manual-run/step_15_auto_detect_public.py

# Step 16: Outermost boundaries
python3 manual-run/step_16_outermost_boundaries.py

# Step 17: Connections
python3 manual-run/step_17_connections.py

# Step 18: Export
python3 manual-run/step_18_export.py
```

### Chạy tất cả các steps bằng script

Tạo file `run_all_steps.sh`:

```bash
#!/bin/bash
set -e

TERRAFORM_PATH=$1
if [ -z "$TERRAFORM_PATH" ]; then
    echo "Usage: $0 <terraform_project_path>"
    exit 1
fi

echo "Running all steps..."
python3 manual-run/step_01_initialize.py "$TERRAFORM_PATH"
python3 manual-run/step_02_cleanup_db.py
python3 manual-run/step_03_load_graph.py
python3 manual-run/step_04_implicit_resolution.py
python3 manual-run/step_05_tag_nodes.py
python3 manual-run/step_06_remove_nontagged.py
python3 manual-run/step_07_cleanup.py
python3 manual-run/step_08_compress.py
python3 manual-run/step_09_link_tagged.py
python3 manual-run/step_10_remove_nontagged_again.py
python3 manual-run/step_11_semgrep_public.py
python3 manual-run/step_12_remove_public_boundaries.py
python3 manual-run/step_13_cleanup_again.py
python3 manual-run/step_14_build_diagram.py
python3 manual-run/step_15_auto_detect_public.py
python3 manual-run/step_16_outermost_boundaries.py
python3 manual-run/step_17_connections.py
python3 manual-run/step_18_export.py

echo "All steps completed!"
```

## Logging

Mỗi step tạo một log file riêng trong thư mục `manual-run/`:
- `step_01.log`
- `step_02.log`
- ...
- `step_18.log`

Các log file này giúp bạn xác định:
- Bước nào đang chạy
- Thời gian thực thi của mỗi bước
- Lỗi xảy ra ở bước nào
- Thông tin chi tiết về quá trình xử lý

## State Management

Các step sử dụng `shared_state.py` để lưu trữ và chia sẻ dữ liệu:
- `pathID`: ID của project path trong database
- `in_path`: Đường dẫn input
- `out_path`: Đường dẫn output
- `anno`: Annotation configuration
- `rule`: Rule configuration
- `compresses`: Danh sách resources cần compress
- `publics`: Danh sách public resource patterns

State được lưu trong file `.state.json` trong thư mục `manual-run/`.

## Debugging Timeout

Nếu gặp timeout:

1. Chạy từng step một và xem log file tương ứng
2. Xác định step nào timeout bằng cách kiểm tra:
   - Log file của step đó
   - Thời gian thực thi trong log
   - Thông báo lỗi trong log

3. Các step có khả năng timeout cao:
   - **Step 03**: Load graph (nếu project lớn)
   - **Step 04**: Implicit resolution (nếu graph lớn)
   - **Step 06, 10**: Remove non-tagged (nếu graph lớn)
   - **Step 08**: Compress (nếu nhiều resources)
   - **Step 09**: Link tagged (nếu graph lớn)
   - **Step 11**: Semgrep (nếu project lớn)
   - **Step 14**: Build diagram (nếu nhiều relationships)

## Lưu ý

- Luôn chạy các step theo thứ tự
- Nếu một step fail, bạn có thể fix và chạy lại từ step đó
- State được lưu giữa các lần chạy, nên bạn có thể tiếp tục từ step đã dừng
- Để xóa state và bắt đầu lại, dùng `--clear_previous_state=True` trong step 01
