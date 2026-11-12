cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(ToothFairySegmentationLoader)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/pedro/ToothFairySegmentationLoader")
set(EXTENSION_CATEGORY "Dental")
set(EXTENSION_CONTRIBUTORS "Pediatric & Maxillofacial AI Research / Antigravity")
set(EXTENSION_DESCRIPTION "Loads ToothFairy2 3D dental segmentations (.mha) directly as multi-segment Segmentation nodes with proper anatomical names, colors, and FDI teeth classification from dataset.json.")
set(EXTENSION_ICONURL "")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "NA-MIC/Slicer")
set(EXTENSION_BUILD_SUBDIRECTORY ".")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(ToothFairySegmentationLoader)

#-----------------------------------------------------------------------------
# Extension packaging
include(${Slicer_EXTENSION_CPACK})
