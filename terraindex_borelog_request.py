import requests, os, base64
import xml.etree.ElementTree as ET
import functools


from qgis.PyQt.QtWidgets import QProgressBar





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

        bar = QProgressBar()
        bar.setRange(0, 0)

        self.iface.mainWindow().statusBar().insertWidget(1, bar)

        value = func(self, *args, **kwargs)

        self.iface.mainWindow().statusBar().removeWidget(bar)

        return value

    return wrapper


def testconnection(plugin) -> requests.Response:
    """Test request for login parameters

    Parameters
    ----------
    plugin : TerraIndex
        plugin class reference for credentials

    Returns
    -------
    requests.Response
        Response object for response codes
    """


    request = TIBorelogRequest(plugin)
    request.addBorehole(48, 11437)

    response, _ = request.request()

    return response




class TIBorelogRequest:
    """Request class for the SOAP requests to the servers."""

    def __init__(self, plugin):
        self.plugin = plugin
        self.iface = plugin.iface

        self.username = plugin.username
        self.password = plugin.password
        self.ln = plugin.ln
        self.ac = plugin.ac

        self.borelogParameters = plugin.borelog_parameters

        # TO-DO: availability for multiple boreholes
        self.boreholes = []

        self.xml = None

    def addBorehole(self, boreHoleID: int, projectID: int):
        self.boreholes.append(
            {'BoreHoleID': str(boreHoleID), 'ProjectID': str(projectID)})

    def setXMLparameters(self):

        xmlfile = os.path.join(self.plugin.plugin_dir, 'data',
                               'Borelog_Request_SOAP.xml')

        with open(xmlfile, 'r') as f:
            xml_base = f.read()

        root = ET.fromstring(xml_base)

        for key, val in self.plugin.getAuthorisationInfo().items():
            print(key, val)
            elem = root.find('.//c:{}'.format(key), ns)
            elem.text = str(val)

        for key, val in self.borelogParameters.items():
            elem = root.find('.//b:{}'.format(key), ns)
            elem.text = str(val)

        assert len(self.boreholes) > 0, 'no boreholes selected'

        # TO-DO: adding multiple boreholes
        for key, val in self.boreholes[0].items():
            elem = root.find('.//b:{}'.format(key), ns)
            elem.text = str(val)

        self.xml = ET.tostring(root, encoding='unicode')

    @loadingbar
    def request(self):

        if self.xml is None:
            self.setXMLparameters()

        url = 'https://web.terraindex.com/DataWS/ITWBoreprofileService_V1_0.svc?singleWsdl'

        headers = {'content-type': 'application/soap+xml'}
        
        print(self.xml) 

        response = requests.post(url=url, data=self.xml, headers=headers)
        image = None

        if response.status_code is requests.codes.ok:
            content = response.content
            root_content = ET.fromstring(content)

            bytes64 = root_content.find('.//b:Content', ns).text
            image = BoreHoleImage(bytes64=bytes64, **self.boreholes[0])

        return response, image


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
