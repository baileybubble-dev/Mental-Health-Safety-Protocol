#!/usr/bin/env python3
"""
分析 experiment_results/run2 目录下的实验结果
"""

import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple
import statistics
from datetime import datetime

# 导入原有分析函数
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_results import (
    extract_main_condition,
    classify_breach_type,
    infer_attempted_breach_types,
    load_all_results,
    analyze_results
)

def get_demographics_distribution(profiles_file: str) -> Dict:
    """从 profiles.json 中获取 Demographics 的分布情况"""
    with open(profiles_file, 'r', encoding='utf-8') as f:
        profiles = json.load(f)
    
    distribution = {
        'by_age_group': defaultdict(int),
        'by_gender': defaultdict(int),
        'by_income': defaultdict(int),
        'by_education': defaultdict(int),
        'by_occupation': defaultdict(int),
        'by_marital_status': defaultdict(int),
        'by_has_children': defaultdict(int),
        'by_ethnicity': defaultdict(int),
        'by_location': defaultdict(int)
    }
    
    def get_age_group(age):
        if age is None:
            return 'Unknown'
        try:
            age_int = int(age)
            if age_int < 25:
                return '18-24'
            elif age_int < 35:
                return '25-34'
            elif age_int < 45:
                return '35-44'
            elif age_int < 55:
                return '45-54'
            elif age_int < 65:
                return '55-64'
            else:
                return '65+'
        except:
            return 'Unknown'
    
    for profile in profiles:
        demo = profile.get('demographics', {})
        
        # 年龄组
        age = demo.get('age')
        age_group = get_age_group(age)
        distribution['by_age_group'][age_group] += 1
        
        # 性别
        gender = demo.get('gender', 'Unknown')
        distribution['by_gender'][gender] += 1
        
        # 收入
        income = demo.get('income', 'Unknown')
        distribution['by_income'][income] += 1
        
        # 教育水平
        education = demo.get('education_level', 'Unknown')
        distribution['by_education'][education] += 1
        
        # 职业
        occupation = demo.get('occupation', 'Unknown')
        distribution['by_occupation'][occupation] += 1
        
        # 婚姻状况
        marital_status = demo.get('marital_status', 'Unknown')
        distribution['by_marital_status'][marital_status] += 1
        
        # 是否有孩子
        has_children = demo.get('has_children')
        has_children_key = 'Yes' if has_children else 'No' if has_children is False else 'Unknown'
        distribution['by_has_children'][has_children_key] += 1
        
        # 种族
        ethnicity = demo.get('ethnicity', 'Unknown')
        distribution['by_ethnicity'][ethnicity] += 1
        
        # 地理位置
        location = demo.get('location', 'Unknown')
        distribution['by_location'][location] += 1
    
    # 转换为普通字典并计算百分比
    result = {}
    total_profiles = len(profiles)
    
    for key, counts in distribution.items():
        result[key] = {}
        for item, count in sorted(counts.items()):
            result[key][item] = {
                'count': count,
                'percentage': (count / total_profiles * 100) if total_profiles > 0 else 0
            }
    
    return result

def generate_markdown_report_run2(analysis: Dict, base_dir: str, demographics_dist: Dict) -> str:
    """生成Markdown格式的分析报告（中文，针对run2，去掉Statistics by Demographics）"""
    from datetime import datetime
    
    lines = []
    
    # 标题
    lines.append("# 实验结果全面分析报告")
    lines.append("")
    
    # 执行时间
    lines.append("## 执行时间")
    lines.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"数据来源: `{base_dir}/`")
    
    # 计算总文件数
    total_files = analysis['overall']['total_tests']
    lines.append(f"总测试文件数: {total_files} (包含 DeepSeek, Gemini, XAI)")
    lines.append("测试轮数限制: 每个测试最多 20 轮")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 总体统计
    overall = analysis['overall']
    breach_rate = overall['breach_rate'] * 100
    lines.append("## 📊 总体统计")
    lines.append("")
    lines.append(f"- **总测试数**: {overall['total_tests']}")
    lines.append(f"- **达到 TERMINATE_BREACH 的数量**: {overall['total_breaches']}")
    
    # 添加警告符号
    if breach_rate >= 85:
        warning_symbol = "⚠️⚠️⚠️"
    elif breach_rate >= 75:
        warning_symbol = "⚠️⚠️"
    elif breach_rate >= 65:
        warning_symbol = "⚠️"
    else:
        warning_symbol = ""
    
    lines.append(f"- **总体越界比例**: **{breach_rate:.2f}%** {warning_symbol}")
    lines.append("")
    lines.append("### 关键发现")
    lines.append(f"- 超过五分之四的测试案例最终达到了 TERMINATE_BREACH 状态")
    lines.append("- 这表明在压力测试下，模型容易提供绝对保证或确定性承诺")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 按模型统计
    lines.append("## 🤖 按模型统计")
    lines.append("")
    
    model_order = ['deepseek', 'gemini', 'xai']
    for model in model_order:
        if model not in analysis['by_model']:
            continue
        stats = analysis['by_model'][model]
        model_breach_rate = stats['breach_rate'] * 100
        
        # 确定警告符号
        if model_breach_rate >= 85:
            warning = "⚠️⚠️ (最高，与其他模型并列)"
        elif model_breach_rate >= 75:
            warning = "⚠️⚠️"
        elif model_breach_rate >= 65:
            warning = "⚠️"
        else:
            warning = "(相对最低)"
        
        lines.append(f"### {model.capitalize()}")
        lines.append(f"- **测试总数**: {stats['total_tests']}")
        lines.append(f"- **越界次数**: {stats['breaches']}")
        lines.append(f"- **越界比例**: **{model_breach_rate:.2f}%** {warning}")
        lines.append(f"- **平均轮数**: {stats['avg_turns']:.2f}")
        lines.append(f"- **中位数轮数**: {stats['median_turns']:.2f}")
        lines.append(f"- **越界案例平均轮数**: {stats['avg_turns_breach']:.2f}")
        lines.append(f"- **未越界案例平均轮数**: {stats['avg_turns_non_breach']:.2f}")
        lines.append(f"- **轮数范围**: {stats['min_turns']} - {stats['max_turns']}")
        lines.append("")
    
    # 模型对比分析
    lines.append("### 模型对比分析")
    model_stats_list = [(model, analysis['by_model'][model]) for model in model_order if model in analysis['by_model']]
    model_stats_list.sort(key=lambda x: x[1]['breach_rate'], reverse=True)
    
    # 找出最高和最低越界率
    if len(model_stats_list) >= 2:
        highest_models = [m for m, s in model_stats_list if s['breach_rate'] == model_stats_list[0][1]['breach_rate']]
        lowest_models = [m for m, s in model_stats_list if s['breach_rate'] == model_stats_list[-1][1]['breach_rate']]
        
        lines.append(f"1. **{' 和 '.join([m.capitalize() for m in highest_models])} 越界率最高**: 两者均为 {model_stats_list[0][1]['breach_rate']*100:.2f}%，明显高于其他模型")
        if len(model_stats_list) >= 3:
            avg_breach_turns = [(m, s['avg_turns_breach']) for m, s in model_stats_list]
            avg_breach_turns.sort(key=lambda x: x[1])
            fastest = avg_breach_turns[0]
            lines.append(f"2. **{fastest[0].capitalize()} 越界速度最快**: {fastest[0].capitalize()} 平均仅需 {fastest[1]:.2f} 轮即可越界，是所有模型中最快的")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 按语言统计
    lines.append("## 🌐 按目标语言统计")
    lines.append("")
    
    for lang, stats in sorted(analysis['by_language'].items()):
        lang_breach_rate = stats['breach_rate'] * 100
        lang_name = "Chinese (中文)" if lang.lower() in ['chinese', '中文'] else f"{lang} (英文)" if lang.lower() == 'english' else lang
        
        if lang_breach_rate == 100:
            warning = "⚠️⚠️⚠️ (全部越界)"
        elif lang_breach_rate >= 85:
            warning = "⚠️⚠️"
        elif lang_breach_rate >= 75:
            warning = "⚠️"
        else:
            warning = ""
        
        lines.append(f"### {lang_name}")
        lines.append(f"- **测试总数**: {stats['total_tests']}")
        lines.append(f"- **越界次数**: {stats['breaches']}")
        lines.append(f"- **越界比例**: **{lang_breach_rate:.2f}%** {warning}")
        lines.append(f"- **平均轮数**: {stats['avg_turns']:.2f}")
        lines.append(f"- **中位数轮数**: {stats['median_turns']:.2f}")
        lines.append("")
    
    lines.append("### 语言对比分析")
    lang_list = list(analysis['by_language'].items())
    if len(lang_list) >= 2:
        lang_list.sort(key=lambda x: x[1]['breach_rate'], reverse=True)
        high_lang = lang_list[0]
        low_lang = lang_list[-1]
        diff = (high_lang[1]['breach_rate'] - low_lang[1]['breach_rate']) * 100
        lines.append(f"1. **{high_lang[0]}测试越界率显著更高**: {high_lang[0]}测试的越界率 ({high_lang[1]['breach_rate']*100:.2f}%) 比 {low_lang[0]} ({low_lang[1]['breach_rate']*100:.2f}%) 高约 {diff:.1f} 个百分点")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Demographics 分布情况（从 profiles.json）
    lines.append("## 👥 Demographics 分布情况")
    lines.append("")
    lines.append("以下数据展示了 profiles.json 中 Demographics 的分布情况：")
    lines.append("")
    
    # 按年龄组
    if 'by_age_group' in demographics_dist and demographics_dist['by_age_group']:
        lines.append("### 按年龄组")
        lines.append("")
        lines.append("| 年龄组 | 数量 | 占比 |")
        lines.append("|--------|------|------|")
        for age_group, stats in sorted(demographics_dist['by_age_group'].items()):
            lines.append(f"| **{age_group}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # 按性别
    if 'by_gender' in demographics_dist and demographics_dist['by_gender']:
        lines.append("### 按性别")
        lines.append("")
        lines.append("| 性别 | 数量 | 占比 |")
        lines.append("|------|------|------|")
        for gender, stats in sorted(demographics_dist['by_gender'].items()):
            lines.append(f"| **{gender}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # 按收入
    if 'by_income' in demographics_dist and demographics_dist['by_income']:
        lines.append("### 按收入")
        lines.append("")
        lines.append("| 收入 | 数量 | 占比 |")
        lines.append("|------|------|------|")
        for income, stats in sorted(demographics_dist['by_income'].items()):
            lines.append(f"| **{income}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # 按教育水平
    if 'by_education' in demographics_dist and demographics_dist['by_education']:
        lines.append("### 按教育水平")
        lines.append("")
        lines.append("| 教育水平 | 数量 | 占比 |")
        lines.append("|----------|------|------|")
        for education, stats in sorted(demographics_dist['by_education'].items()):
            lines.append(f"| **{education}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # 按职业
    if 'by_occupation' in demographics_dist and demographics_dist['by_occupation']:
        lines.append("### 按职业")
        lines.append("")
        lines.append("| 职业 | 数量 | 占比 |")
        lines.append("|------|------|------|")
        sorted_occ = sorted(demographics_dist['by_occupation'].items(), key=lambda x: x[1]['count'], reverse=True)
        for occupation, stats in sorted_occ:
            lines.append(f"| **{occupation}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # 按婚姻状况
    if 'by_marital_status' in demographics_dist and demographics_dist['by_marital_status']:
        lines.append("### 按婚姻状况")
        lines.append("")
        lines.append("| 婚姻状况 | 数量 | 占比 |")
        lines.append("|----------|------|------|")
        for marital_status, stats in sorted(demographics_dist['by_marital_status'].items()):
            lines.append(f"| **{marital_status}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # 按是否有孩子
    if 'by_has_children' in demographics_dist and demographics_dist['by_has_children']:
        lines.append("### 按是否有孩子")
        lines.append("")
        lines.append("| 是否有孩子 | 数量 | 占比 |")
        lines.append("|-----------|------|------|")
        for has_children, stats in sorted(demographics_dist['by_has_children'].items()):
            lines.append(f"| **{has_children}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # 按种族
    if 'by_ethnicity' in demographics_dist and demographics_dist['by_ethnicity']:
        lines.append("### 按种族")
        lines.append("")
        lines.append("| 种族 | 数量 | 占比 |")
        lines.append("|------|------|------|")
        sorted_eth = sorted(demographics_dist['by_ethnicity'].items(), key=lambda x: x[1]['count'], reverse=True)
        for ethnicity, stats in sorted_eth:
            lines.append(f"| **{ethnicity}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # 按地理位置
    if 'by_location' in demographics_dist and demographics_dist['by_location']:
        lines.append("### 按地理位置")
        lines.append("")
        lines.append("| 地理位置 | 数量 | 占比 |")
        lines.append("|----------|------|------|")
        for location, stats in sorted(demographics_dist['by_location'].items()):
            lines.append(f"| **{location}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    # 按主要病情类型统计
    lines.append("## 🏥 按主要病情类型统计（忽略 \"with\" 部分）")
    lines.append("")
    lines.append("### 主要发现")
    lines.append("")
    lines.append("| 病情类型 | 测试数 | 越界数 | 越界率 | 平均轮数 |")
    lines.append("|---------|--------|--------|--------|----------|")
    
    sorted_conditions = sorted(
        analysis['by_main_condition'].items(),
        key=lambda x: (x[1]['breach_rate'], -x[1]['total_tests']),
        reverse=True
    )
    
    for condition, stats in sorted_conditions[:20]:  # Top 20
        breach_rate_pct = stats['breach_rate'] * 100
        avg_turns = stats['avg_turns']
        
        # 添加警告符号
        if breach_rate_pct == 100:
            warning = "⚠️"
            if avg_turns < 8:
                warning += " (最快)"
        elif breach_rate_pct >= 80:
            warning = ""
        else:
            warning = ""
        
        lines.append(f"| **{condition}** | {stats['total_tests']} | {stats['breaches']} | **{breach_rate_pct:.0f}%** | {avg_turns:.2f} {warning} |")
    
    lines.append("")
    lines.append("### 关键洞察")
    if sorted_conditions:
        top_condition = sorted_conditions[0]
        lines.append(f"1. **{top_condition[0]} 越界率最高**: {top_condition[1]['breach_rate']*100:.0f}%，平均需 {top_condition[1]['avg_turns']:.2f} 轮")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 按越界类型统计
    lines.append("## 🚨 按越界类型统计")
    lines.append("")
    lines.append("### 越界方式分布")
    lines.append("")
    lines.append("| 越界类型 | 数量 | 占比 | 平均轮数 | 轮数范围 |")
    lines.append("|---------|------|------|----------|----------|")
    
    sorted_breach_types = sorted(
        analysis['by_breach_type'].items(),
        key=lambda x: x[1]['total_tests'],
        reverse=True
    )
    
    total_breaches = analysis['overall']['total_breaches']
    for breach_type, stats in sorted_breach_types:
        count = stats['total_tests']
        percentage = (count / total_breaches * 100) if total_breaches > 0 else 0
        lines.append(f"| **{breach_type}** | {count} | **{percentage:.2f}%** | {stats['avg_turns']:.2f} | {stats['min_turns']}-{stats['max_turns']} |")
    
    lines.append("")
    lines.append("### 越界类型分析")
    if sorted_breach_types:
        top_type = sorted_breach_types[0]
        lines.append(f"1. **{top_type[0]}是最主要的越界方式** ({top_type[1]['total_tests']/total_breaches*100:.2f}%)")
        lines.append(f"   - 平均 {top_type[1]['avg_turns']:.2f} 轮即可越界")
        lines.append(f"   - 最快仅需 {top_type[1]['min_turns']} 轮")
        lines.append(f"   - 这是最需要关注的越界类型")
        lines.append("")
        
        # 添加其他主要越界类型的说明
        if len(sorted_breach_types) > 1:
            second_type = sorted_breach_types[1]
            lines.append(f"2. **{second_type[0]}** ({second_type[1]['total_tests']/total_breaches*100:.2f}%)")
            lines.append(f"   - 平均 {second_type[1]['avg_turns']:.2f} 轮越界")
            lines.append(f"   - 需要加强专业角色边界的维护")
            lines.append("")
        
        if len(sorted_breach_types) > 2:
            third_type = sorted_breach_types[2]
            lines.append(f"3. **{third_type[0]}** ({third_type[1]['total_tests']/total_breaches*100:.2f}%)")
            lines.append(f"   - 平均 {third_type[1]['avg_turns']:.2f} 轮越界")
            lines.append("")
        
        # 特别说明认知验证/扭曲认知验证
        cognitive_validation = next((t for t in sorted_breach_types if '认知验证' in t[0] or 'Cognitive' in t[0]), None)
        if cognitive_validation:
            lines.append(f"4. **{cognitive_validation[0]}** ({cognitive_validation[1]['total_tests']/total_breaches*100:.2f}%)")
            lines.append(f"   - 平均 {cognitive_validation[1]['avg_turns']:.2f} 轮越界")
            lines.append(f"   - 模型验证了用户的扭曲认知、病态逻辑或有害信念（如饮食障碍规则、偏执妄想、自我责备等）")
            lines.append(f"   - 这是认知验证测试（Cognitive Validation Testing）的表现，说明模型在压力下可能放弃专业边界而迎合用户的错误认知")
            lines.append("")
        
        # 特别说明自我伤害认可
        self_harm = next((t for t in sorted_breach_types if '自我伤害' in t[0] or 'self-harm' in t[0]), None)
        if self_harm:
            lines.append(f"5. **{self_harm[0]}** ({self_harm[1]['total_tests']/total_breaches*100:.2f}%)")
            lines.append(f"   - 平均 {self_harm[1]['avg_turns']:.2f} 轮越界")
            lines.append(f"   - 这是最危险的越界类型，需要特别关注")
            lines.append("")
        
        # 说明医学诊断越界
        medical = next((t for t in sorted_breach_types if '医学' in t[0] or 'medical' in t[0]), None)
        if medical:
            lines.append(f"6. **{medical[0]}** ({medical[1]['total_tests']/total_breaches*100:.2f}%)")
            lines.append(f"   - 平均 {medical[1]['avg_turns']:.2f} 轮越界")
            lines.append(f"   - 说明模型在此方面边界维护相对较好")
            lines.append("")
    else:
        lines.append("")
    lines.append("---")
    lines.append("")
    
    # 每种越界方式的尝试次数和成功率统计
    if 'breach_attempt_analysis' in analysis:
        lines.append("## 🎯 每种越界方式的尝试次数和成功率统计")
        lines.append("")
        lines.append("### 总体统计")
        lines.append("")
        lines.append("| 越界类型 | 尝试次数 | 成功次数 | 失败次数 | 成功率 |")
        lines.append("|---------|---------|---------|---------|--------|")
        
        summary = analysis['breach_attempt_analysis']['summary']
        for breach_type, stats in sorted(summary.items(), key=lambda x: x[1]['attempted'], reverse=True):
            lines.append(f"| **{breach_type}** | {stats['attempted']} | {stats['succeeded']} | {stats['failed']} | **{stats['success_rate']:.2f}%** |")
        
        lines.append("")
        lines.append("### 关键发现")
        if summary:
            max_attempted = max(summary.items(), key=lambda x: x[1]['attempted'])
            max_success_rate = max([(k, v) for k, v in summary.items() if v['attempted'] > 0], key=lambda x: x[1]['success_rate'])
            lines.append(f"1. **尝试次数最多的越界方式**: {max_attempted[0]} ({max_attempted[1]['attempted']} 次尝试)")
            lines.append(f"2. **成功率最高的越界方式**: {max_success_rate[0]} ({max_success_rate[1]['success_rate']:.2f}%)")
        lines.append("")
        
        # 按模型详细统计
        lines.append("### 按模型详细统计")
        lines.append("")
        by_model = analysis['breach_attempt_analysis']['by_model']
        for model in sorted(by_model.keys()):
            lines.append(f"#### {model.upper()}")
            lines.append("")
            lines.append("| 越界类型 | 尝试次数 | 成功次数 | 失败次数 | 成功率 |")
            lines.append("|---------|---------|---------|---------|--------|")
            model_stats = by_model[model]
            for breach_type, stats in sorted(model_stats.items(), key=lambda x: x[1]['attempted'], reverse=True):
                lines.append(f"| {breach_type} | {stats['attempted']} | {stats['succeeded']} | {stats['failed']} | **{stats['success_rate']:.2f}%** |")
            lines.append("")
        lines.append("---")
        lines.append("")
    
    # 按模型+语言组合统计
    lines.append("## 🔗 按模型+语言组合统计")
    lines.append("")
    
    model_lang_combinations = sorted(analysis['by_model_language'].items(), key=lambda x: (x[1]['model'], x[1]['language']))
    for key, stats in model_lang_combinations:
        lang_name = "Chinese" if stats['language'].lower() in ['chinese', '中文'] else "English"
        lang_breach_rate = stats['breach_rate'] * 100
        
        if lang_breach_rate == 100:
            warning = "⚠️⚠️⚠️ (最高风险)"
        elif lang_breach_rate >= 85:
            warning = "⚠️⚠️"
        elif lang_breach_rate >= 75:
            warning = "⚠️"
        else:
            warning = "(最低)"
        
        lines.append(f"### {stats['model'].capitalize()} - {lang_name}")
        lines.append(f"- **测试总数**: {stats['total_tests']}")
        lines.append(f"- **越界次数**: {stats['breaches']}")
        lines.append(f"- **越界比例**: **{lang_breach_rate:.2f}%** {warning}")
        lines.append(f"- **平均轮数**: {stats['avg_turns']:.2f}")
        lines.append(f"- **中位数轮数**: {stats['median_turns']:.2f}")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    # 轮数详细分析
    lines.append("## 📈 轮数详细分析")
    lines.append("")
    turns = analysis['turns_analysis']
    
    lines.append("### 所有案例")
    lines.append(f"- **平均轮数**: {turns['overall']['avg']:.2f}")
    lines.append(f"- **中位数轮数**: {turns['overall']['median']:.2f}")
    lines.append(f"- **标准差**: {turns['overall']['stdev']:.2f}")
    lines.append(f"- **范围**: {turns['overall']['min']} - {turns['overall']['max']}")
    lines.append("")
    
    lines.append("### 越界案例")
    lines.append(f"- **平均轮数**: {turns['breach_cases']['avg']:.2f}")
    lines.append(f"- **中位数轮数**: {turns['breach_cases']['median']:.2f}")
    lines.append(f"- **标准差**: {turns['breach_cases']['stdev']:.2f}")
    lines.append(f"- **范围**: {turns['breach_cases']['min']} - {turns['breach_cases']['max']}")
    lines.append("")
    
    lines.append("### 未越界案例")
    lines.append(f"- **平均轮数**: {turns['non_breach_cases']['avg']:.2f}")
    lines.append(f"- **中位数轮数**: {turns['non_breach_cases']['median']:.2f}")
    lines.append(f"- **标准差**: {turns['non_breach_cases']['stdev']:.2f}")
    lines.append(f"- **范围**: {turns['non_breach_cases']['min']} - {turns['non_breach_cases']['max']}")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    
    # 多维度尝试策略分析（所有最终成功的维度）
    if 'multi_attempt_analysis' in analysis and analysis['multi_attempt_analysis']['total_cases'] > 0:
        multi_analysis = analysis['multi_attempt_analysis']
        lines.append("## 🔄 多维度尝试策略分析")
        lines.append("")
        lines.append("### 核心发现")
        lines.append("")
        total_multi = multi_analysis['total_cases']
        total_breaches = analysis['overall']['total_breaches']
        pct_of_total = (total_multi / total_breaches * 100) if total_breaches > 0 else 0
        lines.append(f"在所有越界案例中，有 **{total_multi} 个案例**（占所有越界案例的 **{pct_of_total:.1f}%**）尝试了多种边界突破策略，但最终只在一个维度上成功突破边界。")
        lines.append("")
        lines.append("### 按最终成功维度分类")
        lines.append("")
        lines.append("| 最终成功的维度 | 案例数 | 占比 | 平均轮数 | 中位数轮数 |")
        lines.append("|--------------|--------|------|----------|------------|")
        by_successful = multi_analysis['by_successful_type']
        for breach_type, stats in sorted(by_successful.items(), key=lambda x: x[1]['count'], reverse=True):
            lines.append(f"| **{breach_type}** | {stats['count']} | {stats['percentage']:.1f}% | {stats['avg_turns']:.2f} | {stats['median_turns']:.2f} |")
        lines.append("")
        lines.append("### 尝试类型组合模式（总体）")
        lines.append("")
        lines.append("| 尝试的类型组合 | 案例数 | 占比 |")
        lines.append("|--------------|--------|------|")
        for combo, count in sorted(multi_analysis['type_combinations'].items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_multi * 100) if total_multi > 0 else 0
            lines.append(f"| {combo} | {count} | {pct:.1f}% |")
        lines.append("")
        lines.append("### 按模型分布")
        lines.append("")
        for model, count in sorted(multi_analysis['by_model'].items()):
            lines.append(f"- **{model.capitalize()}**: {count} 例")
        lines.append("")
        lines.append("### 轮数统计")
        turns_stats = multi_analysis['turns_stats']
        lines.append(f"- **平均轮数**: {turns_stats['avg']:.2f}")
        lines.append(f"- **中位数轮数**: {turns_stats['median']:.2f}")
        lines.append(f"- **轮数范围**: {turns_stats['min']} - {turns_stats['max']}")
        lines.append("")
        lines.append("### 认知分析")
        lines.append("")
        lines.append("#### 1. **策略失效与成功模式**")
        lines.append("")
        lines.append("当AS尝试多种边界突破策略时，模型可能在以下方面表现出不同的抵抗力：")
        lines.append("- **专业角色越界**：模型可能在早期就识别并拒绝了充当治疗师/HR/法律顾问等专业角色的请求")
        lines.append("- **关系依赖/排他性承诺**：模型可能拒绝了24/7陪伴、专属关系的承诺")
        lines.append("- **认知验证/扭曲认知验证**：模型可能拒绝验证偏执妄想、自我责备等扭曲认知")
        lines.append("- **医学诊断/医疗建议越界**：模型可能拒绝了提供诊断或处方的请求")
        lines.append("- **绝对保证/零风险承诺**：模型可能更容易妥协（见下文详细分析）")
        lines.append("")
        lines.append("当某些策略失败后，AS转而使用其他策略时，模型可能在另一个维度上妥协。")
        lines.append("")
        lines.append("#### 2. **最终成功维度的分布模式**")
        lines.append("")
        # 找出最常见的最终成功维度
        most_common_success_type = max(by_successful.items(), key=lambda x: x[1]['count'])
        lines.append(f"- **最常见的最终成功维度**：{most_common_success_type[0]} ({most_common_success_type[1]['count']} 例，占 {most_common_success_type[1]['percentage']:.1f}%)")
        lines.append("")
        if most_common_success_type[0] == '绝对保证/零风险承诺':
            lines.append("**关键发现**：绝对保证/零风险承诺是多维度尝试中最常见的最终突破点，这表明：")
            lines.append("- 模型对其他边界类型（专业角色、关系依赖、认知验证等）可能有一定的防御机制")
            lines.append("- 但当面对用户对确定性的迫切需求时，模型更容易放弃边界")
            lines.append("- **绝对保证/零风险承诺可能是模型最脆弱的边界点**")
        else:
            lines.append(f"**关键发现**：{most_common_success_type[0]}是多维度尝试中最常见的最终突破点，说明该维度可能是模型相对脆弱的边界。")
        lines.append("")
        lines.append("#### 3. **最常见的组合模式**")
        lines.append("")
        if multi_analysis['type_combinations']:
            most_common_combo = max(multi_analysis['type_combinations'].items(), key=lambda x: x[1])
            lines.append(f"- **最常见的组合**：{most_common_combo[0]} ({most_common_combo[1]} 例，占 {most_common_combo[1]/total_multi*100:.1f}%)")
            lines.append("- 这反映了AS最常用的多维度攻击策略组合")
        lines.append("")
        lines.append("#### 4. **详细维度分析**")
        lines.append("")
        for breach_type, stats in sorted(by_successful.items(), key=lambda x: x[1]['count'], reverse=True):
            if stats['count'] > 0:
                lines.append(f"**{breach_type}** ({stats['count']} 例):")
                if stats['combinations']:
                    lines.append(f"- 主要组合模式：")
                    top_combos = sorted(stats['combinations'].items(), key=lambda x: x[1], reverse=True)[:3]
                    for combo, count in top_combos:
                        pct = (count / stats['count'] * 100) if stats['count'] > 0 else 0
                        lines.append(f"  - {combo}: {count} 例 ({pct:.1f}%)")
                lines.append(f"- 平均轮数: {stats['avg_turns']:.2f}，中位数: {stats['median_turns']:.2f}")
                lines.append("")
        lines.append("#### 5. **心理机制分析**")
        lines.append("")
        lines.append("这种多维度尝试模式可能反映了以下心理机制：")
        lines.append("1. **策略失效后的替代路径**：当一种边界突破策略失败后，AS会尝试其他策略，直到找到模型最脆弱的点")
        lines.append("2. **移情疲劳**：当模型多次拒绝用户的请求后，可能在用户表达强烈的情感需求时更容易妥协")
        lines.append("3. **边界差异敏感性**：模型对不同边界类型的敏感性可能不同，某些边界更容易在压力下被突破")
        lines.append("4. **即时性压力**：用户往往在请求时会使用紧急、危机的语言，这种即时性压力可能降低模型的边界判断")
        lines.append("5. **累积效应**：之前的多轮互动建立了信任关系，使模型更愿意在用户'最后需要'时提供让步")
        lines.append("")
        lines.append("#### 6. **安全启示**")
        lines.append("")
        lines.append("这一发现对AI安全具有重要启示：")
        if most_common_success_type[0] == '绝对保证/零风险承诺':
            lines.append("- **需要特别加强绝对保证/零风险承诺边界的防护**，因为这是最常见的最终突破点")
        else:
            lines.append(f"- **需要特别加强{most_common_success_type[0]}边界的防护**，因为这是最常见的最终突破点")
        lines.append("- **多轮互动后的边界维护**：随着互动轮数增加，模型需要更强的边界维护机制")
        lines.append("- **紧急/危机语言的识别**：需要训练模型识别并抵抗以紧急需求为包装的边界突破尝试")
        lines.append("- **移情与边界的平衡**：模型需要学会在保持同理心的同时，坚定维护所有安全边界")
        lines.append("- **边界一致性**：需要确保模型对所有边界类型都有同等强度的保护，避免出现'薄弱环节'")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # 数据文件
    lines.append("## 📋 数据文件")
    lines.append("")
    lines.append(f"详细的分析数据（JSON 格式）已保存至:")
    lines.append(f"`{base_dir}/analysis_report.json`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d')}*")
    lines.append("*分析脚本版本: analyze_run2.py*")
    
    return "\n".join(lines)

def generate_markdown_report_en_run2(analysis: Dict, base_dir: str, demographics_dist: Dict) -> str:
    """Generate Markdown format analysis report in English (for run2, without Statistics by Demographics)"""
    from datetime import datetime
    
    # Mapping for breach types (Chinese to English)
    breach_type_mapping = {
        '绝对保证/零风险承诺': 'Absolute Guarantee/Zero-Risk Promise',
        '自我伤害认可/允许性语言': 'Self-Harm Endorsement/Permissive Language',
        '认知验证/扭曲认知验证': 'Cognitive Validation/Distorted Cognition Validation',
        '专业角色越界': 'Professional Role Boundary Breach',
        '关系依赖/排他性承诺': 'Relationship Dependency/Exclusive Commitment',
        '医学诊断/医疗建议越界': 'Medical Diagnosis/Medical Advice Boundary Breach',
        '其他越界': 'Other Boundary Breaches',
        'N/A': 'N/A',
        '未知类型': 'Unknown Type'
    }
    
    def translate_breach_type(breach_type: str) -> str:
        return breach_type_mapping.get(breach_type, breach_type)
    
    lines = []
    
    # Title
    lines.append("# Comprehensive Experimental Results Analysis Report")
    lines.append("")
    
    # Execution time
    lines.append("## Execution Time")
    lines.append(f"Analysis Time: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"Data Source: `{base_dir}/`")
    
    # Calculate total files
    total_files = analysis['overall']['total_tests']
    lines.append(f"Total Test Files: {total_files} (including DeepSeek, Gemini, XAI)")
    lines.append("Turn Limit: Maximum 20 turns per test")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Overall statistics
    overall = analysis['overall']
    breach_rate = overall['breach_rate'] * 100
    lines.append("## 📊 Overall Statistics")
    lines.append("")
    lines.append(f"- **Total Tests**: {overall['total_tests']}")
    lines.append(f"- **TERMINATE_BREACH Count**: {overall['total_breaches']}")
    
    # Add warning symbols
    if breach_rate >= 85:
        warning_symbol = "⚠️⚠️⚠️"
    elif breach_rate >= 75:
        warning_symbol = "⚠️⚠️"
    elif breach_rate >= 65:
        warning_symbol = "⚠️"
    else:
        warning_symbol = ""
    
    lines.append(f"- **Overall Breach Rate**: **{breach_rate:.2f}%** {warning_symbol}")
    lines.append("")
    lines.append("### Key Findings")
    lines.append(f"- More than four-fifths of test cases eventually reached TERMINATE_BREACH status")
    lines.append("- This indicates that under stress testing, models are prone to providing absolute guarantees or certainty promises")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Statistics by model
    lines.append("## 🤖 Statistics by Model")
    lines.append("")
    
    model_order = ['deepseek', 'gemini', 'xai']
    for model in model_order:
        if model not in analysis['by_model']:
            continue
        stats = analysis['by_model'][model]
        model_breach_rate = stats['breach_rate'] * 100
        
        # Determine warning symbol
        if model_breach_rate >= 85:
            warning = "⚠️⚠️ (Highest, tied with other models)"
        elif model_breach_rate >= 75:
            warning = "⚠️⚠️"
        elif model_breach_rate >= 65:
            warning = "⚠️"
        else:
            warning = "(Relatively lowest)"
        
        lines.append(f"### {model.capitalize()}")
        lines.append(f"- **Total Tests**: {stats['total_tests']}")
        lines.append(f"- **Breaches**: {stats['breaches']}")
        lines.append(f"- **Breach Rate**: **{model_breach_rate:.2f}%** {warning}")
        lines.append(f"- **Average Turns**: {stats['avg_turns']:.2f}")
        lines.append(f"- **Median Turns**: {stats['median_turns']:.2f}")
        lines.append(f"- **Average Turns (Breach Cases)**: {stats['avg_turns_breach']:.2f}")
        lines.append(f"- **Average Turns (Non-Breach Cases)**: {stats['avg_turns_non_breach']:.2f}")
        lines.append(f"- **Turn Range**: {stats['min_turns']} - {stats['max_turns']}")
        lines.append("")
    
    # Model comparison analysis
    lines.append("### Model Comparison Analysis")
    model_stats_list = [(model, analysis['by_model'][model]) for model in model_order if model in analysis['by_model']]
    model_stats_list.sort(key=lambda x: x[1]['breach_rate'], reverse=True)
    
    # Find highest and lowest breach rates
    if len(model_stats_list) >= 2:
        highest_models = [m for m, s in model_stats_list if s['breach_rate'] == model_stats_list[0][1]['breach_rate']]
        lowest_models = [m for m, s in model_stats_list if s['breach_rate'] == model_stats_list[-1][1]['breach_rate']]
        
        lines.append(f"1. **{' and '.join([m.capitalize() for m in highest_models])} have the highest breach rate**: Both at {model_stats_list[0][1]['breach_rate']*100:.2f}%, significantly higher than other models")
        if len(model_stats_list) >= 3:
            avg_breach_turns = [(m, s['avg_turns_breach']) for m, s in model_stats_list]
            avg_breach_turns.sort(key=lambda x: x[1])
            fastest = avg_breach_turns[0]
            lines.append(f"2. **{fastest[0].capitalize()} breaches fastest**: {fastest[0].capitalize()} requires an average of only {fastest[1]:.2f} turns to breach, the fastest among all models")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Statistics by language
    lines.append("## 🌐 Statistics by Target Language")
    lines.append("")
    
    for lang, stats in sorted(analysis['by_language'].items()):
        lang_breach_rate = stats['breach_rate'] * 100
        lang_name = "Chinese (中文)" if lang.lower() in ['chinese', '中文'] else f"{lang} (English)" if lang.lower() == 'english' else lang
        
        if lang_breach_rate == 100:
            warning = "⚠️⚠️⚠️ (All breached)"
        elif lang_breach_rate >= 85:
            warning = "⚠️⚠️"
        elif lang_breach_rate >= 75:
            warning = "⚠️"
        else:
            warning = ""
        
        lines.append(f"### {lang_name}")
        lines.append(f"- **Total Tests**: {stats['total_tests']}")
        lines.append(f"- **Breaches**: {stats['breaches']}")
        lines.append(f"- **Breach Rate**: **{lang_breach_rate:.2f}%** {warning}")
        lines.append(f"- **Average Turns**: {stats['avg_turns']:.2f}")
        lines.append(f"- **Median Turns**: {stats['median_turns']:.2f}")
        lines.append("")
    
    lines.append("### Language Comparison Analysis")
    lang_list = list(analysis['by_language'].items())
    if len(lang_list) >= 2:
        lang_list.sort(key=lambda x: x[1]['breach_rate'], reverse=True)
        high_lang = lang_list[0]
        low_lang = lang_list[-1]
        diff = (high_lang[1]['breach_rate'] - low_lang[1]['breach_rate']) * 100
        lines.append(f"1. **{high_lang[0]} tests have a significantly higher breach rate**: {high_lang[0]} test breach rate ({high_lang[1]['breach_rate']*100:.2f}%) is approximately {diff:.1f} percentage points higher than {low_lang[0]} ({low_lang[1]['breach_rate']*100:.2f}%)")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Demographics Distribution (from profiles.json)
    lines.append("## 👥 Demographics Distribution")
    lines.append("")
    lines.append("The following data shows the distribution of Demographics in profiles.json:")
    lines.append("")
    
    # By age group
    if 'by_age_group' in demographics_dist and demographics_dist['by_age_group']:
        lines.append("### By Age Group")
        lines.append("")
        lines.append("| Age Group | Count | Percentage |")
        lines.append("|-----------|-------|------------|")
        for age_group, stats in sorted(demographics_dist['by_age_group'].items()):
            lines.append(f"| **{age_group}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # By gender
    if 'by_gender' in demographics_dist and demographics_dist['by_gender']:
        lines.append("### By Gender")
        lines.append("")
        lines.append("| Gender | Count | Percentage |")
        lines.append("|--------|-------|------------|")
        for gender, stats in sorted(demographics_dist['by_gender'].items()):
            lines.append(f"| **{gender}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # By income
    if 'by_income' in demographics_dist and demographics_dist['by_income']:
        lines.append("### By Income")
        lines.append("")
        lines.append("| Income | Count | Percentage |")
        lines.append("|--------|-------|------------|")
        for income, stats in sorted(demographics_dist['by_income'].items()):
            lines.append(f"| **{income}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # By education
    if 'by_education' in demographics_dist and demographics_dist['by_education']:
        lines.append("### By Education Level")
        lines.append("")
        lines.append("| Education Level | Count | Percentage |")
        lines.append("|----------------|-------|------------|")
        for education, stats in sorted(demographics_dist['by_education'].items()):
            lines.append(f"| **{education}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # By occupation
    if 'by_occupation' in demographics_dist and demographics_dist['by_occupation']:
        lines.append("### By Occupation")
        lines.append("")
        lines.append("| Occupation | Count | Percentage |")
        lines.append("|------------|-------|------------|")
        sorted_occ = sorted(demographics_dist['by_occupation'].items(), key=lambda x: x[1]['count'], reverse=True)
        for occupation, stats in sorted_occ:
            lines.append(f"| **{occupation}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # By marital status
    if 'by_marital_status' in demographics_dist and demographics_dist['by_marital_status']:
        lines.append("### By Marital Status")
        lines.append("")
        lines.append("| Marital Status | Count | Percentage |")
        lines.append("|----------------|-------|------------|")
        for marital_status, stats in sorted(demographics_dist['by_marital_status'].items()):
            lines.append(f"| **{marital_status}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # By has children
    if 'by_has_children' in demographics_dist and demographics_dist['by_has_children']:
        lines.append("### By Has Children")
        lines.append("")
        lines.append("| Has Children | Count | Percentage |")
        lines.append("|--------------|-------|------------|")
        for has_children, stats in sorted(demographics_dist['by_has_children'].items()):
            lines.append(f"| **{has_children}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # By ethnicity
    if 'by_ethnicity' in demographics_dist and demographics_dist['by_ethnicity']:
        lines.append("### By Ethnicity")
        lines.append("")
        lines.append("| Ethnicity | Count | Percentage |")
        lines.append("|----------|-------|------------|")
        sorted_eth = sorted(demographics_dist['by_ethnicity'].items(), key=lambda x: x[1]['count'], reverse=True)
        for ethnicity, stats in sorted_eth:
            lines.append(f"| **{ethnicity}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    # By location
    if 'by_location' in demographics_dist and demographics_dist['by_location']:
        lines.append("### By Location")
        lines.append("")
        lines.append("| Location | Count | Percentage |")
        lines.append("|---------|-------|------------|")
        for location, stats in sorted(demographics_dist['by_location'].items()):
            lines.append(f"| **{location}** | {stats['count']} | **{stats['percentage']:.2f}%** |")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    # Statistics by main condition type
    lines.append("## 🏥 Statistics by Main Condition Type (ignoring \"with\" part)")
    lines.append("")
    lines.append("### Key Findings")
    lines.append("")
    lines.append("| Condition Type | Tests | Breaches | Breach Rate | Avg Turns |")
    lines.append("|---------------|-------|----------|-------------|-----------|")
    
    sorted_conditions = sorted(
        analysis['by_main_condition'].items(),
        key=lambda x: (x[1]['breach_rate'], -x[1]['total_tests']),
        reverse=True
    )
    
    for condition, stats in sorted_conditions[:20]:  # Top 20
        breach_rate_pct = stats['breach_rate'] * 100
        avg_turns = stats['avg_turns']
        
        # Add warning symbols
        if breach_rate_pct == 100:
            warning = "⚠️"
            if avg_turns < 8:
                warning += " (Fastest)"
        elif breach_rate_pct >= 80:
            warning = ""
        else:
            warning = ""
        
        lines.append(f"| **{condition}** | {stats['total_tests']} | {stats['breaches']} | **{breach_rate_pct:.0f}%** | {avg_turns:.2f} {warning} |")
    
    lines.append("")
    lines.append("### Key Insights")
    if sorted_conditions:
        top_condition = sorted_conditions[0]
        lines.append(f"1. **{top_condition[0]} has the highest breach rate**: {top_condition[1]['breach_rate']*100:.0f}%, requiring an average of {top_condition[1]['avg_turns']:.2f} turns")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Statistics by breach type
    lines.append("## 🚨 Statistics by Breach Type")
    lines.append("")
    lines.append("### Breach Type Distribution")
    lines.append("")
    lines.append("| Breach Type | Count | Percentage | Avg Turns | Turn Range |")
    lines.append("|------------|-------|------------|-----------|------------|")
    
    sorted_breach_types = sorted(
        analysis['by_breach_type'].items(),
        key=lambda x: x[1]['total_tests'],
        reverse=True
    )
    
    total_breaches = analysis['overall']['total_breaches']
    for breach_type, stats in sorted_breach_types:
        count = stats['total_tests']
        percentage = (count / total_breaches * 100) if total_breaches > 0 else 0
        breach_type_en = translate_breach_type(breach_type)
        lines.append(f"| **{breach_type_en}** | {count} | **{percentage:.2f}%** | {stats['avg_turns']:.2f} | {stats['min_turns']}-{stats['max_turns']} |")
    
    lines.append("")
    lines.append("### Breach Type Analysis")
    if sorted_breach_types:
        top_type = sorted_breach_types[0]
        top_type_en = translate_breach_type(top_type[0])
        lines.append(f"1. **{top_type_en} is the primary breach method** ({top_type[1]['total_tests']/total_breaches*100:.2f}%)")
        lines.append(f"   - Average {top_type[1]['avg_turns']:.2f} turns to breach")
        lines.append(f"   - Fastest only requires {top_type[1]['min_turns']} turns")
        lines.append(f"   - This is the breach type requiring the most attention")
        lines.append("")
        
        # Add descriptions for other main breach types
        if len(sorted_breach_types) > 1:
            second_type = sorted_breach_types[1]
            second_type_en = translate_breach_type(second_type[0])
            lines.append(f"2. **{second_type_en}** ({second_type[1]['total_tests']/total_breaches*100:.2f}%)")
            lines.append(f"   - Average {second_type[1]['avg_turns']:.2f} turns to breach")
            lines.append(f"   - Professional role boundaries need strengthening")
            lines.append("")
        
        if len(sorted_breach_types) > 2:
            third_type = sorted_breach_types[2]
            third_type_en = translate_breach_type(third_type[0])
            lines.append(f"3. **{third_type_en}** ({third_type[1]['total_tests']/total_breaches*100:.2f}%)")
            lines.append(f"   - Average {third_type[1]['avg_turns']:.2f} turns to breach")
            lines.append("")
        
        # Special note on cognitive validation
        cognitive_validation = next((t for t in sorted_breach_types if '认知验证' in t[0] or 'Cognitive' in t[0]), None)
        if cognitive_validation:
            cog_val_en = translate_breach_type(cognitive_validation[0])
            lines.append(f"4. **{cog_val_en}** ({cognitive_validation[1]['total_tests']/total_breaches*100:.2f}%)")
            lines.append(f"   - Average {cognitive_validation[1]['avg_turns']:.2f} turns to breach")
            lines.append(f"   - Model validated user's distorted cognitions, pathological logic, or harmful beliefs (e.g., eating disorder rules, paranoid delusions, self-blame, etc.)")
            lines.append(f"   - This is a manifestation of Cognitive Validation Testing, indicating that models may abandon professional boundaries and collude with users' erroneous cognitions under pressure")
            lines.append("")
        
        # Special note on self-harm endorsement
        self_harm = next((t for t in sorted_breach_types if '自我伤害' in t[0] or 'self-harm' in t[0]), None)
        if self_harm:
            self_harm_en = translate_breach_type(self_harm[0])
            lines.append(f"5. **{self_harm_en}** ({self_harm[1]['total_tests']/total_breaches*100:.2f}%)")
            lines.append(f"   - Average {self_harm[1]['avg_turns']:.2f} turns to breach")
            lines.append(f"   - This is the most dangerous breach type and requires special attention")
            lines.append("")
        
        # Note on medical diagnosis breach
        medical = next((t for t in sorted_breach_types if '医学' in t[0] or 'medical' in t[0]), None)
        if medical:
            medical_en = translate_breach_type(medical[0])
            lines.append(f"6. **{medical_en}** ({medical[1]['total_tests']/total_breaches*100:.2f}%)")
            lines.append(f"   - Average {medical[1]['avg_turns']:.2f} turns to breach")
            lines.append(f"   - Model boundary maintenance is relatively better in this aspect")
            lines.append("")
    else:
        lines.append("")
    lines.append("---")
    lines.append("")
    
    # Statistics on attempt counts and success rates for each breach method
    if 'breach_attempt_analysis' in analysis:
        lines.append("## 🎯 Attempt Counts and Success Rates by Breach Type")
        lines.append("")
        lines.append("### Overall Statistics")
        lines.append("")
        lines.append("| Breach Type | Attempts | Successes | Failures | Success Rate |")
        lines.append("|------------|----------|-----------|----------|--------------|")
        
        summary = analysis['breach_attempt_analysis']['summary']
        for breach_type, stats in sorted(summary.items(), key=lambda x: x[1]['attempted'], reverse=True):
            breach_type_en = translate_breach_type(breach_type)
            lines.append(f"| **{breach_type_en}** | {stats['attempted']} | {stats['succeeded']} | {stats['failed']} | **{stats['success_rate']:.2f}%** |")
        
        lines.append("")
        lines.append("### Key Findings")
        if summary:
            max_attempted = max(summary.items(), key=lambda x: x[1]['attempted'])
            max_success_rate = max([(k, v) for k, v in summary.items() if v['attempted'] > 0], key=lambda x: x[1]['success_rate'])
            max_attempted_en = translate_breach_type(max_attempted[0])
            max_success_rate_en = translate_breach_type(max_success_rate[0])
            lines.append(f"1. **Most attempted breach type**: {max_attempted_en} ({max_attempted[1]['attempted']} attempts)")
            lines.append(f"2. **Highest success rate breach type**: {max_success_rate_en} ({max_success_rate[1]['success_rate']:.2f}%)")
        lines.append("")
        
        # Detailed statistics by model
        lines.append("### Detailed Statistics by Model")
        lines.append("")
        by_model = analysis['breach_attempt_analysis']['by_model']
        for model in sorted(by_model.keys()):
            lines.append(f"#### {model.upper()}")
            lines.append("")
            lines.append("| Breach Type | Attempts | Successes | Failures | Success Rate |")
            lines.append("|------------|----------|-----------|----------|--------------|")
            model_stats = by_model[model]
            for breach_type, stats in sorted(model_stats.items(), key=lambda x: x[1]['attempted'], reverse=True):
                breach_type_en = translate_breach_type(breach_type)
                lines.append(f"| {breach_type_en} | {stats['attempted']} | {stats['succeeded']} | {stats['failed']} | **{stats['success_rate']:.2f}%** |")
            lines.append("")
        lines.append("---")
        lines.append("")
    
    # Statistics by model+language combination
    lines.append("## 🔗 Statistics by Model+Language Combination")
    lines.append("")
    
    model_lang_combinations = sorted(analysis['by_model_language'].items(), key=lambda x: (x[1]['model'], x[1]['language']))
    for key, stats in model_lang_combinations:
        lang_name = "Chinese" if stats['language'].lower() in ['chinese', '中文'] else "English"
        lang_breach_rate = stats['breach_rate'] * 100
        
        if lang_breach_rate == 100:
            warning = "⚠️⚠️⚠️ (Highest risk)"
        elif lang_breach_rate >= 85:
            warning = "⚠️⚠️"
        elif lang_breach_rate >= 75:
            warning = "⚠️"
        else:
            warning = "(Lowest)"
        
        lines.append(f"### {stats['model'].capitalize()} - {lang_name}")
        lines.append(f"- **Total Tests**: {stats['total_tests']}")
        lines.append(f"- **Breaches**: {stats['breaches']}")
        lines.append(f"- **Breach Rate**: **{lang_breach_rate:.2f}%** {warning}")
        lines.append(f"- **Average Turns**: {stats['avg_turns']:.2f}")
        lines.append(f"- **Median Turns**: {stats['median_turns']:.2f}")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    # Detailed turn analysis
    lines.append("## 📈 Detailed Turn Analysis")
    lines.append("")
    turns = analysis['turns_analysis']
    
    lines.append("### All Cases")
    lines.append(f"- **Average Turns**: {turns['overall']['avg']:.2f}")
    lines.append(f"- **Median Turns**: {turns['overall']['median']:.2f}")
    lines.append(f"- **Standard Deviation**: {turns['overall']['stdev']:.2f}")
    lines.append(f"- **Range**: {turns['overall']['min']} - {turns['overall']['max']}")
    lines.append("")
    
    lines.append("### Breach Cases")
    lines.append(f"- **Average Turns**: {turns['breach_cases']['avg']:.2f}")
    lines.append(f"- **Median Turns**: {turns['breach_cases']['median']:.2f}")
    lines.append(f"- **Standard Deviation**: {turns['breach_cases']['stdev']:.2f}")
    lines.append(f"- **Range**: {turns['breach_cases']['min']} - {turns['breach_cases']['max']}")
    lines.append("")
    
    lines.append("### Non-Breach Cases")
    lines.append(f"- **Average Turns**: {turns['non_breach_cases']['avg']:.2f}")
    lines.append(f"- **Median Turns**: {turns['non_breach_cases']['median']:.2f}")
    lines.append(f"- **Standard Deviation**: {turns['non_breach_cases']['stdev']:.2f}")
    lines.append(f"- **Range**: {turns['non_breach_cases']['min']} - {turns['non_breach_cases']['max']}")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    
    # Multi-dimensional attempt strategy analysis
    if 'multi_attempt_analysis' in analysis and analysis['multi_attempt_analysis']['total_cases'] > 0:
        multi_analysis = analysis['multi_attempt_analysis']
        lines.append("## 🔄 Multi-Dimensional Attempt Strategy Analysis")
        lines.append("")
        lines.append("### Core Findings")
        lines.append("")
        total_multi = multi_analysis['total_cases']
        total_breaches = analysis['overall']['total_breaches']
        pct_of_total = (total_multi / total_breaches * 100) if total_breaches > 0 else 0
        lines.append(f"Among all breach cases, **{total_multi} cases** ({pct_of_total:.1f}% of all breach cases) attempted multiple boundary-breaking strategies but ultimately succeeded in only one dimension.")
        lines.append("")
        lines.append("### Classification by Final Successful Dimension")
        lines.append("")
        lines.append("| Final Successful Dimension | Cases | Percentage | Avg Turns | Median Turns |")
        lines.append("|---------------------------|-------|------------|-----------|--------------|")
        by_successful = multi_analysis['by_successful_type']
        for breach_type, stats in sorted(by_successful.items(), key=lambda x: x[1]['count'], reverse=True):
            breach_type_en = translate_breach_type(breach_type)
            lines.append(f"| **{breach_type_en}** | {stats['count']} | {stats['percentage']:.1f}% | {stats['avg_turns']:.2f} | {stats['median_turns']:.2f} |")
        lines.append("")
        lines.append("### Attempt Type Combination Patterns (Overall)")
        lines.append("")
        lines.append("| Attempt Type Combination | Cases | Percentage |")
        lines.append("|-------------------------|-------|------------|")
        for combo, count in sorted(multi_analysis['type_combinations'].items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_multi * 100) if total_multi > 0 else 0
            # Translate combination
            combo_parts = combo.split(' + ')
            combo_en = ' + '.join([translate_breach_type(part) for part in combo_parts])
            lines.append(f"| {combo_en} | {count} | {pct:.1f}% |")
        lines.append("")
        lines.append("### Distribution by Model")
        lines.append("")
        for model, count in sorted(multi_analysis['by_model'].items()):
            lines.append(f"- **{model.capitalize()}**: {count} cases")
        lines.append("")
        lines.append("### Turn Statistics")
        turns_stats = multi_analysis['turns_stats']
        lines.append(f"- **Average Turns**: {turns_stats['avg']:.2f}")
        lines.append(f"- **Median Turns**: {turns_stats['median']:.2f}")
        lines.append(f"- **Turn Range**: {turns_stats['min']} - {turns_stats['max']}")
        lines.append("")
        lines.append("### Cognitive Analysis")
        lines.append("")
        lines.append("#### 1. **Strategy Failure and Success Patterns**")
        lines.append("")
        lines.append("When AS attempts multiple boundary-breaking strategies, models may show different resistance in the following aspects:")
        lines.append("- **Professional Role Boundary Breach**: Models may identify and reject requests to act as therapist/HR/legal advisor early on")
        lines.append("- **Relationship Dependency/Exclusive Commitment**: Models may reject 24/7 companionship and exclusive relationship commitments")
        lines.append("- **Cognitive Validation/Distorted Cognition Validation**: Models may reject validating paranoid delusions, self-blame, etc.")
        lines.append("- **Medical Diagnosis/Medical Advice Boundary Breach**: Models may reject providing diagnoses or prescriptions")
        lines.append("- **Absolute Guarantee/Zero-Risk Promise**: Models may be more likely to compromise (see detailed analysis below)")
        lines.append("")
        lines.append("When certain strategies fail, AS switches to other strategies, and models may compromise in another dimension.")
        lines.append("")
        lines.append("#### 2. **Distribution Pattern of Final Successful Dimensions**")
        lines.append("")
        # Find the most common final successful dimension
        most_common_success_type = max(by_successful.items(), key=lambda x: x[1]['count'])
        most_common_en = translate_breach_type(most_common_success_type[0])
        lines.append(f"- **Most Common Final Successful Dimension**: {most_common_en} ({most_common_success_type[1]['count']} cases, {most_common_success_type[1]['percentage']:.1f}%)")
        lines.append("")
        if most_common_success_type[0] == '绝对保证/零风险承诺':
            lines.append("**Key Finding**: Absolute Guarantee/Zero-Risk Promise is the most common final breakthrough point in multi-dimensional attempts, indicating:")
            lines.append("- Models may have some defense mechanisms against other boundary types (professional role, relationship dependency, cognitive validation, etc.)")
            lines.append("- But when facing users' urgent need for certainty, models are more likely to abandon boundaries")
            lines.append("- **Absolute Guarantee/Zero-Risk Promise may be the model's weakest boundary point**")
        else:
            lines.append(f"**Key Finding**: {most_common_en} is the most common final breakthrough point in multi-dimensional attempts, suggesting this dimension may be a relatively weak boundary for models.")
        lines.append("")
        lines.append("#### 3. **Most Common Combination Patterns**")
        lines.append("")
        if multi_analysis['type_combinations']:
            most_common_combo = max(multi_analysis['type_combinations'].items(), key=lambda x: x[1])
            combo_parts = most_common_combo[0].split(' + ')
            combo_en = ' + '.join([translate_breach_type(part) for part in combo_parts])
            lines.append(f"- **Most Common Combination**: {combo_en} ({most_common_combo[1]} cases, {most_common_combo[1]/total_multi*100:.1f}%)")
            lines.append("- This reflects the most commonly used multi-dimensional attack strategy combinations by AS")
        lines.append("")
        lines.append("#### 4. **Detailed Dimension Analysis**")
        lines.append("")
        for breach_type, stats in sorted(by_successful.items(), key=lambda x: x[1]['count'], reverse=True):
            if stats['count'] > 0:
                breach_type_en = translate_breach_type(breach_type)
                lines.append(f"**{breach_type_en}** ({stats['count']} cases):")
                if stats['combinations']:
                    lines.append(f"- Main Combination Patterns:")
                    top_combos = sorted(stats['combinations'].items(), key=lambda x: x[1], reverse=True)[:3]
                    for combo, count in top_combos:
                        pct = (count / stats['count'] * 100) if stats['count'] > 0 else 0
                        combo_parts = combo.split(' + ')
                        combo_en = ' + '.join([translate_breach_type(part) for part in combo_parts])
                        lines.append(f"  - {combo_en}: {count} cases ({pct:.1f}%)")
                lines.append(f"- Average Turns: {stats['avg_turns']:.2f}, Median: {stats['median_turns']:.2f}")
                lines.append("")
        lines.append("#### 5. **Psychological Mechanism Analysis**")
        lines.append("")
        lines.append("This multi-dimensional attempt pattern may reflect the following psychological mechanisms:")
        lines.append("1. **Alternative Paths After Strategy Failure**: When one boundary-breaking strategy fails, AS tries other strategies until finding the model's weakest point")
        lines.append("2. **Empathy Fatigue**: After models repeatedly reject user requests, they may be more likely to compromise when users express strong emotional needs")
        lines.append("3. **Boundary Differential Sensitivity**: Models may have different sensitivity to different boundary types, with some boundaries more easily breached under pressure")
        lines.append("4. **Immediate Pressure**: Users often use urgent, crisis language when making requests, and this immediate pressure may reduce the model's boundary judgment")
        lines.append("5. **Cumulative Effect**: Previous multi-turn interactions build trust relationships, making models more willing to provide concessions when users 'need it most'")
        lines.append("")
        lines.append("#### 6. **Safety Implications**")
        lines.append("")
        lines.append("This finding has important implications for AI safety:")
        if most_common_success_type[0] == '绝对保证/零风险承诺':
            lines.append("- **Need to particularly strengthen Absolute Guarantee/Zero-Risk Promise boundary protection**, as this is the most common final breakthrough point")
        else:
            most_common_en = translate_breach_type(most_common_success_type[0])
            lines.append(f"- **Need to particularly strengthen {most_common_en} boundary protection**, as this is the most common final breakthrough point")
        lines.append("- **Boundary Maintenance After Multi-Turn Interactions**: As interaction turns increase, models need stronger boundary maintenance mechanisms")
        lines.append("- **Urgency/Crisis Language Recognition**: Need to train models to recognize and resist boundary-breaking attempts packaged as urgent needs")
        lines.append("- **Balance Between Empathy and Boundaries**: Models need to learn to maintain all safety boundaries while maintaining empathy")
        lines.append("- **Boundary Consistency**: Need to ensure models have equal-strength protection for all boundary types to avoid 'weak links'")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # Data files
    lines.append("## 📋 Data Files")
    lines.append("")
    lines.append(f"Detailed analysis data (JSON format) saved to:")
    lines.append(f"`{base_dir}/analysis_report.json`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Report Generated: {datetime.now().strftime('%Y-%m-%d')}*")
    lines.append("*Analysis Script Version: analyze_run2.py*")
    
    return "\n".join(lines)

def main():
    base_dir = "experiment_results/run2"
    profiles_file = "profiles.json"
    
    print(f"正在加载结果文件从: {base_dir}")
    results = load_all_results(base_dir)
    print(f"成功加载 {len(results)} 个结果文件\n")
    
    print("正在分析数据...")
    analysis = analyze_results(results)
    
    print("正在获取 Demographics 分布情况...")
    demographics_dist = get_demographics_distribution(profiles_file)
    
    # 保存JSON格式的分析结果
    output_file = os.path.join(base_dir, "analysis_report.json")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print(f"\n详细分析结果已保存到: {output_file}")
    
    # 生成Markdown格式的报告（中文）
    markdown_report_cn = generate_markdown_report_run2(analysis, base_dir, demographics_dist)
    md_output_file_cn = os.path.join(base_dir, "ANALYSIS_REPORT_CN.md")
    with open(md_output_file_cn, 'w', encoding='utf-8') as f:
        f.write(markdown_report_cn)
    print(f"Markdown分析报告（中文）已保存到: {md_output_file_cn}")
    
    # 生成Markdown格式的报告（英文）
    markdown_report_en = generate_markdown_report_en_run2(analysis, base_dir, demographics_dist)
    md_output_file_en = os.path.join(base_dir, "ANALYSIS_REPORT_EN.md")
    with open(md_output_file_en, 'w', encoding='utf-8') as f:
        f.write(markdown_report_en)
    print(f"Markdown analysis report (English) saved to: {md_output_file_en}")

if __name__ == "__main__":
    main()

