#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JJ-Brain Vault Health Audit
감시: 깨진 링크, 고아 노트, 미분류 노트, 최근 활동, 백업 검증
"""

import os
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

def get_vault_config():
    """운영팀 설정 읽기"""
    config_path = Path(r"C:\Users\ojaej\jj-company\departments\ops\config.md")
    config = {}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if ': ' in line:
                    key, val = line.split(': ', 1)
                    config[key] = val
    except Exception as e:
        print(f"Config read error: {e}", file=sys.stderr)
    return config

def find_all_md_files(vault_path):
    """vault의 모든 .md 파일 찾기"""
    vault = Path(vault_path)
    md_files = []
    for md_file in vault.rglob('*.md'):
        # 숨김 폴더(.obsidian, .omc 등) 제외
        if any(part.startswith('.') for part in md_file.relative_to(vault).parts):
            continue
        md_files.append(md_file)
    return md_files

def parse_wikilinks(content):
    """[[...]] 형태의 위키링크 파싱"""
    # [[link]] 또는 [[link|display]] 형태
    pattern = r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]'
    links = re.findall(pattern, content)
    return links

def read_file_safe(path):
    """파일 안전 읽기"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ""

def resolve_link_target(link, vault_path):
    """
    [[link]] 대상 파일 찾기
    .md 확장자 자동 추가, 정확 매치, 대소문자 무시
    """
    vault = Path(vault_path)
    
    # 링크에서 #anchor 제거
    if '#' in link:
        link = link.split('#')[0]
    
    link = link.strip()
    if not link:
        return None
    
    # 정확한 경로인지 확인 (없으면 .md 추가)
    candidates = []
    
    # 1. 정확 매치: link 그대로
    target = vault / link
    if target.exists() and target.is_file():
        return target
    
    # 2. link.md
    target = vault / f"{link}.md"
    if target.exists() and target.is_file():
        return target
    
    # 3. 폴더 안에서 대소문자 무시 찾기
    for md_file in vault.rglob('*.md'):
        if any(part.startswith('.') for part in md_file.relative_to(vault).parts):
            continue
        stem = md_file.stem
        if stem.lower() == link.lower():
            return md_file
    
    return None

def get_file_mtime(path):
    """파일 수정 시간"""
    try:
        return datetime.fromtimestamp(os.path.getmtime(path))
    except:
        return None

def is_in_exclude_folder(file_path, vault_path, exclude_folders):
    """파일이 제외 폴더에 있는지 확인"""
    vault = Path(vault_path)
    rel_path = file_path.relative_to(vault)
    for exclude in exclude_folders:
        exclude = exclude.rstrip('/')
        if str(rel_path).startswith(exclude):
            return True
    return False

def main():
    config = get_vault_config()
    vault_path = config.get('VAULT_PATH', r'C:\Obsidian.JJ\JJ-Brain')
    exclude_orphan_str = config.get('EXCLUDE_ORPHAN', '00_Inbox/, 06_Templates/')
    backup_path = config.get('BACKUP_PATH', '(미설정)')
    
    exclude_orphan = [x.strip() for x in exclude_orphan_str.split(',')]
    
    vault = Path(vault_path)
    if not vault.exists():
        print(f"VAULT_PATH 없음: {vault_path}", file=sys.stderr)
        sys.exit(1)
    
    # 모든 .md 파일 수집
    all_md_files = find_all_md_files(vault_path)
    print(f"[*] 총 노트: {len(all_md_files)}", file=sys.stderr)
    
    # === 1. 깨진 위키링크 ===
    broken_links_dict = defaultdict(list)  # {link: [files]}
    broken_links_count = 0
    
    for md_file in all_md_files:
        content = read_file_safe(md_file)
        links = parse_wikilinks(content)
        for link in links:
            if not resolve_link_target(link, vault_path):
                broken_links_dict[link].append(md_file)
                broken_links_count += 1
    
    # 상위 10개
    sorted_broken = sorted(broken_links_dict.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    
    # === 2. 고아 노트 ===
    # 역링크(backlink) 구축
    backlinks = defaultdict(set)  # {target_file: {sources}}
    
    for md_file in all_md_files:
        content = read_file_safe(md_file)
        links = parse_wikilinks(content)
        for link in links:
            target = resolve_link_target(link, vault_path)
            if target:
                backlinks[target].add(md_file)
    
    orphan_count = 0
    orphan_notes = []
    for md_file in all_md_files:
        # 제외 폴더 체크
        if is_in_exclude_folder(md_file, vault_path, exclude_orphan):
            continue
        if md_file not in backlinks or len(backlinks[md_file]) == 0:
            orphan_count += 1
            orphan_notes.append(md_file)
    
    # === 3. 미분류 노트 (7일 이상 방치) ===
    inbox_paths = [vault / '00_Inbox', vault / 'inbox']
    unclassified_notes = []
    cutoff_date = datetime.now() - timedelta(days=7)
    
    for inbox_path in inbox_paths:
        if not inbox_path.exists():
            continue
        for md_file in inbox_path.rglob('*.md'):
            mtime = get_file_mtime(md_file)
            if mtime and mtime < cutoff_date:
                unclassified_notes.append((md_file, mtime))
    
    unclassified_count = len(unclassified_notes)
    
    # === 4. 최근 활동 (24시간) ===
    recent_count = 0
    cutoff_recent = datetime.now() - timedelta(hours=24)
    for md_file in all_md_files:
        mtime = get_file_mtime(md_file)
        if mtime and mtime >= cutoff_recent:
            recent_count += 1
    
    # === 5. 백업 검증 ===
    backup_status = "확인 불가 (BACKUP_PATH 미설정)" if backup_path == "(미설정)" else backup_path
    
    # 출력 (파이썬이 읽기 위함)
    print(f"BROKEN_LINKS_COUNT={broken_links_count}")
    print(f"BROKEN_LINKS_TOP10={sorted_broken}")
    print(f"ORPHAN_COUNT={orphan_count}")
    print(f"UNCLASSIFIED_COUNT={unclassified_count}")
    print(f"RECENT_COUNT={recent_count}")
    print(f"BACKUP_STATUS={backup_status}")

if __name__ == '__main__':
    main()
