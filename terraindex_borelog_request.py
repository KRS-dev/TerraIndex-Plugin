import gzip
import requests
import os
import base64
import json
import xml.etree.ElementTree as ET
import functools


from qgis.PyQt.QtWidgets import QProgressDialog
# from qgis.PyQt

# Namespaces for the SOAP request
ns = {
    's': "http://www.w3.org/2003/05/soap-envelope",
    'a': "http://www.w3.org/2005/08/addressing",
    'terraindex': "https://wsterraindex.terraindex.com/ITWorks.TerraIndex/",
    'b': "http://schemas.datacontract.org/2004/07/ITWorks.BusinessEntities.Boreprofile",
    'i': "http://www.w3.org/2001/XMLSchema-instance",
    'c': "http://schemas.datacontract.org/2004/07/ITWorks.BusinessEntities.Authorisation"
}


def loadingbar(func):

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        

        ## TODO: Fix progress dialog, it does not show.
        progress = QProgressDialog("Querying TerraIndex...", "Cancel", 0,0, parent=self.iface.mainWindow(), minimumDuration=0)
        progress.open()
        # progress.setWindowModality()


        value = func(self, *args, **kwargs)

        progress.reset()


        return value

    return wrapper


# def testconnection(plugin) -> requests.Response:
#     """Test request for login parameters

#     Parameters
#     ----------
#     plugin : TerraIndex
#         plugin class reference for credentials

#     Returns
#     -------
#     requests.Response
#         Response object for response codes
#     """

#     request = BorelogRequest(plugin)
#     request.addBorehole(48, 11437)

#     response = request.request()

#     return response


class BorelogRequest:
    """Request class for the SOAP requests to the servers.

    Returns
    -------
    _type_
        _description_
    """    

    

    def __init__(self, plugin, **kwargs):
        """_summary_

        Parameters
        ----------
        plugin : _type_
            _description_
        """        
        self.plugin = plugin
        self.iface = plugin.iface

        # self.username = kwargs.get('username', plugin.username)
        # self.password = kwargs.get('password', plugin.password)
        # self.ln = kwargs.get('licensenumber', plugin.ln)
        # self.ac = kwargs.get('applicationcode', plugin.ac)

        self.borelogParameters = {
            'PageNumber': kwargs.get('PageNumber', '1'),
            'Language': kwargs.get('Language', 'NL'),
            # BMP, WMF, EMF, JPG, PNG, DXF, PDF, GEF, TIFF
            'OutputType': kwargs.get('OutputType', 'PNG'),
            'DrawMode': kwargs.get('DrawMode', 'Single'), # Single, Multipage, Page
            'DrawKind': kwargs.get('DrawKind', 'BoreHole'),  # BoreHole, Legend
            'LayoutName': '',
            'Layout' : None
        }

        # Load in the layout file
        if self.plugin.layoutsDict == {} or not isinstance(self.plugin.layoutsDict, dict):        
            with open(os.path.join(self.plugin.plugin_dir, 'data', r'depots 4 blad.txt'), encoding='utf8') as f:
                ini = f.read()
                self.borelogParameters['Layout'] = ini
            
            self.borelogParameters['LayoutName'] = 'depots 4 blad'
        else:
            layoutID = self.plugin.dockwidget.CB_layout.currentData()
            layout = self.plugin.layoutsDict[layoutID]

            self.borelogParameters['Layout'] = self.plugin.getLayout(layoutID)
            self.borelogParameters['LayoutName'] = layout['TemplateName']

        
        self.boreholes = []
        self.xml = None

    def addBorehole(self, BoreHoleID: int, ProjectID: int):
        self.boreholes.append(
            {'BoreHoleID': str(BoreHoleID), 'ProjectID': str(ProjectID)})

    def setXMLparameters(self):

        # Open the xml request blueprint
        xmlfile = os.path.join(self.plugin.plugin_dir, 'data',
                               'Borelog_Request_SOAP.xml')

        with open(xmlfile, 'r') as f:
            xml_base = f.read()

        root = ET.fromstring(xml_base)

        
        authorisationParameters ={
            'Username' : self.plugin.username,
            'ApplicationCode' : self.plugin.applicationcode,
            'Licensenumber': self.plugin.licensenumber
        }

        for key, val in authorisationParameters.items():
            elem = root.find('.//c:{}'.format(key), ns)
            elem.text = str(val)

        for key, val in self.borelogParameters.items():
            elem = root.find('.//b:{}'.format(key), ns)
            elem.text = val

        assert len(self.boreholes) > 0, 'no boreholes selected'

        # append new element for each borehole
        elem_boreholes = root.find('.//b:Boreholes', ns)
        for borehole_dict in self.boreholes:
            b = ET.SubElement(elem_boreholes, "{" + ns['b'] + "}Borehole")
            BoreHoleID = ET.SubElement(b, "{" + ns['b'] + "}BoreHoleID")
            ProjectID = ET.SubElement(b, "{" + ns['b'] + "}ProjectID")
            BoreHoleID.text = borehole_dict['BoreHoleID']
            ProjectID.text = borehole_dict['ProjectID']

        self.xml = ET.tostring(root)

        # print(self.xml)

    @loadingbar
    def request(self):

        if self.xml is None:
            self.setXMLparameters()

        url = 'https://web.terraindex.com/DataWSExternals/ITWBoreprofileService_V1_0.svc?singleWsdl'

        token = self.plugin.token

        headers = {'content-type': 'application/soap+xml',
            'Authorization' : 'Bearer {}'.format(token) 
        }

        response = requests.post(url=url, data=self.xml, headers=headers)
        # image = None

        # if response.status_code is requests.codes.ok:
        #     content = response.content
        #     root_content = ET.fromstring(content)

        #     bytes64 = root_content.find('.//b:Content', ns).text

        #     image = BoreHoleImage(bytes64=bytes64, **self.boreholes[0])

        # print(response)
        # print(response.content)

        return response


class BoreholeDataRequest:
    

    def __init__(self, plugin):


        self.plugin = plugin
        self.iface = plugin.iface

        self.boreholes = []
    
    def addBorehole(self, BoreHoleID: int, ProjectID: int):
        self.boreholes.append(
            {'BoreHoleID': str(BoreHoleID), 'ProjectID': str(ProjectID)})
    

    @loadingbar
    def request(self):

        if self.boreholes:

            data = []
            for borehole in self.boreholes:
                url = 'https://web.terraindex.com/DataWSExternals/ITWViewRestService_V1_0/GetQuerryResponse'

                headers = {
                    'Content-Type': 'application/json',
                    'Authorization' : 'Bearer {}'.format(self.plugin.token),
                }

                authorisation = self.plugin.getAuthorisationInfo()

                authorisation['Language'] = "nl"

                param = {"LANGUAGECODE": "nld",
                    "PROJECTID": str(borehole['ProjectID']),
                    "IDBOORPUNT": str(borehole['BoreHoleID'])}

                body = {
                    "Authorisation": authorisation,
                    "LanguageCode": "nld",
                    "WebserviceVersion": "1.0",
                    "UseZipStream": True,
                    "DataType": "JSON",
                    "Param": json.dumps(param),
                    "ViewName":"QGIS.Borehole.Layers"
                }


                response = requests.post(url = url, headers=headers, data=json.dumps(body))

                content = json.loads(response.content)['Content']

                data.extend(json.loads(gzip.decompress(base64.b64decode(content)))['Table'])
        
            return data
    






class BoreHoleImage:
    """Simple class to keep the image together with the boreholeID and projectID."""

    def __init__(self,  BoreHoleID, ProjectID, bytes64=None):
        self.id = BoreHoleID    
        self.projectID = ProjectID
        self.bytes = base64.b64decode(bytes64)

        # with BytesIO(self.bytes) as stream:
        #     self.image = Image.open(stream).convert("RGBA")

    # def show(self):
    #     self.image.show()
