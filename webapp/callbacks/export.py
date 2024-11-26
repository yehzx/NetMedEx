from dash import Input, Output, State, dcc

from netmedex.cytoscape_js import save_as_html
from netmedex.cytoscape_xgmml import save_as_xgmml
from webapp.callbacks.graph_utils import rebuild_graph
from webapp.utils import DATA


def callbacks(app):
    @app.callback(
        Output("download-pubtator", "data"),
        Input("download-pubtator-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def download_pubtator(n_clicks):
        return dcc.send_file(str(DATA["pubtator"]))

    @app.callback(
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

    @app.callback(
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

    @app.callback(
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
