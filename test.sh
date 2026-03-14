#!/usr/bin/env bash

FILE="${1:-test_messages.txt}"
API="${2:-http://localhost:8000}"

if [[ ! -f "$FILE" ]]; then
  echo "Usage: $0 [messages_file] [api_url]"
  echo "Error: file '$FILE' not found"
  exit 1
fi

echo "API: $API"
echo "File: $FILE"
echo "---"

total=0
failed=0

while IFS= read -r msg || [[ -n "$msg" ]]; do
  [[ -z "$msg" ]] && continue

  total=$((total + 1))

  body=$(curl -s -o /tmp/_classify_body -w "%{http_code}" -X POST "$API/classify" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg t "$msg" '{text: $t}')")

  http_code="$body"
  body=$(cat /tmp/_classify_body)

  echo "[$total] $msg"

  if [[ "$http_code" != "200" ]]; then
    echo "    ERROR: HTTP $http_code"
    echo "    $body"
    failed=$((failed + 1))
  else
    importance=$(echo "$body" | jq -r '.importance')
    urgency=$(echo "$body" | jq -r '.urgency')
    category=$(echo "$body" | jq -r '.category')
    requires_human=$(echo "$body" | jq -r '.requires_human')
    owner=$(echo "$body" | jq -r '.recommended_owner')
    echo "    importance=$importance  urgency=$urgency  category=$category"
    echo "    requires_human=$requires_human  recommended_owner=$owner"
  fi

  echo ""
done < "$FILE"

echo "---"
echo "Done: $total messages, $failed failed"
