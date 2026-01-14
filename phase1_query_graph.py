#!/usr/bin/env python3
"""
Phase 1: Query Memgraph database to review Phase 1 output
Usage: python3 phase1_query_graph.py <project_path>
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.n4j_helper import Initialize, GetPathID

def main():
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python3 phase1_query_graph.py <project_path>")
        print("Example: python3 phase1_query_graph.py /home/thangdd/repos/TerrARA/demo_tf_project")
        sys.exit(1)
    
    project_path = os.path.abspath(sys.argv[1])
    
    if not os.path.exists(project_path):
        print(f"Error: Project path not found: {project_path}")
        sys.exit(1)
    
    # Initialize connection
    print("Connecting to Memgraph...")
    INSTANCE = Initialize()
    print("✓ Connected to Memgraph\n")
    
    # Get encoded path ID
    pathID = GetPathID(project_path)
    print(f"Querying graph for path ID: {pathID}\n")
    
    # Query 1: List all nodes
    print("=" * 80)
    print("ALL NODES")
    print("=" * 80)
    # Use backticks to escape label with dots
    records, _, _ = INSTANCE.execute_query(
        f"MATCH (n:`{pathID}`) RETURN ID(n) as id, n.type as type, n.name as name, labels(n) as labels ORDER BY n.type, n.name",
        database_="memgraph"
    )
    
    if not records:
        print("No nodes found. Make sure Phase 1 has been executed.")
        return
    
    for r in records:
        labels_str = ", ".join([l for l in r['labels'] if l != pathID])
        print(f"ID: {r['id']:4d} | Type: {r['type']:20s} | Name: {r['name']:30s} | Labels: {labels_str}")
    
    # Query 2: List all edges
    print("\n" + "=" * 80)
    print("ALL EDGES (DEPENDENCIES)")
    print("=" * 80)
    # Use backticks to escape label with dots
    records, _, _ = INSTANCE.execute_query(
        f"MATCH (a:`{pathID}`)-[r:REF]->(b:`{pathID}`) RETURN ID(a) as from_id, a.type as from_type, a.name as from_name, ID(b) as to_id, b.type as to_type, b.name as to_name ORDER BY a.type, a.name",
        database_="memgraph"
    )
    
    if not records:
        print("No edges found.")
    else:
        for r in records:
            from_label = f"{r['from_type']}.{r['from_name']}" if r['from_name'] else r['from_type']
            to_label = f"{r['to_type']}.{r['to_name']}" if r['to_name'] else r['to_type']
            print(f"{from_label:40s} → {to_label}")
    
    # Query 3: Statistics
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)
    
    # Use backticks to escape label with dots
    records, _, _ = INSTANCE.execute_query(
        f"MATCH (n:`{pathID}`) RETURN count(n) as node_count",
        database_="memgraph"
    )
    node_count = records[0]['node_count'] if records else 0
    
    records, _, _ = INSTANCE.execute_query(
        f"MATCH ()-[r:REF]->() RETURN count(r) as edge_count",
        database_="memgraph"
    )
    edge_count = records[0]['edge_count'] if records else 0
    
    records, _, _ = INSTANCE.execute_query(
        f"MATCH (n:`{pathID}`) RETURN DISTINCT n.type as type, count(*) as count ORDER BY count DESC",
        database_="memgraph"
    )
    
    print(f"Total nodes: {node_count}")
    print(f"Total edges: {edge_count}")
    print(f"\nNodes by type:")
    for r in records:
        print(f"  {r['type']:20s}: {r['count']:3d}")
    
    # Query 4: Dependency chains
    print("\n" + "=" * 80)
    print("DEPENDENCY CHAINS")
    print("=" * 80)
    
    # Use backticks to escape label with dots
    records, _, _ = INSTANCE.execute_query(
        f"""
        MATCH path = (a:`{pathID}`)-[:REF*]->(b:`{pathID}`)
        WHERE a.type = 'aws_instance' OR a.type = 'aws_s3_bucket'
        RETURN a.type as from_type, a.name as from_name, 
               [node in nodes(path) | node.type + '.' + node.name] as path_nodes
        ORDER BY length(path) DESC
        LIMIT 10
        """,
        database_="memgraph"
    )
    
    if records:
        for r in records:
            from_label = f"{r['from_type']}.{r['from_name']}" if r['from_name'] else r['from_type']
            path_str = " → ".join(r['path_nodes'])
            print(f"{from_label:40s} → {path_str}")
    else:
        print("No dependency chains found.")
    
    print("\n" + "=" * 80)
    print("To visualize the graph, open Memgraph Lab: http://localhost:3000")
    print("=" * 80)

if __name__ == "__main__":
    main()

