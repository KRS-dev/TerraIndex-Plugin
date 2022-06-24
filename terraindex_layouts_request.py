import requests
import xml.etree.ElementTree as ET
import os

ns_req = {
    'soap' : "http://www.w3.org/2003/05/soap-envelope",
    'lib' : "https://wsterraindex.terraindex.com/Library/",
    'itw' : "http://schemas.datacontract.org/2004/07/ITWorks.BusinessEntities.FieldTemplate",
    'itw1' : "http://schemas.datacontract.org/2004/07/ITWorks.BusinessEntities.Authorisation",
}

ns_res = {
    'ns0':"http://www.w3.org/2003/05/soap-envelope",
    'ns1' :"http://www.w3.org/2005/08/addressing",
    'ns2' :"https://wsterraindex.terraindex.com/Library/",
    'ns3' :"http://schemas.datacontract.org/2004/07/ITWorks.BusinessEntities.FieldTemplate",
    'xsi':"http://www.w3.org/2001/XMLSchema-instance"
}

def layoutsRequest(TIPlugin, LayoutType = 2):
    """_summary_

    Parameters
    ----------
    TIPlugin : Terraindex
        Reference to the main plugin class
    LayoutType : int, optional
        Integer specifying layouttype, by default 2 for borelog type

    Returns
    -------
    dict
        Dictionary of different TerraIndex layouts with layoutType
    """    


    xmlfile = os.path.join(TIPlugin.plugin_dir, 'data',
                               'GetFieldTemplates.xml')
    tree = ET.parse(xmlfile)
    root = tree.getroot()

    for key, val in TIPlugin.getAuthorisationInfo().items():
        elem = root.find('.//itw1:{}'.format(key), ns_req)
        elem.text = val


    xml = ET.tostring(root, encoding='unicode')


    url = 'https://web.terraindex.com/LibraryWS/ITWFieldTemplateService_V1_0.svc'


    token = TIPlugin.token

    headers = {
        'content-type': 'application/soap+xml',
        'Authorization' : 'Bearer {}'.format(token) 
    }


    r = requests.post(url=url, data=xml, headers=headers)
    r.raise_for_status()



    content = r.content ### XML file in the form of a string
    root_content = ET.fromstring(content) # Read in the xml

    templatelist = root_content.find('.//ns3:TemplateList', ns_res)
    templateDict = {}

    for template in templatelist:

        TemplateType = template.find('.//ns3:TemplateType', ns_res)

        
        if int(TemplateType.text) == LayoutType or LayoutType is None:
            TemplateID = template.find('.//ns3:TemplateID', ns_res)
            TemplateName = template.find('.//ns3:TemplateName', ns_res)
            TemplateFile = template.find('.//ns3:TemplateFile', ns_res)

            templateDict[TemplateID.text] = {
                'TemplateName': TemplateName.text,
                'TemplateFile': TemplateFile.text,
                'TemplateType': TemplateType.text
            }

    return templateDict

