"""
ModFetch 入口点

`python -m modfetch` 时执行，代理到 CLI 适配层（modfetch.cli.main）。
"""

from modfetch.cli import main

if __name__ == "__main__":
    main()
