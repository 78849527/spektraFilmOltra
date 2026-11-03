#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -d node_modules ]; then
  echo "首次运行，正在安装前端依赖…"
  npm install --no-audit --no-fund
fi

npm run build
exec npx electron .
