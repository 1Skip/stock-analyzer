Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

ProjectPath = FSO.GetParentFolderName(WScript.ScriptFullName)
DesktopPath = WshShell.SpecialFolders("Desktop")
ShortcutPath = DesktopPath & "\Stock Analyzer.lnk"

Set Shortcut = WshShell.CreateShortcut(ShortcutPath)
Shortcut.TargetPath = ProjectPath & "\start.bat"
Shortcut.WorkingDirectory = ProjectPath
Shortcut.IconLocation = "%SystemRoot%\System32\shell32.dll,21"
Shortcut.Description = "Stock Analyzer Web Launcher"
Shortcut.Save

MsgBox "Desktop shortcut created:" & vbCrLf & ShortcutPath & vbCrLf & vbCrLf & _
       "Double-click it to start Stock Analyzer.", vbInformation, "Done"
