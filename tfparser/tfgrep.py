import os
from subprocess import run
import logging
from utils import get_random_tmp_path

logger = logging.getLogger(__name__)

def GetSemgrepJSON(folderPath: str, configPath: str) -> str:
    """Dump JSON pattern matching information from terraform project

    Args:
        folderPath (str): Path to terraform project
        configPath (str): Path to semgrep config

    Raises:
        Exception: Invalid Folder path

    Returns:
        str: Path to generated JSON
    """
    # check if folderPath exist
    if not os.path.exists(folderPath) or not os.path.exists(configPath):
        raise Exception("Cannot found specified folder path!")

    path = get_random_tmp_path(".json")
    command = [
        "semgrep",
        "--metrics=off",
        f"--config={configPath}",
        "--output",
        path,
        "--json",
        folderPath
    ]

    logger.info("Running %s" % ' '.join(command)) 
    run(command, capture_output=True, check=True)
    
    logger.info("Writting to %s" % path)

    return path

def SemgrepFix(folderPath: str, configPath: str):
    """Fixing project by semgrep rule

    Args:
        folderPath (str): Path to terraform project
        configPath (str): Path to semgrep config

    Raises:
        Exception: Invalid Folder path
    """
    # check if folderPath exist
    if not os.path.exists(folderPath) or not os.path.exists(configPath):
        raise Exception("Cannot found specified folder path!")

    command = [
        "semgrep",
        "--metrics=off",
        "--autofix",
        f"--config={configPath}",
        folderPath
    ]

    logger.info("Running %s" % ' '.join(command)) 
    run(command, capture_output=True, check=True)