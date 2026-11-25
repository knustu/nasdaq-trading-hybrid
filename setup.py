from __future__ import annotations

import sys

import pybind11
from setuptools import Extension, setup

compile_args = ["/std:c++17", "/O2", "/utf-8", "/EHsc"] if sys.platform.startswith("win") else ["-std=c++17", "-O3", "-Wall", "-Wextra"]

extension = Extension(
    "trading_engine",
    sources=[
        "cpp_engine/bind_module.cpp",
        "cpp_engine/engine.cpp",
    ],
    include_dirs=[pybind11.get_include(), "cpp_engine"],
    language="c++",
    extra_compile_args=compile_args,
)

setup(
    name="trading_engine",
    version="2.0.1",
    description="Hybrid C++ strategy/risk engine for the customer trading application",
    ext_modules=[extension],
    python_requires=">=3.11",
)
