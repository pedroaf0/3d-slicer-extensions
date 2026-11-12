import os
import json
import glob
import time
import colorsys
import numpy as np

import vtk
import qt
import ctk
import slicer
from slicer.ScriptedLoadableModule import *

# =============================================================================
# Portuguese Dental & Anatomical Translation Dictionary
# =============================================================================

TRANSLATIONS_PT = {
    "Background": "Fundo",
    "Lower Jawbone": "Mandíbula",
    "Upper Jawbone": "Maxila",
    "Left Inferior Alveolar Canal": "Canal Alveolar Inferior Esquerdo",
    "Right Inferior Alveolar Canal": "Canal Alveolar Inferior Direito",
    "Left Maxillary Sinus": "Seio Maxilar Esquerdo",
    "Right Maxillary Sinus": "Seio Maxilar Direito",
    "Pharynx": "Faringe / Via Aérea",
    "Bridge": "Ponte Protética",
    "Crown": "Coroa Protética",
    "Implant": "Implante Dentário",
    "NA": "Não Aplicável (NA)",

    # Quadrant 1: Upper Right
    "Upper Right Central Incisor": "Incisivo Central Superior Direito",
    "Upper Right Lateral Incisor": "Incisivo Lateral Superior Direito",
    "Upper Right Canine": "Canino Superior Direito",
    "Upper Right First Premolar": "Primeiro Pré-Molar Superior Direito",
    "Upper Right Second Premolar": "Segundo Pré-Molar Superior Direito",
    "Upper Right First Molar": "Primeiro Molar Superior Direito",
    "Upper Right Second Molar": "Segundo Molar Superior Direito",
    "Upper Right Third Molar (Wisdom Tooth)": "Terceiro Molar Superior Direito (Siso)",

    # Quadrant 2: Upper Left
    "Upper Left Central Incisor": "Incisivo Central Superior Esquerdo",
    "Upper Left Lateral Incisor": "Incisivo Lateral Superior Esquerdo",
    "Upper Left Canine": "Canino Superior Esquerdo",
    "Upper Left First Premolar": "Primeiro Pré-Molar Superior Esquerdo",
    "Upper Left Second Premolar": "Segundo Pré-Molar Superior Esquerdo",
    "Upper Left First Molar": "Primeiro Molar Superior Esquerdo",
    "Upper Left Second Molar": "Segundo Molar Superior Esquerdo",
    "Upper Left Third Molar (Wisdom Tooth)": "Terceiro Molar Superior Esquerdo (Siso)",

    # Quadrant 3: Lower Left
    "Lower Left Central Incisor": "Incisivo Central Inferior Esquerdo",
    "Lower Left Lateral Incisor": "Incisivo Lateral Inferior Esquerdo",
    "Lower Left Canine": "Canino Inferior Esquerdo",
    "Lower Left First Premolar": "Primeiro Pré-Molar Inferior Esquerdo",
    "Lower Left Second Premolar": "Segundo Pré-Molar Inferior Esquerdo",
    "Lower Left First Molar": "Primeiro Molar Inferior Esquerdo",
    "Lower Left Second Molar": "Segundo Molar Inferior Esquerdo",
    "Lower Left Third Molar (Wisdom Tooth)": "Terceiro Molar Inferior Esquerdo (Siso)",

    # Quadrant 4: Lower Right
    "Lower Right Central Incisor": "Incisivo Central Inferior Direito",
    "Lower Right Lateral Incisor": "Incisivo Lateral Inferior Direito",
    "Lower Right Canine": "Canino Inferior Direito",
    "Lower Right First Premolar": "Primeiro Pré-Molar Inferior Direito",
    "Lower Right Second Premolar": "Segundo Pré-Molar Inferior Direito",
    "Lower Right First Molar": "Primeiro Molar Inferior Direito",
    "Lower Right Second Molar": "Segundo Molar Inferior Direito",
    "Lower Right Third Molar (Wisdom Tooth)": "Terceiro Molar Inferior Direito (Siso)"
}

# Anatomical Categories
def get_label_category(val):
    if val == 0:
        return "Fundo"
    elif val in [1, 2]:
        return "Osso / Arcada"
    elif val in [3, 4]:
        return "Canal Nervoso"
    elif val in [5, 6]:
        return "Seio Aéreo"
    elif val == 7:
        return "Via Aérea"
    elif val in [8, 9, 10]:
        return "Prótese / Implante"
    elif (11 <= val <= 28) or (31 <= val <= 48):
        return "Elemento Dentário"
    return "Outro"


# =============================================================================
# Main Module Class
# =============================================================================

class ToothFairySegmentationLoader(ScriptedLoadableModule):
    """3D Slicer Extension to load ToothFairy2 segmentations with names and colors."""

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "ToothFairy Segmentation Loader"
        self.parent.categories = ["Dental", "Informatics"]
        self.parent.dependencies = ["Segmentations"]
        self.parent.contributors = ["Antigravity Dental AI Team", "ToothFairy2 Research"]
        self.parent.helpText = (
            "Carrega automaticamente arquivos de segmentação do dataset ToothFairy2 (*.mha) "
            "diretamente como nós de segmentação com múltiplos segmentos nomeados e coloridos "
            "corretamente de acordo com o dataset.json (Notação FDI de 11 a 48 e estruturas anatômicas).\n\n"
            "Recursos:\n"
            "- Suporte dinâmico ao dataset.json\n"
            "- Nomes em Português e Inglês com notação FDI\n"
            "- Esquemas de cores clínicas anatômicas (por quadrante e estrutura)\n"
            "- Carregamento automático da imagem tomográfica CBCT correspondente (Background Volume)\n"
            "- Geração instantânea de superfícies 3D e tabela interativa de segmentos."
        )
        self.parent.acknowledgementText = (
            "Desenvolvido para integração anatômica e visualização avançada do dataset ToothFairy2 no 3D Slicer."
        )


# =============================================================================
# Widget Class (UI)
# =============================================================================

class ToothFairySegmentationLoaderWidget(ScriptedLoadableModuleWidget):
    """GUI Widget for ToothFairy Segmentation Loader."""

    def resourcePath(self, filename):
        scriptedModulesPath = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(scriptedModulesPath, "Resources", filename)

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        self.logic = ToothFairySegmentationLoaderLogic()
        self.currentSegmentationNode = None
        self.datasetInfo = None

        # ---------------------------------------------------------------------
        # Section 1: dataset.json Configuration
        # ---------------------------------------------------------------------
        jsonCollapsibleButton = ctk.ctkCollapsibleButton()
        jsonCollapsibleButton.text = "1. Configuração do dataset.json"
        self.layout.addWidget(jsonCollapsibleButton)
        jsonFormLayout = qt.QFormLayout(jsonCollapsibleButton)

        self.jsonPathEdit = ctk.ctkPathLineEdit()
        self.jsonPathEdit.filters = ctk.ctkPathLineEdit.Files
        self.jsonPathEdit.nameFilters = ["JSON Files (*.json)", "All Files (*)"]

        # Try to locate dataset.json automatically
        autoJsonPath = self.logic.findDefaultDatasetJson()
        if autoJsonPath:
            self.jsonPathEdit.setCurrentPath(autoJsonPath)

        self.jsonPathEdit.currentPathChanged.connect(self.onJsonPathChanged)
        jsonFormLayout.addRow("Arquivo dataset.json:", self.jsonPathEdit)

        self.jsonStatusLabel = qt.QLabel("")
        self.jsonStatusLabel.setStyleSheet("font-size: 11px; font-weight: bold; color: #2E7D32;")
        jsonFormLayout.addRow("", self.jsonStatusLabel)
        self.updateJsonStatus()

        # ---------------------------------------------------------------------
        # Section 2: Input Selection (Case Dropdown, File Browser or Scene)
        # ---------------------------------------------------------------------
        inputCollapsibleButton = ctk.ctkCollapsibleButton()
        inputCollapsibleButton.text = "2. Seleção da Segmentação (.mha)"
        self.layout.addWidget(inputCollapsibleButton)
        inputFormLayout = qt.QFormLayout(inputCollapsibleButton)

        self.inputModeCombo = qt.QComboBox()
        self.inputModeCombo.addItems([
            "Lista de Casos do Dataset (labelsTr/*.mha)",
            "Selecionar Arquivo no Disco (.mha / .nii)",
            "Nó LabelMap já aberto na Cena do Slicer"
        ])
        self.inputModeCombo.currentIndexChanged.connect(self.onInputModeChanged)
        inputFormLayout.addRow("Método de Seleção:", self.inputModeCombo)

        # Mode A: Case Dropdown
        self.caseSelectWidget = qt.QWidget()
        caseSelectLayout = qt.QHBoxLayout(self.caseSelectWidget)
        caseSelectLayout.setContentsMargins(0, 0, 0, 0)
        self.caseCombo = qt.QComboBox()
        self.caseCombo.setSizeAdjustPolicy(qt.QComboBox.AdjustToContents)
        self.refreshCasesButton = qt.QPushButton("Atualizar Lista")
        self.refreshCasesButton.setIcon(qt.QIcon.fromTheme("view-refresh"))
        self.refreshCasesButton.clicked.connect(self.populateCasesList)
        caseSelectLayout.addWidget(self.caseCombo, 1)
        caseSelectLayout.addWidget(self.refreshCasesButton)
        inputFormLayout.addRow("Caso do Dataset:", self.caseSelectWidget)

        # Mode B: File Path
        self.filePathEdit = ctk.ctkPathLineEdit()
        self.filePathEdit.filters = ctk.ctkPathLineEdit.Files
        self.filePathEdit.nameFilters = ["Arquivos de Imagem (*.mha *.nii *.nii.gz *.nrrd)", "Todos os Arquivos (*)"]
        self.filePathEdit.setVisible(False)
        inputFormLayout.addRow("Arquivo de Segmentação:", self.filePathEdit)

        # Mode C: Scene Node
        self.sceneNodeSelector = slicer.qMRMLNodeComboBox()
        self.sceneNodeSelector.nodeTypes = ["vtkMRMLLabelMapVolumeNode"]
        self.sceneNodeSelector.selectNodeUponCreation = False
        self.sceneNodeSelector.addEnabled = False
        self.sceneNodeSelector.removeEnabled = False
        self.sceneNodeSelector.noneEnabled = False
        self.sceneNodeSelector.setMRMLScene(slicer.mrmlScene)
        self.sceneNodeSelector.setVisible(False)
        inputFormLayout.addRow("Nó LabelMap na Cena:", self.sceneNodeSelector)

        # ---------------------------------------------------------------------
        # Section 3: Formatting & Appearance Options
        # ---------------------------------------------------------------------
        optsCollapsibleButton = ctk.ctkCollapsibleButton()
        optsCollapsibleButton.text = "3. Opções de Nomes, Cores e Visualização"
        self.layout.addWidget(optsCollapsibleButton)
        optsFormLayout = qt.QFormLayout(optsCollapsibleButton)

        # Name format
        self.nameFormatCombo = qt.QComboBox()
        self.nameFormatCombo.addItems([
            "[FDI]: Nome em Português (ex: '11: Incisivo Central Superior Direito')",
            "[FDI]: English Name (ex: '11: Upper Right Central Incisor')",
            "English Name (FDI) (ex: 'Upper Right Central Incisor (11)')",
            "Apenas Nome em Português (ex: 'Incisivo Central Superior Direito')",
            "Apenas Nome em Inglês (ex: 'Upper Right Central Incisor')",
            "Apenas Número FDI (ex: '11')"
        ])
        optsFormLayout.addRow("Formato dos Nomes:", self.nameFormatCombo)

        # Color scheme
        self.colorSchemeCombo = qt.QComboBox()
        self.colorSchemeCombo.addItems([
            "Anatômico Clínico (Tons por Quadrante, Ossos e Estruturas)",
            "Quadrantes Simplificados (Ciano, Verde, Laranja, Magenta)",
            "Arco-íris / Cores Exclusivas para cada Rótulo"
        ])
        optsFormLayout.addRow("Esquema de Cores:", self.colorSchemeCombo)

        # CBCT Image Background Loader
        self.loadCbctCheck = qt.QCheckBox()
        self.loadCbctCheck.setChecked(True)
        self.loadCbctCheck.setToolTip("Localiza e carrega automaticamente o volume CBCT correspondente em imagesTr/ como imagem de fundo nas fatias 2D.")
        optsFormLayout.addRow("Carregar CBCT correspondente (Background):", self.loadCbctCheck)

        # 3D Closed Surface Generation
        self.create3DSurfaceCheck = qt.QCheckBox()
        self.create3DSurfaceCheck.setChecked(True)
        self.create3DSurfaceCheck.setToolTip("Gera os modelos 3D de superfície fechada para visualização volumétrica imediata.")
        optsFormLayout.addRow("Gerar Modelo 3D (Superfície Fechada):", self.create3DSurfaceCheck)

        # Hide Bones in 3D by default
        self.hideBones3DCheck = qt.QCheckBox()
        self.hideBones3DCheck.setChecked(True)
        self.hideBones3DCheck.setToolTip("Oculta a Maxila e Mandíbula na visualização 3D inicial para permitir visualização limpa de toda a arcada dentária (permanecem visíveis nos cortes 2D).")
        optsFormLayout.addRow("Ocultar Maxila/Mandíbula no 3D inicialmente:", self.hideBones3DCheck)

        # Remove temporary labelmap node
        self.removeTempLabelMapCheck = qt.QCheckBox()
        self.removeTempLabelMapCheck.setChecked(True)
        self.removeTempLabelMapCheck.setToolTip("Remove o nó intermediário LabelMapVolumeNode mantendo a árvore da cena limpa apenas com a Segmentação.")
        optsFormLayout.addRow("Manter Cena Limpa (Remover LabelMap bruto):", self.removeTempLabelMapCheck)

        # ---------------------------------------------------------------------
        # Section 4: Load & Convert Action Button
        # ---------------------------------------------------------------------
        self.loadButton = qt.QPushButton("Carregar Segmentação com Nomes Corretos")
        self.loadButton.setIcon(qt.QIcon.fromTheme("document-open"))
        self.loadButton.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px; background-color: #2E7D32; color: white; border-radius: 6px;")
        self.loadButton.clicked.connect(self.onLoadButtonClicked)
        self.layout.addWidget(self.loadButton)

        self.progressBar = qt.QProgressBar()
        self.progressBar.setVisible(False)
        self.layout.addWidget(self.progressBar)

        self.statusLabel = qt.QLabel("Pronto para carregar.")
        self.statusLabel.setStyleSheet("font-style: italic; color: #555;")
        self.layout.addWidget(self.statusLabel)

        # ---------------------------------------------------------------------
        # Section 5: Segment Manager & Quick Visibility Filter Table
        # ---------------------------------------------------------------------
        tableCollapsibleButton = ctk.ctkCollapsibleButton()
        tableCollapsibleButton.text = "4. Gerenciador de Segmentos e Visibilidade"
        self.layout.addWidget(tableCollapsibleButton)
        tableLayout = qt.QVBoxLayout(tableCollapsibleButton)

        # Quick visibility filter bar
        filterBarLayout = qt.QHBoxLayout()
        self.showAllBtn = qt.QPushButton("Mostrar Todos")
        self.showAllBtn.clicked.connect(lambda: self.setBatchVisibility(True))
        self.hideAllBtn = qt.QPushButton("Ocultar Todos")
        self.hideAllBtn.clicked.connect(lambda: self.setBatchVisibility(False))
        self.teethOnlyBtn = qt.QPushButton("Apenas Dentes")
        self.teethOnlyBtn.clicked.connect(lambda: self.filterVisibilityCategory("Elemento Dentário"))
        self.upperOnlyBtn = qt.QPushButton("Arcada Superior")
        self.upperOnlyBtn.clicked.connect(lambda: self.filterVisibilityArch("upper"))
        self.lowerOnlyBtn = qt.QPushButton("Arcada Inferior")
        self.lowerOnlyBtn.clicked.connect(lambda: self.filterVisibilityArch("lower"))

        filterBarLayout.addWidget(self.showAllBtn)
        filterBarLayout.addWidget(self.hideAllBtn)
        filterBarLayout.addWidget(self.teethOnlyBtn)
        filterBarLayout.addWidget(self.upperOnlyBtn)
        filterBarLayout.addWidget(self.lowerOnlyBtn)
        tableLayout.addLayout(filterBarLayout)

        # Table
        self.segmentsTable = qt.QTableWidget()
        self.segmentsTable.setColumnCount(5)
        self.segmentsTable.setHorizontalHeaderLabels(["Visível", "ID", "Nome do Segmento", "Categoria", "Cor"])
        self.segmentsTable.horizontalHeader().setSectionResizeMode(2, qt.QHeaderView.Stretch)
        self.segmentsTable.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        tableLayout.addWidget(self.segmentsTable)

        # Export button
        exportLayout = qt.QHBoxLayout()
        self.exportSegNrrdBtn = qt.QPushButton("Exportar Segmentação (.seg.nrrd)")
        self.exportSegNrrdBtn.setIcon(qt.QIcon.fromTheme("document-save"))
        self.exportSegNrrdBtn.clicked.connect(self.onExportSegNrrdClicked)
        self.exportSegNrrdBtn.setEnabled(False)
        exportLayout.addWidget(self.exportSegNrrdBtn)
        tableLayout.addLayout(exportLayout)

        # Initial populate
        self.populateCasesList()

        self.layout.addStretch(1)

    # -------------------------------------------------------------------------
    # UI Callbacks & Logic Handling
    # -------------------------------------------------------------------------

    def onJsonPathChanged(self, newPath):
        self.updateJsonStatus()

    def updateJsonStatus(self):
        jsonPath = self.jsonPathEdit.currentPath
        if jsonPath and os.path.exists(jsonPath):
            try:
                self.datasetInfo = self.logic.loadDatasetJson(jsonPath)
                numLabels = len(self.datasetInfo.get("labels", {}))
                self.jsonStatusLabel.setText(f"✓ {numLabels} rótulos carregados de dataset.json")
                self.jsonStatusLabel.setStyleSheet("font-size: 11px; font-weight: bold; color: #2E7D32;")
            except Exception as e:
                self.jsonStatusLabel.setText(f"Erro ao ler JSON: {e}")
                self.jsonStatusLabel.setStyleSheet("font-size: 11px; font-weight: bold; color: #D32F2F;")
        else:
            self.jsonStatusLabel.setText("Aviso: dataset.json não encontrado.")
            self.jsonStatusLabel.setStyleSheet("font-size: 11px; font-style: italic; color: #E65100;")

    def onInputModeChanged(self, index):
        self.caseSelectWidget.setVisible(index == 0)
        self.filePathEdit.setVisible(index == 1)
        self.sceneNodeSelector.setVisible(index == 2)

    def populateCasesList(self):
        self.caseCombo.clear()
        cases = self.logic.findAvailableCases()
        if cases:
            for c in cases:
                self.caseCombo.addItem(os.path.basename(c), c)
            self.statusLabel.setText(f"{len(cases)} casos encontrados em labelsTr.")
        else:
            self.caseCombo.addItem("Nenhum arquivo encontrado em labelsTr", "")

    def onLoadButtonClicked(self):
        mode = self.inputModeCombo.currentIndex
        jsonPath = self.jsonPathEdit.currentPath

        if not jsonPath or not os.path.exists(jsonPath):
            slicer.util.errorDisplay("Por favor, indique um arquivo dataset.json válido.")
            return

        options = {
            "name_format": self.nameFormatCombo.currentIndex,
            "color_scheme": self.colorSchemeCombo.currentIndex,
            "load_cbct": self.loadCbctCheck.isChecked(),
            "create_3d": self.create3DSurfaceCheck.isChecked(),
            "hide_bones_3d": self.hideBones3DCheck.isChecked(),
            "remove_temp_labelmap": self.removeTempLabelMapCheck.isChecked()
        }

        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)
        self.loadButton.setEnabled(False)
        self.statusLabel.setText("Iniciando carregamento da segmentação...")
        slicer.app.processEvents()

        t0 = time.time()
        try:
            if mode == 0: # Case list
                mhaPath = self.caseCombo.currentData
                if not mhaPath or not os.path.exists(mhaPath):
                    slicer.util.errorDisplay("Nenhum caso selecionado.")
                    return
                segNode = self.logic.loadAndConvert(mhaPath, jsonPath, options, self.onProgressUpdate)

            elif mode == 1: # File browser
                mhaPath = self.filePathEdit.currentPath
                if not mhaPath or not os.path.exists(mhaPath):
                    slicer.util.errorDisplay("Por favor, selecione um arquivo .mha/.nii válido.")
                    return
                segNode = self.logic.loadAndConvert(mhaPath, jsonPath, options, self.onProgressUpdate)

            elif mode == 2: # Scene node
                labelNode = self.sceneNodeSelector.currentNode()
                if not labelNode:
                    slicer.util.errorDisplay("Selecione um nó de LabelMap na cena.")
                    return
                segNode = self.logic.convertLabelMapNode(labelNode, jsonPath, options, self.onProgressUpdate)

            elapsed = time.time() - t0
            self.currentSegmentationNode = segNode
            self.updateSegmentsTable(segNode)
            self.exportSegNrrdBtn.setEnabled(True)
            numSegs = segNode.GetSegmentation().GetNumberOfSegments()
            self.statusLabel.setText(f"Segmentação carregada: {numSegs} segmentos nomeados em {elapsed:.2f}s!")

        except Exception as e:
            import traceback
            traceback.print_exc()
            slicer.util.errorDisplay(f"Erro ao carregar segmentação: {str(e)}")
            self.statusLabel.setText("Erro no carregamento.")
        finally:
            self.progressBar.setVisible(False)
            self.loadButton.setEnabled(True)

    def onProgressUpdate(self, pct, msg):
        self.progressBar.setValue(int(pct))
        self.statusLabel.setText(msg)
        slicer.app.processEvents()

    def updateSegmentsTable(self, segNode):
        if not segNode:
            return
        segmentation = segNode.GetSegmentation()
        dispNode = segNode.GetDisplayNode()
        numSegs = segmentation.GetNumberOfSegments()

        self.segmentsTable.setRowCount(numSegs)
        self.segmentsTable.blockSignals(True)

        for i in range(numSegs):
            seg = segmentation.GetNthSegment(i)
            segId = segmentation.GetNthSegmentID(i)
            val = seg.GetLabelValue()
            name = seg.GetName()
            cat = get_label_category(val)
            color = seg.GetColor()
            vis = dispNode.GetSegmentVisibility(segId) if dispNode else True

            # Checkbox column
            chk = qt.QCheckBox()
            chk.setChecked(vis)
            chk.toggled.connect(lambda checked, sId=segId: self.toggleSegmentVisibility(sId, checked))
            chkWidget = qt.QWidget()
            chkLayout = qt.QHBoxLayout(chkWidget)
            chkLayout.addWidget(chk)
            chkLayout.setAlignment(qt.Qt.AlignCenter)
            chkLayout.setContentsMargins(0, 0, 0, 0)
            self.segmentsTable.setCellWidget(i, 0, chkWidget)

            # Label Value
            valItem = qt.QTableWidgetItem(str(val))
            valItem.setTextAlignment(qt.Qt.AlignCenter)
            self.segmentsTable.setItem(i, 1, valItem)

            # Name
            nameItem = qt.QTableWidgetItem(name)
            self.segmentsTable.setItem(i, 2, nameItem)

            # Category
            catItem = qt.QTableWidgetItem(cat)
            catItem.setTextAlignment(qt.Qt.AlignCenter)
            self.segmentsTable.setItem(i, 3, catItem)

            # Color icon/cell
            colorItem = qt.QTableWidgetItem()
            pix = qt.QPixmap(24, 16)
            qcol = qt.QColor(int(color[0]*255), int(color[1]*255), int(color[2]*255))
            pix.fill(qcol)
            colorItem.setIcon(qt.QIcon(pix))
            colorItem.setTextAlignment(qt.Qt.AlignCenter)
            self.segmentsTable.setItem(i, 4, colorItem)

        self.segmentsTable.blockSignals(False)

    def toggleSegmentVisibility(self, segId, visible):
        if self.currentSegmentationNode:
            dispNode = self.currentSegmentationNode.GetDisplayNode()
            if dispNode:
                dispNode.SetSegmentVisibility(segId, visible)

    def setBatchVisibility(self, visible):
        if not self.currentSegmentationNode:
            return
        dispNode = self.currentSegmentationNode.GetDisplayNode()
        if not dispNode:
            return
        segmentation = self.currentSegmentationNode.GetSegmentation()
        for i in range(segmentation.GetNumberOfSegments()):
            segId = segmentation.GetNthSegmentID(i)
            dispNode.SetSegmentVisibility(segId, visible)
        self.updateSegmentsTable(self.currentSegmentationNode)

    def filterVisibilityCategory(self, targetCategory):
        if not self.currentSegmentationNode:
            return
        dispNode = self.currentSegmentationNode.GetDisplayNode()
        if not dispNode:
            return
        segmentation = self.currentSegmentationNode.GetSegmentation()
        for i in range(segmentation.GetNumberOfSegments()):
            seg = segmentation.GetNthSegment(i)
            segId = segmentation.GetNthSegmentID(i)
            val = seg.GetLabelValue()
            cat = get_label_category(val)
            dispNode.SetSegmentVisibility(segId, (cat == targetCategory))
        self.updateSegmentsTable(self.currentSegmentationNode)

    def filterVisibilityArch(self, arch):
        if not self.currentSegmentationNode:
            return
        dispNode = self.currentSegmentationNode.GetDisplayNode()
        if not dispNode:
            return
        segmentation = self.currentSegmentationNode.GetSegmentation()
        for i in range(segmentation.GetNumberOfSegments()):
            seg = segmentation.GetNthSegment(i)
            segId = segmentation.GetNthSegmentID(i)
            val = seg.GetLabelValue()
            if arch == "upper":
                vis = (11 <= val <= 28) or (val == 2) or (val in [5, 6])
            else:
                vis = (31 <= val <= 48) or (val == 1) or (val in [3, 4])
            dispNode.SetSegmentVisibility(segId, vis)
        self.updateSegmentsTable(self.currentSegmentationNode)

    def onExportSegNrrdClicked(self):
        if not self.currentSegmentationNode:
            return
        defaultPath = os.path.join(slicer.app.temporaryPath, f"{self.currentSegmentationNode.GetName()}.seg.nrrd")
        filePath = qt.QFileDialog.getSaveFileName(
            None, "Salvar Segmentação (.seg.nrrd)", defaultPath, "Segmentation (*.seg.nrrd)"
        )
        if filePath:
            slicer.util.saveNode(self.currentSegmentationNode, filePath)
            slicer.util.infoDisplay(f"Segmentação salva com sucesso em:\n{filePath}")


# =============================================================================
# Logic Class
# =============================================================================

class ToothFairySegmentationLoaderLogic(ScriptedLoadableModuleLogic):
    """Core logic to parse dataset.json and build Slicer Segmentations."""

    def findDefaultDatasetJson(self):
        """Searches common locations for dataset.json."""
        currentDir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(currentDir, "dataset.json"),
            os.path.join(os.path.dirname(currentDir), "dataset.json"),
            os.path.join(os.path.dirname(os.path.dirname(currentDir)), "dataset.json"),
            r"D:\ToothFairy2_Dataset\Dataset112_ToothFairy2\dataset.json"
        ]
        for c in candidates:
            if os.path.exists(c):
                return os.path.abspath(c)
        return ""

    def findAvailableCases(self):
        """Finds all .mha segmentation files in labelsTr."""
        jsonPath = self.findDefaultDatasetJson()
        baseDir = os.path.dirname(jsonPath) if jsonPath else os.getcwd()
        labelsTrDir = os.path.join(baseDir, "labelsTr")
        if os.path.exists(labelsTrDir):
            files = sorted(glob.glob(os.path.join(labelsTrDir, "*.mha")))
            return files
        return []

    def loadDatasetJson(self, jsonPath):
        """Loads and parses dataset.json."""
        with open(jsonPath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    def loadAndConvert(self, mhaPath, jsonPath, options=None, progressCallback=None):
        """Loads a .mha file from disk and converts it to a named Segmentation Node."""
        if progressCallback:
            progressCallback(10.0, f"Carregando volume: {os.path.basename(mhaPath)}...")

        # 1. Load label volume
        labelMapNode = slicer.util.loadLabelVolume(mhaPath)
        if not labelMapNode:
            raise RuntimeError(f"Falha ao carregar o arquivo: {mhaPath}")

        caseName = os.path.basename(mhaPath).replace(".mha", "").replace(".nii.gz", "").replace(".nii", "")

        # 2. Check and load matching CBCT image if requested
        if options and options.get("load_cbct", True):
            if progressCallback:
                progressCallback(25.0, "Buscando e carregando tomografia CBCT correspondente...")
            self.loadMatchingCbct(mhaPath, caseName)

        # 3. Convert labelmap to segmentation node
        segNode = self.convertLabelMapNode(
            labelMapNode=labelMapNode,
            jsonPath=jsonPath,
            options=options,
            progressCallback=progressCallback,
            segNodeName=f"{caseName}_Segmentation"
        )

        return segNode

    def loadMatchingCbct(self, labelPath, caseName):
        """Finds and loads corresponding CBCT from imagesTr/."""
        labelsDir = os.path.dirname(os.path.abspath(labelPath))
        baseDatasetDir = os.path.dirname(labelsDir)
        imagesDir = os.path.join(baseDatasetDir, "imagesTr")

        if not os.path.exists(imagesDir):
            return None

        # Look for <caseName>_0000.mha or similar
        cbctPattern = os.path.join(imagesDir, f"{caseName}_0000.mha")
        if os.path.exists(cbctPattern):
            cbctNode = slicer.util.loadVolume(cbctPattern)
            if cbctNode:
                slicer.util.setSliceViewerLayers(background=cbctNode, fit=True)
                return cbctNode

        # Try alternative match
        altPattern = glob.glob(os.path.join(imagesDir, f"{caseName}*.mha"))
        if altPattern:
            cbctNode = slicer.util.loadVolume(altPattern[0])
            if cbctNode:
                slicer.util.setSliceViewerLayers(background=cbctNode, fit=True)
                return cbctNode

        return None

    def convertLabelMapNode(self, labelMapNode, jsonPath, options=None, progressCallback=None, segNodeName=None):
        """Converts an existing LabelMapVolumeNode into a named SegmentationNode."""
        if not segNodeName:
            segNodeName = f"{labelMapNode.GetName()}_Segmentation"

        if progressCallback:
            progressCallback(40.0, "Importando segmentos para vtkMRMLSegmentationNode...")

        # Parse dataset.json
        dInfo = self.loadDatasetJson(jsonPath)
        rawLabels = dInfo.get("labels", {})
        # Map: integer_label -> string_name_en
        valToEnName = {int(v): k for k, v in rawLabels.items() if int(v) != 0}

        # Create Segmentation Node
        segNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", segNodeName)
        segNode.CreateDefaultDisplayNodes()

        # Import labelmap into segmentation
        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelMapNode, segNode)

        # Apply names and colors to each segment
        if progressCallback:
            progressCallback(60.0, "Configurando nomes anatômicos e paletas de cores...")

        self.applyNamingAndColors(segNode, valToEnName, options)

        # Display configurations
        dispNode = segNode.GetDisplayNode()
        if dispNode:
            dispNode.SetVisibility(True)
            dispNode.SetVisibility2D(True)
            dispNode.SetVisibility3D(True)

            # Option: Hide bones in 3D by default
            if options and options.get("hide_bones_3d", True):
                segmentation = segNode.GetSegmentation()
                for i in range(segmentation.GetNumberOfSegments()):
                    seg = segmentation.GetNthSegment(i)
                    segId = segmentation.GetNthSegmentID(i)
                    val = seg.GetLabelValue()
                    if val in [1, 2]: # Upper and Lower Jawbone
                        if hasattr(dispNode, "SetSegmentVisibility3D"):
                            dispNode.SetSegmentVisibility3D(segId, False)

        # Generate 3D surface representation if requested
        if options and options.get("create_3d", True):
            if progressCallback:
                progressCallback(80.0, "Construindo representação de superfície 3D...")
            segNode.CreateClosedSurfaceRepresentation()

        # Remove temporary labelmap node if requested
        if options and options.get("remove_temp_labelmap", True):
            slicer.mrmlScene.RemoveNode(labelMapNode)

        if progressCallback:
            progressCallback(100.0, "Segmentação configurada com sucesso!")

        return segNode

    def applyNamingAndColors(self, segNode, valToEnName, options):
        """Applies formatting to names and assigns anatomical colors."""
        nameFormat = options.get("name_format", 0) if options else 0
        colorScheme = options.get("color_scheme", 0) if options else 0

        segmentation = segNode.GetSegmentation()
        numSegments = segmentation.GetNumberOfSegments()

        for i in range(numSegments):
            seg = segmentation.GetNthSegment(i)
            origName = seg.GetName()

            # Determine label integer value
            try:
                val = int(origName)
            except ValueError:
                val = seg.GetLabelValue()

            seg.SetLabelValue(val)
            nameEn = valToEnName.get(val, f"Label {val}")
            namePt = TRANSLATIONS_PT.get(nameEn, nameEn)

            # Format name according to user choice
            if nameFormat == 0:   # [FDI]: Nome PT
                formattedName = f"{val}: {namePt}"
            elif nameFormat == 1: # [FDI]: Nome EN
                formattedName = f"{val}: {nameEn}"
            elif nameFormat == 2: # Nome EN (FDI)
                formattedName = f"{nameEn} ({val})"
            elif nameFormat == 3: # Apenas Nome PT
                formattedName = namePt
            elif nameFormat == 4: # Apenas Nome EN
                formattedName = nameEn
            elif nameFormat == 5: # Apenas FDI
                formattedName = str(val)
            else:
                formattedName = f"{val}: {namePt}"

            seg.SetName(formattedName)

            # Assign Color
            color = self.getSegmentColor(val, colorScheme)
            seg.SetColor(color[0], color[1], color[2])

    def getSegmentColor(self, val, schemeIndex):
        """Returns [R, G, B] normalized (0.0 - 1.0) for a given label value and scheme."""
        # Scheme 0: Clinical Anatomical
        if schemeIndex == 0:
            if val == 1: # Lower Jawbone
                return [0.86, 0.82, 0.73] # Bone tan
            elif val == 2: # Upper Jawbone
                return [0.91, 0.88, 0.80] # Ivory bone
            elif val in [3, 4]: # Inferior Alveolar Canals
                return [1.0, 0.85, 0.10] # Electric nerve yellow
            elif val in [5, 6]: # Maxillary Sinuses
                return [0.25, 0.75, 0.95] # Cyan air cavity
            elif val == 7: # Pharynx
                return [0.65, 0.35, 0.75] # Airway purple
            elif val in [8, 9]: # Bridge / Crown
                return [0.94, 0.78, 0.35] # Gold/Ceramic
            elif val == 10: # Implant
                return [0.55, 0.65, 0.78] # Titanium metal
            elif 11 <= val <= 18: # Upper Right (Q1) - Turquoise/Cyan shades
                offset = (val - 11) / 8.0
                return [0.10 + 0.30 * offset, 0.80 + 0.15 * offset, 0.90 - 0.10 * offset]
            elif 21 <= val <= 28: # Upper Left (Q2) - Emerald/Mint shades
                offset = (val - 21) / 8.0
                return [0.15 + 0.25 * offset, 0.85 - 0.10 * offset, 0.45 + 0.35 * offset]
            elif 31 <= val <= 38: # Lower Left (Q3) - Warm Coral/Orange shades
                offset = (val - 31) / 8.0
                return [1.00 - 0.10 * offset, 0.55 + 0.20 * offset, 0.15 + 0.25 * offset]
            elif 41 <= val <= 48: # Lower Right (Q4) - Lavender/Magenta shades
                offset = (val - 41) / 8.0
                return [0.85 - 0.15 * offset, 0.35 + 0.30 * offset, 0.85 + 0.10 * offset]
            else:
                return [0.70, 0.70, 0.70]

        # Scheme 1: Simplified Quadrants
        elif schemeIndex == 1:
            if val in [1, 2]:
                return [0.85, 0.82, 0.75]
            elif val in [3, 4]:
                return [1.0, 0.85, 0.10]
            elif val in [5, 6]:
                return [0.25, 0.75, 0.95]
            elif 11 <= val <= 18:
                return [0.0, 0.80, 0.95] # Q1 Cyan
            elif 21 <= val <= 28:
                return [0.2, 0.85, 0.40] # Q2 Green
            elif 31 <= val <= 38:
                return [1.0, 0.55, 0.10] # Q3 Orange
            elif 41 <= val <= 48:
                return [0.9, 0.25, 0.75] # Q4 Magenta
            else:
                return [0.65, 0.65, 0.65]

        # Scheme 2: Rainbow (Distinct colors by HSV golden angle)
        else:
            golden_ratio_conjugate = 0.618033988749895
            h = (val * golden_ratio_conjugate) % 1.0
            r, g, b = colorsys.hsv_to_rgb(h, 0.75, 0.90)
            return [r, g, b]


# =============================================================================
# Unit Test Class
# =============================================================================

class ToothFairySegmentationLoaderTest(ScriptedLoadableModuleTest):
    """Unit test for ToothFairy Segmentation Loader."""

    def setUp(self):
        slicer.mrmlScene.Clear(0)

    def runTest(self):
        self.setUp()
        self.test_LoaderOnToothFairy2()

    def test_LoaderOnToothFairy2(self):
        self.delayDisplay("Iniciando teste do ToothFairy Segmentation Loader...")

        logic = ToothFairySegmentationLoaderLogic()
        jsonPath = logic.findDefaultDatasetJson()
        self.assertIsNotNone(jsonPath, "dataset.json não encontrado.")

        cases = logic.findAvailableCases()
        self.assertGreater(len(cases), 0, "Nenhum caso encontrado em labelsTr.")

        testCase = cases[0]
        self.delayDisplay(f"Testando carregamento do caso: {os.path.basename(testCase)}")

        options = {
            "name_format": 0,
            "color_scheme": 0,
            "load_cbct": False,
            "create_3d": True,
            "hide_bones_3d": True,
            "remove_temp_labelmap": True
        }

        segNode = logic.loadAndConvert(testCase, jsonPath, options)
        self.assertIsNotNone(segNode)
        self.assertTrue(segNode.IsA("vtkMRMLSegmentationNode"))

        numSegs = segNode.GetSegmentation().GetNumberOfSegments()
        self.assertGreater(numSegs, 0, "Deveria ter carregado múltiplos segmentos.")

        # Verify that segments have names matching dataset.json
        firstSeg = segNode.GetSegmentation().GetNthSegment(0)
        self.assertIn(":", firstSeg.GetName(), "O nome do segmento deve conter o formato FDI: Nome")

        self.delayDisplay(f"Teste concluído com sucesso! {numSegs} segmentos nomeados carregados.")
