"""Build the portable Windows directory from this repository's current source."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed',
        '--name', 'DXPX_Helper', '--distpath', str(root/'dist'), '--workpath', str(root/'.build'),
        '--specpath', str(root/'.build'), '--add-data', str(root/'assets') + ';assets']
for name in ['liblzma.dll','LIBBZ2.dll','libexpat.dll','tcl86t.dll','tk86t.dll','ffi.dll']:
    path = Path(sys.base_prefix)/'Library'/'bin'/name
    if path.is_file():
        args += ['--add-binary', str(path) + ';.']
args += [str(root/'src'/'app.py')]
subprocess.run(args, cwd=root, check=True)
output = root/'dist'/'DXPX_Helper'
for track, name in [('jjfz','积极分子'),('fzdx','发展对象')]:
    command = '@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0DXPX_Helper.exe" --track '+track+' --auto %*\r\n'
    (output/(name+'一键启动.cmd')).write_bytes(command.encode('ascii'))
import shutil
shutil.copyfile(root/'使用教程.txt', output/'使用教程.txt')
shutil.copytree(root/'assets'/'题库', output/'题库', dirs_exist_ok=True)
print(output)
