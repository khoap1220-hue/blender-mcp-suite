"""
generate_detailed_city.py — Advanced Detailed 3D Metropolis Generator for Blender 4.1+
Upgrades:
1. Real 3D Architectural Geometry:
   - Floor slabs, recessed glass curtain walls, vertical structural fins and columns.
   - Stepped crowns, helipads with "H" marks, satellite dishes, water tanks on stilts, HVAC chillers, multi-antenna arrays.
   - Giant glowing LED commercial billboards and holographic neon signs on facades.
2. Urban Street Life & Clutter:
   - Zebra crosswalks, stop lines, asphalt with wet puddle reflections.
   - 3D vehicles (cars, cyber transports) and long-exposure traffic light trails (white headlights, red taillights).
   - Traffic light gantries, sidewalk planters with trees, modern streetlamps.
3. Atmosphere & Volumetrics:
   - Atmospheric depth haze/fog, volumetric light blooming, dramatic twilight lighting.
4. Cinematic Camera:
   - Street-level to mid-rise vantage point looking down the bustling neon avenue.
"""

import bpy
import bmesh
import math
import random

random.seed(777)

def clean_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras, bpy.data.images):
        for item in list(block):
            block.remove(item)

def create_materials():
    mats = {}

    # 1. Concrete / Slabs / Columns
    mat_concrete = bpy.data.materials.new(name="Mat_Concrete_Structural")
    mat_concrete.use_nodes = True
    b_c = mat_concrete.node_tree.nodes.get("Principled BSDF")
    if b_c:
        b_c.inputs['Base Color'].default_value = (0.12, 0.13, 0.15, 1.0)
        b_c.inputs['Roughness'].default_value = 0.75
        b_c.inputs['Metallic'].default_value = 0.2
    mats['concrete'] = mat_concrete

    # 2. Dark Metal / Frames / Antennas
    mat_metal = bpy.data.materials.new(name="Mat_Dark_Metal")
    mat_metal.use_nodes = True
    b_m = mat_metal.node_tree.nodes.get("Principled BSDF")
    if b_m:
        b_m.inputs['Base Color'].default_value = (0.05, 0.05, 0.06, 1.0)
        b_m.inputs['Metallic'].default_value = 0.95
        b_m.inputs['Roughness'].default_value = 0.3
    mats['metal'] = mat_metal

    # 3. Recessed Office Glass with Individual Illuminated Windows
    mat_glass_win = bpy.data.materials.new(name="Mat_Recessed_Windows")
    mat_glass_win.use_nodes = True
    nodes = mat_glass_win.node_tree.nodes
    links = mat_glass_win.node_tree.links
    nodes.clear()

    n_out = nodes.new('ShaderNodeOutputMaterial')
    n_mix = nodes.new('ShaderNodeMixShader')

    n_glass = nodes.new('ShaderNodeBsdfPrincipled')
    n_glass.inputs['Base Color'].default_value = (0.01, 0.015, 0.025, 1.0)
    n_glass.inputs['Metallic'].default_value = 0.95
    n_glass.inputs['Roughness'].default_value = 0.06

    n_emit = nodes.new('ShaderNodeEmission')
    n_emit.inputs['Color'].default_value = (1.0, 0.86, 0.58, 1.0)
    n_emit.inputs['Strength'].default_value = 16.0

    n_coord = nodes.new('ShaderNodeTexCoord')
    n_mapping = nodes.new('ShaderNodeMapping')
    n_mapping.inputs['Scale'].default_value = (0.4, 0.4, 0.4)

    n_brick = nodes.new('ShaderNodeTexBrick')
    n_brick.inputs['Scale'].default_value = 1.5
    n_brick.inputs['Brick Width'].default_value = 1.2
    n_brick.inputs['Row Height'].default_value = 0.75
    n_brick.inputs['Mortar Size'].default_value = 0.15

    n_noise = nodes.new('ShaderNodeTexNoise')
    n_noise.inputs['Scale'].default_value = 1.6

    n_mult = nodes.new('ShaderNodeMath')
    n_mult.operation = 'MULTIPLY'

    n_comp = nodes.new('ShaderNodeMath')
    n_comp.operation = 'GREATER_THAN'
    n_comp.inputs[1].default_value = 0.35

    links.new(n_coord.outputs['Object'], n_mapping.inputs['Vector'])
    links.new(n_mapping.outputs['Vector'], n_brick.inputs['Vector'])
    links.new(n_mapping.outputs['Vector'], n_noise.inputs['Vector'])
    links.new(n_brick.outputs['Color'], n_mult.inputs[0])
    links.new(n_noise.outputs['Fac'], n_mult.inputs[1])
    links.new(n_mult.outputs['Value'], n_comp.inputs[0])
    links.new(n_comp.outputs['Value'], n_mix.inputs['Fac'])
    links.new(n_glass.outputs['BSDF'], n_mix.inputs[1])
    links.new(n_emit.outputs['Emission'], n_mix.inputs[2])
    links.new(n_mix.outputs['Shader'], n_out.inputs['Surface'])
    mats['windows'] = mat_glass_win

    # 4. Wet Asphalt Road with Glossy Reflections
    mat_road = bpy.data.materials.new(name="Mat_Wet_Road")
    mat_road.use_nodes = True
    nodes_r = mat_road.node_tree.nodes
    links_r = mat_road.node_tree.links
    nodes_r.clear()

    out_r = nodes_r.new('ShaderNodeOutputMaterial')
    bsdf_r = nodes_r.new('ShaderNodeBsdfPrincipled')
    bsdf_r.inputs['Base Color'].default_value = (0.015, 0.016, 0.018, 1.0)
    
    # Noise for puddles
    noise_r = nodes_r.new('ShaderNodeTexNoise')
    noise_r.inputs['Scale'].default_value = 4.0
    ramp_r = nodes_r.new('ShaderNodeValToRGB')
    ramp_r.color_ramp.elements[0].position = 0.4
    ramp_r.color_ramp.elements[0].color = (0.1, 0.1, 0.1, 1.0) # Wet puddle
    ramp_r.color_ramp.elements[1].position = 0.65
    ramp_r.color_ramp.elements[1].color = (0.75, 0.75, 0.75, 1.0) # Dry asphalt

    links_r.new(noise_r.outputs['Fac'], ramp_r.inputs['Fac'])
    links_r.new(ramp_r.outputs['Color'], bsdf_r.inputs['Roughness'])
    links_r.new(bsdf_r.outputs['BSDF'], out_r.inputs['Surface'])
    mats['road'] = mat_road

    # 5. Paint Markings (Yellow & White)
    mat_yellow = bpy.data.materials.new(name="Mat_Yellow_Markings")
    mat_yellow.use_nodes = True
    by = mat_yellow.node_tree.nodes.get('Principled BSDF')
    by.inputs['Base Color'].default_value = (1.0, 0.75, 0.05, 1.0)
    by.inputs['Roughness'].default_value = 0.4
    mats['yellow'] = mat_yellow

    mat_white = bpy.data.materials.new(name="Mat_White_Markings")
    mat_white.use_nodes = True
    bw = mat_white.node_tree.nodes.get('Principled BSDF')
    bw.inputs['Base Color'].default_value = (0.95, 0.95, 0.95, 1.0)
    bw.inputs['Roughness'].default_value = 0.4
    mats['white'] = mat_white

    # 6. Neon / Commercial Billboard Shaders
    colors = [
        ("neon_cyan", (0.0, 0.95, 1.0, 1.0)),
        ("neon_magenta", (1.0, 0.05, 0.65, 1.0)),
        ("neon_orange", (1.0, 0.45, 0.0, 1.0)),
        ("neon_green", (0.1, 1.0, 0.4, 1.0)),
        ("headlight", (1.0, 0.98, 0.85, 1.0)),
        ("taillight", (1.0, 0.02, 0.02, 1.0)),
        ("tree_foliage", (0.04, 0.18, 0.06, 1.0)),
        ("beacon_red", (1.0, 0.0, 0.0, 1.0)),
    ]
    for name, col in colors:
        m = bpy.data.materials.new(name=f"Mat_{name}")
        m.use_nodes = True
        nodes_m = m.node_tree.nodes
        links_m = m.node_tree.links
        nodes_m.clear()
        out_m = nodes_m.new('ShaderNodeOutputMaterial')
        if "tree" in name:
            b_tree = nodes_m.new('ShaderNodeBsdfPrincipled')
            b_tree.inputs['Base Color'].default_value = col
            b_tree.inputs['Roughness'].default_value = 0.85
            links_m.new(b_tree.outputs['BSDF'], out_m.inputs['Surface'])
        else:
            e_m = nodes_m.new('ShaderNodeEmission')
            e_m.inputs['Color'].default_value = col
            e_m.inputs['Strength'].default_value = 32.0 if "neon" in name or "beacon" in name else 45.0
            links_m.new(e_m.outputs['Emission'], out_m.inputs['Surface'])
        mats[name] = m

    return mats

def create_tree(location, mats):
    """Creates a stylized street tree in a concrete box planter."""
    x, y, z = location
    # Planter box
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z + 0.3))
    planter = bpy.context.active_object
    planter.scale = (1.4, 1.4, 0.6)
    planter.data.materials.append(mats['concrete'])
    bpy.ops.object.transform_apply(scale=True)

    # Trunk
    bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=2.8, location=(x, y, z + 1.8))
    trunk = bpy.context.active_object
    trunk.data.materials.append(mats['concrete'])

    # Foliage (2 layered icospeheres)
    for fz, r in [(z + 3.2, 0.95), (z + 4.2, 0.7)]:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=r, location=(x, y, fz))
        foliage = bpy.context.active_object
        foliage.data.materials.append(mats['tree_foliage'])

def create_traffic_light(location, rotation_z, mats):
    """Creates an urban traffic signal pole with cantilever arm."""
    x, y, z = location
    # Vertical Pole
    bpy.ops.mesh.primitive_cylinder_add(radius=0.14, depth=5.5, location=(x, y, z + 2.75))
    pole = bpy.context.active_object
    pole.data.materials.append(mats['metal'])

    # Cantilever Arm
    bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=4.0, location=(x + 2.0, y, z + 5.2), rotation=(0, math.radians(90), 0))
    arm = bpy.context.active_object
    arm.data.materials.append(mats['metal'])

    # Signal Box
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x + 3.2, y, z + 4.8))
    box = bpy.context.active_object
    box.scale = (0.35, 0.35, 0.9)
    box.data.materials.append(mats['metal'])
    bpy.ops.object.transform_apply(scale=True)

    # Signal Lights (Red / Green)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.08, location=(x + 3.2, y - 0.2, z + 5.05))
    s_red = bpy.context.active_object
    s_red.data.materials.append(mats['taillight'])

    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.08, location=(x + 3.2, y - 0.2, z + 4.6))
    s_green = bpy.context.active_object
    s_green.data.materials.append(mats['neon_green'])

def create_car(location, heading, mats, is_driving=True):
    """Creates a modern vehicle with headlights and taillights."""
    x, y, z = location
    # Car Body
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z + 0.55))
    car = bpy.context.active_object
    car.scale = (1.8, 3.8, 0.9)
    car.rotation_euler.z = heading
    car.data.materials.append(mats['concrete'])
    bpy.ops.object.transform_apply(scale=True)

    # Cabin / Roof
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y - 0.2, z + 1.15))
    cabin = bpy.context.active_object
    cabin.scale = (1.5, 2.0, 0.65)
    cabin.rotation_euler.z = heading
    cabin.data.materials.append(mats['metal'])
    bpy.ops.object.transform_apply(scale=True)

    # Headlights & Taillights
    dx = math.sin(heading)
    dy = math.cos(heading)

    # Front Headlights
    hx1 = x - 0.65 * dy + 1.8 * dx
    hy1 = y + 0.65 * dx + 1.8 * dy
    hx2 = x + 0.65 * dy + 1.8 * dx
    hy2 = y - 0.65 * dx + 1.8 * dy

    for hx, hy in [(hx1, hy1), (hx2, hy2)]:
        bpy.ops.mesh.primitive_cube_add(size=0.2, location=(hx, hy, z + 0.55))
        hl = bpy.context.active_object
        hl.data.materials.append(mats['headlight'])

    # Rear Taillights
    rx1 = x - 0.65 * dy - 1.8 * dx
    ry1 = y + 0.65 * dx - 1.8 * dy
    rx2 = x + 0.65 * dy - 1.8 * dx
    ry2 = y - 0.65 * dx - 1.8 * dy

    for rx, ry in [(rx1, ry1), (rx2, ry2)]:
        bpy.ops.mesh.primitive_cube_add(size=0.2, location=(rx, ry, z + 0.55))
        tl = bpy.context.active_object
        tl.data.materials.append(mats['taillight'])

    # Long-exposure streak if driving
    if is_driving:
        # Headlight beam
        bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=14.0, location=(x + 8.0 * dx, y + 8.0 * dy, z + 0.55), rotation=(math.radians(90), 0, heading))
        streak_h = bpy.context.active_object
        streak_h.data.materials.append(mats['headlight'])

        # Taillight beam
        bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=16.0, location=(x - 9.0 * dx, y - 9.0 * dy, z + 0.55), rotation=(math.radians(90), 0, heading))
        streak_t = bpy.context.active_object
        streak_t.data.materials.append(mats['taillight'])

def create_rooftop_details(cx, cy, top_z, top_w, top_l, mats):
    """Fills skyscraper rooftops with AC chillers, water towers, satellite dishes, helipads, and beacon towers."""
    r = random.random()

    # 1. Helipad on large flat roofs
    if top_w > 12.0 and r < 0.4:
        # Raised Pad
        bpy.ops.mesh.primitive_cylinder_add(radius=top_w * 0.38, depth=0.4, location=(cx, cy, top_z + 0.2))
        pad = bpy.context.active_object
        pad.data.materials.append(mats['concrete'])

        # Outer Glow Ring
        bpy.ops.mesh.primitive_torus_add(major_radius=top_w * 0.36, minor_radius=0.12, location=(cx, cy, top_z + 0.45))
        ring = bpy.context.active_object
        ring.data.materials.append(mats['neon_orange'])

        # "H" Helipad marking (2 vertical bars + 1 crossbar)
        hw = top_w * 0.08
        hl = top_w * 0.28
        for ox in (-hw * 1.3, hw * 1.3):
            bpy.ops.mesh.primitive_plane_add(size=1.0, location=(cx + ox, cy, top_z + 0.43))
            bar = bpy.context.active_object
            bar.scale = (hw * 0.45, hl, 1.0)
            bar.data.materials.append(mats['yellow'])
            bpy.ops.object.transform_apply(scale=True)
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(cx, cy, top_z + 0.43))
        hbar = bpy.context.active_object
        hbar.scale = (hw * 2.6, hw * 0.45, 1.0)
        hbar.data.materials.append(mats['yellow'])
        bpy.ops.object.transform_apply(scale=True)

    # 2. Water Tower on Stilts
    elif r < 0.65:
        # 4 Stilts
        stilt_h = 3.5
        tank_r = 1.8
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=stilt_h, location=(cx + sx, cy + sy, top_z + stilt_h/2.0))
                stilt = bpy.context.active_object
                stilt.data.materials.append(mats['metal'])
        # Tank
        bpy.ops.mesh.primitive_cylinder_add(radius=tank_r, depth=2.8, location=(cx, cy, top_z + stilt_h + 1.4))
        tank = bpy.context.active_object
        tank.data.materials.append(mats['concrete'])
        # Cone Roof
        bpy.ops.mesh.primitive_cone_add(radius1=tank_r * 1.05, depth=1.0, location=(cx, cy, top_z + stilt_h + 3.3))
        cone = bpy.context.active_object
        cone.data.materials.append(mats['metal'])

    # 3. Satellite Communication Dish
    if random.random() > 0.4:
        sx = cx + top_w * 0.25 * random.choice([-1, 1])
        sy = cy + top_l * 0.25 * random.choice([-1, 1])
        # Mount post
        bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=2.0, location=(sx, sy, top_z + 1.0))
        dish_post = bpy.context.active_object
        dish_post.data.materials.append(mats['metal'])
        # Parabolic Dish (Hemisphere)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.3, location=(sx, sy, top_z + 2.0), rotation=(math.radians(35), math.radians(20), 0))
        dish = bpy.context.active_object
        dish.scale = (1.0, 1.0, 0.4)
        dish.data.materials.append(mats['white'])
        bpy.ops.object.transform_apply(scale=True)

    # 4. Multi-Tier Antenna Mast with Red Obstruction Beacon
    mast_h = random.uniform(10.0, 22.0)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=mast_h, location=(cx, cy, top_z + mast_h/2.0))
    mast = bpy.context.active_object
    mast.data.materials.append(mats['metal'])

    # Red blinking beacon on tip
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.35, location=(cx, cy, top_z + mast_h + 0.35))
    beacon = bpy.context.active_object
    beacon.data.materials.append(mats['beacon_red'])

    # 5. Heavy Industrial HVAC Chillers
    for ox, oy in [(top_w * 0.22, -top_l * 0.22), (-top_w * 0.22, top_l * 0.22)]:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx + ox, cy + oy, top_z + 1.2))
        chiller = bpy.context.active_object
        chiller.scale = (top_w * 0.28, top_l * 0.22, 2.4)
        chiller.data.materials.append(mats['metal'])
        bpy.ops.object.transform_apply(scale=True)
        # Chiller fan vent on top
        bpy.ops.mesh.primitive_cylinder_add(radius=top_l * 0.08, depth=0.3, location=(cx + ox, cy + oy, top_z + 2.5))
        vent = bpy.context.active_object
        vent.data.materials.append(mats['concrete'])

def build_advanced_skyscraper(cx, cy, base_w, base_l, height, mats, building_idx):
    """Builds a high-detail skyscraper with real 3D floor slabs, structural fins, glass core, and billboard ads."""
    # 1. Ground Floor Lobby Entrance (Taller, Transparent glass with columns)
    lobby_h = 5.0
    # Core glass lobby
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, lobby_h / 2.0))
    lobby = bpy.context.active_object
    lobby.scale = (base_w * 0.96, base_l * 0.96, lobby_h)
    lobby.data.materials.append(mats['windows'])
    bpy.ops.object.transform_apply(scale=True)

    # Perimeter columns for the lobby
    col_r = 0.35
    for px in (-base_w * 0.46, base_w * 0.46):
        for py in (-base_l * 0.46, 0.0, base_l * 0.46):
            bpy.ops.mesh.primitive_cylinder_add(radius=col_r, depth=lobby_h, location=(cx + px, cy + py, lobby_h / 2.0))
            col = bpy.context.active_object
            col.data.materials.append(mats['concrete'])

    # Canopy / Awning over entrance
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy - base_l * 0.52, 4.2))
    canopy = bpy.context.active_object
    canopy.scale = (base_w * 0.5, 3.2, 0.3)
    canopy.data.materials.append(mats['neon_cyan'] if building_idx % 2 == 0 else mats['neon_orange'])
    bpy.ops.object.transform_apply(scale=True)

    # 2. Main Tower Shaft: Floor Slabs + Recessed Glass Core
    tower_h = height - lobby_h
    floor_height = 3.6
    num_floors = int(tower_h // floor_height)

    # Recessed Glass Curtain Wall (Interior Core)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, lobby_h + tower_h / 2.0))
    core = bpy.context.active_object
    core.scale = (base_w * 0.92, base_l * 0.92, tower_h)
    core.data.materials.append(mats['windows'])
    bpy.ops.object.transform_apply(scale=True)

    # 3D Horizontal Floor Slabs (Protrude slightly to create real geometric shadows)
    # We step every 2 floors to keep performance brisk while looking hyper-detailed
    step_floors = 2
    for fi in range(0, num_floors, step_floors):
        fz = lobby_h + fi * floor_height
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, fz))
        slab = bpy.context.active_object
        slab.scale = (base_w * 1.01, base_l * 1.01, 0.5)
        slab.data.materials.append(mats['concrete'])
        bpy.ops.object.transform_apply(scale=True)

    # 3D Vertical Structural Fins / Mullions along the corners
    fin_thick = 0.6
    for fx in (-base_w * 0.49, base_w * 0.49):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx + fx, cy, lobby_h + tower_h / 2.0))
        fin = bpy.context.active_object
        fin.scale = (fin_thick, base_l * 1.02, tower_h)
        fin.data.materials.append(mats['concrete'])
        bpy.ops.object.transform_apply(scale=True)

    # 3. Giant Commercial LED Billboard (Every 3rd building)
    if building_idx % 3 == 0 and height > 40.0:
        bb_side = random.choice([-1, 1])
        bb_y = cy + (base_l * 0.49) * bb_side
        bb_z = lobby_h + tower_h * 0.4
        bb_w = base_w * 0.75
        bb_h = tower_h * 0.28
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, bb_y + 0.2 * bb_side, bb_z))
        bb = bpy.context.active_object
        bb.scale = (bb_w, 0.4, bb_h)
        # Select vibrant cyber ad color
        ad_color = random.choice(['neon_magenta', 'neon_cyan', 'neon_orange'])
        bb.data.materials.append(mats[ad_color])
        bpy.ops.object.transform_apply(scale=True)

    # 4. Rooftop Clutter
    create_rooftop_details(cx, cy, height, base_w, base_l, mats)

def build_detailed_city(mats, grid_size=6, block_size=24.0, road_width=10.0):
    step = block_size + road_width
    total_span = grid_size * step
    start_pos = -total_span / 2.0 + step / 2.0

    # Ground Asphalt Plane
    bpy.ops.mesh.primitive_plane_add(size=total_span + 140.0, location=(0, 0, 0.0))
    ground = bpy.context.active_object
    ground.name = "Ground_Wet_Asphalt"
    ground.data.materials.append(mats['road'])

    # Avenue Lane Markings, Dashes, Crosswalks
    for i in range(grid_size + 1):
        coord = -total_span / 2.0 + i * step - road_width / 2.0
        
        # Double Yellow Center Lines
        for dy in (-0.25, 0.25):
            bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, coord + dy, 0.015))
            h_line = bpy.context.active_object
            h_line.scale = (total_span + 100.0, 0.2, 1.0)
            h_line.data.materials.append(mats['yellow'])
            bpy.ops.object.transform_apply(scale=True)

            bpy.ops.mesh.primitive_plane_add(size=1.0, location=(coord + dy, 0, 0.015))
            v_line = bpy.context.active_object
            v_line.scale = (0.2, total_span + 100.0, 1.0)
            v_line.data.materials.append(mats['yellow'])
            bpy.ops.object.transform_apply(scale=True)

        # White Zebra Crosswalks at Intersections
        for j in range(grid_size + 1):
            ix = -total_span / 2.0 + j * step - road_width / 2.0
            iy = coord
            # 4 zebra stripes per approach
            for s in range(-3, 4):
                if s != 0:
                    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(ix + s * 0.75, iy + road_width * 0.55, 0.02))
                    z_stripe = bpy.context.active_object
                    z_stripe.scale = (0.45, 2.5, 1.0)
                    z_stripe.data.materials.append(mats['white'])
                    bpy.ops.object.transform_apply(scale=True)

    building_id = 0

    # Populate City Blocks
    for gx in range(grid_size):
        for gy in range(grid_size):
            cx = start_pos + gx * step
            cy = start_pos + gy * step
            dist = math.sqrt(cx**2 + cy**2)
            max_d = (total_span / 2.0) * 1.3
            height_factor = max(0.3, 1.0 - (dist / max_d))

            # Sidewalk Slab
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, 0.2))
            sw = bpy.context.active_object
            sw.scale = (block_size * 0.95, block_size * 0.95, 0.4)
            sw.data.materials.append(mats['concrete'])
            bpy.ops.object.transform_apply(scale=True)

            # Street Trees along sidewalks
            sw_half = (block_size * 0.95) / 2.0 - 1.2
            for tx in (-sw_half, sw_half):
                for ty in (-sw_half * 0.5, sw_half * 0.5):
                    if random.random() > 0.25:
                        create_tree((cx + tx, cy + ty, 0.4), mats)

            # Traffic Lights at block corners
            if (gx + gy) % 2 == 0:
                create_traffic_light((cx + sw_half + 0.6, cy + sw_half + 0.6, 0.4), 0, mats)

            # Vehicles on the street
            lane_offset = road_width * 0.28
            car_x = cx + (block_size/2.0 + lane_offset) * random.choice([-1, 1])
            car_y = cy + random.uniform(-block_size * 0.4, block_size * 0.4)
            if abs(car_x) < total_span/2.0 and abs(car_y) < total_span/2.0:
                create_car((car_x, car_y, 0.0), heading=math.radians(90 if random.random() > 0.5 else -90), mats=mats, is_driving=True)

            # Construct Skyscraper
            # Central iconic Megatower
            if dist < block_size * 1.1 or (gx == grid_size // 2 and gy == grid_size // 2):
                h = random.uniform(110.0, 150.0)
                bw = block_size * 0.75
                build_advanced_skyscraper(cx, cy, bw, bw, h, mats, building_id)
                building_id += 1

            elif random.random() < 0.4:
                # Cylindrical Tower
                h = random.uniform(50.0, 85.0) * height_factor + 25.0
                rad = (block_size * 0.72) / 2.0
                bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=rad, depth=h, location=(cx, cy, h / 2.0))
                cyl = bpy.context.active_object
                cyl.data.materials.append(mats['windows'])
                bpy.ops.object.transform_apply(scale=True)

                # Floor rings
                for fz in range(6, int(h), 6):
                    bpy.ops.mesh.primitive_torus_add(major_radius=rad * 1.02, minor_radius=0.25, location=(cx, cy, fz))
                    t_ring = bpy.context.active_object
                    t_ring.data.materials.append(mats['concrete'])

                # Neon Crown
                bpy.ops.mesh.primitive_torus_add(major_radius=rad * 0.98, minor_radius=0.4, location=(cx, cy, h + 0.4))
                crown = bpy.context.active_object
                crown.data.materials.append(mats['neon_cyan'])

                create_rooftop_details(cx, cy, h, rad * 2, rad * 2, mats)
                building_id += 1

            else:
                # Stepped high-rise
                h = random.uniform(40.0, 75.0) * height_factor + 20.0
                bw = block_size * random.uniform(0.65, 0.78)
                bl = block_size * random.uniform(0.65, 0.78)
                build_advanced_skyscraper(cx, cy, bw, bl, h, mats, building_id)
                building_id += 1

            # Arched Streetlamps with warm sodium illumination
            for lx, ly in [(-block_size/2.0 - 1.5, 0.0), (block_size/2.0 + 1.5, 0.0)]:
                lamp_x = cx + lx
                lamp_y = cy + ly
                if abs(lamp_x) < total_span/2.0:
                    # Lamp post
                    bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=6.0, location=(lamp_x, lamp_y, 3.0))
                    lp = bpy.context.active_object
                    lp.data.materials.append(mats['metal'])
                    # Overhang lamp arm
                    bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=2.0, location=(lamp_x + (-1.0 if lx > 0 else 1.0), lamp_y, 5.8), rotation=(0, math.radians(90), 0))
                    la = bpy.context.active_object
                    la.data.materials.append(mats['metal'])
                    # Point light
                    bpy.ops.object.light_add(type='POINT', location=(lamp_x + (-1.8 if lx > 0 else 1.8), lamp_y, 5.5))
                    light = bpy.context.active_object
                    light.data.energy = 550.0
                    light.data.color = (1.0, 0.82, 0.5)
                    light.data.shadow_soft_size = 0.5

def setup_atmosphere_and_cinematic_camera():
    """Sets up volumetric twilight atmosphere, moonlight, and a breathtaking avenue camera angle."""
    scene = bpy.context.scene

    # World Volume & Background
    world = scene.world or bpy.data.worlds.new("CyberMetropolisWorld")
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()

    out_w = nodes.new('ShaderNodeOutputWorld')
    bg_w = nodes.new('ShaderNodeBackground')
    bg_w.inputs['Color'].default_value = (0.008, 0.012, 0.024, 1.0) # Midnight indigo
    bg_w.inputs['Strength'].default_value = 0.6
    links.new(bg_w.outputs['Background'], out_w.inputs['Surface'])

    # Atmospheric Haze / Fog (Volumetric)
    vol_w = nodes.new('ShaderNodeVolumePrincipled')
    vol_w.inputs['Density'].default_value = 0.0018
    vol_w.inputs['Anisotropy'].default_value = 0.65
    vol_w.inputs['Color'].default_value = (0.05, 0.12, 0.25, 1.0) # Cool blue mist
    links.new(vol_w.outputs['Volume'], out_w.inputs['Volume'])

    # Directional Key Moonlight
    bpy.ops.object.light_add(type='SUN', location=(140.0, -160.0, 180.0), rotation=(math.radians(52), math.radians(22), math.radians(-38)))
    sun = bpy.context.active_object
    sun.name = "Key_Moonlight"
    sun.data.energy = 4.5
    sun.data.color = (0.75, 0.88, 1.0)

    # Magenta Horizon City Glow
    bpy.ops.object.light_add(type='SUN', location=(-120.0, 140.0, 60.0), rotation=(math.radians(-40), math.radians(-15), math.radians(130)))
    glow = bpy.context.active_object
    glow.name = "City_Glow_Fill"
    glow.data.energy = 1.6
    glow.data.color = (0.8, 0.15, 0.6)

    # Cinematic Avenue Hero Camera
    # Placed at 3rd-story level looking right down the grand boulevard toward the Megatowers
    # Showing cars, zebra crosswalks, trees, and towering skyscrapers with billboards
    bpy.ops.object.camera_add(location=(-52.0, -82.0, 16.0), rotation=(math.radians(82), 0.0, math.radians(-32)))
    cam = bpy.context.active_object
    cam.name = "Hero_Avenue_Camera"
    cam.data.lens = 22.0 # Dramatic wide angle
    scene.camera = cam

    # Render settings
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = False

def main():
    print("[*] Generating Ultra-Detailed 3D Metropolis...")
    clean_scene()
    mats = create_materials()
    build_detailed_city(mats, grid_size=6, block_size=24.0, road_width=10.0)
    setup_atmosphere_and_cinematic_camera()

    blend_file = "y:/MCP Blender Agent/city_scene.blend"
    bpy.ops.wm.save_as_mainfile(filepath=blend_file)
    print(f"[+] Saved Blender project: {blend_file}")

    preview_img = "y:/MCP Blender Agent/city_preview.png"
    bpy.context.scene.render.filepath = preview_img
    bpy.ops.render.render(write_still=True)
    print(f"[+] Rendered preview image: {preview_img}")
    print("[+] Ultra-Detailed Metropolis generated successfully!")

if __name__ == "__main__":
    main()
