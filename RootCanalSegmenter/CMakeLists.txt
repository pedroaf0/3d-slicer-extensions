cmake_minimum_required(VERSION 3.16.3...3.28.2 FATAL_ERROR)

project(RootCanalSegmenter)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/RootCanalSegmenter")
set(EXTENSION_CONTRIBUTORS "Pedro Afonso (Developer)")
set(EXTENSION_DESCRIPTION "Segmentacao do canal radicular a partir da segmentacao do dente: selecao de um intervalo de valores hipodensos dentro do dente, com histograma, sugestao automatica de faixa, preview, pos-processamento e region growing restrito.")
set(EXTENSION_ICONURL "")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(RootCanalSegmenter)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
