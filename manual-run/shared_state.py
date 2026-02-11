"""
Shared state module để lưu trữ các biến được chia sẻ giữa các steps
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

# File để lưu state
STATE_FILE = os.path.join(os.path.dirname(__file__), ".state.json")

def save_state(key, value):
    """Lưu một giá trị vào state file"""
    state = load_all_state()
    state[key] = value
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2, default=str)
        logger.debug(f"Saved state: {key} = {value}")
    except Exception as e:
        logger.error(f"Error saving state: {e}")

def load_state(key, default=None):
    """Load một giá trị từ state file"""
    state = load_all_state()
    return state.get(key, default)

def load_all_state():
    """Load toàn bộ state từ file"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading state file: {e}, returning empty state")
            return {}
    return {}

def clear_state():
    """Xóa toàn bộ state"""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        logger.info("State file cleared")

def get_path_id():
    """Lấy pathID từ state"""
    return load_state("pathID")

def set_path_id(path_id):
    """Lưu pathID vào state"""
    save_state("pathID", path_id)

def get_in_path():
    """Lấy in_path từ state"""
    return load_state("in_path")

def set_in_path(in_path):
    """Lưu in_path vào state"""
    save_state("in_path", in_path)

def get_out_path():
    """Lấy out_path từ state"""
    return load_state("out_path", "./output")

def set_out_path(out_path):
    """Lưu out_path vào state"""
    save_state("out_path", out_path)

def get_anno():
    """Lấy annotation config từ state"""
    return load_state("anno")

def set_anno(anno):
    """Lưu annotation config vào state"""
    save_state("anno", anno)

def get_rule():
    """Lấy rule config từ state"""
    return load_state("rule")

def set_rule(rule):
    """Lưu rule config vào state"""
    save_state("rule", rule)

def get_compresses():
    """Lấy danh sách compress từ state"""
    return load_state("compresses", [])

def set_compresses(compresses):
    """Lưu danh sách compress vào state"""
    save_state("compresses", compresses)

def get_publics():
    """Lấy danh sách publics từ state"""
    return load_state("publics", set())

def set_publics(publics):
    """Lưu danh sách publics vào state (convert set to list for JSON)"""
    save_state("publics", list(publics) if isinstance(publics, set) else publics)


def get_global_tb_name():
    """Lấy global_tb_name từ state"""
    return load_state("global_tb_name", "Cloud")

def set_global_tb_name(name):
    """Lưu global_tb_name vào state"""
    save_state("global_tb_name", name)

def get_graph_mode():
    """Lấy graph_mode từ state"""
    return load_state("graph_mode", False)

def set_graph_mode(mode):
    """Lưu graph_mode vào state"""
    save_state("graph_mode", mode)
