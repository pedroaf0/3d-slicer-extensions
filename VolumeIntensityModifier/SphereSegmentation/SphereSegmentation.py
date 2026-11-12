import json
import os
import traceback

import numpy as np

import ctk
import qt
import vtk

import slicer
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
)
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin


def _markupEventConstant(name):
    """Return a VTK event id from the markups node or its base node class."""
    event = getattr(slicer.vtkMRMLMarkupsNode, name, None)
    if event is None:
        event = getattr(slicer.vtkMRMLNode, name, None)
    return event


# =============================================================================
# Logic
# =============================================================================

class SphereSegmentationLogic(ScriptedLoadableModuleLogic):
    """Creates sphere masks and writes them into segmentations."""

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        self.undoStack = []

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def createSphereMask(self, volumeNode, centerRAS, radiusMM):
        """Return a boolean mask (Z, Y, X) for a sphere in volume voxel space.

        The calculation is limited to the sphere's bounding box, so large
        volumes are not scanned unnecessarily. Spacing is respected, which
        keeps the shape spherical in physical (millimeter) space even when
        the voxels are anisotropic.
        """
        if volumeNode is None:
            raise ValueError("No reference volume selected.")
        imageData = volumeNode.GetImageData()
        if imageData is None:
            raise RuntimeError("The selected volume has no image data.")

        radiusMM = float(radiusMM)
        if radiusMM <= 0.0:
            raise ValueError("Sphere radius must be greater than zero.")

        dimensions = imageData.GetDimensions()  # x, y, z
        nx, ny, nz = int(dimensions[0]), int(dimensions[1]), int(dimensions[2])
        if nx <= 0 or ny <= 0 or nz <= 0:
            raise RuntimeError("The selected volume is empty.")

        # RAS -> IJK
        ijkToRAS = vtk.vtkMatrix4x4()
        volumeNode.GetIJKToRASMatrix(ijkToRAS)
        rasToIJK = vtk.vtkMatrix4x4()
        rasToIJK.DeepCopy(ijkToRAS)
        rasToIJK.Invert()

        centerRAS4 = [float(centerRAS[0]), float(centerRAS[1]), float(centerRAS[2]), 1.0]
        centerIJK = [0.0, 0.0, 0.0, 0.0]
        rasToIJK.MultiplyPoint(centerRAS4, centerIJK)
        centerI, centerJ, centerK = centerIJK[0], centerIJK[1], centerIJK[2]

        # A physical sphere maps to an ellipsoid in IJK space. Use the rows of
        # the RAS->IJK linear transform to get conservative bounds for each
        # voxel axis, so oblique volumes are handled correctly too.
        rasToIJKLinear = np.array(
            [[rasToIJK.GetElement(row, column) for column in range(3)] for row in range(3)],
            dtype=float,
        )
        extentI = radiusMM * float(np.linalg.norm(rasToIJKLinear[0, :]))
        extentJ = radiusMM * float(np.linalg.norm(rasToIJKLinear[1, :]))
        extentK = radiusMM * float(np.linalg.norm(rasToIJKLinear[2, :]))

        i0 = max(0, int(np.floor(centerI - extentI)))
        i1 = min(nx - 1, int(np.ceil(centerI + extentI)))
        j0 = max(0, int(np.floor(centerJ - extentJ)))
        j1 = min(ny - 1, int(np.ceil(centerJ + extentJ)))
        k0 = max(0, int(np.floor(centerK - extentK)))
        k1 = min(nz - 1, int(np.ceil(centerK + extentK)))

        mask = np.zeros((nz, ny, nx), dtype=bool)
        if i0 > i1 or j0 > j1 or k0 > k1:
            return mask

        kk, jj, ii = np.mgrid[k0:k1 + 1, j0:j1 + 1, i0:i1 + 1]
        # Compare distances in RAS so the result is spherical in physical
        # space even when spacing is anisotropic or the volume is oblique.
        rasX = (
            ijkToRAS.GetElement(0, 0) * ii
            + ijkToRAS.GetElement(0, 1) * jj
            + ijkToRAS.GetElement(0, 2) * kk
            + ijkToRAS.GetElement(0, 3)
        )
        rasY = (
            ijkToRAS.GetElement(1, 0) * ii
            + ijkToRAS.GetElement(1, 1) * jj
            + ijkToRAS.GetElement(1, 2) * kk
            + ijkToRAS.GetElement(1, 3)
        )
        rasZ = (
            ijkToRAS.GetElement(2, 0) * ii
            + ijkToRAS.GetElement(2, 1) * jj
            + ijkToRAS.GetElement(2, 2) * kk
            + ijkToRAS.GetElement(2, 3)
        )
        dx = rasX - centerRAS[0]
        dy = rasY - centerRAS[1]
        dz = rasZ - centerRAS[2]
        localMask = (dx * dx + dy * dy + dz * dz) <= radiusMM * radiusMM
        mask[k0:k1 + 1, j0:j1 + 1, i0:i1 + 1] = localMask
        return mask

    def createPatternSphereMask(
        self,
        volumeNode,
        centerRAS,
        radiusMM,
        shapePattern="uniform",
        distortion=0.25,
        frequency=3,
        controlPointsRAS=None,
        seed=1,
    ):
        """Create a sphere with a uniform, distorted, dented, lobulated, or path shape."""
        shapePattern = str(shapePattern)
        if shapePattern == "uniform":
            return self.createSphereMask(volumeNode, centerRAS, radiusMM)

        if volumeNode is None or volumeNode.GetImageData() is None:
            raise ValueError("A reference volume with image data is required.")
        radiusMM = float(radiusMM)
        if radiusMM <= 0.0:
            raise ValueError("Sphere radius must be greater than zero.")
        if shapePattern not in ("smooth", "dented", "lobulated", "multi_point"):
            raise ValueError("Unknown sphere deformation pattern: {}".format(shapePattern))
        if shapePattern == "multi_point" and (
            controlPointsRAS is None or len(controlPointsRAS) == 0
        ):
            raise ValueError(
                "Select at least one additional markup point for the multi-point lesion."
            )

        distortion = min(max(float(distortion), 0.0), 0.8)
        frequency = min(max(int(frequency), 1), 12)
        points = [[float(value) for value in centerRAS[:3]]]
        if shapePattern == "multi_point":
            points.extend(
                [[float(value) for value in point[:3]] for point in (controlPointsRAS or [])]
            )
        points = np.asarray(points, dtype=float)

        imageData = volumeNode.GetImageData()
        nx, ny, nz = [int(value) for value in imageData.GetDimensions()]
        ijkToRAS = vtk.vtkMatrix4x4()
        volumeNode.GetIJKToRASMatrix(ijkToRAS)
        rasToIJK = vtk.vtkMatrix4x4()
        rasToIJK.DeepCopy(ijkToRAS)
        rasToIJK.Invert()
        rasToIJKLinear = np.array(
            [[rasToIJK.GetElement(row, column) for column in range(3)] for row in range(3)],
            dtype=float,
        )

        maxRadius = radiusMM * (1.0 + distortion)
        extent = maxRadius * np.linalg.norm(rasToIJKLinear, axis=1)
        pointIJK = []
        for point in points:
            ijk = [0.0, 0.0, 0.0, 0.0]
            rasToIJK.MultiplyPoint([point[0], point[1], point[2], 1.0], ijk)
            pointIJK.append(ijk[:3])
        pointIJK = np.asarray(pointIJK, dtype=float)
        lower = np.min(pointIJK, axis=0) - extent
        upper = np.max(pointIJK, axis=0) + extent
        i0, j0, k0 = [max(0, int(np.floor(value))) for value in lower]
        i1 = min(nx - 1, int(np.ceil(upper[0])))
        j1 = min(ny - 1, int(np.ceil(upper[1])))
        k1 = min(nz - 1, int(np.ceil(upper[2])))

        mask = np.zeros((nz, ny, nx), dtype=bool)
        if i0 > i1 or j0 > j1 or k0 > k1:
            return mask

        kk, jj, ii = np.mgrid[k0:k1 + 1, j0:j1 + 1, i0:i1 + 1]
        rasX = (
            ijkToRAS.GetElement(0, 0) * ii
            + ijkToRAS.GetElement(0, 1) * jj
            + ijkToRAS.GetElement(0, 2) * kk
            + ijkToRAS.GetElement(0, 3)
        )
        rasY = (
            ijkToRAS.GetElement(1, 0) * ii
            + ijkToRAS.GetElement(1, 1) * jj
            + ijkToRAS.GetElement(1, 2) * kk
            + ijkToRAS.GetElement(1, 3)
        )
        rasZ = (
            ijkToRAS.GetElement(2, 0) * ii
            + ijkToRAS.GetElement(2, 1) * jj
            + ijkToRAS.GetElement(2, 2) * kk
            + ijkToRAS.GetElement(2, 3)
        )

        # Find distance to the closest point on the control-point polyline.
        # The segment index and projection fraction also provide a stable
        # coordinate for repeating the deformation along a multi-point lesion.
        bestDistanceSquared = np.full(rasX.shape, np.inf, dtype=float)
        pathPosition = np.zeros(rasX.shape, dtype=float)
        segmentCount = max(1, len(points) - 1)
        segments = [(points[0], points[0])] if len(points) == 1 else zip(points[:-1], points[1:])
        for segmentIndex, (start, end) in enumerate(segments):
            direction = end - start
            lengthSquared = float(np.dot(direction, direction))
            if lengthSquared > 0.0:
                projection = np.clip(
                    ((rasX - start[0]) * direction[0]
                     + (rasY - start[1]) * direction[1]
                     + (rasZ - start[2]) * direction[2]) / lengthSquared,
                    0.0,
                    1.0,
                )
            else:
                projection = np.zeros(rasX.shape, dtype=float)
            closestX = start[0] + projection * direction[0]
            closestY = start[1] + projection * direction[1]
            closestZ = start[2] + projection * direction[2]
            distanceSquared = (
                (rasX - closestX) ** 2
                + (rasY - closestY) ** 2
                + (rasZ - closestZ) ** 2
            )
            closer = distanceSquared < bestDistanceSquared
            bestDistanceSquared[closer] = distanceSquared[closer]
            pathPosition[closer] = (
                (segmentIndex + projection[closer]) / float(segmentCount)
            )

        distance = np.sqrt(bestDistanceSquared)
        if shapePattern == "multi_point":
            phase = float(seed) * 0.61803398875
            localRadius = radiusMM * (
                1.0 + distortion * np.sin(2.0 * np.pi * frequency * pathPosition + phase)
            )
        else:
            dx = rasX - points[0, 0]
            dy = rasY - points[0, 1]
            dz = rasZ - points[0, 2]
            theta = np.arctan2(dy, dx)
            phi = np.arctan2(np.sqrt(dx * dx + dy * dy), dz)
            phase = float(seed) * 0.61803398875
            wave = np.sin(frequency * theta + phase) * np.cos(frequency * phi - phase)
            if shapePattern == "smooth":
                factor = 1.0 + distortion * 0.5 * wave
            elif shapePattern == "dented":
                dents = np.maximum(0.0, wave) ** 4
                factor = 1.0 - distortion * dents
            else:  # lobulated
                factor = 1.0 + distortion * np.abs(wave)
            localRadius = radiusMM * factor

        mask[k0:k1 + 1, j0:j1 + 1, i0:i1 + 1] = distance <= localRadius
        return mask

    # ------------------------------------------------------------------
    # Segmentation helpers
    # ------------------------------------------------------------------
    def _ensureBinaryLabelmapRepresentation(self, segmentationNode):
        segmentation = segmentationNode.GetSegmentation()
        if segmentation is None:
            raise RuntimeError("The output segmentation is invalid.")

        sourceRepresentation = ""
        try:
            sourceRepresentation = segmentation.GetSourceRepresentationName()
        except Exception:
            pass

        if sourceRepresentation == "Binary labelmap":
            return

        # ImportLabelmapToSegmentationNode only accepts a segmentation whose
        # source representation is binary labelmap. Surface-based segmentations
        # are converted once, then remain editable as labelmaps.
        if hasattr(segmentationNode, "CreateBinaryLabelmapRepresentation"):
            converted = segmentationNode.CreateBinaryLabelmapRepresentation()
        else:
            converted = segmentation.CreateRepresentation("Binary labelmap")
        if converted is False:
            raise RuntimeError(
                "Could not create a binary labelmap representation for the output segmentation."
            )

        try:
            segmentation.SetSourceRepresentationName("Binary labelmap")
        except Exception:
            # Older Slicer versions used the "master" terminology.
            try:
                segmentation.SetMasterRepresentationName("Binary labelmap")
            except Exception:
                pass

        try:
            if segmentation.GetSourceRepresentationName() != "Binary labelmap":
                raise RuntimeError(
                    "The output segmentation could not be switched to binary labelmap storage."
                )
        except RuntimeError:
            raise
        except Exception:
            pass

    def updateSegmentFromMask(self, segmentationNode, segmentId, mask, referenceVolumeNode):
        """Write a boolean mask into a segment's binary labelmap."""
        if segmentationNode is None or not segmentId:
            raise ValueError("Invalid segmentation or segment.")
        if referenceVolumeNode is None:
            raise ValueError("A reference volume is required to define the mask geometry.")

        maskU8 = np.ascontiguousarray(np.asarray(mask, dtype=np.uint8))

        if hasattr(slicer.util, "updateSegmentBinaryLabelmapFromArray"):
            slicer.util.updateSegmentBinaryLabelmapFromArray(
                maskU8, segmentationNode, segmentId, referenceVolumeNode
            )
            return

        # Compatibility fallback for older Slicer versions.
        from vtk.util import numpy_support

        imageData = referenceVolumeNode.GetImageData()
        if imageData is None:
            raise RuntimeError("The reference volume has no image data.")

        orientedImage = slicer.vtkOrientedImageData()
        orientedImage.SetExtent(imageData.GetExtent())
        orientedImage.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)

        ijkToRAS = vtk.vtkMatrix4x4()
        referenceVolumeNode.GetIJKToRASMatrix(ijkToRAS)
        orientedImage.SetGeometryFromImageToWorldMatrix(ijkToRAS)

        flat = maskU8.ravel(order="C")
        vtkArray = numpy_support.numpy_to_vtk(
            flat, deep=True, array_type=vtk.VTK_UNSIGNED_CHAR
        )
        vtkArray.SetNumberOfComponents(1)
        orientedImage.GetPointData().SetScalars(vtkArray)
        orientedImage.Modified()

        success = slicer.vtkSlicerSegmentationsModuleLogic.SetBinaryLabelmapToSegment(
            orientedImage,
            segmentationNode,
            segmentId,
            slicer.vtkSlicerSegmentationsModuleLogic.MODE_REPLACE,
        )
        if not success:
            raise RuntimeError("Failed to write the mask into the segment.")

    def createClosedSurfaceRepresentation(self, segmentationNode):
        """Create the closed surface representation used by 3D views."""
        if hasattr(segmentationNode, "CreateClosedSurfaceRepresentation"):
            success = segmentationNode.CreateClosedSurfaceRepresentation()
        else:
            success = segmentationNode.GetSegmentation().CreateRepresentation("Closed surface")
        if success is False:
            raise RuntimeError(
                "Could not create the closed surface representation needed for 3D display."
            )

    def configureSegmentationDisplay(self, segmentationNode, segmentId=None):
        """Make a segmentation and its segment visible in 2D and 3D views."""
        if segmentationNode is None:
            return
        try:
            segmentationNode.CreateDefaultDisplayNodes()
        except Exception:
            pass

        displayNode = segmentationNode.GetDisplayNode()
        if displayNode is None:
            return

        for methodName, arguments in (
            ("SetVisibility", (True,)),
            ("SetVisibility3D", (True,)),
            ("SetVisibility2D", (True,)),
        ):
            method = getattr(displayNode, methodName, None)
            if method is not None:
                try:
                    method(*arguments)
                except Exception:
                    pass

        try:
            displayNode.SetOpacity3D(0.75)
        except Exception:
            pass

        if segmentId:
            for methodName in (
                "SetSegmentVisibility",
                "SetSegmentVisibility3D",
                "SetSegmentVisibility2DFill",
            ):
                method = getattr(displayNode, methodName, None)
                if method is not None:
                    try:
                        method(segmentId, True)
                    except Exception:
                        pass
            try:
                displayNode.SetSegmentVisibility2DOutline(segmentId, True)
            except Exception:
                pass

        try:
            displayNode.Modified()
        except Exception:
            pass
        try:
            segmentationNode.Modified()
        except Exception:
            pass

    def _uniqueSegmentName(self, segmentation, requestedName):
        requestedName = (requestedName or "Sphere").strip() or "Sphere"
        existingNames = set()
        for index in range(segmentation.GetNumberOfSegments()):
            segment = segmentation.GetSegment(segmentation.GetNthSegmentID(index))
            if segment is not None and segment.GetName():
                existingNames.add(segment.GetName())

        name = requestedName
        suffix = 2
        while name in existingNames:
            name = "{} {}".format(requestedName, suffix)
            suffix += 1
        return name

    # ------------------------------------------------------------------
    # Apply / undo
    # ------------------------------------------------------------------
    def applySphere(
        self,
        volumeNode,
        centerRAS,
        radiusMM,
        targetSegmentationNode=None,
        segmentName="Sphere",
        color=(1.0, 0.75, 0.10),
        shapePattern="uniform",
        distortion=0.25,
        frequency=3,
        controlPointsRAS=None,
        seed=1,
    ):
        """Create a sphere or deformed lesion segment and record undo."""
        mask = self.createPatternSphereMask(
            volumeNode,
            centerRAS,
            radiusMM,
            shapePattern=shapePattern,
            distortion=distortion,
            frequency=frequency,
            controlPointsRAS=controlPointsRAS,
            seed=seed,
        )
        voxelCount = int(np.count_nonzero(mask))
        if voxelCount == 0:
            raise RuntimeError(
                "The sphere does not intersect the selected volume. "
                "Check its center and radius."
            )

        createdSegmentation = False
        if targetSegmentationNode is None:
            targetSegmentationNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentationNode", "SphereSegmentation"
            )
            createdSegmentation = True
            # New segmentation nodes use binary labelmap as source
            # representation by default. Do not call the deprecated
            # SetMasterRepresentationToBinaryLabelmap(): in Slicer 5.12 it is
            # mistakenly wired to SetSourceRepresentationToClosedSurface().
            try:
                targetSegmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
            except Exception:
                pass

        segmentationNode = targetSegmentationNode
        segmentation = segmentationNode.GetSegmentation()

        # Convert before adding the new segment, so conversion only has to deal
        # with segments that already exist.
        try:
            self._ensureBinaryLabelmapRepresentation(segmentationNode)
        except Exception:
            if createdSegmentation:
                try:
                    slicer.mrmlScene.RemoveNode(segmentationNode)
                except Exception:
                    pass
            raise

        segmentName = self._uniqueSegmentName(segmentation, segmentName)
        # AddEmptySegment signature is (segmentId, segmentName, color).
        # Passing an empty ID lets Slicer generate a safe unique ID.
        segmentId = segmentation.AddEmptySegment("", segmentName)
        if not segmentId:
            # Extremely defensive fallback for API variations.
            for index in range(segmentation.GetNumberOfSegments()):
                candidateId = segmentation.GetNthSegmentID(index)
                candidate = segmentation.GetSegment(candidateId)
                if candidate is not None and candidate.GetName() == segmentName:
                    segmentId = candidateId
                    break
        if not segmentId:
            if createdSegmentation:
                try:
                    slicer.mrmlScene.RemoveNode(segmentationNode)
                except Exception:
                    pass
            raise RuntimeError("Could not create a new segment in the output segmentation.")

        segment = segmentation.GetSegment(segmentId)
        if segment is not None:
            try:
                segment.SetName(segmentName)
            except Exception:
                pass
            try:
                segment.SetColor(float(color[0]), float(color[1]), float(color[2]))
            except Exception:
                pass

        try:
            self.updateSegmentFromMask(segmentationNode, segmentId, mask, volumeNode)
            self.createClosedSurfaceRepresentation(segmentationNode)
            self.configureSegmentationDisplay(segmentationNode, segmentId)
        except Exception:
            # Never leave a half-created segment (or a brand-new segmentation
            # node) behind if representation creation fails.
            try:
                segmentation.RemoveSegment(segmentId)
            except Exception:
                pass
            if createdSegmentation:
                try:
                    slicer.mrmlScene.RemoveNode(segmentationNode)
                except Exception:
                    pass
            raise

        self.undoStack.append({
            "segmentationNodeID": segmentationNode.GetID(),
            "segmentID": segmentId,
            "segmentName": segmentName,
            "createdSegmentationNode": createdSegmentation,
            "voxelCount": voxelCount,
        })
        if len(self.undoStack) > 50:
            self.undoStack.pop(0)

        return segmentationNode, segmentId, voxelCount

    def canUndo(self):
        return len(self.undoStack) > 0

    def undoLast(self):
        """Remove the segment created by the most recent apply."""
        if not self.undoStack:
            return None

        entry = self.undoStack.pop()
        segmentationNode = slicer.mrmlScene.GetNodeByID(entry["segmentationNodeID"])
        if segmentationNode is None or segmentationNode.GetSegmentation() is None:
            return None

        segmentation = segmentationNode.GetSegmentation()
        if segmentation.GetSegment(entry["segmentID"]) is not None:
            try:
                segmentation.RemoveSegment(entry["segmentID"])
            except Exception:
                pass

        try:
            segmentationNode.Modified()
        except Exception:
            pass

        if entry.get("createdSegmentationNode") and segmentation.GetNumberOfSegments() == 0:
            try:
                slicer.mrmlScene.RemoveNode(segmentationNode)
            except Exception:
                pass

        return entry


# =============================================================================
# Widget
# =============================================================================

class SphereSegmentationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)

        self.logic = None

        # Preview state
        self.previewSegmentationNode = None
        self.previewSegmentId = None
        self.previewTimer = None
        self.pointRefreshTimer = None

        # Markup-point positioning
        self._selectedPointKey = ""
        self._linkedPointPosition = None
        self._availablePoints = []
        self._checkedControlPointKeys = set()
        self._markupObserverTags = []
        self._sceneObserverTags = []
        self._sceneObserverCallbacks = []

        # UI
        self.volumeSelector = None
        self.volumeInfoLabel = None
        self.outputSegmentationSelector = None
        self.segmentNameEdit = None
        self.pointCombo = None
        self.refreshPointsButton = None
        self.pointInfoLabel = None
        self.centerXSpin = None
        self.centerYSpin = None
        self.centerZSpin = None
        self.radiusSpin = None
        self.shapePatternCombo = None
        self.distortionSpin = None
        self.frequencySpin = None
        self.seedSpin = None
        self.controlPointsList = None
        self.presetCombo = None
        self.loadPresetButton = None
        self.deletePresetButton = None
        self.previewButton = None
        self.applyButton = None
        self.undoButton = None
        self.clearPreviewButton = None
        self.previewInfoLabel = None
        self.statusLabel = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = SphereSegmentationLogic()

        try:
            self._buildUi()
        except Exception:
            traceback.print_exc()
            slicer.util.errorDisplay(
                _("Failed to create the Sphere Segmentation interface.\n")
                + traceback.format_exc()
            )
            return

        self._setupPreviewTimer()
        self._setupPointRefreshTimer()
        self._setupMarkupObservers()
        self._refreshPointList()
        self._autoSelectSingleVolume()
        self._onVolumeChanged()
        self.updateState()

    def _buildUi(self):
        title = qt.QLabel("<h3>Sphere Segmentation</h3>")
        self.layout.addWidget(title)

        instructions = qt.QLabel(
            "Creates a spherical segment. Place a markup point in the scene and "
            "select it under <b>Position from point</b> to copy its world RAS "
            "position to the sphere center. Choose a shape pattern for smooth "
            "distortion, dents, lobes, or a lesion swept through several checked "
            "markup points. Use <b>Preview</b> to display it in 2D and 3D, then "
            "<b>Apply</b> to "
            "add it to the output segmentation. Applied spheres can be removed "
            "with <b>Undo</b>."
        )
        instructions.wordWrap = True
        self.layout.addWidget(instructions)

        self._buildInputSection()
        self._buildSphereSection()
        self._buildPresetSection()
        self._buildActionSection()

        # Connect only after all widgets exist so callbacks never run while the
        # interface is incomplete (the cause of the previous missing buttons).
        self.volumeSelector.currentNodeChanged.connect(self._onVolumeChanged)

        self.statusLabel = qt.QLabel(_("Select a reference volume."))
        self.statusLabel.wordWrap = True
        self.statusLabel.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        self.layout.addWidget(self.statusLabel)

        self.layout.addStretch(1)

    def _buildInputSection(self):
        box = ctk.ctkCollapsibleButton()
        box.text = _("Reference volume and output segmentation")
        box.collapsed = False
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)
        form = qt.QFormLayout()
        layout.addLayout(form)

        self.volumeSelector = slicer.qMRMLNodeComboBox()
        self.volumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.volumeSelector.selectNodeUponCreation = False
        self.volumeSelector.addEnabled = False
        self.volumeSelector.removeEnabled = False
        self.volumeSelector.noneEnabled = True
        self.volumeSelector.showHidden = False
        self.volumeSelector.showChildNodeTypes = False
        self.volumeSelector.setMRMLScene(slicer.mrmlScene)
        self.volumeSelector.toolTip = _("Volume that defines the geometry of the sphere mask.")
        form.addRow(_("Reference volume:"), self.volumeSelector)

        self.volumeInfoLabel = qt.QLabel(_("No volume selected."))
        self.volumeInfoLabel.wordWrap = True
        self.volumeInfoLabel.setStyleSheet("color: #666; font-size: 8pt;")
        form.addRow("", self.volumeInfoLabel)

        self.outputSegmentationSelector = slicer.qMRMLNodeComboBox()
        self.outputSegmentationSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
        self.outputSegmentationSelector.selectNodeUponCreation = True
        self.outputSegmentationSelector.addEnabled = True
        self.outputSegmentationSelector.removeEnabled = False
        self.outputSegmentationSelector.noneEnabled = True
        self.outputSegmentationSelector.showHidden = False
        self.outputSegmentationSelector.showChildNodeTypes = False
        self.outputSegmentationSelector.setMRMLScene(slicer.mrmlScene)
        self.outputSegmentationSelector.toolTip = (
            "Segmentation that receives the sphere. Leave empty to create a new "
            "'SphereSegmentation' node when applying."
        )
        form.addRow(_("Output segmentation:"), self.outputSegmentationSelector)

        self.segmentNameEdit = qt.QLineEdit("Sphere")
        self.segmentNameEdit.toolTip = "Name of the segment that will be created."
        form.addRow(_("Segment name:"), self.segmentNameEdit)

    def _buildSphereSection(self):
        box = ctk.ctkCollapsibleButton()
        box.text = _("Sphere geometry")
        box.collapsed = False
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)
        form = qt.QFormLayout()
        layout.addLayout(form)

        pointRow = qt.QHBoxLayout()
        self.pointCombo = qt.QComboBox()
        self.pointCombo.toolTip = (
            "Select a markup point placed in the scene. Its world RAS position "
            "is used directly as the sphere center."
        )
        self.pointCombo.currentIndexChanged.connect(self._onPointSelected)
        pointRow.addWidget(self.pointCombo, 1)

        self.refreshPointsButton = qt.QPushButton(_("Refresh"))
        self.refreshPointsButton.toolTip = (
            "Reload the list of markup points from the scene."
        )
        self.refreshPointsButton.clicked.connect(self._onRefreshPoints)
        pointRow.addWidget(self.refreshPointsButton)
        form.addRow(_("Position from point:"), pointRow)

        self.pointInfoLabel = qt.QLabel(_("No point selected."))
        self.pointInfoLabel.wordWrap = True
        self.pointInfoLabel.setStyleSheet("color: #666; font-size: 8pt;")
        form.addRow("", self.pointInfoLabel)

        for axis, label in enumerate(("X", "Y", "Z")):
            spin = qt.QDoubleSpinBox()
            spin.minimum = -100000.0
            spin.maximum = 100000.0
            spin.decimals = 2
            spin.singleStep = 1.0
            spin.value = 0.0
            spin.toolTip = "Sphere center {} coordinate in world RAS millimeters.".format(label)
            form.addRow(_("Center {} (mm):").format(label), spin)
            spin.valueChanged.connect(self._onCenterParameterChanged)
            if axis == 0:
                self.centerXSpin = spin
            elif axis == 1:
                self.centerYSpin = spin
            else:
                self.centerZSpin = spin

        self.radiusSpin = qt.QDoubleSpinBox()
        self.radiusSpin.minimum = 0.10
        self.radiusSpin.maximum = 1000.0
        self.radiusSpin.decimals = 2
        self.radiusSpin.singleStep = 1.0
        self.radiusSpin.value = 5.0
        self.radiusSpin.toolTip = "Sphere radius in millimeters."
        self.radiusSpin.valueChanged.connect(self._onSphereParameterChanged)
        form.addRow(_("Radius (mm):"), self.radiusSpin)

        self.shapePatternCombo = qt.QComboBox()
        self.shapePatternCombo.addItem(_("Uniform sphere"), "uniform")
        self.shapePatternCombo.addItem(_("Smooth distortion"), "smooth")
        self.shapePatternCombo.addItem(_("Dented surface"), "dented")
        self.shapePatternCombo.addItem(_("Lobulated surface"), "lobulated")
        self.shapePatternCombo.addItem(_("Multi-point lesion (connect points)"), "multi_point")
        self.shapePatternCombo.toolTip = _(
            "Choose a regular sphere, a smoothly distorted/dented/lobulated surface, "
            "or a swept lesion passing through selected markup points."
        )
        self.shapePatternCombo.currentIndexChanged.connect(self._onShapePatternChanged)
        form.addRow(_("Shape pattern:"), self.shapePatternCombo)

        centerRow = qt.QHBoxLayout()
        centerOnVolumeButton = qt.QPushButton(_("Center on volume"))
        centerOnVolumeButton.toolTip = "Place the sphere center at the center of the reference volume."
        centerOnVolumeButton.clicked.connect(self._onCenterOnVolume)
        centerRow.addWidget(centerOnVolumeButton)

        crosshairButton = qt.QPushButton(_("Use crosshair"))
        crosshairButton.toolTip = (
            "Place the sphere center at the current slice crosshair position. "
            "Move the crosshair in the slice views to position the sphere."
        )
        crosshairButton.clicked.connect(self._onUseCrosshair)
        centerRow.addWidget(crosshairButton)
        form.addRow("", centerRow)

        deformationBox = ctk.ctkCollapsibleButton()
        deformationBox.text = _("Deformation settings and origin points")
        deformationBox.collapsed = True
        layout.addWidget(deformationBox)
        deformationForm = qt.QFormLayout(deformationBox)

        self.distortionSpin = qt.QDoubleSpinBox()
        self.distortionSpin.minimum = 0.0
        self.distortionSpin.maximum = 80.0
        self.distortionSpin.decimals = 0
        self.distortionSpin.singleStep = 5.0
        self.distortionSpin.value = 25.0
        self.distortionSpin.suffix = "%"
        self.distortionSpin.toolTip = _(
            "Strength of the radial deformation. Higher values create deeper dents "
            "or stronger lobes."
        )
        self.distortionSpin.valueChanged.connect(self._onSphereParameterChanged)
        deformationForm.addRow(_("Deformation strength:"), self.distortionSpin)

        self.frequencySpin = qt.QSpinBox()
        self.frequencySpin.minimum = 1
        self.frequencySpin.maximum = 12
        self.frequencySpin.value = 3
        self.frequencySpin.toolTip = _(
            "Number of repeated surface features, or radius changes along a multi-point path."
        )
        self.frequencySpin.valueChanged.connect(self._onSphereParameterChanged)
        deformationForm.addRow(_("Pattern frequency:"), self.frequencySpin)

        self.seedSpin = qt.QSpinBox()
        self.seedSpin.minimum = 0
        self.seedSpin.maximum = 1000000
        self.seedSpin.value = 1
        self.seedSpin.toolTip = _(
            "Changes the deterministic orientation/phase of the surface pattern."
        )
        self.seedSpin.valueChanged.connect(self._onSphereParameterChanged)
        deformationForm.addRow(_("Pattern seed:"), self.seedSpin)

        self.controlPointsList = qt.QListWidget()
        self.controlPointsList.minimumHeight = 120
        self.controlPointsList.maximumHeight = 180
        self.controlPointsList.setToolTip(_(
            "Check one or more markup points. In the multi-point pattern, the lesion "
            "is swept through them in listed order, starting at the sphere center."
        ))
        self.controlPointsList.itemChanged.connect(self._onControlPointCheckChanged)
        deformationForm.addRow(_("Additional origin points:"), self.controlPointsList)
        self._updateShapeControlState()

    def _buildPresetSection(self):
        box = ctk.ctkCollapsibleButton()
        box.text = _("Parameter presets (JSON)")
        box.collapsed = True
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)

        self.presetCombo = qt.QComboBox()
        self.presetCombo.minimumHeight = 28
        self.presetCombo.toolTip = _(
            "Select a saved radius and shape-pattern configuration. Spatial positions are not saved."
        )
        layout.addWidget(self.presetCombo)

        buttons = qt.QHBoxLayout()
        self.loadPresetButton = qt.QPushButton(_("Load"))
        self.loadPresetButton.clicked.connect(self._onLoadPreset)
        buttons.addWidget(self.loadPresetButton)

        saveButton = qt.QPushButton(_("Save current parameters"))
        saveButton.clicked.connect(self._onSavePreset)
        buttons.addWidget(saveButton, 1)

        self.deletePresetButton = qt.QPushButton(_("Delete"))
        self.deletePresetButton.clicked.connect(self._onDeletePreset)
        buttons.addWidget(self.deletePresetButton)
        layout.addLayout(buttons)
        self._refreshPresetCombo()

    def _presetFilePath(self):
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "sphere_parameter_presets.json"
        )

    def _readPresets(self):
        path = self._presetFilePath()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as presetFile:
                data = json.load(presetFile)
            presets = data.get("presets", []) if isinstance(data, dict) else []
            return [
                preset for preset in presets
                if isinstance(preset, dict)
                and isinstance(preset.get("name"), str)
                and preset.get("name", "").strip()
                and isinstance(preset.get("parameters"), dict)
            ]
        except Exception as exc:
            slicer.util.warningDisplay(
                _("Could not read sphere presets from {}: {}").format(path, exc)
            )
            return []

    def _writePresets(self, presets):
        path = self._presetFilePath()
        temporaryPath = path + ".tmp"
        try:
            with open(temporaryPath, "w", encoding="utf-8") as presetFile:
                json.dump(
                    {"version": 1, "presets": presets},
                    presetFile,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            os.replace(temporaryPath, path)
            return True
        except Exception as exc:
            try:
                if os.path.exists(temporaryPath):
                    os.remove(temporaryPath)
            except Exception:
                pass
            slicer.util.warningDisplay(
                _("Could not save sphere presets to {}: {}\n"
                  "Check that the plugin folder is writable.").format(path, exc)
            )
            return False

    def _refreshPresetCombo(self, selectedName=None):
        if self.presetCombo is None:
            return
        if selectedName is None and self.presetCombo.count:
            selectedName = self.presetCombo.currentData
        self.presetCombo.blockSignals(True)
        self.presetCombo.clear()
        presets = sorted(self._readPresets(), key=lambda item: item["name"].casefold())
        for preset in presets:
            self.presetCombo.addItem(preset["name"], preset["name"])
        selectedIndex = self.presetCombo.findData(selectedName) if selectedName else -1
        if selectedIndex >= 0:
            self.presetCombo.setCurrentIndex(selectedIndex)
        self.presetCombo.blockSignals(False)
        hasPresets = self.presetCombo.count > 0
        self.presetCombo.enabled = hasPresets
        self.loadPresetButton.enabled = hasPresets
        self.deletePresetButton.enabled = hasPresets

    def _currentPresetParameters(self):
        centerRAS = self._sphereParameters()["centerRAS"]
        controlPointsRAS = []
        for entry in self._availablePoints:
            if entry["key"] not in self._checkedControlPointKeys:
                continue
            pointIndex = self._findPointIndexById(entry)
            if pointIndex is None:
                continue
            position = self._pointWorldPosition(entry["node"], pointIndex)
            if position is not None:
                controlPointsRAS.append(position)
        return {
            "centerRAS": centerRAS,
            "radiusMM": float(self.radiusSpin.value),
            "shapePattern": str(self.shapePatternCombo.currentData),
            "distortion": float(self.distortionSpin.value),
            "frequency": int(self.frequencySpin.value),
            "seed": int(self.seedSpin.value),
            "controlPointsRAS": controlPointsRAS,
        }

    def _onSavePreset(self):
        result = qt.QInputDialog.getText(
            slicer.util.mainWindow(), _("Save sphere preset"), _("Preset name:")
        )
        if isinstance(result, tuple):
            name, accepted = result
        else:
            name, accepted = result, bool(result)
        name = str(name).strip()
        if not accepted or not name:
            return

        presets = self._readPresets()
        existingIndex = next(
            (index for index, preset in enumerate(presets)
             if preset["name"].casefold() == name.casefold()),
            None,
        )
        if existingIndex is not None:
            answer = qt.QMessageBox.question(
                slicer.util.mainWindow(),
                _("Replace preset?"),
                _("A preset named '{}' already exists. Replace it?").format(name),
                qt.QMessageBox.Yes | qt.QMessageBox.No,
                qt.QMessageBox.No,
            )
            if answer != qt.QMessageBox.Yes:
                return
            presets.pop(existingIndex)
        presets.append({"name": name, "parameters": self._currentPresetParameters()})
        if self._writePresets(presets):
            self._refreshPresetCombo(name)

    def _onLoadPreset(self):
        name = self.presetCombo.currentData if self.presetCombo else None
        preset = next(
            (item for item in self._readPresets() if item["name"] == name), None
        )
        if preset is None:
            return
        parameters = preset["parameters"]
        patternIndex = self.shapePatternCombo.findData(
            parameters.get("shapePattern", "uniform")
        )
        if patternIndex >= 0:
            self.shapePatternCombo.setCurrentIndex(patternIndex)
        if "radiusMM" in parameters:
            self.radiusSpin.value = float(parameters["radiusMM"])
        if "distortion" in parameters:
            self.distortionSpin.value = float(parameters["distortion"])
        if "frequency" in parameters:
            self.frequencySpin.value = int(parameters["frequency"])
        if "seed" in parameters:
            self.seedSpin.value = int(parameters["seed"])

        centerRAS = parameters.get("centerRAS")
        if isinstance(centerRAS, list) and len(centerRAS) == 3:
            self._detachSelectedPoint()
            for spin, value in zip(
                (self.centerXSpin, self.centerYSpin, self.centerZSpin), centerRAS
            ):
                spin.value = float(value)

        savedPoints = parameters.get("controlPointsRAS", [])
        self._checkedControlPointKeys.clear()
        unmatchedPoints = list(savedPoints) if isinstance(savedPoints, list) else []
        for entry in self._availablePoints:
            position = entry.get("position")
            if position is None:
                continue
            for index, savedPoint in enumerate(unmatchedPoints):
                if not isinstance(savedPoint, list) or len(savedPoint) != 3:
                    continue
                if all(abs(float(position[axis]) - float(savedPoint[axis])) < 0.01
                       for axis in range(3)):
                    self._checkedControlPointKeys.add(entry["key"])
                    unmatchedPoints.pop(index)
                    break
        self._refreshPointList()
        if unmatchedPoints:
            slicer.util.warningDisplay(_(
                "Preset loaded, but {} saved origin point(s) were not found in the current scene."
            ).format(len(unmatchedPoints)))
        self._schedulePreviewUpdate()
        self.updateState()

    def _onDeletePreset(self):
        name = self.presetCombo.currentData if self.presetCombo else None
        if not name:
            return
        answer = qt.QMessageBox.question(
            slicer.util.mainWindow(),
            _("Delete preset?"),
            _("Delete the saved preset '{}'?").format(name),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.No,
        )
        if answer != qt.QMessageBox.Yes:
            return
        presets = [item for item in self._readPresets() if item["name"] != name]
        if self._writePresets(presets):
            self._refreshPresetCombo()

    def _buildActionSection(self):
        box = ctk.ctkCollapsibleButton()
        box.text = _("Preview, apply, and undo")
        box.collapsed = False
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)

        self.previewButton = qt.QPushButton(_("Preview sphere (2D + 3D)"))
        self.previewButton.toolTip = (
            "Create a temporary segmentation with the sphere and show its 3D "
            "surface and slice outline before applying."
        )
        self.previewButton.clicked.connect(self._onPreview)
        layout.addWidget(self.previewButton)

        self.applyButton = qt.QPushButton(_("Apply sphere to segmentation"))
        self.applyButton.toolTip = (
            "Add the sphere as a new segment in the output segmentation. "
            "A new segmentation is created if none is selected."
        )
        self.applyButton.clicked.connect(self._onApply)
        layout.addWidget(self.applyButton)

        self.undoButton = qt.QPushButton(_("Undo last applied sphere"))
        self.undoButton.toolTip = "Remove the segment created by the most recent apply."
        self.undoButton.clicked.connect(self._onUndo)
        layout.addWidget(self.undoButton)

        self.clearPreviewButton = qt.QPushButton(_("Clear preview"))
        self.clearPreviewButton.toolTip = "Remove the temporary preview segmentation from the scene."
        self.clearPreviewButton.clicked.connect(self._onClearPreview)
        layout.addWidget(self.clearPreviewButton)

        self.previewInfoLabel = qt.QLabel(_("No preview active."))
        self.previewInfoLabel.wordWrap = True
        self.previewInfoLabel.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        layout.addWidget(self.previewInfoLabel)

    def _setupPreviewTimer(self):
        self.previewTimer = qt.QTimer()
        self.previewTimer.setSingleShot(True)
        self.previewTimer.setInterval(250)
        self.previewTimer.timeout.connect(self._updatePreviewFromParameters)

    def _setupPointRefreshTimer(self):
        self.pointRefreshTimer = qt.QTimer()
        self.pointRefreshTimer.setSingleShot(True)
        self.pointRefreshTimer.setInterval(0)
        self.pointRefreshTimer.timeout.connect(self._refreshPointList)

    # ------------------------------------------------------------------
    # Markup point positioning
    # ------------------------------------------------------------------
    def _setupMarkupObservers(self):
        scene = slicer.mrmlScene
        # Use integer VTK event ids. String event names are accepted by
        # AddObserver but do not trigger Python callbacks in this Slicer build.
        # Keep strong references to the bound callbacks as well.
        for event in (
            slicer.vtkMRMLScene.NodeAddedEvent,
            slicer.vtkMRMLScene.NodeRemovedEvent,
        ):
            callback = self._onSceneNodesChanged
            try:
                tag = scene.AddObserver(event, callback)
                self._sceneObserverTags.append(tag)
                self._sceneObserverCallbacks.append(callback)
            except Exception:
                pass
        callback = self._onNewScene
        try:
            tag = scene.AddObserver(slicer.vtkMRMLScene.NewSceneEvent, callback)
            self._sceneObserverTags.append(tag)
            self._sceneObserverCallbacks.append(callback)
        except Exception:
            pass

    def _fiducialNodes(self):
        nodes = []
        try:
            collection = slicer.mrmlScene.GetNodesByClass(
                "vtkMRMLMarkupsFiducialNode"
            )
        except Exception:
            return nodes

        for index in range(collection.GetNumberOfItems()):
            node = collection.GetItemAsObject(index)
            if node is not None:
                nodes.append(node)

        # Stable order makes the list predictable when several point nodes exist.
        nodes.sort(
            key=lambda node: (
                (node.GetName() or "").lower(),
                node.GetID() or "",
            )
        )
        return nodes

    def _clearMarkupObservers(self):
        for node, tag, callback in self._markupObserverTags:
            try:
                node.RemoveObserver(tag)
            except Exception:
                pass
        self._markupObserverTags = []

    def _observeMarkupNodes(self, nodes):
        self._clearMarkupObservers()
        structuralEvents = (
            _markupEventConstant("PointAddedEvent"),
            _markupEventConstant("PointRemovedEvent"),
            _markupEventConstant("PointEndInteractionEvent"),
            _markupEventConstant("LabelModifiedEvent"),
            _markupEventConstant("NameModifiedEvent"),
        )
        positionEvents = (
            _markupEventConstant("PointModifiedEvent"),
            _markupEventConstant("PointPositionDefinedEvent"),
            _markupEventConstant("TransformModifiedEvent"),
        )
        for node in nodes:
            structuralCallback = self._onMarkupStructureChanged
            for event in structuralEvents:
                if event is None:
                    continue
                try:
                    tag = node.AddObserver(event, structuralCallback)
                    self._markupObserverTags.append(
                        (node, tag, structuralCallback)
                    )
                except Exception:
                    pass
            positionCallback = self._onMarkupPointChanged
            for event in positionEvents:
                if event is None:
                    continue
                try:
                    tag = node.AddObserver(event, positionCallback)
                    self._markupObserverTags.append(
                        (node, tag, positionCallback)
                    )
                except Exception:
                    pass

    def _onSceneNodesChanged(self, caller, event):
        # Slicer passes the event as "NoEvent" to Python observers here, so
        # use separate callbacks rather than comparing the event string.
        # Defer the refresh: during NodeAddedEvent the new node may not be
        # visible through GetNodesByClass() yet.
        if self.pointRefreshTimer is not None:
            self.pointRefreshTimer.start()

    def _onNewScene(self, caller, event):
        self._selectedPointKey = ""
        self._linkedPointPosition = None
        if self.pointRefreshTimer is not None:
            self.pointRefreshTimer.start()

    def _onMarkupStructureChanged(self, caller, event):
        # Rebuild labels, indices, and the observer list after a point is
        # added/removed or after an interaction changes its displayed name.
        self._refreshPointList()

    def _onMarkupPointChanged(self, caller, event):
        self._syncCenterFromSelectedPoint(caller)
        if any(
            entry["key"] in self._checkedControlPointKeys
            and entry["node"].GetID() == caller.GetID()
            for entry in self._availablePoints
        ):
            if self.pointRefreshTimer is not None:
                self.pointRefreshTimer.start()
            self._schedulePreviewUpdate()

    def _pointWorldPosition(self, node, pointIndex):
        try:
            position = node.GetNthControlPointPositionWorld(pointIndex)
        except Exception:
            return None
        if position is None:
            return None
        try:
            if len(position) < 3:
                return None
            return [
                float(position[0]),
                float(position[1]),
                float(position[2]),
            ]
        except Exception:
            return None

    def _pointDisplayLabel(self, node, pointIndex, position=None):
        nodeName = (node.GetName() or node.GetID() or "Markup").strip()
        pointLabel = ""
        try:
            pointLabel = node.GetNthControlPointLabel(pointIndex) or ""
        except Exception:
            pass
        pointLabel = pointLabel.strip() or _("Point {}").format(pointIndex + 1)

        if pointLabel == nodeName:
            label = pointLabel
        else:
            label = "{}: {}".format(nodeName, pointLabel)

        if position is not None:
            label += " ({:.2f}, {:.2f}, {:.2f})".format(
                position[0], position[1], position[2]
            )
        return label

    def _refreshPointList(self):
        if self.pointCombo is None:
            return

        nodes = self._fiducialNodes()
        entries = []
        targetIndex = 0
        selectionLost = False

        self.pointCombo.blockSignals(True)
        try:
            self.pointCombo.clear()
            self.pointCombo.addItem(_("Select a markup point..."), "")

            for node in nodes:
                try:
                    pointCount = int(node.GetNumberOfControlPoints())
                except Exception:
                    pointCount = 0

                for pointIndex in range(pointCount):
                    pointId = ""
                    try:
                        pointId = str(node.GetNthControlPointID(pointIndex))
                    except Exception:
                        pass
                    key = "{}|{}".format(
                        node.GetID(),
                        pointId or "index:{}".format(pointIndex),
                    )
                    position = self._pointWorldPosition(node, pointIndex)
                    entry = {
                        "key": key,
                        "node": node,
                        "index": pointIndex,
                        "pointId": pointId,
                        "position": position,
                    }
                    entries.append(entry)
                    self.pointCombo.addItem(
                        self._pointDisplayLabel(node, pointIndex, position), key
                    )

            self._availablePoints = entries
            self.pointCombo.enabled = bool(entries)
            if not entries:
                self.pointCombo.setItemText(0, _("No markup points available"))

            if self.controlPointsList is not None:
                self.controlPointsList.blockSignals(True)
                self.controlPointsList.clear()
                availableKeys = set()
                for entry in entries:
                    if entry["position"] is None:
                        continue
                    key = entry["key"]
                    availableKeys.add(key)
                    item = qt.QListWidgetItem(
                        self._pointDisplayLabel(entry["node"], entry["index"], entry["position"])
                    )
                    item.setData(qt.Qt.UserRole, key)
                    item.setCheckState(
                        qt.Qt.Checked if key in self._checkedControlPointKeys else qt.Qt.Unchecked
                    )
                    self.controlPointsList.addItem(item)
                self._checkedControlPointKeys.intersection_update(availableKeys)
                self.controlPointsList.blockSignals(False)
                self.controlPointsList.enabled = bool(entries)

            if self._selectedPointKey:
                targetIndex = self.pointCombo.findData(self._selectedPointKey)
                if targetIndex < 0:
                    targetIndex = 0
                    selectionLost = True
                    self._selectedPointKey = ""
                    self._linkedPointPosition = None
                    if self.pointInfoLabel is not None:
                        self.pointInfoLabel.setText(
                            _("The previously selected point is no longer "
                              "available. The center fields keep their last value.")
                        )
            self.pointCombo.setCurrentIndex(targetIndex)
        finally:
            self.pointCombo.blockSignals(False)

        self._observeMarkupNodes(nodes)

        if targetIndex > 0:
            self._setCenterFromSelectedPoint()
        elif not selectionLost:
            self._updatePointInfoLabel()
        self._updateShapeControlState()

    def _onRefreshPoints(self):
        self._refreshPointList()

    def _selectedPointEntry(self):
        if not self._selectedPointKey:
            return None
        for entry in self._availablePoints:
            if entry["key"] == self._selectedPointKey:
                return entry
        return None

    def _findPointIndexById(self, entry):
        node = entry["node"]
        pointId = entry.get("pointId", "")
        if pointId:
            try:
                for pointIndex in range(int(node.GetNumberOfControlPoints())):
                    if str(node.GetNthControlPointID(pointIndex)) == pointId:
                        return pointIndex
            except Exception:
                pass
        try:
            pointIndex = int(entry["index"])
            if 0 <= pointIndex < int(node.GetNumberOfControlPoints()):
                return pointIndex
        except Exception:
            pass
        return None

    def _setCenterFromSelectedPoint(self):
        entry = self._selectedPointEntry()
        if entry is None:
            return False

        pointIndex = self._findPointIndexById(entry)
        if pointIndex is None:
            return False
        entry["index"] = pointIndex

        position = self._pointWorldPosition(entry["node"], pointIndex)
        if position is None:
            return False

        # Keep the exact world-RAS position. The spin boxes round to two
        # decimals for display, but preview/apply use this value directly.
        self._linkedPointPosition = position
        entry["position"] = position

        blocked = [self.centerXSpin, self.centerYSpin, self.centerZSpin]
        for spin in blocked:
            spin.blockSignals(True)
        self.centerXSpin.value = position[0]
        self.centerYSpin.value = position[1]
        self.centerZSpin.value = position[2]
        for spin in blocked:
            spin.blockSignals(False)

        self._updatePointInfoLabel()
        self._schedulePreviewUpdate()
        return True

    def _syncCenterFromSelectedPoint(self, callerNode=None):
        if not self._selectedPointKey:
            return
        entry = self._selectedPointEntry()
        if entry is None:
            self._refreshPointList()
            return
        if callerNode is not None:
            try:
                if entry["node"].GetID() != callerNode.GetID():
                    return
            except Exception:
                pass
        if not self._setCenterFromSelectedPoint():
            self._refreshPointList()

    def _updatePointInfoLabel(self):
        if self.pointInfoLabel is None:
            return
        entry = self._selectedPointEntry()
        if entry is None:
            self.pointInfoLabel.setText(
                _("No point selected. The center fields are used.")
            )
            return

        position = self._linkedPointPosition or entry.get("position")
        label = self._pointDisplayLabel(
            entry["node"], entry["index"], position=None
        )
        if position is None:
            self.pointInfoLabel.setText(
                _("Selected point: {} | position unavailable.").format(label)
            )
            return
        self.pointInfoLabel.setText(
            _("Selected point: {} | world RAS ({:.3f}, {:.3f}, {:.3f}) mm")
            .format(label, position[0], position[1], position[2])
        )

    def _detachSelectedPoint(self):
        self._selectedPointKey = ""
        self._linkedPointPosition = None
        if self.pointCombo is not None:
            self.pointCombo.blockSignals(True)
            try:
                self.pointCombo.setCurrentIndex(0)
            finally:
                self.pointCombo.blockSignals(False)
        self._updatePointInfoLabel()

    def _onPointSelected(self, index):
        if index <= 0:
            self._selectedPointKey = ""
            self._linkedPointPosition = None
            self._updatePointInfoLabel()
            return

        key = self.pointCombo.itemData(index)
        entry = None
        for candidate in self._availablePoints:
            if candidate["key"] == key:
                entry = candidate
                break
        if entry is None:
            self._detachSelectedPoint()
            return

        self._selectedPointKey = key
        if not self._setCenterFromSelectedPoint():
            self._selectedPointKey = ""
            self._linkedPointPosition = None
            self._updatePointInfoLabel()
            slicer.util.warningDisplay(
                _("Could not read the selected markup point. Place a valid "
                  "point and refresh the list.")
            )
            self._detachSelectedPoint()

    # ------------------------------------------------------------------
    # Inputs
    # ------------------------------------------------------------------
    def _autoSelectSingleVolume(self):
        if self.volumeSelector.currentNode() is not None:
            return
        if slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLScalarVolumeNode") == 1:
            node = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
            if node:
                self.volumeSelector.setCurrentNode(node)

    def _onVolumeChanged(self, node=None):
        self._updateVolumeInfo()
        self._clearPreview()
        volumeNode = self.volumeSelector.currentNode()

        if self._selectedPointKey:
            # The point is in world RAS, so changing the reference volume does
            # not change its position. Keep the explicit point selection.
            if not self._setCenterFromSelectedPoint():
                self._detachSelectedPoint()
                if volumeNode is not None:
                    self._setCenterFromVolume(volumeNode)
        elif volumeNode is not None:
            self._setCenterFromVolume(volumeNode)

        self.updateState()

    def _updateVolumeInfo(self):
        volumeNode = self.volumeSelector.currentNode() if self.volumeSelector else None
        if volumeNode is None or volumeNode.GetImageData() is None:
            self.volumeInfoLabel.setText(_("No volume selected."))
            return
        imageData = volumeNode.GetImageData()
        dimensions = imageData.GetDimensions()
        spacing = volumeNode.GetSpacing()
        minimum, maximum = imageData.GetScalarRange()
        self.volumeInfoLabel.setText(
            _("{} x {} x {} voxels | spacing {:.3f} x {:.3f} x {:.3f} mm | intensity {:.1f} to {:.1f}")
            .format(
                dimensions[0], dimensions[1], dimensions[2],
                spacing[0], spacing[1], spacing[2],
                minimum, maximum,
            )
        )

    def _volumeCenterRAS(self, volumeNode):
        imageData = volumeNode.GetImageData()
        if imageData is None:
            return [0.0, 0.0, 0.0]

        dimensions = imageData.GetDimensions()
        ijkToRAS = vtk.vtkMatrix4x4()
        volumeNode.GetIJKToRASMatrix(ijkToRAS)

        centerIJK = [
            (max(0, dimensions[0]) - 1) / 2.0,
            (max(0, dimensions[1]) - 1) / 2.0,
            (max(0, dimensions[2]) - 1) / 2.0,
            1.0,
        ]
        centerRAS = [0.0, 0.0, 0.0, 0.0]
        ijkToRAS.MultiplyPoint(centerIJK, centerRAS)
        return [centerRAS[0], centerRAS[1], centerRAS[2]]

    def _setCenterFromVolume(self, volumeNode):
        center = self._volumeCenterRAS(volumeNode)
        blocked = [self.centerXSpin, self.centerYSpin, self.centerZSpin]
        for spin in blocked:
            spin.blockSignals(True)
        self.centerXSpin.value = center[0]
        self.centerYSpin.value = center[1]
        self.centerZSpin.value = center[2]
        for spin in blocked:
            spin.blockSignals(False)

    def _onCenterOnVolume(self):
        volumeNode = self.volumeSelector.currentNode()
        if volumeNode is None:
            slicer.util.warningDisplay(_("Select a reference volume first."))
            return
        self._detachSelectedPoint()
        self._setCenterFromVolume(volumeNode)
        self._schedulePreviewUpdate()

    def _onUseCrosshair(self):
        crosshairNode = None
        try:
            crosshairNode = slicer.mrmlScene.GetSingletonNode(
                "Crosshair", "vtkMRMLCrosshairNode"
            )
        except Exception:
            crosshairNode = None
        if crosshairNode is None:
            slicer.util.warningDisplay(_("Crosshair node is not available."))
            return

        position = None
        for methodName in ("GetCrosshairRAS", "GetCrosshairPositionRAS"):
            method = getattr(crosshairNode, methodName, None)
            if method is None:
                continue
            try:
                candidate = method()
                if candidate is not None and len(candidate) >= 3:
                    position = [float(candidate[0]), float(candidate[1]), float(candidate[2])]
                    break
            except Exception:
                continue

        if position is None:
            slicer.util.warningDisplay(_("Could not read the crosshair position."))
            return

        self._detachSelectedPoint()
        blocked = [self.centerXSpin, self.centerYSpin, self.centerZSpin]
        for spin in blocked:
            spin.blockSignals(True)
        self.centerXSpin.value = position[0]
        self.centerYSpin.value = position[1]
        self.centerZSpin.value = position[2]
        for spin in blocked:
            spin.blockSignals(False)
        self._schedulePreviewUpdate()

    def _sphereParameters(self):
        if self._selectedPointKey and self._linkedPointPosition is not None:
            center = list(self._linkedPointPosition)
        else:
            center = [
                float(self.centerXSpin.value),
                float(self.centerYSpin.value),
                float(self.centerZSpin.value),
            ]
        controlPoints = []
        for entry in self._availablePoints:
            if entry["key"] not in self._checkedControlPointKeys:
                continue
            pointIndex = self._findPointIndexById(entry)
            if pointIndex is None:
                continue
            position = self._pointWorldPosition(entry["node"], pointIndex)
            if position is not None:
                controlPoints.append(position)
        return {
            "centerRAS": center,
            "radiusMM": float(self.radiusSpin.value),
            "shapePattern": str(self.shapePatternCombo.currentData),
            "distortion": float(self.distortionSpin.value) / 100.0,
            "frequency": int(self.frequencySpin.value),
            "controlPointsRAS": controlPoints,
            "seed": int(self.seedSpin.value),
        }

    def _onCenterParameterChanged(self, *args):
        # Editing a center field means the sphere is no longer tied to the
        # markup point. This prevents a later point movement from silently
        # overwriting the manually entered position.
        if self._selectedPointKey:
            self._detachSelectedPoint()
        self._onSphereParameterChanged()

    def _onSphereParameterChanged(self, *args):
        if self.previewSegmentationNode is not None:
            self.previewTimer.start()
        self.updateState()

    def _updateShapeControlState(self):
        if self.shapePatternCombo is None:
            return
        pattern = str(self.shapePatternCombo.currentData)
        nonUniform = pattern != "uniform"
        self.distortionSpin.enabled = nonUniform
        self.frequencySpin.enabled = nonUniform
        self.seedSpin.enabled = nonUniform
        if self.controlPointsList is not None:
            self.controlPointsList.enabled = (
                pattern == "multi_point" and self.controlPointsList.count > 0
            )

    def _onShapePatternChanged(self, *args):
        self._updateShapeControlState()
        self._onSphereParameterChanged()

    def _onControlPointCheckChanged(self, item):
        key = item.data(qt.Qt.UserRole)
        if not key:
            return
        if item.checkState() == qt.Qt.Checked:
            self._checkedControlPointKeys.add(str(key))
        else:
            self._checkedControlPointKeys.discard(str(key))
        self._onSphereParameterChanged()

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _schedulePreviewUpdate(self):
        if self.previewSegmentationNode is not None:
            self.previewTimer.start()

    def _onPreview(self):
        try:
            with slicer.util.tryWithErrorDisplay(
                _("Failed to create the sphere preview."), waitCursor=True
            ):
                volumeNode = self.volumeSelector.currentNode()
                if volumeNode is None:
                    raise ValueError("Select a reference volume first.")
                self._ensurePreviewSegmentation(volumeNode)
                self._updatePreviewSegment()
        except Exception:
            traceback.print_exc()

    def _ensurePreviewSegmentation(self, volumeNode):
        if self.previewSegmentationNode is not None:
            return

        previewNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode", "_SphereSegmentation_Preview"
        )
        previewNode.SetName("SphereSegmentation_preview")
        try:
            # The preview node is temporary; keep it out of node selectors and
            # the Data module so it cannot be mistaken for real output.
            previewNode.SetHideFromEditors(True)
        except Exception:
            pass
        try:
            previewNode.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
        except Exception:
            pass

        previewNode.CreateDefaultDisplayNodes()
        segmentId = previewNode.GetSegmentation().AddEmptySegment("", "SpherePreview")
        segment = previewNode.GetSegmentation().GetSegment(segmentId)
        if segment is not None:
            try:
                segment.SetColor(1.0, 0.75, 0.10)
            except Exception:
                pass

        # Normally a no-op (new segmentations are binary labelmap based), but
        # guarantees that updateSegmentBinaryLabelmapFromArray can work.
        self.logic._ensureBinaryLabelmapRepresentation(previewNode)

        self.previewSegmentationNode = previewNode
        self.previewSegmentId = segmentId
        self.logic.configureSegmentationDisplay(previewNode, segmentId)

    def _updatePreviewSegment(self):
        if self.previewSegmentationNode is None:
            return
        volumeNode = self.volumeSelector.currentNode()
        if volumeNode is None:
            self._clearPreview()
            return

        parameters = self._sphereParameters()
        mask = self.logic.createPatternSphereMask(
            volumeNode,
            parameters["centerRAS"],
            parameters["radiusMM"],
            shapePattern=parameters["shapePattern"],
            distortion=parameters["distortion"],
            frequency=parameters["frequency"],
            controlPointsRAS=parameters["controlPointsRAS"],
            seed=parameters["seed"],
        )
        count = int(np.count_nonzero(mask))
        if count == 0:
            # Clear the previous surface so a stale sphere is not left visible.
            try:
                self.logic.updateSegmentFromMask(
                    self.previewSegmentationNode,
                    self.previewSegmentId,
                    mask,
                    volumeNode,
                )
                self.logic.createClosedSurfaceRepresentation(self.previewSegmentationNode)
            except Exception:
                pass
            self.previewInfoLabel.setText(
                _("Preview sphere does not intersect the volume. Adjust center or radius.")
            )
            self.updateState()
            return

        self.logic.updateSegmentFromMask(
            self.previewSegmentationNode,
            self.previewSegmentId,
            mask,
            volumeNode,
        )
        self.logic.createClosedSurfaceRepresentation(self.previewSegmentationNode)
        self.logic.configureSegmentationDisplay(
            self.previewSegmentationNode, self.previewSegmentId
        )

        self.previewInfoLabel.setText(
            _("Preview active: {} shape contains {} voxels. "
              "The segmentation is visible in 2D and 3D views.").format(
                  self.shapePatternCombo.currentText, count
              )
        )
        self.updateState()

    def _updatePreviewFromParameters(self):
        if self.previewSegmentationNode is None:
            return
        try:
            self._updatePreviewSegment()
        except Exception:
            traceback.print_exc()
            self.previewInfoLabel.setText(
                _("Could not update the preview. See the Python console for details.")
            )

    def _clearPreview(self):
        if self.previewSegmentationNode is not None:
            try:
                slicer.mrmlScene.RemoveNode(self.previewSegmentationNode)
            except Exception:
                pass
        self.previewSegmentationNode = None
        self.previewSegmentId = None
        if hasattr(self, "previewInfoLabel") and self.previewInfoLabel:
            self.previewInfoLabel.setText(_("No preview active."))
        if hasattr(self, "previewButton") and self.previewButton:
            self.updateState()

    def _onClearPreview(self):
        self._clearPreview()

    # ------------------------------------------------------------------
    # Apply / undo
    # ------------------------------------------------------------------
    def _onApply(self):
        volumeNode = self.volumeSelector.currentNode()
        if volumeNode is None:
            slicer.util.warningDisplay(_("Select a reference volume first."))
            return
        if self.previewSegmentationNode is None:
            slicer.util.warningDisplay(
                _("Preview the sphere first so you can verify its position in 3D.")
            )
            return

        # Flush any pending preview update, so the applied sphere is exactly
        # the one that was displayed for verification.
        self.previewTimer.stop()
        try:
            self._updatePreviewSegment()
        except Exception:
            traceback.print_exc()
            slicer.util.warningDisplay(
                _("The preview could not be updated. See the Python console for details.")
            )
            return

        parameters = self._sphereParameters()
        segmentName = self.segmentNameEdit.text.strip() or "Sphere"
        targetSegmentationNode = self.outputSegmentationSelector.currentNode()
        if targetSegmentationNode is self.previewSegmentationNode:
            # The preview is temporary and is removed after apply. Never write
            # the permanent segment into it.
            targetSegmentationNode = None

        try:
            with slicer.util.tryWithErrorDisplay(
                _("Failed to apply the sphere."), waitCursor=True
            ):
                segmentationNode, segmentId, count = self.logic.applySphere(
                    volumeNode,
                    parameters["centerRAS"],
                    parameters["radiusMM"],
                    targetSegmentationNode=targetSegmentationNode,
                    segmentName=segmentName,
                    shapePattern=parameters["shapePattern"],
                    distortion=parameters["distortion"],
                    frequency=parameters["frequency"],
                    controlPointsRAS=parameters["controlPointsRAS"],
                    seed=parameters["seed"],
                )

                actualName = segmentName
                segment = segmentationNode.GetSegmentation().GetSegment(segmentId)
                if segment is not None and segment.GetName():
                    actualName = segment.GetName()

                self.outputSegmentationSelector.setCurrentNode(segmentationNode)
                self._clearPreview()
                self.updateState()
                self.statusLabel.setText(
                    _("Sphere '{}' applied to '{}' ({} voxels).").format(
                        actualName,
                        segmentationNode.GetName() or segmentationNode.GetID(),
                        count,
                    )
                )
                slicer.util.infoDisplay(
                    _("Sphere added to the segmentation ({} voxels).\n\n"
                      "Use 'Undo last applied sphere' to remove it.").format(count)
                )
        except Exception:
            traceback.print_exc()

    def _onUndo(self):
        entry = self.logic.undoLast()
        if entry is None:
            slicer.util.warningDisplay(_("There is no applied sphere to undo."))
            return
        self.statusLabel.setText(
            _("Removed segment '{}' ({} voxels).").format(
                entry.get("segmentName", "Sphere"), entry.get("voxelCount", 0)
            )
        )
        self.updateState()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def updateState(self):
        if not hasattr(self, "previewButton") or self.previewButton is None:
            return

        volumeNode = self.volumeSelector.currentNode() if self.volumeSelector else None
        hasVolume = volumeNode is not None

        hasPreview = self.previewSegmentationNode is not None
        self.previewButton.enabled = hasVolume
        self.applyButton.enabled = hasVolume and hasPreview
        self.undoButton.enabled = self.logic.canUndo()
        self.clearPreviewButton.enabled = self.previewSegmentationNode is not None

        if not hasVolume:
            self.statusLabel.setText(_("Select a reference volume."))
        elif self.previewSegmentationNode is not None:
            self.statusLabel.setText(
                _("Preview active. Adjust the parameters or apply the sphere to a segmentation.")
            )
        else:
            self.statusLabel.setText(
                _("Ready. Preview the sphere in 3D, then apply it to a segmentation.")
            )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self):
        try:
            self._clearPreview()
        except Exception:
            pass
        if self.previewTimer is not None:
            try:
                self.previewTimer.stop()
            except Exception:
                pass
        if self.pointRefreshTimer is not None:
            try:
                self.pointRefreshTimer.stop()
            except Exception:
                pass

        self._clearMarkupObservers()
        for tag in self._sceneObserverTags:
            try:
                slicer.mrmlScene.RemoveObserver(tag)
            except Exception:
                pass
        self._sceneObserverTags = []
        self._sceneObserverCallbacks = []

        try:
            self.removeObservers()
        except Exception:
            pass


# =============================================================================
# Module
# =============================================================================

class SphereSegmentation(ScriptedLoadableModule):

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Sphere Segmentation")
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Pedro Afonso (Developer)"]
        self.parent.helpText = _(
            """Create a spherical or deformed synthetic segment and add it to a segmentation.
<br><br>
<b>Workflow:</b>
<ol>
<li>Select a reference volume that defines the image geometry.</li>
<li>Optionally choose a markup point under <b>Position from point</b> to set
    the sphere center.</li>
<li>Set the radius and choose a uniform, smooth, dented, lobulated, or
    multi-point lesion pattern. For a multi-point lesion, check one or more
    additional markup points to define the path through the shape.</li>
<li>The center can also be entered manually or set with <b>Center on volume</b>
    or <b>Use crosshair</b>.</li>
<li>Click <b>Preview sphere</b> to inspect the 3D surface and 2D outline, then
    click <b>Apply sphere to segmentation</b> to add it as a segment.</li>
<li>Use <b>Undo</b> to remove the last applied shape.</li>
</ol>
These shapes are synthetic geometry for educational use, not diagnostic tools.
"""
        )
        self.parent.acknowledgementText = _(
            "Developed for synthetic case generation in medical imaging education."
        )


# =============================================================================
# Tests
# =============================================================================

class SphereSegmentationTest(ScriptedLoadableModuleTest):

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_createSphereMask()
        self.test_deformedAndMultiPointMasks()
        self.test_applyAndUndo()

    def _makeVolume(self, shape=(20, 20, 20), spacing=(1.0, 1.0, 1.0)):
        volumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        array = np.zeros(shape, dtype=np.int16)
        slicer.util.updateVolumeFromArray(volumeNode, array)
        volumeNode.SetSpacing(*spacing)
        identity = vtk.vtkMatrix4x4()
        volumeNode.SetIJKToRASMatrix(identity)
        return volumeNode

    def test_createSphereMask(self):
        self.delayDisplay("Testing sphere mask generation")
        volumeNode = self._makeVolume()
        logic = SphereSegmentationLogic()

        mask = logic.createSphereMask(volumeNode, [10.0, 10.0, 10.0], 5.0)
        count = int(np.count_nonzero(mask))
        self.assertEqual(mask.shape, (20, 20, 20))
        self.assertGreater(count, 450)
        self.assertLess(count, 620)

        # A center outside the volume with a small radius yields no voxels.
        emptyMask = logic.createSphereMask(volumeNode, [1000.0, 1000.0, 1000.0], 1.0)
        self.assertEqual(int(np.count_nonzero(emptyMask)), 0)
        self.delayDisplay("Sphere mask test passed")

    def test_deformedAndMultiPointMasks(self):
        self.delayDisplay("Testing deformed and multi-point sphere masks")
        volumeNode = self._makeVolume(shape=(24, 24, 32))
        logic = SphereSegmentationLogic()
        center = [12.0, 12.0, 16.0]
        uniform = logic.createPatternSphereMask(volumeNode, center, 6.0)
        smooth = logic.createPatternSphereMask(
            volumeNode, center, 6.0, shapePattern="smooth",
            distortion=0.4, frequency=3, seed=2,
        )
        dented = logic.createPatternSphereMask(
            volumeNode, center, 6.0, shapePattern="dented",
            distortion=0.5, frequency=4, seed=3,
        )
        lobulated = logic.createPatternSphereMask(
            volumeNode, center, 6.0, shapePattern="lobulated",
            distortion=0.4, frequency=3, seed=4,
        )
        self.assertGreater(int(np.count_nonzero(smooth)), 0)
        self.assertGreater(int(np.count_nonzero(dented)), 0)
        self.assertGreater(int(np.count_nonzero(lobulated)), 0)
        self.assertFalse(np.array_equal(uniform, smooth))

        multiPoint = logic.createPatternSphereMask(
            volumeNode,
            [5.0, 12.0, 12.0],
            2.0,
            shapePattern="multi_point",
            distortion=0.0,
            controlPointsRAS=[[26.0, 12.0, 12.0]],
        )
        self.assertTrue(multiPoint[12, 12, 5])
        self.assertTrue(multiPoint[12, 12, 15])
        self.assertTrue(multiPoint[12, 12, 26])
        self.delayDisplay("Deformed and multi-point mask tests passed")

    def test_applyAndUndo(self):
        self.delayDisplay("Testing sphere apply and undo")
        volumeNode = self._makeVolume()
        logic = SphereSegmentationLogic()

        segmentationNode, segmentId, count = logic.applySphere(
            volumeNode,
            [10.0, 10.0, 10.0],
            5.0,
            targetSegmentationNode=None,
            segmentName="TestSphere",
        )

        self.assertGreater(count, 0)
        self.assertIsNotNone(segmentationNode.GetSegmentation().GetSegment(segmentId))
        self.assertTrue(logic.canUndo())

        displayNode = segmentationNode.GetDisplayNode()
        self.assertIsNotNone(displayNode)
        try:
            self.assertTrue(displayNode.GetVisibility3D())
        except Exception:
            pass

        entry = logic.undoLast()
        self.assertIsNotNone(entry)
        self.assertFalse(logic.canUndo())
        self.assertIsNone(
            slicer.mrmlScene.GetNodeByID(segmentationNode.GetID())
        )
        self.delayDisplay("Sphere apply/undo test passed")