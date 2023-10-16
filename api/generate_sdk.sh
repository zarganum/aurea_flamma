#!/usr/bin/env sh
# add  "templateDir": "sdk/templates/py" to JSON or -t sdk/templates/py to CLI

rm -rf sdk/py
npx p2o Plant.id_v3.postman_collection.json -o sdk/p2o_options.json >sdk/Plant.id_v3_API.spec.yml 
npx openapi-generator-cli generate -g python -i sdk/Plant.id_v3_API.spec.yml -o sdk/py -c sdk/py_conf.json