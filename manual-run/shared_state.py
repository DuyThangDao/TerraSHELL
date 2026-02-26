"""
Shared state module để lưu trữ các biến được chia sẻ giữa các steps
"""
import os
import json
import logging
try:
    import dill as pickle
except ImportError:
    import pickle

logger = logging.getLogger(__name__)

# File để lưu state
STATE_FILE = os.path.join(os.path.dirname(__file__), ".state.json")
# File để lưu diagram object (pickle format)
DIAGRAM_FILE = os.path.join(os.path.dirname(__file__), ".diagram.pkl")

def save_state(key, value):
    """Lưu một giá trị vào state file"""
    state = load_all_state()
    state[key] = value
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2, default=str)
        logger.debug(f"Saved state: {key} = {value}")
    except Exception as e:
        logger.error(f"Error saving state: {e}")

def load_state(key, default=None):
    """Load một giá trị từ state file"""
    state = load_all_state()
    return state.get(key, default)

def load_all_state():
    """Load toàn bộ state từ file"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading state file: {e}, returning empty state")
            return {}
    return {}

def clear_state():
    """Xóa toàn bộ state"""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        logger.info("State file cleared")

def get_path_id():
    """Lấy pathID từ state"""
    return load_state("pathID")

def set_path_id(path_id):
    """Lưu pathID vào state"""
    save_state("pathID", path_id)

def get_in_path():
    """Lấy in_path từ state"""
    return load_state("in_path")

def set_in_path(in_path):
    """Lưu in_path vào state"""
    save_state("in_path", in_path)

def get_out_path():
    """Lấy out_path từ state"""
    return load_state("out_path", "./output")

def set_out_path(out_path):
    """Lưu out_path vào state"""
    save_state("out_path", out_path)

def get_anno():
    """Lấy annotation config từ state"""
    return load_state("anno")

def set_anno(anno):
    """Lưu annotation config vào state"""
    save_state("anno", anno)

def get_rule():
    """Lấy rule config từ state"""
    return load_state("rule")

def set_rule(rule):
    """Lưu rule config vào state"""
    save_state("rule", rule)

def get_compresses():
    """Lấy danh sách compress từ state"""
    return load_state("compresses", [])

def set_compresses(compresses):
    """Lưu danh sách compress vào state"""
    save_state("compresses", compresses)

def get_publics():
    """Lấy danh sách publics từ state"""
    return load_state("publics", set())

def get_publics_set():
    """Lấy danh sách publics từ state và đảm bảo trả về set"""
    publics = load_state("publics", set())
    # Convert list to set nếu state đã được lưu dưới dạng list
    if isinstance(publics, list):
        return set(publics)
    return publics if isinstance(publics, set) else set()

def set_publics(publics):
    """Lưu danh sách publics vào state (convert set to list for JSON)"""
    save_state("publics", list(publics) if isinstance(publics, set) else publics)


def get_global_tb_name():
    """Lấy global_tb_name từ state"""
    return load_state("global_tb_name", "Cloud")

def set_global_tb_name(name):
    """Lưu global_tb_name vào state"""
    save_state("global_tb_name", name)

def get_graph_mode():
    """Lấy graph_mode từ state"""
    return load_state("graph_mode", False)

def set_graph_mode(mode):
    """Lưu graph_mode vào state"""
    save_state("graph_mode", mode)

def set_diagram_built(flag=True):
    """Đánh dấu rằng step_14 đã build diagram thành công"""
    save_state("diagram_built", flag)

def is_diagram_built():
    """Kiểm tra xem step_14 đã build diagram chưa"""
    return load_state("diagram_built", False)

def rebuild_diagram_from_nodes():
    """Rebuild diagram object từ COMPONENT_ID_NODE và BOUNDARY_ID_NODE.
    Được gọi khi cần diagram object nhưng không thể load từ pickle.
    Rebuild lại toàn bộ structure từ các nodes đã có, bao gồm:
    - Ownership relationships (FindOwn)
    - Outermost boundaries (QueryOutermostBoundary)
    - Connections/DataFlows (QueryAllConnectionResource + AddEdge)"""
    from dfdgraph import Diagram, TrustBoundary, Process, DataStore
    from dfdgraph.component import COMPONENT_ID_NODE
    from dfdgraph.trustboundary import BOUNDARY_ID_NODE
    from utils.n4j_helper import QueryTagged, FindOwn, QueryOutermostBoundary, QueryAllConnectionResource
    from shared_state import get_path_id, get_publics_set, get_anno, get_rule
    import re
    
    diag = Diagram()
    global_tb_name = get_global_tb_name()
    pathID = get_path_id()
    publics = get_publics_set()
    anno = get_anno()
    rule = get_rule()
    
    if not pathID:
        logger.error("pathID not found, cannot rebuild diagram")
        return None, None, None
    
    if not anno:
        logger.error("anno not found, cannot rebuild diagram")
        return None, None, None
    
    if not rule:
        logger.error("rule not found, cannot rebuild diagram")
        return None, None, None
    
    # Extract group names
    procname = set(c["group_name"] for c in anno.get("processes", []))
    dsname = set(c["group_name"] for c in anno.get("data_stores", []))
    boundname = set(c["group_name"] for c in anno.get("boundaries", []))
    
    # Tìm global boundary đã có trong BOUNDARY_ID_NODE bằng name
    # Nếu không tìm thấy, tạo mới
    aws = None
    for bid, boundary in BOUNDARY_ID_NODE.items():
        if boundary.name == global_tb_name:
            aws = boundary
            break
    
    if aws is None:
        aws = TrustBoundary("", global_tb_name)
    diag.AddBoundary(aws)
    
    compos = set()
    
    # ========================================================================
    # STEP 1: Rebuild Ownership Relationships (giống step_14)
    # ========================================================================
    logger.info("Rebuilding ownership relationships...")
    try:
        if "relations" in rule and "own" in rule["relations"]:
            own_rules = rule["relations"]["own"]
            logger.info(f"Found {len(own_rules)} owning rules")
            
            for i, v in enumerate(own_rules, 1):
                try:
                    r = FindOwn(v["first_node"], v["second_node"], v["method"], pathID)
                    logger.debug(f"Rule {i}: Found {len(r)} relationships")
                    
                    for u in r:
                        crafted_name1 = "%s (%s) - %s" % (u["group1"], u["general_name1"], u.get("tfname1", ""))
                        crafted_name2 = "%s (%s) - %s" % (u["group2"], u["general_name2"], u.get("tfname2", ""))
                        
                        # Create or get first node
                        if u["group1"] in boundname:
                            fr = BOUNDARY_ID_NODE.get(str(u["id1"])) if str(u["id1"]) in BOUNDARY_ID_NODE else TrustBoundary(u["id1"], crafted_name1)
                        elif u["group1"] in procname:
                            fr = COMPONENT_ID_NODE.get(str(u["id1"])) if str(u["id1"]) in COMPONENT_ID_NODE else Process(u["id1"], crafted_name1, u.get("annotation1", ""))
                            # Thêm fr vào compos nếu là component
                            if hasattr(fr, 'id'):
                                compos.add(fr.id)
                        elif u["group1"] in dsname:
                            fr = COMPONENT_ID_NODE.get(str(u["id1"])) if str(u["id1"]) in COMPONENT_ID_NODE else DataStore(u["id1"], crafted_name1, u.get("annotation1", ""))
                            # Thêm fr vào compos nếu là component
                            if hasattr(fr, 'id'):
                                compos.add(fr.id)
                        else:
                            continue
                        
                        # Create or get second node
                        if u["group2"] in boundname:
                            if str(u["id1"]) in BOUNDARY_ID_NODE and str(u["id2"]) in BOUNDARY_ID_NODE:
                                continue
                            to = BOUNDARY_ID_NODE.get(str(u["id2"])) if str(u["id2"]) in BOUNDARY_ID_NODE else TrustBoundary(u["id2"], crafted_name2)
                            if u["group1"] not in boundname:
                                to.AddNode(fr)
                                # fr.id đã được thêm vào compos ở trên
                                for pub in publics:
                                    if re.fullmatch(pub, u.get("name1", "")):
                                        diag.AddPublicNode(fr)
                            else:
                                fr.AddInnerBound(to)
                        elif u["group2"] in procname:
                            if str(u["id1"]) in BOUNDARY_ID_NODE and str(u["id2"]) in COMPONENT_ID_NODE:
                                continue
                            to = COMPONENT_ID_NODE.get(str(u["id2"])) if str(u["id2"]) in COMPONENT_ID_NODE else Process(u["id2"], crafted_name2, u.get("annotation2", ""))
                            fr.AddNode(to)
                            compos.add(to.id)
                            for pub in publics:
                                if re.fullmatch(pub, u.get("name2", "")):
                                    diag.AddPublicNode(to)
                        elif u["group2"] in dsname:
                            if str(u["id1"]) in BOUNDARY_ID_NODE and str(u["id2"]) in COMPONENT_ID_NODE:
                                continue
                            to = COMPONENT_ID_NODE.get(str(u["id2"])) if str(u["id2"]) in COMPONENT_ID_NODE else DataStore(u["id2"], crafted_name2, u.get("annotation2", ""))
                            fr.AddNode(to)
                            compos.add(to.id)
                            for pub in publics:
                                if re.fullmatch(pub, u.get("name2", "")):
                                    diag.AddPublicNode(to)
                except Exception as e:
                    logger.warning(f"Error processing own rule {i}: {e}")
                    continue
        else:
            logger.warning("No 'own' rules found in rule config")
    except Exception as e:
        logger.warning(f"Error rebuilding ownership relationships: {e}")
    
    # ========================================================================
    # STEP 2: Rebuild Other Components (giống step_14)
    # ========================================================================
    logger.info("Rebuilding other components...")
    try:
        other_nodes = QueryTagged(pathID, "processes") + QueryTagged(pathID, "data_stores")
        logger.info(f"Found {len(other_nodes)} other nodes")
        
        for r in other_nodes:
            id_ = str(r["id"])
            if id_ in compos:
                continue
            crafted_name = "%s (%s) - %s" % (r["group"], r["general_name"], r.get("tfname", ""))
            
            if r["group"] in procname:
                n = COMPONENT_ID_NODE.get(id_) if id_ in COMPONENT_ID_NODE else Process(id_, crafted_name, r.get("annotation", ""))
            elif r["group"] in dsname:
                n = COMPONENT_ID_NODE.get(id_) if id_ in COMPONENT_ID_NODE else DataStore(id_, crafted_name, r.get("annotation", ""))
            else:
                continue
            
            aws.AddNode(n)
            compos.add(id_)
            
            for pub in publics:
                if re.fullmatch(pub, r.get("name", "")):
                    diag.AddPublicNode(n)
    except Exception as e:
        logger.warning(f"Error rebuilding other components: {e}")
    
    # ========================================================================
    # STEP 3: Rebuild Outermost Boundaries (giống step_16)
    # ========================================================================
    logger.info("Rebuilding outermost boundaries...")
    try:
        outermost_boundaries = QueryOutermostBoundary(pathID)
        logger.info(f"Found {len(outermost_boundaries)} outermost boundaries")
        
        for r in outermost_boundaries:
            id_ = str(r["id"])
            crafted_name = "%s (%s)" % (r["group"], r["general_name"])
            
            boundary = BOUNDARY_ID_NODE.get(id_) if id_ in BOUNDARY_ID_NODE else TrustBoundary(id_, crafted_name)
            if boundary not in aws.innerBoundaries:
                aws.AddInnerBound(boundary)
                logger.debug(f"Added outermost boundary: {boundary.name} (ID: {id_})")
    except Exception as e:
        logger.warning(f"Error rebuilding outermost boundaries: {e}")
    
    # ========================================================================
    # STEP 4: Rebuild Connections/DataFlows (giống step_17)
    # ========================================================================
    logger.info("Rebuilding connections/dataflows...")
    try:
        # Clear previous dataflows to prevent duplicates
        from dfdgraph.dataflow import GLOBAL_DF_SP
        from dfdgraph.component import DF_MAP
        GLOBAL_DF_SP.clear()
        DF_MAP.clear()
        logger.debug(f"Cleared previous dataflows: {len(GLOBAL_DF_SP)} dataflows, {len(DF_MAP)} edges")
        
        connections = QueryAllConnectionResource(pathID)
        logger.info(f"Found {len(connections)} connections")
        
        connections_added = 0
        for i, r in enumerate(connections, 1):
            node1 = COMPONENT_ID_NODE.get(str(r["id1"]))
            node2 = COMPONENT_ID_NODE.get(str(r["id2"]))
            
            if node1 and node2:
                node1.AddEdge(node2)
                connections_added += 1
            else:
                if not node1:
                    logger.debug(f"Node1 not found: {r['id1']}")
                if not node2:
                    logger.debug(f"Node2 not found: {r['id2']}")
        
        logger.info(f"Added {connections_added} dataflows")
    except Exception as e:
        logger.warning(f"Error rebuilding connections: {e}")
    
    # ========================================================================
    # STEP 5: Rebuild Auto-detected Public Nodes (giống step_15)
    # ========================================================================
    logger.info("Rebuilding auto-detected public nodes...")
    try:
        from shared_state import get_in_path
        from utils.auto_detect_public_resources import auto_detect_public_resources
        
        in_path = get_in_path()
        if in_path:
            auto_public_ids = auto_detect_public_resources(in_path, pathID)
            logger.info(f"Found {len(auto_public_ids)} auto-detected public resources")
            
            for resource_id in auto_public_ids:
                if resource_id in COMPONENT_ID_NODE:
                    resource_node = COMPONENT_ID_NODE[resource_id]
                    diag.AddPublicNode(resource_node)
                    logger.debug(f"Auto-marked as public: {resource_node.name} (ID: {resource_id})")
                else:
                    logger.debug(f"Resource ID {resource_id} not found in COMPONENT_ID_NODE")
    except Exception as e:
        logger.warning(f"Error rebuilding auto-detected public nodes: {e}")
    
    logger.info(f"Rebuilt diagram with {len(compos)} components, {len([b for b in BOUNDARY_ID_NODE.values() if b != aws])} inner boundaries")
    return diag, compos, aws

# Legacy functions - giữ lại để tương thích
def set_diagram(diagram, compos=None, aws=None):
    """Đánh dấu rằng diagram đã được build (không lưu object vì pyecore không pickle được)"""
    set_diagram_built(True)
    logger.debug("Diagram build flag set (diagram object cannot be pickled due to pyecore limitations)")

def get_diagram():
    """Rebuild diagram từ COMPONENT_ID_NODE và BOUNDARY_ID_NODE vì pyecore objects không pickle được."""
    if not is_diagram_built():
        return None, None, None
    try:
        return rebuild_diagram_from_nodes()
    except Exception as e:
        logger.error(f"Error rebuilding diagram: {e}", exc_info=True)
        return None, None, None
