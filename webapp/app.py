from dotenv import load_dotenv

load_dotenv()


import base64
import os
import pickle
import threading
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
import uuid

import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
import dash_svg as svg
import diskcache
import networkx as nx
from dash import (ClientsideFunction, Dash, Input, Output, State, callback,
                  clientside_callback, dcc, html, no_update)
from dash.long_callback import DiskcacheLongCallbackManager

from netmedex.api_cli import load_pmids, run_query_pipeline
from netmedex.cytoscape_js import create_cytoscape_js, save_as_html
from netmedex.cytoscape_xgmml import save_as_xgmml
from netmedex.exceptions import EmptyInput, NoArticles, UnsuccessfulRequest
from netmedex.network_cli import (pubtator2cytoscape, remove_edges_by_weight,
                                  remove_isolated_nodes,
                                  set_network_communities, spring_layout)
from netmedex.utils import config_logger
from netmedex.utils_threading import run_thread_with_error_notification

config_logger(is_debug=(os.getenv("LOGGING_DEBUG") == "true"))

cache = diskcache.Cache("./cache")
long_callback_manager = DiskcacheLongCallbackManager(cache)
APP_ROOT = Path(__file__).parent
DATA = {"graph": APP_ROOT / "G.pkl",
        "xgmml": APP_ROOT / "output.xgmml",
        "html": APP_ROOT / "output.html",
        "pubtator": APP_ROOT / "output.pubtator",
        "edge_info": APP_ROOT / "output.csv"}
MAX_ARTICLES = 1000

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP],
           long_callback_manager=long_callback_manager,
           suppress_callback_exceptions=True)
app.title = "PubTatorToCytoscape"
visibility = SimpleNamespace(visible={"visibility": "visible"},
                             hidden={"visibility": "hidden"})
display = SimpleNamespace(block={"display": "block"},
                          none={"display": "none"})


def generate_query_component(hidden=False):
    return html.Div(
        [
            html.H5("Query"),
            dbc.Input(
                placeholder="Enter a query (ex: dimethylnitrosamine)",
                type="text",
                id="data-input"
            )
        ],
        hidden=hidden
    )


def generate_pmid_component(hidden=False):
    return html.Div(
        [
            html.H5("PMID"),
            dbc.Input(
                placeholder="Enter PMIDs (ex: 33422831,33849366)",
                type="text",
                id="data-input"
            )
        ],
        hidden=hidden)


def generate_pmid_file_component(hidden=False):
    return html.Div(
        [
            html.H5("PMID File"),
            dcc.Upload(
                id="pmid-file-data",
                children=html.Div([
                    "Drag and Drop or ",
                    html.A("Select Files", className="hyperlink")
                ], className="upload-box form-control")
            ),
            html.Div(id="output-data-upload"),
        ],
        hidden=hidden)


api_toggle = html.Div([
    html.Div([
        html.H5("Source"),
        dbc.RadioItems(id="api-toggle-items",
                       options=[
                           {"label": "PubTator3 API", "value": "api"},
                           {"label": "PubTator File", "value": "file"}
                       ],
                       value="api",
                       inline=True),
    ], className="param")
], id="api-toggle")

pubtator_file = html.Div([
    html.Div([
        html.H5("PubTator File"),
        dcc.Upload(
            id="pubtator-file-data",
            children=html.Div([
                "Drag and Drop or ",
                html.A("Select Files", className="hyperlink")
            ], className="upload-box form-control")
        ),
        html.Div(id="pubtator-file-upload"),
    ], className="param")
], style=display.none, id="pubtator-file-wrapper")

api = html.Div([
    html.Div([
        html.H5("Search Type"),
        dcc.Dropdown(id="input-type-selection",
                     options=[
                         {"label": "Text Search", "value": "query"},
                         {"label": "PMID", "value": "pmids"},
                         {"label": "PMID File", "value": "pmid_file"}
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
                {"label": "Use MeSH Vocabulary", "value": "use_mesh"},
                {"label": "Full Text", "value": "full_text"},
            ],
            switch=True,
            id="pubtator-params",
            value=["use_mesh"],
        ),
    ], className="param"),
], id="api-wrapper")


cytoscape = html.Div([
    html.Div([
        html.H5("Node Type"),
        dcc.Dropdown(id="node-type",
                     options=[
                         {"label": "Normalized Text", "value": "all"},
                         {"label": "Has MeSH", "value": "mesh"},
                         {"label": "BioREx Relation Only", "value": "relation"}
                     ],
                     value="all",
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
        html.H5("Edge Weight Cutoff"),
        dcc.Slider(1, 20, 1, value=3, marks=None, id="cut-weight",
                   tooltip={"placement": "bottom", "always_visible": True}),
    ], className="param"),
    html.Div([
        html.H5("Network Parameters"),
        dbc.Checklist(
            options=[
                {"label": "Community", "value": "community"},
            ],
            switch=True,
            id="cy-params",
            value=[],
        ),
    ], className="param"),
], id="cy-wrapper")

progress = html.Div([
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
], id="progress-wrapper")

toolbox = html.Div([
    dbc.Button(
        "Export (html)",
        id="export-btn-html",
        className="export-btn"),
    dcc.Download(id="export-html"),
    dbc.Button(
        "Export (xgmml)",
        id="export-btn-xgmml",
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
        className="btn-secondary"),
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
            html.H5("Minimal Degree"),
            dbc.Input(id="node-degree",
                      min=1, step=1, value=1, type="number",
                      style={"width": "200px"},
                      ),
            dcc.Store(id="memory-node-degree", data=1)
        ], className="param"),
        html.Div([
            html.H5("Edge Weight Cutoff"),
            dcc.Slider(1, 20, 1, value=3, marks=None, id="graph-cut-weight",
                       tooltip={"placement": "bottom", "always_visible": False}),
            dcc.Store(id="memory-graph-cut-weight", data=3),
        ], className="param"),
    ],
        id="graph-settings-collapse",
        style=visibility.hidden,
    ),
], id="toolbox")

edge_info = html.Div([
    html.H5("Edge Info", className="text-center"),
    dbc.Button("Export (CSV)", id="export-edge-btn", className="export-btn"),
    dcc.Download(id="export-edge-csv"),
    html.Div(id="edge-info"),
], id="edge-info-container", className="flex-grow-1", style=visibility.hidden)


def create_legend_box(icon, text):
    return html.Div([
        html.Img(src=app.get_asset_url(icon), width=25, height=25),
        html.P(text),
    ], className="legend-box")


legend = html.Div([
    create_legend_box("icon_species.svg", "Species"),
    create_legend_box("icon_chemical.svg", "Chemical"),
    create_legend_box("icon_gene.svg", "Gene"),
    create_legend_box("icon_disease.svg", "Disease"),
    create_legend_box("icon_cellline.svg", "CellLine"),
    create_legend_box("icon_dnamutation.svg", "DNAMutation"),
    create_legend_box("icon_proteinmutation.svg", "ProteinMutation"),
    create_legend_box("icon_snp.svg", "SNP"),
], id="legend-container")

bottom = html.Div([edge_info, legend],
                  id="bottom-container",
                  className="d-flex")

content = html.Div([
    html.Div([api_toggle, api, pubtator_file, cytoscape, progress],
             className="sidebar"),
    html.Div([
        html.Div([
            html.Img(src=app.get_asset_url("NetMedEx.png"), height="40px"),
        ], className="d-flex flex-row justify-content-center"),
        html.Div([
            toolbox,
            bottom,
            html.Div(id="cy-graph", className="flex-grow-1"),
            dcc.Store(id="is-new-graph", data=False),
            dcc.Store(id="pmid-title-dict", data={}),
        ],
            id="cy-graph-container",
            className="d-flex flex-column flex-grow-1 position-relative",
            style=visibility.hidden),
    ], className="d-flex flex-column flex-grow-1 main-div"),
], className="d-flex flex-row position-relative h-100")

app.layout = html.Div(
    [
        content
    ], className="wrapper"
)


@callback(
    Output("api-wrapper", "style"),
    Output("pubtator-file-wrapper", "style"),
    Input("api-toggle-items", "value"),
    prevent_initial_call=True,
)
def update_api_toggle(api_toggle):
    if api_toggle == "api":
        return display.block, display.none
    elif api_toggle == "file":
        return display.none, display.block


@callback(
    Output("input-type", "children"),
    Input("input-type-selection", "value"),
)
def update_input_type(input_type):
    if input_type == "query":
        return [generate_query_component(hidden=False),
                generate_pmid_file_component(hidden=True)]
    elif input_type == "pmids":
        return [generate_pmid_component(hidden=False),
                generate_pmid_file_component(hidden=True)]
    elif input_type == "pmid_file":
        return [generate_query_component(hidden=True),
                generate_pmid_file_component(hidden=False)]


def display_uploaded_data(data, filename):
    if data is not None:
        content_type, content_string = data.split(",")
        decoded_content = base64.b64decode(content_string).decode("utf-8")
        displayed_text = decoded_content.split("\n")[:5]
        displayed_text = [t[:100] + "..." if len(t) > 100 else t for t in displayed_text]
        return [
            html.H6(f"File: {filename}",
                    style={"marginBottom": "5px", "marginTop": "5px"}),
            html.Pre("\n".join(displayed_text), className="upload-preview"),
        ]
    else:
        return no_update


@callback(
    Output("output-data-upload", "children"),
    Input("pmid-file-data", "contents"),
    State("pmid-file-data", "filename"),
)
def update_data_upload(upload_data, filename):
    return display_uploaded_data(upload_data, filename)


@callback(
    Output("pubtator-file-upload", "children"),
    Input("pubtator-file-data", "contents"),
    State("pubtator-file-data", "filename"),
)
def update_pubtator_upload(pubtator_data, filename):
    return display_uploaded_data(pubtator_data, filename)


@callback(
    Output("graph-settings-collapse", "style", allow_duplicate=True),
    Output("graph-cut-weight", "value"),
    Output("graph-cut-weight", "tooltip", allow_duplicate=True),
    Input("cy-graph-container", "style"),
    State("memory-graph-cut-weight", "data"),
    prevent_initial_call=True,
)
def update_graph_params(container_style, cut_weight):
    return (visibility.hidden,
            cut_weight,
            {"placement": "bottom", "always_visible": False})


@app.long_callback(
    Output("cy-graph-container", "style", allow_duplicate=True),
    Output("memory-graph-cut-weight", "data", allow_duplicate=True),
    Output("is-new-graph", "data"),
    Output("pmid-title-dict", "data"),
    Input("submit-button", "n_clicks"),
    [State("api-toggle-items", "value"),
     State("input-type-selection", "value"),
     State("data-input", "value"),
     State("pmid-file-data", "contents"),
     State("pubtator-file-data", "contents"),
     State("cut-weight", "value"),
     State("pubtator-params", "value"),
     State("cy-params", "value"),
     State("weighting-method", "value"),
     State("node-type", "value")],
    running=[(Input("submit-button", "disabled"), True, False)],
    progress=[Output("progress", "value"),
              Output("progress", "max"),
              Output("progress", "label"),
              Output("progress-status", "children")],
    prevent_initial_call=True,
)
def run_pubtator3_api(set_progress,
                      btn,
                      source,
                      input_type,
                      data_input,
                      pmid_file_data,
                      pubtator_file_data,
                      weight,
                      pubtator_params,
                      cy_params,
                      weighting_method,
                      node_type):
    _exception_msg = None
    _exception_type = None

    def custom_hook(args):
        nonlocal _exception_msg
        nonlocal _exception_type
        _exception_msg = args.exc_value
        _exception_type = args.exc_type

    use_mesh = "use_mesh" in pubtator_params
    full_text = "full_text" in pubtator_params
    community = "community" in cy_params

    if source == "api":
        if input_type == "query":
            query = data_input
        elif input_type == "pmids":
            query = load_pmids(data_input, load_from="string")
        elif input_type == "pmid_file":
            content_type, content_string = pmid_file_data.split(",")
            decoded_content = base64.b64decode(content_string).decode("utf-8")
            decoded_content = decoded_content.replace("\n", ",")
            query = load_pmids(decoded_content, load_from="string")
            input_type = "pmids"

        queue = Queue()
        threading.excepthook = custom_hook
        job = threading.Thread(
            target=run_thread_with_error_notification(run_query_pipeline, queue),
            args=(query,
                  str(DATA["pubtator"]),
                  input_type,
                  MAX_ARTICLES,
                  full_text,
                  use_mesh,
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
                exception_msg = str(_exception_msg)
            else:
                exception_msg = "An unexpected error occurred."
            set_progress((1, 1, "", exception_msg))
            return (no_update, weight, False, no_update)

        job.join()
    elif source == "file":
        with open(DATA["pubtator"], "w") as f:
            content_type, content_string = pubtator_file_data.split(",")
            decoded_content = base64.b64decode(content_string).decode("utf-8")
            f.write(decoded_content)

    args = {
        "input": DATA["pubtator"],
        "output": DATA["html"],
        "cut_weight": 1,
        "format": "html",
        "node_type": node_type,
        "weighting_method": weighting_method,
        "pmid_weight": None,
        "community": False,
    }

    set_progress((0, 1, "0/1", "Generating network..."))
    G = pubtator2cytoscape(args["input"], args["output"], args)

    G.graph["is_community"] = True if community else False

    with open(DATA["graph"], "wb") as f:
        pickle.dump(G, f)

    return (visibility.visible, weight, True, G.graph["pmid_title"])


def generate_cytoscape_js_network(graph_layout, graph_json):
    if graph_json is not None:
        elements = [*graph_json["elements"]["nodes"],
                    *graph_json["elements"]["edges"]]
    else:
        elements = []

    cytoscape_graph = cyto.Cytoscape(
        id="cy",
        minZoom=0.1,
        maxZoom=20,
        wheelSensitivity=0.3,
        style={},
        layout={"name": graph_layout},
        stylesheet=[
            {
                "selector": "node",
                "style": {
                    "text-valign": "center",
                    "label": "data(label)",
                    "shape": "data(shape)",
                    "color": "data(label_color)",
                    "background-color": "data(color)",
                },
            },
            {
                "selector": ":parent",
                "style": {
                    "background-opacity": 0.3,
                },
            },
            {
                "selector": "edge",
                "style": {
                    "width": "data(weight)",
                },
            },
            {
                "selector": ".top-center",
                "style": {
                    "text-valign": "top",
                    "text-halign": "center",
                    "font-size": "20px",
                },
            },
        ],
        elements=elements,
    )

    return cytoscape_graph


def filter_node(G: nx.Graph, node_degree_threshold: int):
    for (node, degree) in list(G.degree()):
        if degree < node_degree_threshold:
            G.remove_node(node)


@callback(
    Output("progress", "value"),
    Output("progress", "max"),
    Output("progress", "label"),
    Output("progress-status", "children"),
    Input("cy-graph", "children"),
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
    Output("graph-settings-collapse", "style", allow_duplicate=True),
    Output("graph-cut-weight", "tooltip"),
    Input("graph-settings", "n_clicks"),
    State("graph-settings-collapse", "style"),
    prevent_initial_call=True,
)
def open_settings(n_clicks, style):
    visibility = style["visibility"]
    toggle = {"hidden": "visible", "visible": "hidden"}
    weight_toggle = {"hidden": True, "visible": False}
    return ({"visibility": toggle[visibility]},
            {"placement": "bottom",
             "always_visible": weight_toggle[visibility]})


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
        G = rebuild_graph(node_degree,
                          weight,
                          with_layout=True)
        graph_json = create_cytoscape_js(G, style="dash")
        graph_json = generate_new_id(graph_json)
        elements = [*graph_json["elements"]["nodes"],
                    *graph_json["elements"]["edges"]]

    return {"name": layout}, elements


# TODO: temporary workaround for cannot create edge for non-existence source or target
# https://github.com/plotly/dash-cytoscape/issues/106
def generate_new_id(graph_json):
    id_map = {}
    # Give new id to each node
    for node in graph_json["elements"]["nodes"]:
        new_id = str(uuid.uuid4())
        old_id = node["data"]["id"]
        id_map[old_id] = new_id
        node["data"]["id"] = new_id

    # Update parent node id
    for node in graph_json["elements"]["nodes"]:
        if (old_parent_id := node["data"]["parent"]) is not None:
            node["data"]["parent"] = id_map[old_parent_id]

    # Update source and target for each edge
    for edge in graph_json["elements"]["edges"]:
        edge["data"]["source"] = id_map[edge["data"]["source"]]
        edge["data"]["target"] = id_map[edge["data"]["target"]]

    return graph_json


def rebuild_graph(node_degree,
                  cut_weight,
                  G=None,
                  with_layout=False):
    if G is None:
        with open(DATA["graph"], "rb") as f:
            G = pickle.load(f)

    remove_edges_by_weight(G, cut_weight)
    remove_isolated_nodes(G)
    filter_node(G, node_degree)

    if with_layout:
        spring_layout(G)

    if G.graph.get("is_community", False):
        set_network_communities(G)

    return G


@callback(
    Output("cy-graph", "children"),
    Output("is-new-graph", "data", allow_duplicate=True),
    Output("memory-node-degree", "data"),
    Output("memory-graph-cut-weight", "data", allow_duplicate=True),
    Input("node-degree", "value"),
    Input("graph-cut-weight", "value"),
    State("memory-node-degree", "data"),
    State("memory-graph-cut-weight", "data"),
    State("cy-graph-container", "style"),
    State("graph-layout", "value"),
    State("is-new-graph", "data"),
    prevent_initial_call=True,
)
def update_graph(new_node_degree,
                 new_cut_weight,
                 old_node_degree,
                 old_cut_weight,
                 container_style,
                 graph_layout,
                 is_new_graph):
    if container_style["visibility"] == "hidden":
        cy_graph = generate_cytoscape_js_network(graph_layout, None)
        return cy_graph, False, new_node_degree, new_cut_weight

    if new_node_degree is None:
        new_node_degree = old_node_degree

    conditions = (is_new_graph
                  or new_cut_weight != old_cut_weight
                  or new_node_degree != old_node_degree)
    if conditions:
        G = rebuild_graph(new_node_degree,
                          new_cut_weight,
                          with_layout=True)
        graph_json = create_cytoscape_js(G, style="dash")
        graph_json = generate_new_id(graph_json)
        cy_graph = generate_cytoscape_js_network(graph_layout, graph_json)
        return cy_graph, False, new_node_degree, new_cut_weight
    else:
        return no_update, False, new_node_degree, new_cut_weight


@callback(
    Output("export-html", "data"),
    Input("export-btn-html", "n_clicks"),
    State("graph-layout", "value"),
    State("node-degree", "value"),
    State("graph-cut-weight", "value"),
    prevent_initial_call=True,
)
def export_html(n_clicks, layout, node_degree, weight):
    G = rebuild_graph(node_degree, weight, with_layout=True)
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
    G = rebuild_graph(node_degree, weight, with_layout=True)
    save_as_xgmml(G, DATA["xgmml"])
    return dcc.send_file(DATA["xgmml"])


@callback(
    Output("export-edge-csv", "data"),
    Input("export-edge-btn", "n_clicks"),
    State("cy", "tapEdgeData"),
    State("pmid-title-dict", "data"),
    prevent_initial_call=True,
)
def export_edge_csv(n_clicks, tap_edge, pmid_title):
    import csv
    with open(DATA["edge_info"], "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["PMID", "Title"])
        writer.writerows([[pmid, pmid_title[pmid]] for pmid in tap_edge["pmids"]])
    n1, n2 = tap_edge["label"].split(" (interacts with) ")
    filename = f"{n1}_{n2}.csv"
    return dcc.send_file(DATA["edge_info"], filename=filename)


clientside_callback(
    ClientsideFunction(
        namespace="clientside",
        function_name="show_edge_info"
    ),
    Output("edge-info-container", "style"),
    Output("edge-info", "children"),
    Input("cy", "selectedEdgeData"),
    State("cy", "tapEdgeData"),
    State("pmid-title-dict", "data"),
    prevent_initial_call=True,
)


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
