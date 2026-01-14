#!/usr/bin/env python3
"""
Phase 1 Extension: Enrich Variable/Local/Resource Nodes with values from HCL files.
This script bridges the gap between the structural graph (from terraform graph)
and the configuration values (from .tf files).

Usage: python3 phase1_enrich_graph.py <project_path>
"""
import sys
import os
import logging
import json

# 1. Setup paths to import internal modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import utils
try:
    from utils.n4j_helper import Initialize, INSTANCE, GetPathID, UpdateNodeProperties
except ImportError:
    # Fallback if running from a subdirectory
    sys.path.insert(0, os.path.dirname(current_dir))
    from utils.n4j_helper import Initialize, INSTANCE, GetPathID, UpdateNodeProperties

# Import Parser (Assuming it is in tfparser/parse_tf_properties.py)
try:
    from tfparser.parse_tf_properties import parse_terraform_project
except ImportError:
    logging.error("Could not import parse_terraform_project. Make sure tfparser/parse_tf_properties.py exists.")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def enrich_graph(project_path):
    # 2. Initialize Database Connection
    try:
        Initialize()
        logger.info("Connected to Memgraph")
    except Exception as e:
        logger.error(f"Failed to connect to Memgraph: {e}")
        sys.exit(1)

    # 3. Calculate Path ID (Must match the one used in phase1_load_graph.py)
    abs_path = os.path.abspath(project_path)
    path_id = GetPathID(abs_path)
    logger.info(f"Enriching Graph for Path ID: {path_id}")

    # 4. Parse HCL files to get concrete values
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
        if data.get('default') is not None:
            # Prepare value for storage (Memgraph properties must be primitives)
            val = data['default']
            if isinstance(val, (dict, list)):
                val = json.dumps(val) # Use JSON string for complex types
            
            # Query Logic:
            # We look for nodes belonging to this project ($pid)
            # that are of type 'variable'.
            # We match by 'resource_name' (preferred) or variations of 'name'.
            query = """
            MATCH (n)
            WHERE ($pid IN labels(n))
              AND (n.type = 'variable' OR 'variable' IN labels(n) OR 'Variable' IN labels(n)) OR 'var' IN labels(n) OR n.resource_type = 'var'
              AND (
                  n.resource_name = $name 
                  OR n.name = $name 
                  OR n.name = 'var.' + $name
              )
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
                logger.info(f"  ✓ Updated Variable: {var_name}")
                vars_updated += 1
            else:
                logger.debug(f"  - Skipped Variable {var_name} (Node not found in Graph)")

    # ==============================================================================
    # ENRICH LOCALS
    # ==============================================================================
    logger.info("--- Enriching LOCALS ---")
    locals_updated = 0
    for local_name, data in parsed_data.get('locals', {}).items():
        # Locals might not have a simple 'value' if they are expressions, 
        # but parse_terraform_project tries to resolve them.
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
                val=str(val), # Ensure string
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
        # parsed data structure: data['type'], data['name'], data['properties']
        res_type = data['type']
        res_name = data['name']
        props = data.get('properties', {})
        
        if not props:
            continue
            
        # 1. Find the specific resource node
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
            
            # 2. Update properties using helper
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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 phase1_enrich_graph.py <project_path>")
        sys.exit(1)
    
    project_path = sys.argv[1]
    if not os.path.exists(project_path):
        print(f"Error: Path does not exist: {project_path}")
        sys.exit(1)
        
    enrich_graph(project_path)