cmake_minimum_required(VERSION 3.16.3...3.28.2 FATAL_ERROR)

project(SegmentationBooleanDifference)

set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/SegmentationBooleanDifference")
set(EXTENSION_CONTRIBUTORS "Pedro (Developer)")
set(EXTENSION_DESCRIPTION "Performs boolean difference (A \\ B) between two segments, even from different segmentations, removing from A the voxels that belong to B.")
set(EXTENSION_ICONURL "")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "NA")

find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

add_subdirectory(SegmentationBooleanDifference)

include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
