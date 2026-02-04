#!/usr/bin/env python3
"""
Phase 1 Step 5: Ghost Node Creation (TERRAFORM SYNTAX FIX)

Fixes:
- Prevents internal Terraform references (e.g., 'rule.allow', 'var.ip') from being treated as Domains.
- Extracts ONLY the matched substring (URL/ARN) to avoid duplicates.
- Skips descriptive keys to reduce noise.
"""

import sys
import os
import logging
import json
import re
from typing import List, Dict, Any, Set, Tuple

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from utils.n4j_helper import Initialize, GetPathID, INSTANCE
except ImportError:
    sys.path.insert(0, os.path.dirname(current_dir))
    from utils.n4j_helper import Initialize, GetPathID, INSTANCE

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# REGEX PATTERNS
# ==========================================
PATTERNS = {
    'ARN': r'(arn:aws:[a-z0-9-]+:[a-z0-9-]*:(?:\d{12})?:[a-zA-Z0-9-_\/]+)',
    'URL': r'((?:https?|ftp|jdbc|postgres|mysql|redis|mongodb):\/\/[^\s/$.?#].[^\s"]+)',
    'IP': r'(\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?\b)',
    'DOMAIN': r'([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+)'
}

# --- NEW: BLOCK TERRAFORM SYNTAX ---
# Blocks strings starting with these keywords followed by a dot or underscore
# Examples blocked: rule.allow, var.ip, module.vpc, aws_instance.id
TERRAFORM_SYNTAX_BLOCKER = r'^(rule|var|module|data|resource|aws|local|output|provider|terraform)[\._]'

# IGNORE LISTS
IGNORED_KEYS = {
    'description', 'note', 'comment', 'readme', 'usage', 'version', 
    'parent_id', 'id', 'type', 'source', 'ingress', 'egress' 
}

IGNORED_VALUES = {
    'module.root', 'root', 'terraform', 'provider', 'aws', 
    '0.0.0.0', '127.0.0.1', 'localhost', 'true', 'false', 'null'
}

class GhostNodeCreator:
    def __init__(self, path_id: str):
        self.path_id = path_id

    def flatten_props(self, obj: Any, result: Dict[str, str] = None) -> Dict[str, str]:
        if result is None: result = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in IGNORED_KEYS: continue
                
                if isinstance(v, (dict, list)):
                    self.flatten_props(v, result)
                elif isinstance(v, str):
                    result[k] = v
        elif isinstance(obj, list):
            for item in obj:
                self.flatten_props(item, result)
        return result

    def extract_candidate(self, value: str) -> Tuple[str, str]:
        """
        Extracts valid external candidates, strictly filtering out Terraform syntax.
        """
        if not value or len(value) < 5 or "${" in value: return None, None
        
        # Clean up string
        clean_val = value.strip('",\' ')
        
        # Check Ignore List
        if clean_val in IGNORED_VALUES: return None, None

        # --- FIX: Check Terraform Syntax Blocker FIRST ---
        # If it looks like 'rule.allow' or 'var.something', kill it immediately.
        if re.match(TERRAFORM_SYNTAX_BLOCKER, clean_val.lower()):
            return None, None
        # -------------------------------------------------
        
        # 1. ARN
        match = re.search(PATTERNS['ARN'], clean_val)
        if match: return match.group(1), 'ARN'
        
        # 2. URL
        match = re.search(PATTERNS['URL'], clean_val)
        if match: return match.group(1), 'URL'
        
        # 3. IP
        match = re.search(PATTERNS['IP'], clean_val)
        if match:
            ip = match.group(1)
            if ip.startswith('0.') or ip == '127.0.0.1': return None, None
            return ip, 'IP'
        
        # 4. Domain
        if len(clean_val) < 100 and ' ' not in clean_val:
            match = re.search(PATTERNS['DOMAIN'], clean_val)
            if match:
                domain = match.group(1)
                tld = domain.split('.')[-1]
                
                # Extra safety: Check TLD blacklist
                if tld in ['local', 'internal', 'tf', 'json', 'yaml', 'tpl', 'root', 'backend', 'partner', 'allow', 'deny']: 
                    return None, None
                
                return domain, 'DOMAIN'
            
        return None, None

    def get_internal_resource_names(self) -> Set[str]:
        target_label = f"`{self.path_id}`"
        query = f"""
        MATCH (r:{target_label})
        WHERE (r:resource OR r:Resource)
        RETURN r.name, properties(r) as props, r.taint_resolved_properties as taint_props
        """
        internal_names = set()
        try:
            records, _, _ = INSTANCE.execute_query(query, database_="memgraph")
            for rec in records:
                if rec['r.name']: internal_names.add(rec['r.name'])
                
                props = rec['props'] or {}
                if rec['taint_props']:
                    try: props.update(json.loads(rec['taint_props']))
                    except: pass
                
                for k, v in props.items():
                    if k in ['bucket', 'name', 'identifier', 'function_name', 'id', 'endpoint'] and isinstance(v, str):
                        internal_names.add(v)
            return internal_names
        except Exception:
            return set()

    def create_ghost_node(self, source_id: int, target_value: str, target_type: str, prop_key: str) -> bool:
        target_label = f"`{self.path_id}`"
        
        merge_node_query = f"""
        MERGE (e:ExternalEntity {{name: $val}})
        ON CREATE SET e.entity_type = $type, e.is_external = true, e.label = 'ExternalEntity'
        RETURN ID(e) as ghost_id
        """
        
        link_query = f"""
        MATCH (s:{target_label}), (e:ExternalEntity)
        WHERE ID(s) = $sid AND ID(e) = $gid
        MERGE (s)-[r:REF]->(e)
        SET r.method = 'ghost_node', r.details = $details
        RETURN r
        """
        
        try:
            node_res, _, _ = INSTANCE.execute_query(merge_node_query, val=target_value, type=target_type, database_="memgraph")
            if not node_res: return False
            ghost_id = node_res[0]['ghost_id']
            
            details = f"External dependency found in '{prop_key}' ({target_type})"
            link_res, _, _ = INSTANCE.execute_query(link_query, sid=source_id, gid=ghost_id, details=details, database_="memgraph")
            return len(link_res) > 0
        except Exception as e:
            logger.error(f"Error creating ghost node: {e}")
            return False

    def run(self) -> int:
        internal_names = self.get_internal_resource_names()
        logger.info(f"Loaded {len(internal_names)} internal identifiers for exclusion.")
        
        target_label = f"`{self.path_id}`"
        query = f"""
        MATCH (r:{target_label})
        WHERE (r:resource OR r:Resource)
        RETURN ID(r) as id, r.name as name, properties(r) as props, r.taint_resolved_properties as taint_props
        """
        records, _, _ = INSTANCE.execute_query(query, database_="memgraph")
        
        ghosts_created = 0
        
        for rec in records:
            source_id = rec['id']
            source_name = rec['name']
            
            props = rec.get('props', {})
            if rec.get('taint_props'):
                try: props.update(json.loads(rec['taint_props']))
                except: pass
            
            flat_props = self.flatten_props(props)
            
            for key, raw_value in flat_props.items():
                extracted_val, candidate_type = self.extract_candidate(raw_value)
                
                if not extracted_val: continue
                
                is_internal = False
                for internal in internal_names:
                    if internal in extracted_val: 
                        is_internal = True
                        break
                
                if is_internal: continue

                if self.create_ghost_node(source_id, extracted_val, candidate_type, key):
                    logger.info(f"  👻 Created Ghost Node: {source_name} -> {extracted_val} [{candidate_type}] (from '{key}')")
                    ghosts_created += 1

        return ghosts_created

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 phase1_ghost_node.py <project_path>")
        sys.exit(1)
    
    try:
        Initialize()
        path_id = GetPathID(os.path.abspath(sys.argv[1]))
        logger.info(f"Step 5: Ghost Node Creation (TERRAFORM SYNTAX FIX) for {path_id}")
        
        creator = GhostNodeCreator(path_id)
        count = creator.run()
        
        logger.info("="*60)
        logger.info(f"✓ Step 5 Completed: {count} external/ghost links created.")
        logger.info("="*60)
    except Exception as e:
        logger.error(e)

if __name__ == "__main__":
    main()