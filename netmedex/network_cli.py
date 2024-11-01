import csv
import importlib
import logging
import math
import pickle
import re
import sys
import uuid
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from operator import itemgetter
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Union

import networkx as nx

from netmedex.graph_data import CommunityEdgeData, GraphEdgeData, GraphNodeData
from netmedex.pubtator_data import (PubTatorEdgeData, PubTatorLine,
                                    PubTatorNodeData)
from netmedex.utils import config_logger

# VARIANT_PATTERN = re.compile(r"CorrespondingGene:.*CorrespondingSpecies:\d+")
HEADER_SYMBOL = "##"
MUTATION_PATTERNS = {
    "tmvar": re.compile(r"(tmVar:[^;]+)"),
    "hgvs": re.compile(r"(HGVS:[^;]+)"),
    "rs": re.compile(r"(RS#:[^;]+)"),
    "variantgroup": re.compile(r"(VariantGroup:[^;]+)"),
    "gene": re.compile(r"(CorrespondingGene:[^;]+)"),
    "species": re.compile(r"(CorrespondingSpecies:[^;]+)"),
    "ca": re.compile(r"(CA#:[^;]+)")
}

NODE_COLOR_MAP = {
    "Chemical": "#67A9CF",
    "Gene": "#74C476",
    "Species": "#FD8D3C",
    "Disease": "#8C96C6",
    "DNAMutation": "#FCCDE5",
    "ProteinMutation": "#FA9FB5",
    "CellLine": "#BDBDBD",
    "SNP": "#FFFFB3"
}
NODE_SHAPE_MAP = {
    "Chemical": "ELLIPSE",
    "Gene": "TRIANGLE",
    "Species": "DIAMOND",
    "Disease": "ROUNDRECTANGLE",
    "DNAMutation": "PARALLELOGRAM",
    "ProteinMutation": "HEXAGON",
    "CellLine": "VEE",
    "SNP": "OCTAGON"
}

MIN_EDGE_WIDTH = 1
MAX_EDGE_WIDTH = 20
EDGE_BASE_COLOR = "#AD1A66"

pmid_counter = 0
pmid_title_dict = {}
flags = {"use_mesh": False}
# TODO: other ways to solve modified MeSH mismatch
mesh_map = {}
logger = logging.getLogger(__name__)


def main():
    args = parse_args(sys.argv[1:])

    log_file = "tocytoscape" if args.debug else None

    config_logger(args.debug, log_file)

    check_not_implemented(args)

    input_filepath = Path(args.input)
    if args.output is None:
        output_filepath = input_filepath.with_suffix(f".{args.format}")
    else:
        output_filepath = Path(args.output)
        output_filepath.parent.mkdir(parents=True, exist_ok=True)

    pubtator2cytoscape(input_filepath, output_filepath, vars(args))


def check_not_implemented(args):
    if args.community and args.format == "xgmml":
        logger.info("Save community in XGMML format not yet supported.")
        sys.exit()


def pubtator2cytoscape(
    filepath: Union[str, Path],
    savepath: Union[str, Path, None],
    args: Mapping[str, Any],
) -> nx.Graph:
    G = nx.Graph()
    result = parse_pubtator(filepath, args["node_type"])
    add_node_to_graph(G=G,
                      node_dict=result["node_dict"],
                      non_isolated_nodes=result["non_isolated_nodes"])
    add_edge_to_graph(G=G,
                      node_dict=result["node_dict"],
                      edge_dict=result["edge_dict"],
                      doc_weight_csv=args["pmid_weight"],
                      weighting_method=args["weighting_method"])
    add_attrs_to_graph(G=G)

    if args.get("debug", False):
        # Save before truncation
        now = datetime.now().strftime("%y%m%d%H%M%S")
        with open(f"tocytoscape_graph_{now}.pkl", "wb") as f:
            pickle.dump(G, f)

    remove_edges_by_weight(G, args["cut_weight"])
    remove_isolated_nodes(G)

    assert_graph_properties(G)

    set_network_layout(G)

    if args["community"]:
        set_network_communities(G)

    if savepath is not None:
        save_network(G, savepath, args["format"])

    return G


def assert_graph_properties(G: nx.Graph):
    num_selfloops = nx.number_of_selfloops(G)
    assert num_selfloops == 0, f"Find {num_selfloops}"


def set_network_layout(G: nx.Graph):
    pos = nx.spring_layout(G,
                           weight="scaled_edge_weight",
                           scale=300,
                           k=0.25,
                           iterations=15)
    nx.set_node_attributes(G, pos, "pos")


def set_network_communities(G: nx.Graph, seed: int = 1):
    communities = nx.community.louvain_communities(
        G, seed=seed, weight="scaled_edge_weight")
    community_labels = set()
    for c_idx, community in enumerate(communities):
        highest_degree_node = max(
            G.degree(community, weight="scaled_edge_weight"),
            key=itemgetter(1))[0]
        community_node = f"c{c_idx}"
        community_labels.add(community_node)
        community_attrs = G.nodes[highest_degree_node].copy()
        community_attrs.update(
            {"label_color": "#dd4444", "parent": None, "_id": community_node})
        node_data = GraphNodeData(**community_attrs)
        G.add_node(community_node, **asdict(node_data))

        for node in community:
            G.nodes[node]["parent"] = community_node

    G.graph["num_communities"] = len(community_labels)

    # Gather edges between communities
    inter_edge_weight = defaultdict(int)
    inter_edge_pmids = defaultdict(list)
    to_remove = []
    for u, v, attrs in G.edges(data=True):
        if (c_0 := G.nodes[u]["parent"]) != (c_1 := G.nodes[v]["parent"]):
            assert c_0 is not None and c_1 is not None
            to_remove.append((u, v))
            community_edge = tuple(sorted([c_0, c_1]))
            inter_edge_weight[community_edge] += attrs["scaled_edge_weight"]
            inter_edge_pmids[community_edge].extend(attrs["pmids"])

    G.remove_edges_from(to_remove)
    for idx, ((c_0, c_1), weight) in enumerate(inter_edge_weight.items()):
        # Log-adjusted weight for balance
        weight = math.log(weight) * 5
        pmids = list(set(inter_edge_pmids[(c_0, c_1)]))
        edge_data = CommunityEdgeData(
            _id=create_id(),
            edge_weight=weight,
            scaled_edge_weight=weight,
            pmids=pmids,
        )
        G.add_edge(c_0, c_1, type="community", **asdict(edge_data))


def save_network(G: nx.Graph,
                 savepath: Union[str, Path],
                 format: Literal["xgmml", "html", "json"] = "html"):
    FORMAT_FUNCTION_MAP = {
        "xgmml": "netmedex.cytoscape_xgmml.save_as_xgmml",
        "html": "netmedex.cytoscape_js.save_as_html",
        "json": "netmedex.cytoscape_js.save_as_json",
    }

    module_path, func_name = FORMAT_FUNCTION_MAP[format].rsplit(".", 1)
    module = importlib.import_module(module_path)
    save_func = getattr(module, func_name)

    save_func(G, savepath)

    global pmid_counter
    logger.info(f"# articles: {pmid_counter}")
    if num_communities := G.graph.get("num_communities", 0):
        logger.info(f"# communities: {num_communities}")
    logger.info(f"# nodes: {G.number_of_nodes() - num_communities}")
    logger.info(f"# edges: {G.number_of_edges()}")
    logger.info(f"Save graph to {savepath}")


def parse_pubtator(filepath: Union[str, Path],
                   node_type: Literal["all", "mesh", "relation"]):
    def is_title(line: str):
        return line.find("|t|") != -1

    def parse_title(line: str):
        global pmid_title_dict
        pmid, title = line.split("|t|")
        pmid_title_dict.setdefault(pmid, title)
        return pmid

    global pmid_counter
    node_dict = {}
    edge_dict = defaultdict(list)
    non_isolated_nodes = set()
    pmid = -1
    last_pmid = -1
    node_dict_each = {}

    parse_header(filepath)
    with open(filepath) as f:
        for line in f.readlines():
            if is_title(line):
                pmid = parse_title(line)
                pmid_counter += 1
                continue
            if node_type == "relation":
                parsed_line = PubTatorLine(line)
                parse_line_relation(parsed_line, node_dict, edge_dict,
                                    non_isolated_nodes)
            else:
                if pmid != last_pmid:
                    create_complete_graph(node_dict_each, edge_dict, last_pmid)
                    last_pmid = pmid
                    node_dict_each = {}
                parsed_line = PubTatorLine(line)
                if parsed_line.type == "annotation":
                    args = (parsed_line, node_dict, node_dict_each)
                    if node_type == "all":
                        add_node(*args, mesh_only=False)
                    elif node_type == "mesh":
                        add_node(*args, mesh_only=True)
        create_complete_graph(node_dict_each, edge_dict, pmid)
    determine_mesh_term_labels(node_dict, edge_dict)
    if node_type in ("all", "mesh"):
        non_isolated_nodes = set(node_dict.keys())
    elif node_type == "relation":
        non_isolated_nodes = set()
        for node_1, node_2 in edge_dict:
            non_isolated_nodes.add(node_1)
            non_isolated_nodes.add(node_2)

    return {
        "node_dict": node_dict,
        "non_isolated_nodes": non_isolated_nodes,
        "edge_dict": edge_dict
    }


def parse_header(filepath: Union[str, Path]):
    with open(filepath) as f:
        for line in f.readlines():
            if not line.startswith(HEADER_SYMBOL):
                break
            assign_flags(line.replace(HEADER_SYMBOL, "", 1).strip())


def assign_flags(line: str):
    global flags
    if line == "USE-MESH-VOCABULARY":
        flags["use_mesh"] = True
        PubTatorLine.use_mesh = True


def parse_line_relation(line: PubTatorLine,
                        node_dict: dict[str, PubTatorNodeData],
                        edge_dict: defaultdict[str, list[PubTatorEdgeData]],
                        non_isolated_nodes: set[str]):
    if line.type == "annotation":
        add_node(line, node_dict, {}, mesh_only=True)
    elif line.type == "relation":
        create_edges_for_relations(line, edge_dict, non_isolated_nodes)


def create_edges_for_relations(line: PubTatorLine,
                               edge_dict: defaultdict[str, list[PubTatorEdgeData]],
                               non_isolated_nodes: set[str]):
    global mesh_map
    data = line.data
    # TODO: better way to deal with DNAMutation notation inconsistency
    mesh_1 = data.mesh1.split("|")[0]
    mesh_1 = mesh_map.get(mesh_1, mesh_1)
    mesh_2 = data.mesh2.split("|")[0]
    mesh_2 = mesh_map.get(mesh_2, mesh_2)
    edge_dict[(mesh_1, mesh_2)].append(
        PubTatorEdgeData(id=create_id(),
                         pmid=data.pmid,
                         relation=data.relation)
    )
    non_isolated_nodes.add(mesh_1)
    non_isolated_nodes.add(mesh_2)


def _node_id_registered(node_dict: dict[str, PubTatorNodeData],
                        line: PubTatorLine,
                        node_id: str):
    is_registered = False
    data = line.data
    if node_id in node_dict:
        is_registered = True
        if data.type != node_dict[node_id].type:
            info = {
                "id": node_id,
                "type": data.type,
                "name": data.name,
            }
            logger.debug(f"Found collision of MeSH:\n{node_dict[node_id]}\n{info}")
            logger.debug("Discard the latter\n")

    return is_registered


def create_complete_graph(node_dict_each: dict[str, PubTatorNodeData],
                          edge_dict: defaultdict[str, list[PubTatorEdgeData]],
                          pmid: str):
    for i, name_1 in enumerate(node_dict_each.keys()):
        for j, name_2 in enumerate(node_dict_each.keys()):
            if i >= j:
                continue
            if edge_dict.get((name_2, name_1), []):
                key = (name_2, name_1)
            else:
                key = (name_1, name_2)
            edge_dict[key].append(
                PubTatorEdgeData(id=create_id(), pmid=pmid)
            )


def determine_mesh_term_labels(node_dict: dict[str, PubTatorNodeData],
                               edge_dict: defaultdict[str, list[PubTatorEdgeData]]):
    def determine_node_label(candidate_name: str):
        nonlocal node_data
        return (node_data.name[candidate_name], -len(candidate_name))

    for node_id, node_data in node_dict.items():
        if isinstance(node_data.name, defaultdict):
            # Use the name that appears the most times
            node_dict[node_id].name = max(node_data.name,
                                          key=determine_node_label)

    merge_same_name_genes(node_dict, edge_dict)


def merge_same_name_genes(node_dict: dict[str, PubTatorNodeData],
                          edge_dict: defaultdict[str, list[PubTatorEdgeData]]):
    gene_name_dict = defaultdict(list)
    for node_id, node_data in node_dict.items():
        if node_data.type != "Gene" or node_data.mesh == "-":
            continue
        gene_name_dict[node_data.name].append({
            "node_id": node_id,
            "mesh": node_data.mesh,
            "pmids": node_data.pmids,
        })

    for node_data_list in gene_name_dict.values():
        mesh_list = []
        edges_to_merge = []
        removed_node_ids = []
        pmid_collection = set()
        for node_data in node_data_list:
            node_id = node_data["node_id"]
            # Nodes
            popped_node_data = node_dict.pop(node_id)
            removed_node_ids.append(node_id)
            mesh_list.append(node_data["mesh"])
            for pmid in node_data["pmids"]:
                pmid_collection.add(pmid)

            # Edges
            for u, v in edge_dict.keys():
                if u == node_id:
                    edges_to_merge.append((u, v, "u"))
                elif v == node_id:
                    edges_to_merge.append((u, v, "v"))

        # Nodes
        concated_mesh = ";".join(mesh_list)
        # popped_node_data is the last node_data of nodes having the same name
        popped_node_data.mesh = concated_mesh
        popped_node_data.pmids = pmid_collection
        node_key = f"gene_{concated_mesh}"
        node_dict[node_key] = popped_node_data

        # Edges
        merged_edges = defaultdict(list)
        for u, v, pos in edges_to_merge:
            neighbor = v if pos == "u" else u
            try:
                popped_edge_data = edge_dict.pop((u, v))
            except KeyError:
                # The same gene but given different ids in the same article
                assert neighbor in removed_node_ids
            if neighbor in removed_node_ids:
                continue
            merged_edges[(node_key, neighbor)].extend(popped_edge_data)
        edge_dict.update(merged_edges)


def add_node(line: PubTatorLine,
             node_dict: dict[str, PubTatorNodeData],
             node_dict_each: dict[str, PubTatorNodeData],
             mesh_only: bool):
    data = line.data
    if data.mesh in ("-", ""):
        if mesh_only:
            return
        # By Text
        line.normalize_name()

        name = data.name
        if not _node_id_registered(node_dict, line, name):
            node_dict[name] = PubTatorNodeData(id=create_id(),
                                               mesh=data.mesh,
                                               type=data.type,
                                               name=name,
                                               pmids=set())
        node_dict_each.setdefault(name, node_dict[data.name])
        node_dict[name].pmids.add(data.pmid)
    else:
        # By MeSH
        global mesh_map
        mesh_list = line.parse_mesh(mesh_map)

        for mesh in mesh_list:
            node_id = mesh["key"]
            if not _node_id_registered(node_dict, line, node_id):
                node_dict[node_id] = PubTatorNodeData(
                    id=create_id(),
                    mesh=mesh["mesh"],
                    type=data.type,
                    name=defaultdict(int),
                    pmids=set()
                )
            node_dict_each.setdefault(node_id, node_dict[node_id])
            node_dict[node_id].name[data.name] += 1
            node_dict[node_id].pmids.add(data.pmid)


def create_id():
    return str(uuid.uuid4())


def add_node_to_graph(G: nx.Graph,
                      node_dict: dict[str, PubTatorNodeData],
                      non_isolated_nodes: set[str]):
    # TODO: add feature: mark specific names
    marked = False
    for node_id in non_isolated_nodes:
        node_data = GraphNodeData(
            _id=str(node_dict[node_id].id),
            color=NODE_COLOR_MAP[node_dict[node_id].type],
            label_color="#000000",
            shape=NODE_SHAPE_MAP[node_dict[node_id].type],
            type=node_dict[node_id].type,
            name=node_dict[node_id].name,
            document_frequency=len(node_dict[node_id].pmids),
            marked=marked
        )
        G.add_node(node_id, **asdict(node_data))


def add_edge_to_graph(G: nx.Graph,
                      node_dict: dict[str, PubTatorNodeData],
                      edge_dict: defaultdict[str, list[PubTatorEdgeData]],
                      doc_weight_csv: Union[str, Path, None],
                      weighting_method: Literal["freq", "npmi"] = "freq"):
    global pmid_counter
    doc_weights = {}
    if doc_weight_csv is not None:
        with open(doc_weight_csv, newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                doc_weights[row[0]] = float(row[1])

    max_width = MAX_EDGE_WIDTH
    # Change min_width to 0 in npmi
    min_width = MIN_EDGE_WIDTH if weighting_method == "freq" else 0

    for pair, edge_data_list in edge_dict.items():
        if not G.has_node(pair[0]) or not G.has_node(pair[1]):
            continue

        pmids = [edge_data.pmid for edge_data in edge_data_list]
        unique_pmids = set(pmids)

        w_freq = round(sum([doc_weights.get(pmid, 1)
                       for pmid in unique_pmids]), 2)
        npmi = normalized_pointwise_mutual_information(
            n_x=len(node_dict[pair[0]].pmids),
            n_y=len(node_dict[pair[1]].pmids),
            n_xy=len(unique_pmids),
            N=pmid_counter,
            n_threshold=2,
            below_threshold_default=MIN_EDGE_WIDTH / max_width,
        )

        if weighting_method == "npmi":
            edge_weight = npmi
        elif weighting_method == "freq":
            edge_weight = w_freq

        edge_data = GraphEdgeData(
            _id=str(edge_data_list[0].id),
            raw_frequency=len(unique_pmids),
            weighted_frequency=w_freq,
            npmi=npmi,
            edge_weight=edge_weight,
            pmids=list(unique_pmids),
        )

        G.add_edge(pair[0], pair[1], type="node", **asdict(edge_data))

    edge_weights = nx.get_edge_attributes(G, "edge_weight")
    scale_factor = calculate_scale_factor(edge_weights.values(),
                                          max_width=max_width,
                                          weighting_method=weighting_method)
    for edge, weight in edge_weights.items():
        G.edges[edge]["scaled_edge_weight"] = max(
            int(round(weight * scale_factor, 0)), min_width)


def calculate_scale_factor(edge_weights: Iterable[float],
                           max_width: int,
                           weighting_method: Literal["npmi", "freq"]):
    max_weight = max(edge_weights)
    if weighting_method == "npmi":
        scale_factor = max_width
    elif weighting_method == "freq":
        scale_factor = min(max_width / max_weight, 1)

    return scale_factor


def remove_edges_by_weight(G: nx.Graph, cut_weight: int):
    to_remove = []
    for u, v, edge_attrs in G.edges(data=True):
        if edge_attrs["scaled_edge_weight"] < cut_weight:
            to_remove.append((u, v))
    G.remove_edges_from(to_remove)


def remove_isolated_nodes(G: nx.Graph):
    G.remove_nodes_from(list(nx.isolates(G)))


def spring_layout(G: nx.Graph):
    pos = nx.spring_layout(G,
                           weight="scaled_edge_weight",
                           scale=300,
                           k=0.25,
                           iterations=15)
    nx.set_node_attributes(G, pos, "pos")


def normalized_pointwise_mutual_information(n_x: float,
                                            n_y: float,
                                            n_xy: float,
                                            N: int,
                                            n_threshold: int,
                                            below_threshold_default: float):
    if n_xy == 0:
        npmi = -1
    elif (n_xy / N) == 1:
        npmi = 1
    else:
        npmi = -1 + (math.log2(n_x / N) + math.log2(n_y / N)) / math.log2(n_xy / N)

    # non-normalized
    # pmi = math.log2(p_x) + math.log2(p_y) - math.log2(p_xy)

    if n_x < n_threshold or n_y < n_threshold:
        npmi = min(npmi, below_threshold_default)

    return npmi


def add_attrs_to_graph(G: nx.Graph):
    G.graph["pmid_title"] = pmid_title_dict


def parse_args(args):
    parser = setup_argparsers()
    return parser.parse_args(args)


def setup_argparsers():
    parser = ArgumentParser()
    parser.add_argument("-i",
                        "--input",
                        type=str,
                        help="Path to the pubtator file")
    parser.add_argument("-o",
                        "--output",
                        default=None,
                        help="Output path (default: [INPUT FILEPATH].xgmml)")
    parser.add_argument("-w",
                        "--cut_weight",
                        type=int,
                        default=5,
                        help="Discard the edges with weight smaller than the specified value (default: 5)")
    parser.add_argument("-f",
                        "--format", choices=["xgmml", "html", "json"],
                        default="html",
                        help="Output format (default: html)")
    parser.add_argument("--node_type",
                        choices=["all", "mesh", "relation"],
                        default="all",
                        help="Keep specific types of nodes (default: all)")
    parser.add_argument("--weighting_method",
                        choices=["freq", "npmi"],
                        default="freq",
                        help="Weighting method for network edge (default: freq)")
    parser.add_argument("--pmid_weight",
                        default=None,
                        help="CSV file for the weight of the edge from a PMID (default: 1)")
    parser.add_argument("--debug",
                        action="store_true",
                        help="Print debug information")
    parser.add_argument("--community",
                        action="store_true",
                        help="Divide nodes into distinct communities by the Louvain method")

    return parser


if __name__ == "__main__":
    main()
