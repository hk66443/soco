python3 - <<'SOCO_COMPILE_ISOLATED'
import hashlib,json,os,shutil,subprocess
from pathlib import Path
root=Path('/root/soco-verified-tests')
work=root/'adapter-clean-build-20261121-v1'
assert work.resolve()==work and root in work.parents and work.is_dir()
source=work/'adapter-amd64-clean.c';output=work/'libsoco-amd64.so';receipt=work/'build_receipt.json'
assert not output.exists() and not receipt.exists()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='dd10f8c3c93c0df342448f5c1fafdac9ef72570d28368376f37af6d7f8443ef4'
assert sha(source)==expected
formal_paths=['/usr/local/soga/soga','/usr/local/soco/soco','/usr/local/soco/libsoco.so','/etc/soco/soco.conf','/etc/systemd/system/soco.service']
formal_before={p:sha(p) for p in formal_paths}
def run(a,input=None):
 p=subprocess.run(a,input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=work,timeout=60)
 return {'argv':a,'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
result={'source':str(source),'source_sha256':expected,'work':str(work),'gcc':shutil.which('gcc')}
if not result['gcc']:raise RuntimeError('Existing gcc missing')
result['gcc_version']=run(['gcc','--version'])
result['headers_preflight']=run(['gcc','-E','-x','c','-'], '#include <curl/curl.h>\n#include <json-c/json.h>\nint main(void){return 0;}\n')
# Only expose the last diagnostic lines for failed header checks; no source secrets exist.
result['headers_preflight']['stdout']='header preprocessor output length=%d'%len(result['headers_preflight']['stdout'])
if result['headers_preflight']['exit_code']!=0:
 receipt.write_text(json.dumps(result,indent=2));receipt.chmod(0o600)
 print(json.dumps(result));raise SystemExit(3)
argv=['gcc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror','-Wl,-z,relro,-z,now','-o','libsoco-amd64.so','adapter-amd64-clean.c','-lcurl','-ljson-c']
result['compile']=run(argv)
if result['compile']['exit_code']==0:
 output.chmod(0o600);result['output']=str(output);result['output_sha256']=sha(output);result['output_size']=output.stat().st_size
 result['dynamic']=run(['readelf','-d',str(output)])
 result['dyn_symbols']=run(['readelf','--dyn-syms','--wide',str(output)])
 result['versions']=run(['readelf','--version-info',str(output)])
 result['elf_header']=run(['readelf','-h',str(output)])
 result['ldd']=run(['ldd',str(output)])
result['formal_before']=formal_before;result['formal_after']={p:sha(p) for p in formal_paths}
result['production_unchanged']=result['formal_before']==result['formal_after']
result['service_after']=run(['systemctl','show','soco.service','--property=MainPID,ActiveState,SubState,NRestarts,ExecMainStartTimestamp'])
assert 'MainPID=80093' in result['service_after']['stdout'] and 'ActiveState=active' in result['service_after']['stdout'] and result['production_unchanged']
receipt.write_text(json.dumps(result,indent=2));receipt.chmod(0o600)
print(json.dumps({'source_sha256':expected,'compile_exit':result['compile']['exit_code'],'output':result.get('output'),'sha256':result.get('output_sha256'),'bytes':result.get('output_size'),'receipt':str(receipt),'gcc':result['gcc_version']['stdout'].splitlines()[0],'production_unchanged':result['production_unchanged'],'compiler_stderr':result['compile']['stderr']}))
raise SystemExit(result['compile']['exit_code'])
SOCO_COMPILE_ISOLATED
