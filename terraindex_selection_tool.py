from qgis.gui import QgsMapToolIdentify, QgsRubberBand
from qgis.core import QgsHtmlAnnotation, QgsSvgAnnotation, QgsTextAnnotation, QgsPointXY, QgsProject, QgsPointXY, QgsRectangle, QgsWkbTypes

from qgis.PyQt.QtGui import QTextDocument
from qgis.PyQt.QtCore import QSizeF

from collections import OrderedDict




class TISelectionTool(QgsMapToolIdentify):
    """Pointtool class, which overwrites the normal cursor during use of the plugin"""
    def __init__(self, iface, plugin):
        super(QgsMapToolIdentify, self).__init__(iface.mapCanvas())

        self.iface = iface
        self.plugin = plugin

        self.annotationManager = QgsProject.instance().annotationManager()


        self.isEmittingPoint = False
        self.rubberband = QgsRubberBand(self.canvas(), geometryType=QgsWkbTypes.PolygonGeometry)

        self.selected_features = None

        self.annotation_features = OrderedDict()
        # QApplication.instance().setOverrideCursor(Qt.ArrowCursor)


    def canvasPressEvent(self, event):
        
        self.startPoint = self.toMapCoordinates(event.pos())
        self.endPoint = self.startPoint
        self.isEmittingPoint = True 


    def canvasMoveEvent(self, event):
        if not self.isEmittingPoint:
            return

        self.endPoint = self.toMapCoordinates(event.pos())
        self.showRect(self.startPoint, self.endPoint)

    def canvasReleaseEvent(self, event):
        
        
        self.isEmittingPoint = False

        # do something when a single point is clicked
        if self.startPoint.compare(self.endPoint):
            found_features = self.identify(x = event.x(), y= event.y(),
                                        layerList=[self.plugin.TILayer], 
                                        mode=self.TopDownStopAtFirst)

            if len(found_features) > 0:
                layer = found_features[0].mLayer
                feature = found_features[0].mFeature
                self.unsetSelectedFeatures()
                self.setSelectedFeatures([feature])
                #self.addAnnotation(feature, layer) 

                self.plugin.getBorelogImage(feature)
            else:
                self.unsetSelectedFeatures()
        # do something when a selection is made
        else:
            r = self.rectangle()

            layer = self.plugin.TILayer


            self.unsetSelectedFeatures()

            if r is not None:
                #builds bbRect and select from layer, adding selection
                bbRect = self.canvas().mapSettings().mapToLayerCoordinates(layer, r)
                features = layer.getFeatures(bbRect)
                self.setSelectedFeatures([f for f in features])
            
            self.rubberband.hide()
            

    def showRect(self, startPoint, endPoint):
        self.rubberband.reset(QgsWkbTypes.PolygonGeometry)
        
        if startPoint.x() == endPoint.x() or startPoint.y() == endPoint.y():
            return
        point1 = QgsPointXY(startPoint.x(), startPoint.y())
        point2 = QgsPointXY(startPoint.x(), endPoint.y())
        point3 = QgsPointXY(endPoint.x(), endPoint.y())
        point4 = QgsPointXY(endPoint.x(), startPoint.y())

        self.rubberband.addPoint(point1, False)
        self.rubberband.addPoint(point2, False)
        self.rubberband.addPoint(point3, False)
        self.rubberband.addPoint(point4, True)    # true to update canvas
        self.rubberband.show()

    def rectangle(self):
        """
        Builds rectangle from self.startPoint and self.endPoint
        """
        if self.startPoint is None or self.endPoint is None:
            return None
        elif self.startPoint.x() == self.endPoint.x() or self.startPoint.y() == self.endPoint.y():
            return None
        return QgsRectangle(self.startPoint, self.endPoint)

    def setSelectedFeatures(self, features):
        self.plugin.TILayer.selectByIds([f.id() for f in features])
        
    def unsetSelectedFeatures(self):
        self.plugin.TILayer.removeSelection()

    def getSelectedFeature(self):
        return self.plugin.TILayer.selectedFeatures()

    def addAnnotation(self, feature, layer):

        if  feature not in set(self.annotation_features.keys()):

            geom = feature.geometry().asPoint()

            annot = QgsTextAnnotation()
            annot.setDocument( QTextDocument('test'))
            annot.setFrameSize(QSizeF(100,100))
            #annot.setAssociatedFeature(feature)
            annot.setMapPositionCrs(layer.crs())
            annot.setMapPosition(QgsPointXY(geom.x(), geom.y()))


            if len(self.annotation_features) < 10:
                self.annotation_features[feature] = annot
                self.annotationManager.addAnnotation(annot)
            else:
                _, annot_last = self.annotation_features.popitem(last=True)

                self.annotationManager.removeAnnotation(annot_last)
                self.annotation_features[feature] = annot
                self.annotation_features.move_to_end(feature, last=False)
                self.annotationManager.addAnnotation(annot)


    def removeAnnotations(self):
        for annot in self.annotation_features.values():
            self.annotationManager.removeAnnotation(annot)


    def deactivate(self):

        self.removeAnnotations()

        self.rubberband.reset()
        QgsMapToolIdentify.deactivate(self)




    def isZoomTool(self):
        return False

    def isTransient(self):
        return False

    def isEditTool(self):
        return False
