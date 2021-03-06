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
from operator import attrgetter
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import QAction, QGraphicsScene, QGraphicsPixmapItem, QProgressBar, QFileDialog
from qgis.core import Qgis, QgsProject, QgsVectorLayer, QgsDataSourceUri

# Initialize Qt resources from file resources.py
from .resources import *

# Import the code for the DockWidget
from .terraindex_dockwidget import TerraIndexDockWidget
from .terraindex_login import TerraIndexLoginDialog
from .terraindex_borelog_request import TIBorelogRequest
from .terraindex_selection_tool import TISelectionTool
from .terraindex_layouts_request import layoutNamesRequest, layoutRequest

import os.path
import functools
import time

# Import for requests
import requests, base64
import xml.etree.ElementTree as ET
from io import BytesIO
import webbrowser


## Namespaces for the SOAP request/response
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
    """Login Wrapper to check if user credentialcheckTILainyinterAvailables are available or ask for the credentials."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):

        def credentialPull(self, dialog, func):
            success, results, username, licensenumber, applicationcode = dialog.getToken()

            if success is 1: ## clicked ok

                if results['ResultCode'] is 0:
                    
                    self.session_start_t = time.time()
                    self.token = results['Result']
                    self.errormessage = ''

                    self.username = username
                    self.licensenumber = licensenumber
                    self.applicationcode = applicationcode

                    self.authorisationBool = True
                    # evaluate the actual function
                    return func(self, *args, **kwargs)
                else:
                    ## connection failed


                    self.errormessage = results['Message']
                    dialog.message.setText(self.errormessage)


                    dialog.open()


            else: # Closed dialog any other way
                pass

        
        def setupCredentialsDialog(self):

            dialog = TerraIndexLoginDialog(message = self.errormessage)
            
            partialCredPull = functools.partial(credentialPull, self=self, dialog=dialog, func=func)

            dialog.finished.connect(partialCredPull)

            dialog.open()
        
        # Check if we have a token or the token expired (~1 hour)
        if self.token is None or time.time() - self.session_start_t > 3580:
            setupCredentialsDialog(self)
        else:
            return func(self, *args, **kwargs)


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

        self.TILayer = None
      
        self.token = None
        self.session_start_t = 0
        self.username = None
        self.licensenumber = None
        self.applicationcode = None
        self.errormessage = None

        self.layoutsDict = {}


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

    def initTILayer(self):

        #TO-DO: not to hardcode the username and password here
        uri = r"user='skemp' password='ikZKBDoVJv' maxNumFeatures='2000' pagingEnabled='true' preferCoordinatesForWfsT11='false' restrictToRequestBBOX='1' srsname='EPSG:4326' typename='ti-workspace:AllProjects_MeasurementPoints_pnt' url='https://gwr.geoserver.terraindex.com/geoserver/ti-workspace/ows' version='auto'"

        layers = QgsProject.instance().mapLayers()
        TILayer = None

        for layer in layers.values():

            src = QgsDataSourceUri(layer.source())


            if src.hasParam('url') and src.hasParam('typename'):
                if src.param('url') == 'https://gwr.geoserver.terraindex.com/geoserver/ti-workspace/ows' and src.param('typename') == 'ti-workspace:AllProjects_MeasurementPoints_pnt':
                    TILayer = layer
        
        if TILayer is None:
            TILayer = QgsVectorLayer(uri,'AllProjects_MeasurementPoints_pnt', 'WFS')
            TILayer.loadNamedStyle(os.path.join(self.plugin_dir, 'data', 'TerraIndexLayerStyle.qml'))
            QgsProject.instance().addMapLayer(TILayer)

        self.TILayer = TILayer
            

    # --------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        print('Closing TerraIndex')

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # reset maptool
        self.map_tool.removeAnnotations()
        self.iface.mapCanvas().unsetMapTool(self.map_tool)
        # set map tool to the previous one
        self.iface.mapCanvas().setMapTool(self.last_map_tool)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        # self.dockwidget = None_summary_

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
            self.map_tool = TISelectionTool(self.iface, self)
            self.last_map_tool = self.iface.mapCanvas().mapTool()
            self.iface.mapCanvas().setMapTool(self.map_tool)

    def getAuthorisationInfo(self):
        d = {
            'ApplicationCode': self.applicationcode,
            'Licensenumber': self.licensenumber,
            'Username': self.username,
        }
        return d

    @login
    def getBorelogImage(self, feature):
        
        fields = [field.name() for field in feature.fields()]

        req = ['ProjectID', 'MeasurementPointID']

        if set(req).issubset(fields):
            projectID = feature[req[0]]
            measurementPointID = feature[req[1]]
            #print(projectID)
            #print(measurementPointID)

            request = TIBorelogRequest(self, )

            request.addBorehole(measurementPointID, projectID)

            response = request.request()

            if response.status_code is not requests.codes.ok:
                
                self.iface.messageBar().pushMessage("Error", response.reason, level=Qgis.Critical)
            else:
                xml_content = ET.fromstring(response.content)

                bytes64 = xml_content.find('.//b:Content', ns).text

                bytes = base64.b64decode(bytes64)


                pixmap = QPixmap()
                pixmap.loadFromData(bytes, 'PNG')
                pmitem = QGraphicsPixmapItem(pixmap)
                scene = QGraphicsScene()
                scene.addItem(pmitem)
                self.dockwidget.graphicsView.setScene(scene)

        else:
            # show warning maybe
            self.iface.messageBar().pushMessage('Error', 'Kon geen ProjectID of MeasurementPointID in de features vinden. Heb je wel punten van de TerraIndex Laag geselecteerd?', level=Qgis.Warning)
    
    @login
    def getBorelogsPDF(self, features):

        boreholeid_list = []
        for feature in features:
            boreholeid_list.append({'ProjectID': feature['ProjectID'],
                                'BoreHoleID': feature['MeasurementPointID']})
        

        request = TIBorelogRequest(self, DrawMode='MultiPage', OutputType='PDF')

        for d in boreholeid_list:
            request.addBorehole(**d)

        
        filename, _ = QFileDialog.getSaveFileName(self.dockwidget, self.tr("Save PDF:"), 'borelogs', self.tr('pdf (*.pdf)') )

        response = request.request()
        if response.status_code is not requests.codes.ok:
            
            self.iface.messageBar().pushMessage("Error", response.reason, level=Qgis.Critical)
        else:
            print('response check true')
            xml_content = ET.fromstring(response.content)

            bytes64 = xml_content.find('.//b:Content', ns).text

            bytes = base64.b64decode(bytes64)

            with open(filename, 'wb') as f:
                f.write(bytes)

            webbrowser.open(filename)

    @login
    def updateLayoutNames(self):
        self.layoutsDict = layoutNamesRequest(self)
        for key, val in self.layoutsDict.items():
            ## adds the names as text to the combobox and layoutid as data
            self.dockwidget.CB_layout.addItem(val['TemplateName'], userData=key)
    
    @login
    def getLayout(self, id):
        return layoutRequest(self, TemplateID=id)
    
    def downloadPDF(self):
        features = self.TILayer.selectedFeatures()

        if len(features) > 0 :

            features2 = self.sortFeatures(features)
            self.getBorelogsPDF(features2) 

    def sortFeatures(self, features):

        def get_projectID(f):
            return f['ProjectID']

        def get_pointID(f):
            return f['MeasurementPointID'] 

        def sortProjectPoint(f):
            return (get_projectID(f), get_pointID(f)) 

        features2 = sorted(features, key=sortProjectPoint) 

        return features2

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
            self.dockwidget.PB_downloadpdf.clicked.connect(self.downloadPDF)
            self.dockwidget.PB_updateLayouts.pressed.connect(self.updateLayoutNames)

            # TODO: make querying layouts more inituitive
            # self.dockwidget.CB_layout.activated.connect(self.updateLayouts)
            # Load the layouts
            if self.layoutsDict == {}:
                self.updateLayoutNames()


            # initialize TISelectionTool
            self.setMapTool()
            self.initTILayer()


            # show the dockwidget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()



