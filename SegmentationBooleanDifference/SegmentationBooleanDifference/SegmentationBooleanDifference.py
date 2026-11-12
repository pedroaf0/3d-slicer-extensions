import logging
import traceback

import ctk
import qt
import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

import qMRMLWidgetsPythonQt


class SegmentationBooleanDifference(ScriptedLoadableModule):

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Diferenca Booleana (A \\ B)")
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Pedro (Developer)"]
        self.parent.helpText = _(
            """Remove do segmento <b>A</b> os voxels que pertencem ao segmento <b>B</b> (A \\ B).
A e B podem ser de segmentacoes diferentes. Escolha tambem um volume de referencia para alinhar as geometrias; se vazio, usa a geometria da segmentacao A.
Operacao e feita em labelmap binario alinhado e o resultado volta para o segmento A (ou cria um novo)."""
        )
        self.parent.acknowledgementText = ""


class SegmentationBooleanDifferenceWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._segAIds = []
        self._segBIds = []
        self._obsA = None
        self._obsB = None
        self._lastCreateNew = False

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        try:
            self._buildUi()
        except Exception:
            traceback.print_exc()
            slicer.util.errorDisplay(_("Nao foi possivel criar a interface.\n") + traceback.format_exc())

    def _buildUi(self):
        self.logic = SegmentationBooleanDifferenceLogic()

        ioBox = ctk.ctkCollapsibleButton()
        ioBox.text = _("Segmentos")
        ioBox.collapsed = False
        self.layout.addWidget(ioBox)
        ioForm = qt.QFormLayout(ioBox)

        self.segANodeSelector = qMRMLWidgetsPythonQt.qMRMLNodeComboBox()
        self.segANodeSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
        self.segANodeSelector.baseName = "Segmentacao A"
        self.segANodeSelector.setMRMLScene(slicer.mrmlScene)
        self.segANodeSelector.toolTip = _("Segmentacao que contem o segmento A (minuendo).")
        ioForm.addRow(_("Segmentacao A:"), self.segANodeSelector)

        self.segACombo = qt.QComboBox()
        self.segACombo.toolTip = _("Segmento A: dele serao removidos os voxels de B.")
        ioForm.addRow(_("Segmento A:"), self.segACombo)

        self.allACheck = qt.QCheckBox(_("Usar todos os segmentos de A (uniao)"))
        self.allACheck.checked = False
        self.allACheck.toolTip = _("Se marcado, usa a uniao de todos os segmentos da segmentacao A como minuendo. Ignora a selecao de Segmento A.")
        ioForm.addRow("", self.allACheck)

        self.segBNodeSelector = qMRMLWidgetsPythonQt.qMRMLNodeComboBox()
        self.segBNodeSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
        self.segBNodeSelector.baseName = "Segmentacao B"
        self.segBNodeSelector.setMRMLScene(slicer.mrmlScene)
        self.segBNodeSelector.toolTip = _("Segmentacao que contem o segmento B (subtraendo). Pode ser a mesma de A ou diferente.")
        ioForm.addRow(_("Segmentacao B:"), self.segBNodeSelector)

        self.segBCombo = qt.QComboBox()
        self.segBCombo.toolTip = _("Segmento B: seus voxels serao removidos de A.")
        ioForm.addRow(_("Segmento B:"), self.segBCombo)

        self.allBCheck = qt.QCheckBox(_("Usar todos os segmentos de B (uniao)"))
        self.allBCheck.checked = False
        self.allBCheck.toolTip = _("Se marcado, usa a uniao de todos os segmentos da segmentacao B como subtraendo. Ignora a selecao de Segmento B.")
        ioForm.addRow("", self.allBCheck)

        self.refVolumeSelector = qMRMLWidgetsPythonQt.qMRMLNodeComboBox()
        self.refVolumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode", "vtkMRMLLabelMapVolumeNode"]
        self.refVolumeSelector.baseName = "Volume referencia"
        self.refVolumeSelector.noneEnabled = True
        self.refVolumeSelector.addEnabled = False
        self.refVolumeSelector.removeEnabled = False
        self.refVolumeSelector.setMRMLScene(slicer.mrmlScene)
        self.refVolumeSelector.toolTip = _("Geometria de referencia (origem/espacamento/dimensoes). Se vazio, usa a geometria da segmentacao A.")
        ioForm.addRow(_("Volume referencia:"), self.refVolumeSelector)

        optsBox = ctk.ctkCollapsibleButton()
        optsBox.text = _("Opcoes")
        optsBox.collapsed = False
        self.layout.addWidget(optsBox)
        optsForm = qt.QFormLayout(optsBox)

        self.createNewCheck = qt.QCheckBox(_("Criar novo segmento com resultado (em vez de sobrescrever A)"))
        self.createNewCheck.checked = False
        self.createNewCheck.toolTip = _("Se marcado, cria um novo segmento 'A_minus_B' na segmentacao A. Se desmarcado, sobrescreve o segmento A.")
        optsForm.addRow(self.createNewCheck)

        self.newNameEdit = qt.QLineEdit()
        self.newNameEdit.placeholderText = _("Nome do novo segmento (opcional)")
        self.newNameEdit.toolTip = _("Se vazio, usa '<A> minus <B>'.")
        self.newNameEdit.enabled = False
        optsForm.addRow(_("Nome novo:"), self.newNameEdit)

        self.undoCheck = qt.QCheckBox(_("Salvar estado para desfazer (undo)"))
        self.undoCheck.checked = True
        optsForm.addRow(self.undoCheck)

        btnRow = qt.QHBoxLayout()
        self.swapButton = qt.QPushButton(_("⇄ Inverter A/B"))
        self.swapButton.toolTip = _("Troca A e B (segmentacoes e segmentos). Vira B \\ A.")
        btnRow.addWidget(self.swapButton)
        self.undoButton = qt.QPushButton(_("⎌ Desfazer"))
        self.undoButton.toolTip = _("Desfaz a ultima operacao A \\ B (restaura o segmento A ou remove o segmento criado).")
        btnRow.addWidget(self.undoButton)
        self.layout.addLayout(btnRow)

        self.subtractButton = qt.QPushButton(_("Subtrair B de A  (A \\ B)"))
        self.subtractButton.toolTip = _("Executa A = A AND NOT B (voxel a voxel, geometria alinhada).")
        self.layout.addWidget(self.subtractButton)

        self.statusLabel = qt.QLabel(_("Pronto."))
        self.statusLabel.setWordWrap(True)
        self.layout.addWidget(self.statusLabel)
        self.layout.addStretch(1)

        self.segANodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSegANodeChanged)
        self.segBNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSegBNodeChanged)
        self.allACheck.connect("toggled(bool)", self._onAllAToggled)
        self.allBCheck.connect("toggled(bool)", self._onAllBToggled)
        self.createNewCheck.connect("toggled(bool)", lambda v: setattr(self.newNameEdit, "enabled", bool(v)))
        self.swapButton.connect("clicked()", self.onSwapClicked)
        self.undoButton.connect("clicked()", self.onUndoClicked)
        self.subtractButton.connect("clicked()", self.onSubtractClicked)

        self.onSegANodeChanged()
        self.onSegBNodeChanged()
        self._undoBackup = None
        self._refreshUndoButton()

    def _fillCombo(self, combo, segmentationNode, idList):
        combo.blockSignals(True)
        combo.clear()
        idList.clear()
        if segmentationNode is None:
            combo.blockSignals(False)
            return
        seg = segmentationNode.GetSegmentation()
        if not seg:
            combo.blockSignals(False)
            return
        for i in range(seg.GetNumberOfSegments()):
            sid = seg.GetNthSegmentID(i)
            s = seg.GetSegment(sid)
            name = s.GetName() if s and s.GetName() else sid
            combo.addItem(str(name), sid)
            idList.append(sid)
        combo.blockSignals(False)

    def onSegANodeChanged(self, *args, **kwargs):
        node = self.segANodeSelector.currentNode()
        if self._obsA is not None:
            self.removeObserver(self._obsA, vtk.vtkCommand.ModifiedEvent, self._refreshA)
        self._obsA = node
        if node is not None:
            self.addObserver(node, vtk.vtkCommand.ModifiedEvent, self._refreshA)
        self._refreshA()

    def onSegBNodeChanged(self, *args, **kwargs):
        node = self.segBNodeSelector.currentNode()
        if self._obsB is not None:
            self.removeObserver(self._obsB, vtk.vtkCommand.ModifiedEvent, self._refreshB)
        self._obsB = node
        if node is not None:
            self.addObserver(node, vtk.vtkCommand.ModifiedEvent, self._refreshB)
        self._refreshB()

    def _refreshA(self, caller=None, event=None):
        prev = self.segACombo.currentData if self.segACombo.count else None
        self._fillCombo(self.segACombo, self._obsA, self._segAIds)
        if prev:
            idx = self.segACombo.findData(prev)
            if idx >= 0:
                self.segACombo.setCurrentIndex(idx)

    def _onAllAToggled(self, checked):
        self.segACombo.enabled = not bool(checked)

    def _onAllBToggled(self, checked):
        self.segBCombo.enabled = not bool(checked)

    def _refreshB(self, caller=None, event=None):
        prev = self.segBCombo.currentData if self.segBCombo.count else None
        self._fillCombo(self.segBCombo, self._obsB, self._segBIds)
        if prev:
            idx = self.segBCombo.findData(prev)
            if idx >= 0:
                self.segBCombo.setCurrentIndex(idx)

    def _getSegmentArray(self, segNode, segId, refVol):
        tmp = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
        slicer.mrmlScene.AddNode(tmp)
        tmp.SetName("_tmpUndoCapture")
        try:
            arr = vtk.vtkStringArray()
            arr.InsertNextValue(segId)
            if not slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(segNode, arr, tmp, refVol):
                return None, None
            a = slicer.util.arrayFromVolume(tmp)
            if a is None:
                return None, None
            import numpy as np
            return (a > 0).astype(np.uint8).copy(), tmp.GetImageData() and tmp.GetImageData() or tmp
        finally:
            slicer.mrmlScene.RemoveNode(tmp)

    def _refreshUndoButton(self):
        has = self._undoBackup is not None
        try:
            self.undoButton.enabled = bool(has)
        except:  # noqa
            pass

    def onSwapClicked(self):
        aNode = self.segANodeSelector.currentNode()
        bNode = self.segBNodeSelector.currentNode()
        aData = self.segACombo.currentData if self.segACombo.count else None
        bData = self.segBCombo.currentData if self.segBCombo.count else None
        aAll = bool(self.allACheck.checked)
        bAll = bool(self.allBCheck.checked)
        self.segANodeSelector.setCurrentNode(bNode)
        self.segBNodeSelector.setCurrentNode(aNode)
        qt.QTimer.singleShot(0, lambda: self._swapComboSelections(aData, bData, aAll, bAll))

    def _swapComboSelections(self, aData, bData, aAll=False, bAll=False):
        if aData is not None:
            idx = self.segBCombo.findData(aData)
            if idx >= 0:
                self.segBCombo.setCurrentIndex(idx)
        if bData is not None:
            idx = self.segACombo.findData(bData)
            if idx >= 0:
                self.segACombo.setCurrentIndex(idx)
        self.allACheck.checked = bool(bAll)
        self.allBCheck.checked = bool(aAll)

    def onUndoClicked(self):
        if self._undoBackup is None:
            slicer.util.warningDisplay(_("Nada para desfazer."))
            return
        try:
            with slicer.util.tryWithErrorDisplay(_("Falha ao desfazer."), waitCursor=True):
                self._doUndo()
        except Exception as e:
            traceback.print_exc()
            slicer.util.errorDisplay(str(e))

    def _doUndo(self):
        b = self._undoBackup
        segANode = slicer.mrmlScene.GetNodeByID(b["segANodeID"]) if b.get("segANodeID") else self.segANodeSelector.currentNode()
        if segANode is None or segANode.GetSegmentation() is None:
            raise RuntimeError(_("Segmentacao A nao encontrada para desfazer."))
        refVol = slicer.mrmlScene.GetNodeByID(b["refVolID"]) if b.get("refVolID") else self.refVolumeSelector.currentNode()
        if b.get("createNew"):
            before = set(b.get("beforeIds") or [])
            curIds = set(segANode.GetSegmentation().GetNthSegmentID(i) for i in range(segANode.GetSegmentation().GetNumberOfSegments()))
            newIds = list(curIds - before)
            # fallback: try by name if ids changed
            if not newIds and b.get("newName"):
                seg = segANode.GetSegmentation().GetSegment(b["newName"])
                if seg is not None:
                    newIds = [b["newName"]]
            for nid in newIds:
                try:
                    segANode.GetSegmentation().RemoveSegment(nid)
                except:  # noqa
                    pass
            self._undoBackup = None
            self._refreshUndoButton()
            self.statusLabel.setStyleSheet("color: #1e7b34; font-weight: bold;")
            self.statusLabel.setText(_("Desfeito: segmento(s) criado(s) removido(s): {}").format(", ".join(newIds) if newIds else _("(nenhum)")))
            return
        else:
            if b.get("multi"):
                segAIds = b.get("segAIds") or []
                arrays = b.get("arrays") or {}
                if not segAIds:
                    raise RuntimeError(_("Sem backup multi-segmento."))
                for sid in segAIds:
                    arr = arrays.get(sid)
                    if arr is None:
                        try:
                            slicer.mrmlScene.Undo()
                        except:  # noqa
                            pass
                        continue
                    refForUpdate = refVol
                    if refForUpdate is None:
                        tmp = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
                        slicer.mrmlScene.AddNode(tmp)
                        try:
                            ta = vtk.vtkStringArray()
                            ta.InsertNextValue(sid)
                            slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(segANode, ta, tmp, None)
                            refForUpdate = tmp
                            if hasattr(slicer.util, "updateSegmentBinaryLabelmapFromArray"):
                                slicer.util.updateSegmentBinaryLabelmapFromArray(arr, segANode, sid, refForUpdate)
                            else:
                                slicer.util.updateVolumeFromArray(tmp, arr)
                                seg = self.logic._createSegmentFromLabelmapNodeCompat(slicer.modules.segmentations.logic(), tmp)
                                try:
                                    segANode.GetSegmentation().RemoveSegment(sid)
                                except:  # noqa
                                    pass
                                try:
                                    segANode.GetSegmentation().AddSegment(seg, sid)
                                except TypeError:
                                    segANode.GetSegmentation().AddSegment(seg)
                        finally:
                            slicer.mrmlScene.RemoveNode(tmp)
                    else:
                        if hasattr(slicer.util, "updateSegmentBinaryLabelmapFromArray"):
                            slicer.util.updateSegmentBinaryLabelmapFromArray(arr, segANode, sid, refForUpdate)
                        else:
                            tmp2 = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
                            slicer.mrmlScene.AddNode(tmp2)
                            try:
                                slicer.util.updateVolumeFromArray(tmp2, arr)
                                tmp2.CopyOrientation(refForUpdate)
                                seg = self.logic._createSegmentFromLabelmapNodeCompat(slicer.modules.segmentations.logic(), tmp2)
                                try:
                                    segANode.GetSegmentation().RemoveSegment(sid)
                                except:  # noqa
                                    pass
                                try:
                                    segANode.GetSegmentation().AddSegment(seg, sid)
                                except TypeError:
                                    segANode.GetSegmentation().AddSegment(seg)
                            finally:
                                slicer.mrmlScene.RemoveNode(tmp2)
                self._undoBackup = None
                self._refreshUndoButton()
                self.statusLabel.setStyleSheet("color: #1e7b34; font-weight: bold;")
                self.statusLabel.setText(_("Desfeito: {} segmentos de A restaurados.").format(len(segAIds)))
                return
            segAId = b["segAId"]
            arr = b.get("array")
            if arr is None:
                # fallback: slicer global undo
                try:
                    slicer.mrmlScene.Undo()
                    self.statusLabel.setText(_("Desfeito via undo global."))
                    self._undoBackup = None
                    self._refreshUndoButton()
                    return
                except:  # noqa
                    raise RuntimeError(_("Sem backup para restaurar."))
            refForUpdate = refVol
            if refForUpdate is None:
                tmp = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
                slicer.mrmlScene.AddNode(tmp)
                try:
                    ta = vtk.vtkStringArray()
                    ta.InsertNextValue(segAId)
                    slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(segANode, ta, tmp, None)
                    refForUpdate = tmp
                    if hasattr(slicer.util, "updateSegmentBinaryLabelmapFromArray"):
                        slicer.util.updateSegmentBinaryLabelmapFromArray(arr, segANode, segAId, refForUpdate)
                    else:
                        slicer.util.updateVolumeFromArray(tmp, arr)
                        seg = self.logic._createSegmentFromLabelmapNodeCompat(slicer.modules.segmentations.logic(), tmp)
                        try:
                            segANode.GetSegmentation().RemoveSegment(segAId)
                        except:  # noqa
                            pass
                        try:
                            org = segANode.GetSegmentation().GetSegment(segAId)
                            if org is not None:
                                seg.SetName(org.GetName())
                                seg.SetColor(org.GetColor())
                        except:  # noqa
                            pass
                        try:
                            segANode.GetSegmentation().AddSegment(seg, segAId)
                        except TypeError:
                            segANode.GetSegmentation().AddSegment(seg)
                finally:
                    slicer.mrmlScene.RemoveNode(tmp)
            else:
                if hasattr(slicer.util, "updateSegmentBinaryLabelmapFromArray"):
                    slicer.util.updateSegmentBinaryLabelmapFromArray(arr, segANode, segAId, refForUpdate)
                else:
                    tmp2 = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
                    slicer.mrmlScene.AddNode(tmp2)
                    try:
                        slicer.util.updateVolumeFromArray(tmp2, arr)
                        tmp2.CopyOrientation(refForUpdate)
                        seg = self.logic._createSegmentFromLabelmapNodeCompat(slicer.modules.segmentations.logic(), tmp2)
                        try:
                            segANode.GetSegmentation().RemoveSegment(segAId)
                        except:  # noqa
                            pass
                        try:
                            segANode.GetSegmentation().AddSegment(seg, segAId)
                        except TypeError:
                            segANode.GetSegmentation().AddSegment(seg)
                    finally:
                        slicer.mrmlScene.RemoveNode(tmp2)
            self._undoBackup = None
            self._refreshUndoButton()
            self.statusLabel.setStyleSheet("color: #1e7b34; font-weight: bold;")
            self.statusLabel.setText(_("Desfeito: segmento A restaurado ({} voxels).").format(int(arr.sum()) if hasattr(arr, "sum") else "?"))

    def onSubtractClicked(self):
        self.subtractButton.enabled = False
        try:
            with slicer.util.tryWithErrorDisplay(_("Falha na diferenca booleana."), waitCursor=True):
                self.doSubtract()
        finally:
            self.subtractButton.enabled = True

    def _getAllSegmentIds(self, segNode):
        if segNode is None or segNode.GetSegmentation() is None:
            return []
        seg = segNode.GetSegmentation()
        return [seg.GetNthSegmentID(i) for i in range(seg.GetNumberOfSegments())]

    def _getSegmentArrayUnion(self, segNode, segIds, refVol):
        if not segIds:
            return None, None
        if len(segIds) == 1:
            return self._getSegmentArray(segNode, segIds[0], refVol)
        tmp = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
        slicer.mrmlScene.AddNode(tmp)
        tmp.SetName("_tmpUndoCaptureUnion")
        try:
            arr = vtk.vtkStringArray()
            for sid in segIds:
                arr.InsertNextValue(sid)
            if not slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(segNode, arr, tmp, refVol):
                return None, None
            a = slicer.util.arrayFromVolume(tmp)
            if a is None:
                return None, None
            import numpy as np
            return (a > 0).astype(np.uint8).copy(), tmp.GetImageData() and tmp.GetImageData() or tmp
        finally:
            slicer.mrmlScene.RemoveNode(tmp)

    def doSubtract(self):
        segANode = self.segANodeSelector.currentNode()
        segBNode = self.segBNodeSelector.currentNode()
        useAllA = bool(self.allACheck.checked)
        useAllB = bool(self.allBCheck.checked)
        segAId = self.segACombo.currentData if self.segACombo.count else None
        segBId = self.segBCombo.currentData if self.segBCombo.count else None
        refVol = self.refVolumeSelector.currentNode()

        if segANode is None:
            raise ValueError(_("Selecione a segmentacao A."))
        if segBNode is None:
            raise ValueError(_("Selecione a segmentacao B."))
        if useAllA:
            segAIds = self._getAllSegmentIds(segANode)
            if not segAIds:
                raise ValueError(_("Segmentacao A nao tem segmentos."))
        else:
            if not segAId:
                raise ValueError(_("Selecione o segmento A ou marque 'todos os segmentos de A'."))
            segAIds = [segAId]
        if useAllB:
            segBIds = self._getAllSegmentIds(segBNode)
            if not segBIds:
                raise ValueError(_("Segmentacao B nao tem segmentos."))
        else:
            if not segBId:
                raise ValueError(_("Selecione o segmento B ou marque 'todos os segmentos de B'."))
            segBIds = [segBId]

        createNew = bool(self.createNewCheck.checked)
        newName = self.newNameEdit.text.strip() if createNew else ""
        saveUndo = bool(self.undoCheck.checked)

        beforeIds = None
        backupArray = None
        backupArrays = None
        if saveUndo:
            if createNew:
                try:
                    beforeIds = [segANode.GetSegmentation().GetNthSegmentID(i) for i in range(segANode.GetSegmentation().GetNumberOfSegments())]
                except:  # noqa
                    beforeIds = []
            else:
                if useAllA:
                    backupArrays = {}
                    for sid in segAIds:
                        try:
                            arr, _ = self._getSegmentArray(segANode, sid, refVol)
                            backupArrays[sid] = arr
                        except:  # noqa
                            backupArrays[sid] = None
                else:
                    try:
                        backupArray, _ = self._getSegmentArray(segANode, segAId, refVol)
                    except:  # noqa
                        backupArray = None

        aArg = segAIds if useAllA else segAId
        bArg = segBIds if useAllB else segBId
        removed, kept, totalA = self.logic.subtract(
            segANode, aArg, segBNode, bArg, refVol,
            createNewSegment=createNew, newSegmentName=newName, saveUndoState=saveUndo
        )
        if saveUndo:
            if createNew:
                curIds = []
                try:
                    curIds = [segANode.GetSegmentation().GetNthSegmentID(i) for i in range(segANode.GetSegmentation().GetNumberOfSegments())]
                except:  # noqa
                    pass
                newIds = [x for x in curIds if x not in (beforeIds or [])]
                deducedName = newName
                if not deducedName:
                    try:
                        if newIds:
                            deducedName = segANode.GetSegmentation().GetSegment(newIds[0]).GetName()
                    except:  # noqa
                        pass
                self._undoBackup = {"segANodeID": segANode.GetID(), "createNew": True, "beforeIds": beforeIds, "newName": deducedName, "refVolID": refVol.GetID() if refVol else None}
            else:
                if useAllA:
                    self._undoBackup = {"segANodeID": segANode.GetID(), "segAIds": segAIds, "arrays": backupArrays, "createNew": False, "multi": True, "refVolID": refVol.GetID() if refVol else None}
                else:
                    self._undoBackup = {"segANodeID": segANode.GetID(), "segAId": segAId, "array": backupArray, "createNew": False, "refVolID": refVol.GetID() if refVol else None}
            self._lastCreateNew = createNew
            self._refreshUndoButton()
        self.statusLabel.setStyleSheet("color: #1e7b34; font-weight: bold;")
        self.statusLabel.setText(_("Concluido: A tinha {} voxels, removidos {} (sobreposicao), restaram {}").format(totalA, removed, kept))
        qt.QMessageBox.information(slicer.util.mainWindow(), _("Diferenca concluida"),
                                   _("A \\ B concluido.\n\nA: {} voxels\nRemovidos: {}\nRestaram: {}").format(totalA, removed, kept))

    def cleanup(self):
        if self._obsA is not None:
            self.removeObserver(self._obsA, vtk.vtkCommand.ModifiedEvent, self._refreshA)
            self._obsA = None
        if self._obsB is not None:
            self.removeObserver(self._obsB, vtk.vtkCommand.ModifiedEvent, self._refreshB)
            self._obsB = None
        self.removeObservers()


class SegmentationBooleanDifferenceLogic(ScriptedLoadableModuleLogic):

    def _createSegmentFromLabelmapNodeCompat(self, logic, labelmapNode):
        if hasattr(logic, "CreateSegmentFromLabelmapNode"):
            return logic.CreateSegmentFromLabelmapNode(labelmapNode)
        tmpSeg = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentationNode")
        slicer.mrmlScene.AddNode(tmpSeg)
        try:
            logic.ImportLabelmapToSegmentationNode(labelmapNode, tmpSeg)
            if tmpSeg.GetSegmentation().GetNumberOfSegments() == 0:
                raise RuntimeError(_("Falha ao criar segmento a partir do labelmap (compat)."))
            sid = tmpSeg.GetSegmentation().GetNthSegmentID(0)
            src = tmpSeg.GetSegmentation().GetSegment(sid)
            seg = slicer.vtkSegment()
            seg.DeepCopy(src)
            return seg
        finally:
            slicer.mrmlScene.RemoveNode(tmpSeg)

    def subtract(self, segANode, segAId, segBNode, segBId, referenceVolumeNode=None,
                 createNewSegment=False, newSegmentName="", saveUndoState=True):
        aIds = segAId if isinstance(segAId, (list, tuple)) else ([segAId] if segAId else [])
        bIds = segBId if isinstance(segBId, (list, tuple)) else ([segBId] if segBId else [])
        if not segANode or not aIds:
            raise ValueError("Invalid segment A")
        if not segBNode or not bIds:
            raise ValueError("Invalid segment B")
        for sid in aIds:
            if not segANode.GetSegmentation().GetSegment(sid):
                raise ValueError(_("Segmento A nao encontrado: {}").format(sid))
        for sid in bIds:
            if not segBNode.GetSegmentation().GetSegment(sid):
                raise ValueError(_("Segmento B nao encontrado: {}").format(sid))

        import numpy as np

        logic = slicer.modules.segmentations.logic()

        tmpA = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
        slicer.mrmlScene.AddNode(tmpA)
        tmpA.SetName("_tmpBoolDiff_A")
        tmpB = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
        slicer.mrmlScene.AddNode(tmpB)
        tmpB.SetName("_tmpBoolDiff_B")

        try:
            arrA = vtk.vtkStringArray()
            for sid in aIds:
                arrA.InsertNextValue(sid)
            if not logic.ExportSegmentsToLabelmapNode(segANode, arrA, tmpA, referenceVolumeNode):
                raise RuntimeError(_("Falha ao converter segmento A para labelmap."))

            arrB = vtk.vtkStringArray()
            for sid in bIds:
                arrB.InsertNextValue(sid)
            if not logic.ExportSegmentsToLabelmapNode(segBNode, arrB, tmpB, referenceVolumeNode):
                raise RuntimeError(_("Falha ao converter segmento B para labelmap."))

            aZYX = slicer.util.arrayFromVolume(tmpA)
            bZYX = slicer.util.arrayFromVolume(tmpB)
            if aZYX is None or bZYX is None:
                raise RuntimeError(_("Nao foi possivel ler labelmaps temporarios."))

            if aZYX.shape != bZYX.shape:
                raise RuntimeError(_("Geometrias de A e B divergiram (shapes {} vs {}). Escolha um volume de referencia comum.").format(aZYX.shape, bZYX.shape))

            aBin = aZYX > 0
            bBin = bZYX > 0

            if saveUndoState:
                try:
                    segANode.GetSegmentation().SetConversionParameter("SaveUndoState", "1")
                except:  # noqa
                    pass
                try:
                    slicer.mrmlScene.SaveStateForUndo(segANode)
                except:  # noqa
                    pass

            refForUpdate = referenceVolumeNode if referenceVolumeNode is not None else tmpA

            if createNewSegment:
                totalA = int(np.count_nonzero(aBin))
                overlap = int(np.count_nonzero(np.logical_and(aBin, bBin)))
                result = np.logical_and(aBin, np.logical_not(bBin)).astype(np.uint8)
                kept = int(np.count_nonzero(result))
                segA0 = segANode.GetSegmentation().GetSegment(aIds[0]) if aIds else None
                segB0 = segBNode.GetSegmentation().GetSegment(bIds[0]) if bIds else None
                if newSegmentName and newSegmentName.strip():
                    baseName = newSegmentName.strip()
                else:
                    if len(aIds) > 1 or len(bIds) > 1:
                        aName = segANode.GetName() if segANode.GetName() else "A"
                        bName = segBNode.GetName() if segBNode.GetName() else "B"
                        if len(aIds) == 1 and segA0 and segA0.GetName():
                            aName = segA0.GetName()
                        if len(bIds) == 1 and segB0 and segB0.GetName():
                            bName = segB0.GetName()
                        aLabel = "{} ({} segs)".format(aName, len(aIds)) if len(aIds) > 1 else aName
                        bLabel = "{} ({} segs)".format(bName, len(bIds)) if len(bIds) > 1 else bName
                        baseName = "{} minus {}".format(aLabel, bLabel)
                    else:
                        baseName = "{} minus {}".format(
                            segA0.GetName() if segA0 and segA0.GetName() else aIds[0],
                            segB0.GetName() if segB0 and segB0.GetName() else bIds[0]
                        )
                if hasattr(slicer.util, "updateSegmentBinaryLabelmapFromArray"):
                    try:
                        newId = segANode.GetSegmentation().GenerateUniqueSegmentID(baseName.replace(" ", "_")[:30])
                    except:  # noqa
                        newId = baseName
                    try:
                        segANode.GetSegmentation().AddEmptySegment(newId)
                    except:  # noqa
                        segANode.GetSegmentation().AddEmptySegment(newId, baseName, [1, 0, 0])
                    newSeg = segANode.GetSegmentation().GetSegment(newId)
                    if newSeg is not None:
                        try:
                            newSeg.SetName(baseName)
                        except:  # noqa
                            pass
                        if segA0 is not None:
                            try:
                                newSeg.SetColor(segA0.GetColor())
                            except:  # noqa
                                pass
                        slicer.util.updateSegmentBinaryLabelmapFromArray(result, segANode, newId, refForUpdate)
                else:
                    resultNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
                    slicer.mrmlScene.AddNode(resultNode)
                    resultNode.SetName("_tmpBoolDiff_Result")
                    try:
                        slicer.util.updateVolumeFromArray(resultNode, result)
                        resultNode.CopyOrientation(tmpA)
                        newSeg = self._createSegmentFromLabelmapNodeCompat(logic, resultNode)
                        newSeg.SetName(baseName)
                        if segA0 is not None:
                            try:
                                newSeg.SetColor(segA0.GetColor())
                            except:  # noqa
                                pass
                        segANode.GetSegmentation().AddSegment(newSeg)
                    finally:
                        slicer.mrmlScene.RemoveNode(resultNode)
                logging.info("Boolean difference: A=%d overlap=%d kept=%d -> %s", totalA, overlap, kept, "new segment")
                return overlap, kept, totalA
            else:
                if len(aIds) == 1:
                    totalA = int(np.count_nonzero(aBin))
                    overlap = int(np.count_nonzero(np.logical_and(aBin, bBin)))
                    result = np.logical_and(aBin, np.logical_not(bBin)).astype(np.uint8)
                    kept = int(np.count_nonzero(result))
                    sid = aIds[0]
                    if hasattr(slicer.util, "updateSegmentBinaryLabelmapFromArray"):
                        slicer.util.updateSegmentBinaryLabelmapFromArray(result, segANode, sid, refForUpdate)
                    else:
                        slicer.util.updateVolumeFromArray(tmpA, result)
                        seg = self._createSegmentFromLabelmapNodeCompat(logic, tmpA)
                        origSeg = segANode.GetSegmentation().GetSegment(sid)
                        name = origSeg.GetName() if origSeg and origSeg.GetName() else sid
                        color = origSeg.GetColor() if origSeg else None
                        if origSeg is not None:
                            try:
                                seg.SetColor(color)
                                seg.SetName(name)
                            except:  # noqa
                                pass
                        try:
                            segANode.GetSegmentation().RemoveSegment(sid)
                        except:  # noqa
                            pass
                        try:
                            segANode.GetSegmentation().AddSegment(seg, sid)
                        except TypeError:
                            segANode.GetSegmentation().AddSegment(seg)
                    logging.info("Boolean difference: A=%d overlap=%d kept=%d -> %s", totalA, overlap, kept, "overwrite A")
                    return overlap, kept, totalA
                else:
                    totalA_sum = 0
                    overlap_sum = 0
                    kept_sum = 0
                    for sid in aIds:
                        tmpSingle = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
                        slicer.mrmlScene.AddNode(tmpSingle)
                        tmpSingle.SetName("_tmpBoolDiff_A_single")
                        try:
                            sa = vtk.vtkStringArray()
                            sa.InsertNextValue(sid)
                            if not logic.ExportSegmentsToLabelmapNode(segANode, sa, tmpSingle, referenceVolumeNode):
                                raise RuntimeError(_("Falha ao converter segmento A '{}' para labelmap.").format(sid))
                            aSingle = slicer.util.arrayFromVolume(tmpSingle)
                            if aSingle is None:
                                raise RuntimeError(_("Nao foi possivel ler labelmap de A '{}'.").format(sid))
                            if aSingle.shape != bBin.shape:
                                raise RuntimeError(_("Geometrias divergiram para '{}' (shapes {} vs {}).").format(sid, aSingle.shape, bBin.shape))
                            aSingleBin = aSingle > 0
                            totalA_i = int(np.count_nonzero(aSingleBin))
                            overlap_i = int(np.count_nonzero(np.logical_and(aSingleBin, bBin)))
                            result_i = np.logical_and(aSingleBin, np.logical_not(bBin)).astype(np.uint8)
                            kept_i = int(np.count_nonzero(result_i))
                            totalA_sum += totalA_i
                            overlap_sum += overlap_i
                            kept_sum += kept_i
                            refSingle = referenceVolumeNode if referenceVolumeNode is not None else tmpSingle
                            if hasattr(slicer.util, "updateSegmentBinaryLabelmapFromArray"):
                                slicer.util.updateSegmentBinaryLabelmapFromArray(result_i, segANode, sid, refSingle)
                            else:
                                slicer.util.updateVolumeFromArray(tmpSingle, result_i)
                                seg = self._createSegmentFromLabelmapNodeCompat(logic, tmpSingle)
                                origSeg = segANode.GetSegmentation().GetSegment(sid)
                                name = origSeg.GetName() if origSeg and origSeg.GetName() else sid
                                color = origSeg.GetColor() if origSeg else None
                                if origSeg is not None:
                                    try:
                                        seg.SetColor(color)
                                        seg.SetName(name)
                                    except:  # noqa
                                        pass
                                try:
                                    segANode.GetSegmentation().RemoveSegment(sid)
                                except:  # noqa
                                    pass
                                try:
                                    segANode.GetSegmentation().AddSegment(seg, sid)
                                except TypeError:
                                    segANode.GetSegmentation().AddSegment(seg)
                        finally:
                            slicer.mrmlScene.RemoveNode(tmpSingle)
                    logging.info("Boolean difference multi-A: A=%d overlap=%d kept=%d -> %s", totalA_sum, overlap_sum, kept_sum, "overwrite A (per-segment)")
                    return overlap_sum, kept_sum, totalA_sum

        finally:
            slicer.mrmlScene.RemoveNode(tmpA)
            slicer.mrmlScene.RemoveNode(tmpB)


class SegmentationBooleanDifferenceTest(ScriptedLoadableModuleTest):

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_Subtract()

    def test_Subtract(self):
        self.delayDisplay("Starting boolean difference test")
        import numpy as np

        vol = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        slicer.util.updateVolumeFromArray(vol, np.zeros((8, 8, 8), dtype=np.int16))

        def _makeSegNode(pos, name, nodeName):
            ln = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
            a = np.zeros((8, 8, 8), dtype=np.uint8)
            for p in pos:
                a[p] = 1
            slicer.util.updateVolumeFromArray(ln, a)
            logicTmp = slicer.modules.segmentations.logic()
            if hasattr(logicTmp, "CreateSegmentFromLabelmapNode"):
                seg = logicTmp.CreateSegmentFromLabelmapNode(ln)
            else:
                tmpSeg = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentationNode")
                slicer.mrmlScene.AddNode(tmpSeg)
                logicTmp.ImportLabelmapToSegmentationNode(ln, tmpSeg)
                src = tmpSeg.GetSegmentation().GetSegment(tmpSeg.GetSegmentation().GetNthSegmentID(0))
                seg = slicer.vtkSegment()
                seg.DeepCopy(src)
                slicer.mrmlScene.RemoveNode(tmpSeg)
            seg.SetName(name)
            sn = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            sn.SetName(nodeName)
            sn.GetSegmentation().AddSegment(seg)
            slicer.mrmlScene.RemoveNode(ln)
            return sn, sn.GetSegmentation().GetNthSegmentID(0)

        segA, idA = _makeSegNode([(2, 2, 2), (2, 2, 3), (3, 3, 3)], "A", "SegA")
        segB, idB = _makeSegNode([(2, 2, 3), (5, 5, 5)], "B", "SegB")

        logic = SegmentationBooleanDifferenceLogic()
        removed, kept, totalA = logic.subtract(segA, idA, segB, idB, vol, createNewSegment=True, newSegmentName="A_minus_B")

        self.assertEqual(totalA, 3)
        self.assertEqual(removed, 1)
        self.assertEqual(kept, 2)
        self.assertIsNotNone(segA.GetSegmentation().GetSegment("A_minus_B"))
        self.delayDisplay("Boolean difference test passed")
