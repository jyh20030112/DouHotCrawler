from PyInstaller.utils.hooks import collect_data_files

# Patchright registers a hook under this Playwright module name; override it.
datas = collect_data_files("playwright")
