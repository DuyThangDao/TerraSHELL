"""
Exact Matching Module - Step 2 of Implicit Dependency Resolution Pipeline

Matches resolved string values (from Step 1 Taint Analysis) against resource names
to create missing dependency links through exact string matching.

This is the "Happy Path" - handles cases where developers use hardcoded strings
that exactly match resource names (Logical or Physical), but forgot to use Terraform reference syntax.
"""

import logging
import json
import re
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


class ExactMatcher:
    def __init__(self, path_id: str, case_sensitive: bool = False):
        """
        Initialize Exact Matcher for implicit dependency resolution.
        
        Args:
            path_id: Path ID of the project (used for graph queries)
            case_sensitive: Whether matching should be case-sensitive (default: False)
        """
        self.path_id = path_id
        self.case_sensitive = case_sensitive

    def build_symbol_table(self) -> Dict[str, Dict[str, Any]]:
        """
        Build enriched symbol table mapping resource names AND physical IDs to metadata.
        
        Improvements:
        - Includes Logical IDs (e.g., "aws_s3_bucket.main")
        - Includes Physical IDs (e.g., "my-prod-bucket", "order-queue") extracted from 
          taint_resolved_properties (prioritized) or raw properties.
        """
        target_label = f"`{self.path_id}`"
        
        # 1. CẬP NHẬT QUERY: Lấy thêm taint_resolved_properties để có Physical ID chính xác nhất
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
                name_property = record.get('name', '')
                resource_name = record.get('resource_name', '')
                # Ưu tiên lấy resource_type chuẩn
                resource_type = record.get('resource_type') or record.get('resource_type_alt', '')
                
                # --- PHẦN 1: LOGICAL ID INDEXING ---
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
                    'full_name': full_name, # Tên hiển thị khi match
                    'base_name': base_name
                }
                
                # Helper function để add vào bảng
                def add_to_table(key_string):
                    if not key_string or not isinstance(key_string, str): return
                    
                    key_full = key_string if self.case_sensitive else key_string.lower()
                    
                    # Chỉ add nếu chưa tồn tại hoặc ưu tiên Logical Name chính xác hơn
                    if key_full not in symbol_table:
                        symbol_table[key_full] = metadata
                
                # Add Logical Names
                add_to_table(full_name)
                add_to_table(base_name)
                
                # --- PHẦN 2: PHYSICAL ID INDEXING (ENRICHMENT) ---
                # Logic: Merge Raw Properties với Resolved Properties (ưu tiên Resolved)
                # để lấy được tên thật của resource (ví dụ: tên bucket sau khi giải biến)
                
                raw_props = record.get('raw_props', {})
                taint_props_str = record.get('taint_props')
                
                final_props = raw_props.copy()
                
                # Parse taint_props nếu có
                if taint_props_str and isinstance(taint_props_str, str):
                    try:
                        resolved_props = json.loads(taint_props_str)
                        if isinstance(resolved_props, dict):
                            final_props.update(resolved_props)
                    except (json.JSONDecodeError, TypeError):
                        pass

                physical_ids = []
                rtype_lower = str(resource_type).lower()
                
                # Trích xuất Physical ID dựa trên loại Resource
                # Bạn có thể mở rộng danh sách này cho các resource khác
                if 's3_bucket' in rtype_lower:
                    physical_ids.append(final_props.get('bucket'))
                elif 'sqs_queue' in rtype_lower:
                    physical_ids.append(final_props.get('name'))
                elif 'dynamodb_table' in rtype_lower:
                    physical_ids.append(final_props.get('name'))
                elif 'lambda_function' in rtype_lower:
                    physical_ids.append(final_props.get('function_name'))
                elif 'rds_cluster' in rtype_lower or 'db_instance' in rtype_lower:
                    physical_ids.append(final_props.get('identifier'))
                elif 'iam_role' in rtype_lower:
                    physical_ids.append(final_props.get('name'))
                elif 'kinesis_stream' in rtype_lower:
                    physical_ids.append(final_props.get('name'))
                elif 'sns_topic' in rtype_lower:
                    physical_ids.append(final_props.get('name'))
                
                # Add Physical IDs vào bảng
                for pid in physical_ids:
                    if pid and isinstance(pid, str):
                        # Logic lọc rác: Chỉ add nếu tên đủ dài và không chứa ký tự template ${}
                        # Nếu vẫn còn ${}, nghĩa là Step 1 chưa resolve được, ta không nên index chuỗi rác này
                        if len(pid) > 3 and "${" not in pid and "var." not in pid:
                            add_to_table(pid)
                            # Uncomment để debug xem nó index những gì
                            # logger.debug(f"Added Physical ID: {pid} -> {full_name}")

            logger.info(f"Built enriched symbol table with {len(symbol_table)} entries from {len(records)} resources")
            return symbol_table
            
        except Exception as e:
            logger.error(f"Error building symbol table: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}

    def extract_string_values(self, resolved_properties: dict) -> List[str]:
        """
        Recursively extract all string values from resolved properties.
        
        Filters out:
        - Empty strings
        - Complex strings (ARNs, URLs) that should be handled by Step 3
        - Non-identifier strings
        
        Args:
            resolved_properties: Dictionary of resolved properties (from taint_resolved_properties)
            
        Returns:
            List of candidate strings to match against resource names
        """
        strings = []
        
        def is_identifier_string(s: str) -> bool:
            """Check if string looks like a simple identifier (not ARN, URL, etc.)"""
            if not s or len(s) < 2: # Tăng min length lên 2
                return False
            
            # Filter out ARNs (arn:aws:...) - Để Step 3 xử lý
            if s.startswith('arn:'):
                return False
            
            # Filter out URLs (http://, https://) - Để Step 3 xử lý
            if s.startswith('http://') or s.startswith('https://'):
                return False
            
            # Filter out email addresses
            if '@' in s and '.' in s:
                return False
            
            # Filter out IP addresses (basic check)
            if re.match(r'^\d+\.\d+\.\d+\.\d+', s):
                return False
            
            # Filter out very long strings (likely complex identifiers or descriptions)
            if len(s) > 100:
                return False
            
            # Filter out template strings that Step 1 failed to resolve
            if "${" in s:
                return False

            return True
        
        def extract_recursive(value: Any) -> None:
            """Recursively extract strings from nested structures"""
            if isinstance(value, str):
                if is_identifier_string(value):
                    strings.append(value)
            elif isinstance(value, dict):
                for v in value.values():
                    extract_recursive(v)
            elif isinstance(value, list):
                for item in value:
                    extract_recursive(item)
        
        extract_recursive(resolved_properties)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_strings = []
        for s in strings:
            normalized = s.lower() if not self.case_sensitive else s
            if normalized not in seen:
                seen.add(normalized)
                unique_strings.append(s)
        
        return unique_strings

    def find_matching_resources(self, source_string: str, symbol_table: dict) -> List[Dict[str, Any]]:
        """
        Find resources in symbol table that match the source string.
        """
        matches = []
        
        if not source_string:
            return matches
        
        # Normalize source string for matching
        search_key = source_string if self.case_sensitive else source_string.lower()
        
        # Try exact match
        if search_key in symbol_table:
            matches.append(symbol_table[search_key])
        
        # Also try matching against original case versions if case-insensitive
        if not self.case_sensitive:
            if source_string in symbol_table:
                # Avoid duplicates if search_key == source_string
                if source_string != search_key:
                    matches.append(symbol_table[source_string])
        
        return matches

    def create_implicit_links(self, source_resource_id: int, target_resource_id: int) -> bool:
        """
        Create REF edge from source resource to target resource.
        """
        if source_resource_id == target_resource_id:
            return False  # Don't create self-loops
        
        target_label = f"`{self.path_id}`"
        
        # Check if edge already exists
        check_query = f"""
        MATCH (source:{target_label})-[r:REF]->(target:{target_label})
        WHERE ID(source) = $source_id AND ID(target) = $target_id
        RETURN r
        LIMIT 1
        """
        
        try:
            records, _, _ = INSTANCE.execute_query(
                check_query,
                source_id=source_resource_id,
                target_id=target_resource_id,
                database_="memgraph"
            )
            
            if records:
                return False  # Edge already exists
            
            # Create edge using MERGE to avoid duplicates
            # Added property 'method' to track how this link was found
            create_query = f"""
            MATCH (source:{target_label}), (target:{target_label})
            WHERE ID(source) = $source_id AND ID(target) = $target_id
            MERGE (source)-[r:REF]->(target)
            SET r.method = 'implicit_exact_match'
            RETURN r
            """
            
            create_records, _, _ = INSTANCE.execute_query(
                create_query,
                source_id=source_resource_id,
                target_id=target_resource_id,
                database_="memgraph"
            )
            
            return len(create_records) > 0
            
        except Exception as e:
            logger.warning(f"Error creating link from {source_resource_id} to {target_resource_id}: {e}")
            return False

    def _get_resource_properties(self, node_props: dict) -> dict:
        """
        Extract properties dictionary from node properties, filtering out metadata fields.
        """
        exclude_fields = {
            'enriched', 'taint_resolved_values', 'taint_resolved_properties',
            'parent_id', 'resource_type', 'resource_name', 'name', 'label',
            'type', 'id'
        }
        
        properties = {}
        for key, value in node_props.items():
            if key not in exclude_fields:
                if isinstance(value, str):
                    if value.strip().startswith(('{', '[')):
                        try:
                            parsed = json.loads(value)
                            properties[key] = parsed
                        except (json.JSONDecodeError, ValueError):
                            properties[key] = value
                    else:
                        properties[key] = value
                else:
                    properties[key] = value
        
        return properties
    
    def _extract_properties_from_node(self, node_props: dict) -> dict:
        """
        Extract properties from node, prioritizing taint_resolved_properties if available.
        """
        # Priority 1: Use taint_resolved_properties
        if 'taint_resolved_properties' in node_props and node_props['taint_resolved_properties']:
            try:
                resolved_props_json = node_props['taint_resolved_properties']
                if isinstance(resolved_props_json, str):
                    resolved_props = json.loads(resolved_props_json)
                else:
                    resolved_props = resolved_props_json
                
                if resolved_props and isinstance(resolved_props, dict):
                    return resolved_props
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug(f"Failed to parse taint_resolved_properties: {e}")
        
        # Priority 2: Fallback to raw resource properties
        raw_properties = self._get_resource_properties(node_props)
        if raw_properties:
            return raw_properties
        
        return {}

    def run(self) -> int:
        """
        Main execution method for exact matching.
        """
        logger.info(f"--- Starting Exact Matching for Project: {self.path_id} ---")
        
        # Step 1: Build symbol table (Enriched with Physical IDs)
        symbol_table = self.build_symbol_table()
        if not symbol_table:
            logger.warning("Symbol table is empty, cannot perform matching")
            return 0
        
        # Step 2: Query ALL resources
        target_label = f"`{self.path_id}`"
        
        query = f"""
        MATCH (r:{target_label})
        WHERE (r:resource OR r:Resource OR r.type = 'resource' OR r.resource_type = 'resource')
        RETURN ID(r) as resource_id,
               r.name as resource_name,
               properties(r) as node_properties
        """
        
        try:
            records, _, _ = INSTANCE.execute_query(query, database_="memgraph")
            
            if not records:
                logger.info("No resources found in graph")
                return 0
            
            logger.info(f"Found {len(records)} resources to scan for outgoing links")
            
            links_created = 0
            resources_with_properties = 0
            
            # Step 3: Process each resource
            for record in records:
                source_resource_id = record['resource_id']
                resource_name = record.get('resource_name', 'unknown')
                node_properties = record.get('node_properties', {})
                
                if not node_properties:
                    continue
                
                try:
                    # Extract properties (prioritize taint_resolved_properties)
                    properties = self._extract_properties_from_node(node_properties)
                    
                    if not properties:
                        continue
                    
                    resources_with_properties += 1
                    
                    # Extract string values from properties
                    candidate_strings = self.extract_string_values(properties)
                    
                    # Match each string against symbol table
                    for source_string in candidate_strings:
                        matches = self.find_matching_resources(source_string, symbol_table)
                        
                        for match in matches:
                            target_resource_id = match['node_id']
                            target_name = match['full_name']
                            
                            # Skip self-loops
                            if source_resource_id == target_resource_id:
                                continue
                            
                            # Create link
                            if self.create_implicit_links(source_resource_id, target_resource_id):
                                links_created += 1
                                logger.info(
                                    f"  ✓ Created link: {resource_name} -> {target_name} "
                                    f"(matched string: '{source_string}')"
                                )
                
                except Exception as e:
                    logger.warning(f"Error processing resource {resource_name}: {e}")
                    continue
            
            logger.info(f"Processed {resources_with_properties} resources with extractable properties")
            logger.info(f"--- Exact Matching completed. Created {links_created} implicit links. ---")
            return links_created
            
        except Exception as e:
            logger.error(f"Error during exact matching: {e}")
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
        print("Usage: python3 exact_matching.py <project_path>")
        print("Example: python3 exact_matching.py /home/thangdd/repos/TerrARA/demo_tf_project")
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
    logger.info(f"Running Exact Matching for Path ID: {path_id}")
    
    # Run Exact Matching
    logger.info("="*60)
    logger.info("STEP 2: EXACT MATCHING - Creating Implicit Dependency Links")
    logger.info("="*60)
    
    try:
        matcher = ExactMatcher(path_id, case_sensitive=False)
        links_created = matcher.run()
        logger.info("="*60)
        logger.info(f"✓ Exact Matching completed: {links_created} implicit links created")
        logger.info("="*60)
    except Exception as e:
        logger.error(f"✗ Exact Matching failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)