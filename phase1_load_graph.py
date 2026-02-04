#!/usr/bin/env python3
"""
Phase 1: Load JSON graph into Memgraph database
Usage: python3 phase1_load_graph.py <json_file_path> <project_path>
"""
import json
import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.n4j_helper import (
    Initialize, CreateNode, AddConnection, GetPathID, CleanUp
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Parse arguments
    if len(sys.argv) < 3:
        print("Usage: python3 phase1_load_graph.py <json_file_path> <project_path>")
        sys.exit(1)
    
    json_path = sys.argv[1]
    project_path = os.path.abspath(sys.argv[2])
    
    if not os.path.exists(json_path):
        print(f"Error: JSON file not found: {json_path}")
        sys.exit(1)
    
    # Initialize connection
    print("Connecting to Memgraph...")
    Initialize()
    print("✓ Connected to Memgraph")
    
    # Clean up previous data
    print("\nCleaning up previous data...")
    CleanUp()
    print("✓ Database cleaned")
    
    # Load JSON file
    print(f"\nLoading JSON file: {json_path}")
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to read JSON file: {e}")
        sys.exit(1)
    
    if data is None:
        print("Error: JSON file is empty or contains null")
        sys.exit(1)
    
    # Handle case where nodes/edges might be None in JSON
    nodes = data.get('nodes') or []
    edges = data.get('edges') or []
    print(f"✓ Loaded {len(nodes)} nodes, {len(edges)} edges")
    
    # Get encoded path ID
    pathID = GetPathID(project_path)
    print(f"\nPath ID: {pathID}")
    
    # Create node mapping
    nodeInvMap = {}
    
    # --- CREATING NODES (ONLY FROM JSON) ---
    print("\n=== Creating Nodes from JSON ===")
    for node in nodes:
        source = node["data"]
        
        # 1. Parse basic info from label
        # Example label: "aws_security_group.allow_tls" or "var.region"
        raw_label = source.get("label", "")
        label_parts = raw_label.split(".")
        
        resource_type = label_parts[0] if len(label_parts) > 0 else "unknown"
        resource_name = ".".join(label_parts[1:]) if len(label_parts) > 1 else ""
        
        # 2. Prepare Properties Dictionary
        node_props = {
            "parent_id": source.get("parent", ""),
            "resource_type": resource_type,
            "resource_name": resource_name,
            "label": raw_label, # Keep original label for debugging
            "name": raw_label   # Important: Set 'name' to label for matching in Enrich phase
        }

        # 3. Flatten 'attributes' (if any exist in JSON from beautifier)
        if "attributes" in source and isinstance(source["attributes"], dict):
            for k, v in source["attributes"].items():
                if isinstance(v, (dict, list)):
                    node_props[k] = json.dumps(v)
                else:
                    node_props[k] = v
        
        # 4. Fallback attributes
        if "default" in source and "default" not in node_props:
            node_props["default"] = source["default"]
        if "value" in source and "value" not in node_props:
            node_props["value"] = source["value"]

        # 5. Determine Labels
        # Convention: [pathID, "resource_type"]
        node_type = source.get("type", "unknown")
        labels = [pathID, node_type]
        
        # Add 'Variable' or 'Local' label if type matches (helps in querying)
        if node_type == 'variable' or resource_type == 'var':
            labels.append('Variable')
        if node_type == 'local' or resource_type == 'local':
            labels.append('Local')

        # 6. Create Node
        # We use CreateNode (wrapper for CREATE) because we just cleaned the DB
        try:
            # Note: We pass node_props containing 'resource_type' etc, 
            # but CreateNode expects specific keys in the second argument dictionary.
            # Let's use a generic property creation to be safe, or stick to n4j_helper's CreateNode signature
            
            # Since n4j_helper.CreateNode expects specific keys (parent_id, resource_type, resource_name),
            # we pass node_props which has them.
            # BUT, to store EXTRA properties (like 'label', 'default'), we need CreateNodeWithProperties
            # or Update afterwards.
            
            # OPTION: Use CreateNodeWithProperties directly for everything to be flexible
            from utils.n4j_helper import CreateNodeWithProperties
            node_id = CreateNodeWithProperties(labels, node_props, pathID)
            
            nodeInvMap[source["id"]] = node_id
            # print(f"  ✓ Created: {raw_label:40s} → ID: {node_id}")
        except Exception as e:
            print(f"  ✗ Failed to create node {raw_label}: {e}")
    
    print(f"Total nodes created: {len(nodeInvMap)}")

    # --- CREATING EDGES ---
    print("\n=== Creating Edges from JSON ===")
    edge_count = 0
    if edges:
        for edge in edges:
            source_key = edge["data"]["source"]
            target_key = edge["data"]["target"]
            
            source_id = nodeInvMap.get(source_key)
            target_id = nodeInvMap.get(target_key)
            
            if source_id is not None and target_id is not None:
                try:
                    AddConnection(source_id, target_id, pathID)
                    edge_count += 1
                except Exception as e:
                    print(f"  ✗ Failed to link {source_key} -> {target_key}: {e}")
            else:
                # print(f"  ✗ Skipped link (node missing): {source_key} -> {target_key}")
                pass
    
    print(f"Total edges created: {edge_count}")
    print(f"\n=== Phase 1 Load Complete ===")
    print("Next step: Run phase1_enrich_graph.py to populate variables/locals values.")

if __name__ == "__main__":
    main()