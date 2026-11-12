import os
import vtk
import slicer

from qt import (
    QComboBox,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QSettings
)

from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic
)


# ============================================================
# MODULE
# ============================================================

class SlicerSliceOBJ(ScriptedLoadableModule):

    def __init__(self, parent):

        ScriptedLoadableModule.__init__(
            self,
            parent
        )

        parent.title = "Slice to OBJ"
        parent.categories = ["Utilities"]
        parent.dependencies = []
        parent.contributors = ["Pedro"]

        parent.helpText = (
            "Exporta um corte do 3D Slicer "
            "como um plano OBJ texturizado."
        )


# ============================================================
# WIDGET
# ============================================================

class SlicerSliceOBJWidget(
    ScriptedLoadableModuleWidget
):

    def setup(self):

        ScriptedLoadableModuleWidget.setup(
            self
        )

        self.settings = QSettings()

        self.logic = (
            SlicerSliceOBJLogic()
        )

        # ====================================================
        # TITULO
        # ====================================================

        title = QLabel(
            "<h2>Slice to OBJ</h2>"
        )

        self.layout.addWidget(
            title
        )


        description = QLabel(
            "Exporta o corte selecionado como "
            "um plano 3D OBJ usando a imagem "
            "do corte como textura."
        )

        description.setWordWrap(
            True
        )

        self.layout.addWidget(
            description
        )


        # ====================================================
        # CORTE
        # ====================================================

        sliceBox = QGroupBox(
            "Corte"
        )

        sliceLayout = QFormLayout(
            sliceBox
        )


        self.sliceSelector = QComboBox()


        self.sliceSelector.addItem(
            "Red - Axial",
            "Red"
        )


        self.sliceSelector.addItem(
            "Yellow - Sagittal",
            "Yellow"
        )


        self.sliceSelector.addItem(
            "Green - Coronal",
            "Green"
        )


        self.sliceSelector.addItem(
            "Reformatted / outro Slice",
            "Reformatted"
        )


        sliceLayout.addRow(
            "Tipo:",
            self.sliceSelector
        )


        self.layout.addWidget(
            sliceBox
        )


        # ====================================================
        # REFORMATTED
        # ====================================================

        self.reformattedSelector = (
            slicer.qMRMLNodeComboBox()
        )


        self.reformattedSelector.nodeTypes = [
            "vtkMRMLSliceNode"
        ]


        self.reformattedSelector.setMRMLScene(
            slicer.mrmlScene
        )


        self.reformattedSelector.addEnabled = False
        self.reformattedSelector.removeEnabled = False
        self.reformattedSelector.noneEnabled = False
        self.reformattedSelector.showHidden = False


        self.reformattedLabel = QLabel(
            "Slice Node:"
        )


        self.layout.addWidget(
            self.reformattedLabel
        )


        self.layout.addWidget(
            self.reformattedSelector
        )


        # ====================================================
        # CONEXAO
        # ====================================================

        self.sliceSelector.currentIndexChanged.connect(
            self.updateInterface
        )


        # ====================================================
        # SAIDA
        # ====================================================

        outputBox = QGroupBox(
            "Saída"
        )


        outputLayout = QFormLayout(
            outputBox
        )


        # ====================================================
        # NOME
        # ====================================================

        self.nameEdit = QLineEdit()


        savedName = self.settings.value(
            "SliceToOBJ/name",
            "slice_plane"
        )


        self.nameEdit.setText(
            str(savedName)
        )


        outputLayout.addRow(
            "Nome:",
            self.nameEdit
        )


        # ====================================================
        # PASTA
        # ====================================================

        folderLayout = QHBoxLayout()


        self.folderEdit = QLineEdit()


        savedFolder = self.settings.value(
            "SliceToOBJ/folder",
            os.path.join(
                os.path.expanduser("~"),
                "Desktop",
                "SlicerSliceOBJ"
            )
        )


        self.folderEdit.setText(
            str(savedFolder)
        )


        folderLayout.addWidget(
            self.folderEdit
        )


        self.folderButton = QPushButton(
            "Escolher..."
        )


        self.folderButton.clicked.connect(
            self.chooseFolder
        )


        folderLayout.addWidget(
            self.folderButton
        )


        outputLayout.addRow(
            "Pasta:",
            folderLayout
        )


        # ====================================================
        # PREFERENCIAS
        # ====================================================

        self.savePreferences = QCheckBox(
            "Salvar nome e pasta como padrão"
        )


        self.savePreferences.setChecked(
            True
        )


        outputLayout.addRow(
            "",
            self.savePreferences
        )


        self.layout.addWidget(
            outputBox
        )


        # ====================================================
        # EXPORTAR
        # ====================================================

        self.exportButton = QPushButton(
            "EXPORTAR COMO OBJ"
        )


        self.exportButton.setMinimumHeight(
            45
        )


        self.exportButton.clicked.connect(
            self.exportSlice
        )


        self.layout.addWidget(
            self.exportButton
        )


        # ====================================================
        # STATUS
        # ====================================================

        self.statusLabel = QLabel(
            ""
        )


        self.statusLabel.setWordWrap(
            True
        )


        self.layout.addWidget(
            self.statusLabel
        )


        self.layout.addStretch(
            1
        )


        # ====================================================
        # ESTADO INICIAL
        # ====================================================

        self.updateInterface()


    # ========================================================
    # INTERFACE
    # ========================================================

    def updateInterface(
        self,
        index=None
    ):

        selected = (
            self.sliceSelector.currentData
        )


        isReformatted = (
            selected == "Reformatted"
        )


        self.reformattedLabel.setVisible(
            isReformatted
        )


        self.reformattedSelector.setVisible(
            isReformatted
        )


        if isReformatted:

            self.statusLabel.setText(
                "Selecione o Slice Node "
                "reformatted ou oblíquo."
            )

        else:

            self.statusLabel.setText(
                "Slice selecionado: "
                + str(selected)
            )


    # ========================================================
    # ESCOLHER PASTA
    # ========================================================

    def chooseFolder(self):

        folder = QFileDialog.getExistingDirectory(
            self,
            "Escolher pasta de saída",
            self.folderEdit.text
        )


        if folder:

            self.folderEdit.setText(
                folder
            )


    # ========================================================
    # OBTER SLICE
    # ========================================================

    def getSliceNode(self):

        selected = (
            self.sliceSelector.currentData
        )


        # ====================================================
        # REFORMATTED
        # ====================================================

        if selected == "Reformatted":

            node = (
                self.reformattedSelector
                .currentNode()
            )


            if node is None:

                raise RuntimeError(
                    "Selecione um Slice Node "
                    "reformatted."
                )


            return node


        # ====================================================
        # SLICE PADRAO
        # ====================================================

        layoutManager = (
            slicer.app.layoutManager()
        )


        sliceWidget = (
            layoutManager
            .sliceWidget(
                selected
            )
        )


        if sliceWidget is None:

            raise RuntimeError(
                "Não foi possível encontrar "
                "o Slice " + str(selected)
            )


        return (
            sliceWidget
            .mrmlSliceNode()
        )


    # ========================================================
    # EXPORTAR
    # ========================================================

    def exportSlice(self):

        try:

            sliceNode = (
                self.getSliceNode()
            )


            name = (
                self.nameEdit.text
                .strip()
            )


            folder = (
                self.folderEdit.text
                .strip()
            )


            # ------------------------------------------------
            # VALIDACAO
            # ------------------------------------------------

            if not name:

                raise RuntimeError(
                    "Digite um nome para o OBJ."
                )


            if not folder:

                raise RuntimeError(
                    "Escolha uma pasta de saída."
                )


            # ------------------------------------------------
            # REMOVER EXTENSAO
            # ------------------------------------------------

            for extension in (
                ".obj",
                ".mtl",
                ".png"
            ):

                if name.lower().endswith(
                    extension
                ):

                    name = name[
                        :-len(extension)
                    ]


            os.makedirs(
                folder,
                exist_ok=True
            )


            # =================================================
            # EXPORTACAO
            # =================================================

            result = (
                self.logic.exportSlice(
                    sliceNode,
                    folder,
                    name
                )
            )


            # =================================================
            # SALVAR PREFERENCIAS
            # =================================================

            if self.savePreferences.isChecked():

                self.settings.setValue(
                    "SliceToOBJ/name",
                    name
                )


                self.settings.setValue(
                    "SliceToOBJ/folder",
                    folder
                )


            # =================================================
            # RESULTADO
            # =================================================

            self.statusLabel.setText(
                "<b>Exportação concluída!</b><br><br>"
                "OBJ:<br>"
                + result["obj"]
                + "<br><br>"
                "MTL:<br>"
                + result["mtl"]
                + "<br><br>"
                "Textura:<br>"
                + result["texture"]
            )


            slicer.util.infoDisplay(
                "OBJ exportado com sucesso!",
                windowTitle="Slice to OBJ"
            )


        except Exception as error:

            import traceback

            traceback.print_exc()


            self.statusLabel.setText(
                "<b>ERRO:</b><br>"
                + str(error)
            )


            slicer.util.errorDisplay(
                str(error),
                windowTitle="Slice to OBJ"
            )


# ============================================================
# LOGIC
# ============================================================

class SlicerSliceOBJLogic(
    ScriptedLoadableModuleLogic
):


    # ========================================================
    # SLICE LOGIC
    # ========================================================

    def getSliceLogic(
        self,
        sliceNode
    ):

        layoutName = (
            sliceNode.GetLayoutName()
        )


        # ----------------------------------------------------
        # PELO LAYOUT
        # ----------------------------------------------------

        if layoutName:

            try:

                sliceWidget = (
                    slicer.app
                    .layoutManager()
                    .sliceWidget(
                        layoutName
                    )
                )


                if sliceWidget:

                    return (
                        sliceWidget
                        .sliceLogic()
                    )

            except:

                pass


        # ----------------------------------------------------
        # PROCURAR NOS TRES PADRAO
        # ----------------------------------------------------

        layoutManager = (
            slicer.app
            .layoutManager()
        )


        for name in (
            "Red",
            "Yellow",
            "Green"
        ):

            try:

                widget = (
                    layoutManager
                    .sliceWidget(name)
                )


                if widget:

                    node = (
                        widget
                        .mrmlSliceNode()
                    )


                    if node == sliceNode:

                        return (
                            widget
                            .sliceLogic()
                        )


            except:

                pass


        raise RuntimeError(
            "Não foi possível obter "
            "o Slice Logic."
        )


    # ========================================================
    # EXPORT
    # ========================================================

    def exportSlice(
        self,
        sliceNode,
        folder,
        name
    ):


        print("")
        print(
            "========================================"
        )
        print(
            "EXPORTANDO SLICE"
        )
        print(
            "========================================"
        )


        print(
            "Slice:",
            sliceNode.GetLayoutName()
        )


        # ====================================================
        # SLICE LOGIC
        # ====================================================

        sliceLogic = (
            self.getSliceLogic(
                sliceNode
            )
        )


        # ====================================================
        # COMPOSITE
        # ====================================================

        composite = (
            sliceLogic
            .GetSliceCompositeNode()
        )


        if composite is None:

            raise RuntimeError(
                "Slice Composite Node "
                "não encontrado."
            )


        # ====================================================
        # VOLUME
        # ====================================================

        volumeID = (
            composite
            .GetBackgroundVolumeID()
        )


        if not volumeID:

            raise RuntimeError(
                "Não existe volume "
                "de background."
            )


        volume = (
            slicer.mrmlScene
            .GetNodeByID(
                volumeID
            )
        )


        if volume is None:

            raise RuntimeError(
                "Volume não encontrado."
            )


        print(
            "Volume:",
            volume.GetName()
        )


        # ====================================================
        # RESLICE
        # ====================================================

        backgroundLayer = (
            sliceLogic
            .GetBackgroundLayer()
        )


        if backgroundLayer is None:

            raise RuntimeError(
                "Background Layer "
                "não encontrada."
            )


        reslice = (
            backgroundLayer
            .GetReslice()
        )


        if reslice is None:

            raise RuntimeError(
                "Reslice não encontrado."
            )


        reslice.Update()


        image = vtk.vtkImageData()


        image.DeepCopy(
            reslice.GetOutput()
        )


        # ====================================================
        # SCALARS
        # ====================================================

        if (
            image
            .GetPointData()
            .GetScalars()
            is None
        ):

            raise RuntimeError(
                "Imagem do corte "
                "não possui pixels."
            )


        print(
            "Imagem obtida."
        )


        # ====================================================
        # EXTENT
        # ====================================================

        extent = (
            image.GetExtent()
        )


        width = (
            extent[1]
            - extent[0]
            + 1
        )


        height = (
            extent[3]
            - extent[2]
            + 1
        )


        print(
            "Dimensão:",
            width,
            "x",
            height
        )


        # ====================================================
        # WINDOW / LEVEL
        # ====================================================

        display = (
            volume.GetDisplayNode()
        )


        if display:

            window = (
                display.GetWindow()
            )


            level = (
                display.GetLevel()
            )

        else:

            window = 0
            level = 0


        print(
            "Window:",
            window
        )


        print(
            "Level:",
            level
        )


        # ====================================================
        # WINDOW LEVEL
        # ====================================================

        wl = (
            vtk.vtkImageMapToWindowLevelColors()
        )


        wl.SetInputData(
            image
        )


        wl.SetWindow(
            window
        )


        wl.SetLevel(
            level
        )


        wl.SetOutputFormatToRGB()


        wl.Update()


        rgb = vtk.vtkImageData()


        rgb.DeepCopy(
            wl.GetOutput()
        )


        # ====================================================
        # ARQUIVOS
        # ====================================================

        objPath = os.path.join(
            folder,
            name + ".obj"
        )


        mtlPath = os.path.join(
            folder,
            name + ".mtl"
        )


        texturePath = os.path.join(
            folder,
            name + "_texture.png"
        )


        # ====================================================
        # TEXTURA
        # ====================================================

        pngWriter = (
            vtk.vtkPNGWriter()
        )


        pngWriter.SetFileName(
            texturePath
        )


        pngWriter.SetInputData(
            rgb
        )


        pngWriter.Write()


        print(
            "Textura:",
            texturePath
        )


        # ====================================================
        # TRANSFORMACAO DO SLICE
        # ====================================================

        xyToRAS = (
            sliceNode
            .GetXYToRAS()
        )


        # ====================================================
        # DIMENSOES DO SLICE
        # ====================================================

        dimensions = (
            sliceNode
            .GetDimensions()
        )


        fov = (
            sliceNode
            .GetFieldOfView()
        )


        print(
            "Slice dimensions:",
            dimensions
        )


        print(
            "FOV:",
            fov
        )


        # ====================================================
        # TAMANHO DO PIXEL
        # ====================================================

        pixelSizeX = (
            float(fov[0])
            /
            float(dimensions[0])
        )


        pixelSizeY = (
            float(fov[1])
            /
            float(dimensions[1])
        )


        # ====================================================
        # TAMANHO DO PLANO
        # ====================================================

        planeWidth = (
            width
            * pixelSizeX
        )


        planeHeight = (
            height
            * pixelSizeY
        )


        print(
            "Plano:",
            planeWidth,
            "x",
            planeHeight,
            "mm"
        )


        # ====================================================
        # CENTRO DO SLICE
        # ====================================================

        centerX = (
            float(dimensions[0])
            / 2.0
        )


        centerY = (
            float(dimensions[1])
            / 2.0
        )


        # ====================================================
        # TAMANHO DA IMAGEM
        # ====================================================

        halfWidth = (
            float(width)
            / 2.0
        )


        halfHeight = (
            float(height)
            / 2.0
        )


        # ====================================================
        # PONTOS XY
        # ====================================================

        xyPoints = [

            (
                centerX - halfWidth,
                centerY - halfHeight
            ),

            (
                centerX + halfWidth,
                centerY - halfHeight
            ),

            (
                centerX + halfWidth,
                centerY + halfHeight
            ),

            (
                centerX - halfWidth,
                centerY + halfHeight
            )

        ]


        # ====================================================
        # XY -> RAS
        # ====================================================

        rasPoints = []


        for x, y in xyPoints:

            p = (
                xyToRAS
                .MultiplyPoint(
                    [
                        x,
                        y,
                        0,
                        1
                    ]
                )
            )


            rasPoints.append(
                (
                    p[0],
                    p[1],
                    p[2]
                )
            )


        # ====================================================
        # MOSTRAR RAS
        # ====================================================

        print(
            ""
        )


        print(
            "Pontos RAS:"
        )


        for i, p in enumerate(
            rasPoints
        ):

            print(
                i,
                p
            )


        # ====================================================
        # RAS -> LPS
        # ====================================================

        lpsPoints = []


        for x, y, z in rasPoints:

            lpsPoints.append(
                (
                    -x,
                    -y,
                    z
                )
            )


        # ====================================================
        # OBJ
        # ====================================================

        with open(
            objPath,
            "w",
            encoding="utf-8"
        ) as f:


            f.write(
                "# Slicer Slice OBJ\n"
            )


            f.write(
                "mtllib "
                +
                os.path.basename(
                    mtlPath
                )
                +
                "\n"
            )


            f.write(
                "o "
                +
                name
                +
                "\n"
            )


            # ------------------------------------------------
            # VERTICES
            # ------------------------------------------------

            for x, y, z in lpsPoints:

                f.write(
                    "v "
                    "{:.9f} "
                    "{:.9f} "
                    "{:.9f}\n"
                    .format(
                        x,
                        y,
                        z
                    )
                )


            # ------------------------------------------------
            # UV
            # ------------------------------------------------

            uv = [

                (0, 0),
                (1, 0),
                (1, 1),
                (0, 1)

            ]


            for u, v in uv:

                f.write(
                    "vt "
                    "{:.9f} "
                    "{:.9f}\n"
                    .format(
                        u,
                        v
                    )
                )


            # ------------------------------------------------
            # MATERIAL
            # ------------------------------------------------

            f.write(
                "usemtl SliceTexture\n"
            )


            # ------------------------------------------------
            # FACE
            # ------------------------------------------------

            f.write(
                "f "
                "1/1 "
                "2/2 "
                "3/3 "
                "4/4\n"
            )


        # ====================================================
        # MTL
        # ====================================================

        with open(
            mtlPath,
            "w",
            encoding="utf-8"
        ) as f:


            f.write(
                "newmtl SliceTexture\n"
            )


            f.write(
                "Ka 1.0 1.0 1.0\n"
            )


            f.write(
                "Kd 1.0 1.0 1.0\n"
            )


            f.write(
                "Ks 0.0 0.0 0.0\n"
            )


            f.write(
                "Ns 0.0\n"
            )


            f.write(
                "d 1.0\n"
            )


            f.write(
                "illum 1\n"
            )


            f.write(
                "map_Kd "
                +
                os.path.basename(
                    texturePath
                )
                +
                "\n"
            )


        # ====================================================
        # PREVIEW NO SLICER
        # ====================================================

        points = vtk.vtkPoints()


        for x, y, z in rasPoints:

            points.InsertNextPoint(
                x,
                y,
                z
            )


        quad = vtk.vtkQuad()


        for i in range(4):

            quad.GetPointIds().SetId(
                i,
                i
            )


        cells = vtk.vtkCellArray()


        cells.InsertNextCell(
            quad
        )


        poly = vtk.vtkPolyData()


        poly.SetPoints(
            points
        )


        poly.SetPolys(
            cells
        )


        # ====================================================
        # UV NO MODELO
        # ====================================================

        tcoords = (
            vtk.vtkFloatArray()
        )


        tcoords.SetNumberOfComponents(
            2
        )


        tcoords.SetName(
            "TextureCoordinates"
        )


        for u, v in [

            (0, 0),
            (1, 0),
            (1, 1),
            (0, 1)

        ]:

            tcoords.InsertNextTuple2(
                u,
                v
            )


        poly.GetPointData().SetTCoords(
            tcoords
        )


        # ====================================================
        # PREVIEW MODEL
        # ====================================================

        previewName = (
            name
            +
            "_Preview"
        )


        old = (
            slicer.mrmlScene
            .GetFirstNodeByName(
                previewName
            )
        )


        if old:

            slicer.mrmlScene.RemoveNode(
                old
            )


        model = (
            slicer.mrmlScene
            .AddNewNodeByClass(
                "vtkMRMLModelNode",
                previewName
            )
        )


        model.SetAndObservePolyData(
            poly
        )


        model.CreateDefaultDisplayNodes()


        modelDisplay = (
            model.GetDisplayNode()
        )


        modelDisplay.SetBackfaceCulling(
            False
        )


        modelDisplay.SetScalarVisibility(
            False
        )


        # ====================================================
        # TEXTURA NO PREVIEW
        # ====================================================

        textureReader = (
            vtk.vtkPNGReader()
        )


        textureReader.SetFileName(
            texturePath
        )


        textureReader.Update()


        modelDisplay.SetTextureImageDataConnection(
            textureReader.GetOutputPort()
        )


        # ====================================================
        # FINAL
        # ====================================================

        print("")
        print(
            "========================================"
        )


        print(
            "EXPORTACAO CONCLUIDA"
        )


        print(
            "========================================"
        )


        print(
            "OBJ:",
            objPath
        )


        print(
            "MTL:",
            mtlPath
        )


        print(
            "TEXTURA:",
            texturePath
        )


        print(
            "Tamanho:",
            planeWidth,
            "x",
            planeHeight,
            "mm"
        )


        return {

            "obj": objPath,

            "mtl": mtlPath,

            "texture": texturePath,

            "width": planeWidth,

            "height": planeHeight

        }