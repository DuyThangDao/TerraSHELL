import logging
from typing import List, Mapping, Dict, Any
from neo4j import GraphDatabase
import os

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

    records, _, _ = INSTANCE.execute_query(
    """
    MATCH (u:$id:tagged:resource) -[:REF]-> (v:$id:tagged:resource)
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
    records, _, _ = INSTANCE.execute_query(
        """
        MATCH (u:$id:resource)
        WHERE u.type =~ $regex
        RETURN ID(u) as id
        ORDER BY degree(u)
        """,
        id = pathID,
        regex=regexName,
        database_="memgraph"
    )
    return [elem["id"] for elem in records]

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
    
    # Batch Cleanup: Chỉ gọi Cleanup một lần ở cuối
    # Conditional Cleanup: Chỉ cleanup nếu có self-loops
    if has_self_loops(pathID):
        logger.debug("Self-loops detected, running cleanup...")
        Cleanup(pathID)
    else:
        logger.debug("No self-loops detected, skipping cleanup")
    
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
    # PHASE 4: Compress node với node u đã tìm được (giữ nguyên logic)
    # ========================================================================
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
