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
from qgis.PyQt.QtGui import QIcon, QPixmap, QStandardItemModel, QStandardItem
from qgis.PyQt.QtWidgets import QAction, QGraphicsScene, QGraphicsPixmapItem, QProgressBar, QFileDialog
from qgis.core import Qgis, QgsProject, QgsVectorLayer, QgsFeature, QgsDataSourceUri
from qgis.gui import QgsMapTool, QgisInterface

# Initialize Qt resources from file resources.py
from .resources import *

# Import the code for the DockWidget
from .terraindex_dockwidget import TerraIndexDockWidget
from .terraindex_login import TerraIndexLoginDialog
from .terraindex_borelog_request import BoreholeDataRequest, BorelogRequest
from .terraindex_selection_tool import TISelectionTool
from .terraindex_crosssection_tool import TICrossSectionTool
from .terraindex_layouts_request import layoutTemplatesRequest, layoutDataRequest

import os.path
import functools
import time

# Import for requests
import requests, base64
import xml.etree.ElementTree as ET
from io import BytesIO
import webbrowser
import pandas as pd
import numpy as np

import pprint

from typing import Any, Dict, Iterable, List, Sequence, Tuple, Union

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

                if results['ResultCode'] == 0:
                    
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

    def __init__(self, iface: QgisInterface):
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

        self.TILayer = None
      
        self.token = None
        self.session_start_t = 0
        self.username = None
        self.licensenumber = None
        self.applicationcode = None
        self.errormessage = None

        self.map_tool = None

        self.layoutsDict = {}

        self.crossSectionDict = {}

        self.pluginIsActive = False

        # Main widget ui reference, is instantiated in run()
        self.dockwidget = None
        self.table = None

    # noinspection PyMethodMayBeStatic

    def tr(self, message: str) -> str:
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

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # reset maptool
        if self.map_tool:
            self.map_tool.deactivate()
        # self.iface.mapCanvas().unsetMapTool(self.map_tool)
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

    def setMapTool(self, newMapTool: QgsMapTool=TISelectionTool):
        currentMapTool = self.iface.mapCanvas().mapTool()
        if isinstance(currentMapTool, (TISelectionTool, TICrossSectionTool)):
            if not isinstance(currentMapTool, newMapTool):
                tool = newMapTool(self.iface, self)
                self.map_tool = tool
                self.iface.mapCanvas().setMapTool(tool)
        else:

            self.last_map_tool = currentMapTool
            tool = newMapTool(self.iface, self)
            self.map_tool = tool
            self.iface.mapCanvas().setMapTool(tool)
    
    def getAuthorisationInfo(self):
        d = {
            'ApplicationCode': self.applicationcode,
            'Licensenumber': self.licensenumber,
            'Username': self.username,
        }
        return d

    @login
    def getBorelogImage(self, feature: QgsFeature):
        
        if self.checkRequiredFields(feature) is False:
            self.iface.messageBar().pushMessage('Error', 'Kon geen ProjectID of MeasurementPointID in de features vinden. Heb je wel punten van de TerraIndex Laag geselecteerd?', level=Qgis.Warning)
            return

        projectID = feature['ProjectID']
        measurementPointID = feature['MeasurementPointID']

        request = BorelogRequest(self)
        request.addBorehole(measurementPointID, projectID)
        response = request.request()

        if response.status_code is not requests.codes.ok:
            print(response)
            print(response.text)
            self.iface.messageBar().pushMessage("Error", response.reason, level=Qgis.Critical)
            response.raise_for_status()
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
            self.dockwidget.tabWidget.setCurrentIndex(0)
    
    @login
    def getBorelogsPDF(self, features: Iterable[QgsFeature]):

        if self.checkRequiredFields(features[0]) is False:
            self.iface.messageBar().pushMessage('Error', 'Kon geen ProjectID of MeasurementPointID in de features vinden. Heb je wel punten van de TerraIndex Laag geselecteerd?', level=Qgis.Warning)
            return

        boreholeid_list = []
        for feature in features:
            boreholeid_list.append({'ProjectID': feature['ProjectID'],
                                'BoreHoleID': feature['MeasurementPointID']})
        
        request = BorelogRequest(self, DrawMode='MultiPage', OutputType='PDF')

        for d in boreholeid_list:
            request.addBorehole(**d)

        filename, _ = QFileDialog.getSaveFileName(self.dockwidget, self.tr("Save PDF:"), 'borelogs', self.tr('pdf (*.pdf)') )

        if not filename:
            return

        response = request.request()
        if response.status_code is not requests.codes.ok:
            print(response)
            print(response.text)
            self.iface.messageBar().pushMessage("Error", response.reason, level=Qgis.Critical)
            response.raise_for_status()
        else:
            xml_content = ET.fromstring(response.content)

            bytes64 = xml_content.find('.//b:Content', ns).text

            bytes = base64.b64decode(bytes64)

            with open(filename, 'wb') as f:
                f.write(bytes)

            webbrowser.open(filename)
    
    @staticmethod
    def sortCrossSection(crossSectionDict: Dict[int, Tuple[QgsFeature, float]]) -> Dict[int, Tuple[QgsFeature, float]]:
        
        def distance( a: Tuple[Any, float]) -> float:
            return a[1][1]
        
        return {k: v for k, v in sorted(crossSectionDict.items(), key=distance)}
    
    @staticmethod
    def scaleCrossSectionDistances(crossSectionDict: Dict[int, Tuple[QgsFeature, float]], factor: float) -> Dict[int, Tuple[QgsFeature, float]]:
        distances= [x[1] for x in crossSectionDict.values()]
        min_dist = min(distances)

        return {fid: (f, factor*(d-min_dist)) for fid, (f, d) in crossSectionDict.items()}


    # # def normalizeCrossSectionDistances(self, crossSectionDict: Dict[int, Tuple[QgsFeature, float]], min_width:int=10, factor=None) -> Tuple[float, Dict[int, Tuple[QgsFeature, float]]]:
    #     if crossSectionDict:
    #         distances = [float(f[1]) for f in crossSectionDict]
    #         idx = np.argsort(distances).tolist()
    #         sorted_distances = [distances[i] for i in idx]
    #         print(sorted_distances)
 
    #         sorted_crossSections = [crossSectionDict[i] for i in idx]

    #         diff = np.diff(sorted_distances)
    #         min_dist = np.min(diff)
    #         if factor is None:
    #             factor = min_width/min_dist
    #             distances2 = np.hstack([np.array([0]), np.cumsum(diff)*factor]) # start distances from 0
    #         else:
    #             distances2 = np.hstack([np.array([0]), np.cumsum(diff)*factor]) # start distances from 0

    #         crossSectionDict2 = []
    #         for i, (f, d) in enumerate(sorted_crossSections):
    #             crossSectionDict2.append((f, round(distances2[i])))

    #         return factor, crossSectionDict2

    @login
    def getCrossSectionPDF(self, crossSectionDict: Dict[int, Tuple[QgsFeature, float]]):

        scale = self.dockwidget.SP_scale.value()
        norm_crossSections = self.scaleCrossSectionDistances(self.sortCrossSection(crossSectionDict), scale)

        boreholeid_list = []
        for feature, distance in norm_crossSections.values():
            boreholeid_list.append({'ProjectID': feature['ProjectID'],
                                'BoreHoleID': feature['MeasurementPointID'],
                                'Distance': int(distance)
                                })

        request = BorelogRequest(self, DrawKind='CrossSection', DrawMode='MultiPage', OutputType='PDF')

        for d in boreholeid_list:
            request.addBorehole(**d)

        filename, _ = QFileDialog.getSaveFileName(self.dockwidget, self.tr("Save PDF:"), 'CrossSection', self.tr('pdf (*.pdf)') )

        if not filename:
            return

        response = request.request()
        if response.status_code is not requests.codes.ok:
            print(response)
            print(response.text)
            self.iface.messageBar().pushMessage("Error", response.reason, level=Qgis.Critical)
            response.raise_for_status()
        else:
            # print('response check true')
            xml_content = ET.fromstring(response.content)

            bytes64 = xml_content.find('.//b:Content', ns).text

            bytes = base64.b64decode(bytes64)

            with open(filename, 'wb') as f:
                f.write(bytes)

            webbrowser.open(filename)

    @login
    def requestBoreholeData(self, features: Iterable[QgsFeature]) ->  dict:
        
        boreholeid_list = []
        for feature in features:
            boreholeid_list.append({'ProjectID': feature['ProjectID'],
                                'BoreHoleID': feature['MeasurementPointID']})
        
        request = BoreholeDataRequest(self)

        for d in boreholeid_list:
            request.addBorehole(**d)
        
        response, data = request.request()

        if response.status_code is not requests.codes.ok:
            self.iface.messageBar().pushMessage("Error", response.reason, level=Qgis.Critical)
            response.raise_for_status()
        
        return data
    
    @login
    def showData(self, *args):
        features = self.TILayer.selectedFeatures()

        if len(features) > 0:
            features2 = self.sortFeatures(features)
            data = self.requestBoreholeData(features2)
            df = pd.DataFrame(data)

            if self.crossSectionDict:
                self.checkCanvasCrs()
                crossSectionDict2 = self.sortCrossSection(self.crossSectionDict)
                join_table = [[f['MeasurementPointID'], f['ProjectID'], round(d,2)] for f, d in self.crossSectionDict.values()]
                join_table = pd.DataFrame(data=join_table, columns=['MeasurementPointID', 'ProjectID', 'CrossSectionDistance'])
                df = pd.merge(df, join_table, how='left', left_on=['MeasurementPointID', 'ProjectID'], right_on=['MeasurementPointID', 'ProjectID'])

            self.updateTable(df)

    @login
    def downloadData(self, *args):
        filename, selectedFilter = QFileDialog.getSaveFileName(self.dockwidget, self.tr("Save Borehole Data:"), 'borelogs_data', self.tr('data (*.csv *.xlsx)') )
        if not filename:
            return
        _, ext = os.path.splitext(filename)

        df = self.table._data
        if ext == '.csv': 
            df.to_csv(filename, sep=';')
        elif ext == '.xlsx':
            df.to_excel(filename)

    @login
    def updateLayoutNames(self):
        self.layoutsDict = layoutTemplatesRequest(self)
        for key, val in self.layoutsDict.items():
            ## adds the names as text to the combobox and layoutid as data
            self.dockwidget.CB_layout.addItem(val['TemplateName'], userData=key)
    
    @login
    def getLayout(self, id: int) -> str:
        return layoutDataRequest(self, TemplateID=id)
    
    @login
    def downloadPDF(self):
        
        features = self.TILayer.selectedFeatures()
            
        if not len(features) > 0 :
            return
        elif self.checkRequiredFields(features[0]) is False:
            self.iface.messageBar().pushMessage('Error', 'Kon geen ProjectID of MeasurementPointID in de features vinden. Heb je wel punten van de TerraIndex Laag geselecteerd?', level=Qgis.Warning)
            return

        if self.crossSectionDict:
            self.checkCanvasCrs()
            self.getCrossSectionPDF(self.crossSectionDict)
        else:
            features2 = self.sortFeatures(features)
            self.getBorelogsPDF(features2) 
    
    def checkCanvasCrs(self):
        crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        if not crs.authid() == 'EPSG:28992':
            self.iface.messageBar().pushMessage(
                "CRS warning", 
                "The project CRS is not EPSG:28992. Note that the crosssectional distance will be calculated in the project CRS:{}".format(crs.authid()), 
                level=Qgis.Warning
                )
    
    def updateTable(self, df: pd.DataFrame=None, reset=False):
        if not reset:
            self.table = PandasTableModel(df)
            self.dockwidget.tableView.setModel(self.table)
            self.dockwidget.tableView.resizeColumnsToContents()
            self.dockwidget.tabWidget.setCurrentIndex(1)
        else:
            if self.table:
                self.table.clear()

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
            
            self.dockwidget.PB_downloadpdf.clicked.connect(self.downloadPDF)
            self.dockwidget.PB_updateLayouts.pressed.connect(self.updateLayoutNames)
            self.dockwidget.PB_showdata.clicked.connect(self.showData)
            self.dockwidget.PB_downloaddata.clicked.connect(self.downloadData)

            setMapToolCrossSection = functools.partial(self.setMapTool, newMapTool=TICrossSectionTool)
            self.dockwidget.PB_crosssection.clicked.connect(setMapToolCrossSection)
            setMapToolSelection = functools.partial(self.setMapTool, newMapTool=TISelectionTool)
            self.dockwidget.PB_boreprofile.clicked.connect(setMapToolSelection)

            # self.dockwidget.CB_layout.activated.connect(self.updateLayouts)
            # Load the layouts
            if self.layoutsDict == {}:
                self.updateLayoutNames()


            # initialize TISelectionTool
            self.setMapTool()

            # Import TerraIndex Measurement point layer
            self.initTILayer()


            # show the dockwidget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()



    @staticmethod
    def sortFeatures(features: Iterable[QgsFeature]) -> List[QgsFeature]:

        def get_projectID(f):
            return f['ProjectID']

        def get_pointID(f):
            return f['MeasurementPointID'] 

        def sortProjectPoint(f):
            return (get_projectID(f), get_pointID(f)) 

        features2 = sorted(features, key=sortProjectPoint) 

        return features2

    @staticmethod
    def checkRequiredFields(feature: QgsFeature) -> bool:

        req = ['ProjectID', 'MeasurementPointID']
        fields = [field.name() for field in feature.fields()]

        return set(req).issubset(fields)

class PandasTableModel(QStandardItemModel):
    '''Helper class for converting Pandas Dataframe to a Qt Table model.
    https://stackoverflow.com/questions/31475965/fastest-way-to-populate-qtableview-from-pandas-data-frame
    '''    
    def __init__(self, data:pd.DataFrame, parent=None):
        QStandardItemModel.__init__(self, parent)
        self._data = data
        for col in data.columns:
            data_col = [QStandardItem("{}".format(x)) for x in data[col].values]
            self.appendColumn(data_col)
        return

    def rowCount(self, parent=None) -> int:
        return len(self._data.values)

    def columnCount(self, parent=None) -> int:
        return self._data.columns.size

    def headerData(self, x, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._data.columns[x]
        if orientation == Qt.Vertical and role == Qt.DisplayRole:
            return self._data.index[x]
        return None
    
    # def clear(self):
    #     self.layoutAboutToBeChanged.emit()
    #     self._data.drop(self._data.index,inplace=True) 
    #     self.layoutChanged.emit()
