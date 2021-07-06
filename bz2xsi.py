"""This module provides BZ2 XSI utilities, including a parser and writer for XSI files."""
VERSION = 1.1

# No print calls will be made by the module if this is False
ALLOW_PRINT = True

DEFAULT_DIFFUSE = (0.7, 0.7, 0.7, 1.0)
DEFAULT_SPECULAR = (0.35, 0.35, 0.35)
DEFAULT_EMISSIVE = (0.0, 0.0, 0.0)
DEFAULT_AMBIENT = (0.5, 0.5, 0.5)
DEFAULT_HARDNESS = 200.0
DEFAULT_SHADING_TYPE = 2
DEFAULT_TEXTURE = None

DEFAULT_XSI_NAME = "<XSI ROOT>"

RENAME_DUPLICATE_NAMED_FRAMES = True
DUPLICATE_FRAME_NOEXCEPT = False

class DuplicateFrame(Exception): pass

# XSI & Frame inherit from this internal class
class _FrameContainer:
	def __init__(self):
		self.xsi = self
		self.frames = []
	
	def add_frame(self, name):
		if name in self.xsi.frame_table and not DUPLICATE_FRAME_NOEXCEPT:
			raise DuplicateFrame("Duplicate Frame %r" % name)
		
		frame = Frame(name)
		frame.parent = self if not self is self.xsi else None # XSI container itself is not a parent
		frame.xsi = self.xsi
		
		self.xsi.frame_table[name] = frame
		self.frames.append(frame)
		
		return frame
	
	def get_all_frames(self):
		frames = []
		for frame in self.frames:
			frames += [frame] + frame.get_all_frames()
		
		return frames
	
	def find_frame(self, name):
		for frame in self.get_all_frames():
			if frame.name == name:
				return frame
	
	def get_animated_frames(self):
		for frame in self.get_all_frames():
			if frame.animation_keys:
				yield frame
	
	def get_skinned_frames(self):
		for frame in self.get_all_frames():
			if frame.envelopes:
				yield frame
	
	def get_bone_frames(self):
		for frame in self.get_all_frames():
			if frame.is_bone:
				yield frame
	
	def get_all_meshes(self):
		for frame in self.get_all_frames():
			if frame.mesh:
				yield frame.mesh
	
	def get_envelope_count(self):
		"""Returns total amount of envelopes in each frame."""
		return sum((len(f.envelopes) for f in self.get_skinned_frames()))

class XSI(_FrameContainer):
	def __init__(self, filepath=None):
		self.frame_table = {}
		self.lights = []
		self.cameras = []
		self.frames = []
		self.xsi = self
		
		self.name = filepath if filepath else DEFAULT_XSI_NAME
		
		if filepath:
			self.read(filepath)
	
	def read(self, filepath, re_skip=None):
		with open(filepath, "r") as f:
			self.name = filepath
			Reader(f, bz2xsi_xsi=self, re_skip=re_skip, log_name=self.name)
	
	def write(self, filepath):
		with open(filepath, "w") as f:
			Writer(self, f)
	
	def is_skinned(self):
		return len(list(self.get_skinned_frames())) >= 1
	
	def is_animated(self):
		return len(list(self.get_animated_frames())) >= 1
	
	# String representation will result in XML output
	def __str__(self):
		return "%s<XSI>%s%s</XSI>" % (
			"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"no\" ?>\n",
			"".join(map(str, self.lights)),
			"".join(map(str, self.frames)),
		)

class PointLight:
	def __init__(self, name, rgb=None, location_xyz=None):
		self.name = name
		self.rgb = rgb if rgb else (1.0, 1.0, 1.0)
		
		if not location_xyz:
			location_xyz = (0.0, 0.0, 0.0)
		
		self.transform = Matrix(posit=(*location_xyz, 1.0))
	
	def __str__(self):
		return "<PointLight>%s (%f, %f, %f)</PointLight>" % (self.name, *self.rgb)

class Camera:
	def __init__(self, name, location_xyz=None, look_at_xyz=None, roll=0.0, near_plane=0.001, far_plane=1000.0):
		self.name = name
		self.roll = roll
		self.near_plane = near_plane
		self.far_plane = far_plane
		
		if not location_xyz:
			location_xyz = (0.0, 0.0, 0.0)
		
		if not look_at_xyz:
			look_at_xyz = (0.0, 0.0, 0.0)
		
		self.transform = Matrix(posit=(*location_xyz, 1.0))
		self.target = Matrix(posit=(*look_at_xyz, 1.0))
	
	def __str__(self):
		return "<Camera>%s</Camera>" % self.name

class Frame(_FrameContainer):
	def __init__(self, name):
		self.name = name
		self.is_bone = False
		
		self.transform = None
		self.pose = None
		self.mesh = None
		
		self.parent = None
		self.frames = []
		self.animation_keys = []
		
		# About envelopes:
		# Frames (meshes) which are NOT bones contain envelopes.
		# Frames which ARE bones do NOT contain envelopes, but are referenced BY envelopes.
		self.envelopes = []
	
	def __str__(self):
		return "<Frame>%s%s%s%s%s%s%s</Frame>" % (
			self.name,
			str(self.transform),
			str(self.pose),
			str(self.mesh),
			"".join(map(str, self.frames)),
			"".join(map(str, self.animation_keys)),
			"".join(map(str, self.envelopes)),
		)
	
	def get_chained_name(self, delimiter=" -> "):
		frm, chain = self, []
		
		while frm:
			chain += [frm.name]
			frm = frm.parent
		
		return delimiter.join(reversed(chain))
	
	def add_animationkey(self, *args):
		self.animation_keys.append(AnimationKey(*args))
		return self.animation_keys[-1]
	
	def add_envelope(self, *args):
		self.envelopes.append(Envelope(*args))
		return self.envelopes[-1]

class Matrix:
	def __init__(self, right=None, up=None, front=None, posit=None):
		self.right = right if right else (1.0, 0.0, 0.0, 0.0)
		self.up    = up    if up    else (0.0, 1.0, 0.0, 0.0)
		self.front = front if front else (0.0, 0.0, 1.0, 0.0)
		self.posit = posit if posit else (0.0, 0.0, 0.0, 1.0)
	
	def __str__(self):
		return "<Matrix>(x=%f y=%f z=%f)</Matrix>" % tuple(self.posit[0:3])
	
	def to_list(self):
		return [list(self.right), list(self.up), list(self.front), list(self.posit)]

class Mesh:
	def __init__(self, name=None):
		self.name=name
		
		self.vertices = []
		self.faces = []
		
		self.normal_vertices = []
		self.normal_faces = []
		
		self.uv_vertices = []
		self.uv_faces = []
		
		self.face_materials = []
		
		self.vertex_colors = []
		self.vertex_color_faces = []
	
	def __str__(self):
		def XML(name, vertices, faces):
			if vertices or faces:
				return "<%s>%d Vertices %d Faces</%s>" % (
					name,
					len(vertices),
					len(faces),
					name
				)
			else:
				return ""
		
		indices, materials = self.get_material_indices()
		
		return "<Mesh>%d Vertices %d Faces%s%s%s%s</Mesh>" % (
			len(self.vertices),
			len(self.faces),
			"".join(map(str, materials)),
			XML("Normals", self.normal_vertices, self.normal_faces),
			XML("UV-Map", self.uv_vertices, self.uv_faces),
			XML("Vertex-Colors", self.vertex_colors, self.vertex_color_faces)
		)
	
	def get_material_indices(self):
		materials = []
		indices = []
		for material in self.face_materials:
			if not material in materials:
				materials += [material]
			
			indices += [materials.index(material)]
		
		return indices, materials

class Material:
	def __init__(self,
				diffuse=None, hardness=DEFAULT_HARDNESS, specular=None,
				ambient=None, emissive=None, shading_type=DEFAULT_SHADING_TYPE,
				texture=None
			):
		self.diffuse  = diffuse  if diffuse  else list(DEFAULT_DIFFUSE)
		self.specular = specular if specular else list(DEFAULT_SPECULAR)
		self.emissive = emissive if emissive else list(DEFAULT_EMISSIVE)
		self.ambient  = ambient  if ambient  else list(DEFAULT_AMBIENT)
		
		self.hardness = hardness
		self.shading_type = shading_type
		self.texture = texture
		
		if len(self.diffuse) == 3:
			self.diffuse += (1.0,) # Append alpha channel
		
		elif len(self.diffuse) != 4:
			raise TypeError("Material Diffuse color must be RGB or RGBA.")
		
		if len(self.specular) != 3:
			raise TypeError("Material Specular color must be RGB.")
		
		if len(self.emissive) != 3:
			raise TypeError("Material Emissive color must be RGB.")
		
		if len(self.ambient) != 3:
			raise TypeError("Material Ambient color must be RGB.")
	
	def __str__(self):
		return "<Material>%r (%f, %f, %f, %f)</Material>" % (str(self.texture), *self.diffuse)
	
	def __eq__(self, other):
		return (
			self.texture == other.texture
			and self.diffuse      == other.diffuse
			and self.hardness     == other.hardness
			and self.specular     == other.specular
			and self.ambient      == other.ambient
			and self.emissive     == other.emissive
			and self.shading_type == other.shading_type
		)
	
	def __nq__(self, other):
		return not self.__eq__(other)

class AnimationKey:
	TYPE_SIZE = (
		4, # 0: WXYZ Quaternion Rotation
		3, # 1: XYZ Scale
		3, # 2: XYZ Translate
		3  # 3: XYZ Euler Rotation
	)
	
	def __str__(self):
		return "<AnimationKey>%d:%d Keys</AnimationKey>" % (self.key_type, len(self.keys))
	
	def __init__(self, key_type):
		if not key_type in range(4):
			raise ValueError("Invalid Animation Key Type %d" % key_type)
		
		self.key_type = key_type
		self.keys = []
		self.vector_size = __class__.TYPE_SIZE[self.key_type]
	
	def add_key(self, keyframe, vector):
		if len(vector) != self.vector_size:
			raise ValueError("Incorrect Vector Size")
		
		self.keys.append((keyframe, vector))
		
		return self.keys[-1]

class Envelope:
	def __init__(self, bone, vertices=None):
		self.bone = bone # bone is a Frame object which is the bone this envelope refers to.
		self.vertices = vertices if vertices else []
	
	def __str__(self):
		return "<Envelope>Bone %s</Envelope>" % self.bone.name
	
	def add_weight(self, vertex_index, weight_value):
		# (weight_value) is what percent the vertex at index (vertex_index) is influenced by (self.bone)
		self.vertices.append((vertex_index, weight_value))

class XSIParseError(Exception): pass

class Reader:
	# Prevent number strings like "0.0" from raising exceptions in int()
	def int_float(value):
		return int(float(value))
	
	BLOCK_EOF = None
	BLOCK_END = False
	MAX_WORD = 128
	UNNAMED_FRAME_NAME = "unnamed"
	NON_CHARACTERS = "\r"
	
	# These regular expressions allow for looser syntax matching of different XSI template names.
	import re
	RE_HEADER             = re.compile(r"(?i)^\s*xsi\s*0101txt\s*0032\s*$")
	RE_FRAME              = re.compile(r"(?i)(?:SI_)?Frame")
	RE_TRANSFORM_MATRIX   = re.compile(r"(?i)(?:SI_)?(?:Frame)?(?:Transform)?Matrix")
	RE_POSE_MATRIX        = re.compile(r"(?i)(?:SI_)?(?:Frame)?(?:Base)(?:Pose)?Matrix")
	RE_MESH               = re.compile(r"(?i)(?:SI_)?Mesh")
	RE_MESH_MATERIALLIST  = re.compile(r"(?i)(?:SI_)?(?:Mesh)?MaterialList")
	RE_MESH_MATERIAL      = re.compile(r"(?i)(?:SI_)?(?:Mesh)?Material")
	RE_MESH_TEXTURE       = re.compile(r"(?i)(?:SI_)?(?:Texture|TextureFilename)(?:2D)?")
	RE_MESH_NORMALS       = re.compile(r"(?i)(?:SI_)?(?:Mesh)?Normals")
	RE_MESH_VERTEX_COLORS = re.compile(r"(?i)(?:SI_)?(?:Mesh)?VertexColors")
	RE_MESH_UVMAP         = re.compile(r"(?i)(?:SI_)?(?:Mesh)?TextureCoords")
	RE_ANIMATION_SET      = re.compile(r"(?i)(?:SI_)?AnimationSet")
	RE_ANIMATION          = re.compile(r"(?i)(?:SI_)?Animation")
	RE_ANIMATION_KEY      = re.compile(r"(?i)(?:SI_)?AnimationKey")
	RE_ENVELOPE_LIST      = re.compile(r"(?i)(?:SI_)?EnvelopeList")
	RE_ENVELOPE           = re.compile(r"(?i)(?:SI_)?Envelope")
	RE_LIGHT              = re.compile(r"(?i)(?:SI_)?Light")
	RE_CAMERA             = re.compile(r"(?i)(?:SI_)?Camera")

	# Silently skip any blocks that match:
	RE_JUNK = re.compile(r"(?i)(?:SI_)?(?:Fog|Ambience|Angle|Coord.+?|AnimationParam.+?)")
	DEFAULT_RE_SKIP = set((RE_JUNK,))
	
	def __init__(self, f, bz2xsi_xsi=None, re_skip=None, log_name="XSI"):
		self.f = f
		self.xsi = bz2xsi_xsi if bz2xsi_xsi else XSI()
		self.re_skip = Reader.DEFAULT_RE_SKIP.copy() if re_skip is None else re_skip
		
		self.log_name = log_name # Name used in Reader.pos
		self.line = 1
		self.col = 1
		
		self.read()
	
	def pos(self, info=""):
		return "%s:%d:%d:%s" % (self.log_name, self.line, self.col, info)
	
	# Cleans prefix information out of data block names
	def clean(self, name):
		if name[0] == "{" and name[-1] == "}":
			name = name[1:-1]
		
		if name[0:4].casefold() == "frm-":
			return name[4::]
		
		elif name[0:5].casefold() == "anim-":
			return name[5::]
		
		if not name:
			name = Reader.UNNAMED_FRAME_NAME
		
		return name
	
	def parse_block_headers(self):
		while True:
			word = ""
			name, parameters = None, []
			
			for i in range(Reader.MAX_WORD):
				c = self.f.read(1)
				
				# No more data in file
				if not c:
					# yield Reader.BLOCK_EOF, None
					return
				
				# Update line/col for debugging and error reporting
				if c in Reader.NON_CHARACTERS:
					continue
				elif c == "\n":
					self.line += 1
					self.col = 1
				else:
					self.col += 1
				
				# Create word if delimiter is found
				if c in " \t\n{}":
					if word:
						if name == None:
							name = word
						else:
							parameters.append(word)
						
						word = ""
				else:
					# Treat ';' & ',' as delimiters until first character is found
					if word or not c in ",;":
						word += c
				
				if c == "{":
					yield name, parameters
					break
				
				elif c == "}":
					# yield Reader.BLOCK_END, None
					return
			else:
				raise XSIParseError(self.pos("Single Data Word Exceeded %d" % Reader.MAX_WORD))
	
	def parse_word(self):
		word = ""
		in_quote = False
		
		for i in range(Reader.MAX_WORD):
			c = self.f.read(1)
			
			# No more data in file
			if not c:
				return Reader.BLOCK_EOF
			
			# Being in a quote always takes presedence
			if in_quote:
				if c == "\n":
					continue
					# raise XSIParseError(self.pos("Unterminated String"))
				
				if not c in Reader.NON_CHARACTERS:
					self.col += 1
					
					if c == in_quote:
						return word
					
					word += c
					
					continue
			
			# Update line/col for debugging and error reporting
			if c in Reader.NON_CHARACTERS:
				continue
			elif c == "\n":
				self.line += 1
				self.col = 1
			else:
				self.col += 1
			
			# Check for string quote start
			if c in "'\"":
				in_quote = c
				
				continue
			
			# Finalize word if it's been delimited
			if c in " \t\n,;":
				if word:
					return word
				
				continue
			
			word += c
		else:
			raise XSIParseError(self.pos("Single Data Word Exceeded %d" % Reader.MAX_WORD))
	
	def parse_type(self, data_type):
			word = self.parse_word()
			
			if word == None:
				raise XSIParseError(self.pos("Unexpected EOF"))
			
			try:
				return data_type(word)
			
			except ValueError:
				raise XSIParseError(self.pos("Expected %s, got %r" % (data_type.__name__, word)))
	
	def parse_types(self, *read_as_data_type):
		segments = []
		for data_type in read_as_data_type:
			segments.append(self.parse_type(data_type))
		
		return segments
	
	def parse_3d_data(self, vector=(float, float, float), faces_are_indexed=True):
		vertices = []
		for index in range(self.parse_type(Reader.int_float)):
			vertices.append(self.parse_types(*vector))
		
		faces = []
		if faces_are_indexed:
			for face_index in range(self.parse_type(Reader.int_float)):
				index, count = self.parse_types(int, int)
				vector = (int,) * count
				faces.append(self.parse_types(*vector))
		else:
			for face_index in range(self.parse_type(Reader.int_float)):
				count = self.parse_type(int)
				vector = (int,) * count
				faces.append(self.parse_types(*vector))
		
		return vertices, faces
	
	def skip_block(self):
		depth = 1 # Only call skip_block if parser already parsed past initial '{' of block being skipped!
		
		while depth:
			word = self.parse_word()
			
			if word == None:
				return Reader.BLOCK_EOF # raise XSIParseError(self.pos("Unexpected EOF"))
			
			if word == "{":
				depth += 1
			elif word == "}":
				depth -= 1
		
		return Reader.BLOCK_END
	
	def read(self):
		header = " ".join(self.parse_types(str, str, str))
		
		if not Reader.RE_HEADER.match(header):
			raise XSIParseError(self.pos("Invalid XSI Header %r" % header))
		
		for block_type, parameters in self.parse_block_headers():
			if any(r.match(block_type) for r in self.re_skip):
				self.skip_block()
			
			elif Reader.RE_LIGHT.match(block_type):
				self.read_light(self.xsi, parameters)
			
			elif Reader.RE_CAMERA.match(block_type):
				self.read_camera(self.xsi, parameters)
			
			elif Reader.RE_FRAME.match(block_type):
				self.read_frame(self.xsi, parameters)
			
			elif Reader.RE_ANIMATION_SET.match(block_type):
				self.read_animation_set()
			
			elif Reader.RE_ENVELOPE_LIST.match(block_type):
				self.read_envelope_list()
			
			else:
				if ALLOW_PRINT:
					print(self.pos("Unknown Block %r In XSI" % block_type))
				
				self.skip_block()
	
	def read_light(self, parent_container, parameters):
		name = self.clean(parameters[0]) if parameters else Reader.UNNAMED_FRAME_NAME
		
		# 0 = point
		# 1 = directional
		# 2 = spot
		# 3 = Softimage infinite light
		light_type = self.parse_type(Reader.int_float)
		
		if light_type == 0:
			parent_container.lights.append(
				PointLight(
					name=name,
					rgb=self.parse_types(float, float, float),
					location_xyz=self.parse_types(float, float, float)
				)
			)
		
		self.skip_block()
	
	def read_camera(self, parent_container, parameters):
		name = self.clean(parameters[0]) if parameters else Reader.UNNAMED_FRAME_NAME
		
		parent_container.cameras.append(
			Camera(
				name=name,
				location_xyz=self.parse_types(float, float, float),
				look_at_xyz=self.parse_types(float, float, float),
				roll=self.parse_type(float),
				near_plane=self.parse_type(float),
				far_plane=self.parse_type(float)
			)
		)
		
		self.skip_block()
	
	def read_frame(self, parent_frame, parameters):
		name = self.clean(parameters[0]) if parameters else Reader.UNNAMED_FRAME_NAME
		
		if RENAME_DUPLICATE_NAMED_FRAMES:
			for index in range(9999):
				if not name in self.xsi.frame_table:
					break
				
				if ALLOW_PRINT:
					print(self.pos("Duplicate Frame %r Renamed" % name))
				name += "_"
			else:
				raise XSIParseError("Failed To Generate Unique Frame Name")
		
		frame = parent_frame.add_frame(name)
		
		for block_type, parameters in self.parse_block_headers():
			if any(r.match(block_type) for r in self.re_skip):
				self.skip_block()
			
			elif Reader.RE_TRANSFORM_MATRIX.match(block_type):
				frame.transform = self.read_matrix()
		
			elif Reader.RE_POSE_MATRIX.match(block_type):
				frame.pose = self.read_matrix()
			
			elif Reader.RE_MESH.match(block_type):
				frame.mesh = self.read_mesh()
			
			elif Reader.RE_FRAME.match(block_type):
				self.read_frame(frame, parameters)
			
			# Sometimes XSI files might have unclosed braces for frames.
			# In this scenario the animation set or envelope list may appear as a child of the last frame.
			# Because these are non-hierarchical blocks we can just read them as if they were parsed globally
			# outside of frames at root level.
			elif Reader.RE_ANIMATION_SET.match(block_type):
				self.read_animation_set()
			
			elif Reader.RE_ENVELOPE_LIST.match(block_type):
				self.read_envelope_list()
			
			else:
				if ALLOW_PRINT:
					print(self.pos("Unknown Block %r In Frame %r" % (block_type, frame.name)))
				
				self.skip_block()
		
		return frame
	
	def read_matrix(self):
		matrix = Matrix(
			self.parse_types(float, float, float, float),
			self.parse_types(float, float, float, float),
			self.parse_types(float, float, float, float),
			self.parse_types(float, float, float, float)
		)
		
		self.skip_block()
		return matrix
	
	def read_mesh(self):
		mesh = Mesh()
		
		mesh.vertices, mesh.faces = self.parse_3d_data((float, float, float), False)
		
		for block_type, parameters in self.parse_block_headers():
			if any(r.match(block_type) for r in self.re_skip):
				self.skip_block()
			
			elif Reader.RE_MESH_MATERIALLIST.match(block_type):
				self.read_material_list(mesh)
			
			elif Reader.RE_MESH_NORMALS.match(block_type):
				mesh.normal_vertices, mesh.normal_faces = self.parse_3d_data((float, float, float), True)
				self.skip_block()
			
			elif Reader.RE_MESH_UVMAP.match(block_type):
				mesh.uv_vertices, mesh.uv_faces = self.parse_3d_data((float, float), True)
				self.skip_block()
			
			elif Reader.RE_MESH_VERTEX_COLORS.match(block_type):
				mesh.vertex_colors, mesh.vertex_color_faces = self.parse_3d_data((float, float, float, float), True)
				self.skip_block()
			
			else:
				print(self.pos("Unknown Block %r In Mesh" % block_type))
				self.skip_block()
		
		return mesh
	
	def read_material_list(self, mesh):
		material_count = self.parse_type(Reader.int_float)
		material_face_count = self.parse_type(Reader.int_float)
		material_face_indices = self.parse_types(*(int,) * material_face_count)
		materials = []
		
		for block_type, parameters in self.parse_block_headers():
			if any(r.match(block_type) for r in self.re_skip):
				self.skip_block()
			
			elif Reader.RE_MESH_MATERIAL.match(block_type):
				materials.append(self.read_material())
			
			else:
				if ALLOW_PRINT:
					print(self.pos("Unknown Block %r In Mesh Material List" % block_type))
				self.skip_block()
		
		# Make sure material count matches the one specified in the header.
		while len(materials) < material_count:
			if ALLOW_PRINT:
				print(self.pos("Missing Material %d in Mesh Material List" % len(materials)))
			materials.append(Material()) # Assign default material
		
		# Assign data to Mesh object
		for index in material_face_indices:
			# Note: material face index being > material list size would result in IndexError being raised
			mesh.face_materials.append(materials[index])
	
	def read_material(self):
		material = Material(
			diffuse      = self.parse_types(float, float, float, float),
			hardness     = self.parse_type(float),
			specular     = self.parse_types(float, float, float),
			emissive     = self.parse_types(float, float, float),
			shading_type = self.parse_type(Reader.int_float),
			ambient      = self.parse_types(float, float, float)
		)
		
		for block_type, parameters in self.parse_block_headers():
			if any(r.match(block_type) for r in self.re_skip):
				self.skip_block()
			
			elif Reader.RE_MESH_TEXTURE.match(block_type):
				material.texture = self.parse_type(str)
				self.skip_block() # BZ2 only uses texture file name
			
			else:
				if ALLOW_PRINT:
					print("Unknown Block In Material %r" % block_type)
				self.skip_block()
		
		return material
	
	def read_animation_set(self):
		for block_type, parameters in self.parse_block_headers():
			if any(r.match(block_type) for r in self.re_skip):
				self.skip_block()
			
			elif Reader.RE_ANIMATION.match(block_type):
				self.read_animation(parameters)
			
			else:
				if ALLOW_PRINT:
					print(self.pos("Unknown Block %r In Animation Set" % block_type))
				self.skip_block()
	
	def read_animation(self, parameters):
		name = self.clean(parameters[0]) if parameters else Reader.UNNAMED_FRAME_NAME
		frame_name = self.clean(self.parse_type(str))
		
		if not frame_name in self.xsi.frame_table:
			if ALLOW_PRINT:
				print(self.pos("Invalid Frame %r Referenced By Animation %r" % (frame_name, name)))
			self.skip_block()
		else:
			frame = self.xsi.frame_table[frame_name]
			
			for block_type, parameters in self.parse_block_headers():
				if any(r.match(block_type) for r in self.re_skip):
					self.skip_block()
				
				elif Reader.RE_ANIMATION_KEY.match(block_type):
					self.read_animation_key(frame)
				
				else:
					if ALLOW_PRINT:
						print(self.pos("Unknown Block %r In Animation %r" % (block_type, name)))
					self.skip_block()
	
	def read_animation_key(self, frame):
		try:
			key = AnimationKey(self.parse_type(Reader.int_float))
			key_count = self.parse_type(Reader.int_float)
			
			for animation_index in range(key_count):
				keyframe = self.parse_type(Reader.int_float)
				vector = (float,) * self.parse_type(int)
				key.add_key(keyframe, self.parse_types(*vector))
			
			frame.animation_keys.append(key)
		except ValueError as msg:
			if ALLOW_PRINT:
				print(self.pos(msg))
		
		self.skip_block()
	
	def read_envelope_list(self):
		envelope_count = self.parse_type(Reader.int_float)
		
		for block_type, parameters in self.parse_block_headers():
			if any(r.match(block_type) for r in self.re_skip):
				self.skip_block()
			
			elif Reader.RE_ENVELOPE.match(block_type):
				self.read_envelope()
				envelope_count -= 1
			
			else:
				if ALLOW_PRINT:
					print(self.pos("Unknown Block %r In Envelope List" % block_type))
				self.skip_block()
		
		if envelope_count != 0:
			if ALLOW_PRINT:
				print("Envelope Count Mismatch In Envelope List")
		
		self.skip_block()
	
	def read_envelope(self):
		frame_name = self.clean(self.parse_type(str))
		bone_name  = self.clean(self.parse_type(str))
		error_format = None
		
		if not frame_name in self.xsi.frame_table:
			error_format = ("Frame", frame_name, "Bone", bone_name)
			if ALLOW_PRINT:
				print(self.pos("Invalid %s %r Used By Envelope For %s %r" % error_format))
		
		if not bone_name in self.xsi.frame_table:
			error_format = ("Bone", bone_name, "Frame", frame_name)
			if ALLOW_PRINT:
				print(self.pos("Invalid %s %r Used By Envelope For %s %r" % error_format))
		
		if error_format:
			self.skip_block()
			return
		
		frame = self.xsi.frame_table[frame_name]
		bone = self.xsi.frame_table[bone_name]
		bone.is_bone = True
		weight_count = self.parse_type(Reader.int_float)
		envelope = frame.add_envelope(bone)
		
		for weight_index in range(weight_count):
			envelope.add_weight(*self.parse_types(int, float))
		
		self.skip_block()

class Writer:
	def __init__(self, bz2xsi_xsi, f):
		self.xsi = bz2xsi_xsi
		self.file = f
		
		if f:
			self.write_xsi()
	
	def get_safe_name(self, name, sub="_"):
		ENABLE_NAME_WARNING = False
		
		if not name:
			name = "unnamed"
			if ENABLE_NAME_WARNING:
				print("XSI WRITER WARNING: Object with no name renamed to %r." % name)
		
		allowed = "QWERTYUIOPASDFGHJKLZXCVBNMqwertyuiopasdfghjklzxcvbnm1234567890_-"
		new_name = "".join((c if c in allowed else sub) for c in name)
		
		if ENABLE_NAME_WARNING and new_name != name:
			print("XSI WRITER WARNING: Object %r renamed to %r." % (new_name, name))
		
		return new_name
	
	def write(self, t=0, data=""):
		self.file.write("\t" * t + data + "\n")
	
	def write_vector_list(self, t, format_string, vectors):
		self.write(t, "%d;" % len(vectors))
		if not vectors: return
		
		for vector in vectors[0:-1]:
			self.write(t, format_string % tuple(vector) + ",")
		else:
			self.write(t, format_string % tuple(vectors[-1],) + ";")
	
	def write_face_list(self, t, faces, indexed=True):
		def make_face(face):
			return "%d;" % len(face) + ",".join(str(i) for i in face) + ";"
		
		self.write(t, "%d;" % len(faces))
		if not faces: return
		
		if not indexed:
			for face in faces[0:-1]:
				self.write(t, make_face(face) + ",")
			self.write(t, make_face(faces[-1]) + ";")
		else:
			for index, face in enumerate(faces[0:-1]):
				self.write(t, "%d;" % index + make_face(face) + ",")
			self.write(t, "%d;" % (len(faces)-1) + make_face(faces[-1]) + ";")
	
	def write_face_vertices(self, t, format_string, faces, vertices):
		self.write(t, "%d;" % len(vertices))
		if not vertices: return
		
		for face in faces:
			for index in face[0:-1]:
				self.write(t, format_string % tuple(vertices[index]) + ",")
			else:
				self.write(t, format_string % tuple(vertices[face[-1]]) + ";")
	
	def write_animationkeys(self, t, keys):
		self.write(t, "%d;" % len(keys))
		if not keys: return
		
		vector_size = len(keys[0][1])
		format_string = "%d;%d;" + ";".join(["%f"] * vector_size) + ";;%s"
		
		for keyframe, vector in keys[0:-1]:
			self.write(t, format_string % (keyframe, vector_size, *vector, ","))
		self.write(t, format_string % (keys[-1][0], vector_size, *keys[-1][1], ";"))
	
	def write_xsi(self):
		self.write(0, "xsi 0101txt 0032\n")
		
		self.write(0, "SI_CoordinateSystem coord {")
		self.write(1, "1;")
		self.write(1, "0;")
		self.write(1, "1;")
		self.write(1, "0;")
		self.write(1, "2;")
		self.write(1, "5;")
		self.write(0, "}")
		
		for root_frame in self.xsi.frames:
			self.write()
			self.write_frame(0, root_frame)
		
		animated_frames = tuple(self.xsi.get_animated_frames())
		if animated_frames:
			self.write(0, "\nAnimationSet {")
			
			for frame in animated_frames:
				self.write_animation(1, frame)
			
			self.write(0, "}")
		
		skinned_frames = tuple(self.xsi.get_skinned_frames())
		if skinned_frames:
			self.write(0, "\nSI_EnvelopeList {")
			self.write(1, "%d;" % self.xsi.get_envelope_count())
			
			for frame in skinned_frames:
				for envelope in frame.envelopes:
					self.write_envelope(1, frame, envelope)
			
			self.write(0, "}")
	
	def write_frame(self, t, frame):
		self.write(t, "Frame frm-%s {" % self.get_safe_name(frame.name))
		
		if frame.transform:
			self.write_matrix(t + 1, frame.transform, "FrameTransformMatrix")
		
		if frame.pose:
			self.write_matrix(t + 1, frame.pose, "SI_FrameBasePoseMatrix")
		
		if frame.mesh:
			self.write_mesh(t + 1, frame.mesh, frame.mesh.name if frame.mesh.name else frame.name)
		
		for sub_frame in frame.frames:
			self.write_frame(t + 1, sub_frame)
		
		self.write(t, "}")
	
	def write_matrix(self, t, matrix, block_name):
		self.write(t, block_name + " {")
		self.write(t + 1, "%f,%f,%f,%f,"  % tuple(matrix.right))
		self.write(t + 1, "%f,%f,%f,%f,"  % tuple(matrix.up))
		self.write(t + 1, "%f,%f,%f,%f,"  % tuple(matrix.front))
		self.write(t + 1, "%f,%f,%f,%f;;" % tuple(matrix.posit))
		self.write(t, "}")
	
	def write_mesh(self, t, mesh, name):
		self.write(t, "Mesh %s {" % self.get_safe_name(name))
		
		if mesh.vertices:
			self.write_vector_list(t + 1, "%f;%f;%f;", mesh.vertices)
			
			if mesh.faces:
				self.write_face_list(t + 1, mesh.faces, indexed = False)
			
			if mesh.face_materials and mesh.faces:
				face_material_indices, materials = mesh.get_material_indices()
				
				self.write(t + 1, "MeshMaterialList {")
				self.write(t + 2, "%d;" % len(materials))
				self.write(t + 2, "%d;" % len(face_material_indices))
				for index in face_material_indices[0:-1]:
					self.write(t + 2, "%d," % index)
				else:
					self.write(t + 2, "%d;" % face_material_indices[-1])
				
				for material in materials:
					self.write_material(t + 2, material)
				
				self.write(t + 1, "}")
			
			if mesh.normal_vertices:
				self.write(t + 1, "SI_MeshNormals {")
				self.write_vector_list(t + 2, "%f;%f;%f;", mesh.normal_vertices)
				
				if mesh.normal_faces:
					self.write_face_list(t + 2, mesh.normal_faces, indexed=True)
				
				self.write(t + 1, "}")
			
			if mesh.uv_vertices:
				self.write(t + 1, "SI_MeshTextureCoords {")
				self.write_vector_list(t + 2, "%f;%f;", mesh.uv_vertices)
				
				if mesh.uv_faces:
					self.write_face_list(t + 2, mesh.uv_faces, indexed=True)
				
				self.write(t + 1, "}")
			
			if mesh.vertex_colors and mesh.vertex_color_faces:
				self.write(t + 1, "SI_MeshVertexColors {")
				self.write_face_vertices(
					t + 2,
					"%f;%f;%f;%f;",
					mesh.vertex_color_faces,
					mesh.vertex_colors
				)
				self.write_face_list(t + 2, mesh.vertex_color_faces, indexed=True)
				self.write(t + 1, "}")
		
		self.write(t, "}")
	
	def write_material(self, t, material):
		self.write(t, "SI_Material {")
		self.write(t + 1, "%f;%f;%f;%f;;" % tuple(material.diffuse))
		self.write(t + 1, "%f;" % material.hardness)
		self.write(t + 1, "%f;%f;%f;;" % tuple(material.specular))
		self.write(t + 1, "%f;%f;%f;;" % tuple(material.emissive))
		self.write(t + 1, "%d;" % material.shading_type)
		self.write(t + 1, "%f;%f;%f;;" % tuple(material.ambient))
		
		if material.texture:
			self.write(t + 1, "SI_Texture2D {")
			self.write(t + 2, "\"%s\";" % material.texture)
			self.write(t + 1, "}")
		
		self.write(t, "}")
	
	def write_animation(self, t, frame):
		self.write(t, "Animation anim-%s {" % self.get_safe_name(frame.name))
		self.write(t + 1, "{frm-%s}" % self.get_safe_name(frame.name))
		
		for anim_key in frame.animation_keys:
			self.write(t + 1, "SI_AnimationKey {")
			self.write(t + 2, "%d;" % anim_key.key_type)
			self.write_animationkeys(t + 2, anim_key.keys)
			self.write(t + 1, "}")
		
		self.write(t, "}")
	
	def write_envelope(self, t, frame, envelope):
		self.write(t, "SI_Envelope {")
		self.write(t + 1, "\"frm-%s\";" % self.get_safe_name(frame.name))
		self.write(t + 1, "\"frm-%s\";" % self.get_safe_name(envelope.bone.name))
		self.write_vector_list(t + 1, "%d;%f;", envelope.vertices)
		self.write(t, "}")

def read(filepath, regex_skip_types=None):
	with open(filepath, "r") as f:
		if regex_skip_types == None:
			reader = Reader(f, bz2xsi_xsi=None, log_name=filepath) # Use defaults
		else:
			reader = Reader(f, bz2xsi_xsi=None, log_name=filepath, re_skip=regex_skip_types)
		
		return reader.xsi
