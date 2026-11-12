cmake_minimum_required(VERSION 3.16.3...3.28.2 FATAL_ERROR)

project(MultiChannelSegmentationExporter)

set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/MultiChannelSegmentationExporter")
set(EXTENSION_CONTRIBUTORS "Pedro (Developer)")
set(EXTENSION_DESCRIPTION "Exports a segmentation as a multichannel NIfTI (nii.gz) labelmap, allowing the user to assign each segment to a specific channel.")
set(EXTENSION_ICONURL "")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "NA")

find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

add_subdirectory(MultiChannelSegmentationExporter)

include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
