import os


class PyoHelper:
    def __init__(self,
                 pyodide_app_name: str,
                 pyodide_folder='pyodide_content'
                 ):
        self._abs_app_path = f"{os.getcwd()}{os.sep}{pyodide_folder}{os.sep}{pyodide_app_name}"

        with open(f"{self._abs_app_path}{os.sep}{pyodide_app_name}.js") as f:
            self.js_file = f.read().strip()

        with open(f"{self._abs_app_path}{os.sep}{pyodide_app_name}.py") as f:
            self.py_file = f.read().strip()
