#!/usr/bin/env python3
"""
Step 18: Export results (graph or sparta)
"""
import sys
import os
import logging
import time
import graphviz
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared_state import get_out_path, get_anno, get_graph_mode
import step_14_build_diagram as step14_module

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 18] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_18.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 18: Export results
    
    This step exports the final diagram either as a graph (PNG) or SPARTA format.
    """
    logger.info("="*80)
    logger.info("STEP 18: EXPORT RESULTS")
    logger.info("="*80)
    
    try:
        # Get data from state
        out_path = get_out_path()
        anno = get_anno()
        graph_mode = get_graph_mode()
        
        if not anno:
            logger.error("Annotation config not found in state. Please run Step 01 first.")
            sys.exit(1)
        
        # Check if diagram exists from step 14
        if step14_module.diagram is None:
            logger.error("Diagram not found. Please run Step 14 first.")
            sys.exit(1)
        
        diag = step14_module.diagram
        
        # Handle Docker environment
        if os.getenv("DOCKER_ENV") == "1":
            out_path = "../output"
        
        logger.info(f"Output path: {out_path}")
        logger.info(f"Graph mode: {graph_mode}")
        
        # Create output directory if it doesn't exist
        os.makedirs(out_path, exist_ok=True)
        
        start_time = time.time()
        
        external_entities = anno.get("external_entities", [])
        logger.info(f"External entities: {len(external_entities)}")
        
        if graph_mode:
            logger.info("Exporting as graph (PNG)...")
            g = graphviz.Digraph("G", directory=out_path, filename="result.dot")
            g.graph_attr['nodesep'] = '1'
            g.graph_attr['ranksep'] = '2'
            diag.DrawDiagram(g, external_entities)
            g.render(filename="dfd", format="png", view=False)
            logger.info(f"✓ Graph exported to: {out_path}/dfd.png")
        else:
            logger.info("Exporting as SPARTA...")
            diag.ExportSparta(out_path, external_entities)
            logger.info(f"✓ SPARTA exported to: {out_path}")
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Export completed!")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 18 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        logger.info("="*80)
        logger.info("ALL STEPS COMPLETED!")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 18: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
