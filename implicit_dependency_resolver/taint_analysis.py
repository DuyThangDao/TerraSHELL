import logging
from utils.n4j_helper import INSTANCE

logger = logging.getLogger(__name__)

class TaintAnalyzer:
    def __init__(self, path_id):
        self.path_id = path_id

    def run(self):
        logger.info(f"--- Bắt đầu Taint Analysis cho Project: {self.path_id} ---")
        count = self.propagate_constants()
        logger.info(f"--- Kết thúc Taint Analysis. Đã giải mã được {count} resources. ---")

    def propagate_constants(self):
        """
        THUẬT TOÁN: Constant Propagation - Chỉ propagate đến resource TRỰC TIẾP tham chiếu Variable/Local
        Không propagate qua resource trung gian (ví dụ: web_server không nhận giá trị từ var qua web_profile)
        
        CHỈ PROPAGATE TỪ VARIABLES/LOCALS ĐƯỢC THAM CHIẾU THỰC SỰ TRONG RESOURCE PROPERTIES
        """
        # 1. Chuẩn bị Label (để thay thế vào query sau)
        # Dùng backticks để đảm bảo an toàn nếu ID có ký tự lạ
        target_label = f"`{self.path_id}`"

        # 2. Viết Query dạng chuỗi thường (KHÔNG dùng f"")
        # Lưu ý: Ở đây ta dùng placeholder 'TARGET_LABEL' để thay thế sau
        query_template = """
        MATCH (r:TARGET_LABEL)
        WHERE (r:resource OR r:Resource OR r.type = 'resource')
        
        // Tìm Variable được tham chiếu TRỰC TIẾP từ resource này
        OPTIONAL MATCH (r)-[:REF]->(direct_var:TARGET_LABEL)
        WHERE (direct_var:Variable OR direct_var:var OR 'Variable' IN labels(direct_var))
          AND (direct_var.default IS NOT NULL)
        
        // Lấy variable name từ resource_name hoặc name property
        WITH r, direct_var,
             COALESCE(direct_var.resource_name, 
                      CASE 
                        WHEN direct_var.name IS NOT NULL AND direct_var.name CONTAINS '.' 
                        THEN SPLIT(direct_var.name, '.')[1]
                        ELSE direct_var.name
                      END,
                      '') as var_name
        
        WHERE var_name <> '' OR direct_var IS NULL
        
        // Tạo một chuỗi từ tất cả property values của resource để kiểm tra
        // Sử dụng properties() function để lấy tất cả properties, sau đó convert values thành string
        // Lưu ý: Trong Memgraph/Cypher, ta cần kiểm tra các property phổ biến và concatenate chúng
        WITH r, direct_var, var_name,
             // Concatenate các property values phổ biến thành một chuỗi để tìm kiếm
             COALESCE(toString(r.name), '') + '|' + 
             COALESCE(toString(r.description), '') + '|' +
             COALESCE(toString(r.value), '') + '|' +
             COALESCE(toString(r.default), '') + '|' +
             COALESCE(toString(r.label), '') + '|' +
             COALESCE(toString(r.resource_name), '') as all_props_string
        
        // Kiểm tra xem variable có được tham chiếu trong resource properties không
        // Pattern: var.var_name hoặc ${var.var_name} hoặc var.var_name}
        WITH r, direct_var, var_name, all_props_string,
             CASE 
               WHEN direct_var IS NULL THEN 0
               WHEN all_props_string CONTAINS ('var.' + var_name) OR 
                    all_props_string CONTAINS ('${var.' + var_name) OR
                    all_props_string CONTAINS ('var.' + var_name + '}')
               THEN 1 
               ELSE 0 
             END as is_var_referenced
        
        // Tìm Local được tham chiếu TRỰC TIẾP từ resource này
        OPTIONAL MATCH (r)-[:REF]->(direct_local:TARGET_LABEL)
        WHERE (direct_local:Local OR direct_local:local OR 'Local' IN labels(direct_local))
          AND (direct_local.value IS NOT NULL)
        
        // Lấy local name
        WITH r, direct_var, direct_local, var_name, all_props_string, is_var_referenced,
             COALESCE(direct_local.resource_name,
                      CASE 
                        WHEN direct_local.name IS NOT NULL AND direct_local.name CONTAINS '.' 
                        THEN SPLIT(direct_local.name, '.')[1]
                        ELSE direct_local.name
                      END,
                      '') as local_name
        
        // Kiểm tra xem local có được tham chiếu trong properties không
        WITH r, direct_var, direct_local, var_name, local_name, all_props_string, is_var_referenced,
             CASE 
               WHEN direct_local IS NULL THEN 0
               WHEN all_props_string CONTAINS ('local.' + local_name) OR 
                    all_props_string CONTAINS ('${local.' + local_name) OR
                    all_props_string CONTAINS ('local.' + local_name + '}')
               THEN 1 
               ELSE 0 
             END as is_local_referenced
        
        // Nếu Local tham chiếu Variable, resolve giá trị từ Variable đó
        OPTIONAL MATCH (direct_local)-[:REF]->(var_from_local:TARGET_LABEL)
        WHERE (var_from_local:Variable OR var_from_local:var OR 'Variable' IN labels(var_from_local))
          AND (var_from_local.default IS NOT NULL)
          AND is_local_referenced = 1
        
        // Lấy giá trị: ưu tiên Variable trực tiếp (đã được verify), sau đó là Variable qua Local, cuối cùng là Local
        WITH r, 
             COALESCE(
               CASE WHEN is_var_referenced = 1 AND direct_var IS NOT NULL THEN direct_var.default ELSE NULL END,
               CASE 
                 WHEN is_local_referenced = 1 AND var_from_local.default IS NOT NULL 
                 THEN var_from_local.default
                 WHEN is_local_referenced = 1 AND direct_local.value IS NOT NULL
                 THEN direct_local.value
                 ELSE NULL
               END
             ) as candidate_val
        
        WHERE candidate_val IS NOT NULL
        
        // Kiểm tra giá trị có "sạch" không (không chứa interpolation)
        WITH r, candidate_val,
             CASE 
                WHEN candidate_val CONTAINS "${" THEN 0
                WHEN candidate_val CONTAINS "var." THEN 0
                WHEN candidate_val CONTAINS "local." THEN 0
                ELSE 1 
             END as score
        
        WHERE score = 1  // Chỉ lấy giá trị "sạch"
        
        SET r.taint_resolved_value = candidate_val
        
        RETURN count(r) as cnt
        """
        
        # 3. Thay thế Label thực tế vào Query
        final_query = query_template.replace("TARGET_LABEL", target_label)
        
        try:
            records, _, _ = INSTANCE.execute_query(final_query, database_="memgraph")
            return records[0]["cnt"] if records else 0
        except Exception as e:
            logger.error(f"Lỗi khi chạy Taint Analysis: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0