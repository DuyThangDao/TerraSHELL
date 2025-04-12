import xml.etree.ElementTree as ET
import os
import json

# <?xml version="1.0" encoding="UTF-8"?>
# <spartamodel:ThreatTypeCatalog xmi:version="2.0" xmlns:xmi="http://www.omg.org/XMI" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:spartamodel="http://distrinet.cs.kuleuven.be/spartamodel" xmi:id="_wtbg4N0UEe2919UI-pqpPA">
#   <threat xsi:type="spartamodel:ThreatType" xmi:id="_DbwoQN0VEe2919UI-pqpPA" name="Unauthorized access to functionality" title="">
#     <patterns xmi:id="_6bahwN0XEe2919UI-pqpPA" key="ExternalEntityToProcess" value="true"/>
#     <patterns xmi:id="_OEw9wN1WEe2iR-CLQYlzAQ" key="ProcessToExternalEntity" value="true"/>
#   </threat>
#   <threat xsi:type="spartamodel:ThreatType" xmi:id="_ZqQaMN1WEe2iR-CLQYlzAQ" name="Unauthorized access to sensitive data">
#     <patterns xmi:id="_gAbSEN1WEe2iR-CLQYlzAQ" key="ExternalEntityToProcess" value="true"/>
#     <patterns xmi:id="_nii_sN1WEe2iR-CLQYlzAQ" key="ProcessToExternalEntity" value="true"/>
#     <patterns xmi:id="_9A4JgN1WEe2iR-CLQYlzAQ" key="ProcessToDataStore" value="true"/>
#     <patterns xmi:id="_IDOcoN1XEe2iR-CLQYlzAQ" key="ExternalEntityToDataStore" value="true"/>
#   </threat>
#   <threat xsi:type="spartamodel:ThreatType" xmi:id="_M_F5sN1XEe2iR-CLQYlzAQ" name="Privacy Leakage">
#     <patterns xmi:id="_QEwqIN1XEe2iR-CLQYlzAQ" key="ProcessToExternalEntity" value="true"/>
#   </threat>
#   <threat xsi:type="spartamodel:ThreatType" xmi:id="_TQXDcN1XEe2iR-CLQYlzAQ" name="Injection Attack">
#     <patterns xmi:id="_T96F8N1XEe2iR-CLQYlzAQ" key="ExternalEntityToProcess" value="true"/>
#     <patterns xmi:id="_T96F8d1XEe2iR-CLQYlzAQ" key="ProcessToExternalEntity" value="true"/>
#     <patterns xmi:id="_hnm10N1XEe2iR-CLQYlzAQ" key="ProcessToDataStore" value="true"/>
#     <patterns xmi:id="_inaF8N1XEe2iR-CLQYlzAQ" key="ExternalEntityToDataStore" value="true"/>
#   </threat>
#   <threat xsi:type="spartamodel:ThreatType" xmi:id="_ZjDJgN1XEe2iR-CLQYlzAQ" name="Component Hijacking">
#     <patterns xmi:id="_cBfh4N1XEe2iR-CLQYlzAQ" key="ExternalEntityToProcess" value="true"/>
#     <patterns xmi:id="_cBfh4d1XEe2iR-CLQYlzAQ" key="ProcessToExternalEntity" value="true"/>
#     <patterns xmi:id="_g238cN1XEe2iR-CLQYlzAQ" key="ProcessToDataStore" value="true"/>
#   </threat>
#   <threat xsi:type="spartamodel:ThreatType" xmi:id="_-iU4sN1XEe2iR-CLQYlzAQ" name="Eavesdropping or interception of sensitive data in communication">
#     <patterns xmi:id="_CTiggN1YEe2iR-CLQYlzAQ" key="ExternalEntityToProcess" value="true"/>
#     <patterns xmi:id="_D4570N1YEe2iR-CLQYlzAQ" key="ProcessToDataStore" value="true"/>
#     <patterns xmi:id="_Fry1wN1YEe2iR-CLQYlzAQ" key="ProcessToExternalEntity" value="true"/>
#   </threat>
#   <threat xsi:type="spartamodel:ThreatType" xmi:id="_HcTKEN1YEe2iR-CLQYlzAQ" name="Man-in-the-middle attacks">
#     <patterns xmi:id="_NGPOEN1YEe2iR-CLQYlzAQ" key="ProcessToExternalEntity" value="true"/>
#     <patterns xmi:id="_PsxygN1YEe2iR-CLQYlzAQ" key="ExternalEntityToProcess" value="true"/>
#   </threat>
#   <threat xsi:type="spartamodel:ThreatType" xmi:id="_Rh12sN1YEe2iR-CLQYlzAQ" name="Denial-of-service attacks">
#     <patterns xmi:id="_UOUrEN1YEe2iR-CLQYlzAQ" key="ExternalEntityToProcess" value="true"/>
#     <patterns xmi:id="_VoNPIN1YEe2iR-CLQYlzAQ" key="ProcessToExternalEntity" value="true"/>
#   </threat>
# </spartamodel:ThreatTypeCatalog>

def change_name(name):
    if name == 'ExternalService':
        return 'ExternalEntity'
    elif name == 'CloudApplication':
        return 'Process'
    elif name == 'Process':
        return 'Process'
    elif name == 'HostStorage':
        return 'DataStore'
    elif name == 'RemoteUser':
        return 'ExternalEntity'
    elif name == 'ComplianceManager':
        return 'ExternalEntity'
    else:
        print(name)
        return name

def mapping(name: str):
    proc = ["Container", "CloudApplication", "VirtualMachine", "ContainerSocket"]
    ee = ["ComplianceManager", "RemoteUser", "ExternalService"]
    ds = ["HostStorage", "ContainerVolume"]

    if name in proc:
        return "Process"
    elif name in ee:
        return "ExternalEntity"
    elif name in ds:
        return "DataStore"
    else:
        print("????", name)
        return ""

"""

<?xml version="1.0" encoding="UTF-8"?>
<spartamodel:ThreatTypeCatalog xmi:version="2.0" xmlns:xmi="http://www.omg.org/XMI" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:spartamodel="http://distrinet.cs.kuleuven.be/spartamodel" xmi:id="_MDqvUOlNEe6U0rTVRqWvTg" name="IaC Threat Type">
  <imports>import &quot;http://distrinet.cs.kuleuven.be/spartamodel&quot;</imports>
  <threat xsi:type="spartamodel:ThreatType" xmi:id="_N8y0IOlNEe6U0rTVRqWvTg" name="Spoofing" description="This is an example">
    <threatpattern xmi:id="_VMcRsOlNEe6U0rTVRqWvTg" name="Spoofing Type 1" description="This is the spoofing by &lt;$p$>">
      <patterns>pattern Spoofing(ee: ExternalEntity, p: Process, df:DataFlow ) { 

"""

"""
<?xml version="1.0" encoding="UTF-8"?>
    <spartamodel:ThreatTypeCatalog xmi:version="2.0" xmlns:xmi="http://www.omg.org/XMI" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:spartamodel="http://distrinet.cs.kuleuven.be/spartamodel" name="IaC Threat Type">
    <imports>import &quot;http://distrinet.cs.kuleuven.be/spartamodel&quot;</imports>
    <threat xsi:type="spartamodel:ThreatType" name="Spoofing" description="This is an example">
        <threatpattern name="Spoofing Type 1" description="">
            <patterns>
            pattern Spoofing(ee: ExternalEntity, p: Process, df:DataFlow ) { 
                ModelElementAnnotation(a1);
                ModelElementAnnotation.value(a1, &quot;CloudApplication&quot;);
                Process.annotations(p, a1);

                ModelElementAnnotation(a2);
                ModelElementAnnotation.value(a2, &quot;RemoteUser&quot;);
                ExternalEntity.annotations(ee, a2);

                DataFlow.sender(df, ee);
                DataFlow.recipient(df, p);
            }
            </patterns>
            <mapping key="location" value="p"/>
            <mapping key="flow" value="df"/>
        </threatpattern>
    </threat>
    </spartamodel:ThreatTypeCatalog>
"""

template_0 = """<?xml version="1.0" encoding="UTF-8"?>
    <spartamodel:ThreatTypeCatalog xmi:version="2.0" xmlns:xmi="http://www.omg.org/XMI" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:spartamodel="http://distrinet.cs.kuleuven.be/spartamodel" name="IaC Threat Type">
    <imports>import &quot;http://distrinet.cs.kuleuven.be/spartamodel&quot;</imports>
    %s
    </spartamodel:ThreatTypeCatalog>

"""

template_1 = """
    <threat xsi:type="spartamodel:ThreatType" name="%s" description="%s">
    %s
    </threat>
"""

template_2 = """
        <threatpattern name="{0}" description="{1}">
            <patterns>pattern {6}(ee: {2}, p: {3}, df:DataFlow ) {{ 
                ModelElementAnnotation(a1);
                ModelElementAnnotation.value(a1, &quot;{5}&quot;);
                {3}.annotations(p, a1);

                ModelElementAnnotation(a2);
                ModelElementAnnotation.value(a2, &quot;{4}&quot;);
                {2}.annotations(ee, a2);

                DataFlow.sender(df, ee);
                DataFlow.recipient(df, p);
            }}</patterns>
            <mapping key="location" value="p"/>
            <mapping key="flow" value="df"/>
        </threatpattern>
"""
template_2_no_send_anno = """
        <threatpattern name="{0}" description="{1}">
            <patterns>pattern {6}(ee: {2}, p: {3}, df:DataFlow ) {{ 
                ModelElementAnnotation(a1);
                ModelElementAnnotation.value(a1, &quot;{5}&quot;);
                {3}.annotations(p, a1);

                {2}(ee);

                DataFlow.sender(df, ee);
                DataFlow.recipient(df, p);
            }}</patterns>
            <mapping key="location" value="p"/>
            <mapping key="flow" value="df"/>
        </threatpattern>
"""
template_2_no_recv_anno = """
        <threatpattern name="{0}" description="{1}">
            <patterns>pattern {6}(ee: {2}, p: {3}, df:DataFlow ) {{ 
                ModelElementAnnotation(a1);
                ModelElementAnnotation.value(a1, &quot;{5}&quot;);
                {3}.annotations(p, a1);

                {2}(ee);

                DataFlow.sender(df, ee);
                DataFlow.recipient(df, p);
            }}</patterns>
            <mapping key="location" value="p"/>
            <mapping key="flow" value="df"/>
        </threatpattern>
"""

counter = 0

def threat_pattern(name: str, desc: str, annoFrom: str, annoTo: str):
    global counter
    counter += 1
    typeFrom = mapping(annoFrom)
    typeTo = mapping(annoTo)
    # print(name, desc, typeFrom, typeTo, annoFrom, annoTo)
    return template_2.format(name, desc, typeFrom, typeTo, annoFrom, annoTo, f"Pattern_{counter}")

def threat(type, threats):
    res = ""

    r2 = ""

    for name, desc, attackers, victims in threats:
        t = ""
        for atk, vic in zip(attackers, victims):
            t += threat_pattern("", "", atk, vic)
        r2 += template_1 % (type + ": " + name, desc, t)
    return r2
    # return template_1 % (type, res)

def get_xml(m):
    res = ""
    for type, threats in m.items():
        res += threat(type, threats)
    return template_0 % res

def statistic():
    m = {}
    r = []
    for file_name in os.listdir('catalog'):
        if file_name.endswith('.json'):
            with open(os.path.join('catalog', file_name), 'r') as f:
                data = json.load(f)
                strd = data["security"]["ns:hasSTRIDE"]
                r += data["security"]["ns:hasAggressor"] + data["context"]["ns:hasAffectedComponent"]
                print(strd)
                if len(strd) in m:
                    m[len(strd)] += 1
                else:
                    m[len(strd)] = 0
                
    print(m)
    print(set(r))
statistic()

def generate():
    m = {}
    m["Other"] = []
    m["Denial of Service"] = []
    m["Information Disclosure"] = []
    m["Tampering"] = []
    m["Elevation of Privilege"] = []
    m["Spoofing"] = []
    m["Repudiation"] = []
    for file_name in os.listdir("catalog"):
        if file_name.endswith('.json'):
            with open(os.path.join('catalog', file_name), 'r') as f:
                data = json.load(f)
                name = ' '.join(data["metadata"]["ns:textName"].split(" ")[1:])
                desc = data["metadata"]["ns:textReviewProblem"]
                strds = data["security"]["ns:hasSTRIDE"]
                attackers = list(map(lambda x: x.split("_")[1], data['security']['ns:hasAggressor']))
                victims = list(map(lambda x: x.split("_")[1], data['context']['ns:hasAffectedComponent']))
                
                group = (name, desc, attackers, victims)
                
                if len(strds) == 0:
                    m["Other"].append(group)
                else:
                    for strd in strds:
                        strd = ' '.join(strd.split("_")[1:])
                        m[strd].append(group)
                pass
    with open("output.xml", "w") as f:
        f.write(get_xml(m))
    # print(get_xml(m))
    pass

generate()
