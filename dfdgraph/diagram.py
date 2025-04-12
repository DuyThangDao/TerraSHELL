import graphviz
import logging
from typing import List

from dfdgraph.dataflow import GLOBAL_DF_SP
from sparta_utils.sparta import AddElement, Export, ThreatAnalyze
from .component import DFDNode, ExternalEntity
from .trustboundary import TrustBoundary


logger = logging.getLogger(__name__)

class Diagram:
    def __init__(self):
        self.publicNodes: List[DFDNode] = []
        self.boundaries: List[TrustBoundary] = []

    def ExportSparta(self, path, external_entities):
        # ee = ExternalEntity("", "User", "RemoteUser")
        ee_list = [ExternalEntity("", ee["name"], ee["annotation"]) for ee in external_entities]
        
        for node in self.publicNodes:
            for ee in ee_list:
                ee.AddEdge(node)
                # node.AddEdge(ee)

        for ee in ee_list:
            AddElement(ee.Get())
        for bound in self.boundaries:
            AddElement(bound.Get())
        
        for df in GLOBAL_DF_SP:
            AddElement(df)

        Export(path + "/output.sparta")
        ThreatAnalyze(path + "/output.csv", path + "/output.sparta")

    def DrawDiagram(self, g: graphviz.Digraph, external_entities):
        # Special node representates User
        ee_list = [ExternalEntity("", ee["name"], ee["annotation"]) for ee in external_entities]
        # Connect to all public node
        # !TODO: Assume User has bidirectional data flow to those node
        for node in self.publicNodes:
            for ee in ee_list:
                ee.AddEdge(node)
                # node.AddEdge(ee)

        # Separating node and edge draw (graphviz bug)
        for ee in ee_list:
            ee.DrawNode(g)
        for bound in self.boundaries:
            logger.info(f"In diag: {bound.name}")
            bound.DrawBoundNode(g)

        for ee in ee_list:
            ee.DrawEdge(g)
        for bound in self.boundaries:
            bound.DrawBoundEdge(g)

    def AddPublicNode(self, n: DFDNode):
        self.publicNodes.append(n)
    def AddBoundary(self, b: TrustBoundary):
        self.boundaries.append(b)