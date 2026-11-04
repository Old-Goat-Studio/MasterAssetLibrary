# SPDX-License-Identifier: Apache-2.0
"""The selected asset, shown or played: a picture; a font's sample; a sound; a model turning, or
a texture set as a material on a sphere (both in 3D, through Qt Quick 3D: drag to turn, the wheel
to zoom, double-click to start again)."""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QPixmap, QVector3D
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .gltf_bounds import model_bounds
from .library_format import Asset
from .roles import IMAGES, TEXTURE_ROLES, texture_set

PLAYER_SIZE = (360, 300)
MODELS = (".glb", ".gltf")
SOUNDS = (".ogg", ".opus", ".wav", ".mp3", ".flac")
FONTS = (".ttf", ".otf")
SHOWN_PICTURES = (".png", ".jpg", ".jpeg")  # (.ktx2 isn't one Qt reads)

# The 3D view: a model (RuntimeLoader, framed by its bounds) or a material on a sphere.
SCENE_QML = r"""
import QtQuick
import QtQuick3D
import QtQuick3D.AssetUtils

Rectangle {
    id: root
    color: "#283038"
    property string mode: ""            // "model", "material" or ""
    property url modelSource: ""
    property url colorMap: ""
    property url normalMap: ""
    property url roughnessMap: ""
    property url metallicMap: ""
    property url combinedMap: ""        // glTF's: roughness in green, metallic in blue
    property url occlusionMap: ""
    property url emissiveMap: ""
    property real angle: 0
    property real pitch: 15
    property real zoom: 1
    property bool turning: true
    property int status: loader.status  // RuntimeLoader.Empty, Success or Error
    property string error: loader.errorString

    // The model's box (read from its file by Python: the loader's own bounds stay empty).
    property vector3d lo: Qt.vector3d(-0.5, -0.5, -0.5)
    property vector3d hi: Qt.vector3d(0.5, 0.5, 0.5)
    property real size: Math.max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z, 0.001)

    function reset() { angle = 0; pitch = 15; zoom = 1 }

    NumberAnimation on angle {
        running: root.turning && root.mode !== ""
        from: root.angle; to: root.angle + 360; duration: 12000; loops: Animation.Infinite
    }

    View3D {
        anchors.fill: parent
        environment: SceneEnvironment {
            clearColor: "#283038"
            backgroundMode: SceneEnvironment.Color
            antialiasingMode: SceneEnvironment.MSAA
        }
        DirectionalLight { eulerRotation.x: -40; eulerRotation.y: 30; brightness: 1.3 }
        DirectionalLight { eulerRotation.x: 15; eulerRotation.y: 210; brightness: 0.45 }
        Node {
            position: Qt.vector3d((root.lo.x + root.hi.x) / 2, (root.lo.y + root.hi.y) / 2,
                                  (root.lo.z + root.hi.z) / 2)
            eulerRotation.y: root.angle
            Node {
                eulerRotation.x: -root.pitch
                PerspectiveCamera {
                    id: camera
                    z: root.size * 1.7 / root.zoom
                    clipNear: root.size * 0.01
                    clipFar: root.size * 100
                    fieldOfView: 40
                }
            }
        }
        camera: camera
        RuntimeLoader {
            id: loader
            source: root.mode === "model" ? root.modelSource : ""
        }
        Model {
            visible: root.mode === "material"
            source: "#Sphere"
            scale: Qt.vector3d(0.01, 0.01, 0.01)
            materials: PrincipledMaterial {
                baseColor: "white"
                baseColorMap: root.colorMap != "" ? colorTexture : null
                normalMap: root.normalMap != "" ? normalTexture : null
                roughness: root.combinedMap != "" || root.roughnessMap != "" ? 1.0 : 0.5
                roughnessMap: root.combinedMap != "" ? combinedTexture
                              : root.roughnessMap != "" ? roughnessTexture : null
                roughnessChannel: root.combinedMap != "" ? Material.G : Material.R
                metalness: root.combinedMap != "" || root.metallicMap != "" ? 1.0 : 0.0
                metalnessMap: root.combinedMap != "" ? combinedTexture
                              : root.metallicMap != "" ? metallicTexture : null
                metalnessChannel: root.combinedMap != "" ? Material.B : Material.R
                occlusionMap: root.occlusionMap != "" ? occlusionTexture : null
                emissiveMap: root.emissiveMap != "" ? emissiveTexture : null
                emissiveFactor: root.emissiveMap != "" ? Qt.vector3d(1, 1, 1)
                                                       : Qt.vector3d(0, 0, 0)
            }
            Texture { id: colorTexture; source: root.colorMap }
            Texture { id: normalTexture; source: root.normalMap }
            Texture { id: roughnessTexture; source: root.roughnessMap }
            Texture { id: metallicTexture; source: root.metallicMap }
            Texture { id: combinedTexture; source: root.combinedMap }
            Texture { id: occlusionTexture; source: root.occlusionMap }
            Texture { id: emissiveTexture; source: root.emissiveMap }
        }
    }
    DragHandler {
        target: null
        property real startAngle: 0
        property real startPitch: 0
        onActiveChanged: if (active) { startAngle = root.angle; startPitch = root.pitch;
                                       root.turning = false }
        onTranslationChanged: {
            root.angle = startAngle - translation.x * 0.5
            root.pitch = Math.max(-80, Math.min(80, startPitch + translation.y * 0.5))
        }
    }
    WheelHandler {
        onWheel: (event) => root.zoom = Math.max(0.3, Math.min(6,
                     root.zoom * Math.pow(1.1, event.angleDelta.y / 120)))
    }
    TapHandler { onDoubleTapped: root.reset() }
}
"""


def choices(asset: Asset | None) -> list[tuple[str, str, Path | None]]:
    """What an asset holds that can be shown: (label, kind, file). A texture set's material
    first, then its models, sounds and fonts, then its pictures."""
    if asset is None:
        return []
    paths = [asset.folder / f["path"] for f in asset.files]
    out: list[tuple[str, str, Path | None]] = []
    roles = texture_set(paths) if asset.type == "textures" else {}
    if roles:
        out.append(("Material (all maps)", "material", None))
    for p in paths:
        ext = p.suffix.lower()
        if ext in MODELS:
            out.append((p.name, "model", p))
        elif ext in SOUNDS:
            out.append((p.name, "sound", p))
        elif ext in FONTS:
            out.append((p.name, "font", p))
    by_path = {path: role for role, path in roles.items()}
    for p in paths:
        if p.suffix.lower() in SHOWN_PICTURES:
            role = by_path.get(p)
            out.append((f"{p.name} ({TEXTURE_ROLES[role].lower()})" if role else p.name,
                        "picture", p))
    return out


class AssetPlayer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(PLAYER_SIZE[0])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        self.stack.setMinimumSize(*PLAYER_SIZE)
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setWordWrap(True)
        self.stack.addWidget(self.picture)
        self._scene = None  # the 3D view, made the first time it is needed (False: can't be)
        self.scene_error = ""
        layout.addWidget(self.stack, 1)
        controls = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(self._play)
        controls.addWidget(self.play_button)
        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.sliderMoved.connect(self._seek)
        controls.addWidget(self.position, 1)
        self.time = QLabel()
        controls.addWidget(self.time)
        layout.addLayout(controls)
        self.kind = ""  # "", "picture", "font", "sound", "model", "material"
        self.asset: Asset | None = None
        self.shown: Path | None = None
        self._audio = None
        self.show_asset(None)

    # ---- what it shows ----------------------------------------------------------------------
    def show_asset(self, asset: Asset | None) -> None:
        """An asset, its first showable thing shown."""
        self.asset = asset
        found = choices(asset)
        if not found:
            self._nothing("Select an asset to see it." if asset is None
                          else "Nothing in it can be shown here.")
            return
        _label, kind, path = found[0]
        if kind == "material":
            self.show_material()
        else:
            self.show_file(path)

    def show_file(self, path: Path) -> None:
        self.stop()
        self.shown = path
        ext = path.suffix.lower()
        if ext in MODELS:
            self._show_model(path)
        elif ext in SOUNDS:
            self._show_sound(path)
        elif ext in FONTS:
            self._show_font(path)
        elif ext in IMAGES:
            self._show_picture(path)
        else:
            self._nothing(f"{path.name} can't be shown here.")
        self._controls()

    def show_material(self) -> None:
        """The texture set's maps together, on a sphere."""
        self.stop()
        self.shown = None
        roles = texture_set([self.asset.folder / f["path"] for f in self.asset.files])
        scene = self._scene_view()
        if scene is None:
            if "color" in roles:
                self._show_picture(roles["color"])
            self._controls()
            return
        root = scene.rootObject()
        for role, prop in (("color", "colorMap"), ("normal", "normalMap"),
                           ("roughness", "roughnessMap"), ("metallic", "metallicMap"),
                           ("metallic_roughness", "combinedMap"),
                           ("occlusion", "occlusionMap"), ("emissive", "emissiveMap")):
            path = roles.get(role)
            root.setProperty(prop, QUrl.fromLocalFile(str(path)) if path else QUrl())
        root.setProperty("lo", QVector3D(-0.5, -0.5, -0.5))
        root.setProperty("hi", QVector3D(0.5, 0.5, 0.5))
        root.setProperty("mode", "material")
        root.setProperty("turning", True)
        self.kind = "material"
        self.stack.setCurrentWidget(scene)
        self._controls()

    def _nothing(self, text: str) -> None:
        self.stop()
        self.kind = ""
        self.picture.setPixmap(QPixmap())
        self.picture.setText(text)
        self.stack.setCurrentWidget(self.picture)
        self._controls()

    def _show_picture(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._nothing(f"{path.name} can't be shown here.")
            return
        self.kind = "picture"
        self.picture.setFont(QFont())
        self.picture.setPixmap(pixmap.scaled(*PLAYER_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))
        self.stack.setCurrentWidget(self.picture)

    def _show_font(self, path: Path) -> None:
        family_id = QFontDatabase.addApplicationFont(str(path))
        families = QFontDatabase.applicationFontFamilies(family_id) if family_id >= 0 else []
        if not families:
            self._nothing(f"{path.name} can't be read as a font.")
            return
        self.kind = "font"
        self.picture.setPixmap(QPixmap())
        self.picture.setFont(QFont(families[0], 20))
        self.picture.setText(f"{families[0]}\nThe quick brown fox jumps over the lazy dog.\n"
                             "0123456789")
        self.stack.setCurrentWidget(self.picture)

    def _show_sound(self, path: Path) -> None:
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except ImportError:
            self._nothing("Sounds can't be played here.")
            return
        if self._audio is None:
            player, output = QMediaPlayer(self), QAudioOutput(self)
            player.setAudioOutput(output)
            player.durationChanged.connect(lambda ms: self.position.setRange(0, int(ms)))
            player.positionChanged.connect(self._audio_moved)
            self._audio = (player, output)
        self._audio[0].setSource(QUrl.fromLocalFile(str(path)))
        self.kind = "sound"
        self.picture.setPixmap(QPixmap())
        self.picture.setFont(QFont())
        self.picture.setText(f"♪  {path.name}")
        self.stack.setCurrentWidget(self.picture)
        self._audio_moved(0)

    def _show_model(self, path: Path) -> None:
        scene = self._scene_view()
        if scene is None:
            self._nothing("Models can't be shown here (no 3D).")
            return
        root = scene.rootObject()
        lo, hi = model_bounds(path) or ([-0.5, -0.5, -0.5], [0.5, 0.5, 0.5])
        root.setProperty("lo", QVector3D(*lo))
        root.setProperty("hi", QVector3D(*hi))
        root.setProperty("mode", "model")
        root.setProperty("modelSource", QUrl.fromLocalFile(str(path)))
        root.setProperty("turning", True)
        root.reset()
        self.kind = "model"
        self.stack.setCurrentWidget(scene)

    def _scene_view(self):
        """The 3D view (a QQuickWidget), or None where Qt Quick 3D can't run."""
        if self._scene is not None:
            return self._scene or None
        try:
            from PySide6.QtQuickWidgets import QQuickWidget
            view = QQuickWidget()
            view.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            view.setMinimumSize(*PLAYER_SIZE)
            from PySide6.QtQml import QQmlComponent
            component = QQmlComponent(view.engine())
            component.setData(SCENE_QML.encode("utf-8"), QUrl("player.qml"))
            root = component.create()
            if root is None:
                raise RuntimeError("; ".join(e.toString() for e in component.errors()))
            view.setContent(QUrl("player.qml"), component, root)
        except (ImportError, RuntimeError) as e:
            self._scene = False  # (tried: no 3D here)
            self.scene_error = str(e)
            return None
        self._scene = view
        self.stack.addWidget(view)
        return view

    def scene_root(self):
        return self._scene.rootObject() if self._scene else None

    # ---- playing ----------------------------------------------------------------------------
    def _controls(self) -> None:
        sound = self.kind == "sound"
        turning = self.kind in ("model", "material")
        self.play_button.setVisible(sound or turning)
        self.play_button.blockSignals(True)
        self.play_button.setChecked(turning)
        self.play_button.setText("Stop" if turning else "Play")
        self.play_button.blockSignals(False)
        self.position.setVisible(sound)
        self.time.setVisible(sound)

    def _play(self, on: bool) -> None:
        self.play_button.setText("Stop" if on else "Play")
        if self.kind == "sound" and self._audio is not None:
            (self._audio[0].play if on else self._audio[0].stop)()
        elif self.kind in ("model", "material") and self._scene:
            self._scene.rootObject().setProperty("turning", on)

    def _audio_moved(self, ms: int) -> None:
        if not self.position.isSliderDown():
            self.position.setValue(int(ms))
        total = self._audio[0].duration() if self._audio else 0
        self.time.setText(f"{ms / 1000:.1f} / {total / 1000:.1f} s")

    def _seek(self, ms: int) -> None:
        if self._audio is not None:
            self._audio[0].setPosition(ms)

    def stop(self) -> None:
        if self._audio is not None:
            self._audio[0].stop()
        if self._scene:
            self._scene.rootObject().setProperty("mode", "")
        self.play_button.blockSignals(True)
        self.play_button.setChecked(False)
        self.play_button.setText("Play")
        self.play_button.blockSignals(False)
