import os
import pickle
import threading
import time
from pathlib import Path
from queue import Queue

import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
import dash_svg as svg
import diskcache
import networkx as nx
from dash import Dash, Input, Output, State, callback, dcc, html
from dash.long_callback import DiskcacheLongCallbackManager

from pubtoscape.cytoscape_html import save_as_html
from pubtoscape.cytoscape_json import create_cytoscape_json
from pubtoscape.cytoscape_xgmml import save_as_xgmml
from pubtoscape.exceptions import EmptyInput, NoArticles, UnsuccessfulRequest
from pubtoscape.pubtator3_api_cli import run_query_pipeline
from pubtoscape.pubtator3_to_cytoscape_cli import (pubtator2cytoscape,
                                                   remove_edges_by_weight,
                                                   remove_isolated_nodes,
                                                   spring_layout)
from pubtoscape.utils import config_logger
from pubtoscape.utils_threading import run_thread_with_error_notification
from dotenv import load_dotenv

load_dotenv()
config_logger(is_debug=(os.getenv("LOGGING_DEBUG") == "true"))

cache = diskcache.Cache("./cache")
long_callback_manager = DiskcacheLongCallbackManager(cache)
APP_ROOT = Path(__file__).parent
DATA = {"graph": APP_ROOT / "G.pkl",
        "xgmml": APP_ROOT / "output.xgmml",
        "html": APP_ROOT / "output.html",
        "pubtator": APP_ROOT / "output.pubtator"}
MAX_ARTICLES = 1000

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP],
           long_callback_manager=long_callback_manager,
           suppress_callback_exceptions=True)
app.title = "PubTatorToCytoscape"


query_component = [
    html.H5("Query"),
    dbc.Input(
        placeholder="Enter a query (ex: dimethylnitrosamine)",
        type="text",
        id="data-input"
    ),
]

pmid_component = [
    html.H5("PMID"),
    dbc.Input(
        placeholder="Enter PMIDs (ex: 33422831,33849366)",
        type="text",
        id="data-input"
    ),
]

api = [
    html.Div([
        html.H5("Search Type"),
        dcc.Dropdown(id="input-type-selection",
                     options=[
                         {"label": "Query", "value": "query"},
                         {"label": "PMID", "value": "pmid"}
                     ],
                     value="query",
                     style={"width": "200px"},
                     ),
    ], className="param"),
    html.Div(id="input-type", className="param"),
    html.Div([
        html.H5("PubTator3 Parameters"),
        dbc.Checklist(
            options=[
                {"label": "Standardized name", "value": 1},
                {"label": "Full text", "value": 2},
            ],
            switch=True,
            id="extra-params",
            value=[],
        ),
    ], className="param"),
]

cytoscape = [
    html.Div([
        html.H5("Indexing Method"),
        dcc.Dropdown(id="index-by",
                     options=[
                         {"label": "Name", "value": "name"},
                         {"label": "MeSH", "value": "mesh"},
                         {"label": "Relation", "value": "relation"}
                     ],
                     value="name",
                     style={"width": "200px"},
                     ),
    ], className="param"),
    html.Div([
        html.H5("Weighting Method"),
        dcc.Dropdown(id="weighting-method",
                     options=[
                         {"label": "Frequency", "value": "freq"},
                         {"label": "NPMI", "value": "npmi"},
                     ],
                     value="freq",
                     style={"width": "200px"},
                     ),
    ], className="param"),
    html.Div([
        html.H5("Cut Weight"),
        dcc.Slider(1, 20, 1, value=3, id="cut-weight"),
    ], className="param"),
]

progress = [
    html.Div(
        [
            html.H5("Progress"),
            html.P(" ", id="progress-status"),
            dbc.Progress(id="progress")
        ],
        className="param"
    ),
    html.Div([
        dbc.Button("Submit", id="submit-button"),
        html.Div(id="output")
    ]),
]

content = html.Div([
    html.Div([*api, *cytoscape, *progress], className="sidebar"),
    html.Div([
        html.H2("PubTator3 To Cytoscape"),
        html.Div(id="cytoscape-graph", className="graph"),
    ], className="flex-grow-1 main-div"),
    html.Div([
        dbc.Button(
            "Export (html)",
            id="export-btn-html",
            style={"visibility": "hidden"},
            className="export-btn"),
        dcc.Download(id="export-html"),
        dbc.Button(
            "Export (xgmml)",
            id="export-btn-xgmml",
            style={"visibility": "hidden"},
            className="export-btn"),
        dcc.Download(id="export-xgmml"),
        dbc.Button(
            svg.Svg(xmlns="http://www.w3.org/2000/svg",
                    width="20",
                    height="20",
                    fill="currentColor",
                    className="bi bi-three-dots",
                    viewBox="0 0 16 16",
                    children=[
                        svg.Path(
                            d="M3 9.5a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3m5 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3m5 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3"),
                    ]
                    ),
            # "Settings",
            id="graph-settings",
            style={"visibility": "hidden"},
            className="btn-secondary"),
        dbc.Collapse(
            html.Div([
                html.H4("Settings"),
                html.Div([
                    html.H5("Graph Layout"),
                    dcc.Dropdown(id="graph-layout",
                                 options=[
                                     {"label": "Preset", "value": "preset"},
                                     {"label": "Circle", "value": "circle"},
                                     {"label": "Grid", "value": "grid"},
                                     {"label": "Random", "value": "random"},
                                     {"label": "Concentric", "value": "concentric"},
                                     {"label": "Breadthfirst",
                                         "value": "breadthfirst"},
                                     {"label": "Cose", "value": "cose"},
                                 ],
                                 value="preset",
                                 style={"width": "200px"},
                                 ),
                ], className="param"),
                html.Div([
                    html.H5("Minimal degree"),
                    dbc.Input(id="node-degree",
                              min=1, step=1, value=1, type="number",
                              style={"width": "200px"},
                              ),
                    dcc.Store(id="memory-node-degree", data=1)
                ], className="param"),
                html.Div([
                    html.H5("Cut weight"),
                    dcc.Slider(1, 20, 1, value=3, id="graph-cut-weight"),
                    dcc.Store(id="memory-graph-cut-weight", data=3),
                ], className="param"),

            ]),
            id="graph-settings-collapse",
            is_open=False,
            className="collapse",
        ),
    ], id="toolbox"),
], className="d-flex flex-row position-relative")

app.layout = html.Div(
    [
        content
    ], className="container wrapper"
)


@callback(
    Output("input-type", "children"),
    Input("input-type-selection", "value"),
)
def update_input_type(input_type):
    if input_type == "query":
        return query_component
    elif input_type == "pmid":
        return pmid_component


@app.long_callback(
    Output("cytoscape-graph", "children"),
    Output("graph-settings", "style"),
    Output("export-btn-html", "style"),
    Output("export-btn-xgmml", "style"),
    Output("graph-settings-collapse", "is_open", allow_duplicate=True),
    Output("graph-cut-weight", "value"),
    Input("submit-button", "n_clicks"),
    [State("input-type-selection", "value"),
     State("data-input", "value"),
     State("cut-weight", "value"),
     State("extra-params", "value"),
     State("weighting-method", "value"),
     State("index-by", "value"),
     State("graph-layout", "value"),
     State("node-degree", "value")],
    running=[(Input("submit-button", "disabled"), True, False)],
    progress=[Output("progress", "value"),
              Output("progress", "max"),
              Output("progress", "label"),
              Output("progress-status", "children")],
    prevent_initial_call=True,
)
def run_pubtator3_api(set_progress,
                      btn,
                      input_type,
                      data_input,
                      weight,
                      extra_params,
                      weighting_method,
                      index_by,
                      graph_layout,
                      node_degree_threshold):
    _exception_msg = None
    _exception_type = None

    def custom_hook(args):
        nonlocal _exception_msg
        nonlocal _exception_type
        _exception_msg = args.exc_value
        _exception_type = args.exc_type

    full_text = 2 in extra_params
    standardized_name = 1 in extra_params

    queue = Queue()
    threading.excepthook = custom_hook
    job = threading.Thread(
        target=run_thread_with_error_notification(run_query_pipeline, queue),
        args=(data_input,
              str(DATA["pubtator"]),
              input_type,
              MAX_ARTICLES,
              full_text,
              standardized_name,
              queue)
    )
    set_progress((0, 1, "", "Finding articles..."))

    job.start()
    while True:
        progress = queue.get()
        if progress is None:
            break
        n, total = progress.split("/")
        set_progress((n, total, progress, "Finding articles..."))

    if _exception_type is not None:
        known_exceptions = (
            EmptyInput,
            NoArticles,
            UnsuccessfulRequest,
        )
        if issubclass(_exception_type, known_exceptions):
            set_progress((1, 1, "", str(_exception_msg)))
            return (None, *([{"visibility": "hidden"}] * 3), False, weight)

    time.sleep(0.5)

    args = {
        "input": DATA["pubtator"],
        "output": DATA["html"],
        "cut_weight": 1,
        "format": "html",
        "index_by": index_by,
        "weighting_method": weighting_method,
        "pmid_weight": None,
    }

    set_progress((0, 1, "0/1", "Generating network..."))
    G = pubtator2cytoscape(args["input"], args["output"], args)

    with open(DATA["graph"], "wb") as f:
        pickle.dump(G, f)

    remove_edges_by_weight(G, weight)
    remove_isolated_nodes(G)
    filter_node(G, node_degree_threshold)
    spring_layout(G)

    graph_json = create_cytoscape_json(G)
    cytoscape_graph = cyto.Cytoscape(
        id="cy",
        minZoom=0.1,
        maxZoom=20,
        style={},
        layout={"name": graph_layout},
        stylesheet=[
            {
                "selector": "node",
                "style": {
                    "text-valign": "center",
                    "label": "data(label)",
                    "shape": "data(shape)",
                    "background-color": "data(color)",
                },
            },
            {
                "selector": "edge",
                "style": {
                    "width": "data(weight)",
                },
            }
        ],
        elements=[*graph_json["elements"]["nodes"],
                  *graph_json["elements"]["edges"]],
    )

    return (cytoscape_graph, *([{"visibility": "visible"}] * 3), False, weight)


def filter_node(G: nx.Graph, node_degree_threshold: int):
    for (node, degree) in list(G.degree()):
        if degree < node_degree_threshold:
            G.remove_node(node)


@callback(
    Output("progress", "value"),
    Output("progress", "max"),
    Output("progress", "label"),
    Output("progress-status", "children"),
    Input("cytoscape-graph", "children"),
    State("progress-status", "children"),
    running=[(Input("submit-button", "disabled"), True, False)],
    prevent_initial_call=True,
)
def plot_cytoscape_graph(graph_children, progress):
    if graph_children is not None:
        return 1, 1, "1/1", "Done"
    else:
        return 1, 1, "", progress


@callback(
    Output("graph-settings-collapse", "is_open"),
    Input("graph-settings", "n_clicks"),
    State("graph-settings-collapse", "is_open"),
    prevent_initial_call=True,
)
def open_settings(n_clicks, is_open):
    return not is_open


@callback(
    Output("cy", "layout"),
    Output("cy", "elements", allow_duplicate=True),
    Input("graph-layout", "value"),
    State("node-degree", "value"),
    State("graph-cut-weight", "value"),
    State("cy", "elements"),
    prevent_initial_call=True,
)
def update_graph_layout(layout, node_degree, weight, elements):
    if layout == "preset":
        G = rebuild_graph_from_original(node_degree,
                                        weight,
                                        with_layout=True)
        graph_json = create_cytoscape_json(G)
        elements = [*graph_json["elements"]["nodes"],
                    *graph_json["elements"]["edges"]]

    return {"name": layout}, elements


def rebuild_graph_from_original(node_degree, cut_weight, with_layout=False):
    with open(DATA["graph"], "rb") as f:
        G = pickle.load(f)
    remove_edges_by_weight(G, cut_weight)
    remove_isolated_nodes(G)
    filter_node(G, node_degree)
    if with_layout:
        spring_layout(G)
    return G


@callback(
    Output("cy", "elements", allow_duplicate=True),
    Output("memory-node-degree", "data"),
    Output("memory-graph-cut-weight", "data"),
    Input("node-degree", "value"),
    Input("graph-cut-weight", "value"),
    State("memory-node-degree", "data"),
    State("memory-graph-cut-weight", "data"),
    State("cy", "elements"),
    prevent_initial_call=True,
)
def update_nodes(new_node_degree,
                 new_cut_weight,
                 old_node_degree,
                 old_cut_weight,
                 elements):
    if new_cut_weight != old_cut_weight or new_node_degree != old_node_degree:
        G = rebuild_graph_from_original(new_node_degree,
                                        new_cut_weight,
                                        with_layout=True)
        graph_json = create_cytoscape_json(G)
        elements = [*graph_json["elements"]["nodes"],
                    *graph_json["elements"]["edges"]]

    return elements, new_node_degree, new_cut_weight


@callback(
    Output("export-html", "data"),
    Input("export-btn-html", "n_clicks"),
    State("graph-layout", "value"),
    State("node-degree", "value"),
    State("graph-cut-weight", "value"),
    prevent_initial_call=True,
)
def export_html(n_clicks, layout, node_degree, weight):
    G = rebuild_graph_from_original(node_degree, weight, with_layout=True)
    save_as_html(G, DATA["html"], layout=layout)
    return dcc.send_file(str(DATA["html"]))


@callback(
    Output("export-xgmml", "data"),
    Input("export-btn-xgmml", "n_clicks"),
    State("graph-layout", "value"),
    State("node-degree", "value"),
    State("graph-cut-weight", "value"),
    prevent_initial_call=True,
)
def export_xgmml(n_clicks, layout, node_degree, weight):
    G = rebuild_graph_from_original(node_degree, weight, with_layout=True)
    save_as_xgmml(G, DATA["xgmml"])
    return dcc.send_file(DATA["xgmml"])


def clean_up_files():
    for file in DATA.values():
        try:
            os.remove(str(file))
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    try:
        app.run()
    finally:
        clean_up_files()
