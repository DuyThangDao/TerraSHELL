#!/usr/bin/python3
import json
import fire
import logging
import graphviz
import re
import os

from dfdgraph import DataStore
from dfdgraph.component import COMPONENT_ID_NODE
from dfdgraph.trustboundary import BOUNDARY_ID_NODE
from graph import LoadFromFolder
from dfdgraph import Diagram, Process, TrustBoundary
from tfparser.tfgrep import GetSemgrepJSON
from utils.n4j_helper import CleanUp, Cleanup, CompressV2, FindOwn, LinkTagged, QueryAllConnectionResource, QueryOutermostBoundary, QueryTagged, RemoveNonTagged, RemovePublicBoundaries, TaggingNode, TaggingPublic
from utils.yaml_importer import read_config


def GenerateDockerPath(folderPath: str) -> str:
    if '\\' in folderPath:
        folderPath = folderPath.replace('\\', '/')
    pathComponents = folderPath.split("/")
    for i in range(len(pathComponents) - 1, -1, -1):
        currentPath = "/".join(pathComponents[i:])
        dockerPath = os.path.join("/project", currentPath)
        if os.path.exists(dockerPath):
            return dockerPath + "/"
    return folderPath

def main(in_path, anno_path="./input/aws_annotation.yaml", rule_path="./input/aws_rule.yaml", sem_rule="./input/semgrep_rule.yaml", out_path="./output", global_tb_name="Cloud", reinit=True, graph_mode=False, verbose=False):
    logging.basicConfig(level = logging.INFO)
    if not verbose:
        logging.disable(logging.INFO)
    if os.getenv("DOCKER_ENV") == "1":
        in_path = GenerateDockerPath(in_path)
        out_path = "/output"
    logging.info(f"Reading {in_path}, Writing to {out_path}")

    anno = read_config(anno_path)
    rule = read_config(rule_path)

    # Process compressed first

    compresses = \
        [m["tf_name"] for c in anno["processes"] for m in c["members"] if m.get("compress", False)] + \
        [m["tf_name"] for c in anno["data_stores"] for m in c["members"] if m.get("compress", False)]
    
    publics = set(
        [m["tf_name"] for c in anno["processes"] for m in c["members"] if m.get("can_public", False)] + \
        [m["tf_name"] for c in anno["data_stores"] for m in c["members"] if m.get("can_public", False)]
    )

    # if rm_depend_on:
    #     SemgrepFix(in_path, fix_rule)

    # Cleaning up (FOR DEBUGGING ONLY)
    CleanUp()

    # Getting path id
    pathID = LoadFromFolder(in_path, init=reinit)

    for key in anno:
        if key == "external_entities":
            continue
        for c in anno[key]:
            for member in c["members"]:
                TaggingNode(member["tf_name"], pathID, c["group_name"], member["name"], key, c.get("annotation", ""))

    RemoveNonTagged(pathID)
    Cleanup(pathID)

    for compress in compresses:
        logging.info("Compressing " + compress)
        CompressV2(compress, pathID)

    LinkTagged(pathID)
    RemoveNonTagged(pathID)

    sem_json = json.load(open(GetSemgrepJSON(in_path, sem_rule), "r"))
    for v in rule["publics"]:
        name = v["variable"]

        list_of_public_bound = set([result["extra"]["metavars"][name]["abstract_content"] for result in sem_json["results"]])
        logging.info(f"Public boundary {list_of_public_bound}")
        for bound in list_of_public_bound:
            TaggingPublic(pathID, bound)

    RemovePublicBoundaries(pathID)
    Cleanup(pathID)

    procname = set(c["group_name"] for c in anno["processes"])
    dsname = set(c["group_name"] for c in anno["data_stores"])
    boundname = set(c["group_name"] for c in anno["boundaries"])

    logging.info("List of Boundaries")
    
    compos = set()
    diag = Diagram()
    
    logging.info("-------- Boundary --------")
    for r in QueryTagged(pathID, "boundaries"):
        id_ = str(r["id"])
        crafted_name = "%s (%s)" % (r["group"], r["general_name"])
        logging.info(f"{id_} - {crafted_name}")

    logging.info("-------- Owning --------")
    logging.info("Traversing through owning rules")
    for v in rule["relations"]["own"]:
        r = FindOwn(v["first_node"], v["second_node"], v["method"], pathID)
        for u in r: 
            crafted_name1 = "%s (%s) - %s" % (u["group1"], u["general_name1"], u["tfname1"])
            crafted_name2 = "%s (%s) - %s" % (u["group2"], u["general_name2"], u["tfname2"])
            if u["group1"] in boundname:
                fr = BOUNDARY_ID_NODE[str(u["id1"])] if str(u["id1"]) in BOUNDARY_ID_NODE else TrustBoundary(u["id1"], crafted_name1)
            elif u["group1"] in procname:
                fr = COMPONENT_ID_NODE[str(u["id1"])] if str(u["id1"]) in COMPONENT_ID_NODE else Process(u["id1"], crafted_name1, u["annotation1"])
            elif u["group1"] in dsname:
                fr = COMPONENT_ID_NODE[str(u["id1"])] if str(u["id1"]) in COMPONENT_ID_NODE else DataStore(u["id1"], crafted_name1, u["annotation1"])
            else:
                logging.info("? " + str(u))

            if u["group2"] in boundname:
                if str(u["id1"]) in BOUNDARY_ID_NODE and str(u["id2"]) in BOUNDARY_ID_NODE:
                    logging.info("Already " + str(u))
                    continue
                to = BOUNDARY_ID_NODE[str(u["id2"])] if str(u["id2"]) in BOUNDARY_ID_NODE else TrustBoundary(u["id2"], crafted_name2)
                if u["group1"] not in boundname:
                    to.AddNode(fr)
                    compos.add(fr.id)
                    for pub in publics:
                        if re.fullmatch(pub, u["name1"]):
                            diag.AddPublicNode(fr)
                else:
                    fr.AddInnerBound(to)
            elif u["group2"] in procname:
                if str(u["id1"]) in BOUNDARY_ID_NODE and str(u["id2"]) in COMPONENT_ID_NODE:
                    logging.info("Already " + str(u))
                    continue
                to = COMPONENT_ID_NODE[str(u["id2"])] if str(u["id2"]) in COMPONENT_ID_NODE else Process(u["id2"], crafted_name2, u["annotation2"])
                fr.AddNode(to)
                compos.add(to.id)
                for pub in publics:
                    if re.fullmatch(pub, u["name2"]):
                        diag.AddPublicNode(to)
            elif u["group2"] in dsname:
                if str(u["id1"]) in BOUNDARY_ID_NODE and str(u["id2"]) in COMPONENT_ID_NODE:
                    logging.info("Already " + str(u))
                    continue
                to = COMPONENT_ID_NODE[str(u["id2"])] if str(u["id2"]) in COMPONENT_ID_NODE else DataStore(u["id2"], crafted_name2, u["annotation2"])
                fr.AddNode(to)
                compos.add(to.id)
                for pub in publics:
                    if re.fullmatch(pub, u["name2"]):
                        diag.AddPublicNode(to)
            logging.info("TO " + type(to).__name__ + str(to.name) + " " + to.id)

    # Add boundaries to graph
    aws = TrustBoundary("", global_tb_name)
    diag.AddBoundary(aws)

    logging.info("GOT: " + str(compos))

    logging.info("------------ Other Proc & DS ------------")
    for r in QueryTagged(pathID, "processes") + QueryTagged(pathID, "data_stores"):
        id_ = str(r["id"])
        if id_ in compos:
            continue
        crafted_name = "%s (%s) - %s" % (r["group"], r["general_name"], r["tfname"])
        logging.info(f"{id_} - {crafted_name}")
        if r["group"] in procname:
            n = COMPONENT_ID_NODE[id_] if id_ in COMPONENT_ID_NODE else Process(id_, crafted_name, r["annotation"])
        else:
            n = COMPONENT_ID_NODE[id_] if id_ in COMPONENT_ID_NODE else DataStore(id_, crafted_name, r["annotation"])
        aws.AddNode(n)
        logging.info(crafted_name)    

        for pub in publics:
            if re.fullmatch(pub, r["name"]):
                diag.AddPublicNode(n)

    logging.info("------- Outer boundary -----")

    for r in QueryOutermostBoundary(pathID):
        id_ = str(r["id"])
        crafted_name = "%s (%s)" % (r["group"], r["general_name"])
        aws.AddInnerBound(BOUNDARY_ID_NODE.get(id_))
        logging.info("OUTER " + crafted_name)

    logging.info("------- Connection -----")
    for r in QueryAllConnectionResource(pathID):
        crafted_name1 = "%s (%s)" % (r["group1"], r["general_name1"])
        crafted_name2 = "%s (%s)" % (r["group2"], r["general_name2"])
        logging.info(crafted_name1 + "-->" + crafted_name2)
        COMPONENT_ID_NODE.get(str(r["id1"])).AddEdge(COMPONENT_ID_NODE.get(str(r["id2"])))
        
    # Fill with connections
    
    if graph_mode:
        g = graphviz.Digraph("G", directory=out_path, filename="result.dot")
        g.graph_attr['nodesep'] = '1'
        g.graph_attr['ranksep'] = '2'
        diag.DrawDiagram(g, anno["external_entities"])
        g.render(filename="dfd", format="png", view=False)
    else:
        if os.getenv("DOCKER_ENV") == "1":
            out_path = "../output"
        diag.ExportSparta(out_path, anno["external_entities"])

    

if __name__ == '__main__':
    fire.Fire(main)
