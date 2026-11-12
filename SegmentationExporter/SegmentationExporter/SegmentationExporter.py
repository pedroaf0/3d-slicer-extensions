"""SegmentationExporter - creates training data for deep learning segmentation (nnU-Net format).

The module exports, for one case:
  * the selected volume              -> <dataset>/imagesTr/<name>_0000.nii.gz
  * the selected segment (as labelmap) -> <dataset>/labelsTr/<name>.nii.gz

Example dataset folder: Dataset001_canalRadicular
"""

import csv
import datetime
import logging
import os
import re
import shutil
import time
import traceback

import ctk
import qt
import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

import qMRMLWidgetsPythonQt


def sanitizeCaseName(name):
    """Make a safe nnU-Net case file-name base from the user input."""
    name = name.strip()
    name = name.replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_-]", "_", name)
    name = name.strip("_")
    return name


class SegmentationExporter(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Exportador de Segmentacoes (nnU-Net)"
        self.parent.categories = ["Segmentation", "Deep Learning"]
        self.parent.dependencies = []
        self.parent.contributors = ["Pedro (Developer)"]
        self.parent.helpText = _(
            """Exporta um volume acompanhado de um segmento (convertido para labelmap) nas pastas
<code>imagesTr</code> e <code>labelsTr</code> de um dataset no formato nnU-Net
(por exemplo <code>Dataset001_canalRadicular</code>).

Saida gerada:
  <code>&lt;dataset&gt;/imagesTr/&lt;nome&gt;_0000.nii.gz</code>
  <code>&lt;dataset&gt;/labelsTr/&lt;nome&gt;.nii.gz</code>
"""
        )
        self.parent.acknowledgementText = _("Developed for canalRadicular segmentation training.")


class SegmentationExporterWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._paramNode = None
        self._observedSegmentationNode = None
        self._segmentNames = []
        self._segmentIds = []

    def setup(self):
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        try:
            self._buildUi()
        except Exception:
            traceback.print_exc()
            slicer.util.errorDisplay(
                _("Nao foi possivel criar a interface do modulo.\n") + traceback.format_exc()
            )

    def _buildUi(self):
        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = SegmentationExporterLogic()

        # ------------------------------------------------------------------
        # Input/output collapsible box
        # ------------------------------------------------------------------
        paramCollapsibleButton = ctk.ctkCollapsibleButton()
        paramCollapsibleButton.text = _("Parametros de exportacao")
        paramCollapsibleButton.collapsed = False
        self.layout.addWidget(paramCollapsibleButton)

        formLayout = qt.QFormLayout(paramCollapsibleButton)

        # Dataset folder
        self.datasetFolderSelector = ctk.ctkPathLineEdit()
        self.datasetFolderSelector.filters = ctk.ctkPathLineEdit.Dirs
        self.datasetFolderSelector.toolTip = _(
            "Pasta do dataset, por exemplo: Dataset001_canalRadicular. "
            "Dentro dela sao criadas/carregadas as pastas imagesTr e labelsTr."
        )
        formLayout.addRow(_("Dataset:"), self.datasetFolderSelector)

        # Case name
        self.caseNameEdit = qt.QLineEdit()
        self.caseNameEdit.setPlaceholderText(_("exemplo: paciente_001"))
        self.caseNameEdit.toolTip = _(
            "Nome do caso. Entra no nome final dos arquivos: "
            "<nome>_<dicom>_<segmentador>_<data>_0000.nii.gz (imagem) e <nome>.nii.gz (labelmap)."
        )
        formLayout.addRow(_("Nome:"), self.caseNameEdit)

        # Volume selector
        self.volumeSelector = qMRMLWidgetsPythonQt.qMRMLNodeComboBox()
        self.volumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.volumeSelector.baseName = "Volume"
        self.volumeSelector.setMRMLScene(slicer.mrmlScene)
        self.volumeSelector.toolTip = _("Volume a ser exportado (geometria de referencia do labelmap).")
        formLayout.addRow(_("Volume:"), self.volumeSelector)

        # Segmentation node selector
        self.segmentationNodeSelector = qMRMLWidgetsPythonQt.qMRMLNodeComboBox()
        self.segmentationNodeSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
        self.segmentationNodeSelector.baseName = "Segmentacao"
        self.segmentationNodeSelector.setMRMLScene(slicer.mrmlScene)
        self.segmentationNodeSelector.toolTip = _("Segmentation node criada no Segment Editor.")
        formLayout.addRow(_("Segmentacao:"), self.segmentationNodeSelector)

        # Segment selector
        self.segmentComboBox = qt.QComboBox()
        self.segmentComboBox.toolTip = _(
            "Segmento a ser convertido para labelmap (valor 1 = estrutura, 0 = fundo)."
        )
        formLayout.addRow(_("Segmento:"), self.segmentComboBox)

        # Original DICOM name (either type it or pick the original volume)
        self.dicomOriginalLineEdit = qt.QLineEdit()
        self.dicomOriginalLineEdit.setPlaceholderText(_("digite o nome do DICOM original"))
        self.dicomOriginalLineEdit.toolTip = _(
            "Nome do DICOM original (do PACS/label do exame). "
            "Digite manualmente ou selecione o volume original abaixo."
        )
        formLayout.addRow(_("DICOM original:"), self.dicomOriginalLineEdit)

        self.dicomVolumeSelector = qMRMLWidgetsPythonQt.qMRMLNodeComboBox()
        self.dicomVolumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.dicomVolumeSelector.baseName = "Volume DICOM"
        self.dicomVolumeSelector.setMRMLScene(slicer.mrmlScene)
        self.dicomVolumeSelector.toolTip = _(
            "Selecione o volume DICOM original para preencher o nome acima automaticamente."
        )
        formLayout.addRow(_("Pegar nome do:"), self.dicomVolumeSelector)

        # Person performing the segmentation
        self.segmenterNameEdit = qt.QLineEdit()
        self.segmenterNameEdit.setPlaceholderText(_("nome de quem esta segmentando"))
        self.segmenterNameEdit.toolTip = _("Nome da pessoa que realizou a segmentacao (vai para o CSV).")
        formLayout.addRow(_("Segmentador:"), self.segmenterNameEdit)

        # ------------------------------------------------------------------
        # Export button
        # ------------------------------------------------------------------
        self.exportButton = qt.QPushButton(_("Exportar"))
        self.exportButton.toolTip = _(
            "Exporta o volume em imagesTr/<nome>_<dicom>_<segmentador>_<data>_0000.nii.gz e o segmento "
            "(labelmap) em labelsTr/<nome>_<dicom>_<segmentador>_<data>.nii.gz"
        )
        self.layout.addWidget(self.exportButton)

        # Status
        self.statusLabel = qt.QLabel(_("Pronto."))
        self.statusLabel.setWordWrap(True)
        self.layout.addWidget(self.statusLabel)

        self.layout.addStretch(1)

        # Connections
        self.exportButton.connect("clicked()", self.onExportClicked)
        self.segmentationNodeSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.onSegmentationNodeChanged
        )
        self.segmentComboBox.connect("currentIndexChanged(int)", self.onCurrentSegmentChanged)
        self.dicomVolumeSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.onDicomVolumeChanged
        )

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

        # Fill the segment combo box with the current segmentation
        self.onSegmentationNodeChanged()

    # ------------------------------------------------------------------
    # Parameter node management
    # ------------------------------------------------------------------
    def initializeParameterNode(self):
        """Ensure parameter node exists and restore stored settings."""
        node = self.logic.getParameterNode()
        if node is not self._paramNode:
            self._paramNode = node

        folder = node.GetParameter("DatasetFolder") or ""
        name = node.GetParameter("CaseName") or ""
        dicomOriginal = node.GetParameter("DicomOriginal") or ""
        segmenterName = node.GetParameter("SegmenterName") or ""

        # Last used values (persist between Slicer restarts, they take precedence)
        settings = qt.QSettings()
        folder = settings.value("SegmentationExporter/DatasetFolder", folder)
        name = settings.value("SegmentationExporter/CaseName", name)
        dicomOriginal = settings.value("SegmentationExporter/DicomOriginal", dicomOriginal)
        segmenterName = settings.value("SegmentationExporter/SegmenterName", segmenterName)

        if folder:
            self.datasetFolderSelector.currentPath = folder
        if name:
            self.caseNameEdit.text = name
        if dicomOriginal:
            self.dicomOriginalLineEdit.text = dicomOriginal
        if segmenterName:
            self.segmenterNameEdit.text = segmenterName

    def _saveInputs(self, datasetFolder, caseName, dicomOriginal="", segmenterName=""):
        node = self.logic.getParameterNode()
        node.SetParameter("DatasetFolder", datasetFolder)
        node.SetParameter("CaseName", caseName)
        if dicomOriginal:
            node.SetParameter("DicomOriginal", dicomOriginal)
        if segmenterName:
            node.SetParameter("SegmenterName", segmenterName)

        settings = qt.QSettings()
        settings.setValue("SegmentationExporter/DatasetFolder", datasetFolder)
        settings.setValue("SegmentationExporter/CaseName", caseName)
        settings.setValue("SegmentationExporter/DicomOriginal", dicomOriginal)
        settings.setValue("SegmentationExporter/SegmenterName", segmenterName)

    # ------------------------------------------------------------------
    # DICOM original name handling
    # ------------------------------------------------------------------
    def onDicomVolumeChanged(self, *args, **kwargs):
        node = self.dicomVolumeSelector.currentNode()
        if node is not None:
            self.dicomOriginalLineEdit.text = node.GetName()

    # ------------------------------------------------------------------
    # Segment / segmentation handling
    # ------------------------------------------------------------------
    def onSegmentationNodeChanged(self, *args, **kwargs):
        node = self.segmentationNodeSelector.currentNode()

        if self._observedSegmentationNode is not None:
            self.removeObserver(self._observedSegmentationNode, vtk.vtkCommand.ModifiedEvent, self.refreshSegmentComboBox)
        self._observedSegmentationNode = node
        if node is not None:
            # Keeps the segment dropdown in sync when segments are added/removed/renamed in Segment Editor
            self.addObserver(node, vtk.vtkCommand.ModifiedEvent, self.refreshSegmentComboBox)
        self.refreshSegmentComboBox()

    def refreshSegmentComboBox(self, caller=None, event=None):
        node = self._observedSegmentationNode
        previous = str(self.segmentComboBox.currentText)
        self.segmentComboBox.blockSignals(True)
        try:
            self.segmentComboBox.clear()
            self._segmentNames = []
            self._segmentIds = []
            if node is None:
                return
            segmentation = node.GetSegmentation()
            count = segmentation.GetNumberOfSegments()
            usedNames = set()
            for index in range(count):
                segmentId = segmentation.GetNthSegmentID(index)
                segment = segmentation.GetSegment(segmentId)
                name = str(segment.GetName()) if segment else str(segmentId)
                display = name
                if display in usedNames:
                    display = "{} [{}]".format(name, segmentId)
                usedNames.add(display)
                self._segmentNames.append(display)
                self._segmentIds.append(segmentId)
            self.segmentComboBox.addItems(self._segmentNames)
            if previous in self._segmentNames:
                self.segmentComboBox.setCurrentIndex(self._segmentNames.index(previous))
        finally:
            self.segmentComboBox.blockSignals(False)
        self.onCurrentSegmentChanged()

    def onCurrentSegmentChanged(self, *args, **kwargs):
        self.statusLabel.setText(_("Pronto."))
        self.statusLabel.setStyleSheet("")

    def currentSegmentId(self):
        index = self.segmentComboBox.currentIndex
        if 0 <= index < len(self._segmentIds):
            return self._segmentIds[index]
        return None

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def onExportClicked(self, arg=None):
        self.exportButton.enabled = False
        try:
            with slicer.util.tryWithErrorDisplay(_("Falha ao exportar os dados."), waitCursor=True):
                self.doExport()
        finally:
            self.exportButton.enabled = True

    def doExport(self):
        datasetFolder = str(self.datasetFolderSelector.currentPath).strip()
        caseNameInput = self.caseNameEdit.text.strip()
        volumeNode = self.volumeSelector.currentNode()
        segmentationNode = self.segmentationNodeSelector.currentNode()
        segmentId = self.currentSegmentId()
        dicomOriginalInput = str(self.dicomOriginalLineEdit.text).strip()
        segmenterNameInput = str(self.segmenterNameEdit.text).strip()

        if not datasetFolder:
            raise ValueError(_("Selecione a pasta do dataset (ex.: Dataset001_canalRadicular)."))
        if not os.path.isdir(datasetFolder):
            raise ValueError(_("A pasta do dataset informada nao existe ou nao e uma pasta: ") + datasetFolder)
        if volumeNode is None:
            raise ValueError(_("Selecione o volume a ser exportado."))
        if segmentationNode is None:
            raise ValueError(_("Selecione a segmentacao (criada no Segment Editor)."))
        if not segmentId:
            raise ValueError(_("A segmentacao selecionada nao contem nenhum segmento."))
        if not caseNameInput:
            raise ValueError(_("Informe o nome do caso."))
        if not segmenterNameInput:
            raise ValueError(_("Informe o nome do segmentador."))

        caseName = sanitizeCaseName(caseNameInput)
        if not caseName:
            raise ValueError(_("O nome do caso informado e invalido."))

        # Original DICOM name: use the typed name, otherwise the selected volume name
        dicomOriginal = dicomOriginalInput or (volumeNode.GetName() or "")

        baseDir = os.path.abspath(datasetFolder)
        imagesDir = os.path.join(baseDir, "imagesTr")
        labelsDir = os.path.join(baseDir, "labelsTr")
        os.makedirs(imagesDir, exist_ok=True)
        os.makedirs(labelsDir, exist_ok=True)

        dateStr = datetime.datetime.now().strftime("%Y%m%d")
        nameParts = [caseName]
        dicomPart = sanitizeCaseName(dicomOriginal)
        if dicomPart:
            nameParts.append(dicomPart)
        segmenterPart = sanitizeCaseName(segmenterNameInput)
        if segmenterPart:
            nameParts.append(segmenterPart)
        nameParts.append(dateStr)
        baseName = sanitizeCaseName("_".join(nameParts))

        imagePath = os.path.join(imagesDir, "{}_0000.nii.gz".format(baseName))
        labelPath = os.path.join(labelsDir, "{}.nii.gz".format(baseName))

        self.logic.exportTrainingData(volumeNode, segmentationNode, segmentId, imagePath, labelPath)
        self._writeMetadataCsv(baseDir, caseName, dicomOriginal, segmenterNameInput, imagePath, labelPath)

        self._saveInputs(datasetFolder, caseNameInput, dicomOriginal, segmenterNameInput)
        self.statusLabel.setStyleSheet("color: #1e7b34; font-weight: bold;")
        self.statusLabel.setText(_("Exportado com sucesso:\n{}\n{}").format(imagePath, labelPath))
        qt.QMessageBox.information(
            slicer.util.mainWindow(),
            _("Exportacao concluida"),
            _("Arquivos gerados com sucesso:\n\n{}\n{}").format(imagePath, labelPath),
        )

    # ------------------------------------------------------------------
    # CSV metadata
    # ------------------------------------------------------------------
    _METADATA_CSV_FILENAME = "segmentation_metadata.csv"
    _METADATA_CSV_FIELDS = [
        "nome",
        "dicom original",
        "nome do segmentador",
        "nome do arquivo imagem",
        "nome do arquivo label",
    ]

    def _writeMetadataCsv(self, datasetFolder, caseName, dicomOriginal, segmenterName, imagePath, labelPath):
        """Append (or update) a line in the dataset CSV with the export metadata."""
        csvPath = os.path.join(datasetFolder, self._METADATA_CSV_FILENAME)
        imageFileName = os.path.basename(imagePath)

        rows = []
        if os.path.isfile(csvPath):
            with open(csvPath, "r", encoding="utf-8-sig", newline="") as csvFile:
                reader = csv.DictReader(csvFile)
                rows = [dict(row) for row in reader if row.get("nome do arquivo imagem") != imageFileName]

        rows.append({
            "nome": caseName,
            "dicom original": dicomOriginal,
            "nome do segmentador": segmenterName,
            "nome do arquivo imagem": imageFileName,
            "nome do arquivo label": os.path.basename(labelPath),
        })

        with open(csvPath, "w", encoding="utf-8-sig", newline="") as csvFile:
            writer = csv.DictWriter(csvFile, fieldnames=self._METADATA_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def cleanup(self):
        """Called when the application closes and the module widget is destroyed."""
        if self._observedSegmentationNode is not None:
            self.removeObserver(self._observedSegmentationNode, vtk.vtkCommand.ModifiedEvent, self.refreshSegmentComboBox)
            self._observedSegmentationNode = None
        self.removeObservers()


class SegmentationExporterLogic(ScriptedLoadableModuleLogic):
    """Implements all the actual computation done by this module.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)

    def exportTrainingData(self, volumeNode, segmentationNode, segmentId, imageOutputPath, labelOutputPath):
        """Export a volume and a single segment (converted to a labelmap aligned
        with the volume geometry) to image and label file paths.

        :return: tuple of the two file paths that were written.
        """
        if volumeNode is None or segmentationNode is None:
            raise ValueError("Invalid input nodes")

        imageOutputPath = os.path.abspath(imageOutputPath)
        labelOutputPath = os.path.abspath(labelOutputPath)
        for path in (imageOutputPath, labelOutputPath):
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)

        startTime = time.time()
        logging.info("SegmentationExporter: export started")

        # 1) Volume
        if not slicer.util.saveNode(volumeNode, imageOutputPath):
            raise RuntimeError(_("Nao foi possivel salvar o volume em: ") + imageOutputPath)
        logging.info("Volume saved: %s", imageOutputPath)

        # 2) Segment as labelmap matching the volume geometry
        segmentLabels = vtk.vtkStringArray()
        segmentLabels.InsertNextValue(segmentId)
        segmentsLogic = slicer.modules.segmentations.logic()

        labelNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
        slicer.mrmlScene.AddNode(labelNode)
        labelNode.SetName("TrainingLabelmapExport")
        try:
            if not segmentsLogic.ExportSegmentsToLabelmapNode(
                segmentationNode, segmentLabels, labelNode, volumeNode
            ):
                raise RuntimeError(_("Nao foi possivel converter o segmento para labelmap."))
            if not slicer.util.saveNode(labelNode, labelOutputPath):
                raise RuntimeError(_("Nao foi possivel salvar o labelmap em: ") + labelOutputPath)
            logging.info("Labelmap saved: %s", labelOutputPath)
        finally:
            slicer.mrmlScene.RemoveNode(labelNode)

        logging.info("SegmentationExporter: export completed in %.2f seconds", time.time() - startTime)
        return (imageOutputPath, labelOutputPath)


class SegmentationExporterTest(ScriptedLoadableModuleTest):
    """Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        self.test_SanitizeCaseName()
        self.test_ExportCreatesFiles()

    def test_SanitizeCaseName(self):
        self.assertEqual(sanitizeCaseName("Paciente 001"), "Paciente_001")
        self.assertEqual(sanitizeCaseName("  a/b\\c  "), "a_b_c")
        self.assertNotIn(" ", sanitizeCaseName("spaces and accents"))

    def test_ExportCreatesFiles(self):
        """Create a tiny volume + segmentation and check that export writes the expected files."""
        self.delayDisplay("Starting export test")

        import numpy as np
        import tempfile

        volumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        volumeArray = np.zeros((8, 8, 8), dtype=np.int16)
        volumeArray[2, 2, 2] = 5
        slicer.util.updateVolumeFromArray(volumeNode, volumeArray)

        labelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        labelArray = np.zeros((8, 8, 8), dtype=np.uint8)
        labelArray[2, 2, 2] = 1
        slicer.util.updateVolumeFromArray(labelNode, labelArray)

        segmentsLogic = slicer.modules.segmentations.logic()
        segment = segmentsLogic.CreateSegmentFromLabelmapNode(labelNode)
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        segmentationNode.GetSegmentation().AddSegment(segment)
        segmentId = segmentationNode.GetSegmentation().GetNthSegmentID(0)
        self.assertTrue(segmentId)

        tempDir = tempfile.mkdtemp()
        imagePath = os.path.join(tempDir, "imagesTr", "paciente_001_0000.nii.gz")
        labelPath = os.path.join(tempDir, "labelsTr", "paciente_001.nii.gz")

        logic = SegmentationExporterLogic()
        imagePathOut, labelPathOut = logic.exportTrainingData(
            volumeNode, segmentationNode, segmentId, imagePath, labelPath
        )

        self.assertTrue(os.path.isfile(imagePathOut))
        self.assertTrue(os.path.isfile(labelPathOut))
        self.assertEqual(sanitizeCaseName(os.path.basename(imagePathOut)), "paciente_001_0000")

        # Clean up the temporary folder
        shutil.rmtree(tempDir, ignore_errors=True)

        self.delayDisplay("Export test passed")