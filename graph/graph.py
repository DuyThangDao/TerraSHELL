from os import environ
from utils.n4j_helper import AddConnection, CreateNode, GetPathID
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


    """
    Sample Node format
    ---------------------------------------------------------
    {
        "data": {
            "id": "module.root.module.network.aws_vpc.km_vpc",
            "parent": "module.root.module.network",
            "label": "aws_vpc.km_vpc",
            "type": "resource"
        },
        "classes": [
            "resource"
        ]
    }
    """

    # TODO: Make this working other OS
    encoded_path = GetPathID(filePath)


    
    data = json.load(open(jsonPath, "r"))
    nodeInvMap:dict[str, object] = {} 
    # Add all node info
    for node in data["nodes"]:
        source = node["data"]
        _id = CreateNode(
            [encoded_path, source["type"]], 
            {
                "parent_id": source["parent"] if "parent" in source else "",
                "resource_type": source["label"].split(".")[0],
                "resource_name": ".".join(source["label"].split(".")[1:])
            }
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
