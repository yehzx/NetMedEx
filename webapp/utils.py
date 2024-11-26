import os
from pathlib import Path
from types import SimpleNamespace

APP_ROOT = Path(__file__).parent
MAX_ARTICLES = 1000
DATA = {
    "graph": APP_ROOT / "G.pkl",
    "xgmml": APP_ROOT / "output.xgmml",
    "html": APP_ROOT / "output.html",
    "pubtator": APP_ROOT / "output.pubtator",
    "edge_info": APP_ROOT / "output.csv",
}
visibility = SimpleNamespace(visible={"visibility": "visible"}, hidden={"visibility": "hidden"})
display = SimpleNamespace(block={"display": "block"}, none={"display": "none"})


def clean_up_files():
    for file in DATA.values():
        try:
            os.remove(str(file))
        except FileNotFoundError:
            pass
