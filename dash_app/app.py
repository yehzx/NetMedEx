import threading
import time
from queue import Queue

import dash_bootstrap_components as dbc
import diskcache
from dash import Dash, Input, Output, State, callback, dcc, html
from dash.long_callback import DiskcacheLongCallbackManager
import dash_cytoscape as cyto

from pubtoscape.pubtator3_api_cli import run_query_pipeline
from pubtoscape.pubtator3_to_cytoscape_cli import pubtator2cytoscape

captured_output = ""
cache = diskcache.Cache("./cache")
long_callback_manager = DiskcacheLongCallbackManager(cache)


app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP],
           long_callback_manager=long_callback_manager,
           suppress_callback_exceptions=True)


query_component = [
    html.H5("Query"),
    dbc.Input(
        placeholder='Enter a value...',
        type='text',
        id="data-input"
    ),
]

pmid_component = [
    html.H5("PMID"),
    dbc.Input(
        placeholder='Enter PMIDs... (ex: 33422831,33849366)',
        type='text',
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
    # html.Br(),
    # html.Div([
    #     html.H5("Output"),
    #     html.Div(html.P(id="output-area"), className="output-container")
    # ], className="param"),
]

content = html.Div([
    html.Div([*api, *cytoscape, *progress], className="sidebar"),
    html.Div([
        html.H2("PubTator3 To Cytoscape"),
        html.Div(id="cytoscape-graph", className="graph"),
    ], className="flex-grow-1 main-div"),
], className="d-flex flex-row")

app.layout = html.Div(
    [
        content
    ], className="container wrapper")

# @callback(
#     [Output("progress", "value"), Output("progress", "label")],
#     [Input("progress-interval", "n_intervals")],
# )


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
    Input("submit-button", "n_clicks"),
    [State("input-type-selection", "value"),
     State("data-input", "value"),
     State("cut-weight", "value"),
     State("extra-params", "value"),
     State("weighting-method", "value"),
     State("index-by", "value")],
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
                      index_by):
    full_text = 2 in extra_params
    standardized_name = 1 in extra_params
    queue = Queue()

    job = threading.Thread(target=run_query_pipeline,
                           args=(data_input,
                                 "pubtator3_output",
                                 input_type,
                                 1000,
                                 full_text,
                                 standardized_name,
                                 queue))
    job.start()
    set_progress((0, 1, "", "Finding articles..."))
    while True:
        progress = queue.get()
        if progress is None:
            break
        n, total = progress.split("/")
        set_progress((n, total, progress, "Finding articles..."))

    time.sleep(1)

    args = {
        "input": "pubtator3_output",
        "output": "pubtator3_graph.html",
        "cut_weight": weight,
        "format": "html",
        "index_by": index_by,
        "weighting_method": weighting_method,
        "pmid_weight": None,
    }

    graph_json = pubtator2cytoscape(args["input"], args["output"], args, True)

    # run_query_pipeline(query=query,
    #                    savepath="pubtator3 output",
    #                    type="query",
    #                    full_text=full_text,
    #                    standardized=standardized_name)
    cytoscape_graph = cyto.Cytoscape(
        id="cy",
        minZoom=0.1,
        maxZoom=20,
        style={},
        layout={"name": "preset"},
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

    return cytoscape_graph


if __name__ == "__main__":
    app.run(debug=True)
