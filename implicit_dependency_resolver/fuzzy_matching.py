"""
Logic Module for Step 4: Fuzzy & Heuristic Matching.
Contains the FuzzyMatcher class and heuristic rules.
"""

import logging
import json
import os
import sys
from typing import List, Dict, Any

# Try to use rapidfuzz for better performance (10-100x faster than difflib)
# Fallback to difflib if rapidfuzz is not available
try:
    from rapidfuzz import fuzz
    USE_RAPIDFUZZ = True
except ImportError:
    import difflib
    USE_RAPIDFUZZ = False

# Setup paths to import internal modules BEFORE importing utils
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Now import utils after path is set up
from utils.n4j_helper import INSTANCE

logger = logging.getLogger(__name__)

# Log which library is being used (only log once at module level)
if USE_RAPIDFUZZ:
    logger.debug("Using rapidfuzz for fuzzy matching (fast mode - 10-100x faster)")
else:
    logger.warning(
        "rapidfuzz not found. Install it with 'pip install rapidfuzz' for 10-100x faster fuzzy matching. "
        "Falling back to difflib (slower)."
    )

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
DEFAULT_SIMILARITY_THRESHOLD = 0.85

PROPERTY_TO_RESOURCE_TYPE = {
    'bucket': ['aws_s3_bucket'],
    's3':     ['aws_s3_bucket'],
    'db':       ['aws_db_instance', 'aws_rds_cluster', 'aws_dynamodb_table'],
    'database': ['aws_db_instance', 'aws_rds_cluster'],
    'rds':      ['aws_db_instance', 'aws_rds_cluster'],
    'host':     ['aws_db_instance', 'aws_instance', 'aws_rds_cluster'], 
    'instance': ['aws_instance'],
    'server':   ['aws_instance'],
    'queue': ['aws_sqs_queue'],
    'sqs':   ['aws_sqs_queue'],
    'topic': ['aws_sns_topic'],
    'function': ['aws_lambda_function'],
    'lambda':   ['aws_lambda_function'],
    'role':     ['aws_iam_role'],
    'policy':   ['aws_iam_policy']
}

class FuzzyMatcher:
    def __init__(self, path_id: str, threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
        self.path_id = path_id
        self.threshold = threshold
        
        # Log which library is being used
        if USE_RAPIDFUZZ:
            logger.info("Using rapidfuzz for fuzzy matching (fast mode)")
        else:
            logger.info("Using difflib for fuzzy matching (slow mode - consider installing rapidfuzz)")

    def flatten_props(self, obj: Any, result: Dict[str, str] = None) -> Dict[str, str]:
        """Flatten nested properties into a single-level Dict."""
        if result is None: result = {}
        
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    self.flatten_props(v, result)
                elif isinstance(v, str):
                    result[k] = v
        elif isinstance(obj, list):
            for item in obj:
                self.flatten_props(item, result)
        
        return result

    def build_target_cache(self) -> Dict[str, List[Dict]]:
        """Builds a cache of Target Resources."""
        target_label = f"`{self.path_id}`"
        query = f"""
        MATCH (r:{target_label})
        WHERE (r:resource OR r:Resource OR r.type = 'resource' OR r.resource_type = 'resource')
          AND r.name IS NOT NULL
        RETURN ID(r) as node_id, r.resource_type as type, r.name as logical_name, 
               properties(r) as props, r.taint_resolved_properties as taint_props
        """
        
        try:
            records, _, _ = INSTANCE.execute_query(query, database_="memgraph")
            cache = {}
            count = 0
            
            for rec in records:
                rtype = rec['type']
                if not rtype: continue
                
                names = set()
                names.add(rec['logical_name'])
                
                # Merge props
                raw_props = rec.get('props', {})
                taint_props_str = rec.get('taint_props')
                final_props = raw_props.copy()
                if taint_props_str and isinstance(taint_props_str, str):
                    try: 
                        resolved = json.loads(taint_props_str)
                        if isinstance(resolved, dict): final_props.update(resolved)
                    except: pass
                
                # --- FIX 1: Parse JSON TAGS ---
                # "ép" chuỗi tags thành dict để flatten_props đọc được
                if 'tags' in final_props and isinstance(final_props['tags'], str):
                    try:
                        tags_dict = json.loads(final_props['tags'])
                        if isinstance(tags_dict, dict):
                            final_props['tags'] = tags_dict
                    except: pass # Nếu lỗi thì bỏ qua
                # ------------------------------

                flat_props = self.flatten_props(final_props)
                
                # Whitelist keys (Thêm 'Name', 'tags', 'tag')
                target_keys = [
                    'bucket', 'name', 'identifier', 'function_name', 'id', 'cluster_id',
                    'Name', 'tags', 'tag'
                ]
                
                for key, val in flat_props.items():
                    if key in target_keys or key.lower().endswith('_name'): 
                        if val and isinstance(val, str) and len(val) > 3 and "${" not in val:
                            names.add(val)

                if rtype not in cache: cache[rtype] = []
                for n in names:
                    cache[rtype].append({'id': rec['node_id'], 'name': n, 'full_node_name': rec['logical_name']})
                    count += 1
            
            logger.info(f"Built target cache with {count} entries.")
            return cache
        except Exception as e:
            logger.error(f"Error building target cache: {e}")
            return {}

    def get_potential_target_types(self, property_key: str) -> List[str]:
        key_lower = property_key.lower()
        target_types = set()
        for keyword, types in PROPERTY_TO_RESOURCE_TYPE.items():
            if keyword in key_lower:
                target_types.update(types)
        return list(target_types)

    def calculate_similarity(self, a: str, b: str) -> float:
        """
        Calculate similarity ratio between two strings.
        
        Uses rapidfuzz if available (10-100x faster), otherwise falls back to difflib.
        Both libraries produce identical results for basic ratio calculation.
        
        Args:
            a: First string
            b: Second string
            
        Returns:
            Similarity ratio between 0.0 and 1.0
        """
        if USE_RAPIDFUZZ:
            # rapidfuzz.ratio returns 0-100, convert to 0-1
            return fuzz.ratio(a.lower(), b.lower()) / 100.0
        else:
            # difflib.SequenceMatcher returns 0-1 directly
            return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def create_fuzzy_link(self, source_id: int, target_id: int, score: float, details: str) -> bool:
        """
        Create REF edge from source resource to target resource.
        DEPRECATED: Use batch_create_links() for better performance.
        Kept for backward compatibility.
        """
        # --- FIX 2: CHẶN SELF-LOOP ---
        if source_id == target_id: return False
        # -----------------------------

        target_label = f"`{self.path_id}`"
        
        check_q = f"""
        MATCH (s:{target_label})-[r:REF]->(t:{target_label})
        WHERE ID(s)=$sid AND ID(t)=$tid
        RETURN r
        """
        existing, _, _ = INSTANCE.execute_query(check_q, sid=source_id, tid=target_id, database_="memgraph")
        if existing: return False

        query = f"""
        MATCH (s:{target_label}), (t:{target_label})
        WHERE ID(s)=$sid AND ID(t)=$tid
        MERGE (s)-[r:REF]->(t)
        SET r.method = 'fuzzy_match', r.confidence = $score, r.details = $details
        RETURN r
        """
        res, _, _ = INSTANCE.execute_query(query, sid=source_id, tid=target_id, score=score, details=details, database_="memgraph")
        return len(res) > 0

    def batch_create_links(self, links: List[tuple]) -> int:
        """
        Batch create multiple links in a single transaction for better performance.
        
        Args:
            links: List of tuples (source_id, target_id, source_name, target_name, score, details)
        
        Returns:
            Number of links created
        """
        if not links:
            return 0
        
        target_label = f"`{self.path_id}`"
        
        # Filter out self-loops
        valid_links = [(s, t, n1, n2, sc, d) for s, t, n1, n2, sc, d in links if s != t]
        
        if not valid_links:
            return 0
        
        try:
            # Batch check existing links
            check_query = f"""
            UNWIND $links AS link
            MATCH (s:{target_label})-[r:REF]->(t:{target_label})
            WHERE ID(s) = link.source AND ID(t) = link.target
            RETURN link.source as source, link.target as target
            """
            
            existing_records, _, _ = INSTANCE.execute_query(
                check_query,
                links=[{"source": s, "target": t} for s, t, _, _, _, _ in valid_links],
                database_="memgraph"
            )
            
            existing_pairs = {(r['source'], r['target']) for r in existing_records}
            
            # Filter out existing links
            new_links = [(s, t, n1, n2, sc, d) for s, t, n1, n2, sc, d in valid_links if (s, t) not in existing_pairs]
            
            if not new_links:
                logger.info(f"All {len(valid_links)} links already exist, skipping batch create")
                return 0
            
            # Batch create new links with confidence and details
            create_query = f"""
            UNWIND $links AS link
            MATCH (s:{target_label}), (t:{target_label})
            WHERE ID(s) = link.source AND ID(t) = link.target
            MERGE (s)-[r:REF]->(t)
            SET r.method = 'fuzzy_match',
                r.confidence = link.confidence,
                r.details = link.details
            RETURN count(r) as created
            """
            
            create_records, _, _ = INSTANCE.execute_query(
                create_query,
                links=[{
                    "source": s,
                    "target": t,
                    "confidence": sc,
                    "details": d
                } for s, t, _, _, sc, d in new_links],
                database_="memgraph"
            )
            
            created_count = create_records[0]['created'] if create_records else 0
            
            # Log created links
            for source_id, target_id, source_name, target_name, score, details in new_links[:10]:  # Log first 10
                logger.info(f"  ✓ Fuzzy Link ({score:.2f}): {source_name} -> {target_name} [{details}]")
            if len(new_links) > 10:
                logger.info(f"  ... and {len(new_links) - 10} more links")
            
            return created_count
            
        except Exception as e:
            logger.error(f"Error in batch_create_links: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0

    def run(self) -> int:
        target_cache = self.build_target_cache()
        if not target_cache: return 0
        
        target_label = f"`{self.path_id}`"
        query = f"""
        MATCH (r:{target_label})
        WHERE (r:resource OR r:Resource OR r.type = 'resource' OR r.resource_type = 'resource')
        RETURN ID(r) as id, r.name as name, properties(r) as props, r.taint_resolved_properties as taint_props
        """
        records, _, _ = INSTANCE.execute_query(query, database_="memgraph")
        
        # Collect links to batch create later
        links_to_create = []
        
        for rec in records:
            source_id = rec['id']
            source_name = rec['name']
            
            raw_props = rec.get('props', {})
            taint_props_str = rec.get('taint_props')
            props = raw_props.copy()
            if taint_props_str:
                try: props.update(json.loads(taint_props_str))
                except: pass
            
            flat_props = self.flatten_props(props)
            
            for key, value in flat_props.items():
                if len(value) < 4: continue
                if "${" in value or "arn:" in value or "http" in value: continue

                potential_types = self.get_potential_target_types(key)
                if not potential_types: continue 

                for rtype in potential_types:
                    candidates = target_cache.get(rtype, [])
                    for cand in candidates:
                        target_string = cand['name']
                        if abs(len(value) - len(target_string)) > 4: continue

                        score = self.calculate_similarity(value, target_string)
                        if score >= self.threshold:
                            details = f"Fuzzy matched '{value}' with '{target_string}' via '{key}'"
                            # Collect link for batch creation
                            links_to_create.append((
                                source_id,
                                cand['id'],
                                source_name,
                                cand['full_node_name'],
                                score,
                                details
                            ))
        
        # Batch create all collected links
        if links_to_create:
            logger.info(f"Batch creating {len(links_to_create)} fuzzy links...")
            links_created = self.batch_create_links(links_to_create)
        else:
            logger.info("No fuzzy links to create")
            links_created = 0
        
        return links_created


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
        print("Usage: python3 fuzzy_matching.py <project_path> [threshold]")
        print("Example: python3 fuzzy_matching.py /home/thangdd/repos/TerrARA/demo_tf_project")
        print("Example: python3 fuzzy_matching.py /home/thangdd/repos/TerrARA/demo_tf_project 0.85")
        sys.exit(1)
    
    project_path = os.path.abspath(sys.argv[1])
    
    if not os.path.exists(project_path):
        print(f"Error: Path does not exist: {project_path}")
        sys.exit(1)
    
    # Optional threshold parameter (defaults to 0.85)
    threshold = float(sys.argv[2]) if len(sys.argv) > 2 else None
    
    # Initialize connection
    try:
        Initialize()
        logger.info("Connected to Memgraph")
    except Exception as e:
        logger.error(f"Failed to connect to Memgraph: {e}")
        sys.exit(1)
    
    # Get path ID
    path_id = GetPathID(project_path)
    logger.info(f"Running Fuzzy & Heuristic Matching for Path ID: {path_id}")
    
    # Run Fuzzy & Heuristic Matching
    logger.info("="*60)
    logger.info("STEP 4: FUZZY & HEURISTIC MATCHING - Creating Implicit Dependency Links")
    logger.info("="*60)
    
    try:
        if threshold is not None:
            matcher = FuzzyMatcher(path_id, threshold=threshold)
            logger.info(f"Using custom similarity threshold: {threshold}")
        else:
            matcher = FuzzyMatcher(path_id)
            logger.info(f"Using default similarity threshold: {matcher.threshold}")
        links_created = matcher.run()
        logger.info("="*60)
        logger.info(f"✓ Fuzzy & Heuristic Matching completed: {links_created} implicit links created")
        logger.info("="*60)
    except Exception as e:
        logger.error(f"✗ Fuzzy & Heuristic Matching failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)