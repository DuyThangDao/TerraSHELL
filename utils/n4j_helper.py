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
