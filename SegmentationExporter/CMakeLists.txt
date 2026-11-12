cmake_minimum_required(VERSION 3.16.3...3.28.2 FATAL_ERROR)

project(SegmentationExporter)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/SegmentationExporter")
set(EXTENSION_CONTRIBUTORS "Pedro (Developer)")
set(EXTENSION_DESCRIPTION "Exports a volume and a segment (as labelmap) into the imagesTr/labelsTr folders of an nnU-Net dataset for segmentation training.")
set(EXTENSION_ICONURL "")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(SegmentationExporter)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})