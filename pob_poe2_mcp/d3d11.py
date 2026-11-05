"""Отрисовка команд Lua штатным Direct3D 11 WARP без окна и сторонних пакетов."""

import ctypes as C
from functools import lru_cache
import struct
import sys

from .errors import EngineError
from .tree_assets import Raster

V, U, F, H = C.c_void_p, C.c_uint32, C.c_float, C.c_int32


class Sample(C.Structure):
    _fields_ = [('count', U), ('quality', U)]


class TextureDesc(C.Structure):
    _fields_ = [('width', U), ('height', U), ('mips', U), ('layers', U), ('format', U),
                ('sample', Sample), ('usage', U), ('bind', U), ('cpu', U), ('misc', U)]


class BufferDesc(C.Structure):
    _fields_ = [(name, U) for name in ['size', 'usage', 'bind', 'cpu', 'misc', 'stride']]


class Subresource(C.Structure):
    _fields_ = [('data', V), ('pitch', U), ('slice_pitch', U)]


class Mapped(C.Structure):
    _fields_ = [('data', V), ('pitch', U), ('depth', U)]


class Viewport(C.Structure):
    _fields_ = [(name, F) for name in ['x', 'y', 'width', 'height', 'min_depth', 'max_depth']]


class RenderBlend(C.Structure):
    _fields_ = [(name, U) for name in ['enabled', 'source', 'destination', 'operation', 'source_alpha', 'destination_alpha', 'alpha_operation']] + [('mask', C.c_uint8)]


class BlendDesc(C.Structure):
    _fields_ = [('coverage', U), ('independent', U), ('targets', RenderBlend * 8)]


class RasterizerDesc(C.Structure):
    _fields_ = [('fill', U), ('cull', U), ('counter_clockwise', U), ('bias', H), ('clamp', F),
                ('slope', F), ('depth_clip', U), ('scissor', U), ('multisample', U), ('antialias', U)]


class SamplerDesc(C.Structure):
    _fields_ = [('filter', U), ('u', U), ('v', U), ('w', U), ('bias', F), ('anisotropy', U),
                ('comparison', U), ('border', F * 4), ('min_lod', F), ('max_lod', F)]


DEVICE = {
    'CreateBuffer': (3, H, [V, V, V]), 'CreateTexture2D': (5, H, [V, V, V]),
    'CreateShaderResourceView': (7, H, [V, V, V]), 'CreateRenderTargetView': (9, H, [V, V, V]),
    'CreateVertexShader': (12, H, [V, C.c_size_t, V, V]), 'CreatePixelShader': (15, H, [V, C.c_size_t, V, V]),
    'CreateBlendState': (20, H, [V, V]), 'CreateRasterizerState': (22, H, [V, V]),
    'CreateSamplerState': (23, H, [V, V]),
}
CONTEXT = {
    'VSSetConstantBuffers': (7, None, [U, U, V]), 'PSSetShaderResources': (8, None, [U, U, V]),
    'PSSetShader': (9, None, [V, V, U]), 'PSSetSamplers': (10, None, [U, U, V]),
    'VSSetShader': (11, None, [V, V, U]), 'Draw': (13, None, [U, U]),
    'Map': (14, H, [V, U, U, U, V]), 'Unmap': (15, None, [V, U]),
    'IASetPrimitiveTopology': (24, None, [U]), 'OMSetRenderTargets': (33, None, [U, V, V]),
    'OMSetBlendState': (35, None, [V, V, U]), 'RSSetState': (43, None, [V]),
    'RSSetViewports': (44, None, [U, V]), 'CopyResource': (47, None, [V, V]),
    'ClearRenderTargetView': (50, None, [V, V]), 'ClearState': (110, None, []),
}


def checked(result, operation):
    if result is not None and result < 0:
        raise EngineError('IMAGE_RENDER_FAILED', f'{operation}: HRESULT 0x{result & 0xffffffff:08X}')


class Com:
    def __init__(self, pointer, methods=None):
        self.pointer, self.methods, self.bound = pointer, methods or {}, {}

    def invoke(self, index, result_type, argtypes, *args):
        key = index, result_type, tuple(argtypes)
        if key not in self.bound:
            table = C.cast(self.pointer, C.POINTER(C.POINTER(V))).contents
            self.bound[key] = C.WINFUNCTYPE(result_type, V, *argtypes)(table[index])
        return self.bound[key](self.pointer, *args)

    def call(self, name, *args):
        index, result, types = self.methods[name]
        returned = self.invoke(index, result, types, *args)
        checked(returned, name)
        return returned

    def close(self):
        if self.pointer:
            self.invoke(2, U, [])
            self.pointer = None


SHADER = b'''
cbuffer Quad : register(b0) { float4 corners[4]; float4 coords[4]; float4 tint; };
struct Vertex { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float4 color : COLOR0; };
Vertex vs(uint id : SV_VertexID) {
    const uint indices[6] = {0,1,2,0,2,3}; uint i = indices[id];
    Vertex v; v.pos = corners[i]; v.uv = coords[i].xy; v.color = tint; return v;
}
Texture2DArray art : register(t0); SamplerState filterArt : register(s0);
float4 ps(Vertex v) : SV_TARGET { return art.Sample(filterArt, float3(v.uv, 0)) * v.color; }
'''


@lru_cache(maxsize=2)
def compile_shader(kind):
    dll = C.WinDLL('d3dcompiler_47')
    dll.D3DCompile.restype = H
    dll.D3DCompile.argtypes = [V, C.c_size_t, C.c_char_p, V, V, C.c_char_p, C.c_char_p, U, U, V, V]
    blob, error = V(), V()
    result = dll.D3DCompile(SHADER, len(SHADER), None, None, None, kind.encode(), (kind + '_4_0').encode(), 0, 0, C.byref(blob), C.byref(error))
    try:
        if result < 0 and error:
            pointer = Com(error).invoke(3, V, [])
            raise EngineError('IMAGE_RENDER_FAILED', C.string_at(pointer).decode('utf-8', errors='replace'))
        checked(result, 'D3DCompile')
        source = Com(blob)
        pointer, size = source.invoke(3, V, []), source.invoke(4, C.c_size_t, [])
        return C.string_at(pointer, size)
    finally:
        Com(blob).close()
        Com(error).close()


class Renderer:
    def __init__(self, width, height):
        if sys.platform != 'win32':
            raise EngineError('UNSUPPORTED_PLATFORM', 'Отрисовка дерева требует Windows Direct3D 11')
        self.resources, self.textures = [], {}
        self.width, self.height = width, height
        try:
            self.create_device()
            self.create_target()
            self.create_pipeline()
        except Exception:
            self.close()
            raise

    def owned(self, pointer, methods=None):
        resource = Com(pointer, methods)
        self.resources.append(resource)
        return resource

    def create_device(self):
        dll = C.WinDLL('d3d11')
        dll.D3D11CreateDevice.restype = H
        dll.D3D11CreateDevice.argtypes = [V, U, V, U, V, U, U, V, V, V]
        device, context = V(), V()
        checked(dll.D3D11CreateDevice(None, 5, None, 0, None, 0, 7, C.byref(device), None, C.byref(context)), 'D3D11CreateDevice WARP')
        self.device = self.owned(device, DEVICE)
        self.context = self.owned(context, CONTEXT)

    def create(self, name, *args):
        pointer = V()
        self.device.call(name, *args, C.byref(pointer))
        return self.owned(pointer).pointer

    def create_target(self):
        desc = TextureDesc(self.width, self.height, 1, 1, 87, Sample(1, 0), 0, 32, 0, 0)
        self.target = self.create('CreateTexture2D', C.byref(desc), None)
        view = self.create('CreateRenderTargetView', self.target, None)
        self.context.call('OMSetRenderTargets', 1, C.byref(view), None)
        viewport = Viewport(0, 0, self.width, self.height, 0, 1)
        self.context.call('RSSetViewports', 1, C.byref(viewport))
        self.context.call('ClearRenderTargetView', view, (F * 4)(0.025, 0.035, 0.045, 1))
        desc.usage, desc.bind, desc.cpu = 3, 0, 0x20000
        self.staging = self.create('CreateTexture2D', C.byref(desc), None)

    def create_pipeline(self):
        for kind, method, setter in [('vs', 'CreateVertexShader', 'VSSetShader'), ('ps', 'CreatePixelShader', 'PSSetShader')]:
            code = compile_shader(kind)
            shader = self.create(method, code, len(code), None)
            self.context.call(setter, shader, None, 0)
        desc = BufferDesc(144, 2, 4, 0x10000, 0, 0)
        self.constants = self.create('CreateBuffer', C.byref(desc), None)
        self.context.call('VSSetConstantBuffers', 0, 1, C.byref(self.constants))
        self.context.call('IASetPrimitiveTopology', 4)
        raster = RasterizerDesc(3, 1, 0, 0, 0, 0, 1, 0, 0, 0)
        state = self.create('CreateRasterizerState', C.byref(raster))
        self.context.call('RSSetState', state)
        self.samplers = {clamp: self.sampler(clamp) for clamp in [False, True]}
        self.blends = {mode: self.blend(mode) for mode in ['ALPHA', 'PREALPHA', 'ADDITIVE']}

    def sampler(self, clamp):
        address = 3 if clamp else 1
        desc = SamplerDesc(0x15, address, address, address, 0, 1, 1, (F * 4)(), 0, 3.402823e38)
        return self.create('CreateSamplerState', C.byref(desc))

    def blend(self, mode):
        desc = BlendDesc()
        desc.targets[0] = RenderBlend(1, 2 if mode == 'PREALPHA' else 5,
                                      2 if mode == 'ADDITIVE' else 6, 1, 2, 6, 1, 15)
        return self.create('CreateBlendState', C.byref(desc))

    def texture(self, key, mips):
        if key not in self.textures:
            base = mips[0]
            desc = TextureDesc(base.width, base.height, len(mips), 1, base.format, Sample(1, 0), 1, 8, 0, 0)
            buffers = [C.create_string_buffer(mip.data) for mip in mips]
            data = (Subresource * len(mips))(*(Subresource(C.cast(buffer, V), mip.pitch, len(mip.data)) for buffer, mip in zip(buffers, mips)))
            texture = self.create('CreateTexture2D', C.byref(desc), data)
            srv_desc = (U * 6)(base.format, 5, 0, len(mips), 0, 1)
            self.textures[key] = self.create('CreateShaderResourceView', texture, srv_desc)
        return self.textures[key]

    def draw(self, command, texture):
        corners = command['positions']
        values = []
        for i in range(0, 8, 2):
            values.extend((2 * corners[i] / self.width - 1, 1 - 2 * corners[i + 1] / self.height, 0, 1))
        for i in range(0, 8, 2):
            values.extend((command['uv'][i], command['uv'][i + 1], 0, 0))
        values.extend(command['color'])
        packed = struct.pack('<36f', *values)
        mapped = Mapped()
        self.context.call('Map', self.constants, 0, 4, 0, C.byref(mapped))
        C.memmove(mapped.data, packed, len(packed))
        self.context.call('Unmap', self.constants, 0)
        sampler = self.samplers[command.get('clamp', True)]
        self.context.call('PSSetSamplers', 0, 1, C.byref(sampler))
        self.context.call('PSSetShaderResources', 0, 1, C.byref(texture))
        self.context.call('OMSetBlendState', self.blends[command.get('blend', 'ALPHA')], None, 0xffffffff)
        self.context.call('Draw', 6, 0)

    def raster(self):
        self.context.call('CopyResource', self.staging, self.target)
        mapped = Mapped()
        self.context.call('Map', self.staging, 0, 1, 0, C.byref(mapped))
        try:
            pixels = b''.join(C.string_at(mapped.data + row * mapped.pitch, self.width * 4) for row in range(self.height))
            return Raster(self.width, self.height, pixels)
        finally:
            self.context.call('Unmap', self.staging, 0)

    def close(self):
        if hasattr(self, 'context') and self.context.pointer:
            self.context.call('ClearState')
        for resource in reversed(self.resources):
            resource.close()
        self.resources.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
