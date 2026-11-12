# ToothFairy Segmentation Loader for 3D Slicer

Extensão oficial e independente para o **3D Slicer** desenvolvida para carregar arquivos de segmentação do dataset **ToothFairy 2** (`labelsTr/*.mha`) diretamente como nós nativos de **Segmentação (`vtkMRMLSegmentationNode`)** com múltiplos segmentos nomeados e coloridos corretamente, seguindo as diretrizes e a ontologia anatômica definidas no `dataset.json`.

---

## 🌟 Principais Recursos

1. **Importação Direta com Metadados do `dataset.json`:**
   - Lê dinamicamente o arquivo `dataset.json` para obter os nomes oficiais de todas as 42 estruturas rotuladas.
   - Suporte bilíngue completo (Português e Inglês) e notação odontológica internacional **FDI (11 a 48)**.
   - Categorização automática: *Elemento Dentário*, *Osso/Arcada*, *Canal Nervoso*, *Seio Aéreo*, *Via Aérea* e *Prótese/Implante*.

2. **Esquemas de Cores Anatômicas Clínicas:**
   - **Clínico / Cirúrgico:**
     - Mandíbula e Maxila: Bege/Marfim ósseo natural.
     - Canais Alveolares Inferiores (Esquerdo e Direito): Amarelo nervo elétrico.
     - Seios Maxilares (Esquerdo e Direito): Azul ciano translúcido (cavidades aéreas).
     - Faringe: Roxo via aérea.
     - Implantes e Próteses: Titânio e cerâmica dourada.
     - Dentes com distinção por quadrante: Quadrante 1 (Ciano), Quadrante 2 (Verde), Quadrante 3 (Coral/Laranja), Quadrante 4 (Magenta/Lavanda).
   - **Quadrantes Simplificados:** 4 cores sólidas para os quadrantes e bege para ossos.
   - **Arco-íris / Cores Exclusivas:** máxima separação cromática no espaço HSV (cada rótulo tem uma cor única).

3. **Carregamento Automático da Tomografia CBCT (Background Volume):**
   - Ao carregar uma segmentação (ex: `ToothFairy2F_001.mha`), a extensão localiza automaticamente o exame de tomografia computadorizada CBCT correspondente em `imagesTr/` (ex: `ToothFairy2F_001_0000.mha`).
   - Carrega o volume e configura automaticamente as três janelas de corte 2D (*Axial/Red, Coronal/Green, Sagital/Yellow*) com a tomografia em nível de cinza como fundo e a segmentação colorida sobreposta!

4. **Gerador de Superfícies 3D e Gerenciador de Visibilidade:**
   - Gera instantaneamente a representação de superfície fechada 3D (`Closed Surface Representation`).
   - Opção para **ocultar Maxila e Mandíbula no 3D inicialmente**, permitindo que o usuário visualize toda a arcada dentária em 3D de forma desobstruída (mantendo os ossos visíveis nas fatias 2D).
   - Barra de filtros de visibilidade rápida com 1 clique:
     - *Mostrar Todos*
     - *Ocultar Todos*
     - *Apenas Dentes*
     - *Arcada Superior*
     - *Arcada Inferior*

5. **Navegação Rápida entre Casos do Dataset:**
   - Dropdown que lista automaticamente todos os 480 exames disponíveis na pasta `labelsTr/`.
   - Permite alternar rapidamente entre casos clínicos do dataset sem precisar usar diálogos de navegação de pastas repetidamente.

6. **Exportação para `.seg.nrrd`:**
   - Permite salvar a segmentação no formato padrão do 3D Slicer (`.seg.nrrd`), preservando todos os nomes, cores, valores de label e metadados.

---

## 📁 Estrutura da Extensão

```text
ToothFairySegmentationLoader/
├── CMakeLists.txt                       # Arquivo de configuração para o Slicer Extension Wizard
├── ToothFairySegmentationLoader.py      # Código fonte completo (Interface Qt, Lógica e Testes)
├── README.md                            # Documentação completa em português
└── Resources/
    └── Icons/
        └── ToothFairySegmentationLoader.png # Ícone oficial com estilização de segmentação multi-label
```

---

## 🚀 Como Instalar e Usar no 3D Slicer

### Passo 1: Adicionar a Extensão ao 3D Slicer

1. Abra o **3D Slicer**.
2. Vá no menu principal em: **Edit** -> **Application Settings** -> **Modules**.
3. Na seção **Additional module paths**, clique em **Add** e adicione o diretório:
   ```text
   D:\ToothFairy2_Dataset\Dataset112_ToothFairy2\ToothFairySegmentationLoader
   ```
4. Se ainda não adicionou a extensão de detecção de ápices, adicione também:
   ```text
   D:\ToothFairy2_Dataset\Dataset112_ToothFairy2\DentalRootApexDetector
   ```
5. Clique em **OK** e reinicie o 3D Slicer.
6. Acesse o módulo no menu de módulos na categoria **Dental** -> **ToothFairy Segmentation Loader** (ou pressione `Ctrl + F` e digite `ToothFairy`).

### Passo 2: Carregar uma Segmentação com Nomes Corretos

1. No campo **Caso do Dataset**, selecione o caso desejado (ex: `ToothFairy2F_001.mha`).
2. Escolha o formato dos nomes (ex: `[FDI]: Nome em Português`).
3. Mantenha marcado **Carregar CBCT correspondente (Background)** para ver o exame tomográfico junto com as estruturas coloridas.
4. Clique em **"Carregar Segmentação com Nomes Corretos"**.
5. Pronto! A cena do 3D Slicer exibirá a tomografia CBCT com todos os dentes e estruturas anatômicas identificados com seus nomes oficiais e cores anatômicas.

---

## 🔗 Integração com o Dental Root Apex Detector

As duas extensões foram desenhadas para trabalhar em conjunto:
1. Carregue o caso com o **ToothFairy Segmentation Loader**.
2. Abra o **Dental Root Apex Detector**, selecione a segmentação carregada e clique em **Identificar Ápices Radiculares**.
3. Os marcadores fiduciais nativos do Slicer serão posicionados diretamente sobre os ápices das raízes identificadas na segmentação.
