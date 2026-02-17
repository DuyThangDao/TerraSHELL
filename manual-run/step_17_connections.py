#!/usr/bin/env python3
"""
Step 17: Query all connections and add edges
"""
import sys
import logging
import time
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dfdgraph.component import COMPONENT_ID_NODE, DF_MAP
from dfdgraph.dataflow import GLOBAL_DF_SP
from utils.n4j_helper import QueryAllConnectionResource
from shared_state import get_path_id

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 17] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_17.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 17: Query all connections and add edges
    
    This step queries all connections between resources and adds them to the diagram.
    """
    logger.info("="*80)
    logger.info("STEP 17: QUERY ALL CONNECTIONS")
    logger.info("="*80)
    
    try:
        # Get pathID from state
        pathID = get_path_id()
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        
        # Clear previous dataflows to prevent duplicates
        logger.info("Clearing previous dataflows...")
        GLOBAL_DF_SP.clear()
        DF_MAP.clear()
        logger.info(f"  Cleared {len(GLOBAL_DF_SP)} dataflows, {len(DF_MAP)} edges")
        
        start_time = time.time()
        
        logger.info("Querying all connections...")
        connections = QueryAllConnectionResource(pathID)
        logger.info(f"Found {len(connections)} connections")
        
        # #region agent log
        try:
            with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({
                    "id": f"log_{int(time.time() * 1000)}",
                    "timestamp": int(time.time() * 1000),
                    "location": "step_17_connections.py:58",
                    "message": "QueryAllConnectionResource results",
                    "data": {
                        "total_connections": len(connections),
                        "sample_connections": [
                            {
                                "id1": r["id1"],
                                "id2": r["id2"],
                                "name1": r.get("general_name1", ""),
                                "name2": r.get("general_name2", "")
                            } for r in connections[:20]
                        ]
                    },
                    "runId": "compression-debug",
                    "hypothesisId": "H"
                }) + "\n")
        except: pass
        # #endregion
        
        for i, r in enumerate(connections, 1):
            crafted_name1 = "%s (%s)" % (r["group1"], r["general_name1"])
            crafted_name2 = "%s (%s)" % (r["group2"], r["general_name2"])
            
            if i <= 10 or i % 100 == 0:  # Log first 10 and every 100th
                logger.info(f"  [{i}/{len(connections)}] {crafted_name1} --> {crafted_name2}")
            
            node1 = COMPONENT_ID_NODE.get(str(r["id1"]))
            node2 = COMPONENT_ID_NODE.get(str(r["id2"]))
            
            # #region agent log
            if not node1 or not node2:
                try:
                    with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                        f.write(json.dumps({
                            "id": f"log_{int(time.time() * 1000)}",
                            "timestamp": int(time.time() * 1000),
                            "location": "step_17_connections.py:72",
                            "message": "Node not found in COMPONENT_ID_NODE",
                            "data": {
                                "id1": r["id1"],
                                "id2": r["id2"],
                                "name1": crafted_name1,
                                "name2": crafted_name2,
                                "node1_found": node1 is not None,
                                "node2_found": node2 is not None,
                                "COMPONENT_ID_NODE_keys": list(COMPONENT_ID_NODE.keys())[:10]
                            },
                            "runId": "compression-debug",
                            "hypothesisId": "H"
                        }) + "\n")
                except: pass
            # #endregion
            
            if node1 and node2:
                node1.AddEdge(node2)
            else:
                if not node1:
                    logger.warning(f"  Node1 not found: {r['id1']}")
                if not node2:
                    logger.warning(f"  Node2 not found: {r['id2']}")
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ All connections added!")
        logger.info(f"  Total connections: {len(connections)}")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 17 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 17: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
