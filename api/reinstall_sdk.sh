#!/usr/bin/env sh
pip uninstall -y aioplantid_sdk
pushd sdk/py
rm -rf dist build
python setup.py bdist_wheel
pip install dist/aioplantid_sdk-3.0.0-py3-none-any.whl
popd
