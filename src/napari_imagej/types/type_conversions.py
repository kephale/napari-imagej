from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from scyjava import Priority

from napari_imagej.setup_imagej import ij, jc
from napari_imagej.types.mappings import ptypes
from napari_imagej.types.placeholders import TypePlaceholders


@lru_cache(maxsize=None)
def type_placeholders() -> Dict[Any, Any]:
    """
    Lazily creates a map of type placeholders.
    This object is then cached upon function return,
    effectively making this function a lazily initialized field.

    This object should be lazily initialized as it will import java classes.
    Those Java classes should not be imported until ImageJ has been able to set
    up the JVM, adding its required JARs to the classpath. For that reason,
    java class importing is done with java_import, which blocks UNTIL the imagej
    gateway has been created (in a separate thread). Thus, prematurely calling this
    function would block the calling thread.

    By lazily initializing this function, we minimize the time this thread is blocked.
    """
    return TypePlaceholders()


# List of Module Item Converters, along with their priority
_MODULE_ITEM_CONVERTERS: List[Tuple[Callable, int]] = []


def module_item_converter(
    priority: int = Priority.NORMAL,
) -> Callable[["jc.ModuleInfo"], Callable]:
    """
    A decorator used to register the annotated function among the
    available module item converters
    :param priority: How much this converter should be prioritized
    :return: The annotated function
    """

    def converter(func: Callable):
        """Registers the annotated function with its priority"""
        _MODULE_ITEM_CONVERTERS.append((func, priority))
        return func

    return converter


# TODO: Move this function to scyjava.convert and/or ij.py.
def python_type_of(module_item: "jc.ModuleItem"):
    """Returns the Python type associated with the passed ModuleItem."""
    for converter, _ in sorted(
        _MODULE_ITEM_CONVERTERS, reverse=True, key=lambda x: x[1]
    ):
        converted = converter(module_item)
        if converted is not None:
            return converted
    raise ValueError(
        (
            f"Unsupported Java Type: {module_item.getType()}. "
            "Let us know about the failure at https://forum.image.sc, "
            "or file an issue at https://github.com/imagej/napari-imagej!"
        )
    )


@module_item_converter(priority=Priority.HIGH)
def placeholder_converter(item: "jc.ModuleItem"):
    """
    Checks to see if this type can be satisfied by a placeholder.
    For a placeholder to work, it MUST be a pure input.
    This is because the python type has no functionality, as it is just an Enum choice.
    """
    if item.isInput() and not item.isOutput():
        java_type = item.getType()
        return type_placeholders().get(java_type, None)


def _checkerUsingFunc(
    item: "jc.ModuleItem", func: Callable[[Type, Type], bool]
) -> Optional[Type]:
    """
    The logic of this checker is as follows:

    type_mappings().ptypes.items() contains (java_type, python_type) pairs.
    These pairs are considered to be equivalent types; i.e. we can freely
    convert between these types.

    There are 3 cases:
    1) The ModuleItem is a PURE INPUT:
        We can satisfy item with an object of ptype IF its corresponding
        jtype can be converted to item's type. The conversion then goes
        ptype -> jtype -> java_type
    2) The ModuleItem is a PURE OUTPUT:
        We can satisfy item with ptype IF java_type can be converted to jtype.
        Then jtype can be converted to ptype. The conversion then goes
        java_type -> jtype -> ptype
    3) The ModuleItem is BOTH:
        We can satisfy item with ptype IF we satisfy both 1 and 2.
        ptype -> jtype -> java_type -> jtype -> ptype

    :param item: the ModuleItem we'd like to convert
    :return: the python equivalent of ModuleItem's type, or None if that type
    cannot be converted.
    """
    # Get the type of the Module item
    java_type = item.getType()
    type_pairs = ptypes().items()
    # Case 1
    if item.isInput() and not item.isOutput():
        for jtype, ptype in type_pairs:
            # can we go from jtype to java_type?
            if func(jtype, java_type):
                return ptype
    # Case 2
    elif item.isOutput() and not item.isInput():
        # NB type_pairs is ordered from least to most specific.
        for jtype, ptype in reversed(type_pairs):
            # can we go from java_type to jtype?
            if func(java_type, jtype):
                return ptype
    # Case 3
    elif item.isInput() and item.isOutput():
        for jtype, ptype in type_pairs:
            # can we go both ways?
            if func(java_type, jtype) and func(jtype, java_type):
                return ptype
    # Didn't satisfy any cases!
    return None


@module_item_converter()
def isAssignableChecker(item: "jc.ModuleItem") -> Optional[Type]:
    """
    Determines whether we can simply cast from ptype to item's type java_type
    """

    def isAssignable(from_type, to_type) -> bool:
        # Use Types to get the raw type of each
        from_raw = jc.Types.raw(from_type)
        to_raw = jc.Types.raw(to_type)
        return from_raw.isAssignableFrom(to_raw)

    return _checkerUsingFunc(item, isAssignable)


@module_item_converter(priority=Priority.LOW)
def canConvertChecker(item: "jc.ModuleItem") -> Optional[Type]:
    """
    Determines whether imagej can do a conversion from ptype to item's type java_type.
    """

    def isAssignable(from_type, to_type) -> bool:
        return ij().convert().supports(from_type, to_type)

    return _checkerUsingFunc(item, isAssignable)
