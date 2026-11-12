# SegmentationValidator (nnU-Net)

Extensão para o **3D Slicer** que **valida as segmentações de treinamento** de um
dataset no formato **nnU-Net**. Ela navega pelos casos de `imagesTr`/`labelsTr` e
importa cada label como **segmento**, para conferir visualmente se a segmentação
está correta sobre a imagem.

## Como funciona

1. Informe a pasta do dataset (ex.: `Dataset001_canalRadicular`), que deve conter:
   ```
   <dataset>/imagesTr/<caso>_0000.nii.gz   (imagens)
   <dataset>/labelsTr/<caso>.nii.gz         (labels / ground truth)
   ```
2. Clique em **Carregar lista de casos** — o módulo cruza as pastas e lista os
   casos com imagem + label correspondentes (a modalidade `_0000`/`_0001` é
   ignorada na correspondência).
3. Navegue com os botões **Anterior** / **Próximo** (ou pela lista suspensa de casos).
4. Para cada caso:
   - a **imagem** é carregada na cena;
   - o **label é importado como segmento** (`ImportLabelmapToSegmentationNode`),
     sobreposto à imagem nas fatias (e no 3D).
5. Use **Fatia anterior** / **Fatia próxima** para percorrer as fatias do caso.

## Interface do módulo

* **Dataset:** pasta do dataset (contendo `imagesTr` e `labelsTr`)
* **Carregar lista de casos:** escaneia os pares imagem+label
* **Caso:** lista de casos (imagem + label)
* **Anterior / Próximo:** navegam entre os casos
* **Segmentos:** segmentos importados do label do caso atual (ao selecionar um,
  apenas ele fica visível)
* **Fatias:** navegação de fatia a fatia na vista axial (Red)

## Como instalar / usar sem compilação

1. Abra o 3D Slicer.
2. **Arraste e solte** o arquivo `SegmentationValidator/SegmentationValidator.py`
   (ou a pasta `SegmentationValidator`) dentro da janela do Slicer.
3. No diálogo, escolha *"Add Python scripted modules to the application"* → OK.
4. Marque o módulo *SegmentationValidator* e clique **Yes** (marque a opção
   *Add selected modules to 'Additional module paths'* para persistir).
5. Pasta o módulo em **Segmentation / Deep Learning**.

Caminho alternativo: **Edit → Application Settings → Modules**, arraste a pasta
`SegmentationValidator` até *Additional module paths* e reinicie o Slicer.

## Usar pela linha de comando / batch

```python
import SegmentationValidator
cases, skipped = SegmentationValidator.discoverTrainingCases("C:/data/Dataset001_x")
# cases listave-los: {'case', 'imageFile', 'labelFile', 'imagePath', 'labelPath'}
logic = SegmentationValidator.SegmentationValidatorLogic()
logic.loadTrainingCase(cases[0], index=0)
```

## Compilar como extensão (opcional)

1. Clone/copie esta pasta (a pasta raiz deve se chamar `SegmentationValidator`).
2. Configure com CMake apontando `Slicer_DIR` para a pasta `Slicer-build` de um
   Slicer compilado localmente:
   ```
   cmake -DSlicer_DIR:PATH=C:/SD/Slicer-SuperBuild-Release/Slicer-build ../SegmentationValidator
   cmake --build . --config Release
   ```

## Estrutura de arquivos

```
SegmentationValidator/
├── CMakeLists.txt                         # metadados da extensão
└── SegmentationValidator/
    ├── CMakeLists.txt                     # build do módulo scripted
    ├── SegmentationValidator.py            # módulo principal
    └── Resources/Icons/SegmentationValidator.png
```

## Observações

* O label é convertido para segmento usando o módulo nativo de Segmentações do
  Slicer (`ImportLabelmapToSegmentationNode`); se o label tiver vários rótulos,
  cada rótulo vira um segmento (navegável no combo **Segmentos**).
* Casos sem o par (imagem OU label) são ignorados e aparecem no aviso do módulo.
* A pasta do dataset fica salva (parameter node + `QSettings`) entre sessões.