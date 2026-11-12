import vtk
import qt
import ctk
import slicer
from slicer.ScriptedLoadableModule import ScriptedLoadableModule, ScriptedLoadableModuleWidget, ScriptedLoadableModuleLogic, ScriptedLoadableModuleTest

class RASLPSSwitcher(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        parent.title = "RAS <-> LPS Switcher"
        parent.categories = ["Utilities", "Segmentation"]
        parent.dependencies = []
        parent.contributors = ["Pedro"]
        parent.helpText = "Inverte RAS <-> LPS (X->-X, Y->-Y) para Modelos e Segmentacoes com 1 clique. Nao usa HardenTransform: edita a geometria diretamente. Reversivel (2x volta)."
        parent.acknowledgementText = "RAS (Slicer) <-> LPS (DICOM/ITK/NIfTI)"

class RASLPSSwitcherWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = RASLPSSwitcherLogic()
        self._updating = False
        title = qt.QLabel("<h2>RAS \u2194 LPS — 1 clique</h2>")
        self.layout.addWidget(title)
        info = qt.QLabel("Converte entre <b>RAS</b> (Slicer) e <b>LPS</b> (DICOM/NIfTI).<br>Operacao: <code>X->-X, Y->-Y, Z igual</code>. Reaplicar restaura. Metodo direto sem transform hardening (evita crash).")
        info.setWordWrap(True)
        self.layout.addWidget(info)
        selBox = ctk.ctkCollapsibleButton()
        selBox.text = "Alvos (Modelos e Segmentacoes)"
        selBox.collapsed = False
        self.layout.addWidget(selBox)
        selLayout = qt.QVBoxLayout(selBox)
        btnRow = qt.QHBoxLayout()
        self.refreshBtn = qt.QPushButton("Atualizar lista")
        self.selectAllBtn = qt.QPushButton("Selecionar tudo")
        self.clearBtn = qt.QPushButton("Limpar")
        btnRow.addWidget(self.refreshBtn)
        btnRow.addWidget(self.selectAllBtn)
        btnRow.addWidget(self.clearBtn)
        selLayout.addLayout(btnRow)
        split = qt.QHBoxLayout()
        selLayout.addLayout(split)
        left = qt.QVBoxLayout()
        right = qt.QVBoxLayout()
        split.addLayout(left, 1)
        split.addLayout(right, 1)
        left.addWidget(qt.QLabel("<b>Segmentacoes</b>"))
        self.segList = qt.QListWidget()
        self.segList.setSelectionMode(qt.QAbstractItemView.NoSelection)
        left.addWidget(self.segList)
        right.addWidget(qt.QLabel("<b>Modelos</b>"))
        self.modelList = qt.QListWidget()
        self.modelList.setSelectionMode(qt.QAbstractItemView.NoSelection)
        right.addWidget(self.modelList)
        self.flipBtn = qt.QPushButton("\u21c4  INVERTER RAS \u2194 LPS (1 clique)")
        self.flipBtn.setMinimumHeight(48)
        self.flipBtn.setStyleSheet("font-weight:bold; font-size:13px;")
        self.flipBtn.toolTip = "Inverte X,Y diretamente na geometria. Seguro para segmentacoes."
        self.layout.addWidget(self.flipBtn)
        self.status = qt.QLabel("")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        self.layout.addWidget(self.status)
        self.layout.addStretch(1)
        self.refreshBtn.clicked.connect(self.refresh)
        self.selectAllBtn.clicked.connect(lambda: self.setAllChecked(True))
        self.clearBtn.clicked.connect(lambda: self.setAllChecked(False))
        self.flipBtn.clicked.connect(self.onFlip)
        self.refresh()

    def refresh(self):
        if self._updating:
            return
        self._updating = True
        try:
            selSeg = set()
            selMod = set()
            for i in range(self.segList.count):
                it = self.segList.item(i)
                if it.flags() & qt.Qt.ItemIsUserCheckable and it.checkState() == qt.Qt.Checked:
                    selSeg.add(it.data(32))
            for i in range(self.modelList.count):
                it = self.modelList.item(i)
                if it.flags() & qt.Qt.ItemIsUserCheckable and it.checkState() == qt.Qt.Checked:
                    selMod.add(it.data(32))
            self.segList.clear()
            self.modelList.clear()
            segs = []
            mods = []
            try:
                col = slicer.mrmlScene.GetNodesByClass("vtkMRMLSegmentationNode")
                for i in range(col.GetNumberOfItems()):
                    segs.append(col.GetItemAsObject(i))
            except:
                pass
            try:
                col = slicer.mrmlScene.GetNodesByClass("vtkMRMLModelNode")
                for i in range(col.GetNumberOfItems()):
                    mods.append(col.GetItemAsObject(i))
            except:
                pass
            for node in segs:
                try:
                    nid = node.GetID()
                    name = node.GetName() or nid
                except:
                    continue
                item = qt.QListWidgetItem(name)
                item.setFlags(item.flags() | qt.Qt.ItemIsUserCheckable)
                item.setCheckState(qt.Qt.Checked if nid in selSeg else qt.Qt.Unchecked)
                item.setData(32, nid)
                self.segList.addItem(item)
            for node in mods:
                try:
                    nid = node.GetID()
                    if node.IsA("vtkMRMLSegmentationNode"):
                        continue
                    name = node.GetName() or nid
                except:
                    continue
                item = qt.QListWidgetItem(name)
                item.setFlags(item.flags() | qt.Qt.ItemIsUserCheckable)
                item.setCheckState(qt.Qt.Checked if nid in selMod else qt.Qt.Unchecked)
                item.setData(32, nid)
                self.modelList.addItem(item)
            if self.segList.count == 0:
                it = qt.QListWidgetItem("(nenhuma segmentacao na cena)")
                it.setFlags(qt.Qt.NoItemFlags)
                self.segList.addItem(it)
            if self.modelList.count == 0:
                it = qt.QListWidgetItem("(nenhum modelo na cena)")
                it.setFlags(qt.Qt.NoItemFlags)
                self.modelList.addItem(it)
        finally:
            self._updating = False

    def setAllChecked(self, v):
        s = qt.Qt.Checked if v else qt.Qt.Unchecked
        for lst in (self.segList, self.modelList):
            for i in range(lst.count):
                it = lst.item(i)
                if it.flags() & qt.Qt.ItemIsUserCheckable:
                    it.setCheckState(s)

    def selectedNodes(self):
        ids = []
        for lst in (self.segList, self.modelList):
            for i in range(lst.count):
                it = lst.item(i)
                if (it.flags() & qt.Qt.ItemIsUserCheckable) and it.checkState() == qt.Qt.Checked:
                    ids.append(it.data(32))
        nodes = []
        for nid in ids:
            try:
                n = slicer.mrmlScene.GetNodeByID(nid)
                if n:
                    nodes.append(n)
            except:
                pass
        return nodes

    def onFlip(self):
        nodes = self.selectedNodes()
        if not nodes:
            slicer.util.warningDisplay("Marque pelo menos uma segmentacao ou modelo.", windowTitle="RAS <-> LPS")
            return
        self.flipBtn.enabled = False
        try:
            with slicer.util.tryWithErrorDisplay("Falha ao inverter RAS<->LPS", waitCursor=True):
                ok, fail, msgs = self.logic.flipNodesSafe(nodes)
                self.status.setText("<b>OK:</b> %d invertido(s), %d falha(s).<br>%s" % (ok, fail, "<br>".join(msgs[-3:])))
                if fail == 0:
                    slicer.util.infoDisplay("%d node(s) invertido(s) RAS<->LPS.\nAplicar novamente restaura." % ok, windowTitle="RAS <-> LPS")
                self.refresh()
        finally:
            self.flipBtn.enabled = True

class RASLPSSwitcherLogic(ScriptedLoadableModuleLogic):
    def rasLpsMatrix(self):
        m = vtk.vtkMatrix4x4()
        m.Identity()
        m.SetElement(0, 0, -1)
        m.SetElement(1, 1, -1)
        return m

    def _flipPolyDataInPlace(self, poly):
        if poly is None or poly.GetNumberOfPoints() == 0:
            return 0
        pts = poly.GetPoints()
        n = pts.GetNumberOfPoints()
        for i in range(n):
            x, y, z = pts.GetPoint(i)
            pts.SetPoint(i, -x, -y, z)
        pts.Modified()
        normals = poly.GetPointData().GetNormals()
        if normals is not None:
            for i in range(normals.GetNumberOfTuples()):
                nx, ny, nz = normals.GetTuple3(i)
                normals.SetTuple3(i, -nx, -ny, nz)
            normals.Modified()
        cellNormals = poly.GetCellData().GetNormals()
        if cellNormals is not None:
            for i in range(cellNormals.GetNumberOfTuples()):
                nx, ny, nz = cellNormals.GetTuple3(i)
                cellNormals.SetTuple3(i, -nx, -ny, nz)
            cellNormals.Modified()
        poly.Modified()
        return n

    def _flipModelNode(self, node):
        poly = node.GetPolyData()
        if poly is None:
            return False, "sem polydata"
        n = self._flipPolyDataInPlace(poly)
        if n == 0:
            return False, "polydata vazio"
        try:
            node.Modified()
            dnode = node.GetDisplayNode()
            if dnode:
                dnode.Modified()
        except:
            pass
        return True, "%d pontos" % n

    def _flipOrientedImageData(self, img):
        if img is None:
            return False
        try:
            mat = vtk.vtkMatrix4x4()
            if hasattr(img, "GetImageToWorldMatrix"):
                img.GetImageToWorldMatrix(mat)
                flip = self.rasLpsMatrix()
                res = vtk.vtkMatrix4x4()
                vtk.vtkMatrix4x4.Multiply4x4(flip, mat, res)
                img.SetImageToWorldMatrix(res)
                return True
        except:
            pass
        try:
            mat = vtk.vtkMatrix4x4()
            if hasattr(img, "GetIndexToWorldMatrix"):
                img.GetIndexToWorldMatrix(mat)
                flip = self.rasLpsMatrix()
                res = vtk.vtkMatrix4x4()
                vtk.vtkMatrix4x4.Multiply4x4(flip, mat, res)
                img.SetIndexToWorldMatrix(res)
                return True
        except:
            pass
        try:
            if hasattr(img, "GetDirectionMatrix"):
                dm = vtk.vtkMatrix4x4()
                img.GetDirectionMatrix(dm)
                for r in range(3):
                    dm.SetElement(r, 0, -dm.GetElement(r, 0))
                    dm.SetElement(r, 1, -dm.GetElement(r, 1))
                img.SetDirectionMatrix(dm)
                return True
        except:
            pass
        return False

    def _flipSegmentationNode(self, node):
        seg = node.GetSegmentation()
        if seg is None:
            return False, "sem segmentation"
        nSeg = seg.GetNumberOfSegments()
        if nSeg == 0:
            return False, "sem segmentos"
        flipped = 0
        details = []
        node.StartModify()
        try:
            for idx in range(nSeg):
                sid = seg.GetNthSegmentID(idx)
                segment = seg.GetSegment(sid)
                if segment is None:
                    continue
                didSomething = False
                for repName in ("Closed surface", "Binary labelmap"):
                    try:
                        rep = segment.GetRepresentation(repName)
                    except:
                        rep = None
                    if rep is None:
                        continue
                    if rep.IsA("vtkPolyData"):
                        try:
                            c = self._flipPolyDataInPlace(rep)
                            if c > 0:
                                didSomething = True
                                details.append("%s:%s poly %d" % (sid, repName, c))
                        except Exception as e:
                            details.append("%s:%s erro %s" % (sid, repName, e))
                    elif rep.IsA("vtkOrientedImageData") or rep.IsA("vtkImageData"):
                        try:
                            if self._flipOrientedImageData(rep):
                                didSomething = True
                                details.append("%s:%s imagem flip" % (sid, repName))
                            else:
                                details.append("%s:%s imagem nao flipada (api)" % (sid, repName))
                        except Exception as e:
                            details.append("%s:%s imagem erro %s" % (sid, repName, e))
                if didSomething:
                    flipped += 1
                    try:
                        segment.Modified()
                    except:
                        pass
            try:
                seg.Modified()
            except:
                pass
        finally:
            node.EndModify()
            try:
                node.Modified()
            except:
                pass
        if flipped == 0:
            return False, "; ".join(details) if details else "nenhuma representacao flipada"
        return True, "%d/%d segmentos; %s" % (flipped, nSeg, ", ".join(details[:3]))

    def flipNodesSafe(self, nodes):
        ok = 0
        fail = 0
        msgs = []
        for node in nodes:
            try:
                if node is None:
                    fail += 1
                    msgs.append("node None")
                    continue
                if node.IsA("vtkMRMLSegmentationNode"):
                    success, msg = self._flipSegmentationNode(node)
                elif node.IsA("vtkMRMLModelNode"):
                    success, msg = self._flipModelNode(node)
                else:
                    fail += 1
                    msgs.append("%s: tipo nao suportado" % node.GetName())
                    continue
                if success:
                    ok += 1
                    msgs.append("%s: OK (%s)" % (node.GetName(), msg))
                else:
                    fail += 1
                    msgs.append("%s: falha (%s)" % (node.GetName(), msg))
            except Exception as e:
                import traceback
                traceback.print_exc()
                fail += 1
                try:
                    msgs.append("%s: excecao %s" % (node.GetName(), e))
                except:
                    msgs.append("excecao %s" % e)
        return ok, fail, msgs

    def flipNodes(self, nodes):
        ok, fail, msgs = self.flipNodesSafe(nodes)
        if fail and ok == 0:
            raise RuntimeError("; ".join(msgs))
        return ok

class RASLPSSwitcherTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()
    def runTest(self):
        self.setUp()
        self.test_FlipModel()
    def test_FlipModel(self):
        pts = vtk.vtkPoints()
        pts.InsertNextPoint(10, 20, 30)
        poly = vtk.vtkPolyData()
        poly.SetPoints(pts)
        verts = vtk.vtkCellArray()
        verts.InsertNextCell(1)
        verts.InsertCellPoint(0)
        poly.SetVerts(verts)
        model = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "TestModel")
        model.SetAndObservePolyData(poly)
        logic = RASLPSSwitcherLogic()
        logic.flipNodesSafe([model])
        p0 = model.GetPolyData().GetPoint(0)
        self.assertAlmostEqual(p0[0], -10, delta=1e-6)
        self.assertAlmostEqual(p0[1], -20, delta=1e-6)
        self.assertAlmostEqual(p0[2], 30, delta=1e-6)
        logic.flipNodesSafe([model])
        p0b = model.GetPolyData().GetPoint(0)
        self.assertAlmostEqual(p0b[0], 10, delta=1e-6)
        self.assertAlmostEqual(p0b[1], 20, delta=1e-6)
