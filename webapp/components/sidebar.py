import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.components.advanced_settings import advanced_settings
from webapp.components.utils import generate_param_title
from webapp.utils import display

api_or_file = html.Div(
    [
        html.Div(
            [
                generate_param_title(
                    "Source",
                    [
                        html.P("PubTator3 API: Search + Network Generation"),
                        html.P("PubTator File: Network Generation from PubTator File"),
                    ],
                ),
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
                generate_param_title(
                    "PubTator File",
                    [
                        html.P(
                            "The file downloaded using the 'PubTator File' button after running the 'PubTator3 API'"
                        ),
                    ],
                ),
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
                generate_param_title(
                    "Search Type",
                    [
                        html.P(
                            "Text Search: Query PubTator3 by text (use double quotes to match whole words and AND/OR to combine keywords)"
                        ),
                        html.P("PMID: Query PubTator3 by comma-separated PMIDs"),
                        html.P(
                            "PMID File: Query PubTator3 by a text file of PMIDs (one per line)"
                        ),
                    ],
                ),
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
                generate_param_title(
                    "PubTator3 Parameters",
                    [
                        html.P(
                            "Use MeSH Vocabulary: Replace original text in articles with standardized MeSH terms"
                        ),
                        html.P(
                            "Full Text: Build network from full-text articles if available, defaulting to abstracts otherwise (not recommended to enable)"
                        ),
                    ],
                ),
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
                generate_param_title(
                    "Node Filter",
                    [
                        html.P("All: Retain all annotations"),
                        html.P("MeSH: Retain annotations with standardized MeSH terms only"),
                        html.P(
                            "BioREx Relation: Retain annotations with high-confidence relationships from PubTator3 BioREx model"
                        ),
                    ],
                ),
                dcc.Dropdown(
                    id="node-type",
                    options=[
                        {"label": "All", "value": "all"},
                        {"label": "MeSH", "value": "mesh"},
                        {"label": "BioREx Relation", "value": "relation"},
                    ],
                    value="all",
                    style={"width": "200px"},
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                generate_param_title(
                    "Weighting Method",
                    [
                        html.P("Frequency: Calculate edge weights using co-occurence counts"),
                        html.P(
                            "NPMI: Calulate edge weights using normalized mutual pointwise information"
                        ),
                    ],
                ),
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
                generate_param_title(
                    "Edge Weight Cutoff",
                    [
                        html.P("Set the minimum edge weight to filter the graph"),
                    ],
                ),
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
                generate_param_title(
                    "Network Parameters",
                    [
                        html.P("Community: Group nodes into communities"),
                    ],
                ),
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
    [advanced_settings, api_or_file, api_params, pubtator_file, network_params, progress],
    className="sidebar",
)
