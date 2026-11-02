#!/bin/zsh
# Spektrafilm 启动器：双击即可打开界面（约 1-3 分钟后窗口出现，首次较慢）
# 关闭 = 直接关窗口；若要彻底退出请 ⌘Q。

cd "/Users/megmeet/Documents/开发 APP/Spektrafilm"

export NUMBA_CACHE_DIR=/tmp/sf_numba_cache
export PYTHONPYCACHEPREFIX=/tmp/sf_pycache

exec /Users/megmeet/.workbuddy-ai/binaries/python/envs/spektrafilm/bin/python -c "from spektrafilm_gui.app import main; main()"
