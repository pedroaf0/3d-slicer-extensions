cmake_minimum_required(VERSION 3.16.3...3.28.2 FATAL_ERROR)

project(BinarySegmentationExporter)

set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/BinarySegmentationExporter")
set(EXTENSION_CONTRIBUTORS "Pedro (Developer)")
set(EXTENSION_DESCRIPTION "Exports a segmentation as a single binary NIfTI (nii.gz) labelmap (0=background, 1=union of all segments). All segments are merged with OR into one 0/1 volume.")
set(EXTENSION_ICONURL "")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "NA")

find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

add_subdirectory(BinarySegmentationExporter)

include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
