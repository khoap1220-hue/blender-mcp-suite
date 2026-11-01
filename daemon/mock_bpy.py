"""
mock_bpy.py — Pure Python Mock Implementation of Blender 4.1 bpy & mathutils
Enables 100% offline testing of Blender MCP operations and E2E suites.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union


# ==============================================================================
# mathutils Mock
# ==============================================================================

class Vector(list):
    def __init__(self, vals=(0.0, 0.0, 0.0)) -> None:
        super().__init__([float(x) for x in vals])

    @property
    def x(self) -> float:
        return self[0]

    @x.setter
    def x(self, v: float) -> None:
        self[0] = float(v)

    @property
    def y(self) -> float:
        return self[1]

    @y.setter
    def y(self, v: float) -> None:
        self[1] = float(v)

    @property
    def z(self) -> float:
        return self[2]

    @z.setter
    def z(self, v: float) -> None:
        self[2] = float(v)


class Euler(list):
    def __init__(self, vals=(0.0, 0.0, 0.0)) -> None:
        super().__init__([float(x) for x in vals])


class Color(list):
    def __init__(self, vals=(1.0, 1.0, 1.0)) -> None:
        super().__init__([float(x) for x in vals])


class Matrix:
    def __init__(self, rows: Optional[List[List[float]]] = None) -> None:
        self.rows = rows or [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]

    @classmethod
    def Identity(cls, n: int = 4) -> Matrix:
        return cls([[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)])

    def inverted(self) -> Matrix:
        return Matrix()


# ==============================================================================
# Blender Data Structures Mock
# ==============================================================================

class MockNamedList:
    def __init__(self) -> None:
        self._items: List[Any] = []

    def __iter__(self) -> Iterator[Any]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, key: Union[int, str]) -> Any:
        if isinstance(key, int):
            return self._items[key]
        for item in self._items:
            if getattr(item, "name", None) == key:
                return item
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        if isinstance(key, str):
            return any(getattr(item, "name", None) == key for item in self._items)
        return key in self._items

    def get(self, key: str, default: Any = None) -> Any:
        for item in self._items:
            if getattr(item, "name", None) == key:
                return item
        return default

    def append(self, item: Any) -> None:
        self._items.append(item)

    def link(self, item: Any) -> None:
        if item not in self._items:
            self._items.append(item)

    def unlink(self, item: Any) -> None:
        if item in self._items:
            self._items.remove(item)

    def remove(self, item: Any, do_unlink: bool = True) -> None:
        if item in self._items:
            self._items.remove(item)

    def new(self, name: str = "", *args: Any, **kwargs: Any) -> Any:
        c_type = kwargs.get("type", name or "TRACK_TO")
        c_name = kwargs.get("name", name or "Constraint")
        if "type" in kwargs or c_type in ("TRACK_TO", "IK", "COPY_LOCATION", "COPY_ROTATION"):
            obj = MockConstraint(c_type, c_name)
        else:
            obj = MockGenericNamed(c_name)
        self._items.append(obj)
        return obj

    def clear(self) -> None:
        self._items.clear()


class MockGenericNamed:
    def __init__(self, name: str = "") -> None:
        self.name = name
        self.identifier = name
        self.head = [0.0, 0.0, 0.0]
        self.tail = [0.0, 0.0, 1.0]
        self.parent = None
        self.use_connect = False


class MockSocket:
    def __init__(self, name: str) -> None:
        self.name = name
        self.default_value: Any = [1.0, 1.0, 1.0, 1.0] if "color" in name.lower() else 0.0
        self.links: List[Any] = []
        self.is_linked: bool = False


class MockNode:
    def __init__(self, name: str, node_type: str = "BSDF_PRINCIPLED") -> None:
        self.name = name
        self.type = node_type
        self.location = [0.0, 0.0]
        self.inputs: Dict[str, MockSocket] = {}
        self.outputs: Dict[str, MockSocket] = {"BSDF": MockSocket("BSDF"), "Color": MockSocket("Color")}

        common_inputs = [
            "Base Color", "Metallic", "Roughness", "IOR", "Alpha",
            "Transmission Weight", "Subsurface Weight", "Emission Color",
            "Emission Strength", "Strength", "Color", "Vector"
        ]
        for inp in common_inputs:
            self.inputs[inp] = MockSocket(inp)


class MockNodeTree:
    def __init__(self) -> None:
        self.nodes = MockNamedList()
        self.links = MockNamedList()
        # Initialize default Principled BSDF and Output Material
        bsdf = MockNode("Principled BSDF", "BSDF_PRINCIPLED")
        out = MockNode("Material Output", "OUTPUT_MATERIAL")
        self.nodes.append(bsdf)
        self.nodes.append(out)

    def new_link(self, output_sock: Any, input_sock: Any) -> Any:
        link = (output_sock, input_sock)
        self.links.append(link)
        if hasattr(input_sock, "is_linked"):
            input_sock.is_linked = True
        return link


class MockDOF:
    def __init__(self) -> None:
        self.use_dof = False
        self.focus_object = None
        self.focus_distance = 10.0
        self.aperture_fstop = 2.8


class MockMaterialSlot:
    def __init__(self, mat: Any = None) -> None:
        self.material = mat


class MockObjectData:
    def __init__(self, obj_type: str = "MESH", name: str = "") -> None:
        self.name = name
        self.type = obj_type
        self.materials: List[Any] = []
        self.vertices: List[Any] = [Vector([0, 0, 0])] * 8
        self.polygons: List[Any] = [1, 2, 3, 4, 5, 6]
        self.edges: List[Any] = [1] * 12
        self.edit_bones = MockNamedList()
        self.bones = MockNamedList()
        self.energy = 1000.0
        self.color = Color([1.0, 1.0, 1.0])
        self.spot_size = 0.785
        self.spot_blend = 0.15
        self.lens = 50.0
        self.sensor_width = 36.0
        self.dof = MockDOF()


class MockConstraint:
    def __init__(self, c_type: str = "TRACK_TO", name: str = "Track To") -> None:
        self.type = c_type
        self.name = name
        self.target: Optional[Any] = None
        self.subtarget = ""
        self.track_axis = "TRACK_NEGATIVE_Z"
        self.up_axis = "UP_Y"
        self.chain_count = 2
        self.pole_target = None
        self.pole_subtarget = ""
        self.pole_angle = 0.0


class MockPoseBone:
    def __init__(self, name: str = "") -> None:
        self.name = name
        self.constraints = MockNamedList()


class MockPose:
    def __init__(self, obj: Any = None) -> None:
        self.obj = obj
        self._bones = MockNamedList()

    @property
    def bones(self) -> MockNamedList:
        if self.obj and self.obj.data and hasattr(self.obj.data, "edit_bones"):
            for eb in self.obj.data.edit_bones:
                if eb.name not in self._bones:
                    self._bones.append(MockPoseBone(eb.name))
        return self._bones


class MockObject:
    def __init__(
        self,
        name: str = "Cube",
        obj_type: str = "MESH",
        location: Any = (0.0, 0.0, 0.0),
        rotation: Any = (0.0, 0.0, 0.0),
        scale: Any = (1.0, 1.0, 1.0),
    ) -> None:
        self.name = name
        self.type = obj_type
        self.location = Vector(location)
        self.rotation_euler = Euler(rotation)
        self.scale = Vector(scale)
        self.dimensions = Vector([2.0, 2.0, 2.0])
        self.bound_box = [
            [-1.0, -1.0, -1.0], [1.0, -1.0, -1.0],
            [1.0, 1.0, -1.0], [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0], [1.0, -1.0, 1.0],
            [1.0, 1.0, 1.0], [-1.0, 1.0, 1.0]
        ]
        self.parent: Optional[MockObject] = None
        self.children: List[MockObject] = []
        self.matrix_world = Matrix()
        self.matrix_parent_inverse = Matrix()
        self.data = MockObjectData(obj_type, name)
        self.constraints = MockNamedList()
        self.pose = MockPose(self)
        self.users_collection: List[Any] = []
        self.modifiers = MockNamedList()
        self.vertex_groups = MockNamedList()
        self._material_slots: List[MockMaterialSlot] = []

    @property
    def material_slots(self) -> List[MockMaterialSlot]:
        if self.data and self.data.materials:
            return [MockMaterialSlot(m) for m in self.data.materials]
        return self._material_slots

    def select_set(self, val: bool) -> None:
        pass


class MockMaterial:
    def __init__(self, name: str = "Material", use_nodes: bool = True) -> None:
        self.name = name
        self.use_nodes = use_nodes
        self.node_tree = MockNodeTree()


class MockWorld:
    def __init__(self, name: str = "World") -> None:
        self.name = name
        self.use_nodes = True
        self.node_tree = MockNodeTree()


class MockCollection:
    def __init__(self, name: str = "Collection") -> None:
        self.name = name
        self.objects = MockNamedList()
        self.children = MockNamedList()


class MockRenderEngineProperty:
    def __init__(self) -> None:
        self.enum_items = [
            MockGenericNamed("CYCLES"),
            MockGenericNamed("BLENDER_EEVEE"),
            MockGenericNamed("BLENDER_EEVEE_NEXT"),
            MockGenericNamed("BLENDER_WORKBENCH"),
        ]


class MockRNA:
    def __init__(self) -> None:
        self.properties = {"engine": MockRenderEngineProperty()}


class MockRenderSettings:
    def __init__(self) -> None:
        self.engine = "CYCLES"
        self.resolution_x = 1920
        self.resolution_y = 1080
        self.filepath = ""
        self.bl_rna = MockRNA()

        class MockImgSettings:
            file_format = "PNG"

        self.image_settings = MockImgSettings()


class MockScene:
    def __init__(self, name: str = "Scene") -> None:
        self.name = name
        self.render = MockRenderSettings()
        self.collection = MockCollection("Scene Collection")
        self.camera: Optional[MockObject] = None
        self.world = MockWorld("World")
        self.frame_current = 1
        self.frame_start = 1
        self.frame_end = 250

        class MockCycles:
            samples = 128
            device = "CPU"

        class MockEevee:
            taa_render_samples = 64

        self.cycles = MockCycles()
        self.eevee = MockEevee()


class MockContext:
    def __init__(self) -> None:
        self.mode = "OBJECT"
        self.scene = MockScene()
        self.active_object: Optional[MockObject] = None
        self.selected_objects: List[MockObject] = []
        self.collection = self.scene.collection

        class MockViewLayerObjects:
            def __init__(self, ctx: MockContext) -> None:
                self._ctx = ctx

            @property
            def active(self) -> Optional[MockObject]:
                return self._ctx.active_object

            @active.setter
            def active(self, obj: Optional[MockObject]) -> None:
                self._ctx.active_object = obj

        class MockViewLayer:
            def __init__(self, ctx: MockContext) -> None:
                self.objects = MockViewLayerObjects(ctx)

        self.view_layer = MockViewLayer(self)


class MockObjectsCollection(MockNamedList):
    def new(self, name: str, object_data: Any = None, data: Any = None, **kw: Any) -> MockObject:
        d = object_data if object_data is not None else data
        obj_type = "MESH"
        if d and hasattr(d, "name"):
            if "Light" in d.name or getattr(d, "energy", None) is not None:
                obj_type = "LIGHT"
            elif "Camera" in d.name or getattr(d, "lens", None) is not None:
                obj_type = "CAMERA"
            elif "Armature" in d.name or getattr(d, "bones", None) is not None:
                obj_type = "ARMATURE"
        obj = MockObject(name=name, obj_type=obj_type)
        if d:
            obj.data = d
        self.append(obj)
        return obj


class MockDataRoot:
    def __init__(self) -> None:
        self.objects = MockObjectsCollection()
        self.materials = MockNamedList()
        self.materials.new = lambda name, **kw: self._create_mat(name, **kw)
        self.lights = MockNamedList()
        self.lights.new = lambda name, light_type="POINT", **kw: self._create_light(name, light_type)
        self.cameras = MockNamedList()
        self.cameras.new = lambda name, **kw: self._create_camera(name)
        self.armatures = MockNamedList()
        self.armatures.new = lambda name, **kw: self._create_armature(name)
        self.collections = MockNamedList()
        self.collections.new = lambda name, **kw: MockCollection(name)
        self.worlds = MockNamedList()
        self.worlds.new = lambda name, **kw: MockWorld(name)

        class MockImages(MockNamedList):
            def load(self, filepath: str, check_existing: bool = True) -> Any:
                img = MockGenericNamed(Path(filepath).name)
                img.filepath = filepath
                self.append(img)
                return img

        self.images = MockImages()

    def _create_mat(self, name: str, **kw: Any) -> MockMaterial:
        mat = MockMaterial(name)
        self.materials.append(mat)
        return mat

    def _create_light(self, name: str, light_type: str = "POINT") -> MockObjectData:
        data = MockObjectData("LIGHT", name)
        self.lights.append(data)
        return data

    def _create_camera(self, name: str) -> MockObjectData:
        data = MockObjectData("CAMERA", name)
        self.cameras.append(data)
        return data

    def _create_armature(self, name: str) -> MockObjectData:
        data = MockObjectData("ARMATURE", name)
        self.armatures.append(data)
        return data

    def reset(self) -> None:
        self.objects.clear()
        self.materials.clear()
        self.lights.clear()
        self.cameras.clear()
        self.collections.clear()
        self.armatures.clear()
        self.images.clear()
        context.active_object = None
        context.selected_objects = []


class MockOps:
    class wm:
        @staticmethod
        def read_homefile(use_empty: bool = True) -> Dict[str, Any]:
            data.reset()
            return {"FINISHED"}

        @staticmethod
        def quit_blender() -> None:
            pass

    class object:
        @staticmethod
        def mode_set(mode: str = "OBJECT") -> Dict[str, Any]:
            context.mode = mode
            return {"FINISHED"}

        @staticmethod
        def empty_add(type: str = "PLAIN_AXES", location: Any = (0, 0, 0), rotation: Any = (0, 0, 0), scale: Any = (1, 1, 1)) -> Dict[str, Any]:
            obj = MockObject("Empty", "EMPTY", location, rotation, scale)
            data.objects.append(obj)
            context.active_object = obj
            return {"FINISHED"}

        @staticmethod
        def select_all(action: str = "DESELECT") -> Dict[str, Any]:
            return {"FINISHED"}

        @staticmethod
        def transform_apply(location: bool = True, rotation: bool = True, scale: bool = True) -> Dict[str, Any]:
            return {"FINISHED"}

        @staticmethod
        def parent_set(type: str = "OBJECT", keep_transform: bool = False) -> Dict[str, Any]:
            return {"FINISHED"}

        @staticmethod
        def delete(use_global: bool = False) -> Dict[str, Any]:
            if context.active_object:
                data.objects.remove(context.active_object)
                context.active_object = None
            return {"FINISHED"}

        @staticmethod
        def duplicate(linked: bool = False) -> Dict[str, Any]:
            if context.active_object:
                old = context.active_object
                new_obj = MockObject(old.name + ".001", old.type, old.location, old.rotation_euler, old.scale)
                data.objects.append(new_obj)
                context.active_object = new_obj
            return {"FINISHED"}

    class mesh:
        @staticmethod
        def _add(prim: str, location: Any = (0, 0, 0), rotation: Any = (0, 0, 0), scale: Any = (1, 1, 1)) -> Dict[str, Any]:
            obj = MockObject(prim.capitalize(), "MESH", location, rotation, scale)
            data.objects.append(obj)
            context.active_object = obj
            return {"FINISHED"}

        primitive_cube_add = staticmethod(lambda **kw: MockOps.mesh._add("Cube", **kw))
        primitive_uv_sphere_add = staticmethod(lambda **kw: MockOps.mesh._add("Sphere", **kw))
        primitive_ico_sphere_add = staticmethod(lambda **kw: MockOps.mesh._add("IcoSphere", **kw))
        primitive_cylinder_add = staticmethod(lambda **kw: MockOps.mesh._add("Cylinder", **kw))
        primitive_cone_add = staticmethod(lambda **kw: MockOps.mesh._add("Cone", **kw))
        primitive_plane_add = staticmethod(lambda **kw: MockOps.mesh._add("Plane", **kw))
        primitive_torus_add = staticmethod(lambda **kw: MockOps.mesh._add("Torus", **kw))
        primitive_monkey_add = staticmethod(lambda **kw: MockOps.mesh._add("Suzanne", **kw))

    class render:
        @staticmethod
        def render(write_still: bool = False) -> Dict[str, Any]:
            if write_still and context.scene.render.filepath:
                fp = context.scene.render.filepath
                Path(fp).parent.mkdir(parents=True, exist_ok=True)
                with open(fp, "wb") as f:
                    f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
            return {"FINISHED"}


class MockApp:
    version = (4, 1, 1)
    version_string = "4.1.1"
    background = True


# ==============================================================================
# Global Mock Singletons
# ==============================================================================

app = MockApp()
data = MockDataRoot()
context = MockContext()
ops = MockOps()
