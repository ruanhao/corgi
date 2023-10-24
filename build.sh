#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# Description:

rm -rf ./dist
# python setup.py sdist bdist_wheel --universal
python setup.py sdist bdist_wheel
