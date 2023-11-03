#!/usr/bin/env sh
# add  "templateDir": "sdk/templates/py" to JSON or -t sdk/templates/py to CLI

if [[ ! -d node_modules ]]; then
	echo Run npm install first
	exit 1
fi

rm -rf sdk/py
tempyml=$(mktemp)
npx p2o Plant.id_v3.postman_collection.json -o p2o_options.json >"${tempyml}"
npx openapi-generator-cli generate -g python -i "${tempyml}" -o sdk/py -c py_conf.json
rm -f "${tempyml}"
