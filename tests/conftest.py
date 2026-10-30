"""Shared pytest configuration.

Stubs out the ibm_watsonx_orchestrate package so tools/ modules can be imported
in tests without the ADK installed.  This must run before any test module import,
which conftest.py guarantees.

The stubs are registered with sys.modules using setdefault so they never clobber
a real installation if the ADK is actually present.
"""
from __future__ import annotations

import sys
import types


def _ensure_stub(name: str, **attrs) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    for k, v in attrs.items():
        if not hasattr(mod, k):
            setattr(mod, k, v)
    return mod


# Top-level package
_pkg = _ensure_stub("ibm_watsonx_orchestrate")

# agent_builder sub-package
_ab = _ensure_stub("ibm_watsonx_orchestrate.agent_builder")
if not isinstance(getattr(_pkg, "agent_builder", None), types.ModuleType):
    _pkg.agent_builder = _ab

# agent_builder.tools — @tool decorator identity
_tools_mod = _ensure_stub(
    "ibm_watsonx_orchestrate.agent_builder.tools",
    tool=lambda *a, **kw: (a[0] if a and callable(a[0]) else lambda f: f),
)
_ab.tools = _tools_mod

# agent_builder.connections — ConnectionType enum stub
class _ConnectionType:
    KEY_VALUE = "key_value"

_connections_mod = _ensure_stub(
    "ibm_watsonx_orchestrate.agent_builder.connections",
    ConnectionType=_ConnectionType,
)
_ab.connections = _connections_mod

# run — connections helper stub
class _RunConnections:
    @staticmethod
    def key_value(app_id: str) -> dict:
        raise RuntimeError("No live Orchestrate connection in tests")

_run_mod = _ensure_stub(
    "ibm_watsonx_orchestrate.run",
    connections=_RunConnections(),
)
