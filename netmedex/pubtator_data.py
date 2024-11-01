import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Union

from netmedex.stemmers import s_stemmer

MUTATION_PATTERNS = {
    "tmvar": re.compile(r"(tmVar:[^;]+)"),
    "hgvs": re.compile(r"(HGVS:[^;]+)"),
    "rs": re.compile(r"(RS#:[^;]+)"),
    "variantgroup": re.compile(r"(VariantGroup:[^;]+)"),
    "gene": re.compile(r"(CorrespondingGene:[^;]+)"),
    "species": re.compile(r"(CorrespondingSpecies:[^;]+)"),
    "ca": re.compile(r"(CA#:[^;]+)")
}


@dataclass
class PubTatorNodeData:
    id: str
    mesh: str
    type: str
    name: Union[str, defaultdict[str, int]]
    pmids: set[str]


@dataclass
class PubTatorEdgeData:
    id: str
    pmid: str
    relation: Optional[str] = None


@dataclass
class PubTatorAnnotation:
    pmid: str
    start: str
    end: str
    name: str
    type: str
    mesh: str


@dataclass
class PubTatorRelation:
    pmid: str
    relation: str
    mesh1: str
    mesh2: str


class PubTatorLine:
    use_mesh = False

    def __init__(self, line: str):
        self.values: list[str] = [value.strip() for value in line.split("\t")]
        self.type: str = self.assign_line_type(self.values)
        self._data: Union[PubTatorAnnotation, PubTatorRelation, None] = None

    @staticmethod
    def assign_line_type(values: Sequence):
        if len(values) == 4:
            return "relation"
        elif len(values) == 6:
            return "annotation"
        else:
            return "unknown"

    @property
    def data(self):
        if self._data is None:
            self._data = self.parse_line()
        return self._data

    def parse_line(self):
        if self.type == "annotation":
            data = PubTatorAnnotation(*self.values)
        elif self.type == "relation":
            data = PubTatorRelation(*self.values)
        else:
            data = None
        return data

    def normalize_name(self):
        self.data.name = s_stemmer(self.data.name.lower())

    def parse_mesh(self, mesh_map: Mapping[str, str]):
        def convert_mesh(mesh: str, type_: str):
            converted = f"{type_}_{mesh}"
            if mesh not in mesh_map:
                mesh_map[mesh] = converted
            return converted

        anno_type = self.data.type
        mesh = self.data.mesh

        if not self.use_mesh:
            self.normalize_name()

        if anno_type in ("DNAMutation", "ProteinMutation", "SNP"):
            match_data = {}
            for key, pattern in MUTATION_PATTERNS.items():
                try:
                    match_data[key] = f"{re.search(pattern, mesh).group(1)};"
                except AttributeError:
                    match_data[key] = ""
            if anno_type == "DNAMutation":
                mesh = (f'{match_data["gene"]}{match_data["species"]}{match_data["variantgroup"]}'
                        f'{match_data["tmvar"].split("|")[0]}').strip(";")
            elif anno_type == "ProteinMutation":
                mesh = f'{match_data["rs"]}{match_data["hgvs"]}{match_data["gene"]}'.strip(";")
            elif anno_type == "SNP":
                mesh = f'{match_data["rs"]}{match_data["hgvs"]}{match_data["gene"]}'.strip(";")
            result = [{"key": mesh, "mesh": mesh}]
        elif anno_type == "Gene":
            mesh_list = mesh.split(";")
            result = [{"key": convert_mesh(mesh, "gene"),
                       "mesh": mesh} for mesh in mesh_list]
        elif anno_type == "Species":
            result = [{"key": convert_mesh(mesh, "species"),
                       "mesh": mesh}]
        else:
            result = [{"key": mesh, "mesh": mesh}]

        return result
