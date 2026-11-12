import os
import traceback

import numpy as np

import qt
import ctk
import vtk
import slicer

from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
)


#
# ============================================================
# Constantes
# ============================================================
#

PREVIEW_SEGMENTATION_NAME = "__RootCanalSegmenter_Preview__"

DEFAULT_OUTPUT_SEGMENTATION_NAME = "CanalRadicular"

DEFAULT_CANAL_SEGMENT_NAME = "Canal"

SLICE_NAMES = ["Red", "Yellow", "Green"]


#
# ============================================================
# Helpers de conexao de sinais (PythonQt tolerante)
# ============================================================
#

def connectSignal(obj, name, signature, callback):
    """Tenta conectar um sinal Qt de duas formas (atributo e por assinatura)."""

    if obj is None:
        return False

    #

    try:
        getattr(obj, name).connect(callback)
        return True
    except Exception:
        pass

    try:
        obj.connect(signature, callback)
        return True
    except Exception:
        pass

    return False


def qvariantToString(v):

    if v is None:
        return None

    if isinstance(v, str):
        return v

    try:
        if hasattr(v, "toString"):
            try:
                s = v.toString()
                if s is not None:
                    return str(s)
            except Exception:
                pass
        s = str(v)
        if s == "None":
            return None
        return s
    except Exception:
        return None


#
# ============================================================
# HistogramWidget
#
# Desenha o histograma das intensidades dentro do dente usando
# apenas QPainter (sem matplotlib, que nao esta disponivel no
# Python embutido do Slicer).
# ============================================================
#

class HistogramWidget(qt.QWidget):

    def __init__(self, parent=None):

        super(HistogramWidget, self).__init__(parent)

        self.binEdges = None
        self.counts = None

        self.dataMin = None
        self.dataMax = None

        self.rangeMin = None
        self.rangeMax = None

        self.selectedMin = None
        self.selectedMax = None

        self.setMinimumHeight(170)

        try:
            self.setSizePolicy(
                qt.QSizePolicy.Expanding,
                qt.QSizePolicy.Fixed
            )
        except Exception:
            pass

    def setHistogram(self, binEdges, counts):

        self.binEdges = np.asarray(binEdges, dtype=float)
        self.counts = np.asarray(counts, dtype=float)

        if self.binEdges.size > 0:
            self.dataMin = float(self.binEdges[0])
            self.dataMax = float(self.binEdges[-1])

        self.update()

    def setDataRange(self, lo, hi):

        self.dataMin = lo
        self.dataMax = hi
        self.update()

    def setHighlightRange(self, vmin, vmax):

        self.rangeMin = vmin
        self.rangeMax = vmax
        self.update()

    def clear(self):

        self.binEdges = None
        self.counts = None
        self.dataMin = None
        self.dataMax = None
        self.rangeMin = None
        self.rangeMax = None

        self.update()

    def paintEvent(self, event):

        painter = qt.QPainter(self)

        try:

            rect = self.rect

            w = int(rect.width())
            h = int(rect.height())

            painter.fillRect(
                rect,
                qt.QBrush(qt.QColor(250, 250, 252))
            )

            left = 46
            right = 12
            top = 10
            bottom = 24

            plotW = max(1, w - left - right)
            plotH = max(1, h - top - bottom)

            painter.setPen(qt.QPen(qt.QColor(190, 190, 195)))
            painter.drawRect(left, top, plotW, plotH)

            if (
                self.counts is None
                or self.counts.size == 0
                or self.dataMin is None
                or self.dataMax is None
                or self.dataMax <= self.dataMin
            ):

                painter.setPen(qt.QColor(130, 130, 135))
                painter.drawText(
                    rect,
                    qt.Qt.AlignCenter,
                    "Calcule o histograma para visualizar a distribuicao."
                )
                return

            maxCount = float(self.counts.max())

            if maxCount <= 0:
                maxCount = 1.0

            nbins = int(self.counts.size)
            barW = plotW / float(nbins)

            def valToX(v):
                f = (v - self.dataMin) / (self.dataMax - self.dataMin)
                return left + f * plotW

            #
            # Faixa selecionada (hipodenso)
            #

            if self.rangeMin is not None and self.rangeMax is not None:

                v1 = max(self.dataMin, min(self.rangeMin, self.dataMax))
                v2 = max(self.dataMin, min(self.rangeMax, self.dataMax))

                x1 = valToX(v1)
                x2 = valToX(v2)

                if x2 < x1:
                    x1, x2 = x2, x1

                painter.fillRect(
                    qt.QRectF(x1, top, max(1.0, x2 - x1), plotH),
                    qt.QBrush(qt.QColor(255, 170, 120, 120))
                )

            #
            # Barras
            #

            painter.setPen(qt.Qt.NoPen)

            for i in range(nbins):

                bh = self.counts[i] / maxCount * plotH

                x = left + i * barW

                painter.fillRect(
                    qt.QRectF(x, top + plotH - bh, max(1.0, barW), bh),
                    qt.QBrush(qt.QColor(70, 110, 180))
                )

            #
            # Rotulos de eixo
            #

            painter.setPen(qt.QColor(80, 80, 85))

            painter.drawText(
                qt.QRect(left - 42, top, 38, 14),
                qt.Qt.AlignRight | qt.Qt.AlignVCenter,
                "{:.0f}".format(self.dataMin)
            )

            painter.drawText(
                qt.QRect(left + plotW + 2, top, 40, 14),
                qt.Qt.AlignLeft | qt.Qt.AlignVCenter,
                "{:.0f}".format(self.dataMax)
            )

            painter.drawText(
                qt.QRect(left, top + plotH + 2, plotW, bottom - 4),
                qt.Qt.AlignCenter,
                "Intensidade (valores nativos do volume)"
            )

        except Exception:

            pass

        finally:

            painter.end()


#
# ============================================================
# RootCanalSegmenter (modulo)
# ============================================================
#

class RootCanalSegmenter(ScriptedLoadableModule):

    def __init__(self, parent):

        ScriptedLoadableModule.__init__(self, parent)

        self.parent.title = "Root Canal Segmenter"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Pedro Afonso"]

        self.parent.helpText = """
Root Canal Segmenter para 3D Slicer.

A partir da segmentacao completa do dente (incluindo o canal),
permite selecionar um intervalo de valores hipodensos dentro do
dente para segmentar o canal radicular.

Ferramentas incluidas:

- Histograma e estatisticas das intensidades dentro do dente.
- Sugestao automatica de faixa hipodensa (Otsu, media - k*DP,
  percentis).
- Sliders + spinboxes do intervalo [min, max].
- Preview do intervalo como sobreposicao (overlay).
- Selecao do valor por clique nas Slice Views.
- Pos-processamento (maior componente, remover ilhas, closing,
  opening, preencher buracos, dilatar, erodir).
- Region growing restrito ao intervalo hipodenso.
- Automacao completa com 1 clique.
- Desfazer (undo).

O resultado e gravado em uma NOVA segmentacao dedicada.
"""

        self.parent.acknowledgementText = """
Root Canal Segmenter
"""


#
# ============================================================
# RootCanalSegmenterLogic
# ============================================================
#

class RootCanalSegmenterLogic(ScriptedLoadableModuleLogic):

    def __init__(self):

        ScriptedLoadableModuleLogic.__init__(self)

    #
    # ========================================================
    # Volume / mascara
    # ========================================================
    #

    def getVolumeArray(self, volumeNode):

        if volumeNode is None:
            raise ValueError("Volume invalido.")

        arr = slicer.util.arrayFromVolume(volumeNode)

        if arr is None:
            raise RuntimeError("Nao foi possivel obter o array do volume.")

        return arr

    def getSegmentMaskArray(self, segmentationNode, segmentID, volumeNode):

        if segmentationNode is None:
            raise ValueError("Segmentacao invalida.")

        if not segmentID:
            raise ValueError("SegmentID invalido.")

        segmentation = segmentationNode.GetSegmentation()

        if segmentation is None or segmentation.GetSegment(segmentID) is None:
            raise ValueError("Segmento nao encontrado: {}".format(segmentID))

        #
        # Garante representacao binaria
        #

        try:
            segmentation.CreateRepresentation("Binary labelmap")
        except Exception:
            pass

        #
        # 1a tentativa
        #

        try:

            arr = slicer.util.arrayFromSegmentBinaryLabelmap(
                segmentationNode,
                segmentID,
                volumeNode
            )

            if arr is not None:

                return (np.asarray(arr) > 0)

        except Exception as e:

            print(
                "[RootCanalSegmenter] arrayFromSegmentBinaryLabelmap falhou:",
                e
            )

        #
        # Fallback: exporta para labelmap temporario
        #

        tempName = "__RootCanalSegmenter_MaskTemp__"

        labelmapNode = None

        try:

            labelmapNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLLabelMapVolumeNode",
                tempName
            )

            slicer.vtkSlicerSegmentationsModuleLogic.ExportSegmentsToLabelmapNode(
                segmentationNode,
                [segmentID],
                labelmapNode,
                volumeNode
            )

            arr = slicer.util.arrayFromVolume(labelmapNode)

            if arr is None:
                raise RuntimeError("Labelmap temporario vazio.")

            return np.asarray(arr, copy=True) > 0

        finally:

            if labelmapNode is not None:
                try:
                    slicer.mrmlScene.RemoveNode(labelmapNode)
                except Exception:
                    pass

    def getSpacing(self, volumeNode):

        try:
            s = volumeNode.GetSpacing()
            return (float(s[0]), float(s[1]), float(s[2]))
        except Exception:
            return (1.0, 1.0, 1.0)

    #
    # ========================================================
    # Estatisticas
    # ========================================================
    #

    def computeStats(self, volumeNode, segmentationNode, segmentID):

        volumeArray = self.getVolumeArray(volumeNode)

        toothMask = self.getSegmentMaskArray(
            segmentationNode,
            segmentID,
            volumeNode
        )

        if toothMask.shape != volumeArray.shape:
            raise RuntimeError(
                "Mascara do dente ({}) e volume ({}) com dimensoes "
                "diferentes. Verifique se o volume de referencia "
                "coincide com a segmentacao.".format(
                    toothMask.shape,
                    volumeArray.shape
                )
            )

        values = volumeArray[toothMask].astype(np.float64)

        if values.size == 0:
            raise RuntimeError("O segmento do dente esta vazio.")

        stats = {
            "count": int(values.size),
            "min": float(values.min()),
            "max": float(values.max()),
            "mean": float(values.mean()),
            "std": float(values.std()),
            "percentiles": {},
        }

        pList = [1, 5, 10, 25, 50, 75, 90, 95, 99]

        pvals = np.percentile(values, pList)

        for p, v in zip(pList, pvals):
            stats["percentiles"][p] = float(v)

        histCounts, histEdges = np.histogram(values, bins=128)

        stats["histCounts"] = histCounts
        stats["histEdges"] = histEdges

        return stats, toothMask, volumeArray

    #
    # ========================================================
    # Sugestoes de faixa (nucleo puro)
    # ========================================================
    #

    @staticmethod
    def otsuThreshold(values, nbins=256):

        v = np.asarray(values, dtype=np.float64).ravel()

        if v.size == 0:
            return None

        lo = float(v.min())
        hi = float(v.max())

        if hi <= lo:
            return lo

        hist, edges = np.histogram(v, bins=nbins, range=(lo, hi))

        hist = hist.astype(np.float64)

        total = hist.sum()

        if total <= 0:
            return lo

        centers = (edges[:-1] + edges[1:]) / 2.0

        weight1 = np.cumsum(hist)
        weight2 = total - weight1

        cumMean = np.cumsum(hist * centers)
        sumTotal = cumMean[-1]

        mean1 = np.divide(
            cumMean,
            weight1,
            out=np.zeros_like(cumMean),
            where=weight1 > 0
        )

        mean2 = np.divide(
            sumTotal - cumMean,
            weight2,
            out=np.zeros_like(cumMean),
            where=weight2 > 0
        )

        variance = weight1 * weight2 * (mean1 - mean2) ** 2

        idx = int(np.argmax(variance))

        return float(edges[idx + 1])

    def suggestRangeOtsu(self, stats, values=None):

        #
        # values opcional; se nao fornecido usa percentis/min
        #

        vmin = stats["min"]

        if values is not None:
            threshold = self.otsuThreshold(values)
        else:
            threshold = stats["percentiles"][50]

        if threshold is None:
            threshold = stats["mean"]

        return (float(vmin), float(threshold))

    def suggestRangeMeanStd(self, stats, k=1.0):

        hi = stats["mean"] - float(k) * stats["std"]

        hi = max(stats["min"], min(hi, stats["max"]))

        return (float(stats["min"]), float(hi))

    def suggestRangePercentile(self, stats, pLow=5, pHigh=25):

        lo = stats["percentiles"].get(int(pLow), stats["min"])
        hi = stats["percentiles"].get(int(pHigh), stats["mean"])

        return (float(lo), float(hi))

    #
    # ========================================================
    # Mascara do intervalo hipodenso (nucleo puro)
    # ========================================================
    #

    @staticmethod
    def buildRangeMask(volumeArray, toothMask, vmin, vmax):

        low = float(min(vmin, vmax))
        high = float(max(vmin, vmax))

        return (
            (volumeArray >= low)
            & (volumeArray <= high)
            & (toothMask > 0)
        )

    #
    # ========================================================
    # Pos-processamento (nucleo puro, scipy.ndimage)
    # ========================================================
    #

    @staticmethod
    def _structure(connectivity):

        from scipy import ndimage as ndi

        if int(connectivity) == 6:
            return ndi.generate_binary_structure(3, 1)

        if int(connectivity) == 18:
            return ndi.generate_binary_structure(3, 2)

        return ndi.generate_binary_structure(3, 3)

    @staticmethod
    def keepLargestComponent(mask, connectivity=6):

        from scipy import ndimage as ndi

        if mask is None or not mask.any():
            return mask

        structure = RootCanalSegmenterLogic._structure(connectivity)

        labeled, n = ndi.label(mask, structure=structure)

        if n <= 1:
            return mask

        counts = np.bincount(labeled.ravel())
        counts[0] = 0

        largest = int(np.argmax(counts))

        return labeled == largest

    @staticmethod
    def removeSmallComponents(mask, minSize, connectivity=6):

        from scipy import ndimage as ndi

        if mask is None or not mask.any():
            return mask

        minSize = int(minSize)

        if minSize <= 1:
            return mask

        structure = RootCanalSegmenterLogic._structure(connectivity)

        labeled, n = ndi.label(mask, structure=structure)

        if n <= 1:
            return mask

        counts = np.bincount(labeled.ravel())

        keep = counts >= minSize
        keep[0] = False

        return keep[labeled]

    @staticmethod
    def keepComponentAtSeed(mask, seedIJK, connectivity=6):

        from scipy import ndimage as ndi

        if mask is None or not mask.any():
            return mask

        if seedIJK is None:
            return mask

        structure = RootCanalSegmenterLogic._structure(connectivity)

        labeled, n = ndi.label(mask, structure=structure)

        if n <= 0:
            return mask

        #
        # seedIJK esta em (i, j, k); array numpy e (k, j, i)
        #

        i, j, k = int(seedIJK[0]), int(seedIJK[1]), int(seedIJK[2])

        if not (
            0 <= k < labeled.shape[0]
            and 0 <= j < labeled.shape[1]
            and 0 <= i < labeled.shape[2]
        ):
            return mask

        lbl = int(labeled[k, j, i])

        if lbl == 0:
            return np.zeros_like(mask)

        return labeled == lbl

    @staticmethod
    def binaryClosing(mask, radius, connectivity=6):

        from scipy import ndimage as ndi

        radius = int(radius)

        if radius <= 0:
            return mask

        structure = RootCanalSegmenterLogic._structure(connectivity)

        return ndi.binary_closing(mask, structure=structure, iterations=radius)

    @staticmethod
    def binaryOpening(mask, radius, connectivity=6):

        from scipy import ndimage as ndi

        radius = int(radius)

        if radius <= 0:
            return mask

        structure = RootCanalSegmenterLogic._structure(connectivity)

        return ndi.binary_opening(mask, structure=structure, iterations=radius)

    @staticmethod
    def binaryDilate(mask, radius, connectivity=6):

        from scipy import ndimage as ndi

        radius = int(radius)

        if radius <= 0:
            return mask

        structure = RootCanalSegmenterLogic._structure(connectivity)

        return ndi.binary_dilation(mask, structure=structure, iterations=radius)

    @staticmethod
    def binaryErode(mask, radius, connectivity=6):

        from scipy import ndimage as ndi

        radius = int(radius)

        if radius <= 0:
            return mask

        structure = RootCanalSegmenterLogic._structure(connectivity)

        return ndi.binary_erosion(mask, structure=structure, iterations=radius)

    @staticmethod
    def fillHoles(mask):

        from scipy import ndimage as ndi

        if mask is None or not mask.any():
            return mask

        return ndi.binary_fill_holes(mask)

    def postProcess(self, mask, params):

        if mask is None:
            return mask

        result = np.asarray(mask, dtype=bool)

        connectivity = int(params.get("connectivity", 6))

        #
        # Fechamento
        #

        result = self.binaryClosing(
            result,
            int(params.get("closingRadius", 0)),
            connectivity
        )

        #
        # Abertura
        #

        result = self.binaryOpening(
            result,
            int(params.get("openingRadius", 0)),
            connectivity
        )

        #
        # Dilatar / erodir
        #

        result = self.binaryDilate(
            result,
            int(params.get("dilateRadius", 0)),
            connectivity
        )

        result = self.binaryErode(
            result,
            int(params.get("erodeRadius", 0)),
            connectivity
        )

        #
        # Remover ilhas pequenas
        #

        result = self.removeSmallComponents(
            result,
            int(params.get("minSize", 0)),
            connectivity
        )

        #
        # Manter maior componente
        #

        if params.get("keepLargest", False):

            result = self.keepLargestComponent(result, connectivity)

        #
        # Preencher buracos
        #

        if params.get("fillHoles", False):

            result = self.fillHoles(result)

        return result

    #
    # ========================================================
    # Aplicar mascara em segmentacao
    # ========================================================
    #

    def applyMaskToSegmentation(
        self,
        mask,
        segmentationNode,
        segmentName,
        volumeNode
    ):

        if segmentationNode is None:
            raise ValueError("Segmentacao de saida invalida.")

        if volumeNode is None:
            raise ValueError("Volume invalido.")

        segmentation = segmentationNode.GetSegmentation()

        segmentID = None

        for i in range(segmentation.GetNumberOfSegments()):

            sid = segmentation.GetNthSegmentID(i)
            seg = segmentation.GetSegment(sid)

            if seg is not None and seg.GetName() == segmentName:
                segmentID = sid
                break

        if segmentID is None:

            try:
                segmentID = segmentation.AddEmptySegment(segmentName, segmentName)
            except Exception:
                segmentID = segmentation.AddEmptySegment(segmentName)

        array = np.asarray(mask, dtype=np.uint8)

        try:

            slicer.util.updateSegmentBinaryLabelmapFromArray(
                array,
                segmentationNode,
                segmentID,
                volumeNode
            )

        except Exception as e:

            print(
                "[RootCanalSegmenter] updateSegmentBinaryLabelmapFromArray "
                "falhou, tentando fallback:",
                e
            )

            #
            # Fallback robusto via vtkOrientedImageData
            #

            labelmapImage = self.maskToOrientedImageData(array, volumeNode)

            ok = slicer.vtkSlicerSegmentationsModuleLogic.SetBinaryLabelmapToSegment(
                labelmapImage,
                segmentationNode,
                segmentID,
                slicer.vtkSlicerSegmentationsModuleLogic.MODE_REPLACE
            )

            if not ok:
                raise RuntimeError(
                    "Nao foi possivel gravar a mascara no segmento."
                )

        #
        # Cor do segmento
        #

        try:

            seg = segmentation.GetSegment(segmentID)

            if seg is not None:
                try:
                    seg.SetColor(1.0, 0.45, 0.10)
                except Exception:
                    pass

        except Exception:
            pass

        try:
            segmentationNode.Modified()
        except Exception:
            pass

        try:
            segmentationNode.GetDisplayNode().Modified()
        except Exception:
            pass

        return segmentID

    def maskToOrientedImageData(self, mask, volumeNode):

        from vtk.util import numpy_support

        imageData = volumeNode.GetImageData()

        extent = imageData.GetExtent()

        output = slicer.vtkOrientedImageData()

        output.SetExtent(extent)

        output.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)

        ijkToRAS = vtk.vtkMatrix4x4()
        volumeNode.GetIJKToRASMatrix(ijkToRAS)
        output.SetGeometryFromImageToWorldMatrix(ijkToRAS)

        #
        # Copia a mascara (array k,j,i) para o vtkImageData.
        # Ordem C (i mais rapido, depois j, depois k) coincide com
        # a ordem de pontos do vtkImageData.
        #

        arr = np.ascontiguousarray(
            np.asarray(mask, dtype=np.uint8).ravel(order="C")
        )

        vtkArray = numpy_support.numpy_to_vtk(
            arr,
            deep=True,
            array_type=vtk.VTK_UNSIGNED_CHAR
        )

        vtkArray.SetNumberOfComponents(1)

        output.GetPointData().SetScalars(vtkArray)

        output.Modified()

        return output


#
# ============================================================
# RootCanalSegmenterWidget
# ============================================================
#

class RootCanalSegmenterWidget(ScriptedLoadableModuleWidget):

    def __init__(self, parent=None):

        ScriptedLoadableModuleWidget.__init__(self, parent)

        self.logic = None

        #
        # Estado
        #

        self.sliceObservers = {}
        self.layoutManager = None

        self.pickMode = None          # None | "range" | "seed"
        self.seedIJK = None
        self.seedRAS = None
        self.seedValue = None
        self.seedMarkupNode = None

        self.toothStats = None
        self.toothValues = None
        self.toothMask = None

        self.currentMask = None

        self.undoStack = []
        self.lastErrorText = ""

        self.outputSegmentationNode = None

        self._updatingRange = False
        self._debounceTimer = None

        #
        # Widgets (referencias)
        #

        self.toothSegmentIDs = []

    #
    # ========================================================
    # SETUP
    # ========================================================
    #

    def setup(self):

        ScriptedLoadableModuleWidget.setup(self)

        self.logic = RootCanalSegmenterLogic()

        titleLabel = qt.QLabel("<h3>Root Canal Segmenter</h3>")
        self.layout.addWidget(titleLabel)

        instructionsLabel = qt.QLabel(
            "1. Selecione o <b>Volume</b> (CBCT/HU) e a "
            "<b>Segmentacao</b> do dente (segmento completo, incluindo o canal).<br>"
            "2. Clique em <b>Calcular histograma / estatisticas</b>.<br>"
            "3. Escolha o intervalo hipodenso [min, max] (manual, sugestao "
            "automatica ou clique nas slices).<br>"
            "4. Faca o <b>Preview</b>, ajuste o <b>Pos-processamento</b> e clique "
            "em <b>Aplicar</b> para gerar a <b>nova segmentacao</b> do canal."
        )
        instructionsLabel.wordWrap = True
        self.layout.addWidget(instructionsLabel)

        self._buildInputSection()
        self._buildHistogramSection()
        self._buildRangeSection()
        self._buildPreviewSection()
        self._buildPostSection()
        self._buildRegionGrowSection()
        self._buildAutoSection()
        self._buildOutputSection()

        #
        # Undo / progresso / status / console
        #

        self.undoButton = qt.QPushButton("Desfazer (undo)")
        self.undoButton.enabled = False
        self.undoButton.toolTip = (
            "Restaura o segmento de saida ao estado anterior ao ultimo Aplicar."
        )
        connectSignal(self.undoButton, "clicked", "clicked()", self.onUndo)
        self.layout.addWidget(self.undoButton)

        self.progressBar = qt.QProgressBar()
        self.progressBar.minimum = 0
        self.progressBar.maximum = 100
        self.progressBar.value = 0
        self.layout.addWidget(self.progressBar)

        self.statusLabel = qt.QLabel(
            "Selecione o volume e a segmentacao do dente."
        )
        self.statusLabel.wordWrap = True
        try:
            self.statusLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse
        except Exception:
            pass
        self.layout.addWidget(self.statusLabel)

        self._buildConsoleSection()

        #
        # Layout manager + observadores de slice
        #

        try:
            self.layoutManager = slicer.app.layoutManager()
        except Exception:
            self.layoutManager = None

        qt.QTimer.singleShot(600, self.installSliceObservers)

        #
        # Timer de refresh
        #

        self.refreshTimer = qt.QTimer()
        self.refreshTimer.setInterval(500)
        connectSignal(
            self.refreshTimer,
            "timeout",
            "timeout()",
            self.updateState
        )
        self.refreshTimer.start()

        #
        # Debounce de preview
        #

        self._debounceTimer = qt.QTimer()
        self._debounceTimer.setSingleShot(True)
        self._debounceTimer.setInterval(250)
        connectSignal(
            self._debounceTimer,
            "timeout",
            "timeout()",
            lambda: self.updatePreview(showErrors=False)
        )

        self.updateState()

    #
    # --------------------------------------------------------
    # Secao: entrada
    # --------------------------------------------------------

    def _buildInputSection(self):

        collapsible = ctk.ctkCollapsibleButton()
        collapsible.text = "Volume e segmentacao do dente"
        collapsible.collapsed = False
        self.layout.addWidget(collapsible)

        form = qt.QFormLayout(collapsible)

        self.volumeSelector = slicer.qMRMLNodeComboBox()
        self.volumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.volumeSelector.selectNodeUponCreation = False
        self.volumeSelector.addEnabled = False
        self.volumeSelector.removeEnabled = False
        self.volumeSelector.noneEnabled = True
        self.volumeSelector.showHidden = False
        self.volumeSelector.showChildNodeTypes = False
        self.volumeSelector.setMRMLScene(slicer.mrmlScene)
        self.volumeSelector.toolTip = (
            "Volume de referencia (CBCT). Deve coincidir com a segmentacao."
        )
        form.addRow("Volume:", self.volumeSelector)

        self.toothSegmentationSelector = slicer.qMRMLNodeComboBox()
        self.toothSegmentationSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
        self.toothSegmentationSelector.selectNodeUponCreation = False
        self.toothSegmentationSelector.addEnabled = False
        self.toothSegmentationSelector.removeEnabled = False
        self.toothSegmentationSelector.noneEnabled = True
        self.toothSegmentationSelector.showHidden = False
        self.toothSegmentationSelector.showChildNodeTypes = False
        self.toothSegmentationSelector.setMRMLScene(slicer.mrmlScene)
        self.toothSegmentationSelector.toolTip = (
            "Segmentacao que contem o dente (dente completo, incluindo o canal)."
        )
        form.addRow("Segmentacao:", self.toothSegmentationSelector)

        self.toothSegmentComboBox = qt.QComboBox()
        self.toothSegmentComboBox.toolTip = (
            "Segmento do dente completo."
        )

        row = qt.QHBoxLayout()
        row.addWidget(self.toothSegmentComboBox, 1)

        self.refreshToothSegmentsButton = qt.QPushButton("Atualizar")
        self.refreshToothSegmentsButton.minimumWidth = 85
        connectSignal(
            self.refreshToothSegmentsButton,
            "clicked",
            "clicked()",
            self.onRefreshToothSegments
        )
        row.addWidget(self.refreshToothSegmentsButton)

        form.addRow("Segmento do dente:", row)

        self.inputInfoLabel = qt.QLabel("Selecione volume + segmentacao + segmento.")
        self.inputInfoLabel.wordWrap = True
        form.addRow("Estado:", self.inputInfoLabel)

        connectSignal(
            self.toothSegmentationSelector,
            "currentNodeChanged",
            "currentNodeChanged(vtkMRMLNode*)",
            self.onToothSegmentationChanged
        )

        connectSignal(
            self.toothSegmentComboBox,
            "currentIndexChanged",
            "currentIndexChanged(int)",
            self.updateState
        )

        connectSignal(
            self.volumeSelector,
            "currentNodeChanged",
            "currentNodeChanged(vtkMRMLNode*)",
            self.onVolumeChanged
        )

        self.onToothSegmentationChanged()

    #
    # --------------------------------------------------------
    # Secao: histograma
    # --------------------------------------------------------

    def _buildHistogramSection(self):

        collapsible = ctk.ctkCollapsibleButton()
        collapsible.text = "Histograma e estatisticas (dentro do dente)"
        collapsible.collapsed = False
        self.layout.addWidget(collapsible)

        layout = qt.QVBoxLayout(collapsible)

        self.calcHistogramButton = qt.QPushButton(
            "Calcular histograma / estatisticas"
        )
        connectSignal(
            self.calcHistogramButton,
            "clicked",
            "clicked()",
            self.onComputeHistogram
        )
        layout.addWidget(self.calcHistogramButton)

        self.histogramWidget = HistogramWidget()
        layout.addWidget(self.histogramWidget)

        self.statsLabel = qt.QLabel("Sem estatisticas.")
        self.statsLabel.wordWrap = True
        try:
            self.statsLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse
        except Exception:
            pass
        layout.addWidget(self.statsLabel)

    #
    # --------------------------------------------------------
    # Secao: sugestao + intervalo
    # --------------------------------------------------------

    def _buildRangeSection(self):

        collapsible = ctk.ctkCollapsibleButton()
        collapsible.text = "Intervalo hipodenso [min, max]"
        collapsible.collapsed = False
        self.layout.addWidget(collapsible)

        layout = qt.QVBoxLayout(collapsible)

        #
        # Sugestoes
        #

        suggestForm = qt.QFormLayout()

        self.suggestMethodComboBox = qt.QComboBox()
        self.suggestMethodComboBox.addItem("Otsu (min ate o limiar)", "otsu")
        self.suggestMethodComboBox.addItem("Media - k*DP", "meanstd")
        self.suggestMethodComboBox.addItem("Percentis (p_low ate p_high)", "percentile")
        suggestForm.addRow("Metodo sugerido:", self.suggestMethodComboBox)

        self.suggestKSpinBox = qt.QDoubleSpinBox()
        self.suggestKSpinBox.minimum = 0.0
        self.suggestKSpinBox.maximum = 10.0
        self.suggestKSpinBox.singleStep = 0.1
        self.suggestKSpinBox.decimals = 2
        self.suggestKSpinBox.value = 1.0
        suggestForm.addRow("k (para media - k*DP):", self.suggestKSpinBox)

        self.suggestPLowSpinBox = qt.QSpinBox()
        self.suggestPLowSpinBox.minimum = 0
        self.suggestPLowSpinBox.maximum = 100
        self.suggestPLowSpinBox.value = 10
        suggestForm.addRow("Percentil baixo:", self.suggestPLowSpinBox)

        self.suggestPHighSpinBox = qt.QSpinBox()
        self.suggestPHighSpinBox.minimum = 0
        self.suggestPHighSpinBox.maximum = 100
        self.suggestPHighSpinBox.value = 25
        suggestForm.addRow("Percentil alto:", self.suggestPHighSpinBox)

        layout.addLayout(suggestForm)

        self.suggestButton = qt.QPushButton("Sugerir faixa")
        connectSignal(
            self.suggestButton,
            "clicked",
            "clicked()",
            self.onSuggestRange
        )
        layout.addWidget(self.suggestButton)

        self.suggestedRangeLabel = qt.QLabel("-")
        try:
            self.suggestedRangeLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse
        except Exception:
            pass
        layout.addWidget(self.suggestedRangeLabel)

        #
        # Range slider + spinboxes
        #

        self.rangeSlider = ctk.ctkDoubleRangeSlider()
        self.rangeSlider.minimum = 0.0
        self.rangeSlider.maximum = 100.0

        connectSignal(
            self.rangeSlider,
            "valuesChanged",
            "valuesChanged(double,double)",
            self.onRangeSliderChanged
        )
        layout.addWidget(self.rangeSlider)

        rangeRow = qt.QHBoxLayout()

        self.rangeMinSpinBox = qt.QDoubleSpinBox()
        self.rangeMinSpinBox.minimum = -1e9
        self.rangeMinSpinBox.maximum = 1e9
        self.rangeMinSpinBox.decimals = 2
        self.rangeMinSpinBox.singleStep = 1.0
        rangeRow.addWidget(qt.QLabel("min:"))
        rangeRow.addWidget(self.rangeMinSpinBox)

        self.rangeMaxSpinBox = qt.QDoubleSpinBox()
        self.rangeMaxSpinBox.minimum = -1e9
        self.rangeMaxSpinBox.maximum = 1e9
        self.rangeMaxSpinBox.decimals = 2
        self.rangeMaxSpinBox.singleStep = 1.0
        rangeRow.addWidget(qt.QLabel("max:"))
        rangeRow.addWidget(self.rangeMaxSpinBox)

        layout.addLayout(rangeRow)

        connectSignal(
            self.rangeMinSpinBox,
            "valueChanged",
            "valueChanged(double)",
            self.onRangeSpinChanged
        )
        connectSignal(
            self.rangeMaxSpinBox,
            "valueChanged",
            "valueChanged(double)",
            self.onRangeSpinChanged
        )

        #
        # Clique nas slices
        #

        clicForm = qt.QFormLayout()

        self.pickActionComboBox = qt.QComboBox()
        self.pickActionComboBox.addItem("Centrar faixa no valor", "center")
        self.pickActionComboBox.addItem("Definir minimo", "min")
        self.pickActionComboBox.addItem("Definir maximo", "max")
        clicForm.addRow("Acao do clique:", self.pickActionComboBox)

        self.pickWidthSpinBox = qt.QDoubleSpinBox()
        self.pickWidthSpinBox.minimum = 0.0
        self.pickWidthSpinBox.maximum = 1e6
        self.pickWidthSpinBox.decimals = 1
        self.pickWidthSpinBox.value = 100.0
        clicForm.addRow("Largura (centrar):", self.pickWidthSpinBox)

        layout.addLayout(clicForm)

        self.pickRangeButton = qt.QPushButton("Ativar clique nas slices (faixa)")
        connectSignal(
            self.pickRangeButton,
            "clicked",
            "clicked()",
            self.onPickRangeButton
        )
        layout.addWidget(self.pickRangeButton)

        self.pickInfoLabel = qt.QLabel("-")
        try:
            self.pickInfoLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse
        except Exception:
            pass
        layout.addWidget(self.pickInfoLabel)

    #
    # --------------------------------------------------------
    # Secao: preview
    # --------------------------------------------------------

    def _buildPreviewSection(self):

        collapsible = ctk.ctkCollapsibleButton()
        collapsible.text = "Preview (sobreposicao)"
        collapsible.collapsed = False
        self.layout.addWidget(collapsible)

        layout = qt.QVBoxLayout(collapsible)

        row = qt.QHBoxLayout()

        self.previewButton = qt.QPushButton("Atualizar preview")
        connectSignal(
            self.previewButton,
            "clicked",
            "clicked()",
            self.onPreviewClicked
        )
        row.addWidget(self.previewButton)

        self.clearPreviewButton = qt.QPushButton("Limpar preview")
        connectSignal(
            self.clearPreviewButton,
            "clicked",
            "clicked()",
            self.onClearPreview
        )
        row.addWidget(self.clearPreviewButton)

        layout.addLayout(row)

        self.previewInfoLabel = qt.QLabel("Sem preview.")
        self.previewInfoLabel.wordWrap = True
        try:
            self.previewInfoLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse
        except Exception:
            pass
        layout.addWidget(self.previewInfoLabel)

    #
    # --------------------------------------------------------
    # Secao: pos-processamento
    # --------------------------------------------------------

    def _buildPostSection(self):

        collapsible = ctk.ctkCollapsibleButton()
        collapsible.text = "Pos-processamento"
        collapsible.collapsed = False
        self.layout.addWidget(collapsible)

        form = qt.QFormLayout(collapsible)

        self.keepLargestCheckBox = qt.QCheckBox()
        self.keepLargestCheckBox.checked = True
        form.addRow("Manter so o maior componente:", self.keepLargestCheckBox)

        self.minSizeSpinBox = qt.QSpinBox()
        self.minSizeSpinBox.minimum = 0
        self.minSizeSpinBox.maximum = 1000000
        self.minSizeSpinBox.value = 0
        form.addRow("Remover componentes < N voxels:", self.minSizeSpinBox)

        self.closingSpinBox = qt.QSpinBox()
        self.closingSpinBox.minimum = 0
        self.closingSpinBox.maximum = 20
        self.closingSpinBox.value = 0
        form.addRow("Closing (raio voxels):", self.closingSpinBox)

        self.openingSpinBox = qt.QSpinBox()
        self.openingSpinBox.minimum = 0
        self.openingSpinBox.maximum = 20
        self.openingSpinBox.value = 0
        form.addRow("Opening (raio voxels):", self.openingSpinBox)

        self.dilateSpinBox = qt.QSpinBox()
        self.dilateSpinBox.minimum = 0
        self.dilateSpinBox.maximum = 20
        self.dilateSpinBox.value = 0
        form.addRow("Dilatar (raio voxels):", self.dilateSpinBox)

        self.erodeSpinBox = qt.QSpinBox()
        self.erodeSpinBox.minimum = 0
        self.erodeSpinBox.maximum = 20
        self.erodeSpinBox.value = 0
        form.addRow("Erodir (raio voxels):", self.erodeSpinBox)

        self.fillHolesCheckBox = qt.QCheckBox()
        self.fillHolesCheckBox.checked = True
        form.addRow("Preencher buracos internos:", self.fillHolesCheckBox)

        self.connectivityComboBox = qt.QComboBox()
        self.connectivityComboBox.addItem("6 vizinhos", 6)
        self.connectivityComboBox.addItem("18 vizinhos", 18)
        self.connectivityComboBox.addItem("26 vizinhos", 26)
        form.addRow("Conectividade:", self.connectivityComboBox)

    #
    # --------------------------------------------------------
    # Secao: region growing
    # --------------------------------------------------------

    def _buildRegionGrowSection(self):

        collapsible = ctk.ctkCollapsibleButton()
        collapsible.text = "Region growing restrito ao intervalo"
        collapsible.collapsed = False
        self.layout.addWidget(collapsible)

        layout = qt.QVBoxLayout(collapsible)

        info = qt.QLabel(
            "Mantem apenas o componente conectado a semente, dentro da "
            "mascara do intervalo hipodenso."
        )
        info.wordWrap = True
        layout.addWidget(info)

        self.regionGrowCheckBox = qt.QCheckBox()
        self.regionGrowCheckBox.checked = False
        self.regionGrowCheckBox.text = "Aplicar region growing restrito"
        layout.addWidget(self.regionGrowCheckBox)

        self.pickSeedButton = qt.QPushButton("Marcar semente nas slices")
        connectSignal(
            self.pickSeedButton,
            "clicked",
            "clicked()",
            self.onPickSeedButton
        )
        layout.addWidget(self.pickSeedButton)

        self.seedInfoLabel = qt.QLabel("Semente: nao definida.")
        try:
            self.seedInfoLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse
        except Exception:
            pass
        layout.addWidget(self.seedInfoLabel)

        connectSignal(
            self.regionGrowCheckBox,
            "toggled",
            "toggled(bool)",
            self.updateState
        )

    #
    # --------------------------------------------------------
    # Secao: automacao
    # --------------------------------------------------------

    def _buildAutoSection(self):

        collapsible = ctk.ctkCollapsibleButton()
        collapsible.text = "Automacao completa (1 clique)"
        collapsible.collapsed = True
        self.layout.addWidget(collapsible)

        layout = qt.QVBoxLayout(collapsible)

        info = qt.QLabel(
            "Sugere a faixa (metodo acima) -> pos-processamento -> "
            "aplica na nova segmentacao."
        )
        info.wordWrap = True
        layout.addWidget(info)

        self.autoRunButton = qt.QPushButton("Executar automacao completa")
        connectSignal(
            self.autoRunButton,
            "clicked",
            "clicked()",
            self.onAutoRun
        )
        layout.addWidget(self.autoRunButton)

    #
    # --------------------------------------------------------
    # Secao: saida
    # --------------------------------------------------------

    def _buildOutputSection(self):

        collapsible = ctk.ctkCollapsibleButton()
        collapsible.text = "Saida (nova segmentacao)"
        collapsible.collapsed = False
        self.layout.addWidget(collapsible)

        form = qt.QFormLayout(collapsible)

        self.outputSegNameEdit = qt.QLineEdit()
        self.outputSegNameEdit.text = DEFAULT_OUTPUT_SEGMENTATION_NAME
        form.addRow("Nome da nova segmentacao:", self.outputSegNameEdit)

        self.outputSegmentNameEdit = qt.QLineEdit()
        self.outputSegmentNameEdit.text = DEFAULT_CANAL_SEGMENT_NAME
        form.addRow("Nome do segmento:", self.outputSegmentNameEdit)

        self.applyButton = qt.QPushButton("Aplicar / criar segmento do canal")
        connectSignal(
            self.applyButton,
            "clicked",
            "clicked()",
            self.onApply
        )
        form.addRow(self.applyButton)

        self.outputInfoLabel = qt.QLabel("Saida: sera criada ao aplicar.")
        self.outputInfoLabel.wordWrap = True
        try:
            self.outputInfoLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse
        except Exception:
            pass
        form.addRow("Estado:", self.outputInfoLabel)

    #
    # --------------------------------------------------------
    # Console
    # --------------------------------------------------------

    def _buildConsoleSection(self):

        collapsible = ctk.ctkCollapsibleButton()
        collapsible.text = "Console / Log (copiavel)"
        collapsible.collapsed = True
        self.layout.addWidget(collapsible)

        layout = qt.QVBoxLayout(collapsible)

        self.logTextEdit = qt.QPlainTextEdit()
        self.logTextEdit.readOnly = True
        self.logTextEdit.placeholderText = (
            "Log do Root Canal Segmenter. Erros aparecem aqui e podem ser copiados."
        )

        try:
            self.logTextEdit.lineWrapMode = qt.QPlainTextEdit.NoWrap
        except Exception:
            pass

        self.logTextEdit.minimumHeight = 140
        self.logTextEdit.maximumHeight = 220

        try:
            self.logTextEdit.setTextInteractionFlags(
                qt.Qt.TextSelectableByMouse | qt.Qt.TextSelectableByKeyboard
            )
        except Exception:
            pass

        layout.addWidget(self.logTextEdit)

        row = qt.QHBoxLayout()

        self.copyLogButton = qt.QPushButton("Copiar log")
        connectSignal(self.copyLogButton, "clicked", "clicked()", self.onCopyLog)
        row.addWidget(self.copyLogButton)

        self.copyLastErrorButton = qt.QPushButton("Copiar ultimo erro")
        connectSignal(
            self.copyLastErrorButton,
            "clicked",
            "clicked()",
            self.onCopyLastError
        )
        row.addWidget(self.copyLastErrorButton)

        self.clearLogButton = qt.QPushButton("Limpar")
        connectSignal(self.clearLogButton, "clicked", "clicked()", self.onClearLog)
        row.addWidget(self.clearLogButton)

        layout.addLayout(row)

        self.appendLog(
            "[RootCanalSegmenter] Console pronto."
        )

    #
    # ========================================================
    # GETTERS
    # ========================================================
    #

    def getVolumeNode(self):

        try:
            return self.volumeSelector.currentNode()
        except Exception:
            return None

    def getToothSegmentationNode(self):

        try:
            return self.toothSegmentationSelector.currentNode()
        except Exception:
            return None

    def getToothSegmentID(self):

        try:
            cb = self.toothSegmentComboBox
            idx = int(cb.currentIndex)
            ids = self.toothSegmentIDs
            if 0 <= idx < len(ids):
                sid = qvariantToString(ids[idx])
                if sid:
                    return sid
            sid = qvariantToString(cb.itemData(idx))
            if sid:
                return sid
        except Exception:
            pass
        return None

    def getRange(self):

        try:
            lo = float(self.rangeMinSpinBox.value)
            hi = float(self.rangeMaxSpinBox.value)
        except Exception:
            lo, hi = 0.0, 1.0

        if lo > hi:
            lo, hi = hi, lo

        return lo, hi

    #
    # ========================================================
    # SEGMENTO DO DENTE
    # ========================================================
    #

    def onToothSegmentationChanged(self, node=None):

        try:
            if node is None:
                node = self.getToothSegmentationNode()
            self.updateToothSegmentComboBox(node)
        except Exception as e:
            print("[RootCanalSegmenter] onToothSegmentationChanged:", e)

        self.updateState()

    def updateToothSegmentComboBox(self, segmentationNode):

        cb = self.toothSegmentComboBox

        previousID = self.getToothSegmentID()

        try:
            cb.blockSignals(True)
        except Exception:
            pass

        cb.clear()
        self.toothSegmentIDs = []

        if segmentationNode is None:
            cb.addItem("Nenhum", "")
            self.toothSegmentIDs = [""]
        else:
            seg = segmentationNode.GetSegmentation()
            num = seg.GetNumberOfSegments() if seg else 0

            if num <= 0:
                cb.addItem("Nenhum", "")
                self.toothSegmentIDs = [""]
            else:
                previousIdx = -1
                for i in range(num):
                    sid = seg.GetNthSegmentID(i)
                    s = seg.GetSegment(sid)
                    name = s.GetName() if (s and s.GetName()) else sid
                    cb.addItem(name, sid)
                    self.toothSegmentIDs.append(sid)
                    if previousID and sid == previousID:
                        previousIdx = i
                if previousIdx >= 0:
                    cb.currentIndex = previousIdx

        try:
            cb.blockSignals(False)
        except Exception:
            pass

    def onRefreshToothSegments(self):

        node = self.getToothSegmentationNode()

        if node is None:
            slicer.util.warningDisplay("Selecione primeiro uma segmentacao.")
            return

        try:
            node.CreateDefaultDisplayNodes()
            seg = node.GetSegmentation()
            if seg is not None:
                seg.CreateRepresentation("Binary labelmap")
        except Exception:
            pass

        self.updateToothSegmentComboBox(node)
        self.updateState()

        self.appendLog(
            "Segmentos atualizados ({}).".format(
                node.GetName() or node.GetID()
            )
        )

    def onVolumeChanged(self, node=None):

        #
        # Auto-uso do volume unico ja tratado no updateState
        #

        self.updateState()

    #
    # ========================================================
    # HISTOGRAMA
    # ========================================================
    #

    def onComputeHistogram(self):

        volumeNode = self.getVolumeNode()
        segNode = self.getToothSegmentationNode()
        segID = self.getToothSegmentID()

        if volumeNode is None or segNode is None or not segID:
            slicer.util.warningDisplay(
                "Selecione volume, segmentacao e segmento do dente."
            )
            return

        self._setBusy(True, "Calculando histograma...")

        try:

            stats, toothMask, volumeArray = self.logic.computeStats(
                volumeNode,
                segNode,
                segID
            )

            self.toothStats = stats
            self.toothMask = toothMask
            self.toothValues = volumeArray[toothMask].astype(np.float64)

            self.histogramWidget.setHistogram(
                stats["histEdges"],
                stats["histCounts"]
            )

            #
            # Atualiza limites dos controles de faixa
            #

            lo = stats["min"]
            hi = stats["max"]

            self._updatingRange = True

            try:
                self.rangeSlider.minimum = lo
                self.rangeSlider.maximum = hi

                self.rangeMinSpinBox.minimum = lo
                self.rangeMinSpinBox.maximum = hi
                self.rangeMaxSpinBox.minimum = lo
                self.rangeMaxSpinBox.maximum = hi
            except Exception:
                pass

            self._updatingRange = False

            p = stats["percentiles"]

            self.statsLabel.text = (
                "Voxels no dente: {count}\n"
                "min={min:.1f}  max={max:.1f}  media={mean:.1f}  DP={std:.1f}\n"
                "P1={p1:.1f}  P5={p5:.1f}  P10={p10:.1f}  P25={p25:.1f}\n"
                "P50={p50:.1f}  P75={p75:.1f}  P90={p90:.1f}  P95={p95:.1f}  P99={p99:.1f}"
            ).format(
                count=stats["count"],
                min=stats["min"],
                max=stats["max"],
                mean=stats["mean"],
                std=stats["std"],
                p1=p[1], p5=p[5], p10=p[10], p25=p[25],
                p50=p[50], p75=p[75], p90=p[90], p95=p[95], p99=p[99]
            )

            self.appendLog(
                "Histograma calculado: {} voxels no dente.".format(stats["count"])
            )

            self._setBusy(False, "Histograma calculado.")

        except Exception as e:

            tb = traceback.format_exc()
            self.lastErrorText = tb
            self.appendLog("ERRO histograma: {}\n{}".format(e, tb))
            self._setBusy(False, "Erro ao calcular histograma (ver Console).")
            slicer.util.errorDisplay("Erro ao calcular histograma:\n{}".format(e))

    #
    # ========================================================
    # SUGESTAO DE FAIXA
    # ========================================================
    #

    def onSuggestRange(self):

        if self.toothStats is None:
            slicer.util.warningDisplay(
                "Calcule o histograma do dente primeiro."
            )
            return

        method = "otsu"

        try:
            method = qvariantToString(self.suggestMethodComboBox.currentData)
        except Exception:
            pass

        if method == "meanstd":
            lo, hi = self.logic.suggestRangeMeanStd(
                self.toothStats,
                self.suggestKSpinBox.value
            )
        elif method == "percentile":
            lo, hi = self.logic.suggestRangePercentile(
                self.toothStats,
                self.suggestPLowSpinBox.value,
                self.suggestPHighSpinBox.value
            )
        else:
            lo, hi = self.logic.suggestRangeOtsu(
                self.toothStats,
                self.toothValues
            )

        self.suggestedRangeLabel.text = (
            "Faixa sugerida: [{:.1f}, {:.1f}]".format(lo, hi)
        )

        self._applyRange(lo, hi, updateSlider=True, updateSpin=True)
        self.appendLog("Faixa sugerida [{}]: [{:.1f}, {:.1f}]".format(method, lo, hi))

    #
    # ========================================================
    # RANGE - handlers
    # ========================================================
    #

    def onRangeSliderChanged(self, vmin, vmax):

        if self._updatingRange:
            return

        self._updatingRange = True
        try:
            self.rangeMinSpinBox.value = float(vmin)
            self.rangeMaxSpinBox.value = float(vmax)
        except Exception:
            pass
        self._updatingRange = False

        self.histogramWidget.setHighlightRange(vmin, vmax)
        self._schedulePreview()

    def onRangeSpinChanged(self, value=None):

        if self._updatingRange:
            return

        lo, hi = self.getRange()

        self._updatingRange = True
        try:
            self.rangeSlider.setValues(lo, hi)
        except Exception:
            try:
                self.rangeSlider.minimumValue = lo
                self.rangeSlider.maximumValue = hi
            except Exception:
                pass
        self._updatingRange = False

        self.histogramWidget.setHighlightRange(lo, hi)
        self._schedulePreview()

    def _applyRange(self, lo, hi, updateSlider=True, updateSpin=True):

        lo = float(lo)
        hi = float(hi)

        if lo > hi:
            lo, hi = hi, lo

        self._updatingRange = True

        try:
            if updateSpin:
                self.rangeMinSpinBox.value = lo
                self.rangeMaxSpinBox.value = hi

            if updateSlider:
                try:
                    self.rangeSlider.setValues(lo, hi)
                except Exception:
                    try:
                        self.rangeSlider.minimumValue = lo
                        self.rangeSlider.maximumValue = hi
                    except Exception:
                        pass
        except Exception:
            pass

        self._updatingRange = False

    #
    # ========================================================
    # CLIQUE NAS SLICES
    # ========================================================
    #

    def installSliceObservers(self):

        if self.layoutManager is None:
            try:
                self.layoutManager = slicer.app.layoutManager()
            except Exception:
                return

        if self.layoutManager is None:
            return

        for sliceName in SLICE_NAMES:

            try:

                sliceWidget = self.layoutManager.sliceWidget(sliceName)

                if sliceWidget is None:
                    continue

                sliceView = sliceWidget.sliceView()

                if sliceView is None:
                    continue

                interactor = sliceView.interactor()

                if interactor is None:
                    continue

                old = self.sliceObservers.get(sliceName)

                if old and old.get("interactor") == interactor:
                    continue

                if old:
                    try:
                        old["interactor"].RemoveObserver(old["tag"])
                    except Exception:
                        pass

                callback = self._createSliceCallback(sliceWidget, sliceName)

                tag = interactor.AddObserver(
                    vtk.vtkCommand.LeftButtonPressEvent,
                    callback
                )

                self.sliceObservers[sliceName] = {
                    "interactor": interactor,
                    "tag": tag,
                    "callback": callback,
                }

            except Exception as e:
                print("[RootCanalSegmenter] observer erro:", sliceName, e)

    def _createSliceCallback(self, sliceWidget, sliceName):

        def callback(caller, event):
            try:
                self._onSliceClick(sliceWidget, sliceName, caller, event)
            except Exception:
                traceback.print_exc()

        return callback

    def _onSliceClick(self, sliceWidget, sliceName, caller, event):

        if self.pickMode is None:
            return

        position = caller.GetEventPosition()
        x = int(position[0])
        y = int(position[1])

        sliceNode = sliceWidget.mrmlSliceNode()

        if sliceNode is None:
            return

        xyToRAS = sliceNode.GetXYToRAS()

        rasPoint = xyToRAS.MultiplyPoint([float(x), float(y), 0.0, 1.0])

        clickedRAS = [float(rasPoint[0]), float(rasPoint[1]), float(rasPoint[2])]

        volumeNode = self._getVolumeForSlice(sliceWidget)

        if volumeNode is None:
            self.statusLabel.text = "Nenhum volume nesta Slice View."
            return

        rasToIJK = vtk.vtkMatrix4x4()
        volumeNode.GetRASToIJKMatrix(rasToIJK)

        ijkPoint = rasToIJK.MultiplyPoint(
            [clickedRAS[0], clickedRAS[1], clickedRAS[2], 1.0]
        )

        ijk = [
            int(round(ijkPoint[0])),
            int(round(ijkPoint[1])),
            int(round(ijkPoint[2])),
        ]

        imageData = volumeNode.GetImageData()
        extent = imageData.GetExtent()

        if not (
            extent[0] <= ijk[0] <= extent[1]
            and extent[2] <= ijk[1] <= extent[3]
            and extent[4] <= ijk[2] <= extent[5]
        ):
            self.statusLabel.text = "Clique fora do volume."
            return

        value = float(
            imageData.GetScalarComponentAsDouble(ijk[0], ijk[1], ijk[2], 0)
        )

        if self.pickMode == "seed":

            self.seedIJK = ijk
            self.seedRAS = clickedRAS
            self.seedValue = value

            self.seedInfoLabel.text = (
                "Semente: IJK=[{}, {}, {}]  valor={:.1f}".format(
                    ijk[0], ijk[1], ijk[2], value
                )
            )

            self._showSeedMarker(clickedRAS)

            self.pickMode = None
            self.pickSeedButton.text = "Marcar semente nas slices"

            self.appendLog("Semente: IJK={} valor={:.2f}".format(ijk, value))

        else:

            action = "center"
            try:
                action = qvariantToString(self.pickActionComboBox.currentData)
            except Exception:
                pass

            lo, hi = self.getRange()

            if action == "min":
                lo = value
            elif action == "max":
                hi = value
            else:
                half = abs(float(self.pickWidthSpinBox.value)) / 2.0
                lo = value - half
                hi = value + half

            self._applyRange(lo, hi)

            self.pickInfoLabel.text = (
                "Ultimo clique: IJK=[{}, {}, {}]  valor={:.1f}  ->  faixa "
                "[{:.1f}, {:.1f}]".format(
                    ijk[0], ijk[1], ijk[2], value, lo, hi
                )
            )

            self.histogramWidget.setHighlightRange(lo, hi)

            self.pickMode = None
            self.pickRangeButton.text = "Ativar clique nas slices (faixa)"

            self._schedulePreview()

            self.appendLog(
                "Clique: IJK={} valor={:.2f} -> faixa [{:.1f}, {:.1f}]".format(
                    ijk, value, lo, hi
                )
            )

        self.updateState()

    def _getVolumeForSlice(self, sliceWidget):

        selectedVolume = self.getVolumeNode()

        if selectedVolume is not None:
            return selectedVolume

        try:
            sliceLogic = sliceWidget.sliceLogic()
            if sliceLogic is None:
                return None

            layer = sliceLogic.GetBackgroundLayer()
            if layer:
                v = layer.GetVolumeNode()
                if v:
                    return v

            layer = sliceLogic.GetForegroundLayer()
            if layer:
                v = layer.GetVolumeNode()
                if v:
                    return v
        except Exception:
            pass

        return None

    def onPickRangeButton(self):

        if self.pickMode == "range":
            self.pickMode = None
            self.pickRangeButton.text = "Ativar clique nas slices (faixa)"
            self.statusLabel.text = "Selecao por clique desativada."
        else:
            self.pickMode = "range"
            self.pickSeedButton.text = "Marcar semente nas slices"
            self.pickRangeButton.text = "Cancelar clique (faixa)"
            self.statusLabel.text = (
                "Clique em um voxel nas Slice Views para ajustar a faixa."
            )

    def onPickSeedButton(self):

        if self.pickMode == "seed":
            self.pickMode = None
            self.pickSeedButton.text = "Marcar semente nas slices"
            self.statusLabel.text = "Selecao de semente desativada."
        else:
            self.pickMode = "seed"
            self.pickRangeButton.text = "Ativar clique nas slices (faixa)"
            self.pickSeedButton.text = "Cancelar semente"
            self.statusLabel.text = (
                "Clique em um voxel nas Slice Views para marcar a semente."
            )

    def _showSeedMarker(self, ras):

        try:

            if self.seedMarkupNode:
                try:
                    slicer.mrmlScene.RemoveNode(self.seedMarkupNode)
                except Exception:
                    pass
                self.seedMarkupNode = None

            node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsFiducialNode",
                "RootCanalSegmenterSeed"
            )

            node.AddControlPoint(float(ras[0]), float(ras[1]), float(ras[2]))

            displayNode = node.GetDisplayNode()
            if displayNode:
                try:
                    displayNode.SetPointLabelsVisibility(False)
                except Exception:
                    pass
                try:
                    displayNode.SetSelectedColor(1.0, 0.0, 0.0)
                except Exception:
                    pass

            self.seedMarkupNode = node

        except Exception as e:
            print("[RootCanalSegmenter] erro marcador:", e)

    #
    # ========================================================
    # PREVIEW
    # ========================================================
    #

    def _schedulePreview(self):

        if self._debounceTimer is not None:
            try:
                self._debounceTimer.start()
            except Exception:
                pass

    def onPreviewClicked(self):

        self.updatePreview(showErrors=True)

    def updatePreview(self, showErrors=True):

        volumeNode = self.getVolumeNode()
        segNode = self.getToothSegmentationNode()
        segID = self.getToothSegmentID()

        if volumeNode is None or segNode is None or not segID:
            if showErrors:
                slicer.util.warningDisplay(
                    "Selecione volume, segmentacao e segmento do dente."
                )
            return

        try:

            toothMask = self.toothMask
            volumeArray = None

            if toothMask is None or self.toothStats is None:
                stats, toothMask, volumeArray = self.logic.computeStats(
                    volumeNode, segNode, segID
                )
                self.toothStats = stats
                self.toothMask = toothMask
                self.toothValues = volumeArray[toothMask].astype(np.float64)
                self.histogramWidget.setHistogram(
                    stats["histEdges"], stats["histCounts"]
                )

            if volumeArray is None:
                volumeArray = self.logic.getVolumeArray(volumeNode)

            lo, hi = self.getRange()

            rawMask = self.logic.buildRangeMask(
                volumeArray, toothMask, lo, hi
            )

            finalMask = self._computeFinalMask(rawMask, volumeArray)

            self.currentMask = finalMask

            self._updatePreviewNode(finalMask, volumeNode)

            spacing = self.logic.getSpacing(volumeNode)
            voxelVol = spacing[0] * spacing[1] * spacing[2]

            rawCount = int(rawMask.sum())
            finalCount = int(finalMask.sum())

            toothCount = int(toothMask.sum())

            pct = (100.0 * finalCount / toothCount) if toothCount else 0.0

            self.previewInfoLabel.text = (
                "Faixa [{:.1f}, {:.1f}]  |  bruto={} voxels  |  "
                "final={} voxels  |  volume={:.2f} mm3  |  "
                "{:.1f}% do dente".format(
                    lo, hi, rawCount, finalCount,
                    finalCount * voxelVol, pct
                )
            )

            self.histogramWidget.setHighlightRange(lo, hi)

            self.statusLabel.text = "Preview atualizado."

        except Exception as e:

            tb = traceback.format_exc()
            self.lastErrorText = tb
            self.appendLog("ERRO preview: {}\n{}".format(e, tb))

            if showErrors:
                slicer.util.errorDisplay("Erro no preview:\n{}".format(e))

    def _computeFinalMask(self, rawMask, volumeArray):

        params = self._getPostParams()

        result = self.logic.postProcess(rawMask, params)

        #
        # Region growing restrito
        #

        if self.regionGrowCheckBox.checked and self.seedIJK is not None:
            result = self.logic.keepComponentAtSeed(
                result,
                self.seedIJK,
                params.get("connectivity", 6)
            )

        return result

    def _getPostParams(self):

        conn = 6
        try:
            conn = int(self.connectivityComboBox.currentData)
        except Exception:
            pass

        return {
            "keepLargest": bool(self.keepLargestCheckBox.checked),
            "minSize": int(self.minSizeSpinBox.value),
            "closingRadius": int(self.closingSpinBox.value),
            "openingRadius": int(self.openingSpinBox.value),
            "dilateRadius": int(self.dilateSpinBox.value),
            "erodeRadius": int(self.erodeSpinBox.value),
            "fillHoles": bool(self.fillHolesCheckBox.checked),
            "connectivity": conn,
        }

    def _getOrCreatePreviewSegmentation(self):

        node = slicer.mrmlScene.GetFirstNodeByName(PREVIEW_SEGMENTATION_NAME)

        if node is None:
            node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentationNode",
                PREVIEW_SEGMENTATION_NAME
            )

        node.CreateDefaultDisplayNodes()

        try:
            displayNode = node.GetDisplayNode()
            if displayNode:
                displayNode.SetVisibility(True)
                displayNode.SetVisibility3D(False)
                displayNode.SetOpacity3D(0.6)
                try:
                    displayNode.SetAllSegmentsOpacity(0.6)
                except Exception:
                    pass
        except Exception:
            pass

        return node

    def _updatePreviewNode(self, mask, volumeNode):

        node = self._getOrCreatePreviewSegmentation()

        segmentName = "Preview"

        self.logic.applyMaskToSegmentation(
            mask,
            node,
            segmentName,
            volumeNode
        )

        #
        # Cor verde para o preview
        #

        try:
            seg = node.GetSegmentation()
            for i in range(seg.GetNumberOfSegments()):
                sid = seg.GetNthSegmentID(i)
                s = seg.GetSegment(sid)
                if s is not None and s.GetName() == segmentName:
                    try:
                        s.SetColor(0.1, 0.9, 0.2)
                    except Exception:
                        pass
        except Exception:
            pass

    def onClearPreview(self):

        self.currentMask = None

        try:
            node = slicer.mrmlScene.GetFirstNodeByName(PREVIEW_SEGMENTATION_NAME)
            if node is not None:
                slicer.mrmlScene.RemoveNode(node)
        except Exception:
            pass

        self.previewInfoLabel.text = "Sem preview."
        self.statusLabel.text = "Preview removido."

    #
    # ========================================================
    # APLICAR
    # ========================================================
    #

    def _getOrCreateOutputSegmentation(self, name):

        node = slicer.mrmlScene.GetFirstNodeByName(name)

        if node is not None and node.IsA("vtkMRMLSegmentationNode"):
            self.outputSegmentationNode = node
            node.CreateDefaultDisplayNodes()
            return node

        node = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            name
        )

        node.CreateDefaultDisplayNodes()

        self.outputSegmentationNode = node

        return node

    def onApply(self):

        volumeNode = self.getVolumeNode()
        segNode = self.getToothSegmentationNode()
        segID = self.getToothSegmentID()

        if volumeNode is None or segNode is None or not segID:
            slicer.util.warningDisplay(
                "Selecione volume, segmentacao e segmento do dente."
            )
            return

        self._setBusy(True, "Aplicando...")

        try:

            if self.currentMask is None:
                self.updatePreview(showErrors=False)

            mask = self.currentMask

            if mask is None:
                raise RuntimeError("Nenhuma mascara calculada.")

            if not mask.any():
                raise RuntimeError(
                    "A mascara esta vazia. Ajuste a faixa ou o pos-processamento."
                )

            outName = self.outputSegNameEdit.text.strip() or DEFAULT_OUTPUT_SEGMENTATION_NAME
            segmentName = self.outputSegmentNameEdit.text.strip() or DEFAULT_CANAL_SEGMENT_NAME

            outNode = self._getOrCreateOutputSegmentation(outName)

            #
            # Undo: guarda estado atual do segmento (se existir)
            #

            previousMask = None
            try:
                previousMask = self.logic.getSegmentMaskArray(
                    outNode, self._findSegmentIDByName(outNode, segmentName), volumeNode
                )
            except Exception:
                previousMask = None

            self._pushUndo(outNode.GetID(), segmentName, previousMask)

            self.logic.applyMaskToSegmentation(
                mask,
                outNode,
                segmentName,
                volumeNode
            )

            spacing = self.logic.getSpacing(volumeNode)
            voxelVol = spacing[0] * spacing[1] * spacing[2]
            count = int(mask.sum())

            self.outputInfoLabel.text = (
                "Saida: '{}' / segmento '{}'  |  {} voxels  |  {:.2f} mm3".format(
                    outName, segmentName, count, count * voxelVol
                )
            )

            self.appendLog(
                "Aplicado em '{}' / '{}': {} voxels ({:.2f} mm3).".format(
                    outName, segmentName, count, count * voxelVol
                )
            )

            self._setBusy(False, "Segmento do canal criado/atualizado.")

        except Exception as e:

            tb = traceback.format_exc()
            self.lastErrorText = tb
            self.appendLog("ERRO aplicar: {}\n{}".format(e, tb))
            self._setBusy(False, "Erro ao aplicar (ver Console).")
            slicer.util.errorDisplay("Erro ao aplicar:\n{}".format(e))

    def _findSegmentIDByName(self, segmentationNode, name):

        try:
            seg = segmentationNode.GetSegmentation()
            for i in range(seg.GetNumberOfSegments()):
                sid = seg.GetNthSegmentID(i)
                s = seg.GetSegment(sid)
                if s is not None and s.GetName() == name:
                    return sid
        except Exception:
            pass

        return None

    #
    # ========================================================
    # AUTOMACAO
    # ========================================================
    #

    def onAutoRun(self):

        self.onComputeHistogram()

        if self.toothStats is None:
            return

        self.onSuggestRange()

        self.updatePreview(showErrors=False)

        self.onApply()

    #
    # ========================================================
    # UNDO
    # ========================================================
    #

    def _pushUndo(self, segNodeID, segmentName, previousMask):

        snapshot = None

        if previousMask is not None:
            snapshot = np.array(previousMask, copy=True)

        self.undoStack.append(
            {
                "segNodeID": segNodeID,
                "segmentName": segmentName,
                "mask": snapshot,
            }
        )

        if len(self.undoStack) > 20:
            self.undoStack.pop(0)

        self._updateUndoButton()

    def _updateUndoButton(self):

        try:
            self.undoButton.enabled = len(self.undoStack) > 0
        except Exception:
            pass

    def onUndo(self):

        if not self.undoStack:
            return

        entry = self.undoStack.pop()

        try:

            volumeNode = self.getVolumeNode()

            node = slicer.mrmlScene.GetNodeByID(entry["segNodeID"])

            if node is None or volumeNode is None:
                raise RuntimeError("Estado de undo indisponivel.")

            mask = entry["mask"]

            if mask is None:
                mask = np.zeros(
                    self.logic.getVolumeArray(volumeNode).shape,
                    dtype=bool
                )

            self.logic.applyMaskToSegmentation(
                mask,
                node,
                entry["segmentName"],
                volumeNode
            )

            self.appendLog("Undo aplicado em '{}'.".format(entry["segmentName"]))
            self.statusLabel.text = "Undo aplicado."

        except Exception as e:

            tb = traceback.format_exc()
            self.lastErrorText = tb
            self.appendLog("ERRO undo: {}\n{}".format(e, tb))
            slicer.util.errorDisplay("Erro no undo:\n{}".format(e))

        self._updateUndoButton()

    #
    # ========================================================
    # ESTADO
    # ========================================================
    #

    def _autoSelectSingleVolumeIfNeeded(self):

        try:
            cur = self.volumeSelector.currentNode()
        except Exception:
            cur = None

        if cur is not None:
            return

        try:
            n = slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLScalarVolumeNode")
        except Exception:
            n = 0

        if n != 1:
            return

        try:
            single = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
        except Exception:
            single = None

        if single is None:
            return

        try:
            self.volumeSelector.setCurrentNode(single)
        except Exception:
            pass

    def updateState(self, *args):

        self._autoSelectSingleVolumeIfNeeded()

        volumeNode = self.getVolumeNode()
        segNode = self.getToothSegmentationNode()
        segID = self.getToothSegmentID()

        ready = (
            volumeNode is not None
            and segNode is not None
            and bool(segID)
        )

        #
        # Info de entrada
        #

        try:

            if not ready:

                parts = []
                if volumeNode is None:
                    parts.append("volume")
                if segNode is None:
                    parts.append("segmentacao")
                elif not segID:
                    parts.append("segmento")

                self.inputInfoLabel.text = (
                    "Falta selecionar: {}.".format(", ".join(parts))
                )

            else:
                name = segNode.GetName() or segNode.GetID()
                self.inputInfoLabel.text = (
                    "OK: '{}' (volume '{}').".format(
                        name, volumeNode.GetName() or volumeNode.GetID()
                    )
                )

        except Exception:
            pass

        #
        # Habilitacao de botoes
        #

        for btnName in (
            "calcHistogramButton",
            "suggestButton",
            "previewButton",
            "applyButton",
            "autoRunButton",
            "pickRangeButton",
            "pickSeedButton",
        ):
            btn = getattr(self, btnName, None)
            if btn is None:
                continue
            try:
                btn.enabled = ready
            except Exception:
                pass

        #
        # Info de semente
        #

        try:
            if self.seedIJK is not None:
                self.seedInfoLabel.text = (
                    "Semente: IJK={} valor={:.1f}".format(
                        self.seedIJK,
                        self.seedValue if self.seedValue is not None else 0.0
                    )
                )
        except Exception:
            pass

    #
    # ========================================================
    # HELPERS DE UI
    # ========================================================
    #

    def _setBusy(self, busy, message=None):

        try:
            self.progressBar.value = 30 if busy else 100
        except Exception:
            pass

        if message is not None:
            try:
                self.statusLabel.text = message
            except Exception:
                pass

        if not busy:
            qt.QTimer.singleShot(1200, self._resetProgress)

    def _resetProgress(self):

        try:
            self.progressBar.value = 0
        except Exception:
            pass

    def appendLog(self, text):

        try:
            self.logTextEdit.appendPlainText(str(text))
        except Exception:
            pass

    def onCopyLog(self):

        self._copyText(self.logTextEdit.toPlainText() if self.logTextEdit else "")

    def onCopyLastError(self):

        self._copyText(self.lastErrorText or "Nenhum erro registrado.")

    def onClearLog(self):

        try:
            self.logTextEdit.clear()
        except Exception:
            pass

    def _copyText(self, text):

        try:
            cb = qt.QApplication.clipboard()
            cb.setText(str(text))
            self.statusLabel.text = "Copiado para a area de transferencia."
        except Exception as e:
            print("[RootCanalSegmenter] erro copiando:", e)

    #
    # ========================================================
    # CLEANUP
    # ========================================================
    #

    def cleanup(self):

        #
        # Remove preview
        #

        try:
            self.onClearPreview()
        except Exception:
            pass

        #
        # Remove marcador de semente
        #

        try:
            if self.seedMarkupNode is not None:
                slicer.mrmlScene.RemoveNode(self.seedMarkupNode)
                self.seedMarkupNode = None
        except Exception:
            pass

        #
        # Remove observers
        #

        for sliceName, obs in list(self.sliceObservers.items()):
            try:
                obs["interactor"].RemoveObserver(obs["tag"])
            except Exception:
                pass

        self.sliceObservers = {}

        #
        # Para timers
        #

        for timerName in ("refreshTimer", "_debounceTimer"):
            try:
                getattr(self, timerName).stop()
            except Exception:
                pass

        ScriptedLoadableModuleWidget.cleanup(self)


#
# ============================================================
# Test
# ============================================================
#

class RootCanalSegmenterTest(ScriptedLoadableModuleTest):

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.testCoreFunctions()

    def testCoreFunctions(self):

        logic = RootCanalSegmenterLogic()

        #
        # Otsu
        #

        values = np.concatenate([
            np.random.normal(100.0, 10.0, 5000),
            np.random.normal(2000.0, 50.0, 5000),
        ])

        t = logic.otsuThreshold(values)

        self.assertTrue(t is not None)
        self.assertTrue(100.0 < t < 2000.0)

        #
        # Faixa + mascara
        #

        volumeArray = np.zeros((6, 6, 6), dtype=np.int16)
        volumeArray[2:4, 2:4, 2:4] = 100
        volumeArray[2:4, 2:4, 3] = 2500

        toothMask = np.zeros((6, 6, 6), dtype=bool)
        toothMask[1:5, 1:5, 1:5] = True

        mask = logic.buildRangeMask(volumeArray, toothMask, 0, 800)

        self.assertEqual(int(mask.sum()), 8)

        #
        # Pos-processamento: maior componente
        #

        m = np.zeros((5, 5, 5), dtype=bool)
        m[0, 0, 0] = True
        m[2:4, 2:4, 2:4] = True

        largest = logic.keepLargestComponent(m, 6)
        self.assertEqual(int(largest.sum()), 8)

        #
        # Region growing no componente da semente
        #

        seed = logic.keepComponentAtSeed(m, [2, 2, 2], 6)
        self.assertEqual(int(seed.sum()), 8)

        seed2 = logic.keepComponentAtSeed(m, [0, 0, 0], 6)
        self.assertEqual(int(seed2.sum()), 1)
