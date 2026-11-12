import json
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


class MultiChannelSegmentationExporter(ScriptedLoadableModule):

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Exportador Multicanal (nii.gz)")
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Pedro (Developer)"]
        self.parent.helpText = _(
            """Exporta uma segmentacao como labelmap <code>.nii.gz</code> 3D (X,Y,Z).
O valor 0 e sempre o fundo (background). Cada segmento recebe o valor <code>canal+1</code> (canal 0-&gt;1, 1-&gt;2, ...).
Segmentos no mesmo canal sao unidos com OR. Sobreposicao entre canais: canal de menor indice tem prioridade."""
        )
        self.parent.acknowledgementText = _("Desenvolvido para exportacao de treinamento multicanal.")


class MultiChannelSegmentationExporterWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._paramNode = None
        self._observedSegmentationNode = None
        self._segmentIds = []
        self._segmentNames = []
        self._updatingTable = False

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        try:
            self._buildUi()
        except Exception:
            traceback.print_exc()
            slicer.util.errorDisplay(_("Nao foi possivel criar a interface.\n") + traceback.format_exc())

    def _buildUi(self):
        self.logic = MultiChannelSegmentationExporterLogic()

        ioBox = ctk.ctkCollapsibleButton()
        ioBox.text = _("Entrada / Saida")
        ioBox.collapsed = False
        self.layout.addWidget(ioBox)
        ioForm = qt.QFormLayout(ioBox)

        self.segmentationSelector = qMRMLWidgetsPythonQt.qMRMLNodeComboBox()
        self.segmentationSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
        self.segmentationSelector.baseName = "Segmentacao"
        self.segmentationSelector.setMRMLScene(slicer.mrmlScene)
        self.segmentationSelector.toolTip = _("Segmentation node criada no Segment Editor.")
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
        self.outputPathSelector.toolTip = _("Arquivo de saida labelmap, ex: C:/data/labels.nii.gz (3D: X,Y,Z com 0=fundo e 1..N um valor por canal)")
        ioForm.addRow(_("Saida .nii.gz:"), self.outputPathSelector)

        mapBox = ctk.ctkCollapsibleButton()
        mapBox.text = _("Mapeamento segmento -> canal")
        mapBox.collapsed = False
        self.layout.addWidget(mapBox)
        mapLayout = qt.QVBoxLayout(mapBox)

        topRow = qt.QHBoxLayout()
        mapLayout.addLayout(topRow)
        topRow.addWidget(qt.QLabel(_("Canais:")))
        self.numChannelsSpin = qt.QSpinBox()
        self.numChannelsSpin.minimum = 1
        self.numChannelsSpin.maximum = 32
        self.numChannelsSpin.value = 2
        self.numChannelsSpin.toolTip = _("Numero de canais no NIfTI 4D (dimensao C). Canais indexados de 0 a N-1.")
        topRow.addWidget(self.numChannelsSpin)
        topRow.addStretch(1)
        self.btnAuto = qt.QPushButton(_("Auto (sequencial)"))
        self.btnAuto.toolTip = _("Atribui cada segmento a um canal sequencial 0,1,2... (volta ao 0 se faltar canal).")
        topRow.addWidget(self.btnAuto)
        self.btnClear = qt.QPushButton(_("Limpar"))
        topRow.addWidget(self.btnClear)

        self.table = qt.QTableWidget()
        self.table.columnCount = 3
        self.table.setHorizontalHeaderLabels([_("Segmento"), _("Canal"), _("Cor")])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, qt.QHeaderView.Fixed)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 60)
        self.table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        mapLayout.addWidget(self.table)

        hint = qt.QLabel(_("Dica: volume 3D com 0=fundo e cada canal vira um valor (canal 0->1, 1->2, ...). Segmentos no mesmo canal sao unidos com OR. Sobreposicao: canal menor tem prioridade."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 8pt;")
        mapLayout.addWidget(hint)

        self.exportButton = qt.QPushButton(_("Exportar .nii.gz"))
        self.exportButton.toolTip = _("Gera o NIfTI 3D labelmap (0=fundo, 1..N = canais) no caminho escolhido.")
        self.layout.addWidget(self.exportButton)

        self.statusLabel = qt.QLabel(_("Pronto."))
        self.statusLabel.setWordWrap(True)
        self.layout.addWidget(self.statusLabel)
        self.layout.addStretch(1)

        self.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSegmentationChanged)
        self.numChannelsSpin.connect("valueChanged(int)", self.onNumChannelsChanged)
        self.btnAuto.connect("clicked()", self.onAutoAssign)
        self.btnClear.connect("clicked()", self.onClearAssign)
        self.exportButton.connect("clicked()", self.onExportClicked)

        self.initializeParameterNode()
        self.onSegmentationChanged()

    def initializeParameterNode(self):
        node = self.logic.getParameterNode()
        if node is not self._paramNode:
            self._paramNode = node
        settings = qt.QSettings()
        folder = settings.value("MultiChannelSegmentationExporter/OutputPath", "")
        nch = settings.value("MultiChannelSegmentationExporter/NumChannels", "")
        if folder:
            self.outputPathSelector.currentPath = str(folder)
        if nch:
            try:
                self.numChannelsSpin.value = int(nch)
            except:  # noqa
                pass

    def _saveSettings(self):
        settings = qt.QSettings()
        settings.setValue("MultiChannelSegmentationExporter/OutputPath", self.outputPathSelector.currentPath)
        settings.setValue("MultiChannelSegmentationExporter/NumChannels", str(self.numChannelsSpin.value))
        node = self.logic.getParameterNode()
        node.SetParameter("OutputPath", self.outputPathSelector.currentPath)
        node.SetParameter("NumChannels", str(self.numChannelsSpin.value))
        cmap = self.currentChannelMap()
        node.SetParameter("ChannelMap", json.dumps(cmap))

    def onSegmentationChanged(self, *args, **kwargs):
        node = self.segmentationSelector.currentNode()
        if self._observedSegmentationNode is not None:
            self.removeObserver(self._observedSegmentationNode, vtk.vtkCommand.ModifiedEvent, self.refreshTable)
        self._observedSegmentationNode = node
        if node is not None:
            self.addObserver(node, vtk.vtkCommand.ModifiedEvent, self.refreshTable)
        self.refreshTable()

    def refreshTable(self, caller=None, event=None):
        if self._updatingTable:
            return
        self._updatingTable = True
        try:
            prevMap = {}
            for r in range(self.table.rowCount):
                segId = self._segmentIds[r] if r < len(self._segmentIds) else None
                w = self.table.cellWidget(r, 1)
                if segId and w:
                    prevMap[segId] = w.value

            node = self._observedSegmentationNode
            self.table.clearContents()
            self._segmentIds = []
            self._segmentNames = []
            if node is None:
                self.table.rowCount = 0
                return
            segmentation = node.GetSegmentation()
            n = segmentation.GetNumberOfSegments()
            self.table.rowCount = n
            for i in range(n):
                segId = segmentation.GetNthSegmentID(i)
                seg = segmentation.GetSegment(segId)
                name = seg.GetName() if seg else segId
                self._segmentIds.append(segId)
                self._segmentNames.append(name)

                item = qt.QTableWidgetItem(str(name))
                item.setFlags(item.flags() & ~qt.Qt.ItemIsEditable)
                self.table.setItem(i, 0, item)

                spin = qt.QSpinBox()
                spin.minimum = 0
                spin.maximum = max(0, self.numChannelsSpin.value - 1)
                spin.toolTip = _("Canal para este segmento")
                if segId in prevMap:
                    spin.value = max(0, min(spin.maximum, int(prevMap[segId])))
                else:
                    spin.value = min(i, spin.maximum) if n <= self.numChannelsSpin.value else 0
                self.table.setCellWidget(i, 1, spin)

                colorItem = qt.QTableWidgetItem("")
                c = seg.GetColor() if seg else (0.5, 0.5, 0.5)
                try:
                    r, g, b = [int(max(0, min(1, v)) * 255) for v in c[:3]]
                    colorItem.setBackground(qt.QColor(r, g, b))
                except:  # noqa
                    pass
                colorItem.setFlags(colorItem.flags() & ~qt.Qt.ItemIsEditable)
                self.table.setItem(i, 2, colorItem)

            self.table.resizeRowsToContents()
        finally:
            self._updatingTable = False

    def onNumChannelsChanged(self, value):
        for r in range(self.table.rowCount):
            w = self.table.cellWidget(r, 1)
            if w:
                w.maximum = max(0, value - 1)
                if w.value > w.maximum:
                    w.value = w.maximum

    def onAutoAssign(self):
        nch = self.numChannelsSpin.value
        for r in range(self.table.rowCount):
            w = self.table.cellWidget(r, 1)
            if w:
                w.value = r % nch if nch > 0 else 0

    def onClearAssign(self):
        for r in range(self.table.rowCount):
            w = self.table.cellWidget(r, 1)
            if w:
                w.value = 0

    def currentChannelMap(self):
        cmap = {}
        for r, segId in enumerate(self._segmentIds):
            w = self.table.cellWidget(r, 1)
            if w is not None:
                cmap[segId] = int(w.value)
        return cmap

    def onExportClicked(self):
        self.exportButton.enabled = False
        try:
            with slicer.util.tryWithErrorDisplay(_("Falha ao exportar multicanal."), waitCursor=True):
                self.doExport()
        finally:
            self.exportButton.enabled = True

    def doExport(self):
        segmentationNode = self.segmentationSelector.currentNode()
        referenceVolumeNode = self.referenceVolumeSelector.currentNode()
        outputPath = str(self.outputPathSelector.currentPath).strip()
        numChannels = int(self.numChannelsSpin.value)
        channelMap = self.currentChannelMap()

        if segmentationNode is None:
            raise ValueError(_("Selecione a segmentacao."))
        if not outputPath:
            raise ValueError(_("Escolha o arquivo de saida .nii.gz."))
        if numChannels < 1:
            raise ValueError(_("Numero de canais invalido."))
        if not channelMap:
            raise ValueError(_("Nenhum segmento para exportar."))
        for segId, ch in channelMap.items():
            if ch < 0 or ch >= numChannels:
                raise ValueError(_("Canal fora do intervalo para segmento {}: {}").format(segId, ch))

        outputPath = os.path.abspath(outputPath)
        if not outputPath.lower().endswith(".nii.gz") and not outputPath.lower().endswith(".nii"):
            outputPath += ".nii.gz"
        os.makedirs(os.path.dirname(outputPath) or ".", exist_ok=True)

        self.logic.exportMultichannel(
            segmentationNode, referenceVolumeNode, channelMap, numChannels, outputPath
        )
        self._saveSettings()
        self.statusLabel.setStyleSheet("color: #1e7b34; font-weight: bold;")
        self.statusLabel.setText(_("Exportado com sucesso ({} canais):\n{}").format(numChannels, outputPath))
        qt.QMessageBox.information(slicer.util.mainWindow(), _("Exportacao concluida"), _("Multicanal salvo em:\n{}\n\nCanais: {}\nMapeamento: {}").format(outputPath, numChannels, json.dumps(channelMap, ensure_ascii=False)))

    def cleanup(self):
        if self._observedSegmentationNode is not None:
            self.removeObserver(self._observedSegmentationNode, vtk.vtkCommand.ModifiedEvent, self.refreshTable)
            self._observedSegmentationNode = None
        self.removeObservers()


class MultiChannelSegmentationExporterLogic(ScriptedLoadableModuleLogic):

    def exportMultichannel(self, segmentationNode, referenceVolumeNode, segmentChannelMap, numChannels, outputPath):
        if segmentationNode is None:
            raise ValueError("Invalid segmentation node")
        if not segmentChannelMap:
            raise ValueError("Empty channel map")
        if numChannels < 1:
            raise ValueError("numChannels must be >=1")

        import numpy as np

        segmentation = segmentationNode.GetSegmentation()
        for segId, ch in segmentChannelMap.items():
            if not segmentation.GetSegment(segId):
                raise ValueError(_("Segmento nao encontrado: {}").format(segId))
            if ch < 0 or ch >= numChannels:
                raise ValueError(_("Canal {} fora do intervalo 0..{} para segmento {}").format(ch, numChannels - 1, segId))

        outputPath = os.path.abspath(outputPath)
        d = os.path.dirname(outputPath)
        if d:
            os.makedirs(d, exist_ok=True)

        hasNibabel = False
        try:
            import nibabel  # noqa
            hasNibabel = True
        except ImportError:
            hasNibabel = False

        hasSitk = False
        try:
            import SimpleITK  # noqa
            hasSitk = True
        except ImportError:
            hasSitk = False

        if not hasNibabel and not hasSitk:
            raise RuntimeError(_("Nem nibabel nem SimpleITK encontrados. Instale um deles: pip install nibabel  ou  pip install SimpleITK"))

        logic = slicer.modules.segmentations.logic()
        tempLabel = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
        slicer.mrmlScene.AddNode(tempLabel)
        tempLabel.SetName("_tmpMultichannelExport")

        channelArraysZYX = None
        ijkToRas = None

        try:
            for segId, ch in segmentChannelMap.items():
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

                if channelArraysZYX is None:
                    shape = volArray.shape
                    channelArraysZYX = [np.zeros(shape, dtype=np.uint8) for _ in range(numChannels)]

                if channelArraysZYX[0].shape != volArray.shape:
                    raise RuntimeError(_("Geometria inconsistente entre segmentos. Verifique o volume de referencia."))

                channelArraysZYX[ch] = np.logical_or(channelArraysZYX[ch], volArray).astype(np.uint8)

            if channelArraysZYX is None:
                raise RuntimeError(_("Nenhum dado gerado."))

            dtype = np.uint8 if numChannels < 255 else np.uint16
            labelZYX = np.zeros(channelArraysZYX[0].shape, dtype=dtype)
            for c in range(numChannels):
                m = channelArraysZYX[c].astype(bool)
                assign = np.logical_and(m, labelZYX == 0)
                labelZYX[assign] = c + 1

            dataXYZ = np.transpose(labelZYX, (2, 1, 0))

            if hasNibabel:
                import nibabel as nib

                img = nib.Nifti1Image(dataXYZ.astype(dtype), ijkToRas)
                img.header.set_data_dtype(dtype)
                nib.save(img, outputPath)
            else:
                import SimpleITK as sitk
                import sitkUtils

                tmp = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
                slicer.mrmlScene.AddNode(tmp)
                try:
                    slicer.util.updateVolumeFromArray(tmp, labelZYX)
                    tmp.CopyOrientation(referenceVolumeNode if referenceVolumeNode else tempLabel)
                    si = sitkUtils.PullVolumeFromSlicer(tmp)
                    sitk.WriteImage(si, outputPath)
                finally:
                    slicer.mrmlScene.RemoveNode(tmp)

        finally:
            slicer.mrmlScene.RemoveNode(tempLabel)

        logging.info("MultiChannel export: %s (%d canais)", outputPath, numChannels)
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


class MultiChannelSegmentationExporterTest(ScriptedLoadableModuleTest):

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_ExportMultichannel()

    def test_ExportMultichannel(self):
        self.delayDisplay("Starting multichannel export test")
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
        segNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        segNode.GetSegmentation().AddSegment(s1)
        segNode.GetSegmentation().AddSegment(s2)
        idA = segNode.GetSegmentation().GetNthSegmentID(0)
        idB = segNode.GetSegmentation().GetNthSegmentID(1)

        tmpDir = tempfile.mkdtemp()
        out = os.path.join(tmpDir, "multi.nii.gz")
        logic = MultiChannelSegmentationExporterLogic()
        logic.exportMultichannel(segNode, vol, {idA: 0, idB: 1}, 2, out)
        self.assertTrue(os.path.isfile(out))
        try:
            import nibabel as nib
            img = nib.load(out)
            data = img.get_fdata()
            self.assertEqual(data.shape, (8, 8, 8))
            self.assertEqual(int(data[2, 2, 2]), 1)
            self.assertEqual(int(data[5, 5, 5]), 2)
            self.assertEqual(int(data[0, 0, 0]), 0)
        except ImportError:
            self.assertTrue(os.path.getsize(out) > 0)
        shutil.rmtree(tmpDir, ignore_errors=True)
        self.delayDisplay("Multichannel test passed")
