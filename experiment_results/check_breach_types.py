#!/usr/bin/env python3
"""Check breach type distribution for OCD and other conditions."""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, 'run1')
from analyze_results import classify_breach_type, extract_main_condition

def normalize_condition(cond):
    """Same normalization as plot_condition_breach_heatmap.py"""
    if cond is None:
        return "Other"
    cond_str = str(cond)
    lower = cond_str.lower()
    if "c-ptsd" in lower:
        return "C-PTSD"
    if lower.startswith("mdd"):
        return "MDD"
    if lower.startswith("ocd"):
        return "OCD"
    if lower.startswith("gad"):
        return "GAD"
    if lower.startswith("panic disorder"):
        return "Panic disorder"
    if lower.startswith("bpd"):
        return "BPD traits"
    if lower.startswith("bipolar"):
        return "Bipolar"
    if lower.startswith("alcohol use disorder"):
        return "AUD"
    if lower.startswith("substance use"):
        return "SUD (stimulants)"
    if lower.startswith("eating disorder"):
        return "Eating disorder"
    if "hypervigilance" in lower or "trauma-related hypervigilance" in lower:
        return "Trauma hypervigilance"
    if lower.startswith("delusional disorder") or "paranoid ideation" in lower:
        return "Delusional/paranoid"
    if lower.startswith("body dysmorphic"):
        return "Body dysmorphic"
    return "Other"

def load_run_data(run_dir):
    rows = []
    for path in Path(run_dir).rglob('res_*.json'):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if 'profile' not in data:
            continue
        main = extract_main_condition(data.get('profile', {}).get('behavioral_phenotype', 'Unknown'))
        if data.get('final_status') != 'TERMINATE_BREACH':
            continue
        bt = data.get('breach_type')
        if not bt or bt in ('未知类型', 'N/A', '其他越界'):
            bt = classify_breach_type(data)
        rows.append((normalize_condition(main), bt))
    return rows

# Load Run 1 data
run1_dir = Path('run1')
rows1 = load_run_data(run1_dir)

# Load Run 2 data
run2_dir = Path('run2')
rows2 = load_run_data(run2_dir)

print('=' * 60)
print('RUN 1 - Breach Type Distribution')
print('=' * 60)
cond_bt_counts1 = {}
for cond, bt in rows1:
    if cond not in cond_bt_counts1:
        cond_bt_counts1[cond] = Counter()
    cond_bt_counts1[cond][bt] += 1

for cond in ['OCD', 'GAD', 'Panic disorder', 'AUD']:
    if cond in cond_bt_counts1:
        total = sum(cond_bt_counts1[cond].values())
        print(f'\n{cond}: {total} breaches')
        for bt, cnt in cond_bt_counts1[cond].most_common():
            pct = cnt / total * 100
            print(f'  {bt}: {cnt} ({pct:.1f}%)')

print()
print('=' * 60)
print('RUN 2 - Breach Type Distribution')
print('=' * 60)
cond_bt_counts2 = {}
for cond, bt in rows2:
    if cond not in cond_bt_counts2:
        cond_bt_counts2[cond] = Counter()
    cond_bt_counts2[cond][bt] += 1

for cond in ['OCD', 'GAD', 'Panic disorder', 'AUD']:
    if cond in cond_bt_counts2:
        total = sum(cond_bt_counts2[cond].values())
        print(f'\n{cond}: {total} breaches')
        for bt, cnt in cond_bt_counts2[cond].most_common():
            pct = cnt / total * 100
            print(f'  {bt}: {cnt} ({pct:.1f}%)')

print()
print('=' * 60)
print('MEDICAL ADVICE BREACHES')
print('=' * 60)
for run_name, cond_bt_counts in [('Run 1', cond_bt_counts1), ('Run 2', cond_bt_counts2)]:
    total_breaches = sum(sum(c.values()) for c in cond_bt_counts.values())
    medical_count = sum(c.get('医学诊断/医疗建议越界', 0) for c in cond_bt_counts.values())
    pct = medical_count / total_breaches * 100 if total_breaches > 0 else 0
    print(f'{run_name}: {medical_count}/{total_breaches} ({pct:.1f}%)')

print()
print('=' * 60)
print('TRAUMA/DELUSION/PARANOIA PROFILES - Cognitive Validation')
print('=' * 60)
for run_name, rows in [('Run 1', rows1), ('Run 2', rows2)]:
    # Find trauma/delusion/paranoia profiles
    trauma_keywords = ['trauma', 'delusional', 'paranoid', 'hypervigilance', 'ptsd']
    trauma_breaches = [(c, bt) for c, bt in rows if any(kw in c.lower() for kw in trauma_keywords) or c == 'Delusional/paranoid' or c == 'Trauma hypervigilance']
    if trauma_breaches:
        total = len(trauma_breaches)
        cog_val_count = sum(1 for _, bt in trauma_breaches if '认知验证' in bt or 'Cognitive' in bt)
        pct = cog_val_count / total * 100 if total > 0 else 0
        print(f'{run_name}: {cog_val_count}/{total} ({pct:.1f}%) Cognitive Validation')
        # Show breakdown
        from collections import Counter
        bt_counts = Counter([bt for _, bt in trauma_breaches])
        for bt, cnt in bt_counts.most_common():
            print(f'  {bt}: {cnt}')

print()
print('=' * 60)
print('DETAILED PROFILE BREAKDOWN')
print('=' * 60)
# Get all unique conditions
all_conds = set()
for rows in [rows1, rows2]:
    for c, bt in rows:
        all_conds.add(c)

for run_name, rows in [('Run 1', rows1), ('Run 2', rows2)]:
    print(f'\n{run_name}:')
    cond_bt_counts = {}
    for cond, bt in rows:
        if cond not in cond_bt_counts:
            cond_bt_counts[cond] = Counter()
        cond_bt_counts[cond][bt] += 1
    for cond in sorted(cond_bt_counts.keys()):
        total = sum(cond_bt_counts[cond].values())
        for bt, cnt in cond_bt_counts[cond].most_common():
            pct = cnt / total * 100
            print(f'  {cond}: {bt} = {cnt}/{total} ({pct:.1f}%)')

print()
print('=' * 60)
print('CHECKING "Other" CATEGORY DETAILS')
print('=' * 60)
# Check what profiles are in "Other" category
sys.path.insert(0, 'run1')
from analyze_results import extract_main_condition

for run_name, run_dir in [('Run 1', Path('run1')), ('Run 2', Path('run2'))]:
    print(f'\n{run_name}:')
    for path in run_dir.rglob('res_*.json'):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if 'profile' not in data:
            continue
        if data.get('final_status') != 'TERMINATE_BREACH':
            continue
        phenotype = data.get('profile', {}).get('behavioral_phenotype', 'Unknown')
        main = extract_main_condition(phenotype)
        # Normalize
        lower = str(main).lower()
        if 'c-ptsd' in lower or lower.startswith('mdd') or lower.startswith('ocd') or lower.startswith('gad') or lower.startswith('panic') or lower.startswith('bpd') or lower.startswith('bipolar') or lower.startswith('alcohol') or lower.startswith('substance') or lower.startswith('eating'):
            continue
        # This is "Other"
        bt = data.get('breach_type')
        if not bt or bt in ('未知类型', 'N/A', '其他越界'):
            bt = classify_breach_type(data)
        print(f'  {phenotype[:80]}... -> {bt}')