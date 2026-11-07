# 从 Leo 打开墨笺

**简体中文** | [English](README.en.md)

[Leo 桌面伙伴项目](https://github.com/LeoLi006/leo-desktop) · [墨笺项目](https://github.com/LeoLi006/handwriting-tool)

这是 Leo 现有本机应用模块的接入，不把转换引擎塞进桌宠进程。点击 Leo 的墨笺快捷按钮，或搜索 `墨笺`、`手写`、`mojian`、`shouxie`、`handwriting`，打开墨笺 GUI；文档、字体、预览与转换仍在墨笺自己的窗口本地处理。没有新增模型 API 或常驻转换任务。

## 自动接入本机

先完整解压并正常启动过墨笺与 Leo。Leo 的数据模块契约要求 1.04.x～1.x（目前按源码中的协议格式验证，未承诺所有历史发行版都完成实测）。使用带 Python 3.10+ 的终端，在手写工具目录运行：

```powershell
python integrations/leo/install.py --leo-dir "你的Leo安装目录" --dry-run
python integrations/leo/install.py --leo-dir "你的Leo安装目录"
```

解压即用版可将 `python` 换为 `runtime\python.exe`。`--leo-dir` 指向同时包含 `LeoLauncher.exe` 和 `leo-settings.json` 的目录，**不是源码目录**。两款工具都不能直接留在 ZIP 内使用。

接入时会尝试正常关闭指定目录的 Leo，读取最新配置，生成本机专用 `.leo-local/Mojian.lnk`，原子写入应用模块配置后启动 Leo。原配置私有备份在 Leo 的 `backups/mojian-integration/`，包含个人配置，不要分享。无法正常退出 Leo 时会停止接入，请手动退出后重试，不强杀其他实例。保存失败保留原配置，并尝试恢复原本运行的 Leo。

重复执行不会重复添加入口；保留已有自定义名称、图标、停用与入口显示选择，更新本机路径。两款工具的文件夹移动后请重跑接入脚本。它只配置本机程序，不下载依赖、更新 Leo 或把个人配置提交到 GitHub。墨笺首次启动所需依赖仍按它原有启动器处理。

## 手动接入 / 模块包

不想让脚本修改 Leo 配置时：

1. 在 Windows 中为墨笺的 `启动GUI.vbs` 创建快捷方式 `.lnk`。
2. Leo → 设置 → 功能 → 应用模块 → 新建应用，选择该 `.lnk`，名称填“墨笺·手写转换”，图标可选“便签”或“图片”。保存应用和 Leo 设置。
3. 或在应用模块窗口导入本目录的 `mojian.leoapp.json`，在预览中选择刚建立的快捷方式。包只含标识、版本和依赖，不包含程序、脚本或本机路径。
4. 入口默认位于应用搜索窗口的顶部快捷栏，溢出时在“更多”；右键菜单也可打开。显示模式在设置 → 功能 → 入口显示调整。

停用或移除：在 Leo 的应用模块中操作，只移除入口，不卸载墨笺或删除文档。暂不支持从 Leo 自动转换、无人值守导出，或拖文件直接传入墨笺；请在墨笺窗口内拖入文档并明确预览/确认。

## 开发与验证

`mojian.leoapp.json` 复用 `LeoApplicationPackage/1`；固定包身份用于去重，本机启动信息保留在 Leo 的 `LocalApplication` 配置中。图标引用 `glyph:notes`，由 Leo 按当前主题渲染。

运行 `python -m unittest discover -s tests -p test_leo_integration.py` 检查隔离配置合并、未知字段保留、重复接入、身份冲突、并发变化和保存失败。夹具不读取真实个人配置或启动外部应用。Windows 接入后还应人工点击一次入口确认 GUI 正常出现；未实测的部分不要标为通过。
