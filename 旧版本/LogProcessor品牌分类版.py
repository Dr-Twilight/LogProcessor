#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#该版本是输出不同厂商分类的csv文件

import os
import sys
import glob
import csv
import re
import shutil
from itertools import islice

# ——— 全局配置区域 ———

if getattr(sys, 'frozen', False):
    # 打包后的EXE模式
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 脚本模式
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_DIR = os.path.join(BASE_DIR, 'logs')
H3C_LOG_DIR = os.path.join(LOG_DIR, 'h3c_logs')
HW_LOG_DIR = os.path.join(LOG_DIR, 'huawei_logs')
H3C_OUT = os.path.join(BASE_DIR, 'h3c_results.csv')
HW_OUT = os.path.join(BASE_DIR, 'huawei_results.csv')

# ——— 公共工具函数 ———


def ensure_dirs():
    """确保所有必要的日志目录存在
    遍历需要创建的目录列表,使用os.makedirs创建目录
    exist_ok=True参数确保目录已存在时不会抛出异常
    """
    for d in (LOG_DIR, H3C_LOG_DIR, HW_LOG_DIR):  # 添加LOG_DIR
        os.makedirs(d, exist_ok=True)


def detect_type(fp):
    """识别日志文件类型(H3C / Huawei)
    采用分批读取策略,避免一次性加载大文件到内存
    每次读取batch_size行,直到找到匹配类型或文件结束

    参数:
        fp: 日志文件路径
    返回:
        str: 'Huawei'、'H3C'或None(未知类型)
    """
    batch_size = 100  # 每次检查100行,平衡性能和准确性
    with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
        while True:
            # 读取当前批次的行并转换为小写,统一匹配规则
            lines = [line.lower() for line in islice(f, batch_size)]
            if not lines:
                break  # 文件读取完毕,未找到匹配类型

            # 检查当前批次的行是否包含特征关键字
            for line in lines:
                if 'huawei' in line:
                    return 'Huawei'
                if 'h3c' in line or 'new h3c technologies' in line:
                    return 'H3C'
    return None


def classify_logs():
    """将日志文件分类移动到对应厂商的子目录
    遍历LOG_DIR中的.log文件,调用detect_type识别类型
    根据识别结果移动到H3C_LOG_DIR或HW_LOG_DIR
    已存在文件会跳过移动并给出警告
    """
    print("🔍 分类整理日志...")
    # 仅处理.log文件,可根据需要扩展支持其他格式
    for path in glob.glob(os.path.join(LOG_DIR, '*.log')):
        dev = detect_type(path)
        if dev == 'H3C':
            # 添加文件存在性检查,避免覆盖已有文件
            dest_path = os.path.join(H3C_LOG_DIR, os.path.basename(path))
            if os.path.exists(dest_path):
                print(f"⚠️ {dest_path}已存在,跳过移动")
            else:
                shutil.move(path, dest_path)
        elif dev == 'Huawei':
            shutil.move(path, os.path.join(HW_LOG_DIR, os.path.basename(path)))
        else:
            print(f"⚠️ 跳过未知类型文件: {path}")
    print("✅ 分类完成。")


# ——— 华为日志解析部分 ———

# 正则表达式定义区 - 提取华为设备信息的关键模式
# 匹配设备名称模式,支持[]或<>包裹的SD-JN/JY开头的设备标识
BRACKET_RE = re.compile(
    r'\[(SD-(?:JN|JY)-[^\]]+)\]|<(SD-(?:JN|JY)-[^>]+)>', re.MULTILINE)
# 匹配条形码信息,提取BarCode=后的非空白字符
BARCODE_RE = re.compile(r'BarCode=(\S+)')
# 匹配简单CPU使用率格式 (CPU Usage : x% Max : y%)
CPU_SIMPLE_RE = re.compile(
    r'CPU Usage\s*:\s*([\d\.]+)%\s*Max\s*:\s*([\d\.]+)%')
# 匹配控制平面CPU使用率格式 (Control Plane ... CPU Usage: x% Max: y%)
CPU_CTRL_RE = re.compile(
    r'Control Plane[\s\S]*?CPU Usage:\s*([\d\.]+)%\s*Max:\s*([\d\.]+)%')
# 匹配内存使用量 (Total Memory Used Is: x bytes)
MEM_USED_RE = re.compile(r'Total Memory Used Is:\s*(\d+)\s*bytes')
# 匹配内存使用率 (Memory Using Percentage Is: x%)
MEM_PCT_RE = re.compile(r'Memory Using Percentage Is:\s*([\d\.]+)%')


def parse_huawei_logs():
    """解析华为设备日志并生成CSV报告
    1. 检查日志目录是否存在及包含日志文件
    2. 遍历日志文件,提取设备信息、硬件指标
    3. 处理异常情况并记录错误
    4. 将提取结果写入CSV文件

    返回:
        list: 包含所有设备信息字典的列表
    """
    rows = []
    # 目录检查 - 确保日志目录存在
    if not os.path.exists(HW_LOG_DIR):
        print(f"错误：华为日志目录{HW_LOG_DIR}不存在")
        return []
    # 获取所有.log文件 - 可扩展支持其他格式
    log_files = glob.glob(os.path.join(HW_LOG_DIR, '*.log'))
    if not log_files:
        print(f"警告：在{HW_LOG_DIR}未找到任何.log文件")
        return []

    # 遍历处理每个日志文件
    for fp in log_files:
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                txt = f.read()  # 读取整个文件内容

            # 清理文本 - 移除ANSI控制字符和特殊字符
            clean_text = re.sub(r'\x1b\[\d+[A-Za-z]|[\x07\x08]', '', txt)
            device = None
            # 提取设备名称 - 优先从文本中匹配设备标识
            m = BRACKET_RE.search(clean_text)
            if m:
                device = m.group(1) or m.group(2)  # 处理两种可能的捕获组
            # 设备名称提取失败时使用文件名作为回退
            if not device:
                device = os.path.basename(fp)
                print(f"警告：未从{fp}中提取到设备名称,使用文件名代替")

            # 提取硬件信息 - 构建信息字典
            # 每个字段使用条件表达式处理匹配失败的情况
            info = {
                'SN': BARCODE_RE.search(txt).group(1) if BARCODE_RE.search(txt) else '',
                'TotalUsed(bytes)': MEM_USED_RE.search(txt).group(1) if MEM_USED_RE.search(txt) else '',
                'UsedPct(%)': f"{float(MEM_PCT_RE.search(txt).group(1)):.2f}%" if MEM_PCT_RE.search(txt) else '',
                'CPU_Usage(%)': '',  # 初始化为空,后续填充
                'CPU_Max(%)': '',     # 初始化为空,后续填充
                'LogFileName': os.path.basename(fp)
            }

            # 提取CPU信息 - 优先匹配控制平面CPU,再尝试简单格式
            m = CPU_CTRL_RE.search(txt) or CPU_SIMPLE_RE.search(txt)
            if m:
                info['CPU_Usage(%)'] = f"{float(m.group(1)):.2f}%" if m.group(
                    1) else ''
                info['CPU_Max(%)'] = f"{float(m.group(2)):.2f}%" if m.group(
                    2) else ''

            # 添加设备名称并收集结果
            info['Device'] = device
            rows.append(info)
        except Exception as e:
            # 捕获并记录处理单个文件时的异常
            print(f"❌ Huawei 文件错误: {fp} - {e}")

    # 写入CSV报告 - 使用utf-8编码确保中文正常显示
    with open(HW_OUT, 'w', newline='', encoding='utf-8') as f:
        # 定义CSV字段顺序
        writer = csv.DictWriter(f, fieldnames=[
                                'Device', 'SN', 'CPU_Usage(%)', 'CPU_Max(%)', 'TotalUsed(bytes)', 'UsedPct(%)', 'LogFileName'])
        writer.writeheader()  # 写入表头
        writer.writerows(rows)  # 写入所有数据行
    print(f"✅ Huawei 日志解析完成,共处理 {len(rows)} 个文件。")


# ——— H3C 日志解析部分 ———
# 匹配内存信息 (Mem: total used free)
MEM_RE = re.compile(r'Mem:\s*(\d+)\s*(\d+)\s*(\d+)')
# 匹配CPU使用率 (xx% in last yy seconds/minutes)
CPU_RE = re.compile(r'(\d+)% in last\s+(\d+)\s+(seconds?|minutes?)')
# 匹配设备序列号 (DEVICE_SERIAL_NUMBER : SNxxx)
SN_RE = re.compile(r'DEVICE_SERIAL_NUMBER\s*:\s*(\S+)')
# 复用华为设备名称匹配正则
DEVNAME_RE = BRACKET_RE


def parse_h3c_logs():
    """解析H3C设备日志并生成CSV报告
    1. 检查日志目录是否存在及包含日志文件
    2. 遍历日志文件，提取设备信息、CPU和内存指标
    3. 计算CPU使用率的最小值和最大值
    4. 计算内存使用率百分比
    5. 将提取结果写入CSV文件

    返回:
        list: 包含所有设备信息字典的列表
    """
    rows = []
    # 添加目录检查
    if not os.path.exists(H3C_LOG_DIR):
        print(f"错误：H3C日志目录{H3C_LOG_DIR}不存在")
        return []
    log_files = glob.glob(os.path.join(H3C_LOG_DIR, '*.log'))
    # 添加文件存在检查
    if not log_files:
        print(f"警告：在{H3C_LOG_DIR}未找到任何.log文件")
        return []
    for fp in log_files:
        try:
            # 使用with上下文管理器安全打开文件
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.read().splitlines()
            clean_head = '\n'.join(
                [re.sub(r'\x1b\[\d+[A-Za-z]|[\x07\x08]', '', ln) for ln in lines[:50]])
            m = DEVNAME_RE.search(clean_head)
            device = m.group(1) or m.group(2) if m else os.path.basename(fp)
            # 添加提取失败警告
            if not m:
                print(f"警告：未从{fp}中提取到设备名称，使用文件名代替")
            total_kb = used_kb = None
            cpu_stats = {}  # 初始化CPU统计字典
            serial = ''     # 初始化序列号
            for ln in lines:
                if mm := MEM_RE.search(ln):
                    total_kb, used_kb = map(int, mm.groups()[:2])
                if mc := CPU_RE.search(ln):
                    pct, num, unit = mc.groups()
                    secs = int(num) * (60 if 'minute' in unit else 1)
                    cpu_stats[secs] = int(pct)
                if ms := SN_RE.search(ln):
                    serial = ms.group(1)
            # 计算内存使用率百分比并保留两位小数
            used_pct = round(used_kb * 100 / total_kb,
                            2) if (used_kb and total_kb) else ''
            # 提取CPU使用率统计值
            cpu_min = min(cpu_stats.values()) if cpu_stats else ''
            cpu_max = max(cpu_stats.values()) if cpu_stats else ''
            rows.append({
                'Device': device,
                'SN': serial,
                'CPU_Usage(%)': f"{float(cpu_min):.2f}%" if cpu_min else '',
                'CPU_Max(%)': f"{float(cpu_max):.2f}%" if cpu_max else '',
                'TotalUsed(bytes)': used_kb or '',
                'UsedPct(%)': f"{used_pct:.2f}%" if used_pct else '',
                'LogFileName': os.path.basename(fp)
            })
        except Exception as e:
            print(f"❌ H3C 文件错误: {fp} - {e}")
    with open(H3C_OUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
                                'Device', 'SN', 'CPU_Usage(%)', 'CPU_Max(%)', 'TotalUsed(bytes)', 'UsedPct(%)', 'LogFileName'])
        writer.writeheader()
        writer.writerows(rows)
    print(f"✅ H3C 日志解析完成,共处理 {len(rows)} 个文件。")

# ——— 主函数 ———


def main():
    ensure_dirs()
    classify_logs()
    parse_huawei_logs()
    parse_h3c_logs()
    print("🎉 所有巡检日志处理完成。")
    input("按任意键退出...")


if __name__ == '__main__':
    main()
