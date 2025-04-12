import os
from subprocess import run
import logging
from utils import get_random_tmp_path
import os

logger = logging.getLogger(__name__)

def GetJSON(folderPath: str, init: bool, isTofu=True) -> str:
    """Dump JSON graph information from terraform project

    Args:
        folderPath (str): Path to terraform project
        init (bool): Re-init the terraform project (Destructive!, useful for first time run, otherwise should be False)
        isTofu (bool, optional): Use OpenTofu executable instead of Terraform. Defaults to True.

    Raises:
        Exception: Invalid Folder path

    Returns:
        str: Path to generated JSON
    """
    # check if folderPath exist
    if not os.path.exists(folderPath):
        raise Exception("Cannot found specified folder path!")
    if init:
        InitTerraform(folderPath, isTofu)
    dotPath = GenerateDotFile(folderPath, isTofu)
    jsonPath = GenerateJSON(dotPath)
    return jsonPath    


def InitTerraform(folderPath, isTofu=True):
    # Cleanup
    command = [
            "rm",
            "-rf",
            folderPath + ".terraform",
            folderPath + ".terraform.lock.hcl"
    ]

    logger.info("Running %s" % ' '.join(command)) 
    run(command)
    # Init
    # command = [
    #         "tofu" if isTofu else "terraform",
    #         "-chdir=%s"%folderPath,
    #         "init"
    # ]
    if os.getenv("DOCKER_ENV") == "1":
        command = [
            "terraform",
            f"-chdir={str(os.path.abspath(folderPath))}",
            "init"
        ]
    else:
        command = [
            "docker",
            "run",
            "--platform",
            "linux/amd64",
            "--rm",
            "-a",
            "stdout",
            "-v",
            str(os.path.abspath(folderPath)) + ":/app",
            "hashicorp/terraform:1.8.0-rc2",
            "-chdir=/app",
            "init"
        ]


    logger.info("Running %s" % ' '.join(command)) 
    run(command, check=True)

# tofu graph -chdir ../aws_vpc_msk/
def GenerateDotFile(folderPath: str, isTofu=True) -> str:
    # command = [
    #         "tofu" if isTofu else "terraform",
    #         "-chdir=%s"%folderPath,
    #         "graph",
    #         "-type=plan"
    # ]
    if os.getenv("DOCKER_ENV") == "1":
        command = [
            "terraform",
            f"-chdir={str(os.path.abspath(folderPath))}",
            "graph",
            "-type=plan",
        ]
    else:
        command = [
            "docker",
            "run",
            "--platform",
            "linux/amd64",
            "--rm",
            "-a",
            "stdout",
            "-v",
            str(os.path.abspath(folderPath)) + ":/app",
            "hashicorp/terraform:1.8.0-rc2",
            "-chdir=/app",
            "graph",
            "-type=plan"
        ]

    logger.info("Running %s" % ' '.join(command)) 
    result = run(command, capture_output=True, check=True)
    
    path = get_random_tmp_path()
    logger.info("Writting to %s" % path)

    with open(path, "wb") as f:
        f.write(result.stdout)

    return path

def GenerateJSON(dotPath: str) -> str:
    # command = [
    #         "terraform-graph-beautifier",
    #         "-input",
    #         dotPath,
    #         "--output-type=cyto-json"
    # ]
    if os.getenv("DOCKER_ENV") == "1":
        command = [
            "terraform-graph-beautifier",
            "-input",
            dotPath,
            "--output-type=cyto-json"
        ]
    else:
        command = [
            "docker",
            "run",
            "--platform",
            "linux/amd64",
            "--rm",
            "-a",
            "stdout",
            "-v",
            str(os.path.abspath(dotPath))+":/app/d.dot",
            "ghcr.io/pcasteran/terraform-graph-beautifier:0.3.4-linux",
            "-input",
            "/app/d.dot",
            "--output-type=cyto-json"
        ]

    logger.info("Running %s" % ' '.join(command)) 
    result = run(command, capture_output=True, check=True)
    
    path = get_random_tmp_path(".json")
    logger.info("Writting to %s" % path)

    with open(path, "wb") as f:
        f.write(result.stdout)

    return path
