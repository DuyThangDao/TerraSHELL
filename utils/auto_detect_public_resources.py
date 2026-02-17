"""
Auto-detect Public Resources Module

Automatically detects and marks resources (EC2, RDS) with public access 
through Security Groups with ingress rules allowing 0.0.0.0/0.

Problem:
- EC2/RDS always go through Security Groups in real AWS
- SPARTA patterns require direct flow User → EC2/RDS to detect threats
- But EC2/RDS don't have can_public: true in annotation

Solution:
- Automatically detect Security Groups with ingress rules with cidr_blocks = ["0.0.0.0/0"]
- Find EC2/RDS connected to that Security Group
- Automatically mark them as publicNode to create direct flow User → EC2/RDS
"""

import logging
import os
from typing import List, Set, Dict, Any
from tfparser.parse_tf_properties import parse_terraform_project, get_resource_properties
from utils.n4j_helper import INSTANCE, GetPathID

logger = logging.getLogger(__name__)


def has_public_ingress(ingress_rules: List[Dict[str, Any]]) -> bool:
    """
    Check if Security Group has ingress rule allowing 0.0.0.0/0.
    
    Args:
        ingress_rules: List of ingress rule dictionaries
        
    Returns:
        True if at least one rule allows 0.0.0.0/0
    """
    if not ingress_rules:
        return False
    
    for rule in ingress_rules:
        # Handle both list and single value
        cidr_blocks = rule.get('cidr_blocks', [])
        if isinstance(cidr_blocks, str):
            cidr_blocks = [cidr_blocks]
        
        # Check for 0.0.0.0/0
        if cidr_blocks and "0.0.0.0/0" in cidr_blocks:
            return True
        
        # Also check ipv6_cidr_blocks
        ipv6_cidr_blocks = rule.get('ipv6_cidr_blocks', [])
        if isinstance(ipv6_cidr_blocks, str):
            ipv6_cidr_blocks = [ipv6_cidr_blocks]
        
        if ipv6_cidr_blocks and "::/0" in ipv6_cidr_blocks:
            return True
    
    return False


def find_resources_connected_to_sg(pathID: str, sg_node_id: str, resource_types: List[str]) -> List[Dict[str, Any]]:
    """
    Find resources (EC2, RDS) connected to Security Group.
    
    Args:
        pathID: Path ID of the project
        sg_node_id: Node ID of Security Group in the graph
        resource_types: List of resource types to find (e.g., ["aws_instance", "aws_db_instance"])
        
    Returns:
        List of resource records with id, group, general_name, tfname
    """
    results = []
    
    for resource_type in resource_types:
        # Query to find resources connected to Security Group
        # EC2/RDS have vpc_security_group_ids reference to Security Group
        try:
            # Query to find resources connected to Security Group
            # Check res.type, res.resource_type, and res.name (phase 1.5 may change how types are stored)
            # res.name format: "aws_instance.goat_instance" -> check if starts with resource_type
            resource_type_prefix = f"{resource_type}."
            
            records, _, _ = INSTANCE.execute_query(
                """
                MATCH (sg:$id:tagged:resource) <-[:REF]- (res:$id:tagged:resource)
                WHERE ID(sg) = $sg_id
                  AND ((res.type = $resource_type) 
                    OR (res.resource_type = $resource_type)
                    OR (res.name STARTS WITH $resource_type_prefix))
                  AND ((res:processes) OR (res:data_stores))
                RETURN ID(res) as id, res.group as group, res.general_name as general_name, res.name as tfname
                """,
                id=pathID,
                parameters_={"sg_id": int(sg_node_id), "resource_type": resource_type, "resource_type_prefix": resource_type_prefix},
                database_="memgraph"
            )
            results.extend(records)
        except Exception as e:
            logger.warning(f"Error querying resources for {resource_type}: {e}")
            continue
    
    return results


def find_public_security_groups(project_path: str, pathID: str) -> List[Dict[str, Any]]:
    """
    Find all Security Groups with public ingress rules.
    
    Args:
        project_path: Path to Terraform project
        pathID: Path ID of the project
        
    Returns:
        List of Security Group records with id, name, and node info
    """
    # Parse Terraform project to get Security Group properties
    parsed = parse_terraform_project(project_path)
    
    public_sgs = []
    
    # Query all Security Groups from graph (using QueryTagged similar approach)
    try:
        records, _, _ = INSTANCE.execute_query(
            """
            MATCH (sg:$id:tagged:resource:processes)
            WHERE sg.type = 'aws_security_group'
            RETURN ID(sg) as id, sg.name as name, sg.group as group, sg.general_name as general_name, sg.resource_type as resource_type, sg.resource_name as resource_name
            """,
            id=pathID,
            database_="memgraph"
        )
        
        for record in records:
            sg_id = str(record["id"])
            sg_name = record.get("name", "")
            sg_resource_type = record.get("resource_type", "")
            sg_resource_name = record.get("resource_name", "")
            
            # Parse Security Group name to find resource in Terraform
            # Format: "aws_security_group.allow_ssh" -> type="aws_security_group", name="allow_ssh"
            if "." in sg_name:
                parts = sg_name.split(".", 1)
                resource_type = parts[0]
                resource_name = parts[1] if len(parts) > 1 else ""
            elif sg_resource_type and sg_resource_name:
                # Use resource_type and resource_name from node properties (more reliable after phase 1.5)
                resource_type = sg_resource_type
                resource_name = sg_resource_name
            else:
                # Try to find by name pattern
                resource_type = "aws_security_group"
                resource_name = sg_name
            
            # Get properties from parsed Terraform
            resource_id = f"{resource_type}.{resource_name}"
            if resource_id in parsed.get('resources', {}):
                properties = parsed['resources'][resource_id]['properties']
                ingress_rules = properties.get('ingress', [])
                
                # Check if has public ingress
                if has_public_ingress(ingress_rules):
                    logger.info(f"Found public Security Group: {resource_id}")
                    public_sgs.append({
                        'id': sg_id,
                        'name': sg_name,
                        'resource_id': resource_id,
                        'group': record.get('group'),
                        'general_name': record.get('general_name')
                    })
            else:
                # If not found in parsed resources, log warning
                logger.debug(f"Security Group {resource_id} not found in parsed resources")
    
    except Exception as e:
        logger.error(f"Error querying Security Groups: {e}")
    
    return public_sgs


def auto_detect_public_resources(project_path: str, pathID: str) -> Set[str]:
    """
    Automatically detect and return list of resource IDs that need to be marked as public.
    
    Args:
        project_path: Path to Terraform project
        pathID: Path ID of the project
        
    Returns:
        Set of resource node IDs (as strings) that need to be marked as public
    """
    public_resource_ids = set()
    
    # Find all Security Groups with public ingress
    public_sgs = find_public_security_groups(project_path, pathID)
    
    if not public_sgs:
        logger.info("No public Security Groups found")
        return public_resource_ids
    
    logger.info(f"Found {len(public_sgs)} public Security Group(s)")
    
    # For each public Security Group, find connected EC2 and RDS
    resource_types_to_check = ["aws_instance", "aws_db_instance", "aws_rds_cluster"]
    
    for sg in public_sgs:
        sg_id = sg['id']
        sg_name = sg['name']
        
        logger.info(f"Checking resources connected to Security Group: {sg_name} (ID: {sg_id})")
        
        # Find resources connected to this Security Group
        connected_resources = find_resources_connected_to_sg(
            pathID, sg_id, resource_types_to_check
        )
        
        for resource in connected_resources:
            resource_id = str(resource['id'])
            resource_name = resource.get('tfname', '')
            resource_group = resource.get('group', '')
            
            logger.info(f"  → Found public resource: {resource_name} ({resource_group}) - ID: {resource_id}")
            public_resource_ids.add(resource_id)
    
    logger.info(f"Auto-detected {len(public_resource_ids)} public resource(s)")
    return public_resource_ids
