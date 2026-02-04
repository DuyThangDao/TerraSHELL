#!/usr/bin/env python3
"""
Phase 1 Step 5: Ghost Node Creation - Create External Entity Nodes

This script runs after Fuzzy & Heuristic Matching (Step 4) to detect external dependencies
(APIs, SaaS, Legacy DBs, Cross-account resources) that are NOT managed by the current 
Terraform project and creates 'ExternalEntity' nodes.

Usage: python3 phase1_ghost_node_creation.py <project_path>
"""
import sys
import os
import logging

# Setup paths to import internal modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import utils
try:
    from utils.n4j_helper import Initialize, GetPathID
except ImportError:
    sys.path.insert(0, os.path.dirname(current_dir))
    from utils.n4j_helper import Initialize, GetPathID

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python3 phase1_ghost_node_creation.py <project_path>")
        print("Example: python3 phase1_ghost_node_creation.py /home/thangdd/repos/TerrARA/demo_tf_project")
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
    logger.info(f"Running Ghost Node Creation for Path ID: {path_id}")
    
    # Run Ghost Node Creation
    logger.info("="*60)
    logger.info("STEP 5: GHOST NODE CREATION - Creating External Entity Nodes")
    logger.info("="*60)
    
    try:
        from implicit_dependency_resolver.ghost_node_creation import GhostNodeCreator
        creator = GhostNodeCreator(path_id)
        ghosts_created = creator.run()
        logger.info("="*60)
        logger.info(f"✓ Ghost Node Creation completed: {ghosts_created} external/ghost links created")
        logger.info("="*60)
    except Exception as e:
        logger.error(f"✗ Ghost Node Creation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
