# import pyecore.type as xmltypes # loads default XML Types in the global registry
from pyecore.resources import ResourceSet, URI
from pyecore.utils import DynamicEPackage
import os
import logging

from subprocess import run
logger = logging.getLogger(__name__)

# CATALOG_PATH    = str(os.path.abspath("./sparta_utils/IACThreatTypeCatalog.sparta"))
CATALOG_PATH    = str(os.path.abspath("./sparta_utils/IACNewCatalog_v2.sparta"))
CLI_PATH        = "./sparta_utils/sparta-cli-2022.1.1-shaded.jar"
MODEL_PATH      = "./sparta_utils/spartamodel.ecore"
OUT_PATH        = './output/output.sparta'


def Initialize(name = "DFD"):
    rset = ResourceSet()
    mm_rs = rset.get_resource(URI(MODEL_PATH))
    mm_root = mm_rs.contents[0]
    rset.metamodel_registry[mm_root.nsURI] = mm_root # register package NS in the resource set
    ePkg = DynamicEPackage(mm_root)
    stride = rset.get_resource(URI(CATALOG_PATH))

    gModel = ePkg.DFDModel(name=name)
    gModel.resource.append(stride.contents[0])
    
    return (ePkg, gModel, rset)

STATIC_INSTANCE = Initialize()
    

class SpartaComponent:
    root = STATIC_INSTANCE[0]
    @staticmethod
    def DFDModel(name=""):
        return SpartaComponent.root.DFDModel(name=name)

    @staticmethod
    def TrustBoundaryContainer(name=""):
        return SpartaComponent.root.TrustBoundaryContainer(name=name)
    
    @staticmethod
    def Process(name="", anno=""):
        p = SpartaComponent.root.Process(name=name)
        p.annotations.append(
            SpartaComponent.root.ModelElementAnnotation(value=anno)
        )
        return p

    @staticmethod
    def DataStore(name="", anno=""):
        p = SpartaComponent.root.DataStore(name=name)

        p.annotations.append(
            SpartaComponent.root.ModelElementAnnotation(value=anno)
        )
        return p
    
    @staticmethod
    def ExternalEntity(name="", anno=""):
        p = SpartaComponent.root.ExternalEntity(name=name)
        p.annotations.append(
            SpartaComponent.root.ModelElementAnnotation(value=anno)
        )
        return p
    
    @staticmethod
    def DataFlow(sender, recipient, name = ""):
        return SpartaComponent.root.DataFlow(sender=sender, recipient=recipient, name=name)
    

def AddElement(e):
    STATIC_INSTANCE[1].containedElements.append(e)

def Export(path=""):
    if path == "":
        path = OUT_PATH
    output = STATIC_INSTANCE[2].create_resource(URI(path))
    output.use_uuid = True
    output.append(STATIC_INSTANCE[1])
    output.save()

def ThreatAnalyze(csv_path, sparta_path):
    command = [
        "java",
        "-jar",
        "./sparta_utils/sparta-cli.jar",
        "-i",
        sparta_path,
        "-pt",
        "./sparta_utils/IACNewCatalog_v2.sparta",
        "-oc", 
        csv_path
        # "result.csv"
    ]

    logger.info("Running %s" % ' '.join(command)) 
    run(command)
