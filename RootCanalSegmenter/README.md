# RootCanalSegmenter (3D Slicer)

Extensao para o **3D Slicer** especializada em **segmentar o canal radicular**
a partir da **segmentacao completa do dente** (dente + canal).

A ideia central: a partir do dente ja segmentado, selecionar um
**intervalo de valores hipodensos** (`[min, max]`) dentro da mascara do dente.
Os voxels do dente cuja intensidade cai nesse intervalo correspondem ao
canal radicular (polpa). O resultado vai para uma **nova segmentacao dedicada**.

## Funcionalidades

- **Histograma e estatisticas** das intensidades dentro do dente
  (min, max, media, DP e percentis 1/5/10/25/50/75/90/95/99).
- **Sugestao automatica de faixa hipodensa**:
  - Otsu (min ate o limiar de Otsu);
  - Media - k*DP;
  - Percentis (p_low ate p_high).
- **Intervalo [min, max]** com `ctkDoubleRangeSlider` + spinboxes.
- **Preview** do intervalo como sobreposicao (overlay) nas slices/3D,
  com contagem de voxels, volume (mm3) e % do dente.
- **Selecao por clique** nas Slice Views (Red/Yellow/Green):
  - centrar a faixa no valor clicado;
  - definir o minimo;
  - definir o maximo;
  - marcar a **semente** para o region growing.
- **Pos-processamento** da mascara:
  - manter so o maior componente;
  - remover componentes menores que N voxels;
  - closing / opening (raio em voxels);
  - dilatar / erodir;
  - preencher buracos internos;
  - conectividade 6 / 18 / 26.
- **Region growing restrito** ao intervalo hipodenso (mantem o componente
  conectado a semente).
- **Automacao completa (1 clique)**: sugere a faixa -> pos-processa -> aplica.
- **Desfazer (undo)** do ultimo `Aplicar`.
- **Console / Log copiavel** (copiar log, copiar ultimo erro, limpar).

## Como usar (passo a passo)

1. Carregue o volume (por exemplo um CBCT / DICOM) no Slicer.
2. Certifique-se de que existe uma segmentacao com o **dente completo**
   (incluindo o canal).
3. Abra o modulo **Segmentation -> Root Canal Segmenter**.
4. Em *Volume e segmentacao do dente*, selecione o **Volume** e a
   **Segmentacao** e o **Segmento do dente**.
5. Clique em **Calcular histograma / estatisticas**.
6. Escolha a faixa hipodensa:
   - clique em **Sugerir faixa**, ou
   - ajuste `min`/`max` nos controles, ou
   - use **Ativar clique nas slices (faixa)** e clique em um voxel do canal.
7. Clique em **Atualizar preview** para conferir a sobreposicao (verde).
8. Ajuste o **Pos-processamento** (recomendado: *manter so o maior componente*
   + *preencher buracos*; use *closing* se o canal ficar fragmentado).
9. (Opcional) marque **Aplicar region growing restrito** e defina uma semente.
10. Em *Saida (nova segmentacao)*, informe o nome da nova segmentacao e do
    segmento, e clique em **Aplicar / criar segmento do canal**.

> **Dica:** o Slicer carrega volumes de CBCT em HU (ou valores nativos). Se o
> seu volume estiver em outra escala, use as estatisticas/percentis para se
> orientar, em vez de valores absolutos.

## Instalacao sem compilacao (drag & drop)

1. Abra o 3D Slicer.
2. Arraste e solte o arquivo
   `RootCanalSegmenter/RootCanalSegmenter.py` (ou a pasta `RootCanalSegmenter`)
   dentro da janela do Slicer.
3. No dialogo, escolha *"Add Python scripted modules to the application"* -> OK.
4. Marque o modulo *RootCanalSegmenter* e clique **Yes** (marque a opcao
   *Add selected modules to 'Additional module paths'* para persistir).
5. O modulo aparece em **Segmentation -> Root Canal Segmenter**.

Caminho alternativo: **Edit -> Application Settings -> Modules**, arraste a
pasta `RootCanalSegmenter` para *Additional module paths* e reinicie o Slicer.

## Compilar como extensao (opcional)

1. Copie/clone esta pasta (a pasta raiz deve se chamar `RootCanalSegmenter`).
2. Compile usando o build de extensoes do Slicer (CMake), como nos outros
   modulos (`slicerMacroBuildScriptedModule`).
   Os arquivos `CMakeLists.txt` (raiz e aninhado) ja estao prontos.

## Estrutura

```
RootCanalSegmenter/
├── CMakeLists.txt
├── README.md
└── RootCanalSegmenter/
    ├── CMakeLists.txt
    ├── RootCanalSegmenter.py
    └── Resources/
        └── Icons/
            └── RootCanalSegmenter.png
```

## Notas tecnicas

- Leitura da mascara: `slicer.util.arrayFromSegmentBinaryLabelmap`
  (com fallback para `ExportSegmentsToLabelmapNode`).
- Leitura do volume: `slicer.util.arrayFromVolume`.
- Escrita da mascara: `slicer.util.updateSegmentBinaryLabelmapFromArray`
  (com fallback via `vtkOrientedImageData` + `SetBinaryLabelmapToSegment`).
- Pos-processamento e connected components via `scipy.ndimage`.
- O histograma e desenhado com `QPainter` (o Python embutido do Slicer nao
  traz `matplotlib`).
