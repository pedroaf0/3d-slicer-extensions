cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(DentalRootApexDetector)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/pedro/DentalRootApexDetector")
set(EXTENSION_CATEGORY "Dental")
set(EXTENSION_CONTRIBUTORS "Pediatric & Maxillofacial AI Research / Antigravity")
set(EXTENSION_DESCRIPTION "Automatic detection of dental root apices from 3D CBCT tooth segmentations with native 3D Slicer Markups fiducial placement.")
set(EXTENSION_ICONURL "")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "NA-MIC/Slicer") # Built-in Markups and Segmentations
set(EXTENSION_BUILD_SUBDIRECTORY ".")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(DentalRootApexDetector)

#-----------------------------------------------------------------------------
# Extension packaging
include(${Slicer_EXTENSION_CPACK})
