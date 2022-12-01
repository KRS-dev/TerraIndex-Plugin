from qgis.gui import QgsMapToolIdentify, QgsRubberBand, QgisInterface, QgsMapMouseEvent
from qgis.core import QgsHtmlAnnotation, QgsSvgAnnotation, QgsTextAnnotation, QgsPointXY, QgsProject, QgsPointXY, QgsRectangle, QgsWkbTypes, QgsFeature, QgsVectorLayer

from qgis.PyQt.QtGui import QTextDocument
from qgis.PyQt.QtCore import QSizeF, Qt

from collections import OrderedDict
from typing import List

class TISelectionTool(QgsMapToolIdentify):
    """Pointtool class, which overwrites the normal cursor during use of the plugin"""

    def __init__(self, iface: QgisInterface, plugin: 'TerraIndex'):
        super(QgsMapToolIdentify, self).__init__(iface.mapCanvas())

        self.iface = iface
        self.plugin = plugin

        self.isEmittingPoint = False
        self.rubberband = QgsRubberBand(
            self.canvas(), geometryType=QgsWkbTypes.PolygonGeometry)

        self.annotationManager = QgsProject.instance().annotationManager()
        self.annotation_features = OrderedDict()

    def canvasPressEvent(self, event: QgsMapMouseEvent):

        self.startPoint = self.toMapCoordinates(event.pos())
        self.endPoint = self.startPoint
        self.isEmittingPoint = True

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        if not self.isEmittingPoint:
            return

        self.endPoint = self.toMapCoordinates(event.pos())
        self.showRect(self.startPoint, self.endPoint)

    def canvasReleaseEvent(self, event: QgsMapMouseEvent):
        modifiers = event.modifiers()

        self.isEmittingPoint = False

        # do something when a single point is clicked
        if self.startPoint.compare(self.endPoint):
            found_features = self.identify(x=event.x(), y=event.y(),
                                           layerList=[self.plugin.TILayer],
                                           mode=self.TopDownStopAtFirst)

            if modifiers == Qt.ControlModifier:
                if len(found_features) > 0:
                    f = found_features[0].mFeature
                    if f.id() in self.plugin.TILayer.selectedFeatureIds():
                        self.removeFeature(f)
                    else:
                        self.addFeature(f)
                else:
                    return
            elif len(found_features) > 0:
                # layer = found_features[0].mLayer
                f = found_features[0].mFeature
                self.deselectFeatures()
                self.addFeature(f)
                #self.addAnnotation(feature, layer)
                self.plugin.getBorelogImage(f)
            else:

                self.deselectFeatures()
        # do something when a selection is made
        else:
            r = self.rectangle()

            if not event.modifiers() == Qt.ControlModifier:
                self.deselectFeatures()

            if r is not None:
                # builds bbRect and select from layer, adding selection
                bbRect = self.canvas().mapSettings().mapToLayerCoordinates(self.plugin.TILayer, r)
                features = self.plugin.TILayer.getFeatures(bbRect)
                for f in features:
                    self.addFeature(f)

            self.rubberband.hide()

    def showRect(self, startPoint: QgsPointXY, endPoint: QgsPointXY):
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

    def rectangle(self) -> QgsRectangle:
        """
        Builds rectangle from self.startPoint and self.endPoint
        """
        if self.startPoint is None or self.endPoint is None:
            return None
        elif self.startPoint.x() == self.endPoint.x() or self.startPoint.y() == self.endPoint.y():
            return None
        return QgsRectangle(self.startPoint, self.endPoint)

    def addFeature(self, feature: QgsFeature):
        self.plugin.TILayer.select(feature.id())

    def removeFeature(self, feature: QgsFeature):
        self.plugin.TILayer.deselect(feature.id())

    def setSelectedFeatures(self, features: List[QgsFeature]):
        self.plugin.TILayer.selectByIds([f.id() for f in features])

    def deselectFeatures(self):
        self.plugin.TILayer.removeSelection()

    def getSelectedFeature(self) -> List[QgsFeature]:
        return self.plugin.TILayer.selectedFeatures()

    def addAnnotation(self, feature: QgsFeature, layer: QgsVectorLayer):

        if feature not in set(self.annotation_features.keys()):

            geom = feature.geometry().asPoint()

            annot = QgsTextAnnotation()
            annot.setDocument(QTextDocument('test'))
            annot.setFrameSize(QSizeF(100, 100))
            # annot.setAssociatedFeature(feature)
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
