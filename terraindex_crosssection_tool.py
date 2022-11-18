from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.core import  QgsPointXY, QgsProject, QgsPointXY, QgsRectangle, QgsWkbTypes, QgsGeometry, QgsPolygon, QgsLineString, QgsCoordinateTransform

from qgis.PyQt.QtGui import QTextDocument, QColor, QGuiApplication
from qgis.PyQt.QtCore import QSizeF, Qt

from collections import OrderedDict

import numpy as np

from functools import partial


class TICrossSectionTool(QgsMapTool):
    """Pointtool class, which overwrites the normal cursor during use of the plugin"""
    def __init__(self, iface, plugin):
        super(QgsMapTool, self).__init__(iface.mapCanvas())

        self.setCursor(Qt.CrossCursor)

        self.iface = iface
        self.plugin = plugin

        self.isEmittingPoint = False

        self.rubberband = QgsRubberBand(self.canvas(), geometryType=QgsWkbTypes.LineGeometry)
        self.rubberband.setColor(QColor(0, 0, 0))
        self.rubberband.setWidth(3)

        self.bufferband = QgsRubberBand(self.canvas(), geometryType=QgsWkbTypes.PolygonGeometry)
        
        self.thickness = self.plugin.dockwidget.SB_crosssectionWidth.value()
        self.plugin.dockwidget.SB_crosssectionWidth.valueChanged.connect(self.setThickness)

        self.orth_segments = [] # list of QgsRubberBands for the orth seg

        self.distances = {}

    def setThickness(self):
        self.thickness = self.plugin.dockwidget.SB_crosssectionWidth.value()

    def mapToLayer(self, QgsGeometry):
        return self.canvas().mapSettings().mapToLayerCoordinates(self.plugin.TILayer, QgsGeometry)
    
    def layerToMap(self, QgsGeometry):
        return self.canvas().mapSettings().layerToMapCoordinates(self.plugin.TILayer, QgsGeometry)


    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.isEmittingPoint:
                modifiers = QGuiApplication.keyboardModifiers()
                if modifiers == Qt.ShiftModifier & self.startPoint is None:
                    print('shift clicked')
                    pass
                else:
                    self.startPoint = self.toMapCoordinates(event.pos())
                    self.endPoint = self.startPoint
                    self.unsetSelectedFeatures()
                    self.isEmittingPoint = True 
            else:

                self.endPoint = self.toMapCoordinates(event.pos())

                if self.startPoint.compare(self.endPoint):
                    self.unsetSelectedFeatures()
                    self.rubberband.hide()
                    self.isEmittingPoint = False
                else:
                    self.unsetSelectedFeatures()
                    self.isEmittingPoint = False

                    layer = self.plugin.TILayer
                    self.buffer(self.startPoint, self.endPoint)
                    geom = self.bufferband.asGeometry()
                    

                    bbRect = self.mapToLayer(geom.boundingBox())
                    features1 = layer.getFeatures(bbRect)

                    tr = QgsCoordinateTransform(self.canvas().mapSettings().destinationCrs(), layer.crs(), QgsProject.instance())

                    geom.transform(tr)

                    features = []
                    for f in features1:
                        pointGeom = f.geometry()
                        if geom.contains(pointGeom):
                            features.append(f)

                    proj_vec = self.getProjVec(self.startPoint, self.endPoint)

                    features = []
                    distances = []
                    for f in features:

                        pointf = self.layerToMap(f.geometry().asPoint()) # PointXY in mapcanvas coordinates
                        vec = pointf  - self.startPoint

                        d = self.projLength(vec, proj_vec) # projection distance on line in coordinatesystem of the mapcanvas

                        pointOnLine = self.startPoint  + proj_vec*d       # new point

                        seg = QgsRubberBand(self.canvas(), geometryType=QgsWkbTypes.LineGeometry)
                        seg.setColor(QColor(100,100,100))
                        seg.setWidth(2)
                        seg.addPoint(pointOnLine, False)
                        seg.addPoint(pointf, True)
                        seg.show()

                        self.orth_segments.append(seg)

                        features.append(f)
                        distances.append(d)

                    min_dist = min(distances)
                    distances = [d - min_dist for d in distances]
                    selectedFeatures = zip(features, distances)
                        
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
        self.buffer(self.startPoint, self.endPoint)

    def canvasReleaseEvent(self, event):
        pass          

    def showLine(self, startPoint, endPoint):
        self.rubberband.reset(geometryType=QgsWkbTypes.LineGeometry)
        
        if startPoint.x() == endPoint.x() or startPoint.y() == endPoint.y():
            return
        point1 = QgsPointXY(startPoint.x(), startPoint.y())
        point2 = QgsPointXY(endPoint.x(), endPoint.y())

        self.rubberband.addPoint(point1, False)
        self.rubberband.addPoint(point2, True) # true to update canvas  
        self.rubberband.show()

    def buffer(self, startPoint, endPoint):
        '''Creates a rectangle with thickness orthogonal to a line segment

        Args:
            thickness (float): Thickness within the given coordinate systems xy-plane 

        Returns:
            QgsRectangle: Rectangle around the Line
        '''        

        if startPoint is None or endPoint is None:
            return None
        elif startPoint.compare(endPoint):
            return None
        else:
            vec_norm = self.getProjVec(startPoint, endPoint)
            vec_orth = np.array([-1*vec_norm.y(), vec_norm.x()])

            a = self.thickness/2

            point1 = QgsPointXY( startPoint.x() + a*vec_orth[0], startPoint.y() + a*vec_orth[1])
            point2 = QgsPointXY( endPoint.x() + a*vec_orth[0], endPoint.y() + a*vec_orth[1])
            point3 = QgsPointXY( endPoint.x() - a*vec_orth[0], endPoint.y() - a*vec_orth[1])
            point4 = QgsPointXY( startPoint.x() - a*vec_orth[0], startPoint.y() - a*vec_orth[1])
            
            self.bufferband.reset(QgsWkbTypes.PolygonGeometry)
            self.bufferband.addPoint(point1, False)
            self.bufferband.addPoint(point2, False)
            self.bufferband.addPoint(point3, False)
            self.bufferband.addPoint(point4, True) 
            self.bufferband.show()
            
    
    def getProjVec(self, startPoint, endPoint):
        if startPoint is None or endPoint is None:
            return None
        else:
            vec = endPoint - startPoint
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
        self.plugin.TILayer.selectByIds([f[0].id() for f in features])
        self.plugin.crossSectionList = features
        
    def unsetSelectedFeatures(self):
        self.plugin.TILayer.removeSelection()
        self.plugin.crossSectionList = []

        self.bufferband.reset()
        for seg in self.orth_segments:
            seg.reset()

    def getSelectedFeature(self):
        return self.plugin.TILayer.selectedFeatures()


    def deactivate(self):
        self.unsetSelectedFeatures()
        self.rubberband.reset()
        self.bufferband.reset()
        for seg in self.orth_segments:
            seg.reset()
        
        QgsMapTool.deactivate(self)


    def isZoomTool(self):
        return False

    def isTransient(self):
        return False

    def isEditTool(self):
        return False
