from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.core import  QgsPointXY, QgsProject, QgsPointXY, QgsRectangle, QgsWkbTypes, 

from qgis.PyQt.QtGui import QTextDocument, Qt
from qgis.PyQt.QtCore import QSizeF

from collections import OrderedDict

import numpy as np


class TICrosssectionTool(QgsMapTool):
    """Pointtool class, which overwrites the normal cursor during use of the plugin"""
    def __init__(self, iface, plugin):
        super(QgsMapTool, self).__init__(iface.mapCanvas())

        self.iface = iface
        self.plugin = plugin

        self.isEmittingPoint = False

        self.rubberband = QgsRubberBand(self.canvas(), geometryType=QgsWkbTypes.LineString)

        self.distances = {}



    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.isEmittingPoint:
                self.startPoint = self.toMapCoordinates(event.pos())
                self.endPoint = self.startPoint
                self.isEmittingPoint = True 
            
            else:
                self.endPoint = self.toMapCoordinates(event.pos())

                if self.startPoint.compare(self.endPoint):
                    self.unsetSelectedFeatures()
                    self.rubberband.hide()
                    self.isEmittingPoint = False


                else:
                    self.unsetSelectedFeatures()
                    bbRect_map = self.bbRect(10)
                    

                    if bbRect_map is not None:
                        layer = self.plugin.TILayer
                        bbRect = self.canvas().mapSettings().mapToLayerCoordinates(layer, bbRect_map)
                        features = layer.getFeatures(bbRect)
                        
                        proj_vec = self.getProjVec()
                        selectedFeatures = []
                        for f in features:
                            vec = self.canvas().mapSettings().layerToMapCoordinates(layer, f.geometry().asPoint()) - self.startPoint

                            selectedFeatures.append((f,  self.projLength(vec, proj_vec)))
                            
                        self.setSelectedFeatures(selectedFeatures)

        
        elif event.button() == Qt.RightButton:

            self.isEmittingPoint = False
            self.unsetSelectedFeatures()
            self.rubberband.hide()

            


    def canvasMoveEvent(self, event):
        if not self.isEmittingPoint:
            return

        self.endPoint = self.toMapCoordinates(event.pos())
        self.showLine(self.startPoint, self.endPoint)

    def canvasReleaseEvent(self, event):
        pass          

    def showLine(self, startPoint, endPoint):
        self.rubberband.reset(QgsWkbTypes.LineString)
        
        if startPoint.x() == endPoint.x() or startPoint.y() == endPoint.y():
            return
        point1 = QgsPointXY(startPoint.x(), startPoint.y())
        point2 = QgsPointXY(endPoint.x(), endPoint.y())

        self.rubberband.addPoint(point1, False)
        self.rubberband.addPoint(point2, True) # true to update canvas  
        self.rubberband.show()

    def bbRect(self, thickness):
        '''Creates a rectangle with thickness around the line segment

        Args:
            thickness (float): Thickness within the given coordinate systems xy-plane 

        Returns:
            QgsRectangle: Rectangle around the Line
        '''        

        if self.startPoint is None or self.endPoint is None:
            return None
        elif self.startPoint.compare(self.endPoint):
            return None
        else:
            vec_norm = self.getProjVec()
            vec_orth = np.array([vec_norm[1], -1*vec_norm[0]])

            a = thickness/2

            point1 = QgsPointXY( self.startPoint.x() + a*vec_orth[0], self.startPoint.y() + a*vec_orth[1])
            point2 = QgsPointXY( self.endPoint.x() - a*vec_orth[0], self.endPoint.y() - a*vec_orth[1])
            return QgsRectangle(point1, point2)
    
    def getProjVec(self):
        if self.startPoint is None or self.endPoint is None:
            return None
        else:
            vec = self.endPoint - self.startPoint
            return vec.normalized()

    def projLength(self, vec1, vec2):
        '''Projects vector 1 onto the line of vector 2

        Args:
            vec1 (QgsVector): vector 1
            vec2 (QgsVector): vector 2 that spans a projection line

        Returns:
            _type_: _description_
        '''        
        d = vec1 * vec2/(vec2 * vec2)
        return d
    

    def setSelectedFeatures(self, features):
        self.plugin.TILayer.selectByIds([f.key().id() for f in features])
        self.plugin.crossSectionList = features
        
    def unsetSelectedFeatures(self):
        self.plugin.TILayer.removeSelection()
        self.plugin.crossSectionList = []

    def getSelectedFeature(self):
        return self.plugin.TILayer.selectedFeatures()


    def deactivate(self):

        self.rubberband.reset()
        
        QgsMapTool.deactivate(self)


    def isZoomTool(self):
        return False

    def isTransient(self):
        return False

    def isEditTool(self):
        return False
