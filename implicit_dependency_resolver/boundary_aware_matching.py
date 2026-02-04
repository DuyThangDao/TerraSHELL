"""
Boundary-aware Substring Matching Module - Step 3 of Implicit Dependency Resolution Pipeline

Matches complex strings (ARNs, URLs, Connection Strings) against resource names
by checking if resource names appear as substrings with valid boundary characters.
"""

import logging
import json
import re
import string
import os
import sys
from typing import List, Dict, Any, Set

# Setup paths to import internal modules BEFORE importing utils
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Now import utils after path is set up
from utils.n4j_helper import INSTANCE

logger = logging.getLogger(__name__)

# Valid boundary characters: :, /, ., @, -, " or start/end of string
VALID_BOUNDARY_CHARS = {':', '/', '.', '@', '-', '"', "'", ' ', '=', '<', '>'}
# Invalid boundary characters: letters and digits (to avoid matching words within words)
INVALID_BOUNDARY_CHARS = set(string.ascii_letters + string.digits + '_') # Thêm '_' vào invalid để tránh match biến

class BoundaryAwareMatcher:
    def __init__(self, path_id: str, case_sensitive: bool = False):
        self.path_id = path_id
        self.case_sensitive = case_sensitive

    def build_symbol_table(self) -> Dict[str, Dict[str, Any]]:
        """
        Build ENRICHED symbol table mapping resource names AND Physical IDs to metadata.
        CRITICAL: Step 3 relies heavily on Physical IDs because ARNs/URLs contain Physical IDs, not Logical IDs.
        """
        target_label = f"`{self.path_id}`"
        
        # Query lấy cả taint_resolved_properties để trích xuất Physical ID chuẩn xác
        query = f"""
        MATCH (r:{target_label})
        WHERE (r:resource OR r:Resource OR r.type = 'resource' OR r.resource_type = 'resource')
          AND r.name IS NOT NULL
        RETURN ID(r) as node_id, 
               r.name as name,
               r.resource_name as resource_name,
               r.type as resource_type,
               r.resource_type as resource_type_alt,
               properties(r) as raw_props,
               r.taint_resolved_properties as taint_props
        """
        
        try:
            records, _, _ = INSTANCE.execute_query(query, database_="memgraph")
            symbol_table = {}
            
            for record in records:
                node_id = record['node_id']
                resource_name = record.get('resource_name', '')
                resource_type = record.get('resource_type') or record.get('resource_type_alt', '')
                name_property = record.get('name', '')
                
                # 1. Logical Names
                if resource_type and resource_name:
                    full_name = f"{resource_type}.{resource_name}"
                elif name_property:
                    full_name = name_property
                else:
                    continue
                
                base_name = full_name.split('.', 1)[1] if '.' in full_name else full_name
                
                metadata = {
                    'node_id': node_id,
                    'resource_type': resource_type,
                    'full_name': full_name,
                    'base_name': base_name
                }
                
                # Helper add
                def add(val):
                    if not val or not isinstance(val, str): return
                    # SAFETY CHECK: Step 3 rất nhạy cảm, không index tên quá ngắn (< 3 chars)
                    # Ví dụ: resource tên "db", "id", "s3" -> Bỏ qua để tránh noise
                    if len(val) < 3: return
                    
                    key = val if self.case_sensitive else val.lower()
                    if key not in symbol_table:
                        # Lưu tên gốc để dùng cho việc check boundary
                        # (metadata lưu tên đại diện, nhưng ta cần biết chính xác từ khóa nào đã match)
                        meta_copy = metadata.copy()
                        meta_copy['match_keyword'] = val 
                        symbol_table[key] = meta_copy

                add(full_name)
                add(base_name)
                
                # 2. Physical IDs (Enrichment Logic - Copy from Step 2)
                raw_props = record.get('raw_props', {})
                taint_props_str = record.get('taint_props')
                final_props = raw_props.copy()
                
                if taint_props_str and isinstance(taint_props_str, str):
                    try:
                        resolved = json.loads(taint_props_str)
                        if isinstance(resolved, dict): final_props.update(resolved)
                    except: pass
                
                physical_ids = []
                rtype_lower = str(resource_type).lower()
                
                if 's3_bucket' in rtype_lower: physical_ids.append(final_props.get('bucket'))
                elif 'sqs_queue' in rtype_lower: physical_ids.append(final_props.get('name'))
                elif 'dynamodb_table' in rtype_lower: physical_ids.append(final_props.get('name'))
                elif 'lambda_function' in rtype_lower: physical_ids.append(final_props.get('function_name'))
                elif 'rds_cluster' in rtype_lower or 'db_instance' in rtype_lower: physical_ids.append(final_props.get('identifier'))
                elif 'iam_role' in rtype_lower: physical_ids.append(final_props.get('name'))
                elif 'kinesis' in rtype_lower: physical_ids.append(final_props.get('name'))
                
                for pid in physical_ids:
                    # Chỉ index Physical ID nếu nó sạch sẽ (không còn template variable)
                    if pid and isinstance(pid, str) and "${" not in pid and "var." not in pid:
                        add(pid)

            logger.info(f"Built enriched symbol table with {len(symbol_table)} entries")
            return symbol_table
            
        except Exception as e:
            logger.error(f"Error building symbol table: {e}")
            return {}

    def is_valid_boundary(self, char: str) -> bool:
        if char is None: return True
        return char in VALID_BOUNDARY_CHARS or char not in INVALID_BOUNDARY_CHARS

    def check_boundary_match(self, source_string: str, target_name: str) -> bool:
        """
        Check if target_name appears in source_string with valid boundaries.
        """
        if not source_string or not target_name: return False
        
        if self.case_sensitive:
            source_search = source_string
            target_search = target_name
        else:
            source_search = source_string.lower()
            target_search = target_name.lower()
        
        start_pos = source_search.find(target_search)
        while start_pos != -1:
            end_pos = start_pos + len(target_name)
            char_before = source_string[start_pos - 1] if start_pos > 0 else None
            char_after = source_string[end_pos] if end_pos < len(source_string) else None
            
            if self.is_valid_boundary(char_before) and self.is_valid_boundary(char_after):
                return True
            
            start_pos = source_search.find(target_search, start_pos + 1)
        
        return False

    def extract_complex_strings(self, resolved_properties: dict) -> List[str]:
        """
        Extract complex strings (ARNs, URLs, etc.)
        """
        strings = []
        
        def is_complex_string(s: str) -> bool:
            if not s or len(s) < 5: return False # Tăng độ dài tối thiểu
            
            s_lower = s.lower()
            # Fast checks
            if s_lower.startswith(('arn:', 'http://', 'https://', 'jdbc:', 'postgres:', 'mysql:', 'mongodb:', 'redis:')):
                return True
            
            # Domain-like or S3/SQS URL patterns
            if '.amazonaws.com' in s_lower or '.internal' in s_lower:
                return True
                
            # Generic Domain check (có dấu chấm, không phải số, không có khoảng trắng)
            if '.' in s and ' ' not in s and not re.match(r'^\d+(\.\d+)+$', s):
                # Regex check domain đơn giản
                if re.search(r'[a-z0-9][a-z0-9-]*\.[a-z]{2,}', s_lower):
                    return True

            return False
        
        def extract_recursive(value: Any):
            if isinstance(value, str):
                if is_complex_string(value):
                    strings.append(value)
            elif isinstance(value, dict):
                for v in value.values(): extract_recursive(v)
            elif isinstance(value, list):
                for item in value: extract_recursive(item)
        
        extract_recursive(resolved_properties)
        return list(set(strings)) # Unique

    def find_matching_resources(self, source_string: str, symbol_table: dict) -> List[Dict[str, Any]]:
        matches = []
        if not source_string: return matches
        
        # Optimization: Thay vì duyệt cả bảng, ta chỉ duyệt những resource name 
        # mà độ dài của nó nhỏ hơn source_string (đương nhiên)
        # Nhưng với Python dict iteration thì cứ duyệt hết cũng được với size nhỏ.
        
        for name_key, metadata in symbol_table.items():
            # Keyword thực tế được index (ví dụ: "order-queue")
            match_keyword = metadata.get('match_keyword', name_key)
            
            # Nếu keyword dài hơn chuỗi nguồn thì bỏ qua luôn
            if len(match_keyword) > len(source_string):
                continue

            if self.check_boundary_match(source_string, match_keyword):
                matches.append(metadata)
        
        # Remove duplicates
        seen_ids = set()
        unique_matches = []
        for match in matches:
            if match['node_id'] not in seen_ids:
                seen_ids.add(match['node_id'])
                unique_matches.append(match)
        
        return unique_matches

    def create_implicit_links(self, source_resource_id: int, target_resource_id: int, matched_substring: str = "") -> bool:
        if source_resource_id == target_resource_id: return False
        
        target_label = f"`{self.path_id}`"
        
        # Check exist
        check_query = f"""
        MATCH (source:{target_label})-[r:REF]->(target:{target_label})
        WHERE ID(source) = $source_id AND ID(target) = $target_id
        RETURN r LIMIT 1
        """
        try:
            records, _, _ = INSTANCE.execute_query(check_query, source_id=source_resource_id, target_id=target_resource_id, database_="memgraph")
            if records: return False
            
            # Create Edge
            create_query = f"""
            MATCH (source:{target_label}), (target:{target_label})
            WHERE ID(source) = $source_id AND ID(target) = $target_id
            MERGE (source)-[r:REF]->(target)
            SET r.method = 'boundary_match',
                r.details = $details
            RETURN r
            """
            
            # Ghi chú thêm vào cạnh để biết tại sao match
            details = f"Matched substring '{matched_substring}'"
            
            res, _, _ = INSTANCE.execute_query(create_query, source_id=source_resource_id, target_id=target_resource_id, details=details, database_="memgraph")
            return len(res) > 0
        except Exception as e:
            logger.warning(f"Error creating link: {e}")
            return False

    # ... (Giữ nguyên các hàm helper _get_resource_properties, _extract_properties_from_node từ Step 2) ...
    # Để code gọn, tôi không paste lại các hàm helper extract properties, 
    # BẠN HÃY COPY CHÚNG TỪ FILE phase1_exact_matching.py SANG ĐÂY NHÉ.
    # (Chúng giống hệt nhau).

    def run(self) -> int:
        logger.info(f"--- Starting Boundary-aware Matching for Project: {self.path_id} ---")
        
        symbol_table = self.build_symbol_table()
        if not symbol_table: return 0
        
        target_label = f"`{self.path_id}`"
        query = f"""
        MATCH (r:{target_label})
        WHERE (r:resource OR r:Resource OR r.type = 'resource' OR r.resource_type = 'resource')
        RETURN ID(r) as resource_id, r.name as resource_name, properties(r) as node_properties, r.taint_resolved_properties as taint_props
        """
        
        try:
            records, _, _ = INSTANCE.execute_query(query, database_="memgraph")
            if not records: return 0
            
            links_created = 0
            
            for record in records:
                source_id = record['resource_id']
                res_name = record.get('resource_name', 'unknown')
                
                # Logic extract properties (cần hàm helper _extract_properties_from_node)
                # Giả định bạn đã copy hàm helper vào class này
                # properties = self._extract_properties_from_node(record) 
                
                # --- TẠM THỜI VIẾT LOGIC EXTRACT NHANH TẠI ĐÂY (NẾU CHƯA COPY HELPER) ---
                raw_props = record.get('node_properties', {})
                taint_props_str = record.get('taint_props')
                properties = raw_props.copy()
                if taint_props_str:
                    try: 
                        properties.update(json.loads(taint_props_str))
                    except: pass
                # -------------------------------------------------------------------

                complex_strings = self.extract_complex_strings(properties)
                
                for source_str in complex_strings:
                    matches = self.find_matching_resources(source_str, symbol_table)
                    for match in matches:
                        target_id = match['node_id']
                        target_full_name = match['full_name']
                        match_keyword = match.get('match_keyword', 'unknown')
                        
                        if source_id == target_id: continue
                        
                        if self.create_implicit_links(source_id, target_id, match_keyword):
                            links_created += 1
                            logger.info(f"  ✓ Link: {res_name} -> {target_full_name} (found '{match_keyword}' in '{source_str[:50]}...')")
            
            logger.info(f"--- Boundary Matching Done. Links created: {links_created} ---")
            return links_created
            
        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0

# --- MAIN BLOCK FOR STANDALONE EXECUTION ---
if __name__ == "__main__":
    import sys
    import os
    
    # Setup paths to import internal modules
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Import utils
    try:
        from utils.n4j_helper import Initialize, GetPathID
    except ImportError:
        logger.error("Could not import utils.n4j_helper")
        sys.exit(1)
    
    # Configure logging for standalone test
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    if len(sys.argv) < 2:
        print("Usage: python3 boundary_aware_matching.py <project_path>")
        print("Example: python3 boundary_aware_matching.py /home/thangdd/repos/TerrARA/demo_tf_project")
        sys.exit(1)
    
    project_path = os.path.abspath(sys.argv[1])
    
    if not os.path.exists(project_path):
        print(f"Error: Path does not exist: {project_path}")
        sys.exit(1)
    
    # Initialize connection
    try:
        Initialize()
        logger.info("Connected to Memgraph")
    except Exception as e:
        logger.error(f"Failed to connect to Memgraph: {e}")
        sys.exit(1)
    
    # Get path ID
    path_id = GetPathID(project_path)
    logger.info(f"Running Boundary-aware Substring Matching for Path ID: {path_id}")
    
    # Run Boundary-aware Substring Matching
    logger.info("="*60)
    logger.info("STEP 3: BOUNDARY-AWARE SUBSTRING MATCHING - Creating Implicit Dependency Links")
    logger.info("="*60)
    
    try:
        matcher = BoundaryAwareMatcher(path_id, case_sensitive=False)
        links_created = matcher.run()
        logger.info("="*60)
        logger.info(f"✓ Boundary-aware Substring Matching completed: {links_created} implicit links created")
        logger.info("="*60)
    except Exception as e:
        logger.error(f"✗ Boundary-aware Substring Matching failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)