# Dental Root Apex Detector for 3D Slicer

Extensão oficial e independente para o **3D Slicer**, desenvolvida para identificar automaticamente o **ápice de cada raiz dentária** em segmentações 3D de tomografias computadorizadas de feixe cônico (CBCT), com suporte nativo ao dataset **ToothFairy 2** e ao sistema de numeração odontológica **FDI (11 a 48)**.

A extensão calcula com precisão a anatomia tridimensional de cada elemento dentário, isola individualmente as raízes de dentes unirradiculares e multirradiculares (incluindo molares superiores com 3 raízes e molares inferiores com 2 raízes ou variações como *radix entomolaris*), e insere marcadores fiduciais nativos do 3D Slicer (`vtkMRMLMarkupsFiducialNode`) nos ápices, permitindo visualização imediata nos planos ortogonais 2D (Axial, Coronal e Sagital) e no modelo volumétrico 3D.

---

## 🦷 Principais Características

1. **Classificação e Identificação FDI (11 a 48):**
   - Utiliza a numeração dentária internacional FDI para direcionar a busca anatômica de acordo com o quadrante e o grupo dentário (incisivos, caninos, pré-molares e molares).
   - Suporte a nomes em Português e Inglês com terminologia clínica oficial.

2. **Diferenciação Superior vs. Inferior:**
   - Detecta automaticamente a orientação craniocaudal do paciente e a curvatura da arcada dentária no volume, determinando a polaridade coroa-ápice para a maxila e para a mandíbula.

3. **Tratamento Avançado de Dentes Multirradiculares:**
   - Não presume número fixo de raízes: analisa a geometria de cada dente individualmente.
   - Aplica propagação de distância geodésica 3D (`Fast Geodesic BFS`) a partir da porção coronária até as extremidades apicais.
   - Identifica bifurcações e trifurcações anatômicas através de análise de componentes conexos nas zonas apicais profundas.
   - Nomeação anatômica automatizada:
     - **Molares Superiores:** Mésio-Vestibular (`MV`), Disto-Vestibular (`DV`), Palatina (`P`).
     - **Molares Inferiores:** Mesial (`M`), Distal (`D`), Disto-Lingual / Radix (`DL`).
     - **Pré-Molares Superiores:** Vestibular (`V`), Palatina (`P`).

4. **Refinamento Geométrico por Estreitamento 3D (Tapering):**
   - Utiliza a Transformada de Distância Euclidiana 3D (`scipy.ndimage.distance_transform_edt`) para determinar o afunilamento progressivo da raiz e centralizar o ponto fiducial no lúmen apical, evitando bordas ou ruídos de segmentação.

5. **Integração Nativa com o 3D Slicer:**
   - Cria nós de fiduciais nativos (`vtkMRMLMarkupsFiducialNode`).
   - Permite interação direta: ao clicar em qualquer dente na tabela de resultados da extensão, os planos 2D (*Red, Yellow, Green*) e a câmera 3D centralizam automaticamente sobre o ápice selecionado.
   - Visualização com cores anatômicas (azul ciano para dentes superiores, laranja para dentes inferiores).
   - Edição manual direta posterior através das ferramentas convencionais do Slicer.

6. **Geração Automática de Superfície 3D:**
   - Reconstrói a representação de superfície fechada 3D (`Closed Surface Representation`) dos dentes para visualização espacial volumétrica.

7. **Exportação de Dados e Processamento em Lote:**
   - Exportação direta dos resultados com coordenadas físicas milimétricas (RAS) e de voxel (IJK) para arquivos `.CSV`.
   - Módulo de processamento em lote capaz de iterar sobre múltiplas tomografias do dataset e consolidar os dados estatísticos.

---

## 📁 Estrutura da Extensão

```text
DentalRootApexDetector/
├── CMakeLists.txt                    # Arquivo de configuração de build para o Slicer Extension Wizard
├── DentalRootApexDetector.py         # Código fonte completo (Módulo, Widget Qt, Lógica Algorítmica e Testes)
└── Resources/
    └── Icons/
        └── DentalRootApexDetector.png # Ícone oficial da extensão com estilização odontológica
```

---

## 🚀 Como Instalar e Usar no 3D Slicer

### Passo 1: Adicionar a Extensão ao 3D Slicer

1. Abra o **3D Slicer**.
2. Vá no menu principal em: **Edit** -> **Application Settings** -> **Modules**.
3. Na seção **Additional module paths**, clique em **Add** e selecione o diretório:
   `D:\ToothFairy2_Dataset\Dataset112_ToothFairy2\DentalRootApexDetector`
4. Clique em **OK** e reinicie o 3D Slicer (ou confirme para recarregar).
5. O módulo agora estará disponível na categoria **Dental** -> **Dental Root Apex Detector** (ou pesquisando por "Dental" na barra de busca de módulos `Ctrl + F`).

### Passo 2: Executar a Detecção

1. **Carregar o Dataset:**
   - Você pode carregar um arquivo `.mha` de `labelsTr/` diretamente arrastando para o 3D Slicer ou utilizando o botão **Carregar Arquivo do Disco** no próprio painel da extensão.
2. **Selecionar a Segmentação:**
   - Escolha o nó de segmentação ou labelmap no campo *Segmentação na cena*.
3. **Filtros Anatômicos (Opcional):**
   - Escolha processar *Todos os Dentes*, apenas a *Arcada Superior*, *Arcada Inferior*, ou insira números específicos (ex: `16, 26, 36, 46`).
4. **Executar:**
   - Clique no botão azul **"Identificar Ápices Radiculares Automaticamente"**.
5. **Visualizar e Validar:**
   - Os marcadores fiduciais aparecerão nas fatias 2D e na cena 3D.
   - Clique em qualquer linha na tabela inferior para navegar imediatamente até o ápice correspondente.
   - Exporte a planilha completa clicando em **Exportar Resultados (.CSV)**.

---

## 🧪 Validação dos Testes

O módulo foi testado e validado de ponta a ponta com o Python interno do 3D Slicer 5.12.3:
- Casos com dentes unirradiculares (incisivos, caninos): 100% de precisão de extremidade apical única.
- Casos com dentes multirradiculares (molares 16, 26 com 3 raízes e 36, 46 com 2 raízes): separação e rotulação anatômica exatas de cada canal radicular.
- Tempo de processamento médio: **~0.3 a 0.5 segundos por dente** em um volume completo de 512x512x262 voxels.
