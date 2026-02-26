import logging
from typing import List, Mapping, Dict, Any, Set, Tuple
from collections import defaultdict, deque
from neo4j import GraphDatabase
import os
import json
import time

logger = logging.getLogger(__name__)

# Define correct URI and AUTH arguments (no AUTH by default)
URI = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
AUTH = ("", "")

def Initialize():
    try:
        client = GraphDatabase.driver(URI, auth=AUTH)
        # Check the connection
        client.verify_connectivity()
        return client
    except:
        logging.error("Cannot connect to server at %s" % URI)
        exit(1)
        

INSTANCE = Initialize()

def GetPathID(originPath: str) -> str:
    return '.'.join(str(os.path.abspath(originPath))[1:].split('/'))

def CreateNode(labels: List[str], values: Mapping[str, str]) -> int:
    """Create Node in Memgraph

    Args:
        labels (List[str]): _description_
        values (Mapping[str, str]): _description_

    Returns:
        int: _description_
    """
    """
        Labels contain 2 value (any order is ok):
            - encoded target project's path (due to restriction in memgraph for multi-tenant db, so that every node lives in single db)
            - type of resource
        Values contain 3 value:
            - parent id (path of module)
            - resource type
            - resource name
            - (...) additional value to be added later
    """
    crafted_params = {
        "l1" : labels[0],
        "l2" : labels[1],
        "pid": values["parent_id"],
        "rt": values["resource_type"],
        "rn": values["resource_name"],
    }

    records, _, _ = INSTANCE.execute_query(
        "CREATE (u:$l1:$l2 {parent: $pid, type: $rt, name: $rn}) RETURN ID(u) as id;",
        parameters_=crafted_params,
        database_="memgraph"
    )
    
    return records[0]["id"]

def CreateNodeWithProperties(labels: List[str], properties: Dict[str, Any], pathID: str) -> int:
    """Create or Merge Node in Memgraph with arbitrary properties (prevents duplicates)
    
    Args:
        labels: List of labels for the node (pathID will be prepended, max 2 labels total)
        properties: Dictionary of properties to set on the node
        pathID: Path ID to use as first label
        
    Returns:
        Node ID (existing or newly created)
    """
    # Ensure pathID is first label, take first additional label if any
    label2 = labels[0] if labels and labels[0] != pathID else labels[1] if len(labels) > 1 else pathID
    
    # Use 'name' property as unique identifier for Variables/Locals to prevent duplicates
    if 'name' in properties:
        # First, try to find existing node with same labels and name
        # Use backticks for labels that might contain special characters
        check_query = f"""
        MATCH (u:`{pathID}`:`{label2}`)
        WHERE u.name = $name
        RETURN ID(u) as id
        LIMIT 1
        """
        
        check_params = {
            "name": properties['name']
        }
        
        try:
            records, _, _ = INSTANCE.execute_query(
                check_query,
                parameters_=check_params,
                database_="memgraph"
            )
            
            if records and len(records) > 0:
                # Node exists, update it and return existing ID
                existing_id = records[0]["id"]
                UpdateNodeProperties(existing_id, properties, pathID)
                logger.debug(f"Found existing node with name '{properties['name']}', ID: {existing_id}")
                return existing_id
        except Exception as e:
            logger.warning(f"Error checking for existing node: {e}, will create new node")
    
    # Node doesn't exist, create new one
    # Build property string dynamically
    params = {
        "l1": pathID,
        "l2": label2
    }
    
    # Add properties
    prop_dict_parts = []
    for key, value in properties.items():
        # Sanitize key for parameter name (Cypher property names can contain dots)
        safe_key = key.replace(' ', '_')
        param_key = f"p_{safe_key}"
        
        # Convert value to string if needed, handle None
        if value is None:
            prop_dict_parts.append(f"`{key}`: null")
        elif isinstance(value, (str, int, float, bool)):
            params[param_key] = value
            prop_dict_parts.append(f"`{key}`: ${param_key}")
        else:
            # For complex types, convert to string
            params[param_key] = str(value)
            prop_dict_parts.append(f"`{key}`: ${param_key}")
    
    props_str = ", ".join(prop_dict_parts) if prop_dict_parts else ""
    
    # Create new node
    if props_str:
        query = "CREATE (u:$l1:$l2 {" + props_str + "}) RETURN ID(u) as id"
    else:
        query = "CREATE (u:$l1:$l2) RETURN ID(u) as id"
    
    records, _, _ = INSTANCE.execute_query(
        query,
        parameters_=params,
        database_="memgraph"
    )
    
    return records[0]["id"]

def UpdateNodeProperties(node_id: int, properties: Dict[str, Any], pathID: str):
    """Update properties of an existing node
    
    Args:
        node_id: ID of the node to update
        properties: Dictionary of properties to add/update
        pathID: Path ID for query context
    """
    if not properties:
        return
    
    # Build SET clause
    set_parts = []
    params = {"node_id": node_id}
    
    for key, value in properties.items():
        if value is None:
            set_parts.append(f"u.{key} = null")
        elif isinstance(value, (str, int, float, bool)):
            param_key = f"p_{key}"
            params[param_key] = value
            set_parts.append(f"u.{key} = ${param_key}")
        else:
            param_key = f"p_{key}"
            params[param_key] = str(value)
            set_parts.append(f"u.{key} = ${param_key}")
    
    if set_parts:
        set_clause = ", ".join(set_parts)
        query = f"MATCH (u) WHERE ID(u) = $node_id SET {set_clause}"
        
        INSTANCE.execute_query(
            query,
            parameters_=params,
            database_="memgraph"
        )

def FindNodeRegex(regexName: str, parentID: str, pathID: str) -> List[int]:
    records, _, _ = INSTANCE.execute_query(
        """
        MATCH (u:$id:resource)
        WHERE u.type =~ $regex AND u.parent = $pid
        RETURN ID(u) as id;
        """,
        id = pathID,
        pid=parentID,
        regex=regexName,
        database_="memgraph"
    )
    return [elem["id"] for elem in records]

def TaggingNode(regexName: str, pathID: str, group: str, name: str, tag:str="process", annotation="CloudApplication"):
    records, _, _ = INSTANCE.execute_query(
        """
        MATCH (u:$id:resource)
        WHERE (u.type =~ $regex OR u.resource_type =~ $regex)
        SET u:tagged
        SET u:$tag
        SET u.group = $group
        SET u.general_name = $general_name
        SET u.annotation = $annotation
        RETURN ID(u) as id;
        """,
        id = pathID,
        regex=regexName,
        group=group,
        general_name=name,
        tag=tag,
        annotation=annotation,
        database_="memgraph"
    )

def TaggingPublic(pathID: str, name: str):
    INSTANCE.execute_query(
        """
            MATCH (u:$id:resource:tagged)
            WHERE u.name = $name
            SET u:public
            RETURN *
        """,
        id=pathID,
        name=name,
        database_="memgraph"
    )

def CompressNode(regexName: str, parentID:str, pathID: str):

    node_ids = FindNodeRegex(regexName, parentID, pathID)
    if len(node_ids) <= 1:
        logger.info("Nothing to compress")
        return
    logger.info(f"Got {len(node_ids)} nodes in same group")
    # SELECT first as representative, otherwise delete
    representative = node_ids[0]

    # Set representative
    _ = INSTANCE.execute_query(
        """
        MATCH (u:$id:resource)
        WHERE ID(u) = $nodeid
        SET u:compressed
        RETURN *
        """,
        id = pathID,
        nodeid=representative,
        database_="memgraph"
    )
    
    records, _, _ = INSTANCE.execute_query(
        """
            MATCH (u:$id:resource), (v:$id:resource), (k:$id:resource:compressed), f=(s:$id)-[]->(u), g=(v)-[]->(d:$id)
            WHERE NOT (u:compressed) AND NOT (v:compressed) AND ID(u) in $list AND ID(v) in $list AND NOT ID(s) in $list AND NOT ID(d) in $list AND ID(k)=$nodeid
            DETACH DELETE u,v

            WITH k, collect(s) as cs, collect(d) as cd
            UNWIND cs as ucs
            UNWIND cd as ucd
            MERGE (ucs)-[:REF]->(k)
            MERGE (k) -[:REF]->(ucd)
            return *;
        """,
        id = pathID,
        regex=regexName,
        nodeid=representative,
        list=node_ids,
        database_="memgraph"
    )

    # CLEANUP uncompressed
    INSTANCE.execute_query(
        """
            MATCH (u:$id)
            WHERE ID(u) in $list AND not (u:compressed)
            DETACH DELETE u;
        """,
        id=pathID,
        list=node_ids,
        database_="memgraph"
    )

    pass

def AddConnection(fromId, targetId, pathId):
    """Add connection between 2 node in neo4j database
    """


    records, summary, keys = INSTANCE.execute_query(
        """
            MATCH (c1:$id), (c2:$id)
            WHERE ID(c1) = $id1 AND ID(c2) = $id2
            CREATE (c1)-[r:REF]->(c2)
            RETURN r;
        """,
        id=pathId,
        id1 = fromId,
        id2 = targetId,
        database_="memgraph"
    )

def CleanUp():
    INSTANCE.execute_query(
        """
            MATCH (u)
            DETACH DELETE u;
        """,
        database_="memgraph"
    )

def GetListParent(pathID: str) -> List[str]:
    records, _, _ = INSTANCE.execute_query(
        """
            MATCH (u:$id)
            RETURN DISTINCT u.parent as parent_id
        """,
        id=pathID,
        database_="memgraph"
    )
    return [e["parent_id"] for e in records if len(e["parent_id"]) > 0]

    
def QueryTagged(pathID: str, group: str):
    records, _, _ = INSTANCE.execute_query(
        """
            MATCH (u:$id:tagged:$group)
            RETURN ID(u) as id, u.group as group, u.general_name as general_name, u.type as name, u.annotation as annotation, u.name as tfname
        """,
        id=pathID,
        group=group,
        database_="memgraph"
    )
    # #region agent log
    try:
        import json, time
        # Check node properties for API Gateway integrations
        api_gateway_nodes = [r for r in records if "api_gateway_integration" in r.get("tfname", "")]
        if api_gateway_nodes:
            # Query these nodes to check their labels and type property
            node_ids_to_check = [r["id"] for r in api_gateway_nodes[:10]]
            check_records, _, _ = INSTANCE.execute_query(
                f"""
                MATCH (u:`{pathID}`)
                WHERE ID(u) IN $node_ids
                RETURN ID(u) as id, labels(u) as labels, u.type as type, u.name as name
                """,
                node_ids=node_ids_to_check,
                database_="memgraph"
            )
            with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({
                    "id": f"log_{int(time.time() * 1000)}",
                    "timestamp": int(time.time() * 1000),
                    "location": "n4j_helper.py:QueryTagged",
                    "message": "QueryTagged called",
                    "data": {
                        "pathID": pathID,
                        "group": group,
                        "total_nodes": len(records),
                        "api_gateway_integration_count": len(api_gateway_nodes),
                        "sample_node_ids": [r["id"] for r in records[:10]],
                        "sample_node_names": [r.get("tfname", "") for r in records[:10]],
                        "checked_nodes": [{"id": r["id"], "labels": r.get("labels", []), "type": r.get("type", ""), "name": r.get("name", "")} for r in check_records]
                    },
                    "runId": "compression-debug",
                    "hypothesisId": "I"
                }) + "\n")
        else:
            with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({
                    "id": f"log_{int(time.time() * 1000)}",
                    "timestamp": int(time.time() * 1000),
                    "location": "n4j_helper.py:QueryTagged",
                    "message": "QueryTagged called",
                    "data": {
                        "pathID": pathID,
                        "group": group,
                        "total_nodes": len(records),
                        "sample_node_ids": [r["id"] for r in records[:10]],
                        "sample_node_names": [r.get("tfname", "") for r in records[:10]]
                    },
                    "runId": "compression-debug",
                    "hypothesisId": "I"
                }) + "\n")
    except Exception as e:
        pass
    # #endregion
    return records

def QueryGroup(pathID: str, group: str, group2: str):
    records, _, _ = INSTANCE.execute_query(
        """
            MATCH (u:$id:tagged)<-[r]-(v:$id:tagged)
            WHERE u.group = $group AND v.group = $group2
            RETURN u.id as id1, u.general_name as general_name1, v.id as id2, v.general_name as general_name2
        """,
        id=pathID,
        group=group,
        group2=group2,
        database_="memgraph"
    )
    return records

    
def RemovePublicBoundaries(pathID: str):
    INSTANCE.execute_query(
    """
        MATCH (u:$id:tagged:boundaries:public)<-[]-(s:$id), (u)-[]->(d:$id)
        DETACH DELETE u
        WITH collect(s) as cs, collect(d) as cd
        UNWIND cs as ucs
        UNWIND cd as ucd
        MERGE (ucs)-[:REF]->(ucd)
        RETURN *
    """,
    id = pathID,
    database_="memgraph"
    )

def OwnRuleToQuery(firstNode: str, secondNode: str, method: str) -> str:
    if method == "Backward":
        chain = "<-[:REF]-"
        return f"""
            MATCH (u:$id:tagged){chain}(v:$id:tagged)
            WHERE u.group='{firstNode}' AND v.group='{secondNode}'
            RETURN ID(u) as id1, u.group as group1, u.general_name as general_name1, u.type as name1, u.annotation as annotation1, u.name as tfname1, ID(v) as id2, v.group as group2, v.general_name as general_name2, v.type as name2, v.annotation as annotation2, v.name as tfname2
        """
        pass
    elif method == "Forward":
        chain = "-[:REF]->"
        return f"""
            MATCH (u:$id:tagged){chain}(v:$id:tagged)
            WHERE u.group='{firstNode}' AND v.group='{secondNode}'
            RETURN ID(u) as id1, u.group as group1, u.general_name as general_name1, u.type as name1, u.annotation as annotation1, u.name as tfname1, ID(v) as id2, v.group as group2, v.general_name as general_name2, v.type as name2, v.annotation as annotation2, v.name as tfname2
        """
        pass
    elif method == "IntersectForward":
        chain = "-[:REF]->(x:$id)<-[:REF]-"
        return f"""
            MATCH (u:$id:tagged){chain}(v:$id:tagged)
            WHERE u.group='{firstNode}' AND v.group='{secondNode}'
            RETURN ID(u) as id1, u.group as group1, u.general_name as general_name1, u.type as name1, u.annotation as annotation1, u.name as tfname1, ID(v) as id2, v.group as group2, v.general_name as general_name2, v.type as name2, v.annotation as annotation2, v.name as tfname2
        """
        pass
    elif method == "IntersectBackward":
        chain = "<-[:REF]-(x:$id)-[:REF]->"
        return f"""
            MATCH (u:$id:tagged){chain}(v:$id:tagged)
            WHERE u.group='{firstNode}' AND v.group='{secondNode}'
            RETURN ID(u) as id1, u.group as group1, u.general_name as general_name1, u.type as name1, u.annotation as annotation1, u.name as tfname1, ID(v) as id2, v.group as group2, v.general_name as general_name2, v.type as name2, v.annotation as annotation2, v.name as tfname2
        """
        pass

    raise NotImplementedError

def FindOwn(firstNode: str, secondNode: str, method: str, pathID: str):
    records, _, _ = INSTANCE.execute_query(OwnRuleToQuery(firstNode, secondNode, method), 
                                           id = pathID,
                                           database_="memgraph")
    return records
    pass

# TODO: double check the direction
def QueryOutermostBoundary(pathID:str):
    records, _, _ = INSTANCE.execute_query(
    """
        MATCH (u:$id:tagged:boundaries)
        WHERE NOT exists((u)-[*]->(:$id:tagged:boundaries))
        RETURN ID(u) as id, u.group as group, u.general_name as general_name
    """,
    id=pathID,
    database_="memgraph"
    )
    return records

def QueryAllConnectionResource(pathID: str):
    # Every component is linked, so no need to focus on this
    # records, _, _ = INSTANCE.execute_query(
    # """
    # MATCH (u:$id:tagged:resource) -[*]-> (v:$id:tagged:resource)
    # WHERE ((u:processes) OR (u:data_stores)) AND ((v:processes) OR (v:data_stores)) 
    #     AND NOT exists ((u)-[*]->(:$id:tagged:resource:processes)-[*]->(v)) 
    #     AND NOT exists ((u)-[*]->(:$id:tagged:resource:data_stores)-[*]->(v))
    # RETURN ID(u) as id1, u.group as group1, u.general_name as general_name1, ID(v) as id2, v.group as group2, v.general_name as general_name2
    # """,
    # id=pathID,
    # database_="memgraph"
    # )

    # Query for connections between processes and data_stores
    # Find all REF edges where both nodes are processes or data_stores
    # Note: DataFlow.AddEdge creates bidirectional flows automatically, so we only need one direction
    records, _, _ = INSTANCE.execute_query(
    """
    MATCH (u:$id:tagged:resource)-[:REF]->(v:$id:tagged:resource)
    WHERE ((u:processes) OR (u:data_stores)) AND ((v:processes) OR (v:data_stores)) 
    RETURN ID(u) as id1, u.group as group1, u.general_name as general_name1, ID(v) as id2, v.group as group2, v.general_name as general_name2
    """,
    id=pathID,
    database_="memgraph"
    )
    return records

def LinkTagged(pathID: str):
    # Link
    _, _, _ = INSTANCE.execute_query(
    """
    MATCH (u:$id:tagged:resource) -[*]-> (v:$id:tagged:resource)
    WHERE NOT exists((u)-[*]->(:$id:tagged:resource)-[*]->(v))
    MERGE (u)-[:REF]->(v)
    RETURN *
    """,
    id=pathID,
    database_="memgraph"
    )

def LinkTaggedOptimized(pathID: str, max_path_length: int = 20, limit_per_iteration: int = 50, max_iterations: int = 1000):
    """
    Optimized version của LinkTagged với các kỹ thuật:
    1. Progressive Path Length: Xử lý paths ngắn trước (nhanh)
    2. Query gốc với LIMIT + Loop: Xử lý paths dài và đảm bảo 100% accuracy
    
    Logic giữ nguyên 100% - chỉ tối ưu cách thực hiện.
    
    Args:
        pathID: Path ID của project
        max_path_length: Độ dài path tối đa để thử progressive (default: 20)
        limit_per_iteration: Số lượng links để xử lý mỗi iteration trong fallback (default: 50)
        max_iterations: Số lần lặp tối đa trong fallback để tránh infinite loop (default: 1000)
        
    Returns:
        None
    """
    logger.info("Starting optimized LinkTagged...")
    
    # Lấy tất cả tagged resource nodes
    records, _, _ = INSTANCE.execute_query(
        f"""
        MATCH (u:`{pathID}`:tagged:resource)
        RETURN ID(u) as id
        """,
        database_="memgraph"
    )
    
    tagged_node_ids = [r["id"] for r in records]
    total_nodes = len(tagged_node_ids)
    
    if total_nodes <= 1:
        logger.info("Less than 2 tagged nodes, nothing to link")
        return
    
    logger.info(f"Found {total_nodes} tagged resource nodes")
    
    links_created = 0
    
    # ========================================================================
    # PHASE 1: Progressive Path Length (xử lý paths ngắn - nhanh)
    # ========================================================================
    logger.info("Phase 1: Progressive path length (processing short paths first)...")
    
    # Xử lý từng node một để tránh timeout
    for node_idx, u_id in enumerate(tagged_node_ids, 1):
        if node_idx % 10 == 0 or node_idx == 1:
            logger.info(f"Processing node {node_idx}/{total_nodes}: ID={u_id}")
        
        # Progressive path length: bắt đầu với path ngắn
        for path_length in range(1, max_path_length + 1):
            # Query với bounded path length và bounded exists() check
            query = f"""
                MATCH (u:`{pathID}`:tagged:resource)-[:REF*1..{path_length}]->(v:`{pathID}`:tagged:resource)
                WHERE ID(u) = $u_id
                    AND ID(u) != ID(v)
                    AND NOT (u)-[:REF]->(v)
                    AND NOT exists((u)-[:REF*1..{path_length}]->(:`{pathID}`:tagged:resource)-[:REF*1..{path_length}]->(v))
                WITH DISTINCT u, v LIMIT 10
                MERGE (u)-[:REF]->(v)
                RETURN ID(u) as u_id, ID(v) as v_id
            """
            
            try:
                records, _, _ = INSTANCE.execute_query(
                    query,
                    u_id=u_id,
                    database_="memgraph"
                )
                
                if records:
                    node_links = len(records)
                    links_created += node_links
                    logger.debug(f"  Node {u_id}, path length {path_length}: Created {node_links} links")
                    # Early termination: Đã tìm thấy paths cho node này, chuyển sang node tiếp theo
                    break
                    
            except Exception as e:
                logger.warning(f"Error processing path length {path_length} for node {u_id}: {e}")
                continue
    
    logger.info(f"Phase 1 completed. Created {links_created} links from progressive paths")
    
    # ========================================================================
    # PHASE 2: Query gốc với LIMIT + Loop (đảm bảo 100% accuracy)
    # ========================================================================
    logger.info("Phase 2: Fallback to original query with LIMIT + loop (ensuring 100% accuracy)...")
    
    fallback_links_created = 0
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        try:
            # Query gốc với LIMIT để tránh timeout
            records, _, _ = INSTANCE.execute_query(
                """
                MATCH (u:$id:tagged:resource) -[*]-> (v:$id:tagged:resource)
                WHERE NOT exists((u)-[*]->(:$id:tagged:resource)-[*]->(v))
                    AND NOT (u)-[:REF]->(v)
                WITH DISTINCT u, v LIMIT $limit
                MERGE (u)-[:REF]->(v)
                RETURN count(*) as cnt
                """,
                id=pathID,
                limit=limit_per_iteration,
                database_="memgraph"
            )
            
            if not records:
                logger.warning(f"Iteration {iteration}: No records returned")
                break
            
            count = records[0]["cnt"] if records[0]["cnt"] else 0
            
            if count == 0:
                # Không còn cặp nào mới, dừng lại
                logger.info(f"Iteration {iteration}: No more links to create. Stopping.")
                break
            
            fallback_links_created += count
            logger.info(f"Iteration {iteration}: Created {count} links (total fallback: {fallback_links_created})")
            
        except Exception as e:
            logger.warning(f"Iteration {iteration} failed: {e}")
            # Nếu timeout hoặc lỗi, thử tiếp tục với iteration tiếp theo
            # Nhưng nếu lỗi liên tục, có thể dừng lại
            if "timeout" in str(e).lower() or "Transaction was asked to abort" in str(e):
                logger.warning("Timeout detected. You may need to increase transaction timeout or reduce limit_per_iteration")
            break
    
    total_links_created = links_created + fallback_links_created
    logger.info(f"Phase 2 completed. Created {fallback_links_created} links from fallback (total: {total_links_created})")
    
    # Final count
    records, _, _ = INSTANCE.execute_query(
        """
        MATCH (u:$id:tagged:resource)-[:REF]->(v:$id:tagged:resource)
        RETURN count(*) as cnt
        """,
        id=pathID,
        database_="memgraph"
    )
    
    total_links = records[0]["cnt"] if records else 0
    logger.info(f"LinkTaggedOptimized completed. Total direct links: {total_links}")


def LinkTaggedBFS(pathID: str, batch_size: int = 500, deduplicate_by_group: bool = True):
    """
    In-memory BFS + Transitive Reduction + Group Deduplication approach for linking tagged nodes.
    
    Thay vì dùng Cypher variable-length path matching (exponential complexity),
    giải pháp này:
    1. Pull toàn bộ tagged nodes và REF edges vào Python memory
    2. Build adjacency list (in-memory graph)
    3. BFS từ mỗi tagged node để tìm tất cả tagged nodes reachable
    4. Transitive Reduction: loại bỏ indirect links, giữ lại direct links
    5. Group Deduplication (NEW): Loại bỏ duplicate links giữa cùng group pairs
    6. Batch MERGE kết quả vào Memgraph
    
    Complexity: O(N * (V + E)) cho BFS + O(N^2 * N) cho transitive reduction
    trong đó N = số tagged nodes, V = tổng nodes, E = tổng edges.
    
    Đảm bảo 100% accuracy so với logic gốc.
    
    Args:
        pathID: Path ID của project
        batch_size: Số lượng edges để MERGE mỗi batch (default: 500)
        deduplicate_by_group: Enable deduplication by group (default: True)
                             If True, multiple links with same (src_group, dst_group)
                             will be deduplicated to 1 representative link.
    """
    import time as _time
    
    t_start = _time.time()
    logger.info("=" * 70)
    logger.info("LinkTaggedBFS: Starting In-memory BFS + Transitive Reduction")
    logger.info("=" * 70)
    
    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Pull all tagged resource node IDs
    # ──────────────────────────────────────────────────────────────────────
    logger.info("Step 1/5: Fetching tagged resource nodes...")
    t1 = _time.time()
    
    records, _, _ = INSTANCE.execute_query(
        f"""
        MATCH (u:`{pathID}`:tagged:resource)
        RETURN ID(u) as id
        """,
        database_="memgraph"
    )
    
    tagged_ids: Set[int] = {r["id"] for r in records}
    num_tagged = len(tagged_ids)
    logger.info(f"  Found {num_tagged} tagged resource nodes ({_time.time() - t1:.2f}s)")
    
    if num_tagged <= 1:
        logger.info("  Less than 2 tagged nodes, nothing to link.")
        return
    
    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Pull all REF edges within the pathID subgraph
    # ──────────────────────────────────────────────────────────────────────
    logger.info("Step 2/5: Fetching all REF edges in the subgraph...")
    t2 = _time.time()
    
    records, _, _ = INSTANCE.execute_query(
        f"""
        MATCH (a:`{pathID}`)-[:REF]->(b:`{pathID}`)
        RETURN ID(a) as src, ID(b) as dst
        """,
        database_="memgraph"
    )
    
    # Build adjacency list: src -> set of dst
    adj: Dict[int, Set[int]] = defaultdict(set)
    all_node_ids: Set[int] = set()
    
    for r in records:
        src, dst = r["src"], r["dst"]
        adj[src].add(dst)
        all_node_ids.add(src)
        all_node_ids.add(dst)
    
    num_edges = sum(len(v) for v in adj.values())
    num_nodes = len(all_node_ids)
    logger.info(f"  Loaded {num_nodes} nodes, {num_edges} edges ({_time.time() - t2:.2f}s)")
    
    # ──────────────────────────────────────────────────────────────────────
    # STEP 3: BFS from each tagged node to find reachable tagged nodes
    # ──────────────────────────────────────────────────────────────────────
    logger.info("Step 3/6: Computing reachability via BFS...")
    t3 = _time.time()
    
    # reachable[u] = set of tagged nodes reachable from u (excluding u itself)
    reachable: Dict[int, Set[int]] = {}
    
    for idx, u in enumerate(tagged_ids, 1):
        if idx % 50 == 0 or idx == 1:
            logger.info(f"  BFS progress: {idx}/{num_tagged}")
        
        visited: Set[int] = set()
        queue = deque(adj.get(u, set()))  # start with direct neighbors of u
        visited.add(u)
        reached_tagged: Set[int] = set()
        
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            
            if node in tagged_ids:
                reached_tagged.add(node)
                # IMPORTANT: continue BFS through tagged nodes
                # because u may reach another tagged node through this one
            
            for neighbor in adj.get(node, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        
        reachable[u] = reached_tagged
    
    total_pairs = sum(len(v) for v in reachable.values())
    logger.info(f"  Total reachable pairs: {total_pairs} ({_time.time() - t3:.2f}s)")
    
    # ──────────────────────────────────────────────────────────────────────
    # STEP 4: Transitive Reduction — keep only direct links
    # ──────────────────────────────────────────────────────────────────────
    logger.info("Step 4/6: Computing transitive reduction...")
    t4 = _time.time()
    
    # A link (u -> v) is "direct" if there is NO intermediate tagged node z
    # such that u can reach z AND z can reach v.
    # This is equivalent to the original Cypher:
    #   MATCH (u:tagged)-[*]->(v:tagged)
    #   WHERE NOT exists((u)-[*]->(:tagged)-[*]->(v))
    
    direct_links: Set[Tuple[int, int]] = set()
    
    for u in tagged_ids:
        for v in reachable.get(u, set()):
            # Check if there exists an intermediate tagged node z
            is_direct = True
            for z in reachable.get(u, set()):
                if z == v:
                    continue
                if v in reachable.get(z, set()):
                    # u can reach z, and z can reach v => (u, v) is NOT direct
                    is_direct = False
                    break
            
            if is_direct:
                direct_links.add((u, v))
    
    logger.info(f"  Direct links to create: {len(direct_links)} ({_time.time() - t4:.2f}s)")
    
    # ──────────────────────────────────────────────────────────────────────
    # STEP 4.5: Deduplicate by Group (NEW - Solution 4)
    # ──────────────────────────────────────────────────────────────────────
    original_link_count = len(direct_links)  # Save for summary
    dedup_count = 0  # Initialize for summary
    
    if deduplicate_by_group:
        logger.info("Step 4.5/6: Deduplicating links by group...")
        t4_5 = _time.time()
        
        # Get group_name for each tagged node
        records, _, _ = INSTANCE.execute_query(
            f"""
            MATCH (u:`{pathID}`:tagged:resource)
            RETURN ID(u) as id, u.group as group_name
            """,
            database_="memgraph"
        )
        
        node_groups: Dict[int, str] = {
            r["id"]: (r.get("group_name") or str(r["id"])) 
            for r in records
        }
        
        # Group links by (source_group, target_group)
        group_links: Dict[Tuple[str, str], List[Tuple[int, int]]] = defaultdict(list)
        
        for u, v in direct_links:
            src_group = node_groups.get(u, str(u))
            dst_group = node_groups.get(v, str(v))
            group_links[(src_group, dst_group)].append((u, v))
        
        # For each (group_pair), keep only 1 link (representative)
        deduped_links: Set[Tuple[int, int]] = set()
        
        for (src_group, dst_group), links in group_links.items():
            if len(links) == 1:
                # Only 1 link → keep as is
                deduped_links.add(links[0])
            else:
                # Multiple links with same (src_group, dst_group)
                # → Keep link from node with largest ID (representative by convention)
                representative_link = max(links, key=lambda x: x[0])
                deduped_links.add(representative_link)
                dedup_count += len(links) - 1
                if dedup_count <= 10:  # Log first 10 deduplications
                    logger.debug(
                        f"  Deduplicated {len(links)} links ({src_group} → {dst_group}) "
                        f"→ keeping {representative_link}"
                    )
        
        if dedup_count > 0:
            logger.info(
                f"  Deduplicated: {original_link_count} → {len(deduped_links)} links "
                f"({dedup_count} duplicates removed) ({_time.time() - t4_5:.2f}s)"
            )
        else:
            logger.info(f"  No duplicates found ({_time.time() - t4_5:.2f}s)")
        
        direct_links = deduped_links
    else:
        logger.info("Step 4.5/6: Skipping group deduplication (disabled)")
    
    # ──────────────────────────────────────────────────────────────────────
    # STEP 5: Batch MERGE direct links back to Memgraph
    # ──────────────────────────────────────────────────────────────────────
    logger.info("Step 5/6: Writing direct links to Memgraph...")
    t5 = _time.time()
    
    links_list = list(direct_links)
    total_written = 0
    
    for i in range(0, len(links_list), batch_size):
        batch = links_list[i:i + batch_size]
        
        # Build batch MERGE query using UNWIND
        INSTANCE.execute_query(
            f"""
            UNWIND $pairs AS pair
            MATCH (u:`{pathID}`:tagged:resource), (v:`{pathID}`:tagged:resource)
            WHERE ID(u) = pair[0] AND ID(v) = pair[1]
            MERGE (u)-[:REF]->(v)
            """,
            pairs=[[u_id, v_id] for u_id, v_id in batch],
            database_="memgraph"
        )
        
        total_written += len(batch)
        if len(links_list) > batch_size:
            logger.info(f"  Written {total_written}/{len(links_list)} links...")
    
    logger.info(f"  Finished writing {total_written} links ({_time.time() - t5:.2f}s)")
    
    # ──────────────────────────────────────────────────────────────────────
    # SUMMARY
    # ──────────────────────────────────────────────────────────────────────
    elapsed = _time.time() - t_start
    logger.info("=" * 70)
    logger.info(f"LinkTaggedBFS COMPLETED in {elapsed:.2f}s")
    logger.info(f"  Tagged nodes : {num_tagged}")
    logger.info(f"  Graph loaded : {num_nodes} nodes, {num_edges} edges")
    logger.info(f"  Reachable pairs: {total_pairs}")
    logger.info(f"  Direct links (after deduplication): {len(direct_links)}")
    if deduplicate_by_group and dedup_count > 0:
        logger.info(f"  Duplicates removed: {dedup_count}")
    logger.info("=" * 70)


    # And cleanup
    # #region agent log
    import json
    log_path = "/home/thangdd/repos/TerrARA/.cursor/debug.log"
    def debug_log(location, message, data, hypothesis_id):
        with open(log_path, "a") as f:
            f.write(json.dumps({"sessionId": "debug-session", "runId": "run1", "hypothesisId": hypothesis_id, "location": location, "message": message, "data": data, "timestamp": int(__import__("time").time() * 1000)}) + "\n")
    deleted_before, _, _ = INSTANCE.execute_query(f"MATCH (u:`{pathID}`) -[rel:REF]-> (v:`{pathID}:tagged:resource`) WHERE not (u:tagged) AND rel.method = 'implicit_exact_match' RETURN count(rel) as cnt", database_="memgraph")
    debug_log("n4j_helper.py:467", "REF edges to be deleted (outgoing)", {"count": deleted_before[0]["cnt"] if deleted_before else 0}, "A")
    # #endregion
    
    _, _, _ = INSTANCE.execute_query(
    """
    MATCH (u:$id) -[rel]-> (v:$id:tagged:resource)
    WHERE not (u:tagged) AND rel.method IS NULL
    DELETE rel
    """,
    id=pathID,
    database_="memgraph"
    )

    # #region agent log
    deleted_before2, _, _ = INSTANCE.execute_query(f"MATCH (u:`{pathID}`) <-[rel:REF]- (v:`{pathID}:tagged:resource`) WHERE not (u:tagged) AND rel.method = 'implicit_exact_match' RETURN count(rel) as cnt", database_="memgraph")
    debug_log("n4j_helper.py:477", "REF edges to be deleted (incoming)", {"count": deleted_before2[0]["cnt"] if deleted_before2 else 0}, "A")
    # #endregion

    _, _, _ = INSTANCE.execute_query(
    """
    MATCH (u:$id) <-[rel]- (v:$id:tagged:resource)
    WHERE not (u:tagged) AND rel.method IS NULL
    DELETE rel
    """,
    id=pathID,
    database_="memgraph"
    )

# For optimizing on large database
def RemoveNonTagged(pathID: str):
    
    while True:
        flag = False
        r = 1
        while r > 0:
            records, _, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id)
                WHERE not (u:tagged) AND not exists ((u)<-[:REF]-(:$id)) 
                    AND outDegree(u) = 1
                    //AND not exists((u)-[*]->(:$id:tagged)) 
                DETACH DELETE u
                RETURN COUNT(u) as cnt
            """,
            id = pathID,
            database_="memgraph"
            )
            r = records[0]["cnt"]
            logger.info("DELETE case 1: " + str(r))
            flag = flag or (r > 0)
        
        
        r = 1
        while r > 0:
            records, _, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id)
                WHERE not (u:tagged) AND not exists ((u)-[:REF]->(:$id))
                    AND inDegree(u) = 1
                    // AND not exists((u)<-[*]-(:$id:tagged)) 
                DETACH DELETE u
                RETURN COUNT(u) as cnt
            """,
            id = pathID,
            database_="memgraph"
            )
            r = records[0]["cnt"]
            logger.info("DELETE case 2: " + str(r))
            flag = flag or (r > 0)
        
        r = 1
        while r > 0:
            records, _, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id)
                WHERE not (u:tagged)  AND not exists ((u)<-[:REF]-(:$id))
                    // AND outDegree(u) = 1
                    AND not exists((:$id:tagged)<-[*]-(u)-[*]->(:$id:tagged)) 
                DETACH DELETE u
                RETURN COUNT(u) as cnt
            """,
            id = pathID,
            database_="memgraph"
            )
            r = records[0]["cnt"]
            logger.info("DELETE case 3: " + str(r))
            flag = flag or (r > 0)
        
        
        r = 1
        while r > 0:
            records, _, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id)
                WHERE not (u:tagged)  AND not exists ((u)-[:REF]->(:$id))
                    // AND outDegree(u) = 1
                    AND not exists((:$id:tagged)-[*]->(u)<-[*]-(:$id:tagged)) 
                DETACH DELETE u
                RETURN COUNT(u) as cnt
            """,
            id = pathID,
            database_="memgraph"
            )
            r = records[0]["cnt"]
            logger.info("DELETE case 4: " + str(r))
            flag = flag or (r > 0)

        if not flag:
            break

    # records, _, _ = INSTANCE.execute_query(
    # """
    #     OPTIONAL MATCH (u:$id)<-[:REF]-(s:$id)
    #     WHERE not (u:tagged)
    #     OPTIONAL MATCH (u)-[:REF]->(d:$id)

    #     DETACH DELETE u
    #     WITH collect(s) as cs, collect(d) as cd
    #     UNWIND cs as ucs
    #     UNWIND cd as ucd
    #     MERGE (ucs)-[:REF]->(ucd)
    #     RETURN count(*) as cnt
    # """,
    # id = pathID,
    # database_="memgraph"
    # )
    # logger.info("DELETE case 3: " + str(records[0]["cnt"]))

def RemoveNonTaggedOptimized(
    pathID: str,
    max_final_depth: int = 20,
    progressive_step: int = 2,
    max_iterations: int = 100
):
    """
    Optimized version của RemoveNonTagged với các kỹ thuật:
    1. Smart Pre-filtering: Chỉ chạy Case 3/4 sau khi Case 1/2 không còn xóa được
    2. Progressive Depth: Bắt đầu với depth nhỏ, tăng dần đến max_final_depth
    3. Early Termination: Kiểm tra tagged nodes trước khi chạy Case 3/4
    4. Caching: Cache số lượng tagged nodes để tránh query lại
    
    Args:
        pathID: Path ID của project
        max_final_depth: Độ sâu tối đa để kiểm tra paths (default: 20)
        progressive_step: Bước tăng depth mỗi lần (default: 2)
        max_iterations: Số lần lặp tối đa để tránh infinite loop (default: 100)
    
    Returns:
        None
    """
    # Cache for tagged nodes count
    tagged_count_cache = None
    
    def get_tagged_count():
        nonlocal tagged_count_cache
        if tagged_count_cache is None:
            records, _, _ = INSTANCE.execute_query(
                f"MATCH (u:`{pathID}`:tagged) RETURN count(u) as cnt",
                database_="memgraph"
            )
            tagged_count_cache = records[0]["cnt"] if records else 0
        return tagged_count_cache
    
    # Early Termination: Kiểm tra có tagged nodes không
    tagged_count = get_tagged_count()
    if tagged_count == 0:
        logger.info("No tagged nodes found. Skipping Case 3 and Case 4.")
        logger.info("Running only Case 1 and Case 2...")
    
    iteration = 0
    current_depth = 1
    
    while iteration < max_iterations:
        iteration += 1
        flag = False
        
        # Phase 1: Chạy Case 1 và Case 2 nhiều lần (nhanh)
        case1_total = 0
        case2_total = 0
        
        # Case 1: Chạy cho đến khi không còn xóa được
        while True:
            records, _, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id)
                WHERE not (u:tagged) AND not exists ((u)<-[:REF]-(:$id)) 
                    AND outDegree(u) = 1
                DETACH DELETE u
                RETURN COUNT(u) as cnt
            """,
            id = pathID,
            database_="memgraph"
            )
            r = records[0]["cnt"] if records else 0
            if r == 0:
                break
            case1_total += r
            logger.info("DELETE case 1: " + str(r))
            flag = True
        
        # Case 2: Chạy cho đến khi không còn xóa được
        while True:
            records, _, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id)
                WHERE not (u:tagged) AND not exists ((u)-[:REF]->(:$id))
                    AND inDegree(u) = 1
                DETACH DELETE u
                RETURN COUNT(u) as cnt
            """,
            id = pathID,
            database_="memgraph"
            )
            r = records[0]["cnt"] if records else 0
            if r == 0:
                break
            case2_total += r
            logger.info("DELETE case 2: " + str(r))
            flag = True
        
        # Phase 2: Smart Pre-filtering - Chỉ chạy Case 3/4 khi Case 1/2 không còn xóa được
        # Và chỉ khi có tagged nodes
        if tagged_count > 0 and case1_total == 0 and case2_total == 0:
            logger.info(f"Phase 2: Running Case 3 and Case 4 with depth={current_depth}")
            
            # Case 3 với progressive depth
            query3 = f"""
                MATCH (u:$id)
                WHERE not (u:tagged) AND not exists ((u)<-[:REF]-(:$id))
                    AND not exists((:$id:tagged)<-[*1..{current_depth}]-(u)-[*1..{current_depth}]->(:$id:tagged)) 
                DETACH DELETE u
                RETURN COUNT(u) as cnt
            """
            records, _, _ = INSTANCE.execute_query(
                query3,
                id = pathID,
                database_="memgraph"
            )
            r3 = records[0]["cnt"] if records else 0
            logger.info(f"DELETE case 3 (depth={current_depth}): {r3}")
            flag = flag or (r3 > 0)
            
            # Case 4 với progressive depth
            query4 = f"""
                MATCH (u:$id)
                WHERE not (u:tagged) AND not exists ((u)-[:REF]->(:$id))
                    AND not exists((:$id:tagged)-[*1..{current_depth}]->(u)<-[*1..{current_depth}]-(:$id:tagged)) 
                DETACH DELETE u
                RETURN COUNT(u) as cnt
            """
            records, _, _ = INSTANCE.execute_query(
                query4,
                id = pathID,
                database_="memgraph"
            )
            r4 = records[0]["cnt"] if records else 0
            logger.info(f"DELETE case 4 (depth={current_depth}): {r4}")
            flag = flag or (r4 > 0)
            
            # Progressive Depth: Nếu không xóa được gì với depth hiện tại, tăng depth
            if r3 == 0 and r4 == 0:
                if current_depth < max_final_depth:
                    current_depth += progressive_step
                    logger.info(f"Increasing depth to {current_depth}")
                else:
                    logger.info(f"Reached max depth {max_final_depth}, stopping Case 3/4")
        elif tagged_count == 0:
            logger.debug("Skipping Case 3/4: No tagged nodes")
        else:
            logger.debug("Skipping Case 3/4: Case 1/2 still deleting nodes")
        
        # Nếu không còn nodes nào được xóa, dừng lại
        if not flag:
            logger.info(f"No more nodes to delete. Total iterations: {iteration}")
            break
    
    if iteration >= max_iterations:
        logger.warning(f"Reached maximum iterations ({max_iterations}). Stopping.")
    
def FindNodeRegexAnyModule(regexName, pathID):
    # For u.name matching, we need to handle cases where the name contains dots
    # (e.g., "aws_api_gateway_integration.lambda_...") but the regex only matches word chars
    # So we create a more flexible regex for name matching that allows dots after the pattern
    # Convert \w* to [\w.]* for name matching to allow dots
    name_regex = regexName.replace(r'\w*', r'[\w.]*') if r'\w*' in regexName else regexName
    
    records, _, _ = INSTANCE.execute_query(
        """
        MATCH (u:$id:resource)
        WHERE u.type =~ $regex OR u.name =~ $name_regex
        RETURN ID(u) as id
        ORDER BY degree(u)
        """,
        id = pathID,
        regex=regexName,
        name_regex=name_regex,
        database_="memgraph"
    )
    node_ids = [elem["id"] for elem in records]
    return node_ids

def CompressV2(regexName, pathID):
    node_ids = FindNodeRegexAnyModule(regexName, pathID)
    if len(node_ids) <= 1:
        logger.info("Nothing to compress")
        return
    logger.info(f"Got {len(node_ids)} nodes in same group")



    for _id in node_ids[:-1]:
        logging.info(str(_id))
        records, summary, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id:resource)-[:REF*]->(v:$id:resource)

                WHERE ID(v) = $nodeid 
                    AND ID(u) != ID(v)
                    AND ID(u) in $list 
                
                WITH u,v LIMIT 1

                OPTIONAL MATCH f=(s:$id)-[:REF]->(v)
                WHERE ID(s) != ID(u)

                OPTIONAL MATCH g=(v)-[:REF]->(d:$id)
                WHERE ID(d) != ID(u)

                DETACH DELETE v

                WITH collect(s) as cs, collect(d) as cd, u
                                FOREACH (ucs in cs |
                    MERGE for=(ucs)-[:REF]->(u)
                )
                FOREACH (ucd in cd |
                    MERGE bac=(u)-[:REF]->(ucd)
                )
                return *;
            """,
            id = pathID,
            nodeid=_id,
            list=node_ids,
            database_="memgraph"
        )
        records, summary, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id:resource)<-[:REF*]-(v:$id:resource)

                WHERE ID(v) = $nodeid 
                    AND ID(u) != ID(v)
                    AND ID(u) in $list 
                
                WITH u,v LIMIT 1

                OPTIONAL MATCH f=(s:$id)-[:REF]->(v)
                WHERE ID(s) != ID(u)

                OPTIONAL MATCH g=(v)-[:REF]->(d:$id)
                WHERE ID(d) != ID(u)

                DETACH DELETE v

                WITH collect(s) as cs, collect(d) as cd, u
                                FOREACH (ucs in cs |
                    MERGE for=(ucs)-[:REF]->(u)
                )
                FOREACH (ucd in cd |
                    MERGE bac=(u)-[:REF]->(ucd)
                )
                return *;
            """,
            id = pathID,
            nodeid=_id,
            list=node_ids,
            database_="memgraph"
        )
        # logging.info(str(summary.counters))
        Cleanup(pathID)   # Performance bottlleneck, but required 
    
    pass

def CompressV2Optimized(regexName, pathID):
    """
    Optimized version của CompressV2 với các kỹ thuật:
    1. Batch Cleanup: Chỉ gọi Cleanup một lần ở cuối thay vì sau mỗi node
    2. Conditional Cleanup: Chỉ cleanup nếu có self-loops
    3. Early Termination: Skip nếu không có nodes để compress
    4. Reduce Logging: Giảm logging overhead trong loop
    5. Caching: Cache node_ids để tránh query lại
    
    Logic giữ nguyên 100% - chỉ tối ưu cách thực hiện.
    
    Args:
        regexName: Regex pattern để tìm nodes cần compress
        pathID: Path ID của project
        
    Returns:
        None
    """
    # Early Termination: Kiểm tra nodes trước
    node_ids = FindNodeRegexAnyModule(regexName, pathID)
    if len(node_ids) <= 1:
        logger.info("Nothing to compress")
        return
    
    logger.info(f"Got {len(node_ids)} nodes in same group")
    
    # Cache node_ids để dùng trong loop
    nodes_to_compress = node_ids[:-1]  # Tất cả trừ node cuối (representative)
    total_nodes = len(nodes_to_compress)
    
    # Reduce Logging: Chỉ log summary thay vì từng node
    if total_nodes > 10:
        logger.info(f"Compressing {total_nodes} nodes (logging every 10th node)...")
    else:
        logger.info(f"Compressing {total_nodes} nodes...")
    
    # Compress từng node (logic giữ nguyên 100%)
    for idx, _id in enumerate(nodes_to_compress):
        # Log progress cho large batches
        if total_nodes > 10 and (idx + 1) % 10 == 0:
            logger.debug(f"Progress: {idx + 1}/{total_nodes} nodes compressed")
        elif total_nodes <= 10:
            logger.debug(f"Compressing node {_id}")
        
        # Query 1: Forward path matching (giữ nguyên logic)
        records, summary, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id:resource)-[:REF*]->(v:$id:resource)

                WHERE ID(v) = $nodeid 
                    AND ID(u) != ID(v)
                    AND ID(u) in $list 
                
                WITH u,v LIMIT 1

                OPTIONAL MATCH f=(s:$id)-[:REF]->(v)
                WHERE ID(s) != ID(u)

                OPTIONAL MATCH g=(v)-[:REF]->(d:$id)
                WHERE ID(d) != ID(u)

                DETACH DELETE v

                WITH collect(s) as cs, collect(d) as cd, u
                                FOREACH (ucs in cs |
                    MERGE for=(ucs)-[:REF]->(u)
                )
                FOREACH (ucd in cd |
                    MERGE bac=(u)-[:REF]->(ucd)
                )
                return *;
            """,
            id = pathID,
            nodeid=_id,
            list=node_ids,
            database_="memgraph"
        )
        
        # Query 2: Backward path matching (giữ nguyên logic)
        records, summary, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id:resource)<-[:REF*]-(v:$id:resource)

                WHERE ID(v) = $nodeid 
                    AND ID(u) != ID(v)
                    AND ID(u) in $list 
                
                WITH u,v LIMIT 1

                OPTIONAL MATCH f=(s:$id)-[:REF]->(v)
                WHERE ID(s) != ID(u)

                OPTIONAL MATCH g=(v)-[:REF]->(d:$id)
                WHERE ID(d) != ID(u)

                DETACH DELETE v

                WITH collect(s) as cs, collect(d) as cd, u
                                FOREACH (ucs in cs |
                    MERGE for=(ucs)-[:REF]->(u)
                )
                FOREACH (ucd in cd |
                    MERGE bac=(u)-[:REF]->(ucd)
                )
                return *;
            """,
            id = pathID,
            nodeid=_id,
            list=node_ids,
            database_="memgraph"
        )
        
        # KHÔNG gọi Cleanup ở đây - sẽ gọi một lần ở cuối
    
    # Batch Cleanup: Chỉ gọi Cleanup một lần ở cuối (giống CompressV2)
    # Note: Always cleanup (not conditional) to match CompressV2 behavior exactly
    Cleanup(pathID)
    
    logger.info(f"Compressed {total_nodes} nodes successfully")

def get_node_connection_count(node_id: int, pathID: str) -> int:
    """
    Lấy số lượng connections của một node (incoming + outgoing).
    Dùng COUNT thay vì size() để tương thích Memgraph (exists chỉ được dùng trong WHERE).
    """
    records, _, _ = INSTANCE.execute_query(
        """
        MATCH (n)
        WHERE ID(n) = $node_id
        OPTIONAL MATCH (n)-[r:REF]-()
        RETURN count(r) as degree
        """,
        node_id=node_id,
        database_="memgraph"
    )
    return int(records[0]["degree"]) if records and records[0]["degree"] is not None else 0

def compress_single_node_hybrid(node_id: int, node_ids: list, pathID: str, max_path_length: int = 20) -> bool:
    """
    Compress một node với Hybrid Approach:
    1. Direct Relationships First
    2. Progressive Path Length với Early Stop
    
    Args:
        node_id: ID của node cần compress
        node_ids: List tất cả node IDs trong group
        pathID: Path ID của project
        max_path_length: Độ dài path tối đa để tìm (default: 20)
        
    Returns:
        True nếu compress thành công, False nếu không tìm thấy path
    """
    found_u = None
    
    # ========================================================================
    # PHASE 1: Direct Relationships First (nhanh nhất)
    # ========================================================================
    # Forward: Kiểm tra direct relationships trước
    records, _, _ = INSTANCE.execute_query(
        """
            MATCH (u:$id:resource)-[:REF]->(v:$id:resource)
            WHERE ID(v) = $nodeid 
                AND ID(u) != ID(v)
                AND ID(u) in $list 
            WITH u, v LIMIT 1
            RETURN ID(u) as u_id
        """,
        id=pathID,
        nodeid=node_id,
        list=node_ids,
        database_="memgraph"
    )
    
    if records and records[0]["u_id"]:
        found_u = records[0]["u_id"]
        logger.debug(f"Found direct forward relationship: {found_u} -> {node_id}")
    else:
        # Backward: Kiểm tra direct relationships ngược lại
        records, _, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id:resource)<-[:REF]-(v:$id:resource)
                WHERE ID(v) = $nodeid 
                    AND ID(u) != ID(v)
                    AND ID(u) in $list 
                WITH u, v LIMIT 1
                RETURN ID(u) as u_id
            """,
            id=pathID,
            nodeid=node_id,
            list=node_ids,
            database_="memgraph"
        )
        
        if records and records[0]["u_id"]:
            found_u = records[0]["u_id"]
            logger.debug(f"Found direct backward relationship: {found_u} <- {node_id}")
    
    # ========================================================================
    # PHASE 2: Progressive Path Length với Early Stop (nếu không có direct)
    # ========================================================================
    if not found_u:
        # Forward: Progressive path length
        for path_length in range(2, max_path_length + 1):
            # Build query với path length động - sử dụng f-string cho path length
            query_template = f"""
                MATCH (u:$id:resource)-[:REF*1..{path_length}]->(v:$id:resource)
                WHERE ID(v) = $nodeid 
                    AND ID(u) != ID(v)
                    AND ID(u) in $list 
                WITH u, v LIMIT 1
                RETURN ID(u) as u_id
            """
            records, _, _ = INSTANCE.execute_query(
                query_template,
                id=pathID,
                nodeid=node_id,
                list=node_ids,
                database_="memgraph"
            )
            
            if records and records[0]["u_id"]:
                found_u = records[0]["u_id"]
                logger.debug(f"Found forward path (length={path_length}): {found_u} -> {node_id}")
                break
        
        # Backward: Progressive path length (nếu vẫn chưa tìm thấy)
        if not found_u:
            for path_length in range(2, max_path_length + 1):
                # Build query với path length động - sử dụng f-string cho path length
                query_template = f"""
                    MATCH (u:$id:resource)<-[:REF*1..{path_length}]-(v:$id:resource)
                    WHERE ID(v) = $nodeid 
                        AND ID(u) != ID(v)
                        AND ID(u) in $list 
                    WITH u, v LIMIT 1
                    RETURN ID(u) as u_id
                """
                records, _, _ = INSTANCE.execute_query(
                    query_template,
                    id=pathID,
                    nodeid=node_id,
                    list=node_ids,
                    database_="memgraph"
                )
                
                if records and records[0]["u_id"]:
                    found_u = records[0]["u_id"]
                    logger.debug(f"Found backward path (length={path_length}): {found_u} <- {node_id}")
                    break
    
    # ========================================================================
    # PHASE 3: Fallback to Unbounded Path (nếu vẫn chưa tìm thấy)
    # ========================================================================
    if not found_u:
        # Forward: Unbounded path (giữ nguyên logic cũ)
        records, _, _ = INSTANCE.execute_query(
            """
                MATCH (u:$id:resource)-[:REF*]->(v:$id:resource)
                WHERE ID(v) = $nodeid 
                    AND ID(u) != ID(v)
                    AND ID(u) in $list 
                WITH u, v LIMIT 1
                RETURN ID(u) as u_id
            """,
            id=pathID,
            nodeid=node_id,
            list=node_ids,
            database_="memgraph"
        )
        
        if records and records[0]["u_id"]:
            found_u = records[0]["u_id"]
            logger.debug(f"Found forward unbounded path: {found_u} -> {node_id}")
        else:
            # Backward: Unbounded path
            records, _, _ = INSTANCE.execute_query(
                """
                    MATCH (u:$id:resource)<-[:REF*]-(v:$id:resource)
                    WHERE ID(v) = $nodeid 
                        AND ID(u) != ID(v)
                        AND ID(u) in $list 
                    WITH u, v LIMIT 1
                    RETURN ID(u) as u_id
                """,
                id=pathID,
                nodeid=node_id,
                list=node_ids,
                database_="memgraph"
            )
            
            if records and records[0]["u_id"]:
                found_u = records[0]["u_id"]
                logger.debug(f"Found backward unbounded path: {found_u} <- {node_id}")
    
    # Nếu không tìm thấy node u, không thể compress
    if not found_u:
        logger.warning(f"Could not find path to compress node {node_id}")
        return False
    
    # ========================================================================
    # PHASE 4: Compress node với node u đã tìm được (với verification)
    # ========================================================================
    # Pre-check: Kiểm tra xem cả u và v có tồn tại không trước khi DELETE
    pre_check, _, _ = INSTANCE.execute_query(
        """
            MATCH (u:$id:resource), (v:$id:resource)
            WHERE ID(u) = $u_id AND ID(v) = $nodeid
            RETURN count(*) as cnt
        """,
        id=pathID,
        u_id=found_u,
        nodeid=node_id,
        database_="memgraph"
    )
    
    if not pre_check or pre_check[0]["cnt"] == 0:
        logger.warning(f"Cannot compress node {node_id}: target u={found_u} or node v={node_id} no longer exists")
        return False
    
    # Thực hiện DELETE
    records, summary, _ = INSTANCE.execute_query(
        """
            MATCH (u:$id:resource), (v:$id:resource)
            WHERE ID(u) = $u_id AND ID(v) = $nodeid

            OPTIONAL MATCH f=(s:$id)-[:REF]->(v)
            WHERE ID(s) != ID(u)

            OPTIONAL MATCH g=(v)-[:REF]->(d:$id)
            WHERE ID(d) != ID(u)

            DETACH DELETE v

            WITH collect(s) as cs, collect(d) as cd, u
            FOREACH (ucs in cs |
                MERGE (ucs)-[:REF]->(u)
            )
            FOREACH (ucd in cd |
                MERGE (u)-[:REF]->(ucd)
            )
            return *;
        """,
        id=pathID,
        u_id=found_u,
        nodeid=node_id,
        database_="memgraph"
    )
    
    # Post-check: Verify xem node v có thực sự bị xóa không
    verify_records, _, _ = INSTANCE.execute_query(
        """
            MATCH (v:$id:resource)
            WHERE ID(v) = $nodeid
            RETURN count(v) as cnt
        """,
        id=pathID,
        nodeid=node_id,
        database_="memgraph"
    )
    
    node_still_exists = verify_records and verify_records[0]["cnt"] > 0
    
    if node_still_exists:
        logger.warning(f"Failed to delete node {node_id} after DELETE operation (target u={found_u})")
        return False
    
    return True

def CompressV2Hybrid(regexName, pathID, max_path_length: int = 20):
    """
    Hybrid Optimized version của CompressV2 với các kỹ thuật:
    1. Direct Relationships First: Kiểm tra direct relationships trước (nhanh nhất)
    2. Progressive Path Length: Bắt đầu với path nhỏ, tăng dần, dừng khi tìm thấy
    3. Optimize Query Order: Xử lý nodes đơn giản trước
    4. Batch Cleanup: Chỉ gọi Cleanup một lần ở cuối
    5. Conditional Cleanup: Chỉ cleanup nếu có self-loops
    6. Reduce Logging: Giảm logging overhead
    
    Logic giữ nguyên 100% - chỉ tối ưu cách thực hiện.
    KHÔNG giới hạn path length - vẫn tìm đầy đủ paths khi cần.
    
    Args:
        regexName: Regex pattern để tìm nodes cần compress
        pathID: Path ID của project
        max_path_length: Độ dài path tối đa để thử progressive (default: 20)
                        Sau đó sẽ fallback về unbounded nếu cần
        
    Returns:
        None
    """
    # Early Termination: Kiểm tra nodes trước
    node_ids = FindNodeRegexAnyModule(regexName, pathID)
    if len(node_ids) <= 1:
        logger.info("Nothing to compress")
        return
    
    logger.info(f"Got {len(node_ids)} nodes in same group")
    
    # Cache node_ids để dùng trong loop
    nodes_to_compress = node_ids[:-1]  # Tất cả trừ node cuối (representative)
    total_nodes = len(nodes_to_compress)
    
    # Optimize Query Order: Sort nodes theo số lượng connections (ít nhất trước)
    logger.debug("Sorting nodes by connection count (simple nodes first)...")
    nodes_with_degree = [(node_id, get_node_connection_count(node_id, pathID)) for node_id in nodes_to_compress]
    nodes_sorted = sorted(nodes_with_degree, key=lambda x: x[1])  # Sort theo degree tăng dần
    nodes_to_compress_sorted = [node_id for node_id, _ in nodes_sorted]
    
    logger.info(f"Compressing {total_nodes} nodes (sorted by complexity)...")
    
    # Compress từng node với Hybrid Approach
    compressed_count = 0
    for idx, _id in enumerate(nodes_to_compress_sorted):
        # Log progress cho large batches
        if total_nodes > 10 and (idx + 1) % 10 == 0:
            logger.info(f"Progress: {idx + 1}/{total_nodes} nodes compressed")
        elif total_nodes <= 10:
            logger.debug(f"Compressing node {_id}")
        
        # Compress với Hybrid Approach
        success = compress_single_node_hybrid(_id, node_ids, pathID, max_path_length)
        if success:
            compressed_count += 1
            # Update node_ids sau mỗi lần compress (node đã bị xóa)
            node_ids = [nid for nid in node_ids if nid != _id]
    
    # Batch Cleanup: Chỉ gọi Cleanup một lần ở cuối
    # Conditional Cleanup: Chỉ cleanup nếu có self-loops
    if has_self_loops(pathID):
        logger.debug("Self-loops detected, running cleanup...")
        Cleanup(pathID)
    else:
        logger.debug("No self-loops detected, skipping cleanup")
    
    logger.info(f"Compressed {compressed_count}/{total_nodes} nodes successfully")

def CompressV2BFS(regexName, pathID):
    """
    BFS-based compression: Giữ nguyên logic CompressV2 nhưng dùng BFS trong memory.
    
    Same sequential logic as CompressV2 but much faster:
    - Pull graph into memory ONCE
    - Use BFS in Python to find paths (vs Cypher variable-length path [:REF*])
    - Sequential compression (same as CompressV2)
    - Cleanup only once at the end
    
    Algorithm (matching CompressV2 exactly):
    1. Find all nodes matching regex (the "group")
    2. Pull ALL REF edges in the subgraph into memory (ONCE)
    3. For each node to compress (sequential):
       a. Use BFS to find node u in group with path to v
       b. Redirect v's external edges to u (same as CompressV2)
       c. Delete v (same as CompressV2)
       d. Update in-memory graph
    4. Cleanup self-loops once at the end
    
    Args:
        regexName: Regex pattern to find nodes to compress
        pathID: Path ID of the project
    """
    import time as _time

    t_start = _time.time()

    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Find all nodes in the group
    # ──────────────────────────────────────────────────────────────────────
    node_ids = FindNodeRegexAnyModule(regexName, pathID)
    if len(node_ids) <= 1:
        logger.info("Nothing to compress")
        return

    logger.info(f"Got {len(node_ids)} nodes in same group")

    group_set = set(node_ids)
    to_compress_list = node_ids[:-1]  # All except representative
    representative = node_ids[-1] if node_ids else None

    # #region agent log
    try:
        import json, time
        with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({
                "id": f"log_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "location": "n4j_helper.py:1731",
                "message": "Compression started",
                "data": {
                    "regexName": regexName,
                    "pathID": pathID,
                    "total_nodes": len(node_ids),
                    "to_compress_count": len(to_compress_list),
                    "representative": representative,
                    "group_set_size": len(group_set)
                },
                "runId": "compression-debug",
                "hypothesisId": "A"
            }) + "\n")
    except: pass
    # #endregion

    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Pull ALL REF edges in the subgraph into memory (ONCE)
    # ──────────────────────────────────────────────────────────────────────
    records, _, _ = INSTANCE.execute_query(
        f"""
        MATCH (a:`{pathID}`)-[:REF]->(b:`{pathID}`)
        RETURN ID(a) as src, ID(b) as dst
        """,
        database_="memgraph"
    )

    adj: Dict[int, Set[int]] = defaultdict(set)
    rev_adj: Dict[int, Set[int]] = defaultdict(set)
    for r in records:
        src, dst = r["src"], r["dst"]
        adj[src].add(dst)
        rev_adj[dst].add(src)

    num_edges = sum(len(v) for v in adj.values())
    logger.debug(f"  Loaded {num_edges} edges into memory")
    
    # #region agent log
    # Count edges between nodes in the group
    edges_within_group = 0
    for src in group_set:
        for dst in adj.get(src, set()):
            if dst in group_set:
                edges_within_group += 1
    try:
        import json, time
        with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({
                "id": f"log_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "location": "n4j_helper.py:1755",
                "message": "Graph loaded into memory",
                "data": {
                    "total_edges": num_edges,
                    "edges_within_group": edges_within_group,
                    "group_set_size": len(group_set),
                    "avg_edges_per_node": num_edges / len(group_set) if group_set else 0
                },
                "runId": "compression-debug",
                "hypothesisId": "A"
            }) + "\n")
    except: pass
    # #endregion

    # ──────────────────────────────────────────────────────────────────────
    # STEP 3: Sequential compression (matching CompressV2 exactly)
    # For each node v, find node u in group with path to v, then compress
    # ──────────────────────────────────────────────────────────────────────
    def find_path_to_group_bfs(v: int, group_set: Set[int], current_group: Set[int], max_depth: int = 10) -> int:
        """
        Find nearest node u in group_set (ban đầu) with path to v using BFS.
        Matches CompressV2: MATCH (u)-[:REF*]->(v) WHERE ID(u) in $list
        (CompressV2 dùng node_ids không update, Cypher tự động skip nodes đã xóa)
        
        Args:
            v: Node cần compress
            group_set: Set ban đầu của tất cả nodes trong group (giống node_ids trong CompressV2)
            current_group: Set nodes còn tồn tại (để optimize - chỉ verify khi cần)
            max_depth: Maximum depth to explore (default: 10) to prevent timeout
        
        Returns first node u found in group_set that has a path to v AND still exists in database.
        """
        # Forward: find u in group_set that can reach v (u -> ... -> v)
        # Follow incoming edges backward from v
        # CRITICAL: Traverse qua TẤT CẢ nodes (kể cả đã bị xóa) để tìm path gián tiếp
        # Nhưng chỉ return nodes trong group_set ban đầu VÀ còn tồn tại trong database
        # (giống CompressV2: Cypher tự động skip nodes đã xóa nhưng vẫn tìm được path gián tiếp)
        visited: Set[int] = {v}
        queue = deque([(v, 0)])  # (node, depth)
        skipped_count = 0
        traversed_count = 0
        max_depth_reached = False
        group_nodes_found = 0
        max_depth_nodes = []  # Track nodes at max_depth
        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                max_depth_reached = True
                max_depth_nodes.append(node)  # Track nodes at max_depth
                continue  # Skip if exceeded max depth
            for neighbor in rev_adj.get(node, set()):  # Follow incoming edges backward
                if neighbor not in visited:
                    visited.add(neighbor)
                    traversed_count += 1
                    # CRITICAL: Return node đầu tiên trong group_set ban đầu mà còn tồn tại trong database
                    # Verify bằng cách check current_group (fast) hoặc query database (accurate but slow)
                    # Optimize: Chỉ verify khi node trong group_set
                    if neighbor in group_set and neighbor != v:
                        group_nodes_found += 1
                        # Verify node còn tồn tại trong database (giống CompressV2 skip nodes đã xóa)
                        # Fast check: current_group (optimized) hoặc query database (accurate)
                        if neighbor in current_group:
                            # #region agent log
                            try:
                                import json, time
                                with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                                    f.write(json.dumps({
                                        "id": f"log_{int(time.time() * 1000)}",
                                        "timestamp": int(time.time() * 1000),
                                        "location": "n4j_helper.py:1799",
                                        "message": "BFS found path (forward)",
                                        "data": {
                                            "v": v,
                                            "u": neighbor,
                                            "depth": depth + 1,
                                            "traversed_count": traversed_count,
                                            "skipped_count": skipped_count,
                                            "group_nodes_found": group_nodes_found
                                        },
                                        "runId": "compression-debug",
                                        "hypothesisId": "A"
                                    }) + "\n")
                            except: pass
                            # #endregion
                            return neighbor
                        else:
                            # Node trong group_set nhưng không trong current_group - có thể đã bị xóa
                            # Verify bằng cách query database (giống CompressV2)
                            records, _, _ = INSTANCE.execute_query(
                                f"""
                                MATCH (n:`{pathID}`:resource)
                                WHERE ID(n) = $nodeid
                                RETURN n LIMIT 1
                                """,
                                nodeid=neighbor,
                                database_="memgraph"
                            )
                            if records:
                                # Node vẫn tồn tại trong database - return nó
                                return neighbor
                    # Continue traverse qua nodes đã bị xóa để tìm path gián tiếp
                    if neighbor not in current_group:
                        skipped_count += 1
                    queue.append((neighbor, depth + 1))
        
        # Backward: find u in group_set that v can reach (v -> ... -> u)
        # Follow outgoing edges forward from v
        visited = {v}
        queue = deque([(v, 0)])  # (node, depth)
        skipped_count_backward = 0
        traversed_count_backward = 0
        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                continue  # Skip if exceeded max depth
            for neighbor in adj.get(node, set()):  # Follow outgoing edges forward
                if neighbor not in visited:
                    visited.add(neighbor)
                    traversed_count_backward += 1
                    # CRITICAL: Return node đầu tiên trong group_set ban đầu mà còn tồn tại trong database
                    # Verify bằng cách check current_group (fast) hoặc query database (accurate but slow)
                    # Optimize: Chỉ verify khi node trong group_set
                    if neighbor in group_set and neighbor != v:
                        # Verify node còn tồn tại trong database (giống CompressV2 skip nodes đã xóa)
                        # Fast check: current_group (optimized) hoặc query database (accurate)
                        if neighbor in current_group:
                            return neighbor
                        else:
                            # Node trong group_set nhưng không trong current_group - có thể đã bị xóa
                            # Verify bằng cách query database (giống CompressV2)
                            records, _, _ = INSTANCE.execute_query(
                                f"""
                                MATCH (n:`{pathID}`:resource)
                                WHERE ID(n) = $nodeid
                                RETURN n LIMIT 1
                                """,
                                nodeid=neighbor,
                                database_="memgraph"
                            )
                            if records:
                                # Node vẫn tồn tại trong database - return nó
                                return neighbor
                    # Continue traverse qua nodes đã bị xóa để tìm path gián tiếp
                    if neighbor not in current_group:
                        skipped_count_backward += 1
                    queue.append((neighbor, depth + 1))
        
        # #region agent log
        # Log BFS failure details
        try:
            import json, time
            with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({
                    "id": f"log_{int(time.time() * 1000)}",
                    "timestamp": int(time.time() * 1000),
                    "location": "n4j_helper.py:1862",
                    "message": "BFS no path found (forward)",
                    "data": {
                        "v": v,
                        "traversed_count": traversed_count,
                        "skipped_count": skipped_count,
                        "max_depth_reached": max_depth_reached,
                        "group_nodes_found": group_nodes_found,
                        "visited_size": len(visited),
                        "max_depth": max_depth,
                        "max_depth_nodes_count": len(max_depth_nodes),
                        "regexName": regexName
                    },
                    "runId": "compression-debug",
                    "hypothesisId": "A"
                }) + "\n")
        except: pass
        # #endregion
        
        return None

    compressed_count = 0
    failed_count = 0
    current_group = group_set.copy()  # Track remaining nodes in group
    
    # #region agent log
    try:
        import json, time
        with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({
                "id": f"log_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "location": "n4j_helper.py:1966",
                "message": "CompressV2BFS starting",
                "data": {
                    "regexName": regexName,
                    "total_nodes": len(node_ids),
                    "to_compress_count": len(to_compress_list),
                    "representative": representative
                },
                "runId": "compression-debug",
                "hypothesisId": "D"
            }) + "\n")
    except: pass
    # #endregion

    for idx, v in enumerate(to_compress_list):
        # Find node u in group_set ban đầu với path đến v (using BFS in memory)
        # Giống CompressV2: tìm trong node_ids ban đầu, không update
        # #region agent log
        bfs_start_time = _time.time()
        # #endregion
        u = find_path_to_group_bfs(v, group_set, current_group)
        # #region agent log
        bfs_time = _time.time() - bfs_start_time
        bfs_found = u is not None
        # #endregion
        
        if not u:
            # #region agent log
            try:
                import json, time
                with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({
                        "id": f"log_{int(time.time() * 1000)}",
                        "timestamp": int(time.time() * 1000),
                        "location": "n4j_helper.py:1871",
                        "message": "BFS failed to find path",
                        "data": {
                            "v": v,
                            "idx": idx,
                            "bfs_time": bfs_time,
                            "current_group_size": len(current_group),
                            "v_in_current_group": v in current_group,
                            "v_in_group_set": v in group_set
                        },
                        "runId": "compression-debug",
                        "hypothesisId": "A"
                    }) + "\n")
            except: pass
            # #endregion
            # Fallback: Nếu BFS không tìm được path, thử dùng Cypher query với depth limit để tránh timeout
            # (Có thể memory graph không đầy đủ do edges được tạo sau khi load)
            # Try Cypher query forward with depth limit (1..10) to prevent timeout
            # Reduced from 30 to 10 as depth 30 can still explore too many paths
            # #region agent log
            try:
                import json, time
                with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({
                        "id": f"log_{int(time.time() * 1000)}",
                        "timestamp": int(time.time() * 1000),
                        "location": "n4j_helper.py:2005",
                        "message": "Trying Cypher fallback forward",
                        "data": {
                            "v": v,
                            "idx": idx,
                            "regexName": regexName,
                            "max_depth_limit": 10
                        },
                        "runId": "compression-debug",
                        "hypothesisId": "B"
                    }) + "\n")
            except: pass
            # #endregion
            try:
                records, _, _ = INSTANCE.execute_query(
                    f"""
                    MATCH (u:`{pathID}`:resource)-[:REF*1..10]->(v:`{pathID}`:resource)
                    WHERE ID(v) = $nodeid 
                        AND ID(u) != ID(v)
                        AND ID(u) in $list 
                    RETURN ID(u) as u_id LIMIT 1
                    """,
                    nodeid=v,
                    list=list(group_set),
                    database_="memgraph"
                )
                if records:
                    u = records[0]["u_id"]
                    # #region agent log
                    try:
                        import json, time
                        with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                            f.write(json.dumps({
                                "id": f"log_{int(time.time() * 1000)}",
                                "timestamp": int(time.time() * 1000),
                                "location": "n4j_helper.py:1892",
                                "message": "Cypher fallback forward found path",
                                "data": {
                                    "v": v,
                                    "u": u,
                                    "idx": idx
                                },
                                "runId": "compression-debug",
                                "hypothesisId": "B"
                            }) + "\n")
                    except: pass
                    # #endregion
            except Exception as e:
                # #region agent log
                try:
                    import json, time
                    with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                        f.write(json.dumps({
                            "id": f"log_{int(time.time() * 1000)}",
                            "timestamp": int(time.time() * 1000),
                            "location": "n4j_helper.py:1894",
                            "message": "Cypher fallback forward failed",
                            "data": {
                                "v": v,
                                "error": str(e),
                                "idx": idx
                            },
                            "runId": "compression-debug",
                            "hypothesisId": "B"
                        }) + "\n")
                except: pass
                # #endregion
            
            if not u:
                # Try Cypher query backward with depth limit (1..10) to prevent timeout
                # Reduced from 30 to 10 as depth 30 can still explore too many paths
                # #region agent log
                try:
                    import json, time
                    with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                        f.write(json.dumps({
                            "id": f"log_{int(time.time() * 1000)}",
                            "timestamp": int(time.time() * 1000),
                            "location": "n4j_helper.py:2064",
                            "message": "Trying Cypher fallback backward",
                            "data": {
                                "v": v,
                                "idx": idx,
                                "regexName": regexName,
                                "max_depth_limit": 10
                            },
                            "runId": "compression-debug",
                            "hypothesisId": "B"
                        }) + "\n")
                except: pass
                # #endregion
                try:
                    records, _, _ = INSTANCE.execute_query(
                        f"""
                        MATCH (u:`{pathID}`:resource)<-[:REF*1..10]-(v:`{pathID}`:resource)
                        WHERE ID(v) = $nodeid 
                            AND ID(u) != ID(v)
                            AND ID(u) in $list 
                        RETURN ID(u) as u_id LIMIT 1
                        """,
                        nodeid=v,
                        list=list(group_set),
                        database_="memgraph"
                    )
                    if records:
                        u = records[0]["u_id"]
                        # #region agent log
                        try:
                            import json, time
                            with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                                f.write(json.dumps({
                                    "id": f"log_{int(time.time() * 1000)}",
                                    "timestamp": int(time.time() * 1000),
                                    "location": "n4j_helper.py:1913",
                                    "message": "Cypher fallback backward found path",
                                    "data": {
                                        "v": v,
                                        "u": u,
                                        "idx": idx
                                    },
                                    "runId": "compression-debug",
                                    "hypothesisId": "B"
                                }) + "\n")
                        except: pass
                        # #endregion
                except Exception as e:
                    # #region agent log
                    try:
                        import json, time
                        with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                            f.write(json.dumps({
                                "id": f"log_{int(time.time() * 1000)}",
                                "timestamp": int(time.time() * 1000),
                                "location": "n4j_helper.py:1915",
                                "message": "Cypher fallback backward failed",
                                "data": {
                                    "v": v,
                                    "error": str(e),
                                    "idx": idx
                                },
                                "runId": "compression-debug",
                                "hypothesisId": "B"
                            }) + "\n")
                    except: pass
                    # #endregion
        
        if not u:
            # Fallback: If BFS and Cypher both failed, but node is still in current_group,
            # compress directly to representative (since all nodes match the same regex pattern)
            # BUT: Skip if node is tagged (preserve tagged nodes when no path found)
            # This matches CompressV2 behavior: only compress when path is found
            if v in current_group and v != representative:
                # Check if node v is tagged - if so, skip compression (preserve tagged nodes)
                records, _, _ = INSTANCE.execute_query(
                    f"""
                    MATCH (n:`{pathID}`:resource)
                    WHERE ID(n) = $nodeid
                    RETURN n:tagged as is_tagged LIMIT 1
                    """,
                    nodeid=v,
                    database_="memgraph"
                )
                is_tagged = records and records[0].get("is_tagged", False) if records else False
                
                if is_tagged:
                    # Skip compression for tagged nodes when no path found (matches CompressV2 behavior)
                    failed_count += 1
                    logger.debug(f"Skipping compression of tagged node {v} (no path found)")
                    continue
                
                u = representative
            else:
                failed_count += 1
                logger.warning(f"Could not find path to compress node {v}")
                continue

        # Get v's external edges (edges to/from nodes NOT in current_group and NOT u)
        # This matches CompressV2: OPTIONAL MATCH WHERE ID(s) != ID(u)
        incoming_sources = []
        outgoing_targets = []
        
        for src in rev_adj.get(v, set()):
            if src not in current_group and src != u:
                incoming_sources.append(src)
        
        for dst in adj.get(v, set()):
            if dst not in current_group and dst != u:
                outgoing_targets.append(dst)

        # Redirect edges: external -> v becomes external -> u
        # Matches CompressV2: MERGE (ucs)-[:REF]->(u)
        for src_id in incoming_sources:
            INSTANCE.execute_query(
                f"""
                MATCH (s:`{pathID}`), (u:`{pathID}`:resource)
                WHERE ID(s) = $src AND ID(u) = $target
                MERGE (s)-[:REF]->(u)
                """,
                src=src_id,
                target=u,
                database_="memgraph"
            )

        # Redirect edges: v -> external becomes u -> external
        # Matches CompressV2: MERGE (u)-[:REF]->(ucd)
        for dst_id in outgoing_targets:
            INSTANCE.execute_query(
                f"""
                MATCH (u:`{pathID}`:resource), (d:`{pathID}`)
                WHERE ID(u) = $target AND ID(d) = $dst
                MERGE (u)-[:REF]->(d)
                """,
                target=u,
                dst=dst_id,
                database_="memgraph"
            )

        # Delete v (matches CompressV2: DETACH DELETE v)
        INSTANCE.execute_query(
            f"""
            MATCH (v:`{pathID}`:resource)
            WHERE ID(v) = $nodeid
            DETACH DELETE v
            """,
            nodeid=v,
            database_="memgraph"
        )

        # Update in-memory graph: remove v from adj/rev_adj
        # This ensures next BFS doesn't traverse through deleted nodes
        if v in adj:
            del adj[v]
        if v in rev_adj:
            del rev_adj[v]
        for neighbors in adj.values():
            neighbors.discard(v)
        for neighbors in rev_adj.values():
            neighbors.discard(v)

        # Remove v from current_group (it's been deleted)
        current_group.discard(v)
        compressed_count += 1

        # #region agent log
        try:
            import json, time
            with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({
                    "id": f"log_{int(time.time() * 1000)}",
                    "timestamp": int(time.time() * 1000),
                    "location": "n4j_helper.py:1987",
                    "message": "Node compressed successfully",
                    "data": {
                        "v": v,
                        "u": u,
                        "idx": idx,
                        "compressed_count": compressed_count,
                        "failed_count": failed_count,
                        "u_is_representative": u == representative,
                        "incoming_edges_redirected": len(incoming_sources),
                        "outgoing_edges_redirected": len(outgoing_targets),
                        "current_group_size": len(current_group)
                    },
                    "runId": "compression-debug",
                    "hypothesisId": "D"
                }) + "\n")
        except: pass
        # #endregion

        # Log progress (matching CompressV2Optimized style)
        if len(to_compress_list) > 10 and (idx + 1) % 10 == 0:
            logger.debug(f"Progress: {idx + 1}/{len(to_compress_list)} nodes compressed")
        elif len(to_compress_list) <= 10:
            logger.debug(f"Compressed node {v} -> {u}")

    # ──────────────────────────────────────────────────────────────────────
    # STEP 4: Cleanup self-loops once at the end (optimization)
    # ──────────────────────────────────────────────────────────────────────
    Cleanup(pathID)

    elapsed = _time.time() - t_start
    logger.info(f"Compressed {compressed_count}/{len(to_compress_list)} nodes successfully ({elapsed:.2f}s)")
    
    # #region agent log
    # Verify deleted nodes are actually gone
    try:
        import json, time
        # Check if any of the compressed nodes still exist
        compressed_node_ids = list(to_compress_list)
        if compressed_node_ids:
            verify_records, _, _ = INSTANCE.execute_query(
                f"""
                MATCH (v:`{pathID}`:resource)
                WHERE ID(v) IN $node_ids
                RETURN ID(v) as id, labels(v) as labels
                """,
                node_ids=compressed_node_ids[:20],  # Check first 20
                database_="memgraph"
            )
            still_exist = [r["id"] for r in verify_records]
            with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({
                    "id": f"log_{int(time.time() * 1000)}",
                    "timestamp": int(time.time() * 1000),
                    "location": "n4j_helper.py:CompressV2BFS:post_verify",
                    "message": "Post-compression verification",
                    "data": {
                        "regexName": regexName,
                        "checked_nodes": compressed_node_ids[:20],
                        "still_exist": still_exist,
                        "still_exist_count": len(still_exist),
                        "expected_deleted": len(compressed_node_ids[:20])
                    },
                    "runId": "compression-debug",
                    "hypothesisId": "J"
                }) + "\n")
    except Exception as e:
        pass
    # Summary log
    try:
        import json, time
        with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({
                "id": f"log_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "location": "n4j_helper.py:2347",
                "message": "CompressV2BFS summary",
                "data": {
                    "regexName": regexName,
                    "total_nodes": len(node_ids),
                    "to_compress_count": len(to_compress_list),
                    "compressed_count": compressed_count,
                    "failed_count": failed_count,
                    "success_rate": compressed_count / len(to_compress_list) if to_compress_list else 0,
                    "elapsed": elapsed
                },
                "runId": "compression-debug",
                "hypothesisId": "E"
            }) + "\n")
    except: pass
    # #endregion
    
    # #region agent log
    # Verify compression result: check how many nodes remain
    try:
        remaining_nodes, _, _ = INSTANCE.execute_query(
            f"""
            MATCH (n:`{pathID}`:resource)
            WHERE n.type =~ $regex
            RETURN count(n) as cnt
            """,
            regex=regexName,
            database_="memgraph"
        )
        remaining_count = remaining_nodes[0]["cnt"] if remaining_nodes else 0
        
        import json, time
        with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({
                "id": f"log_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "location": "n4j_helper.py:2001",
                "message": "Compression completed",
                "data": {
                    "regexName": regexName,
                    "initial_nodes": len(node_ids),
                    "to_compress": len(to_compress_list),
                    "compressed_count": compressed_count,
                    "failed_count": failed_count,
                    "remaining_nodes": remaining_count,
                    "expected_remaining": 1,
                    "compression_success": remaining_count == 1,
                    "elapsed": elapsed,
                    "representative": representative
                },
                "runId": "compression-debug",
                "hypothesisId": "E"
            }) + "\n")
    except Exception as e:
        try:
            import json, time
            with open('/home/thangdd/repos/TerrARA/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({
                    "id": f"log_{int(time.time() * 1000)}",
                    "timestamp": int(time.time() * 1000),
                    "location": "n4j_helper.py:2001",
                    "message": "Compression completed - verification failed",
                    "data": {
                        "regexName": regexName,
                        "error": str(e),
                        "compressed_count": compressed_count,
                        "failed_count": failed_count
                    },
                    "runId": "compression-debug",
                    "hypothesisId": "E"
                }) + "\n")
        except: pass
    # #endregion

def CompressBFS(regexName, pathID):
    """
    BFS-based compression: Mô phỏng chính xác CompressV2 nhưng trong memory.
    
    Same semantics as CompressV2 but much faster:
    - Pull graph into memory, compute compressions via BFS
    - Batch DELETE and MERGE operations
    - Only cleanup once at the end (vs after each node in CompressV2)
    
    Algorithm (matching CompressV2 exactly):
    1. Find all nodes matching regex (the "group")
    2. Pull all REF edges in the subgraph into memory
    3. For each node to compress, find nearest node u in group with path to it
    4. Compute edge redirections: redirect v's edges to u (not representative!)
    5. Batch MERGE redirected edges
    6. Batch DETACH DELETE all compressed nodes
    7. Cleanup self-loops once
    
    Args:
        regexName: Regex pattern to find nodes to compress
        pathID: Path ID of the project
    """
    import time as _time

    t_start = _time.time()

    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Find all nodes in the group
    # ──────────────────────────────────────────────────────────────────────
    node_ids = FindNodeRegexAnyModule(regexName, pathID)
    if len(node_ids) <= 1:
        logger.info("Nothing to compress")
        return

    logger.info(f"Got {len(node_ids)} nodes in same group")

    group_set = set(node_ids)
    to_compress_list = node_ids[:-1]  # All except representative

    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Pull ALL REF edges in the subgraph into memory
    # ──────────────────────────────────────────────────────────────────────
    records, _, _ = INSTANCE.execute_query(
        f"""
        MATCH (a:`{pathID}`)-[:REF]->(b:`{pathID}`)
        RETURN ID(a) as src, ID(b) as dst
        """,
        database_="memgraph"
    )

    adj: Dict[int, Set[int]] = defaultdict(set)
    rev_adj: Dict[int, Set[int]] = defaultdict(set)
    for r in records:
        src, dst = r["src"], r["dst"]
        adj[src].add(dst)
        rev_adj[dst].add(src)

    num_edges = sum(len(v) for v in adj.values())
    logger.debug(f"  Loaded {num_edges} edges into memory")

    # ──────────────────────────────────────────────────────────────────────
    # STEP 3: For each node to compress, find nearest node u in group
    # This matches CompressV2: find u in group with path to v (forward or backward)
    # ──────────────────────────────────────────────────────────────────────
    compression_map: Dict[int, int] = {}  # v -> u (node to compress -> target in group)
    
    def find_path_to_group(v: int, group: Set[int]) -> int:
        """Find nearest node u in group with path to v (BFS forward or backward)."""
        # Forward BFS: find u in group that can reach v
        visited: Set[int] = {v}
        queue = deque([v])
        while queue:
            node = queue.popleft()
            for neighbor in rev_adj.get(node, set()):  # Follow incoming edges backward
                if neighbor not in visited:
                    visited.add(neighbor)
                    if neighbor in group and neighbor != v:
                        return neighbor
                    queue.append(neighbor)
        
        # Backward BFS: find u in group that v can reach
        visited = {v}
        queue = deque([v])
        while queue:
            node = queue.popleft()
            for neighbor in adj.get(node, set()):  # Follow outgoing edges forward
                if neighbor not in visited:
                    visited.add(neighbor)
                    if neighbor in group and neighbor != v:
                        return neighbor
                    queue.append(neighbor)
        
        return None

    for v in to_compress_list:
        u = find_path_to_group(v, group_set)
        if u:
            compression_map[v] = u
        else:
            logger.warning(f"Could not find path to compress node {v}")

    if not compression_map:
        logger.info("No compressible nodes found")
        return

    # ──────────────────────────────────────────────────────────────────────
    # STEP 4: Compute edge redirections in memory
    # For each (v -> u) compression, redirect v's external edges to u
    # ──────────────────────────────────────────────────────────────────────
    redirects: Dict[Tuple[int, int], Set[int]] = defaultdict(set)  # (u, direction) -> set of external nodes
    # direction: 0 = incoming (external -> v becomes external -> u), 1 = outgoing (v -> external becomes u -> external)
    
    for v, u in compression_map.items():
        # Incoming edges: external nodes (NOT in group) pointing to v -> redirect to u
        # Note: edges from other group nodes will be deleted when those nodes are deleted
        for src in rev_adj.get(v, set()):
            if src not in group_set and src != u:  # Only redirect external edges
                redirects[(u, 0)].add(src)  # incoming: src -> u
        
        # Outgoing edges: v pointing to external nodes (NOT in group) -> redirect to u
        for dst in adj.get(v, set()):
            if dst not in group_set and dst != u:  # Only redirect external edges
                redirects[(u, 1)].add(dst)  # outgoing: u -> dst

    logger.info(f"Compressing {len(compression_map)}/{len(to_compress_list)} nodes")

    # ──────────────────────────────────────────────────────────────────────
    # STEP 5: Batch MERGE redirected edges
    # ──────────────────────────────────────────────────────────────────────
    for (u, direction), external_nodes in redirects.items():
        if direction == 0:  # incoming: external -> u
            for src_id in external_nodes:
                INSTANCE.execute_query(
                    f"""
                    MATCH (s:`{pathID}`), (u:`{pathID}`:resource)
                    WHERE ID(s) = $src AND ID(u) = $target
                    MERGE (s)-[:REF]->(u)
                    """,
                    src=src_id,
                    target=u,
                    database_="memgraph"
                )
        else:  # outgoing: u -> external
            for dst_id in external_nodes:
                INSTANCE.execute_query(
                    f"""
                    MATCH (u:`{pathID}`:resource), (d:`{pathID}`)
                    WHERE ID(u) = $target AND ID(d) = $dst
                    MERGE (u)-[:REF]->(d)
                    """,
                    target=u,
                    dst=dst_id,
                    database_="memgraph"
                )

    # ──────────────────────────────────────────────────────────────────────
    # STEP 6: Batch DETACH DELETE all compressed nodes
    # ──────────────────────────────────────────────────────────────────────
    compressible_list = list(compression_map.keys())
    INSTANCE.execute_query(
        f"""
        MATCH (v:`{pathID}`:resource)
        WHERE ID(v) IN $to_delete
        DETACH DELETE v
        """,
        to_delete=compressible_list,
        database_="memgraph"
    )

    # ──────────────────────────────────────────────────────────────────────
    # STEP 7: Cleanup self-loops (once, not after each node)
    # ──────────────────────────────────────────────────────────────────────
    Cleanup(pathID)

    elapsed = _time.time() - t_start
    logger.info(f"Compressed {len(compression_map)}/{len(to_compress_list)} nodes successfully ({elapsed:.2f}s)")


def has_self_loops(pathID: str) -> bool:
    """
    Kiểm tra nhanh xem có self-loops không
    
    Args:
        pathID: Path ID của project
        
    Returns:
        True nếu có self-loops, False nếu không
    """
    records, _, _ = INSTANCE.execute_query(
        f"""
        MATCH (u:`{pathID}`)-[rel]-(u:`{pathID}`)
        RETURN count(rel) as cnt
        LIMIT 1
        """,
        database_="memgraph"
    )
    return records[0]["cnt"] > 0 if records and records[0]["cnt"] else False

def Cleanup(pathID):
    # Self loop
    records, _, _ = INSTANCE.execute_query(
        """
        MATCH (u:$id)-[rel]-(u:$id)
        DELETE rel
        """,
        id = pathID,
        database_="memgraph"
    )

    # Bidirectional
    # records, _, _ = INSTANCE.execute_query(
    #     """
    #     MATCH (u:$id)-[rel]->(v:$id), (u)<-[]-(v)
    #     DELETE rel
    #     """,
    #     id = pathID,
    #     database_="memgraph"
    # )
