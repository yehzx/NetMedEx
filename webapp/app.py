from dotenv import load_dotenv

load_dotenv()


import os

import dash_bootstrap_components as dbc
import diskcache
from dash import Dash, html
from dash.long_callback import DiskcacheLongCallbackManager

from netmedex.utils import config_logger
from webapp.callbacks import collect_callbacks
from webapp.utils import clean_up_files

config_logger(is_debug=(os.getenv("LOGGING_DEBUG") == "true"))


cache = diskcache.Cache("./cache")
long_callback_manager = DiskcacheLongCallbackManager(cache)

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    long_callback_manager=long_callback_manager,
    suppress_callback_exceptions=True,
)
app.title = "NetMedEx"

from webapp.components.graph import graph
from webapp.components.sidebar import sidebar

content = html.Div(
    [sidebar, graph],
    className="d-flex flex-row position-relative h-100",
)

app.layout = html.Div([content], id="main-container")


if __name__ == "__main__":
    try:
        collect_callbacks(app)
        app.run()
    finally:
        clean_up_files()
