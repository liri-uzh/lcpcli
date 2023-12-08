#!/bin/bash

cd ./lcp-upload/
pip install -r requirements.txt
python setup.py install

cd ../corpert/
pip install -r requirements.txt
python setup.py install

cd ../
python setup.py install