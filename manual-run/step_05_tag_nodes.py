#!/usr/bin/env python3
"""
Step 05: Tag nodes from annotation configuration
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.n4j_helper import TaggingNode
from shared_state import get_anno, get_path_id

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 05] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_05.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 05: Tag nodes from annotation configuration
    """
    logger.info("="*80)
    logger.info("STEP 05: TAG NODES FROM ANNOTATION")
    logger.info("="*80)
    
    try:
        # Get data from state
        anno = get_anno()
        pathID = get_path_id()
        
        if not anno:
            logger.error("Annotation config not found in state. Please run Step 01 first.")
            sys.exit(1)
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        logger.info(f"Annotation keys: {list(anno.keys())}")
        
        start_time = time.time()
        
        # Tag nodes for each category (processes, boundaries, data_stores)
        total_tagged = 0
        for key in anno:
            if key == "external_entities":
                logger.info(f"Skipping external_entities (not nodes)...")
                continue
            
            logger.info(f"Processing {key}...")
            category_count = 0
            
            for c in anno[key]:
                group_name = c["group_name"]
                annotation = c.get("annotation", "")
                logger.info(f"  Group: {group_name} (annotation: {annotation})")
                
                for member in c["members"]:
                    tf_name = member["tf_name"]
                    name = member["name"]
                    logger.info(f"    Tagging: {tf_name} -> {name}")
                    
                    TaggingNode(
                        tf_name,
                        pathID,
                        group_name,
                        name,
                        key,
                        annotation
                    )
                    category_count += 1
                    total_tagged += 1
            
            logger.info(f"  ✓ Tagged {category_count} patterns in {key}")
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Tagging completed!")
        logger.info(f"  Total patterns tagged: {total_tagged}")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 05 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 05: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
