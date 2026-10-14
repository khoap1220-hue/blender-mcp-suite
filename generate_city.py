"""
generate_city.py — High-End Architectural 3D Metropolis for Blender 4.1+
Features:
- Procedural skyscrapers (cubes, cylinders, stepped high-rises)
- Clean window grids with interior warm lighting
- Realistic dark gravel/tar rooftops with HVAC and antennas (no glowing roofs!)
- Paved asphalt streets with double yellow line markings and sidewalk curbs
- Warm streetlamps illuminating avenues
- Atmospheric twilight / dusk sky gradient
- Cinematic aerial drone camera angle
"""

import bpy
import bmesh
import math
import random

random.seed(2026)

def clean_scene():
    """Remove existing objects and orphan data."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for item in list(block):
            block.remove(item)

def create_materials():
    """Create procedural shaders for facades, roofs, roads, sidewalks, and neon lights."""
    mats = {}

    # 1. Dark Glass Facade with Illuminated Windows
    mat_facade = bpy.data.materials.new(name="Mat_Facade_Windows")
    mat_facade.use_nodes = True
    nodes = mat_facade.node_tree.nodes
    links = mat_facade.node_tree.links
    nodes.clear()

    n_out = nodes.new(type='ShaderNodeOutputMaterial')
    n_mix = nodes.new(type='ShaderNodeMixShader')

    # Dark reflective architectural glass
    n_glass = nodes.new(type='ShaderNodeBsdfPrincipled')
    n_glass.inputs['Base Color'].default_value = (0.015, 0.02, 0.035, 1.0)
    n_glass.inputs['Metallic'].default_value = 0.92
    n_glass.inputs['Roughness'].default_value = 0.12

    # Warm incandescent office window emission
    n_emit = nodes.new(type='ShaderNodeEmission')
    n_emit.inputs['Color'].default_value = (1.0, 0.82, 0.48, 1.0) # Warm amber light
    n_emit.inputs['Strength'].default_value = 14.0

    # Object Texture Coordinate & Mapping
    n_coord = nodes.new(type='ShaderNodeTexCoord')
    n_mapping = nodes.new(type='ShaderNodeMapping')
    n_mapping.inputs['Scale'].default_value = (0.5, 0.5, 0.5)

    # Brick Texture for window grid
    n_brick = nodes.new(type='ShaderNodeTexBrick')
    n_brick.inputs['Scale'].default_value = 1.6
    n_brick.inputs['Brick Width'].default_value = 1.1
    n_brick.inputs['Row Height'].default_value = 0.75
    n_brick.inputs['Mortar Size'].default_value = 0.14
    n_brick.inputs['Mortar Smooth'].default_value = 0.04

    # Noise texture to randomly toggle unlit rooms (~45% dark)
    n_noise = nodes.new(type='ShaderNodeTexNoise')
    n_noise.inputs['Scale'].default_value = 1.4
    n_noise.inputs['Detail'].default_value = 2.0

    n_mult = nodes.new(type='ShaderNodeMath')
    n_mult.operation = 'MULTIPLY'

    n_compare = nodes.new(type='ShaderNodeMath')
    n_compare.operation = 'GREATER_THAN'
    n_compare.inputs[1].default_value = 0.36

    links.new(n_coord.outputs['Object'], n_mapping.inputs['Vector'])
    links.new(n_mapping.outputs['Vector'], n_brick.inputs['Vector'])
    links.new(n_mapping.outputs['Vector'], n_noise.inputs['Vector'])

    links.new(n_brick.outputs['Color'], n_mult.inputs[0])
    links.new(n_noise.outputs['Fac'], n_mult.inputs[1])
    links.new(n_mult.outputs['Value'], n_compare.inputs[0])

    links.new(n_compare.outputs['Value'], n_mix.inputs['Fac'])
    links.new(n_glass.outputs['BSDF'], n_mix.inputs[1])
    links.new(n_emit.outputs['Emission'], n_mix.inputs[2])
    links.new(n_mix.outputs['Shader'], n_out.inputs['Surface'])

    mats['facade'] = mat_facade

    # 2. Rooftop Material (Dark Non-Reflective Tar/Concrete)
    mat_roof = bpy.data.materials.new(name="Mat_Rooftop_Tar")
    mat_roof.use_nodes = True
    bsdf_roof = mat_roof.node_tree.nodes.get('Principled BSDF')
    if bsdf_roof:
        bsdf_roof.inputs['Base Color'].default_value = (0.04, 0.045, 0.05, 1.0)
        bsdf_roof.inputs['Roughness'].default_value = 0.85
        bsdf_roof.inputs['Metallic'].default_value = 0.1
    mats['roof'] = mat_roof

    # 3. Road Material (Asphalt)
    mat_road = bpy.data.materials.new(name="Mat_Road_Asphalt")
    mat_road.use_nodes = True
    bsdf_road = mat_road.node_tree.nodes.get('Principled BSDF')
    if bsdf_road:
        bsdf_road.inputs['Base Color'].default_value = (0.02, 0.022, 0.025, 1.0)
        bsdf_road.inputs['Roughness'].default_value = 0.65
    mats['road'] = mat_road

    # 4. Road Lane Stripes (Bright Yellow)
    mat_stripes = bpy.data.materials.new(name="Mat_Lane_Stripes")
    mat_stripes.use_nodes = True
    bsdf_stripes = mat_stripes.node_tree.nodes.get('Principled BSDF')
    if bsdf_stripes:
        bsdf_stripes.inputs['Base Color'].default_value = (1.0, 0.72, 0.08, 1.0)
        bsdf_stripes.inputs['Roughness'].default_value = 0.4
    mats['stripes'] = mat_stripes

    # 5. Sidewalk Material (Concrete)
    mat_sidewalk = bpy.data.materials.new(name="Mat_Sidewalk_Concrete")
    mat_sidewalk.use_nodes = True
    bsdf_sw = mat_sidewalk.node_tree.nodes.get('Principled BSDF')
    if bsdf_sw:
        bsdf_sw.inputs['Base Color'].default_value = (0.14, 0.15, 0.16, 1.0)
        bsdf_sw.inputs['Roughness'].default_value = 0.8
    mats['sidewalk'] = mat_sidewalk

    # 6. Neon Accents (Cyan & Magenta)
    mat_cyan = bpy.data.materials.new(name="Mat_Neon_Cyan")
    mat_cyan.use_nodes = True
    n_emit_c = mat_cyan.node_tree.nodes.new(type='ShaderNodeEmission')
    n_emit_c.inputs['Color'].default_value = (0.0, 0.85, 1.0, 1.0)
    n_emit_c.inputs['Strength'].default_value = 28.0
    mat_cyan.node_tree.links.new(n_emit_c.outputs['Emission'], mat_cyan.node_tree.nodes.get('Material Output').inputs['Surface'])
    mats['neon_cyan'] = mat_cyan

    mat_magenta = bpy.data.materials.new(name="Mat_Neon_Magenta")
    mat_magenta.use_nodes = True
    n_emit_m = mat_magenta.node_tree.nodes.new(type='ShaderNodeEmission')
    n_emit_m.inputs['Color'].default_value = (1.0, 0.08, 0.55, 1.0)
    n_emit_m.inputs['Strength'].default_value = 28.0
    mat_magenta.node_tree.links.new(n_emit_m.outputs['Emission'], mat_magenta.node_tree.nodes.get('Material Output').inputs['Surface'])
    mats['neon_magenta'] = mat_magenta

    return mats

def assign_roof_material(obj, mat_roof):
    """Assigns the non-emissive roof material to top-facing polygons."""
    if obj.type != 'MESH':
        return
    if mat_roof.name not in obj.data.materials:
        obj.data.materials.append(mat_roof)
    roof_idx = obj.data.materials.find(mat_roof.name)
    for poly in obj.data.polygons:
        if poly.normal.z > 0.65:
            poly.material_index = roof_idx

def build_city(mats, grid_size=7, block_size=20.0, road_width=8.0):
    """Creates avenues, markings, diverse building types, and street lighting."""
    step = block_size + road_width
    total_span = grid_size * step
    start_pos = -total_span / 2.0 + step / 2.0

    # Ground Road Plane
    bpy.ops.mesh.primitive_plane_add(size=total_span + 120.0, location=(0, 0, 0.0))
    ground = bpy.context.active_object
    ground.name = "Ground_Asphalt"
    ground.data.materials.append(mats['road'])

    # Avenue Lane Markings
    for i in range(grid_size + 1):
        coord = -total_span / 2.0 + i * step - road_width / 2.0
        # Horizontal
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, coord, 0.015))
        h_line = bpy.context.active_object
        h_line.scale = (total_span + 100.0, 0.35, 1.0)
        h_line.data.materials.append(mats['stripes'])
        bpy.ops.object.transform_apply(scale=True)
        # Vertical
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(coord, 0, 0.015))
        v_line = bpy.context.active_object
        v_line.scale = (0.35, total_span + 100.0, 1.0)
        v_line.data.materials.append(mats['stripes'])
        bpy.ops.object.transform_apply(scale=True)

    building_id = 0

    for gx in range(grid_size):
        for gy in range(grid_size):
            cx = start_pos + gx * step
            cy = start_pos + gy * step
            dist = math.sqrt(cx**2 + cy**2)
            max_d = (total_span / 2.0) * 1.3
            height_factor = max(0.28, 1.0 - (dist / max_d))

            # Sidewalk Block
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, 0.15))
            sw = bpy.context.active_object
            sw.scale = (block_size * 0.94, block_size * 0.94, 0.3)
            sw.data.materials.append(mats['sidewalk'])
            bpy.ops.object.transform_apply(scale=True)

            roll = random.random()

            # Iconic Megatower (Downtown Core)
            if dist < block_size * 1.1 or (gx == grid_size // 2 and gy == grid_size // 2):
                h = random.uniform(90.0, 130.0)
                bw = block_size * 0.72

                # Main tower body
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, h * 0.35))
                b1 = bpy.context.active_object
                b1.scale = (bw, bw, h * 0.7)
                b1.data.materials.append(mats['facade'])
                bpy.ops.object.transform_apply(scale=True)
                assign_roof_material(b1, mats['roof'])

                # Setback upper tower
                top_w = bw * 0.62
                top_h = h * 0.3
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, h * 0.7 + top_h / 2.0))
                b2 = bpy.context.active_object
                b2.scale = (top_w, top_w, top_h)
                b2.data.materials.append(mats['facade'])
                bpy.ops.object.transform_apply(scale=True)
                assign_roof_material(b2, mats['roof'])

                # Neon crown rim & antenna
                bpy.ops.mesh.primitive_cylinder_add(radius=0.35, depth=22.0, location=(cx, cy, h + 11.0))
                spire = bpy.context.active_object
                spire.data.materials.append(mats['neon_magenta'])

                bpy.ops.mesh.primitive_torus_add(major_radius=top_w * 0.55, minor_radius=0.4, location=(cx, cy, h))
                crown = bpy.context.active_object
                crown.data.materials.append(mats['neon_cyan'])

                building_id += 1

            elif roll < 0.35:
                # Cylindrical Glass Skyscraper
                h = random.uniform(45.0, 75.0) * height_factor + 22.0
                rad = (block_size * 0.7) / 2.0
                bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=rad, depth=h, location=(cx, cy, h / 2.0))
                cyl = bpy.context.active_object
                cyl.data.materials.append(mats['facade'])
                bpy.ops.object.transform_apply(scale=True)
                assign_roof_material(cyl, mats['roof'])

                # Glowing Rooftop Crown Ring
                bpy.ops.mesh.primitive_torus_add(major_radius=rad * 0.96, minor_radius=0.3, location=(cx, cy, h + 0.2))
                ring = bpy.context.active_object
                ring.data.materials.append(mats['neon_cyan'])

                building_id += 1

            elif roll < 0.72:
                # Stepped High-Rise
                h = random.uniform(32.0, 62.0) * height_factor + 16.0
                bw = block_size * random.uniform(0.6, 0.76)
                bl = block_size * random.uniform(0.6, 0.76)
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, h / 2.0))
                bldg = bpy.context.active_object
                bldg.scale = (bw, bl, h)
                bldg.data.materials.append(mats['facade'])
                bpy.ops.object.transform_apply(scale=True)
                assign_roof_material(bldg, mats['roof'])

                # Rooftop HVAC Equipment Box
                ac_w, ac_l, ac_h = bw * 0.35, bl * 0.35, random.uniform(1.8, 3.2)
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx + bw * 0.15, cy + bl * 0.15, h + ac_h / 2.0))
                ac = bpy.context.active_object
                ac.scale = (ac_w, ac_l, ac_h)
                ac.data.materials.append(mats['roof'])
                bpy.ops.object.transform_apply(scale=True)

                building_id += 1

            else:
                # 4 Dense Mid-Rise Commercial Blocks
                sub = block_size * 0.25
                for sx in (-sub, sub):
                    for sy in (-sub, sub):
                        sh = random.uniform(16.0, 36.0) * height_factor + 10.0
                        sw_w = block_size * 0.38
                        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx + sx, cy + sy, sh / 2.0))
                        mb = bpy.context.active_object
                        mb.scale = (sw_w, sw_w, sh)
                        mb.data.materials.append(mats['facade'])
                        bpy.ops.object.transform_apply(scale=True)
                        assign_roof_material(mb, mats['roof'])
                        building_id += 1

            # Corner Street Lamps with warm sodium illumination
            for lx, ly in [(-block_size/2.0 - 1.2, -block_size/2.0 - 1.2), (block_size/2.0 + 1.2, block_size/2.0 + 1.2)]:
                lamp_x = cx + lx
                lamp_y = cy + ly
                if abs(lamp_x) < total_span/2.0 and abs(lamp_y) < total_span/2.0:
                    bpy.ops.object.light_add(type='POINT', location=(lamp_x, lamp_y, 4.8))
                    lamp = bpy.context.active_object
                    lamp.data.energy = 380.0
                    lamp.data.color = (1.0, 0.78, 0.42)
                    lamp.data.shadow_soft_size = 0.5

def setup_lighting_and_drone_camera():
    """Sets up dusk sky gradient, moon directional lighting, and an epic drone perspective camera."""
    # World Background with gradient twilight sky
    world = bpy.context.scene.world or bpy.data.worlds.new("CyberCityWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()

    w_out = nodes.new(type='ShaderNodeOutputWorld')
    w_bg = nodes.new(type='ShaderNodeBackground')
    w_bg.inputs['Color'].default_value = (0.012, 0.018, 0.035, 1.0) # Midnight navy sky
    w_bg.inputs['Strength'].default_value = 0.75
    links.new(w_bg.outputs['Background'], w_out.inputs['Surface'])

    # Key Moonlight (Cool Blue Directional)
    bpy.ops.object.light_add(type='SUN', location=(120.0, -140.0, 160.0), rotation=(math.radians(55), math.radians(20), math.radians(-40)))
    sun = bpy.context.active_object
    sun.name = "Moon_Directional"
    sun.data.energy = 3.8
    sun.data.color = (0.7, 0.85, 1.0)

    # Ambient Soft Horizon Fill
    bpy.ops.object.light_add(type='SUN', location=(-100.0, 130.0, 70.0), rotation=(math.radians(-50), math.radians(-10), math.radians(135)))
    fill = bpy.context.active_object
    fill.name = "Horizon_Fill"
    fill.data.energy = 1.0
    fill.data.color = (0.2, 0.5, 0.8)

    # Drone High-Angle Cinematic Camera
    # Looking down the avenue towards the downtown megatowers
    bpy.ops.object.camera_add(location=(-86.0, -106.0, 64.0), rotation=(math.radians(66), 0.0, math.radians(-40)))
    cam = bpy.context.active_object
    cam.name = "Drone_Cinematic_Camera"
    cam.data.lens = 28.0
    bpy.context.scene.camera = cam

    # Render Settings
    scene = bpy.context.scene
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = False

def main():
    print("[*] Generating High-End 3D Metropolis...")
    clean_scene()
    mats = create_materials()
    build_city(mats, grid_size=7, block_size=20.0, road_width=8.0)
    setup_lighting_and_drone_camera()
    print("[+] 3D City generated successfully!")

if __name__ == "__main__":
    main()
