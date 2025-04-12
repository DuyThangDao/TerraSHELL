import graphviz

from sparta_utils.sparta import SpartaComponent

GLOBAL_DF_SP = []

class DataFlow:
    def __init__(self, fromNode, toNode, label):
        self.fromNode = fromNode
        self.toNode = toNode
        self.label = label
        self.df = SpartaComponent.DataFlow(
            self.fromNode.Get(), 
            self.toNode.Get(),
            fromNode.name + "->" + toNode.name
        )
        GLOBAL_DF_SP.append(self.df)
        # bidirection inference
        GLOBAL_DF_SP.append(SpartaComponent.DataFlow(
            self.toNode.Get(),
            self.fromNode.Get(), 
            toNode.name + "->" + fromNode.name
        ))
        
    def MakeDirected(self, g: graphviz.Digraph):
        g.edge(self.fromNode.id, self.toNode.id, label=self.label, dir="both")
    def Get(self):
        return self.df