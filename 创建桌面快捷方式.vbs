Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

ProjectPath = FSO.GetParentFolderName(WScript.ScriptFullName)
DesktopPath = WshShell.SpecialFolders("Desktop")
ShortcutPath = DesktopPath & "\Stock Analyzer.lnk"
IconPath = ProjectPath & "\assets\app.ico"

Set Shortcut = WshShell.CreateShortcut(ShortcutPath)
Shortcut.TargetPath = ProjectPath & "\start.bat"
Shortcut.WorkingDirectory = ProjectPath
If FSO.FileExists(IconPath) Then
    Shortcut.IconLocation = IconPath
Else
    Shortcut.IconLocation = "%SystemRoot%\System32\shell32.dll,21"
End If
Shortcut.Description = "Stock Analyzer Web Launcher"
Shortcut.Save

MsgBox "Desktop shortcut created:" & vbCrLf & ShortcutPath & vbCrLf & vbCrLf & _
       "Double-click it to start Stock Analyzer.", vbInformation, "Done"
