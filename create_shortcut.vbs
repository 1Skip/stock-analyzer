Set WshShell = CreateObject("WScript.Shell")
strDesktop = WshShell.SpecialFolders("Desktop")
strPath = "C:\Users\skip8\stock_analyzer"

Set oShortcut = WshShell.CreateShortcut(strDesktop & "\Stock Analyzer.lnk")
oShortcut.TargetPath = strPath & "\start.bat"
oShortcut.WorkingDirectory = strPath
oShortcut.IconLocation = "%SystemRoot%\System32\shell32.dll,21"
oShortcut.Description = "Stock Analysis System"
oShortcut.Save

MsgBox "Shortcut created on desktop!" & vbCrLf & vbCrLf & _
       "Double-click 'Stock Analyzer' icon to start.", vbInformation, "Done"
