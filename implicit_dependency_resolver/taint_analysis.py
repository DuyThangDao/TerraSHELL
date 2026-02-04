import logging
import json
import re
import os
import sys
from typing import Dict, Any, Union, List, Optional

# Setup paths to import internal modules BEFORE importing utils
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Now import utils after path is set up
from utils.n4j_helper import INSTANCE, Initialize, GetPathID, UpdateNodeProperties

logger = logging.getLogger(__name__)

class TaintAnalyzer:
    def __init__(self, path_id: str):
        self.path_id = path_id

    def run(self) -> int:
        """
        Chạy quy trình Taint Analysis:
        1. Tìm các giá trị hằng số (constants) từ variables/locals.
        2. Lan truyền (Propagate) các giá trị này vào resource properties.
        3. Lưu kết quả đã giải mã vào node trong DB.
        """
        logger.info(f"--- Bắt đầu Taint Analysis cho Project: {self.path_id} ---")
        count = self.propagate_constants()
        logger.info(f"--- Kết thúc Taint Analysis. Đã giải mã thành công cho {count} resources. ---")
        return count

    def _has_variable_reference(self, text: str) -> bool:
        """
        Kiểm tra xem string có chứa tham chiếu biến hay không.
        Hỗ trợ: var, local, module, data và khoảng trắng.
        """
        if not isinstance(text, str):
            return False
        
        # Pattern 1: Interpolation ${ var.xxx }
        # Hỗ trợ khoảng trắng và các scope khác nhau
        pattern1 = r'\$\{\s*(var|local|module|data)\.([a-zA-Z0-9_\-]+(?:\.[a-zA-Z0-9_\-]+)*)\s*\}'
        if re.search(pattern1, text):
            return True
        
        # Pattern 2: Standalone var.xxx (ít gặp trong string property nhưng có thể xảy ra)
        pattern2 = r'(?<!\$)\b(var|local)\.([a-zA-Z0-9_\-]+)'
        if re.search(pattern2, text):
            return True
        
        return False

    def _has_resolved_variable_reference(self, text: str, var_values: Dict[str, Any]) -> bool:
        """
        Kiểm tra xem string có chứa reference VÀ reference đó đã có giá trị trong var_values không.
        """
        if not isinstance(text, str):
            return False
        
        # Pattern 1: ${ var.xxx }
        pattern1 = r'\$\{\s*(?:var|local|module|data)\.([a-zA-Z0-9_\-]+(?:\.[a-zA-Z0-9_\-]+)*)\s*\}'
        for match in re.finditer(pattern1, text):
            # Pattern chỉ có 1 group, không phải group(2)
            try:
                full_ref_name = match.group(1)
            except IndexError:
                continue
            # Lấy key chính (bỏ qua phần nested property nếu có)
            main_key = full_ref_name.split('.')[0]
            if main_key in var_values:
                return True
        
        # Pattern 2: Standalone
        pattern2 = r'(?<!\$)\b(?:var|local)\.([a-zA-Z0-9_\-]+)'
        for match in re.finditer(pattern2, text):
            var_name = match.group(1)
            if var_name in var_values:
                return True
        
        return False

    def _replace_variables_in_string(self, text: str, var_values: Dict[str, Any]) -> str:
        """
        Thay thế các variable references trong string bằng giá trị thực tế.
        
        Logic xử lý an toàn:
        - Chỉ thay thế nếu giá trị là Primitive (str, int, bool).
        - Nếu giá trị là Complex (dict, list), KHÔNG thay thế vào string interpolation 
          để tránh tạo ra chuỗi rác (như "app-{'key': 'val'}-v1"), trừ khi cần thiết.
        """
        if not isinstance(text, str):
            return text
        
        result = text
        
        # 1. Xử lý Interpolation: ${ scope.name }
        pattern1 = r'\$\{\s*(?:var|local|module|data)\.([a-zA-Z0-9_\-]+(?:\.[a-zA-Z0-9_\-]+)*)\s*\}'
        
        def replace_interpolation(match):
            full_ref_name = match.group(1) # vd: "bucket_name"
            main_key = full_ref_name.split('.')[0]
            
            if main_key in var_values:
                val = var_values[main_key]
                # Chỉ thay thế nếu là kiểu dữ liệu đơn giản có thể convert sang string an toàn
                if isinstance(val, (str, int, float, bool)):
                    return str(val)
                # Nếu là dict/list, giữ nguyên placeholder để tránh lỗi logic string
                # (Hoặc có thể mở rộng để hỗ trợ jsonencode nếu cần)
                return match.group(0)
            
            return match.group(0) # Giữ nguyên nếu không tìm thấy

        result = re.sub(pattern1, replace_interpolation, result)
        
        # 2. Xử lý Standalone: var.name (thường gặp khi gán trực tiếp property = var.name)
        # Lưu ý: Nếu property là string "var.name", ta thay thế. 
        pattern2 = r'(?<!\$)\b(?:var|local)\.([a-zA-Z0-9_\-]+)'
        
        def replace_standalone(match):
            var_name = match.group(1)
            if var_name in var_values:
                val = var_values[var_name]
                if isinstance(val, (str, int, float, bool)):
                    return str(val)
            return match.group(0)
        
        result = re.sub(pattern2, replace_standalone, result)
        
        return result

    def _resolve_properties(self, properties: Dict[str, Any], var_values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Duyệt qua các properties của resource, tìm và thay thế biến.
        Chỉ trả về dict chứa các properties ĐÃ được thay đổi/giải mã.
        """
        resolved = {}
        
        for key, value in properties.items():
            # Bỏ qua các metadata fields
            if key in ['enriched', 'taint_resolved_values', 'taint_resolved_properties', 'id', 'type']:
                continue
            
            resolved_value = None
            
            # Case A: Value là JSON String (Do Memgraph lưu object/list dưới dạng string)
            if isinstance(value, str):
                try:
                    # Thử parse JSON xem có phải là complex structure không
                    if value.strip().startswith(('{', '[')):
                        parsed = json.loads(value)
                        if isinstance(parsed, (dict, list)):
                            resolved_value = self._resolve_nested_value_if_has_var(parsed, var_values)
                        else:
                            # Parse được nhưng là primitive, xử lý như string thường
                            resolved_value = self._resolve_nested_value_if_has_var(value, var_values)
                    else:
                        # String thường
                        resolved_value = self._resolve_nested_value_if_has_var(value, var_values)
                except (json.JSONDecodeError, TypeError):
                    # Không phải JSON, xử lý như string thường
                    resolved_value = self._resolve_nested_value_if_has_var(value, var_values)
            else:
                # Case B: Value là kiểu khác (Dict/List Python nếu driver đã convert, hoặc int/bool)
                resolved_value = self._resolve_nested_value_if_has_var(value, var_values)
            
            # Chỉ lưu nếu có sự thay đổi (giải mã được)
            if resolved_value is not None:
                resolved[key] = resolved_value
        
        return resolved

    def _resolve_nested_value_if_has_var(self, value: Any, var_values: Dict[str, Any]) -> Any:
        """
        Đệ quy xử lý Dict/List lồng nhau.
        Returns: 
            - Giá trị đã giải mã nếu tìm thấy biến.
            - None nếu không có biến nào được giải mã trong nhánh này.
        """
        if isinstance(value, str):
            if self._has_resolved_variable_reference(value, var_values):
                return self._replace_variables_in_string(value, var_values)
            return None
        
        elif isinstance(value, dict):
            resolved_dict = {}
            has_change = False
            for k, v in value.items():
                res = self._resolve_nested_value_if_has_var(v, var_values)
                if res is not None:
                    resolved_dict[k] = res
                    has_change = True
                else:
                    resolved_dict[k] = v # Giữ nguyên giá trị gốc
            return resolved_dict if has_change else None
        
        elif isinstance(value, list):
            resolved_list = []
            has_change = False
            for item in value:
                res = self._resolve_nested_value_if_has_var(item, var_values)
                if res is not None:
                    resolved_list.append(res)
                    has_change = True
                else:
                    resolved_list.append(item)
            return resolved_list if has_change else None
            
        return None

    def _trace_reference_to_value(self, ref_name: str, ref_type: str, visited: Optional[set] = None) -> Optional[Any]:
        """
        Trace một reference (var.xxx hoặc local.xxx) theo REF relationships để tìm giá trị cuối cùng.
        Recursively resolve chain nếu giá trị chứa references khác.
        
        Args:
            ref_name: Tên reference (ví dụ: "project_name" từ "var.project_name")
            ref_type: Loại reference ("var" hoặc "local")
            visited: Set các references đã visit để tránh circular references
        
        Returns:
            Giá trị đã resolve được, hoặc None nếu không tìm thấy
        """
        # Tránh circular references
        if visited is None:
            visited = set()
        
        ref_key = f"{ref_type}.{ref_name}"
        if ref_key in visited:
            return None
        
        visited.add(ref_key)
        
        target_label = f"`{self.path_id}`"
        
        # Tìm node variable/local đầu tiên
        find_node_query = f"""
        MATCH (v:{target_label})
        WHERE (
            ('var' IN labels(v) AND '{ref_type}' = 'var') OR
            ('local' IN labels(v) AND '{ref_type}' = 'local') OR
            (v:Variable AND '{ref_type}' = 'var') OR
            (v:Local AND '{ref_type}' = 'local') OR
            (v.type IN ['variable', 'local', 'var'] AND '{ref_type}' = v.type)
        )
        AND (
            v.name = $ref_name OR
            v.name = $ref_type + '.' + $ref_name OR
            (v.name CONTAINS '.' AND split(v.name, '.')[1] = $ref_name)
        )
        RETURN ID(v) as node_id, v.default as default_val, v.value as value_val, v.name as node_name
        LIMIT 1
        """
        
        records, _, _ = INSTANCE.execute_query(
            find_node_query,
            ref_name=ref_name,
            ref_type=ref_type,
            database_="memgraph"
        )
        
        if not records:
            return None
        
        node_id = records[0]['node_id']
        default_val = records[0].get('default_val')
        value_val = records[0].get('value_val')
        
        # Lấy giá trị của node
        final_val = default_val if default_val is not None else value_val
        if final_val is None:
            return None
        
        # Nếu giá trị sạch (không có references), trả về ngay
        if isinstance(final_val, str) and not ("${" in final_val or "var." in final_val or "local." in final_val):
            return final_val
        
        # Nếu giá trị chứa references, resolve chúng recursively
        if isinstance(final_val, str):
            # Extract references từ giá trị
            nested_refs = self._extract_references_from_text(final_val)
            
            if nested_refs:
                # Build var_values_map từ nested references
                nested_var_values = {}
                for nested_ref_type, nested_ref_name in nested_refs:
                    nested_key = f"{nested_ref_type}.{nested_ref_name}"
                    if nested_key not in visited:  # Tránh circular
                        nested_resolved = self._trace_reference_to_value(nested_ref_name, nested_ref_type, visited.copy())
                        if nested_resolved is not None:
                            nested_var_values[nested_ref_name] = nested_resolved
                
                # Nếu có giá trị nào được resolve, thay thế vào string
                if nested_var_values:
                    resolved_str = self._replace_variables_in_string(final_val, nested_var_values)
                    # Kiểm tra lại xem còn references không
                    if isinstance(resolved_str, str) and not ("${" in resolved_str or "var." in resolved_str or "local." in resolved_str):
                        return resolved_str
        
        # Nếu vẫn không resolve được, thử trace theo REF relationships (fallback)
        trace_query = f"""
        MATCH path = (start:{target_label})-[r:REF*0..10]->(end:{target_label})
        WHERE ID(start) = $node_id
          AND (
            ('var' IN labels(end) OR 'local' IN labels(end) OR 
             end:Variable OR end:Local OR 
             end.type IN ['variable', 'local', 'var'])
          )
          AND (end.default IS NOT NULL OR end.value IS NOT NULL)
        WITH end, length(path) as path_length
        ORDER BY path_length ASC
        LIMIT 1
        RETURN COALESCE(end.default, end.value) as final_value, path_length
        """
        
        trace_records, _, _ = INSTANCE.execute_query(
            trace_query,
            node_id=node_id,
            database_="memgraph"
        )
        
        if trace_records:
            final_value = trace_records[0].get('final_value')
            # Kiểm tra xem giá trị có sạch không (không có references)
            if isinstance(final_value, str) and not ("${" in final_value or "var." in final_value or "local." in final_value):
                return final_value
        
        return None

    def _extract_references_from_text(self, text: str) -> List[tuple]:
        """
        Extract tất cả references (var.xxx, local.xxx) từ một string.
        
        Returns:
            List of tuples: [(ref_type, ref_name), ...]
            Ví dụ: [("var", "project_name"), ("local", "bucket_name")]
        """
        references = []
        
        if not isinstance(text, str):
            return references
        
        # Pattern 1: ${ var.xxx } hoặc ${ local.xxx }
        pattern1 = r'\$\{\s*(var|local|module|data)\.([a-zA-Z0-9_\-]+(?:\.[a-zA-Z0-9_\-]+)*)\s*\}'
        for match in re.finditer(pattern1, text):
            ref_type = match.group(1)
            full_ref_name = match.group(2)
            # Lấy key chính (bỏ qua nested properties)
            main_key = full_ref_name.split('.')[0]
            references.append((ref_type, main_key))
        
        # Pattern 2: Standalone var.xxx hoặc local.xxx
        pattern2 = r'(?<!\$)\b(var|local)\.([a-zA-Z0-9_\-]+)'
        for match in re.finditer(pattern2, text):
            ref_type = match.group(1)
            ref_name = match.group(2)
            references.append((ref_type, ref_name))
        
        return references

    def propagate_constants(self) -> int:
        """
        Thực hiện Constant Propagation qua Graph DB.
        
        APPROACH: Trace theo REF relationships để tìm giá trị cuối cùng.
        1. Parse properties của resources để tìm references (var.xxx, local.xxx)
        2. Với mỗi reference, trace theo REF relationships để tìm node cuối cùng có giá trị
        3. Resolve và update properties
        """
        target_label = f"`{self.path_id}`"
        
        # Get all resources
        resource_query = f"""
        MATCH (r:{target_label})
        WHERE (r:resource OR r:Resource OR r.type = 'resource')
        RETURN ID(r) as resource_id, properties(r) as props
        """
        
        try:
            resource_records, _, _ = INSTANCE.execute_query(resource_query, database_="memgraph")
            
            if not resource_records:
                logger.info("Không tìm thấy resource nào.")
                return 0
            
            updated_count = 0
            
            # Process each resource
            for rec in resource_records:
                r_id = rec['resource_id']
                props = rec['props']
                
                # Build var_values_map cho resource này bằng cách trace references
                var_values_map = {}
                
                # Extract tất cả references từ properties
                for key, value in props.items():
                    if key in ['enriched', 'taint_resolved_values', 'taint_resolved_properties', 'id', 'type']:
                        continue
                    
                    # Convert value to string để extract references
                    if isinstance(value, str):
                        text = value
                    elif isinstance(value, (dict, list)):
                        text = json.dumps(value)
                    else:
                        text = str(value)
                    
                    # Extract references từ text
                    references = self._extract_references_from_text(text)
                    
                    # Trace mỗi reference để tìm giá trị
                    for ref_type, ref_name in references:
                        if ref_name not in var_values_map:
                            resolved_value = self._trace_reference_to_value(ref_name, ref_type)
                            if resolved_value is not None:
                                var_values_map[ref_name] = resolved_value
                
                # Nếu có giá trị nào được resolve, update properties
                if var_values_map:
                    # Resolve properties sử dụng var_values_map
                    resolved_props = self._resolve_properties(props, var_values_map)
                    
                    if resolved_props:
                        json_vals = json.dumps(var_values_map, ensure_ascii=False)
                        json_props = json.dumps(resolved_props, ensure_ascii=False)
                        
                        # Update node
                        update_q = f"""
                        MATCH (r) WHERE ID(r) = {r_id}
                        SET r.taint_resolved_values = $vals,
                            r.taint_resolved_properties = $props
                        """
                        INSTANCE.execute_query(
                            update_q, 
                            vals=json_vals, 
                            props=json_props, 
                            database_="memgraph"
                        )
                        updated_count += 1
            
            return updated_count

        except Exception as e:
            logger.error(f"Lỗi Taint Analysis: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0


def enrich_graph(project_path: str):
    """
    Enrich Variable/Local/Resource Nodes with values from HCL files.
    This function bridges the gap between the structural graph (from terraform graph)
    and the configuration values (from .tf files).
    
    Args:
        project_path: Absolute path to Terraform project directory
    """
    # Path should already be set up at module level, but ensure it's there
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Import Parser
    try:
        from tfparser.parse_tf_properties import parse_terraform_project
    except ImportError:
        logger.error("Could not import parse_terraform_project. Make sure tfparser/parse_tf_properties.py exists.")
        raise
    
    # Initialize Database Connection
    try:
        Initialize()
        logger.info("Connected to Memgraph")
    except Exception as e:
        logger.error(f"Failed to connect to Memgraph: {e}")
        raise
    
    # Calculate Path ID (Must match the one used in phase1_load_graph.py)
    abs_path = os.path.abspath(project_path)
    path_id = GetPathID(abs_path)
    logger.info(f"Enriching Graph for Path ID: {path_id}")
    
    # Parse HCL files to get concrete values
    logger.info(f"Parsing HCL files in: {abs_path}")
    parsed_data = parse_terraform_project(abs_path)
    
    if not parsed_data:
        logger.warning("No data parsed from Terraform files.")
        return
    
    # ==============================================================================
    # ENRICH VARIABLES
    # ==============================================================================
    logger.info("--- Enriching VARIABLES ---")
    vars_updated = 0
    for var_name, data in parsed_data.get('variables', {}).items():
        # Only enrich variables that have explicit default values
        if 'default' not in data or data.get('default') is None:
            logger.debug(f"  - Skipping Variable {var_name} (no default value in parsed data)")
            continue
        
        default_val = data['default']
        # Skip empty strings and empty collections
        if default_val == '' or (isinstance(default_val, (dict, list)) and len(default_val) == 0):
            logger.debug(f"  - Skipping Variable {var_name} (default value is empty)")
            continue
        
        # Prepare value for storage (Memgraph properties must be primitives)
        val = default_val
        if isinstance(val, (dict, list)):
            val = json.dumps(val)  # Use JSON string for complex types
        
        query = """
        MATCH (n)
        WHERE ($pid IN labels(n))
          AND (
              n.type = 'variable' 
              OR 'variable' IN labels(n) 
              OR 'Variable' IN labels(n) 
              OR 'var' IN labels(n) 
              OR n.resource_type = 'var'
          )
          AND (
              n.resource_name = $name 
              OR n.name = $name 
              OR n.name = 'var.' + $name
          )
          AND (n.default IS NULL OR n.default = '')  // Only update if not already set to avoid overwriting
        SET n.default = $val, 
            n.enriched = true,
            n.description = $desc,
            n.var_type = $vtype
        RETURN count(n) as updated
        """
        
        res, _, _ = INSTANCE.execute_query(
            query, 
            pid=path_id, 
            name=var_name, 
            val=val,
            desc=data.get('description', ''),
            vtype=data.get('type', 'string'),
            database_="memgraph"
        )
        
        if res and res[0]['updated'] > 0:
            logger.info(f"  ✓ Updated Variable: {var_name} = {val}")
            vars_updated += 1
        else:
            logger.debug(f"  - Skipped Variable {var_name} (Node not found in Graph or already has default)")
    
    # ==============================================================================
    # ENRICH LOCALS
    # ==============================================================================
    logger.info("--- Enriching LOCALS ---")
    locals_updated = 0
    for local_name, data in parsed_data.get('locals', {}).items():
        val = data.get('value')
        raw_val = data.get('raw_value')
        
        if val is not None:
            if isinstance(val, (dict, list)):
                val = json.dumps(val)
            if isinstance(raw_val, (dict, list)):
                raw_val = json.dumps(raw_val)
            
            query = """
            MATCH (n)
            WHERE ($pid IN labels(n))
              AND (n.type = 'local' OR 'local' IN labels(n) OR 'Local' IN labels(n))
              AND (
                  n.resource_name = $name 
                  OR n.name = $name 
                  OR n.name = 'local.' + $name
              )
            SET n.value = $val, 
                n.raw_value = $raw_val,
                n.enriched = true
            RETURN count(n) as updated
            """
            
            res, _, _ = INSTANCE.execute_query(
                query, 
                pid=path_id, 
                name=local_name, 
                val=str(val),  # Ensure string
                raw_val=str(raw_val),
                database_="memgraph"
            )
            
            if res and res[0]['updated'] > 0:
                logger.info(f"  ✓ Updated Local: {local_name}")
                locals_updated += 1
    
    # ==============================================================================
    # ENRICH RESOURCES
    # ==============================================================================
    logger.info("--- Enriching RESOURCES ---")
    resources_updated = 0
    for res_id, data in parsed_data.get('resources', {}).items():
        res_type = data['type']
        res_name = data['name']
        props = data.get('properties', {})
        
        if not props:
            continue
        
        # Find the specific resource node
        query_match = """
        MATCH (n)
        WHERE ($pid IN labels(n))
          AND n.resource_type = $rtype
          AND n.resource_name = $rname
        RETURN ID(n) as id
        """
        
        records, _, _ = INSTANCE.execute_query(
            query_match,
            pid=path_id,
            rtype=res_type,
            rname=res_name,
            database_="memgraph"
        )
        
        if records:
            node_id = records[0]['id']
            
            # Update properties using helper
            # Clean properties (convert dicts/lists to JSON strings)
            clean_props = {}
            for k, v in props.items():
                if isinstance(v, (dict, list)):
                    clean_props[k] = json.dumps(v)
                else:
                    clean_props[k] = v
            
            # Mark as enriched
            clean_props['enriched'] = True
            
            UpdateNodeProperties(node_id, clean_props, path_id)
            logger.info(f"  ✓ Updated Resource: {res_type}.{res_name}")
            resources_updated += 1
    
    logger.info("="*40)
    logger.info(f"Enrichment Summary for {path_id}:")
    logger.info(f"  Variables Updated: {vars_updated}")
    logger.info(f"  Locals Updated:    {locals_updated}")
    logger.info(f"  Resources Updated: {resources_updated}")
    logger.info("="*40)
    
    # ==============================================================================
    # RUN TAINT ANALYSIS TO RESOLVE VALUES FOR RESOURCES (Step 1 - Preprocessing)
    # ==============================================================================
    logger.info("--- Running Taint Analysis (Preprocessing Step) ---")
    try:
        analyzer = TaintAnalyzer(path_id)
        taint_count = analyzer.run()
        logger.info(f"  ✓ Taint Analysis completed: {taint_count} resources resolved")
        logger.info("  Note: This is a preprocessing step. Exact Matching will use all resource data.")
    except Exception as e:
        logger.warning(f"  ⚠ Taint Analysis failed: {e}")
        logger.warning("  Continuing anyway - Exact Matching can work with raw properties")
        import traceback
        logger.debug(traceback.format_exc())


# Standalone execution (for testing)
if __name__ == "__main__":
    import sys
    
    # Configure logging for standalone test
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    if len(sys.argv) < 2:
        print("Usage: python3 taint_analysis.py <project_path>")
        print("Example: python3 taint_analysis.py /home/thangdd/repos/TerrARA/demo_tf_project")
        sys.exit(1)
    
    project_path = sys.argv[1]
    if not os.path.exists(project_path):
        print(f"Error: Path does not exist: {project_path}")
        sys.exit(1)
    
    enrich_graph(project_path)
