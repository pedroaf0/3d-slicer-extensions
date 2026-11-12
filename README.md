# 3D Slicer Extensions

Este repositório reúne uma coleção de extensões para o 3D Slicer focadas em processamento de imagem médica, segmentação odontológica, exportação de datasets para deep learning e ferramentas utilitárias para análise volumétrica.

A ideia principal é centralizar módulos que ajudam em fluxos de trabalho clínicos e de pesquisa, especialmente em tomografias CBCT e segmentações dentárias.

## Visão geral do repositório

O repositório contém extensões para:

- segmentação automática e semi-automática de estruturas dentárias;
- detecção de ápices radiculares;
- exportação de segmentações em formato compatível com nnU-Net;
- validação de datasets de treinamento;
- carregamento de segmentações com nomes anatômicos;
- manipulação de intensidade e região de interesse volumétrica;
- utilitários para exportação de objetos 3D e segmentações em formatos úteis.

## Estrutura principal

```text
3d-slicer-extensions/
├── BinarySegmentationExporter/
├── DentalRootApexDetector/
├── MultiChannelSegmentationExporter/
├── RASLPSSwitcher/
├── RootCanalSegmenter/
├── SegmentationBooleanDifference/
├── SegmentationExporter/
├── SegmentationValidator/
├── SlicerSliceOBJ/
├── ToothFairySegmentationLoader/
├── VolumeIntensityModifier/
├── VoxelRegionGrowing/
├── CMakeLists.txt
├── README.md
└── ...
```

## Extensões e finalidade

| Extensão | Descrição | Uso principal |
| --- | --- | --- |
| BinarySegmentationExporter | Exporta segmentações binárias para uso em pipelines e treinamento. | Conversão de segmentação em dados exportáveis. |
| DentalRootApexDetector | Detecta o ápice radicular de dentes em CBCT/segmentações 3D. | Planejamento endodôntico, navegação anatômica. |
| MultiChannelSegmentationExporter | Exporta segmentações com múltiplos canais ou estruturas. | Datasets multi-label / multi-class. |
| RASLPSSwitcher | Alterna ou ajusta configurações relacionadas à orientação RAS/LPS. | Organização espacial e compatibilidade de coordenadas. |
| RootCanalSegmenter | Segmenta o canal radicular a partir de uma segmentação do dente. | Endodontia e análise do canal radicular. |
| SegmentationBooleanDifference | Realiza operações booleanas entre segmentações. | Diferença e comparação entre máscaras. |
| SegmentationExporter | Exporta segmentações em formato de dataset nnU-Net. | Treinamento de deep learning. |
| SegmentationValidator | Valida casos de treinamento e visualiza labels/segmentações. | Verificação de ground truth. |
| SlicerSliceOBJ | Exporta fatias ou objetos em OBJ a partir do ambiente do Slicer. | Conversão de fatias / visualização 3D. |
| ToothFairySegmentationLoader | Carrega segmentações do dataset ToothFairy com nomes e cores anatômicas. | Estudos odontológicos e carga de cases clínicos. |
| VolumeIntensityModifier | Modifica intensidade de volumes e realiza segmentações por esfera / ajuste de contraste. | Pré-processamento de volumes. |
| VoxelRegionGrowing | Permite crescimento de região sobre voxels com critérios específicos. | Segmentação interativa e semi-automática. |

## Detalhamento por extensão

### 1) BinarySegmentationExporter
Essa extensão foi criada para exportar segmentações binárias, geralmente em cenários em que uma estrutura de interesse precisa ser isolada e salva em um formato manejável para processamento posterior.

Em geral, ela é útil quando se deseja:
- transformar uma máscara de segmentação em dado exportável;
- preparar informações para pipeline de automação;
- trabalhar com dados binários em estudos de comparação ou treinamento.

### 2) DentalRootApexDetector
Uma das extensões mais relevantes do repositório. Ela tem foco em odontologia e em identificar automaticamente os ápices radiculares em tomografias 3D.

Suas principais funções incluem:
- análise anatômica dos dentes;
- identificação de raízes e bifurcações;
- marcação de fiduciais/apices em coordenadas do Slicer;
- apoio ao planejamento endodôntico e a validação visual do resultado.

O módulo é especialmente útil quando se trabalha com dados CBCT e segmentações dentárias complexas.

### 3) MultiChannelSegmentationExporter
Essa extensão amplia a ideia de exportação de segmentações para cenários com múltiplos canais ou múltiplos rótulos. Ela é indicada para casos em que o problema não é uma binarização simples, mas sim uma saída com diversas estruturas ou classes.

Ela é útil em:
- datasets multi-label;
- segmentação multi-estrutura;
- exportação de várias classes associadas a um mesmo volume.

### 4) RASLPSSwitcher
Foca em manipulação/alternância entre sistemas de coordenadas e convenções espaciais, como RAS e LPS. Em ferramentas de imagem médica, isso é importante porque inconsistências de coordenadas podem causar erros na visualização e na interpretação dos dados.

Esse módulo ajuda a manter compatibilidade entre diferentes representações do espaço.

### 5) RootCanalSegmenter
Extensão direcionada para segmentação do canal radicular a partir de uma máscara do dente completo. A ideia central é identificar voxels hipodensos dentro do dente para separar o canal da estrutura dentária.

Ela inclui recursos como:
- histograma de intensidades;
- sugestões automáticas de faixa de valores;
- preview em overlay;
- processing pós-segmentação;
- region growing restrito;
- aplicação de filtros e refinamento da máscara.

É uma ferramenta muito útil para endodontia e análise de canal radicular em CBCT.

### 6) SegmentationBooleanDifference
Essa ferramenta realiza operações booleanas entre segmentações. Em segmentação médica, é comum comparar estruturas distintas, remover sobreposições ou obter regiões exclusivas entre máscaras.

Possíveis usos:
- diferenciar duas segmentações;
- analisar o que ficou fora da interseção;
- comparar segmentação alvo vs. referência;
- pós-processamento de máscaras complexas.

### 7) SegmentationExporter
Esta é uma extensão de exportação para pipeline de aprendizado profundo. Ela gera arquivos em estrutura compatível com nnU-Net, criando pastas como `imagesTr` e `labelsTr` com volumes e labels.

Ela facilita a criação de datasets de treinamento para tarefas de segmentação, como:
- exportar um segmento selecionado;
- gerar labelmaps geométricos alinhados ao volume;
- padronizar casos para treinamento em redes neurais.

### 8) SegmentationValidator
Extensão focada na validação visual de segmentações em datasets de treinamento. Ela lê casos em formato nnU-Net, carrega a imagem e o label correspondente, e permite inspeção caso a caso.

Essa ferramenta é útil para:
- verificar qualidade de ground truth;
- inspecionar erros de anotação;
- revisar datasets antes do treinamento.

### 9) SlicerSliceOBJ
Extensão de suporte para manipulação de fatias/objetos 3D em formato OBJ dentro do ecossistema do Slicer. É útil para usuários que precisam converter ou exportar representações de superfícies e fatias em formatos intercambiáveis.

### 10) ToothFairySegmentationLoader
Essa é uma ferramenta de carga de segmentações do dataset ToothFairy. Ela é especialmente interessante para estudos odontológicos, pois importa segmentações com nomes anatômicos, classificação dentária e esquema de cores.

Entre os recursos esperados estão:
- leitura de metadados do dataset;
- nomes em português/inglês;
- classificação FDI;
- carregamento automático de volumes CBCT associados;
- exportação em formatos compatíveis com a cena do Slicer.

### 11) VolumeIntensityModifier
Este módulo atua sobre volumes, modificando intensidades e permitindo edição de contraste ou segmentação baseada em valores. Ele pode ser usado para:
- ajustar intensidade de imagens;
- segmentar estruturas por faixa de valores;
- preparar volumes para análise automatizada.

No repositório, há subcomponentes relacionados a `SphereSegmentation` e `VolumeModification`, indicando workflows específicos de modificação volumétrica e segmentação por esfera.

### 12) VoxelRegionGrowing
Ferramenta de segmentação interativa baseada em crescimento de região. Esse tipo de algoritmo começa a partir de uma semente e cresce a região seguindo critérios de similaridade ou conectividade.

Ela é útil para:
- segmentação semi-automática;
- identificar estruturas com intensidades homogêneas;
- refinar máscaras geradas manualmente.

## Fluxos típicos de uso

Os módulos do repositório normalmente se encaixam em alguns fluxos comuns:

1. Carregar uma imagem CBCT no 3D Slicer.
2. Realizar ou importar uma segmentação.
3. Usar uma extensão específica para refinamento anatômico ou exportação.
4. Exportar dados para treinamento em deep learning ou para análise clínica.
5. Validar e revisar resultados visualmente.

## Como usar as extensões

A maioria dos módulos neste repositório é um módulo Python para 3D Slicer e pode ser carregada de duas formas simples:

### Opção 1: arrastar e soltar
- Abra o 3D Slicer.
- Arraste a pasta da extensão (ou o arquivo `.py`) para a janela do Slicer.
- Escolha a opção para adicionar módulos Python.

### Opção 2: adicionar ao `Additional module paths`
- Vá em: Edit → Application Settings → Modules
- Adicione a pasta da extensão em `Additional module paths`
- Reinicie o Slicer

## Recomendação de uso

Para quem trabalha com odontologia e CBCT, as extensões mais relevantes são:
- DentalRootApexDetector
- RootCanalSegmenter
- ToothFairySegmentationLoader
- SegmentationValidator

Para criação de datasets de treinamento, as mais úteis são:
- SegmentationExporter
- SegmentationValidator
- MultiChannelSegmentationExporter

## Observações finais

Este repositório combina ferramentas práticas de pesquisa, automação e validação em processamento de imagem 3D, com forte foco em odontologia, segmentação e deep learning.

A organização por módulos facilita o uso independente de cada extensão, além de permitir a integração entre diferentes ferramentas dentro do mesmo fluxo de trabalho no 3D Slicer.

Se você trabalha com CBCT, segmentações dentárias, treinamento de rede neural ou processamento volumétrico, este repositório oferece uma boa base de módulos específicos para esse contexto.

## Licença

Consulte os arquivos individuais do repositório para verificar a licença de cada extensão, caso seja necessário em um projeto específico.

---

Este README foi escrito para servir como visão geral do repositório e documentação introdutória das extensões disponíveis.
