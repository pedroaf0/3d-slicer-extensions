"""SegmentationValidator - validates nnU-Net training segmentations in 3D Slicer.

The module lets the user point to a training dataset folder (nnU-Net style)
that contains:

    <dataset>/imagesTr/<case>_0000.nii.gz   (input images)
    <dataset>/labelsTr/<case>.nii.gz         (ground truth labels)

It lists the matching image/label pairs and provides Previous / Next buttons
to step through the cases. For each case the image volume is loaded into the
scene and the label file is imported as a segmentation segment, so the ground
truth can be visually validated on top of the image.
"""

import logging
import os
import re
import traceback

import ctk
import qt
import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

SUPPORTED_IMAGE_EXTENSIONS = (
    ".nii.gz", ".nii", ".nrrd", ".nhdr", ".mha", ".mhd", ".nia", ".hdr", ".img",
)

_MODALITY_SUFFIX_RE = re.compile(r"(?P<name>.+)_(?P<modality>\d{3,4})$")


def isSupportedImageFile(fileName):
    """Return True if the given file name has a supported volume extension."""
    lower = fileName.lower()
    return any(lower.endswith(extension) for extension in SUPPORTED_IMAGE_EXTENSIONS)


def stripExtension(fileName):
    """Remove the extension of a supported image file (handles .nii.gz)."""
    lower = fileName.lower()
    for extension in SUPPORTED_IMAGE_EXTENSIONS:
        if lower.endswith(extension):
            return fileName[: len(fileName) - len(extension)]
    return os.path.splitext(fileName)[0]


def caseNameFromImageBase(imageBaseName):
    """nnU-Net images use a modality suffix, e.g. 'case_0000'; return 'case'."""
    match = _MODALITY_SUFFIX_RE.match(imageBaseName)
    if match:
        return match.group("name")
    return imageBaseName


def discoverTrainingCases(datasetFolder):
    """Return the list of cases and the list of skipped names.

    A case is valid when it has a matching image (in imagesTr) and label
    (in labelsTr). Result items are dicts with the keys: case, imageFile,
    labelFile, imagePath and labelPath.
    """
    if not os.path.isdir(datasetFolder):
        raise ValueError(_("A pasta do dataset nao existe: ") + str(datasetFolder))

    imagesDir = os.path.join(datasetFolder, "imagesTr")
    labelsDir = os.path.join(datasetFolder, "labelsTr")
    if not os.path.isdir(imagesDir):
        raise ValueError(_("Pasta nao encontrada: ") + imagesDir)
    if not os.path.isdir(labelsDir):
        raise ValueError(_("Pasta nao encontrada: ") + labelsDir)

    # Index the label files by their case name (e.g. "border" -> border.nii.gz)
    labelByCase = {}
    for name in sorted(os.listdir(labelsDir)):
        if not isSupportedImageFile(name):
            continue
        case = stripExtension(name)
        labelByCase.setdefault(case, os.path.join(labelsDir, name))

    # Index the image files by their case name (prefer the _0000 modality)
    imageByCase = {}
    for name in sorted(os.listdir(imagesDir)):
        if not isSupportedImageFile(name):
            continue
        base = stripExtension(name)
        case = caseNameFromImageBase(base) or base
        imageByCase.setdefault(case, os.path.join(imagesDir, name))

    cases = []
    skipped = []
    for case in sorted(set(list(imageByCase.keys()) + list(labelByCase.keys()))):
        imagePath = imageByCase.get(case)
        labelPath = labelByCase.get(case)
        if imagePath and labelPath:
            cases.append({
                "case": case,
                "imageFile": os.path.basename(imagePath),
                "labelFile": os.path.basename(labelPath),
                "imagePath": imagePath,
                "labelPath": labelPath,
            })
        else:
            skipped.append(case)
    return cases, skipped


class SegmentationValidator(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Validador de Segmentacoes (nnU-Net)"
        self.parent.categories = ["Segmentation", "Deep Learning"]
        self.parent.dependencies = []
        self.parent.contributors = ["Pedro (Developer)"]
        self.parent.helpText = _(
            """Valida as segmentacoes de treinamento de um dataset no formato nnU-Net.

Informe a pasta do dataset (que contem <code>imagesTr</code> e <code>labelsTr</code>),
carregue a lista de casos e navegue com os botoes <b>Anterior</b> / <b>Proximo</b>.

Para cada caso o modulo carrega a imagem na cena e importa o arquivo de label
como <b>segmento</b>, permitindo conferir visualmente se a segmentacao esta
correta sobre a imagem.
"""
        )
        self.parent.acknowledgementText = _("Developed for canalRadicular segmentation training.")


class SegmentationValidatorWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._paramNode = None
        self._cases = []
        self._skipped = []
        self._caseIndex = -1
        self._volumeNode = None
        self._segmentationNode = None

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        try:
            self._buildUi()
        except Exception:
            traceback.print_exc()
            slicer.util.errorDisplay(
                _("Nao foi possivel criar a interface do modulo.\n") + traceback.format_exc()
            )

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _buildUi(self):
        self.logic = SegmentationValidatorLogic()

        # Dataset selection
        paramCollapsibleButton = ctk.ctkCollapsibleButton()
        paramCollapsibleButton.text = _("Parametros de validacao")
        paramCollapsibleButton.collapsed = False
        self.layout.addWidget(paramCollapsibleButton)

        formLayout = qt.QFormLayout(paramCollapsibleButton)

        self.datasetFolderSelector = ctk.ctkPathLineEdit()
        self.datasetFolderSelector.filters = ctk.ctkPathLineEdit.Dirs
        self.datasetFolderSelector.toolTip = _(
            "Pasta do dataset de treinamento (nnU-Net). Deve conter as subpastas "
            "imagesTr (imagens) e labelsTr (labels), por exemplo "
            "Dataset001_canalRadicular."
        )
        formLayout.addRow(_("Dataset:"), self.datasetFolderSelector)

        self.loadListButton = qt.QPushButton(_("Carregar lista de casos"))
        self.loadListButton.toolTip = _(
            "Escaneia a pasta imagesTr/labelsTr e monta a lista de casos validos."
        )
        formLayout.addRow("", self.loadListButton)

        self.datasetInfoLabel = qt.QLabel()
        self.datasetInfoLabel.setWordWrap(True)
        formLayout.addRow("", self.datasetInfoLabel)

        # Navigation
        navCollapsibleButton = ctk.ctkCollapsibleButton()
        navCollapsibleButton.text = _("Navegacao")
        navCollapsibleButton.collapsed = False
        self.layout.addWidget(navCollapsibleButton)

        navFormLayout = qt.QFormLayout(navCollapsibleButton)

        self.caseComboBox = qt.QComboBox()
        self.caseComboBox.setSizeAdjustPolicy(qt.QComboBox.AdjustToContents)
        self.caseComboBox.toolTip = _("Caso atual (imagem + label). A selecao carrega o caso.")
        navFormLayout.addRow(_("Caso:"), self.caseComboBox)

        buttonsRow = qt.QHBoxLayout()
        self.previousButton = qt.QPushButton(_("Anterior"))
        self.previousButton.toolTip = _("Vai para o caso anterior.")
        self.nextButton = qt.QPushButton(_("Proximo"))
        self.nextButton.toolTip = _("Vai para o proximo caso.")
        self.casePositionLabel = qt.QLabel(_("- / -"))
        self.casePositionLabel.setAlignment(qt.Qt.AlignCenter)
        buttonsRow.addWidget(self.previousButton)
        buttonsRow.addWidget(self.casePositionLabel, 1)
        buttonsRow.addWidget(self.nextButton)
        navFormLayout.addRow("", buttonsRow)

        self.segmentComboBox = qt.QComboBox()
        self.segmentComboBox.toolTip = _(
            "Segmentos presentes no label do caso atual (importados do arquivo de label)."
        )
        navFormLayout.addRow(_("Segmentos:"), self.segmentComboBox)

        sliceRow = qt.QHBoxLayout()
        self.previousSliceButton = qt.QPushButton(_("Fatia anterior"))
        self.nextSliceButton = qt.QPushButton(_("Fatia proxima"))
        self.slicePositionLabel = qt.QLabel("--")
        self.slicePositionLabel.setAlignment(qt.Qt.AlignCenter)
        sliceRow.addWidget(self.previousSliceButton)
        sliceRow.addWidget(self.slicePositionLabel, 1)
        sliceRow.addWidget(self.nextSliceButton)
        navFormLayout.addRow(_("Fatias:"), sliceRow)

        self.statusLabel = qt.QLabel(_("Pronto."))
        self.statusLabel.setWordWrap(True)
        self.layout.addWidget(self.statusLabel)

        self.layout.addStretch(1)

        # Connections
        self.loadListButton.connect("clicked()", self.onLoadListClicked)
        self.previousButton.connect("clicked()", self.onPreviousCase)
        self.nextButton.connect("clicked()", self.onNextCase)
        self.caseComboBox.connect("currentIndexChanged(int)", self.onCaseSelected)
        self.segmentComboBox.connect("currentIndexChanged(int)", self.onSegmentSelected)
        self.previousSliceButton.connect("clicked()", lambda: self.stepSlice(-1))
        self.nextSliceButton.connect("clicked()", lambda: self.stepSlice(1))

        self.initializeParameterNode()
        self.updateNavigationState()

    # ------------------------------------------------------------------
    # Parameter node
    # ------------------------------------------------------------------
    def initializeParameterNode(self):
        node = self.logic.getParameterNode()
        if node is not self._paramNode:
            self._paramNode = node

        folder = node.GetParameter("DatasetFolder") or ""
        settings = qt.QSettings()
        folder = settings.value("SegmentationValidator/DatasetFolder", folder)
        if folder and os.path.isdir(folder):
            self.datasetFolderSelector.currentPath = folder

    def _saveDatasetFolder(self, folder):
        node = self.logic.getParameterNode()
        node.SetParameter("DatasetFolder", folder)
        qt.QSettings().setValue("SegmentationValidator/DatasetFolder", folder)

    # ------------------------------------------------------------------
    # List handling
    # ------------------------------------------------------------------
    def onLoadListClicked(self, arg=None):
        folder = str(self.datasetFolderSelector.currentPath).strip()
        with slicer.util.tryWithErrorDisplay(_("Falha ao carregar a lista de casos."), waitCursor=True):
            self.reloadCaseList(folder)

    def reloadCaseList(self, folder):
        if not os.path.isdir(folder):
            raise ValueError(_("A pasta do dataset informada nao existe: ") + folder)

        cases, skipped = self.logic.discoverCases(folder)
        self._cases = cases
        self._skipped = skipped
        self._saveDatasetFolder(folder)

        self.caseComboBox.blockSignals(True)
        try:
            self.caseComboBox.clear()
            for case in cases:
                self.caseComboBox.addItem(case["case"])
        finally:
            self.caseComboBox.blockSignals(False)

        info = _("Encontrados {} casos validos (imagem + label).").format(len(cases))
        if skipped:
            names = ", ".join(skipped[:10])
            info = info + "\n" + _("Sem par correspondente (ignorados): {}").format(names)
        self.datasetInfoLabel.setText(info)

        self._removeLoadedNodes()
        self._caseIndex = -1
        if cases:
            self._selectCase(0)
        else:
            self.statusLabel.setText(_("Nenhum caso com imagem E label encontrado."))
        self.updateNavigationState()

    # ------------------------------------------------------------------
    # Case navigation
    # ------------------------------------------------------------------
    def onCaseSelected(self, index):
        if index < 0 or index == self._caseIndex:
            return
        self._selectCase(index)

    def onPreviousCase(self):
        if self._caseIndex > 0:
            self._selectCase(self._caseIndex - 1)

    def onNextCase(self):
        if self._caseIndex < len(self._cases) - 1:
            self._selectCase(self._caseIndex + 1)

    def _selectCase(self, index):
        if not (0 <= index < len(self._cases)):
            return
        self._caseIndex = index
        with slicer.util.tryWithErrorDisplay(_("Falha ao carregar o caso."), waitCursor=True):
            self._loadCase(index)
        self.caseComboBox.blockSignals(True)
        try:
            self.caseComboBox.setCurrentIndex(index)
        finally:
            self.caseComboBox.blockSignals(False)
        self.updateNavigationState()

    def updateNavigationState(self):
        count = len(self._cases)
        enabled = count > 0
        self.caseComboBox.enabled = enabled
        self.previousButton.enabled = enabled and self._caseIndex > 0
        self.nextButton.enabled = enabled and self._caseIndex < count - 1
        position = "{} / {}".format(self._caseIndex + 1 if self._caseIndex >= 0 else "-", count)
        self.casePositionLabel.text = position

    # ------------------------------------------------------------------
    # Case loading
    # ------------------------------------------------------------------
    def _loadCase(self, index):
        self._removeLoadedNodes()
        case = self._cases[index]

        volumeNode, segmentationNode = self.logic.loadTrainingCase(case, index)

        self._volumeNode = volumeNode
        self._segmentationNode = segmentationNode

        if volumeNode is not None:
            slicer.util.setSliceViewerLayers(background=volumeNode, fit=True)
        self._ensureSegmentationDisplay(segmentationNode)
        self._repopulateSegmentComboBox()
        self._centerSlice()
        self._updateSliceLabel()

        self.statusLabel.setStyleSheet("")
        self.statusLabel.setText(_("Exibindo: {} (label: {})").format(case["imageFile"], case["labelFile"]))

    def _removeLoadedNodes(self):
        for node in (self._segmentationNode, self._volumeNode):
            if node is not None:
                try:
                    if node.GetScene() is not None:
                        slicer.mrmlScene.RemoveNode(node)
                except Exception:
                    pass
        self._segmentationNode = None
        self._volumeNode = None

    def _ensureSegmentationDisplay(self, segmentationNode):
        """Make sure the segmentation can be seen in the slice and 3D viewers."""
        try:
            segmentationNode.CreateDefaultDisplayNodes()
        except Exception:
            pass
        if segmentationNode.GetDisplayNode() is None:
            try:
                segmentationNode.CreateDisplayNode()
            except Exception:
                pass
        display = segmentationNode.GetDisplayNode()
        if display is not None:
            try:
                display.SetVisibility(True)
            except Exception:
                pass
        try:
            segmentationNode.Create3DDisplayNode()
        except Exception:
            pass
        try:
            segmentationNode.CreateSliceIntersection()
        except Exception:
            pass

    def _repopulateSegmentComboBox(self):
        self.segmentComboBox.blockSignals(True)
        try:
            self.segmentComboBox.clear()
            self.segmentComboBox.setEnabled(False)
            if self._segmentationNode is None:
                return
            segmentation = self._segmentationNode.GetSegmentation()
            count = segmentation.GetNumberOfSegments()
            self.segmentComboBox.addItem(_("(todos os segmentos)"))
            if count == 0:
                self.segmentComboBox.addItem(_("(sem segmentos)"))
                return
            for index in range(count):
                segmentId = segmentation.GetNthSegmentID(index)
                segment = segmentation.GetSegment(segmentId)
                name = str(segment.GetName()) if segment else _("Segmento_{}").format(index + 1)
                self.segmentComboBox.addItem(name)
            self.segmentComboBox.setEnabled(True)
        finally:
            self.segmentComboBox.blockSignals(False)
        self.onSegmentSelected(0)

    def onSegmentSelected(self, index):
        segmentNode = self._segmentationNode
        if segmentNode is None:
            return
        display = segmentNode.GetDisplayNode()
        if display is None:
            return
        segmentation = segmentNode.GetSegmentation()
        if segmentation is None:
            return
        count = segmentation.GetNumberOfSegments()
        selectedId = None
        if index > 0 and count > 0:
            selectedId = segmentation.GetNthSegmentID(index - 1)
        for i in range(count):
            segmentId = segmentation.GetNthSegmentID(i)
            visible = (selectedId is None or segmentId == selectedId)
            try:
                display.SetSegmentVisibility(segmentId, visible)
            except Exception:
                try:
                    segment = segmentation.GetSegment(segmentId)
                    display.SetSegmentVisibility(segment, visible)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Slice navigation
    # ------------------------------------------------------------------
    def _redSliceLogic(self):
        try:
            layoutManager = slicer.app.layoutManager()
            if layoutManager is None:
                return None
            sliceWidget = layoutManager.sliceWidget("Red")
            if sliceWidget is None:
                return None
            return sliceWidget.sliceLogic()
        except Exception:
            return None

    def _centerSlice(self):
        sliceLogic = self._redSliceLogic()
        if sliceLogic is None:
            return
        try:
            sliceRange = sliceLogic.GetSliceRange()
            sliceLogic.SetSliceOffset((sliceRange[0] + sliceRange[1]) / 2.0)
        except Exception:
            pass

    def stepSlice(self, delta):
        sliceLogic = self._redSliceLogic()
        if sliceLogic is None:
            return
        try:
            thickness = sliceLogic.GetSliceThickness()
        except Exception:
            thickness = 1.0
        if not thickness or thickness <= 0:
            thickness = 1.0
        try:
            sliceLogic.SetSliceOffset(sliceLogic.GetSliceOffset() + delta * thickness)
        except Exception:
            return
        self._updateSliceLabel()

    def _updateSliceLabel(self):
        sliceLogic = self._redSliceLogic()
        if sliceLogic is None:
            self.slicePositionLabel.text = "--"
            return
        try:
            thickness = sliceLogic.GetSliceThickness()
        except Exception:
            thickness = 1.0
        if not thickness or thickness <= 0:
            thickness = 1.0
        try:
            sliceRange = sliceLogic.GetSliceRange()
            current = sliceLogic.GetSliceOffset()
            number = int(round((current - sliceRange[0]) / thickness)) + 1
            total = int(round((sliceRange[1] - sliceRange[0]) / thickness)) + 1
            self.slicePositionLabel.text = _("Fatia {} de {}").format(number, total)
        except Exception:
            self.slicePositionLabel.text = ""

    # ------------------------------------------------------------------
    def cleanup(self):
        self.removeObservers()


class SegmentationValidatorLogic(ScriptedLoadableModuleLogic):
    """Implements the actual computation done by this module."""

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)

    @staticmethod
    def discoverCases(datasetFolder):
        return discoverTrainingCases(datasetFolder)

    def loadTrainingCase(self, caseInfo, index):
        """Load an image volume and import its label as a segmentation (segment).

        :return: tuple (volumeNode, segmentationNode)
        """
        volumeNode = slicer.util.loadVolume(
            caseInfo["imagePath"],
            {"name": "ValidationVolume_{}".format(index), "show": True},
        )
        if volumeNode is None:
            raise RuntimeError(_("Nao foi possivel carregar a imagem: ") + caseInfo["imagePath"])

        labelNode = slicer.util.loadLabelVolume(
            caseInfo["labelPath"],
            {"name": "ValidationLabel_tmp", "show": False},
        )
        if labelNode is None:
            slicer.mrmlScene.RemoveNode(volumeNode)
            raise RuntimeError(_("Nao foi possivel carregar o label: ") + caseInfo["labelPath"])

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        segmentationNode.SetName("ValidationSegmentation_{}".format(index))

        try:
            segmentsLogic = slicer.modules.segmentations.logic()
            segmentsLogic.ImportLabelmapToSegmentationNode(labelNode, segmentationNode)
        except Exception:
            if hasattr(slicer.modules.segmentations, "logicImportLabelmapToSegmentationNode"):
                slicer.modules.segmentations.logicImportLabelmapToSegmentationNode(labelNode, segmentationNode)
            else:
                slicer.mrmlScene.RemoveNode(labelNode)
                slicer.mrmlScene.RemoveNode(segmentationNode)
                slicer.mrmlScene.RemoveNode(volumeNode)
                raise RuntimeError(
                    _("Nao foi possivel importar o label como segmento (modulo Segmentations indisponivel).")
                )

        # The label was imported as segments; the temporary label volume is not needed anymore.
        slicer.mrmlScene.RemoveNode(labelNode)

        logging.info("SegmentationValidator: case %s imported", caseInfo["case"])
        return volumeNode, segmentationNode


class SegmentationValidatorTest(ScriptedLoadableModuleTest):
    """Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_DiscoverCases()
        self.test_SuffixParsing()

    def test_DiscoverCases(self):
        import shutil
        import tempfile

        tempDir = tempfile.mkdtemp()
        try:
            imagesDir = os.path.join(tempDir, "imagesTr")
            labelsDir = os.path.join(tempDir, "labelsTr")
            os.makedirs(imagesDir)
            os.makedirs(labelsDir)

            # Valid pairs
            for caseName in ("border", "middle"):
                open(os.path.join(imagesDir, "{}_0000.nii.gz".format(caseName)), "w").close()
                open(os.path.join(labelsDir, "{}.nii.gz".format(caseName)), "w").close()
            # No label for this image -> must be skipped
            open(os.path.join(imagesDir, "no_label_0000.nii.gz"), "w").close()
            # Image without modality suffix but with label -> valid
            open(os.path.join(imagesDir, "plain.nii.gz"), "w").close()
            open(os.path.join(labelsDir, "plain.nii.gz"), "w").close()
            # Label without image -> skipped
            open(os.path.join(labelsDir, "orphan.nii.gz"), "w").close()

            cases, skipped = discoverTrainingCases(tempDir)
            caseNames = [case["case"] for case in cases]

            self.assertEqual(caseNames, ["border", "middle", "plain"])
            self.assertNotIn("no_label", caseNames)
            self.assertIn("no_label", skipped)
            self.assertIn("orphan", skipped)
            for case, labelName in zip(cases, ["border", "middle", "plain"]):
                self.assertTrue(case["labelPath"].endswith(labelName + ".nii.gz"))
        finally:
            shutil.rmtree(tempDir, ignore_errors=True)

    def test_SuffixParsing(self):
        self.assertEqual(caseNameFromImageBase("patient_001_0000"), "patient_001")
        self.assertEqual(caseNameFromImageBase("patient_001_0001"), "patient_001")
        self.assertEqual(caseNameFromImageBase("patient_001"), "patient_001")
        self.assertEqual(stripExtension("a.nii.gz"), "a")
        self.assertEqual(stripExtension("a.nrrd"), "a")