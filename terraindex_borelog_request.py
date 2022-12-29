import gzip
import requests
import os
import base64
import json
import xml.etree.ElementTree as ET
import functools

from qgis.PyQt.QtWidgets import QProgressDialog

from typing import List, Tuple, Dict
from qgis.core import Qgis

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
    """Loading bar decorator TODO freezes as gui

    
    """    
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):

        # TODO: Fix progress dialog, it does not show.
        progress = QProgressDialog("Querying TerraIndex...", "Cancel",
                                   0, 0, parent=self.iface.mainWindow(), minimumDuration=0)
        progress.open()

        value = func(self, *args, **kwargs)

        progress.reset()

        return value

    return wrapper


class BorelogRequest:
    """Request class for the SOAP requests to the servers.

    Returns
    -------
    request.Response
        Soap request response from ITWBoreprofileService_V1_0.svc.
    """

    def __init__(self, plugin: 'TerraIndex', **kwargs):
        """
        Parameters
        ----------
        plugin : TerraIndex
        """        
        self.plugin = plugin
        self.iface = plugin.iface

        self.url = 'https://web.terraindex.com/DataWSExternals/ITWBoreprofileService_V1_0.svc?singleWsdl'

        self.borelogParameters = {
            'PageNumber': kwargs.get('PageNumber', '1'),
            'Language': kwargs.get('Language', 'NL'),
            'OutputType': kwargs.get('OutputType', 'PNG'),   # BMP, WMF, EMF, JPG, PNG, DXF, PDF, GEF, TIFF
            'DrawMode': kwargs.get('DrawMode', 'Single'),    # Single, Multipage, Page
            'DrawKind': kwargs.get('DrawKind', 'BoreHole'),  # BoreHole, Legend
            'LayoutName': '',
            'Layout': None
        }

        self.checkLayoutTemplate()

        self.boreholes = []
        self.xml = None

    def addBorehole(self, BoreHoleID: int, ProjectID: int, **kwargs):

        d = {'BoreHoleID': str(BoreHoleID), 'ProjectID': str(ProjectID)}

        for key, val in kwargs.items():
            d[key] = str(val)

        self.boreholes.append(d)

    def checkLayoutTemplate(self):
        # Load in the layout file
        if self.plugin.layoutsDict == {} or not isinstance(self.plugin.layoutsDict, dict):
            # Backup template
            with open(os.path.join(self.plugin.plugin_dir, 'data', r'depots 4 blad.txt'), encoding='utf8') as f:
                ini = f.read()
                self.borelogParameters['Layout'] = ini

            self.borelogParameters['LayoutName'] = 'depots 4 blad'
        else:
            layoutID = self.plugin.dockwidget.CB_layout.currentData()
            layout = self.plugin.layoutsDict[layoutID]

            self.borelogParameters['Layout'] = self.plugin.getLayout(layoutID)
            self.borelogParameters['LayoutName'] = layout['TemplateName']

        # if self.borelogParameters['DrawKind'] == 'CrossSection':

        #     layout = self.borelogParameters['Layout']
        #     PageOrientation = layout.split('PageOrientation=')[
        #         1].split(r'\n')[0]
        #     if not PageOrientation == 'poLandscape':
        #         self.iface.messageBar().pushMessage('Warning', 'Layouts in portretmodus zijn niet aan te raden voor dwarsdoorsnedes.', level=Qgis.Warning)
        #         #TODO load other layout that is in landscape, give off warning

    def setXMLparameters(self):

        # Open the xml request blueprint
        xmlfile = os.path.join(self.plugin.plugin_dir, 'data',
                               'Borelog_Request_SOAP.xml')

        with open(xmlfile, 'r') as f:
            xml_base = f.read()

        root = ET.fromstring(xml_base)

        authorisationParameters = {
            'Username': self.plugin.username,
            'ApplicationCode': self.plugin.applicationcode,
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
            for key, val in borehole_dict.items():
                a = ET.SubElement(b, "{" + ns['b'] + "}" + key)
                a.text = val

        self.xml = ET.tostring(root)


    @loadingbar
    def request(self) -> requests.Response:

        if self.xml is None:
            self.setXMLparameters()

        token = self.plugin.token

        headers = {'content-type': 'application/soap+xml',
                   'Authorization': 'Bearer {}'.format(token)
                   }

        response = requests.post(url=self.url, data=self.xml, headers=headers)
        return response


class BoreholeDataRequest:

    def __init__(self, plugin: 'TerraIndex'):
        self.plugin = plugin
        self.iface = plugin.iface

        self.boreholes = []

    def addBorehole(self, BoreHoleID: int, ProjectID: int):
        self.boreholes.append(
            {'BoreHoleID': str(BoreHoleID), 'ProjectID': str(ProjectID)})

    @loadingbar
    def request(self) -> Tuple[requests.Response, List[Dict]]:
        if self.boreholes:
            url = 'https://web.terraindex.com/DataWSExternals/ITWViewRestService_V1_0/GetQuerryResponse'
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer {}'.format(self.plugin.token),
            }
            authorisation = self.plugin.getAuthorisationInfo()
            authorisation['Language'] = "nl"

            data = []
            for borehole in self.boreholes:

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
                    "ViewName": "QGIS.Borehole.Layers"
                }

                response = requests.post(
                    url=url, headers=headers, data=json.dumps(body))

                if response.status_code is not requests.codes.ok:
                    print(response.text)
                    response.raise_for_status()

                else:
                    content = json.loads(response.content)['Content']

                    data.extend(json.loads(gzip.decompress(
                        base64.b64decode(content)))['Table'])

            return response, data
