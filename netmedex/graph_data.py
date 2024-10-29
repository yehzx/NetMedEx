from dataclasses import dataclass
from typing import Optional


@dataclass
class GraphNodeData:
    _id: str
    color: str
    label_color: str
    shape: str
    type: str
    name: str
    document_frequency: int
    marked: bool = False
    parent: Optional[str] = None


@dataclass
class GraphEdgeData:
    _id: str
    raw_frequency: int
    weighted_frequency: float
    npmi: float
    edge_weight: float
    pmids: dict[str, str]
    scaled_edge_weight: Optional[float] = None


@dataclass
class CommunityEdgeData:
    _id: int
    edge_weight: float
    scaled_edge_weight: float
    pmids: dict[str, str]
