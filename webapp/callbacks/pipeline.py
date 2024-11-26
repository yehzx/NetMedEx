import base64
import pickle
import threading
from queue import Queue

from dash import Input, Output, State, no_update

from netmedex.api_cli import load_pmids, run_query_pipeline
from netmedex.exceptions import EmptyInput, NoArticles, UnsuccessfulRequest
from netmedex.network_cli import pubtator2cytoscape
from netmedex.utils_threading import run_thread_with_error_notification
from webapp.utils import DATA, MAX_ARTICLES, visibility


def callbacks(app):
    @app.long_callback(
        Output("cy-graph-container", "style", allow_duplicate=True),
        Output("memory-graph-cut-weight", "data", allow_duplicate=True),
        Output("is-new-graph", "data"),
        Output("pmid-title-dict", "data"),
        Input("submit-button", "n_clicks"),
        [
            State("api-toggle-items", "value"),
            State("input-type-selection", "value"),
            State("data-input", "value"),
            State("pmid-file-data", "contents"),
            State("pubtator-file-data", "contents"),
            State("cut-weight", "value"),
            State("max-edges", "value"),
            State("pubtator-params", "value"),
            State("cy-params", "value"),
            State("weighting-method", "value"),
            State("node-type", "value"),
        ],
        running=[(Input("submit-button", "disabled"), True, False)],
        progress=[
            Output("progress", "value"),
            Output("progress", "max"),
            Output("progress", "label"),
            Output("progress-status", "children"),
        ],
        prevent_initial_call=True,
    )
    def run_pubtator3_api(
        set_progress,
        btn,
        source,
        input_type,
        data_input,
        pmid_file_data,
        pubtator_file_data,
        weight,
        max_edges,
        pubtator_params,
        cy_params,
        weighting_method,
        node_type,
    ):
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
                args=(
                    query,
                    str(DATA["pubtator"]),
                    input_type,
                    MAX_ARTICLES,
                    full_text,
                    use_mesh,
                    "cite",
                    queue,
                ),
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
            "cut_weight": 0,
            "format": "html",
            "node_type": node_type,
            "weighting_method": weighting_method,
            "max_edges": 0,
            "pmid_weight": None,
            "community": False,
        }

        set_progress((0, 1, "0/1", "Generating network..."))
        G = pubtator2cytoscape(args["input"], args["output"], args)

        # Keeping track of the graph's metadata
        G.graph["is_community"] = True if community else False
        G.graph["max_edges"] = max_edges

        with open(DATA["graph"], "wb") as f:
            pickle.dump(G, f)

        return (visibility.visible, weight, True, G.graph["pmid_title"])