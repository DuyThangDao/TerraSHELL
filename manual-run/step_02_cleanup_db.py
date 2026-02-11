#!/usr/bin/env python3
"""
Step 02: Clean up database (FOR DEBUGGING ONLY)
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.n4j_helper import CleanUp

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 02] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_02.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 02: Clean up database
    
    WARNING: This will delete ALL nodes and relationships in the database!
    """
    logger.info("="*80)
    logger.info("STEP 02: CLEAN UP DATABASE")
    logger.info("="*80)
    logger.warning("WARNING: This will delete ALL nodes and relationships!")
    
    try:
        start_time = time.time()
        
        logger.info("Starting database cleanup...")
        CleanUp()
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Database cleanup completed in {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 02 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 02: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
