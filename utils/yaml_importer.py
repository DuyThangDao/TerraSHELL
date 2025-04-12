import yaml
import json

def read_config(filePath: str) -> object:
    with open(filePath, "r") as f:
        return yaml.load(f, Loader=yaml.Loader)

def print_object(obj: object):
    print(json.dumps(obj, indent=2, default=str))