#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Historical maintenance utility.

This script is not part of the v0.1 MVP startup path. Do not run it as
part of the normal QA or release workflow.

Scan all .py files under the project and print every line containing CJK characters,
along with the file path and line number.

Usage: python scripts/dev/fix_chinese.py
"""
import os
import re

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CJK = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff01-\uffef]+')

results = []
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', 'venv', '.venv', 'node_modules']]
    for fname in files:
        if not fname.endswith('.py'):
            continue
        fpath = os.path.join(root, fname)
        try:
            text = open(fpath, encoding='utf-8', errors='replace').read()
        except Exception as e:
            print(f'[ERROR] {fpath}: {e}')
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            if CJK.search(line):
                rel = os.path.relpath(fpath, BASE)
                results.append((rel, i, line.rstrip()))

if not results:
    print('[OK] No CJK characters found in any .py file.')
else:
    print(f'[FOUND] {len(results)} line(s) with CJK characters:\n')
    current_file = None
    for rel, lineno, line in results:
        if rel != current_file:
            print(f'\n  {rel}')
            current_file = rel
        print(f'    L{lineno:04d}: {line}')
