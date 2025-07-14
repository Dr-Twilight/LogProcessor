# 网络设备日志解析工具

## 项目概述
本项目是一个用于解析华为(Huawei)和H3C网络设备巡检日志的Python工具，能够自动分类日志文件、提取关键硬件指标（CPU使用率、内存使用率等）并生成格式化的CSV报告。

## 功能特点
- **自动日志分类**：根据日志特征自动识别设备品牌并分类存放
- **硬件指标解析**：提取CPU使用率、内存使用率等关键性能指标
- **数据格式化**：将解析结果输出为标准CSV格式报告
- **错误处理**：具备完善的异常处理和日志提示功能
- **跨环境支持**：提供Python脚本和Windows可执行文件两种运行方式

## 安装说明
### 环境要求
- Python 3.6+ 或直接使用打包好的可执行文件
- 依赖库：无额外依赖 (详见requirements.txt)

### 源码安装
1. 克隆或下载项目到本地
2. 安装依赖包：
```bash
pip install -r requirements.txt
```
### 打包命令
🧵 打包为 EXE（可选） 请确保使用 Python 3.8–3.11 环境，执行命令：
```python
pyinstaller --clean -F --name "LogProcessor" LogProcessor.py
```

## 使用方法
### 方法一：使用Python脚本
```bash
python LogProcessor.py
```

### 方法二：使用可执行文件
直接双击运行 `LogProcessor.exe`

### 操作步骤
1. 将待解析的日志文件(.log)放入项目根目录下的`logs`文件夹
2. 运行程序，系统会自动分类日志并生成报告
3. 解析结果将保存为：
   - `huawei_results.csv` (华为设备)
   - `h3c_results.csv` (H3C设备)

## 项目结构
```
XunJian/
├── LogProcessor.exe           # 可执行文件
├── LogProcessor.py            # 主程序源码
├── logs/                      # 日志文件目录
│   ├── huawei_logs/           # 自动分类后的华为日志分类目录
│   └── h3c_logs/              # 自动分类后的H3C日志分类目录
├── packet_LogProcessor.bat    # 打包脚本
└──  requirements.txt           # 依赖库列表
```

## 注意事项
- 确保日志文件格式符合华为/H3C设备标准输出格式
- 程序会自动创建所需的目录结构，无需手动创建
- 解析结果将覆盖同名CSV文件，请及时备份重要数据
- 如遇编码问题，请确保日志文件为UTF-8编码

## 常见问题
**Q: 运行程序后没有生成CSV文件？**
A: 请检查logs目录下是否有日志文件，或日志文件格式是否正确。

**Q: 中文显示乱码怎么办？**
A: 确保使用UTF-8编码打开CSV文件，建议使用Excel或Notepad++打开。
        
