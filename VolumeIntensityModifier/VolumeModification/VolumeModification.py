import logging
import json
import os
import traceback

import numpy as np

import ctk
import qt
import vtk

import slicer
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
)
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

try:
    from scipy import ndimage as ndi
    HAVE_SCIPY = True
except ImportError:
    ndi = None
    HAVE_SCIPY = False


# =============================================================================
# Intensity patterns
#
# Each pattern is a small, self-contained component:
#   - apply()                : pure array operation (no MRML side effects)
#   - createParameterWidgets : builds the controls for its own parameters
#   - readParameters         : reads parameter values from those controls
#
# Adding a new pattern means adding one class and registering it at the bottom
# of this section. The widget does not need to know anything about it.
# =============================================================================

# -----------------------------------------------------------------------------
# Memory-bounded helpers
#
# Large volumes (for example 641x641x641) cannot be converted to float64 as a
# whole: one such array is ~2 GB. Patterns therefore write results in small
# blocks and never allocate a full-volume floating point copy.
# -----------------------------------------------------------------------------

def _maskBoundingBox(mask):
    """Return (k0, k1, j0, j1, i0, i1) for the mask, or None if empty."""
    kIndices = np.flatnonzero(np.any(mask, axis=(1, 2)))
    jIndices = np.flatnonzero(np.any(mask, axis=(0, 2)))
    iIndices = np.flatnonzero(np.any(mask, axis=(0, 1)))
    if kIndices.size == 0 or jIndices.size == 0 or iIndices.size == 0:
        return None
    return (
        int(kIndices[0]), int(kIndices[-1]) + 1,
        int(jIndices[0]), int(jIndices[-1]) + 1,
        int(iIndices[0]), int(iIndices[-1]) + 1,
    )


def _maskCenter(mask):
    """Return the mean (i, j, k) position of mask voxels without np.where."""
    count = int(np.count_nonzero(mask))
    if count == 0:
        return 0.0, 0.0, 0.0
    iCounts = np.count_nonzero(mask, axis=(0, 1))
    jCounts = np.count_nonzero(mask, axis=(0, 2))
    kCounts = np.count_nonzero(mask, axis=(1, 2))
    centerI = float(np.dot(np.arange(mask.shape[2], dtype=np.float64), iCounts) / count)
    centerJ = float(np.dot(np.arange(mask.shape[1], dtype=np.float64), jCounts) / count)
    centerK = float(np.dot(np.arange(mask.shape[0], dtype=np.float64), kCounts) / count)
    return centerI, centerJ, centerK


def _iterBlocks(bbox, targetVoxels=1000000):
    """Yield small z-slab bounding boxes covering bbox."""
    k0, k1, j0, j1, i0, i1 = bbox
    sliceVoxels = max(1, (j1 - j0) * (i1 - i0))
    blockDepth = max(1, int(targetVoxels // sliceVoxels))
    for blockK0 in range(k0, k1, blockDepth):
        yield blockK0, min(k1, blockK0 + blockDepth), j0, j1, i0, i1


def _distanceSquaredBlock(block, center, spacing):
    """Squared physical distances from center for one block."""
    k0, k1, j0, j1, i0, i1 = block
    centerI, centerJ, centerK = center
    ii = np.arange(i0, i1, dtype=np.float64)[None, None, :]
    jj = np.arange(j0, j1, dtype=np.float64)[None, :, None]
    kk = np.arange(k0, k1, dtype=np.float64)[:, None, None]
    di = (ii - centerI) * float(spacing[0])
    dj = (jj - centerJ) * float(spacing[1])
    dk = (kk - centerK) * float(spacing[2])
    return di * di + dj * dj + dk * dk


def _clipValuesToDtype(values, dtype):
    """Clip block values in place to the destination dtype range."""
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        np.clip(values, info.min, info.max, out=values)
    elif np.issubdtype(dtype, np.floating):
        info = np.finfo(dtype)
        np.clip(values, info.min, info.max, out=values)
    return values


def _clipScalarToDtype(value, dtype):
    value = float(value)
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        return min(max(value, float(info.min)), float(info.max))
    if np.issubdtype(dtype, np.floating):
        info = np.finfo(dtype)
        return min(max(value, float(info.min)), float(info.max))
    return value


# A float64 distance transform for a 32-million-voxel bounding box already
# needs about 256 MB. Keep the same safety limit used by the original
# radiolucent pattern for all patterns that need a boundary distance map.
_MAX_DISTANCE_BBOX_VOXELS = 32000000


def _distanceToMaskBoundary(mask, volumeNode, patternName):
    """Return (bbox, distance to the mask boundary in mm).

    The distance is computed inside the mask bounding box only, with one
    background voxel of padding so bounding-box faces are not mistaken for
    the segment surface.
    """
    if not HAVE_SCIPY:
        raise RuntimeError(
            "The {} pattern requires SciPy. Install it with: pip install scipy"
            .format(patternName)
        )

    bbox = _maskBoundingBox(mask)
    if bbox is None:
        return None, None

    k0, k1, j0, j1, i0, i1 = bbox
    bboxVoxels = (k1 - k0) * (j1 - j0) * (i1 - i0)
    if bboxVoxels > _MAX_DISTANCE_BBOX_VOXELS:
        raise RuntimeError(
            "The selected region is too large for the {} pattern "
            "({} voxels in its bounding box). Reduce the segment or use "
            "another pattern.".format(patternName, bboxVoxels)
        )

    maskBBox = mask[k0:k1, j0:j1, i0:i1]
    spacing = volumeNode.GetSpacing()
    # Mask axes are (Z, Y, X), while spacing is (X, Y, Z).
    sampling = (float(spacing[2]), float(spacing[1]), float(spacing[0]))
    paddedMask = np.pad(maskBBox, 1, mode="constant", constant_values=False)
    distance = ndi.distance_transform_edt(paddedMask, sampling=sampling)
    return bbox, distance[1:-1, 1:-1, 1:-1]


def _sampleMaskedValues(source, mask, bbox, maxSamples=1000000):
    """Return an evenly spaced, bounded sample of values inside the mask.

    Sampling avoids allocating a full masked copy of a large volume while
    still giving representative percentiles for the local reference.
    """
    blocks = list(_iterBlocks(bbox))
    counts = []
    total = 0
    for block in blocks:
        k0, k1, j0, j1, i0, i1 = block
        count = int(np.count_nonzero(mask[k0:k1, j0:j1, i0:i1]))
        counts.append(count)
        total += count

    if total == 0:
        return np.empty(0, dtype=source.dtype)

    sampleCount = min(total, maxSamples)
    step = 1 if total <= maxSamples else int(np.ceil(total / float(maxSamples)))
    samples = np.empty(sampleCount, dtype=source.dtype)
    offset = 0
    globalCount = 0

    for block, count in zip(blocks, counts):
        if count == 0:
            continue
        k0, k1, j0, j1, i0, i1 = block
        blockMask = mask[k0:k1, j0:j1, i0:i1]
        values = source[k0:k1, j0:j1, i0:i1][blockMask]

        # Select every step-th masked voxel across the whole bounding box.
        first = (-globalCount) % step
        chosen = values[first::step]
        if offset + chosen.size > sampleCount:
            chosen = chosen[:sampleCount - offset]
        samples[offset:offset + chosen.size] = chosen
        offset += chosen.size
        globalCount += count

    return samples[:offset]


def _localReferenceStatistics(source, mask, bbox, volumeNode):
    """Return P10, P50, P90, spread, and a bounded sample of local values."""
    sample = _sampleMaskedValues(source, mask, bbox)
    if sample.size == 0:
        raise RuntimeError("The selected region contains no voxels.")

    values = sample.astype(np.float64, copy=False)
    p10, p50, p90 = np.percentile(values, [10.0, 50.0, 90.0])
    p10 = float(p10)
    p50 = float(p50)
    p90 = float(p90)
    spread = p90 - p10

    if not np.isfinite(spread) or spread <= 0.0:
        # A perfectly homogeneous region has no local dynamic range. Use a
        # conservative fallback so the pattern still has visible contrast.
        try:
            scalarMin, scalarMax = volumeNode.GetImageData().GetScalarRange()
            fallback = 0.1 * (float(scalarMax) - float(scalarMin))
        except Exception:
            fallback = 0.0
        fallback = max(fallback, 0.1 * abs(p50), 1.0)
        p10 = p50 - 0.5 * fallback
        p90 = p50 + 0.5 * fallback
        spread = fallback

    return p10, p50, p90, spread, sample


def _blockNoise(block, seed, count):
    """Return deterministic pseudo-random values for one block."""
    k0, k1, j0, j1, i0, i1 = block
    blockSeed = (
        int(seed) * 6364136223846793005
        + k0 * 1442695040888963407
        + j0 * 14029467366897019727
        + i0 * 1609587929392839161
    ) & 0xFFFFFFFFFFFFFFFF
    generator = np.random.default_rng(blockSeed)
    return generator.random(count)


class IntensityPattern:
    id = "base"
    name = "Base"
    description = ""
    usesVolumeRange = True

    def writeValues(self, output, source, mask, volumeNode, parameters):
        """Write modified values into output, without copying the volume."""
        raise NotImplementedError

    def apply(self, volumeArray, mask, volumeNode, parameters):
        """Return a modified copy (used by tests and external callers)."""
        result = volumeArray.copy()
        self.writeValues(result, volumeArray, mask, volumeNode, parameters)
        return result

    def createParameterWidgets(self, form, refs):
        """Create parameter widgets into a QFormLayout."""
        raise NotImplementedError

    def readParameters(self, refs):
        """Return a dictionary of parameters from the created widgets."""
        raise NotImplementedError


class UniformPattern(IntensityPattern):
    id = "uniform"
    name = "Uniform radiopacity"
    description = (
        "Sets every voxel of the selected region to one constant intensity. "
        "Useful for simulating radiopaque material such as endodontic filling."
    )

    def writeValues(self, output, source, mask, volumeNode, parameters):
        value = _clipScalarToDtype(
            parameters.get("intensity", 3000.0), output.dtype
        )
        output[mask] = value

    def createParameterWidgets(self, form, refs):
        spin = qt.QDoubleSpinBox()
        spin.minimum = -1000000.0
        spin.maximum = 1000000.0
        spin.decimals = 2
        spin.singleStep = 50.0
        spin.value = 3000.0
        spin.toolTip = "Intensity assigned to all voxels inside the region."
        form.addRow(_("Intensity:"), spin)
        refs["intensity"] = spin

    def readParameters(self, refs):
        return {"intensity": float(refs["intensity"].value)}


class RadialFalloffPattern(IntensityPattern):
    id = "radial"
    name = "Radial intensity falloff"
    description = (
        "Applies a high intensity at the geometric center of the region that "
        "gradually decreases toward its boundary. Distances respect image spacing."
    )

    def writeValues(self, output, source, mask, volumeNode, parameters):
        count = int(np.count_nonzero(mask))
        if count == 0:
            return

        centerIntensity = float(parameters.get("centerIntensity", 3000.0))
        edgeIntensity = float(parameters.get("edgeIntensity", 500.0))
        power = max(0.1, float(parameters.get("falloffPower", 2.0)))

        center = _maskCenter(mask)
        bbox = _maskBoundingBox(mask)
        if bbox is None:
            return
        spacing = volumeNode.GetSpacing()

        # First pass: maximum distance from the mask center. This avoids
        # storing distances for the whole volume.
        maxDistanceSquared = 0.0
        for block in _iterBlocks(bbox):
            k0, k1, j0, j1, i0, i1 = block
            blockMask = mask[k0:k1, j0:j1, i0:i1]
            if not np.any(blockMask):
                continue
            distancesSquared = _distanceSquaredBlock(block, center, spacing)
            maxDistanceSquared = max(
                maxDistanceSquared, float(np.max(distancesSquared[blockMask]))
            )

        if maxDistanceSquared <= 0.0:
            output[mask] = _clipScalarToDtype(centerIntensity, output.dtype)
            return

        maxDistance = float(np.sqrt(maxDistanceSquared))
        for block in _iterBlocks(bbox):
            k0, k1, j0, j1, i0, i1 = block
            blockMask = mask[k0:k1, j0:j1, i0:i1]
            if not np.any(blockMask):
                continue
            distances = np.sqrt(_distanceSquaredBlock(block, center, spacing))
            maskedDistances = distances[blockMask]
            t = np.power(maskedDistances / maxDistance, power)
            values = centerIntensity + (edgeIntensity - centerIntensity) * t
            values = _clipValuesToDtype(values, output.dtype)
            output[k0:k1, j0:j1, i0:i1][blockMask] = values

    def createParameterWidgets(self, form, refs):
        center = qt.QDoubleSpinBox()
        center.minimum = -1000000.0
        center.maximum = 1000000.0
        center.decimals = 2
        center.singleStep = 50.0
        center.value = 3000.0
        center.toolTip = "Intensity at the center of the region."
        form.addRow(_("Center intensity:"), center)
        refs["centerIntensity"] = center

        edge = qt.QDoubleSpinBox()
        edge.minimum = -1000000.0
        edge.maximum = 1000000.0
        edge.decimals = 2
        edge.singleStep = 50.0
        edge.value = 500.0
        edge.toolTip = "Intensity at the outer boundary of the region."
        form.addRow(_("Edge intensity:"), edge)
        refs["edgeIntensity"] = edge

        power = qt.QDoubleSpinBox()
        power.minimum = 0.1
        power.maximum = 8.0
        power.decimals = 2
        power.singleStep = 0.1
        power.value = 2.0
        power.toolTip = "Falloff shape: 1 = linear, 2 = quadratic, higher = sharper center."
        form.addRow(_("Falloff power:"), power)
        refs["falloffPower"] = power

    def readParameters(self, refs):
        return {
            "centerIntensity": float(refs["centerIntensity"].value),
            "edgeIntensity": float(refs["edgeIntensity"].value),
            "falloffPower": float(refs["falloffPower"].value),
        }


class RadiolucentLesionPattern(IntensityPattern):
    id = "radiolucent"
    name = "Radiolucent lesion with radiopaque border"
    description = (
        "Creates a low-intensity core surrounded by a high-intensity rim, "
        "simulating a well-defined radiolucent lesion. Requires SciPy."
    )

    def writeValues(self, output, source, mask, volumeNode, parameters):
        if not np.any(mask):
            return

        centerIntensity = float(parameters.get("centerIntensity", -500.0))
        borderIntensity = float(parameters.get("borderIntensity", 3000.0))
        borderThickness = max(0.0, float(parameters.get("borderThickness", 1.0)))
        transitionWidth = max(0.0, float(parameters.get("transitionWidth", 0.5)))

        bbox, distance = _distanceToMaskBoundary(
            mask, volumeNode, "radiolucent lesion"
        )
        if bbox is None:
            return
        k0, k1, j0, j1, i0, i1 = bbox
        maskBBox = mask[k0:k1, j0:j1, i0:i1]

        for block in _iterBlocks(bbox):
            blockK0, blockK1, blockJ0, blockJ1, blockI0, blockI1 = block
            localK0 = blockK0 - k0
            localK1 = blockK1 - k0
            localJ0 = blockJ0 - j0
            localJ1 = blockJ1 - j0
            localI0 = blockI0 - i0
            localI1 = blockI1 - i0

            blockMask = maskBBox[localK0:localK1, localJ0:localJ1, localI0:localI1]
            if not np.any(blockMask):
                continue
            blockDistance = distance[
                localK0:localK1, localJ0:localJ1, localI0:localI1
            ]
            maskedDistance = blockDistance[blockMask]

            values = np.empty(maskedDistance.shape, dtype=np.float64)
            rim = maskedDistance <= borderThickness
            core = maskedDistance > borderThickness + transitionWidth
            transition = ~rim & ~core

            if np.any(rim):
                values[rim] = borderIntensity
            if np.any(core):
                values[core] = centerIntensity
            if np.any(transition):
                if transitionWidth > 0.0:
                    t = (maskedDistance[transition] - borderThickness) / transitionWidth
                    t = np.clip(t, 0.0, 1.0)
                else:
                    t = np.ones(np.count_nonzero(transition), dtype=np.float64)
                values[transition] = (
                    borderIntensity + (centerIntensity - borderIntensity) * t
                )

            values = _clipValuesToDtype(values, output.dtype)
            output[blockK0:blockK1, blockJ0:blockJ1, blockI0:blockI1][blockMask] = values

    def createParameterWidgets(self, form, refs):
        center = qt.QDoubleSpinBox()
        center.minimum = -1000000.0
        center.maximum = 1000000.0
        center.decimals = 2
        center.singleStep = 50.0
        center.value = -500.0
        center.toolTip = "Intensity of the radiolucent core."
        form.addRow(_("Core intensity:"), center)
        refs["centerIntensity"] = center

        border = qt.QDoubleSpinBox()
        border.minimum = -1000000.0
        border.maximum = 1000000.0
        border.decimals = 2
        border.singleStep = 50.0
        border.value = 3000.0
        border.toolTip = "Intensity of the radiopaque rim."
        form.addRow(_("Border intensity:"), border)
        refs["borderIntensity"] = border

        thickness = qt.QDoubleSpinBox()
        thickness.minimum = 0.0
        thickness.maximum = 100.0
        thickness.decimals = 2
        thickness.singleStep = 0.1
        thickness.value = 1.0
        thickness.toolTip = "Thickness of the high-intensity rim, in millimeters."
        form.addRow(_("Border thickness (mm):"), thickness)
        refs["borderThickness"] = thickness

        transition = qt.QDoubleSpinBox()
        transition.minimum = 0.0
        transition.maximum = 50.0
        transition.decimals = 2
        transition.singleStep = 0.1
        transition.value = 0.5
        transition.toolTip = (
            "Width of the blend between the rim and the core, in millimeters. "
            "Set to 0 for a hard edge."
        )
        form.addRow(_("Transition width (mm):"), transition)
        refs["transitionWidth"] = transition

    def readParameters(self, refs):
        return {
            "centerIntensity": float(refs["centerIntensity"].value),
            "borderIntensity": float(refs["borderIntensity"].value),
            "borderThickness": float(refs["borderThickness"].value),
            "transitionWidth": float(refs["transitionWidth"].value),
        }


class PeriapicalLesionPatternBase(IntensityPattern):
    """Relative periapical lesion patterns for CBCT-like gray values.

    These patterns deliberately avoid absolute HU thresholds. The original
    intensities inside the selected segment are used as the local reference,
    so the segment should be drawn over the bone region that will be replaced.
    Any sclerotic halo is created inside the segment's outer edge.
    """

    usesVolumeRange = False

    defaultCoreDarkening = 10.0
    defaultHeterogeneity = 10.0
    defaultResidualTrabeculae = 8.0
    defaultHaloThickness = 0.0
    defaultHaloBoost = 25.0
    defaultMarginTransition = 1.5
    defaultTextureSeed = 1

    def writeValues(self, output, source, mask, volumeNode, parameters):
        if not np.any(mask):
            return

        coreDarkening = max(
            0.0, float(parameters.get("coreDarkening", self.defaultCoreDarkening))
        )
        heterogeneity = min(
            100.0,
            max(0.0, float(parameters.get("heterogeneity", self.defaultHeterogeneity))),
        )
        residualPercent = min(
            50.0,
            max(
                0.0,
                float(parameters.get(
                    "residualTrabeculae", self.defaultResidualTrabeculae
                )),
            ),
        )
        haloThickness = max(
            0.0, float(parameters.get("haloThickness", self.defaultHaloThickness))
        )
        haloBoost = max(
            0.0, float(parameters.get("haloBoost", self.defaultHaloBoost))
        )
        marginTransition = max(
            0.0,
            float(parameters.get("marginTransition", self.defaultMarginTransition)),
        )
        textureSeed = int(parameters.get("textureSeed", self.defaultTextureSeed))

        bbox, distance = _distanceToMaskBoundary(mask, volumeNode, self.name)
        if bbox is None:
            return

        p10, p50, p90, spread, referenceSample = _localReferenceStatistics(
            source, mask, bbox, volumeNode
        )
        coreIntensity = p10 - (coreDarkening / 100.0) * spread
        haloIntensity = p90 + (haloBoost / 100.0) * spread
        noiseAmplitude = (heterogeneity / 100.0) * spread

        if residualPercent > 0.0:
            residualThreshold = float(
                np.percentile(referenceSample, 100.0 - residualPercent)
            )
        else:
            residualThreshold = None
        del referenceSample

        k0, k1, j0, j1, i0, i1 = bbox
        maskBBox = mask[k0:k1, j0:j1, i0:i1]

        for block in _iterBlocks(bbox):
            blockK0, blockK1, blockJ0, blockJ1, blockI0, blockI1 = block
            localK0 = blockK0 - k0
            localK1 = blockK1 - k0
            localJ0 = blockJ0 - j0
            localJ1 = blockJ1 - j0
            localI0 = blockI0 - i0
            localI1 = blockI1 - i0

            blockMask = maskBBox[localK0:localK1, localJ0:localJ1, localI0:localI1]
            if not np.any(blockMask):
                continue

            blockDistance = distance[
                localK0:localK1, localJ0:localJ1, localI0:localI1
            ]
            maskedDistance = blockDistance[blockMask]
            sourceValues = source[
                blockK0:blockK1, blockJ0:blockJ1, blockI0:blockI1
            ][blockMask].astype(np.float64, copy=False)

            # Sclerotic rim weight: 1 at the outer edge, fading to 0 toward the
            # core over the same margin-transition width. With no rim, the
            # whole segment is core.
            rimWeight = np.zeros_like(maskedDistance)
            if haloThickness > 0.0:
                rimWeight[maskedDistance <= haloThickness] = 1.0
                if marginTransition > 0.0:
                    inTransition = (
                        (maskedDistance > haloThickness)
                        & (maskedDistance < haloThickness + marginTransition)
                    )
                    rimWeight[inTransition] = 1.0 - (
                        (maskedDistance[inTransition] - haloThickness)
                        / marginTransition
                    )

            values = coreIntensity + (
                haloIntensity - coreIntensity
            ) * rimWeight

            # Deterministic texture. The rim receives less texture than the
            # core because mineralized reactive bone is more homogeneous.
            if noiseAmplitude > 0.0:
                noise = _blockNoise(block, textureSeed, maskedDistance.size)
                textureAmplitude = noiseAmplitude * (1.0 - 0.8 * rimWeight)
                values += (noise - 0.5) * 2.0 * textureAmplitude

            # Retain the brightest original voxels as residual trabeculae.
            # This reuses the original anatomy instead of drawing random
            # bright speckles.
            if residualThreshold is not None:
                residual = (
                    (sourceValues >= residualThreshold)
                    & (rimWeight < 0.5)
                )
                if np.any(residual):
                    values[residual] = sourceValues[residual]

            # Partial-volume blend at the outer boundary. This makes an
            # ill-defined lesion fade into bone, while a small value keeps a
            # well-defined lesion crisp.
            if marginTransition > 0.0:
                edgeWeight = np.clip(maskedDistance / marginTransition, 0.0, 1.0)
            else:
                edgeWeight = 1.0
            values = sourceValues + (values - sourceValues) * edgeWeight

            values = _clipValuesToDtype(values, output.dtype)
            output[
                blockK0:blockK1, blockJ0:blockJ1, blockI0:blockI1
            ][blockMask] = values

    def createParameterWidgets(self, form, refs):
        note = qt.QLabel(
            _("Relative pattern: the original intensities inside the segment "
              "are the local reference. No absolute HU threshold is assumed. "
              "Draw the segment over the bone to replace; any sclerotic rim "
              "is created inside the segment's outer edge. Keep root, "
              "endodontic material, and obvious streak artifacts outside "
              "the segment.")
        )
        note.wordWrap = True
        note.setStyleSheet("color: #666; font-size: 8pt;")
        form.addRow(note)

        core = qt.QDoubleSpinBox()
        core.minimum = 0.0
        core.maximum = 200.0
        core.decimals = 1
        core.singleStep = 5.0
        core.value = self.defaultCoreDarkening
        core.toolTip = (
            "Core intensity below the local P10, as a percentage of the "
            "local P10-P90 range. Higher values make a darker lesion."
        )
        form.addRow(_("Core darkening (% local range):"), core)
        refs["coreDarkening"] = core

        heterogeneity = qt.QDoubleSpinBox()
        heterogeneity.minimum = 0.0
        heterogeneity.maximum = 100.0
        heterogeneity.decimals = 1
        heterogeneity.singleStep = 2.0
        heterogeneity.value = self.defaultHeterogeneity
        heterogeneity.toolTip = (
            "Amplitude of deterministic internal texture, as a percentage of "
            "the local P10-P90 range."
        )
        form.addRow(_("Heterogeneity:"), heterogeneity)
        refs["heterogeneity"] = heterogeneity

        residual = qt.QDoubleSpinBox()
        residual.minimum = 0.0
        residual.maximum = 50.0
        residual.decimals = 1
        residual.singleStep = 1.0
        residual.value = self.defaultResidualTrabeculae
        residual.toolTip = (
            "Approximate percentage of the brightest original voxels retained "
            "inside the core as residual trabeculae."
        )
        form.addRow(_("Residual trabeculae (%):"), residual)
        refs["residualTrabeculae"] = residual

        haloThickness = qt.QDoubleSpinBox()
        haloThickness.minimum = 0.0
        haloThickness.maximum = 20.0
        haloThickness.decimals = 2
        haloThickness.singleStep = 0.1
        haloThickness.value = self.defaultHaloThickness
        haloThickness.toolTip = (
            "Thickness of the reactive rim inside the segment's outer edge, "
            "in millimeters. Set to 0 for no rim."
        )
        form.addRow(_("Halo thickness (mm):"), haloThickness)
        refs["haloThickness"] = haloThickness

        haloBoost = qt.QDoubleSpinBox()
        haloBoost.minimum = 0.0
        haloBoost.maximum = 200.0
        haloBoost.decimals = 1
        haloBoost.singleStep = 5.0
        haloBoost.value = self.defaultHaloBoost
        haloBoost.toolTip = (
            "Halo intensity above the local P90, as a percentage of the "
            "local P10-P90 range. Used only when halo thickness is greater "
            "than 0."
        )
        form.addRow(_("Halo boost (% local range):"), haloBoost)
        refs["haloBoost"] = haloBoost

        margin = qt.QDoubleSpinBox()
        margin.minimum = 0.0
        margin.maximum = 20.0
        margin.decimals = 2
        margin.singleStep = 0.1
        margin.value = self.defaultMarginTransition
        margin.toolTip = (
            "Width of the partial-volume blend at the outer boundary and "
            "between the core and the halo, in millimeters. Set to 0 for a "
            "hard edge."
        )
        form.addRow(_("Margin transition (mm):"), margin)
        refs["marginTransition"] = margin

        seed = qt.QSpinBox()
        seed.minimum = 0
        seed.maximum = 1000000
        seed.value = self.defaultTextureSeed
        seed.toolTip = (
            "Seed for the deterministic internal texture. Preview and Apply "
            "use the same seed."
        )
        form.addRow(_("Texture seed:"), seed)
        refs["textureSeed"] = seed

    def readParameters(self, refs):
        return {
            "coreDarkening": float(refs["coreDarkening"].value),
            "heterogeneity": float(refs["heterogeneity"].value),
            "residualTrabeculae": float(refs["residualTrabeculae"].value),
            "haloThickness": float(refs["haloThickness"].value),
            "haloBoost": float(refs["haloBoost"].value),
            "marginTransition": float(refs["marginTransition"].value),
            "textureSeed": int(refs["textureSeed"].value),
        }


class PeriapicalInflammatoryPattern(PeriapicalLesionPatternBase):
    id = "periapical_inflammatory"
    name = "Periapical inflammatory lesion (relative)"
    description = (
        "Simulates an ill-defined inflammatory periapical hypodensity using "
        "the original voxels inside the segment as the local reference. The "
        "core is darker than the local P10, with heterogeneous texture, "
        "optional residual trabeculae, and a gradual margin. No absolute HU "
        "threshold is assumed. Requires SciPy. Educational simulation, not a "
        "diagnosis."
    )

    defaultCoreDarkening = 10.0
    defaultHeterogeneity = 12.0
    defaultResidualTrabeculae = 10.0
    defaultHaloThickness = 0.0
    defaultHaloBoost = 25.0
    defaultMarginTransition = 1.5


class PeriapicalScleroticHaloPattern(PeriapicalLesionPatternBase):
    id = "periapical_sclerotic_halo"
    name = "Periapical lesion with sclerotic halo (relative)"
    description = (
        "Simulates a well-defined periapical hypodensity with a reactive "
        "sclerotic rim. The rim is created inside the segment's outer edge, "
        "so draw the segment to include the intended halo. The halo represents "
        "reactive mineralized bone, not an epithelial lining. Intensities are "
        "relative to the local P10-P90 range, not absolute HU. Requires SciPy. "
        "Educational simulation, not a diagnosis."
    )

    defaultCoreDarkening = 20.0
    defaultHeterogeneity = 4.0
    defaultResidualTrabeculae = 0.0
    defaultHaloThickness = 0.8
    defaultHaloBoost = 40.0
    defaultMarginTransition = 0.4


class CustomPattern(IntensityPattern):
    id = "custom"
    name = "Custom blend"
    description = (
        "Blends the original intensity with a target intensity using a "
        "Gaussian, linear, or edge-weighted profile controlled by distance."
    )

    def writeValues(self, output, source, mask, volumeNode, parameters):
        count = int(np.count_nonzero(mask))
        if count == 0:
            return

        formula = str(parameters.get("formula", "gaussian"))
        targetIntensity = float(parameters.get("targetIntensity", 3000.0))
        sigma = max(0.01, float(parameters.get("sigma", 5.0)))

        center = _maskCenter(mask)
        bbox = _maskBoundingBox(mask)
        if bbox is None:
            return
        spacing = volumeNode.GetSpacing()

        maxDistance = None
        if formula in ("linear", "edge"):
            maxDistanceSquared = 0.0
            for block in _iterBlocks(bbox):
                k0, k1, j0, j1, i0, i1 = block
                blockMask = mask[k0:k1, j0:j1, i0:i1]
                if not np.any(blockMask):
                    continue
                distancesSquared = _distanceSquaredBlock(block, center, spacing)
                maxDistanceSquared = max(
                    maxDistanceSquared, float(np.max(distancesSquared[blockMask]))
                )
            maxDistance = float(np.sqrt(maxDistanceSquared))

        for block in _iterBlocks(bbox):
            k0, k1, j0, j1, i0, i1 = block
            blockMask = mask[k0:k1, j0:j1, i0:i1]
            if not np.any(blockMask):
                continue
            distances = np.sqrt(_distanceSquaredBlock(block, center, spacing))
            maskedDistances = distances[blockMask]
            original = source[k0:k1, j0:j1, i0:i1][blockMask].astype(np.float64)

            if formula == "gaussian":
                t = np.exp(
                    -(maskedDistances * maskedDistances) / (2.0 * sigma * sigma)
                )
            elif formula == "linear":
                if maxDistance is not None and maxDistance > 0.0:
                    t = 1.0 - maskedDistances / maxDistance
                else:
                    t = np.ones_like(maskedDistances)
            else:  # "edge"
                if maxDistance is not None and maxDistance > 0.0:
                    t = maskedDistances / maxDistance
                else:
                    t = np.zeros_like(maskedDistances)

            values = original + (targetIntensity - original) * np.clip(t, 0.0, 1.0)
            values = _clipValuesToDtype(values, output.dtype)
            output[k0:k1, j0:j1, i0:i1][blockMask] = values

    def createParameterWidgets(self, form, refs):
        formula = qt.QComboBox()
        formula.addItem(_("Gaussian blend"), "gaussian")
        formula.addItem(_("Linear blend"), "linear")
        formula.addItem(_("Edge-weighted blend"), "edge")
        formula.toolTip = "Distance profile used to blend the original and target intensities."
        form.addRow(_("Formula:"), formula)
        refs["formula"] = formula

        target = qt.QDoubleSpinBox()
        target.minimum = -1000000.0
        target.maximum = 1000000.0
        target.decimals = 2
        target.singleStep = 50.0
        target.value = 3000.0
        target.toolTip = "Target intensity at the center (Gaussian/linear) or at the edge (edge-weighted)."
        form.addRow(_("Target intensity:"), target)
        refs["targetIntensity"] = target

        sigma = qt.QDoubleSpinBox()
        sigma.minimum = 0.01
        sigma.maximum = 200.0
        sigma.decimals = 2
        sigma.singleStep = 0.5
        sigma.value = 5.0
        sigma.toolTip = "Gaussian sigma in millimeters (used by the Gaussian blend)."
        form.addRow(_("Sigma (mm):"), sigma)
        refs["sigma"] = sigma

    def readParameters(self, refs):
        return {
            "formula": str(refs["formula"].currentData),
            "targetIntensity": float(refs["targetIntensity"].value),
            "sigma": float(refs["sigma"].value),
        }


PATTERN_CLASSES = [
    UniformPattern,
    RadialFalloffPattern,
    RadiolucentLesionPattern,
    PeriapicalInflammatoryPattern,
    PeriapicalScleroticHaloPattern,
    CustomPattern,
]

_PATTERNS_BY_ID = {cls.id: cls for cls in PATTERN_CLASSES}


def getPattern(patternId):
    cls = _PATTERNS_BY_ID.get(patternId)
    if cls is None:
        cls = UniformPattern
    return cls()


def getAvailablePatterns():
    return [(cls.id, cls.name, cls.description) for cls in PATTERN_CLASSES]


# =============================================================================
# Logic
# =============================================================================

class VolumeModificationLogic(ScriptedLoadableModuleLogic):
    """Applies intensity patterns to volume voxels and keeps undo patches."""

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        # Each entry: volume ID, mask bounding box, packed mask, old values,
        # voxel count, and description.
        self.undoStack = []
        self.maxUndoEntries = 20

    # ------------------------------------------------------------------
    # Masks
    # ------------------------------------------------------------------
    def getSegmentMaskArray(self, segmentationNode, segmentId, volumeNode):
        """Return a boolean mask (Z, Y, X) for a segment aligned to volumeNode."""
        if segmentationNode is None:
            raise ValueError("No segmentation selected.")
        if not segmentId:
            raise ValueError("No segment selected.")
        if volumeNode is None:
            raise ValueError("No reference volume selected.")

        segmentation = segmentationNode.GetSegmentation()
        if segmentation is None or segmentation.GetSegment(segmentId) is None:
            raise ValueError("Segment not found: {}".format(segmentId))

        volumeArray = slicer.util.arrayFromVolume(volumeNode)
        if volumeArray is None:
            raise RuntimeError("Could not read the selected volume.")

        try:
            segmentation.CreateRepresentation("Binary labelmap")
        except Exception:
            pass

        # Preferred API: direct binary labelmap extraction.
        if hasattr(slicer.util, "arrayFromSegmentBinaryLabelmap"):
            try:
                segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(
                    segmentationNode, segmentId, volumeNode
                )
                if segmentArray is not None:
                    mask = np.asarray(segmentArray) > 0
                    if mask.shape != volumeArray.shape:
                        raise RuntimeError(
                            "Segment mask shape {} does not match volume shape {}. "
                            "Check that the segmentation and volume use the same geometry."
                            .format(mask.shape, volumeArray.shape)
                        )
                    return mask
            except Exception as exc:
                logging.warning("arrayFromSegmentBinaryLabelmap failed: %s", exc)

        # Fallback: temporary labelmap export.
        labelmapNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLabelMapVolumeNode", "_VolumeModification_mask"
        )
        try:
            segmentIds = vtk.vtkStringArray()
            segmentIds.InsertNextValue(segmentId)
            exportLogic = slicer.modules.segmentations.logic()
            if not exportLogic.ExportSegmentsToLabelmapNode(
                segmentationNode, segmentIds, labelmapNode, volumeNode
            ):
                raise RuntimeError("Failed to export the segment to a labelmap.")
            exportedArray = slicer.util.arrayFromVolume(labelmapNode)
            if exportedArray is None:
                raise RuntimeError("Exported labelmap is empty.")
            mask = np.asarray(exportedArray) > 0
            if mask.shape != volumeArray.shape:
                raise RuntimeError(
                    "Exported mask shape {} does not match volume shape {}."
                    .format(mask.shape, volumeArray.shape)
                )
            return mask
        finally:
            slicer.mrmlScene.RemoveNode(labelmapNode)

    # ------------------------------------------------------------------
    # Computation / application
    # ------------------------------------------------------------------
    def _prepareMask(self, volumeNode, mask):
        """Validate inputs and return (volumeArray, boolMask, voxelCount)."""
        if volumeNode is None:
            raise ValueError("No volume selected.")
        volumeArray = slicer.util.arrayFromVolume(volumeNode)
        if volumeArray is None:
            raise RuntimeError("Could not read the selected volume.")

        mask = np.asarray(mask, dtype=bool)
        if mask.shape != volumeArray.shape:
            raise RuntimeError(
                "Mask shape {} does not match volume shape {}."
                .format(mask.shape, volumeArray.shape)
            )
        count = int(np.count_nonzero(mask))
        if count == 0:
            raise RuntimeError("The selected region contains no voxels.")
        return volumeArray, mask, count

    def _notifyVolumeModified(self, volumeNode):
        """Notify Slicer after modifying a volume array in place."""
        try:
            if hasattr(slicer.util, "arrayFromVolumeModified"):
                slicer.util.arrayFromVolumeModified(volumeNode)
                return
        except Exception:
            pass
        try:
            imageData = volumeNode.GetImageData()
            if imageData is not None:
                imageData.Modified()
            volumeNode.Modified()
        except Exception:
            pass

    def computeModifiedArray(self, volumeNode, mask, pattern, parameters):
        """Return (modifiedArray, voxelCount) without touching the volume."""
        volumeArray, mask, count = self._prepareMask(volumeNode, mask)

        # One copy in the volume's native dtype (not float64).
        modified = volumeArray.copy()
        pattern.writeValues(modified, volumeArray, mask, volumeNode, parameters)
        return modified, count

    def computeModifiedImageData(self, volumeNode, mask, pattern, parameters):
        """Return (vtkImageData, voxelCount) for preview, with one copy only."""
        volumeArray, mask, count = self._prepareMask(volumeNode, mask)

        imageData = vtk.vtkImageData()
        imageData.DeepCopy(volumeNode.GetImageData())

        from vtk.util import numpy_support

        scalars = imageData.GetPointData().GetScalars()
        if scalars is None:
            raise RuntimeError("The selected volume has no scalar data.")
        output = numpy_support.vtk_to_numpy(scalars)
        dimensions = tuple(int(value) for value in imageData.GetDimensions())
        expectedSize = dimensions[0] * dimensions[1] * dimensions[2]
        if output.size != expectedSize:
            raise RuntimeError("Only single-component scalar volumes are supported.")
        output = output.reshape(tuple(reversed(dimensions)))

        pattern.writeValues(output, volumeArray, mask, volumeNode, parameters)
        return imageData, count

    def _createUndoPatch(self, volumeNode, volumeArray, mask, count, description):
        """Store only the mask bounding box and old values of masked voxels."""
        bbox = _maskBoundingBox(mask)
        if bbox is None:
            raise RuntimeError("The selected region contains no voxels.")
        k0, k1, j0, j1, i0, i1 = bbox
        maskBBox = mask[k0:k1, j0:j1, i0:i1]
        return {
            "volumeID": volumeNode.GetID(),
            "shape": tuple(volumeArray.shape),
            "bbox": bbox,
            "bboxShape": tuple(maskBBox.shape),
            # packbits uses about one byte per 8 voxels instead of 3 int64
            # coordinate arrays per masked voxel.
            "packedMask": np.packbits(maskBBox, axis=None),
            # Boolean indexing already returns a new array; do not copy twice.
            "values": volumeArray[k0:k1, j0:j1, i0:i1][maskBBox],
            "count": count,
            "description": description,
        }

    def _restoreUndoPatch(self, volumeNode, volumeArray, entry):
        """Restore a patch in place. Return True on success."""
        if tuple(volumeArray.shape) != tuple(entry["shape"]):
            return False

        k0, k1, j0, j1, i0, i1 = entry["bbox"]
        bboxShape = tuple(entry["bboxShape"])
        bboxVoxels = bboxShape[0] * bboxShape[1] * bboxShape[2]
        try:
            # unpackbits returns 0/1 bytes. Reinterpret them as bool instead
            # of allocating a second full-size boolean array.
            maskBBox = (
                np.unpackbits(entry["packedMask"])[:bboxVoxels]
                .view(np.bool_)
                .reshape(bboxShape)
            )
            volumeArray[k0:k1, j0:j1, i0:i1][maskBBox] = entry["values"]
        except (IndexError, ValueError):
            return False
        return True

    def applyToVolume(self, volumeNode, mask, pattern, parameters, description=""):
        """Apply a pattern in place and store a compact undo patch."""
        volumeArray, mask, count = self._prepareMask(volumeNode, mask)
        patch = self._createUndoPatch(
            volumeNode, volumeArray, mask, count, description or pattern.name
        )

        # Write directly into the volume's VTK-managed array. No full-volume
        # modified copy is needed; only small pattern blocks are allocated.
        # If a pattern fails midway, restore the patch before re-raising.
        try:
            pattern.writeValues(volumeArray, volumeArray, mask, volumeNode, parameters)
        except Exception:
            if self._restoreUndoPatch(volumeNode, volumeArray, patch):
                self._notifyVolumeModified(volumeNode)
            raise

        self._notifyVolumeModified(volumeNode)
        self.undoStack.append(patch)
        if len(self.undoStack) > self.maxUndoEntries:
            self.undoStack.pop(0)

        return count

    def canUndo(self, volumeNode):
        if volumeNode is None:
            return False
        volumeID = volumeNode.GetID()
        return any(entry["volumeID"] == volumeID for entry in self.undoStack)

    def undoLast(self, volumeNode):
        """Restore the voxels changed by the most recent apply on volumeNode."""
        if volumeNode is None:
            return None
        volumeID = volumeNode.GetID()

        entryIndex = None
        for index in range(len(self.undoStack) - 1, -1, -1):
            if self.undoStack[index]["volumeID"] == volumeID:
                entryIndex = index
                break
        if entryIndex is None:
            return None

        entry = self.undoStack[entryIndex]
        volumeArray = slicer.util.arrayFromVolume(volumeNode)
        if volumeArray is None:
            return None

        if not self._restoreUndoPatch(volumeNode, volumeArray, entry):
            # The volume geometry changed since apply; leave the undo entry in
            # place instead of silently discarding it.
            return None

        self.undoStack.pop(entryIndex)
        self._notifyVolumeModified(volumeNode)
        return entry

    def clearUndoHistory(self):
        self.undoStack = []


# =============================================================================
# Widget
# =============================================================================

class VolumeModificationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)

        self.logic = None

        # Pattern state
        self.pattern = None
        self.patternWidgets = {}

        # Segmentation observation
        self.observedSegmentationNode = None
        self.segmentSignature = ()

        # Preview state
        self.previewVolumeNode = None
        self.previewActive = False
        self.previewContext = None
        self.savedSliceStates = {}

        # UI
        self.volumeSelector = None
        self.volumeInfoLabel = None
        self.segmentationSelector = None
        self.segmentCombo = None
        self.segmentInfoLabel = None
        self.patternCombo = None
        self.patternDescriptionLabel = None
        self.patternForm = None
        self.presetCombo = None
        self.loadPresetButton = None
        self.deletePresetButton = None
        self.useRangeButton = None
        self.previewButton = None
        self.applyButton = None
        self.undoButton = None
        self.clearPreviewButton = None
        self.previewInfoLabel = None
        self.statusLabel = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = VolumeModificationLogic()

        try:
            self._buildUi()
        except Exception:
            traceback.print_exc()
            slicer.util.errorDisplay(
                _("Failed to create the Volume Modification interface.\n")
                + traceback.format_exc()
            )
            return

        # Everything exists now; initialize safely.
        self._initializePattern()
        self._onVolumeChanged()
        self._onSegmentationChanged()
        self._autoSelectSingleVolume()
        self.updateState()

    def _buildUi(self):
        title = qt.QLabel("<h3>Volume Modification</h3>")
        self.layout.addWidget(title)

        instructions = qt.QLabel(
            "Modifies voxel intensities inside a segmentation segment. "
            "The original volume is preserved until <b>Apply</b> is clicked, "
            "and every apply can be reverted with <b>Undo</b>."
        )
        instructions.wordWrap = True
        self.layout.addWidget(instructions)

        self._buildInputSection()
        self._buildPatternSection()
        self._buildActionSection()

        # Connect input signals only after every widget exists. This prevents
        # callbacks from running while the interface is still being assembled.
        self.volumeSelector.currentNodeChanged.connect(self._onVolumeChanged)
        self.segmentationSelector.currentNodeChanged.connect(self._onSegmentationChanged)
        self.segmentCombo.currentIndexChanged.connect(self._onSegmentChanged)

        self.statusLabel = qt.QLabel(_("Select a volume, segmentation, and segment."))
        self.statusLabel.wordWrap = True
        self.statusLabel.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        self.layout.addWidget(self.statusLabel)

        self.layout.addStretch(1)

    def _buildInputSection(self):
        box = ctk.ctkCollapsibleButton()
        box.text = _("Input: volume and segment")
        box.collapsed = False
        self.layout.addWidget(box)
        form = qt.QFormLayout(box)

        self.volumeSelector = slicer.qMRMLNodeComboBox()
        self.volumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.volumeSelector.selectNodeUponCreation = False
        self.volumeSelector.addEnabled = False
        self.volumeSelector.removeEnabled = False
        self.volumeSelector.noneEnabled = True
        self.volumeSelector.showHidden = False
        self.volumeSelector.showChildNodeTypes = False
        self.volumeSelector.setMRMLScene(slicer.mrmlScene)
        self.volumeSelector.toolTip = _("Volume whose voxel intensities will be modified.")
        form.addRow(_("Volume:"), self.volumeSelector)

        self.volumeInfoLabel = qt.QLabel(_("No volume selected."))
        self.volumeInfoLabel.wordWrap = True
        self.volumeInfoLabel.setStyleSheet("color: #666; font-size: 8pt;")
        form.addRow("", self.volumeInfoLabel)

        self.segmentationSelector = slicer.qMRMLNodeComboBox()
        self.segmentationSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
        self.segmentationSelector.selectNodeUponCreation = False
        self.segmentationSelector.addEnabled = False
        self.segmentationSelector.removeEnabled = False
        self.segmentationSelector.noneEnabled = True
        self.segmentationSelector.showHidden = False
        self.segmentationSelector.showChildNodeTypes = False
        self.segmentationSelector.setMRMLScene(slicer.mrmlScene)
        self.segmentationSelector.toolTip = _("Segmentation that contains the region to modify.")
        form.addRow(_("Segmentation:"), self.segmentationSelector)

        segmentRow = qt.QHBoxLayout()
        self.segmentCombo = qt.QComboBox()
        self.segmentCombo.toolTip = _("Segment whose voxels will be modified.")
        segmentRow.addWidget(self.segmentCombo, 1)

        refreshButton = qt.QPushButton(_("Refresh"))
        refreshButton.minimumWidth = 80
        refreshButton.toolTip = _("Reload the segment list from the selected segmentation.")
        refreshButton.clicked.connect(self._onRefreshSegments)
        segmentRow.addWidget(refreshButton)
        form.addRow(_("Segment:"), segmentRow)

        self.segmentInfoLabel = qt.QLabel(_("No segment selected."))
        self.segmentInfoLabel.wordWrap = True
        self.segmentInfoLabel.setStyleSheet("color: #666; font-size: 8pt;")
        form.addRow("", self.segmentInfoLabel)

    def _buildPatternSection(self):
        box = ctk.ctkCollapsibleButton()
        box.text = _("Intensity pattern")
        box.collapsed = False
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)

        form = qt.QFormLayout()
        layout.addLayout(form)

        self.patternCombo = qt.QComboBox()
        for patternId, patternName, description in getAvailablePatterns():
            self.patternCombo.addItem(patternName, patternId)
            self.patternCombo.setItemData(
                self.patternCombo.count - 1, description, qt.Qt.ToolTipRole
            )
        self.patternCombo.toolTip = _("Select how voxel intensities inside the region are changed.")
        form.addRow(_("Pattern:"), self.patternCombo)

        self.patternDescriptionLabel = qt.QLabel("")
        self.patternDescriptionLabel.wordWrap = True
        self.patternDescriptionLabel.setStyleSheet("color: #555; font-size: 8pt;")
        form.addRow(self.patternDescriptionLabel)

        defaultsRow = qt.QHBoxLayout()
        self.useRangeButton = qt.QPushButton(_("Use volume intensity range"))
        self.useRangeButton.toolTip = (
            "Fill the current pattern parameters from the selected volume's "
            "minimum and maximum intensity values."
        )
        self.useRangeButton.clicked.connect(self._onUseVolumeRange)
        defaultsRow.addWidget(self.useRangeButton)
        defaultsRow.addStretch(1)
        form.addRow("", defaultsRow)

        paramsBox = ctk.ctkCollapsibleButton()
        paramsBox.text = _("Pattern parameters")
        paramsBox.collapsed = False
        layout.addWidget(paramsBox)
        self.patternForm = qt.QFormLayout(paramsBox)
        self.patternForm.setVerticalSpacing(8)
        self.patternForm.setHorizontalSpacing(10)
        self.patternForm.setFieldGrowthPolicy(qt.QFormLayout.ExpandingFieldsGrow)
        self.patternForm.setLabelAlignment(qt.Qt.AlignLeft | qt.Qt.AlignVCenter)

        presetBox = qt.QGroupBox(_("Reusable presets"))
        presetBox.minimumHeight = 104
        presetLayout = qt.QVBoxLayout(presetBox)
        presetLayout.setContentsMargins(8, 10, 8, 8)
        presetLayout.setSpacing(7)
        self.presetCombo = qt.QComboBox()
        self.presetCombo.minimumHeight = 30
        self.presetCombo.toolTip = _("Choose a saved pattern and its parameter values.")
        presetLayout.addWidget(self.presetCombo)

        presetButtons = qt.QHBoxLayout()
        presetButtons.setSpacing(7)
        self.loadPresetButton = qt.QPushButton(_("Load"))
        self.loadPresetButton.minimumHeight = 30
        self.loadPresetButton.clicked.connect(self._onLoadPreset)
        presetButtons.addWidget(self.loadPresetButton)

        savePresetButton = qt.QPushButton(_("Save current parameters"))
        savePresetButton.minimumHeight = 30
        savePresetButton.toolTip = _(
            "Save the selected pattern and its parameters to a JSON file in the plugin folder."
        )
        savePresetButton.clicked.connect(self._onSavePreset)
        presetButtons.addWidget(savePresetButton, 1)

        self.deletePresetButton = qt.QPushButton(_("Delete"))
        self.deletePresetButton.minimumHeight = 30
        self.deletePresetButton.clicked.connect(self._onDeletePreset)
        presetButtons.addWidget(self.deletePresetButton)
        presetLayout.addLayout(presetButtons)
        layout.addWidget(presetBox)
        self._refreshPresetCombo()

        self.patternCombo.currentIndexChanged.connect(self._onPatternChanged)

    def _buildActionSection(self):
        box = ctk.ctkCollapsibleButton()
        box.text = _("Preview, apply, and undo")
        box.collapsed = False
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)

        self.previewButton = qt.QPushButton(_("Preview modification"))
        self.previewButton.toolTip = (
            "Create a temporary copy of the volume with the pattern applied and "
            "show it in the slice views."
        )
        self.previewButton.clicked.connect(self._onPreview)
        layout.addWidget(self.previewButton)

        self.applyButton = qt.QPushButton(_("Apply modification"))
        self.applyButton.toolTip = _("Write the previewed modification into the original volume.")
        self.applyButton.clicked.connect(self._onApply)
        layout.addWidget(self.applyButton)

        self.undoButton = qt.QPushButton(_("Undo last apply"))
        self.undoButton.toolTip = _("Restore the voxels changed by the last apply on this volume.")
        self.undoButton.clicked.connect(self._onUndo)
        layout.addWidget(self.undoButton)

        self.clearPreviewButton = qt.QPushButton(_("Clear preview"))
        self.clearPreviewButton.toolTip = _("Remove the temporary preview and restore the original slice display.")
        self.clearPreviewButton.clicked.connect(self._onClearPreview)
        layout.addWidget(self.clearPreviewButton)

        self.previewInfoLabel = qt.QLabel(_("No preview active."))
        self.previewInfoLabel.wordWrap = True
        self.previewInfoLabel.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        layout.addWidget(self.previewInfoLabel)

    # ------------------------------------------------------------------
    # Pattern UI
    # ------------------------------------------------------------------
    def _presetFilePath(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "parameter_presets.json")

    def _readPresets(self):
        path = self._presetFilePath()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as presetFile:
                data = json.load(presetFile)
            presets = data.get("presets", []) if isinstance(data, dict) else []
            return [
                preset for preset in presets
                if isinstance(preset, dict)
                and isinstance(preset.get("name"), str)
                and preset.get("name", "").strip()
                and isinstance(preset.get("patternId"), str)
                and isinstance(preset.get("parameters"), dict)
            ]
        except Exception as exc:
            slicer.util.warningDisplay(
                _("Could not read parameter presets from {}: {}").format(path, exc)
            )
            return []

    def _writePresets(self, presets):
        path = self._presetFilePath()
        try:
            with open(path, "w", encoding="utf-8") as presetFile:
                json.dump(
                    {"version": 1, "presets": presets},
                    presetFile,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            return True
        except Exception as exc:
            slicer.util.warningDisplay(
                _("Could not save parameter presets to {}: {}\n"
                  "Check that the plugin folder is writable.").format(path, exc)
            )
            return False

    def _refreshPresetCombo(self, selectedName=None):
        if self.presetCombo is None:
            return
        if selectedName is None and self.presetCombo.count:
            selectedName = self.presetCombo.currentData

        presets = self._readPresets()
        self.presetCombo.blockSignals(True)
        self.presetCombo.clear()
        for preset in sorted(presets, key=lambda item: item["name"].casefold()):
            self.presetCombo.addItem(preset["name"], preset["name"])
        selectedIndex = self.presetCombo.findData(selectedName) if selectedName else -1
        if selectedIndex >= 0:
            self.presetCombo.setCurrentIndex(selectedIndex)
        self.presetCombo.blockSignals(False)

        hasPresets = self.presetCombo.count > 0
        self.presetCombo.enabled = hasPresets
        self.loadPresetButton.enabled = hasPresets
        self.deletePresetButton.enabled = hasPresets

    def _onSavePreset(self):
        if self.pattern is None:
            slicer.util.warningDisplay(_("Select a pattern before saving a preset."))
            return
        result = qt.QInputDialog.getText(
            slicer.util.mainWindow(),
            _("Save parameter preset"),
            _("Preset name:"),
        )
        if isinstance(result, tuple):
            name, accepted = result
        else:
            name, accepted = result, bool(result)
        name = str(name).strip()
        if not accepted or not name:
            return

        presets = self._readPresets()
        existingIndex = next(
            (index for index, preset in enumerate(presets)
             if preset["name"].casefold() == name.casefold()),
            None,
        )
        if existingIndex is not None:
            answer = qt.QMessageBox.question(
                slicer.util.mainWindow(),
                _("Replace preset?"),
                _("A preset named '{}' already exists. Replace it?").format(name),
                qt.QMessageBox.Yes | qt.QMessageBox.No,
                qt.QMessageBox.No,
            )
            if answer != qt.QMessageBox.Yes:
                return
            presets.pop(existingIndex)

        presets.append({
            "name": name,
            "patternId": self.pattern.id,
            "parameters": self._currentParameters(),
        })
        if self._writePresets(presets):
            self._refreshPresetCombo(name)

    def _onLoadPreset(self):
        name = self.presetCombo.currentData if self.presetCombo else None
        if not name:
            return
        preset = next(
            (item for item in self._readPresets() if item["name"] == name),
            None,
        )
        if preset is None:
            self._refreshPresetCombo()
            slicer.util.warningDisplay(_("The selected preset could not be found."))
            return

        patternIndex = self.patternCombo.findData(preset["patternId"])
        if patternIndex < 0:
            slicer.util.warningDisplay(
                _("The preset refers to an unavailable pattern: {}").format(
                    preset["patternId"]
                )
            )
            return
        if self.patternCombo.currentIndex != patternIndex:
            self.patternCombo.setCurrentIndex(patternIndex)

        try:
            for key, value in preset["parameters"].items():
                widget = self.patternWidgets.get(key)
                if widget is None:
                    continue
                widget.blockSignals(True)
                if isinstance(widget, qt.QComboBox):
                    itemIndex = widget.findData(value)
                    if itemIndex >= 0:
                        widget.setCurrentIndex(itemIndex)
                elif isinstance(widget, qt.QSpinBox):
                    widget.value = int(value)
                elif isinstance(widget, qt.QDoubleSpinBox):
                    widget.value = float(value)
                widget.blockSignals(False)
        except Exception as exc:
            for widget in self.patternWidgets.values():
                try:
                    widget.blockSignals(False)
                except Exception:
                    pass
            slicer.util.warningDisplay(_("Could not load preset values: ") + str(exc))
            return

        self._clearPreview()
        self.updateState()

    def _onDeletePreset(self):
        name = self.presetCombo.currentData if self.presetCombo else None
        if not name:
            return
        answer = qt.QMessageBox.question(
            slicer.util.mainWindow(),
            _("Delete preset?"),
            _("Delete the saved preset '{}'?").format(name),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.No,
        )
        if answer != qt.QMessageBox.Yes:
            return
        presets = [item for item in self._readPresets() if item["name"] != name]
        if self._writePresets(presets):
            self._refreshPresetCombo()

    def _initializePattern(self):
        self._setPattern(0)

    def _clearForm(self, form):
        while True:
            try:
                rowCount = int(form.rowCount())
            except Exception:
                try:
                    rowCount = int(form.rowCount)
                except Exception:
                    break
            if rowCount <= 0:
                break
            form.removeRow(0)

    def _setPattern(self, index):
        self._clearForm(self.patternForm)
        self.patternWidgets = {}

        patternId = self.patternCombo.currentData
        if patternId is None:
            patternId = UniformPattern.id
        self.pattern = getPattern(patternId)

        self.patternDescriptionLabel.setText(self.pattern.description)
        self.pattern.createParameterWidgets(self.patternForm, self.patternWidgets)
        for widget in self.patternWidgets.values():
            if isinstance(widget, (qt.QDoubleSpinBox, qt.QSpinBox)):
                widget.minimumHeight = 30
                widget.minimumWidth = 130
                widget.setAlignment(qt.Qt.AlignRight | qt.Qt.AlignVCenter)
                widget.setStyleSheet(
                    "QSpinBox, QDoubleSpinBox {"
                    " min-height: 28px; padding: 2px 6px; font-size: 10pt; }"
                )
                label = self.patternForm.labelForField(widget)
                if label is not None:
                    label.minimumHeight = 30
                    label.setStyleSheet("font-size: 10pt;")
        self._connectPatternParameterSignals()

        if hasattr(self, "useRangeButton") and self.useRangeButton is not None:
            usesRange = bool(getattr(self.pattern, "usesVolumeRange", True))
            self.useRangeButton.enabled = usesRange
            if usesRange:
                self.useRangeButton.toolTip = (
                    "Fill the current pattern parameters from the selected "
                    "volume's minimum and maximum intensity values."
                )
            else:
                self.useRangeButton.toolTip = (
                    "This pattern uses intensities relative to the original "
                    "voxels inside the segment, so the volume range is not used."
                )

        self._clearPreview()
        self.updateState()

    def _onPatternChanged(self, index):
        if not hasattr(self, "patternForm") or self.patternForm is None:
            return
        self._setPattern(index)

    def _connectPatternParameterSignals(self):
        for widget in self.patternWidgets.values():
            try:
                if isinstance(widget, qt.QComboBox):
                    widget.currentIndexChanged.connect(self._onPatternParameterChanged)
                elif isinstance(widget, (qt.QDoubleSpinBox, qt.QSpinBox)):
                    widget.valueChanged.connect(self._onPatternParameterChanged)
            except Exception:
                pass

    def _onPatternParameterChanged(self, *args):
        # A preview made with previous parameters would be misleading.
        if self.previewActive:
            self._clearPreview()
        self.updateState()

    def _onUseVolumeRange(self):
        volumeNode = self.volumeSelector.currentNode()
        if volumeNode is None or volumeNode.GetImageData() is None:
            slicer.util.warningDisplay(_("Select a volume first."))
            return
        if self.pattern is None:
            return
        if not getattr(self.pattern, "usesVolumeRange", True):
            return

        minimum, maximum = volumeNode.GetImageData().GetScalarRange()
        try:
            if self.pattern.id == UniformPattern.id:
                self.patternWidgets["intensity"].value = maximum
            elif self.pattern.id == RadialFalloffPattern.id:
                self.patternWidgets["centerIntensity"].value = maximum
                self.patternWidgets["edgeIntensity"].value = minimum
            elif self.pattern.id == RadiolucentLesionPattern.id:
                self.patternWidgets["borderIntensity"].value = maximum
                self.patternWidgets["centerIntensity"].value = minimum
            elif self.pattern.id == CustomPattern.id:
                self.patternWidgets["targetIntensity"].value = maximum
        except Exception as exc:
            slicer.util.warningDisplay(_("Could not update pattern values: ") + str(exc))

    # ------------------------------------------------------------------
    # Inputs
    # ------------------------------------------------------------------
    def _autoSelectSingleVolume(self):
        if self.volumeSelector.currentNode() is not None:
            return
        volumeCount = slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLScalarVolumeNode")
        if volumeCount == 1:
            node = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
            if node:
                self.volumeSelector.setCurrentNode(node)

    def _onVolumeChanged(self, node=None):
        self._updateVolumeInfo()
        self._clearPreview()
        self.updateState()

    def _updateVolumeInfo(self):
        volumeNode = self.volumeSelector.currentNode() if self.volumeSelector else None
        if volumeNode is None or volumeNode.GetImageData() is None:
            self.volumeInfoLabel.setText(_("No volume selected."))
            return
        imageData = volumeNode.GetImageData()
        dimensions = imageData.GetDimensions()
        spacing = volumeNode.GetSpacing()
        minimum, maximum = imageData.GetScalarRange()
        self.volumeInfoLabel.setText(
            _("{} x {} x {} voxels | spacing {:.3f} x {:.3f} x {:.3f} mm | intensity {:.1f} to {:.1f}")
            .format(
                dimensions[0], dimensions[1], dimensions[2],
                spacing[0], spacing[1], spacing[2],
                minimum, maximum,
            )
        )

    def _onSegmentationChanged(self, node=None):
        if self.observedSegmentationNode is not None:
            try:
                self.removeObserver(
                    self.observedSegmentationNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onSegmentationModified,
                )
            except Exception:
                pass
            self.observedSegmentationNode = None

        segmentationNode = self.segmentationSelector.currentNode()
        if segmentationNode is not None:
            try:
                self.addObserver(
                    segmentationNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onSegmentationModified,
                )
                self.observedSegmentationNode = segmentationNode
            except Exception:
                self.observedSegmentationNode = None

        self._refreshSegmentCombo()
        self._clearPreview()
        self.updateState()

    def _onSegmentationModified(self, caller=None, event=None):
        if self.observedSegmentationNode is None:
            return
        signature = self._segmentationSignature(self.observedSegmentationNode)
        if signature != self.segmentSignature:
            self._refreshSegmentCombo()
            self._clearPreview()
            self.updateState()

    def _segmentationSignature(self, segmentationNode):
        segmentation = segmentationNode.GetSegmentation() if segmentationNode else None
        if segmentation is None:
            return ()
        result = []
        for index in range(segmentation.GetNumberOfSegments()):
            segmentId = segmentation.GetNthSegmentID(index)
            segment = segmentation.GetSegment(segmentId)
            name = segment.GetName() if segment and segment.GetName() else segmentId
            result.append((segmentId, name))
        return tuple(result)

    def _refreshSegmentCombo(self):
        previousId = self.segmentCombo.currentData if self.segmentCombo.count else None

        self.segmentCombo.blockSignals(True)
        self.segmentCombo.clear()

        segmentationNode = self.segmentationSelector.currentNode() if self.segmentationSelector else None
        if segmentationNode is not None and segmentationNode.GetSegmentation() is not None:
            segmentation = segmentationNode.GetSegmentation()
            for index in range(segmentation.GetNumberOfSegments()):
                segmentId = segmentation.GetNthSegmentID(index)
                segment = segmentation.GetSegment(segmentId)
                name = segment.GetName() if segment and segment.GetName() else segmentId
                self.segmentCombo.addItem(str(name), segmentId)

        if previousId is not None:
            previousIndex = self.segmentCombo.findData(previousId)
            if previousIndex >= 0:
                self.segmentCombo.setCurrentIndex(previousIndex)

        self.segmentCombo.blockSignals(False)
        self.segmentSignature = self._segmentationSignature(segmentationNode)

    def _onRefreshSegments(self):
        segmentationNode = self.segmentationSelector.currentNode()
        if segmentationNode is None:
            slicer.util.warningDisplay(_("Select a segmentation first."))
            return
        try:
            segmentationNode.CreateDefaultDisplayNodes()
            segmentationNode.GetSegmentation().CreateRepresentation("Binary labelmap")
        except Exception:
            pass
        self._refreshSegmentCombo()
        self._clearPreview()
        self.updateState()

    def _onSegmentChanged(self, index):
        self._clearPreview()
        self.updateState()

    def _selectedSegmentId(self):
        if self.segmentCombo is None or self.segmentCombo.count == 0:
            return None
        return self.segmentCombo.currentData

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def updateState(self):
        if not hasattr(self, "previewButton") or self.previewButton is None:
            return

        volumeNode = self.volumeSelector.currentNode() if self.volumeSelector else None
        segmentationNode = self.segmentationSelector.currentNode() if self.segmentationSelector else None
        segmentId = self._selectedSegmentId()

        hasVolume = volumeNode is not None
        hasSegmentation = segmentationNode is not None
        hasSegment = bool(segmentId)

        ready = hasVolume and hasSegmentation and hasSegment and self.pattern is not None

        self.previewButton.enabled = ready
        self.applyButton.enabled = ready and self.previewActive
        self.clearPreviewButton.enabled = self.previewActive
        self.undoButton.enabled = self.logic.canUndo(volumeNode) if volumeNode else False

        if hasSegmentation and hasSegment:
            self.segmentInfoLabel.setText(
                _("Region: {} / {}").format(
                    segmentationNode.GetName() or segmentationNode.GetID(),
                    self.segmentCombo.currentText,
                )
            )
        elif hasSegmentation:
            self.segmentInfoLabel.setText(_("Select a segment."))
        else:
            self.segmentInfoLabel.setText(_("No segment selected."))

        if not hasVolume:
            self.statusLabel.setText(_("Select a volume to modify."))
        elif not hasSegmentation:
            self.statusLabel.setText(_("Select a segmentation containing the region."))
        elif not hasSegment:
            self.statusLabel.setText(_("Select a segment."))
        elif self.previewActive:
            self.statusLabel.setText(
                _("Preview active. Apply writes the changes; Clear preview restores the original display.")
            )
        else:
            self.statusLabel.setText(_("Ready. Create a preview to inspect the modification."))

    # ------------------------------------------------------------------
    # Preview / apply / undo
    # ------------------------------------------------------------------
    def _currentParameters(self):
        if self.pattern is None:
            raise RuntimeError("No intensity pattern selected.")
        return self.pattern.readParameters(self.patternWidgets)

    def _currentMask(self, volumeNode):
        segmentationNode = self.segmentationSelector.currentNode()
        segmentId = self._selectedSegmentId()
        if segmentationNode is None or not segmentId:
            raise ValueError("Select a segmentation and segment first.")
        return self.logic.getSegmentMaskArray(segmentationNode, segmentId, volumeNode)

    def _onPreview(self):
        try:
            with slicer.util.tryWithErrorDisplay(
                _("Failed to create the preview."), waitCursor=True
            ):
                self._createPreview()
        except Exception:
            traceback.print_exc()

    def _createPreview(self):
        volumeNode = self.volumeSelector.currentNode()
        if volumeNode is None:
            raise ValueError("Select a volume first.")

        # Remove a previous preview before extracting the mask, so its
        # full-volume copy does not coexist with the new mask and image copy.
        self._clearPreview()

        parameters = self._currentParameters()
        mask = self._currentMask(volumeNode)
        if not np.any(mask):
            raise RuntimeError("The selected segment contains no voxels.")

        # Build exactly one native-dtype copy and write pattern blocks into it.
        modifiedImageData, count = self.logic.computeModifiedImageData(
            volumeNode, mask, self.pattern, parameters
        )
        del mask

        previewNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode", "_VolumeModification_Preview"
        )
        previewNode.SetName(
            "{}_preview".format(volumeNode.GetName() or volumeNode.GetID())
        )
        try:
            # Keep the temporary volume out of Data module / node selectors.
            previewNode.SetHideFromEditors(True)
        except Exception:
            pass
        previewNode.SetAndObserveImageData(modifiedImageData)
        previewNode.CopyOrientation(volumeNode)
        try:
            # Create a display node so the preview volume is guaranteed to be
            # renderable in slice views, then match the source contrast.
            previewNode.CreateDefaultDisplayNodes()
            sourceDisplayNode = volumeNode.GetDisplayNode()
            previewDisplayNode = previewNode.GetDisplayNode()
            if sourceDisplayNode is not None and previewDisplayNode is not None:
                try:
                    previewDisplayNode.SetAndObserveColorNodeID(
                        sourceDisplayNode.GetColorNodeID()
                    )
                except Exception:
                    pass
                try:
                    previewDisplayNode.SetAutoWindowLevel(0)
                    previewDisplayNode.SetWindowLevel(
                        sourceDisplayNode.GetWindow(), sourceDisplayNode.GetLevel()
                    )
                except Exception:
                    pass
                try:
                    previewDisplayNode.SetInterpolate(sourceDisplayNode.GetInterpolate())
                except Exception:
                    pass
        except Exception:
            logging.warning("Could not configure the preview volume display node.")
        self.previewVolumeNode = previewNode

        self._saveSliceStates()
        self._displayPreviewInSliceViews(previewNode)

        segmentationNode = self.segmentationSelector.currentNode()
        self.previewActive = True
        self.previewContext = {
            "volumeID": volumeNode.GetID(),
            "segmentationID": segmentationNode.GetID() if segmentationNode else None,
            "segmentID": self._selectedSegmentId(),
            "patternID": self.pattern.id,
            "parameters": dict(parameters),
            "maskCount": count,
        }

        self.previewInfoLabel.setText(
            _("Preview active: {} voxels affected. "
              "Original volume is unchanged.").format(count)
        )
        self.updateState()

    def _saveSliceStates(self):
        self.savedSliceStates = {}
        try:
            layoutManager = slicer.app.layoutManager()
        except Exception:
            layoutManager = None
        if layoutManager is None:
            return
        for sliceName in ["Red", "Yellow", "Green"]:
            widget = layoutManager.sliceWidget(sliceName)
            if widget is None:
                continue
            composite = widget.mrmlSliceCompositeNode()
            if composite is None:
                continue
            self.savedSliceStates[sliceName] = {
                "background": composite.GetBackgroundVolumeID() or "",
                "foreground": composite.GetForegroundVolumeID() or "",
                "foregroundOpacity": composite.GetForegroundOpacity(),
                "label": composite.GetLabelVolumeID() or "",
            }

    def _restoreSliceStates(self):
        if not self.savedSliceStates:
            return
        try:
            layoutManager = slicer.app.layoutManager()
        except Exception:
            layoutManager = None
        if layoutManager is None:
            self.savedSliceStates = {}
            return

        fallbackVolume = self.volumeSelector.currentNode() if self.volumeSelector else None
        fallbackId = fallbackVolume.GetID() if fallbackVolume else ""

        for sliceName, state in self.savedSliceStates.items():
            widget = layoutManager.sliceWidget(sliceName)
            if widget is None:
                continue
            composite = widget.mrmlSliceCompositeNode()
            if composite is None:
                continue
            backgroundId = state.get("background") or fallbackId
            composite.SetBackgroundVolumeID(backgroundId)
            composite.SetForegroundVolumeID(state.get("foreground") or "")
            composite.SetLabelVolumeID(state.get("label") or "")
            composite.SetForegroundOpacity(state.get("foregroundOpacity", 1.0))

        self.savedSliceStates = {}

    def _displayPreviewInSliceViews(self, previewNode):
        try:
            layoutManager = slicer.app.layoutManager()
        except Exception:
            layoutManager = None
        if layoutManager is None:
            return
        for sliceName in ["Red", "Yellow", "Green"]:
            widget = layoutManager.sliceWidget(sliceName)
            if widget is None:
                continue
            composite = widget.mrmlSliceCompositeNode()
            if composite is None:
                continue
            composite.SetBackgroundVolumeID(previewNode.GetID())
            composite.SetForegroundVolumeID("")
            composite.SetLabelVolumeID("")

    def _removePreviewNode(self):
        if self.previewVolumeNode is not None:
            try:
                slicer.mrmlScene.RemoveNode(self.previewVolumeNode)
            except Exception:
                pass
            self.previewVolumeNode = None

    def _clearPreview(self):
        self._removePreviewNode()
        self._restoreSliceStates()
        self.previewActive = False
        self.previewContext = None
        if hasattr(self, "previewInfoLabel") and self.previewInfoLabel:
            self.previewInfoLabel.setText(_("No preview active."))
        if hasattr(self, "previewButton") and self.previewButton:
            self.updateState()

    def _onClearPreview(self):
        self._clearPreview()

    def _onApply(self):
        volumeNode = self.volumeSelector.currentNode()
        if volumeNode is None:
            slicer.util.warningDisplay(_("Select a volume first."))
            return
        if not self.previewActive:
            slicer.util.warningDisplay(_("Create a preview before applying."))
            return

        try:
            with slicer.util.tryWithErrorDisplay(
                _("Failed to apply the modification."), waitCursor=True
            ):
                parameters = self._currentParameters()
                expectedMaskCount = None
                if self.previewContext is not None:
                    expectedMaskCount = int(
                        self.previewContext.get("maskCount", -1)
                    )

                # Release the preview image before extracting the mask and
                # applying, so only the original volume, mask, and compact undo
                # patch are in memory.
                self._clearPreview()

                mask = self._currentMask(volumeNode)

                # Guard against a stale preview (e.g. segment edited after preview).
                if expectedMaskCount is not None:
                    if int(np.count_nonzero(mask)) != expectedMaskCount:
                        raise RuntimeError(
                            "The selected region changed after the preview was created. "
                            "Create the preview again before applying."
                        )

                count = self.logic.applyToVolume(
                    volumeNode, mask, self.pattern, parameters,
                    description=self.pattern.name,
                )
                del mask

                self.updateState()
                self.statusLabel.setText(
                    _("Applied '{}' to {} voxels.").format(self.pattern.name, count)
                )
                slicer.util.infoDisplay(
                    _("Modification applied to {} voxels.\n\nUse Undo to revert it.")
                    .format(count)
                )
        except Exception:
            traceback.print_exc()

    def _onUndo(self):
        volumeNode = self.volumeSelector.currentNode()
        if volumeNode is None:
            return
        if self.previewActive:
            self._clearPreview()
        entry = self.logic.undoLast(volumeNode)
        if entry is None:
            slicer.util.warningDisplay(_("Nothing to undo for this volume."))
            return
        self.statusLabel.setText(
            _("Undo restored {} voxels ({}).").format(entry["count"], entry["description"])
        )
        self.updateState()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self):
        try:
            self._clearPreview()
        except Exception:
            pass
        if self.observedSegmentationNode is not None:
            try:
                self.removeObserver(
                    self.observedSegmentationNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onSegmentationModified,
                )
            except Exception:
                pass
            self.observedSegmentationNode = None
        try:
            self.removeObservers()
        except Exception:
            pass


# =============================================================================
# Module
# =============================================================================

class VolumeModification(ScriptedLoadableModule):

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Volume Modification")
        self.parent.categories = ["Segmentation", "Quantification"]
        self.parent.dependencies = []
        self.parent.contributors = ["Pedro Afonso (Developer)"]
        self.parent.helpText = _(
            """Apply configurable intensity patterns to a volume inside a segmentation segment.
<br><br>
<b>Workflow:</b>
<ol>
<li>Select the volume to modify and the segmentation/segment that defines the region.</li>
<li>Choose an intensity pattern and configure its parameters.</li>
<li>Click <b>Preview modification</b> to inspect the result in slice views.</li>
<li>Click <b>Apply modification</b> to write it to the original volume, or <b>Undo</b> to revert.</li>
</ol>
Patterns: uniform radiopacity, radial intensity falloff, radiolucent lesion with radiopaque border, periapical inflammatory lesion, periapical lesion with sclerotic halo, and custom blend.
<br><br>
The two periapical patterns use the original intensities inside the segment as a local reference. They are educational simulations and do not assume that CBCT gray values are calibrated Hounsfield units.
"""
        )
        self.parent.acknowledgementText = _(
            "Developed for synthetic case generation in medical imaging education."
        )


# =============================================================================
# Tests
# =============================================================================

class VolumeModificationTest(ScriptedLoadableModuleTest):

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_uniformApplyAndUndo()
        self.test_radialFalloff()
        self.test_periapicalPatterns()
        self.test_customBlend()

    def _makeVolume(self, shape=(10, 10, 10), dtype=np.int16):
        volumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        array = np.zeros(shape, dtype=dtype)
        slicer.util.updateVolumeFromArray(volumeNode, array)
        return volumeNode

    def test_uniformApplyAndUndo(self):
        self.delayDisplay("Testing uniform pattern apply/undo")
        volumeNode = self._makeVolume()
        mask = np.zeros((10, 10, 10), dtype=bool)
        mask[3:7, 3:7, 3:7] = True

        pattern = UniformPattern()
        parameters = {"intensity": 1000.0}
        logic = VolumeModificationLogic()

        count = logic.applyToVolume(volumeNode, mask, pattern, parameters)
        self.assertEqual(count, 64)
        modified = slicer.util.arrayFromVolume(volumeNode)
        self.assertTrue(np.all(modified[mask] == 1000))
        self.assertTrue(np.all(modified[~mask] == 0))
        self.assertTrue(logic.canUndo(volumeNode))

        entry = logic.undoLast(volumeNode)
        self.assertIsNotNone(entry)
        restored = slicer.util.arrayFromVolume(volumeNode)
        self.assertTrue(np.all(restored == 0))
        self.assertFalse(logic.canUndo(volumeNode))
        self.delayDisplay("Uniform pattern test passed")

    def test_radialFalloff(self):
        self.delayDisplay("Testing radial falloff")
        volumeNode = self._makeVolume()
        mask = np.zeros((10, 10, 10), dtype=bool)
        mask[2:8, 2:8, 2:8] = True

        pattern = RadialFalloffPattern()
        parameters = {
            "centerIntensity": 3000.0,
            "edgeIntensity": 500.0,
            "falloffPower": 2.0,
        }
        logic = VolumeModificationLogic()
        modified, count = logic.computeModifiedArray(volumeNode, mask, pattern, parameters)
        self.assertEqual(count, 216)
        self.assertGreater(modified[5, 5, 5], modified[2, 5, 5])
        self.delayDisplay("Radial falloff test passed")

    def test_periapicalPatterns(self):
        if not HAVE_SCIPY:
            self.delayDisplay("SciPy not available; skipping periapical patterns")
            return

        self.delayDisplay("Testing periapical lesion patterns")
        volumeNode = self._makeVolume(shape=(20, 20, 20))
        rng = np.random.default_rng(11)
        original = (
            800 + rng.integers(-120, 121, size=(20, 20, 20))
        ).astype(np.int16)
        slicer.util.updateVolumeFromArray(volumeNode, original)

        mask = np.zeros((20, 20, 20), dtype=bool)
        mask[5:15, 5:15, 5:15] = True
        logic = VolumeModificationLogic()

        cases = [
            (
                PeriapicalInflammatoryPattern(),
                {},
            ),
            (
                PeriapicalScleroticHaloPattern(),
                {
                    "coreDarkening": 20.0,
                    "heterogeneity": 4.0,
                    "residualTrabeculae": 0.0,
                    "haloThickness": 1.5,
                    "haloBoost": 40.0,
                    "marginTransition": 0.5,
                    "textureSeed": 3,
                },
            ),
        ]

        for pattern, parameters in cases:
            modified, count = logic.computeModifiedArray(
                volumeNode, mask, pattern, parameters
            )
            self.assertEqual(count, 1000)
            self.assertTrue(np.array_equal(modified[~mask], original[~mask]))
            self.assertLess(
                float(np.median(modified[mask])),
                float(np.median(original[mask])) - 10.0,
            )

            # Preview and Apply must use exactly the same deterministic texture.
            repeated, repeatedCount = logic.computeModifiedArray(
                volumeNode, mask, pattern, parameters
            )
            self.assertEqual(repeatedCount, count)
            self.assertTrue(np.array_equal(modified, repeated))

        haloModified, _ = logic.computeModifiedArray(
            volumeNode,
            mask,
            PeriapicalScleroticHaloPattern(),
            cases[1][1],
        )
        self.assertGreater(
            float(haloModified[5, 10, 10]),
            float(haloModified[10, 10, 10]),
        )
        self.delayDisplay("Periapical lesion patterns test passed")

    def test_customBlend(self):
        self.delayDisplay("Testing custom blend")
        volumeNode = self._makeVolume()
        mask = np.zeros((10, 10, 10), dtype=bool)
        mask[3:7, 3:7, 3:7] = True

        pattern = CustomPattern()
        parameters = {
            "formula": "gaussian",
            "targetIntensity": 2000.0,
            "sigma": 2.0,
        }
        logic = VolumeModificationLogic()
        modified, count = logic.computeModifiedArray(volumeNode, mask, pattern, parameters)
        self.assertEqual(count, 64)
        self.assertGreater(modified[5, 5, 5], 0)
        self.delayDisplay("Custom blend test passed")