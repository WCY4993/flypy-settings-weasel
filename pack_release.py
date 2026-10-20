"""Build a clean release from tracked source, the GUI and a verified upstream."""
from pathlib import Path
import hashlib
import io
import json
import subprocess
import urllib.request
import zipfile

ROOT=Path(__file__).parent

def main():
    lock=json.loads((ROOT/'upstream.json').read_text(encoding='utf-8'))
    url=f"https://codeload.github.com/iDvel/rime-ice/zip/{lock['commit']}"
    with urllib.request.urlopen(url,timeout=120) as response: data=response.read()
    if hashlib.sha256(data).hexdigest()!=lock['archive_sha256']:
        raise RuntimeError('Upstream archive checksum mismatch')
    exe=ROOT/'dist/小鶴設定工具.exe'
    if not exe.is_file():raise RuntimeError('Build the GUI first')
    from settings_core import VERSION
    version=VERSION
    destination=ROOT/'dist'/f'Flypy-Settings-{version}-Windows-x64.zip'
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').split('\0')
    verification=json.loads((ROOT/'VERIFICATION.json').read_text(encoding='utf-8'))
    verification['exe_sha256']=hashlib.sha256(exe.read_bytes()).hexdigest()
    verification['release_source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as out:
        for name in tracked:
            if name and name!='VERIFICATION.json':out.write(ROOT/name,name)
        out.writestr('VERIFICATION.json',json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
        out.write(ROOT/'flypy_taiwan.dict.yaml','flypy_taiwan.dict.yaml')
        out.write(exe,'小鶴設定工具.exe')
        with zipfile.ZipFile(io.BytesIO(data)) as upstream:
            prefix=f"rime-ice-{lock['commit']}/"
            for info in upstream.infolist():
                if not info.is_dir():
                    if not info.filename.startswith(prefix):raise RuntimeError('Unexpected upstream archive layout')
                    relative=info.filename[len(prefix):]
                    if '..' in Path(relative).parts:raise RuntimeError('Invalid upstream path')
                    out.writestr('upstream/'+relative,upstream.read(info))
    checksum=ROOT/'dist'/f'Flypy-Settings-{version}-SHA256.txt'
    checksum.write_text(f'{hashlib.sha256(destination.read_bytes()).hexdigest()}  {destination.name}\n{verification["exe_sha256"]}  小鶴設定工具.exe\n',encoding='utf-8')
    print(destination.name)

if __name__=='__main__':main()
