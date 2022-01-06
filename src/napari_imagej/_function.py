"""
This module is an example of a barebones function plugin for napari

It implements the ``napari_experimental_provide_function`` hook specification.
see: https://napari.org/docs/dev/plugins/hook_specifications.html

Replace code below according to your needs.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import napari

import os, re
import imagej
from scyjava import config, jimport
from collections.abc import Mapping
from qtpy.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QScrollArea, QLineEdit, QTableWidget, QAbstractItemView, QHeaderView, QTableWidgetItem, QLabel
from jpype import JObject, JClass, JProxy
from napari_imagej._preprocessor import NapariPreprocessor

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) #TEMP

# config.add_repositories({'scijava.public': 'https://maven.scijava.org/content/groups/public'})
# config.endpoints.append('org.scijava:scijava-common:2.87.1')

logger.debug('Initializing ImageJ2')
config.add_option(f'-Dimagej.dir={os.getcwd()}') #TEMP
ij = imagej.init(headless=False)
ij.log().setLevel(4)
logger.debug(f'Initialized at version {ij.getVersion()}')

Object = jimport('java.lang.Object')
getClass = Object.class_.getMethod('getClass')

def which_class(o):
    return getClass.invoke(o)

# PluginInfo = jimport('org.scijava.plugin.PluginInfo')
# PreprocessorPlugin = jimport('org.scijava.module.process.PreprocessorPlugin')
# JNapariPreprocessor = which_class(NapariPreprocessor())
# napari_preprocessor_info = PluginInfo(JNapariPreprocessor, PreprocessorPlugin)
# pluginService = ij.plugin()
# pluginService.addPlugin(napari_preprocessor_info)

preprocessors = ij.plugin().getPluginsOfClass('org.scijava.module.process.PreprocessorPlugin')
napari_preprocessor = NapariPreprocessor()
napari_preprocessor.context = ij.context()
preprocessors.add(napari_preprocessor)

postprocessors = ij.plugin().getPluginsOfClass('org.scijava.module.process.PostprocessorPlugin')


_ptypes = {
    # Primitives.
    jimport('[B'):                                            int,
    jimport('[S'):                                            int,
    jimport('[I'):                                            int,
    jimport('[J'):                                            int,
    jimport('[F'):                                            float,
    jimport('[D'):                                            float,
    jimport('[Z'):                                            bool,
    jimport('[C'):                                            str,
    # Primitive wrappers.
    jimport('java.lang.Boolean'):                             bool,
    jimport('java.lang.Character'):                           str,
    jimport('java.lang.Byte'):                                int,
    jimport('java.lang.Short'):                               int,
    jimport('java.lang.Integer'):                             int,
    jimport('java.lang.Long'):                                int,
    jimport('java.lang.Float'):                               float,
    jimport('java.lang.Double'):                              float,
    # Core library types.
    jimport('java.math.BigInteger'):                          int,
    jimport('java.lang.String'):                              str,
    jimport('java.lang.Enum'):                                'enum.Enum',
    jimport('java.io.File'):                                  'pathlib.PosixPath',
    jimport('java.nio.file.Path'):                            'pathlib.PosixPath',
    jimport('java.util.Date'):                                'datetime.datetime',
    # SciJava types.
    jimport('org.scijava.table.Table'):                       'pandas.DataFrame',
    # ImgLib2 types.
    jimport('net.imglib2.type.BooleanType'):                  bool,
    jimport('net.imglib2.type.numeric.IntegerType'):          int,
    jimport('net.imglib2.type.numeric.RealType'):             float,
    jimport('net.imglib2.type.numeric.ComplexType'):          complex,
    jimport('net.imglib2.RandomAccessibleInterval'):          'napari.types.ImageData',
    jimport('net.imglib2.roi.geom.real.PointMask'):           'napari.types.PointsData',
    jimport('net.imglib2.roi.geom.real.RealPointCollection'): 'napari.types.PointsData',
    jimport('net.imglib2.roi.labeling.ImgLabeling'):          'napari.types.LabelsData',
    jimport('net.imglib2.roi.geom.real.Line'):                'napari.types.ShapesData',
    jimport('net.imglib2.roi.geom.real.Box'):                 'napari.types.ShapesData',
    jimport('net.imglib2.roi.geom.real.SuperEllipsoid'):      'napari.types.ShapesData',
    jimport('net.imglib2.roi.geom.real.Polygon2D'):           'napari.types.ShapesData',
    jimport('net.imglib2.roi.geom.real.Polyline'):            'napari.types.ShapesData',
    jimport('net.imglib2.display.ColorTable'):                'vispy.color.Colormap',
    # ImageJ2 types.
    jimport('net.imagej.mesh.Mesh'):                          'napari.types.SurfaceData'
}

# TODO: Move this function to scyjava.convert and/or ij.py.
def _ptype(java_type):
    for jtype, ptype in _ptypes.items():
        if jtype.class_.isAssignableFrom(java_type): return ptype
    for jtype, ptype in _ptypes.items():
        if ij.convert().supports(java_type, jtype): return ptype
    raise ValueError(f'Unsupported Java type: {java_type}')


def _return_type(info):
    out_types = [o.getType() for o in info.outputs()]
    if len(out_types) == 0: return None
    if len(out_types) == 1: return _ptype(out_types[0])
    return dict


def _usable(info):
    #if not info.canRunHeadless(): return False
    menu_path = info.getMenuPath()
    return menu_path is not None and len(menu_path) > 0


# Credit: https://gist.github.com/xhlulu/95117e225b7a1aa806e696180a72bdd0

def _functionify(info):
    def run_module(**kwargs):
        args = kwargs #locals()
        logger.debug(f'run_module: {run_module.__qualname__}({args}) -- {info.getIdentifier()}')
        m = ij.module().run(info, True, ij.py.jargs(args)).get()
        logger.debug(f'run_module: execution complete')
        outputs = ij.py.from_java(m.getOutputs())
        result = outputs.popitem()[1] if len(outputs) == 1 else outputs
        logger.debug(f'run_module: result = {result}')
        return result

    menu_string = " > ".join(str(p) for p in info.getMenuPath())
    run_module.__doc__ = f"Invoke ImageJ2's {menu_string} command"
    run_module.__name__ = re.sub('[^a-zA-Z0-9_]', '_', menu_string)
    run_module.__qualname__ = menu_string

    # Rewrite the function signature to match the module inputs.
    from inspect import signature, Parameter
    try:
        sig = signature(run_module)
        run_module.__signature__ = sig.replace(parameters=[
            Parameter(
                str(i.getName()),
                kind=Parameter.POSITIONAL_OR_KEYWORD,
                annotation=_ptype(i.getType())
            )
            for i in info.inputs()
        ], return_annotation=_return_type(info))
    except Exception as e:
        print(e)

    # Add the type hints as annotations metadata as well.
    # Without this, magicgui doesn't pick up on the types.
    type_hints = {str(i.getName()): _ptype(i.getType()) for i in info.inputs()}
    out_types = [o.getType() for o in info.outputs()]
    type_hints['return'] = _ptype(out_types[0]) if len(out_types) == 1 else dict
    run_module.__annotation__ = type_hints

    run_module._info = info
    return run_module


def napari_experimental_provide_function():
    logger.debug('Converting SciJava modules to Python functions')
    functions = [_functionify(info) for info in ij.module().getModules() if _usable(info)]
    # TODO: Sort by menu weight rather than function name.
    return sorted(functions, key=lambda f: f.__name__)

class ExampleQWidget(QWidget):

    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer

        self.setLayout(QVBoxLayout())

        ## Search Bar
        searchWidget = QWidget()
        searchWidget.setLayout(QHBoxLayout())
        searchWidget.layout().addWidget(self._generate_searchbar())
        
        # TODO: Do we want a button?
        # btn = QPushButton("Search")
        # btn.clicked.connect(self._on_click)
        # searchWidget.layout().addWidget(btn)

        self.layout().addWidget(searchWidget)

        self.searcher = self._generate_searcher()
        self.searchService = self._generate_search_service()

        ## Results box
        labels = ['Module: ']
        self.results = []
        self.maxResults = 12
        self.tableWidget = QTableWidget(self.maxResults, len(labels))
        self.tableWidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableWidget.setHorizontalHeaderLabels(labels)
        self.tableWidget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tableWidget.verticalHeader().hide()
        self.tableWidget.setShowGrid(False)
        self.tableWidget.cellClicked.connect(self._highlight_module)
        self.layout().addWidget(self.tableWidget)

        ## Module highlighter
        self.focus_widget = QWidget()
        self.focus_widget.setLayout(QVBoxLayout())
        self.focused_module = QLabel()
        self.focus_widget.layout().addWidget(self.focused_module)
        self.focused_module.setText("Display Module Here")
        self.layout().addWidget(self.focus_widget)
        self.focused_action_buttons = []

    def _generate_searchbar(self):
        searchbar = QLineEdit()
        searchbar.textChanged.connect(self._search)
        # TODO: On a Return, we might just want to select the top result
        return searchbar

    def _generate_searcher(self):
        pluginService = ij.get('org.scijava.plugin.PluginService')
        moduleServiceCls = jimport('org.scijava.search.module.ModuleSearcher')
        searcherCls = jimport('org.scijava.search.Searcher')
        info = pluginService.getPlugin(moduleServiceCls, searcherCls)
        searcher = info.createInstance()
        ij.context().inject(searcher)
        return searcher

    def _generate_search_service(self):
        return ij.get('org.scijava.search.SearchService')

    def _on_click(self):
        print("napari has", len(self.viewer.layers), "layers")

    def _search(self, text):
        # TODO: Consider adding a button to toggle fuzziness
        breakpoint()
        self.results = self.searcher.search(text, True)
        for i in range(len(self.results)):
            name = ij.py.from_java(self.results[i].name())
            self.tableWidget.setItem(i, 0, QTableWidgetItem(name))
        for i in range(len(self.results), self.maxResults):
            self.tableWidget.setItem(i, 0, QTableWidgetItem(""))

    def _highlight_module(self, row: int, col: int):
        # Print highlighted module
        name = ij.py.from_java(self.results[row].name())
        self.focused_module.setText(name)

        # Create buttons for each action
        self.focused_actions = self.searchService.actions(self.results[row])
        activated_actions = len(self.focused_action_buttons)
        # Hide buttons if we have more than needed
        while activated_actions > len(self.focused_actions):
            activated_actions = activated_actions - 1
            self.focused_action_buttons[activated_actions].hide()
        # Create buttons if we need more than we have
        while len(self.focused_action_buttons) < len(self.focused_actions):
            button = QPushButton()
            self.focused_action_buttons.append(button)
            self.focus_widget.layout().addWidget(button)
        # Rename buttons to reflect focused module's actions
        for i in range(len(self.focused_actions)):
            action_name = ij.py.from_java(self.focused_actions[i].toString())
            self.focused_action_buttons[i].setText(action_name)
            self.focused_action_buttons[i].clicked.connect(lambda : ij.module().run(self.results[row].info(), preprocessors, postprocessors, JObject({}, JClass('java.util.Map'))))
            self.focused_action_buttons[i].show()
