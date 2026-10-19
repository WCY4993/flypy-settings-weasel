"""Minimal official librime 1.x levers API binding, isolated in a subprocess."""
import ctypes as C
import json
import os
from pathlib import Path

P, V, I = C.c_char_p, C.c_void_p, C.c_int
class Traits(C.Structure):
    _fields_ = [('data_size', I)] + [(n, P) for n in ['shared_data_dir', 'user_data_dir', 'distribution_name', 'distribution_code_name', 'distribution_version', 'app_name']] + [('modules', C.POINTER(P)), ('min_log_level', I)] + [(n, P) for n in ['log_dir', 'prebuilt_data_dir', 'staging_dir']]
class Module(C.Structure):
    _fields_ = [('data_size', I), ('name', P), ('initialize', V), ('finalize', V), ('get_api', V)]
class Iterator(C.Structure):
    _fields_ = [('ptr', V), ('i', C.c_size_t)]
NAMES = ['custom_settings_init', 'custom_settings_destroy', 'load_settings', 'save_settings', 'customize_bool', 'customize_int', 'customize_double', 'customize_string', 'is_first_run', 'settings_is_modified', 'settings_get_config', 'switcher_settings_init', 'get_available_schema_list', 'get_selected_schema_list', 'schema_list_destroy', 'get_schema_id', 'get_schema_name', 'get_schema_version', 'get_schema_author', 'get_schema_description', 'get_schema_file_path', 'select_schemas', 'get_hotkeys', 'set_hotkeys', 'user_dict_iterator_init', 'user_dict_iterator_destroy', 'next_user_dict', 'backup_user_dict', 'restore_user_dict', 'export_user_dict', 'import_user_dict', 'customize_item']
class Levers(C.Structure):
    _fields_ = [('data_size', I)] + [(n, V) for n in NAMES]

def export_all(user_root, weasel_root, destination):
    user_root, weasel_root, destination = map(Path, (user_root, weasel_root, destination))
    destination.mkdir(parents=True, exist_ok=True)
    with os.add_dll_directory(str(weasel_root)):
        dll = C.CDLL(str(weasel_root / 'rime.dll'))
    traits = Traits()
    traits.data_size = C.sizeof(Traits) - C.sizeof(I)
    traits.shared_data_dir = str(weasel_root / 'data').encode('utf-8')
    traits.user_data_dir = str(user_root).encode('utf-8')
    traits.app_name = b'rime.flypy_settings'
    traits.log_dir = str(destination).encode('utf-8')
    traits.min_log_level = 2
    dll.RimeSetup.argtypes = dll.RimeDeployerInitialize.argtypes = [C.POINTER(Traits)]
    dll.RimeFindModule.argtypes = [P]
    dll.RimeFindModule.restype = C.POINTER(Module)
    dll.RimeSetup(C.byref(traits))
    dll.RimeDeployerInitialize(C.byref(traits))
    counts = {}
    try:
        module = dll.RimeFindModule(b'levers')
        if not module or not module.contents.get_api:
            raise RuntimeError('librime levers module is unavailable')
        api = C.CFUNCTYPE(C.POINTER(Levers))(module.contents.get_api)().contents
        if api.data_size < Levers.export_user_dict.offset + C.sizeof(V) - C.sizeof(I):
            raise RuntimeError('librime levers API version is incompatible')
        init = C.CFUNCTYPE(I, C.POINTER(Iterator))(api.user_dict_iterator_init)
        finish = C.CFUNCTYPE(None, C.POINTER(Iterator))(api.user_dict_iterator_destroy)
        next_dict = C.CFUNCTYPE(P, C.POINTER(Iterator))(api.next_user_dict)
        export = C.CFUNCTYPE(I, P, P)(api.export_user_dict)
        iterator = Iterator()
        if not init(C.byref(iterator)):
            raise RuntimeError('Cannot enumerate user dictionaries')
        try:
            while name := next_dict(C.byref(iterator)):
                decoded = name.decode('utf-8')
                if Path(decoded).name != decoded or '/' in decoded or '\\' in decoded:
                    raise RuntimeError('Unsafe dictionary name')
                final = destination / (decoded + '.txt')
                temp = final.with_suffix('.pending')
                try:
                    count = export(name, str(temp).encode('utf-8'))
                    if count < 0:
                        raise RuntimeError('Cannot export user dictionary: ' + decoded)
                    os.replace(temp, final)
                    counts[decoded] = count
                finally:
                    temp.unlink(missing_ok=True)
        finally:
            finish(C.byref(iterator))
        (destination / 'export-info.json').write_text(json.dumps(counts), encoding='utf-8')
    finally:
        dll.RimeFinalize()
    return counts
