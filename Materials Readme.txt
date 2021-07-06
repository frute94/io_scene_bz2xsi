To explicitly set specific material values in a way that prefectly corresponds to BZ2, you can use these overrides in blender per material:
https://docs.blender.org/manual/en/2.79/data_system/custom_properties.html

"diffuse": tuple(float, float, float, float)
"hardness": float
"specular": tuple(float, float, float)
"ambient": tuple(float, float, float)
"emissive": tuple(float, float, float)
"shading_type": integer
"texture": string


If not explicitly set, the exporter will just use the texture image file in the first texture node it finds,
and the default values for the rest of the material settings defined at the top of bz2xsi.py.
