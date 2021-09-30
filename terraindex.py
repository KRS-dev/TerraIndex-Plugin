# -*- coding: utf-8 -*-
"""
/***************************************************************************
 TerraIndex
                                 A QGIS plugin
 Links geotechnical information to the TerraIndex WFS layer.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2021-08-06
        git sha              : $Format:%H$
        copyright            : (C) 2021 by Gemeente Rotterdam
        email                : kevinschuurman98@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import QAction, QGraphicsScene, QGraphicsPixmapItem, QProgressBar

from qgis.gui import QgsMapTool, QgsMapToolIdentify
from qgis.core import QgsRectangle, QgsVectorLayer, QgsCredentials
# Initialize Qt resources from file resources.py
from .resources import *

# Import the code for the DockWidget
from .terraindex_dockwidget import TerraIndexDockWidget
from .terraindex_login import TerraIndexLoginDialog
import os.path
import functools

# Import for requests
import requests
import xml.etree.ElementTree as ET
import base64
from io import BytesIO
from PIL import Image

# Namespaces for the SOAP request
ns = {
    's': "http://www.w3.org/2003/05/soap-envelope",
    'a': "http://www.w3.org/2005/08/addressing",
    'terraindex': "https://wsterraindex.terraindex.com/ITWorks.TerraIndex/",
    'b': "http://schemas.datacontract.org/2004/07/ITWorks.BusinessEntities.Boreprofile",
    'i': "http://www.w3.org/2001/XMLSchema-instance",
    'c': "http://schemas.datacontract.org/2004/07/ITWorks.BusinessEntities.Authorisation"
}

## Defining to useful wrapper functions

def login(func):
    """Login Wrapper to check if user credentials are available or ask for the credentials."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):

        value = None
        if self.username is None or self.password is None or self.ln is None or self.ac is None:
            
            # Initialize the dialog for credentials
            dialog = TerraIndexLoginDialog(
                self.username, self.password, self.ln, self.ac)
            
            # Wait until Ok is clicked
            # .open() ._exec() do almost the same thing, forgot what the exact difference was 
            dialog._exec()

            (success, user, passwd, ln, ac) = dialog.getCredentials()
            print(success)

            if success is 1:
                self.username = user
                self.password = passwd
                self.ln = ln
                self.applicationcode = ac

                # evaluate the actual function
                value = func(self, *args, **kwargs)

        elif self.response_check is False:
            print('ask for cred after wrong entry')

            dialog = TerraIndexLoginDialog(
                self.username, self.password, self.ln, self.ac, self.errormessage)

            dialog._exec()

            (success, user, passwd, ln, ac) = dialog.getCredentials()
            print(success)

            if success is 1:
                self.username = user
                self.password = passwd
                self.ln = ln
                self.ac = ac
                value = func(self, *args, **kwargs)
        else:
            value = func(self, *args, **kwargs)

        return value

    return wrapper


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


## Main Class
class TerraIndex:
    """TerraIndex Plugin Implementation """

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'TerraIndex_{}.qm'.format(locale))

        # Setting up the translator, not used in plugin
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&TerraIndex')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'TerraIndex')
        self.toolbar.setObjectName(u'TerraIndex')

        # print "** INITIALIZING TerraIndex"
        self.map_tool = None

        self.borelog_parameters = {
            'PageNumber': '1',
            'Language': 'NL',
            'OutputType': 'PNG',
            'DrawMode': 'Single',
            'DrawKind': 'BoreHole',
            'Layout': None
        }

        self.username = None
        self.password = None
        self.ln = 613
        self.ac = 98
        self.response_check = True
        self.errormessage = None

        # Load in the layout file
        with open(os.path.join(self.plugin_dir, '4op1blad.ini')) as f:
            ini = f.read().replace('\n', '')
            self.borelog_parameters['Layout'] = ini

        self.pluginIsActive = False

        # Main widget ui reference, is instantiated in run()
        self.dockwidget = None

    # noinspection PyMethodMayBeStatic

    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('TerraIndex', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/terraindex/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Text for the menu item'),
            callback=self.run,
            parent=self.iface.mainWindow())

    # --------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        print('Closing TerraIndex')

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # reset maptool
        self.iface.mapCanvas().unsetMapTool(self.map_tool)
        # set map tool to the previous one
        self.iface.mapCanvas().setMapTool(self.last_map_tool)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        # self.dockwidget = None

        self.pluginIsActive = False

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        # print "** UNLOAD TerraIndex"

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&TerraIndex'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    # --------------------------------------------------------------------------

    def setMapTool(self):

        if type(self.iface.mapCanvas().mapTool()) is type(self.map_tool) and self.map_tool is not None:
            print('type=type')
        else:
            self.map_tool = PointTool(self.iface, self.iface.mapCanvas(), self)
            self.last_map_tool = self.iface.mapCanvas().mapTool()
            self.iface.mapCanvas().setMapTool(self.map_tool)

    @login
    def getBorelogImage(self, feature):
        
        fields = [field.name() for field in feature.fields()]

        req = ['ProjectID', 'MeasurementPointID']

        if set(req).issubset(fields):
            projectID = feature[req[0]]
            measurementPointID = feature[req[1]]
            #print(projectID)
            #print(measurementPointID)

            request = BorelogRequest(self)

            request.addBorehole(measurementPointID, projectID)

            response, image = request.request()

            if response.status_code is not requests.codes.ok:
                print('set false')
                self.response_check = False
                self.errormessage = response.reason
            else:
                self.response_check = True
                self.errormessage = None
                pixmap = QPixmap()
                pixmap.loadFromData(image.bytes, 'PNG')
                pmitem = QGraphicsPixmapItem(pixmap)
                scene = QGraphicsScene()
                scene.addItem(pmitem)
                self.dockwidget.graphicsView.setScene(scene)

        else:
            # show warning maybe
            pass

    def run(self):
        """Run method that loads and starts the plugin"""

        if not self.pluginIsActive:
            self.pluginIsActive = True

            # print "** STARTING TerraIndex"

            # dockwidget may not exist if:
            #    first run of plugin
            #    removed on close (see self.onClosePlugin method)
            if self.dockwidget == None:
                # Create the dockwidget (after translation) and keep reference
                self.dockwidget = TerraIndexDockWidget()

            # connect to provide cleanup on closing of dockwidget
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)
            self.dockwidget.PB_boreprofile.clicked.connect(self.setMapTool)
            # initialize pointtool
            self.setMapTool()

            # show the dockwidget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()



class PointTool(QgsMapToolIdentify):
    """Pointtool class, which overwrites the normal cursor during use of the plugin"""
    def __init__(self, iface, canvas, plugin):
        QgsMapToolIdentify.__init__(self, canvas)

        self.canvas = canvas
        self.iface = iface
        self.plugin = plugin

        self.selected_feature = None
        # QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def canvasPressEvent(self, event):
        pass

    def canvasMoveEvent(self, event):
        pass

    def canvasReleaseEvent(self, event):
        found_features = self.identify(event.x(), event.y(),
                                       self.TopDownStopAtFirst,
                                       self.VectorLayer)

        if len(found_features) > 0:
            layer = found_features[0].mLayer
            feature = found_features[0].mFeature
            layer.removeSelection()
            layer.select(feature.id())
            self.setSelectedFeature(feature)
        else:
            for layer in self.canvas.layers():
                if layer.type() == layer.VectorLayer:
                    layer.removeSelection()
            self.unsetSelectedFeature()

    def setSelectedFeature(self, feature):
        self.selected_feature = feature
        self.plugin.getBorelogImage(feature)

    def unsetSelectedFeature(self):
        self.selected_feature = None

    def getSelectedFeature(self):
        return self.selected_feature

    def isZoomTool(self):
        return False

    def isTransient(self):
        return False

    def isEditTool(self):
        return False


## 

class BorelogRequest:
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

    def addBorehole(self, boreHoleID, projectID):
        self.boreholes.append(
            {'BoreHoleID': str(boreHoleID), 'ProjectID': str(projectID)})

    def getAuthorisationInfo(self):
        d = {
            'ApplicationCode': self.ac,
            'Licensenumber': self.ln,
            'Username': self.username,
            'Password': self.password,
        }
        return d

    def setXMLparameters(self):

        xmlfile = os.path.join(self.plugin.plugin_dir,
                               'Borelog_Request_SOAP.xml')

        with open(xmlfile, 'r') as f:
            xml_base = f.read()

        root = ET.fromstring(xml_base)

        for key, val in self.getAuthorisationInfo().items():
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
