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
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis.gui import QgsMapTool, QgsMapToolIdentify
from qgis.core import QgsRectangle, QgsVectorLayer
# Initialize Qt resources from file resources.py
from .resources import *

# Import the code for the DockWidget
from .terraindex_dockwidget import TerraIndexDockWidget
import os.path


class TerraIndex:
    """QGIS Plugin Implementation."""

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

        #print "** INITIALIZING TerraIndex"
        self.map_tool = None

        self.pluginIsActive = False
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

    #--------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        print('Closing TerraIndex')

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # reset maptool
        self.iface.mapCanvas().unsetMapTool(self.map_tool)
        self.iface.mapCanvas().setMapTool(self.last_map_tool)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        # self.dockwidget = None

        self.pluginIsActive = False


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        #print "** UNLOAD TerraIndex"

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&TerraIndex'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    #--------------------------------------------------------------------------

    def setMapTool(self):
        if type(self.iface.mapCanvas().mapTool()) is type(self.map_tool) and self.map_tool is not None:
            print('type=type')
        else:
            print('set maptool')
            self.map_tool = PointTool(self.iface, self.iface.mapCanvas(), self)
            self.last_map_tool = self.iface.mapCanvas().mapTool()
            self.iface.mapCanvas().setMapTool(self.map_tool)
    
    def getBorelogImage(self, feature):
        fields = [field.name() for field in feature.fields()]
        
        req = ['ProjectID', 'MeasurementPointID']

        if set(req).issubset(fields):
            projectID = feature[req[0]]
            measurementPointID = feature[req[1]]
            print(projectID)
            print(measurementPointID)
        else:
            #show warning maybe
            pass



    def run(self):
        """Run method that loads and starts the plugin"""

        if not self.pluginIsActive:
            self.pluginIsActive = True

            #print "** STARTING TerraIndex"

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
    def __init__(self, iface, canvas, plugin):
        QgsMapToolIdentify.__init__(self, canvas)
        
        self.canvas = canvas    
        self.iface = iface
        self.plugin = plugin

        self.selected_feature = None
        #QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def canvasPressEvent(self, event):
        pass

    def canvasMoveEvent(self, event):
        pass

    def canvasReleaseEvent(self, event):
        found_features = self.identify(event.x(), event.y(),
                                self.TopDownStopAtFirst,
                                self.VectorLayer) 
        
        if len(found_features) > 0:
            help(found_features[0])
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
