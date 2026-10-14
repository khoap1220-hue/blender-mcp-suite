import bpy
import math

blend_path = "y:/MCP Blender Agent/city_scene.blend"
bpy.ops.wm.open_mainfile(filepath=blend_path)

scene = bpy.context.scene
print(f"Total objects in scene: {len(bpy.data.objects)}")

# Optimize World Shader - remove heavy fog if it obscures, keep dark aesthetic with ambient skylight
world = scene.world
if world and world.use_nodes:
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    out_w = nodes.new('ShaderNodeOutputWorld')
    bg_w = nodes.new('ShaderNodeBackground')
    bg_w.inputs['Color'].default_value = (0.015, 0.025, 0.05, 1.0)
    bg_w.inputs['Strength'].default_value = 1.2
    links.new(bg_w.outputs['Background'], out_w.inputs['Surface'])

# Enhance Key Moonlight
sun = bpy.data.objects.get("Key_Moonlight")
if sun:
    sun.data.energy = 8.0
    sun.data.color = (0.8, 0.9, 1.0)
    sun.rotation_euler = (math.radians(50), math.radians(15), math.radians(-45))

# Add an ambient fill light from opposite angle
fill = bpy.data.objects.get("City_Glow_Fill")
if fill:
    fill.data.energy = 4.0
    fill.data.color = (0.9, 0.3, 0.7)

# Target empty at center of metropolis
target = bpy.data.objects.get("City_Center_Target")
if not target:
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 30.0))
    target = bpy.context.active_object
    target.name = "City_Center_Target"

# 1. Cinematic Skyline Camera
cam = bpy.data.objects.get("Hero_Avenue_Camera")
if not cam:
    bpy.ops.object.camera_add()
    cam = bpy.context.active_object
    cam.name = "Hero_Avenue_Camera"

cam.location = (-110.0, -130.0, 70.0)
cam.data.lens = 28.0
cam.data.clip_end = 2000.0

# Add Track To constraint
cam.constraints.clear()
tt = cam.constraints.new(type='TRACK_TO')
tt.target = target
tt.track_axis = 'TRACK_NEGATIVE_Z'
tt.up_axis = 'UP_Y'

scene.camera = cam

# Render settings
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 100
scene.render.filepath = "y:/MCP Blender Agent/city_preview.png"

# Save updated scene
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print("[+] Saved updated .blend file.")

# Render Skyline
print("[*] Rendering cinematic skyline preview...")
bpy.ops.render.render(write_still=True)
print("[+] Rendered city_preview.png successfully!")

# 2. Street Level Camera (Avenue perspective looking down main road)
# Road is at X = 0.0 (between -17 and +17)
cam_street = bpy.data.objects.get("Street_Level_Camera")
if not cam_street:
    bpy.ops.object.camera_add()
    cam_street = bpy.context.active_object
    cam_street.name = "Street_Level_Camera"

cam_street.location = (0.0, -100.0, 3.5)
target_street = bpy.data.objects.get("Street_Target")
if not target_street:
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 20.0))
    target_street = bpy.context.active_object
    target_street.name = "Street_Target"

cam_street.constraints.clear()
tt_st = cam_street.constraints.new(type='TRACK_TO')
tt_st.target = target_street
tt_st.track_axis = 'TRACK_NEGATIVE_Z'
tt_st.up_axis = 'UP_Y'
cam_street.data.lens = 20.0
cam_street.data.clip_end = 1500.0

scene.camera = cam_street
scene.render.filepath = "y:/MCP Blender Agent/city_street_preview.png"
print("[*] Rendering street level preview...")
bpy.ops.render.render(write_still=True)
print("[+] Rendered city_street_preview.png successfully!")

# Switch back to Skyline as primary camera
scene.camera = cam
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print("[+] All done!")
