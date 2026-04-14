import os
import ctypes

lib_dir = r"E:\Medicon\venv\Lib\site-packages\torch\lib"
os.add_dll_directory(lib_dir)

for file in os.listdir(lib_dir):
    if file.endswith(".dll"):
        dll_path = os.path.join(lib_dir, file)
        try:
            ctypes.WinDLL(dll_path)
            print("OK:", file)
        except Exception as e:
            print("FAIL:", file, e)
