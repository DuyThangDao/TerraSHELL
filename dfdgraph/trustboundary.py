import graphviz
import logging
from typing import List, Mapping

from sparta_utils.sparta import SpartaComponent
from utils.random_tmp import get_random_id
from .component import DFDNode


logger = logging.getLogger(__name__)

BOUNDARY_ID_NODE: Mapping[str, "TrustBoundary"] = {}

class TrustBoundary:
    boundaryIdx = 0
    def __init__(self, id, name = ""):
        self.name = name
        self.nodes: List[DFDNode] = []
        self.innerBoundaries: List[TrustBoundary] = []

        self.spartaBoundary = SpartaComponent.TrustBoundaryContainer(name)

        if id == "":
            self.id = get_random_id()
        else:
            self.id = str(id)
        BOUNDARY_ID_NODE[self.id] = self

        # self.g:graphviz.Digraph = g.subgraph(name=f"cluster_{TrustBoundary.boundaryIdx}")
        self.currentIdx = TrustBoundary.boundaryIdx
        TrustBoundary.boundaryIdx += 1
    def DrawBoundNode(self,g: graphviz.Digraph):
        with g.subgraph(name=f"cluster_{self.currentIdx}") as sg:
            sg.attr(style="dashed", color="firebrick2")
            sg.attr(label=self.name)
            for node in self.nodes:
                node.DrawNode(sg)
                # node.DrawEdge(sg)
            for boundary in self.innerBoundaries:
                logger.info(f"In {self.name}: {boundary.name}")
                boundary.DrawBoundNode(sg)
    def DrawBoundEdge(self, g:graphviz.Digraph):
        for node in self.nodes:
            node.DrawEdge(g)
        for boundary in self.innerBoundaries:
            boundary.DrawBoundEdge(g)
    def AddNode(self, n: DFDNode):
        self.nodes.append(n)
        self.spartaBoundary.containedElements.append(n.Get())

    def Get(self):
        return self.spartaBoundary

    def AddInnerBound(self, bound: "TrustBoundary"):
        self.innerBoundaries.append(bound)
        self.spartaBoundary.containedElements.append(bound.Get())