' 创建桌面快捷方式
Set WshShell = CreateObject("WScript.Shell")

' 获取桌面路径
strDesktop = WshShell.SpecialFolders("Desktop")
strProgramPath = "C:\Users\skip8\stock_analyzer"

' 创建主快捷方式
Set oShortcut = WshShell.CreateShortcut(strDesktop & "\股票分析系统.lnk")
oShortcut.TargetPath = strProgramPath & "\股票分析系统.bat"
oShortcut.WorkingDirectory = strProgramPath
oShortcut.IconLocation = "%SystemRoot%\System32\shell32.dll,21"
oShortcut.Description = "股票分析系统 - 集成分析个股、热门股票、推荐股票功能"
oShortcut.Save

MsgBox "桌面快捷方式创建成功！" & vbCrLf & vbCrLf & _
       "请在桌面上找到 [股票分析系统] 图标，双击即可启动。" & vbCrLf & vbCrLf & _
       "功能包括：" & vbCrLf & _
       "  - 分析个股 (支持A股/美股/港股)" & vbCrLf & _
       "  - 热门股票排行" & vbCrLf & _
       "  - 智能推荐股票" & vbCrLf & _
       "  - 快速演示" & vbCrLf & _
       "  - 多股对比" & vbCrLf, vbInformation, "创建完成"
