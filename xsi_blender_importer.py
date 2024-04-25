import bpy
from mathutils import Matrix, Vector, Euler, Quaternion
from bpy_extras import image_utils

from . import bz2xsi
from math import radians, floor, ceil
import os

DEBUGGING_BONES = False

# Normals changed in 4.1 from 4.0
OLD_NORMALS = not (bpy.app.version[0] >= 4 and bpy.app.version[1] >= 1)

class InvalidXSI(Exception): pass
class UnsupportedAnim(InvalidXSI): pass

def find_texture(texture_filepath, search_directories, acceptable_extensions, recursive=False):
	acceptable_extensions = list(acceptable_extensions)
	
	if os.path.exists(texture_filepath):
		return texture_filepath
	
	file_name, original_extension = os.path.splitext(os.path.basename(texture_filepath))
	
	original_extension_compare = original_extension.lower()
	while original_extension_compare in acceptable_extensions:
		# Remove if already present, so we don't look twice
		del acceptable_extensions[acceptable_extensions.index(original_extension_compare)]
	
	# Originally specified extension will be searched for first
	acceptable_extensions = [original_extension] + acceptable_extensions
	
	for ext in acceptable_extensions:
		for directory in search_directories:
			for root, folders, files in os.walk(directory):
				path = os.path.join(root, file_name + ext)
				
				if os.path.exists(path) and os.path.isfile(path):
					return path
				
				if not recursive:
					break
	
	# Return as-is by default
	return file_name + original_extension

def flags_from_name(name):
	flags = name.split("__")
	flags = flags[-1].casefold() if len(flags) >= 2 else ""
	first_name = name.split("_")[0].casefold()
	
	if first_name == "flame":
		flags += "IFe" # "F" = special flame
	
	elif first_name == "hp":
		flags += "h"
	
	elif first_name == "tractor":
		flags += "I" # "I" = ignore hidden flag
	
	return flags

class Load:
	def __init__(self, operator, context, filepath="", **opt):
		self.opt = opt
		self.context = context
		
		self.name = os.path.basename(filepath)
		self.filefolder = os.path.dirname(filepath)
		self.ext_list = self.opt["find_textures_ext"].casefold().split()
		self.tex_dir = self.context.preferences.filepaths.texture_directory
		
		self.bpy_armature = None		
		
		# Note: we are assuming unique frame names using these.
		self.bpy_obj_of_bone = {}
		self.animated_bones = set()
		self.animated_objects = []
		
		self.bpy_objects = [] # All objects we create
		bpy_root_objects = [] # Objects we create without parents
		
		bz2_xsi = self.load_xsi(filepath) # Entire file is read into this object
		
		# Deselect objects in blender
		for bpy_obj in self.context.scene.objects:
			bpy_obj.select_set(False)
		
		if self.opt["import_lights"]:
			for xsi_light in bz2_xsi.lights:
				bpy_root_objects += [self.import_light(xsi_light)]
		
		if self.opt["import_cameras"]:
			for xsi_camera in bz2_xsi.cameras:
				bpy_root_objects += [*self.import_camera(xsi_camera)]
		
		if self.opt["import_envelopes"] and bz2_xsi.is_skinned():
			self.bpy_armature = bpy.data.objects.new(self.name, bpy.data.armatures.new(self.name))
			self.context.view_layer.active_layer_collection.collection.objects.link(self.bpy_armature)
		
		for xsi_frame in bz2_xsi.frames:
			bpy_root_objects += [self.walk(xsi_frame)]
		
		if self.bpy_armature:
			# Blender offers no other way to create bones than using bpy.ops.
			# This requires us to switch object modes to create 'edit' bones.
			# If any exceptions occur after this blender will be left in edit mode.
			self.bpy_armature.select_set(True)
			self.context.view_layer.objects.active = self.bpy_armature
			
			if DEBUGGING_BONES:
				self.bpy_armature.data.show_names = True
				self.bpy_armature.data.show_axes = True 
				self.bpy_armature.data.axes_position = 0.0 # 1.0 for tail, 0.0 for head
			
			bpy.ops.object.mode_set(mode="EDIT")
			
			for xsi_frame in bz2_xsi.frames:
				self.walk_skel(xsi_frame)
			
			bpy.ops.object.mode_set(mode="OBJECT")
		
		if self.opt["import_animations"] and bz2_xsi.is_animated():
			root_frame_options = self.opt["rotate_for_yz"] or self.opt["place_at_cursor"]
			
			if self.bpy_armature:
				bpy_anim = self.bpy_armature.animation_data_create()
				bpy_anim.action = bpy.data.actions.new(name="Skeleton Animations")
				
				for xsi_frame, name in self.animated_bones:
					if not xsi_frame.parent and root_frame_options:
						print("Root-level bone has animation: %r" % xsi_frame.get_chained_name())
					
					bpy_posebone = self.bpy_armature.pose.bones[name]
					self.import_animations(xsi_frame, bpy_posebone, bpy_anim, as_bone=True)
			
			for xsi_frame, bpy_obj in self.animated_objects:
				if not xsi_frame.parent and root_frame_options:
					print("Root-level frame has animation: %r" % xsi_frame.get_chained_name())
				
				bpy_anim = bpy_obj.animation_data_create()
				bpy_anim.action = bpy.data.actions.new(name="anim-" + xsi_frame.name)
				self.import_animations(xsi_frame, bpy_obj, bpy_anim, as_bone=False)
			
			start_frame, end_frame = xsi_frame.get_animation_frame_range()
			self.context.scene.frame_start = start_frame
			self.context.scene.frame_end = end_frame
			self.context.scene.frame_current = start_frame
		
		# Armature will be the only root object, if present
		if self.bpy_armature:
			for bpy_obj in bpy_root_objects:
				bpy_obj.parent = self.bpy_armature
			
			bpy_root_objects = [self.bpy_armature]
		
		for bpy_obj in bpy_root_objects:
			if self.opt["rotate_for_yz"]:
				bpy_obj.rotation_euler[0] = radians(90)
				bpy_obj.rotation_euler[2] = radians(180)
				bpy_obj.location[1], bpy_obj.location[2] = bpy_obj.location[2], bpy_obj.location[1] # Swap y and z
			
			if self.opt["place_at_cursor"]:
				bpy_obj.location += context.scene.cursor.location
		
		for bpy_obj in self.bpy_objects:
			bpy_obj.select_set(True)
		
		if bpy_root_objects:
			self.context.view_layer.objects.active = bpy_root_objects[0]
	
	def load_xsi(self, filepath):
		reader = bz2xsi.Reader
		re_skip = set()
		re_skip.add(reader.RE_JUNK)
		
		if not self.opt["import_lights"]:
			re_skip.add(reader.RE_LIGHT)
		
		if not self.opt["import_cameras"]:
			re_skip.add(reader.RE_CAMERA)
		
		if not self.opt["import_animations"]:
			re_skip.add(reader.RE_ANIMATION_SET)
			
		if not self.opt["import_envelopes"]:
			re_skip.add(reader.RE_ENVELOPE_LIST)
		
		if self.opt["import_mesh"]:
			if not self.opt["import_mesh_normals"]:
				re_skip.add(reader.RE_MESH_NORMALS)
			
			if not self.opt["import_mesh_materials"]:
				re_skip.add(reader.RE_MESH_MATERIALLIST)
			
			if not self.opt["import_mesh_uvmap"]:
				re_skip.add(reader.RE_MESH_UVMAP)
			
			if not self.opt["import_mesh_vertcolor"]:
				re_skip.add(reader.RE_MESH_VERTEX_COLORS)
		
		else:
			re_skip.add(reader.RE_MESH)
			re_skip.add(reader.RE_MESH_MATERIALLIST)
			re_skip.add(reader.RE_MESH_NORMALS)
			re_skip.add(reader.RE_MESH_UVMAP)
			re_skip.add(reader.RE_MESH_VERTEX_COLORS)
			re_skip.add(reader.RE_ENVELOPE_LIST)
		
		self.ignore_invalid_animations = True
		
		return bz2xsi.read(filepath, regex_skip_types=re_skip)
	
	def create_object(self, name, data, matrix, bpy_obj_parent=None):
		bpy_obj = bpy.data.objects.new(name=name, object_data=data)
		
		if bpy_obj_parent:
			bpy_obj.parent = bpy_obj_parent
		
		bpy_obj.matrix_local = matrix
		
		self.bpy_objects += [bpy_obj]
		self.context.view_layer.active_layer_collection.collection.objects.link(bpy_obj)
		
		return bpy_obj
	
	def walk(self, xsi_frame, bpy_parent=None):
		bpy_matrix = self.import_matrix(xsi_frame.transform)
		bpy_mesh = None
		
		flags = flags_from_name(xsi_frame.name) if self.opt["emulate_flags"] else ""
		
		if self.opt["import_mesh"] and xsi_frame.mesh:
			bpy_mesh = self.import_mesh(xsi_frame.mesh, xsi_frame.name, flags)
		
		bpy_obj = self.create_object(
			xsi_frame.name if not xsi_frame.is_bone else "%s" % xsi_frame.name, # "bone_%s"
			bpy_mesh,
			bpy_matrix,
			bpy_parent
		)
		
		if not bpy_mesh:
			bpy_obj.empty_display_type = "ARROWS"
			bpy_obj.empty_display_size = 0.1
			bpy_obj.show_name = True
		
		if "I" not in flags:
			if "h" in flags or "c" in flags:
				# Hardpoints, Collisions and Hidden shown as wireframe in viewport
				bpy_obj.display_type = "WIRE"
		
		if self.bpy_armature and bpy_mesh and xsi_frame.envelopes:
			self.import_envelopes(xsi_frame, bpy_obj)
			bpy_obj.modifiers.new(name="Armature", type="ARMATURE").object = self.bpy_armature
			pass
			# raise Exception("Empty object cannot have envelopes %r." % (bpy_obj.name))
		
		if xsi_frame.is_bone:
			self.bpy_obj_of_bone[xsi_frame.name] = bpy_obj # So walk_skel() can get this object
		
		if xsi_frame.animation_keys:
			self.animated_objects += [(xsi_frame, bpy_obj)]
		
		for xsi_sub_frame in xsi_frame.frames:
			self.walk(xsi_sub_frame, bpy_obj)
		
		return bpy_obj
	
	def walk_skel(self, xsi_frame, bpy_editbone_parent=None):
		bpy_editbone = None
		
		if xsi_frame.is_bone:
			bpy_editbone = self.bpy_armature.data.edit_bones.new(xsi_frame.name)
			bpy_editbone.parent = bpy_editbone_parent
			
			bpy_matrix = self.bpy_obj_of_bone[xsi_frame.name].matrix_world
			bpy_vector = bpy_matrix.to_translation()
			bpy_editbone.head = (bpy_vector.x, bpy_vector.y, bpy_vector.z)
			bpy_child_positions = [child.matrix_world.to_translation() for child in self.bpy_obj_of_bone[xsi_frame.name].children]
			
			if bpy_child_positions:
				child_sum = Vector((0.0, 0.0, 0.0))
				for bpy_child_vector in bpy_child_positions:
					child_sum += bpy_child_vector
				
				child_average = child_sum / len(bpy_child_positions)
				bpy_editbone.tail = (child_average.x, child_average.y, child_average.z)
			
			else:
				if bpy_editbone_parent:
					# Make it continue along the same direction as its parent with 1/10 the length
					bpy_editbone.tail = bpy_editbone_parent.head
					bpy_editbone.length = -bpy_editbone.length/10
				
				else:
					# No parent, no children.
					bpy_editbone.tail = (bpy_vector.x, bpy_vector.y, bpy_vector.z + 1.0)
			
			if (bpy_editbone.head == bpy_editbone.tail):
				bpy_editbone.tail = (bpy_vector.x, bpy_vector.y, bpy_vector.z + 1.0)
				print("Zero-length bone %r" % xsi_frame.get_chained_name())
				# raise Exception("Zero-length bone %r" % xsi_frame.get_chained_name())
			
			self.animated_bones.add((xsi_frame, bpy_editbone.name))
		
		for xsi_sub_frame in xsi_frame.frames:
			self.walk_skel(xsi_sub_frame, bpy_editbone)
	
	def import_light(self, xsi_light):
		bpy_data = bpy.data.lights.new(name=xsi_light.name, type="POINT")
		bpy_data.color = tuple(xsi_light.rgb)
		
		bpy_obj = self.create_object(
			xsi_light.name,
			bpy_data,
			self.import_matrix(xsi_light.transform)
		)
		
		return bpy_obj
	
	def import_camera(self, xsi_camera):
		bpy_data = bpy.data.cameras.new(name=xsi_camera.name)
		bpy_data.clip_end = xsi_camera.near_plane
		bpy_data.clip_start = xsi_camera.far_plane
		
		bpy_obj = self.create_object(
			xsi_camera.name,
			bpy_data,
			self.import_matrix(xsi_camera.transform)
		)
		
		bpy_obj.rotation_euler[2] = radians(xsi_camera.roll)
		
		# Create an empty look-at object for the camera to track to
		bpy_obj_look = self.create_object(
			xsi_camera.name + " (Look-At Constraint)",
			None,
			self.import_matrix(xsi_camera.target)
		)
		
		# Add a constraint for the camera to look at the empty we just created
		bpy_con = bpy_obj.constraints.new(type="DAMPED_TRACK")
		bpy_con.track_axis = "TRACK_NEGATIVE_Z"
		bpy_con.target = bpy_obj_look
		
		return bpy_obj, bpy_obj_look
	
	def import_matrix(self, xsi_matrix):
		return Matrix(xsi_matrix.to_list()).transposed()
	
	def import_envelopes(self, xsi_frame, bpy_obj):
		bpy_groups = []
		for envelope in xsi_frame.envelopes:
			if envelope.vertices:
				bpy_vertgroup = bpy_obj.vertex_groups.new(name=envelope.bone.name)
				
				if bpy_vertgroup:
					for vertex_index, weight in envelope.vertices:
						bpy_vertgroup.add([vertex_index], weight / 100.0, "ADD")
				
				bpy_groups += [bpy_vertgroup]
		
		return bpy_groups
	
	def import_mesh(self, xsi_mesh, name, flags):
		bpy_mesh = bpy.data.meshes.new(name)
		bpy_mesh.from_pydata(xsi_mesh.vertices, [], xsi_mesh.faces)
		
		if self.opt["import_mesh_normals"] and xsi_mesh.normal_vertices:
			if xsi_mesh.normal_faces:
				try:
					normals = []
					for norm_face in xsi_mesh.normal_faces:
						for norm_index in norm_face:
							normals += [xsi_mesh.normal_vertices[norm_index]]
					bpy_mesh.normals_split_custom_set(normals)
				
				except IndexError:
					bpy_mesh.normals_split_custom_set_from_vertices(xsi_mesh.normal_vertices)
			
			else:
				bpy_mesh.normals_split_custom_set_from_vertices(xsi_mesh.normal_vertices)
			
			if OLD_NORMALS:
				bpy_mesh.use_auto_smooth = True
		
		if self.opt["import_mesh_materials"]:
			xsi_face_indices, xsi_materials = xsi_mesh.get_material_indices()
			if xsi_materials:
				for index, xsi_material in enumerate(xsi_materials):
					bpy_mesh.materials.append(
						self.import_material(
							xsi_material,
							"%s %d" % (name, index),
							emissive=bool("e" in flags or "g" in flags),
							emissive_strength=7.0 if "g" in flags else 1.0,
							double_sided=bool("2" in flags),
							use_vcol=bool(xsi_mesh.vertex_colors),
							notex=bool("F" in flags) # ignore texture if true
						)
					)
				
				for index, material_index in enumerate(xsi_face_indices):
					bpy_mesh.polygons[index].material_index = material_index
		
		if self.opt["import_mesh_uvmap"] and xsi_mesh.uv_vertices:
			bpy_uvmap = bpy_mesh.uv_layers.new().data
			
			if xsi_mesh.uv_faces:
				bpy_uv_index = 0
				for uv_face in xsi_mesh.uv_faces:
					for uv_index in uv_face:
						bpy_uvmap[bpy_uv_index].uv = Vector(tuple(xsi_mesh.uv_vertices[uv_index]))
						bpy_uv_index += 1
			
			else:
				for index, uv_vert in enumerate(xsi_mesh.uv_vertices):
					bpy_uvmap[index].uv = Vector(tuple(uv_vert))
		
		if self.opt["import_mesh_vertcolor"] and xsi_mesh.vertex_colors:
			bpy_vcol = bpy_mesh.vertex_colors.new().data
			
			if xsi_mesh.vertex_color_faces:
				bpy_vcol_index = 0
				for vcol_face in xsi_mesh.vertex_color_faces:
					for vcol_index in vcol_face:
						bpy_vcol[bpy_vcol_index].color = tuple(xsi_mesh.vertex_colors[vcol_index])
						bpy_vcol_index += 1
			else:
				for index, color in enumerate(xsi_mesh.vertex_colors):
					bpy_vcol[index].color = tuple(color)
		
		return bpy_mesh
	
	def import_material(self, xsi_material, name, emissive=False, emissive_strength=1.0, double_sided=False, use_vcol=False, notex=False):
		COL = 320 # column spacing for nodes
		
		image_filepath = xsi_material.texture
		bpy_material = bpy.data.materials.new(name=name)
		bpy_material.use_nodes = True
		bpy_material.use_backface_culling = not double_sided
		bpy_material.show_transparent_back = double_sided
		bpy_material.blend_method = "BLEND"
		
		alpha = float(xsi_material.diffuse[3]) if len(xsi_material.diffuse) >= 4 else 1.0
		specular_rgb = tuple(float(x) for x in xsi_material.specular[0:3]) if len(xsi_material.specular) >= 3 else (0.5, 0.5, 0.5)
		
		bpy_node_bsdf = bpy_material.node_tree.nodes["Principled BSDF"]
		bpy_node_bsdf.inputs["Base Color"].default_value = tuple(xsi_material.diffuse[0:3]) + (1.0,)
		bpy_node_bsdf.inputs["Specular IOR Level"].default_value = 0.5 # Specular Intensity
		bpy_node_bsdf.inputs["Specular Tint"].default_value = tuple((*specular_rgb, 1.0))
		bpy_node_bsdf.inputs["Alpha"].default_value = alpha
		bpy_node_bsdf.inputs["Emission Strength"].default_value = emissive_strength
		bpy_node_bsdf.inputs["Emission Color"].default_value = xsi_material.diffuse if emissive else (0.0, 0.0, 0.0, 0.0) # Emissive
		
		if use_vcol:
			bpy_node_attribute = bpy_material.node_tree.nodes.new("ShaderNodeAttribute")
			bpy_node_attribute.attribute_name = "Col"
			bpy_node_attribute.attribute_type = "GEOMETRY"
			bpy_node_attribute.location = (-COL*2, COL)
		
		# Texture is used for material
		if type(image_filepath) == str and not notex:
			image = image_utils.load_image(
				find_texture(image_filepath, (self.filefolder, self.tex_dir), self.ext_list, self.opt["find_textures"]),
				place_holder=True,
				check_existing=True
			)
			
			# BZ2 Chrome
			if os.path.basename(image_filepath)[0:-4].casefold() == "reflection3":
				bpy_node_bsdf.inputs[4].default_value = 1.0 # Metallic
				bpy_node_bsdf.inputs[7].default_value = 0.0 # Roughness
			
			# Texture image
			bpy_node_texture = bpy_material.node_tree.nodes.new("ShaderNodeTexImage")
			bpy_node_texture.label = os.path.basename(image_filepath)
			bpy_node_texture.image = image
			bpy_node_texture.location = (-COL*2, 0)
			
			# Multiplies with either diffuse color, or with vertex color (which overrides diffuse)
			bpy_node_mixrgb = bpy_material.node_tree.nodes.new("ShaderNodeMixRGB")
			bpy_node_mixrgb.inputs["Fac"].default_value = 1.0 # Factor
			bpy_node_mixrgb.inputs["Color1"].default_value = bpy_node_bsdf.inputs[0].default_value # Default Mix
			bpy_node_mixrgb.blend_type = "MULTIPLY"
			bpy_node_mixrgb.location = (-COL, 0)
			
			# Alpha mixed (lowest value used) with vertex color alpha or diffuse alpha
			bpy_node_alphamath = bpy_material.node_tree.nodes.new("ShaderNodeMath")
			bpy_node_alphamath.inputs[0].default_value = bpy_node_bsdf.inputs["Alpha"].default_value
			bpy_node_alphamath.operation = "MINIMUM" # Use whichever is more transparent - texture alpha vs vertex or diffuse alpha
			bpy_node_alphamath.location = (-COL, -COL)
			
			# Texture alpha to math
			bpy_material.node_tree.links.new(
				bpy_node_alphamath.inputs[1],
				bpy_node_texture.outputs["Alpha"]
			)
			
			if use_vcol:
				# Multiply diffuse with vertex colors
				bpy_material.node_tree.links.new(
					bpy_node_mixrgb.inputs["Color1"],
					bpy_node_attribute.outputs["Color"]
				)
				
				# Vertex color alpha to math
				bpy_material.node_tree.links.new(
					bpy_node_alphamath.inputs[0],
					bpy_node_attribute.outputs["Alpha"]
				)
				
				# Math to shader alpha
				bpy_material.node_tree.links.new(
					bpy_node_bsdf.inputs["Alpha"],
					bpy_node_alphamath.outputs["Value"]
				)
			
			# Texture to color mixer
			bpy_material.node_tree.links.new(
				bpy_node_mixrgb.inputs["Color2"],
				bpy_node_texture.outputs["Color"]
			)
			
			# Final color to shader
			bpy_material.node_tree.links.new(
				bpy_node_bsdf.inputs["Base Color"],
				bpy_node_mixrgb.outputs["Color"]
			)
			
			# Final alpha to shader alpha
			bpy_material.node_tree.links.new(
				bpy_node_bsdf.inputs["Alpha"],
				bpy_node_alphamath.outputs["Value"]
			)
			
			# Emissive (no lighting mode)
			if emissive:
				bpy_material.node_tree.links.new(
					bpy_node_mixrgb.outputs["Color"],
					bpy_node_bsdf.inputs["Emission Color"]
				)
		
		# No texture
		else:
			if use_vcol:
				# Vertex color as diffuse
				bpy_material.node_tree.links.new(
					bpy_node_attribute.outputs["Color"],
					bpy_node_bsdf.inputs["Base Color"]
				)
				
				# Vertex color alpha
				bpy_material.node_tree.links.new(
					bpy_node_bsdf.inputs["Alpha"],
					bpy_node_attribute.outputs["Alpha"]
				)
				
				if emissive:
					bpy_material.node_tree.links.new(
						bpy_node_attribute.outputs["Color"],
						bpy_node_bsdf.inputs["Emission Color"]
					)
		
		if self.opt["add_material_overrides"]: # Blender Material Custom Properties
			bpy_material["diffuse"] = [float(value) for value in xsi_material.diffuse]
			bpy_material["hardness"] = float(xsi_material.hardness)
			bpy_material["specular"] = [float(value) for value in xsi_material.specular]
			bpy_material["ambient"] = [float(value) for value in xsi_material.ambient]
			bpy_material["emissive"] = [float(value) for value in xsi_material.emissive]
			bpy_material["shading_type"] = int(xsi_material.shading_type)
			
			if xsi_material.texture:
				bpy_material["texture"] = str(xsi_material.texture)
		
		return bpy_material
	
	def import_animations(self, xsi_frame, bpy_animated, bpy_anim, as_bone=False):
		key_data_paths = ["rotation_quaternion", "scale", "location", "rotation_euler"]
		bpy_mult = Matrix()
		
		if as_bone:
			# bpy_animated is a PoseBone
			key_data_paths = ["pose.bones[\"%s\"].%s" % (bpy_animated.name, data_path) for data_path in key_data_paths]
			bpy_mult = Matrix()
			# TODO: This is where we can fix the fucked up bone anims
		
		else:
			# bpy_animated is an Object
			bpy_mult = bpy_animated.matrix_local
		
		for xsi_animkey in xsi_frame.animation_keys:
			key_type = xsi_animkey.key_type
			
			if not key_type in (0, 1, 2, 3):
				error = "Unknown Animation Key Type %d in %r" % (key_type, xsi_frame.get_chained_name())
				
				if not self.ignore_invalid_animations:
					raise UnsupportedAnim(error)
				
				print(error)
				continue
			
			if key_type == 1 and not self.ignore_invalid_animations:
				error = "Scale Anmations Unsupported %d in %r" % (key_type, xsi_frame.get_chained_name())
				raise UnsupportedAnim(error)
			
			vector_size = xsi_animkey.TYPE_SIZE[key_type]
			data_path = key_data_paths[key_type]
			keys = xsi_animkey.keys.copy()
			
			if key_type == 0:
				if not self.opt["quat_anims_to_euler"]:
					# WXYZ Quaternion
					for index, (keyframe, vector) in enumerate(keys):
						bpy_matrix = Quaternion(vector).to_matrix().to_4x4().transposed() @ bpy_mult
						bpy_quat = bpy_matrix.to_quaternion()
						keys[index] = keyframe, (bpy_quat.w, bpy_quat.x, bpy_quat.y, bpy_quat.z)
					
					bpy_animated.rotation_mode = "QUATERNION"
				
				else:
					# WXYZ Quaternion converted to XYZ Euler
					for index, (keyframe, vector) in enumerate(keys):
						bpy_quat = Quaternion((vector[0], vector[1], vector[2], vector[3]))
						bpy_matrix = bpy_quat.to_matrix().to_4x4().transposed() @ bpy_mult
						bpy_euler = bpy_matrix.to_euler()
						keys[index] = keyframe, (bpy_euler.x, bpy_euler.y, bpy_euler.z)
					
					data_path = key_data_paths[3]
					vector_size = xsi_animkey.TYPE_SIZE[3]
					key_type = 3
					
					bpy_animated.rotation_mode = "XYZ" # Euler
			
			elif key_type == 3:
				# XYZ Euler
				for index, (keyframe, vector) in enumerate(keys):
					bpy_matrix = Euler(vector).to_matrix().to_4x4().transposed() @ bpy_mult
					bpy_euler = bpy_matrix.to_euler()
					keys[index] = keyframe, (bpy_euler.x, bpy_euler.y, bpy_euler.z)
			
			elif key_type == 2:
				# XYZ Translation
				pass
			
			elif key_type == 1:
				# XYZ Scale - not supported in BZ2
				pass
			
			if self.opt["remove_negative_rotations"] and key_type in (0, 3):
				is_quaternion = (key_type == 0)
				
				if is_quaternion: # Convert from quaternion to euler
					for index, (keyframe, vector) in enumerate(keys):
						bpy_euler = Quaternion((vector[0], vector[1], vector[2], vector[3])).to_euler()
						keys[index] = keyframe, (bpy_euler.x, bpy_euler.y, bpy_euler.z)
				
				max_rotation = radians(360)
				for index, (keyframe, vector) in enumerate(keys):
					keys[index] = keyframe, [v % max_rotation for v in vector]
				
				if is_quaternion: # Convert back to quaternion from euler, after having removed negative rotations
					for index, (keyframe, vector) in enumerate(keys):
						bpy_quat = Euler((vector[0], vector[1], vector[2])).to_quaternion()
						keys[index] = keyframe, (bpy_quat.w, bpy_quat.x, bpy_quat.y, bpy_quat.z)
			
			fcurves = [bpy_anim.action.fcurves.new(data_path=data_path, index=index) for index in range(vector_size)]
			
			for fcurve in fcurves:
				fcurve.keyframe_points.add(len(keys))
			
			for index, (keyframe, vector) in enumerate(keys):
				for fcurve_index, fcurve in enumerate(fcurves):
					fcurve.keyframe_points[index].co = keyframe, vector[fcurve_index]
			
			for fcurve in fcurves:
				fcurve.extrapolation = "LINEAR"
				fcurve.update()

def load(operator, context, filepath="", **opt):
	Load(operator, context, filepath, **opt)
	return {"FINISHED"}
