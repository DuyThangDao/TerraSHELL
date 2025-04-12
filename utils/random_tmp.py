from random import choices
from string import ascii_lowercase
import os

def get_random_tmp_path(suffix: str = ".dot") -> str:
    name = get_random_id(8)
    if not os.path.exists("./tmp"):
        os.makedirs("./tmp")
    return "./tmp/" + name + suffix

def get_random_id(length = 10) -> str:
    return ''.join(choices(ascii_lowercase, k=length))