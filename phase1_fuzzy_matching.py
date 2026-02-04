#!/usr/bin/env python3
"""
Phase 1 Step 4: Fuzzy & Heuristic Matching - Create Implicit Dependency Links

This script runs after Boundary-aware Substring Matching (Step 3) to create implicit 
dependency links by matching string values with typos, naming convention variations 
(snake_case vs kebab-case), and slight variations using Levenshtein distance/Sequence Matching.

Usage: python3 phase1_fuzzy_matching.py <project_path> [threshold]
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
        print("Usage: python3 phase1_fuzzy_matching.py <project_path> [threshold]")
        print("Example: python3 phase1_fuzzy_matching.py /home/thangdd/repos/TerrARA/demo_tf_project")
        print("Example: python3 phase1_fuzzy_matching.py /home/thangdd/repos/TerrARA/demo_tf_project 0.85")
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
        from implicit_dependency_resolver.fuzzy_matching import FuzzyMatcher
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

if __name__ == "__main__":
    main()
