import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.utils import display

api_or_file = html.Div(
    [
        html.Div(
            [
                html.H5("Source"),
                dbc.RadioItems(
                    id="api-toggle-items",
                    options=[
                        {"label": "PubTator3 API", "value": "api"},
                        {"label": "PubTator File", "value": "file"},
                    ],
                    value="api",
                    inline=True,
                ),
            ],
            className="param",
        )
    ],
    id="api-toggle",
)

pubtator_file = html.Div(
    [
        html.Div(
            [
                html.H5("PubTator File"),
                dcc.Upload(
                    id="pubtator-file-data",
                    children=html.Div(
                        ["Drag and Drop or ", html.A("Select Files", className="hyperlink")],
                        className="upload-box form-control",
                    ),
                ),
                html.Div(id="pubtator-file-upload"),
            ],
            className="param",
        )
    ],
    style=display.none,
    id="pubtator-file-wrapper",
)

api_params = html.Div(
    [
        html.Div(
            [
                html.H5("Search Type"),
                dcc.Dropdown(
                    id="input-type-selection",
                    options=[
                        {"label": "Text Search", "value": "query"},
                        {"label": "PMID", "value": "pmids"},
                        {"label": "PMID File", "value": "pmid_file"},
                    ],
                    value="query",
                    style={"width": "200px"},
                ),
            ],
            className="param",
        ),
        html.Div(id="input-type", className="param"),
        html.Div(
            [
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
            ],
            className="param",
        ),
    ],
    id="api-wrapper",
)


network_params = html.Div(
    [
        html.Div(
            [
                html.H5("Node Type"),
                dcc.Dropdown(
                    id="node-type",
                    options=[
                        {"label": "Normalized Text", "value": "all"},
                        {"label": "Has MeSH", "value": "mesh"},
                        {"label": "BioREx Relation Only", "value": "relation"},
                    ],
                    value="all",
                    style={"width": "200px"},
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                html.H5("Weighting Method"),
                dcc.Dropdown(
                    id="weighting-method",
                    options=[
                        {"label": "Frequency", "value": "freq"},
                        {"label": "NPMI", "value": "npmi"},
                    ],
                    value="freq",
                    style={"width": "200px"},
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                html.H5("Edge Weight Cutoff"),
                dcc.Slider(
                    0,
                    20,
                    1,
                    value=3,
                    marks=None,
                    id="cut-weight",
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                html.H5("Max Edges"),
                dcc.Slider(
                    0,
                    500,
                    10,
                    value=0,
                    marks=None,
                    id="max-edges",
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                html.H5("Network Parameters"),
                dbc.Checklist(
                    options=[
                        {"label": "Community", "value": "community"},
                    ],
                    switch=True,
                    id="cy-params",
                    value=[],
                ),
            ],
            className="param",
        ),
    ],
    id="cy-wrapper",
)


progress = html.Div(
    [
        html.Div(
            [html.H5("Progress"), html.P(" ", id="progress-status"), dbc.Progress(id="progress")],
            className="param",
        ),
        html.Div([dbc.Button("Submit", id="submit-button"), html.Div(id="output")]),
    ],
    id="progress-wrapper",
)


sidebar = html.Div(
    [api_or_file, api_params, pubtator_file, network_params, progress], className="sidebar"
)
