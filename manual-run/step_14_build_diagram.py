#!/usr/bin/env python3
"""
Step 14: Build diagram - Query tagged nodes and create diagram structure
"""
import sys
import logging
import time
import json
import re
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dfdgraph import DataStore, Diagram, Process, TrustBoundary
from dfdgraph.component import COMPONENT_ID_NODE
from dfdgraph.trustboundary import BOUNDARY_ID_NODE
from utils.n4j_helper import QueryTagged, FindOwn
from shared_state import (
    get_anno, get_rule, get_publics_set, get_global_tb_name, 
    get_path_id, set_diagram
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 14] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_14.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 14: Build diagram - Query tagged nodes and create diagram structure
    
    This step queries all tagged nodes and creates the initial diagram structure.
    """
    logger.info("="*80)
    logger.info("STEP 14: BUILD DIAGRAM - QUERY TAGGED NODES")
    logger.info("="*80)
    
    try:
        # Get data from state
        anno = get_anno()
        rule = get_rule()
        publics = get_publics_set()
        global_tb_name = get_global_tb_name()
        pathID = get_path_id()
        
        if not anno:
            logger.error("Annotation config not found in state. Please run Step 01 first.")
            sys.exit(1)
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        logger.info(f"Global trust boundary name: {global_tb_name}")
        
        # Extract group names
        procname = set(c["group_name"] for c in anno["processes"])
        dsname = set(c["group_name"] for c in anno["data_stores"])
        boundname = set(c["group_name"] for c in anno["boundaries"])
        
        logger.info(f"Process groups: {procname}")
        logger.info(f"Data store groups: {dsname}")
        logger.info(f"Boundary groups: {boundname}")
        
        start_time = time.time()
        
        # Initialize diagram
        compos = set()
        diag = Diagram()
        
        # Query and log boundaries
        logger.info("-------- Querying Boundaries --------")
        boundaries = QueryTagged(pathID, "boundaries")
        logger.info(f"Found {len(boundaries)} boundaries")
        for r in boundaries:
            id_ = str(r["id"])
            crafted_name = "%s (%s)" % (r["group"], r["general_name"])
            logger.info(f"  {id_} - {crafted_name}")
        
        # Query and log owning relationships
        logger.info("-------- Querying Owning Relationships --------")
        logger.info("Traversing through owning rules...")
        
        if "relations" in rule and "own" in rule["relations"]:
            own_rules = rule["relations"]["own"]
            logger.info(f"Found {len(own_rules)} owning rules")
            
            for i, v in enumerate(own_rules, 1):
                logger.info(f"[{i}/{len(own_rules)}] Processing rule: {v.get('id', 'unknown')}")
                logger.info(f"  First node: {v['first_node']}, Second node: {v['second_node']}, Method: {v['method']}")
                
                r = FindOwn(v["first_node"], v["second_node"], v["method"], pathID)
                logger.info(f"  Found {len(r)} relationships")
                
                for u in r:
                    crafted_name1 = "%s (%s) - %s" % (u["group1"], u["general_name1"], u["tfname1"])
                    crafted_name2 = "%s (%s) - %s" % (u["group2"], u["general_name2"], u["tfname2"])
                    
                    # Create or get first node
                    if u["group1"] in boundname:
                        fr = BOUNDARY_ID_NODE.get(str(u["id1"])) if str(u["id1"]) in BOUNDARY_ID_NODE else TrustBoundary(u["id1"], crafted_name1)
                    elif u["group1"] in procname:
                        fr = COMPONENT_ID_NODE.get(str(u["id1"])) if str(u["id1"]) in COMPONENT_ID_NODE else Process(u["id1"], crafted_name1, u["annotation1"])
                    elif u["group1"] in dsname:
                        fr = COMPONENT_ID_NODE.get(str(u["id1"])) if str(u["id1"]) in COMPONENT_ID_NODE else DataStore(u["id1"], crafted_name1, u["annotation1"])
                    else:
                        logger.warning(f"Unknown group1: {u['group1']} - {u}")
                        continue
                    
                    # Create or get second node
                    if u["group2"] in boundname:
                        if str(u["id1"]) in BOUNDARY_ID_NODE and str(u["id2"]) in BOUNDARY_ID_NODE:
                            logger.debug(f"  Already exists: {u}")
                            continue
                        to = BOUNDARY_ID_NODE.get(str(u["id2"])) if str(u["id2"]) in BOUNDARY_ID_NODE else TrustBoundary(u["id2"], crafted_name2)
                        if u["group1"] not in boundname:
                            to.AddNode(fr)
                            compos.add(fr.id)
                            for pub in publics:
                                if re.fullmatch(pub, u["name1"]):
                                    diag.AddPublicNode(fr)
                        else:
                            fr.AddInnerBound(to)
                    elif u["group2"] in procname:
                        if str(u["id1"]) in BOUNDARY_ID_NODE and str(u["id2"]) in COMPONENT_ID_NODE:
                            logger.debug(f"  Already exists: {u}")
                            continue
                        to = COMPONENT_ID_NODE.get(str(u["id2"])) if str(u["id2"]) in COMPONENT_ID_NODE else Process(u["id2"], crafted_name2, u["annotation2"])
                        fr.AddNode(to)
                        compos.add(to.id)
                        for pub in publics:
                            if re.fullmatch(pub, u["name2"]):
                                diag.AddPublicNode(to)
                    elif u["group2"] in dsname:
                        if str(u["id1"]) in BOUNDARY_ID_NODE and str(u["id2"]) in COMPONENT_ID_NODE:
                            logger.debug(f"  Already exists: {u}")
                            continue
                        to = COMPONENT_ID_NODE.get(str(u["id2"])) if str(u["id2"]) in COMPONENT_ID_NODE else DataStore(u["id2"], crafted_name2, u["annotation2"])
                        fr.AddNode(to)
                        compos.add(to.id)
                        for pub in publics:
                            if re.fullmatch(pub, u["name2"]):
                                diag.AddPublicNode(to)
                    
                    logger.debug(f"  Added: {type(to).__name__} {to.name} ({to.id})")
        else:
            logger.warning("No 'own' rules found in rule config")
        
        # Add global boundary
        aws = TrustBoundary("", global_tb_name)
        diag.AddBoundary(aws)
        logger.info(f"✓ Added global boundary: {global_tb_name}")
        
        logger.info(f"Components in relationships: {len(compos)}")
        
        # Query other processes and data stores
        logger.info("------------ Querying Other Processes & Data Stores ------------")
        other_nodes = QueryTagged(pathID, "processes") + QueryTagged(pathID, "data_stores")
        logger.info(f"Found {len(other_nodes)} other nodes")
        
        # #region agent log
        try:
            with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({
                    "id": f"log_{int(time.time() * 1000)}",
                    "timestamp": int(time.time() * 1000),
                    "location": "step_14_build_diagram.py:165",
                    "message": "QueryTagged results",
                    "data": {
                        "total_nodes": len(other_nodes),
                        "nodes": [{"id": str(r["id"]), "name": r.get("tfname", ""), "group": r.get("group", "")} for r in other_nodes[:20]]
                    },
                    "runId": "compression-debug",
                    "hypothesisId": "G"
                }) + "\n")
        except: pass
        # #endregion
        
        for r in other_nodes:
            id_ = str(r["id"])
            if id_ in compos:
                continue
            crafted_name = "%s (%s) - %s" % (r["group"], r["general_name"], r["tfname"])
            logger.info(f"  {id_} - {crafted_name}")
            
            # #region agent log
            try:
                with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({
                        "id": f"log_{int(time.time() * 1000)}",
                        "timestamp": int(time.time() * 1000),
                        "location": "step_14_build_diagram.py:172",
                        "message": "Adding node to diagram",
                        "data": {
                            "id": id_,
                            "name": crafted_name,
                            "tfname": r.get("tfname", ""),
                            "group": r.get("group", ""),
                            "in_compos": id_ in compos
                        },
                        "runId": "compression-debug",
                        "hypothesisId": "G"
                    }) + "\n")
            except: pass
            # #endregion
            
            if r["group"] in procname:
                n = COMPONENT_ID_NODE.get(id_) if id_ in COMPONENT_ID_NODE else Process(id_, crafted_name, r["annotation"])
            else:
                n = COMPONENT_ID_NODE.get(id_) if id_ in COMPONENT_ID_NODE else DataStore(id_, crafted_name, r["annotation"])
            
            aws.AddNode(n)
            
            for pub in publics:
                if re.fullmatch(pub, r["name"]):
                    diag.AddPublicNode(n)
        
        # Save diagram to state (both module-level for same-process access and pickle for cross-process)
        # Store in a module-level variable (for same-process access)
        import step_14_build_diagram as step14_module
        step14_module.diagram = diag
        step14_module.compos = compos
        step14_module.aws = aws
        
        # Also save to shared_state using pickle (for cross-process access)
        set_diagram(diag, compos, aws)
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Diagram structure built!")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 14 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 14: {e}", exc_info=True)
        sys.exit(1)

# Module-level variables to store diagram state
diagram = None
compos = None
aws = None

if __name__ == '__main__':
    main()
