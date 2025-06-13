import logging
import math
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from operator import itemgetter
from typing import Literal

import networkx as nx
from typing_extensions import override

from netmedex.graph_data import (
    NODE_COLOR_MAP,
    NODE_SHAPE_MAP,
    CommunityEdgeData,
    GraphEdgeData,
    GraphNodeData,
)
from netmedex.npmi import normalized_pointwise_mutual_information
from netmedex.pubtator_parser import PubTatorAnnotation, PubTatorArticle, PubTatorRelation
from netmedex.utils import generate_uuid

MUTATION_PATTERNS = {
    "tmvar": re.compile(r"(tmVar:[^;]+)"),
    "hgvs": re.compile(r"(HGVS:[^;]+)"),
    "rs": re.compile(r"(RS#:[^;]+)"),
    "variantgroup": re.compile(r"(VariantGroup:[^;]+)"),
    "gene": re.compile(r"(CorrespondingGene:[^;]+)"),
    "species": re.compile(r"(CorrespondingSpecies:[^;]+)"),
    "ca": re.compile(r"(CA#:[^;]+)"),
}

ANNOTATION_TYPES = {
    "Chemical",
    "Gene",
    "Species",
    "Disease",
    "DNAMutation",
    "ProteinMutation",
    "CellLine",
    "SNP",
    # "Chromosome",  # Exclude Chromosome
}
MIN_EDGE_WIDTH = 0
MAX_EDGE_WIDTH = 20


logger = logging.getLogger(__name__)


@dataclass
class MeshNodeData:
    mesh: str
    type: str
    name: defaultdict[str, int]
    pmid: str


@dataclass
class PubTatorNodeData:
    mesh: str
    type: str
    name: str
    pmid: str


@dataclass
class PubTatorEdge:
    node1_id: str
    node2_id: str
    pmid: str
    relation: str


class NodeCollection(ABC):
    @abstractmethod
    def add_node(self, annotation: PubTatorAnnotation) -> None:
        pass

    @abstractmethod
    def to_clean_pubtator_nodes(self) -> dict[str, PubTatorNodeData]:
        pass


class NonMeshNodeCollection(NodeCollection):
    nodes: dict[str, PubTatorNodeData]
    node_id_occurrences: defaultdict[str, int]
    node_names: defaultdict[str, set[str]]
    """For removing nodes with the same name but annotated as different types
        {standardized_name : {node_id, ...}}"""

    def __init__(self) -> None:
        self.nodes = {}
        self.node_id_occurrences = defaultdict(int)
        self.node_names = defaultdict(set)

    @override
    def add_node(self, annotation: PubTatorAnnotation) -> None:
        # Normalize text
        name = annotation.get_standardized_name()

        # Text can take on different types depending on the context
        # Append annotation type as suffix
        node_id = annotation.get_non_mesh_node_id(name)
        self.node_id_occurrences[node_id] += 1
        self.node_names[name].add(node_id)

        if node_id not in self.nodes:
            self.nodes[node_id] = PubTatorNodeData(
                mesh=annotation.mesh,
                type=annotation.type,
                name=name,
                pmid=annotation.pmid,
            )

    @override
    def to_clean_pubtator_nodes(self) -> dict[str, PubTatorNodeData]:
        """Parse and remove redundant nodes

        The initial non-MeSH nodes have the same attributes as the final nodes
        we want. The only cleaning performed here is removing nodes with the
        same name but annotated as different types. It is likely that, in the
        same article, these nodes represent the same entity but are misannotated
        as different types.
        """
        nodes = self.nodes.copy()
        for node_id_set in self.node_names.values():
            if len(node_id_set) > 1:
                # Remove nodes with the same name but annotated as different types
                # Choose the node with the most occurrences
                node_id = max(node_id_set, key=lambda x: self.node_id_occurrences[x])
                for node_id in node_id_set:
                    if node_id != node_id:
                        nodes.pop(node_id)
        return nodes


class MeshNodeCollection(NodeCollection):
    use_mesh_vocabulary: bool
    """Whether the PubTator file has standardized MeSH terms as names"""
    nodes: dict[str, MeshNodeData]
    node_occurrences: defaultdict[str, int]

    def __init__(self, use_mesh_vocabulary: bool):
        self.use_mesh_vocabulary = use_mesh_vocabulary
        self.nodes = {}
        self.node_occurrences = defaultdict(int)

    @override
    def add_node(self, annotation: PubTatorAnnotation):
        node_id_list = annotation.get_mesh_node_id()
        name = (
            annotation.get_standardized_name() if not self.use_mesh_vocabulary else annotation.name
        )

        for node_id in node_id_list:
            # Node occurrence information are not used for now, but still keep it
            self.node_occurrences[node_id] += 1
            if node_id not in self.nodes:
                self.nodes[node_id] = MeshNodeData(
                    mesh=annotation.mesh,
                    type=annotation.type,
                    name=defaultdict(int),
                    pmid=annotation.pmid,
                )
            self.nodes[node_id].name[name] += 1

    @override
    def to_clean_pubtator_nodes(self) -> dict[str, PubTatorNodeData]:
        """Parse and convert MeshNodeData to PubTatorNodeData

        MeSH terms are always indexed by their MeSH IDs. If users choose to keep
        the raw text of MeSH terms, we pick the most frequently occurring one
        as the name for each term. If the raw text is already standardized as MeSH
        terms, it will always be selected since there are no other entries in the
        name.
        """
        nodes = {}
        for node_id, node_data in self.nodes.items():
            name: str = max(node_data.name, key=node_data.name.get)  # type: ignore
            nodes[node_id] = PubTatorNodeData(
                mesh=node_data.mesh,
                type=node_data.type,
                name=name,
                pmid=node_data.pmid,
            )

        return nodes


class PubTatorNodeCollection(NodeCollection):
    mesh_only: bool
    """Only Keep MeSH Nodes"""
    use_mesh_vocabulary: bool
    non_mesh_collection: NonMeshNodeCollection
    mesh_collection: MeshNodeCollection
    _mesh_nodes: dict[str, PubTatorNodeData]
    _non_mesh_nodes: dict[str, PubTatorNodeData]
    _nodes: dict[str, PubTatorNodeData]
    _mesh_updated: bool
    _non_mesh_updated: bool

    def __init__(self, mesh_only: bool, use_mesh_vocabulary: bool):
        self.mesh_only = mesh_only
        self.use_mesh_vocabulary = use_mesh_vocabulary
        self.non_mesh_collection = NonMeshNodeCollection()
        self.mesh_collection = MeshNodeCollection(use_mesh_vocabulary)
        self._mesh_nodes = {}
        self._non_mesh_nodes = {}
        self._nodes = {}
        self._mesh_updated = False
        self._non_mesh_updated = False

    @override
    def add_node(self, annotation: PubTatorAnnotation):
        if annotation.type not in ANNOTATION_TYPES:
            return

        if annotation.mesh in ("-", ""):
            if self.mesh_only:
                return
            self.non_mesh_collection.add_node(annotation)
            self._non_mesh_updated = True
        else:
            self.mesh_collection.add_node(annotation)
            self._mesh_updated = True

    @override
    def to_clean_pubtator_nodes(self) -> dict[str, PubTatorNodeData]:
        return self.nodes

    @property
    def mesh_nodes(self) -> dict[str, PubTatorNodeData]:
        if self._mesh_updated:
            self._mesh_nodes = self.mesh_collection.to_clean_pubtator_nodes()
            self._mesh_updated = False
        return self._mesh_nodes

    @property
    def non_mesh_nodes(self) -> dict[str, PubTatorNodeData]:
        if self._non_mesh_updated:
            self._non_mesh_nodes = self.non_mesh_collection.to_clean_pubtator_nodes()
            self._non_mesh_updated = False
        return self._non_mesh_nodes

    @property
    def nodes(self) -> dict[str, PubTatorNodeData]:
        if self._mesh_updated or self._non_mesh_updated:
            self._nodes = self.non_mesh_nodes | self.mesh_nodes
        return self._nodes


class PubTatorRelationParser:
    _mesh_node_id_mapping: dict[str, str]
    """{mesh: node_id} mapping for non-mutation terms"""
    _mutation_mesh_node_info: dict[str, dict[str, str | None]]
    """{node_id: mutation_info} for parsing mutation terms"""

    def __init__(self, mesh_node_ids: Sequence[str]) -> None:
        self._mesh_node_id_mapping = {}
        self._mutation_mesh_node_info = {}

        for mesh_node_id in mesh_node_ids:
            if len(mesh_node_id.split(";", 1)) == 1:
                self._mesh_node_id_mapping[
                    PubTatorAnnotation.get_mesh_from_mesh_node_id(mesh_node_id)
                ] = mesh_node_id
            else:
                # Likely a mutation term
                self._mutation_mesh_node_info[mesh_node_id] = self._get_mutation_info(
                    PubTatorAnnotation.get_mesh_from_mesh_node_id(mesh_node_id)
                )

    @staticmethod
    def _get_mutation_info(mesh: str) -> dict[str, str | None]:
        mutation_info = {}
        for name, pattern in MUTATION_PATTERNS.items():
            if (matched := pattern.search(mesh)) is not None:
                mutation_info[name] = matched.group(1)
            else:
                mutation_info[name] = None

        return mutation_info

    def parse(self, relation: PubTatorRelation) -> tuple[str, str] | None:
        """Parse a relation and return the node IDs of the two nodes"""
        nodes = []
        for mesh in (relation.mesh1, relation.mesh2):
            node = self._mesh_node_id_mapping.get(mesh, self.match_mutation_mesh(mesh))
            if node is None:
                logger.warning(f"Mutation not found: {mesh} (PMID: {relation.pmid})")
                return
            nodes.append(node)

        if nodes[0] <= nodes[1]:
            return tuple(nodes)
        else:
            return tuple(reversed(nodes))

    def match_mutation_mesh(self, mesh: str) -> str | None:
        matched_node_id = None
        mutation_info = self._get_mutation_info(mesh)
        for node_id, info_to_match in self._mutation_mesh_node_info.items():
            is_matched = True
            for attr, value in mutation_info.items():
                if value is None:
                    continue
                if info_to_match[attr] != value:
                    is_matched = False
                    break
            if is_matched:
                matched_node_id = node_id
                break

        return matched_node_id


class PubTatorGraph:
    node_type: Literal["all", "mesh", "relation"]
    num_articles: int
    _mesh_only: bool
    graph: nx.Graph
    _updated: bool
    """Track whether any new articles are added"""

    def __init__(
        self,
        node_type: Literal["all", "mesh", "relation"],
    ) -> None:
        self.node_type = node_type
        self._mesh_only = node_type in ("mesh", "relation")
        self.num_articles = 0
        self.graph = nx.Graph()
        self._updated = False
        self._init_graph_attributes()

    def build(
        self,
        pmid_weights: dict[str, int | float] | None = None,
        weighting_method: Literal["freq", "npmi"] = "freq",
        edge_weight_cutoff: int = 0,
        community: bool = True,
        max_edges: int = 0,
    ):
        """Build the co-mention network with edge weights

        Add node attributes: num_articles, num_edges?
        Add edge attributes: npmi, occurrence_weight, scaled_weight, ...
        Add graph attributes: num_articles

        Args:
            pmid_weights (dict[str, int | float], optional):
                The weight (importance) of each article.
            weighting_method (Literal[&quot;freq&quot;, &quot;npmi&quot;], optional):
                Method used for calculating edge weights. Defaults to "freq".
            edge_weight_cutoff (int, optional):
                For removing edges with weights below the cutoff. Defaults to 0.
            community (bool, optional):
                Whether to apply the community detection method. Defaults to True.
            max_edges (int, optional):
                For keep top [max_edges] edges sorted descendingly by edge weights. Defaults to 0.
        """

        self.build_nodes(pmid_weights)
        self.build_edges(pmid_weights, weighting_method)

        self.remove_edges_by_weight(edge_weight_cutoff)
        self.remove_edges_by_rank(max_edges)

        self.remove_isolated_nodes()

        self.check_graph_properties()

        self.set_network_layout()

        if community:
            self.set_network_communities()

        self.log_graph_info()
        self._updated = False

        return self.graph

    def build_nodes(self, pmid_weights: dict[str, int | float] | None = None):
        for _, data in self.graph.nodes(data=True):
            data["num_articles"] = len(data["pmids"])
            if pmid_weights is not None:
                data["weighted_num_articles"] = round(
                    sum([pmid_weights.get(pmid, 1) for pmid in data["pmids"]]), 2
                )
            else:
                data["weighted_num_articles"] = data["num_articles"]

    def build_edges(
        self,
        pmid_weights: dict[str, int | float] | None,
        weighting_method: Literal["npmi", "freq"],
    ):
        # Update attributes for edges
        for u, v, data in self.graph.edges(data=True):
            data["num_relations"] = len(data["relations"])
            if pmid_weights is not None:
                data["weighted_num_relations"] = round(
                    sum([pmid_weights.get(pmid, 1) for pmid in data["relations"]]), 2
                )
            else:
                data["weighted_num_relations"] = data["num_relations"]

            # data["num_relations_doc_weighted"] = num_evidence *
            data["npmi"] = normalized_pointwise_mutual_information(
                n_x=self.graph.nodes[u]["weighted_num_articles"],
                n_y=self.graph.nodes[v]["weighted_num_articles"],
                n_xy=data["weighted_num_relations"],
                N=self.num_articles,
                n_threshold=2,
            )

        # Calculate scaled weights
        if weighting_method == "npmi":
            edge_weights: dict[tuple[str, str], float] = nx.get_edge_attributes(self.graph, "npmi")
            scale_factor = MAX_EDGE_WIDTH
        elif weighting_method == "freq":
            edge_weights: dict[tuple[str, str], float] = nx.get_edge_attributes(
                self.graph, "weighted_num_relations"
            )
            max_weight = max(edge_weights.values())
            scale_factor = min(MAX_EDGE_WIDTH / max_weight, 1)

        # Update scaled weights for edges
        for edge, weight in edge_weights.items():
            scaled_weight = round(max(weight * scale_factor, 0.0), 2)
            self.graph.edges[edge].update(
                {
                    "edge_weight": scaled_weight,
                    "edge_width": max(scaled_weight, MIN_EDGE_WIDTH),
                }
            )

    def remove_edges_by_weight(self, edge_weight_cutoff: int | float):
        to_remove = []
        for u, v, edge_attrs in self.graph.edges(data=True):
            if edge_attrs["edge_width"] < edge_weight_cutoff:
                to_remove.append((u, v))
        self.graph.remove_edges_from(to_remove)

    def remove_edges_by_rank(self, max_edges: int):
        if max_edges <= 0:
            return

        if self.graph.number_of_edges() > max_edges:
            edges = sorted(
                # u, v, data
                self.graph.edges(data=True),
                key=lambda x: x[2]["edge_weight"],
                reverse=True,
            )
            for edge in edges[max_edges:]:
                self.graph.remove_edge(edge[0], edge[1])

    def remove_isolated_nodes(self):
        self.graph.remove_nodes_from(list(nx.isolates(self.graph)))

    def check_graph_properties(self):
        num_selfloops = nx.number_of_selfloops(self.graph)
        if num_selfloops != 0:
            logger.warning(f"[Error] Find {num_selfloops} selfloops")

    def set_network_layout(self):
        if self.graph.number_of_edges() > 1000:
            pos = nx.circular_layout(self.graph, scale=300)
        else:
            pos = nx.spring_layout(
                self.graph, weight="scaled_edge_weight", scale=300, k=0.25, iterations=15
            )
        nx.set_node_attributes(self.graph, pos, "pos")

    def set_network_communities(self, seed: int = 1):
        communities = nx.community.louvain_communities(self.graph, seed=seed, weight="edge_weight")
        community_labels = set()
        for c_idx, community in enumerate(communities):
            highest_degree_node = max(
                self.graph.degree(community, weight="edge_weight"), key=itemgetter(1)
            )[0]
            community_node = f"c{c_idx}"
            community_labels.add(community_node)
            community_attrs = self.graph.nodes[highest_degree_node].copy()
            community_attrs.update(
                {"label_color": "#dd4444", "parent": None, "_id": community_node}
            )
            node_data = GraphNodeData(**community_attrs)
            self.graph.add_node(community_node, **asdict(node_data))

            for node in community:
                self.graph.nodes[node]["parent"] = community_node

        self.graph.graph["num_communities"] = len(community_labels)

        # Gather edges between communities
        inter_edge_weight = defaultdict(float)
        inter_edge_pmids = defaultdict(dict)
        to_remove = []
        for u, v, attrs in self.graph.edges(data=True):
            if (c_0 := self.graph.nodes[u]["parent"]) != (c_1 := self.graph.nodes[v]["parent"]):
                if c_0 is None or c_1 is None:
                    logger.warning(f"[Error] Node {u} or {v} is not in any community")
                    continue
                to_remove.append((u, v))
                community_edge = tuple(sorted([c_0, c_1]))
                inter_edge_weight[community_edge] += attrs["edge_weight"]
                inter_edge_pmids[community_edge].update(attrs["relations"])

        self.graph.remove_edges_from(to_remove)
        for (c_0, c_1), weight in inter_edge_weight.items():
            # Log-adjusted weight for balance
            try:
                weight = math.log(weight) * 5
                weight = 0.0 if weight < 0.0 else weight
            except ValueError:
                weight = 0.0
            pmids = set(inter_edge_pmids[(c_0, c_1)])
            edge_data = CommunityEdgeData(
                _id=generate_uuid(),
                edge_weight=weight,
                edge_width=max(weight, MIN_EDGE_WIDTH),
                pmids=set(pmids),
            )
            self.graph.add_edge(c_0, c_1, type="community", **asdict(edge_data))

    def log_graph_info(self):
        logger.info(f"# articles: {len(self.graph.graph['pmid_title'])}")
        if num_communities := self.graph.graph.get("num_communities", 0):
            logger.info(f"# communities: {num_communities}")
        logger.info(f"# nodes: {self.graph.number_of_nodes() - num_communities}")
        logger.info(f"# edges: {self.graph.number_of_edges()}")

    def add_article(
        self,
        article: PubTatorArticle,
        use_mesh_vocabulary: bool = True,
    ):
        self._updated = True
        self.num_articles += 1

        node_collection = PubTatorNodeCollection(
            mesh_only=self._mesh_only, use_mesh_vocabulary=use_mesh_vocabulary
        )
        for annotation in article.annotations:
            node_collection.add_node(annotation)

        edges = []
        if self.node_type != "relation":
            edges += self._create_complete_graph_edges(
                list(node_collection.nodes.keys()), article.pmid
            )

        edges += self._create_relation_edges(
            list(node_collection.mesh_nodes.keys()), article.relations
        )

        self._add_attributes(article)
        self._add_nodes(node_collection.nodes)
        self._add_edges(edges)

    def _create_complete_graph_edges(
        self, node_ids: Sequence[str], pmid: str
    ) -> list[PubTatorEdge]:
        """Build co-mention edges for all given nodes

        Assuming that all nodes are in the same article.
        """
        edges: list[PubTatorEdge] = []
        for i in range(len(node_ids) - 1):
            for j in range(i + 1, len(node_ids)):
                # Node1 and Node2 always follow alphabetical order
                if node_ids[i] <= node_ids[j]:
                    edge = PubTatorEdge(node_ids[i], node_ids[j], pmid, "co-mention")
                else:
                    edge = PubTatorEdge(node_ids[j], node_ids[i], pmid, "co-mention")
                edges.append(edge)

        return edges

    def _create_relation_edges(
        self,
        mesh_node_ids: Sequence[str],
        relations: Sequence[PubTatorRelation],
    ) -> list[PubTatorEdge]:
        """Only create BioREx annotated edges"""
        parser = PubTatorRelationParser(mesh_node_ids)

        edges = []
        for relation in relations:
            if (node_ids := parser.parse(relation)) is None:
                continue
            else:
                edges.append(
                    PubTatorEdge(node_ids[0], node_ids[1], relation.pmid, relation.relation_type)
                )

        return edges

    def _add_nodes(self, nodes: Mapping[str, PubTatorNodeData]):
        for node_id, data in nodes.items():
            if self.graph.has_node(node_id):
                self.graph.nodes[node_id]["pmids"].add(data.pmid)
            else:
                node_data = GraphNodeData(
                    _id=generate_uuid(),
                    color=NODE_COLOR_MAP[data.type],
                    label_color="#000000",
                    shape=NODE_SHAPE_MAP[data.type],
                    type=data.type,
                    name=data.name,
                    pmids={data.pmid},
                    num_articles=None,
                    weighted_num_articles=None,
                    marked=False,
                    parent=None,
                    pos=None,
                )
                self.graph.add_node(node_id, **asdict(node_data))

    def _add_edges(self, edges: Sequence[PubTatorEdge]):
        for edge in edges:
            if self.graph.has_edge(edge.node1_id, edge.node2_id):
                relation_dict: dict[str, set[str]] = self.graph.edges[
                    edge.node1_id, edge.node2_id
                ]["relations"]

                if relation_dict.get(edge.pmid) is None:
                    relation_dict[edge.pmid] = {edge.relation}
                else:
                    relation_dict[edge.pmid].add(edge.relation)
            else:
                edge_data = GraphEdgeData(
                    _id=generate_uuid(),
                    relations={edge.pmid: {edge.relation}},
                    num_relations=None,
                    weighted_num_relations=None,
                    npmi=None,
                    edge_weight=None,
                    edge_width=None,
                )
                self.graph.add_edge(edge.node1_id, edge.node2_id, **asdict(edge_data))

    def _add_attributes(self, article: PubTatorArticle):
        # Add pmid_title as a graph attribute
        self.graph.graph["pmid_title"][article.pmid] = article.title

    def _init_graph_attributes(self):
        self.graph.graph["pmid_title"] = {}
