import os
import time
import csv
import numpy as np
from scipy import ndimage

import vtk
import qt
import ctk
import slicer
from slicer.ScriptedLoadableModule import *

# =============================================================================
# Dental Anatomical Knowledge Base (FDI Two-Digit Notation)
# =============================================================================

FDI_TEETH_INFO = {
    # Quadrant 1: Upper Right (Maxillary Right)
    11: {"name_en": "Upper Right Central Incisor", "name_pt": "Incisivo Central Superior Direito", "arch": "upper", "type": "incisor", "roots_expected": [1]},
    12: {"name_en": "Upper Right Lateral Incisor", "name_pt": "Incisivo Lateral Superior Direito", "arch": "upper", "type": "incisor", "roots_expected": [1]},
    13: {"name_en": "Upper Right Canine",          "name_pt": "Canino Superior Direito",           "arch": "upper", "type": "canine",  "roots_expected": [1]},
    14: {"name_en": "Upper Right First Premolar",  "name_pt": "Primeiro Pré-Molar Sup. Direito",   "arch": "upper", "type": "premolar","roots_expected": [1, 2]},
    15: {"name_en": "Upper Right Second Premolar", "name_pt": "Segundo Pré-Molar Sup. Direito",    "arch": "upper", "type": "premolar","roots_expected": [1, 2]},
    16: {"name_en": "Upper Right First Molar",     "name_pt": "Primeiro Molar Superior Direito",   "arch": "upper", "type": "molar",   "roots_expected": [3, 2, 1]},
    17: {"name_en": "Upper Right Second Molar",    "name_pt": "Segundo Molar Superior Direito",    "arch": "upper", "type": "molar",   "roots_expected": [3, 2, 1]},
    18: {"name_en": "Upper Right Third Molar",     "name_pt": "Terceiro Molar (Siso) Sup. Dir.",   "arch": "upper", "type": "molar",   "roots_expected": [1, 2, 3]},

    # Quadrant 2: Upper Left (Maxillary Left)
    21: {"name_en": "Upper Left Central Incisor",  "name_pt": "Incisivo Central Superior Esquerdo","arch": "upper", "type": "incisor", "roots_expected": [1]},
    22: {"name_en": "Upper Left Lateral Incisor",  "name_pt": "Incisivo Lateral Superior Esquerdo","arch": "upper", "type": "incisor", "roots_expected": [1]},
    23: {"name_en": "Upper Left Canine",           "name_pt": "Canino Superior Esquerdo",          "arch": "upper", "type": "canine",  "roots_expected": [1]},
    24: {"name_en": "Upper Left First Premolar",   "name_pt": "Primeiro Pré-Molar Sup. Esquerdo",  "arch": "upper", "type": "premolar","roots_expected": [1, 2]},
    25: {"name_en": "Upper Left Second Premolar",  "name_pt": "Segundo Pré-Molar Sup. Esquerdo",   "arch": "upper", "type": "premolar","roots_expected": [1, 2]},
    26: {"name_en": "Upper Left First Molar",      "name_pt": "Primeiro Molar Superior Esquerdo",  "arch": "upper", "type": "molar",   "roots_expected": [3, 2, 1]},
    27: {"name_en": "Upper Left Second Molar",     "name_pt": "Segundo Molar Superior Esquerdo",   "arch": "upper", "type": "molar",   "roots_expected": [3, 2, 1]},
    28: {"name_en": "Upper Left Third Molar",      "name_pt": "Terceiro Molar (Siso) Sup. Esq.",   "arch": "upper", "type": "molar",   "roots_expected": [1, 2, 3]},

    # Quadrant 3: Lower Left (Mandibular Left)
    31: {"name_en": "Lower Left Central Incisor",  "name_pt": "Incisivo Central Inferior Esquerdo","arch": "lower", "type": "incisor", "roots_expected": [1]},
    32: {"name_en": "Lower Left Lateral Incisor",  "name_pt": "Incisivo Lateral Inferior Esquerdo","arch": "lower", "type": "incisor", "roots_expected": [1]},
    33: {"name_en": "Lower Left Canine",           "name_pt": "Canino Inferior Esquerdo",          "arch": "lower", "type": "canine",  "roots_expected": [1]},
    34: {"name_en": "Lower Left First Premolar",   "name_pt": "Primeiro Pré-Molar Inf. Esquerdo",  "arch": "lower", "type": "premolar","roots_expected": [1, 2]},
    35: {"name_en": "Lower Left Second Premolar",  "name_pt": "Segundo Pré-Molar Inf. Esquerdo",   "arch": "lower", "type": "premolar","roots_expected": [1, 2]},
    36: {"name_en": "Lower Left First Molar",      "name_pt": "Primeiro Molar Inferior Esquerdo",  "arch": "lower", "type": "molar",   "roots_expected": [2, 3, 1]},
    37: {"name_en": "Lower Left Second Molar",     "name_pt": "Segundo Molar Inferior Esquerdo",   "arch": "lower", "type": "molar",   "roots_expected": [2, 1, 3]},
    38: {"name_en": "Lower Left Third Molar",      "name_pt": "Terceiro Molar (Siso) Inf. Esq.",   "arch": "lower", "type": "molar",   "roots_expected": [1, 2, 3]},

    # Quadrant 4: Lower Right (Mandibular Right)
    41: {"name_en": "Lower Right Central Incisor", "name_pt": "Incisivo Central Inferior Direito", "arch": "lower", "type": "incisor", "roots_expected": [1]},
    42: {"name_en": "Lower Right Lateral Incisor", "name_pt": "Incisivo Lateral Inferior Direito", "arch": "lower", "type": "incisor", "roots_expected": [1]},
    43: {"name_en": "Lower Right Canine",          "name_pt": "Canino Inferior Direito",          "arch": "lower", "type": "canine",  "roots_expected": [1]},
    44: {"name_en": "Lower Right First Premolar",  "name_pt": "Primeiro Pré-Molar Inf. Direito",   "arch": "lower", "type": "premolar","roots_expected": [1, 2]},
    45: {"name_en": "Lower Right Second Premolar", "name_pt": "Segundo Pré-Molar Inf. Direito",    "arch": "lower", "type": "premolar","roots_expected": [1, 2]},
    46: {"name_en": "Lower Right First Molar",     "name_pt": "Primeiro Molar Inferior Direito",   "arch": "lower", "type": "molar",   "roots_expected": [2, 3, 1]},
    47: {"name_en": "Lower Right Second Molar",    "name_pt": "Segundo Molar Inferior Direito",    "arch": "lower", "type": "molar",   "roots_expected": [2, 1, 3]},
    48: {"name_en": "Lower Right Third Molar",     "name_pt": "Terceiro Molar (Siso) Inf. Dir.",   "arch": "lower", "type": "molar",   "roots_expected": [1, 2, 3]}
}


def _isFdiTooth(value):
    return (11 <= value <= 28) or (31 <= value <= 48)


def _maxRootsForTooth(fdi):
    """Maximum anatomically plausible number of roots for a given FDI tooth."""
    num = fdi % 10
    if num in (1, 2, 3):
        return 1          # incisivos e caninos: raiz única
    if num in (4, 5):
        return 2          # pré-molares: 1 ou 2 raízes
    return 3              # molares: 1, 2 ou 3 raízes


# =============================================================================
# Main Module Class
# =============================================================================

class DentalRootApexDetector(ScriptedLoadableModule):
    """3D Slicer Extension for automatic dental root apex detection."""

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Dental Root Apex Detector"
        self.parent.categories = ["Dental", "Quantification"]
        self.parent.dependencies = []
        self.parent.contributors = ["Antigravity Dental AI Team", "Pedro", "ToothFairy2 Research"]
        self.parent.helpText = (
            "Esta extensão identifica automaticamente o ápice de cada raiz dentária "
            "a partir de segmentações 3D (ex: dataset ToothFairy2 / CBCT) e insere "
            "pontos fiduciais nativos do 3D Slicer (vtkMRMLMarkupsFiducialNode).\n\n"
            "Como funciona:\n"
            "- Para cada dente, o volume é percorrido da coroa em direção apical, fatia a fatia.\n"
            "- As ramificações radiculares são rastreadas por conectividade 2D entre fatias "
            "consecutivas (bifurcações/trifurcações são detectadas automaticamente).\n"
            "- Cada ramificação válida gera exatamente um ponto fiducial em seu ápice.\n"
            "- A direção anatômica (coroa x ápice) é determinada pela posição relativa das "
            "arcadas e pelo contato das raízes com o osso maxilar/mandibular.\n"
            "- As raízes são nomeadas anatomicamente (Mésio-Vestibular, Disto-Vestibular, "
            "Palatina, Mesial, Distal) a partir das coordenadas físicas RAS.\n\n"
            "Recursos:\n"
            "- Suporte completo à notação FDI (11-48)\n"
            "- Um fiducial por raiz (molares com 2-3 raízes, pré-molares com 2 raízes)\n"
            "- Filtro por arcada e por dentes específicos\n"
            "- Navegação nas fatias 2D ao clicar na tabela de resultados\n"
            "- Exportação para CSV e processamento em lote."
        )
        self.parent.acknowledgementText = (
            "Desenvolvido com base no dataset ToothFairy2 e nas diretrizes anatômicas odontológicas."
        )


# =============================================================================
# Widget Class (UI)
# =============================================================================

class DentalRootApexDetectorWidget(ScriptedLoadableModuleWidget):
    """GUI Widget for the Dental Root Apex Detector module."""

    def resourcePath(self, filename):
        """Override resourcePath to safely locate files even if module is loaded dynamically."""
        scriptedModulesPath = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(scriptedModulesPath, "Resources", filename)

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        self.logic = DentalRootApexDetectorLogic()
        self.currentResults = []
        self.currentMarkupsNode = None

        # ---------------------------------------------------------------------
        # Section 1: Input Segmentation / Volume
        # ---------------------------------------------------------------------
        inputCollapsibleButton = ctk.ctkCollapsibleButton()
        inputCollapsibleButton.text = "1. Entrada de Dados / Segmentação"
        self.layout.addWidget(inputCollapsibleButton)
        inputFormLayout = qt.QFormLayout(inputCollapsibleButton)

        # Mode selector (Scene node vs File on disk)
        self.inputSourceCombo = qt.QComboBox()
        self.inputSourceCombo.addItems(["Nó da Cena 3D Slicer (LabelMap ou Segmentação)", "Carregar Arquivo do Disco (Dataset .mha / .nii)"])
        self.inputSourceCombo.currentIndexChanged.connect(self.onInputSourceChanged)
        inputFormLayout.addRow("Origem dos dados:", self.inputSourceCombo)

        # Scene node selector (LabelMap Volume or Segmentation)
        self.labelMapSelector = slicer.qMRMLNodeComboBox()
        self.labelMapSelector.nodeTypes = ["vtkMRMLLabelMapVolumeNode", "vtkMRMLSegmentationNode"]
        self.labelMapSelector.selectNodeUponCreation = True
        self.labelMapSelector.addEnabled = False
        self.labelMapSelector.removeEnabled = False
        self.labelMapSelector.noneEnabled = False
        self.labelMapSelector.showHidden = False
        self.labelMapSelector.showChildNodeTypes = False
        self.labelMapSelector.setMRMLScene(slicer.mrmlScene)
        self.labelMapSelector.setToolTip("Selecione o LabelMap ou Segmentação com os dentes rotulados.")
        inputFormLayout.addRow("Segmentação na cena:", self.labelMapSelector)

        # File selector (Dataset path)
        self.filePathEdit = ctk.ctkPathLineEdit()
        self.filePathEdit.filters = ctk.ctkPathLineEdit.Files
        self.filePathEdit.nameFilters = ["Imagens Médicas (*.mha *.nii *.nii.gz *.nrrd)", "Todos os Arquivos (*)"]
        self.filePathEdit.setToolTip("Selecione o arquivo de segmentação (.mha) do dataset ToothFairy2.")
        self.filePathEdit.setVisible(False)
        self.loadFileButton = qt.QPushButton("Carregar Arquivo na Cena")
        self.loadFileButton.setIcon(qt.QIcon.fromTheme("document-open"))
        self.loadFileButton.clicked.connect(self.onLoadFileClicked)
        self.loadFileButton.setVisible(False)

        self.fileBoxWidget = qt.QWidget()
        fileBoxLayout = qt.QHBoxLayout(self.fileBoxWidget)
        fileBoxLayout.setContentsMargins(0, 0, 0, 0)
        fileBoxLayout.addWidget(self.filePathEdit)
        fileBoxLayout.addWidget(self.loadFileButton)
        inputFormLayout.addRow("Arquivo do dataset:", self.fileBoxWidget)
        self.fileBoxWidget.setVisible(False)

        # ---------------------------------------------------------------------
        # Section 2: Anatomical Filtering & Tooth Selection
        # ---------------------------------------------------------------------
        archCollapsibleButton = ctk.ctkCollapsibleButton()
        archCollapsibleButton.text = "2. Seleção Anatômica dos Dentes"
        self.layout.addWidget(archCollapsibleButton)
        archLayout = qt.QVBoxLayout(archCollapsibleButton)

        archRadioLayout = qt.QHBoxLayout()
        self.allTeethRadio = qt.QRadioButton("Todos os Dentes Presentes")
        self.allTeethRadio.setChecked(True)
        self.upperOnlyRadio = qt.QRadioButton("Arcada Superior (11-28)")
        self.lowerOnlyRadio = qt.QRadioButton("Arcada Inferior (31-48)")
        archRadioLayout.addWidget(self.allTeethRadio)
        archRadioLayout.addWidget(self.upperOnlyRadio)
        archRadioLayout.addWidget(self.lowerOnlyRadio)
        archLayout.addLayout(archRadioLayout)

        # Specific teeth filter
        self.filterSpecificCheck = qt.QCheckBox("Processar apenas dentes específicos (ex: 16, 26, 36, 46)")
        self.filterSpecificCheck.toggled.connect(self.onFilterSpecificToggled)
        archLayout.addWidget(self.filterSpecificCheck)

        self.specificTeethEdit = qt.QLineEdit()
        self.specificTeethEdit.setPlaceholderText("Ex: 11, 16, 26, 36, 46 (separados por vírgula)")
        self.specificTeethEdit.setEnabled(False)
        archLayout.addWidget(self.specificTeethEdit)

        # ---------------------------------------------------------------------
        # Section 3: Parameters & Algorithmic Options
        # ---------------------------------------------------------------------
        paramsCollapsibleButton = ctk.ctkCollapsibleButton()
        paramsCollapsibleButton.text = "3. Parâmetros Geométricos e Anatômicos"
        paramsCollapsibleButton.collapsed = True
        self.layout.addWidget(paramsCollapsibleButton)
        paramsLayout = qt.QFormLayout(paramsCollapsibleButton)

        self.trunkRatioSlider = ctk.ctkSliderWidget()
        self.trunkRatioSlider.singleStep = 0.05
        self.trunkRatioSlider.minimum = 0.20
        self.trunkRatioSlider.maximum = 0.60
        self.trunkRatioSlider.value = 0.40
        self.trunkRatioSlider.setToolTip(
            "Fração do dente (a partir da coroa) onde começa o rastreamento das raízes. "
            "Valores menores começam mais cedo (mais perto da coroa). 0,35-0,45 é o ideal."
        )
        paramsLayout.addRow("Início da Raiz (fração a partir da coroa):", self.trunkRatioSlider)

        self.minRootVolumeSpin = qt.QSpinBox()
        self.minRootVolumeSpin.setRange(3, 200)
        self.minRootVolumeSpin.setValue(15)
        self.minRootVolumeSpin.setToolTip("Volume mínimo em voxels de uma ramificação para ser considerada uma raiz anatômica válida.")
        paramsLayout.addRow("Volume Mínimo da Raiz (voxels):", self.minRootVolumeSpin)

        self.taperingRefinementCheck = qt.QCheckBox()
        self.taperingRefinementCheck.setChecked(True)
        self.taperingRefinementCheck.setToolTip("Centraliza o ponto fiducial no eixo do canal radicular usando transformada de distância no ápice.")
        paramsLayout.addRow("Refinamento por Estreitamento 3D:", self.taperingRefinementCheck)

        self.create3DSurfaceCheck = qt.QCheckBox()
        self.create3DSurfaceCheck.setChecked(True)
        self.create3DSurfaceCheck.setToolTip("Gera automaticamente os modelos de superfície 3D dos dentes para visualização imediata na janela 3D.")
        paramsLayout.addRow("Gerar Modelo 3D dos Dentes:", self.create3DSurfaceCheck)

        # ---------------------------------------------------------------------
        # Section 4: Fiducials Configuration
        # ---------------------------------------------------------------------
        fidCollapsibleButton = ctk.ctkCollapsibleButton()
        fidCollapsibleButton.text = "4. Marcadores Fiduciais (3D Slicer Markups)"
        self.layout.addWidget(fidCollapsibleButton)
        fidLayout = qt.QFormLayout(fidCollapsibleButton)

        self.fiducialSelector = slicer.qMRMLNodeComboBox()
        self.fiducialSelector.nodeTypes = ["vtkMRMLMarkupsFiducialNode"]
        self.fiducialSelector.selectNodeUponCreation = True
        self.fiducialSelector.addEnabled = True
        self.fiducialSelector.removeEnabled = True
        self.fiducialSelector.noneEnabled = True
        self.fiducialSelector.baseName = "Tooth_Root_Apices"
        self.fiducialSelector.setMRMLScene(slicer.mrmlScene)
        self.fiducialSelector.setToolTip("Lista de fiduciais onde os pontos dos ápices serão salvos.")
        fidLayout.addRow("Nó de fiduciais:", self.fiducialSelector)

        self.glyphScaleSpin = qt.QDoubleSpinBox()
        self.glyphScaleSpin.setRange(0.5, 15.0)
        self.glyphScaleSpin.setSingleStep(0.5)
        self.glyphScaleSpin.setValue(2.5)
        self.glyphScaleSpin.setSuffix(" mm")
        self.glyphScaleSpin.setToolTip("Tamanho do glifo fiducial nas fatias 2D e na visão 3D.")
        fidLayout.addRow("Escala do Marcador:", self.glyphScaleSpin)

        self.colorModeCombo = qt.QComboBox()
        self.colorModeCombo.addItems([
            "Diferenciar por Arcada (Superior = Ciano, Inferior = Laranja)",
            "Cor Única (Vermelho)",
            "Cor Única (Amarelo)"
        ])
        fidLayout.addRow("Esquema de Cores:", self.colorModeCombo)

        # ---------------------------------------------------------------------
        # Section 5: Execution Button & Progress
        # ---------------------------------------------------------------------
        self.runButton = qt.QPushButton("Identificar Ápices Radiculares Automaticamente")
        self.runButton.setIcon(qt.QIcon.fromTheme("system-run"))
        self.runButton.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px; background-color: #007ACC; color: white; border-radius: 6px;")
        self.runButton.clicked.connect(self.onRunButtonClicked)
        self.layout.addWidget(self.runButton)

        self.progressBar = qt.QProgressBar()
        self.progressBar.setVisible(False)
        self.layout.addWidget(self.progressBar)

        self.statusLabel = qt.QLabel("Aguardando execução...")
        self.statusLabel.setStyleSheet("font-style: italic; color: #666;")
        self.layout.addWidget(self.statusLabel)

        # ---------------------------------------------------------------------
        # Section 6: Interactive Results Table & Slice Navigation
        # ---------------------------------------------------------------------
        resultsCollapsibleButton = ctk.ctkCollapsibleButton()
        resultsCollapsibleButton.text = "5. Tabela de Ápices e Validação Visual"
        self.layout.addWidget(resultsCollapsibleButton)
        resultsLayout = qt.QVBoxLayout(resultsCollapsibleButton)

        # Navigation hint
        hintLabel = qt.QLabel("💡 Clique em qualquer linha da tabela para navegar automaticamente as fatias 2D até o ápice correspondente.")
        hintLabel.setStyleSheet("color: #005580; font-size: 11px; margin-bottom: 4px;")
        resultsLayout.addWidget(hintLabel)

        self.resultsTable = qt.QTableWidget()
        self.resultsTable.setColumnCount(6)
        self.resultsTable.setHorizontalHeaderLabels(["FDI", "Nome do Dente", "Raiz Identificada", "RAS (mm)", "IJK (voxel)", "Ação"])
        self.resultsTable.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.Stretch)
        self.resultsTable.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.resultsTable.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        self.resultsTable.itemSelectionChanged.connect(self.onTableRowSelected)
        resultsLayout.addWidget(self.resultsTable)

        # Export & Batch Buttons
        tableButtonsLayout = qt.QHBoxLayout()
        self.exportCsvButton = qt.QPushButton("Exportar Resultados (.CSV)")
        self.exportCsvButton.setIcon(qt.QIcon.fromTheme("document-save"))
        self.exportCsvButton.clicked.connect(self.onExportCsvClicked)
        self.exportCsvButton.setEnabled(False)

        self.batchButton = qt.QPushButton("Processamento em Lote (Dataset)...")
        self.batchButton.setIcon(qt.QIcon.fromTheme("system-run"))
        self.batchButton.clicked.connect(self.onBatchProcessClicked)

        tableButtonsLayout.addWidget(self.exportCsvButton)
        tableButtonsLayout.addWidget(self.batchButton)
        resultsLayout.addLayout(tableButtonsLayout)

        # Add vertical spacer
        self.layout.addStretch(1)

    # -------------------------------------------------------------------------
    # UI Callbacks
    # -------------------------------------------------------------------------

    def onInputSourceChanged(self, index):
        isFile = (index == 1)
        self.labelMapSelector.setVisible(not isFile)
        self.fileBoxWidget.setVisible(isFile)
        self.filePathEdit.setVisible(isFile)
        self.loadFileButton.setVisible(isFile)

    def onFilterSpecificToggled(self, checked):
        self.specificTeethEdit.setEnabled(checked)

    def onLoadFileClicked(self):
        filePath = self.filePathEdit.currentPath
        if not filePath or not os.path.exists(filePath):
            slicer.util.errorDisplay("Por favor, selecione um arquivo válido (.mha, .nii, etc.) do dataset.")
            return

        self.statusLabel.setText(f"Carregando {os.path.basename(filePath)}...")
        slicer.app.processEvents()

        try:
            loadedNode = slicer.util.loadLabelVolume(filePath)
            if loadedNode:
                self.labelMapSelector.setCurrentNode(loadedNode)
                self.inputSourceCombo.setCurrentIndex(0) # switch back to scene view
                self.statusLabel.setText(f"Arquivo carregado com sucesso: {loadedNode.GetName()}")
            else:
                slicer.util.errorDisplay(f"Não foi possível carregar o arquivo: {filePath}")
        except Exception as e:
            slicer.util.errorDisplay(f"Erro ao carregar arquivo: {str(e)}")

    def onRunButtonClicked(self):
        inputNode = self.labelMapSelector.currentNode()
        if not inputNode:
            slicer.util.errorDisplay("Por favor, selecione ou carregue um nó de LabelMap ou Segmentação.")
            return

        # Prepare markups node
        markupsNode = self.fiducialSelector.currentNode()
        if not markupsNode:
            markupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Tooth_Root_Apices")
            self.fiducialSelector.setCurrentNode(markupsNode)
        else:
            markupsNode.RemoveAllControlPoints()

        self.currentMarkupsNode = markupsNode

        # Determine teeth filter
        teethFilter = None
        if self.upperOnlyRadio.isChecked():
            teethFilter = [t for t in range(11, 29)]
        elif self.lowerOnlyRadio.isChecked():
            teethFilter = [t for t in range(31, 49)]
        elif self.filterSpecificCheck.isChecked():
            text = self.specificTeethEdit.text.strip()
            if text:
                try:
                    teethFilter = [int(x.strip()) for x in text.split(",") if x.strip()]
                except Exception:
                    slicer.util.errorDisplay("Formato inválido para dentes específicos. Use números separados por vírgula (ex: 16, 26, 36).")
                    return

        # Parameters
        params = {
            "trunk_ratio": self.trunkRatioSlider.value,
            "min_root_volume": self.minRootVolumeSpin.value,
            "refine_tapering": self.taperingRefinementCheck.isChecked(),
            "create_3d": self.create3DSurfaceCheck.isChecked(),
            "glyph_scale": self.glyphScaleSpin.value,
            "color_mode": self.colorModeCombo.currentIndex,
            "teeth_filter": teethFilter
        }

        # Progress setup
        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)
        self.runButton.setEnabled(False)
        self.statusLabel.setText("Iniciando detecção geométrica dos ápices...")
        slicer.app.processEvents()

        t0 = time.time()
        try:
            results = self.logic.run(
                inputNode=inputNode,
                markupsNode=markupsNode,
                params=params,
                progressCallback=self.onProgressUpdate
            )
            elapsed = time.time() - t0
            self.currentResults = results
            self.updateResultsTable(results)
            self.exportCsvButton.setEnabled(len(results) > 0)
            self.statusLabel.setText(f"Concluído! {len(results)} ápices identificados em {elapsed:.2f}s.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            slicer.util.errorDisplay(f"Erro durante o processamento: {str(e)}")
            self.statusLabel.setText("Erro durante o processamento.")
        finally:
            self.progressBar.setVisible(False)
            self.runButton.setEnabled(True)

    def onProgressUpdate(self, percent, message):
        self.progressBar.setValue(int(percent))
        self.statusLabel.setText(message)
        slicer.app.processEvents()

    def updateResultsTable(self, results):
        self.resultsTable.setRowCount(len(results))
        for row, res in enumerate(results):
            # FDI
            fdiItem = qt.QTableWidgetItem(str(res["fdi"]))
            fdiItem.setTextAlignment(qt.Qt.AlignCenter)
            self.resultsTable.setItem(row, 0, fdiItem)

            # Tooth Name
            nameItem = qt.QTableWidgetItem(res["tooth_name"])
            self.resultsTable.setItem(row, 1, nameItem)

            # Root Name
            rootItem = qt.QTableWidgetItem(res["root_label"])
            self.resultsTable.setItem(row, 2, rootItem)

            # RAS
            ras = res["ras"]
            rasStr = f"({ras[0]:.1f}, {ras[1]:.1f}, {ras[2]:.1f})"
            rasItem = qt.QTableWidgetItem(rasStr)
            rasItem.setTextAlignment(qt.Qt.AlignCenter)
            self.resultsTable.setItem(row, 3, rasItem)

            # IJK
            ijk = res["ijk"]
            ijkStr = f"({ijk[0]:.0f}, {ijk[1]:.0f}, {ijk[2]:.0f})"
            ijkItem = qt.QTableWidgetItem(ijkStr)
            ijkItem.setTextAlignment(qt.Qt.AlignCenter)
            self.resultsTable.setItem(row, 4, ijkItem)

            # Jump button
            jumpBtn = qt.QPushButton("Visualizar")
            jumpBtn.setIcon(qt.QIcon.fromTheme("go-jump"))
            jumpBtn.clicked.connect(lambda _, r=res: self.jumpToApex(r))
            self.resultsTable.setCellWidget(row, 5, jumpBtn)

    def onTableRowSelected(self):
        selectedRows = self.resultsTable.selectionModel().selectedRows()
        if not selectedRows:
            return
        row = selectedRows[0].row()
        if 0 <= row < len(self.currentResults):
            self.jumpToApex(self.currentResults[row])

    def jumpToApex(self, res):
        ras = res["ras"]
        # Jump slices to RAS location
        markupsLogic = slicer.modules.markups.logic()
        markupsLogic.JumpSlicesToLocation(ras[0], ras[1], ras[2], True)

    def onExportCsvClicked(self):
        if not self.currentResults:
            return
        defaultPath = os.path.join(slicer.app.temporaryPath, "tooth_root_apices.csv")
        filePath = qt.QFileDialog.getSaveFileName(
            None, "Salvar Resultados como CSV", defaultPath, "Arquivo CSV (*.csv)"
        )
        if filePath:
            self.logic.exportResultsToCsv(self.currentResults, filePath)
            slicer.util.infoDisplay(f"Resultados exportados com sucesso para:\n{filePath}")

    def onBatchProcessClicked(self):
        dirPath = qt.QFileDialog.getExistingDirectory(
            None, "Selecione o diretório contendo segmentações (labelsTr)", ""
        )
        if not dirPath:
            return

        mhaFiles = [os.path.join(dirPath, f) for f in os.listdir(dirPath) if f.endswith(".mha") or f.endswith(".nii") or f.endswith(".nii.gz")]
        if not mhaFiles:
            slicer.util.errorDisplay("Nenhum arquivo .mha ou .nii encontrado na pasta selecionada.")
            return

        confirm = slicer.util.confirmYesNoDisplay(
            f"Foram encontrados {len(mhaFiles)} arquivos para processamento.\n"
            "Deseja iniciar o processamento em lote e gerar o relatório consolidado em CSV?"
        )
        if not confirm:
            return

        outCsvPath = os.path.join(dirPath, "dataset_all_apices.csv")
        self.progressBar.setVisible(True)
        self.statusLabel.setText("Executando processamento em lote...")
        slicer.app.processEvents()

        try:
            totalCount = self.logic.batchProcessFolder(
                mhaFiles, outCsvPath,
                progressCallback=self.onProgressUpdate
            )
            slicer.util.infoDisplay(
                f"Processamento em lote concluído com sucesso!\n\n"
                f"Arquivos processados: {len(mhaFiles)}\n"
                f"Total de ápices detectados: {totalCount}\n"
                f"Arquivo gerado: {outCsvPath}"
            )
        except Exception as e:
            slicer.util.errorDisplay(f"Erro no processamento em lote: {str(e)}")
        finally:
            self.progressBar.setVisible(False)
            self.statusLabel.setText("Pronto.")


# =============================================================================
# Logic Class (Headless Algorithmic Core)
# =============================================================================

class DentalRootApexDetectorLogic(ScriptedLoadableModuleLogic):
    """Core computational logic for 3D tooth root apex localization."""

    def run(self, inputNode, markupsNode, params=None, progressCallback=None):
        """
        Executes apex detection on inputNode (LabelMap or SegmentationNode)
        and populates markupsNode with one fiducial per detected root.
        """
        if params is None:
            params = {}

        trunkRatio = params.get("trunk_ratio", 0.40)
        minRootVolume = params.get("min_root_volume", 15)
        refineTapering = params.get("refine_tapering", True)
        create3D = params.get("create_3d", True)
        teethFilter = params.get("teeth_filter", None)

        # 1. Extract per-tooth cropped masks and voxel-to-RAS converter
        records, voxel_to_ras, segNode, boneMasks = self.extractTeeth(inputNode, create3D)

        if teethFilter:
            records = [r for r in records if r["fdi"] in teethFilter]
        records.sort(key=lambda r: r["fdi"])

        if not records:
            raise ValueError(
                "Nenhum dente com rotulação FDI (11-48) encontrado na segmentação fornecida."
            )

        # 2. Determine arch orientation along the slice (k) axis
        upperAtLowK = self.determineUpperAtLowK(records)

        # 3. Estimate the dental arch midline in physical R (right-left) coordinate
        midlineR = self.estimateMidlineR(records, voxel_to_ras)

        # 4. Detect apices for each tooth
        results = []
        totalTeeth = len(records)

        for idx, rec in enumerate(records):
            tLabel = rec["fdi"]
            toothInfo = FDI_TEETH_INFO.get(tLabel, {
                "name_en": f"Tooth {tLabel}", "name_pt": f"Dente {tLabel}",
                "arch": "upper" if 11 <= tLabel <= 28 else "lower",
                "type": "unknown", "roots_expected": [1]
            })

            if progressCallback:
                pct = (idx / float(totalTeeth)) * 90.0
                progressCallback(pct, f"Analisando Dente {tLabel} ({toothInfo['name_pt']})...")

            isUpper = (11 <= tLabel <= 28)
            apexDir = self.determineApexDirection(rec, isUpper, upperAtLowK, boneMasks)

            # Track individual roots and apical tips
            detectedRoots = self.detectToothApices(
                rec=rec,
                apexDir=apexDir,
                trunkRatio=trunkRatio,
                minRootVolume=minRootVolume,
                refineTapering=refineTapering,
                maxRoots=_maxRootsForTooth(tLabel)
            )

            # Convert IJK coordinates to physical RAS and assign anatomical names
            rootsWithRas = []
            for rData in detectedRoots:
                kji = rData["kji"]
                ras = voxel_to_ras(kji[0], kji[1], kji[2])
                rootsWithRas.append({"kji": kji, "ras": ras, "volume": rData["volume"]})

            namedRoots = self.assignAnatomicalNames(tLabel, rootsWithRas, midlineR)

            for named in namedRoots:
                kji = named["kji"]
                results.append({
                    "fdi": tLabel,
                    "tooth_name": toothInfo["name_pt"],
                    "tooth_name_en": toothInfo["name_en"],
                    "arch": toothInfo["arch"],
                    "root_label": named["root_name"],
                    "full_marker_name": named["full_marker_name"],
                    "description": named["description"],
                    "ijk": np.array([kji[2], kji[1], kji[0]], dtype=np.float64),
                    "ras": named["ras"]
                })

        # 5. Add fiducial points to 3D Slicer Markups Node
        if progressCallback:
            progressCallback(92.0, "Inserindo pontos fiduciais no 3D Slicer...")
        self.populateMarkupsNode(markupsNode, results, params)

        # 6. Create 3D closed surfaces if requested
        if create3D and segNode is not None:
            if progressCallback:
                progressCallback(96.0, "Construindo modelos de superfície 3D...")
            self.generate3DSurfaces(segNode)

        if progressCallback:
            progressCallback(100.0, "Detecção finalizada com sucesso!")

        return results

    # -------------------------------------------------------------------------
    # Input Extraction (preserves original FDI label values)
    # -------------------------------------------------------------------------

    def extractTeeth(self, inputNode, create3DSurface=False):
        """
        Extracts per-tooth binary masks (cropped to their bounding boxes) plus a
        voxel -> RAS converter. Returns:
            records: list of {"fdi": int, "sub": np.bool array, "bbox": (k0,k1,j0,j1,i0,i1)}
            voxel_to_ras: callable (k, j, i) -> [R, A, S]
            segNode: segmentation node used for 3D surfaces (or None)
            boneMasks: {"upper": maxilla mask or None, "lower": mandible mask or None}
        """
        records = []
        segNode = None
        boneMasks = {"upper": None, "lower": None}

        if inputNode.IsA("vtkMRMLLabelMapVolumeNode"):
            arr = slicer.util.arrayFromVolume(inputNode)
            mat = vtk.vtkMatrix4x4()
            inputNode.GetIJKToRASMatrix(mat)

            def voxel_to_ras(k, j, i):
                p = mat.MultiplyPoint([float(i), float(j), float(k), 1.0])
                return [p[0], p[1], p[2]]

            # Jaw bones: dataset.json label 2 = Maxilla, label 1 = Mandible
            maxilla = (arr == 2)
            mandible = (arr == 1)
            boneMasks["upper"] = maxilla if np.any(maxilla) else None
            boneMasks["lower"] = mandible if np.any(mandible) else None

            for rawVal in np.unique(arr):
                val = int(rawVal)
                if not _isFdiTooth(val):
                    continue
                rec = self._makeToothRecordFromLabelArray(arr, val)
                if rec is not None:
                    rec["fdi"] = val
                    records.append(rec)

            if create3DSurface:
                segNode = slicer.mrmlScene.AddNewNodeByClass(
                    "vtkMRMLSegmentationNode", f"{inputNode.GetName()}_3D_Surfaces")
                slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(inputNode, segNode)

        elif inputNode.IsA("vtkMRMLSegmentationNode"):
            segNode = inputNode
            segmentation = segNode.GetSegmentation()
            if segmentation.GetNumberOfSegments() == 0:
                raise ValueError("A segmentação selecionada não contém segmentos.")

            # Use the first segment's internal binary labelmap. In shared-labelmap
            # segmentations (e.g. ToothFairy2 loader) this array contains ALL label
            # values, so FDI identities are preserved exactly.
            seg0_id = segmentation.GetNthSegmentID(0)
            seg0 = segmentation.GetSegment(seg0_id)
            sharedArr = slicer.util.arrayFromSegmentInternalBinaryLabelmap(segNode, seg0_id)
            labelmapRep = seg0.GetRepresentation(
                slicer.vtkSegmentationConverter.GetSegmentationBinaryLabelmapRepresentationName())
            ext = labelmapRep.GetExtent()
            mat = vtk.vtkMatrix4x4()
            labelmapRep.GetImageToWorldMatrix(mat)

            def voxel_to_ras(k, j, i):
                xVox = float(i + ext[0])
                yVox = float(j + ext[2])
                zVox = float(k + ext[4])
                p = mat.MultiplyPoint([xVox, yVox, zVox, 1.0])
                return [p[0], p[1], p[2]]

            # Jaw bones (labels 1/2) when available in the shared labelmap
            maxilla = (sharedArr == 2)
            mandible = (sharedArr == 1)
            boneMasks["upper"] = maxilla if np.any(maxilla) else None
            boneMasks["lower"] = mandible if np.any(mandible) else None

            seen = set()
            for sIdx in range(segmentation.GetNumberOfSegments()):
                seg = segmentation.GetNthSegment(sIdx)
                segId = segmentation.GetNthSegmentID(sIdx)
                labelValue = int(seg.GetLabelValue()) if seg.GetLabelValue() is not None else 0

                fdi = None
                if _isFdiTooth(labelValue):
                    fdi = labelValue
                else:
                    # Fallback: parse the FDI prefix from names like "11: Incisivo..."
                    try:
                        prefix = int(str(seg.GetName()).split(":")[0].strip())
                        if _isFdiTooth(prefix):
                            fdi = prefix
                    except Exception:
                        pass

                if fdi is None or fdi in seen:
                    continue

                # Prefer the shared multi-label array (preserves the original value)
                if _isFdiTooth(labelValue) and np.any(sharedArr == labelValue):
                    rec = self._makeToothRecordFromLabelArray(sharedArr, labelValue)
                else:
                    indivArr = slicer.util.arrayFromSegmentInternalBinaryLabelmap(segNode, segId)
                    rec = self._makeToothRecordFromBinaryMask(indivArr > 0)

                if rec is not None:
                    rec["fdi"] = fdi
                    records.append(rec)
                    seen.add(fdi)

            if create3DSurface:
                segNode.CreateClosedSurfaceRepresentation()

        else:
            raise TypeError("O nó de entrada deve ser vtkMRMLLabelMapVolumeNode ou vtkMRMLSegmentationNode.")

        return records, voxel_to_ras, segNode, boneMasks

    def _makeToothRecordFromLabelArray(self, arr, value):
        """Builds a cropped mask record for one label value of a multi-label array."""
        eq = (arr == value)
        if not np.any(eq):
            return None
        return self._makeToothRecordFromBinaryMask(eq)

    def _makeToothRecordFromBinaryMask(self, mask):
        """Crops a binary mask to its bounding box and removes insignificant islands."""
        if not np.any(mask):
            return None

        kIdx = np.flatnonzero(np.any(mask, axis=(1, 2)))
        jIdx = np.flatnonzero(np.any(mask, axis=(0, 2)))
        iIdx = np.flatnonzero(np.any(mask, axis=(0, 1)))
        if kIdx.size == 0:
            return None

        k0, k1 = int(kIdx[0]), int(kIdx[-1])
        j0, j1 = int(jIdx[0]), int(jIdx[-1])
        i0, i1 = int(iIdx[0]), int(iIdx[-1])

        sub = np.ascontiguousarray(mask[k0:k1 + 1, j0:j1 + 1, i0:i1 + 1])

        # Remove insignificant 3D islands (label noise, stray fragments) while
        # keeping genuinely large disconnected portions.
        lbl, num = ndimage.label(sub, structure=np.ones((3, 3, 3)))
        if num > 1:
            sizes = ndimage.sum(sub, lbl, index=np.arange(1, num + 1))
            maxSize = float(np.max(sizes)) if len(sizes) else 0.0
            keep = np.zeros(num + 1, dtype=bool)
            for c in range(1, num + 1):
                if sizes[c - 1] >= max(50.0, 0.05 * maxSize):
                    keep[c] = True
            sub = keep[lbl]

            pts = np.nonzero(sub)
            if len(pts[0]) == 0:
                return None
            lk0, lk1 = int(pts[0].min()), int(pts[0].max())
            lj0, lj1 = int(pts[1].min()), int(pts[1].max())
            li0, li1 = int(pts[2].min()), int(pts[2].max())
            sub = np.ascontiguousarray(sub[lk0:lk1 + 1, lj0:lj1 + 1, li0:li1 + 1])
            k0 += lk0
            j0 += lj0
            i0 += li0

        return {
            "sub": sub,
            "bbox": (k0, k0 + sub.shape[0] - 1,
                     j0, j0 + sub.shape[1] - 1,
                     i0, i0 + sub.shape[2] - 1)
        }

    # -------------------------------------------------------------------------
    # Anatomical Orientation
    # -------------------------------------------------------------------------

    def determineUpperAtLowK(self, records):
        """
        Returns True if maxillary teeth are on the low-k side of the volume,
        False if they are on the high-k side, or None if only one arch is present.
        """
        upper = [r for r in records if 11 <= r["fdi"] <= 28]
        lower = [r for r in records if 31 <= r["fdi"] <= 48]
        if not upper or not lower:
            return None

        def meanK(rec):
            pts = np.nonzero(rec["sub"])
            return float(pts[0].mean()) + rec["bbox"][0]

        meanUpper = float(np.mean([meanK(r) for r in upper]))
        meanLower = float(np.mean([meanK(r) for r in lower]))
        return bool(meanUpper < meanLower)

    def determineApexDirection(self, rec, isUpper, upperAtLowK, boneMasks):
        """
        Returns -1 if root apices lie toward lower slice indices (k),
        or +1 if they lie toward higher slice indices.
        """
        # Rule 1 (most reliable): relative position of both dental arches.
        # Roots always point away from the occlusal plane, i.e. away from the
        # opposite arch.
        if upperAtLowK is not None:
            return -1 if (isUpper == upperAtLowK) else 1

        # Rule 2: roots are embedded in bone while crowns protrude into the
        # oral cavity. Compare bone contact near both tooth ends.
        bone = boneMasks.get("upper" if isUpper else "lower") if boneMasks else None
        if bone is None and boneMasks:
            bone = boneMasks.get("upper") if boneMasks.get("upper") is not None else boneMasks.get("lower")
        if bone is not None:
            direction = self._apexDirectionFromBoneContact(rec, bone)
            if direction is not None:
                return direction

        # Rule 3 (fallback): the crown is bulky, so the tooth centroid is biased
        # toward it; the apex lies at the farthest end from the centroid.
        pts = np.nonzero(rec["sub"])
        kMin, kMax = int(pts[0].min()), int(pts[0].max())
        if kMax - kMin < 2:
            return -1 if isUpper else 1
        centroidK = float(pts[0].mean())
        return -1 if (centroidK - kMin) > (kMax - centroidK) else 1

    def _apexDirectionFromBoneContact(self, rec, boneMask):
        """Compares jaw-bone contact at both tooth ends (roots are inside bone)."""
        sub = rec["sub"]
        bbox = rec["bbox"]
        pad = 6

        K0 = max(0, bbox[0] - pad)
        K1 = min(boneMask.shape[0] - 1, bbox[1] + pad)
        J0 = max(0, bbox[2] - pad)
        J1 = min(boneMask.shape[1] - 1, bbox[3] + pad)
        I0 = max(0, bbox[4] - pad)
        I1 = min(boneMask.shape[2] - 1, bbox[5] + pad)

        boneCrop = boneMask[K0:K1 + 1, J0:J1 + 1, I0:I1 + 1]
        boneDilated = ndimage.binary_dilation(
            boneCrop, structure=np.ones((3, 3, 3)), iterations=2)

        toothCrop = np.zeros(boneDilated.shape, dtype=bool)
        offK = bbox[0] - K0
        offJ = bbox[2] - J0
        offI = bbox[4] - I0
        toothCrop[offK:offK + sub.shape[0],
                  offJ:offJ + sub.shape[1],
                  offI:offI + sub.shape[2]] = sub

        kList = []
        contactList = []
        for lk in range(toothCrop.shape[0]):
            sl = toothCrop[lk]
            n = int(np.sum(sl))
            if n == 0:
                continue
            kList.append(lk + K0)
            contactList.append(int(np.logical_and(sl, boneDilated[lk]).sum()) / float(n))

        if not kList:
            return None

        kArr = np.asarray(kList, dtype=float)
        cArr = np.asarray(contactList, dtype=float)
        loEnd = kArr.min() + 0.30 * (kArr.max() - kArr.min())
        hiEnd = kArr.max() - 0.30 * (kArr.max() - kArr.min())
        loContact = float(cArr[kArr <= loEnd].mean()) if np.any(kArr <= loEnd) else 0.0
        hiContact = float(cArr[kArr >= hiEnd].mean()) if np.any(kArr >= hiEnd) else 0.0

        if abs(loContact - hiContact) < 0.02:
            return None
        return -1 if loContact > hiContact else 1

    def estimateMidlineR(self, records, voxel_to_ras):
        """Estimates the dental arch midline R coordinate (mm) from anterior teeth."""
        anterior = [r for r in records if (r["fdi"] % 10) in (1, 2, 3)]
        targets = anterior if anterior else records

        rValues = []
        for rec in targets:
            pts = np.nonzero(rec["sub"])
            bbox = rec["bbox"]
            k = float(pts[0].mean()) + bbox[0]
            j = float(pts[1].mean()) + bbox[2]
            i = float(pts[2].mean()) + bbox[4]
            rValues.append(voxel_to_ras(k, j, i)[0])

        return float(np.mean(rValues)) if rValues else 0.0

    # -------------------------------------------------------------------------
    # Root Branch Tracking and Apex Localization
    # -------------------------------------------------------------------------

    def detectToothApices(self, rec, apexDir, trunkRatio=0.40,
                          minRootVolume=15, refineTapering=True, maxRoots=3):
        """
        Tracks root branches slice by slice from the crown toward the apex.
        Each tracked branch yields one apical fiducial, so multi-rooted teeth
        get exactly one point per root.

        Returns a list of {"kji": np.array([k, j, i]), "volume": int, "slices": int}
        in global array coordinates.
        """
        sub = rec["sub"]
        bbox = rec["bbox"]
        nk = sub.shape[0]
        span = nk - 1

        # Degenerate tooth (few slices): fall back to the apex-side extreme slice
        if span < 3:
            pts = np.nonzero(sub)
            extK = int(pts[0].min()) if apexDir == -1 else int(pts[0].max())
            sel = (pts[0] == extK)
            return [{
                "kji": np.array([float(pts[0][sel].mean()) + bbox[0],
                                 float(pts[1][sel].mean()) + bbox[2],
                                 float(pts[2][sel].mean()) + bbox[4]]),
                "volume": int(len(pts[0])),
                "slices": int(nk)
            }]

        # Start slice: inside the root trunk, `trunkRatio` away from the crown
        offset = int(round(trunkRatio * span))
        offset = max(0, min(offset, span - 2))
        if apexDir == -1:
            startK = span - offset   # crown at high k, move toward low k
            stopK = -1
            step = -1
        else:
            startK = offset          # crown at low k, move toward high k
            stopK = nk
            step = 1

        structure8 = np.ones((3, 3), dtype=bool)

        def componentsAt(k):
            sl = sub[k]
            if not np.any(sl):
                return []
            lbl, num = ndimage.label(sl, structure=structure8)
            comps = []
            for c in range(1, num + 1):
                cMask = (lbl == c)
                cSum = int(np.sum(cMask))
                if cSum >= 2:
                    comps.append({
                        "mask": cMask,
                        "pts": np.argwhere(cMask),
                        "sum": cSum
                    })
            return comps

        active = []
        finished = []
        branchCounter = 0

        for comp in componentsAt(startK):
            branchCounter += 1
            center = comp["pts"].mean(axis=0)
            active.append({
                "id": branchCounter,
                "mask": comp["mask"],
                "center": center,
                "tipK": startK,
                "tipMask": comp["mask"],
                "tipPts": comp["pts"],
                "volume": comp["sum"],
                "slices": 1
            })

        if not active:
            # Fallback: whole extreme slice along the apex direction
            extK = 0 if apexDir == -1 else nk - 1
            while extK >= 0 and extK < nk and not np.any(sub[extK]):
                extK += step
            if extK < 0 or extK >= nk:
                extK = startK
            pts = np.argwhere(sub[extK])
            return [{
                "kji": np.array([float(extK) + bbox[0],
                                 float(pts[:, 0].mean()) + bbox[2],
                                 float(pts[:, 1].mean()) + bbox[4]]),
                "volume": int(len(pts)),
                "slices": 1
            }]

        for k in range(startK + step, stopK, step):
            comps = componentsAt(k)
            if not comps:
                finished.extend(active)
                active = []
                if not np.any(sub[k]):
                    break
                continue

            unmatched = list(range(len(comps)))
            newActive = []

            for branch in active:
                bestIdx = None
                bestOverlap = 0
                for idx in unmatched:
                    overlap = int(np.logical_and(branch["mask"], comps[idx]["mask"]).sum())
                    if overlap > bestOverlap:
                        bestOverlap = overlap
                        bestIdx = idx

                # Fallback for abrupt curvature / small displacement
                if bestIdx is None:
                    minDist = float("inf")
                    for idx in unmatched:
                        cCenter = comps[idx]["pts"].mean(axis=0)
                        dist = float(np.linalg.norm(branch["center"] - cCenter))
                        if dist < 14.0 and dist < minDist:
                            minDist = dist
                            bestIdx = idx

                if bestIdx is not None:
                    comp = comps[bestIdx]
                    unmatched.remove(bestIdx)
                    branch["mask"] = comp["mask"]
                    branch["center"] = comp["pts"].mean(axis=0)
                    branch["tipK"] = k
                    branch["tipMask"] = comp["mask"]
                    branch["tipPts"] = comp["pts"]
                    branch["volume"] += comp["sum"]
                    branch["slices"] += 1
                    newActive.append(branch)
                else:
                    finished.append(branch)

            # Remaining components are new branches (bifurcation/trifurcation)
            for idx in unmatched:
                comp = comps[idx]
                branchCounter += 1
                center = comp["pts"].mean(axis=0)
                newActive.append({
                    "id": branchCounter,
                    "mask": comp["mask"],
                    "center": center,
                    "tipK": k,
                    "tipMask": comp["mask"],
                    "tipPts": comp["pts"],
                    "volume": comp["sum"],
                    "slices": 1
                })

            active = newActive

        finished.extend(active)

        # Keep only anatomically meaningful branches
        valid = [b for b in finished
                 if b["slices"] >= 3 and b["volume"] >= max(8, minRootVolume)]
        if not valid and finished:
            valid = [max(finished, key=lambda b: b["volume"])]

        # Refine apex position and merge branches that end at the same place
        refined = []
        for branch in sorted(valid, key=lambda b: b["volume"], reverse=True):
            tipK = branch["tipK"]
            tipMask = branch["tipMask"]
            tipPts = branch["tipPts"]

            if refineTapering and len(tipPts) > 3:
                edt = ndimage.distance_transform_edt(tipMask)
                idxMax = np.unravel_index(np.argmax(edt), edt.shape)
                tipJ = float(idxMax[0])
                tipI = float(idxMax[1])
            else:
                tipJ = float(tipPts[:, 0].mean())
                tipI = float(tipPts[:, 1].mean())

            kji = np.array([float(tipK), tipJ, tipI])
            isDuplicate = False
            for existing in refined:
                if float(np.linalg.norm(kji - existing["localKji"])) < 6.0:
                    isDuplicate = True
                    break

            if not isDuplicate:
                refined.append({
                    "localKji": kji,
                    "kji": np.array([kji[0] + bbox[0], kji[1] + bbox[2], kji[2] + bbox[4]]),
                    "volume": int(branch["volume"]),
                    "slices": int(branch["slices"])
                })

        # Enforce the anatomically plausible maximum number of roots
        refined = refined[:maxRoots]

        return [{"kji": r["kji"], "volume": r["volume"], "slices": r["slices"]} for r in refined]

    # -------------------------------------------------------------------------
    # Anatomical Root Naming (in physical RAS coordinates)
    # -------------------------------------------------------------------------

    def assignAnatomicalNames(self, fdi, roots, midlineR):
        """
        Names each detected root anatomically (Mesiobuccal, Distobuccal, Palatal,
        Mesial, Distal, Buccal, Lingual) from RAS geometry.
        roots: list of {"kji": array, "ras": [R, A, S], "volume": int}
        """
        n = len(roots)
        if n == 0:
            return []

        if n == 1:
            r = roots[0]
            return [{
                "kji": r["kji"],
                "ras": r["ras"],
                "root_name": "Ápice Único",
                "full_marker_name": f"{fdi}_Apex",
                "description": f"Dente {fdi} - Ápice Radicular Único"
            }]

        isUpper = (11 <= fdi <= 28)
        toothNum = fdi % 10
        rasList = [r["ras"] for r in roots]

        def makeRoot(idx, rootName, code, description):
            return {
                "kji": roots[idx]["kji"],
                "ras": roots[idx]["ras"],
                "root_name": rootName,
                "full_marker_name": f"{fdi}_{code}_Apex",
                "description": f"Dente {fdi} - {description}"
            }

        # ------------------------------------------------------------------
        # Maxillary molars (16, 17, 18, 26, 27, 28)
        # ------------------------------------------------------------------
        if isUpper and toothNum in (6, 7, 8):
            if n >= 3:
                # Palatal root is the closest to the sagittal midline
                dMid = [abs(r[0] - midlineR) for r in rasList]
                palatalIdx = int(np.argmin(dMid))
                buccalIdx = [i for i in range(n) if i != palatalIdx]

                # Mesial is anterior (larger A), distal is posterior (smaller A)
                if rasList[buccalIdx[0]][1] > rasList[buccalIdx[1]][1]:
                    mbIdx, dbIdx = buccalIdx[0], buccalIdx[1]
                else:
                    mbIdx, dbIdx = buccalIdx[1], buccalIdx[0]

                return [
                    makeRoot(mbIdx, "Mésio-Vestibular (MV)", "MV", "Ápice Raiz Mésio-Vestibular"),
                    makeRoot(dbIdx, "Disto-Vestibular (DV)", "DV", "Ápice Raiz Disto-Vestibular"),
                    makeRoot(palatalIdx, "Palatina (P)", "P", "Ápice Raiz Palatina")
                ]

            if n == 2:
                dMid = [abs(r[0] - midlineR) for r in rasList]
                palatalIdx = int(np.argmin(dMid))
                buccalIdx = 1 - palatalIdx
                return [
                    makeRoot(buccalIdx, "Vestibular (V)", "V", "Ápice Raiz Vestibular"),
                    makeRoot(palatalIdx, "Palatina (P)", "P", "Ápice Raiz Palatina")
                ]

        # ------------------------------------------------------------------
        # Mandibular molars (36, 37, 38, 46, 47, 48)
        # ------------------------------------------------------------------
        if (not isUpper) and toothNum in (6, 7, 8):
            if n == 2:
                # Mesial is anterior (larger A)
                if rasList[0][1] > rasList[1][1]:
                    mIdx, dIdx = 0, 1
                else:
                    mIdx, dIdx = 1, 0
                return [
                    makeRoot(mIdx, "Mesial (M)", "M", "Ápice Raiz Mesial"),
                    makeRoot(dIdx, "Distal (D)", "D", "Ápice Raiz Distal")
                ]

            if n >= 3:
                # Radix entomolaris: mesial root is the most anterior one
                sortedByA = sorted(range(n), key=lambda i: rasList[i][1], reverse=True)
                mIdx = sortedByA[0]
                distalIdx = sortedByA[1:3]
                dMid = [abs(rasList[i][0] - midlineR) for i in distalIdx]
                dlIdx = distalIdx[int(np.argmin(dMid))]
                dvIdx = distalIdx[int(np.argmax(dMid))]
                return [
                    makeRoot(mIdx, "Mesial (M)", "M", "Ápice Raiz Mesial"),
                    makeRoot(dvIdx, "Disto-Vestibular (DV)", "DV", "Ápice Raiz Disto-Vestibular"),
                    makeRoot(dlIdx, "Disto-Lingual / Radix (DL)", "DL", "Ápice Radix Entomolaris")
                ]

        # ------------------------------------------------------------------
        # Maxillary premolars (14, 15, 24, 25)
        # ------------------------------------------------------------------
        if isUpper and toothNum in (4, 5):
            if n == 2:
                dMid = [abs(r[0] - midlineR) for r in rasList]
                palatalIdx = int(np.argmin(dMid))
                buccalIdx = 1 - palatalIdx
                return [
                    makeRoot(buccalIdx, "Vestibular (V)", "V", "Ápice Raiz Vestibular"),
                    makeRoot(palatalIdx, "Palatina (P)", "P", "Ápice Raiz Palatina")
                ]

        # ------------------------------------------------------------------
        # Mandibular premolars (34, 35, 44, 45)
        # ------------------------------------------------------------------
        if (not isUpper) and toothNum in (4, 5):
            if n == 2:
                dMid = [abs(r[0] - midlineR) for r in rasList]
                lingualIdx = int(np.argmin(dMid))
                buccalIdx = 1 - lingualIdx
                return [
                    makeRoot(buccalIdx, "Vestibular (V)", "V", "Ápice Raiz Vestibular"),
                    makeRoot(lingualIdx, "Lingual (L)", "L", "Ápice Raiz Lingual")
                ]

        # ------------------------------------------------------------------
        # Generic multi-root fallback
        # ------------------------------------------------------------------
        results = []
        for idx, r in enumerate(roots):
            results.append({
                "kji": r["kji"],
                "ras": r["ras"],
                "root_name": f"Raiz {idx + 1}",
                "full_marker_name": f"{fdi}_R{idx + 1}_Apex",
                "description": f"Dente {fdi} - Ápice Raiz {idx + 1}"
            })
        return results

    # -------------------------------------------------------------------------
    # Markups, 3D Surfaces and Export
    # -------------------------------------------------------------------------

    def _getOrCreateMarkupsNode(self, name):
        node = slicer.mrmlScene.GetFirstNodeByName(name)
        if node is None or not node.IsA("vtkMRMLMarkupsFiducialNode"):
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", name)
        return node

    def _removeMarkupsNodeByName(self, name):
        node = slicer.mrmlScene.GetFirstNodeByName(name)
        if node is not None:
            slicer.mrmlScene.RemoveNode(node)

    def _prepareMarkupsDisplay(self, node, color, glyphScale):
        node.RemoveAllControlPoints()
        node.CreateDefaultDisplayNodes()
        displayNode = node.GetDisplayNode()
        displayNode.SetColor(color[0], color[1], color[2])
        displayNode.SetSelectedColor(color[0], color[1], color[2])
        displayNode.SetGlyphScale(glyphScale)
        displayNode.SetTextScale(glyphScale * 0.8)
        displayNode.SetVisibility(True)
        displayNode.SetVisibility2D(True)
        displayNode.SetVisibility3D(True)

    def populateMarkupsNode(self, markupsNode, results, params):
        """Adds one fiducial control point per detected root with styling."""
        if markupsNode is None:
            markupsNode = self._getOrCreateMarkupsNode("Tooth_Root_Apices")

        glyphScale = params.get("glyph_scale", 2.5)
        colorMode = params.get("color_mode", 0)

        upperColor = [0.0, 0.80, 1.0]   # Ciano
        lowerColor = [1.0, 0.55, 0.0]   # Laranja
        singleColors = {
            1: [1.0, 0.15, 0.15],       # Vermelho
            2: [1.0, 0.85, 0.0]         # Amarelo
        }

        def addPoints(node, subset):
            for res in subset:
                idx = node.AddControlPoint(res["ras"], res["full_marker_name"])
                node.SetNthControlPointDescription(idx, res["description"])

        if colorMode == 0:
            upperResults = [r for r in results if r["arch"] == "upper"]
            lowerResults = [r for r in results if r["arch"] == "lower"]

            if upperResults:
                self._prepareMarkupsDisplay(markupsNode, upperColor, glyphScale)
                addPoints(markupsNode, upperResults)
            else:
                self._prepareMarkupsDisplay(markupsNode, lowerColor, glyphScale)
                addPoints(markupsNode, lowerResults)

            lowerNodeName = "%s_Inferior" % markupsNode.GetName()
            if upperResults and lowerResults:
                lowerNode = self._getOrCreateMarkupsNode(lowerNodeName)
                self._prepareMarkupsDisplay(lowerNode, lowerColor, glyphScale)
                addPoints(lowerNode, lowerResults)
            else:
                self._removeMarkupsNodeByName(lowerNodeName)
        else:
            color = singleColors.get(colorMode, upperColor)
            self._prepareMarkupsDisplay(markupsNode, color, glyphScale)
            addPoints(markupsNode, results)
            self._removeMarkupsNodeByName("%s_Inferior" % markupsNode.GetName())

    def generate3DSurfaces(self, segNode):
        """Creates 3D closed surfaces in Slicer for visualization."""
        if segNode:
            segNode.CreateClosedSurfaceRepresentation()

    def exportResultsToCsv(self, results, filePath):
        """Exports detection results to CSV format."""
        with open(filePath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["FDI", "Tooth_Name_PT", "Tooth_Name_EN", "Arch", "Root_Classification", "Marker_Name", "Description", "RAS_R_mm", "RAS_A_mm", "RAS_S_mm", "IJK_I", "IJK_J", "IJK_K"])
            for r in results:
                ras = r["ras"]
                ijk = r["ijk"]
                writer.writerow([
                    r["fdi"], r["tooth_name"], r["tooth_name_en"], r["arch"],
                    r["root_label"], r["full_marker_name"], r["description"],
                    f"{ras[0]:.2f}", f"{ras[1]:.2f}", f"{ras[2]:.2f}",
                    f"{ijk[0]:.1f}", f"{ijk[1]:.1f}", f"{ijk[2]:.1f}"
                ])

    def batchProcessFolder(self, fileList, outputCsvPath, progressCallback=None):
        """Processes a list of dataset files and saves a combined CSV of all apices."""
        allResults = []
        totalFiles = len(fileList)

        for fIdx, fPath in enumerate(fileList):
            baseName = os.path.basename(fPath)
            if progressCallback:
                pct = (fIdx / float(totalFiles)) * 100.0
                progressCallback(pct, f"Processando arquivo {fIdx + 1}/{totalFiles}: {baseName}...")

            try:
                tempNode = slicer.util.loadLabelVolume(fPath)
                if not tempNode:
                    continue

                tempMarkups = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", f"{baseName}_Apices")
                results = self.run(
                    inputNode=tempNode,
                    markupsNode=tempMarkups,
                    params={
                        "create_3d": False,
                        "trunk_ratio": 0.40,
                        "min_root_volume": 15,
                        "refine_tapering": True,
                        "color_mode": 1
                    }
                )

                for r in results:
                    r["case_name"] = baseName
                    allResults.append(r)

                slicer.mrmlScene.RemoveNode(tempNode)
                slicer.mrmlScene.RemoveNode(tempMarkups)
            except Exception as e:
                print(f"Erro no caso {baseName}: {e}")

        # Write consolidated CSV
        with open(outputCsvPath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Case", "FDI", "Tooth_Name", "Root", "Marker", "RAS_R", "RAS_A", "RAS_S", "IJK_I", "IJK_J", "IJK_K"])
            for r in allResults:
                ras = r["ras"]
                ijk = r["ijk"]
                writer.writerow([
                    r.get("case_name", ""), r["fdi"], r["tooth_name"], r["root_label"], r["full_marker_name"],
                    f"{ras[0]:.2f}", f"{ras[1]:.2f}", f"{ras[2]:.2f}",
                    f"{ijk[0]:.1f}", f"{ijk[1]:.1f}", f"{ijk[2]:.1f}"
                ])

        return len(allResults)


# =============================================================================
# Unit Test Class
# =============================================================================

class DentalRootApexDetectorTest(ScriptedLoadableModuleTest):
    """Automated unit test for the Dental Root Apex Detector module."""

    def setUp(self):
        slicer.mrmlScene.Clear(0)

    def runTest(self):
        self.setUp()
        self.test_DetectorOnToothFairy2()

    def test_DetectorOnToothFairy2(self):
        self.delayDisplay("Iniciando Teste do Detector de Ápices Dentários...")

        # Find a test file in dataset
        datasetDir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        labelsDir = os.path.join(datasetDir, "labelsTr")
        testFiles = [os.path.join(labelsDir, f) for f in os.listdir(labelsDir) if f.endswith(".mha")]
        if not testFiles:
            self.delayDisplay("Nenhum arquivo de teste encontrado em labelsTr.")
            return

        testFile = testFiles[0]
        self.delayDisplay(f"Carregando volume de teste: {os.path.basename(testFile)}")
        labelNode = slicer.util.loadLabelVolume(testFile)
        self.assertIsNotNone(labelNode)

        markupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "TestApices")
        self.assertIsNotNone(markupsNode)

        logic = DentalRootApexDetectorLogic()
        results = logic.run(
            inputNode=labelNode,
            markupsNode=markupsNode,
            params={
                "create_3d": False,
                "trunk_ratio": 0.40,
                "min_root_volume": 15,
                "refine_tapering": True,
                "color_mode": 1
            }
        )

        self.assertGreater(len(results), 0, "Deveria ter identificado pelo menos um ápice radicular.")
        self.assertEqual(markupsNode.GetNumberOfControlPoints(), len(results), "O número de pontos no nó deve ser igual ao número de resultados.")

        self.delayDisplay(f"Teste concluído com sucesso! {len(results)} ápices detectados e validados.")
