#!/usr/bin/env python3
"""
Step 11: Run Semgrep and tag public resources
"""
import sys
import json
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tfparser.tfgrep import GetSemgrepJSON
from utils.n4j_helper import TaggingPublic
from shared_state import get_in_path, get_path_id, get_rule

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 11] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_11.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main(sem_rule="./input/semgrep_rule.yaml"):
    """
    Step 11: Run Semgrep and tag public resources
    
    Args:
        sem_rule: Đường dẫn đến Semgrep rule file (default: ./input/semgrep_rule.yaml)
    """
    logger.info("="*80)
    logger.info("STEP 11: RUN SEMGREP AND TAG PUBLIC RESOURCES")
    logger.info("="*80)
    
    try:
        # Get data from state
        in_path = get_in_path()
        pathID = get_path_id()
        rule = get_rule()
        
        if not in_path:
            logger.error("in_path not found in state. Please run Step 01 first.")
            sys.exit(1)
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        if not rule:
            logger.error("Rule config not found in state. Please run Step 01 first.")
            sys.exit(1)
        
        logger.info(f"Input path: {in_path}")
        logger.info(f"Path ID: {pathID}")
        logger.info(f"Semgrep rule: {sem_rule}")
        
        # Run Semgrep
        logger.info("Running Semgrep...")
        start_time = time.time()
        
        sem_json_path = GetSemgrepJSON(in_path, sem_rule)
        logger.info(f"✓ Semgrep completed. Results: {sem_json_path}")
        
        # Load Semgrep results
        logger.info("Loading Semgrep results...")
        with open(sem_json_path, "r") as f:
            sem_json = json.load(f)
        
        logger.info(f"  Found {len(sem_json.get('results', []))} Semgrep results")
        
        # Tag public resources
        logger.info("Tagging public resources...")
        if "publics" not in rule:
            logger.warning("No 'publics' key in rule config. Skipping public tagging...")
        else:
            for v in rule["publics"]:
                name = v["variable"]
                logger.info(f"  Processing public variable: {name}")
                
                list_of_public_bound = set([
                    result["extra"]["metavars"][name]["abstract_content"]
                    for result in sem_json["results"]
                    if name in result.get("extra", {}).get("metavars", {})
                ])
                
                logger.info(f"    Found {len(list_of_public_bound)} public boundaries: {list_of_public_bound}")
                
                for bound in list_of_public_bound:
                    logger.info(f"      Tagging public: {bound}")
                    TaggingPublic(pathID, bound)
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Public resources tagged!")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 11 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 11: {e}", exc_info=True)
        logger.error("This step may timeout if:")
        logger.error("  1. Semgrep takes too long to run")
        logger.error("  2. Project is very large")
        sys.exit(1)

if __name__ == '__main__':
    import fire
    fire.Fire(main)
