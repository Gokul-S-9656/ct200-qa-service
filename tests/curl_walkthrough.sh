#!/usr/bin/env bash
# End-to-end walkthrough of the CT-200 QA Test Case Generator API.
# Run this after starting the server (see README) with:
#   bash tests/curl_walkthrough.sh
set -e
BASE_URL="http://127.0.0.1:8000"

echo "=== 1. Health check ==="
curl -s "$BASE_URL/" | python3 -m json.tool

echo -e "\n=== 2. List top-level sections ==="
curl -s "$BASE_URL/nodes" | python3 -m json.tool

echo -e "\n=== 3. Get a specific node (Error Codes, id=?) with children ==="
NODE_ID=$(curl -s "$BASE_URL/nodes" | python3 -c "import json,sys; d=json.load(sys.stdin); print(next(n['id'] for n in d if 'Error Codes' in n['heading']))")
curl -s "$BASE_URL/nodes/$NODE_ID" | python3 -m json.tool

echo -e "\n=== 4. Search for 'overpressure' ==="
curl -s "$BASE_URL/nodes/search?q=overpressure" | python3 -m json.tool

echo -e "\n=== 5. Create a selection (section 3.3 + 5.3 E3) ==="
E3_ID=$(curl -s "$BASE_URL/nodes/search?q=E3" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")
INVALID_ID=$(curl -s "$BASE_URL/nodes/search?q=Invalid%20Conditions" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")
SELECTION=$(curl -s -X POST "$BASE_URL/selections" \
  -H "Content-Type: application/json" \
  -d "{\"node_ids\": [$E3_ID, $INVALID_ID], \"name\": \"Overpressure + invalid conditions\"}")
echo "$SELECTION" | python3 -m json.tool
SELECTION_ID=$(echo "$SELECTION" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

echo -e "\n=== 6. Retrieve the selection ==="
curl -s "$BASE_URL/selections/$SELECTION_ID" | python3 -m json.tool

echo -e "\n=== 7. Generate QA test cases from the selection (LLM call) ==="
curl -s -X POST "$BASE_URL/selections/$SELECTION_ID/generate" | python3 -m json.tool

echo -e "\n=== 8. Retrieve generations by selection ==="
curl -s "$BASE_URL/selections/$SELECTION_ID/generations" | python3 -m json.tool

echo -e "\n=== 9. Retrieve generations by node ==="
curl -s "$BASE_URL/nodes/$E3_ID/generations" | python3 -m json.tool

echo -e "\n=== Done. Full interactive docs: $BASE_URL/docs ==="
