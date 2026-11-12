cmake_minimum_required(VERSION 3.16.3...3.28.2 FATAL_ERROR)

project(VolumeIntensityModifier)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/VolumeIntensityModifier")
set(EXTENSION_CONTRIBUTORS "Pedro Afonso (Developer)")
set(EXTENSION_DESCRIPTION "Tools for creating synthetic medical imaging cases. VolumeModification applies configurable intensity patterns to a volume using a segmentation mask. SphereSegmentation creates a sphere-shaped segment with 3D preview and applies it to a segmentation.")
set(EXTENSION_ICONURL "")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "NA")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(VolumeModification)
add_subdirectory(SphereSegmentation)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})