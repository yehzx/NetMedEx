from unittest import mock

import networkx as nx
import pytest

from netmedex.network_cli import (
    HEADER_SYMBOL,
    add_edge_to_graph,
    add_node_to_graph,
    merge_same_name_genes,
    parse_header,
    parse_pubtator,
    remove_isolated_nodes,
)
from netmedex.pubtator_data import PubTatorEdgeData, PubTatorNodeData


@pytest.fixture(scope="module")
def paths():
    return {
        "simple": "./tests/test_data/6_nodes_3_clusters_mesh.pubtator",
        "mesh_collision": "./tests/test_data/mesh_collision.pubtator",
        "merge_genes": "./tests/test_data/merge_genes.pubtator",
    }


def build_graph(result):
    G = nx.Graph()
    add_node_to_graph(G, result["node_dict"], result["non_isolated_nodes"])
    add_edge_to_graph(G, result["node_dict"], result["edge_dict"], None, "freq")
    remove_isolated_nodes(G)

    return G


def test_index_by_text(paths):
    result = parse_pubtator(paths["simple"], node_type="all")
    G = build_graph(result)

    assert G.nodes.get(
        "RS#:854560;HGVS:p.L55M;CorrespondingGene:5444", False
    ), "l55m should be in the graph"
    assert len(G.nodes) == 14, f"result: {len(G.nodes)} nodes\nexpected: 14 nodes"
    assert len(G.edges) == 47, f"result: {len(G.edges)} nodes\nexpected: 47 edges"


def test_index_by_relation(paths):
    result = parse_pubtator(paths["simple"], node_type="relation")
    G = build_graph(result)

    assert G.nodes.get(
        "RS#:854560;HGVS:p.L55M;CorrespondingGene:5444", False
    ), "Not mapped by MeSH"
    assert len(G.nodes) == 8, f"result: {len(G.nodes)} nodes\nexpected: 8 nodes"
    assert len(G.edges) == 9, f"result: {len(G.edges)} nodes\nexpected: 9 edges"


def test_index_by_mesh(paths):
    result = parse_pubtator(paths["simple"], node_type="mesh")
    G = build_graph(result)

    assert G.nodes.get(
        "RS#:854560;HGVS:p.L55M;CorrespondingGene:5444", False
    ), "Not mapped by MeSH"
    assert len(G.nodes) == 13, f"result: {len(G.nodes)} nodes\nexpected: 13 nodes"
    assert len(G.edges) == 41, f"result: {len(G.edges)} nodes\nexpected: 41 edges"


def test_mesh_collision_handling(paths):
    result = parse_pubtator(paths["mesh_collision"], node_type="all")
    G = build_graph(result)

    assert len(G.nodes) == 7, f"result: {len(G.nodes)} nodes\nexpected: 7 nodes"
    assert len(G.edges) == 21, f"result: {len(G.edges)} nodes\nexpected: 21 edges"


def test_merge_genes(paths):
    result = parse_pubtator(paths["merge_genes"], node_type="all")
    G = build_graph(result)

    assert len(G.nodes) == 7, f"result: {len(G.nodes)} nodes\nexpected: 7 nodes"
    assert len(G.edges) == 11, f"result: {len(G.nodes)} nodes\nexpected: 11 edges"


@pytest.mark.parametrize(
    "data,expected",
    [
        (f"{HEADER_SYMBOL}USE-MESH-VOCABULARY\nfoobar", True),
        (f"{HEADER_SYMBOL[0]}USE-MESH-VOCABULARY\nfoobar", False),
        (f"{HEADER_SYMBOL + HEADER_SYMBOL}USE-MESH-VOCABULARY\nfoobar", False),
    ],
)
def test_parse_header(data, expected, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("builtins.open", mock.mock_open(read_data=data))
    flags = {}
    with mock.patch("netmedex.network_cli.flags", flags):
        parse_header("")
        assert flags.get("use_mesh", False) == expected


def test_merge_same_name_genes():
    node_dict = {
        "gene_1": PubTatorNodeData(id=1, mesh="1", type="Gene", name="foo", pmids=set([10])),
        "gene_2": PubTatorNodeData(id=2, mesh="2", type="Gene", name="foo", pmids=set([20])),
        "bar": PubTatorNodeData(id=3, mesh="-", type="Chemical", name="bar", pmids=set([30])),
    }
    edge_dict = {
        ("gene_1", "bar"): [PubTatorEdgeData(id=4, pmid="30"), PubTatorEdgeData(id=5, pmid="40")],
        ("gene_1", "gene_2"): [PubTatorEdgeData(id=6, pmid="20")],
        ("foo", "bar"): [PubTatorEdgeData(id=7, pmid="30"), PubTatorEdgeData(id=8, pmid="40")],
    }
    merge_same_name_genes(node_dict, edge_dict)

    assert node_dict == {
        "bar": PubTatorNodeData(id=3, mesh="-", type="Chemical", name="bar", pmids=set([30])),
        "gene_1;2": PubTatorNodeData(
            id=2, mesh="1;2", type="Gene", name="foo", pmids=set([10, 20])
        ),
    }
    assert edge_dict == {
        ("gene_1;2", "bar"): [
            PubTatorEdgeData(id=4, pmid="30"),
            PubTatorEdgeData(id=5, pmid="40"),
        ],
        ("foo", "bar"): [PubTatorEdgeData(id=7, pmid="30"), PubTatorEdgeData(id=8, pmid="40")],
    }
