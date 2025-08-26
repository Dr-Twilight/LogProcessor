#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import glob
import csv
import re
import shutil
import io
import traceback
import pandas as pd
from itertools import islice

# ——— 全局配置区域 ———

if getattr(sys, 'frozen', False):
    # 打包后的EXE模式
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 脚本模式
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_DIR = os.path.join(BASE_DIR, 'logs')
# 添加内网和外网目录
INT_LOG_DIR = os.path.join(LOG_DIR, '内网')
EXT_LOG_DIR = os.path.join(LOG_DIR, '外网')

# 定义总输出文件
TOTAL_OUT = os.path.join(BASE_DIR, 'total_results.xlsx')

# 定义debug输出是否显示
enable_show_debug = 'n'  # 默认不显示debug输出


# ——— 公共工具函数 ———
def safe_open(file_path):
    """安全打开文件，尝试多种编码"""
    encodings = ['utf-8', 'gbk', 'latin-1']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                # 测试读取前100行
                for _ in range(100):
                    f.readline()
                # 如果成功，重新打开文件并返回
                return open(file_path, 'r', encoding=encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    # 所有编码都失败，使用二进制模式读取并尝试解码
    print(f"警告: 无法用标准编码解码文件 {file_path}，使用二进制模式读取")
    return open(file_path, 'rb')

def ensure_dirs():
    """确保所有必要的日志目录存在
    遍历需要创建的目录列表,使用os.makedirs创建目录
    exist_ok=True参数确保目录已存在时不会抛出异常
    """
    for d in (LOG_DIR, INT_LOG_DIR, EXT_LOG_DIR):
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

    with safe_open(fp) as f:
        # 如果是二进制模式，需要调整读取方式
        if isinstance(f, io.BufferedReader):
            # 处理二进制读取...
            pass  # 添加pass语句以避免语法错误
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
    """识别日志文件类型并直接调用解析函数
    遍历logs/内网和logs/外网目录中的.log文件
    识别每个文件的厂商类型,并直接调用相应的解析函数
    """
    print("🔍 分类识别日志...")
    # 存储所有日志信息
    all_logs = []
    # 存储所有光功率信息
    all_power_info = []

    # 处理内网日志
    for path in glob.glob(os.path.join(INT_LOG_DIR, '*.log')):
        dev_type = detect_type(path)
        if dev_type == 'H3C':
            logs = parse_h3c_logs(path, 'H3C', '内网')
            all_logs.extend(logs)
            # 提取光功率信息
            power_info = extract_power_info(path, 'H3C', '内网')
            all_power_info.extend(power_info)
        elif dev_type == 'Huawei':
            logs = parse_huawei_logs(path, 'Huawei', '内网')
            all_logs.extend(logs)
            # 提取光功率信息
            power_info = extract_power_info(path, 'Huawei', '内网')
            all_power_info.extend(power_info)
        else:
            print(f"⚠️ 跳过未知类型文件: {path}")

    # 处理外网日志
    for path in glob.glob(os.path.join(EXT_LOG_DIR, '*.log')):
        dev_type = detect_type(path)
        if dev_type == 'H3C':
            logs = parse_h3c_logs(path, 'H3C', '外网')
            all_logs.extend(logs)
            # 提取光功率信息
            power_info = extract_power_info(path, 'H3C', '外网')
            all_power_info.extend(power_info)
        elif dev_type == 'Huawei':
            logs = parse_huawei_logs(path, 'Huawei', '外网')
            all_logs.extend(logs)
            # 提取光功率信息
            power_info = extract_power_info(path, 'Huawei', '外网')
            all_power_info.extend(power_info)
        else:
            print(f"⚠️ 跳过未知类型文件: {path}")

    # 写入总结果文件
    write_total_results(all_logs)
    # 写入光功率结果到Excel
    write_power_results(all_power_info)
    print("✅ 日志识别与解析完成。")
    return all_logs


# ——— 华为日志解析部分 ———

# 正则表达式定义区 - 提取华为设备信息的关键模式
# 匹配设备名称模式,支持[]或<>包裹的SD-JN/JY开头的设备标识
BRACKET_RE = re.compile(r'[\[<](SD-(?:JN|JY)-[^\]>]+)[\]>]+', re.MULTILINE | re.IGNORECASE)
# 匹配设备名称（备用）
DEVICE_NAME_RE = re.compile(r'Device\s+Name\s*:\s*(\S+)', re.IGNORECASE)
SYSTEM_NAME_RE = re.compile(r'System\s+Name\s*:\s*(\S+)', re.IGNORECASE)
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


def parse_huawei_logs(fp, vendor, network_type):
    """解析华为设备日志
    参数:
        fp: 日志文件路径
        vendor: 厂商名称
        network_type: 网络类型(内网/外网)
    返回:
        list: 包含设备信息字典的列表
    """
    rows = []
    try:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            txt = f.read()

        clean_text = re.sub(r'\x1b\[\d+[A-Za-z]|[\x07\x08]', '', txt)
        device = None
        # 在 parse_huawei_logs 和 parse_h3c_logs 函数中使用
        # 修改设备名称提取逻辑
        m = BRACKET_RE.search(clean_text)
        if m:
            device = m.group(1)
        else:
            m = DEVICE_NAME_RE.search(clean_text)
            if m:
                device = m.group(1)
            else:
                m = SYSTEM_NAME_RE.search(clean_text)
                if m:
                    device = m.group(1)
                else:
                    device = os.path.basename(fp)
                    print(f"警告：未从{fp}中提取到设备名称,使用文件名代替")

        info = {
            'Vendor': vendor,
            'NetworkType': network_type,
            'Device': device,
            'SN': BARCODE_RE.search(txt).group(1) if BARCODE_RE.search(txt) else '',
            'TotalUsed(KB)': MEM_USED_RE.search(txt).group(1) if MEM_USED_RE.search(txt) else '',
            'UsedPct(%)': f"{float(MEM_PCT_RE.search(txt).group(1)):.2f}%" if MEM_PCT_RE.search(txt) else '',
            'CPU_Usage(%)': '',
            'CPU_Max(%)': '',
            'LogFileName': os.path.basename(fp)
        }

        m = CPU_CTRL_RE.search(txt) or CPU_SIMPLE_RE.search(txt)
        if m:
            info['CPU_Usage(%)'] = f"{float(m.group(1)):.2f}%" if m.group(1) else ''
            info['CPU_Max(%)'] = f"{float(m.group(2)):.2f}%" if m.group(2) else ''

        rows.append(info)
    except Exception as e:
        print(f"❌ Huawei 文件错误: {fp} - {e}")
    return rows


# ——— H3C 日志解析部分 ———

# 复用华为设备名称匹配正则
DEVNAME_RE = BRACKET_RE
# 匹配内存信息 (Mem: total used free)
MEM_RE = re.compile(r'Mem:\s*(\d+)\s*(\d+)\s*(\d+)')
# 匹配CPU使用率 (xx% in last yy seconds/minutes)
CPU_RE = re.compile(r'(\d+)% in last\s+(\d+)\s+(seconds?|minutes?)')
# 匹配设备序列号 (DEVICE_SERIAL_NUMBER : SNxxx)
SN_RE = re.compile(r'DEVICE_SERIAL_NUMBER\s*:\s*(\S+)')


def parse_h3c_logs(fp, vendor, network_type):
    """解析H3C设备日志
    参数:
        fp: 日志文件路径
        vendor: 厂商名称
        network_type: 网络类型(内网/外网)
    返回:
        list: 包含设备信息字典的列表
    """
    rows = []
    try:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.read().splitlines()
        clean_head = '\n'.join([re.sub(r'\x1b\[\d+[A-Za-z]|[\x07\x08]', '', ln) for ln in lines[:50]])
        m = DEVNAME_RE.search(clean_head)
        device = m.group(1) or m.group(2) if m else os.path.basename(fp)
        if not m:
            print(f"警告：未从{fp}中提取到设备名称，使用文件名代替")
        total_kb = used_kb = None
        cpu_stats = {}
        serial = ''
        for ln in lines:
            if mm := MEM_RE.search(ln):
                total_kb, used_kb = map(int, mm.groups()[:2])
            if mc := CPU_RE.search(ln):
                pct, num, unit = mc.groups()
                secs = int(num) * (60 if 'minute' in unit else 1)
                cpu_stats[secs] = int(pct)
            if ms := SN_RE.search(ln):
                serial = ms.group(1)
        used_pct = round(used_kb * 100 / total_kb, 2) if (used_kb and total_kb) else ''
        cpu_min = min(cpu_stats.values()) if cpu_stats else ''
        cpu_max = max(cpu_stats.values()) if cpu_stats else ''
        rows.append({
            'Vendor': vendor,
            'NetworkType': network_type,
            'Device': device,
            'SN': serial,
            'CPU_Usage(%)': f"{float(cpu_min):.2f}%" if cpu_min else '',
            'CPU_Max(%)': f"{float(cpu_max):.2f}%" if cpu_max else '',
            'TotalUsed(KB)': used_kb or '',
            'UsedPct(%)': f"{used_pct:.2f}%" if used_pct else '',
            'LogFileName': os.path.basename(fp)
        })
    except Exception as e:
        print(f"❌ H3C 文件错误: {fp} - {e}")
    return rows


def write_total_results(all_logs):
    """将所有日志信息写入总结果Excel文件的第一个表
    参数:
        all_logs: 包含所有设备信息字典的列表
    """
    if not all_logs:
        print("警告：没有可写入的数据")
        return

    try:
        # 创建DataFrame
        df = pd.DataFrame(all_logs)

        # 检查文件是否存在
        if os.path.exists(TOTAL_OUT):
            # 读取现有文件
            writer = pd.ExcelWriter(TOTAL_OUT, engine='openpyxl', mode='a', if_sheet_exists='replace')
        else:
            # 创建新文件
            writer = pd.ExcelWriter(TOTAL_OUT, engine='openpyxl')

        # 写入第一个表(巡检数据表)
        df.to_excel(writer, sheet_name='巡检数据', index=False, columns=[
            'Vendor', 'NetworkType', 'Device', 'SN', 'CPU_Usage(%)',
            'CPU_Max(%)', 'TotalUsed(KB)', 'UsedPct(%)', 'LogFileName'
        ])
        writer.close()

        print(f"✅ 总结果已写入 {TOTAL_OUT} 的巡检数据表, 共处理 {len(all_logs)} 条记录。")
    except Exception as e:
        print(f"❌ 写入总结果错误: {e}")


# ——— 光功率信息提取 ———
# 非光口（Valid only on/for optical interface）
NON_OPTICAL_RE = re.compile(
    r'valid\s+only\s+(?:on|for)\s+optical\s+interface\.?', re.IGNORECASE
)

# 无模块（transceiver is absent / absent.）
ABSENT_RE = re.compile(
    r'transceiver\s+(?:is\s+)?absent\.?', re.IGNORECASE
)

# 不支持（does not support / not supported / unsupported）
NOT_SUPPORT_RE = re.compile(
    r'transceiver\s+(?:does\s+not\s+support|not\s+supported|unsupported)', re.IGNORECASE
)

# 铜缆接口（Transfer Distance(m) : xxx(copper) 或 (copper)）
TRANSFER_DISTANCE_COPPER_RE = re.compile(
    r'Transfer\s+Distance\(m\)\s*:\s*(?:\d+\s*)?\(\s*copper\s*\)', re.IGNORECASE
)

# 端口名称（兼容 Huawei/H3C，多类型接口名）
PORT_RE = re.compile(
    r'(?:^|\s)(?:Port\s+|interface\s+)?'
    r'([A-Za-z\-]+(?:Ethernet)?\d+(?:[\/\-]\d+)+[A-Za-z0-9\/\-]*)',
    re.IGNORECASE
)

# TX/RX Power 通用匹配（兼容 TxPower / RxPower，允许前面有 Current）
TX_POWER_RE = re.compile(
    r'(?:Current\s+)?(?:TX\s*Power|TxPower)(?:\s*\(dB[mM]\))?\s*[:=]?\s*(-?\d+(?:\.\d+)?)',
    re.IGNORECASE
)
RX_POWER_RE = re.compile(
    r'(?:Current\s+)?(?:RX\s*Power|RxPower)(?:\s*\(dB[mM]\))?\s*[:=]?\s*(-?\d+(?:\.\d+)?)',
    re.IGNORECASE
)

# H3C 表格格式光功率匹配(兼容 TxPower / RxPower)
H3C_TABLE_TX_RE = re.compile(
    r'TX\s*power\s*\(dB[mM]\)\s*(-?\d+(?:\.\d+)?)',
    re.IGNORECASE
)
H3C_TABLE_RX_RE = re.compile(
    r'RX\s*power\s*\(dB[mM]\)\s*(-?\d+(?:\.\d+)?)',
    re.IGNORECASE
)

# 备用光功率值匹配（极端场景）
POWER_VALUE_RE = re.compile(
    r'(TX|RX|Tx|Rx)\s*Power\s*[:=]?\s*(-?\d+(?:\.\d+)?)',
    re.IGNORECASE
)

# 光功率命令匹配（Huawei / H3C）

#display transceiver diagnosis interface
HUAWEI_DIAG_CMD_RE = re.compile(
    r'display\s+transceiver\s+diagnosis\s+interface\b', re.IGNORECASE
)
#display transceiver diagnosis interface detail
HUAWEI_DIAG_DETAIL_CMD_RE = re.compile(
    r'display\s+transceiver\s+diagnosis\s+interface\s+detail\b', re.IGNORECASE
)
#display transceiver verbose
HUAWEI_VERB_CMD_RE = re.compile(
    r'display\s+transceiver\s+verbose\b', re.IGNORECASE
)
#display transceiver diagnosis interface
H3C_DIAG_CMD_RE = re.compile(
    r'display\s+transceiver\s+diagnosis\s+interface\b', re.IGNORECASE
)
#display transceiver verbose
H3C_VERB_CMD_RE = re.compile(
    r'display\s+transceiver\s+verbose\b', re.IGNORECASE
)

# 通用光功率命令集合
#display transceiver diagnosis interface
#display transceiver diagnosis interface detail
#display transceiver verbose
ALL_TRANSCEIVER_CMD_RE = re.compile(
    r'(?:display\s+transceiver\s+(?:diagnosis\s+interface(?:\s+detail)?|verbose)|undo\s+screen-length\s+disable)',
    re.IGNORECASE
)
# H3C 多行表格头匹配
#Current diagnostic parameters:
RE_CURRENT_DIAG = re.compile(r'^Current diagnostic parameters:', re.IGNORECASE)
#Alarm thresholds:
RE_ALARM_THRESHOLDS = re.compile(r'^Alarm thresholds:', re.IGNORECASE)


# 提取光功率信息
def extract_power_info(fp, vendor, network_type):
    """提取设备光功率信息（优化版，支持设备名提取 & 非光口过滤 & 电口跳过）"""
    power_info = []
    try:
        with safe_open(fp) as f:
            lines = f.read().splitlines()
            if enable_show_debug == 'y':
                print(f"[DEBUG] 打开文件 {fp}，读取行数: {len(lines)}")

        # === 1. 全文设备名提取 ===
        clean_text = '\n'.join(re.sub(r'\x1b\[\d+[A-Za-z]|[\x07\x08]', '', ln) for ln in lines)
        m = re.search(r'[\[<]([\w\-]+)[\]>]', clean_text)  # 优先匹配提示符
        if not m:#复用huawei的设备名称提取
            m = BRACKET_RE.search(clean_text)
        if not m:
            DEVICE_NAME_RE = re.compile(r'Device\s+Name\s*:\s*(\S+)', re.IGNORECASE)
            SYSTEM_NAME_RE = re.compile(r'System\s+Name\s*:\s*(\S+)', re.IGNORECASE)
            m = DEVICE_NAME_RE.search(clean_text) or SYSTEM_NAME_RE.search(clean_text)
        device = m.group(1) if m else os.path.basename(fp)
        if enable_show_debug == 'y':
            print(f"[DEBUG] 识别设备名: {device}")

        # === 2. 找所有光功率命令行索引，构成分段 ===
        cmd_indices = [i for i, line in enumerate(lines) if ALL_TRANSCEIVER_CMD_RE.search(line)]
        if not cmd_indices:
            if enable_show_debug == 'y':
                print(f"[DEBUG] 警告：设备 {device} 在{fp}中未找到光功率相关命令")
            return []
        cmd_indices.append(len(lines))  # 加日志末尾作为边界
        if enable_show_debug == 'y':
            print(f"[DEBUG] 设备 {device} 识别到光功率命令段数: {len(cmd_indices)-1}")

        # 逐段处理
        for idx, (start, end) in enumerate(zip(cmd_indices, cmd_indices[1:]), 1):  # 从1开始计数
            segment = lines[start:end]
            if enable_show_debug == 'y':
                print(f"[DEBUG] 设备 {device} 处理第 {idx} 段日志，行数: {len(segment)}，起始行号: {start}")


            # === 3. 状态机解析 ===
            current_port = None  # 当前正在处理的端口名称
            tx_power = None     # 发送功率值 (dBm)
            rx_power = None     # 接收功率值 (dBm)
            status = 'unknown'  # 端口状态 (unknown/non_optical/absent/not_supported/copper_port)
            is_optical_port = False  # 是否为光口
            command_type = "unknown"  # 命令类型 (huawei_diag/huawei_diag_detail/huawei_verb/h3c_diag/h3c_verb)
            # 针对多列表格的解析状态和列索引变量
            table_header_found = False  # 是否已找到表格头部
            rx_power_col_idx = None     # 接收功率在表格中的列索引
            tx_power_col_idx = None     # 发送功率在表格中的列索引

            # 保存当前端口信息
            def save_port():
                nonlocal current_port, tx_power, rx_power, status, is_optical_port,table_header_found, rx_power_col_idx, tx_power_col_idx, parsing_power_data,command_type
                if current_port and (tx_power is not None or rx_power is not None or status != 'unknown'):
                    power_info.append({
                        'Vendor': vendor,
                        'NetworkType': network_type,
                        'Device': device,
                        'Port': current_port,
                        'TX_Power(dBm)': tx_power,
                        'RX_Power(dBm)': rx_power,
                        'Status': status,
                        'CommandType': command_type,
                        'LogFileName': os.path.basename(fp)
                    })
                    if enable_show_debug == 'y':
                        print(f"[DEBUG] 保存设备 {device} 端口: {current_port}，TX: {tx_power}，RX: {rx_power}，状态: {status}，命令类型: {command_type}")

                # 保存后重置端口信息，防止数据混淆
                current_port = None
                tx_power = None
                rx_power = None
                status = 'unknown'
                is_optical_port = False
                command_type = "unknown"
                # 重置表格相关变量，防止跨端口干扰
                table_header_found = False
                rx_power_col_idx = None
                tx_power_col_idx = None
                parsing_power_data = False
                table_header_found = False

            for line in segment:
                line = line.strip()
                # 识别命令类型
                if vendor == 'Huawei':
                    if HUAWEI_DIAG_CMD_RE.search(line):
                        command_type = "huawei_diag"
                    elif HUAWEI_DIAG_DETAIL_CMD_RE.search(line):
                        command_type = "huawei_diag_detail"
                    elif HUAWEI_VERB_CMD_RE.search(line):
                        command_type = "huawei_verb"
                elif vendor == 'H3C':
                    if H3C_DIAG_CMD_RE.search(line):
                        command_type = "h3c_diag"
                    elif H3C_VERB_CMD_RE.search(line):
                        command_type = "h3c_verb"

                # 匹配端口
                port_match = PORT_RE.search(line)
                if port_match:
                    save_port()
                    current_port = port_match.group(1)
                    is_optical_port = True
                    status = 'unknown'
                    if enable_show_debug == 'y':
                        print(f"[DEBUG] 发现设备{device}端口: {current_port}，默认光口，命令类型: {command_type}")
                    continue

                # 非光口 / 无模块 / 不支持 / 电口 状态判断及标记状态
                if NON_OPTICAL_RE.search(line):
                    status = 'non_optical(非光口)'
                    is_optical_port = False
                    if enable_show_debug == 'y':
                        print(f"[DEBUG] 设备 {device} 端口{current_port}检测为非光口")
                    continue
                if ABSENT_RE.search(line):
                    status = 'absent(无模块)'
                    is_optical_port = False
                    if enable_show_debug == 'y':
                        print(f"[DEBUG] 设备 {device} 端口{current_port}检测为无模块")
                    continue
                if NOT_SUPPORT_RE.search(line):
                    status = 'not_supported(不支持)'
                    is_optical_port = False
                    if enable_show_debug == 'y':
                        print(f"[DEBUG] 设备 {device} 端口{current_port}检测为不支持")
                    continue
                if current_port is not None and TRANSFER_DISTANCE_COPPER_RE.search(line):
                    status = 'copper_port(电口)'
                    is_optical_port = False
                    if enable_show_debug == 'y':
                        print(f"[DEBUG] 设备 {device} 端口{current_port}检测为电口")
                    continue

                # 非光口跳过
                if not is_optical_port:
                    continue

                # 控制诊断数据区块开关
                if vendor in ('H3C', 'Huawei') and RE_CURRENT_DIAG.search(line):
                    parsing_power_data = True
                    continue
                # 控制告警阈值区块开关
                if vendor in ('H3C', 'Huawei') and RE_ALARM_THRESHOLDS.search(line):
                    parsing_power_data = False
                    table_header_found = False  # 遇到告警阈值段，重置表头标志
                    continue
                # 多列表格头检测
                if vendor in ('H3C', 'Huawei') and 'Temp.' in line and 'Voltage' in line and 'RX power' in line and 'TX power' in line:
                    table_header_found = True
                    headers = re.split(r'\s{2,}', line.strip())
                    try:
                        rx_power_col_idx = next(i for i, h in enumerate(headers) if 'RX power' in h)
                        tx_power_col_idx = next(i for i, h in enumerate(headers) if 'TX power' in h)
                        if enable_show_debug == 'y':
                            print(f"[DEBUG] 设备 {device} 多列表格检测到功率列 RX: {rx_power_col_idx}, TX: {tx_power_col_idx}")

                    except StopIteration:
                        rx_power_col_idx = None
                        tx_power_col_idx = None
                        if enable_show_debug == 'y':
                            print(f"[DEBUG] 设备 {device} 多列表格未检测到功率列")
                    continue

                # 紧跟表头后的数据行，解析功率
                if table_header_found:
                    columns = re.split(r'\s{2,}', line.strip())
                    if rx_power_col_idx is not None and rx_power_col_idx < len(columns):
                        try:
                            val = float(columns[rx_power_col_idx])
                            if -50 <= val <= 10:
                                rx_power = val
                                if enable_show_debug == 'y':
                                    print(f"[DEBUG] 设备 {device} 端口{current_port} 多列表格 RX功率: {rx_power} dBm")
                        except Exception as e:
                            if enable_show_debug == 'y':
                                print(f"[WARN] 设备 {device} 端口{current_port} 多列表格 RX功率解析错误: {e}")
                    if tx_power_col_idx is not None and tx_power_col_idx < len(columns):
                        try:
                            val = float(columns[tx_power_col_idx])
                            if -50 <= val <= 10:
                                tx_power = val
                                if enable_show_debug == 'y':
                                    print(f"[DEBUG] 设备 {device} 端口{current_port} 多列表格 TX功率: {tx_power} dBm")
                        except Exception as e:
                            if enable_show_debug == 'y':
                                print(f"[WARN] 设备 {device} 端口{current_port} 多列表格 TX功率解析错误: {e}")
                    table_header_found = False  # 只处理一行数据
                    continue

                # 匹配TX功率
                tx_match = TX_POWER_RE.search(line)
                if tx_match:
                    try:
                        val = float(tx_match.group(1))
                        if -50 <= val <= 10:  # 合理范围内才赋值
                            tx_power = val
                            if enable_show_debug == 'y':
                                print(f"[DEBUG] 设备 {device} 端口{current_port} TX功率: {val} dBm")
                    except ValueError:
                        if enable_show_debug == 'y':
                            print(f"[DEBUG] 设备 {device} 端口{current_port} TX功率解析错误: {tx_match.group(1)}")
                        pass

                # 匹配RX功率
                rx_match = RX_POWER_RE.search(line)
                if rx_match:
                    try:
                        val = float(rx_match.group(1))
                        if -50 <= val <= 10:
                            rx_power = val
                            if enable_show_debug == 'y':
                                print(f"[DEBUG] 设备 {device} 端口{current_port} RX功率: {val} dBm")
                    except ValueError:
                        if enable_show_debug == 'y':
                            print(f"[DEBUG] 设备 {device} 端口{current_port} RX功率解析错误: {rx_match.group(1)}")
                        pass

                # H3C表格格式匹配
                if vendor == 'H3C':
                    h3c_tx_match = H3C_TABLE_TX_RE.search(line)
                    if h3c_tx_match:
                        try:
                            val = float(h3c_tx_match.group(1))
                            if -50 <= val <= 10:
                                tx_power = val
                                if enable_show_debug == 'y':
                                    print(f"[DEBUG] 设备 {device} 端口{current_port} H3C TX功率: {val} dBm")
                        except ValueError:
                            if enable_show_debug == 'y':
                                print(f"[DEBUG] 设备 {device} 端口{current_port} H3C TX功率解析错误: {h3c_tx_match.group(1)}")
                            pass

                    h3c_rx_match = H3C_TABLE_RX_RE.search(line)
                    if h3c_rx_match:
                        try:
                            val = float(h3c_rx_match.group(1))
                            if -50 <= val <= 10:
                                rx_power = val
                                if enable_show_debug == 'y':
                                    print(f"[DEBUG] 设备 {device} 端口{current_port} H3C RX功率: {val} dBm")
                        except ValueError:
                            if enable_show_debug == 'y':
                                print(f"[DEBUG] 设备 {device} 端口{current_port} H3C RX功率解析错误: {h3c_rx_match.group(1)}")
                            pass

                # 备用功率匹配
                if tx_power is None:
                    pm = POWER_VALUE_RE.search(line)
                    if pm and pm.group(1).lower() == 'tx':
                        try:
                            val = float(pm.group(2))
                            if -50 <= val <= 10:
                                tx_power = val
                                if enable_show_debug == 'y':
                                    print(f"[DEBUG] 设备 {device} 端口{current_port} 备用TX功率: {val} dBm")
                        except ValueError:
                            if enable_show_debug == 'y':
                                print(f"[DEBUG] 设备 {device} 端口{current_port} 备用TX功率解析错误: {pm.group(2)}")
                            pass

                if rx_power is None:
                    pm = POWER_VALUE_RE.search(line)
                    if pm and pm.group(1).lower() == 'rx':
                        try:
                            val = float(pm.group(2))
                            if -50 <= val <= 10:
                                rx_power = val
                                if enable_show_debug == 'y':
                                    print(f"[DEBUG] 设备 {device} 端口{current_port} 备用RX功率: {val} dBm")
                        except ValueError:
                            if enable_show_debug == 'y':
                                print(f"[DEBUG] 设备 {device} 端口{current_port} 备用RX功率解析错误: {pm.group(2)}")
                            pass

                # 匹配状态 normal/abnormal
                status_match = re.search(r'status\s+(normal|abnormal)', line, re.IGNORECASE)
                if status_match:
                    status = status_match.group(1)
                    if enable_show_debug == 'y':
                        print(f"[DEBUG] 设备 {device} 端口{current_port} 状态: {status}")

            # 循环结束保存最后一个端口
            save_port()
    except Exception as e:
        print(f"❌ 光功率提取错误: {fp} - {e}")
        print(traceback.format_exc())

    return power_info


def write_power_results(power_info):
    """将光功率信息写入Excel文件的sheet2
    参数:
        power_info: 包含所有光功率信息字典的列表
    """
    if not power_info:
        print("❌警告：没有可写入的光功率数据")
        return

    try:
        # 创建DataFrame
        df = pd.DataFrame(power_info)

        # 检查文件是否存在
        if os.path.exists(TOTAL_OUT):
            # 读取现有文件
            writer = pd.ExcelWriter(TOTAL_OUT, engine='openpyxl', mode='a', if_sheet_exists='replace')
        else:
            # 创建新文件
            writer = pd.ExcelWriter(TOTAL_OUT, engine='openpyxl')

        # 写入光功率
        df.to_excel(writer, sheet_name='光功率', index=False)
        writer.close()

        print(f"✅ 光功率信息已写入 {TOTAL_OUT} 的光功率表, 共处理 {len(power_info)} 条记录。")
    except Exception as e:
        print(f"❌ 写入光功率信息错误: {e}")
        # 添加详细的异常堆栈信息以方便调试
        import traceback
        print(f"错误堆栈:\n{traceback.format_exc()}")


def main():
    try:
        ensure_dirs()
        classify_logs()
        print("🎉 所有巡检日志处理完成。")
        input("按任意键退出...")
    except Exception as e:
        print(f"❌ 程序执行出错: {e}")
        input("按任意键退出...")


if __name__ == '__main__':
    # 获取用户输入，是否显示debug命令输出（默认不显示）
    enable_show_debug = input("是否显示debug命令输出？(y/n, 默认n): ").strip().lower() or 'n'
    main()
