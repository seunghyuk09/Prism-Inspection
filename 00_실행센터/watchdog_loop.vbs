' ===================================================================
' Prism watchdog LOOP - runs watchdog.vbs every 2 minutes, forever.
'  - Keeps the web server (port 10000) alive without admin rights.
'  - Silent (wscript, no window). Auto-started at logon + launched now.
' ===================================================================
Option Explicit
Dim sh, fso, single, q
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
q = Chr(34)
single = fso.GetParentFolderName(WScript.ScriptFullName) & "\watchdog.vbs"
Do
  If fso.FileExists(single) Then
    sh.Run "wscript " & q & single & q, 0, True
  End If
  WScript.Sleep 120000   ' 2 minutes
Loop
