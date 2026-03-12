import importlib

def test_import_tools_opz_f3_t2_runner():
    m = importlib.import_module("tools.opz_f3_t2_runner")
    assert hasattr(m, "main")
