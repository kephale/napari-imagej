from typing import Generator

import pytest
from napari import Viewer

from napari_imagej.widget import ImageJWidget
from napari_imagej.widget_IJ2 import GUIWidget


@pytest.fixture(scope="module")
def ij():
    from napari_imagej.setup_imagej import ij

    return ij()


@pytest.fixture
def imagej_widget(make_napari_viewer) -> Generator[ImageJWidget, None, None]:
    # Create widget

    viewer: Viewer = make_napari_viewer()
    ij_widget: ImageJWidget = ImageJWidget(viewer)

    yield ij_widget

    # Cleanup -> Close the widget, trigger ImageJ shutdown
    ij_widget.close()


@pytest.fixture
def gui_widget(make_napari_viewer) -> Generator[GUIWidget, None, None]:
    # Create widget

    viewer: Viewer = make_napari_viewer()
    widget: GUIWidget = GUIWidget(viewer)

    yield widget

    # Cleanup -> Close the widget, trigger ImageJ shutdown
    widget.close()
