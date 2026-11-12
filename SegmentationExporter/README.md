# SegmentationExporter (nnU-Net)

Extensão para o **3D Slicer** que ajuda a criar segmentações para treinamento de redes neurais
(deep learning). Para cada caso ela exporta dois arquivos, prontos para a pasta de um dataset
no formato **nnU-Net**:

```
<dataset>/imagesTr/<nome>_0000.nii.gz   (volume)
<dataset>/labelsTr/<nome>.nii.gz         (segmento convertido em labelmap)
```

Exemplo de pasta de dataset: `Dataset001_canalRadicular` (as pastas `imagesTr` e `labelsTr`
são criadas automaticamente dentro dela, se ainda não existirem).

## Interface do módulo

* **Dataset:** pasta do dataset (ex.: `Dataset001_canalRadicular`)
* **Nome:** nome do caso (ex.: `paciente_001`) — gera `<nome>_0000.nii.gz` e `<nome>.nii.gz`
* **Volume:** seletor de volume de origem (geometria de referência)
* **Segmentação / Segmento:** seguração (Segment Editor) e o segmento a exportar
* **Exportar:** botão que executa a exportação

O labelmap gerado tem a **mesma geometria** do volume selecionado (valor 1 = estrutura,
0 = fundo), o que é o esperado para treinamento de segmentação.

## Como instalar / usar sem compilação (recomendado)

Não é preciso compilar nada para usar módulos puros em Python:

1. Abra o 3D Slicer.
2. **Arraste e solte** o arquivo `SegmentationExporter/SegmentationExporter.py`
   (ou a pasta `SegmentationExporter`) dentro da janela do Slicer.
3. No diálogo, escolha *"Add Python scripted modules to the application"* → OK.
4. Marque o módulo *SegmentationExporter* para carregar e clique **Yes**.
   (Para aparecer em toda sessão, mantenha a opção *Add selected modules to
   'Additional module paths'* marcada.)
5. O módulo aparecerá em **Segmentation / Deep Learning**.

Caminho alternativo: **Edit → Application Settings → Modules**, arraste a pasta
`SegmentationExporter` até a lista *Additional module paths* e reinicie o Slicer.

## Usar pela linha de comando / batch (sem GUI)

```python
import SegmentationExporter
logic = SegmentationExporter.SegmentationExporterLogic()

logic.exportTrainingData(
    volumeNode,          # vtkMRMLScalarVolumeNode
    segmentationNode,    # vtkMRMLSegmentationNode
    segmentId,           # string, ex.: "Segment_1"
    "C:/data/Dataset001_x/imagesTr/paciente_001_0000.nii.gz",
    "C:/data/Dataset001_x/labelsTr/paciente_001.nii.gz",
)
```

## Compilar como extensão (opcional)

1. Clone/copie esta pasta (o nome da pasta raiz deve ser `SegmentationExporter`).
2. Configure com CMake, apontando `Slicer_DIR` para a pasta `Slicer-build` de um
   Slicer compilado localmente (extensões só podem ser compiladas contra um Slicer
   **compilado desde a fonte**):
   ```
   cmake -DSlicer_DIR:PATH=C:/SD/Slicer-SuperBuild-Release/Slicer-build ../SegmentationExporter
   cmake --build . --config Release
   ```
3. Instale o pacote gerado pelo Extension Manager (target `PACKAGE`).

## Estrutura de arquivos

```
SegmentationExporter/
├── CMakeLists.txt                         # metadados da extensão
├── SegmentationExporter/
│   ├── CMakeLists.txt                     # build do módulo scripted
│   ├── SegmentationExporter.py            # módulo principal (widget + lógica)
│   └── Resources/Icons/SegmentationExporter.png
```

## Observações

* O módulo usa o canal de segmentações nativo do Slicer
  (`vtkSlicerSegmentationsModuleLogic::ExportSegmentsToLabelmapNode`) para converter o
  segmento em labelmap alinhado ao volume.
* O nome do caso é "higienizado" automaticamente (espaços vêem, caracteres especiais e
  separadores de caminho são substituídos por `_`).
* As escolhas de pasta e nome ficam salvas no parâmetro node do módulo (persistem
  enquanto a cena for reutilizada).