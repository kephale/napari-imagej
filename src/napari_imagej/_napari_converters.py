from typing import List
from jpype import JArray, JDouble
import numpy as np
from napari_imagej.setup_imagej import ij, java_import
from napari.layers import Labels, Shapes, Points
from napari_imagej import _ntypes
from scyjava import Converter, Priority, when_jvm_starts, add_py_converter, add_java_converter
from labeling.Labeling import Labeling


# -- Labels / ImgLabelings -- #


def _imglabeling_to_layer(imgLabeling) -> Labels:
    """
    Converts a Java ImgLabeling to a napari Labels layer
    :param imgLabeling: the Java ImgLabeling
    :return: a Labels layer
    """
    labeling: Labeling = ij().py._imglabeling_to_labeling(imgLabeling)
    return _ntypes._labeling_to_layer(labeling)


def _layer_to_imglabeling(layer: Labels):
    """
    Converts a napari Labels layer to a Java ImgLabeling
    :param layer: a Labels layer
    :return: the Java ImgLabeling
    """
    labeling: Labeling = _ntypes._layer_to_labeling(layer)
    return ij().py.to_java(labeling)


# -- Shapes Utils -- #


def arr(coords):
    arr = JArray(JDouble)(len(coords))
    arr[:] = coords
    return arr


def realPoint_from(coords: np.ndarray):
    """
    Creates a RealPoint from a numpy [1, D] array of coordinates.
    :param coords: The [1, D] numpy array of coordinates
    :return: a RealPoint
    """
    # JPype doesn't know whether to call the float or double.
    # We make the choice for them using the function arr
    return RealPoint(arr(coords))


def _polyshape_to_layer_data(mask):
    vertices = mask.vertices()
    num_dims = mask.numDimensions()
    arr = JArray(JDouble)(int(num_dims))
    data = np.zeros((vertices.size(), num_dims))
    for i in range(len(vertices)):
        vertices.get(i).localize(arr)
        data[i, :] = arr
    return data


# -- Ellipses -- #


def _ellipse_data_to_mask(pts):
    center = np.mean(pts, axis=0)
    radii = np.abs(pts[0, :] - center)
    return ClosedWritableEllipsoid(center, radii)


def _ellipse_mask_to_data(mask):
    # Make data array
    data = np.zeros((2, mask.numDimensions()))
    # Write center into the first column
    center = mask.center().positionAsDoubleArray()
    data[0, :] = center[:] # Slice needed for JArray
    # Write radii into the second column
    for i in range(data.shape[1]):
        data[1, i] = mask.semiAxisLength(i)
    return data


def _ellipse_mask_to_layer(mask):
    layer = Shapes()
    layer.add_ellipses(_ellipse_mask_to_data(mask))
    return layer


# -- Boxes -- #


def _is_axis_aligned(
    min: np.ndarray,
    max: np.ndarray,
    points: np.ndarray
    ) -> bool:
    """
    Our rectangle consists of four points. We have:
    * The "minimum" point, the point closest to the origin
    * The "maximum" point, the point farthest from the origin
    * Two other points
    If our rectangle is axis aligned, then the distance vector between
    the minimum and another NON-MAXIMUM point will be zero in at least
    one dimension.

    :param min: The minimum corner of the rectangle
    :param max: The maximum corner of the rectangle
    :param points: The four corners of the rectangle
    :return: true iff the rectangle defined by points is axis-aligned.
    """
    other = next(filter(lambda p2: not np.array_equal(min, p2) and not np.array_equal(max, p2), points), None)
    min_diff = other - min
    return any(d == 0 for d in min_diff)


def _rectangle_data_to_mask(points):
    # find rectangle min - closest point to origin
    origin = np.array([0, 0])
    distances = [np.linalg.norm(origin - pt) for pt in points]
    min = points[np.argmin(distances)]
    # find rectangle max - farthest point from minimum
    min_distances = [np.linalg.norm(min - pt) for pt in points]
    max = points[np.argmax(min_distances)]
    # Return box if axis aligned
    if _is_axis_aligned(min, max, points):
        return ClosedWritableBox(arr(min), arr(max))
    # Return polygon if not
    else:
        return _polygon_data_to_mask(points)


def _rectangle_mask_to_data(mask):
    min = mask.minAsDoubleArray()
    max = mask.maxAsDoubleArray()
    data = np.zeros((2, len(min)))
    data[0, :] = min[:] # Slice needed for JArray
    data[1, :] = max[:] # Slice needed for JArray
    return data


def _rectangle_mask_to_layer(mask):
    layer = Shapes()
    layer.add_rectangles(_rectangle_mask_to_data(mask))
    return layer


# -- Polygons -- ##


def _polygon_data_to_mask(points):
    pts = [realPoint_from(x) for x in points]
    ptList = ArrayList(pts)
    return ClosedWritablePolygon2D(ptList)


def _polygon_mask_to_data(mask):
    """
    Polygons are described in the Shapes layer as a set of points.
    This is all a Polyshape is, so a mask's data is just the Polyshape's data.
    """
    return _polyshape_to_layer_data(mask)


def _polygon_mask_to_layer(mask):
    layer = Shapes()
    layer.add_polygons(_polygon_mask_to_data(mask))
    return layer


# -- Lines -- ##


def _line_data_to_mask(points):
    start = realPoint_from(points[0])
    end = realPoint_from(points[1])
    return DefaultWritableLine(start, end)


def _line_mask_to_data(mask):
    num_dims = mask.numDimensions()
    arr = JArray(JDouble)(int(num_dims))
    data = np.zeros((2, num_dims))
    # First point
    mask.endpointOne().localize(arr)
    data[0, :] = arr
    # Second point
    mask.endpointTwo().localize(arr)
    data[1, :] = arr
    return data


def _line_mask_to_layer(mask):
    # Create Shapes layer
    layer = Shapes()
    layer.add_lines(_line_mask_to_data(mask))
    return layer


# -- Paths -- ##


def _path_data_to_mask(points):
    pts = [realPoint_from(x) for x in points]
    ptList = ArrayList(pts)
    return DefaultWritablePolyline(ptList)


def _path_mask_to_data(mask):
    """
    Paths are described in the Shapes layer as a set of points.
    This is all a Polyshape is, so a mask's data is just the Polyshape's data.
    """
    return _polyshape_to_layer_data(mask)


def _path_mask_to_layer(mask):
    layer = Shapes()
    layer.add_paths(_path_mask_to_data(mask))
    return layer


# -- Shapes / ROITrees -- #


def _roitree_to_layer(roitree):
    layer = Shapes()
    rois = [child.data() for child in roitree.children()]
    for roi in rois:
        if isinstance(roi, SuperEllipsoid.class_):
            layer.add_ellipses(_ellipse_mask_to_data(roi))
        elif isinstance(roi, Box.class_):
            layer.add_rectangles(_rectangle_mask_to_data(roi))
        elif isinstance(roi, Polygon2D.class_):
            layer.add_polygons(_polygon_mask_to_data(roi))
        elif isinstance(roi, Line.class_):
            layer.add_lines(_line_mask_to_data(roi))
        elif isinstance(roi, Polyline.class_):
            layer.add_paths(_path_mask_to_data(roi))
        else:
            raise NotImplementedError(f'Cannot convert {roi}: conversion not implemented!')
    return layer


def _layer_to_roitree(layer: Shapes):
    """Converts a Shapes layer to a RealMask or a list of them."""
    masks = ArrayList()
    for pts, shape_type in zip(layer.data, layer.shape_type):
        if shape_type == 'ellipse':
            shape = _ellipse_data_to_mask(pts)
        elif shape_type == 'rectangle':
            shape = _rectangle_data_to_mask(pts)
        elif shape_type == 'polygon':
            shape = _polygon_data_to_mask(pts)
        elif shape_type == 'line':
            shape = _line_data_to_mask(pts)
        elif shape_type == 'path':
            shape = _path_data_to_mask(pts)
        else:
            raise NotImplementedError(f"Shape type {shape_type} cannot yet be converted!")
        masks.add(shape)
    rois = DefaultROITree()
    rois.addROIs(masks)
    return rois


# -- Points / RealPointCollection -- #


def _points_to_realpointcollection(points):
    pts = [realPoint_from(x) for x in points.data]
    ptList = ArrayList(pts)
    return DefaultWritableRealPointCollection(ptList)


def _realpointcollection_to_points(collection):
    data = np.zeros((collection.size(), collection.numDimensions()))
    tmp_arr_dims = int(collection.numDimensions())
    tmp_arr = JArray(JDouble)(tmp_arr_dims)
    for i, pt in enumerate(collection.points()):
        pt.localize(tmp_arr)
        data[i, :] = tmp_arr
    return Points(data=data)


# -- Converters -- #


def _napari_to_java_converters() -> List[Converter]:
    return [
        Converter(
            predicate=lambda obj: isinstance(obj, Labels),
            converter=lambda obj: _layer_to_imglabeling(obj),
            priority=Priority.VERY_HIGH
        ),
        Converter(
            predicate=lambda obj: isinstance(obj, Shapes),
            converter=lambda obj: _layer_to_roitree(obj),
            priority=Priority.VERY_HIGH
        ),
        Converter(
            predicate=lambda obj: isinstance(obj, Points),
            converter=_points_to_realpointcollection,
            priority=Priority.VERY_HIGH + 1
        ),
    ]


def _java_to_napari_converters() -> List[Converter]:
    return [
        Converter(
            predicate=lambda obj: isinstance(obj, ImgLabeling.class_),
            converter=lambda obj: _imglabeling_to_layer(obj),
            priority=Priority.VERY_HIGH
        ),
        Converter(
            predicate=lambda obj: isinstance(obj, SuperEllipsoid.class_),
            converter=_ellipse_mask_to_layer,
            priority=Priority.VERY_HIGH
        ),
        Converter(
            predicate=lambda obj: isinstance(obj, Box.class_),
            converter=_rectangle_mask_to_layer,
            priority=Priority.VERY_HIGH
        ),
        Converter(
            predicate=lambda obj: isinstance(obj, Polygon2D.class_),
            converter=_polygon_mask_to_layer,
            priority=Priority.VERY_HIGH
        ),
        Converter(
            predicate=lambda obj: isinstance(obj, Line.class_),
            converter=_line_mask_to_layer,
            priority=Priority.VERY_HIGH
        ),
        Converter(
            predicate=lambda obj: isinstance(obj, Polyline.class_),
            converter=_path_mask_to_layer,
            priority=Priority.VERY_HIGH
        ),
        Converter(
            predicate=lambda obj: isinstance(obj, ROITree.class_),
            converter=_roitree_to_layer,
            priority=Priority.VERY_HIGH + 1
        ),
        Converter(
            predicate=lambda obj: isinstance(obj, RealPointCollection.class_),
            converter=_realpointcollection_to_points,
            priority=Priority.VERY_HIGH + 1
        ),
    ]

# -- Java classes -- #
class Java_Class(object):

    def __init__(self, name: str):
        self._name = name

    @property
    def class_(self):
        return java_import(self._name)
    
    def __call__(self, *args):
        return self.class_(*args)


Double: Java_Class = Java_Class('java.lang.Double')

ArrayList: Java_Class = Java_Class('java.util.ArrayList')

LabelingIOService: Java_Class = Java_Class('io.scif.labeling.LabelingIOService')

DefaultROITree: Java_Class = Java_Class('net.imagej.roi.DefaultROITree')

SuperEllipsoid: Java_Class = Java_Class('net.imglib2.roi.geom.real.SuperEllipsoid')

Box: Java_Class = Java_Class('net.imglib2.roi.geom.real.Box')

Polygon2D: Java_Class = Java_Class('net.imglib2.roi.geom.real.Polygon2D')

Line: Java_Class = Java_Class('net.imglib2.roi.geom.real.Line')

Polyline: Java_Class = Java_Class('net.imglib2.roi.geom.real.Polyline')

ROITree: Java_Class = Java_Class('net.imagej.roi.ROITree')

ClosedWritableEllipsoid: Java_Class = Java_Class('net.imglib2.roi.geom.real.ClosedWritableEllipsoid')

ClosedWritablePolygon2D: Java_Class = Java_Class('net.imglib2.roi.geom.real.ClosedWritablePolygon2D')

ClosedWritableBox: Java_Class = Java_Class('net.imglib2.roi.geom.real.ClosedWritableBox')

DefaultWritableLine: Java_Class = Java_Class('net.imglib2.roi.geom.real.DefaultWritableLine')

DefaultWritablePolyline: Java_Class = Java_Class('net.imglib2.roi.geom.real.DefaultWritablePolyline')

ImgLabeling: Java_Class = Java_Class('net.imglib2.roi.labeling.ImgLabeling')

RealPoint: Java_Class = Java_Class('net.imglib2.RealPoint')

RealPointCollection: Java_Class = Java_Class('net.imglib2.roi.geom.real.RealPointCollection')

DefaultWritableRealPointCollection: Java_Class = Java_Class('net.imglib2.roi.geom.real.DefaultWritableRealPointCollection')

def init_napari_converters():
    """
    Adds all converters to the ScyJava converter framework.
    :param ij: An ImageJ gateway
    """
    # Add napari -> Java converters
    for converter in _napari_to_java_converters():
        add_java_converter(converter)

    # Add Java -> napari converters
    for converter in _java_to_napari_converters():
        add_py_converter(converter)

# Install napari <-> java converters
when_jvm_starts(lambda: init_napari_converters())
