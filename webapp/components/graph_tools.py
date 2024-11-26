import dash_bootstrap_components as dbc
import dash_svg as svg
from dash import dcc, html

from webapp.utils import visibility

graph_layout = html.Div(
    [
        html.H5("Graph Layout"),
        dcc.Dropdown(
            id="graph-layout",
            options=[
                {"label": "Preset", "value": "preset"},
                {"label": "Circle", "value": "circle"},
                {"label": "Grid", "value": "grid"},
                {"label": "Random", "value": "random"},
                {"label": "Concentric", "value": "concentric"},
                {"label": "Breadthfirst", "value": "breadthfirst"},
                {"label": "Cose", "value": "cose"},
            ],
            value="preset",
            style={"width": "200px"},
        ),
    ],
    className="param",
)


minimal_degree = html.Div(
    [
        html.H5("Minimal Degree"),
        dbc.Input(
            id="node-degree",
            min=1,
            step=1,
            value=1,
            type="number",
            style={"width": "200px"},
        ),
        dcc.Store(id="memory-node-degree", data=1),
    ],
    className="param",
)

edge_weight_cutoff = html.Div(
    [
        html.H5("Edge Weight Cutoff"),
        dcc.Slider(
            0,
            20,
            1,
            value=3,
            marks=None,
            id="graph-cut-weight",
            tooltip={"placement": "bottom", "always_visible": False},
        ),
        dcc.Store(id="memory-graph-cut-weight", data=3),
    ],
    className="param",
)

graph_tools = html.Div(
    [
        dbc.Button(
            "PubTator File",
            id="download-pubtator-btn",
            className="export-btn",
            color="success",
            style=visibility.hidden,
        ),
        dcc.Download(id="download-pubtator"),
        dbc.Button("Export (html)", id="export-btn-html", className="export-btn"),
        dcc.Download(id="export-html"),
        dbc.Button("Export (xgmml)", id="export-btn-xgmml", className="export-btn"),
        dcc.Download(id="export-xgmml"),
        dbc.Button(
            svg.Svg(
                xmlns="http://www.w3.org/2000/svg",
                width="20",
                height="20",
                fill="currentColor",
                className="bi bi-three-dots",
                viewBox="0 0 16 16",
                children=[
                    svg.Path(
                        d="M3 9.5a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3m5 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3m5 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3"
                    ),
                ],
            ),
            # "Settings",
            id="graph-settings-btn",
            className="btn-secondary settings",
        ),
        html.Div(
            [
                html.H4("Settings"),
                graph_layout,
                minimal_degree,
                edge_weight_cutoff,
            ],
            id="graph-settings-collapse",
            className="settings-collapse",
            style=visibility.hidden,
        ),
    ],
    className="settings-container settings-background",
)
