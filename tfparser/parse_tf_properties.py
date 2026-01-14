#!/usr/bin/env python3
"""
Parse Terraform files to extract:
1. Variables with default values
2. Locals with their values
3. Resource properties (all attributes)
"""
import os
import json
import logging
from glob import glob
from typing import Dict, List, Any, Optional
try:
    import hcl2.api as hcl2
except ImportError:
    logging.error("python-hcl2 not installed. Run: pip install python-hcl2")
    raise

logger = logging.getLogger(__name__)


def parse_terraform_project(project_path: str) -> Dict[str, Any]:
    """
    Parse all Terraform files in a project to extract Variables, Locals, and Resources.
    
    Args:
        project_path: Path to Terraform project directory
        
    Returns:
        Dictionary with keys: 'variables', 'locals', 'resources'
    """
    project_path = os.path.abspath(project_path)
    result = {
        'variables': {},
        'locals': {},
        'resources': {}
    }
    
    # Find all .tf files
    tf_files = glob(os.path.join(project_path, "*.tf"))
    
    if not tf_files:
        logger.warning(f"No .tf files found in {project_path}")
        return result
    
    # Parse each .tf file
    for tf_file in tf_files:
        try:
            with open(tf_file, 'r', encoding='utf-8') as f:
                data = hcl2.load(f)
                
            # Extract variables
            if 'variable' in data:
                for var_block in data['variable']:
                    for var_name, var_config in var_block.items():
                        var_value = {
                            'name': var_name,
                            'default': var_config.get('default'),
                            'type': str(var_config.get('type', 'string')),
                            'description': var_config.get('description', ''),
                            'file': os.path.basename(tf_file)
                        }
                        result['variables'][var_name] = var_value
                        logger.debug(f"Found variable: {var_name} = {var_value['default']}")
            
            # Extract locals
            if 'locals' in data:
                for local_block in data['locals']:
                    for local_name, local_value in local_block.items():
                        # Handle different value types
                        resolved_value = _resolve_value(local_value)
                        result['locals'][local_name] = {
                            'name': local_name,
                            'value': resolved_value,
                            'raw_value': local_value,
                            'file': os.path.basename(tf_file)
                        }
                        logger.debug(f"Found local: {local_name} = {resolved_value}")
            
            # Extract resources with all properties
            if 'resource' in data:
                for resource_block in data['resource']:
                    for resource_type, resource_instances in resource_block.items():
                        for instance_name, instance_config in resource_instances.items():
                            resource_id = f"{resource_type}.{instance_name}"
                            # Store all properties
                            properties = {}
                            for key, value in instance_config.items():
                                properties[key] = _resolve_value(value)
                            
                            result['resources'][resource_id] = {
                                'type': resource_type,
                                'name': instance_name,
                                'properties': properties,
                                'file': os.path.basename(tf_file)
                            }
                            logger.debug(f"Found resource: {resource_id} with {len(properties)} properties")
                            
        except Exception as e:
            logger.error(f"Error parsing {tf_file}: {e}")
            continue
    
    logger.info(f"Parsed {len(result['variables'])} variables, {len(result['locals'])} locals, {len(result['resources'])} resources")
    return result


def _resolve_value(value: Any) -> Any:
    """
    Resolve Terraform value expressions to their literal values where possible.
    Handles simple cases like string literals, numbers, booleans.
    For complex expressions (interpolations, functions), returns the raw string.
    """
    if isinstance(value, (str, int, float, bool)):
        return value
    elif isinstance(value, list):
        return [_resolve_value(item) for item in value]
    elif isinstance(value, dict):
        return {k: _resolve_value(v) for k, v in value.items()}
    else:
        # For complex expressions, return string representation
        return str(value)


def get_resource_properties(project_path: str, resource_type: str, resource_name: str) -> Dict[str, Any]:
    """
    Get all properties for a specific resource.
    
    Args:
        project_path: Path to Terraform project
        resource_type: Resource type (e.g., "aws_iam_role")
        resource_name: Resource name (e.g., "app_role")
        
    Returns:
        Dictionary of properties
    """
    parsed = parse_terraform_project(project_path)
    resource_id = f"{resource_type}.{resource_name}"
    if resource_id in parsed['resources']:
        return parsed['resources'][resource_id]['properties']
    return {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 parse_tf_properties.py <project_path>")
        sys.exit(1)
    
    project_path = sys.argv[1]
    result = parse_terraform_project(project_path)
    print(json.dumps(result, indent=2, default=str))

