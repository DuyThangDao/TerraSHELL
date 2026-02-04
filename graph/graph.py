from os import environ
from utils.n4j_helper import AddConnection, CreateNodeWithProperties, GetPathID
import json

def LoadFromFolder(filePath: str, init=True):
    """Load Terraform project to Directed Graph

    Args:
        filePath (str): Path to terraform project
        init (bool, optional): Should project be re-initiated. Defaults to True.

    Returns:
        Graph: _description_
    """        
    from tfparser import GetJSON
    jsonPath = GetJSON(filePath, init, environ.get("TOFU", "") != "") # Automatically detect based on commandline

    # TODO: Make this working other OS
    encoded_path = GetPathID(filePath)
    
    data = json.load(open(jsonPath, "r"))
    nodeInvMap:dict[str, object] = {} 
    
    # Add all node info
    for node in data["nodes"]:
        source = node["data"]
        raw_label = source.get("label", "")
        label_parts = raw_label.split(".")
        
        resource_type = label_parts[0] if len(label_parts) > 0 else "unknown"
        resource_name = ".".join(label_parts[1:]) if len(label_parts) > 1 else ""
        
        # Prepare properties dictionary (similar to phase1_load_graph.py)
        node_props = {
            "parent_id": source.get("parent", "") if "parent" in source else "",
            "resource_type": resource_type,
            "resource_name": resource_name,
            "type": resource_type,  # Set type = resource_type for compatibility with TaggingNode
            "label": raw_label,  # Keep original label for debugging
            "name": raw_label     # Important: Set 'name' to label for matching in Enrich phase
        }
        
        # Add any additional attributes from source if they exist
        if "attributes" in source and isinstance(source["attributes"], dict):
            for k, v in source["attributes"].items():
                if isinstance(v, (dict, list)):
                    node_props[k] = json.dumps(v)
                else:
                    node_props[k] = v
        
        # Determine labels
        node_type = source.get("type", "unknown")
        labels = [encoded_path, node_type]
        
        # Use CreateNodeWithProperties to store all properties
        _id = CreateNodeWithProperties(
            labels,
            node_props,
            encoded_path
        )

        nodeInvMap[node["data"]["id"]] = _id

    
    """
    Sample Edge format
    ---------------------------------------------------------
    {
        "data": {
            "id": "module.root.module.network.aws_subnet.km_private_subnet-module.root.module.network.aws_vpc.km_vpc",
            "source": "module.root.module.network.aws_subnet.km_private_subnet",
            "target": "module.root.module.network.aws_vpc.km_vpc",
            "sourceType": "resource",
            "targetType": "resource"
        },
        "classes": [
            "resource-resource"
        ]
    }
    """
    # Generate connection
    if data["edges"] is None:
        data["edges"] = []
    for edge in data["edges"]:
        source = nodeInvMap[edge["data"]["source"]]
        target = nodeInvMap[edge["data"]["target"]]

        AddConnection(
            source,
            target,
            encoded_path
        )
            
    return encoded_path
