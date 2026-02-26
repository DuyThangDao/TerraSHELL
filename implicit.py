#!/usr/bin/env python3
"""
Implicit Dependency Resolution Module

Consolidates all 4 steps of implicit dependency resolution into a single module
for easy integration into main.py. This module can be called directly or used
as a library.

Usage in main.py:
    from implicit import run_implicit_dependency_resolution
    run_implicit_dependency_resolution(project_path, path_id)
"""

import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def run_implicit_enrich_only(project_path: str) -> Dict[str, int]:
    """
    Phase 1.5a: Enrich Graph with HCL Properties + Taint Analysis ONLY.
    
    This function ONLY enriches properties (decodes variables/locals) and stores
    them in nodes. It does NOT create any edges.
    
    Should be called BEFORE Tag/RemoveNonTagged to ensure all nodes have
    enriched properties before non-tagged nodes are deleted.
    
    Args:
        project_path: Absolute path to Terraform project directory
        
    Returns:
        Dictionary with enrich count: {'enrich': 1}
    """
    results = {'enrich': 0}
    
    logger.info("="*70)
    logger.info("PHASE 1.5a: ENRICH GRAPH (Properties Only)")
    logger.info("="*70)
    
    logger.info("[1/1] Enriching graph with HCL properties...")
    from implicit_dependency_resolver.taint_analysis import enrich_graph
    enrich_graph(project_path)
    results['enrich'] = 1
    
    logger.info("✓ Enrich completed: Properties decoded and stored in nodes")
    logger.info("="*70)
    
    return results


def run_implicit_matching_only(
    path_id: str,
    enable_exact: bool = True,
    enable_boundary: bool = True,
    enable_fuzzy: bool = True,
    fuzzy_threshold: Optional[float] = None,
    case_sensitive: bool = False
) -> Dict[str, int]:
    """
    Phase 1.5b: Implicit Matching ONLY (Exact, Boundary, Fuzzy).
    
    This function ONLY creates REF edges between tagged nodes based on
    matching algorithms. It does NOT enrich properties.
    
    Should be called AFTER Compress to ensure edges are created at the
    compressed level, not at granular resource level.
    
    Args:
        path_id: Path ID from graph database (from GetPathID)
        enable_exact: Enable Exact Matching
        enable_boundary: Enable Boundary-aware Matching
        enable_fuzzy: Enable Fuzzy Matching
        fuzzy_threshold: Custom threshold for fuzzy matching (default: 0.90)
        case_sensitive: Whether matching should be case-sensitive
        
    Returns:
        Dictionary with counts for each matching step:
        {
            'exact': count,
            'boundary': count,
            'fuzzy': count
        }
    """
    results = {
        'exact': 0,
        'boundary': 0,
        'fuzzy': 0
    }
    
    logger.info("="*70)
    logger.info("PHASE 1.5b: IMPLICIT MATCHING (Edges Only)")
    logger.info("="*70)
    
    # ========================================================================
    # STEP 1: Exact Matching
    # ========================================================================
    if enable_exact:
        logger.info("[1/3] Running Exact Matching...")
        from implicit_dependency_resolver.exact_matching import ExactMatcher
        matcher = ExactMatcher(path_id, case_sensitive=case_sensitive)
        results['exact'] = matcher.run()
        logger.info(f"✓ Exact: {results['exact']} links created")
    else:
        logger.info("[1/3] Skipping Exact Matching (disabled)")
    
    # ========================================================================
    # STEP 2: Boundary-aware Substring Matching
    # ========================================================================
    if enable_boundary:
        logger.info("[2/3] Running Boundary-aware Matching...")
        from implicit_dependency_resolver.boundary_aware_matching import BoundaryAwareMatcher
        matcher = BoundaryAwareMatcher(path_id, case_sensitive=case_sensitive)
        results['boundary'] = matcher.run()
        logger.info(f"✓ Boundary: {results['boundary']} links created")
    else:
        logger.info("[2/3] Skipping Boundary-aware Matching (disabled)")
    
    # ========================================================================
    # STEP 3: Fuzzy & Heuristic Matching
    # ========================================================================
    if enable_fuzzy:
        logger.info("[3/3] Running Fuzzy Matching...")
        from implicit_dependency_resolver.fuzzy_matching import FuzzyMatcher
        if fuzzy_threshold is not None:
            matcher = FuzzyMatcher(path_id, threshold=fuzzy_threshold)
            logger.info(f"Using custom fuzzy threshold: {fuzzy_threshold}")
        else:
            matcher = FuzzyMatcher(path_id)
            logger.info(f"Using default fuzzy threshold: {matcher.threshold}")
        results['fuzzy'] = matcher.run()
        logger.info(f"✓ Fuzzy: {results['fuzzy']} links created")
    else:
        logger.info("[3/3] Skipping Fuzzy Matching (disabled)")
    
    # ========================================================================
    # Summary
    # ========================================================================
    total_links = results['exact'] + results['boundary'] + results['fuzzy']
    logger.info("="*70)
    logger.info("IMPLICIT MATCHING SUMMARY")
    logger.info("="*70)
    logger.info(f"  Exact links:    {results['exact']:4d}")
    logger.info(f"  Boundary links: {results['boundary']:4d}")
    logger.info(f"  Fuzzy links:    {results['fuzzy']:4d}")
    logger.info(f"  Total implicit links: {total_links}")
    logger.info("="*70)
    
    return results


def run_implicit_dependency_resolution(
    project_path: str,
    path_id: str,
    enable_enrich: bool = True,
    enable_exact: bool = True,
    enable_boundary: bool = True,
    enable_fuzzy: bool = True,
    fuzzy_threshold: Optional[float] = None,
    case_sensitive: bool = False
) -> Dict[str, int]:
    """
    Run complete implicit dependency resolution pipeline (4 steps).
    
    Args:
        project_path: Absolute path to Terraform project
        path_id: Path ID from graph database (from GetPathID)
        enable_enrich: Enable Step 1 (Enrich Graph + Taint Analysis)
        enable_exact: Enable Step 2 (Exact Matching)
        enable_boundary: Enable Step 3 (Boundary-aware Matching)
        enable_fuzzy: Enable Step 4 (Fuzzy Matching)
        fuzzy_threshold: Custom threshold for fuzzy matching (default: 0.85)
        case_sensitive: Whether matching should be case-sensitive
        
    Returns:
        Dictionary with counts for each step:
        {
            'enrich': count,
            'exact': count,
            'boundary': count,
            'fuzzy': count
        }
    """
    results = {
        'enrich': 0,
        'exact': 0,
        'boundary': 0,
        'fuzzy': 0
    }
    
    logger.info("="*70)
    logger.info("PHASE 1.5: IMPLICIT DEPENDENCY RESOLUTION")
    logger.info("="*70)
    
    # ========================================================================
    # STEP 1: Enrich Graph with HCL Properties + Taint Analysis
    # ========================================================================
    if enable_enrich:
        logger.info("[1/4] Enriching graph with HCL properties...")
        from implicit_dependency_resolver.taint_analysis import enrich_graph
        enrich_graph(project_path)
        results['enrich'] = 1  # enrich_graph doesn't return count, just success
        logger.info("✓ Step 1 completed: Graph enriched with properties")
    else:
        logger.info("[1/4] Skipping Enrich Graph (disabled)")
    
    # ========================================================================
    # STEP 2: Exact Matching
    # ========================================================================
    if enable_exact:
        logger.info("[2/4] Running Exact Matching...")
        from implicit_dependency_resolver.exact_matching import ExactMatcher
        matcher = ExactMatcher(path_id, case_sensitive=case_sensitive)
        results['exact'] = matcher.run()
        logger.info(f"✓ Step 2 completed: {results['exact']} exact links created")
    else:
        logger.info("[2/4] Skipping Exact Matching (disabled)")
    
    # ========================================================================
    # STEP 3: Boundary-aware Substring Matching
    # ========================================================================
    if enable_boundary:
        logger.info("[3/4] Running Boundary-aware Matching...")
        from implicit_dependency_resolver.boundary_aware_matching import BoundaryAwareMatcher
        matcher = BoundaryAwareMatcher(path_id, case_sensitive=case_sensitive)
        results['boundary'] = matcher.run()
        logger.info(f"✓ Step 3 completed: {results['boundary']} boundary links created")
    else:
        logger.info("[3/4] Skipping Boundary-aware Matching (disabled)")
    
    # ========================================================================
    # STEP 4: Fuzzy & Heuristic Matching
    # ========================================================================
    if enable_fuzzy:
        logger.info("[4/4] Running Fuzzy Matching...")
        from implicit_dependency_resolver.fuzzy_matching import FuzzyMatcher
        if fuzzy_threshold is not None:
            matcher = FuzzyMatcher(path_id, threshold=fuzzy_threshold)
            logger.info(f"Using custom fuzzy threshold: {fuzzy_threshold}")
        else:
            matcher = FuzzyMatcher(path_id)
            logger.info(f"Using default fuzzy threshold: {matcher.threshold}")
        results['fuzzy'] = matcher.run()
        logger.info(f"✓ Step 4 completed: {results['fuzzy']} fuzzy links created")
    else:
        logger.info("[4/4] Skipping Fuzzy Matching (disabled)")
    
    # ========================================================================
    # Summary
    # ========================================================================
    total_links = results['exact'] + results['boundary'] + results['fuzzy']
    logger.info("="*70)
    logger.info("IMPLICIT DEPENDENCY RESOLUTION SUMMARY")
    logger.info("="*70)
    logger.info(f"  Exact links:    {results['exact']:4d}")
    logger.info(f"  Boundary links: {results['boundary']:4d}")
    logger.info(f"  Fuzzy links:    {results['fuzzy']:4d}")
    logger.info(f"  Total implicit links: {total_links}")
    logger.info("="*70)
    
    return results


# Standalone execution (for testing)
if __name__ == "__main__":
    import sys
    
    # Setup paths to import internal modules
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    from utils.n4j_helper import Initialize, GetPathID
    
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    if len(sys.argv) < 2:
        print("Usage: python3 implicit.py <project_path>")
        print("Example: python3 implicit.py /home/thangdd/repos/TerrARA/demo_tf_project")
        sys.exit(1)
    
    project_path = os.path.abspath(sys.argv[1])
    
    if not os.path.exists(project_path):
        print(f"Error: Path does not exist: {project_path}")
        sys.exit(1)
    
    # Initialize
    try:
        Initialize()
        logger.info("Connected to Memgraph")
    except Exception as e:
        logger.error(f"Failed to connect to Memgraph: {e}")
        sys.exit(1)
    
    path_id = GetPathID(project_path)
    logger.info(f"Running Implicit Dependency Resolution for Path ID: {path_id}")
    
    # Run pipeline
    results = run_implicit_dependency_resolution(project_path, path_id)
    
    print("\nResults:", results)
