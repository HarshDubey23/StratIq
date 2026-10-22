"""Tiny test runner for environments without pytest: python -m tests.minirun tests.test_engine"""
import importlib
import sys
import traceback

failed = 0
for modname in sys.argv[1:]:
    mod = importlib.import_module(modname)
    for name in dir(mod):
        if name.startswith("test_") and callable(getattr(mod, name)):
            fn = getattr(mod, name)
            undo = []

            class MP:
                def setattr(self, obj, attr, val):
                    undo.append((obj, attr, getattr(obj, attr)))
                    setattr(obj, attr, val)
            try:
                if fn.__code__.co_argcount:
                    fn(MP())
                else:
                    fn()
                print("PASS", modname, name)
            except Exception:
                failed += 1
                print("FAIL", modname, name)
                traceback.print_exc()
            for obj, attr, val in reversed(undo):
                setattr(obj, attr, val)
sys.exit(1 if failed else 0)
