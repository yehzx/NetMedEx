import networkx as nx
from collections import OrderedDict, defaultdict
from typing import DefaultDict, List
from itertools import count
import re
from lxml.etree import QName
from lxml.builder import ElementMaker, E
from lxml import etree


XML_NAMESPACE = {
    "cy": "http://www.cytoscape.org",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xlink": "http://www.w3.org/1999/xlink",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
}
for prefix, uri in XML_NAMESPACE.items():
    etree.register_namespace(prefix, uri)


VARIANT_PATTERN = re.compile(r"CorrespondingGene:.*CorrespondingSpecies:\d+")
HGVS_PATTERN = re.compile(r"(HGVS:.*?);")
# PARSE_LINE_TYPE = ["annotation", "relation"][1]
TYPE_ATTR = {"string": {"type": "string", QName(XML_NAMESPACE["cy"], "type"): "String"},
             "boolean": {"type": "boolean", QName(XML_NAMESPACE["cy"], "type"): "Boolean"},
             "integer": {"type": "integer", QName(XML_NAMESPACE["cy"], "type"): "Integer"},
             }
COLOR_MAP = {"Chemical": "#67A9CF",
             "Gene": "#74C476",
             "Species": "#FD8D3C",
             "Disease": "#8C96C6",
             "DNAMutation": "#FCCDE5",
             "ProteinMutation": "#FA9FB5",
             "CellLine": "#BDBDBD",
             "SNP": "#FFFFB3"}
SHAPE_MAP = {"Chemical": "ELLIPSE",
             "Gene": "TRIANGLE",
             "Species": "DIAMOND",
             "Disease": "ROUND_RECTANGLE",
             "DNAMutation": "PARALLELOGRAM",
             "ProteinMutation": "HEXAGON",
             "CellLine": "VEE",
             "SNP": "OCTAGON"}


def pubtator2cytoscape(filepath, savepath):
    G = nx.Graph()
    result = parse_pubtator(filepath)
    add_node_to_graph(G, result["node_dict"], result["node_in_relation"])
    add_edge_to_graph(G, result["edge_dict"])

    # pos = nx.spring_layout(G)
    save_xgmml(G, savepath) 


def save_xgmml(G: nx.Graph, savepath):
    with open(savepath, "wb") as f:
        graph = create_graph_xml(G)
        f.write(etree.tostring(graph, encoding="utf-8",
                xml_declaration=True, standalone="yes", pretty_print=True))


def parse_pubtator(filepath):
    node_dict = {}
    edge_dict = defaultdict(list)
    node_in_relation = set()
    with open(filepath) as f:
        for line in f.readlines():
            if is_title(line):
                continue
            parse_line(line, node_dict, edge_dict, node_in_relation)
    
    return {"node_dict": node_dict,
            "node_in_relation": node_in_relation,
            "edge_dict": edge_dict}


def is_title(line):
    return line.find("|t|") != -1


def parse_line(line, node_dict: dict, edge_dict: DefaultDict[tuple, list], node_in_relation: set):
    line_type = determine_line_type(line)
    if line_type == "annotation":
        pmid, start, end, name, type, id = line.strip("\n").split("\t")

        # FIXME: PubTator Association has strange ids for SNP and ProteinMutation
        if type in ("SNP", "ProteinMutation"):
            # [..., CorrespondingGene, Name, CorrespondingSpecies]
            string = re.search(VARIANT_PATTERN, id).group(0)
            string = string.split(";")

            if type == "ProteinMutation":
                hgvs = re.search(HGVS_PATTERN, id).group(1)
                id = f"{string[1]};{hgvs};{string[0]}"
            elif type == "SNP":
                id = ";".join(reversed(string))
        else:
            # FIXME: maybe try name mapping approach
            # Some genes contain more than one ID
            id = id.split(";")[0]

        node_dict.setdefault(
            id, {"type": type, "name": name, "xml_id": xml_id_counter()})
    elif line_type == "relation":
        pmid, relationship, name_1, name_2 = line.strip("\n").split("\t")
        edge_dict[(name_1, name_2)].append({"pmid": pmid, "relationship": relationship, "xml_id": xml_id_counter()})
        node_in_relation.add(name_1)
        node_in_relation.add(name_2)


def determine_line_type(line):
    line_split_len = len(line.split("\t"))
    if line_split_len == 4:
        line_type = "relation"
    elif line_split_len == 6:
        line_type = "annotation"
    else:
        line_type = "unknown"

    return line_type


def xml_id_counter(id=count(1)):
    return str(next(id))


def name_value(name, value, with_type="string"):
    attr = {"name": name, "value": value}
    if with_type is not None:
        attr.update(TYPE_ATTR[with_type])
    return attr


def add_node_to_graph(G: nx.Graph, node_dict, node_in_relation):
    for id in node_in_relation:
        # FIXME: currently skip nodes with strange ids
        try:
            G.add_node(id,
                       color=COLOR_MAP[node_dict[id]["type"]],
                       shape=SHAPE_MAP[node_dict[id]["type"]],
                       type=node_dict[id]["type"],
                       name=node_dict[id]["name"],
                       xml_id=node_dict[id]["xml_id"])
        except Exception:
            pass 


def add_edge_to_graph(G: nx.Graph, edge_counter):
    for pair, records in edge_counter.items():
        pmids = [record["pmid"] for record in records]
        unique_pmids = set(pmids)
        try:
            G.add_edge(pair[0], pair[1],
                    xml_id=records[0]["xml_id"],
                    # TODO: try other types of weight determination
                    weight=len(unique_pmids),
                    pmids=",".join(list(unique_pmids)))
        except Exception:
            pass


def create_graph_xml(G):
    _dummy_attr = {QName(XML_NAMESPACE["dc"], "dummy"): "",
                   QName(XML_NAMESPACE["xlink"], "dummy"): "",
                   QName(XML_NAMESPACE["rdf"], "dummy"): ""}
    _graph_attr = {"id": "0", "label": "0", "directed": "1",
                   "xmlns": "http://www.cs.rpi.edu/XGMML",
                   QName(XML_NAMESPACE["cy"], "documentVersion"): "3.0",
                   **_dummy_attr}

    graph = E.graph(_graph_attr,
                    create_graphic_xml(),
                    *create_node_xml(G),
                    *create_edge_xml(G)
                    )

    # Delete attributes, keep namespace definition only
    for key in _dummy_attr:
        del graph.attrib[key]

    return graph


def create_graphic_xml():
    graph = (
        E.graphics(
            E.att(name_value("NETWORK_WIDTH", "795.0")),
            E.att(name_value("NETWORK_DEPTH", "0.0")),
            E.att(name_value("NETWORK_HEIGHT", "500.0")),
            E.att(name_value("NETWORK_NODE_SELECTION", "true")),
            E.att(name_value("NETWORK_EDGE_SELECTION", "true")),
            E.att(name_value("NETWORK_BACKGROUND_PAINT", "#FFFFFF")),
            E.att(name_value("NETWORK_CENTER_Z_LOCATION", "0.0")),
            E.att(name_value("NETWORK_NODE_LABEL_SELECTION", "false")),
            E.att(name_value("NETWORK_TITLE", "")),
        )
    )

    return graph


def create_node_xml(G):
    node_collection = []
    for node in G.nodes(data=True):
        try:
            node_collection.append(_create_node_xml(node))
        except Exception:
            pass
    return node_collection


def _create_node_xml(node):
    node_id, node_attr = node

    _node_attr = {"id": node_attr["xml_id"], "label": node_attr["name"]}
    _graphics_attr = {"width": "0.0", "h": "35.0", "w": "35.0", "z": "0.0",
                      "type": node_attr["shape"], "outline": "#CCCCCC",
                      "fill": node_attr["color"]}

    node = (
        E.node(_node_attr,
            E.att(name_value("shared name", node_attr["name"])),
            E.att(name_value("name", node_attr["name"])),
            E.att(name_value("class", node_attr["type"])),
            E.graphics(_graphics_attr,
                E.att(name_value("NODE_SELECTED", "false")),
                E.att(name_value("NODE_NESTED_NETWORK_IMAGE_VISIBLE", "true")),
                E.att(name_value("NODE_DEPTH", "0.0")),
                    E.att(name_value("NODE_SELECTED_PAINT", "#FFFF00")),
                    E.att(name_value("NODE_LABEL_ROTATION", "0.0")),
                    E.att(name_value("NODE_LABEL_WIDTH", "200.0")),
                    E.att(name_value("COMPOUND_NODE_PADDING", "10.0")),
                    E.att(name_value("NODE_LABEL_TRANSPARENCY", "255")),
                    E.att(name_value("NODE_LABEL_POSITION", "C,C,c,0.00,0.00")),
                    E.att(name_value("NODE_LABEL", node_attr["name"])),
                    E.att(name_value("NODE_VISIBLE", "true")),
                    E.att(name_value("NODE_LABEL_FONT_SIZE", "12")),
                    E.att(name_value("NODE_BORDER_STROKE", "SOLID")),
                    E.att(name_value("NODE_LABEL_FONT_FACE", "SansSerif.plain,plain,12")),
                    E.att(name_value("NODE_BORDER_TRANSPARENCY", "255")),
                    E.att(name_value("COMPOUND_NODE_SHAPE", node_attr["shape"])),
                    E.att(name_value("NODE_LABEL_COLOR", "#000000")),
                    E.att(name_value("NODE_TRANSPARENCY", "255")),
                )
            )
        )

    return node


def create_edge_xml(G):
    edge_collection = []
    for edge in G.edges(data=True):
        try:
            edge_collection.append(_create_edge_xml(edge, G))
        except Exception:
            pass

    return edge_collection


def _create_edge_xml(edge, G):
    node_id_1, node_id_2, edge_attr = edge

    _edge_attr = {"id": edge_attr["xml_id"],
                  "label": f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}",
                  "source": G.nodes[node_id_1]["xml_id"],
                  "target": G.nodes[node_id_2]["xml_id"],
                  QName(XML_NAMESPACE["cy"], "directed"): "1"
                  }

    _graphics_attr = {"width": str(edge_attr["weight"]), "fill": "#848484"}

    edge = (
        E.edge(_edge_attr,
            E.att(name_value("shared name", f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}")),
            E.att(name_value("shared interaction", "interacts with")),
            E.att(name_value("name", f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}")),
            E.att(name_value("selected", "0", with_type="boolean")),
            E.att(name_value("interaction", "interacts with")),
            E.att(name_value("weight", str(edge_attr["weight"]), with_type="integer")),
            # TODO: implement scaled weight
            # E.att(name_value("scaled weight", edge_attr["scaled weight"], with_type="integer")),
            E.att(name_value("pubmed id", edge_attr["pmids"])),
            E.graphics(_graphics_attr,
                E.att(name_value("EDGE_TOOLTIP", "")),
                E.att(name_value("EDGE_SELECTED", "false")),
                E.att(name_value("EDGE_TARGET_ARROW_SIZE", "6.0")),
                E.att(name_value("EDGE_LABEL", "")),
                E.att(name_value("EDGE_LABEL_TRANSPARENCY", "255")),
                E.att(name_value("EDGE_STACKING_DENSITY", "0.5")),
                E.att(name_value("EDGE_TARGET_ARROW_SHAPE", "NONE")),
                E.att(name_value("EDGE_SOURCE_ARROW_UNSELECTED_PAINT", "#000000")),
                E.att(name_value("EDGE_TARGET_ARROW_SELECTED_PAINT", "#FFFF00")),
                E.att(name_value("EDGE_TARGET_ARROW_UNSELECTED_PAINT", "#000000")),
                E.att(name_value("EDGE_SOURCE_ARROW_SHAPE", "None")),
                E.att(name_value("EDGE_BEND", "")),
                E.att(name_value("EDGE_STACKING", "AUTO_BEND")),
                E.att(name_value("EDGE_LABEL_COLOR", "#000000")),
                E.att(name_value("EDGE_TRANSPARENCY", "255")),
                E.att(name_value("EDGE_LABEL_ROTATION", "0.0")),
                E.att(name_value("EDGE_LABEL_WIDTH", "200.0")),
                E.att(name_value("EDGE_CURVED", "true")),
                E.att(name_value("EDGE_SOURCE_ARROW_SIZE", "6.0")),
                E.att(name_value("EDGE_VISIBLE", "true")),
                E.att(name_value("EDGE_LINE_TYPE", "SOLID")),
                E.att(name_value("EDGE_STROKE_SELECTED_PAINT", "#FF0000")),
                E.att(name_value("EDGE_LABEL_FONT_SIZE", "10")),
                E.att(name_value("EDGE_LABEL_FONT_FACE", "Dialog.plain,plain,10")),
                E.att(name_value("EDGE_Z_ORDER", "0.0")),
                E.att(name_value("EDGE_SOURCE_ARROW_SELECTED_PAINT", "#FFFF00")),
                )
            )
        )

    return edge


if __name__ == "__main__":
    filepath = "./examples/example_output.pubtator"
    savepath = "./temp_xml.xgmml"
    pubtator2cytoscape(filepath, savepath)
# nx.draw_networkx(G, pos=pos, with_labels=False, node_size=5)
# nx.write_graphml_lxml(G, "example_graph.graphml")
