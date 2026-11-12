import vtk
import qt
import ctk
import slicer
import numpy as np

from collections import deque

from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
)


#
# ============================================================
# Voxel Region Growing
# ============================================================
#

class VoxelRegionGrowing(ScriptedLoadableModule):

    def __init__(self, parent):

        ScriptedLoadableModule.__init__(self, parent)

        self.parent.title = "Voxel Region Growing"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Pedro Afonso"]

        self.parent.helpText = """
Voxel Region Growing para 3D Slicer.

Permite selecionar um voxel diretamente nas Slice Views
Red, Yellow ou Green e executar um crescimento de região
3D baseado na intensidade do voxel.

O resultado é aplicado diretamente ao segmento ativo
do Segment Editor.
"""

        self.parent.acknowledgementText = """
Voxel Region Growing
"""


#
# ============================================================
# WIDGET
# ============================================================
#

class VoxelRegionGrowingWidget(ScriptedLoadableModuleWidget):

    def __init__(self, parent=None):

        ScriptedLoadableModuleWidget.__init__(
            self,
            parent
        )

        #
        # Logic
        #

        self.logic = None

        #
        # Slice observers
        #

        self.sliceObservers = {}

        #
        # Selection state
        #

        self.selectingVoxel = False

        #
        # Seed information
        #

        self.seedIJK = None
        self.seedRAS = None
        self.seedValue = None
        self.seedVolumeNode = None
        self.seedSliceName = None

        #
        # Seed marker
        #

        self.seedMarkupNode = None

        #
        # Layout manager
        #

        self.layoutManager = None

        #
        # Refresh timer
        #

        self.refreshTimer = None

        self.targetSegmentationSelector = None
        self.targetSegmentComboBox = None
        self.targetInfoLabel = None
        self.refreshTargetSegmentsButton = None
        self.targetSegmentIDs = []

        self.maskSegmentationSelector = None
        self.maskSegmentComboBox = None
        self.maskCheckBox = None

        self.cancelGrowButton = None
        self.cancelRequested = False

        self.undoStack = []
        self.undoButton = None
        self.tolerancePlusButton = None

    #
    # ========================================================
    # SETUP
    # ========================================================
    #

    def setup(self):

        ScriptedLoadableModuleWidget.setup(self)

        #
        # Logic
        #

        self.logic = VoxelRegionGrowingLogic()

        #
        # ----------------------------------------------------
        # Title / instructions
        # ----------------------------------------------------
        #

        titleLabel = qt.QLabel(
            "<h3>Voxel Region Growing</h3>"
        )

        self.layout.addWidget(
            titleLabel
        )

        instructionsLabel = qt.QLabel(
            "1. Selecione a segmentação e o segmento de destino abaixo.<br>"
            "2. Clique em <b>Selecionar voxel inicial</b>.<br>"
            "3. Clique em um voxel na Red, Yellow ou Green Slice.<br>"
            "4. Configure os parâmetros.<br>"
            "5. Execute o Region Growing."
        )

        instructionsLabel.wordWrap = True

        self.layout.addWidget(
            instructionsLabel
        )

        #
        # ----------------------------------------------------
        # Target segmentation / segment (seletores manuais)
        # ----------------------------------------------------
        #

        segmentationCollapsible = (
            ctk.ctkCollapsibleButton()
        )

        segmentationCollapsible.text = (
            "Segmentação / Segmento de destino"
        )

        segmentationCollapsible.collapsed = False

        self.layout.addWidget(
            segmentationCollapsible
        )

        segmentationLayout = qt.QFormLayout(
            segmentationCollapsible
        )

        self.targetSegmentationSelector = (
            slicer.qMRMLNodeComboBox()
        )

        self.targetSegmentationSelector.nodeTypes = [
            "vtkMRMLSegmentationNode"
        ]

        self.targetSegmentationSelector.selectNodeUponCreation = False
        self.targetSegmentationSelector.addEnabled = False
        self.targetSegmentationSelector.removeEnabled = False
        self.targetSegmentationSelector.noneEnabled = True
        self.targetSegmentationSelector.showHidden = False
        self.targetSegmentationSelector.showChildNodeTypes = False

        self.targetSegmentationSelector.setMRMLScene(
            slicer.mrmlScene
        )

        self.targetSegmentationSelector.toolTip = (
            "Segmentação onde o region growing será aplicado."
        )

        segmentationLayout.addRow(
            "Segmentação:",
            self.targetSegmentationSelector
        )

        self.targetSegmentComboBox = (
            qt.QComboBox()
        )

        self.targetSegmentComboBox.toolTip = (
            "Segmento de destino. "
            "O crescimento será mergeado neste segmento."
        )

        segmentRow = qt.QHBoxLayout()

        segmentRow.addWidget(
            self.targetSegmentComboBox,
            1
        )

        self.refreshTargetSegmentsButton = qt.QPushButton(
            "Atualizar"
        )

        self.refreshTargetSegmentsButton.toolTip = (
            "Recarrega a lista de segmentos da segmentação selecionada."
        )

        self.refreshTargetSegmentsButton.minimumWidth = 85

        self.refreshTargetSegmentsButton.clicked.connect(
            self.onRefreshTargetSegments
        )

        segmentRow.addWidget(
            self.refreshTargetSegmentsButton
        )

        segmentationLayout.addRow(
            "Segmento:",
            segmentRow
        )

        self.targetInfoLabel = qt.QLabel(
            "Selecione a segmentação e o segmento de destino."
        )

        self.targetInfoLabel.wordWrap = True

        segmentationLayout.addRow(
            "Estado:",
            self.targetInfoLabel
        )

        try:

            self.targetSegmentationSelector.connect(
                "currentNodeChanged(vtkMRMLNode*)",
                self.onTargetSegmentationChanged
            )

        except Exception:

            pass

        try:

            self.targetSegmentComboBox.connect(
                "currentIndexChanged(int)",
                self.updateActiveSegmentation
            )

        except Exception:

            try:

                self.targetSegmentComboBox.currentIndexChanged.connect(
                    self.updateActiveSegmentation
                )

            except Exception:

                pass

        try:

            self.onTargetSegmentationChanged()

        except Exception:

            pass

        #
        # ----------------------------------------------------
        # Volume
        # ----------------------------------------------------
        #

        volumeCollapsible = (
            ctk.ctkCollapsibleButton()
        )

        volumeCollapsible.text = "Volume"

        volumeCollapsible.collapsed = False

        self.layout.addWidget(
            volumeCollapsible
        )

        volumeLayout = qt.QFormLayout(
            volumeCollapsible
        )

        self.volumeSelector = (
            slicer.qMRMLNodeComboBox()
        )

        self.volumeSelector.nodeTypes = [
            "vtkMRMLScalarVolumeNode"
        ]

        self.volumeSelector.selectNodeUponCreation = False
        self.volumeSelector.addEnabled = False
        self.volumeSelector.removeEnabled = False
        self.volumeSelector.noneEnabled = True
        self.volumeSelector.showHidden = False
        self.volumeSelector.showChildNodeTypes = False

        self.volumeSelector.setMRMLScene(
            slicer.mrmlScene
        )

        volumeLayout.addRow(
            "Volume:",
            self.volumeSelector
        )

        #
        # ----------------------------------------------------
        # Mask segmentation (limitar propagação)
        # ----------------------------------------------------
        #

        maskCollapsible = (
            ctk.ctkCollapsibleButton()
        )

        maskCollapsible.text = (
            "Máscara (limitar propagação)"
        )

        maskCollapsible.collapsed = True

        self.layout.addWidget(
            maskCollapsible
        )

        maskLayout = qt.QFormLayout(
            maskCollapsible
        )

        self.maskCheckBox = (
            qt.QCheckBox()
        )

        self.maskCheckBox.checked = False

        self.maskCheckBox.toolTip = (
            "Se ativado, o region growing só propaga "
            "para voxels que também fazem parte do "
            "segmento selecionado abaixo."
        )

        maskLayout.addRow(
            "Limitar à máscara:",
            self.maskCheckBox
        )

        self.maskSegmentationSelector = (
            slicer.qMRMLNodeComboBox()
        )

        self.maskSegmentationSelector.nodeTypes = [
            "vtkMRMLSegmentationNode"
        ]

        self.maskSegmentationSelector.selectNodeUponCreation = False
        self.maskSegmentationSelector.addEnabled = False
        self.maskSegmentationSelector.removeEnabled = False
        self.maskSegmentationSelector.noneEnabled = True
        self.maskSegmentationSelector.showHidden = False
        self.maskSegmentationSelector.showChildNodeTypes = False

        self.maskSegmentationSelector.setMRMLScene(
            slicer.mrmlScene
        )

        self.maskSegmentationSelector.toolTip = (
            "Segmentação que contém a máscara. "
            "O crescimento ficará restrito aos voxels "
            "dentro do segmento selecionado."
        )

        maskLayout.addRow(
            "Segmentação máscara:",
            self.maskSegmentationSelector
        )

        self.maskSegmentComboBox = (
            qt.QComboBox()
        )

        self.maskSegmentComboBox.toolTip = (
            "Segmento usado como máscara. "
            "Apenas voxels com valor > 0 neste segmento "
            "serão considerados."
        )

        maskLayout.addRow(
            "Segmento máscara:",
            self.maskSegmentComboBox
        )

        self.maskInfoLabel = qt.QLabel(
            "Desativado: propagação livre."
        )

        self.maskInfoLabel.wordWrap = True

        maskLayout.addRow(
            "Estado:",
            self.maskInfoLabel
        )

        try:

            self.maskSegmentationSelector.connect(
                "currentNodeChanged(vtkMRMLNode*)",
                self.onMaskSegmentationChanged
            )

        except Exception:

            pass

        try:

            self.maskCheckBox.toggled.connect(
                self.onMaskCheckToggled
            )

        except Exception:

            pass

        try:

            self.onMaskCheckToggled(
                self.maskCheckBox.checked
            )

        except Exception:

            pass

        try:

            self.onMaskSegmentationChanged()

        except Exception:

            pass

        #
        # ----------------------------------------------------
        # Seed
        # ----------------------------------------------------
        #

        seedCollapsible = (
            ctk.ctkCollapsibleButton()
        )

        seedCollapsible.text = (
            "Voxel inicial"
        )

        seedCollapsible.collapsed = False

        self.layout.addWidget(
            seedCollapsible
        )

        seedLayout = qt.QFormLayout(
            seedCollapsible
        )

        self.viewLabel = qt.QLabel(
            "-"
        )

        self.ijkLabel = qt.QLabel(
            "-"
        )

        self.rasLabel = qt.QLabel(
            "-"
        )

        self.valueLabel = qt.QLabel(
            "-"
        )

        seedLayout.addRow(
            "Slice:",
            self.viewLabel
        )

        seedLayout.addRow(
            "IJK:",
            self.ijkLabel
        )

        seedLayout.addRow(
            "RAS:",
            self.rasLabel
        )

        seedLayout.addRow(
            "Valor:",
            self.valueLabel
        )

        #
        # ----------------------------------------------------
        # Select voxel button
        # ----------------------------------------------------
        #

        self.selectVoxelButton = (
            qt.QPushButton(
                "Selecionar voxel inicial"
            )
        )

        self.selectVoxelButton.toolTip = (
            "Ativa a seleção de voxel. "
            "Depois clique em um voxel nas Slice Views."
        )

        self.selectVoxelButton.clicked.connect(
            self.onSelectVoxelButton
        )

        self.layout.addWidget(
            self.selectVoxelButton
        )

        maskMinRow = qt.QHBoxLayout()

        self.selectMinVoxelButton = (
            qt.QPushButton(
                "Selecionar menor valor na máscara"
            )
        )

        self.selectMinVoxelButton.toolTip = (
            "Seleciona automaticamente como voxel inicial "
            "o voxel de menor intensidade dentro da "
            "segmentação selecionada como limite (máscara). "
            "Usa o Volume selecionado e a Segmentação máscara."
        )

        self.selectMinVoxelButton.clicked.connect(
            self.onSelectMinVoxelInMask
        )

        maskMinRow.addWidget(
            self.selectMinVoxelButton,
            1
        )

        interiorLabel = qt.QLabel(
            "Margem interior:"
        )

        interiorLabel.toolTip = (
            "Número de voxels de afastamento da borda da máscara. "
            "O voxel mínimo só será buscado entre voxels que tenham "
            "pelo menos N voxels de máscara ao redor (não pega periferia)."
        )

        maskMinRow.addWidget(
            interiorLabel
        )

        self.interiorMarginSpinBox = (
            qt.QSpinBox()
        )

        self.interiorMarginSpinBox.minimum = 0
        self.interiorMarginSpinBox.maximum = 10
        self.interiorMarginSpinBox.value = 2
        self.interiorMarginSpinBox.singleStep = 1

        self.interiorMarginSpinBox.toolTip = (
            "0 = permite voxels da borda.<br>"
            "1 = pelo menos 1 voxel de máscara ao redor.<br>"
            "2–3 = mais interior (recomendado para não pegar periferia)."
        )

        maskMinRow.addWidget(
            self.interiorMarginSpinBox
        )

        self.layout.addLayout(
            maskMinRow
        )

        #
        # ----------------------------------------------------
        # Parameters
        # ----------------------------------------------------
        #

        parametersCollapsible = (
            ctk.ctkCollapsibleButton()
        )

        parametersCollapsible.text = (
            "Parâmetros do Region Growing"
        )

        parametersCollapsible.collapsed = False

        self.layout.addWidget(
            parametersCollapsible
        )

        parametersLayout = qt.QFormLayout(
            parametersCollapsible
        )

        #
        # Tolerance
        #

        self.toleranceSpinBox = (
            qt.QDoubleSpinBox()
        )

        self.toleranceSpinBox.minimum = 0.0
        self.toleranceSpinBox.maximum = 1000000.0
        self.toleranceSpinBox.singleStep = 1.0
        self.toleranceSpinBox.decimals = 3
        self.toleranceSpinBox.value = 100.0

        self.toleranceSpinBox.toolTip = (
            "Diferença máxima de intensidade permitida "
            "em relação ao valor de referência."
        )

        toleranceRow = qt.QHBoxLayout()

        toleranceRow.addWidget(
            self.toleranceSpinBox,
            1
        )

        self.tolerancePlusButton = qt.QPushButton(
            "+100"
        )

        self.tolerancePlusButton.toolTip = (
            "Soma 100 à tolerância atual."
        )

        self.tolerancePlusButton.minimumWidth = 90

        self.tolerancePlusButton.clicked.connect(
            self.onTolerancePlus
        )

        toleranceRow.addWidget(
            self.tolerancePlusButton
        )

        parametersLayout.addRow(
            "Tolerância:",
            toleranceRow
        )

        #
        # Loops
        #

        self.loopsSpinBox = (
            qt.QSpinBox()
        )

        self.loopsSpinBox.minimum = 0
        self.loopsSpinBox.maximum = 100000
        self.loopsSpinBox.value = 10

        self.loopsSpinBox.toolTip = (
            "Número máximo de camadas de propagação "
            "a partir do voxel inicial."
        )

        parametersLayout.addRow(
            "Loops:",
            self.loopsSpinBox
        )

        #
        # Connectivity
        #

        self.connectivityComboBox = (
            qt.QComboBox()
        )

        self.connectivityComboBox.addItem(
            "6 vizinhos",
            6
        )

        self.connectivityComboBox.addItem(
            "18 vizinhos",
            18
        )

        self.connectivityComboBox.addItem(
            "26 vizinhos",
            26
        )

        self.connectivityComboBox.toolTip = (
            "6: faces<br>"
            "18: faces + arestas<br>"
            "26: faces + arestas + vértices"
        )

        parametersLayout.addRow(
            "Conectividade:",
            self.connectivityComboBox
        )

        #
        # Adaptive reference
        #

        self.adaptiveCheckBox = (
            qt.QCheckBox()
        )

        self.adaptiveCheckBox.checked = False

        self.adaptiveCheckBox.toolTip = (
            "Atualiza progressivamente o valor de referência "
            "conforme novos voxels são aceitos."
        )

        parametersLayout.addRow(
            "Referência adaptativa:",
            self.adaptiveCheckBox
        )

        #
        # Maximum voxels
        #

        self.maxVoxelsSpinBox = (
            qt.QSpinBox()
        )

        self.maxVoxelsSpinBox.minimum = 1
        self.maxVoxelsSpinBox.maximum = 2000000000
        self.maxVoxelsSpinBox.value = 5000000

        self.maxVoxelsSpinBox.toolTip = (
            "Limite de segurança para o número máximo "
            "de voxels aceitos."
        )

        parametersLayout.addRow(
            "Máx. voxels:",
            self.maxVoxelsSpinBox
        )

        #
        # ----------------------------------------------------
        # Execute button
        # ----------------------------------------------------
        #

        self.undoButton = qt.QPushButton(
            "Desfazer"
        )

        self.undoButton.enabled = False

        self.undoButton.toolTip = (
            "Restaura o segmento ativo ao estado anterior "
            "ao último crescimento/refinamento/buracos/automação."
        )

        self.undoButton.clicked.connect(
            self.onUndo
        )

        self.layout.addWidget(
            self.undoButton
        )

        self.growButton = (
            qt.QPushButton(
                "Executar Region Growing"
            )
        )

        self.growButton.enabled = False

        self.growButton.toolTip = (
            "Executa o crescimento de região usando "
            "o voxel selecionado."
        )

        self.growButton.clicked.connect(
            self.onGrow
        )

        self.layout.addWidget(
            self.growButton
        )

        self.cancelGrowButton = qt.QPushButton(
            "Cancelar propagação"
        )

        self.cancelGrowButton.enabled = False

        self.cancelGrowButton.toolTip = (
            "Cancela a propagação em andamento. "
            "O resultado parcial é descartado."
        )

        self.cancelGrowButton.clicked.connect(
            self.onCancelGrow
        )

        self.layout.addWidget(
            self.cancelGrowButton
        )

        #
        # ----------------------------------------------------
        # Fill holes button (preenche buracos internos)
        # ----------------------------------------------------
        #

        self.fillHolesButton = (
            qt.QPushButton(
                "Preencher buracos internos"
            )
        )

        self.fillHolesButton.toolTip = (
            "Preenche buracos internos (cavidades fechadas) "
            "do segmento ativo da segmentação ativa. "
            "Corrige segmentações ocas sem alterar o contorno externo."
        )

        self.fillHolesButton.clicked.connect(
            self.onFillHoles
        )

        self.layout.addWidget(
            self.fillHolesButton
        )

        #
        # ----------------------------------------------------
        # Refinamento: remover pontes finas / ilhas por poucos voxels
        # (menos destrutivo que joint smoothing)
        # ----------------------------------------------------
        #

        refineCollapsible = (
            ctk.ctkCollapsibleButton()
        )

        refineCollapsible.text = (
            "Refinamento (ponte fina)"
        )

        refineCollapsible.collapsed = False

        self.layout.addWidget(
            refineCollapsible
        )

        refineLayout = qt.QFormLayout(
            refineCollapsible
        )

        refineInfo = qt.QLabel(
            "Remove ilhas/protrusões ligadas ao corpo principal "
            "por ponte fina de poucos voxels. "
            "Menos destrutivo que joint smoothing: áreas sem ponte "
            "não são alteradas."
        )

        refineInfo.wordWrap = True

        refineLayout.addRow(
            refineInfo
        )

        self.bridgeRadiusSpinBox = (
            qt.QSpinBox()
        )

        self.bridgeRadiusSpinBox.minimum = 1
        self.bridgeRadiusSpinBox.maximum = 5
        self.bridgeRadiusSpinBox.value = 1
        self.bridgeRadiusSpinBox.singleStep = 1

        self.bridgeRadiusSpinBox.toolTip = (
            "Espessura da ponte a remover (em voxels).<br>"
            "1 = remove ligações de 1–2 voxels.<br>"
            "2 = mais agressivo, remove pontes de até ~4 voxels.<br>"
            "Mantenha em 1 para ser o menos destrutivo possível."
        )

        refineLayout.addRow(
            "Espessura da ponte:",
            self.bridgeRadiusSpinBox
        )

        self.keepLargestOnlyCheckBox = (
            qt.QCheckBox()
        )

        self.keepLargestOnlyCheckBox.checked = True

        self.keepLargestOnlyCheckBox.toolTip = (
            "Se marcado, mantém apenas o maior corpo após "
            "quebrar pontes finas.<br>"
            "Se desmarcado, mantém todos os corpos grandes "
            "que sobreviverem à erosão (útil se houver 2 órgãos separados)."
        )

        refineLayout.addRow(
            "Manter só maior corpo:",
            self.keepLargestOnlyCheckBox
        )

        self.refineBridgesButton = (
            qt.QPushButton(
                "Refinar: remover pontes finas"
            )
        )

        self.refineBridgesButton.toolTip = (
            "Refinamento por abertura por reconstrução geodésica.<br>"
            "Erode por N voxels → quebra pontes finas → "
            "reconstrói só o maior corpo dentro da máscara original.<br>"
            "Regiões sem ponte fina permanecem idênticas."
        )

        self.refineBridgesButton.clicked.connect(
            self.onRefineBridges
        )

        refineLayout.addRow(
            self.refineBridgesButton
        )

        #
        # ----------------------------------------------------
        # Automação completa
        # ----------------------------------------------------
        #

        autoCollapsible = (
            ctk.ctkCollapsibleButton()
        )

        autoCollapsible.text = (
            "Automação completa"
        )

        autoCollapsible.collapsed = False

        self.layout.addWidget(
            autoCollapsible
        )

        autoLayout = qt.QVBoxLayout(
            autoCollapsible
        )

        autoInfo = qt.QLabel(
            "1 clique: pega o voxel de menor valor dentro da "
            "segmentação limite → faz a propagação com os "
            "parâmetros configurados dentro do limite → refina "
            "removendo pontes finas.<br>"
            "<b>Requisito:</b> deixe <b>Máscara</b> ativada e "
            "selecione a segmentação/segmento limite. "
            "O resultado vai para o <b>segmento ativo</b> da "
            "segmentação ativa."
        )

        autoInfo.wordWrap = True

        autoLayout.addWidget(
            autoInfo
        )

        autoForm = qt.QFormLayout()

        autoLayout.addLayout(
            autoForm
        )

        self.autoRefineCheckBox = (
            qt.QCheckBox()
        )

        self.autoRefineCheckBox.checked = True

        self.autoRefineCheckBox.toolTip = (
            "Se marcado, ao final da propagação executa "
            "automaticamente o refinamento de pontes finas "
            "com o raio configurado acima."
        )

        autoForm.addRow(
            "Refinar ao final:",
            self.autoRefineCheckBox
        )

        self.autoFillHolesCheckBox = (
            qt.QCheckBox()
        )

        self.autoFillHolesCheckBox.checked = False

        self.autoFillHolesCheckBox.toolTip = (
            "Se marcado, também preenche buracos internos "
            "após o refinamento."
        )

        autoForm.addRow(
            "Preencher buracos ao final:",
            self.autoFillHolesCheckBox
        )

        self.autoRunButton = (
            qt.QPushButton(
                "▶ Executar automação completa"
            )
        )

        self.autoRunButton.toolTip = (
            "Executa em sequência: voxel mínimo na máscara → "
            "region growing dentro do limite → refinamento (+ fill holes se marcado)."
        )

        self.autoRunButton.clicked.connect(
            self.onAutoRun
        )

        autoLayout.addWidget(
            self.autoRunButton
        )

        #
        # ----------------------------------------------------
        # Progress
        # ----------------------------------------------------
        #

        self.progressBar = (
            qt.QProgressBar()
        )

        self.progressBar.minimum = 0
        self.progressBar.maximum = 100
        self.progressBar.value = 0

        self.layout.addWidget(
            self.progressBar
        )

        #
        # ----------------------------------------------------
        # Status
        # ----------------------------------------------------
        #

        self.statusLabel = qt.QLabel(
            "Clique em 'Selecionar voxel inicial'."
        )

        self.statusLabel.wordWrap = True
        self.statusLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse

        self.layout.addWidget(
            self.statusLabel
        )

        #
        # ----------------------------------------------------
        # Console (log copiável)
        # ----------------------------------------------------
        #

        consoleCollapsible = (
            ctk.ctkCollapsibleButton()
        )

        consoleCollapsible.text = (
            "Console / Log (copiável)"
        )

        consoleCollapsible.collapsed = False

        self.layout.addWidget(
            consoleCollapsible
        )

        consoleLayout = qt.QVBoxLayout(
            consoleCollapsible
        )

        self.logTextEdit = qt.QPlainTextEdit()

        self.logTextEdit.readOnly = True
        self.logTextEdit.placeholderText = (
            "Log do Voxel Region Growing. Erros e mensagens aparecerão aqui e podem ser copiados."
        )

        try:

            self.logTextEdit.lineWrapMode = qt.QPlainTextEdit.NoWrap

        except Exception:

            pass

        self.logTextEdit.minimumHeight = 140
        self.logTextEdit.maximumHeight = 220

        try:

            self.logTextEdit.setTextInteractionFlags(
                qt.Qt.TextSelectableByMouse
                | qt.Qt.TextSelectableByKeyboard
            )

        except Exception:

            pass

        consoleLayout.addWidget(
            self.logTextEdit
        )

        consoleButtonLayout = qt.QHBoxLayout()

        consoleLayout.addLayout(
            consoleButtonLayout
        )

        self.copyLogButton = qt.QPushButton(
            "Copiar log"
        )

        self.copyLogButton.toolTip = (
            "Copia todo o conteúdo do console para a área de transferência."
        )

        self.copyLogButton.clicked.connect(
            self.onCopyLog
        )

        consoleButtonLayout.addWidget(
            self.copyLogButton
        )

        self.copyLastErrorButton = qt.QPushButton(
            "Copiar último erro"
        )

        self.copyLastErrorButton.toolTip = (
            "Copia apenas o último erro para a área de transferência."
        )

        self.copyLastErrorButton.clicked.connect(
            self.onCopyLastError
        )

        consoleButtonLayout.addWidget(
            self.copyLastErrorButton
        )

        self.clearLogButton = qt.QPushButton(
            "Limpar"
        )

        self.clearLogButton.toolTip = (
            "Limpa o console."
        )

        self.clearLogButton.clicked.connect(
            self.onClearLog
        )

        consoleButtonLayout.addWidget(
            self.clearLogButton
        )

        self.lastErrorText = ""

        try:

            self.appendLog(
                "[VoxelRegionGrowing] Console pronto. Erros ficarão copiáveis aqui."
            )

        except Exception:

            pass

        #
        # ----------------------------------------------------
        # Layout manager
        # ----------------------------------------------------
        #

        try:

            self.layoutManager = (
                slicer.app.layoutManager()
            )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "Erro obtendo layout manager:",
                e
            )

        #
        # ----------------------------------------------------
        # Install slice observers
        # ----------------------------------------------------
        #

        qt.QTimer.singleShot(
            500,
            self.installSliceObservers
        )

        #
        # ----------------------------------------------------
        # Refresh active segmentation
        # ----------------------------------------------------
        #

        self.updateActiveSegmentation()

        #
        # ----------------------------------------------------
        # Refresh timer
        # ----------------------------------------------------
        #

        self.refreshTimer = qt.QTimer()

        self.refreshTimer.setInterval(
            500
        )

        self.refreshTimer.timeout.connect(
            self.updateActiveSegmentation
        )

        self.refreshTimer.start()

    #
    # ========================================================
    # UPDATE ACTIVE SEGMENTATION
    # ========================================================
    #

    def updateActiveSegmentation(self):

        try:

            segmentationNode = None

            segmentID = None

            try:

                segmentationNode = self.getTargetSegmentationNode()

            except Exception:

                segmentationNode = None

            try:

                segmentID = self.getTargetSegmentID()

            except Exception:

                segmentID = None

            if hasattr(self, "targetInfoLabel") and self.targetInfoLabel is not None:

                try:

                    if segmentationNode is None:

                        self.targetInfoLabel.text = (
                            "Selecione a segmentação e o segmento de destino."
                        )

                    elif not segmentID:

                        self.targetInfoLabel.text = (
                            "Segmentação '{}' selecionada — escolha o segmento.".format(
                                segmentationNode.GetName() or segmentationNode.GetID()
                            )
                        )

                    else:

                        try:

                            seg = segmentationNode.GetSegmentation().GetSegment(segmentID)

                            segName = seg.GetName() if seg and seg.GetName() else segmentID

                        except Exception:

                            segName = segmentID

                        self.targetInfoLabel.text = (
                            "Destino: {} / {}".format(
                                segmentationNode.GetName() or segmentationNode.GetID(),
                                segName
                            )
                        )

                except Exception:

                    pass

            #
            # Auto-select single volume
            #

            try:

                self._autoSelectSingleVolumeIfNeeded()

            except Exception:

                pass

            #
            # Enable grow only when seed + target selected
            #

            enabled = (
                self.seedIJK is not None
                and
                segmentationNode is not None
                and
                segmentID is not None
                and
                segmentID != ""
            )

            for btnName in ["growButton", "fillHolesButton", "refineBridgesButton", "autoRunButton"]:

                btn = getattr(self, btnName, None)

                if btn is None:

                    continue

                try:

                    if btnName == "growButton":

                        btn.enabled = enabled

                    else:

                        segOk = segmentationNode is not None and segmentID not in (None, "")

                        if btnName == "autoRunButton":

                            btn.enabled = segOk

                        else:

                            btn.enabled = segOk

                except Exception:

                    pass

            try:

                self._updateUndoButton()

            except Exception:

                pass

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "Erro atualizando segmentação:",
                e
            )

    def getTargetSegmentationNode(self):

        try:

            if hasattr(self, "targetSegmentationSelector") and self.targetSegmentationSelector is not None:

                return self.targetSegmentationSelector.currentNode()

        except Exception:

            pass

        return None

    def _qvariantToString(self, v):

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

            try:

                return str(v)

            except Exception:

                return None

    def getTargetSegmentID(self):

        try:

            cb = getattr(self, "targetSegmentComboBox", None)

            ids = getattr(self, "targetSegmentIDs", None)

            if cb is None:

                return None

            idx = -1

            try:

                idx = cb.currentIndex

                if callable(idx):

                    idx = idx()

                idx = int(idx)

            except Exception:

                try:

                    idx = int(cb.currentIndex())

                except Exception:

                    idx = -1

            if idx >= 0 and isinstance(ids, list) and 0 <= idx < len(ids):

                sid = ids[idx]

                sid = self._qvariantToString(sid)

                if sid is not None and sid != "":

                    return sid

            if idx >= 0:

                try:

                    sid = cb.itemData(idx)

                    sid = self._qvariantToString(sid)

                    if sid is not None and sid != "":

                        return sid

                except Exception:

                    pass

            try:

                cd = getattr(cb, "currentData", None)

                if cd is not None:

                    if callable(cd):

                        try:

                            sid = cd()

                        except Exception:

                            try:

                                sid = cd(0)

                            except Exception:

                                sid = None

                    else:

                        sid = cd

                    sid = self._qvariantToString(sid)

                    if sid is not None and sid != "":

                        return sid

            except Exception:

                pass

        except Exception:

            pass

        return None

    def onTargetSegmentationChanged(self, node=None):

        try:

            if node is None:

                try:

                    node = self.targetSegmentationSelector.currentNode()

                except Exception:

                    node = None

            self.updateTargetSegmentComboBox(node)

            self.updateActiveSegmentation()

        except Exception as e:

            print(
                "[VoxelRegionGrowing] Erro onTargetSegmentationChanged:",
                e
            )

    def updateTargetSegmentComboBox(self, segmentationNode):

        try:

            cb = getattr(self, "targetSegmentComboBox", None)

            if cb is None:

                return

            previousID = None

            try:

                previousID = self.getTargetSegmentID()

            except Exception:

                previousID = None

            try:

                cb.blockSignals(True)

            except Exception:

                pass

            cb.clear()

            self.targetSegmentIDs = []

            if segmentationNode is None:

                cb.addItem("Nenhum", "")

                self.targetSegmentIDs = [""]

                try:

                    cb.blockSignals(False)

                except Exception:

                    pass

                return

            segmentation = segmentationNode.GetSegmentation()

            if segmentation is None:

                cb.addItem("Nenhum", "")

                self.targetSegmentIDs = [""]

                try:

                    cb.blockSignals(False)

                except Exception:

                    pass

                return

            num = segmentation.GetNumberOfSegments()

            if num <= 0:

                cb.addItem("Nenhum", "")

                self.targetSegmentIDs = [""]

                try:

                    cb.blockSignals(False)

                except Exception:

                    pass

                return

            foundPrevious = False

            previousIdx = -1

            for i in range(num):

                sid = segmentation.GetNthSegmentID(i)

                seg = segmentation.GetSegment(sid)

                name = sid

                if seg:

                    n = seg.GetName()

                    if n:

                        name = n

                cb.addItem(name, sid)

                self.targetSegmentIDs.append(sid)

                if sid is not None and previousID is not None and sid == previousID:

                    foundPrevious = True

                    previousIdx = i

            if foundPrevious and previousIdx >= 0:

                cb.currentIndex = previousIdx

            elif not foundPrevious and previousID is not None:

                print(
                    "[VoxelRegionGrowing] updateTargetSegmentComboBox: segmento anterior '{}' não encontrado, mantendo índice 0".format(previousID)
                )

            try:

                cb.blockSignals(False)

            except Exception:

                pass

            try:

                self.updateActiveSegmentation()

            except Exception:

                pass

        except Exception as e:

            print(
                "[VoxelRegionGrowing] Erro updateTargetSegmentComboBox:",
                e
            )

    def onRefreshTargetSegments(self):

        try:

            node = None

            try:

                node = self.targetSegmentationSelector.currentNode()

            except Exception:

                node = None

            if node is None:

                slicer.util.warningDisplay(
                    "Selecione primeiro uma segmentação."
                )

                return

            try:

                node.CreateDefaultDisplayNodes()

            except Exception:

                pass

            seg = node.GetSegmentation()

            if seg is not None:

                try:

                    seg.CreateRepresentation("Binary labelmap")

                except Exception:

                    pass

            self.updateTargetSegmentComboBox(node)

            self.updateActiveSegmentation()

            try:

                count = seg.GetNumberOfSegments() if seg else 0

            except Exception:

                count = -1

            if count >= 0:

                self.targetInfoLabel.text = (
                    "Lista atualizada: {} segmento(s) em '{}'.".format(
                        count,
                        node.GetName() or node.GetID()
                    )
                )

            try:

                self.appendLog(
                    "Segmentos atualizados: {} em '{}'".format(count, node.GetName() or node.GetID())
                )

            except Exception:

                pass

            self.statusLabel.text = "Lista de segmentos atualizada."

        except Exception as e:

            import traceback

            traceback.print_exc()

            msg = "Erro ao atualizar segmentos: {}".format(e)

            try:

                self.appendLog(msg + "\n" + traceback.format_exc())

            except Exception:

                pass

            slicer.util.errorDisplay(msg)

    def _autoSelectSingleVolumeIfNeeded(self):

        if not hasattr(self, "volumeSelector") or self.volumeSelector is None:

            return

        try:

            cur = self.volumeSelector.currentNode()

        except Exception:

            cur = None

        if cur is not None:

            return

        try:

            n = slicer.mrmlScene.GetNumberOfNodesByClass(
                "vtkMRMLScalarVolumeNode"
            )

        except Exception:

            n = 0

        if n != 1:

            return

        try:

            single = slicer.mrmlScene.GetFirstNodeByClass(
                "vtkMRMLScalarVolumeNode"
            )

        except Exception:

            single = None

        if single is None:

            return

        try:

            self.volumeSelector.setCurrentNode(
                single
            )

        except Exception:

            try:

                self.volumeSelector.setCurrentNodeID(
                    single.GetID()
                )

            except Exception:

                return

        try:

            name = single.GetName() or single.GetID()

        except Exception:

            name = "volume único"

        try:

            self.appendLog(
                "Volume único auto-selecionado: {}".format(name)
            )

        except Exception:

            pass

    #
    # ========================================================
    # GET ACTIVE SEGMENTATION
    # ========================================================
    #

    def _getSegmentEditorParameterNode(self):

        try:

            node = (
                slicer.mrmlScene.GetFirstNodeByClass(
                    "vtkMRMLSegmentEditorNode"
                )
            )

            if node is not None:

                return node

        except Exception:

            pass

        try:

            node = (
                slicer.mrmlScene.GetSingletonNode(
                    "SegmentEditor",
                    "vtkMRMLSegmentEditorNode"
                )
            )

            if node is not None:

                return node

        except Exception:

            pass

        return None

    def getActiveSegmentationNode(self):

        #
        # 1) Segment Editor widget
        #

        try:

            segmentEditorModule = (
                slicer.modules.segmenteditor
            )

            widgetRepresentation = (
                segmentEditorModule.widgetRepresentation()
            )

            if widgetRepresentation:

                editorWidget = (
                    widgetRepresentation.self()
                )

                if editorWidget:

                    editor = (
                        editorWidget.editor
                    )

                    if editor:

                        segmentationNode = (
                            editor.segmentationNode()
                        )

                        if segmentationNode:

                            return segmentationNode

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "Segment Editor widget lookup:",
                e
            )

        #
        # 2) SegmentEditor parameter node (mais robusto no 5.12)
        #

        try:

            pe = self._getSegmentEditorParameterNode()

            if pe is not None:

                try:

                    segmentationNode = pe.GetSegmentationNode()

                    if segmentationNode:

                        return segmentationNode

                except Exception:

                    pass

                try:

                    sid = pe.GetSegmentationNodeID()

                    if sid:

                        node = slicer.mrmlScene.GetNodeByID(
                            sid
                        )

                        if node is not None:

                            return node

                except Exception:

                    pass

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "SegmentEditorNode lookup:",
                e
            )

        #
        # 3) Fallback: first segmentation node
        #

        try:

            return (
                slicer.mrmlScene.GetFirstNodeByClass(
                    "vtkMRMLSegmentationNode"
                )
            )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] fallback segmentation lookup:",
                e
            )

            return None

    #
    # ========================================================
    # GET ACTIVE SEGMENT
    # ========================================================
    #

    def getActiveSegmentID(self):

        #
        # 1) Segment Editor widget
        #

        try:

            segmentEditorModule = (
                slicer.modules.segmenteditor
            )

            widgetRepresentation = (
                segmentEditorModule.widgetRepresentation()
            )

            if widgetRepresentation:

                editorWidget = (
                    widgetRepresentation.self()
                )

                if editorWidget:

                    editor = (
                        editorWidget.editor
                    )

                    if editor:

                        try:

                            segmentID = (
                                editor.currentSegmentID()
                            )

                        except Exception:

                            segmentID = None

                        if segmentID:

                            return segmentID

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "Erro obtendo segmento ativo (widget):",
                e
            )

        #
        # 2) SegmentEditor parameter node
        #

        try:

            pe = self._getSegmentEditorParameterNode()

            if pe is not None:

                try:

                    sid = pe.GetSelectedSegmentID()

                    if sid:

                        return sid

                except Exception:

                    pass

                try:

                    sid = pe.GetCurrentSegmentID()

                    if sid:

                        return sid

                except Exception:

                    pass

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "Erro obtendo segmento ativo (parameter node):",
                e
            )

        #
        # Fallback:
        # First segment
        #

        segmentationNode = (
            self.getActiveSegmentationNode()
        )

        if segmentationNode:

            segmentation = (
                segmentationNode.GetSegmentation()
            )

            if (
                segmentation.GetNumberOfSegments()
                > 0
            ):

                return (
                    segmentation.GetNthSegmentID(
                        0
                    )
                )

        return None

    #
    # ========================================================
    # MASK SEGMENTATION HELPERS
    # ========================================================
    #

    def onMaskCheckToggled(self, checked):

        try:

            checked = bool(
                checked
            )

            if hasattr(self, "maskInfoLabel"):

                if checked:

                    self.maskInfoLabel.text = (
                        "Ativado: crescimento restrito à máscara."
                    )

                else:

                    self.maskInfoLabel.text = (
                        "Desativado: propagação livre."
                    )

            if hasattr(self, "maskSegmentationSelector"):

                self.maskSegmentationSelector.enabled = (
                    checked
                )

            if hasattr(self, "maskSegmentComboBox"):

                self.maskSegmentComboBox.enabled = (
                    checked
                )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "Erro onMaskCheckToggled:",
                e
            )

    def onMaskSegmentationChanged(self, node=None):

        try:

            if node is None:

                try:

                    node = (
                        self.maskSegmentationSelector.currentNode()
                    )

                except Exception:

                    node = None

            self.updateMaskSegmentComboBox(
                node
            )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "Erro onMaskSegmentationChanged:",
                e
            )

    def updateMaskSegmentComboBox(self, segmentationNode):

        try:

            if self.maskSegmentComboBox is None:

                return

            previousID = None

            try:

                previousID = (
                    self.maskSegmentComboBox.currentData
                )

            except Exception:

                previousID = None

            self.maskSegmentComboBox.clear()

            if segmentationNode is None:

                self.maskSegmentComboBox.addItem(
                    "Nenhum",
                    ""
                )

                return

            segmentation = (
                segmentationNode.GetSegmentation()
            )

            if segmentation is None:

                self.maskSegmentComboBox.addItem(
                    "Nenhum",
                    ""
                )

                return

            num = (
                segmentation.GetNumberOfSegments()
            )

            if num <= 0:

                self.maskSegmentComboBox.addItem(
                    "Nenhum",
                    ""
                )

                return

            foundPrevious = False

            for i in range(
                num
            ):

                sid = (
                    segmentation.GetNthSegmentID(
                        i
                    )
                )

                seg = (
                    segmentation.GetSegment(
                        sid
                    )
                )

                name = sid

                if seg:

                    n = seg.GetName()

                    if n:

                        name = n

                self.maskSegmentComboBox.addItem(
                    name,
                    sid
                )

                if sid == previousID:

                    foundPrevious = True

            if foundPrevious:

                idx = (
                    self.maskSegmentComboBox.findData(
                        previousID
                    )
                )

                if idx >= 0:

                    self.maskSegmentComboBox.currentIndex = (
                        idx
                    )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "Erro updateMaskSegmentComboBox:",
                e
            )

    def getMaskInfo(self):

        try:

            enabled = False

            try:

                enabled = bool(
                    self.maskCheckBox.checked
                )

            except Exception:

                enabled = False

            if not enabled:

                return (
                    False,
                    None,
                    None
                )

            segNode = None

            try:

                segNode = (
                    self.maskSegmentationSelector.currentNode()
                )

            except Exception:

                segNode = None

            segID = None

            try:

                segID = (
                    self.maskSegmentComboBox.currentData
                )

            except Exception:

                segID = None

            if segID == "":

                segID = None

            return (
                True,
                segNode,
                segID
            )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "Erro getMaskInfo:",
                e
            )

            return (
                False,
                None,
                None
            )

    #
    # ========================================================
    # LAYOUT CHANGED
    # ========================================================
    #

    def onLayoutChanged(self, layout):

        qt.QTimer.singleShot(
            300,
            self.installSliceObservers
        )

    #
    # ========================================================
    # INSTALL SLICE OBSERVERS
    # ========================================================
    #

    def installSliceObservers(self):

        #
        # Get layout manager
        #

        if self.layoutManager is None:

            try:

                self.layoutManager = (
                    slicer.app.layoutManager()
                )

            except Exception:

                return

        if self.layoutManager is None:

            return

        #
        # Slice names
        #

        sliceNames = [
            "Red",
            "Yellow",
            "Green"
        ]

        #
        # Install observer on each slice
        #

        for sliceName in sliceNames:

            try:

                sliceWidget = (
                    self.layoutManager.sliceWidget(
                        sliceName
                    )
                )

                if sliceWidget is None:

                    continue

                sliceView = (
                    sliceWidget.sliceView()
                )

                if sliceView is None:

                    continue

                interactor = (
                    sliceView.interactor()
                )

                if interactor is None:

                    continue

                #
                # Existing observer
                #

                old = (
                    self.sliceObservers.get(
                        sliceName
                    )
                )

                if old:

                    if (
                        old["interactor"]
                        ==
                        interactor
                    ):

                        continue

                    try:

                        old["interactor"].RemoveObserver(
                            old["tag"]
                        )

                    except Exception:

                        pass

                #
                # Callback
                #

                callback = (
                    self.createSliceCallback(
                        sliceWidget,
                        sliceName
                    )
                )

                #
                # Observer
                #

                tag = interactor.AddObserver(
                    vtk.vtkCommand.LeftButtonPressEvent,
                    callback
                )

                self.sliceObservers[
                    sliceName
                ] = {
                    "interactor": interactor,
                    "tag": tag,
                    "callback": callback,
                    "sliceWidget": sliceWidget
                }

                print(
                    "[VoxelRegionGrowing] "
                    "Observer instalado:",
                    sliceName
                )

            except Exception as e:

                print(
                    "[VoxelRegionGrowing] "
                    "Erro instalando observer:",
                    sliceName,
                    e
                )

    #
    # ========================================================
    # CREATE SLICE CALLBACK
    # ========================================================
    #

    def createSliceCallback(
        self,
        sliceWidget,
        sliceName
    ):

        def callback(
            caller,
            event
        ):

            self.onSliceLeftButtonPress(
                sliceWidget,
                sliceName,
                caller,
                event
            )

        return callback

    #
    # ========================================================
    # SELECT VOXEL BUTTON
    # ========================================================
    #

    def onSelectVoxelButton(self):

        #
        # Cancel
        #

        if self.selectingVoxel:

            self.selectingVoxel = False

            self.selectVoxelButton.text = (
                "Selecionar voxel inicial"
            )

            self.statusLabel.text = (
                "Seleção cancelada."
            )

            print(
                "[VoxelRegionGrowing] "
                "Modo de seleção DESATIVADO"
            )

            return

        #
        # Activate
        #

        self.selectingVoxel = True

        self.selectVoxelButton.text = (
            "Clique em um voxel..."
        )

        self.statusLabel.text = (
            "Modo de seleção ativo. "
            "Clique em um voxel na Red, Yellow "
            "ou Green Slice."
        )

        print(
            "[VoxelRegionGrowing] "
            "Modo de seleção ATIVADO"
        )

    def onSelectMinVoxelInMask(self):

        volumeNode = None

        try:

            volumeNode = self.volumeSelector.currentNode()

        except Exception:

            volumeNode = None

        if volumeNode is None:

            try:

                lm = slicer.app.layoutManager()

                if lm is not None:

                    for n in ["Red", "Yellow", "Green"]:

                        w = lm.sliceWidget(n)

                        if w is None:

                            continue

                        vn = self.getVolumeForSlice(w)

                        if vn is not None:

                            volumeNode = vn

                            break

            except Exception:

                pass

        if volumeNode is None:

            slicer.util.errorDisplay(
                "Selecione um Volume válido (ou deixe um volume visível nas slices)."
            )

            return

        maskEnabled, maskSegmentationNode, maskSegmentID = self.getMaskInfo()

        if not maskEnabled or maskSegmentationNode is None or not maskSegmentID:

            slicer.util.errorDisplay(
                "Ative a máscara e selecione a Segmentação máscara e o Segmento máscara. "
                "O botão busca o menor valor dentro desse segmento limite."
            )

            return

        try:

            try:

                margin = int(
                    self.interiorMarginSpinBox.value
                )

            except Exception:

                margin = 2

            self.statusLabel.text = (
                "Buscando voxel de menor valor dentro da máscara (margem interior={})...".format(
                    margin
                )
            )

            qt.QApplication.processEvents()

            ijk, value, ras = self.logic.findMinVoxelInMask(
                volumeNode,
                maskSegmentationNode,
                maskSegmentID,
                interiorMargin=margin
            )

            if ijk is None:

                slicer.util.warningDisplay(
                    "Nenhum voxel encontrado dentro da máscara."
                )

                return

            self.seedIJK = list(ijk)
            self.seedRAS = list(ras)
            self.seedValue = float(value)
            self.seedVolumeNode = volumeNode
            self.seedSliceName = "Auto (mínimo na máscara)"

            self.selectingVoxel = False

            self.selectVoxelButton.text = (
                "Selecionar voxel inicial"
            )

            self.viewLabel.text = self.seedSliceName

            self.ijkLabel.text = "[{}, {}, {}]".format(
                ijk[0], ijk[1], ijk[2]
            )

            self.rasLabel.text = "[{:.3f}, {:.3f}, {:.3f}]".format(
                ras[0], ras[1], ras[2]
            )

            self.valueLabel.text = "{:.4f}".format(
                value
            )

            self.statusLabel.text = (
                "Voxel mínimo na máscara selecionado."
            )

            try:

                self.growButton.enabled = True

            except Exception:

                pass

            self.showSeedMarker(
                ras
            )

            self.updateActiveSegmentation()

            try:

                self.appendLog(
                    "Seed automático (mínimo na máscara): IJK {} valor {:.4f} RAS [{:.2f},{:.2f},{:.2f}]".format(
                        ijk, float(value), float(ras[0]), float(ras[1]), float(ras[2])
                    )
                )

            except Exception:

                pass

            print("========================================")
            print("[VoxelRegionGrowing] VOXEL MÍNIMO NA MÁSCARA")
            print("IJK:", ijk)
            print("Valor:", value)
            print("RAS:", ras)
            print("Volume:", volumeNode.GetName())
            print("Máscara:", maskSegmentationNode.GetName(), maskSegmentID)
            print("========================================")

        except Exception as e:

            import traceback

            traceback.print_exc()

            tb = traceback.format_exc()

            msg = "Erro ao buscar voxel mínimo na máscara:\n{}\n\n{}".format(
                e, tb
            )

            self.lastErrorText = msg

            try:

                self.appendLog(
                    "ERRO voxel mínimo na máscara: {}\n{}".format(e, tb)
                )

            except Exception:

                pass

            try:

                self.statusLabel.text = (
                    "Erro voxel mínimo: {} (ver Console)".format(e)
                )

                self.statusLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse

            except Exception:

                pass

            slicer.util.errorDisplay(
                "Erro ao buscar voxel mínimo na máscara (copiável no Console):\n\n{}".format(
                    msg
                )
            )

    #
    # ========================================================
    # SLICE CLICK
    # ========================================================
    #

    def onSliceLeftButtonPress(
        self,
        sliceWidget,
        sliceName,
        caller,
        event
    ):

        #
        # Ignore click when selection mode disabled
        #

        if not self.selectingVoxel:

            return

        try:

            #
            # Mouse position
            #

            position = (
                caller.GetEventPosition()
            )

            x = int(
                position[0]
            )

            y = int(
                position[1]
            )

            print(
                "[VoxelRegionGrowing] "
                "Clique recebido:",
                sliceName,
                x,
                y
            )

            #
            # Slice node
            #

            sliceNode = (
                sliceWidget.mrmlSliceNode()
            )

            if sliceNode is None:

                raise RuntimeError(
                    "SliceNode não encontrado."
                )

            #
            # IMPORTANT:
            #
            # In Slicer 5.12 GetXYToRAS()
            # returns vtkMatrix4x4 directly.
            #

            xyToRAS = (
                sliceNode.GetXYToRAS()
            )

            if xyToRAS is None:

                raise RuntimeError(
                    "Matriz XY -> RAS não encontrada."
                )

            #
            # XY -> RAS
            #

            rasPoint = (
                xyToRAS.MultiplyPoint(
                    [
                        float(x),
                        float(y),
                        0.0,
                        1.0
                    ]
                )
            )

            clickedRAS = [
                float(rasPoint[0]),
                float(rasPoint[1]),
                float(rasPoint[2])
            ]

            #
            # Get volume
            #

            volumeNode = (
                self.getVolumeForSlice(
                    sliceWidget
                )
            )

            if volumeNode is None:

                raise RuntimeError(
                    "Nenhum volume encontrado "
                    "nesta Slice View."
                )

            #
            # RAS -> IJK
            #

            rasToIJK = (
                vtk.vtkMatrix4x4()
            )

            volumeNode.GetRASToIJKMatrix(
                rasToIJK
            )

            ijkPoint = (
                rasToIJK.MultiplyPoint(
                    [
                        clickedRAS[0],
                        clickedRAS[1],
                        clickedRAS[2],
                        1.0
                    ]
                )
            )

            ijk = [
                int(
                    round(
                        ijkPoint[0]
                    )
                ),
                int(
                    round(
                        ijkPoint[1]
                    )
                ),
                int(
                    round(
                        ijkPoint[2]
                    )
                )
            ]

            #
            # Image data
            #

            imageData = (
                volumeNode.GetImageData()
            )

            if imageData is None:

                raise RuntimeError(
                    "Volume sem ImageData."
                )

            #
            # Extent
            #

            extent = (
                imageData.GetExtent()
            )

            #
            # Validate IJK
            #

            if not self.logic.isIJKInsideExtent(
                ijk,
                extent
            ):

                raise RuntimeError(
                    "IJK fora dos limites do volume.\n"
                    "IJK: {}\n"
                    "Extent: {}".format(
                        ijk,
                        extent
                    )
                )

            #
            # Get value
            #

            value = (
                self.logic.getVoxelValue(
                    volumeNode,
                    ijk
                )
            )

            #
            # Save seed
            #

            self.seedIJK = list(
                ijk
            )

            self.seedRAS = list(
                clickedRAS
            )

            self.seedValue = float(
                value
            )

            self.seedVolumeNode = (
                volumeNode
            )

            self.seedSliceName = (
                sliceName
            )

            #
            # Stop selection immediately
            #

            self.selectingVoxel = False

            self.selectVoxelButton.text = (
                "Selecionar voxel inicial"
            )

            #
            # Update UI
            #

            self.viewLabel.text = (
                sliceName
            )

            self.ijkLabel.text = (
                "[{}, {}, {}]".format(
                    ijk[0],
                    ijk[1],
                    ijk[2]
                )
            )

            self.rasLabel.text = (
                "[{:.3f}, {:.3f}, {:.3f}]".format(
                    clickedRAS[0],
                    clickedRAS[1],
                    clickedRAS[2]
                )
            )

            self.valueLabel.text = (
                "{:.4f}".format(
                    value
                )
            )

            self.statusLabel.text = (
                "Voxel inicial selecionado."
            )

            #
            # Enable grow
            #

            self.growButton.enabled = True

            #
            # Show marker
            #

            self.showSeedMarker(
                clickedRAS
            )

            #
            # Console information
            #

            print(
                "========================================"
            )

            print(
                "[VoxelRegionGrowing] VOXEL INICIAL"
            )

            print(
                "Slice:",
                sliceName
            )

            print(
                "Mouse:",
                x,
                y
            )

            print(
                "IJK:",
                ijk
            )

            print(
                "RAS:",
                clickedRAS
            )

            print(
                "Valor:",
                value
            )

            print(
                "Volume:",
                volumeNode.GetName()
            )

            print(
                "========================================"
            )

        except Exception as e:

            import traceback

            traceback.print_exc()

            tb = traceback.format_exc()

            msg = "Erro ao selecionar voxel:\n{}\n\n{}".format(
                e,
                tb
            )

            self.lastErrorText = msg

            try:

                self.appendLog(
                    "ERRO selecionar voxel: {}\n{}".format(
                        e,
                        tb
                    )
                )

            except Exception:

                pass

            self.statusLabel.text = (
                "Erro ao selecionar voxel: {} (ver Console)".format(
                    e
                )
            )

            try:

                self.statusLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse

            except Exception:

                pass

            slicer.util.errorDisplay(
                "Erro ao selecionar voxel (copiável no Console):\n\n{}".format(
                    msg
                )
            )

    #
    # ========================================================
    # GET VOLUME FOR SLICE
    # ========================================================
    #

    def getVolumeForSlice(
        self,
        sliceWidget
    ):

        #
        # Explicit volume selector has priority
        #

        try:

            selectedVolume = (
                self.volumeSelector.currentNode()
            )

            if selectedVolume is not None:

                return selectedVolume

        except Exception:

            pass

        #
        # Slice logic
        #

        try:

            sliceLogic = (
                sliceWidget.sliceLogic()
            )

            if sliceLogic is None:

                return None

            #
            # Background
            #

            backgroundLayer = (
                sliceLogic.GetBackgroundLayer()
            )

            if backgroundLayer:

                volumeNode = (
                    backgroundLayer.GetVolumeNode()
                )

                if volumeNode:

                    return volumeNode

            #
            # Foreground
            #

            foregroundLayer = (
                sliceLogic.GetForegroundLayer()
            )

            if foregroundLayer:

                volumeNode = (
                    foregroundLayer.GetVolumeNode()
                )

                if volumeNode:

                    return volumeNode

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "Erro obtendo volume da Slice:",
                e
            )

        return None

    #
    # ========================================================
    # SHOW SEED MARKER
    # ========================================================
    #

    def showSeedMarker(
        self,
        ras
    ):

        try:

            #
            # Remove previous marker
            #

            if self.seedMarkupNode:

                try:

                    slicer.mrmlScene.RemoveNode(
                        self.seedMarkupNode
                    )

                except Exception:

                    pass

                self.seedMarkupNode = None

            #
            # Create markup
            #

            node = (
                slicer.mrmlScene.AddNewNodeByClass(
                    "vtkMRMLMarkupsFiducialNode",
                    "VoxelRegionGrowingSeed"
                )
            )

            node.AddControlPoint(
                float(ras[0]),
                float(ras[1]),
                float(ras[2])
            )

            #
            # Display
            #

            displayNode = (
                node.GetDisplayNode()
            )

            if displayNode:

                try:

                    displayNode.SetPointLabelsVisibility(
                        False
                    )

                except Exception:

                    pass

                try:

                    displayNode.SetSelectedColor(
                        1.0,
                        0.0,
                        0.0
                    )

                except Exception:

                    pass

            self.seedMarkupNode = (
                node
            )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "Erro criando marcador:",
                e
            )

    #
    # ========================================================
    # EXECUTE REGION GROWING
    # ========================================================
    #

    def onGrow(self):

        #
        # Check seed
        #

        if self.seedIJK is None:

            slicer.util.warningDisplay(
                "Selecione primeiro um voxel inicial."
            )

            return

        #
        # Volume
        #

        volumeNode = (
            self.seedVolumeNode
        )

        if volumeNode is None:

            try:

                volumeNode = (
                    self.volumeSelector.currentNode()
                )

            except Exception:

                volumeNode = None

        if volumeNode is None:

            slicer.util.errorDisplay(
                "Nenhum volume selecionado."
            )

            return

        #
        # Segmentation
        #

        segmentationNode = (
            self.getTargetSegmentationNode()
        )

        if segmentationNode is None:

            slicer.util.errorDisplay(
                "Selecione a segmentação de destino."
            )

            return

        #
        # Segment
        #

        segmentID = (
            self.getTargetSegmentID()
        )

        if not segmentID:

            slicer.util.errorDisplay(
                "Selecione o segmento de destino."
            )

            return

        #
        # Parameters
        #

        tolerance = float(
            self.toleranceSpinBox.value
        )

        maxLoops = int(
            self.loopsSpinBox.value
        )

        connectivity = int(
            self.connectivityComboBox.currentData
        )

        adaptive = bool(
            self.adaptiveCheckBox.checked
        )

        maxVoxels = int(
            self.maxVoxelsSpinBox.value
        )

        maskEnabled = False
        maskSegmentationNode = None
        maskSegmentID = None

        try:

            maskEnabled, maskSegmentationNode, maskSegmentID = (
                self.getMaskInfo()
            )

        except Exception:

            maskEnabled = False
            maskSegmentationNode = None
            maskSegmentID = None

        if maskEnabled:

            if maskSegmentationNode is None:

                slicer.util.errorDisplay(
                    "Máscara ativada mas nenhuma segmentação máscara selecionada."
                )

                return

            if not maskSegmentID:

                slicer.util.errorDisplay(
                    "Máscara ativada mas nenhum segmento máscara selecionado."
                )

                return

        #
        # UI
        #

        self.cancelRequested = False

        self.growButton.enabled = False

        if hasattr(self, "cancelGrowButton") and self.cancelGrowButton is not None:

            self.cancelGrowButton.enabled = True

        if hasattr(self, "fillHolesButton"):

            self.fillHolesButton.enabled = False

        self.progressBar.value = 0

        if maskEnabled:

            self.statusLabel.text = (
                "Executando Region Growing (restrito à máscara)..."
            )

        else:

            self.statusLabel.text = (
                "Executando Region Growing..."
            )

        try:

            self.appendLog(
                "Region Growing iniciado. Use 'Cancelar propagação' para interromper."
            )

        except Exception:

            pass

        qt.QApplication.processEvents()

        def _cancelCallback():

            try:

                qt.QApplication.processEvents()

            except Exception:

                pass

            return bool(
                getattr(
                    self,
                    "cancelRequested",
                    False
                )
            )

        try:

            #
            # Run
            #

            labelmap = (
                self.logic.regionGrow(
                    volumeNode=volumeNode,
                    seedIJK=self.seedIJK,
                    tolerance=tolerance,
                    maxLoops=maxLoops,
                    connectivity=connectivity,
                    adaptive=adaptive,
                    maxVoxels=maxVoxels,
                    progressCallback=self.updateProgress,
                    maskSegmentationNode=maskSegmentationNode if maskEnabled else None,
                    maskSegmentID=maskSegmentID if maskEnabled else None,
                    cancelCallback=_cancelCallback
                )
            )

            if self.cancelRequested:

                self.progressBar.value = 0

                self.statusLabel.text = (
                    "Propagação cancelada pelo usuário."
                )

                try:

                    self.appendLog(
                        "Propagação cancelada pelo usuário (nenhum voxel aplicado)."
                    )

                except Exception:

                    pass

                return

            if labelmap is None:

                raise RuntimeError(
                    "Region Growing não produziu resultado."
                )

            self._pushUndoState(
                segmentationNode,
                segmentID
            )

            #
            # Apply
            #

            success = (
                self.logic.applyLabelmapToSegment(
                    labelmap,
                    segmentationNode,
                    segmentID
                )
            )

            if not success:

                raise RuntimeError(
                    "Falha ao aplicar o labelmap "
                    "ao segmento."
                )

            #
            # Update
            #

            self.progressBar.value = 100

            try:

                segObj = segmentationNode.GetSegmentation().GetSegment(segmentID)

                segName = segObj.GetName() if segObj and segObj.GetName() else segmentID

            except Exception:

                segName = segmentID

            self.statusLabel.text = (
                "Region Growing concluído no segmento: {}".format(
                    segName
                )
            )

            self.updateActiveSegmentation()

            #
            # Redraw
            #

            try:

                slicer.app.processEvents()

            except Exception:

                pass

            slicer.util.infoDisplay(
                "Region Growing concluído."
            )

        except Exception as e:

            import traceback

            traceback.print_exc()

            tb = traceback.format_exc()

            msg = "Erro no Region Growing:\n{}\n\n{}".format(
                e,
                tb
            )

            self.lastErrorText = msg

            self.appendLog(
                "ERRO Region Growing: {}\n{}".format(
                    e,
                    tb
                )
            )

            self.statusLabel.text = (
                "Erro: {} (ver Console - Copiar último erro)".format(
                    e
                )
            )

            try:

                self.statusLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse

            except Exception:

                pass

            slicer.util.errorDisplay(
                "Erro no Region Growing (copiável no Console):\n\n{}".format(
                    msg
                )
            )

        finally:

            self.growButton.enabled = True

            self.cancelRequested = False

            if hasattr(self, "cancelGrowButton") and self.cancelGrowButton is not None:

                try:

                    self.cancelGrowButton.enabled = False

                except Exception:

                    pass

            if hasattr(self, "fillHolesButton"):

                try:

                    self.fillHolesButton.enabled = True

                except Exception:

                    pass

    def onCancelGrow(self):

        try:

            self.cancelRequested = True

            self.statusLabel.text = (
                "Cancelando propagação..."
            )

            try:

                self.appendLog(
                    "Cancelamento solicitado pelo usuário..."
                )

            except Exception:

                pass

            try:

                qt.QApplication.processEvents()

            except Exception:

                pass

        except Exception as e:

            print(
                "[VoxelRegionGrowing] onCancelGrow:",
                e
            )

    #
    # ========================================================
    # FILL HOLES (PREENCHER BURACOS INTERNOS)
    # ========================================================
    #

    def onFillHoles(self):

        segmentationNode = (
            self.getTargetSegmentationNode()
        )

        if segmentationNode is None:

            slicer.util.errorDisplay(
                "Selecione a segmentação de destino."
            )

            return

        segmentID = (
            self.getTargetSegmentID()
        )

        if not segmentID:

            slicer.util.errorDisplay(
                "Selecione o segmento de destino."
            )

            return

        self.fillHolesButton.enabled = False

        self.growButton.enabled = False

        self.progressBar.value = 0

        self.statusLabel.text = (
            "Preenchendo buracos internos..."
        )

        qt.QApplication.processEvents()

        self._pushUndoState(
            segmentationNode,
            segmentID
        )

        try:

            filled = (
                self.logic.fillHolesInSegment(
                    segmentationNode,
                    segmentID
                )
            )

            self.progressBar.value = 100

            if filled and filled > 0:

                self.statusLabel.text = (
                    "Buracos preenchidos: {} voxels adicionados.".format(
                        filled
                    )
                )

                slicer.util.infoDisplay(
                    "Buracos internos preenchidos.\n"
                    "Voxels adicionados: {}".format(
                        filled
                    )
                )

            else:

                self.statusLabel.text = (
                    "Nenhum buraco interno encontrado."
                )

                slicer.util.infoDisplay(
                    "Nenhum buraco interno encontrado."
                )

            try:

                slicer.app.processEvents()

            except Exception:

                pass

        except Exception as e:

            import traceback

            traceback.print_exc()

            tb = traceback.format_exc()

            msg = "Erro ao preencher buracos:\n{}\n\n{}".format(
                e,
                tb
            )

            self.lastErrorText = msg

            self.appendLog(
                "ERRO preencher buracos: {}\n{}".format(
                    e,
                    tb
                )
            )

            self.statusLabel.text = (
                "Erro ao preencher buracos: {} (ver Console)".format(
                    e
                )
            )

            slicer.util.errorDisplay(
                "Erro ao preencher buracos (copiável no Console):\n\n{}".format(
                    msg
                )
            )

        finally:

            self.fillHolesButton.enabled = True

            self.growButton.enabled = (
                self.seedIJK is not None
            )

            self.updateActiveSegmentation()

    def onRefineBridges(self):

        segmentationNode = (
            self.getTargetSegmentationNode()
        )

        if segmentationNode is None:

            slicer.util.errorDisplay(
                "Selecione a segmentação de destino."
            )

            return

        segmentID = (
            self.getTargetSegmentID()
        )

        if not segmentID:

            slicer.util.errorDisplay(
                "Selecione o segmento de destino."
            )

            return

        try:

            radius = int(
                self.bridgeRadiusSpinBox.value
            )

        except Exception:

            radius = 1

        try:

            keepLargest = bool(
                self.keepLargestOnlyCheckBox.checked
            )

        except Exception:

            keepLargest = True

        for b in [
            getattr(self, "refineBridgesButton", None),
            getattr(self, "fillHolesButton", None),
            getattr(self, "growButton", None),
            getattr(self, "cancelGrowButton", None)
        ]:

            if b is not None:

                try:

                    b.enabled = False

                except Exception:

                    pass

        self.progressBar.value = 0

        self.statusLabel.text = (
            "Refinando pontes finas (raio={})...".format(
                radius
            )
        )

        qt.QApplication.processEvents()

        self._pushUndoState(
            segmentationNode,
            segmentID
        )

        try:

            removed, kept = self.logic.refineThinBridges(
                segmentationNode,
                segmentID,
                radius=radius,
                keepLargestOnly=keepLargest
            )

            self.progressBar.value = 100

            if removed and removed > 0:

                self.statusLabel.text = (
                    "Refinamento concluído: {} voxels removidos, {} mantidos.".format(
                        removed,
                        kept
                    )
                )

                try:

                    self.appendLog(
                        "Refinamento ponte fina raio={} keepLargest={}: removidos {} mantidos {}".format(
                            radius,
                            keepLargest,
                            removed,
                            kept
                        )
                    )

                except Exception:

                    pass

                slicer.util.infoDisplay(
                    "Refinamento concluído.\n"
                    "Voxels removidos: {}\n"
                    "Voxels mantidos: {}\n"
                    "Raio: {}".format(
                        removed,
                        kept,
                        radius
                    )
                )

            else:

                self.statusLabel.text = (
                    "Refinamento: nenhuma ponte fina encontrada (nada removido)."
                )

                try:

                    self.appendLog(
                        "Refinamento ponte fina raio={}: nenhuma ponte encontrada.".format(
                            radius
                        )
                    )

                except Exception:

                    pass

                slicer.util.infoDisplay(
                    "Nenhuma ponte fina encontrada.\n"
                    "Segmento não foi alterado."
                )

            try:

                slicer.app.processEvents()

            except Exception:

                pass

        except Exception as e:

            import traceback

            traceback.print_exc()

            tb = traceback.format_exc()

            msg = "Erro no refinamento de pontes finas:\n{}\n\n{}".format(
                e,
                tb
            )

            self.lastErrorText = msg

            self.appendLog(
                "ERRO refinamento pontes finas: {}\n{}".format(
                    e,
                    tb
                )
            )

            self.statusLabel.text = (
                "Erro no refinamento: {} (ver Console)".format(
                    e
                )
            )

            slicer.util.errorDisplay(
                "Erro no refinamento de pontes finas (copiável no Console):\n\n{}".format(
                    msg
                )
            )

        finally:

            for b in [
                getattr(self, "refineBridgesButton", None),
                getattr(self, "fillHolesButton", None)
            ]:

                if b is not None:

                    try:

                        b.enabled = True

                    except Exception:

                        pass

            try:

                self.growButton.enabled = (
                    self.seedIJK is not None
                )

            except Exception:

                pass

            if hasattr(self, "cancelGrowButton") and self.cancelGrowButton is not None:

                try:

                    self.cancelGrowButton.enabled = False

                except Exception:

                    pass

            self.updateActiveSegmentation()

    def onAutoRun(self):

        segmentationNode = (
            self.getTargetSegmentationNode()
        )

        if segmentationNode is None:

            slicer.util.errorDisplay(
                "Selecione a segmentação de destino."
            )

            return

        segmentID = (
            self.getTargetSegmentID()
        )

        if not segmentID:

            slicer.util.errorDisplay(
                "Selecione o segmento de destino."
            )

            return

        maskEnabled, maskSegmentationNode, maskSegmentID = self.getMaskInfo()

        if not maskEnabled or maskSegmentationNode is None or not maskSegmentID:

            slicer.util.errorDisplay(
                "Ative a máscara e selecione a segmentação/segmento limite.\n"
                "A automação precisa do limite para buscar o voxel mínimo e propagar dentro dele."
            )

            return

        volumeNode = None

        try:

            volumeNode = self.volumeSelector.currentNode()

        except Exception:

            volumeNode = None

        if volumeNode is None:

            try:

                lm = slicer.app.layoutManager()

                if lm is not None:

                    for n in ["Red", "Yellow", "Green"]:

                        w = lm.sliceWidget(n)

                        if w is None:

                            continue

                        vn = self.getVolumeForSlice(w)

                        if vn is not None:

                            volumeNode = vn

                            break

            except Exception:

                pass

        if volumeNode is None:

            slicer.util.errorDisplay(
                "Selecione um Volume válido (ou deixe um volume visível nas slices)."
            )

            return

        try:

            tolerance = float(
                self.toleranceSpinBox.value
            )

            maxLoops = int(
                self.loopsSpinBox.value
            )

            connectivity = int(
                self.connectivityComboBox.currentData
            )

            adaptive = bool(
                self.adaptiveCheckBox.checked
            )

            maxVoxels = int(
                self.maxVoxelsSpinBox.value
            )

            radius = int(
                self.bridgeRadiusSpinBox.value
            )

            keepLargest = bool(
                self.keepLargestOnlyCheckBox.checked
            )

            doRefine = bool(
                self.autoRefineCheckBox.checked
            )

            doFill = bool(
                self.autoFillHolesCheckBox.checked
            )

        except Exception as e:

            slicer.util.errorDisplay(
                "Erro lendo parâmetros: {}".format(
                    e
                )
            )

            return

        for b in [
            getattr(self, "autoRunButton", None),
            getattr(self, "growButton", None),
            getattr(self, "fillHolesButton", None),
            getattr(self, "refineBridgesButton", None),
            getattr(self, "selectMinVoxelButton", None),
            getattr(self, "selectVoxelButton", None)
        ]:

            if b is not None:

                try:

                    b.enabled = False

                except Exception:

                    pass

        self.cancelRequested = False

        if hasattr(self, "cancelGrowButton") and self.cancelGrowButton is not None:

            try:

                self.cancelGrowButton.enabled = True

            except Exception:

                pass

        self.progressBar.value = 0

        qt.QApplication.processEvents()

        def autoProgress(v):

            try:

                v = int(
                    max(0, min(100, v))
                )

                self.progressBar.value = v

                qt.QApplication.processEvents()

                if getattr(self, "cancelRequested", False):

                    return

            except Exception:

                pass

        try:

            self.statusLabel.text = (
                "Automação 0/3: fechando buracos internos da máscara limite..."
            )

            autoProgress(2)

            qt.QApplication.processEvents()

            if self.cancelRequested:

                raise RuntimeError(
                    "Cancelado pelo usuário."
                )

            try:

                maskFilled = self.logic.fillHolesInSegment(
                    maskSegmentationNode,
                    maskSegmentID
                )

            except Exception as e:

                maskFilled = 0

                print(
                    "[VoxelRegionGrowing] Aviso: falha ao fechar buracos da máscara limite:",
                    e
                )

                try:

                    self.appendLog(
                        "Aviso: falha ao fechar buracos da máscara limite: {}".format(
                            e
                        )
                    )

                except Exception:

                    pass

            if maskFilled and maskFilled > 0:

                try:

                    self.appendLog(
                        "Auto 0/3 máscara limite: buracos fechados +{} voxels".format(
                            maskFilled
                        )
                    )

                except Exception:

                    pass

            else:

                try:

                    self.appendLog(
                        "Auto 0/3 máscara limite: nenhum buraco interno para fechar"
                    )

                except Exception:

                    pass

            autoProgress(5)

            self.statusLabel.text = (
                "Automação 1/3: buscando voxel de menor valor na máscara..."
            )

            autoProgress(6)

            qt.QApplication.processEvents()

            if self.cancelRequested:

                raise RuntimeError(
                    "Cancelado pelo usuário."
                )

            try:

                autoMargin = int(
                    self.interiorMarginSpinBox.value
                )

            except Exception:

                autoMargin = 2

            ijk, value, ras = self.logic.findMinVoxelInMask(
                volumeNode,
                maskSegmentationNode,
                maskSegmentID,
                interiorMargin=autoMargin
            )

            if ijk is None:

                raise RuntimeError(
                    "Nenhum voxel encontrado dentro da máscara."
                )

            self.seedIJK = list(ijk)
            self.seedRAS = list(ras)
            self.seedValue = float(value)
            self.seedVolumeNode = volumeNode
            self.seedSliceName = "Auto (mínimo na máscara margem={})".format(
                autoMargin
            )

            self.selectingVoxel = False

            try:

                self.selectVoxelButton.text = (
                    "Selecionar voxel inicial"
                )

            except Exception:

                pass

            try:

                self.viewLabel.text = self.seedSliceName
                self.ijkLabel.text = "[{}, {}, {}]".format(ijk[0], ijk[1], ijk[2])
                self.rasLabel.text = "[{:.3f}, {:.3f}, {:.3f}]".format(ras[0], ras[1], ras[2])
                self.valueLabel.text = "{:.4f}".format(value)

            except Exception:

                pass

            try:

                self.showSeedMarker(
                    ras
                )

            except Exception:

                pass

            try:

                self.appendLog(
                    "Auto 1/3 seed mínimo na máscara (margem {}): IJK {} val {:.4f} RAS [{:.2f},{:.2f},{:.2f}]".format(
                        autoMargin, ijk, float(value), float(ras[0]), float(ras[1]), float(ras[2])
                    )
                )

            except Exception:

                pass

            autoProgress(10)

            self.statusLabel.text = (
                "Automação 2/3: propagando dentro do limite..."
            )

            qt.QApplication.processEvents()

            if self.cancelRequested:

                raise RuntimeError(
                    "Cancelado pelo usuário."
                )

            def growProgress(v):

                try:

                    mapped = 10 + int(v * 0.70)
                    autoProgress(mapped)

                except Exception:

                    pass

                try:

                    qt.QApplication.processEvents()

                except Exception:

                    pass

            def cancelCb():

                try:

                    qt.QApplication.processEvents()

                except Exception:

                    pass

                return bool(
                    getattr(self, "cancelRequested", False)
                )

            labelmap = self.logic.regionGrow(
                volumeNode=volumeNode,
                seedIJK=self.seedIJK,
                tolerance=tolerance,
                maxLoops=maxLoops,
                connectivity=connectivity,
                adaptive=adaptive,
                maxVoxels=maxVoxels,
                progressCallback=growProgress,
                maskSegmentationNode=maskSegmentationNode,
                maskSegmentID=maskSegmentID,
                cancelCallback=cancelCb
            )

            if self.cancelRequested or labelmap is None:

                self.progressBar.value = 0

                self.statusLabel.text = (
                    "Automação cancelada durante a propagação."
                )

                try:

                    self.appendLog(
                        "Automação cancelada na propagação."
                    )

                except Exception:

                    pass

                return

            self._pushUndoState(
                segmentationNode,
                segmentID
            )

            success = self.logic.applyLabelmapToSegment(
                labelmap,
                segmentationNode,
                segmentID
            )

            if not success:

                raise RuntimeError(
                    "Falha ao aplicar labelmap ao segmento."
                )

            autoProgress(82)

            try:

                self.appendLog(
                    "Auto 2/3 propagação concluída (toler={} loops={} conn={} adapt={}).".format(
                        tolerance, maxLoops, connectivity, adaptive
                    )
                )

            except Exception:

                pass

            removed = 0
            kept = 0
            filled = 0

            if doRefine:

                if self.cancelRequested:

                    raise RuntimeError(
                        "Cancelado pelo usuário."
                    )

                self.statusLabel.text = (
                    "Automação 3/3: refinando pontes finas (raio={})...".format(
                        radius
                    )
                )

                autoProgress(85)

                qt.QApplication.processEvents()

                removed, kept = self.logic.refineThinBridges(
                    segmentationNode,
                    segmentID,
                    radius=radius,
                    keepLargestOnly=keepLargest
                )

                autoProgress(95)

                try:

                    self.appendLog(
                        "Auto 3/3 refinamento raio={} keepLargest={}: removidos {} mantidos {}".format(
                            radius, keepLargest, removed, kept
                        )
                    )

                except Exception:

                    pass

            if doFill:

                if self.cancelRequested:

                    raise RuntimeError(
                        "Cancelado pelo usuário."
                    )

                self.statusLabel.text = (
                    "Automação final: preenchendo buracos..."
                )

                autoProgress(97)

                qt.QApplication.processEvents()

                filled = self.logic.fillHolesInSegment(
                    segmentationNode,
                    segmentID
                )

                try:

                    self.appendLog(
                        "Auto fill holes: adicionados {}".format(
                            filled
                        )
                    )

                except Exception:

                    pass

            autoProgress(100)

            self.updateActiveSegmentation()

            msg = "Automação concluída: seed {} val {:.1f}".format(
                ijk, float(value)
            )

            if doRefine:

                msg += " | refinamento: -{} mantidos {}".format(
                    removed, kept
                )

            if doFill:

                msg += " | buracos: +{}".format(
                    filled
                )

            self.statusLabel.text = msg

            try:

                self.appendLog(
                    msg
                )

            except Exception:

                pass

            slicer.util.infoDisplay(
                "Automação concluída.\n"
                "Seed (mínimo na máscara): {} val {:.2f}\n"
                "Propagação dentro do limite aplicada.\n"
                "{}{}".format(
                    ijk,
                    float(value),
                    "Refinamento: -{} voxels\n".format(removed) if doRefine else "",
                    "Buracos preenchidos: +{} voxels\n".format(filled) if doFill else ""
                )
            )

        except Exception as e:

            import traceback

            traceback.print_exc()

            tb = traceback.format_exc()

            if "Cancelado pelo usuário" in str(e):

                self.statusLabel.text = (
                    "Automação cancelada."
                )

                try:

                    self.appendLog(
                        "Automação cancelada."
                    )

                except Exception:

                    pass

            else:

                msg = "Erro na automação:\n{}\n\n{}".format(
                    e, tb
                )

                self.lastErrorText = msg

                self.appendLog(
                    "ERRO automação: {}\n{}".format(
                        e, tb
                    )
                )

                self.statusLabel.text = (
                    "Erro na automação: {} (ver Console)".format(
                        e
                    )
                )

                try:

                    self.statusLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse

                except Exception:

                    pass

                slicer.util.errorDisplay(
                    "Erro na automação (copiável no Console):\n\n{}".format(
                        msg
                    )
                )

        finally:

            self.cancelRequested = False

            if hasattr(self, "cancelGrowButton") and self.cancelGrowButton is not None:

                try:

                    self.cancelGrowButton.enabled = False

                except Exception:

                    pass

            for b in [
                getattr(self, "autoRunButton", None),
                getattr(self, "refineBridgesButton", None),
                getattr(self, "fillHolesButton", None),
                getattr(self, "selectMinVoxelButton", None),
                getattr(self, "selectVoxelButton", None)
            ]:

                if b is not None:

                    try:

                        b.enabled = True

                    except Exception:

                        pass

            try:

                self.growButton.enabled = (
                    self.seedIJK is not None
                )

            except Exception:

                pass

            self.updateActiveSegmentation()

            try:

                qt.QApplication.processEvents()

            except Exception:

                pass

    #
    # ========================================================
    # PROGRESS
    # ========================================================
    #

    def updateProgress(
        self,
        value
    ):

        try:

            value = int(
                max(
                    0,
                    min(
                        100,
                        value
                    )
                )
            )

            self.progressBar.value = (
                value
            )

            qt.QApplication.processEvents()

        except Exception:

            pass

    #
    # ========================================================
    # LOG / CLIPBOARD
    # ========================================================
    #

    def appendLog(
        self,
        text
    ):

        try:

            if text is None:

                return

            text = str(
                text
            )

            if not text:

                return

            import datetime

            stamp = datetime.datetime.now().strftime(
                "%H:%M:%S"
            )

            line = "[{}] {}".format(
                stamp,
                text
            )

            print(
                line
            )

            if hasattr(self, "logTextEdit") and self.logTextEdit is not None:

                try:

                    self.logTextEdit.appendPlainText(
                        line
                    )

                except Exception:

                    try:

                        self.logTextEdit.plainText = (
                            self.logTextEdit.plainText
                            + "\n"
                            + line
                        )

                    except Exception:

                        pass

        except Exception:

            pass

    def copyTextToClipboard(
        self,
        text
    ):

        try:

            text = str(
                text
            ) if text is not None else ""

            if not text.strip():

                self.statusLabel.text = (
                    "Nada para copiar."
                )

                return False

            copied = False

            try:

                cb = qt.QApplication.clipboard()

                if cb is not None:

                    cb.setText(
                        text
                    )

                    copied = True

            except Exception:

                copied = False

            if not copied:

                try:

                    slicer.app.clipboard().setText(
                        text
                    )

                    copied = True

                except Exception:

                    copied = False

            if copied:

                preview = text[:60].replace("\n", " ")

                self.statusLabel.text = (
                    "Copiado para área de transferência."
                )

                self.appendLog(
                    "Copiado ({} chars): {}...".format(
                        len(text),
                        preview
                    )
                )

                return True

            try:

                dlg = qt.QDialog()

                dlg.windowTitle = "Copiar texto"

                layout = qt.QVBoxLayout(
                    dlg
                )

                edit = qt.QPlainTextEdit()

                edit.readOnly = True
                edit.plainText = text

                layout.addWidget(
                    edit
                )

                btn = qt.QPushButton(
                    "Fechar"
                )

                btn.clicked.connect(
                    dlg.accept
                )

                layout.addWidget(
                    btn
                )

                dlg.exec_()

                return True

            except Exception:

                return False

        except Exception as e:

            print(
                "[VoxelRegionGrowing] Erro copiando:",
                e
            )

            return False

    def onCopyLog(self):

        try:

            text = ""

            if hasattr(self, "logTextEdit") and self.logTextEdit is not None:

                try:

                    text = self.logTextEdit.plainText

                except Exception:

                    text = ""

            if not text or not text.strip():

                text = self.lastErrorText if hasattr(self, "lastErrorText") else ""

            if self.copyTextToClipboard(
                text
            ):

                pass

            else:

                slicer.util.warningDisplay(
                    "Nada para copiar no log."
                )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] onCopyLog:",
                e
            )

    def onCopyLastError(self):

        try:

            text = getattr(
                self,
                "lastErrorText",
                ""
            )

            if not text or not text.strip():

                try:

                    text = self.logTextEdit.plainText

                except Exception:

                    text = ""

                if text:

                    lines = [
                        l for l in text.splitlines()
                        if "ERRO" in l or "Traceback" in l or "Error" in l or "Erro" in l
                    ]

                    if lines:

                        text = "\n".join(
                            lines[-30:]
                        )

            if not text or not text.strip():

                slicer.util.warningDisplay(
                    "Nenhum erro registrado ainda."
                )

                return

            self.copyTextToClipboard(
                text
            )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] onCopyLastError:",
                e
            )

    def onClearLog(self):

        try:

            if hasattr(self, "logTextEdit") and self.logTextEdit is not None:

                self.logTextEdit.clear()

            self.appendLog(
                "Log limpo."
            )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] onClearLog:",
                e
            )

    def _getReferenceVolumeForUndo(self, segmentationNode):

        try:

            ref = segmentationNode.GetNodeReference(
                slicer.vtkMRMLSegmentationNode.GetReferenceImageGeometryReferenceRole()
            )

            if ref is not None:

                return ref

        except Exception:

            pass

        try:

            ref = slicer.mrmlScene.GetFirstNodeByClass(
                "vtkMRMLScalarVolumeNode"
            )

            if ref is None:

                ref = slicer.mrmlScene.GetFirstNodeByClass(
                    "vtkMRMLLabelMapVolumeNode"
                )

            return ref

        except Exception:

            return None

    def _updateUndoButton(self):

        try:

            enabled = bool(
                getattr(self, "undoStack", None)
                and
                len(self.undoStack) > 0
            )

            if hasattr(self, "undoButton") and self.undoButton is not None:

                self.undoButton.enabled = enabled

                if enabled:

                    self.undoButton.toolTip = (
                        "Desfazer última alteração ({} estados salvos).".format(
                            len(self.undoStack)
                        )
                    )

                else:

                    self.undoButton.toolTip = (
                        "Nenhum estado para desfazer."
                    )

        except Exception:

            pass

    def _pushUndoState(self, segmentationNode, segmentID):

        try:

            if segmentationNode is None or not segmentID:

                return False

            ref = self._getReferenceVolumeForUndo(
                segmentationNode
            )

            if ref is None:

                print(
                    "[VoxelRegionGrowing] _pushUndoState sem volume de referência"
                )

                return False

            try:

                arr = slicer.util.arrayFromSegmentBinaryLabelmap(
                    segmentationNode,
                    segmentID,
                    ref
                )

            except Exception as e:

                print(
                    "[VoxelRegionGrowing] _pushUndoState arrayFrom falhou:",
                    e
                )

                return False

            if arr is None:

                arr = np.zeros(
                    (1, 1, 1),
                    dtype=np.uint8
                )

            vis = True
            vis3d = True
            try:
                dn = segmentationNode.GetDisplayNode()
                if dn is not None:
                    try:
                        vis = bool(dn.GetSegmentVisibility(segmentID))
                    except Exception:
                        try:
                            vis = bool(segmentationNode.GetSegmentation().GetSegment(segmentID).GetVisibility())
                        except Exception:
                            vis = True
                    try:
                        vis3d = bool(dn.GetSegmentVisibility3D(segmentID))
                    except Exception:
                        vis3d = vis
            except Exception:
                pass

            if not hasattr(self, "undoStack") or self.undoStack is None:

                self.undoStack = []

            self.undoStack.append(
                {
                    "segmentationNodeID": segmentationNode.GetID(),
                    "segmentID": segmentID,
                    "referenceVolumeID": ref.GetID() if ref else None,
                    "array": np.array(arr, copy=True),
                    "visible": vis,
                    "visible3D": vis3d,
                }
            )

            if len(self.undoStack) > 20:

                self.undoStack.pop(0)

            self._updateUndoButton()

            try:

                self.appendLog(
                    "Estado salvo para desfazer ({} voxels no segmento).".format(
                        int(np.count_nonzero(arr))
                    )
                )

            except Exception:

                pass

            return True

        except Exception as e:

            print(
                "[VoxelRegionGrowing] _pushUndoState:",
                e
            )

            return False

    def onUndo(self):

        try:

            if not hasattr(self, "undoStack") or not self.undoStack:

                slicer.util.warningDisplay(
                    "Nenhum estado para desfazer."
                )

                return

            state = self.undoStack.pop()

            self._updateUndoButton()

            segNode = None

            refNode = None

            try:

                segNode = slicer.mrmlScene.GetNodeByID(
                    state["segmentationNodeID"]
                )

            except Exception:

                segNode = None

            try:

                if state.get("referenceVolumeID"):

                    refNode = slicer.mrmlScene.GetNodeByID(
                        state["referenceVolumeID"]
                    )

            except Exception:

                refNode = None

            if segNode is None:

                slicer.util.errorDisplay(
                    "Segmentação do estado salvo não encontrada."
                )

                return

            if refNode is None:

                refNode = self._getReferenceVolumeForUndo(
                    segNode
                )

            if refNode is None:

                slicer.util.errorDisplay(
                    "Volume de referência não encontrado para desfazer."
                )

                return

            arr = state["array"]

            try:

                slicer.util.updateSegmentBinaryLabelmapFromArray(
                    arr,
                    segNode,
                    state["segmentID"],
                    refNode
                )

            except Exception as e:

                raise RuntimeError(
                    "Falha ao restaurar: {}".format(e)
                )

            try:

                dn = segNode.GetDisplayNode()

                if dn is not None:

                    vis = state.get("visible", True)

                    vis3d = state.get("visible3D", vis)

                    try:

                        dn.SetSegmentVisibility(state["segmentID"], bool(vis))

                    except Exception:

                        pass

                    try:

                        dn.SetSegmentVisibility3D(state["segmentID"], bool(vis3d))

                    except Exception:

                        pass

                    try:

                        if not bool(vis3d):

                            dn.SetSegmentVisibility3D(state["segmentID"], True)

                    except Exception:

                        pass

            except Exception:

                pass

            try:

                segNode.Modified()

            except Exception:

                pass

            try:

                segNode.GetDisplayNode().Modified()

            except Exception:

                pass

            try:

                slicer.app.processEvents()

            except Exception:

                pass

            self.statusLabel.text = (
                "Desfeito: segmento restaurado ({} voxels).".format(
                    int(np.count_nonzero(arr))
                )
            )

            self.appendLog(
                "Desfazer aplicado: segmento {} restaurado (3D preservado).".format(
                    state["segmentID"]
                )
            )

            self.updateActiveSegmentation()

        except Exception as e:

            import traceback

            traceback.print_exc()

            tb = traceback.format_exc()

            msg = "Erro ao desfazer:\n{}\n\n{}".format(e, tb)

            self.lastErrorText = msg

            try:

                self.appendLog(
                    "ERRO desfazer: {}\n{}".format(e, tb)
                )

            except Exception:

                pass

            slicer.util.errorDisplay(
                "Erro ao desfazer (ver Console):\n\n{}".format(msg)
            )

        finally:

            self._updateUndoButton()

    def onTolerancePlus(self):

        try:

            cur = float(
                self.toleranceSpinBox.value
            )

            nxt = cur + 100.0

            mx = float(
                self.toleranceSpinBox.maximum
            )

            if nxt > mx:

                nxt = mx

            self.toleranceSpinBox.value = nxt

            try:

                self.appendLog(
                    "Tolerância +100 => {:.3f}".format(float(nxt))
                )

            except Exception:

                pass

            self.statusLabel.text = (
                "Tolerância: {:.3f}".format(float(nxt))
            )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] onTolerancePlus:",
                e
            )

    #
    # ========================================================
    # CLEANUP
    # ========================================================
    #

    def cleanup(self):

        #
        # Disable selection
        #

        self.selectingVoxel = False

        #
        # Stop timer
        #

        if self.refreshTimer:

            try:

                self.refreshTimer.stop()

            except Exception:

                pass

            self.refreshTimer = None

        #
        # Remove slice observers
        #

        for data in list(
            self.sliceObservers.values()
        ):

            try:

                data["interactor"].RemoveObserver(
                    data["tag"]
                )

            except Exception:

                pass

        self.sliceObservers.clear()

        #
        # Remove seed marker
        #

        if self.seedMarkupNode:

            try:

                slicer.mrmlScene.RemoveNode(
                    self.seedMarkupNode
                )

            except Exception:

                pass

            self.seedMarkupNode = None

        #
        # Disconnect layout
        #

        if self.layoutManager:

            try:

                self.layoutManager.disconnect(
                    "layoutChanged(int)",
                    self.onLayoutChanged
                )

            except Exception:

                pass

        #
        # Parent cleanup
        #

        ScriptedLoadableModuleWidget.cleanup(
            self
        )


#
# ============================================================
# LOGIC
# ============================================================
#

class VoxelRegionGrowingLogic(
    ScriptedLoadableModuleLogic
):

    #
    # ========================================================
    # IJK INSIDE EXTENT
    # ========================================================
    #

    def isIJKInsideExtent(
        self,
        ijk,
        extent
    ):

        return (
            extent[0] <= ijk[0] <= extent[1]
            and
            extent[2] <= ijk[1] <= extent[3]
            and
            extent[4] <= ijk[2] <= extent[5]
        )

    #
    # ========================================================
    # GET VOXEL VALUE
    # ========================================================
    #

    def getVoxelValue(
        self,
        volumeNode,
        ijk
    ):

        if volumeNode is None:

            raise ValueError(
                "Volume inválido."
            )

        imageData = (
            volumeNode.GetImageData()
        )

        if imageData is None:

            raise RuntimeError(
                "Volume sem ImageData."
            )

        return float(
            imageData.GetScalarComponentAsDouble(
                int(ijk[0]),
                int(ijk[1]),
                int(ijk[2]),
                0
            )
        )

    #
    # ========================================================
    # GET NEIGHBOR OFFSETS
    # ========================================================
    #

    def getNeighborOffsets(
        self,
        connectivity
    ):

        connectivity = int(
            connectivity
        )

        if connectivity not in (
            6,
            18,
            26
        ):

            raise ValueError(
                "Conectividade deve ser 6, 18 ou 26."
            )

        offsets = []

        for dz in (-1, 0, 1):

            for dy in (-1, 0, 1):

                for dx in (-1, 0, 1):

                    #
                    # Skip center
                    #

                    if (
                        dx == 0
                        and
                        dy == 0
                        and
                        dz == 0
                    ):

                        continue

                    distance = (
                        abs(dx)
                        +
                        abs(dy)
                        +
                        abs(dz)
                    )

                    #
                    # 6-connected
                    #

                    if connectivity == 6:

                        if distance == 1:

                            offsets.append(
                                (
                                    dx,
                                    dy,
                                    dz
                                )
                            )

                    #
                    # 18-connected
                    #

                    elif connectivity == 18:

                        if distance <= 2:

                            offsets.append(
                                (
                                    dx,
                                    dy,
                                    dz
                                )
                            )

                    #
                    # 26-connected
                    #

                    else:

                        offsets.append(
                            (
                                dx,
                                dy,
                                dz
                            )
                        )

        return offsets

    #
    # ========================================================
    # REGION GROW
    # ========================================================
    #

    def _getMaskArray(
        self,
        volumeNode,
        maskSegmentationNode,
        maskSegmentID
    ):

        if maskSegmentationNode is None:

            return None

        if not maskSegmentID:

            return None

        if volumeNode is None:

            return None

        segmentation = (
            maskSegmentationNode.GetSegmentation()
        )

        if segmentation is None:

            return None

        if segmentation.GetSegment(
            maskSegmentID
        ) is None:

            return None

        try:

            arr = slicer.util.arrayFromSegmentBinaryLabelmap(
                maskSegmentationNode,
                maskSegmentID,
                volumeNode
            )

            if arr is not None:

                return arr

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "arrayFromSegmentBinaryLabelmap falhou:",
                e
            )

        tempName = (
            "__VoxelRegionGrowing_MaskTemp__"
        )

        labelmapNode = None

        try:

            labelmapNode = (
                slicer.mrmlScene.AddNewNodeByClass(
                    "vtkMRMLLabelMapVolumeNode",
                    tempName
                )
            )

            slicer.vtkSlicerSegmentationsModuleLogic.ExportSegmentsToLabelmapNode(
                maskSegmentationNode,
                [maskSegmentID],
                labelmapNode,
                volumeNode
            )

            arr = (
                slicer.util.arrayFromVolume(
                    labelmapNode
                )
            )

            if arr is not None:

                return np.array(
                    arr,
                    copy=True
                )

            return None

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "ExportSegmentsToLabelmapNode falhou:",
                e
            )

            return None

        finally:

            if labelmapNode is not None:

                try:

                    slicer.mrmlScene.RemoveNode(
                        labelmapNode
                    )

                except Exception:

                    pass

    def findMinVoxelInMask(
        self,
        volumeNode,
        maskSegmentationNode,
        maskSegmentID,
        interiorMargin=2
    ):

        if volumeNode is None:

            raise ValueError(
                "Volume inválido."
            )

        if maskSegmentationNode is None or not maskSegmentID:

            raise ValueError(
                "Máscara inválida."
            )

        imageData = volumeNode.GetImageData()

        if imageData is None:

            raise RuntimeError(
                "Volume sem ImageData."
            )

        extent = imageData.GetExtent()

        minI = int(extent[0])
        minJ = int(extent[2])
        minK = int(extent[4])

        try:

            volArray = slicer.util.arrayFromVolume(
                volumeNode
            )

        except Exception as e:

            raise RuntimeError(
                "Falha ao obter array do volume: {}".format(
                    e
                )
            )

        if volArray is None:

            raise RuntimeError(
                "Array do volume é nulo."
            )

        maskArray = self._getMaskArray(
            volumeNode,
            maskSegmentationNode,
            maskSegmentID
        )

        if maskArray is None:

            raise RuntimeError(
                "Falha ao obter array da máscara."
            )

        if volArray.shape != maskArray.shape:

            raise RuntimeError(
                "Geometria diferente entre volume {} e máscara {} .".format(
                    volArray.shape,
                    maskArray.shape
                )
            )

        finiteMask = np.isfinite(
            volArray
        )

        baseValid = np.logical_and(
            maskArray != 0,
            finiteMask
        )

        countBase = int(
            np.count_nonzero(
                baseValid
            )
        )

        if countBase == 0:

            hasMask = int(
                np.count_nonzero(
                    maskArray != 0
                )
            )

            if hasMask == 0:

                raise RuntimeError(
                    "Máscara vazia (nenhum voxel)."
                )

            baseValid = maskArray != 0

            countBase = int(
                np.count_nonzero(
                    baseValid
                )
            )

            if countBase == 0:

                raise RuntimeError(
                    "Nenhum voxel válido dentro da máscara."
                )

        interiorMargin = int(
            interiorMargin
        ) if interiorMargin is not None else 0

        if interiorMargin < 0:

            interiorMargin = 0

        if interiorMargin > 10:

            interiorMargin = 10

        if interiorMargin > 0:

            eroded = None

            try:

                from scipy.ndimage import binary_erosion as scipy_erode

                maskBool = maskArray != 0

                eroded = scipy_erode(
                    maskBool,
                    iterations=interiorMargin
                )

            except Exception as e:

                print(
                    "[VoxelRegionGrowing] scipy binary_erosion falhou, tentando fallback manual:",
                    e
                )

                try:

                    maskBool = maskArray != 0

                    eroded = maskBool.copy()

                    for _ in range(interiorMargin):

                        nxt = np.zeros_like(
                            eroded,
                            dtype=bool
                        )

                        nxt[1:, :, :] |= eroded[1:, :, :] & eroded[:-1, :, :]
                        nxt[:-1, :, :] |= eroded[:-1, :, :] & eroded[1:, :, :]
                        nxt[:, 1:, :] |= eroded[:, 1:, :] & eroded[:, :-1, :]
                        nxt[:, :-1, :] |= eroded[:, :-1, :] & eroded[:, 1:, :]
                        nxt[:, :, 1:] |= eroded[:, :, 1:] & eroded[:, :, :-1]
                        nxt[:, :, :-1] |= eroded[:, :, :-1] & eroded[:, :, 1:]

                        eroded = np.logical_and(
                            eroded,
                            nxt
                        )

                        if not np.any(eroded):

                            break

                except Exception as e2:

                    print(
                        "[VoxelRegionGrowing] Fallback erosão interior falhou:",
                        e2
                    )

                    eroded = None

            if eroded is not None:

                interiorValid = np.logical_and(
                    eroded,
                    finiteMask
                )

                if int(np.count_nonzero(interiorValid)) > 0:

                    valid = interiorValid

                    print(
                        "[VoxelRegionGrowing] Margem interior {} aplicada: {} -> {} voxels candidatos.".format(
                            interiorMargin,
                            countBase,
                            int(np.count_nonzero(valid))
                        )
                    )

                else:

                    print(
                        "[VoxelRegionGrowing] Margem interior {} esvaziou a máscara (objeto fino), usando máscara completa.".format(
                            interiorMargin
                        )
                    )

                    valid = baseValid

            else:

                valid = baseValid

        else:

            valid = baseValid

        count = int(
            np.count_nonzero(
                valid
            )
        )

        if count == 0:

            valid = baseValid

            count = int(
                np.count_nonzero(valid)
            )

        maskedVals = volArray[valid]

        minVal = float(
            np.min(
                maskedVals
            )
        )

        coords = np.argwhere(
            valid
        )

        valsAtCoords = volArray[
            coords[:, 0],
            coords[:, 1],
            coords[:, 2]
        ]

        minIdx = int(
            np.argmin(
                valsAtCoords
            )
        )

        k0, j0, i0 = [int(x) for x in coords[minIdx]]

        ijk = [
            int(i0 + minI),
            int(j0 + minJ),
            int(k0 + minK)
        ]

        if len(ijk) != 3:

            raise RuntimeError(
                "Falha ao converter índice do mínimo."
            )

        value = float(
            volArray[k0, j0, i0]
        )

        ijkToRAS = vtk.vtkMatrix4x4()

        volumeNode.GetIJKToRASMatrix(
            ijkToRAS
        )

        ras4 = ijkToRAS.MultiplyPoint(
            [
                float(ijk[0]),
                float(ijk[1]),
                float(ijk[2]),
                1.0
            ]
        )

        ras = [
            float(ras4[0]),
            float(ras4[1]),
            float(ras4[2])
        ]

        print(
            "[VoxelRegionGrowing] Mínimo na máscara: IJK {} val {} RAS {} count {}".format(
                ijk,
                value,
                ras,
                count
            )
        )

        return ijk, value, ras

    def regionGrow(
        self,
        volumeNode,
        seedIJK,
        tolerance,
        maxLoops,
        connectivity,
        adaptive=False,
        maxVoxels=5000000,
        progressCallback=None,
        maskSegmentationNode=None,
        maskSegmentID=None,
        cancelCallback=None
    ):

        #
        # Validate volume
        #

        if volumeNode is None:

            raise ValueError(
                "Volume não informado."
            )

        #
        # Validate seed
        #

        if seedIJK is None:

            raise ValueError(
                "Seed não informado."
            )

        #
        # Validate parameters
        #

        tolerance = float(
            tolerance
        )

        maxLoops = int(
            maxLoops
        )

        connectivity = int(
            connectivity
        )

        maxVoxels = int(
            maxVoxels
        )

        if tolerance < 0:

            raise ValueError(
                "Tolerância não pode ser negativa."
            )

        if maxLoops < 0:

            raise ValueError(
                "Loops não pode ser negativo."
            )

        if maxVoxels <= 0:

            raise ValueError(
                "Máximo de voxels deve ser maior que zero."
            )

        #
        # Image data
        #

        imageData = (
            volumeNode.GetImageData()
        )

        if imageData is None:

            raise RuntimeError(
                "Volume sem ImageData."
            )

        #
        # Extent
        #

        extent = (
            imageData.GetExtent()
        )

        minI = int(
            extent[0]
        )

        maxI = int(
            extent[1]
        )

        minJ = int(
            extent[2]
        )

        maxJ = int(
            extent[3]
        )

        minK = int(
            extent[4]
        )

        maxK = int(
            extent[5]
        )

        #
        # Seed coordinates
        #

        si = int(
            seedIJK[0]
        )

        sj = int(
            seedIJK[1]
        )

        sk = int(
            seedIJK[2]
        )

        seed = (
            si,
            sj,
            sk
        )

        #
        # Validate seed
        #

        if not self.isIJKInsideExtent(
            [si, sj, sk],
            extent
        ):

            raise ValueError(
                "Seed fora do volume.\n"
                "Seed: {}\n"
                "Extent: {}".format(
                    seed,
                    extent
                )
            )

        #
        # ----------------------------------------------------
        # Try NumPy access
        # ----------------------------------------------------
        #

        array = None

        try:

            array = (
                slicer.util.arrayFromVolume(
                    volumeNode
                )
            )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] "
                "arrayFromVolume falhou:",
                e
            )

            array = None

        #
        # ====================================================
        # Helper to get value
        # ====================================================
        #

        def voxelValue(
            i,
            j,
            k
        ):

            if array is not None:

                return float(
                    array[
                        k - minK,
                        j - minJ,
                        i - minI
                    ]
                )

            return self.getVoxelValue(
                volumeNode,
                [
                    i,
                    j,
                    k
                ]
            )

        #
        # Seed value
        #

        seedValue = voxelValue(
            si,
            sj,
            sk
        )

        #
        # Mask array (limitar propagação)
        #

        maskArray = None

        maskEnabled = False

        if (
            maskSegmentationNode is not None
            and
            maskSegmentID
        ):

            maskArray = self._getMaskArray(
                volumeNode,
                maskSegmentationNode,
                maskSegmentID
            )

            if maskArray is None:

                raise RuntimeError(
                    "Não foi possível obter a máscara. "
                    "Verifique a segmentação/segmento máscara."
                )

            if (
                array is not None
                and
                maskArray.shape != array.shape
            ):

                raise RuntimeError(
                    "Máscara com geometria diferente do volume.\n"
                    "Volume: {}\n"
                    "Máscara: {}".format(
                        array.shape,
                        maskArray.shape
                    )
                )

            maskEnabled = True

            if maskArray[
                sk - minK,
                sj - minJ,
                si - minI
            ] == 0:

                raise ValueError(
                    "Voxel inicial fora da máscara selecionada. "
                    "Escolha um voxel dentro do segmento máscara."
                )

        def isInsideMask(
            i,
            j,
            k
        ):

            if not maskEnabled:

                return True

            if maskArray is None:

                return False

            return bool(
                maskArray[
                    k - minK,
                    j - minJ,
                    i - minI
                ] != 0
            )

        #
        # Queue
        #

        queue = deque()

        queue.append(
            seed
        )

        #
        # Visited
        #

        visited = set()

        visited.add(
            seed
        )

        #
        # Accepted
        #

        accepted = [
            seed
        ]

        #
        # Neighbor offsets
        #

        offsets = (
            self.getNeighborOffsets(
                connectivity
            )
        )

        #
        # Reference
        #

        referenceValue = (
            seedValue
        )

        #
        # ====================================================
        # Zero loops
        # ====================================================
        #

        if maxLoops <= 0:

            if progressCallback:

                progressCallback(
                    100
                )

            return self.createLabelmap(
                volumeNode,
                accepted
            )

        #
        # ====================================================
        # BFS layers
        # ====================================================
        #

        currentLayer = 0

        stoppedByMaxVoxels = False

        stoppedByNoGrowth = False

        cancelled = False

        while queue:

            if cancelCallback is not None:

                try:

                    if cancelCallback():

                        cancelled = True

                        break

                except Exception:

                    pass

            #
            # Stop if maximum reached
            #

            if (
                len(accepted)
                >= maxVoxels
            ):

                stoppedByMaxVoxels = True

                break

            #
            # Number of voxels in this layer
            #

            layerSize = len(
                queue
            )

            acceptedThisLayer = 0

            #
            # Process current layer
            #

            for _ in range(
                layerSize
            ):

                if cancelCallback is not None:

                    try:

                        if cancelCallback():

                            cancelled = True

                            break

                    except Exception:

                        pass

                if (
                    len(accepted)
                    >= maxVoxels
                ):

                    stoppedByMaxVoxels = True

                    break

                #
                # Current voxel
                #

                current = (
                    queue.popleft()
                )

                ci = int(
                    current[0]
                )

                cj = int(
                    current[1]
                )

                ck = int(
                    current[2]
                )

                if adaptive:

                    currentValue = voxelValue(
                        ci,
                        cj,
                        ck
                    )

                #
                # Neighbors
                #

                for dx, dy, dz in offsets:

                    #
                    # New coordinate
                    #

                    ni = ci + dx
                    nj = cj + dy
                    nk = ck + dz

                    #
                    # Bounds
                    #

                    if (
                        ni < minI
                        or
                        ni > maxI
                    ):

                        continue

                    if (
                        nj < minJ
                        or
                        nj > maxJ
                    ):

                        continue

                    if (
                        nk < minK
                        or
                        nk > maxK
                    ):

                        continue

                    #
                    # Neighbor tuple
                    #

                    neighbor = (
                        ni,
                        nj,
                        nk
                    )

                    #
                    # Already visited
                    #

                    if neighbor in visited:

                        continue

                    #
                    # Mark visited
                    #

                    visited.add(
                        neighbor
                    )

                    #
                    # Máscara: só propaga dentro do segmento máscara
                    #

                    if maskEnabled:

                        if not isInsideMask(
                            ni,
                            nj,
                            nk
                        ):

                            continue

                    #
                    # Intensity
                    #

                    value = voxelValue(
                        ni,
                        nj,
                        nk
                    )

                    #
                    # Similarity
                    #

                    if adaptive:

                        difference = abs(
                            value
                            -
                            currentValue
                        )

                    else:

                        difference = abs(
                            value
                            -
                            referenceValue
                        )

                    if (
                        difference
                        <=
                        tolerance
                    ):

                        #
                        # Accept
                        #

                        accepted.append(
                            neighbor
                        )

                        queue.append(
                            neighbor
                        )

                        acceptedThisLayer += 1

                        #
                        # Maximum voxels
                        #

                        if (
                            len(accepted)
                            >= maxVoxels
                        ):

                            stoppedByMaxVoxels = True

                            break

                #
                # Stop current layer
                #

                if stoppedByMaxVoxels:

                    break

            #
            # Layer completed
            #

            currentLayer += 1

            #
            # Progress
            #

            if progressCallback:

                progress = int(
                    min(
                        99,
                        (
                            currentLayer
                            /
                            float(
                                maxLoops
                            )
                        )
                        *
                        100.0
                    )
                )

                progressCallback(
                    progress
                )

            #
            # Maximum reached
            #

            if stoppedByMaxVoxels:

                break

            #
            # Maximum number of layers
            #

            if (
                currentLayer
                >=
                maxLoops
            ):

                break

            #
            # No new voxels
            #

            if acceptedThisLayer == 0:

                stoppedByNoGrowth = True

                break

            if cancelled:

                break

        #
        # Final progress
        #

        if progressCallback and not cancelled:

            progressCallback(
                100
            )

        #
        # Console information
        #

        print(
            "========================================"
        )

        print(
            "[VoxelRegionGrowing] Region Growing"
        )

        print(
            "Seed:",
            seed
        )

        print(
            "Seed value:",
            seedValue
        )

        print(
            "Tolerance:",
            tolerance
        )

        print(
            "Loops requested:",
            maxLoops
        )

        print(
            "Loops executed:",
            currentLayer
        )

        print(
            "Connectivity:",
            connectivity
        )

        print(
            "Adaptive:",
            adaptive
        )

        print(
            "Reference final:",
            referenceValue
        )

        print(
            "Accepted voxels:",
            len(accepted)
        )

        print(
            "Max voxels reached:",
            stoppedByMaxVoxels
        )

        print(
            "No growth:",
            stoppedByNoGrowth
        )

        print(
            "Cancelado:",
            cancelled
        )

        print(
            "========================================"
        )

        if cancelled:

            return None

        #
        # Create labelmap
        #

        return self.createLabelmap(
            volumeNode,
            accepted
        )

    #
    # ========================================================
    # CREATE LABELMAP
    # ========================================================
    #

    def createLabelmap(
        self,
        volumeNode,
        voxels
    ):

        if volumeNode is None:

            raise ValueError(
                "Volume inválido."
            )

        imageData = (
            volumeNode.GetImageData()
        )

        if imageData is None:

            raise RuntimeError(
                "Volume sem ImageData."
            )

        #
        # Original volume extent
        #

        extent = (
            imageData.GetExtent()
        )

        #
        # ====================================================
        # IMPORTANT
        #
        # Correct Slicer class:
        #
        # slicer.vtkOrientedImageData()
        #
        # NOT:
        #
        # vtk.vtkOrientedImageData()
        #
        # NOT:
        #
        # vtk.vtkOnentedImageData()
        # ====================================================
        #

        output = (
            slicer.vtkOrientedImageData()
        )

        #
        # Extent
        #

        output.SetExtent(
            extent
        )

        #
        # Allocate binary scalars
        #

        output.AllocateScalars(
            vtk.VTK_UNSIGNED_CHAR,
            1
        )

        #
        # Clear output
        #

        scalars = (
            output.GetPointData().GetScalars()
        )

        if scalars is None:

            raise RuntimeError(
                "Não foi possível criar os scalars "
                "do labelmap."
            )

        scalars.Fill(
            0
        )

        #
        # ====================================================
        # Geometry
        # ====================================================
        #

        ijkToRAS = (
            vtk.vtkMatrix4x4()
        )

        volumeNode.GetIJKToRASMatrix(
            ijkToRAS
        )

        #
        # Correct API for vtkOrientedImageData
        #

        output.SetGeometryFromImageToWorldMatrix(
            ijkToRAS
        )

        #
        # ====================================================
        # Fill accepted voxels
        # ====================================================
        #

        for voxel in voxels:

            i = int(
                voxel[0]
            )

            j = int(
                voxel[1]
            )

            k = int(
                voxel[2]
            )

            #
            # Bounds
            #

            if (
                i < extent[0]
                or
                i > extent[1]
            ):

                continue

            if (
                j < extent[2]
                or
                j > extent[3]
            ):

                continue

            if (
                k < extent[4]
                or
                k > extent[5]
            ):

                continue

            #
            # Set voxel
            #

            output.SetScalarComponentFromDouble(
                i,
                j,
                k,
                0,
                1
            )

        #
        # Modified
        #

        output.Modified()

        return output

    #
    # ========================================================
    # APPLY LABELMAP TO SEGMENT
    # ========================================================
    #

    def applyLabelmapToSegment(
        self,
        labelmap,
        segmentationNode,
        segmentID
    ):

        #
        # Validate labelmap
        #

        if labelmap is None:

            raise ValueError(
                "Labelmap inválido."
            )

        #
        # Validate segmentation
        #

        if segmentationNode is None:

            raise ValueError(
                "Segmentação inválida."
            )

        #
        # Validate segment
        #

        if not segmentID:

            raise ValueError(
                "SegmentID inválido."
            )

        #
        # Check segment exists
        #

        segment = (
            segmentationNode
            .GetSegmentation()
            .GetSegment(
                segmentID
            )
        )

        if segment is None:

            raise ValueError(
                "Segmento não encontrado: {}".format(
                    segmentID
                )
            )

        #
        # ====================================================
        # Apply
        # ====================================================
        #

        success = (
            slicer.vtkSlicerSegmentationsModuleLogic
            .SetBinaryLabelmapToSegment(
                labelmap,
                segmentationNode,
                segmentID,
                slicer.vtkSlicerSegmentationsModuleLogic.MODE_MERGE_MAX
            )
        )

        if not success:

            raise RuntimeError(
                "SetBinaryLabelmapToSegment retornou False."
            )

        #
        # Modified
        #

        segmentationNode.Modified()

        #
        # Request display update
        #

        try:

            segmentationNode.GetDisplayNode().Modified()

        except Exception:

            pass

        #
        # Return
        #

        return True

    #
    # ========================================================
    # FILL HOLES IN SEGMENT
    # ========================================================
    #

    def refineThinBridges(
        self,
        segmentationNode,
        segmentID,
        radius=1,
        keepLargestOnly=True
    ):

        if segmentationNode is None:

            raise ValueError(
                "Segmentação inválida."
            )

        if not segmentID:

            raise ValueError(
                "SegmentID inválido."
            )

        segmentation = (
            segmentationNode.GetSegmentation()
        )

        if segmentation is None:

            raise RuntimeError(
                "Segmentation inválida."
            )

        segment = (
            segmentation.GetSegment(
                segmentID
            )
        )

        if segment is None:

            raise ValueError(
                "Segmento não encontrado: {}".format(
                    segmentID
                )
            )

        radius = int(
            radius
        )

        if radius < 1:

            radius = 1

        if radius > 5:

            radius = 5

        referenceVolumeNode = None

        try:

            referenceVolumeNode = (
                segmentationNode.GetNodeReference(
                    slicer.vtkMRMLSegmentationNode.GetReferenceImageGeometryReferenceRole()
                )
            )

        except Exception:

            referenceVolumeNode = None

        if referenceVolumeNode is None:

            try:

                referenceVolumeNode = (
                    slicer.mrmlScene.GetFirstNodeByClass(
                        "vtkMRMLScalarVolumeNode"
                    )
                )

                if referenceVolumeNode is None:

                    referenceVolumeNode = (
                        slicer.mrmlScene.GetFirstNodeByClass(
                            "vtkMRMLLabelMapVolumeNode"
                        )
                    )

            except Exception:

                referenceVolumeNode = None

        if referenceVolumeNode is None:

            raise RuntimeError(
                "Não foi possível determinar o volume de referência da segmentação."
            )

        try:

            arr = slicer.util.arrayFromSegmentBinaryLabelmap(
                segmentationNode,
                segmentID,
                referenceVolumeNode
            )

        except Exception as e:

            raise RuntimeError(
                "Falha ao obter array do segmento: {}".format(
                    e
                )
            )

        if arr is None:

            raise RuntimeError(
                "Array do segmento é nulo."
            )

        arr = np.array(
            arr,
            copy=True
        )

        if arr.ndim != 3:

            raise RuntimeError(
                "Array do segmento deve ser 3D, recebido shape {}".format(
                    arr.shape
                )
            )

        binary = arr.astype(bool)

        totalBefore = int(
            np.count_nonzero(
                binary
            )
        )

        if totalBefore == 0:

            return 0, 0

        try:

            from scipy import ndimage as ndi

            has_scipy = True

        except Exception:

            has_scipy = False

        if has_scipy:

            try:

                struct_erode = ndi.generate_binary_structure(
                    3,
                    1
                )

                eroded = ndi.binary_erosion(
                    binary,
                    structure=struct_erode,
                    iterations=radius
                )

                if not np.any(eroded):

                    print(
                        "[VoxelRegionGrowing] Erosão removeu tudo (raio muito grande para o objeto), nada a refinar."
                    )

                    return 0, totalBefore

                struct_label = ndi.generate_binary_structure(
                    3,
                    3
                )

                labeled, num = ndi.label(
                    eroded,
                    structure=struct_label
                )

                if num == 0:

                    return 0, totalBefore

                if keepLargestOnly:

                    sizes = ndi.sum(
                        eroded,
                        labeled,
                        range(1, num + 1)
                    )

                    largest = int(
                        np.argmax(sizes) + 1
                    )

                    seed = labeled == largest

                else:

                    seed = eroded

                struct_dilate = ndi.generate_binary_structure(
                    3,
                    1
                )

                recon = seed.copy()

                prev = np.zeros_like(
                    recon,
                    dtype=bool
                )

                iterCount = 0

                while not np.array_equal(recon, prev):

                    prev = recon.copy()

                    recon = np.logical_and(
                        ndi.binary_dilation(
                            recon,
                            structure=struct_dilate
                        ),
                        binary
                    )

                    iterCount += 1

                    if iterCount > 2000:

                        print(
                            "[VoxelRegionGrowing] Reconstrução atingiu limite de iterações."
                        )

                        break

                newBinary = recon

            except Exception as e:

                print(
                    "[VoxelRegionGrowing] refine scipy falhou, fallback manual:",
                    e
                )

                has_scipy = False

        if not has_scipy:

            nz, ny, nx = binary.shape

            eroded = binary.copy()

            for _ in range(radius):

                nxt = np.zeros_like(
                    eroded,
                    dtype=bool
                )

                nxt[1:, :, :] |= eroded[1:, :, :] & eroded[:-1, :, :]
                nxt[:-1, :, :] |= eroded[:-1, :, :] & eroded[1:, :, :]
                nxt[:, 1:, :] |= eroded[:, 1:, :] & eroded[:, :-1, :]
                nxt[:, :-1, :] |= eroded[:, :-1, :] & eroded[:, 1:, :]
                nxt[:, :, 1:] |= eroded[:, :, 1:] & eroded[:, :, :-1]
                nxt[:, :, :-1] |= eroded[:, :, :-1] & eroded[:, :, 1:]

                eroded = np.logical_and(
                    eroded,
                    nxt
                )

                if not np.any(eroded):

                    break

            if not np.any(eroded):

                return 0, totalBefore

            visited = np.zeros_like(
                eroded,
                dtype=np.int32
            )

            label = 0
            sizes = {}

            offsets6 = [
                (1, 0, 0),
                (-1, 0, 0),
                (0, 1, 0),
                (0, -1, 0),
                (0, 0, 1),
                (0, 0, -1)
            ]

            for z in range(nz):
                for y in range(ny):
                    for x in range(nx):

                        if not eroded[z, y, x]:

                            continue

                        if visited[z, y, x] != 0:

                            continue

                        label += 1

                        q = deque()
                        q.append((z, y, x))
                        visited[z, y, x] = label
                        cnt = 0

                        while q:

                            cz, cy, cx = q.popleft()
                            cnt += 1

                            for dz, dy, dx in offsets6:

                                nz2 = cz + dz
                                ny2 = cy + dy
                                nx2 = cx + dx

                                if nz2 < 0 or nz2 >= nz:

                                    continue

                                if ny2 < 0 or ny2 >= ny:

                                    continue

                                if nx2 < 0 or nx2 >= nx:

                                    continue

                                if not eroded[nz2, ny2, nx2]:

                                    continue

                                if visited[nz2, ny2, nx2] != 0:

                                    continue

                                visited[nz2, ny2, nx2] = label
                                q.append((nz2, ny2, nx2))

                        sizes[label] = cnt

            if not sizes:

                return 0, totalBefore

            if keepLargestOnly:

                largest = max(
                    sizes,
                    key=lambda k: sizes[k]
                )

                seed = visited == largest

            else:

                seed = eroded

            recon = seed.copy()

            for _ in range(
                nz + ny + nx
            ):

                nxt = recon.copy()
                nxt[1:, :, :] |= recon[:-1, :, :]
                nxt[:-1, :, :] |= recon[1:, :, :]
                nxt[:, 1:, :] |= recon[:, :-1, :]
                nxt[:, :-1, :] |= recon[:, 1:, :]
                nxt[:, :, 1:] |= recon[:, :, :-1]
                nxt[:, :, :-1] |= recon[:, :, 1:]

                nxt = np.logical_and(
                    nxt,
                    binary
                )

                if np.array_equal(nxt, recon):

                    break

                recon = nxt

            newBinary = recon

        totalAfter = int(
            np.count_nonzero(
                newBinary
            )
        )

        removed = int(
            totalBefore - totalAfter
        )

        if removed <= 0:

            print(
                "[VoxelRegionGrowing] Refinamento: nenhuma ponte fina detectada."
            )

            return 0, totalBefore

        newArr = newBinary.astype(np.uint8)

        try:

            slicer.util.updateSegmentBinaryLabelmapFromArray(
                newArr,
                segmentationNode,
                segmentID,
                referenceVolumeNode
            )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] updateSegmentBinaryLabelmapFromArray falhou no refinamento, fallback:",
                e
            )

            try:

                import vtk
                from vtk.util import numpy_support

                segmentation.CreateRepresentation(
                    "Binary labelmap"
                )

                try:

                    segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(
                        referenceVolumeNode
                    )

                except Exception:

                    pass

                imageData = referenceVolumeNode.GetImageData()

                if imageData is None:

                    raise RuntimeError(
                        "Reference volume sem ImageData."
                    )

                extent = imageData.GetExtent()

                ijkToRAS = vtk.vtkMatrix4x4()

                referenceVolumeNode.GetIJKToRASMatrix(
                    ijkToRAS
                )

                expectedShape = (
                    int(extent[5] - extent[4] + 1),
                    int(extent[3] - extent[2] + 1),
                    int(extent[1] - extent[0] + 1)
                )

                if newArr.shape != expectedShape:

                    raise RuntimeError(
                        "Shape {} difere do esperado {} extent {}".format(
                            newArr.shape,
                            expectedShape,
                            extent
                        )
                    )

                flat = np.ascontiguousarray(
                    newArr
                ).ravel()

                vtkArray = numpy_support.numpy_to_vtk(
                    num_array=flat,
                    deep=True,
                    array_type=vtk.VTK_UNSIGNED_CHAR
                )

                oriented = slicer.vtkOrientedImageData()

                oriented.SetExtent(
                    extent
                )

                oriented.AllocateScalars(
                    vtk.VTK_UNSIGNED_CHAR,
                    1
                )

                oriented.GetPointData().SetScalars(
                    vtkArray
                )

                oriented.SetGeometryFromImageToWorldMatrix(
                    ijkToRAS
                )

                oriented.Modified()

                success = slicer.vtkSlicerSegmentationsModuleLogic.SetBinaryLabelmapToSegment(
                    oriented,
                    segmentationNode,
                    segmentID,
                    slicer.vtkSlicerSegmentationsModuleLogic.MODE_REPLACE
                )

                if not success:

                    raise RuntimeError(
                        "SetBinaryLabelmapToSegment retornou False."
                    )

            except Exception as e2:

                raise RuntimeError(
                    "Falha ao aplicar refinamento: {} ; fallback: {}".format(
                        e,
                        e2
                    )
                )

        segmentationNode.Modified()

        try:

            segmentationNode.GetDisplayNode().Modified()

        except Exception:

            pass

        print(
            "[VoxelRegionGrowing] Refinamento ponte fina raio={} keepLargest={}: antes {} depois {} removidos {}".format(
                radius,
                keepLargestOnly,
                totalBefore,
                totalAfter,
                removed
            )
        )

        return removed, totalAfter

    def fillHolesInSegment(
        self,
        segmentationNode,
        segmentID
    ):

        if segmentationNode is None:

            raise ValueError(
                "Segmentação inválida."
            )

        if not segmentID:

            raise ValueError(
                "SegmentID inválido."
            )

        segmentation = (
            segmentationNode.GetSegmentation()
        )

        if segmentation is None:

            raise RuntimeError(
                "Segmentation inválida."
            )

        segment = (
            segmentation.GetSegment(
                segmentID
            )
        )

        if segment is None:

            raise ValueError(
                "Segmento não encontrado: {}".format(
                    segmentID
                )
            )

        referenceVolumeNode = None

        try:

            referenceVolumeNode = (
                segmentationNode.GetNodeReference(
                    slicer.vtkMRMLSegmentationNode.GetReferenceImageGeometryReferenceRole()
                )
            )

        except Exception:

            referenceVolumeNode = None

        if referenceVolumeNode is None:

            try:

                referenceVolumeNode = (
                    slicer.mrmlScene.GetFirstNodeByClass(
                        "vtkMRMLScalarVolumeNode"
                    )
                )

                if referenceVolumeNode is None:

                    referenceVolumeNode = (
                        slicer.mrmlScene.GetFirstNodeByClass(
                            "vtkMRMLLabelMapVolumeNode"
                        )
                    )

            except Exception:

                referenceVolumeNode = None

        if referenceVolumeNode is None:

            raise RuntimeError(
                "Não foi possível determinar o volume de referência da segmentação. "
                "Defina um Reference Image Geometry na segmentação ou tenha um volume na cena."
            )

        try:

            arr = slicer.util.arrayFromSegmentBinaryLabelmap(
                segmentationNode,
                segmentID,
                referenceVolumeNode
            )

        except Exception as e:

            raise RuntimeError(
                "Falha ao obter array do segmento (arrayFromSegmentBinaryLabelmap): {}".format(
                    e
                )
            )

        if arr is None:

            raise RuntimeError(
                "Não foi possível obter a representação binary labelmap do segmento."
            )

        arr = np.array(
            arr,
            copy=True
        )

        if arr.ndim != 3:

            raise RuntimeError(
                "Array do segmento deve ser 3D, recebido shape {}".format(
                    arr.shape
                )
            )

        binary = arr.astype(bool)

        if not np.any(binary):

            print(
                "[VoxelRegionGrowing] Segmento vazio, nada a preencher."
            )

            return 0

        if np.all(binary):

            print(
                "[VoxelRegionGrowing] Segmento totalmente preenchido."
            )

            return 0

        try:

            from scipy.ndimage import binary_fill_holes as scipy_fill

            filled = scipy_fill(
                binary
            )

            holes = np.logical_and(
                filled,
                np.logical_not(binary)
            )

            filledCount = int(
                np.count_nonzero(holes)
            )

            if filledCount == 0:

                return 0

            newArr = filled.astype(np.uint8)

        except Exception as e:

            print(
                "[VoxelRegionGrowing] scipy não disponível ou falhou, usando flood fill manual:",
                e
            )

            nz, ny, nx = binary.shape

            visited = np.zeros_like(
                binary,
                dtype=bool
            )

            queue = deque()

            def tryEnqueue(z, y, x):

                if binary[z, y, x]:

                    return

                if visited[z, y, x]:

                    return

                visited[z, y, x] = True

                queue.append(
                    (z, y, x)
                )

            for y in range(ny):

                for x in range(nx):

                    tryEnqueue(0, y, x)
                    tryEnqueue(nz - 1, y, x)

            for z in range(nz):

                for x in range(nx):

                    tryEnqueue(z, 0, x)
                    tryEnqueue(z, ny - 1, x)

            for z in range(nz):

                for y in range(ny):

                    tryEnqueue(z, y, 0)
                    tryEnqueue(z, y, nx - 1)

            offsets6 = [
                (1, 0, 0),
                (-1, 0, 0),
                (0, 1, 0),
                (0, -1, 0),
                (0, 0, 1),
                (0, 0, -1)
            ]

            while queue:

                cz, cy, cx = queue.popleft()

                for dz, dy, dx in offsets6:

                    nz2 = cz + dz
                    ny2 = cy + dy
                    nx2 = cx + dx

                    if nz2 < 0 or nz2 >= nz:

                        continue

                    if ny2 < 0 or ny2 >= ny:

                        continue

                    if nx2 < 0 or nx2 >= nx:

                        continue

                    if visited[nz2, ny2, nx2]:

                        continue

                    if binary[nz2, ny2, nx2]:

                        continue

                    visited[nz2, ny2, nx2] = True

                    queue.append(
                        (nz2, ny2, nx2)
                    )

            holes = np.logical_and(
                np.logical_not(binary),
                np.logical_not(visited)
            )

            filledCount = int(
                np.count_nonzero(holes)
            )

            if filledCount == 0:

                return 0

            newArr = np.logical_or(
                binary,
                holes
            ).astype(np.uint8)

        try:

            slicer.util.updateSegmentBinaryLabelmapFromArray(
                newArr,
                segmentationNode,
                segmentID,
                referenceVolumeNode
            )

        except Exception as e:

            print(
                "[VoxelRegionGrowing] updateSegmentBinaryLabelmapFromArray falhou, tentando fallback automático (mask volume):",
                e
            )

            try:

                import vtk
                from vtk.util import numpy_support

                segmentation.CreateRepresentation(
                    "Binary labelmap"
                )

                try:

                    segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(
                        referenceVolumeNode
                    )

                except Exception:

                    pass

                imageData = referenceVolumeNode.GetImageData()

                if imageData is None:

                    raise RuntimeError(
                        "Reference volume sem ImageData."
                    )

                extent = imageData.GetExtent()

                ijkToRAS = vtk.vtkMatrix4x4()

                referenceVolumeNode.GetIJKToRASMatrix(
                    ijkToRAS
                )

                expectedShape = (
                    int(extent[5] - extent[4] + 1),
                    int(extent[3] - extent[2] + 1),
                    int(extent[1] - extent[0] + 1)
                )

                if newArr.shape != expectedShape:

                    raise RuntimeError(
                        "Shape do array preenchido {} difere do extent esperado {} (extent {})".format(
                            newArr.shape,
                            expectedShape,
                            extent
                        )
                    )

                flat = np.ascontiguousarray(
                    newArr
                ).ravel()

                vtkArray = numpy_support.numpy_to_vtk(
                    num_array=flat,
                    deep=True,
                    array_type=vtk.VTK_UNSIGNED_CHAR
                )

                oriented = slicer.vtkOrientedImageData()

                oriented.SetExtent(
                    extent
                )

                oriented.AllocateScalars(
                    vtk.VTK_UNSIGNED_CHAR,
                    1
                )

                oriented.GetPointData().SetScalars(
                    vtkArray
                )

                oriented.SetGeometryFromImageToWorldMatrix(
                    ijkToRAS
                )

                oriented.Modified()

                success = slicer.vtkSlicerSegmentationsModuleLogic.SetBinaryLabelmapToSegment(
                    oriented,
                    segmentationNode,
                    segmentID,
                    slicer.vtkSlicerSegmentationsModuleLogic.MODE_REPLACE
                )

                if not success:

                    tmpLabel = slicer.mrmlScene.AddNewNodeByClass(
                        "vtkMRMLLabelMapVolumeNode",
                        "__VoxelRegionGrowing_FillHoles_Temp__"
                    )

                    try:

                        tmpLabel.SetIJKToRASMatrix(
                            ijkToRAS
                        )

                        tmpLabel.SetAndObserveImageData(
                            oriented
                        )

                        segmentIds = vtk.vtkStringArray()
                        segmentIds.InsertNextValue(
                            segmentID
                        )

                        ok = slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                            tmpLabel,
                            segmentationNode,
                            segmentIds
                        )

                        if not ok:

                            raise RuntimeError(
                                "ImportLabelmapToSegmentationNode retornou False (fallback)."
                            )

                    finally:

                        try:

                            slicer.mrmlScene.RemoveNode(
                                tmpLabel
                            )

                        except Exception:

                            pass

            except Exception as e2:

                raise RuntimeError(
                    "Falha ao aplicar labelmap preenchido (updateSegmentBinaryLabelmapFromArray): {} ; fallback também falhou: {}".format(
                        e,
                        e2
                    )
                )

        segmentationNode.Modified()

        try:

            segmentationNode.GetDisplayNode().Modified()

        except Exception:

            pass

        print(
            "[VoxelRegionGrowing] Buracos preenchidos: {} voxels".format(
                filledCount
            )
        )

        return filledCount


#
# ============================================================
# TEST
# ============================================================
#

class VoxelRegionGrowingTest(
    ScriptedLoadableModuleTest
):

    #
    # ========================================================
    # SETUP
    # ========================================================
    #

    def setUp(self):

        slicer.mrmlScene.Clear(
            0
        )

    #
    # ========================================================
    # RUN TEST
    # ========================================================
    #

    def runTest(self):

        self.setUp()

        self.testVoxelRegionGrowing()

    #
    # ========================================================
    # TEST
    # ========================================================
    #

    def testVoxelRegionGrowing(self):

        self.delayDisplay(
            "Teste Voxel Region Growing"
        )

        #
        # ----------------------------------------------------
        # Download sample
        # ----------------------------------------------------
        #

        import SampleData

        volumeNode = (
            SampleData.downloadSample(
                "MRHead"
            )
        )

        self.assertIsNotNone(
            volumeNode
        )

        #
        # ----------------------------------------------------
        # Create logic
        # ----------------------------------------------------
        #

        logic = (
            VoxelRegionGrowingLogic()
        )

        #
        # ----------------------------------------------------
        # Get extent
        # ----------------------------------------------------
        #

        imageData = (
            volumeNode.GetImageData()
        )

        self.assertIsNotNone(
            imageData
        )

        extent = (
            imageData.GetExtent()
        )

        #
        # ----------------------------------------------------
        # Center seed
        # ----------------------------------------------------
        #

        seed = [
            int(
                round(
                    (
                        extent[0]
                        +
                        extent[1]
                    )
                    /
                    2.0
                )
            ),
            int(
                round(
                    (
                        extent[2]
                        +
                        extent[3]
                    )
                    /
                    2.0
                )
            ),
            int(
                round(
                    (
                        extent[4]
                        +
                        extent[5]
                    )
                    /
                    2.0
                )
            )
        ]

        #
        # ----------------------------------------------------
        # Test IJK
        # ----------------------------------------------------
        #

        self.assertTrue(
            logic.isIJKInsideExtent(
                seed,
                extent
            )
        )

        #
        # ----------------------------------------------------
        # Get seed value
        # ----------------------------------------------------
        #

        value = (
            logic.getVoxelValue(
                volumeNode,
                seed
            )
        )

        self.assertTrue(
            np.isfinite(
                value
            )
        )

        #
        # ----------------------------------------------------
        # Test connectivity
        # ----------------------------------------------------
        #

        neighbors6 = (
            logic.getNeighborOffsets(
                6
            )
        )

        neighbors18 = (
            logic.getNeighborOffsets(
                18
            )
        )

        neighbors26 = (
            logic.getNeighborOffsets(
                26
            )
        )

        self.assertEqual(
            len(neighbors6),
            6
        )

        self.assertEqual(
            len(neighbors18),
            18
        )

        self.assertEqual(
            len(neighbors26),
            26
        )

        #
        # ----------------------------------------------------
        # Run region growing
        # ----------------------------------------------------
        #

        labelmap = (
            logic.regionGrow(
                volumeNode=volumeNode,
                seedIJK=seed,
                tolerance=10.0,
                maxLoops=2,
                connectivity=6,
                adaptive=False,
                maxVoxels=10000
            )
        )

        #
        # ----------------------------------------------------
        # Verify labelmap
        # ----------------------------------------------------
        #

        self.assertIsNotNone(
            labelmap
        )

        #
        # Verify correct class
        #

        self.assertTrue(
            labelmap.IsA(
                "vtkOrientedImageData"
            )
        )

        #
        # Verify scalars
        #

        self.assertIsNotNone(
            labelmap.GetPointData().GetScalars()
        )

        #
        # Verify extent
        #

        self.assertEqual(
            labelmap.GetExtent(),
            extent
        )

        #
        # Finish
        #

        self.delayDisplay(
            "Teste Voxel Region Growing concluído."
        )