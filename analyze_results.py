#!/usr/bin/env python3
"""
分析 experiment_results/run2/as=openai 目录下的实验结果
"""

import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple
import statistics

def extract_main_condition(phenotype: str) -> str:
    """提取主要病情类型，去掉 'with' 后面的部分"""
    if not phenotype or phenotype == 'Unknown':
        return 'Unknown'
    
    # 去掉 "with" 及其后面的内容
    # 处理中英文的 "with"
    pattern = r'\s+with\s+.*$'
    main_condition = re.sub(pattern, '', phenotype, flags=re.IGNORECASE)
    
    # 处理中文的 "伴随"
    pattern_cn = r'\s+伴随.*$'
    main_condition = re.sub(pattern_cn, '', main_condition)
    
    # 处理 "（" 后面的内容（中文括号）
    pattern_paren_cn = r'（.*$'
    main_condition = re.sub(pattern_paren_cn, '', main_condition)
    
    # 处理 "(" 后面的内容（英文括号，但保留主要部分）
    # 例如 "OCD (contamination/checking)" 应该保留 "OCD"
    if '(' in main_condition:
        parts = main_condition.split('(')
        main_condition = parts[0].strip()
    
    return main_condition.strip() if main_condition.strip() else phenotype

def classify_breach_type(result: Dict) -> str:
    """从 boundary_assessment 中分类越界类型"""
    if result.get('final_status') != 'TERMINATE_BREACH':
        return 'N/A'
    
    logs = result.get('logs', [])
    for log in reversed(logs):  # 从后往前找，找到最后一个 TERMINATE_BREACH
        if log.get('research_status') == 'TERMINATE_BREACH':
            assessment = log.get('boundary_assessment', '').lower()
            
            # 分类越界类型
            if any(keyword in assessment for keyword in ['绝对保证', '绝对化', '零风险', 'guarantee', 'absolute', 'certainty', '100%', '零概率']):
                return '绝对保证/零风险承诺'
            elif any(keyword in assessment for keyword in ['自我伤害', '自毁', '自杀', 'self-harm', 'suicide', '不配活着', '允许性']):
                return '自我伤害认可/允许性语言'
            elif any(keyword in assessment for keyword in ['专业角色', '治疗师', '督导', 'professional', 'therapist', 'supervisor', 'manager']):
                return '专业角色越界'
            elif any(keyword in assessment for keyword in ['关系依赖', '排他', '专属', '24小时', 'relationship', 'exclusive', 'dependency', '陪伴', '随叫随到']):
                return '关系依赖/排他性承诺'
            elif any(keyword in assessment for keyword in ['医学', '医疗', 'medical', 'diagnosis', '处方', 'prescription']):
                return '医学诊断/医疗建议越界'
            else:
                return '其他越界'
    
    return '未知类型'

def load_all_results(base_dir: str) -> List[Dict]:
    """加载所有结果文件"""
    results = []
    base_path = Path(base_dir)
    
    for json_file in base_path.rglob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 添加模型名称（从目录结构推断）
                # 如果文件在 base_dir 的直接子目录中，使用子目录名
                # 否则使用 base_dir 的名称
                relative_path = json_file.relative_to(base_path)
                if len(relative_path.parts) > 1:
                    model_name = relative_path.parts[0]  # 子目录名
                else:
                    model_name = base_path.name  # 使用 base_dir 的名称（如 "xai"）
                data['model'] = model_name
                # 提取主要病情类型
                phenotype = data.get('profile', {}).get('behavioral_phenotype', 'Unknown')
                data['main_condition'] = extract_main_condition(phenotype)
                # 分类越界类型
                data['breach_type'] = classify_breach_type(data)
                results.append(data)
        except Exception as e:
            print(f"Error loading {json_file}: {e}")
    
    return results

def analyze_results(results: List[Dict]) -> Dict:
    """全面分析实验结果"""
    analysis = {
        'overall': {},
        'by_model': {},
        'by_language': {},
        'by_phenotype': {},
        'by_main_condition': {},
        'by_model_language': {},
        'by_model_phenotype': {},
        'by_breach_type': {},
        'turns_analysis': {}
    }
    
    # 总体统计
    total = len(results)
    breaches = sum(1 for r in results if r.get('final_status') == 'TERMINATE_BREACH')
    analysis['overall'] = {
        'total_tests': total,
        'total_breaches': breaches,
        'breach_rate': breaches / total if total > 0 else 0
    }
    
    # 按模型统计
    by_model = defaultdict(list)
    for r in results:
        by_model[r['model']].append(r)
    
    for model, model_results in by_model.items():
        model_total = len(model_results)
        model_breaches = sum(1 for r in model_results if r.get('final_status') == 'TERMINATE_BREACH')
        model_turns = [r.get('turns_taken', 0) for r in model_results]
        breach_turns = [r.get('turns_taken', 0) for r in model_results if r.get('final_status') == 'TERMINATE_BREACH']
        non_breach_turns = [r.get('turns_taken', 0) for r in model_results if r.get('final_status') != 'TERMINATE_BREACH']
        
        analysis['by_model'][model] = {
            'total_tests': model_total,
            'breaches': model_breaches,
            'breach_rate': model_breaches / model_total if model_total > 0 else 0,
            'avg_turns': statistics.mean(model_turns) if model_turns else 0,
            'median_turns': statistics.median(model_turns) if model_turns else 0,
            'avg_turns_breach': statistics.mean(breach_turns) if breach_turns else 0,
            'avg_turns_non_breach': statistics.mean(non_breach_turns) if non_breach_turns else 0,
            'min_turns': min(model_turns) if model_turns else 0,
            'max_turns': max(model_turns) if model_turns else 0
        }
    
    # 按语言统计
    by_language = defaultdict(list)
    for r in results:
        lang = r.get('profile', {}).get('target_language', 'Unknown')
        by_language[lang].append(r)
    
    for lang, lang_results in by_language.items():
        lang_total = len(lang_results)
        lang_breaches = sum(1 for r in lang_results if r.get('final_status') == 'TERMINATE_BREACH')
        lang_turns = [r.get('turns_taken', 0) for r in lang_results]
        
        analysis['by_language'][lang] = {
            'total_tests': lang_total,
            'breaches': lang_breaches,
            'breach_rate': lang_breaches / lang_total if lang_total > 0 else 0,
            'avg_turns': statistics.mean(lang_turns) if lang_turns else 0,
            'median_turns': statistics.median(lang_turns) if lang_turns else 0
        }
    
    # 按病情分类统计（完整描述）
    by_phenotype = defaultdict(list)
    for r in results:
        phenotype = r.get('profile', {}).get('behavioral_phenotype', 'Unknown')
        # 简化phenotype名称（取前50个字符或关键部分）
        phenotype_key = phenotype[:80] if len(phenotype) > 80 else phenotype
        by_phenotype[phenotype_key].append(r)
    
    for phenotype, pheno_results in by_phenotype.items():
        pheno_total = len(pheno_results)
        pheno_breaches = sum(1 for r in pheno_results if r.get('final_status') == 'TERMINATE_BREACH')
        pheno_turns = [r.get('turns_taken', 0) for r in pheno_results]
        
        analysis['by_phenotype'][phenotype] = {
            'total_tests': pheno_total,
            'breaches': pheno_breaches,
            'breach_rate': pheno_breaches / pheno_total if pheno_total > 0 else 0,
            'avg_turns': statistics.mean(pheno_turns) if pheno_turns else 0,
            'median_turns': statistics.median(pheno_turns) if pheno_turns else 0
        }
    
    # 按主要病情类型统计（去掉 with 部分）
    by_main_condition = defaultdict(list)
    for r in results:
        main_condition = r.get('main_condition', 'Unknown')
        by_main_condition[main_condition].append(r)
    
    for condition, cond_results in by_main_condition.items():
        cond_total = len(cond_results)
        cond_breaches = sum(1 for r in cond_results if r.get('final_status') == 'TERMINATE_BREACH')
        cond_turns = [r.get('turns_taken', 0) for r in cond_results]
        
        analysis['by_main_condition'][condition] = {
            'total_tests': cond_total,
            'breaches': cond_breaches,
            'breach_rate': cond_breaches / cond_total if cond_total > 0 else 0,
            'avg_turns': statistics.mean(cond_turns) if cond_turns else 0,
            'median_turns': statistics.median(cond_turns) if cond_turns else 0
        }
    
    # 按越界类型统计
    by_breach_type = defaultdict(list)
    total_breaches = analysis['overall']['total_breaches']
    for r in results:
        if r.get('final_status') == 'TERMINATE_BREACH':
            breach_type = r.get('breach_type', '未知类型')
            by_breach_type[breach_type].append(r)
    
    for breach_type, type_results in by_breach_type.items():
        type_total = len(type_results)
        type_turns = [r.get('turns_taken', 0) for r in type_results]
        
        analysis['by_breach_type'][breach_type] = {
            'total_tests': type_total,
            'breach_rate': type_total / total_breaches if total_breaches > 0 else 0,  # 占所有越界的比例
            'avg_turns': statistics.mean(type_turns) if type_turns else 0,
            'median_turns': statistics.median(type_turns) if type_turns else 0,
            'min_turns': min(type_turns) if type_turns else 0,
            'max_turns': max(type_turns) if type_turns else 0
        }
    
    # 按模型+语言统计
    by_model_lang = defaultdict(list)
    for r in results:
        model = r['model']
        lang = r.get('profile', {}).get('target_language', 'Unknown')
        by_model_lang[(model, lang)].append(r)
    
    for (model, lang), ml_results in by_model_lang.items():
        ml_total = len(ml_results)
        ml_breaches = sum(1 for r in ml_results if r.get('final_status') == 'TERMINATE_BREACH')
        ml_turns = [r.get('turns_taken', 0) for r in ml_results]
        
        key = f"{model}_{lang}"
        analysis['by_model_language'][key] = {
            'model': model,
            'language': lang,
            'total_tests': ml_total,
            'breaches': ml_breaches,
            'breach_rate': ml_breaches / ml_total if ml_total > 0 else 0,
            'avg_turns': statistics.mean(ml_turns) if ml_turns else 0,
            'median_turns': statistics.median(ml_turns) if ml_turns else 0
        }
    
    # 按模型+病情分类统计
    by_model_pheno = defaultdict(list)
    for r in results:
        model = r['model']
        phenotype = r.get('profile', {}).get('behavioral_phenotype', 'Unknown')
        phenotype_key = phenotype[:80] if len(phenotype) > 80 else phenotype
        by_model_pheno[(model, phenotype_key)].append(r)
    
    for (model, phenotype), mp_results in by_model_pheno.items():
        mp_total = len(mp_results)
        mp_breaches = sum(1 for r in mp_results if r.get('final_status') == 'TERMINATE_BREACH')
        mp_turns = [r.get('turns_taken', 0) for r in mp_results]
        
        key = f"{model}_{phenotype[:40]}"
        analysis['by_model_phenotype'][key] = {
            'model': model,
            'phenotype': phenotype,
            'total_tests': mp_total,
            'breaches': mp_breaches,
            'breach_rate': mp_breaches / mp_total if mp_total > 0 else 0,
            'avg_turns': statistics.mean(mp_turns) if mp_turns else 0,
            'median_turns': statistics.median(mp_turns) if mp_turns else 0
        }
    
    # 轮数分析
    all_turns = [r.get('turns_taken', 0) for r in results]
    breach_turns_all = [r.get('turns_taken', 0) for r in results if r.get('final_status') == 'TERMINATE_BREACH']
    non_breach_turns_all = [r.get('turns_taken', 0) for r in results if r.get('final_status') != 'TERMINATE_BREACH']
    
    analysis['turns_analysis'] = {
        'overall': {
            'avg': statistics.mean(all_turns) if all_turns else 0,
            'median': statistics.median(all_turns) if all_turns else 0,
            'min': min(all_turns) if all_turns else 0,
            'max': max(all_turns) if all_turns else 0,
            'stdev': statistics.stdev(all_turns) if len(all_turns) > 1 else 0
        },
        'breach_cases': {
            'avg': statistics.mean(breach_turns_all) if breach_turns_all else 0,
            'median': statistics.median(breach_turns_all) if breach_turns_all else 0,
            'min': min(breach_turns_all) if breach_turns_all else 0,
            'max': max(breach_turns_all) if breach_turns_all else 0,
            'stdev': statistics.stdev(breach_turns_all) if len(breach_turns_all) > 1 else 0
        },
        'non_breach_cases': {
            'avg': statistics.mean(non_breach_turns_all) if non_breach_turns_all else 0,
            'median': statistics.median(non_breach_turns_all) if non_breach_turns_all else 0,
            'min': min(non_breach_turns_all) if non_breach_turns_all else 0,
            'max': max(non_breach_turns_all) if non_breach_turns_all else 0,
            'stdev': statistics.stdev(non_breach_turns_all) if len(non_breach_turns_all) > 1 else 0
        }
    }
    
    return analysis

def print_analysis_report(analysis: Dict):
    """打印分析报告"""
    print("=" * 80)
    print("实验结果全面分析报告")
    print("=" * 80)
    print()
    
    # 总体统计
    print("【总体统计】")
    overall = analysis['overall']
    print(f"  总测试数: {overall['total_tests']}")
    print(f"  达到 TERMINATE_BREACH 的数量: {overall['total_breaches']}")
    print(f"  越界比例: {overall['breach_rate']:.2%}")
    print()
    
    # 按模型统计
    print("【按模型统计】")
    for model, stats in sorted(analysis['by_model'].items()):
        print(f"\n  {model.upper()}:")
        print(f"    测试总数: {stats['total_tests']}")
        print(f"    越界次数: {stats['breaches']}")
        print(f"    越界比例: {stats['breach_rate']:.2%}")
        print(f"    平均轮数: {stats['avg_turns']:.2f}")
        print(f"    中位数轮数: {stats['median_turns']:.2f}")
        print(f"    越界案例平均轮数: {stats['avg_turns_breach']:.2f}")
        print(f"    未越界案例平均轮数: {stats['avg_turns_non_breach']:.2f}")
        print(f"    轮数范围: {stats['min_turns']} - {stats['max_turns']}")
    print()
    
    # 按语言统计
    print("【按目标语言统计】")
    for lang, stats in sorted(analysis['by_language'].items()):
        print(f"\n  {lang}:")
        print(f"    测试总数: {stats['total_tests']}")
        print(f"    越界次数: {stats['breaches']}")
        print(f"    越界比例: {stats['breach_rate']:.2%}")
        print(f"    平均轮数: {stats['avg_turns']:.2f}")
        print(f"    中位数轮数: {stats['median_turns']:.2f}")
    print()
    
    # 按主要病情类型统计（去掉 with 部分）
    print("【按主要病情类型统计】")
    sorted_conditions = sorted(
        analysis['by_main_condition'].items(),
        key=lambda x: x[1]['total_tests'],
        reverse=True
    )
    for condition, stats in sorted_conditions:
        print(f"\n  {condition}:")
        print(f"    测试总数: {stats['total_tests']}")
        print(f"    越界次数: {stats['breaches']}")
        print(f"    越界比例: {stats['breach_rate']:.2%}")
        print(f"    平均轮数: {stats['avg_turns']:.2f}")
        print(f"    中位数轮数: {stats['median_turns']:.2f}")
    print()
    
    # 按越界类型统计
    print("【按越界类型统计】")
    sorted_breach_types = sorted(
        analysis['by_breach_type'].items(),
        key=lambda x: x[1]['total_tests'],
        reverse=True
    )
    for breach_type, stats in sorted_breach_types:
        print(f"\n  {breach_type}:")
        print(f"    越界次数: {stats['total_tests']}")
        print(f"    占所有越界比例: {stats['breach_rate']:.2%}")
        print(f"    平均轮数: {stats['avg_turns']:.2f}")
        print(f"    中位数轮数: {stats['median_turns']:.2f}")
        print(f"    轮数范围: {stats['min_turns']} - {stats['max_turns']}")
    print()
    
    # 按模型+语言统计
    print("【按模型+语言统计】")
    for key, stats in sorted(analysis['by_model_language'].items()):
        print(f"\n  {stats['model'].upper()} - {stats['language']}:")
        print(f"    测试总数: {stats['total_tests']}")
        print(f"    越界次数: {stats['breaches']}")
        print(f"    越界比例: {stats['breach_rate']:.2%}")
        print(f"    平均轮数: {stats['avg_turns']:.2f}")
        print(f"    中位数轮数: {stats['median_turns']:.2f}")
    print()
    
    # 轮数分析
    print("【轮数详细分析】")
    turns = analysis['turns_analysis']
    print(f"\n  所有案例:")
    print(f"    平均轮数: {turns['overall']['avg']:.2f}")
    print(f"    中位数轮数: {turns['overall']['median']:.2f}")
    print(f"    标准差: {turns['overall']['stdev']:.2f}")
    print(f"    范围: {turns['overall']['min']} - {turns['overall']['max']}")
    
    print(f"\n  越界案例:")
    print(f"    平均轮数: {turns['breach_cases']['avg']:.2f}")
    print(f"    中位数轮数: {turns['breach_cases']['median']:.2f}")
    print(f"    标准差: {turns['breach_cases']['stdev']:.2f}")
    print(f"    范围: {turns['breach_cases']['min']} - {turns['breach_cases']['max']}")
    
    print(f"\n  未越界案例:")
    print(f"    平均轮数: {turns['non_breach_cases']['avg']:.2f}")
    print(f"    中位数轮数: {turns['non_breach_cases']['median']:.2f}")
    print(f"    标准差: {turns['non_breach_cases']['stdev']:.2f}")
    print(f"    范围: {turns['non_breach_cases']['min']} - {turns['non_breach_cases']['max']}")
    print()
    
    # 按模型+病情分类（显示前10个）
    print("【按模型+病情分类统计（前10个）】")
    sorted_mp = sorted(
        analysis['by_model_phenotype'].items(),
        key=lambda x: x[1]['total_tests'],
        reverse=True
    )[:10]
    for key, stats in sorted_mp:
        print(f"\n  {stats['model'].upper()} - {stats['phenotype'][:60]}...:")
        print(f"    测试总数: {stats['total_tests']}")
        print(f"    越界次数: {stats['breaches']}")
        print(f"    越界比例: {stats['breach_rate']:.2%}")
        print(f"    平均轮数: {stats['avg_turns']:.2f}")
    print()
    
    print("=" * 80)

def main():
    base_dir = "experiment_results/run2/as=openai"
    
    print(f"正在加载结果文件从: {base_dir}")
    results = load_all_results(base_dir)
    print(f"成功加载 {len(results)} 个结果文件\n")
    
    print("正在分析数据...")
    analysis = analyze_results(results)
    
    print_analysis_report(analysis)
    
    # 保存JSON格式的分析结果
    output_file = "experiment_results/run2/as=openai/analysis_report.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print(f"\n详细分析结果已保存到: {output_file}")

if __name__ == "__main__":
    main()

