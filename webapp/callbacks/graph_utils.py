import pickle
from typing import Literal

import networkx as nx

from netmedex.network_cli import (
    remove_edges_by_rank,
    remove_edges_by_weight,
    remove_isolated_nodes,
    set_network_communities,
    set_network_layout,
)


def filter_node(G: nx.Graph, node_degree_threshold: int):
    for node, degree in list(G.degree()):
        if degree < node_degree_threshold:
            G.remove_node(node)


def rebuild_graph(
    node_degree,
    cut_weight,
    format: Literal["xgmml", "html"],
    G=None,
    with_layout=False,
    graph_path=None,
):
    if G is None:
        with open(graph_path, "rb") as f:
            G = pickle.load(f)

    remove_edges_by_weight(G, cut_weight)
    remove_edges_by_rank(G, G.graph.get("max_edges", 0))
    remove_isolated_nodes(G)
    filter_node(G, node_degree)

    if with_layout:
        set_network_layout(G)

    if G.graph.get("is_community", False) and format == "html":
        set_network_communities(G)

    return G
