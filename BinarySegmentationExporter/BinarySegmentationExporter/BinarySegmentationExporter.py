import logging
import os
import traceback

import ctk
import qt
import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

import qMRMLWidgetsPythonQt


class BinarySegmentationExporter(ScriptedLoadableModule):

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Exportador Binario (nii.gz 0/1)")
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Pedro (Developer)"]
        self.parent.helpText = _(
            """Exporta uma segmentacao com varios segmentos em um unico <code>.nii.gz</code> binario 3D (X,Y,Z) contendo apenas 0 e 1. """
            """Todos os segmentos sao unidos com OR: voxel vale 1 se pertencer a qualquer segmento, 0 caso contrario (fundo)."""
        )
        self.parent.acknowledgementText = _("Desenvolvido para exportacao binaria de segmentacoes.")


class BinarySegmentationExporterWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._paramNode = None
        self._observedSegmentationNode = None
        self._segmentIds = []
        self._segmentNames = []

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        try:
            self._buildUi()
        except Exception:
            traceback.print_exc()
            slicer.util.errorDisplay(_("Nao foi possivel criar a interface.\n") + traceback.format_exc())

    def _buildUi(self):
        self.logic = BinarySegmentationExporterLogic()

        ioBox = ctk.ctkCollapsibleButton()
        ioBox.text = _("Entrada / Saida")
        ioBox.collapsed = False
        self.layout.addWidget(ioBox)
        ioForm = qt.QFormLayout(ioBox)

        self.segmentationSelector = qMRMLWidgetsPythonQt.qMRMLNodeComboBox()
        self.segmentationSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
        self.segmentationSelector.baseName = "Segmentacao"
        self.segmentationSelector.setMRMLScene(slicer.mrmlScene)
        self.segmentationSelector.toolTip = _("Segmentation node com um ou mais segmentos.")
        ioForm.addRow(_("Segmentacao:"), self.segmentationSelector)

        self.referenceVolumeSelector = qMRMLWidgetsPythonQt.qMRMLNodeComboBox()
        self.referenceVolumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode", "vtkMRMLLabelMapVolumeNode"]
        self.referenceVolumeSelector.baseName = "Volume referencia"
        self.referenceVolumeSelector.noneEnabled = True
        self.referenceVolumeSelector.addEnabled = False
        self.referenceVolumeSelector.removeEnabled = False
        self.referenceVolumeSelector.setMRMLScene(slicer.mrmlScene)
        self.referenceVolumeSelector.toolTip = _("Volume que define a geometria (origem/espacamento/dimensoes) do NIfTI. Se vazio, usa a geometria da segmentacao.")
        ioForm.addRow(_("Volume referencia:"), self.referenceVolumeSelector)

        self.outputPathSelector = ctk.ctkPathLineEdit()
        self.outputPathSelector.filters = ctk.ctkPathLineEdit.Files
        self.outputPathSelector.nameFilters = ["*.nii.gz (*.nii.gz)", "*.nii (*.nii)", "*.* (*.*)"]
        self.outputPathSelector.toolTip = _("Arquivo de saida binario, ex: C:/data/labels.nii.gz (3D com apenas 0 e 1)")
        ioForm.addRow(_("Saida .nii.gz:"), self.outputPathSelector)

        segBox = ctk.ctkCollapsibleButton()
        segBox.text = _("Segmentos (todos serao unidos com OR)")
        segBox.collapsed = False
        self.layout.addWidget(segBox)
        segLayout = qt.QVBoxLayout(segBox)

        self.segmentList = qt.QListWidget()
        self.segmentList.toolTip = _("Todos os segmentos listados serao unidos em um unico volume binario 0/1.")
        segLayout.addWidget(self.segmentList)

        hint = qt.QLabel(_("Saida: NIfTI 3D binario — 0 = fundo, 1 = uniao de todos os segmentos (OR). Mesmo com N segmentos, o arquivo tera apenas valores 0 e 1."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 8pt;")
        segLayout.addWidget(hint)

        self.exportButton = qt.QPushButton(_("Exportar binario 0/1 (.nii.gz)"))
        self.exportButton.toolTip = _("Gera o NIfTI 3D binario com 0 e 1 no caminho escolhido.")
        self.layout.addWidget(self.exportButton)

        self.statusLabel = qt.QLabel(_("Pronto."))
        self.statusLabel.setWordWrap(True)
        self.layout.addWidget(self.statusLabel)
        self.layout.addStretch(1)

        self.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSegmentationChanged)
        self.exportButton.connect("clicked()", self.onExportClicked)

        self.initializeParameterNode()
        self.onSegmentationChanged()

    def initializeParameterNode(self):
        node = self.logic.getParameterNode()
        if node is not self._paramNode:
            self._paramNode = node
        settings = qt.QSettings()
        folder = settings.value("BinarySegmentationExporter/OutputPath", "")
        if folder:
            self.outputPathSelector.currentPath = str(folder)

    def _saveSettings(self):
        settings = qt.QSettings()
        settings.setValue("BinarySegmentationExporter/OutputPath", self.outputPathSelector.currentPath)
        node = self.logic.getParameterNode()
        node.SetParameter("OutputPath", self.outputPathSelector.currentPath)

    def onSegmentationChanged(self, *args, **kwargs):
        node = self.segmentationSelector.currentNode()
        if self._observedSegmentationNode is not None:
            self.removeObserver(self._observedSegmentationNode, vtk.vtkCommand.ModifiedEvent, self.refreshList)
        self._observedSegmentationNode = node
        if node is not None:
            self.addObserver(node, vtk.vtkCommand.ModifiedEvent, self.refreshList)
        self.refreshList()

    def refreshList(self, caller=None, event=None):
        self.segmentList.clear()
        self._segmentIds = []
        self._segmentNames = []
        node = self._observedSegmentationNode
        if node is None:
            return
        segmentation = node.GetSegmentation()
        n = segmentation.GetNumberOfSegments()
        for i in range(n):
            segId = segmentation.GetNthSegmentID(i)
            seg = segmentation.GetSegment(segId)
            name = seg.GetName() if seg else segId
            self._segmentIds.append(segId)
            self._segmentNames.append(name)
            color = seg.GetColor() if seg else (0.5, 0.5, 0.5)
            try:
                r, g, b = [int(max(0, min(1, v)) * 255) for v in color[:3]]
                pix = " ■ "
            except:
                r, g, b = 128, 128, 128
                pix = ""
            item = qt.QListWidgetItem("{} {}{}".format(pix, str(name), " [{}]".format(segId) if str(name) != str(segId) else ""))
            try:
                item.setBackground(qt.QColor(r, g, b))
            except:
                pass
            item.setFlags(item.flags() & ~qt.Qt.ItemIsEditable)
            self.segmentList.addItem(item)

    def onExportClicked(self):
        self.exportButton.enabled = False
        try:
            with slicer.util.tryWithErrorDisplay(_("Falha ao exportar binario."), waitCursor=True):
                self.doExport()
        finally:
            self.exportButton.enabled = True

    def doExport(self):
        segmentationNode = self.segmentationSelector.currentNode()
        referenceVolumeNode = self.referenceVolumeSelector.currentNode()
        outputPath = str(self.outputPathSelector.currentPath).strip()

        if segmentationNode is None:
            raise ValueError(_("Selecione a segmentacao."))
        if not outputPath:
            raise ValueError(_("Escolha o arquivo de saida .nii.gz."))
        if not self._segmentIds:
            raise ValueError(_("A segmentacao nao contem segmentos."))

        outputPath = os.path.abspath(outputPath)
        if not outputPath.lower().endswith(".nii.gz") and not outputPath.lower().endswith(".nii"):
            outputPath += ".nii.gz"
        os.makedirs(os.path.dirname(outputPath) or ".", exist_ok=True)

        self.logic.exportBinary(segmentationNode, referenceVolumeNode, outputPath)
        self._saveSettings()
        self.statusLabel.setStyleSheet("color: #1e7b34; font-weight: bold;")
        self.statusLabel.setText(_("Exportado com sucesso (binario 0/1, {} segmentos unidos):\n{}").format(len(self._segmentIds), outputPath))
        qt.QMessageBox.information(slicer.util.mainWindow(), _("Exportacao concluida"), _("Binario 0/1 salvo em:\n{}\n\nSegmentos unidos (OR): {}\nValores: apenas 0 e 1").format(outputPath, ", ".join(self._segmentNames)))

    def cleanup(self):
        if self._observedSegmentationNode is not None:
            self.removeObserver(self._observedSegmentationNode, vtk.vtkCommand.ModifiedEvent, self.refreshList)
            self._observedSegmentationNode = None
        self.removeObservers()


class BinarySegmentationExporterLogic(ScriptedLoadableModuleLogic):

    def exportBinary(self, segmentationNode, referenceVolumeNode, outputPath):
        if segmentationNode is None:
            raise ValueError("Invalid segmentation node")

        import numpy as np

        segmentation = segmentationNode.GetSegmentation()
        n = segmentation.GetNumberOfSegments()
        if n == 0:
            raise ValueError(_("A segmentacao nao contem segmentos."))
        segmentIds = [segmentation.GetNthSegmentID(i) for i in range(n)]

        outputPath = os.path.abspath(outputPath)
        d = os.path.dirname(outputPath)
        if d:
            os.makedirs(d, exist_ok=True)

        hasNibabel = False
        try:
            import nibabel
            hasNibabel = True
        except ImportError:
            hasNibabel = False

        hasSitk = False
        try:
            import SimpleITK
            hasSitk = True
        except ImportError:
            hasSitk = False

        if not hasNibabel and not hasSitk:
            raise RuntimeError(_("Nem nibabel nem SimpleITK encontrados. Instale um deles: pip install nibabel  ou  pip install SimpleITK"))

        logic = slicer.modules.segmentations.logic()
        tempLabel = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
        slicer.mrmlScene.AddNode(tempLabel)
        tempLabel.SetName("_tmpBinaryExport")

        ijkToRas = None
        unionZYX = None

        try:
            for segId in segmentIds:
                arr = vtk.vtkStringArray()
                arr.InsertNextValue(segId)
                ok = logic.ExportSegmentsToLabelmapNode(segmentationNode, arr, tempLabel, referenceVolumeNode)
                if not ok:
                    raise RuntimeError(_("Falha ao converter segmento '{}' para labelmap.").format(segId))

                if ijkToRas is None:
                    src = referenceVolumeNode if referenceVolumeNode is not None else tempLabel
                    ijkToRas = self._getIJKToRASMatrix(src)

                volArray = slicer.util.arrayFromVolume(tempLabel)
                if volArray is None:
                    raise RuntimeError(_("Nao foi possivel ler array do labelmap temporario."))
                volArray = (volArray > 0).astype(np.uint8)

                if unionZYX is None:
                    unionZYX = volArray
                else:
                    if unionZYX.shape != volArray.shape:
                        raise RuntimeError(_("Geometria inconsistente entre segmentos. Verifique o volume de referencia."))
                    unionZYX = np.logical_or(unionZYX, volArray).astype(np.uint8)

            if unionZYX is None:
                raise RuntimeError(_("Nenhum dado gerado."))

            unionZYX = (unionZYX > 0).astype(np.uint8)
            dataXYZ = np.transpose(unionZYX, (2, 1, 0))

            if hasNibabel:
                import nibabel as nib
                img = nib.Nifti1Image(dataXYZ.astype(np.uint8), ijkToRas)
                img.header.set_data_dtype(np.uint8)
                nib.save(img, outputPath)
            else:
                import SimpleITK as sitk
                import sitkUtils
                tmp = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
                slicer.mrmlScene.AddNode(tmp)
                try:
                    slicer.util.updateVolumeFromArray(tmp, unionZYX)
                    tmp.CopyOrientation(referenceVolumeNode if referenceVolumeNode else tempLabel)
                    si = sitkUtils.PullVolumeFromSlicer(tmp)
                    sitk.WriteImage(si, outputPath)
                finally:
                    slicer.mrmlScene.RemoveNode(tmp)

        finally:
            slicer.mrmlScene.RemoveNode(tempLabel)

        logging.info("Binary export: %s (%d segmentos -> 0/1)", outputPath, len(segmentIds))
        return outputPath

    def _getIJKToRASMatrix(self, node):
        import numpy as np
        m = vtk.vtkMatrix4x4()
        node.GetIJKToRASMatrix(m)
        arr = np.eye(4)
        for r in range(4):
            for c in range(4):
                arr[r, c] = m.GetElement(r, c)
        return arr


class BinarySegmentationExporterTest(ScriptedLoadableModuleTest):

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_ExportBinary()

    def test_ExportBinary(self):
        self.delayDisplay("Starting binary export test")
        import tempfile
        import shutil
        import numpy as np

        vol = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        arr = np.zeros((8, 8, 8), dtype=np.int16)
        slicer.util.updateVolumeFromArray(vol, arr)

        def makeLabel(pos):
            ln = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
            a = np.zeros((8, 8, 8), dtype=np.uint8)
            a[pos] = 1
            slicer.util.updateVolumeFromArray(ln, a)
            return ln

        l1 = makeLabel((2, 2, 2))
        l2 = makeLabel((5, 5, 5))
        l3 = makeLabel((2, 2, 2))
        logicSeg = slicer.modules.segmentations.logic()

        def _segFromLabel(n):
            if hasattr(logicSeg, "CreateSegmentFromLabelmapNode"):
                return logicSeg.CreateSegmentFromLabelmapNode(n)
            ts = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentationNode")
            slicer.mrmlScene.AddNode(ts)
            logicSeg.ImportLabelmapToSegmentationNode(n, ts)
            src = ts.GetSegmentation().GetSegment(ts.GetSegmentation().GetNthSegmentID(0))
            s = slicer.vtkSegment()
            s.DeepCopy(src)
            slicer.mrmlScene.RemoveNode(ts)
            return s

        s1 = _segFromLabel(l1)
        s1.SetName("SegA")
        s2 = _segFromLabel(l2)
        s2.SetName("SegB")
        s3 = _segFromLabel(l3)
        s3.SetName("SegC_overlap")
        segNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        segNode.GetSegmentation().AddSegment(s1)
        segNode.GetSegmentation().AddSegment(s2)
        segNode.GetSegmentation().AddSegment(s3)

        tmpDir = tempfile.mkdtemp()
        out = os.path.join(tmpDir, "binary.nii.gz")
        logic = BinarySegmentationExporterLogic()
        logic.exportBinary(segNode, vol, out)
        self.assertTrue(os.path.isfile(out))
        try:
            import nibabel as nib
            img = nib.load(out)
            data = img.get_fdata()
            self.assertEqual(data.shape, (8, 8, 8))
            vals = set(np.unique(data).astype(int).tolist())
            self.assertTrue(vals.issubset({0, 1}), "Valores devem ser apenas 0 e 1, obtido: {}".format(vals))
            self.assertEqual(int(data[2, 2, 2]), 1)
            self.assertEqual(int(data[5, 5, 5]), 1)
            self.assertEqual(int(data[0, 0, 0]), 0)
        except ImportError:
            self.assertTrue(os.path.getsize(out) > 0)
        shutil.rmtree(tmpDir, ignore_errors=True)
        self.delayDisplay("Binary test passed")
