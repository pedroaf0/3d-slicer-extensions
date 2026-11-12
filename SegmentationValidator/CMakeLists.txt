cmake_minimum_required(VERSION 3.16.3...3.28.2 FATAL_ERROR)

project(SegmentationValidator)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/SegmentationValidator")
set(EXTENSION_CONTRIBUTORS "Pedro (Developer)")
set(EXTENSION_DESCRIPTION "Validates nnU-Net training segmentations: navigates image/label pairs in imagesTr/labelsTr and imports the labels as segments for visual checking.")
set(EXTENSION_ICONURL "")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(SegmentationValidator)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
