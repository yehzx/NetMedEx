import networkx as nx
import pytest
from unittest import mock
from pubtoscape.pubtator3_to_cytoscape_cli import (add_edge_to_graph,
                                                   add_node_to_graph,
                                                   parse_pubtator,
                                                   parse_header,
                                                   remove_isolated_nodes,
                                                   merge_same_name_genes,
                                                   HEADER_SYMBOL)


@pytest.fixture(scope="module")
def paths():
    return {"simple": "./tests/test_data/6_nodes_3_clusters_mesh.pubtator"}


def build_graph(result):
    G = nx.Graph()
    add_node_to_graph(G, result["node_dict"], result["non_isolated_nodes"])
    add_edge_to_graph(G, result["node_dict"], result["edge_dict"], None, "freq")
    remove_isolated_nodes(G)

    return G


def test_index_by_text(paths):
    result = parse_pubtator(paths["simple"], node_type="all")
    G = build_graph(result)

    assert G.nodes.get("RS#:854560;HGVS:p.L55M;CorrespondingGene:5444", False), "l55m should be in the graph"
    assert len(G.nodes) == 14, f"result: {len(G.nodes)} nodes\nexpected: 14 nodes"
    assert len(G.edges) == 47, f"result: {len(G.edges)} nodes\nexpected: 47 edges"


def test_index_by_relation(paths):
    result = parse_pubtator(paths["simple"], node_type="relation")
    G = build_graph(result)

    assert G.nodes.get("RS#:854560;HGVS:p.L55M;CorrespondingGene:5444", False), "Not mapped by MeSH"
    assert len(G.nodes) == 8, f"result: {len(G.nodes)} nodes\nexpected: 8 nodes"
    assert len(G.edges) == 9, f"result: {len(G.edges)} nodes\nexpected: 9 edges"


def test_index_by_mesh(paths):
    result = parse_pubtator(paths["simple"], node_type="mesh")
    G = build_graph(result)

    assert G.nodes.get("RS#:854560;HGVS:p.L55M;CorrespondingGene:5444", False), "Not mapped by MeSH"
    assert len(G.nodes) == 13, f"result: {len(G.nodes)} nodes\nexpected: 13 nodes"
    assert len(G.edges) == 41, f"result: {len(G.edges)} nodes\nexpected: 41 edges"


@pytest.mark.parametrize("data,expected", [
    (f"{HEADER_SYMBOL}USE-MESH-VOCABULARY\nfoobar", True),
    (f"{HEADER_SYMBOL[0]}USE-MESH-VOCABULARY\nfoobar", False),
    (f"{HEADER_SYMBOL + HEADER_SYMBOL}USE-MESH-VOCABULARY\nfoobar", False),
])
def test_parse_header(data, expected, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("builtins.open", mock.mock_open(read_data=data))
    flags = {}
    with mock.patch("pubtoscape.pubtator3_to_cytoscape_cli.flags", flags):
        parse_header("")
        assert flags.get("use_mesh", False) == expected


def test_merge_same_name_genes():
    node_dict = {
        "gene_1": {"type": "Gene", "pmids": set([10]), "mesh": "1", "name": "foo"},
        "gene_2": {"type": "Gene", "pmids": set([20]), "mesh": "2", "name": "foo"},
        "bar": {"type": "-", "pmids": set([30]), "mesh": "-", "name": "bar"},
    }
    edge_dict = {
        ("gene_1", "bar"): [{"pmid": 30}, {"pmid": 40}],
        ("gene_1", "gene_2"): [{"pmid": 20}],
        ("foo", "bar"): [{"pmid": 30}, {"pmid": 40}],
    }
    merge_same_name_genes(node_dict, edge_dict)

    assert node_dict == {
        'bar': {'type': '-', 'pmids': {30}, 'mesh': '-', 'name': 'bar'},
        'gene_1;2': {'type': 'Gene', 'pmids': {10, 20}, 'mesh': '1;2', 'name': 'foo'}
    }
    assert edge_dict == {
        ('foo', 'bar'): [{'pmid': 30}, {'pmid': 40}],
        ('gene_1;2', 'bar'): [{'pmid': 30}, {'pmid': 40}]
    }