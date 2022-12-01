from typing import List, Tuple, Union
from qgis.gui import QgsRubberBand, QgsMapToolIdentify, QgsMapTool, QgisInterface, QgsMapMouseEvent
from qgis.core import  QgsPointXY, QgsProject, QgsPointXY, QgsRectangle, QgsWkbTypes, QgsGeometry, QgsLineString, QgsCoordinateTransform, QgsVector, QgsFeature

from qgis.PyQt.QtGui import QTextDocument, QColor, QStandardItemModel
from qgis.PyQt.QtCore import QSizeF, Qt

from collections import OrderedDict

import numpy as np
import pandas as pd

from functools import partial


class TICrossSectionTool(QgsMapTool):
    """Pointtool class, which overwrites the normal cursor during use of the plugin"""
    def __init__(self, iface: QgisInterface, plugin: 'TerraIndex'):
        super(QgsMapTool, self).__init__(iface.mapCanvas())

        self.identifier = QgsMapToolIdentify(iface.mapCanvas())

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

        self.orth_segments = {} # dictionary of QgsRubberBands to keep track of the orthogonal segments

        self.distances = {}
        self.isOverrideCursor = False

    def setThickness(self):
        self.thickness = self.plugin.dockwidget.SB_crosssectionWidth.value()

    def mapToLayer(self, QgsGeometry: QgsGeometry):
        return self.canvas().mapSettings().mapToLayerCoordinates(self.plugin.TILayer, QgsGeometry)
    
    def layerToMap(self, QgsGeometry: QgsGeometry):
        return self.canvas().mapSettings().layerToMapCoordinates(self.plugin.TILayer, QgsGeometry)


    def canvasPressEvent(self, event: QgsMapMouseEvent):
        if event.button() == Qt.LeftButton:
            if not self.isEmittingPoint:
                modifiers = event.modifiers()
                if modifiers == Qt.ControlModifier:
                    f = self.identifier.identify(x=event.x(), y=event.y(), mode=self.identifier.TopDownStopAtFirst, layerList=[self.plugin.TILayer])[0].mFeature
                    
                    if f.id() in self.plugin.crossSectionDict.keys():
                        self.removeFeature(f.id())
                    else:
                        pointf = self.layerToMap(f.geometry().asPoint())
                        self.addFeature(f, pointf, self.projVec, update=True)
                elif modifiers == Qt.ShiftModifier:
                    f = self.identifier.identify(x=event.x(), y=event.y(), mode=self.identifier.TopDownStopAtFirst, layerList=[self.plugin.TILayer])[0].mFeature
                    self.plugin.getBorelogImage(f)
                else:
                    self.startPoint = self.toMapCoordinates(event.pos())
                    self.endPoint = self.startPoint
                    self.removeFeatures()
                    self.isEmittingPoint = True 
            else:

                self.endPoint = self.toMapCoordinates(event.pos())

                if self.startPoint.compare(self.endPoint):
                    self.removeFeatures()
                    self.rubberband.hide()
                    self.isEmittingPoint = False
                else:
                    self.removeFeatures()
                    self.isEmittingPoint = False

                    layer = self.plugin.TILayer
                    self.buffer(self.startPoint, self.endPoint)
                    geom = self.bufferband.asGeometry()
                    

                    bbRect = self.mapToLayer(geom.boundingBox())
                    featuresBbRect = layer.getFeatures(bbRect)

                    tr = QgsCoordinateTransform(self.canvas().mapSettings().destinationCrs(), layer.crs(), QgsProject.instance())

                    geom.transform(tr)

                    features = []
                    for f in featuresBbRect:
                        pointGeom = f.geometry()
                        if geom.contains(pointGeom):
                            features.append(f)

                    self.projVec = self.getProjVec(self.startPoint, self.endPoint) # Projection vector in mapcanvas coordinates

                    for f in features:
                        pointf = self.layerToMap(f.geometry().asPoint()) # PointXY in mapcanvas coordinates
                        self.addFeature(f, pointf, self.projVec)
                    
                    self.updateTable()
        
        elif event.button() == Qt.RightButton:
            self.isEmittingPoint = False
            self.removeFeatures()
            self.rubberband.hide()

            


    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        modifiers = event.modifiers()
        if not self.isEmittingPoint:
            if  modifiers == Qt.ShiftModifier:
                if self.isOverrideCursor:
                    pass
                else:
                    self.isOverrideCursor = True
                    QGuiApplication.setOverrideCursor(Qt.WhatsThisCursor)
            else:
                if self.isOverrideCursor:
                    self.isOverrideCursor = False
                    QGuiApplication.restoreOverrideCursor()
                
            return       

        self.endPoint = self.toMapCoordinates(event.pos())
        self.showLine(self.startPoint, self.endPoint)
        self.buffer(self.startPoint, self.endPoint)

    def canvasReleaseEvent(self, event: QgsMapMouseEvent):
        pass          

    def showLine(self, startPoint: QgsPointXY, endPoint: QgsPointXY):
        self.rubberband.reset(geometryType=QgsWkbTypes.LineGeometry)
        
        if startPoint.x() == endPoint.x() or startPoint.y() == endPoint.y():
            return
        point1 = QgsPointXY(startPoint.x(), startPoint.y())
        point2 = QgsPointXY(endPoint.x(), endPoint.y())

        self.rubberband.addPoint(point1, False)
        self.rubberband.addPoint(point2, True) # true to update canvas  
        self.rubberband.show()

    def buffer(self, startPoint: QgsPointXY, endPoint: QgsPointXY):
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
            
    
    def getProjVec(self, startPoint: QgsPointXY, endPoint: QgsPointXY) -> Union[QgsVector, None]:
        if startPoint is None or endPoint is None:
            return None
        else:
            vec = endPoint - startPoint
            return vec.normalized()

    def projLength(self, vec1: QgsVector, vec2: QgsVector) -> float:
        '''Projects vector 1 onto the line of vector 2

        Args:
            vec1 (QgsVector): vector 1
            vec2 (QgsVector): vector 2 that spans a projection line

        Returns:
            _type_: _description_
        '''        
        d = vec1 * vec2/(vec2 * vec2)
        return d
    

    def setFeatures(self, features: List[Tuple[QgsFeature, float]]):
        self.plugin.TILayer.selectByIds([f[0].id() for f in features])
        self.plugin.crossSectionDict = features

    def addFeature(self, f: QgsFeature, pointf: QgsPointXY, projVec: QgsVector, update:bool=False):
        fid = f.id()
        vec = pointf  - self.startPoint

        d = self.projLength(vec, projVec) # projection distance on line in coordinatesystem of the mapcanvas

        pointOnLine = self.startPoint  + projVec*d 

        seg = QgsRubberBand(self.canvas(), geometryType=QgsWkbTypes.LineGeometry)
        seg.setColor(QColor(100,100,100))
        seg.setWidth(2)
        seg.addPoint(pointOnLine, False)
        seg.addPoint(pointf, True)
        seg.show()

        self.orth_segments[fid] = seg
        self.plugin.TILayer.select(fid)
        self.plugin.crossSectionDict[fid] = (f, d)

        if update:
            self.updateTable()


    
    def removeFeature(self, fid: int, updateTab:bool=True):
        self.plugin.TILayer.deselect(fid)
        self.plugin.crossSectionDict.pop(fid)
        seg = self.orth_segments.pop(fid)
        seg.reset()
        if updateTab:
            self.updateTable()

        
    def removeFeatures(self):
        self.plugin.TILayer.removeSelection()
        self.plugin.crossSectionDict = {}

        self.bufferband.reset()
        for seg in self.orth_segments.values():
            seg.reset()
        
        self.orth_segments = {}
        self.plugin.updateTable(reset=True)
    
    def updateTable(self):
        if self.plugin.crossSectionDict:
            d = {fid:[f['MeasurementPointName'], f['ProjectCode'], round(d,2)] for fid, (f, d) in self.plugin.crossSectionDict.items()}
            df = pd.DataFrame.from_dict(d, orient='index', columns=['MeasurementPointName', 'ProjectCode', 'Distance']).sort_values('Distance')
            self.plugin.updateTable(df)
        else:
            self.plugin.updateTable(reset=True)


    def getSelectedFeature(self):
        return self.plugin.TILayer.selectedFeatures()

    def deactivate(self):
        self.removeFeatures()
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



