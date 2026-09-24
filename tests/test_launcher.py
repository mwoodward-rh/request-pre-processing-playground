"""Launcher tests never install, download, start models, or stop external processes."""
import importlib.util
from pathlib import Path
import sys
import subprocess
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('runtime', SCRIPTS/'runtime.py')
runtime = importlib.util.module_from_spec(spec)
sys.modules['runtime'] = runtime
spec.loader.exec_module(runtime)

def test_defaults_and_cpu(tmp_path):
    env = runtime.config(tmp_path, {})
    assert env['JEV_DEVICE'] == 'cpu' and env['JEV_MODE'] == 'local'
    assert env['JEV_TOKENIZER'] == str(tmp_path/'models/open-jev/tokenizer.json')

def test_env_precedence_and_no_shell_evaluation(tmp_path):
    (tmp_path/'.env').write_text('EXTRACTION_MODEL="file-model"\nJEV_MODEL_PATH=custom\n')
    env = runtime.config(tmp_path, {'EXTRACTION_MODEL':'shell-model'})
    assert env['EXTRACTION_MODEL'] == 'shell-model'
    assert env['JEV_TOKENIZER'] == str(tmp_path/'custom/tokenizer.json')
    (tmp_path/'.env').write_text('EXTRACTION_MODEL=$(touch never-run)\n')
    assert runtime.config(tmp_path,{})['EXTRACTION_MODEL'] == '$(touch never-run)'
    assert not (tmp_path/'never-run').exists()

@pytest.mark.parametrize('line', ['UNKNOWN=x','JEV_MODE=bad','LAB_PORT=80','JEV_URL=http://example.com:8022',
                                'JEV_URL=http://127.0.0.1:8030','EXTRACTION_URL=http://user:secret@localhost'])
def test_reject_bad_config(tmp_path,line):
    (tmp_path/'.env').write_text(line)
    with pytest.raises(ValueError): runtime.config(tmp_path,{})

def test_explicit_external_service(tmp_path):
    env = runtime.config(tmp_path, {'JEV_MODE':'external', 'JEV_URL':'http://10.0.0.2:8022'})
    assert env['JEV_MODE']=='external'

def test_existing_ollama_not_started(monkeypatch):
    monkeypatch.setattr(runtime,'request',lambda *a,**kw: {'models':[]})
    owned=runtime.Processes()
    runtime.ensure_ollama(runtime.DEFAULTS,owned)
    assert owned.children == []

def test_missing_model(monkeypatch):
    monkeypatch.setattr(runtime,'request',lambda *a,**kw: {'models':[{'name':'other:latest'}]})
    with pytest.raises(RuntimeError,match='not installed'): runtime.check_ollama(runtime.DEFAULTS)

def test_ownership_cleanup():
    class Process:
        def __init__(self): self.stopped=False
        def poll(self): return None if not self.stopped else 0
        def terminate(self): self.stopped=True
        def wait(self,timeout=None): return 0
    owned=runtime.Processes(); child=Process(); external=Process(); owned.children.append(child)
    owned.close()
    assert child.stopped and not external.stopped

def test_custom_port_origin(monkeypatch):
    from backend.app import app
    from fastapi.testclient import TestClient
    monkeypatch.setenv('LAB_PORT','8031')
    client=TestClient(app)
    assert client.get('/api/health',headers={'Origin':'http://127.0.0.1:8031'}).status_code == 200
    assert client.get('/api/health',headers={'Origin':'http://127.0.0.1:8032'}).status_code == 403

def test_setup_skip_downloads(monkeypatch,tmp_path):
    spec = importlib.util.spec_from_file_location('lab_setup', SCRIPTS/'setup.py')
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    env = runtime.config(tmp_path, {'JEV_MODE':'external'})
    monkeypatch.setattr(setup,'config',lambda:env)
    monkeypatch.setattr(setup,'ROOT',tmp_path)
    monkeypatch.setattr(sys,'argv',['setup.py','--skip-downloads'])
    commands=[]
    monkeypatch.setattr(setup,'run',lambda args,env:commands.append([str(a) for a in args]))
    monkeypatch.setattr(setup,'ensure_ollama',lambda *a:pytest.fail('Must not start Ollama'))
    monkeypatch.setattr(setup,'request',lambda *a,**k:pytest.fail('Must not pull a model'))
    setup.main()
    assert ['npm','ci'] in commands and ['npm','run','build'] in commands
    assert not any('.venv-jev' in ' '.join(command) for command in commands)
