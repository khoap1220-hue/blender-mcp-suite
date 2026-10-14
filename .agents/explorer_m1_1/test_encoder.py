"""
Test Blender custom JSON serialization
"""
import json
import mathutils

class BlenderJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        # mathutils types
        if isinstance(obj, (mathutils.Vector, mathutils.Euler, mathutils.Color)):
            return list(obj)
        if isinstance(obj, mathutils.Matrix):
            return [list(row) for row in obj]
        if isinstance(obj, mathutils.Quaternion):
            return list(obj)
        # Check if it has as_dict or similar
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "name") and hasattr(obj, "type"):
            return {"name": obj.name, "type": obj.type}
        return super().default(obj)

v = mathutils.Vector((1.0, 2.0, 3.0))
m = mathutils.Matrix.Identity(3)
res = {"vec": v, "mat": m}

serialized = json.dumps(res, cls=BlenderJSONEncoder)
print("Serialized:", serialized)
assert json.loads(serialized) == {"vec": [1.0, 2.0, 3.0], "mat": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]}
print("Encoder test passed!")
