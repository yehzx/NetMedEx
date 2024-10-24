import csv
import importlib
import logging
import math
import pickle
from datetime import datetime
import re
import sys
from argparse import ArgumentParser
from collections import defaultdict
from itertools import count
from operator import itemgetter
from pathlib import Path
from typing import DefaultDict, Literal

import networkx as nx

from pubtoscape.stemmers import s_stemmer
from pubtoscape.utils import config_logger

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


def pubtator2cytoscape(filepath, savepath, args):
    G = nx.Graph()
    result = parse_pubtator(filepath, args["node_type"])
    add_node_to_graph(G=G,
                      node_dict=result["node_dict"],
                      non_isolated_nodes=result["non_isolated_nodes"])
    add_edge_to_graph(G=G,
                      node_dict=result["node_dict"],
                      edge_counter=result["edge_dict"],
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


def set_network_communities(G: nx.Graph, seed=1):
    communities = nx.community.louvain_communities(
        G, seed=seed, weight="scaled_edge_weight")
    community_labels = set()
    for c_idx, community in enumerate(communities):
        highest_degree_node = max(G.degree(community, weight="scaled_edge_weight"), key=itemgetter(1))[0]
        community_node = f"c{c_idx}"
        community_labels.add(community_node)
        community_attrs = G.nodes[highest_degree_node].copy()
        community_attrs.update(
            {"label_color": "#dd4444", "parent": None, "_id": community_node})
        G.add_node(community_node, **community_attrs)

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
        G.add_edge(c_0, c_1,
                   pmids=list(set(inter_edge_pmids[(c_0, c_1)])),
                   scaled_edge_weight=weight,
                   _id=idx)


def save_network(G: nx.Graph,
                 savepath: str,
                 format: Literal["xgmml", "html", "json"] = "html"):
    FORMAT_FUNCTION_MAP = {
        "xgmml": "pubtoscape.cytoscape_xgmml.save_as_xgmml",
        "html": "pubtoscape.cytoscape_js.save_as_html",
        "json": "pubtoscape.cytoscape_js.save_as_json",
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


def parse_pubtator(filepath, node_type):
    def is_title(line):
        return line.find("|t|") != -1

    def parse_title(line):
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
                parse_line_relation(line, node_dict, edge_dict,
                                    non_isolated_nodes)
            else:
                if pmid != last_pmid:
                    create_complete_graph(node_dict_each, edge_dict, last_pmid)
                    last_pmid = pmid
                    node_dict_each = {}
                if get_line_type(line) == "annotation":
                    if node_type == "all":
                        if (mesh := line.strip("\n").rsplit("\t", 1))[-1] in ("-", ""):
                            add_node_by_text(line, node_dict, node_dict_each)
                        else:
                            add_node_by_mesh(line, node_dict, node_dict_each)
                    elif node_type == "mesh":
                        add_node_by_mesh(line, node_dict, node_dict_each)
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


def parse_header(filepath):
    with open(filepath) as f:
        for line in f.readlines():
            if not line.startswith(HEADER_SYMBOL):
                break
            assign_flags(line.replace(HEADER_SYMBOL, "", 1).strip())


def assign_flags(line):
    global flags
    if line == "USE-MESH-VOCABULARY":
        flags["use_mesh"] = True


def parse_line_relation(line, node_dict: dict,
                        edge_dict: DefaultDict[tuple, list],
                        non_isolated_nodes: set):
    line_type = get_line_type(line)
    if line_type == "annotation":
        add_node_by_mesh(line, node_dict, {})
    elif line_type == "relation":
        create_edges_for_relations(line, edge_dict, non_isolated_nodes)


def create_edges_for_relations(line, edge_dict, non_isolated_nodes):
    global mesh_map
    pmid, relationship, name_1, name_2 = line.strip("\n").split("\t")
    # TODO: better way to deal with DNAMutation notation inconsistency
    name_1 = name_1.split("|")[0]
    name_1 = mesh_map.get(name_1, name_1)
    name_2 = name_2.split("|")[0]
    name_2 = mesh_map.get(name_2, name_2)
    edge_dict[(name_1, name_2)].append({
        "pmid": pmid,
        "relationship": relationship,
        "_id": id_counter()
    })
    non_isolated_nodes.add(name_1)
    non_isolated_nodes.add(name_2)


def add_node_by_mesh(line, node_dict, node_dict_each):
    global flags
    global mesh_map

    def convert_mesh(mesh, type):
        converted = f"{type}_{mesh}"
        if mesh not in mesh_map:
            mesh_map[mesh] = converted
        return converted

    pmid, start, end, name, type, mesh = line.strip("\n").split("\t")

    # Skip line with no id
    if mesh in ("", "-"):
        return

    if not flags["use_mesh"]:
        name = normalize_text(name)

    if type in ("DNAMutation", "ProteinMutation", "SNP"):
        res = {}
        for key, pattern in MUTATION_PATTERNS.items():
            try:
                res[key] = f"{re.search(pattern, mesh).group(1)};"
            except AttributeError:
                res[key] = ""

        if type == "DNAMutation":
            mesh = (f'{res["gene"]}{res["species"]}{res["variantgroup"]}'
                    f'{res["tmvar"].split("|")[0]}').strip(";")
        elif type == "ProteinMutation":
            mesh = f'{res["rs"]}{res["hgvs"]}{res["gene"]}'.strip(";")
        elif type == "SNP":
            mesh = f'{res["rs"]}{res["hgvs"]}{res["gene"]}'.strip(";")
        mesh_list = [mesh]
    elif type == "Gene":
        mesh_list = mesh.split(";")
        mesh_list = [convert_mesh(mesh, "gene") for mesh in mesh_list]
    elif type == "Species":
        mesh_list = [convert_mesh(mesh, "species")]
    else:
        mesh_list = [mesh]

    for each_mesh in mesh_list:
        if not _node_id_collision(node_dict, name, type, each_mesh):
            node_dict.setdefault(
                each_mesh, {
                    "mesh": mesh,
                    "type": type,
                    "name": defaultdict(int),
                    "pmids": set(),
                    "_id": id_counter()
                })
        node_dict[each_mesh]["name"][name] += 1
        node_dict[each_mesh]["pmids"].add(pmid)
        node_dict_each[each_mesh] = node_dict[each_mesh]


def _node_id_collision(node_dict, name, type, id):
    is_collision = False
    if id in node_dict and type != node_dict[id]["type"]:
        current_line = {
            "id": id,
            "type": type,
            "name": name,
        }
        logger.debug(f"Found collision of MeSH:\n{node_dict[id]}\n{current_line}")
        logger.debug("Discard the latter\n")
        is_collision = True

    return is_collision


def create_complete_graph(node_dict_each, edge_dict, pmid):
    for i, name_1 in enumerate(node_dict_each.keys()):
        for j, name_2 in enumerate(node_dict_each.keys()):
            if i >= j:
                continue
            if edge_dict.get((name_2, name_1), []):
                edge_dict[(name_2, name_1)].append({
                    "pmid": pmid,
                    "_id": id_counter()
                })
            else:
                edge_dict[(name_1, name_2)].append({
                    "pmid": pmid,
                    "_id": id_counter()
                })


def determine_mesh_term_labels(node_dict, edge_dict):
    def determine_node_label(name):
        return (node_info["name"][name], -len(name))

    for node_id, node_info in node_dict.items():
        if isinstance(node_info["name"], defaultdict):
            # Use the name that appears the most times
            node_dict[node_id]["name"] = max(node_info["name"],
                                             key=determine_node_label)

    merge_same_name_genes(node_dict, edge_dict)


def merge_same_name_genes(node_dict, edge_dict):
    gene_name_dict = defaultdict(list)
    for node_id, node_info in node_dict.items():
        if node_info["type"] != "Gene":
            continue
        gene_name_dict[node_info["name"]].append({
            "node_id": node_id,
            "mesh": node_info["mesh"],
            "pmids": node_info["pmids"],
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
        popped_node_data.update({
            "mesh": concated_mesh,
            "pmids": pmid_collection,
        })
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
        print(merged_edges)
        edge_dict.update(merged_edges)


def add_node_by_text(line, node_dict, node_dict_each):
    pmid, start, end, name, type, mesh = line.strip("\n").split("\t")

    name = normalize_text(name)

    node_info = {
        "mesh": mesh,
        "type": type,
        "name": name,
        "pmids": set(),
        "_id": id_counter()
    }

    if name in node_dict and type != node_dict[name]["type"]:
        logger.debug(f"Found collision of name:\n{node_dict[name]}\n{node_info}")
        logger.debug("Discard the latter\n")

    node_dict.setdefault(name, node_info)
    node_dict[name]["pmids"].add(pmid)
    node_dict_each[name] = node_dict[name]


def normalize_text(text):
    text = text.lower()
    text = s_stemmer(text)

    return text


def get_line_type(line):
    line_split_len = len(line.split("\t"))
    if line_split_len == 4:
        line_type = "relation"
    elif line_split_len == 6:
        line_type = "annotation"
    else:
        line_type = "unknown"

    return line_type


def id_counter(id=count(1)):
    return str(next(id))


def add_node_to_graph(G: nx.Graph, node_dict, non_isolated_nodes):
    # TODO: add feature: mark specific names
    marked = False
    for id in non_isolated_nodes:
        try:
            G.add_node(id,
                       color=NODE_COLOR_MAP[node_dict[id]["type"]],
                       label_color="#000000",
                       shape=NODE_SHAPE_MAP[node_dict[id]["type"]],
                       type=node_dict[id]["type"],
                       name=node_dict[id]["name"],
                       document_frquency=len(node_dict[id]["pmids"]),
                       _id=node_dict[id]["_id"],
                       marked=marked)
        except KeyError:
            logger.debug(f"Skip node: {id}")


def add_edge_to_graph(G: nx.Graph,
                      node_dict,
                      edge_counter,
                      doc_weight_csv=None,
                      weighting_method=["freq", "npmi"][0]):
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

    for pair, records in edge_counter.items():
        if not G.has_node(pair[0]) or not G.has_node(pair[1]):
            continue

        pmids = [str(record["pmid"]) for record in records]
        unique_pmids = set(pmids)

        w_freq = round(sum([doc_weights.get(pmid, 1)
                       for pmid in unique_pmids]), 2)
        npmi = normalized_pointwise_mutual_information(
            n_x=len(node_dict[pair[0]]["pmids"]),
            n_y=len(node_dict[pair[1]]["pmids"]),
            n_xy=len(unique_pmids),
            N=pmid_counter,
            n_threshold=2,
            below_threshold_default=MIN_EDGE_WIDTH / max_width,
        )

        if weighting_method == "npmi":
            edge_weight = npmi
        elif weighting_method == "freq":
            edge_weight = w_freq

        try:
            G.add_edge(pair[0],
                       pair[1],
                       _id=records[0]["_id"],
                       raw_frequency=len(unique_pmids),
                       weighted_frequency=w_freq,
                       npmi=npmi,
                       edge_weight=edge_weight,
                       pmids={p: pmid_title_dict[p] for p in list(unique_pmids)})
        except Exception:
            logger.debug(f"Skip edge: ({pair[0]}, {pair[1]})")

    edge_weights = nx.get_edge_attributes(G, "edge_weight")
    scale_factor = calculate_scale_factor(edge_weights,
                                          max_width=max_width,
                                          weighting_method=weighting_method)
    for edge, weight in edge_weights.items():
        G.edges[edge]["scaled_edge_weight"] = max(
            int(round(weight * scale_factor, 0)), min_width)


def calculate_scale_factor(edge_weights, max_width, weighting_method):
    max_weight = max(edge_weights.values())
    if weighting_method == "npmi":
        scale_factor = max_width
    elif weighting_method == "freq":
        scale_factor = min(max_width / max_weight, 1)

    return scale_factor


def remove_edges_by_weight(G: nx.Graph, cut_weight):
    scaled_weights = nx.get_edge_attributes(G, "scaled_edge_weight")
    for edge, scaled_weight in scaled_weights.items():
        if scaled_weight < cut_weight:
            G.remove_edge(edge[0], edge[1])


def remove_isolated_nodes(G: nx.Graph):
    G.remove_nodes_from(list(nx.isolates(G)))


def spring_layout(G: nx.Graph):
    pos = nx.spring_layout(G,
                           weight="scaled_edge_weight",
                           scale=300,
                           k=0.25,
                           iterations=15)
    nx.set_node_attributes(G, pos, "pos")


def normalized_pointwise_mutual_information(n_x, n_y, n_xy, N,
                                            n_threshold,
                                            below_threshold_default):
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
