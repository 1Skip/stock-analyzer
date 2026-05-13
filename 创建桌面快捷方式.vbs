Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

ProjectPath = FSO.GetParentFolderName(WScript.ScriptFullName)
DesktopPath = WshShell.SpecialFolders("Desktop")
ShortcutPath = DesktopPath & "\股票分析系统.lnk"

Set Shortcut = WshShell.CreateShortcut(ShortcutPath)
Shortcut.TargetPath = ProjectPath & "\start.bat"
Shortcut.WorkingDirectory = ProjectPath
Shortcut.IconLocation = "%SystemRoot%\System32\shell32.dll,21"
Shortcut.Description = "股票分析系统 Web 一键启动"
Shortcut.Save

MsgBox "桌面快捷方式已创建：" & vbCrLf & ShortcutPath & vbCrLf & vbCrLf & _
       "以后双击桌面的“股票分析系统”即可启动。", vbInformation, "创建完成"
